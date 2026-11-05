# Qubench, explained in plain English
*Read this once tonight. All three of you should be able to say every bold sentence in your own words.*

---

## 1. The one-sentence version
**"Standard QAOA favours some equally fair juries over others; the Grover mixer gives every fair jury the same chance."**

## 2. The story
- Juries should be **random** (nobody can rig them) and **representative** (they look like the community).
- Real jury pools are often skewed. In the 2018 Stanley/Boushie case, an Indigenous man's death was judged
  by a jury with no Indigenous members, and public trust collapsed. Canada abolished peremptory challenges in 2019.
- Even fair-looking algorithms are black boxes. **We asked: if we use a quantum computer to pick juries, is the quantum algorithm itself fair?**

## 3. How a jury becomes a quantum problem
- **Each juror = one qubit.** Measured 1 = selected, 0 = not selected. 8 jurors = 8 qubits.
- **Cost = how unbalanced a jury is.** For each group (North, South, 18–34, Woman, …) we compare
  "how many we picked" vs "how many we should pick", square the gap, and add it all up. Lower = fairer.
- That cost becomes a **quantum operator** (made of Pauli-Z terms). This translation is our "bridge in".

## 4. QAOA in 30 seconds
QAOA = **Quantum Approximate Optimization Algorithm**. Think of it as a dance with two moves, repeated:
1. **Cost move:** gives every possible jury a "phase" based on how unbalanced it is.
2. **Mixer move:** shuffles probability between juries.

A normal computer tunes the dance (the angles γ and β) so that, when we measure, **balanced juries come out most often**.
Classical optimiser + quantum circuit working together = a *variational* algorithm.

## 5. The key discovery: standard QAOA plays favourites
- In our 12-juror pool, **9 different juries are equally balanced** (tied for best).
- Fair = each of those 9 should be picked **11% of the time**.
- Standard QAOA picks some of them **3.2× more often** than others. **Nobody chose this bias; it comes from how the mixer moves probability around.** Researchers have documented this ("biased degenerate ground-state sampling").

## 6. The fix: Grover-mixer QAOA ("fair QAOA")
Two changes:
1. **Start with every valid jury at once.** We prepare a *Dicke state*: an equal superposition of every jury
   with exactly k people. No wrong-sized juries, no penalty needed. (We use an efficient circuit by Bärtschi & Eidenbenz.)
2. **Use the Grover mixer** instead of the usual one. It treats every valid jury symmetrically, so
   **juries with the same cost always keep exactly the same probability**. That fairness is guaranteed by the maths, not by luck.

**Result:** perfectly even (1.00×), AND it lands on a fair jury far more often (82% vs 21% on 8 jurors).

## 7. Bridge out: from measurements to a jury
- We measure the circuit thousands of times ("shots"); each shot is a jury.
- Keep the fairest juries that were measured, then **pick one measured result at random**. That keeps the
  algorithm's own probabilities, so a fair algorithm gives a fair draw.
- A **receipt** records method, settings, angles, timestamp, and a fingerprint (hash) of all the measurements.

## 8. Real hardware: the honest finding
- The fair circuit is about **10× bigger** (≈400 vs ≈46 two-qubit gates on the 6-juror pool).
- Today's chips are noisy; on a realistic simulation of IBM's chip, **noise washes out the fair circuit's advantage**.
- **How to say it:** "The algorithm is provably fair. Today's hardware isn't good enough to run it faithfully yet. Our tool measures exactly that gap."

## 9. Honest limits (say these before judges ask)
1. Small pools only: each juror is a qubit.
2. A classical computer can solve these sizes easily. Our contribution is the **bridge** and the **fairness analysis**, ready for bigger hardware.
3. Fair juries ≠ fair chances for each individual: a person who appears in more balanced juries is picked more (chart fig3). Classical tools like Panelot (Nature, 2021) target individual fairness; that's our next step.
4. Synthetic people only. We balance neighbourhood, age group and gender, **not race directly**, because selecting individual jurors by race is legally risky in Canada.

---

## Judge Q&A: practise these out loud

**Q: Why use quantum at all? A classical computer can do this.**
A: At this size, yes, and we say so. Our point is the bridge: we show how a fairness problem maps onto quantum
optimization, and we found that the *standard* quantum algorithm is unfair while the Grover-mixer version is
provably fair. If quantum optimizers are ever used for public decisions, that's exactly the check people need.

**Q: What is a Dicke state?**
A: An equal superposition of every bitstring with exactly k ones. For us, every possible jury of the right size, all at once, equally weighted.

**Q: Why is standard QAOA biased?**
A: One intuition: its mixer flips one qubit at a time, so juries surrounded by more similar low-cost
"neighbours" tend to collect more probability. The Grover mixer mixes all valid juries symmetrically, so equal-cost juries stay equal.

**Q: How many qubits?** A: One per juror: 6, 8 or 12 in our runs. The 12-juror run is simulated; real hardware runs use 6.

**Q: How did you choose the angles?** A: A classical optimiser (COBYLA) maximises the probability of measuring a fairest jury, with several random restarts.

**Q: How do you know the simulator results are right?**
A: We check the Qiskit circuits against an independent exact calculation: they match to about 10⁻¹⁶.
Measured (sampled) results also match the ideal numbers within sampling error.

**Q: What error mitigation did you use?** A: Dynamical decoupling and Pauli twirling through IBM's Sampler, plus a shallow 1-layer circuit for hardware.

**Q: Why not balance on race?** A: Picking individual jurors by race is legally problematic in Canada. Underrepresentation mostly
comes from who gets summoned, so we aim at the pool stage and balance on neighbourhood/age/gender. Neighbourhood often tracks the source-list skew.

**Q: Can't someone still rig it?**
A: The receipt records every setting and a hash of all measurements, so the draw can be re-checked. With real
hardware, the IBM job ID is an independent record. We don't claim it's perfectly unriggable.

**Q: What would you do next?**
A: Individual-level fairness (equal chances per person), larger pools on better hardware, and certified quantum randomness.
