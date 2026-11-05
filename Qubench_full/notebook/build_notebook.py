"""Builds Qubench.ipynb: a self-contained, runnable walkthrough of the whole project."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
core = (ROOT / "qubench" / "core.py").read_text().splitlines()


def lines(a, b):  # 1-indexed inclusive slice of core.py
    return "\n".join(core[a - 1:b]).strip("\n")


def find(prefix):
    return next(i + 1 for i, l in enumerate(core) if l.startswith(prefix))


i_imports = find("from __future__")
i_s1, i_s2, i_s3 = find("class JuryProblem") - 3, find("def _qubo_terms") - 3, find("def standard_qaoa_circuit") - 3
i_s4, i_s5 = find("class _ExactSimulator") - 3, find("def bits_to_selection") - 3
end = len(core)

jurors8 = (ROOT / "data" / "jurors_8.csv").read_text().strip()
jurors12 = (ROOT / "data" / "jurors_12.csv").read_text().strip()
targets = (ROOT / "data" / "targets.csv").read_text().strip()

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = []

cells += [md("""# Qubench ⚖️⚛️
### A fair jury needs a fair algorithm
**IBM Qiskit Fall Fest 2026 · UW Quantum Club**
Team: [Team member 1], [Team member 2], [Team member 3]

Qubench is a bridge from a real justice problem (selecting a jury that is random, representative of the community, and checkable) to a quantum algorithm (QAOA) in Qiskit. A court jury administrator can draw a balanced jury and get an audit receipt without knowing anything about quantum computing.

Along the way we found something important: **the standard QAOA plays favourites** among juries that are equally fair, while a **Grover-mixer QAOA** gives every equally fair jury exactly the same chance.

- Code: https://github.com/ShreeyaV1/Qubench
- Website (live Qiskit when run with `python website/server.py`): see the repository

**This notebook is self-contained.** It needs only `qiskit`, `qiskit-aer`, `numpy`, `scipy`, `pandas` and `matplotlib` (plus `qiskit-ibm-runtime` for the noisy-hardware section). It has been run top to bottom, so every result below is already shown.

**Contents**
1. The problem
2. The data (synthetic people)
3. Bridge in: from fairness rules to a quantum operator
4. Two quantum circuits: standard QAOA vs Grover-mixer QAOA
5. Training and checking the circuits
6. Results: is the algorithm fair?
7. The abstraction: `draw_jury()` with an audit receipt
8. Upload your own juror list
9. Real hardware: what noise does
10. Honest limits and next steps"""),
          md("""## 1. The problem
Canadian juries are supposed to be **random** (nobody can steer them) and **representative** (they look like the community). In 2018, in the case over the 2016 killing of Colten Boushie, a 22-year-old Cree man, a jury with no Indigenous members acquitted the accused after five visibly Indigenous people were removed during selection. Canada abolished peremptory challenges in 2019.

In Ontario today, the province takes everyone registered with OHIP, randomly mails jury questionnaires, places eligible people on a jury roll, and randomly summons them (Ontario *Juries Act*, R.S.O. 1990, c. J.3). That is random, but nothing targets balance, and the lists are kept secret by law, so the public cannot check a draw.

**Our question:** can we pick a jury that is random *and* balanced *and* checkable, and if a quantum computer does the picking, **is the quantum algorithm itself fair?**"""),
          code("""# If needed:  pip install qiskit qiskit-aer qiskit-ibm-runtime numpy scipy pandas matplotlib
import warnings; warnings.filterwarnings("ignore")
import qiskit, qiskit_aer
print("Qiskit", qiskit.__version__, "| Aer", qiskit_aer.__version__)""")]

cells += [md("""## 2. The data
All people are **fictional**. Each pool is deliberately **skewed** (too many people aged 55+, too many from the North), so we can see whether the algorithm fixes the imbalance. The community targets say what a fair jury should look like."""),
          code(f'''import io
import pandas as pd

JURORS_8 = """{jurors8}"""
JURORS_12 = """{jurors12}"""
TARGETS = """{targets}"""

jurors8 = pd.read_csv(io.StringIO(JURORS_8))
jurors12 = pd.read_csv(io.StringIO(JURORS_12))
targets = pd.read_csv(io.StringIO(TARGETS))
display(jurors8)
display(targets)'''),
          code("""# How skewed is the 8-person pool compared with the community?
rows = []
for t in targets.itertuples():
    share = (jurors8[t.attribute] == t.group).mean()
    rows.append({"group": t.group, "in pool": f"{share:.0%}", "community": f"{t.community_share:.0%}"})
pd.DataFrame(rows)""")]

cells += [md("""## 3. Bridge in: from fairness rules to a quantum operator
- **Each juror is one qubit:** measured 1 means selected, 0 means not selected.
- **Cost = how unbalanced a jury is:** for every group (North, 18–34, Woman, …) we take *(jurors picked from the group − target)²* and add them up. Lower is fairer.
- The cost is written as a **QUBO** (only yes/no variables, single terms and pair terms), then converted to a **quantum operator** of Pauli-Z terms using x = (1 − Z)/2.

The next cell holds the problem class; the one after it the QUBO → operator translation."""),
          code(lines(i_imports, i_s1 - 1).replace('"""', "#", 0) + "\nfrom IPython.display import display"),
          code(lines(i_s1, i_s2 - 1)),
          code(lines(i_s2, i_s3 - 1)),
          code("""p8 = JuryProblem(jurors8, targets, k=3)
optimal, best = p8.optimal_juries()
print(f"8 jurors, choose 3: {len(p8.all_juries())} possible juries, {len(optimal)} tie for the fairest (cost {best:.3f})")
op = cost_operator(p8, include_size_penalty=False)
print(f"Quantum cost operator: {op.num_qubits} qubits, {len(op)} Pauli terms")
print(op[:6])""")]

cells += [md("""## 4. Two quantum circuits
**Standard QAOA** starts from every bit-string (any jury size), alternates a *cost* layer and an *X mixer* layer, and uses a penalty to keep the jury size right.

**Grover-mixer QAOA ("fair QAOA")** makes two changes:
1. It starts in a **Dicke state**: an equal superposition of *only* the juries with exactly *k* people. We build it with the efficient Bärtschi–Eidenbenz (2019) circuit.
2. It uses the **Grover mixer** exp(−iβ|D⟩⟨D|), which treats every valid jury symmetrically. Juries with the same cost therefore **always keep exactly the same probability**: fair sampling is guaranteed by the maths."""),
          code(lines(i_s3, i_s4 - 1)),
          code("""# The Dicke-state circuit really prepares every 3-person jury of 8 with equal weight
from qiskit.quantum_info import Statevector
fid = abs(np.vdot(dicke_state(8, 3), Statevector(dicke_circuit(8, 3)).data)) ** 2
print(f"Dicke(8,3) fidelity: {fid:.10f}")
print(dicke_circuit(4, 2).draw("text", fold=110))""")]

cells += [md("""## 5. Training and checking the circuits
QAOA has angles (γ, β) for each layer. A classical optimiser (COBYLA) tunes them to maximise the chance of measuring one of the fairest juries, using an exact statevector calculation for speed. We then check that the **Qiskit circuits give exactly the same probabilities** as that calculation."""),
          code(lines(i_s4, i_s5 - 1)),
          code(lines(i_s5, end)),
          code("""%%time
p12 = JuryProblem(jurors12, targets, k=4)
ANGLES = {}
for name, prob in (("n8", p8), ("n12", p12)):
    for method in ("standard", "fair"):
        ANGLES[(name, method)] = train_angles(prob, method, reps=3)
        print(f"{name} {method:8s} P(lands on a fairest jury) = {ANGLES[(name, method)]['p_optimal']:.1%}")"""),
          code("""# Check: Qiskit circuits == exact calculation
for method in ("standard", "fair"):
    ang = ANGLES[("n8", method)]
    circuit_probs = Statevector(build_circuit(p8, ang)).probabilities()
    exact_probs = _ExactSimulator(p8, method).probabilities(ang["gammas"], ang["betas"])
    print(f"{method:8s} max difference: {np.abs(circuit_probs - exact_probs).max():.1e}")""")]

cells += [md("""## 6. Results: is the algorithm fair?
We run each trained circuit **20,000 times on the Qiskit Aer simulator** and count how often each of the equally fair juries comes out. A fair algorithm picks them all equally often.

**Favouritism** = most-picked fair jury ÷ least-picked fair jury (1.00× is perfectly fair)."""),
          code("""from qiskit import transpile
from qiskit_aer import AerSimulator
backend = AerSimulator()

def sample(problem, angles, shots=20000, seed=11):
    qc = build_circuit(problem, angles); qc.measure_all()
    return backend.run(transpile(qc, backend), shots=shots, seed_simulator=seed).result().get_counts()

REPORTS = {}
rows = []
for name, prob in (("n8", p8), ("n12", p12)):
    for method in ("standard", "fair"):
        rep = fairness_report(prob, sample(prob, ANGLES[(name, method)]))
        REPORTS[(name, method)] = rep
        rows.append({"pool": f"{prob.n} choose {prob.k}", "method": method, "equally fair juries": len(rep["optimal_juries"]),
                     "lands on a fairest jury": f"{rep['prob_optimal']:.0%}", "favouritism": f"{rep['max_over_min']:.2f}x",
                     "fairness score": round(rep["fairness_score"], 3)})
pd.DataFrame(rows)"""),
          code("""import matplotlib.pyplot as plt
C_STD, C_FAIR, INK, SURF = "#8f2633", "#a47a1f", "#301413", "#f5ead6"
rep_s, rep_f = REPORTS[("n12", "standard")], REPORTS[("n12", "fair")]
juries = rep_s["optimal_juries"]
x = np.arange(len(juries)); w = 0.38
fig, ax = plt.subplots(figsize=(11, 4.6), facecolor=SURF); ax.set_facecolor(SURF)
ax.bar(x - w/2, [rep_s["share_per_optimal_jury"][j] for j in juries], w, color=C_STD, label="Standard QAOA")
ax.bar(x + w/2, [rep_f["share_per_optimal_jury"][j] for j in juries], w, color=C_FAIR, label="Fair QAOA (Grover mixer)")
ax.axhline(1/len(juries), color=INK, ls="--", lw=1.2, label="Perfectly fair")
ax.set_xticks(x, ["\\n".join(p12.jurors.loc[list(j), "juror_id"]) for j in juries], fontsize=9)
ax.yaxis.set_major_locator(plt.matplotlib.ticker.MultipleLocator(0.04)); ax.yaxis.set_major_formatter(plt.matplotlib.ticker.PercentFormatter(1.0, decimals=0))
ax.set_ylabel("Chance of being picked"); ax.spines[["top", "right"]].set_visible(False)
ax.set_title(f"12 jurors, choose 4: standard QAOA favours one fair jury {rep_s['max_over_min']:.1f}x more than another", loc="left")
ax.legend(frameon=False, ncol=3, loc="upper left"); plt.tight_layout(); plt.show()"""),
          md("""**What this shows:** among the 9 equally balanced juries, standard QAOA picks some about 3× more often than others. Nobody programmed that bias; it comes from how the X mixer moves probability. The Grover-mixer version is flat (up to sampling noise) **and** lands on a fairest jury far more often.""")]

cells += [md("""## 7. The abstraction: `draw_jury()`
This is what a non-expert uses. They pass a juror table and a jury size; everything quantum is hidden. Each draw keeps the fairest measured juries and picks **one measured shot at random**, so the algorithm's own odds (fair or biased) are preserved, and returns an **audit receipt**."""),
          code("""import hashlib, json
from datetime import datetime, timezone

def draw_jury(jurors: pd.DataFrame, k: int, method: str = "fair", shots: int = 4000, reps: int = 3, angles=None):
    \"\"\"Draw one jury with a quantum circuit and return (jury, receipt).\"\"\"
    problem = JuryProblem(jurors, targets, k)
    angles = angles or train_angles(problem, method, reps=reps)
    seed = int(np.random.default_rng().integers(2**31))
    counts = sample(problem, angles, shots=shots, seed=seed)
    sized = {b: c for b, c in counts.items() if len(bits_to_selection(b)) == k}
    cost = {b: problem.balance_cost(np.isin(np.arange(problem.n), bits_to_selection(b)).astype(int)) for b in sized}
    best = min(cost.values()); finalists = [b for b in sized if cost[b] <= best + 1e-9]
    weights = np.array([sized[b] for b in finalists], float)
    chosen = bits_to_selection(finalists[np.random.default_rng(seed).choice(len(finalists), p=weights / weights.sum())])
    jury = problem.jurors.iloc[list(chosen)]
    receipt = {"method": method, "backend": "Qiskit Aer simulator", "pool_size": problem.n, "jury_size": k,
               "selected_ids": jury["juror_id"].tolist(), "balance_cost": round(best, 4),
               "best_possible_cost": round(problem.optimal_juries()[1], 4), "shots": shots, "simulator_seed": seed,
               "qaoa_angles": {"gammas": [round(v, 4) for v in angles["gammas"]], "betas": [round(v, 4) for v in angles["betas"]]},
               "counts_sha256": hashlib.sha256(json.dumps(counts, sort_keys=True).encode()).hexdigest(),
               "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return jury, receipt

jury, receipt = draw_jury(jurors8, k=3, method="fair", angles=ANGLES[("n8", "fair")])
display(jury)
print(json.dumps(receipt, indent=2))""")]

cells += [md("""## 8. Upload your own juror list
Any court office can use its own list (3 to 12 people, since each juror is one qubit). On the website this is a CSV or Excel upload; here we build a table directly. The circuit is trained for the new list, then drawn."""),
          code("""my_list = pd.DataFrame([
    ["A1", "Maya Testperson", "North", "18-34", "Woman"], ["A2", "Ben Example", "North", "55+", "Man"],
    ["A3", "Zara Sample", "South", "35-54", "Woman"],     ["A4", "Leo Mockname", "East", "55+", "Man"],
    ["A5", "Ivy Placeholder", "West", "18-34", "Woman"],  ["A6", "Sam Fakerson", "North", "55+", "Man"],
    ["A7", "Nina Demo", "East", "35-54", "Woman"],        ["A8", "Raj Notreal", "South", "55+", "Man"],
    ["A9", "Tess Synth", "West", "55+", "Woman"],         ["A10", "Omar Instance", "North", "18-34", "Man"],
], columns=["juror_id", "name", "neighbourhood", "age_group", "gender"])
jury, receipt = draw_jury(my_list, k=4, method="fair")
display(jury)
print("balance cost", receipt["balance_cost"], "| best possible", receipt["best_possible_cost"])""")]

cells += [md("""## 9. Real hardware: what noise does
The fair circuit is much deeper than the standard one. We compile both for a real IBM chip layout and run them on **a noisy simulation of the IBM Sherbrooke chip** (`FakeSherbrooke`), using the 6-person pool and one QAOA layer to keep circuits short.

To run on a **real IBM quantum computer**, set up an IBM Quantum account and run `python experiments/run_hardware.py` from the repository (it uses error mitigation: dynamical decoupling and Pauli twirling)."""),
          code("""JURORS_6 = \"\"\"juror_id,name,neighbourhood,age_group,gender
J01,Hana Mockridge,North,55+,Man
J02,Omar Demoss,South,35-54,Woman
J03,Isla Fauxley,East,18-34,Man
J04,Ravi Notreal,North,55+,Woman
J05,Mei Exampleby,West,55+,Woman
J06,Diego Testwood,North,35-54,Man\"\"\"
p6 = JuryProblem(pd.read_csv(io.StringIO(JURORS_6)), targets, k=2)
try:
    from qiskit_ibm_runtime.fake_provider import FakeSherbrooke
    noisy = AerSimulator.from_backend(FakeSherbrooke())
    rows = []
    for method in ("standard", "fair"):
        ang = train_angles(p6, method, reps=1)
        qc = build_circuit(p6, ang); qc.measure_all()
        tqc = transpile(qc, noisy, optimization_level=3, seed_transpiler=7)
        twoq = sum(v for g, v in tqc.count_ops().items() if g in ("ecr", "cx", "cz"))
        ideal = fairness_report(p6, sample(p6, ang))
        hw = fairness_report(p6, noisy.run(tqc, shots=4000, seed_simulator=7).result().get_counts())
        rows.append({"method": method, "two-qubit gates": twoq, "depth": tqc.depth(),
                     "ideal: favouritism": f"{ideal['max_over_min']:.2f}x", "noisy chip: favouritism": f"{hw['max_over_min']:.2f}x",
                     "ideal: lands on fairest": f"{ideal['prob_optimal']:.0%}", "noisy chip: lands on fairest": f"{hw['prob_optimal']:.0%}"})
    display(pd.DataFrame(rows))
except ImportError:
    print("Install qiskit-ibm-runtime to run the noisy-chip simulation.")"""),
          md("""**Honest finding:** the fair circuit needs about 8× more two-qubit gates (390 vs 46 here). In a perfect simulation it lands on a fairest jury far more often than the standard circuit; on the noisy chip that drops to about 5%, below the standard circuit, so its advantage is gone. The algorithm is provably fair; today's hardware cannot yet run it faithfully. Qubench measures exactly that gap.""")]

cells += [md("""## 10. Honest limits and next steps
**Limits**
- **Small pools only.** Each juror is one qubit, so we stop at 12; a classical computer solves these sizes easily. Our contribution is the bridge and the fairness analysis.
- **Fair juries ≠ equal odds per person.** People who appear in more of the balanced juries are picked more often.
- **Hardware isn't ready.** Noise erases the fair circuit's advantage today.
- **Synthetic people.** We balance neighbourhood, age group and gender, not race directly, and target the pool stage.

**Next steps:** equal odds for every individual; larger pools as hardware improves; error mitigation tuned for the Grover-mixer circuit; certified quantum randomness on real IBM machines.

**References**
- Bärtschi & Eidenbenz (2019), *Deterministic Preparation of Dicke States*; (2020), *Grover Mixers for QAOA*.
- Pelofske et al. (2021), fair sampling with Grover-mixer QAOA on IBM Q backends (arXiv:2101.03258).
- Pelofske (2024), *Biased Degenerate Ground-State Sampling of Small Ising Models with Converged QAOA* (arXiv:2411.05294).
- Flanigan et al. (2021), *Fair algorithms for selecting citizens' assemblies*, Nature 596.
- Ontario *Juries Act*, R.S.O. 1990, c. J.3.""")]

nb = nbf.v4.new_notebook(); nb.cells = cells
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
out = ROOT / "Qubench.ipynb"
nbf.write(nb, out)
print("wrote", out)
