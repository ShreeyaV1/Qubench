"""
Qubench experiments - produces every chart and number used in the pitch.

Run from the repo root:   python experiments/run_experiments.py
Outputs:
  results/angles/*.json          trained QAOA angles (reused by the app + hardware script)
  results/figures/*.png          charts for the slides
  results/summary.json           all the numbers
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from qubench import JuryProblem, fairness_report, get_angles, mix_table, sample_counts  # noqa: E402
from qubench.core import _ExactSimulator  # noqa: E402

FIG = ROOT / "results" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

# Colours (validated colour-blind-safe pair) - each method keeps its colour in every chart
C_FAIR, C_STANDARD, C_NEUTRAL, C_POOL = "#2a78d6", "#eb6834", "#8d8c85", "#1baf7a"
INK, INK_2, GRID, SURFACE = "#1f1f1e", "#5f5e58", "#e6e5e0", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "text.color": INK, "font.size": 11, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.axisbelow": True, "legend.frameon": False,
})

CASES = [(8, 3), (12, 4)]
REPS = 3


def exact_shares(problem, method, angles):
    """Ideal (noise-free) probability of each equally-fair jury, normalised among them."""
    sim = _ExactSimulator(problem, method)
    p = sim.probabilities(angles["gammas"], angles["betas"])
    optimal, _ = problem.optimal_juries()
    idx = [sum(1 << q for q in j) for j in optimal]
    raw = p[idx]
    return optimal, raw / raw.sum(), raw.sum()


def fairness_score(shares):
    nz = shares[shares > 0]
    return float(-(nz * np.log(nz)).sum() / np.log(len(shares))) if len(shares) > 1 else 1.0


def jury_label(problem, jury):
    return "\n".join(problem.jurors.loc[list(jury), "juror_id"])


def chart_who_gets_picked(problem, optimal, shares, n, k):
    x = np.arange(len(optimal))
    w = 0.38
    fig, ax = plt.subplots(figsize=(max(8, 0.9 * len(optimal) + 3), 5))
    ax.bar(x - w / 2 - 0.01, shares["standard"], w, color=C_STANDARD, label="Standard QAOA")
    ax.bar(x + w / 2 + 0.01, shares["fair"], w, color=C_FAIR, label="Fair QAOA (Grover mixer)")
    ax.axhline(1 / len(optimal), color=INK_2, ls="--", lw=1.2)
    ax.set_xlim(-0.6, len(optimal) - 0.4)
    ax.text(len(optimal) - 0.35, 1 / len(optimal), "perfectly\nfair", va="center", ha="left",
            color=INK_2, fontsize=9.5, clip_on=False)
    ax.set_xticks(x, [jury_label(problem, j) for j in optimal], fontsize=8.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_ylabel("Chance of being picked\n(among the equally fair juries)")
    ax.set_xlabel(f"The {len(optimal)} equally fair juries (juror IDs)")
    ratio = shares["standard"].max() / shares["standard"].min()
    ax.set_title(f"Who gets picked? {n} jurors, choose {k}\n"
                 f"Standard QAOA favours one fair jury {ratio:.1f}× more than another.\n"
                 f"Fair QAOA treats all of them equally.", loc="left", fontsize=11.5)
    ax.legend(loc="lower left", ncol=2, bbox_to_anchor=(0, 1.0), borderaxespad=0.2)
    ax.set_title(ax.get_title(loc="left"), loc="left", fontsize=11.5, pad=30)
    fig.tight_layout()
    path = FIG / f"fig1_who_gets_picked_n{n}.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def chart_summary(summary):
    labels = [f"{n} jurors\nchoose {k}" for n, k in CASES]
    x = np.arange(len(CASES))
    w = 0.36
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for ax, key, title in [(axes[0], "p_fair_jury", "How often it lands on a fair jury\n(higher = better)"),
                           (axes[1], "max_over_min", "Favouritism: most-picked ÷ least-picked\nfair jury (1.0× = perfectly fair)")]:
        std = [summary[f"n{n}"]["standard"][key] for n, _ in CASES]
        fair = [summary[f"n{n}"]["fair"][key] for n, _ in CASES]
        b1 = ax.bar(x - w / 2 - 0.01, std, w, color=C_STANDARD, label="Standard QAOA")
        b2 = ax.bar(x + w / 2 + 0.01, fair, w, color=C_FAIR, label="Fair QAOA (Grover mixer)")
        for bars in (b1, b2):
            for b in bars:
                v = b.get_height()
                ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.0%}" if key == "p_fair_jury" else f"{v:.1f}×",
                        ha="center", va="bottom", fontsize=9.5, color=INK)
        ax.set_xticks(x, labels)
        ax.set_title(title, loc="left", fontsize=11.5)
        ax.set_ylim(0, 1.12 if key == "p_fair_jury" else max(std) * 1.2)
        if key == "max_over_min":
            ax.axhline(1.0, color=INK_2, ls="--", lw=1.2)
        if key == "p_fair_jury":
            ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    axes[0].legend(loc="upper right")
    fig.tight_layout()
    path = FIG / "fig2_summary.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def chart_person_rate(problem, report, n, k):
    rate = np.array(report["person_selection_rate"])
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.bar(problem.jurors["juror_id"], rate, color=C_FAIR, width=0.6)
    ax.axhline(k / n, color=INK_2, ls="--", lw=1.2)
    ax.text(n - 0.6, k / n, f"  equal chance ({k}/{n})", va="bottom", ha="right", color=INK_2, fontsize=10)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_ylabel("Chance this person is selected")
    ax.set_title("Honest limit: fair juries ≠ fair chances for every individual\n"
                 "(people who appear in more of the balanced juries get picked more often)", loc="left",
                 fontsize=11)
    fig.tight_layout()
    path = FIG / f"fig3_individual_chances_n{n}.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def chart_mix(problem, jury_idx, n, k):
    rows = mix_table(problem, jury_idx)
    labels = [r["group"] for r in rows]
    x = np.arange(len(rows))
    w = 0.27
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.bar(x - w - 0.02, [r["Community"] for r in rows], w, color=C_NEUTRAL, label="Community")
    ax.bar(x, [r["Pool"] for r in rows], w, color=C_POOL, label="Juror pool (skewed)")
    ax.bar(x + w + 0.02, [r["Jury"] for r in rows], w, color=C_FAIR, label="Qubench jury")
    ax.set_xticks(x, labels)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_title(f"Skewed pool in, balanced jury out ({n} jurors, choose {k})", loc="left")
    ax.legend(loc="upper left", ncol=3, bbox_to_anchor=(0, -0.1))
    fig.tight_layout()
    path = FIG / f"fig4_balance_n{n}.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def main():
    summary = {}
    for n, k in CASES:
        problem = JuryProblem.from_csv(ROOT / f"data/jurors_{n}.csv", ROOT / "data/targets.csv", k)
        optimal, best = problem.optimal_juries()
        case, shares = {"n": n, "k": k, "num_equally_fair_juries": len(optimal), "best_cost": best}, {}
        for method in ("standard", "fair"):
            angles = get_angles(problem, method, REPS)
            opt, sh, p_opt = exact_shares(problem, method, angles)
            shares[method] = sh
            counts, _ = sample_counts(problem, method, shots=20000, seed=11)   # measured check
            measured = fairness_report(problem, counts)
            case[method] = {
                "p_fair_jury": float(p_opt), "fairness_score": fairness_score(sh),
                "max_over_min": float(sh.max() / sh.min()),
                "measured_p_fair_jury": measured["prob_optimal"],
                "measured_fairness_score": measured["fairness_score"],
                "measured_max_over_min": measured["max_over_min"],
            }
            if method == "fair":
                fair_report = measured
            print(f"n={n:2d} {method:8s}  P(fair jury)={p_opt:.1%}  fairness={fairness_score(sh):.3f}  "
                  f"max/min={sh.max() / sh.min():.2f}   | measured (20k shots): "
                  f"P={measured['prob_optimal']:.1%} fairness={measured['fairness_score']:.3f}")
        summary[f"n{n}"] = case
        chart_who_gets_picked(problem, optimal, shares, n, k)
        chart_person_rate(problem, fair_report, n, k)
        chart_mix(problem, optimal[0], n, k)
    chart_summary(summary)
    (ROOT / "results" / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nCharts saved to {FIG}")


if __name__ == "__main__":
    main()
