"""
Qubench public API - the "abstraction" a non-expert uses.

    from qubench import draw_jury
    result = draw_jury("data/jurors_8.csv", "data/targets.csv", k=3, method="fair")
    print(result["jury"])        # the selected jurors
    print(result["receipt"])     # audit receipt

The user never touches qubits, circuits or angles.  Under the hood:
  real problem -> QUBO -> quantum circuit (QAOA) -> run on simulator or IBM hardware
  -> measured bitstrings -> a jury + fairness report + receipt.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from qiskit import transpile
from qiskit_aer import AerSimulator

from .core import (JuryProblem, bits_to_selection, build_circuit, fairness_report,
                   train_angles)

ANGLE_DIR = Path(__file__).resolve().parent.parent / "results" / "angles"
METHODS = {"fair": "Fair QAOA (Grover mixer)", "standard": "Standard QAOA", "random": "Plain random draw"}


def get_angles(problem: JuryProblem, method: str, reps: int = 3, retrain: bool = False) -> dict:
    """Load trained angles from results/angles/ (or train and save them the first time)."""
    ANGLE_DIR.mkdir(parents=True, exist_ok=True)
    data_id = hashlib.sha1((problem.jurors.to_csv() + problem.targets.to_csv()).encode()).hexdigest()[:8]
    path = ANGLE_DIR / f"{method}_n{problem.n}_k{problem.k}_p{reps}_{data_id}.json"
    if path.exists() and not retrain:
        return json.loads(path.read_text())
    angles = train_angles(problem, method, reps=reps)
    path.write_text(json.dumps(angles, indent=2))
    return angles


def sample_counts(problem: JuryProblem, method: str, shots: int = 4000, seed: int | None = None,
                  reps: int = 3) -> tuple[dict, dict]:
    """Run the chosen quantum circuit on the local Qiskit Aer simulator and return the counts."""
    angles = get_angles(problem, method, reps)
    qc = build_circuit(problem, angles)
    qc.measure_all()
    backend = AerSimulator(seed_simulator=seed)
    job = backend.run(transpile(qc, backend, optimization_level=1), shots=shots)
    return job.result().get_counts(), angles


def draw_jury(jurors_csv, targets_csv, k: int, method: str = "fair", shots: int = 4000,
              seed: int | None = None, counts: dict | None = None, backend_name: str = "aer_simulator"):
    """Draw one jury.

    method : "fair" (Grover-mixer QAOA), "standard" (textbook QAOA) or "random" (no balancing)
    counts : optional - pass counts from a real IBM hardware run to draw from those instead
    """
    problem = JuryProblem.from_csv(jurors_csv, targets_csv, k)
    rng = np.random.default_rng(seed)
    angles = None

    if method == "random":
        chosen = tuple(sorted(rng.choice(problem.n, size=k, replace=False).tolist()))
        counts = None
    else:
        if counts is None:
            counts, angles = sample_counts(problem, method, shots, seed)
        # Keep only measured juries of the right size, then the fairest ones that were measured.
        sized = {b: c for b, c in counts.items() if len(bits_to_selection(b)) == k}
        if not sized:
            raise RuntimeError("No valid jury was measured - try more shots.")
        costs = {b: problem.balance_cost(_sel_vector(problem.n, bits_to_selection(b))) for b in sized}
        best = min(costs.values())
        finalists = [b for b in sized if costs[b] <= best + 1e-9]
        # Pick ONE measured shot at random (weighted by how often it was measured).
        # This keeps the quantum algorithm's own probabilities - fair or biased - intact.
        weights = np.array([sized[b] for b in finalists], dtype=float)
        chosen_bits = finalists[rng.choice(len(finalists), p=weights / weights.sum())]
        chosen = bits_to_selection(chosen_bits)

    jury = problem.jurors.iloc[list(chosen)].reset_index(drop=True)
    selection = _sel_vector(problem.n, chosen)
    receipt = {
        "method": METHODS[method],
        "backend": backend_name if method != "random" else "numpy RNG",
        "jury_size": k,
        "pool_size": problem.n,
        "selected_ids": jury["juror_id"].tolist(),
        "balance_cost": round(problem.balance_cost(selection), 4),
        "best_possible_cost": round(problem.optimal_juries()[1], 4),
        "shots": shots if method != "random" else None,
        "angles": angles,
        "counts_sha256": hashlib.sha256(json.dumps(counts, sort_keys=True).encode()).hexdigest()
        if counts else None,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return {"jury": jury, "receipt": receipt, "counts": counts,
            "report": fairness_report(problem, counts) if counts else None, "problem": problem}


def mix_table(problem: JuryProblem, selection_idx) -> "list[dict]":
    """Community vs pool vs jury share for every group - used for the comparison chart."""
    rows = []
    n_sel = len(selection_idx)
    for attr, group, members, target in problem.groups:
        rows.append({
            "attribute": attr, "group": group,
            "Community": target / problem.k,
            "Pool": len(members) / problem.n,
            "Jury": len(set(members) & set(selection_idx)) / n_sel,
        })
    return rows


def _sel_vector(n, idx):
    v = np.zeros(n, dtype=int)
    v[list(idx)] = 1
    return v
