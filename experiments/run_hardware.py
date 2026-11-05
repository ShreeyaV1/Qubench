"""
Run Qubench on a REAL IBM quantum computer (or a realistic noisy copy of one).

Run from the repo root:

  # 1) realistic noisy simulation of an IBM chip - no account needed, works offline
  python experiments/run_hardware.py --fake

  # 2) real IBM hardware (one-time setup first - see README "IBM account")
  python experiments/run_hardware.py

  # 3) if the queue is slow: the script prints a job ID - come back later and fetch it
  python experiments/run_hardware.py --job-id <JOB_ID>

It runs BOTH methods (standard + fair QAOA) on the tiny 6-juror pool (choose 2), then saves:
  results/hardware/<run>.json          counts, job ID, backend, fairness numbers  (= audit receipt)
  results/figures/fig5_hardware.png    ideal simulator vs hardware, per method
Hardware is noisy, so we use 1 QAOA layer (shallower circuit) plus IBM's built-in error
mitigation (dynamical decoupling + Pauli twirling).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from qubench import JuryProblem, fairness_report, get_angles  # noqa: E402
from qubench.core import build_circuit  # noqa: E402

OUT = ROOT / "results" / "hardware"
FIG = ROOT / "results" / "figures"
METHODS = ("standard", "fair")
C_FAIR, C_STANDARD, INK_2, GRID, SURFACE = "#a47a1f", "#8f2633", "#6b5a50", "#e0cfb1", "#f5ead6"


def build_circuits(problem, reps):
    circuits = []
    for m in METHODS:
        qc = build_circuit(problem, get_angles(problem, m, reps))
        qc.measure_all()
        qc.name = m
        circuits.append(qc)
    return circuits


def run(args):
    problem = JuryProblem.from_csv(ROOT / f"data/jurors_{args.pool}.csv", ROOT / "data/targets.csv", args.k)
    circuits = build_circuits(problem, args.reps)
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

    if args.fake:
        from qiskit_aer import AerSimulator
        from qiskit_ibm_runtime.fake_provider import FakeSherbrooke
        backend = AerSimulator.from_backend(FakeSherbrooke())
        backend_name, job_id = "fake_sherbrooke (noisy simulation of a real IBM chip)", None
        isa = generate_preset_pass_manager(optimization_level=3, backend=backend, seed_transpiler=7).run(circuits)
        _report_size(isa)
        result = backend.run(isa, shots=args.shots, seed_simulator=7).result()
        counts = [result.get_counts(i) for i in range(len(isa))]
    else:
        from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
        service = QiskitRuntimeService()
        if args.job_id:
            job = service.job(args.job_id)
            backend_name, job_id = job.backend().name, args.job_id
            print(f"Fetching job {job_id} ... status: {job.status()}")
        else:
            backend = service.backend(args.backend) if args.backend else service.least_busy(
                operational=True, simulator=False, min_num_qubits=problem.n)
            backend_name = backend.name
            isa = generate_preset_pass_manager(optimization_level=3, backend=backend).run(circuits)
            _report_size(isa)
            sampler = Sampler(mode=backend)
            sampler.options.dynamical_decoupling.enable = True     # error mitigation
            sampler.options.twirling.enable_gates = True           # error mitigation
            job = sampler.run(isa, shots=args.shots)
            job_id = job.job_id()
            print(f"Submitted to {backend_name}. JOB ID: {job_id}")
            print("If this takes long, stop it (Ctrl+C) and later run:  "
                  f"python experiments/run_hardware.py --job-id {job_id}")
        result = job.result()
        counts = [pub.data.meas.get_counts() for pub in result]

    reports = {m: fairness_report(problem, c) for m, c in zip(METHODS, counts)}
    record = {
        "backend": backend_name, "job_id": job_id, "shots": args.shots, "qaoa_layers": args.reps,
        "pool": args.pool, "k": args.k,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "results": {m: {"prob_fair_jury": r["prob_optimal"], "fairness_score": r["fairness_score"],
                        "max_over_min": r["max_over_min"],
                        "counts_per_fair_jury": {"-".join(map(str, j)): v
                                                 for j, v in r["counts_per_optimal_jury"].items()}}
                    for m, r in reports.items()},
        "raw_counts": dict(zip(METHODS, counts)),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "fake" if args.fake else "ibm"
    path = OUT / f"{tag}_n{args.pool}_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(record, indent=2, default=str))

    for m, r in reports.items():
        print(f"{m:8s}: lands on a fair jury {r['prob_optimal']:.1%} of the time, "
              f"favouritism {r['max_over_min']:.2f}x, fairness score {r['fairness_score']:.3f}")
    _chart(problem, reports, backend_name, args)
    print(f"Saved {path.relative_to(ROOT)} and results/figures/fig5_hardware{'_fake' if args.fake else ''}.png")


def _report_size(isa):
    for qc in isa:
        twoq = sum(v for k, v in qc.count_ops().items() if k in ("ecr", "cz", "cx"))
        print(f"  {qc.name:8s} circuit on chip: depth {qc.depth()}, two-qubit gates {twoq}")


def _chart(problem, reports, backend_name, args):
    from qubench.core import _ExactSimulator
    optimal, _ = problem.optimal_juries()
    idx = [sum(1 << q for q in j) for j in optimal]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True, facecolor=SURFACE)
    for ax, m, colour in zip(axes, METHODS, (C_STANDARD, C_FAIR)):
        ang = get_angles(problem, m, args.reps)
        p = _ExactSimulator(problem, m).probabilities(ang["gammas"], ang["betas"])[idx]
        ideal = p / p.sum()
        hw = np.array([reports[m]["share_per_optimal_jury"][j] for j in optimal])
        x = np.arange(len(optimal))
        ax.set_facecolor(SURFACE)
        ax.bar(x - 0.2, ideal, 0.38, color=colour, alpha=0.45, label="Ideal simulator")
        ax.bar(x + 0.2, hw, 0.38, color=colour, label="Noisy hardware" if args.fake else "IBM hardware",
               hatch="//", edgecolor=SURFACE)
        ax.axhline(1 / len(optimal), color=INK_2, ls="--", lw=1.1)
        ax.set_xticks(x, ["\n".join(problem.jurors.loc[list(j), "juror_id"]) for j in optimal], fontsize=8.5)
        name = "Standard QAOA" if m == "standard" else "Fair QAOA (Grover mixer)"
        ax.set_title(f"{name}\nfavouritism on hardware: {reports[m]['max_over_min']:.2f}×", loc="left",
                     fontsize=11, fontweight="bold")
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
        ax.grid(axis="y", color=GRID)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, -0.2), ncol=2, fontsize=9)
    axes[0].set_ylabel("Share among the equally fair juries")
    fig.suptitle(f"Simulator vs hardware ({backend_name.split(' (')[0]}), {args.pool} jurors choose {args.k}",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"fig5_hardware{'_fake' if args.fake else ''}.png", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fake", action="store_true", help="noisy simulation of a real IBM chip (no account)")
    ap.add_argument("--job-id", help="fetch results of an earlier hardware job")
    ap.add_argument("--backend", help="specific IBM backend name (default: least busy)")
    ap.add_argument("--pool", type=int, default=6, choices=[6, 8, 12])
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--reps", type=int, default=1, help="QAOA layers (1 = shallowest, best for hardware)")
    ap.add_argument("--shots", type=int, default=4000)
    run(ap.parse_args())
