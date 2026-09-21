#!/usr/bin/env python3
"""Is the bottleneck the number of diseases? Measure the long tail.

Two questions, both answerable from data already downloaded, no API cost:

1. HOW MANY diseases would we need to cover most real cases? If the
   distribution has a fat head, adding 200 conditions fixes it. If it is a
   long tail of singletons, no achievable list ever covers it.

2. Is the benchmark even representative? Case reports are published BECAUSE
   a case is unusual. If MedCaseReasoning's most common diagnoses are rare
   diseases, then "3.5% in scope" measures publication bias, not the coverage
   a real clinic would see.
"""
import collections, json, pathlib, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))


def main():
    import pyarrow.parquet as pq
    t = pq.read_table(HERE / "datasets" / "mcr_train.parquet",
                      columns=["final_diagnosis"])
    raw = [str(x).strip() for x in t.column("final_diagnosis").to_pylist()]
    # case-insensitive merge: 'sarcoidosis' and 'Sarcoidosis' are one disease
    c = collections.Counter(d.lower() for d in raw if d)
    n = sum(c.values())
    print(f"cases {n:,}   distinct diagnoses {len(c):,}\n")

    # ---- 1. coverage curve
    ranked = [v for _, v in c.most_common()]
    cum = 0
    marks = [0.25, 0.50, 0.75, 0.90, 0.95]
    mi = 0
    print("how many diagnoses to cover X% of real cases:")
    for i, v in enumerate(ranked, 1):
        cum += v
        while mi < len(marks) and cum / n >= marks[mi]:
            print(f"  {marks[mi]*100:4.0f}% of cases  needs {i:5,} diagnoses")
            mi += 1
    print(f"  100% of cases  needs {len(ranked):5,} diagnoses")

    for k in (49, 100, 250, 500, 1000):
        cov = sum(ranked[:k]) / n
        print(f"\n  a list of {k:5,} conditions covers {100*cov:5.1f}% of real cases")

    singles = sum(1 for v in c.values() if v == 1)
    print(f"\nsingletons: {singles:,} diagnoses seen exactly once "
          f"({100*singles/len(c):.0f}% of distinct, "
          f"{100*singles/n:.0f}% of all cases)")
    print("A disease seen once cannot have its likelihoods estimated at all.")

    # ---- 2. is this corpus representative of a clinic?
    from grids import GRIDS
    ours = sorted({x for cell in GRIDS["ddxplus"].values() for x in cell})
    print(f"\n{'='*62}")
    print("PUBLICATION BIAS CHECK")
    print("our 49 conditions are the COMMON primary-care set.")
    print("how often does each appear in a corpus of published case reports?\n")
    found = []
    for cond in ours:
        k = cond.lower()
        hits = sum(v for d, v in c.items() if k in d)
        found.append((hits, cond))
    found.sort(reverse=True)
    for hits, cond in found[:8]:
        print(f"  {hits:5,}  {cond}")
    print("   ...")
    zero = [cond for hits, cond in found if hits == 0]
    print(f"\n  {len(zero)}/49 of our common conditions NEVER appear:")
    print("   ", ", ".join(zero[:10]) + (" ..." if len(zero) > 10 else ""))

    print(f"\ntop 10 diagnoses in this 'real' corpus:")
    for d, v in c.most_common(10):
        print(f"  {v:4d}  {d[:56]}")
    print("\nThese are rare diseases. Case reports are published BECAUSE the")
    print("case is unusual - nobody publishes 'patient had a cold'. So the")
    print("3.5% in-scope rate measures publication bias, NOT the coverage a")
    print("real clinic would see.")

    json.dump({"cases": n, "distinct": len(c), "singletons": singles,
               "cov_49": sum(ranked[:49]) / n,
               "cov_500": sum(ranked[:500]) / n,
               "never_appear": len(zero)},
              open(HERE / "coverage_curve.json", "w"), indent=1)
    print("\nsaved coverage_curve.json")


if __name__ == "__main__":
    main()
