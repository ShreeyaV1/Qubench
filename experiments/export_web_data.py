"""
Export real Qiskit results for the static website (website/index.html).

For every pool (6/8/12 jurors) and both quantum methods, this runs the trained QAOA
circuit on the Qiskit Aer simulator for 20,000 shots and saves the measurement counts.
The website then draws juries from these real measurements.

Run from the repo root:   python experiments/export_web_data.py
"""
import json, sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from qubench import JuryProblem, get_angles, sample_counts            # noqa: E402
from qubench.core import bits_to_selection                             # noqa: E402

POOLS = [(8, 3, 3), (12, 4, 3), (6, 2, 1)]      # (pool size, jury size, QAOA layers)
targets = pd.read_csv(ROOT / "data/targets.csv")
out = {"targets": targets.to_dict(orient="records"), "pools": {}}
for n, k, reps in POOLS:
    jurors = pd.read_csv(ROOT / f"data/jurors_{n}.csv")
    problem = JuryProblem(jurors, targets, k)
    optimal, best = problem.optimal_juries()
    entry = {"n": n, "k": k, "jurors": jurors.to_dict(orient="records"),
             "optimal": [list(j) for j in optimal], "best_cost": best, "methods": {}}
    for method in ("standard", "fair"):
        counts, angles = sample_counts(problem, method, shots=20000, seed=11, reps=reps)
        # store as {"0-3-5": count} using juror indices (bit order already decoded)
        sel = {}
        for bits, c in counts.items():
            key = "-".join(map(str, bits_to_selection(bits)))
            sel[key] = sel.get(key, 0) + c
        entry["methods"][method] = {"counts": sel, "shots": 20000, "angles": angles,
                                    "backend": "Qiskit Aer simulator"}
        print(f"n={n} {method}: {len(sel)} distinct outcomes")
    out["pools"][str(n)] = entry

hw = sorted((ROOT / "results/hardware").glob("*.json"), key=lambda f: f.stat().st_mtime)
if hw:
    rec = json.loads(hw[-1].read_text())
    out["hardware"] = {k: rec[k] for k in ("backend", "job_id", "shots", "qaoa_layers", "pool", "k", "results")}
(ROOT / "website" / "qiskit_results.json").write_text(json.dumps(out))
print("saved website/qiskit_results.json")
