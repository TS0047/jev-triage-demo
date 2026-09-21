#!/usr/bin/env python3
"""Does a learned discrimination matrix beat a hand-authored one?

Held-out test: fit likelihoods on a TRAIN slice, score on a DISJOINT TEST
slice. Pure naive-Bayes classification from the matrix alone, no API calls -
this isolates the quality of the NUMBERS from everything else in the system.

Three matrices compared:
  uniform   every P(e|d) = 0.5      (no information; floor)
  handish   round numbers on a coarse 0.05 grid, mimicking hand-authoring
            (the real bank's values snapped to how a human actually picks them)
  learned   maximum-likelihood counts with Jeffreys smoothing

'handish' is built by DEGRADING the learned matrix to the granularity a human
produces. That is deliberately generous to hand-authoring: a real human also
gets the direction wrong sometimes, which this does not simulate. If learned
still wins, the gap is a lower bound on the true gap.
"""
import argparse, ast, csv, json, math, pathlib, random
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).parent
DATA = HERE / "datasets"


def base(e):
    return e.split("_@_", 1)[0]


def load(path, limit):
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for i, r in enumerate(csv.DictReader(fh)):
            if limit and i >= limit:
                break
            try:
                ev = ast.literal_eval(r["EVIDENCES"])
            except (ValueError, SyntaxError):
                continue
            rows.append((r["PATHOLOGY"], {base(x) for x in ev}))
    return rows


def fit(rows, evidences, alpha=0.5):
    n_d = Counter()
    present = defaultdict(Counter)
    for d, s in rows:
        n_d[d] += 1
        for e in s:
            present[e][d] += 1
    diseases = sorted(n_d)
    like = {e: {d: (present[e][d] + alpha) / (n_d[d] + 2 * alpha)
                for d in diseases} for e in evidences}
    prior = {d: n_d[d] / len(rows) for d in diseases}
    return like, prior, diseases


def coarsen(like, step=0.05):
    """Snap to the grid a human actually authors on."""
    return {e: {d: min(0.95, max(0.05, round(v / step) * step))
                for d, v in col.items()} for e, col in like.items()}


def uniform(like):
    return {e: {d: 0.5 for d in col} for e, col in like.items()}


def classify(like, prior, evidences, s):
    """Naive Bayes in log space over present AND absent evidences."""
    best, scores = None, {}
    for d in prior:
        lp = math.log(prior[d])
        for e in evidences:
            p = like[e][d]
            p = min(max(p, 1e-6), 1 - 1e-6)
            lp += math.log(p) if e in s else math.log(1 - p)
        scores[d] = lp
        if best is None or lp > scores[best]:
            best = d
    return best, scores


def topk(scores, truth, k=5):
    order = sorted(scores, key=lambda d: -scores[d])
    return truth in order[:k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DATA / "ddx_test.csv"))
    ap.add_argument("--train", type=int, default=60000)
    ap.add_argument("--test", type=int, default=3000)
    ap.add_argument("--alpha", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    allrows = load(args.csv, args.train + args.test)
    random.Random(args.seed).shuffle(allrows)
    train = allrows[:args.train]
    test = allrows[args.train:args.train + args.test]
    evidences = sorted({e for _, s in allrows for e in s})
    print(f"train {len(train)}  test {len(test)}  evidences {len(evidences)}")

    learned, prior, diseases = fit(train, evidences, args.alpha)
    banks = {
        "uniform  (no information)": uniform(learned),
        "handish  (0.05 grid)": coarsen(learned, 0.05),
        "handish  (0.10 grid)": coarsen(learned, 0.10),
        "learned  (MLE + Jeffreys)": learned,
    }

    print(f"\n{'matrix':28s} {'top-1':>7s} {'top-3':>7s} {'top-5':>7s}")
    results = {}
    for name, bank in banks.items():
        t1 = t3 = t5 = 0
        for truth, s in test:
            pred, sc = classify(bank, prior, evidences, s)
            t1 += pred == truth
            t3 += topk(sc, truth, 3)
            t5 += topk(sc, truth, 5)
        n = len(test)
        results[name] = (t1 / n, t3 / n, t5 / n)
        print(f"{name:28s} {100*t1/n:6.1f}% {100*t3/n:6.1f}% {100*t5/n:6.1f}%")

    # how much does granularity alone cost?
    l = results["learned  (MLE + Jeffreys)"][0]
    h5 = results["handish  (0.05 grid)"][0]
    h10 = results["handish  (0.10 grid)"][0]
    print(f"\ncost of rounding to a 0.05 grid: {100*(l-h5):+.1f} pp top-1")
    print(f"cost of rounding to a 0.10 grid: {100*(l-h10):+.1f} pp top-1")
    print("\n(the real hand-authored bank ALSO picks the wrong direction sometimes,")
    print(" which this simulation does not model - so these gaps are a lower bound)")

    json.dump({"n_train": len(train), "n_test": len(test),
               "results": {k: list(v) for k, v in results.items()}},
              open(HERE / "matrix_comparison.json", "w"), indent=1)
    print("\nsaved matrix_comparison.json")


if __name__ == "__main__":
    main()
