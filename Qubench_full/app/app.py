"""
Qubench web app - what the jury administrator sees.

Run from the repo root:   streamlit run app/app.py
Optional: put a courtroom photo at app/assets/hero.jpg and the hero uses it.
"""

import base64
import html
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

# Palette (Old Library). Chart pair validated for colour-blind separation on parchment.
WALNUT, OXBLOOD, BURGUNDY = "#302622", "#67343a", "#7d0e22"
TOBACCO, AGED, PARCH, CARD = "#9a704f", "#d4be9d", "#ede2cf", "#f5ead6"
BIASED, FAIR = "#8f2633", "#a47a1f"          # standard QAOA / skewed pool  vs  fair QAOA / jury
INK_2 = "#6b5a50"

POOLS = {"8 potential jurors (choose 3)": (8, 3), "12 potential jurors (choose 4)": (12, 4),
         "6 potential jurors (choose 2) · hardware size": (6, 2)}
METHOD_LABELS = {"Fair QAOA (Grover mixer) · recommended": "fair", "Standard QAOA": "standard",
                 "Plain random draw (no balancing)": "random"}

st.set_page_config(page_title="Qubench · fair jury selection", page_icon="⚖️", layout="wide")

# ---------------- Styling ----------------
hero_img = ROOT / "app" / "assets" / "hero.jpg"
hero_bg = (f"url('data:image/jpeg;base64,{base64.b64encode(hero_img.read_bytes()).decode()}') center/cover"
           if hero_img.exists() else
           "radial-gradient(ellipse 80% 70% at 60% 30%, #5e2a31 0%, #3b1a1e 45%, #1f1214 100%)")

CSS = f"""
<link href="https://fonts.googleapis.com/css2?family=Anton&family=EB+Garamond:ital@1&family=Hanken+Grotesk:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  .stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp button, .stApp textarea,
  .stApp [data-baseweb="select"] div {{ font-family: "Hanken Grotesk", system-ui, sans-serif; }}
  [data-testid="stHeader"] {{ background: transparent; height: 0; }}
  [data-testid="stAppViewContainer"] {{ background: {PARCH}; }}
  .block-container {{ max-width: 1180px; padding-top: 1.2rem; padding-bottom: 4rem; }}
  h1, h2, h3, .anton {{ font-family: "Anton", Impact, sans-serif !important; font-weight: 400 !important;
                        text-transform: uppercase; letter-spacing: .01em; color: {WALNUT}; }}
  h2 {{ font-size: 2.2rem !important; }}
  h3 {{ font-size: 1.7rem !important; }}

  /* hero */
  .hero {{ position: relative; border-radius: 14px; overflow: hidden; padding: 30px 34px 40px;
           min-height: 560px; display: flex; flex-direction: column; justify-content: space-between;
           background: {hero_bg}; color: #fff5e1; }}
  .hero::before {{ content: ""; position: absolute; inset: 0;
           background: linear-gradient(180deg, rgba(31,18,20,.55) 0%, rgba(31,18,20,.25) 40%, rgba(31,18,20,.75) 100%); }}
  .hero > * {{ position: relative; }}
  .hero .bar {{ display: flex; justify-content: space-between; font-size: 15px; letter-spacing: .32em; color: {AGED}; }}
  .hero h1 {{ font-size: clamp(64px, 10vw, 150px) !important; line-height: .92 !important; margin: 60px 0 0 !important;
              color: #fff5e1 !important; padding: 0 !important; }}
  .hero h1 .mid {{ color: {AGED}; }}
  .hero .foot {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; margin-top: 46px; flex-wrap: wrap; }}
  .hero .sub {{ font-family: "EB Garamond", Georgia, serif; font-style: italic; font-size: 30px; line-height: 1.3;
                color: #fff5e1; max-width: 26ch; margin: 0; }}
  .hero a.cta {{ background: {AGED}; color: {WALNUT} !important; text-decoration: none; font-weight: 500;
                 font-size: 18px; padding: 16px 34px; border-radius: 3px; }}
  .hero a.cta:hover {{ background: #e0cdaf; }}

  /* cards */
  .st-key-controls {{ background: {CARD}; border: 1px solid #d9c7a8; border-radius: 6px; padding: 26px 30px 18px; }}
  .st-key-results {{ border: 1px solid #d4c2a2; border-radius: 6px; padding: 26px 30px; min-height: 340px;
     background-color: {CARD};
     background-image: linear-gradient(#e3d3b7 1px, transparent 1px), linear-gradient(90deg, #e3d3b7 1px, transparent 1px);
     background-size: 38px 38px; }}
  .empty {{ text-align: center; color: {INK_2}; font-size: 19px; padding: 120px 0; }}
  .note {{ color: {INK_2}; font-size: 15px; border-top: 1px solid #d9c7a8; padding-top: 14px; margin-top: 6px; }}
  .honest {{ background: {CARD}; border-left: 4px solid {BURGUNDY}; padding: 14px 18px; border-radius: 3px; color: {WALNUT}; }}

  /* tables */
  table.qb {{ width: 100%; border-collapse: collapse; background: {CARD}; border: 1px solid #d9c7a8; font-size: 16px; }}
  table.qb th {{ background: #e6d6ba; color: {INK_2}; font-weight: 500; text-align: left; letter-spacing: .03em;
                 padding: 12px 14px; text-transform: uppercase; font-size: 14px; }}
  table.qb td {{ padding: 11px 14px; border-top: 1px solid #e0cfb1; color: {WALNUT}; }}
  table.qb th, table.qb td {{ border-left: none !important; border-right: none !important; }}
  table.qb td.id {{ font-family: ui-monospace, Menlo, monospace; font-size: 14px; }}

  /* buttons */
  .stButton > button {{ border-radius: 3px; min-height: 52px; }}
  .stButton > button p {{ font-size: 18px !important; font-weight: 500; }}
  .stButton > button[kind="primary"] {{ background: {BURGUNDY}; border: 0; color: #fff5e1; }}
  .stButton > button[kind="primary"]:hover {{ background: #951a30; }}

  /* tabs as a segmented control */
  .stTabs [role="tablist"] {{ background: #e6d8bf; border-radius: 6px; padding: 5px; gap: 2px; width: fit-content; border: 0; }}
  .stTabs [role="tab"] {{ padding: 10px 22px !important; border-radius: 4px; color: {INK_2}; border: 0 !important; }}
  .stTabs [role="tab"] p {{ font-size: 17px !important; }}
  .stTabs [role="tab"][aria-selected="true"] {{ background: {CARD}; color: {WALNUT}; box-shadow: 0 1px 2px rgba(48,38,34,.12); }}
  .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none !important; }}
  /* framed three-card section (How it works) */
  .label {{ color: #b0503f; font-size: 19px; letter-spacing: .02em; display: inline-block;
            border-bottom: 1.5px solid #b0503f; padding-bottom: 2px; margin: 8px 0 10px; }}
  .lead {{ color: {WALNUT}; font-size: 18px; max-width: 60ch; margin-bottom: 22px; }}
  .frame {{ background: #4a2c1e; border-radius: 10px; padding: 12px; display: grid;
            grid-template-columns: repeat(3, 1fr); gap: 10px; }}
  .frame .card {{ background: {PARCH}; border-radius: 4px; padding: 26px 24px 28px; }}
  .frame .card .step {{ color: #b0503f; font-size: 15px; margin-bottom: 6px; }}
  .frame .card h4 {{ font-family: "Anton", Impact, sans-serif !important; font-weight: 400; text-transform: uppercase;
                     font-size: 34px; line-height: 1; color: {WALNUT}; margin: 0 0 14px; padding: 0; }}
  .frame .card p {{ color: {WALNUT}; font-size: 16px; line-height: 1.5; margin: 0; }}
  @media (max-width: 800px) {{ .frame {{ grid-template-columns: 1fr; }} }}
  [data-testid="stMetricValue"], [data-testid="stMetricValue"] div {{ font-family: "Anton", Impact, sans-serif !important; font-weight: 400; color: {WALNUT}; }}
  [data-testid="stMetricLabel"] p {{ color: {INK_2}; }}
</style>
"""
# Streamlit's markdown renderer ends an HTML block at a blank line, so strip them.
st.markdown("\n".join(line for line in CSS.splitlines() if line.strip()), unsafe_allow_html=True)

# ---------------- Hero ----------------
st.markdown("""
<section class="hero">
  <div class="bar"><span>⚖ QUBENCH</span><span>QISKIT FALL FEST 2026</span></div>
  <h1>A fair jury<br><span class="mid">needs a fair</span><br>algorithm</h1>
  <div class="foot">
    <p class="sub">Quantum-fair jury selection: random, representative, and checkable.</p>
    <a class="cta" href="#controls" target="_self">Take the bench</a>
  </div>
</section>
<div id="controls"></div>
""", unsafe_allow_html=True)
st.write("")


def table_html(df: pd.DataFrame) -> str:
    cols = ["juror_id", "name", "neighbourhood", "age_group", "gender"]
    heads = {"juror_id": "Juror ID", "name": "Name", "neighbourhood": "Neighbourhood",
             "age_group": "Age group", "gender": "Gender"}
    rows = "".join(
        "<tr>" + "".join(f'<td class="{"id" if c == "juror_id" else ""}">{html.escape(str(r[c]))}</td>' for c in cols)
        + "</tr>" for _, r in df.iterrows())
    return f'<table class="qb"><tr>{"".join(f"<th>{heads[c]}</th>" for c in cols)}</tr>{rows}</table>'


def style_chart(chart):
    return (chart.configure(background="transparent", font="Hanken Grotesk")
            .configure_view(stroke=None)
            .configure_axis(labelColor=INK_2, titleColor=INK_2, gridColor="#e0cfb1", domainColor="#c9b393",
                            tickColor="#c9b393", labelFontSize=13, titleFontSize=13)
            .configure_legend(labelColor=WALNUT, titleColor=INK_2, labelFontSize=14, orient="top")
            .configure_title(color=WALNUT, fontSize=16, anchor="start"))


# ---------------- Controls card ----------------
with st.container(key="controls"):
    st.markdown("### 1. Juror pool")
    pool_label = st.selectbox("Example pool", list(POOLS), label_visibility="collapsed")
    n, k = POOLS[pool_label]
    upload = st.file_uploader("…or upload your own list (CSV: juror_id, name, neighbourhood, age_group, gender)",
                              type="csv")
    if upload is not None:
        k = st.number_input("Jury size", min_value=2, max_value=6, value=3)
    st.markdown("### 2. Method")
    method = METHOD_LABELS[st.radio("Selection method", list(METHOD_LABELS), label_visibility="collapsed")]
    shots = st.selectbox("Quantum measurements (shots)", [1000, 2000, 4000, 8000], index=2,
                         format_func=lambda v: f"{v:,}")
    st.markdown('<div class="note">All people are fictional. Circuits run on the Qiskit Aer simulator; '
                'see the hardware tab for IBM chip results.</div>', unsafe_allow_html=True)

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


st.write("")
tab_draw, tab_fair, tab_hw, tab_how = st.tabs(["Draw a jury", "Is the algorithm fair?", "Real hardware", "How it works"])

# ---------------- Tab 1: draw a jury ----------------
with tab_draw:
    st.markdown("## Juror pool")
    st.markdown(table_html(jurors_df), unsafe_allow_html=True)
    st.write("")
    go = st.button("⚖  Draw jury", type="primary", width="stretch")
    if go:
        with st.spinner("Building the quantum circuit and measuring it…"):
            counts = None
            if method != "random":
                # measure once (cached); each draw then picks one measured result at random
                counts = cached_counts(jurors_df.to_csv(index=False), k, method, shots, 0)
            res = draw_jury(StringIO(jurors_df.to_csv(index=False)), targets_csv, k,
                            method=method, shots=shots, counts=counts)
            st.session_state["last"] = res
    st.write("")
    res = st.session_state.get("last")
    with st.container(key="results"):
        if res is None:
            st.markdown('<div class="empty">Choose a pool and method, then press <b>Draw jury</b>.</div>',
                        unsafe_allow_html=True)
        else:
            r = res["receipt"]
            st.markdown("## Selected jury")
            st.markdown(table_html(res["jury"]), unsafe_allow_html=True)
            st.write("")
            c1, c2, c3 = st.columns(3)
            c1.metric("Balance cost (lower is fairer)", r["balance_cost"])
            c2.metric("Best possible", r["best_possible_cost"])
            c3.metric("Method", r["method"].split(" (")[0])
            ids = list(res["problem"].jurors["juror_id"])
            idx = [ids.index(j) for j in r["selected_ids"]]
            mix = pd.DataFrame(mix_table(res["problem"], idx))
            bars = mix.melt(id_vars=["attribute", "group", "Community"], value_vars=["Pool", "Jury"],
                            var_name="Who", value_name="Share")
            bars["Who"] = bars["Who"].map({"Pool": "Juror pool (skewed)", "Jury": "This jury"})
            order = ["Juror pool (skewed)", "This jury"]
            base = alt.Chart(bars).encode(x=alt.X("group:N", title=None, sort=None, axis=alt.Axis(labelAngle=0)))
            bar = base.mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, size=26).encode(
                xOffset=alt.XOffset("Who:N", sort=order),
                y=alt.Y("Share:Q", axis=alt.Axis(format="%"), title="Share"),
                color=alt.Color("Who:N", sort=order, scale=alt.Scale(domain=order, range=[BIASED, FAIR]), title=None),
                tooltip=["attribute", "group", "Who", alt.Tooltip("Share:Q", format=".0%")])
            target = alt.Chart(mix).mark_tick(color=WALNUT, thickness=3, size=60).encode(
                x=alt.X("group:N", sort=None), y="Community:Q",
                tooltip=["group", alt.Tooltip("Community:Q", format=".0%", title="Community target")])
            st.altair_chart(style_chart((bar + target).properties(
                height=280, title="Pool vs this jury (dark line = the community's real share)")), width="stretch")
            with st.expander("🧾 Audit receipt"):
                st.json(r)
                st.download_button("Download receipt (JSON)", json.dumps(r, indent=2, default=str),
                                   file_name="qubench_receipt.json")

# ---------------- Tab 2: fairness of the algorithm ----------------
with tab_fair:
    st.markdown("## A fair jury needs a fair algorithm")
    st.write("Many different juries can be **equally balanced**. A fair system must pick each of them with the "
             "**same chance**. Press the button to measure both quantum methods 20,000 times.")
    if st.button("Run fairness test", type="primary"):
        problem = JuryProblem(jurors_df, pd.read_csv(targets_csv), k)
        rows, metrics = [], {}
        with st.spinner("Measuring both quantum circuits…"):
            for m, name in (("standard", "Standard QAOA"), ("fair", "Fair QAOA (Grover mixer)")):
                rep = fairness_report(problem, cached_counts(jurors_df.to_csv(index=False), k, m, 20000, 11))
                metrics[name] = rep
                for jury, share in rep["share_per_optimal_jury"].items():
                    rows.append({"Jury": " · ".join(problem.jurors.loc[list(jury), "juror_id"]),
                                 "Method": name, "Share": share})
        df = pd.DataFrame(rows)
        cols = st.columns(4)
        for i, (name, rep) in enumerate(metrics.items()):
            cols[2 * i].metric(f"{name.split(' (')[0]}: favouritism", f"{rep['max_over_min']:.2f}×",
                               help="Most-picked fair jury ÷ least-picked fair jury. 1.00× = perfectly fair.")
            cols[2 * i + 1].metric(f"{name.split(' (')[0]}: lands on a fair jury", f"{rep['prob_optimal']:.0%}")
        names = ["Standard QAOA", "Fair QAOA (Grover mixer)"]
        chart = alt.Chart(df).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            x=alt.X("Jury:N", title="The equally fair juries", axis=alt.Axis(labelAngle=-30)),
            xOffset=alt.XOffset("Method:N", sort=names),
            y=alt.Y("Share:Q", axis=alt.Axis(format="%"), title="Chance of being picked"),
            color=alt.Color("Method:N", sort=names, scale=alt.Scale(domain=names, range=[BIASED, FAIR]), title=None),
            tooltip=["Jury", "Method", alt.Tooltip("Share:Q", format=".1%")])
        rule = alt.Chart(pd.DataFrame({"y": [1 / df["Jury"].nunique()]})).mark_rule(
            strokeDash=[5, 4], color=WALNUT).encode(y="y:Q")
        st.altair_chart(style_chart((chart + rule).properties(height=320)), width="stretch")
        st.caption("Dashed line = perfectly fair.")

# ---------------- Tab 3: hardware ----------------
with tab_hw:
    st.markdown("## Running on quantum hardware")
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
            st.image(str(img), width="stretch")
        else:
            st.caption("Chart not found. Run `python experiments/run_hardware.py --fake` to create it.")
        st.markdown('<div class="honest"><b>Honest finding:</b> the fair circuit is about 10× deeper than the '
                    'standard one. On today\'s noisy chips, that noise washes out its fairness advantage. The '
                    'algorithm is provably fair; the hardware is not yet good enough to run it faithfully.</div>',
                    unsafe_allow_html=True)

# ---------------- Tab 4: how it works ----------------
with tab_how:
    st.markdown("""
<div class="label">How it works</div>
<div class="lead">A real fairness problem goes in, a quantum computer does the work, and a jury plus a checkable receipt comes out.</div>
<div class="frame">
  <div class="card"><div class="step">Step 1</div><h4>Bridge in</h4>
    <p>Each potential juror becomes one qubit (1 = selected). A cost scores how far a jury's mix of neighbourhood, age and gender is from the community's, and becomes a quantum operator.</p></div>
  <div class="card"><div class="step">Step 2</div><h4>Quantum</h4>
    <p>Standard QAOA finds balanced juries but plays favourites. Fair QAOA starts from every jury of the right size at once and uses a Grover mixer, which guarantees equally fair juries get equal chances.</p></div>
  <div class="card"><div class="step">Step 3</div><h4>Bridge out</h4>
    <p>The circuit is measured thousands of times. One of the fairest measured juries is picked at random, keeping the algorithm's own odds, and a receipt records every setting so the draw can be checked.</p></div>
</div>
""", unsafe_allow_html=True)
    st.write("")
    st.markdown('<div class="label">Honest limits</div>', unsafe_allow_html=True)
    st.markdown("""
- Small pools only: each juror is one qubit, and a normal computer solves these sizes easily.
- Fair juries don't yet mean equal chances for every individual person.
- Today's hardware is too noisy to run the fair circuit faithfully.
- Synthetic people only; we balance neighbourhood, age group and gender, not race directly.
""")
