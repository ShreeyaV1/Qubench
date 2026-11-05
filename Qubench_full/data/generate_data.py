"""
Qubench - synthetic data generator
-----------------------------------
Creates, in this folder:
  - jurors_6.csv   : 6 fake potential jurors  (tiny - best for real IBM hardware)
  - jurors_8.csv   : 8 fake potential jurors  (main demo)
  - jurors_12.csv  : 12 fake potential jurors (simulator, for the scaling result)
  - targets.csv    : the community's makeup that a fair jury should match

All people are made up. No real personal data is used.
The pools are skewed ON PURPOSE (too many seniors, too many from the North)
so the demo can show Qubench picking a balanced jury from an unbalanced list.

Run with:  python generate_data.py
"""

import csv
import random
from pathlib import Path

SEED = 7  # same seed -> same jurors every time (good for demos)

# What a fair jury should look like (shares add up to 1.0 per attribute)
COMMUNITY_TARGETS = {
    "neighbourhood": {"North": 0.25, "South": 0.25, "East": 0.25, "West": 0.25},
    "age_group":     {"18-34": 0.30, "35-54": 0.35, "55+": 0.35},
    "gender":        {"Woman": 0.50, "Man": 0.50},
}

# How the (skewed) pool is drawn
POOL_WEIGHTS = {
    "neighbourhood": {"North": 0.40, "South": 0.20, "East": 0.20, "West": 0.20},
    "age_group":     {"18-34": 0.20, "35-54": 0.25, "55+": 0.55},
    "gender":        {"Woman": 0.50, "Man": 0.50},
}

FIRST_NAMES = ["Aria", "Kofi", "Mei", "Liam", "Priya", "Mateo", "Noor", "Ethan", "Ayasha", "Jun",
               "Sofia", "Omar", "Chloe", "Ravi", "Isla", "Tariq", "Hana", "Lucas", "Amara", "Diego"]
LAST_NAMES = ["Testwood", "Sampleton", "Mockridge", "Fauxley", "Demoss", "Placeholder",
              "Dummyson", "Exampleby", "Synthwell", "Notreal"]


def make_pool(rng, size):
    """Create `size` fake jurors with unique names, drawn from the skewed POOL_WEIGHTS."""
    used, jurors = set(), []
    for i in range(1, size + 1):
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        while name in used:
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        used.add(name)
        juror = {"juror_id": f"J{i:02d}", "name": name}
        for attribute, weights in POOL_WEIGHTS.items():
            juror[attribute] = rng.choices(list(weights), weights=list(weights.values()))[0]
        jurors.append(juror)
    return jurors


def every_group_present(jurors):
    """Every group must appear at least once, otherwise a balanced jury is impossible."""
    return all(set(groups) <= {j[attr] for j in jurors} for attr, groups in COMMUNITY_TARGETS.items())


def write_pool(path, jurors):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["juror_id", "name", "neighbourhood", "age_group", "gender"])
        writer.writeheader()
        writer.writerows(jurors)


def main():
    out = Path(__file__).parent
    rng = random.Random(SEED)
    for size in (8, 12):
        jurors = make_pool(rng, size)
        while not every_group_present(jurors):
            jurors = make_pool(rng, size)
        write_pool(out / f"jurors_{size}.csv", jurors)
        print(f"Created jurors_{size}.csv")

    # Tiny pool for real hardware (separate seed so the 8/12 pools stay the same)
    rng6 = random.Random(SEED + 100)
    for size in (6,):
        jurors = make_pool(rng6, size)
        while not every_group_present(jurors):
            jurors = make_pool(rng6, size)
        write_pool(out / f"jurors_{size}.csv", jurors)
        print(f"Created jurors_{size}.csv")

    with open(out / "targets.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["attribute", "group", "community_share"])
        for attribute, groups in COMMUNITY_TARGETS.items():
            for group, share in groups.items():
                writer.writerow([attribute, group, share])
    print("Created targets.csv")


if __name__ == "__main__":
    main()
