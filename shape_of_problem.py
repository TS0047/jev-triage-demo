#!/usr/bin/env python3
"""What list length would a REAL clinic need? (as opposed to a journal)

coverage_curve.py showed 49 conditions cover only 10.9% of published case
reports - but 26 of those 49 never appear in that corpus at all, because
journals do not publish 'patient had a cold'. Published cases are selected
for rarity; they are the worst possible estimate of clinic prevalence.

This re-asks the question against DDXPlus, whose 49 pathologies were chosen
to reflect what actually walks into primary care, and against the published
epidemiology of primary-care presentations.

The conclusion either way is about the SHAPE of the distribution, which is
what determines whether 'add more diseases' is a strategy or a treadmill.
"""
import collections, json, pathlib, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))


def zipf_coverage(n_conditions, alpha=1.0, universe=10000):
    """Disease prevalence follows roughly a Zipf/power law. Coverage of the
    top-k under Zipf(alpha) over a universe of `universe` conditions."""
    import math
    H = lambda k: sum(1.0 / (i ** alpha) for i in range(1, k + 1))
    return H(n_conditions) / H(universe)


def main():
    print("THE SHAPE OF THE PROBLEM\n")
    print("Disease prevalence is heavy-tailed. Under a Zipf law, coverage of")
    print("the top-k conditions out of ~10,000 known human diseases:\n")
    print(f"  {'list size':>10s}  {'coverage':>9s}   {'to add +10pp':>14s}")
    prev = None
    for k in (10, 49, 100, 255, 500, 1000, 2500, 5000):
        cov = zipf_coverage(k)
        extra = ""
        if prev is not None:
            extra = f"{k - prev_k:,} more"
        print(f"  {k:10,}  {100*cov:8.1f}%   {extra:>14s}")
        prev, prev_k = cov, k

    print("\nEach fixed gain in coverage costs exponentially more conditions.")
    print("That is the treadmill: doubling the list adds a few points.\n")

    print("=" * 62)
    print("WHAT ACTUALLY HAPPENS IN PRIMARY CARE\n")
    # DDXPlus's 49 were chosen for primary-care realism; its own class
    # distribution is the best available proxy we have locally.
    import csv, ast
    path = HERE / "datasets" / "ddx_test.csv"
    c = collections.Counter()
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            c[row["PATHOLOGY"]] += 1
    n = sum(c.values())
    ranked = [v for _, v in c.most_common()]
    print(f"DDXPlus models a primary-care population ({n:,} patients, "
          f"{len(c)} conditions).")
    print("Its own concentration:")
    for k in (5, 10, 20, 49):
        print(f"  top {k:2d} conditions = {100*sum(ranked[:k])/n:5.1f}% of patients")

    print("\nIn a real clinic a short list covers most patients. The tail is")
    print("long but each tail item is individually rare - which is exactly")
    print("why 'escalate' is a legitimate answer for it, not a cop-out.\n")

    print("=" * 62)
    print("SO WHICH PROBLEM DO WE ACTUALLY HAVE?\n")
    findings = [
        ("Can we estimate likelihoods with the data we have?",
         "YES - saturated at 2,500 patients (learning_curve.py). More data "
         "buys 0.2pp."),
        ("Is 49 conditions too few for published case reports?",
         "YES - 10.9% coverage. But 26 of our 49 never appear there at all, "
         "so that corpus is measuring rarity, not coverage."),
        ("Is 49 too few for a real clinic?",
         "Partly. The common presentations are mostly covered; the tail is "
         "not, and never will be."),
        ("Would adding 200 more conditions fix it?",
         "NO - Zipf says +200 buys single-digit coverage, and each new "
         "condition needs hand-authored likelihoods that are 5x more "
         "dangerous when wrong in DIRECTION (noise_sensitivity.py)."),
        ("What is the actual bottleneck?",
         "Labelled cases PER disease for the tail. 74% of real diagnoses "
         "appear exactly once - you cannot estimate P(finding|disease) from "
         "one case, at any list length."),
    ]
    for q, a in findings:
        print(f"  Q: {q}")
        print(f"  A: {a}\n")

    json.dump({"zipf": {str(k): zipf_coverage(k)
                        for k in (10, 49, 100, 255, 500, 1000, 2500, 5000)},
               "ddxplus_top10_share": sum(ranked[:10]) / n},
              open(HERE / "shape_of_problem.json", "w"), indent=1)
    print("saved shape_of_problem.json")


if __name__ == "__main__":
    main()
