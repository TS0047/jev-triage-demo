#!/usr/bin/env python3
"""Does MORE data improve the discrimination matrix? Learning curve on DDXPlus.

Before chasing a bigger dataset, find out whether the current one is already
saturated. Fits the likelihood matrix on increasing numbers of patients and
scores each fit on the SAME held-out test set.

If accuracy plateaus early, "get a bigger dataset" is the wrong next move and
the constraint is somewhere else entirely.
"""
import argparse, json, pathlib, random
import compare_matrices as CM

HERE = pathlib.Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(HERE / "datasets" / "ddx_test.csv"))
    ap.add_argument("--test", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rows = CM.load(args.csv, None)
    random.Random(args.seed).shuffle(rows)
    test = rows[:args.test]
    pool = rows[args.test:]
    evidences = sorted({e for _, s in rows for e in s})
    print(f"pool {len(pool)}  test {len(test)}  evidences {len(evidences)}\n")

    sizes = [50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000,
             100000, len(pool)]
    print(f"{'train n':>9s} {'top-1':>7s} {'top-3':>7s} {'top-5':>7s}")
    out = {}
    for n in sizes:
        if n > len(pool):
            continue
        like, prior, _ = CM.fit(pool[:n], evidences, 0.5)
        t1 = t3 = t5 = 0
        for truth, s in test:
            pred, sc = CM.classify(like, prior, evidences, s)
            t1 += pred == truth
            t3 += CM.topk(sc, truth, 3)
            t5 += CM.topk(sc, truth, 5)
        m = len(test)
        out[n] = (t1 / m, t3 / m, t5 / m)
        print(f"{n:>9,} {100*t1/m:6.1f}% {100*t3/m:6.1f}% {100*t5/m:6.1f}%")

    ks = sorted(out)
    print(f"\nfrom {ks[0]:,} to {ks[-1]:,} patients: "
          f"{100*out[ks[0]][0]:.1f}% -> {100*out[ks[-1]][0]:.1f}% top-1")
    # find the knee: smallest n within 1pp of the best
    best = max(v[0] for v in out.values())
    knee = min(n for n, v in out.items() if v[0] >= best - 0.01)
    print(f"within 1pp of the best at n = {knee:,} "
          f"({100*out[knee][0]:.1f}% vs best {100*best:.1f}%)")
    print(f"=> everything past ~{knee:,} patients buys "
          f"{100*(best-out[knee][0]):.1f}pp")

    json.dump({str(k): list(v) for k, v in out.items()},
              open(HERE / "learning_curve.json", "w"), indent=1)
    print("\nsaved learning_curve.json")


if __name__ == "__main__":
    main()
