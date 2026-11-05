
/* ===================== THE BENCH: logic ===================== */
(() => {
  const DATA = JSON.parse(document.getElementById("qiskit-data").textContent);
  const C = { biased: "#8f2633", fair: "#a47a1f", ink: "#301413", ink2: "#6b5a50", grid: "#e0cfb1" };
  const $ = (s) => document.querySelector(s);
  const esc = (v) => String(v).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const COLS = [["juror_id", "Juror ID"], ["name", "Name"], ["neighbourhood", "Neighbourhood"], ["age_group", "Age group"], ["gender", "Gender"]];

  let CUSTOM = null;                                   // the user's uploaded juror list
  const pool = () => ($("#pool").value === "custom" ? CUSTOM : DATA.pools[$("#pool").value]);

  // ---------- live Qiskit server (website/server.py) ----------
  let LIVE = false;
  async function api(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
    return r.json();
  }
  async function detectLive() {
    if (!location.protocol.startsWith("http")) return setLive(false);
    try {
      const ctl = new AbortController(); setTimeout(() => ctl.abort(), 2500);
      const r = await fetch("/api/health", { signal: ctl.signal });
      const j = await r.json(); setLive(!!j.live, j.qiskit);
    } catch (e) { setLive(false); }
  }
  function setLive(on, ver) {
    LIVE = on;
    const b = $("#liveBadge");
    b.className = "badge " + (on ? "on" : "off");
    b.innerHTML = on ? `<i></i>Live Qiskit ${ver ? esc(ver) : ""}: every draw runs the circuit now`
                     : `<i></i>Saved Qiskit results: start <code>website/server.py</code> to run circuits live`;
  }
  const method = () => document.querySelector('input[name="method"]:checked').value;
  const METHOD_NAME = { fair: "Fair QAOA (Grover mixer)", standard: "Standard QAOA", random: "Plain random draw" };

  // ---------- tables ----------
  function table(rows, highlight = new Set()) {
    return `<table class="qb"><tr>${COLS.map(([, h]) => `<th>${h}</th>`).join("")}</tr>` +
      rows.map((r, i) => `<tr class="${highlight.has(i) ? "pick" : ""}">` +
        COLS.map(([c]) => `<td class="${c === "juror_id" ? "id" : ""}">${esc(r[c])}</td>`).join("") + "</tr>").join("") + "</table>";
  }
  function renderPool() { $("#poolTable").innerHTML = table(pool().jurors); }

  // ---------- the same cost the Python code uses ----------
  function groups(p) {
    return DATA.targets.map((t) => ({
      attr: t.attribute, group: t.group, share: t.community_share,
      members: p.jurors.map((j, i) => (j[t.attribute] === t.group ? i : -1)).filter((i) => i >= 0),
      target: p.k * t.community_share,
    }));
  }
  function cost(p, sel) {
    const s = new Set(sel);
    return groups(p).reduce((a, g) => a + (g.members.filter((i) => s.has(i)).length - g.target) ** 2, 0);
  }

  // ---------- uploaded juror lists ----------
  const REQUIRED = ["juror_id", "name", "neighbourhood", "age_group", "gender"];
  function parseCSV(text) {
    const rows = []; let row = [], cell = "", q = false;
    text = text.replace(/^\uFEFF/, "");
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (q) { if (ch === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += ch; }
      else if (ch === '"') q = true;
      else if (ch === ",") { row.push(cell); cell = ""; }
      else if (ch === "\n" || ch === "\r") { if (ch === "\r" && text[i + 1] === "\n") i++; row.push(cell); rows.push(row); row = []; cell = ""; }
      else cell += ch;
    }
    if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
    return rows.filter((r) => r.some((c) => c.trim() !== ""));
  }
  function readJurors(text) {
    const rows = parseCSV(text);
    if (rows.length < 2) throw new Error("The file has no juror rows.");
    const head = rows[0].map((h) => h.trim().toLowerCase().replace(/[\s-]+/g, "_"));
    const missing = REQUIRED.filter((c) => !head.includes(c));
    if (missing.length) throw new Error("Missing column(s): " + missing.join(", ") + ".");
    const jurors = rows.slice(1).map((r) => Object.fromEntries(REQUIRED.map((c) => [c, (r[head.indexOf(c)] || "").trim().slice(0, 60)])));
    if (jurors.length < 3 || jurors.length > 12) throw new Error(`Found ${jurors.length} jurors; upload between 3 and 12 (each juror is one qubit).`);
    if (new Set(jurors.map((j) => j.juror_id)).size !== jurors.length) throw new Error("Each juror_id must be unique.");
    // match values to the community groups, ignoring case
    const unknown = new Set();
    for (const j of jurors) for (const attr of ["neighbourhood", "age_group", "gender"]) {
      const groupsFor = DATA.targets.filter((t) => t.attribute === attr).map((t) => t.group);
      if (attr === "age_group") {                       // Excel sometimes turns 18-34 into a date
        const v = j[attr].toLowerCase().replace(/\s/g, "");
        if (/^(18[-/.]34|34[-/.]18)$/.test(v)) j[attr] = "18-34";
        else if (/^(35[-/.]54|54[-/.]35)$/.test(v)) j[attr] = "35-54";
        else if (/^55\+?$|^55(\+|plus|andover)$/.test(v)) j[attr] = "55+";
      }
      const hit = groupsFor.find((g) => g.toLowerCase() === j[attr].toLowerCase());
      if (hit) j[attr] = hit; else unknown.add(`${attr}: "${j[attr]}"`);
    }
    return { jurors, unknown: [...unknown] };
  }
  function computeOptimal(p) {            // every jury of size k, in the same order as Python's itertools
    let best = Infinity, opt = [];
    const rec = (start, chosen) => {
      if (chosen.length === p.k) {
        const c = cost(p, chosen);
        if (c < best - 1e-9) { best = c; opt = [chosen.slice()]; } else if (Math.abs(c - best) <= 1e-9) opt.push(chosen.slice());
        return;
      }
      for (let i = start; i <= p.n - (p.k - chosen.length); i++) { chosen.push(i); rec(i + 1, chosen); chosen.pop(); }
    };
    rec(0, []);
    p.optimal = opt; p.best_cost = best;
  }
  const resetResults = () => { $("#results").innerHTML = '<div class="empty">Choose a pool and method, then press <b>Draw jury</b>.</div>'; $("#fairOut").innerHTML = ""; };
  const needLive = (what) => `<div class="warnbox"><b>${what} runs the quantum circuit live.</b> Start the live server with
      <code>python website/server.py</code> and open the page it gives you; the green "Live Qiskit" badge shows it is connected.</div>`;

  $("#csvFile").addEventListener("change", async (e) => {
    const file = e.target.files[0], msg = $("#upMsg");
    if (!file) return;
    try {
      let text, converted = "";
      if (/\.(xlsx|xlsm|xls)$/i.test(file.name)) {
        // Excel → CSV, right here in the browser (SheetJS)
        if (!window.XLSX) throw new Error("the Excel reader didn't load; save the sheet as CSV instead.");
        const wb = XLSX.read(await file.arrayBuffer(), { type: "array" });
        const sheetName = wb.SheetNames.find((n) => {
          const r = XLSX.utils.sheet_to_csv(wb.Sheets[n]).split(/\r?\n/)[0].toLowerCase();
          return r.includes("juror_id") || r.includes("juror id");
        }) || wb.SheetNames[0];
        text = XLSX.utils.sheet_to_csv(wb.Sheets[sheetName], { blankrows: false });
        converted = `Converted the Excel sheet "${sheetName}" to CSV. `;
      } else {
        text = await file.text();
      }
      const { jurors, unknown } = readJurors(text);
      const n = jurors.length, k = Math.min(Math.max(2, Math.round(n * 0.4)), n - 1);
      CUSTOM = { custom: true, n, k, jurors, name: file.name };
      computeOptimal(CUSTOM);
      let opt = $('#pool option[value="custom"]');
      if (!opt) { opt = document.createElement("option"); opt.value = "custom"; $("#pool").appendChild(opt); }
      opt.textContent = `Your uploaded list: ${file.name} (${n} people)`;
      $("#pool").value = "custom";
      $("#kInput").max = n - 1; $("#kInput").value = k; $("#kRow").hidden = false;
      msg.className = "upmsg " + (unknown.length ? "err" : "ok");
      msg.textContent = converted + `Loaded ${n} jurors.` + (unknown.length
        ? ` These values don't match a community group and won't count toward balance: ${unknown.slice(0, 4).join(", ")}${unknown.length > 4 ? "…" : ""}.`
        : (LIVE ? " Draws will train and run the quantum circuit for your list." : " Start the live server to run the quantum circuit on it."));
      renderPool(); resetResults();
    } catch (err) {
      msg.className = "upmsg err"; msg.textContent = "Couldn't use that file: " + err.message;
      e.target.value = "";
    }
  });
  $("#kInput").addEventListener("change", () => {
    if (!CUSTOM) return;
    const k = Math.min(Math.max(2, Math.round(+$("#kInput").value || 2)), CUSTOM.n - 1);
    $("#kInput").value = k; CUSTOM.k = k; computeOptimal(CUSTOM); resetResults();
  });

  // ---------- sampling real Qiskit measurements ----------
  function subsample(counts, shots) {
    const keys = Object.keys(counts), cum = []; let tot = 0;
    for (const k of keys) { tot += counts[k]; cum.push(tot); }
    const out = {};
    for (let s = 0; s < shots; s++) {
      const r = Math.random() * tot; let lo = 0, hi = cum.length - 1;
      while (lo < hi) { const m = (lo + hi) >> 1; if (cum[m] > r) hi = m; else lo = m + 1; }
      out[keys[lo]] = (out[keys[lo]] || 0) + 1;
    }
    return out;
  }
  const parse = (key) => (key === "" ? [] : key.split("-").map(Number));

  async function sha256(text) {
    if (!(window.crypto && crypto.subtle)) return null;
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  // ---------- generic grouped bar chart (SVG) ----------
  function barChart({ cats, series, ticks = null, hline = null, height = 300, maxY = null, rotate = false, width = 1000 }) {
    const W = width, H = height, L = 52, R = 10, T = 12, B = rotate ? 78 : 40;
    const pw = W - L - R, ph = H - T - B;
    const all = series.flatMap((s) => s.values).concat(ticks || [], hline != null ? [hline] : []);
    const peak = maxY || Math.max(...all) * 1.08;
    const step = peak <= 0.3 ? 0.05 : peak <= 0.6 ? 0.1 : 0.2;          // "nice" gridlines: 5%, 10% or 20%
    const top = Math.max(step, Math.ceil(peak / step - 1e-9) * step);
    const y = (v) => T + ph - (v / top) * ph;
    const gw = pw / cats.length, bw = Math.min(46, (gw * 0.72) / series.length);
    let g = "";
    const steps = Math.round(top / step);
    for (let i = 0; i <= steps; i++) {
      const v = step * i, yy = y(v);
      g += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="${C.grid}" stroke-width="1"/>` +
           `<text x="${L - 8}" y="${yy + 4}" text-anchor="end">${Math.round(v * 100)}%</text>`;
    }
    cats.forEach((c, ci) => {
      const cx = L + gw * ci + gw / 2, x0 = cx - (bw * series.length + 3 * (series.length - 1)) / 2;
      series.forEach((s, si) => {
        const v = s.values[ci], x = x0 + si * (bw + 3), yy = y(v);
        g += `<rect class="bar" x="${x}" y="${yy}" width="${bw}" height="${Math.max(0, T + ph - yy)}" rx="3" fill="${s.color}"${s.hatch ? ' fill-opacity=".45"' : ""}>` +
             `<title>${esc(c)} · ${esc(s.name)}: ${(v * 100).toFixed(1)}%</title></rect>`;
      });
      if (ticks) g += `<line x1="${cx - gw * 0.38}" x2="${cx + gw * 0.38}" y1="${y(ticks[ci])}" y2="${y(ticks[ci])}" stroke="${C.ink}" stroke-width="3"><title>${esc(c)} · community: ${(ticks[ci] * 100).toFixed(0)}%</title></line>`;
      const lbl = esc(c);
      g += rotate
        ? `<text transform="translate(${cx},${H - B + 16}) rotate(-28)" text-anchor="end">${lbl}</text>`
        : `<text x="${cx}" y="${H - B + 22}" text-anchor="middle">${lbl}</text>`;
    });
    if (hline != null) g += `<line x1="${L}" x2="${W - R}" y1="${y(hline)}" y2="${y(hline)}" stroke="${C.ink}" stroke-width="1.5" stroke-dasharray="6 5"/>`;
    g += `<line x1="${L}" x2="${W - R}" y1="${T + ph}" y2="${T + ph}" stroke="#c9b393"/>`;
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
  }
  const legend = (items) => `<div class="legend">${items.map(([cls, color, name]) =>
    `<span><i class="${cls || ""}" style="${color ? `background:${color}` : ""}"></i>${esc(name)}</span>`).join("")}</div>`;

  // ---------- Draw a jury ----------
  async function draw() {
    const p = pool(), m = method(), shots = +$("#shots").value;
    let sel, counts = null;
    let liveReceipt = null;
    if (p.custom && m !== "random" && !LIVE) { $("#results").innerHTML = needLive("Your uploaded list"); return; }
    if (m !== "random" && LIVE) {
      const btn = $("#drawBtn"), label = btn.textContent;
      btn.disabled = true;
      btn.textContent = p.custom ? "Training and running the quantum circuit for your list (first draw takes a few seconds)…" : "Running the quantum circuit…";
      try {
        const body = p.custom ? { jurors: p.jurors, k: p.k, method: m, shots } : { pool: $("#pool").value, method: m, shots };
        const res = await api("/api/draw", body);
        sel = res.selected; liveReceipt = res.receipt;
      } catch (e) {
        btn.disabled = false; btn.textContent = label;
        if (p.custom) { $("#results").innerHTML = `<div class="warnbox"><b>Couldn't run your list:</b> ${esc(e.message)}</div>`; return; }
        setLive(false);
      }
      btn.disabled = false; btn.textContent = label;
    }
    if (sel) { /* live result already in */ }
    else if (m === "random") {
      const idx = p.jurors.map((_, i) => i);
      for (let i = idx.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [idx[i], idx[j]] = [idx[j], idx[i]]; }
      sel = idx.slice(0, p.k).sort((a, b) => a - b);
    } else {
      counts = subsample(p.methods[m].counts, shots);
      const sized = Object.keys(counts).filter((k) => parse(k).length === p.k);
      const costs = Object.fromEntries(sized.map((k) => [k, cost(p, parse(k))]));
      const best = Math.min(...Object.values(costs));
      const finalists = sized.filter((k) => costs[k] <= best + 1e-9);
      let tot = finalists.reduce((a, k) => a + counts[k], 0), r = Math.random() * tot;
      let pick = finalists[0];
      for (const k of finalists) { r -= counts[k]; if (r <= 0) { pick = k; break; } }
      sel = parse(pick);
    }
    const jury = sel.map((i) => p.jurors[i]);
    const receipt = liveReceipt || {
      method: METHOD_NAME[m],
      backend: m === "random" ? "browser random number generator" : "Qiskit Aer simulator (real measurements, resampled)",
      pool_size: p.n, jury_size: p.k,
      selected_ids: jury.map((j) => j.juror_id),
      balance_cost: +cost(p, sel).toFixed(4), best_possible_cost: +p.best_cost.toFixed(4),
      shots: m === "random" ? null : shots,
      qaoa_angles: m === "random" ? null : { gammas: p.methods[m].angles.gammas.map((v) => +v.toFixed(4)), betas: p.methods[m].angles.betas.map((v) => +v.toFixed(4)) },
      counts_sha256: counts ? await sha256(JSON.stringify(Object.keys(counts).sort().map((k) => [k, counts[k]]))) : null,
      timestamp_utc: new Date().toISOString().slice(0, 19) + "Z",
    };
    // pool vs jury chart
    const gs = groups(p), s = new Set(sel);
    const cats = gs.map((g) => g.group);
    const poolV = gs.map((g) => g.members.length / p.n), juryV = gs.map((g) => g.members.filter((i) => s.has(i)).length / p.k);
    const ticks = gs.map((g) => g.share);
    $("#results").innerHTML = `
      <h2>Selected jury</h2>
      ${table(jury)}
      <div class="stats">
        <div class="stat"><div class="k">Balance cost (lower is fairer)</div><div class="v">${receipt.balance_cost}</div></div>
        <div class="stat"><div class="k">Best possible</div><div class="v">${receipt.best_possible_cost}</div></div>
        <div class="stat"><div class="k">Method</div><div class="v">${esc(METHOD_NAME[m].split(" (")[0])}</div></div>
      </div>
      <div class="chart-title">Pool vs this jury</div>
      ${legend([["", C.biased, "Juror pool (skewed)"], ["", C.fair, "This jury"], ["tick", null, "Community's real share"]])}
      ${barChart({ cats, series: [{ name: "Juror pool", color: C.biased, values: poolV }, { name: "This jury", color: C.fair, values: juryV }], ticks, height: 290 })}
      <details class="receipt"><summary>🧾 Audit receipt</summary><pre>${esc(JSON.stringify(receipt, null, 2))}</pre>
        <button class="linkbtn" id="dl">Copy receipt</button> <span class="meta" id="dlmsg"></span></details>`;
    $("#dl").onclick = async () => {
      try { await navigator.clipboard.writeText(JSON.stringify(receipt, null, 2)); $("#dlmsg").textContent = "Copied to clipboard."; }
      catch (e) { $("#dlmsg").textContent = "Couldn't copy automatically; select the text above and copy it."; }
    };
  }

  // ---------- Fairness test ----------
  function fairness(p, m) {
    const counts = p.methods[m].counts, optKeys = p.optimal.map((j) => j.join("-"));
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    const opt = optKeys.map((k) => counts[k] || 0), optTot = opt.reduce((a, b) => a + b, 0);
    const shares = opt.map((v) => v / optTot);
    return { shares, pFair: optTot / total, fav: Math.max(...opt) / Math.max(1, Math.min(...opt)) };
  }
  async function runFair() {
    const p = pool();
    if (p.custom && !LIVE) { $("#fairOut").innerHTML = needLive("The fairness test on your uploaded list"); return; }
    let st = p.custom ? null : fairness(p, "standard"), fa = p.custom ? null : fairness(p, "fair"), live = false;
    if (LIVE) {
      const btn = $("#fairBtn"), label = btn.textContent;
      btn.disabled = true; btn.textContent = p.custom ? "Training both circuits for your list, then running them 20,000 times…" : "Running both circuits 20,000 times…";
      try {
        const r = await api("/api/fairness", p.custom ? { jurors: p.jurors, k: p.k } : { pool: $("#pool").value });
        st = r.standard; fa = r.fair; live = true;
      } catch (e) {
        btn.disabled = false; btn.textContent = label;
        if (p.custom) { $("#fairOut").innerHTML = `<div class="warnbox"><b>Couldn't run your list:</b> ${esc(e.message)}</div>`; return; }
        setLive(false);
      }
      btn.disabled = false; btn.textContent = label;
    }
    if (p.optimal.length < 2) {
      $("#fairOut").innerHTML = `<div class="warnbox">Only one jury is the fairest for this list, so there is nothing to favour: every method picks it. Try a bigger pool or a different jury size.</div>`;
      return;
    }
    const cats = p.optimal.map((j) => j.map((i) => p.jurors[i].juror_id).join(" · "));
    scale.show(st, fa);
    $("#fairOut").innerHTML = `
      <div class="mgrid">
        <div class="stat"><div class="k">Standard QAOA: favouritism</div><div class="v">${st.fav.toFixed(2)}×</div></div>
        <div class="stat"><div class="k">Standard QAOA: lands on a fair jury</div><div class="v">${Math.round(st.pFair * 100)}%</div></div>
        <div class="stat"><div class="k">Fair QAOA: favouritism</div><div class="v">${fa.fav.toFixed(2)}×</div></div>
        <div class="stat"><div class="k">Fair QAOA: lands on a fair jury</div><div class="v">${Math.round(fa.pFair * 100)}%</div></div>
      </div>
      <div class="chart-title">Chance of being picked, among the ${cats.length} equally fair juries</div>
      ${legend([["", C.biased, "Standard QAOA"], ["", C.fair, "Fair QAOA (Grover mixer)"], ["dash", null, "Perfectly fair"]])}
      ${barChart({ cats, series: [{ name: "Standard QAOA", color: C.biased, values: st.shares }, { name: "Fair QAOA", color: C.fair, values: fa.shares }], hline: 1 / cats.length, height: 340, rotate: cats.length > 5 })}
      <p class="meta" style="margin-top:10px">${live ? "Just measured live on the Qiskit Aer simulator. " : ""}Favouritism = most-picked fair jury ÷ least-picked fair jury (1.00× is perfectly fair). Small deviations from 1.00× in the fair method are measurement noise.</p>`;
  }

  // ---------- Hardware ----------
  function renderHardware() {
    const hw = DATA.hardware;
    if (!hw) { $("#hwMeta").textContent = "No hardware results yet."; return; }
    const p = DATA.pools[String(hw.pool)];
    $("#hwMeta").innerHTML = `<b>Backend:</b> ${esc(hw.backend)} · <b>Job ID:</b> ${esc(hw.job_id || "n/a (simulation)")} · <b>Shots:</b> ${hw.shots} · <b>Pool:</b> ${hw.pool} choose ${hw.k}`;
    const cats = p.optimal.map((j) => j.map((i) => p.jurors[i].juror_id).join(" · "));
    const html = ["standard", "fair"].map((m) => {
      const ideal = fairness(p, m).shares;
      const hc = hw.results[m].counts_per_fair_jury, keys = p.optimal.map((j) => j.join("-"));
      const vals = keys.map((k) => hc[k] || 0), tot = vals.reduce((a, b) => a + b, 0) || 1;
      const color = m === "fair" ? C.fair : C.biased, name = m === "fair" ? "Fair QAOA (Grover mixer)" : "Standard QAOA";
      return `<div class="card"><h3>${name}</h3><p class="meta">Favouritism on hardware: <b>${hw.results[m].max_over_min.toFixed(2)}×</b></p>
        ${legend([["", color + "73", "Ideal simulator"], ["", color, "Noisy hardware"], ["dash", null, "Perfectly fair"]])}
        ${barChart({ cats, series: [{ name: "Ideal simulator", color, values: ideal, hatch: true }, { name: "Noisy hardware", color, values: vals.map((v) => v / tot) }], hline: 1 / cats.length, height: 320, maxY: 0.45, width: 520 })}</div>`;
    }).join("");
    $("#hwCharts").innerHTML = html;
  }

  // ---------- tabs ----------
  const tabs = [...document.querySelectorAll('.tabs [role="tab"]')];
  function select(tab) {
    tabs.forEach((t) => { const on = t === tab; t.setAttribute("aria-selected", on); t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on; });
  }
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => select(t));
    t.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length]; n.focus(); select(n);
      }
    });
  });

  $("#pool").addEventListener("change", () => {
    $("#kRow").hidden = $("#pool").value !== "custom";
    renderPool();
    const hadFair = $("#fairOut").innerHTML;
    resetResults();
    if (hadFair && $("#pool").value !== "custom") runFair();
  });
  $("#drawBtn").addEventListener("click", draw);
  $("#fairBtn").addEventListener("click", runFair);
  // ---------- gavel cursor ----------
  (() => {
    if (!window.matchMedia("(pointer: fine)").matches) return;
    const cur = document.getElementById("gcur");
    document.documentElement.classList.add("has-gavel");
    const HOT_X = 15, HOT_Y = 28;               // the striking face of the head (64px cursor)                      // the striking face of the head is the click point
    let x = -100, y = -100, raf = 0;
    const place = () => { raf = 0; cur.style.transform = `translate(${x - HOT_X}px, ${y - HOT_Y}px)`; };
    addEventListener("mousemove", (e) => { x = e.clientX; y = e.clientY; cur.classList.add("on"); if (!raf) raf = requestAnimationFrame(place); }, { passive: true });
    document.addEventListener("mouseleave", () => cur.classList.remove("on"));
    addEventListener("mousedown", () => { cur.classList.remove("tap"); void cur.offsetWidth; cur.classList.add("tap"); });
    addEventListener("mouseup", () => setTimeout(() => cur.classList.remove("tap"), 90));
    addEventListener("blur", () => cur.classList.remove("tap"));
  })();

  // ---------- balance scale: dips toward the cursor, tips during the fairness test ----------
  const scale = (() => {
    const svg = document.getElementById("scale"); if (!svg) return { show() {} };
    const fig = svg.closest(".scale-fig");
    const beam = svg.querySelector("#beam"), panL = svg.querySelector("#panL"), panR = svg.querySelector("#panR");
    const R = 160, reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let angle = 0, vel = 0, testTarget = 0, hover = null, t0 = performance.now();
    function draw(a) {
      const rad = a * Math.PI / 180, dy = R * Math.sin(rad), dx = R * (1 - Math.cos(rad));
      beam.setAttribute("transform", `rotate(${a} 220 70)`);
      panL.setAttribute("transform", `translate(${dx} ${-dy})`);
      panR.setAttribute("transform", `translate(${-dx} ${dy})`);
    }
    function goal(now) {
      if (hover !== null) return hover;                          // the side under the cursor goes down
      if (testTarget !== 0) return testTarget;
      return reduced ? 0 : Math.sin((now - t0) / 1400) * 1.2;   // gentle idle sway
    }
    function tick(now) {
      vel += (goal(now) - angle) * 0.06; vel *= 0.82; angle += vel;
      draw(angle); requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
    fig.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      const rel = Math.max(-1, Math.min(1, ((e.clientX - r.left) / r.width - 0.5) * 2));   // -1 left … +1 right
      hover = Math.abs(rel) < 0.06 ? 0 : rel * 16;              // positive angle = right pan down
    });
    fig.addEventListener("pointerleave", () => { hover = null; });
    const tilt = (fav) => Math.min(18, Math.max(0, (fav - 1) * 26));
    return {
      show(st, fa) {
        testTarget = tilt(st.fav) || 0.001;
        setTimeout(() => { testTarget = tilt(fa.fav) || 0.001; }, 1800);
        setTimeout(() => { testTarget = 0; }, 6000);
      },
    };
  })();

  renderPool(); renderHardware(); detectLive();
})();
