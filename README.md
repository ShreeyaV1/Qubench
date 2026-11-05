# Qubench 
**Quantum-fair jury selection: random, representative, and checkable.**
Built with Qiskit for IBM Qiskit Fall Fest 2026 (UW Quantum Club).

> A fair jury needs a fair algorithm. Qubench turns "pick a jury that looks like the community" into a
> quantum optimization problem, and shows that the *standard* quantum algorithm (QAOA) quietly plays
> favourites among equally fair juries, while a **Grover-mixer QAOA** gives every equally fair jury
> exactly the same chance.

## The problem
Jury pools are supposed to be random *and* representative of the community. In practice pools are often
skewed (e.g. the underrepresentation of Indigenous people highlighted by the 2018 Stanley/Boushie case),
and the public has no way to check how a selection was made.

## What Qubench does
A jury administrator (no quantum knowledge needed) loads a juror list and the community's makeup, clicks
**Draw jury**, and gets a balanced jury, a comparison chart, and an audit receipt.

```python
from qubench import draw_jury
result = draw_jury("data/jurors_8.csv", "data/targets.csv", k=3, method="fair")
print(result["jury"])      # the selected jurors
print(result["receipt"])   # everything needed to check the draw
```

## Key results (ideal simulator, 3 QAOA layers)
| Pool | Method | Lands on a fair jury | Favouritism (most ÷ least picked fair jury) |
|---|---|---|---|
| 8 choose 3 (5 equally fair juries) | Standard QAOA | 21% | 1.26× |
| | **Fair QAOA (Grover mixer)** | **82%** | **1.00×** |
| 12 choose 4 (9 equally fair juries) | Standard QAOA | 4% | 3.17× |
| | **Fair QAOA (Grover mixer)** | **15%** | **1.00×** |

On a **noisy simulation of a real IBM chip** (6 choose 2): the fair circuit needs ~400 two-qubit gates vs
~46 for standard QAOA, and noise washes out its advantage (fair 10% / 1.27×, standard 15% / 1.16×).
The algorithm is provably fair; today's hardware isn't yet good enough to run it faithfully.

## Quick start
```bash
pip install -r requirements.txt
python experiments/run_experiments.py      # all charts + numbers  (~1 min)
streamlit run app/app.py                   # the web app
python experiments/run_hardware.py --fake  # noisy IBM-chip simulation (no account)
python experiments/run_hardware.py         # REAL IBM quantum computer (needs account, below)
```

### IBM account (for real hardware, one time)
1. Sign up at https://quantum.cloud.ibm.com and copy your API key.
2. Run once in Python (never commit the key to GitHub):
   ```python
   from qiskit_ibm_runtime import QiskitRuntimeService
   QiskitRuntimeService.save_account(channel="ibm_quantum_platform", token="YOUR_API_KEY", set_as_default=True)
   ```
3. `python experiments/run_hardware.py`. If the queue is slow, it prints a job ID; later run
   `python experiments/run_hardware.py --job-id <ID>`.

## How it works
1. **Bridge in:** each juror = 1 qubit. Cost = Σ over groups (jurors picked from group − target)².
   Converted to a quantum operator (QUBO → Pauli-Z terms).
2. **Quantum:**
   - *Standard QAOA*: Hadamard start, cost layers + X-mixer, jury size enforced by a penalty.
   - *Fair QAOA*: starts in a **Dicke state** (every jury of size k at once, built with the efficient
     Bärtschi–Eidenbenz circuit), cost layers + **Grover mixer**, which guarantees equal probability for
     equal cost (fair sampling).
   - Angles trained with COBYLA to maximise the chance of landing on an optimal (fairest) jury.
3. **Bridge out:** measure thousands of times, keep the fairest measured juries, pick one measured result
   at random (preserving the algorithm's own probabilities), and issue a receipt.

## Honest limits
- Small pools only (1 qubit per juror); classical methods solve these sizes easily.
- Fair juries ≠ equal chances for every *individual* (see `fig3`).
- Real hardware noise currently erases the fair circuit's advantage.
- Synthetic data only; balancing on neighbourhood, age group and gender (not race directly).

## Repo layout
```
data/          synthetic juror pools (6, 8, 12) + community targets + generator
qubench/       core.py (QUBO, circuits, training, metrics) · api.py (draw_jury)
experiments/   run_experiments.py (charts) · run_hardware.py (IBM hardware / noisy sim)
app/           Streamlit web app
results/       figures/, angles/, hardware/, summary.json
docs/          EXPLAINER.md (plain English + judge Q&A) · SLIDES.md (pitch text)
```

## References
- Bärtschi & Eidenbenz (2019), *Deterministic Preparation of Dicke States*.
- Bärtschi & Eidenbenz (2020), *Grover Mixers for QAOA*.
- Pelofske et al. (2021), fair sampling with Grover-mixer QAOA on IBM Q backends (arXiv:2101.03258).
- Pelofske (2024), *Biased Degenerate Ground-State Sampling of Small Ising Models with Converged QAOA* (arXiv:2411.05294).
- Flanigan et al. (2021), *Fair algorithms for selecting citizens' assemblies*, Nature 596.

## Team
- [Name]: Quantum
- [Name]: App + data
- [Name]: Pitch + testing
