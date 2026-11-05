"""
Qubench core: turns "pick a jury that looks like the community" into a quantum problem,
solves it with two versions of QAOA, and turns the answer back into a jury.

THE BIG IDEA (plain English)
----------------------------
* Each potential juror is one qubit.  1 = selected, 0 = not selected.
* A "cost" measures how far a jury's mix is from the community's mix.  Lower = fairer.
* Many different juries can tie for the lowest cost ("equally fair juries").
  A truly fair system must pick each of those with the SAME chance.

* Standard QAOA  : finds low-cost juries, but plays favourites among the equally fair ones.
* Grover-Mixer QAOA (we call it "fair"): starts from every jury of the right size at once and
  uses a special "Grover" mixer, which mathematically guarantees that juries with the same
  cost always get the same probability.  Fair problem -> fair algorithm.

Bit-order note: in Qiskit, qubit 0 is the RIGHTMOST character of a measured bitstring.
We always convert to "juror order" (juror 0 first) with `bits_to_selection`.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector
from qiskit.circuit.library import PauliEvolutionGate, RYGate
from qiskit.quantum_info import SparsePauliOp


# ---------------------------------------------------------------------------
# 1. The real-world problem
# ---------------------------------------------------------------------------
@dataclass
class JuryProblem:
    """A pool of jurors, the community's makeup, and how many jurors to pick."""

    jurors: pd.DataFrame          # columns: juror_id, name, + one column per attribute
    targets: pd.DataFrame         # columns: attribute, group, community_share
    k: int                        # jury size
    size_penalty: float = 10.0    # only used by standard QAOA (keeps the jury size right)
    groups: list = field(init=False)

    def __post_init__(self):
        self.jurors = self.jurors.reset_index(drop=True)
        # For every group (e.g. "age_group = 55+"): which jurors are in it, and the target count
        self.groups = []
        for row in self.targets.itertuples():
            members = [i for i, v in enumerate(self.jurors[row.attribute]) if v == row.group]
            self.groups.append((row.attribute, row.group, members, self.k * row.community_share))

    @classmethod
    def from_csv(cls, jurors_csv, targets_csv, k):
        return cls(pd.read_csv(jurors_csv), pd.read_csv(targets_csv), k)

    @property
    def n(self) -> int:
        return len(self.jurors)

    # --- classical cost of a jury (used to check answers) ---------------------------
    def balance_cost(self, selection) -> float:
        """Sum over groups of (jurors picked from group - target)^2.  0 would be perfect."""
        selection = np.asarray(selection)
        return float(sum((selection[m].sum() - t) ** 2 for _, _, m, t in self.groups))

    def all_juries(self):
        """Every possible jury of exactly k people, with its balance cost (small pools only)."""
        out = []
        for combo in itertools.combinations(range(self.n), self.k):
            sel = np.zeros(self.n, dtype=int)
            sel[list(combo)] = 1
            out.append((combo, self.balance_cost(sel)))
        return out

    def optimal_juries(self, tol=1e-9):
        """The juries that tie for the lowest balance cost ("equally fair juries")."""
        juries = self.all_juries()
        best = min(c for _, c in juries)
        return [combo for combo, c in juries if c <= best + tol], best


# ---------------------------------------------------------------------------
# 2. Bridge IN: real problem -> quantum operator (QUBO -> Pauli Z terms)
# ---------------------------------------------------------------------------
def _qubo_terms(problem: JuryProblem, include_size_penalty: bool):
    """Write the cost as  const + sum_i lin[i] x_i + sum_{i<j} quad[i,j] x_i x_j  (x in {0,1})."""
    const, lin, quad = 0.0, np.zeros(problem.n), np.zeros((problem.n, problem.n))

    def add_square(members, target, weight=1.0):
        # weight * (sum_{i in members} x_i - target)^2, using x_i^2 = x_i
        nonlocal const
        const_add = weight * target ** 2
        for i in members:
            lin[i] += weight * (1 - 2 * target)
        for a, b in itertools.combinations(members, 2):
            quad[a, b] += 2 * weight
        const += const_add

    for _, _, members, target in problem.groups:
        add_square(members, target)
    if include_size_penalty:
        add_square(list(range(problem.n)), problem.k, problem.size_penalty)
    return const, lin, quad


def cost_operator(problem: JuryProblem, include_size_penalty: bool) -> SparsePauliOp:
    """Turn the QUBO into a quantum operator using x_i = (1 - Z_i) / 2."""
    const, lin, quad = _qubo_terms(problem, include_size_penalty)
    n = problem.n
    terms = {"": const}

    def add(label_qubits, coeff):
        key = tuple(sorted(label_qubits))
        terms[key] = terms.get(key, 0.0) + coeff

    for i in range(n):                      # lin * (1 - Z_i)/2
        add((), lin[i] / 2)
        add((i,), -lin[i] / 2)
    for i, j in zip(*np.nonzero(quad)):     # quad * (1 - Z_i - Z_j + Z_i Z_j)/4
        q = quad[i, j]
        add((), q / 4)
        add((i,), -q / 4)
        add((j,), -q / 4)
        add((i, j), q / 4)

    sparse = [("Z" * len(k), list(k), v) for k, v in terms.items() if k != "" and abs(v) > 1e-12]
    identity = sum(v for k, v in terms.items() if k in ("", ()))
    sparse.append(("", [], identity))
    return SparsePauliOp.from_sparse_list(sparse, num_qubits=n).simplify()


def dicke_state(n: int, k: int) -> np.ndarray:
    """Equal superposition of every jury with exactly k people (a 'Dicke state') - as a vector."""
    vec = np.zeros(2 ** n, dtype=complex)
    for combo in itertools.combinations(range(n), k):
        vec[sum(1 << q for q in combo)] = 1.0
    return vec / np.linalg.norm(vec)


def _split_and_cyclic_shift(qc: QuantumCircuit, l: int, k: int):
    """One building block of the Bärtschi-Eidenbenz (2019) Dicke-state circuit, on qubits 0..l-1."""
    qc.cx(l - 2, l - 1)
    qc.cry(2 * math.acos(math.sqrt(1 / l)), l - 1, l - 2)
    qc.cx(l - 2, l - 1)
    for i in range(2, k + 1):
        qc.cx(l - 1 - i, l - 1)
        qc.append(RYGate(2 * math.acos(math.sqrt(i / l))).control(2), [l - 1, l - i, l - 1 - i])
        qc.cx(l - 1 - i, l - 1)


def dicke_circuit(n: int, k: int) -> QuantumCircuit:
    """Efficient circuit that prepares the Dicke state (every size-k jury, equally weighted).

    Uses the deterministic construction of Bärtschi & Eidenbenz (2019): O(n*k) gates, far
    shallower than generic state preparation - which matters a lot on real, noisy hardware.
    """
    qc = QuantumCircuit(n, name=f"Dicke({n},{k})")
    qc.x(range(n - k, n))
    for l in range(n, k, -1):
        _split_and_cyclic_shift(qc, l, k)
    for l in range(k, 1, -1):
        _split_and_cyclic_shift(qc, l, l - 1)
    return qc


# ---------------------------------------------------------------------------
# 3. The two quantum circuits (these are what run on IBM hardware)
# ---------------------------------------------------------------------------
def standard_qaoa_circuit(problem: JuryProblem, reps: int) -> QuantumCircuit:
    """Textbook QAOA: start in all possible juries (any size), alternate cost + X-mixer layers."""
    op = cost_operator(problem, include_size_penalty=True)
    gammas, betas = ParameterVector("γ", reps), ParameterVector("β", reps)
    qc = QuantumCircuit(problem.n, name="standard_qaoa")
    qc.h(range(problem.n))
    for layer in range(reps):
        qc.append(PauliEvolutionGate(op, time=gammas[layer]), range(problem.n))   # "cost" step
        qc.rx(2 * betas[layer], range(problem.n))                                 # "mixer" step
    return qc


def fair_qaoa_circuit(problem: JuryProblem, reps: int) -> QuantumCircuit:
    """Grover-Mixer QAOA: start in every jury of size k, alternate cost + Grover-mixer layers.

    Grover mixer = exp(-i β |D><D|), where |D> is the starting (Dicke) state.
    Built as:  S^dagger -> phase on |00..0> -> S,  where S prepares |D>.
    Because this mixer treats all states symmetrically, equally-fair juries ALWAYS keep
    equal probability -> fair sampling is guaranteed by the math.
    """
    n = problem.n
    op = cost_operator(problem, include_size_penalty=False)   # jury size is built in, no penalty
    prep = dicke_circuit(n, problem.k).to_gate(label="Dicke")
    gammas, betas = ParameterVector("γ", reps), ParameterVector("β", reps)

    qc = QuantumCircuit(n, name="fair_qaoa")
    qc.append(prep, range(n))
    for layer in range(reps):
        qc.append(PauliEvolutionGate(op, time=gammas[layer]), range(n))           # "cost" step
        qc.append(prep.inverse(), range(n))                                        # Grover mixer:
        qc.x(range(n))                                                             #   flip to find |0..0>
        qc.mcp(-betas[layer], list(range(n - 1)), n - 1)                           #   phase on it
        qc.x(range(n))
        qc.append(prep, range(n))
    return qc


# ---------------------------------------------------------------------------
# 4. Fast exact simulation (used to TRAIN the angles; matches the circuits above)
# ---------------------------------------------------------------------------
class _ExactSimulator:
    """Statevector maths in numpy - same result as the Qiskit circuits, but much faster for training."""

    def __init__(self, problem: JuryProblem, method: str):
        self.n, self.method = problem.n, method
        idx = np.arange(2 ** self.n)
        bits = (idx[:, None] >> np.arange(self.n)) & 1            # bits[state, qubit]
        self.selections = bits
        self.balance = np.array([problem.balance_cost(b) for b in bits])
        size_pen = problem.size_penalty * (bits.sum(1) - problem.k) ** 2
        self.diag = self.balance + (size_pen if method == "standard" else 0.0)
        if method == "standard":
            self.start = np.full(2 ** self.n, 1 / math.sqrt(2 ** self.n), dtype=complex)
        else:
            self.start = dicke_state(self.n, problem.k)

    def state(self, gammas, betas):
        psi = self.start.copy()
        for g, b in zip(gammas, betas):
            psi = psi * np.exp(-1j * g * self.diag)
            if self.method == "standard":
                rx = np.array([[math.cos(b), -1j * math.sin(b)], [-1j * math.sin(b), math.cos(b)]])
                t = psi.reshape([2] * self.n)
                for ax in range(self.n):
                    t = np.moveaxis(np.tensordot(rx, t, axes=([1], [ax])), 0, ax)
                psi = t.reshape(-1)
            else:
                overlap = np.vdot(self.start, psi)
                psi = psi + (np.exp(-1j * b) - 1) * overlap * self.start
        return psi

    def probabilities(self, gammas, betas):
        return np.abs(self.state(gammas, betas)) ** 2


def train_angles(problem: JuryProblem, method: str, reps: int = 3, restarts: int = 8, seed: int = 0):
    """Find the γ, β angles that make low-cost (fair) juries most likely.

    Objective: maximise the probability of landing on one of the equally-fair (optimal) juries.
    Classical optimiser (COBYLA) + quantum circuit = a 'variational' quantum algorithm.
    """
    sim = _ExactSimulator(problem, method)
    best_cost = sim.balance[sim.selections.sum(1) == problem.k].min()
    is_opt = (np.abs(sim.balance - best_cost) < 1e-9) & (sim.selections.sum(1) == problem.k)

    rng = np.random.default_rng(seed)
    best = None
    for _ in range(restarts):
        x0 = np.concatenate([rng.uniform(0, 1.0, reps), rng.uniform(0, math.pi, reps)])
        obj = lambda x: -sim.probabilities(x[:reps], x[reps:])[is_opt].sum()
        res = minimize(obj, x0, method="COBYLA", options={"maxiter": 400})
        if best is None or res.fun < best.fun:
            best = res
    gammas, betas = best.x[:reps], best.x[reps:]
    return {"method": method, "reps": reps, "gammas": gammas.tolist(), "betas": betas.tolist(),
            "p_optimal": float(-best.fun)}


def bind(circuit: QuantumCircuit, angles: dict) -> QuantumCircuit:
    """Plug trained angles into a circuit."""
    values = {}
    for p in circuit.parameters:
        vec = angles["gammas"] if p.name.startswith("γ") else angles["betas"]
        values[p] = vec[p.index]
    return circuit.assign_parameters(values)


def build_circuit(problem: JuryProblem, angles: dict) -> QuantumCircuit:
    maker = standard_qaoa_circuit if angles["method"] == "standard" else fair_qaoa_circuit
    return bind(maker(problem, angles["reps"]), angles)


# ---------------------------------------------------------------------------
# 5. Bridge OUT: measured bitstrings -> juries, plus fairness metrics
# ---------------------------------------------------------------------------
def bits_to_selection(bitstring: str) -> tuple:
    """Qiskit bitstring (qubit 0 on the right) -> tuple of selected juror indices."""
    return tuple(i for i, b in enumerate(reversed(bitstring)) if b == "1")


def fairness_report(problem: JuryProblem, counts: dict) -> dict:
    """How often each equally-fair jury was drawn, and how fair that spread is.

    fairness_score = normalised Shannon entropy over the equally-fair juries
                     1.0 = perfectly even (fair), 0.0 = always the same jury.
    """
    optimal, best_cost = problem.optimal_juries()
    opt_set = set(optimal)
    tally = {j: 0 for j in optimal}
    total = valid = 0
    for bits, c in counts.items():
        sel = bits_to_selection(bits)
        total += c
        if sel in opt_set:
            tally[sel] += c
            valid += c
    freqs = np.array([tally[j] for j in optimal], dtype=float)
    share = freqs / freqs.sum() if freqs.sum() else freqs
    nz = share[share > 0]
    entropy = float(-(nz * np.log(nz)).sum())
    score = entropy / math.log(len(optimal)) if len(optimal) > 1 else 1.0
    person_rate = np.zeros(problem.n)
    for j, c in tally.items():
        person_rate[list(j)] += c
    person_rate = person_rate / valid if valid else person_rate
    return {
        "optimal_juries": optimal,
        "best_cost": best_cost,
        "counts_per_optimal_jury": dict(zip(optimal, freqs.astype(int).tolist())),
        "share_per_optimal_jury": dict(zip(optimal, share.tolist())),
        "prob_optimal": valid / total if total else 0.0,
        "fairness_score": score,
        "max_over_min": float(freqs.max() / freqs.min()) if freqs.min() > 0 else float("inf"),
        "person_selection_rate": person_rate.tolist(),
    }
