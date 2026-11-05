"""
Qubench web app - what the jury administrator sees.

Run from the repo root:   streamlit run app/app.py
"""

import json
import sys
from io import StringIO
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from qubench import JuryProblem, draw_jury, fairness_report, mix_table, sample_counts  # noqa: E402

FAIR, STANDARD, NEUTRAL, POOL = "#2a78d6", "#eb6834", "#8d8c85", "#1baf7a"
POOLS = {"8 potential jurors (choose 3)": (8, 3), "12 potential jurors (choose 4)": (12, 4),
         "6 potential jurors (choose 2) - hardware size": (6, 2)}
METHOD_LABELS = {"Fair QAOA (Grover mixer) - recommended": "fair", "Standard QAOA": "standard",
                 "Plain random draw (no balancing)": "random"}

st.set_page_config(page_title="Qubench - fair jury selection", page_icon="⚖️", layout="wide")
st.title("⚖️ Qubench")
st.caption("Quantum-fair jury selection · random, representative, and checkable · built with Qiskit")

# ---------------- Sidebar: inputs ----------------
with st.sidebar:
    st.header("1. Juror pool")
    pool_label = st.selectbox("Example pool (synthetic people)", list(POOLS))
    n, k = POOLS[pool_label]
    upload = st.file_uploader("…or upload your own juror list (CSV)", type="csv",
                              help="Columns: juror_id, name, neighbourhood, age_group, gender")
    if upload is not None:
        k = st.number_input("Jury size", min_value=2, max_value=6, value=3)
    st.header("2. Method")
    method = METHOD_LABELS[st.radio("Selection method", list(METHOD_LABELS))]
    shots = st.select_slider("Quantum measurements (shots)", [1000, 2000, 4000, 8000], value=4000)
    st.divider()
    st.caption("All people are fictional. Runs on the Qiskit Aer simulator; see the hardware tab "
               "for real IBM quantum computer results.")

jurors_csv = upload if upload is not None else ROOT / f"data/jurors_{n}.csv"
targets_csv = ROOT / "data/targets.csv"
jurors_df = pd.read_csv(jurors_csv)
if upload is not None:
    upload.seek(0)


@st.cache_data(show_spinner=False)
def cached_counts(jurors_csv_text, k, method, shots, seed):
    problem = JuryProblem(pd.read_csv(StringIO(jurors_csv_text)), pd.read_csv(targets_csv), k)
    counts, _ = sample_counts(problem, method, shots=shots, seed=seed)
    return counts


tab_draw, tab_fair, tab_hw, tab_how = st.tabs(
    ["🎲 Draw a jury", "📊 Is the algorithm fair?", "🖥️ Real hardware", "🔍 How it works"])

# ---------------- Tab 1: draw a jury ----------------
with tab_draw:
    left, right = st.columns([1, 1.3])
    with left:
        st.subheader("Juror pool")
        st.dataframe(jurors_df, hide_index=True, use_container_width=True, height=280)
        go = st.button("⚖️ Draw jury", type="primary", use_container_width=True)
    if go:
        with st.spinner("Building the quantum circuit and measuring it..."):
            counts = None
            if method != "random":
                # measure once (cached); each draw then picks one measured result at random
                counts = cached_counts(jurors_df.to_csv(index=False), k, method, shots, 0)
            res = draw_jury(jurors_csv if upload is None else StringIO(jurors_df.to_csv(index=False)),
                            targets_csv, k, method=method, shots=shots, counts=counts)
            st.session_state["draws"] = st.session_state.get("draws", 0) + 1
            st.session_state["last"] = res
    res = st.session_state.get("last")
    with right:
        if res is None:
            st.info("Choose a pool and method on the left, then press **Draw jury**.")
        else:
            st.subheader("Selected jury")
            st.dataframe(res["jury"], hide_index=True, use_container_width=True)
            r = res["receipt"]
            c1, c2, c3 = st.columns(3)
            c1.metric("Balance cost (lower = fairer)", r["balance_cost"])
            c2.metric("Best possible", r["best_possible_cost"])
            c3.metric("Method", r["method"].split(" (")[0])
            idx = [res["problem"].jurors.index[res["problem"].jurors.juror_id == j][0] for j in r["selected_ids"]]
            mix = pd.DataFrame(mix_table(res["problem"], idx)).melt(
                id_vars=["attribute", "group"], var_name="Who", value_name="Share")
            chart = alt.Chart(mix).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                x=alt.X("group:N", title=None, sort=None, axis=alt.Axis(labelAngle=0)),
                xOffset=alt.XOffset("Who:N", sort=["Community", "Pool", "Jury"]),
                y=alt.Y("Share:Q", axis=alt.Axis(format="%"), title="Share"),
                color=alt.Color("Who:N", sort=["Community", "Pool", "Jury"],
                                scale=alt.Scale(range=[NEUTRAL, POOL, FAIR]), legend=alt.Legend(orient="top")),
                tooltip=["attribute", "group", "Who", alt.Tooltip("Share:Q", format=".0%")],
            ).properties(height=260, title="Community vs pool vs this jury")
            st.altair_chart(chart, use_container_width=True)
            with st.expander("🧾 Audit receipt"):
                st.json(r)
                st.download_button("Download receipt (JSON)", json.dumps(r, indent=2, default=str),
                                   file_name="qubench_receipt.json")

# ---------------- Tab 2: fairness of the algorithm ----------------
with tab_fair:
    st.subheader("A fair jury needs a fair algorithm")
    st.write("Many different juries can be **equally balanced**. A fair system must pick each of them "
             "with the **same chance**. Press the button to measure both quantum methods many times.")
    if st.button("Run fairness test", type="primary"):
        problem = JuryProblem(jurors_df, pd.read_csv(targets_csv), k)
        rows, metrics = [], {}
        with st.spinner("Measuring both quantum circuits..."):
            for m, name in (("standard", "Standard QAOA"), ("fair", "Fair QAOA (Grover mixer)")):
                rep = fairness_report(problem, cached_counts(jurors_df.to_csv(index=False), k, m, 20000, 11))
                metrics[name] = rep
                for jury, share in rep["share_per_optimal_jury"].items():
                    rows.append({"Jury": " · ".join(problem.jurors.loc[list(jury), "juror_id"]),
                                 "Method": name, "Share": share})
        df = pd.DataFrame(rows)
        cols = st.columns(2)
        for col, (name, rep) in zip(cols, metrics.items()):
            col.metric(f"{name}: favouritism", f"{rep['max_over_min']:.2f}×",
                       help="Most-picked fair jury ÷ least-picked fair jury. 1.00× = perfectly fair.")
            col.metric(f"{name}: lands on a fair jury", f"{rep['prob_optimal']:.0%}")
        chart = alt.Chart(df).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            x=alt.X("Jury:N", title="The equally fair juries", axis=alt.Axis(labelAngle=-30)),
            xOffset="Method:N",
            y=alt.Y("Share:Q", axis=alt.Axis(format="%"), title="Chance of being picked"),
            color=alt.Color("Method:N", scale=alt.Scale(domain=["Standard QAOA", "Fair QAOA (Grover mixer)"],
                                                        range=[STANDARD, FAIR]), legend=alt.Legend(orient="top")),
            tooltip=["Jury", "Method", alt.Tooltip("Share:Q", format=".1%")],
        ).properties(height=320)
        rule = alt.Chart(pd.DataFrame({"y": [1 / df["Jury"].nunique()]})).mark_rule(
            strokeDash=[5, 4], color="#5f5e58").encode(y="y:Q")
        st.altair_chart(chart + rule, use_container_width=True)
        st.caption("Dashed line = perfectly fair. Simulated with 20,000 measurements per method.")

# ---------------- Tab 3: hardware ----------------
with tab_hw:
    st.subheader("Running on quantum hardware")
    hw_files = sorted((ROOT / "results" / "hardware").glob("*.json"), key=lambda f: f.stat().st_mtime)
    real = [f for f in hw_files if f.name.startswith("ibm_")]
    show = real[-1] if real else (hw_files[-1] if hw_files else None)
    if show is None:
        st.info("No hardware results yet. Run `python experiments/run_hardware.py --fake` "
                "(or without --fake for a real IBM computer).")
    else:
        rec = json.loads(show.read_text())
        st.write(f"**Backend:** {rec['backend']}  ·  **Job ID:** `{rec['job_id'] or 'n/a (simulation)'}`  ·  "
                 f"**Shots:** {rec['shots']}  ·  **Pool:** {rec['pool']} choose {rec['k']}")
        img = ROOT / "results" / "figures" / ("fig5_hardware.png" if real else "fig5_hardware_fake.png")
        if img.exists():
            st.image(str(img), use_container_width=True)
        st.warning("Honest finding: the fair circuit is about 10× deeper than the standard one. "
                   "On today's noisy chips that noise washes out its fairness advantage. The algorithm "
                   "is provably fair; the hardware is not yet good enough to run it faithfully.")

# ---------------- Tab 4: how it works ----------------
with tab_how:
    st.markdown("""
**1. Bridge in.** Each potential juror becomes one qubit (1 = selected). A *cost* measures how far a
jury's mix (neighbourhood, age, gender) is from the community's mix, squared and added up.

**2. Quantum.** Two versions of QAOA (Quantum Approximate Optimization Algorithm) look for low-cost juries:
- *Standard QAOA* starts from every possible group and nudges toward low cost, but it **plays favourites**
  among juries that are equally fair.
- *Fair QAOA* starts from **every jury of the right size at once** (a "Dicke state") and uses a
  **Grover mixer**, which mathematically guarantees that equally fair juries always get **equal chances**.

**3. Bridge out.** The quantum computer is measured thousands of times. We keep the fairest juries it
produced and pick one measured result at random, which keeps the algorithm's own probabilities.
A receipt records every setting so anyone can check the draw afterwards.

**Honest limits:** small pools only (each juror = a qubit); classical methods already solve this size
easily; fair juries ≠ fair chances for every individual; today's hardware is too noisy for the fair circuit.
""")
