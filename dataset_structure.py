#!/usr/bin/env python3
"""Is the ceiling the data volume, or the dataset's own structure?

learning_curve.py showed accuracy saturating at ~2,500 patients out of 131,529.
So volume is not the constraint. This asks what IS.

Two probes:

1. COVERAGE - how many distinct (pathology) classes and how much evidence
   variety exists. A dataset can be huge and still narrow.

2. DETERMINISM - how much of DDXPlus is reducible to a lookup. If a given
   evidence SET maps to exactly one pathology almost always, the dataset is a
   rule-based generator being inverted, and 99% accuracy measures how
   invertible that generator is - not clinical skill. Real patients collide:
   the same symptom set legitimately occurs with different diagnoses.

The collision rate is the honest measure of how realistic a dataset is.
"""
import argparse, json, pathlib, random
from collections import Counter, defaultdict
import compare_matrices as CM

HERE = pathlib.Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(HERE / "datasets" / "ddx_test.csv"))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    rows = CM.load(args.csv, args.limit)
    print(f"patients: {len(rows):,}")

    paths = Counter(d for d, _ in rows)
    print(f"pathologies: {len(paths)}")
    print(f"evidences: {len({e for _, s in rows for e in s})}")

    sizes = [len(s) for _, s in rows]
    print(f"evidences per patient: min {min(sizes)}  "
          f"median {sorted(sizes)[len(sizes)//2]}  max {max(sizes)}")

    print(f"\nclass balance: most common {paths.most_common(1)[0][1]:,}, "
          f"rarest {min(paths.values()):,} "
          f"(ratio {paths.most_common(1)[0][1]/min(paths.values()):.1f}x)")

    # --- determinism: does an evidence set determine the pathology?
    by_set = defaultdict(Counter)
    for d, s in rows:
        by_set[frozenset(s)][d] += 1

    uniq = len(by_set)
    collide = sum(1 for k, c in by_set.items() if len(c) > 1)
    patients_in_collision = sum(sum(c.values()) for c in by_set.values()
                                if len(c) > 1)
    print(f"\ndistinct evidence sets: {uniq:,} over {len(rows):,} patients")
    print(f"sets mapping to >1 pathology: {collide:,} "
          f"({100*collide/uniq:.2f}% of sets)")
    print(f"patients in an ambiguous set: {patients_in_collision:,} "
          f"({100*patients_in_collision/len(rows):.2f}%)")

    # Bayes-optimal ceiling: always guess the majority class for each set
    correct = sum(c.most_common(1)[0][1] for c in by_set.values())
    print(f"\nlookup-table ceiling (memorise every set): "
          f"{100*correct/len(rows):.2f}%")
    print("A model scoring near this is inverting the generator, not reasoning.")

    # --- how much do the differentials themselves overlap?
    print("\nInterpretation:")
    if patients_in_collision / len(rows) < 0.05:
        print("  DDXPlus is near-deterministic. The same symptoms almost always")
        print("  imply the same diagnosis, which real clinical data never does.")
        print("  High accuracy here does NOT transfer to real patients.")
    else:
        print("  Meaningful ambiguity present.")

    json.dump({"patients": len(rows), "pathologies": len(paths),
               "distinct_sets": uniq, "colliding_sets": collide,
               "patients_in_collision": patients_in_collision,
               "lookup_ceiling": correct / len(rows)},
              open(HERE / "dataset_structure.json", "w"), indent=1)
    print("\nsaved dataset_structure.json")


if __name__ == "__main__":
    main()
