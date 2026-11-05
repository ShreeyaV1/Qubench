"""
Builds website/index.html: the gavel + Parliament cover (from frontend/intro.html)
followed by the full Qubench site, with real Qiskit results embedded.

Run from the repo root:
    python experiments/export_web_data.py   # (re)generate the Qiskit results
    python website/build_site.py            # assemble the single-file website
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
W = ROOT / "website"
s = (ROOT / "frontend" / "intro.html").read_text()


def rep(a, b, count=1):
    global s
    assert a in s, f"not found: {a[:70]}"
    s = s.replace(a, b, count)


# fonts for the site body
rep("family=Anton&family=Libre+Caslon+Text:wght@400;700&family=IBM+Plex+Sans:wght@400;500",
    "family=Anton&family=Libre+Caslon+Text:wght@400;700&family=IBM+Plex+Sans:wght@400;500"
    "&family=Hanken+Grotesk:wght@400;500;600")
rep("<title>Qubench</title>", "<title>Qubench · quantum-fair jury selection</title>")

# the cover becomes the first section of a scrolling page
rep("""  body {
    overflow: hidden;
    background: radial-gradient(ellipse 70% 62% at 50% 42%, var(--maroon) 0%, var(--seal) 55%, var(--soy) 100%);""",
    """  body {""")
rep(".viewport { position: fixed;", ".viewport { position: absolute;")
rep(".hero { position: fixed;", ".hero { position: absolute;")
rep(".skip { position: fixed;", ".skip { position: absolute;")
rep("</style>", (W / "app_part.css").read_text() + "\n</style>")

rep("<body>\n<div class=\"hero\" id=\"hero\">", "<body>\n<section class=\"cover\" id=\"cover\">\n<div class=\"hero\" id=\"hero\">")
rep("<button class=\"skip\" id=\"skip\" type=\"button\">Skip intro</button>",
    "<button class=\"skip\" id=\"skip\" type=\"button\">Skip intro</button>\n</section>\n"
    + (W / "app_part.html").read_text())

# "Take the bench" scrolls down to the site; lock scrolling while the intro plays
rep("""  document.getElementById("enter").href = "https://quantum-jury-fairness-lab.lovable.app/#bench";""",
    """  document.getElementById("enter").href = "#bench";
  const lock = (on) => { document.documentElement.style.overflow = on ? "hidden" : ""; };
  // Slow, eased glide from the cover down to the bench
  document.getElementById("enter").addEventListener("click", (e) => {
    e.preventDefault();
    const target = document.getElementById("bench").getBoundingClientRect().top + window.scrollY;
    if (reduced) { window.scrollTo(0, target); return; }
    const startY = window.scrollY, dist = target - startY, dur = 2200, t0 = performance.now();
    const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);   // ease-in-out
    document.documentElement.style.scrollBehavior = "auto";
    const step = (now) => {
      const t = Math.min(1, (now - t0) / dur);
      window.scrollTo(0, startY + dist * ease(t));
      if (t < 1) requestAnimationFrame(step);
      else { document.documentElement.style.scrollBehavior = ""; history.replaceState(null, "", "#bench"); }
    };
    requestAnimationFrame(step);
  });""")
rep("""    hero.classList.remove("instant", "show", "rise", "done");""",
    """    hero.classList.remove("instant", "show", "rise", "done");
    lock(true); window.scrollTo(0, 0);""")
rep("""    at(4700, () => { hero.classList.add("done"); skipBtn.classList.add("hidden"); });""",
    """    at(4700, () => { hero.classList.add("done"); skipBtn.classList.add("hidden"); lock(false); });""")
rep("""    hero.classList.add("instant", "show", "rise", "done");""",
    """    hero.classList.add("instant", "show", "rise", "done"); lock(false);""")

data = (W / "qiskit_results.json").read_text().replace("</", "<\\/")
sheetjs = (W / "vendor" / "xlsx.core.min.js").read_text().replace("</script", "<\\/script")
rep("</body>", f'<script>/* SheetJS (Apache-2.0), reads Excel uploads */\n{sheetjs}</script>\n'
    f'<script type="application/json" id="qiskit-data">{data}</script>\n<script>'
    + (W / "app_part.js").read_text() + "</script>\n</body>")

(W / "index.html").write_text(s)
print(f"built website/index.html ({len(s) // 1024} KB)")
