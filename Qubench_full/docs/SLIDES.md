# Qubench: slide text (copy into your deck)
Target: ~4.5 minutes. One idea per slide. Charts are in `results/figures/`.

---

### Slide 1: Hook (speaker: C, 30 s)
**Title:** 2018. A jury with no Indigenous members decides the killing of an Indigenous man.
**Say:** "In the Stanley/Boushie case, a jury with no Indigenous members acquitted the accused, and public trust in the verdict collapsed. Canada changed jury-selection law in 2019. But one question stayed open: how do you *prove* a selection was fair?"

### Slide 2: The problem (C, 30 s)
**Title:** Random ⟷ Representative ⟷ Provable
- Random: nobody can steer it
- Representative: it looks like the community
- Provable: anyone can check it
**Say:** "Every selection method trades these off, and people are asked to trust a black box."

### Slide 3: The user (C, 15 s)
**Title:** Built for a jury administrator
- Sends out summonses · no coding · no quantum knowledge
**Say:** "She uploads a list, clicks one button, and gets a jury plus a receipt. Everything quantum is hidden."

### Slide 4: The bridge (C, 30 s)
**Title:** Juror list → quantum problem → jury + receipt
`Jurors + community targets → QUBO (1 qubit per juror) → QAOA in Qiskit → measurements → jury + receipt`
**Say:** "Each juror is a qubit. The cost measures how unbalanced a jury is. QAOA searches for low-cost juries."

### Slide 5: Live demo (B, 90 s)
1. Show the skewed pool (lots of seniors, lots from the North)
2. Draw jury (Fair QAOA) → balanced jury + chart (`fig4`)
3. Open the receipt
4. Draw again → a different, equally balanced jury
5. "Is the algorithm fair?" tab → run the fairness test

### Slide 6: The discovery (A, 45 s)
**Title:** A fair jury needs a fair algorithm
**Chart:** `fig1_who_gets_picked_n12.png`
**Say:** "Nine juries are equally balanced, so each should be picked 11% of the time. Standard QAOA picks some 3.2× more than others. Nobody chose that bias; it's built into the algorithm."

### Slide 7: The fix (A, 45 s)
**Title:** Grover-mixer QAOA: equal cost → equal chance, guaranteed
- Start from every valid jury at once (Dicke state)
- Grover mixer keeps equally fair juries exactly equal
**Chart:** `fig2_summary.png`
**Say:** "It's perfectly even, 1.00×, and it finds a fair jury far more often: 82% vs 21%."

### Slide 8: Real hardware, honestly (A, 30 s)
**Chart:** `fig5_hardware.png` (or `fig5_hardware_fake.png`)
**Say:** "The fair circuit is about 10× deeper. On today's noisy chips, noise erases its advantage. The algorithm is provably fair; the hardware isn't ready yet, and our tool measures that gap."

### Slide 9: Honest limits (C, 20 s)
- Small pools (1 qubit per juror); classical computers solve this size easily
- Fair juries ≠ equal chances for each individual (`fig3`)
- Synthetic data; balance on neighbourhood/age/gender, not race directly

### Slide 10: Close (C, 15 s)
**Title:** If quantum computers ever help make public decisions, the algorithm has to be fair too.
**Say:** "Qubench makes that fairness measurable. Thank you."
