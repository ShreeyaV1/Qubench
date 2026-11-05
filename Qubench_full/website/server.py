"""
Qubench live server: serves the website AND runs Qiskit live behind it.

Run from the repo root (with your Python environment turned on):
    python website/server.py

It opens the website in your browser. Every "Draw jury" and "Run fairness test"
then runs the real QAOA circuits on the Qiskit Aer simulator, right now.
Stop it with control + C.

Only uses Python's built-in web server, so nothing extra to install.
"""
import hashlib
import json
import secrets
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd                                                    # noqa: E402
import qiskit                                                          # noqa: E402
from qiskit import transpile                                           # noqa: E402
from qiskit_aer import AerSimulator                                    # noqa: E402
from qubench import JuryProblem, draw_jury, fairness_report, get_angles  # noqa: E402
from qubench.core import build_circuit                                 # noqa: E402

POOLS = {"8": (8, 3, 3), "12": (12, 4, 3), "6": (6, 2, 1)}             # pool -> (n, k, QAOA layers)
MAX_N = 12                                                             # each juror is one qubit
REQUIRED = ["juror_id", "name", "neighbourhood", "age_group", "gender"]
TARGETS = ROOT / "data" / "targets.csv"
BACKEND = AerSimulator()
_cache, _lock = {}, threading.Lock()


def problem_for(pool):
    n, k, _ = POOLS[pool]
    return JuryProblem.from_csv(ROOT / f"data/jurors_{n}.csv", TARGETS, k)


def custom_problem(body):
    """Validate a juror list uploaded from the website and turn it into a JuryProblem."""
    rows, k = body.get("jurors"), body.get("k")
    if not isinstance(rows, list) or not 3 <= len(rows) <= MAX_N:
        raise ValueError(f"Upload between 3 and {MAX_N} jurors (each juror is one qubit).")
    clean = []
    for r in rows:
        if not isinstance(r, dict) or any(c not in r for c in REQUIRED):
            raise ValueError("Every row needs these columns: " + ", ".join(REQUIRED))
        clean.append({c: str(r[c]).strip()[:60] for c in REQUIRED})
    if len({r["juror_id"] for r in clean}) != len(clean):
        raise ValueError("Each juror_id must be unique.")
    try:
        k = int(k)
    except (TypeError, ValueError):
        raise ValueError("Jury size must be a whole number.")
    if not 2 <= k < len(clean):
        raise ValueError("Jury size must be at least 2 and smaller than the pool.")
    return JuryProblem(pd.DataFrame(clean), pd.read_csv(TARGETS), k)


def problem_and_reps(body):
    if body.get("jurors") is not None:
        return custom_problem(body), 3
    pool = str(body.get("pool", "8"))
    if pool not in POOLS:
        raise ValueError("Unknown pool.")
    return problem_for(pool), POOLS[pool][2]


def circuit_for(problem, method, reps):
    """Train (first time only), build and transpile a circuit, then reuse it."""
    data_id = hashlib.sha1((problem.jurors.to_csv() + str(problem.k)).encode()).hexdigest()
    key = (data_id, method, reps)
    with _lock:
        if key not in _cache:
            angles = get_angles(problem, method, reps)
            qc = build_circuit(problem, angles)
            qc.measure_all()
            _cache[key] = (transpile(qc, BACKEND, optimization_level=1), angles)
        return _cache[key]


def run_live(problem, method, shots, reps):
    """Run the quantum circuit on the Aer simulator with a fresh random seed."""
    tqc, angles = circuit_for(problem, method, reps)
    seed = secrets.randbelow(2**31)
    counts = BACKEND.run(tqc, shots=shots, seed_simulator=seed).result().get_counts()
    return counts, angles, seed


def api_draw(body):
    method, shots = body.get("method", "fair"), int(body.get("shots", 4000))
    if method not in ("fair", "standard") or not 100 <= shots <= 20000:
        raise ValueError("bad request")
    problem, reps = problem_and_reps(body)
    t0 = time.time()
    counts, angles, seed = run_live(problem, method, shots, reps)
    res = draw_jury(StringIO(problem.jurors.to_csv(index=False)), TARGETS, problem.k, method=method, shots=shots,
                    counts=counts, backend_name="Qiskit Aer simulator (live)")
    ids = list(problem.jurors["juror_id"])
    receipt = res["receipt"]
    if body.get("jurors") is not None:
        receipt["pool"] = f"uploaded list ({problem.n} jurors)"
    receipt["qaoa_angles"] = {"gammas": [round(v, 4) for v in angles["gammas"]],
                              "betas": [round(v, 4) for v in angles["betas"]]}
    receipt["simulator_seed"] = seed
    receipt["run_seconds"] = round(time.time() - t0, 2)
    receipt.pop("angles", None)
    return {"selected": [ids.index(j) for j in receipt["selected_ids"]], "receipt": receipt}


def api_fairness(body):
    problem, reps = problem_and_reps(body)
    out = {}
    for method in ("standard", "fair"):
        counts, _, _ = run_live(problem, method, 20000, reps)
        rep = fairness_report(problem, counts)
        out[method] = {"shares": [rep["share_per_optimal_jury"][j] for j in rep["optimal_juries"]],
                       "pFair": rep["prob_optimal"], "fav": rep["max_over_min"]}
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "website"), **kw)

    def log_message(self, fmt, *args):                                 # keep the terminal tidy
        if self.path.startswith("/api/"):
            sys.stdout.write(f"[{datetime.now():%H:%M:%S}] {self.command} {self.path}\n")

    def _json(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/health":
            return self._json(200, {"live": True, "qiskit": qiskit.__version__})
        return super().do_GET()

    def do_POST(self):
        routes = {"/api/draw": api_draw, "/api/fairness": api_fairness}
        if self.path not in routes:
            return self._json(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            return self._json(200, routes[self.path](body))
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:                                         # show the problem instead of hanging
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})


def main():
    port = 8000
    for p in range(8000, 8020):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    print("Preparing the quantum circuits (first time only, a few seconds)...")
    for pool in POOLS:
        for method in ("standard", "fair"):
            circuit_for(problem_for(pool), method, POOLS[pool][2])
    url = f"http://localhost:{port}/"
    print(f"\n  Qubench is live at {url}\n  Every draw runs Qiskit {qiskit.__version__} live. Press control + C to stop.\n")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
