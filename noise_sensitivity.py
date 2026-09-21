#!/usr/bin/env python3
"""What actually degrades a discrimination matrix: precision or direction?

compare_matrices.py showed rounding a learned matrix to a 0.05 grid costs only
0.3pp. So the exact decimals barely matter. This isolates the failure mode that
does: getting the DIRECTION wrong - saying a finding favours disease X when the
data says it does not. That is the error a human actually makes, and no amount
of decimal precision protects against it.

Injects, into a learned matrix:
  - swap noise: for a fraction of (evidence, disease) cells, replace P(e|d)
    with a plausible-but-wrong value drawn from another disease's column
  - flip noise: replace P(e|d) with 1 - P(e|d)

Then rescores. The slope tells you how much authoring error you can tolerate.
"""
import argparse, json, math, pathlib, random
import compare_matrices as CM

HERE = pathlib.Path(__file__).parent


def corrupt(like, diseases, frac, mode, rng):
    out = {e: dict(col) for e, col in like.items()}
    cells = [(e, d) for e in like for d in diseases]
    rng.shuffle(cells)
    for e, d in cells[:int(len(cells) * frac)]:
        if mode == "flip":
            out[e][d] = 1.0 - out[e][d]
        else:
            other = rng.choice(diseases)
            out[e][d] = like[e][other]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(HERE / "datasets" / "ddx_test.csv"))
    ap.add_argument("--train", type=int, default=40000)
    ap.add_argument("--test", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    rows = CM.load(args.csv, args.train + args.test)
    random.Random(args.seed).shuffle(rows)
    train, test = rows[:args.train], rows[args.train:args.train + args.test]
    evidences = sorted({e for _, s in rows for e in s})
    like, prior, diseases = CM.fit(train, evidences, 0.5)
    rng = random.Random(args.seed)

    print(f"train {len(train)}  test {len(test)}\n")
    print(f"{'corruption':34s} {'top-1':>7s} {'top-5':>7s}")

    results = {}
    base_t1 = None
    for mode in ("swap", "flip"):
        for frac in (0.0, 0.02, 0.05, 0.10, 0.20, 0.35):
            if frac == 0.0 and mode == "flip":
                continue
            bank = like if frac == 0 else corrupt(like, diseases, frac, mode, rng)
            t1 = t5 = 0
            for truth, s in test:
                pred, sc = CM.classify(bank, prior, evidences, s)
                t1 += pred == truth
                t5 += CM.topk(sc, truth, 5)
            n = len(test)
            label = "none (learned)" if frac == 0 else f"{mode} {int(frac*100)}% of cells"
            if frac == 0:
                base_t1 = t1 / n
            print(f"{label:34s} {100*t1/n:6.1f}% {100*t5/n:6.1f}%")
            results[label] = (t1 / n, t5 / n)

    print(f"\nA 5% direction error costs "
          f"{100*(base_t1 - results['swap 5% of cells'][0]):.1f}pp top-1.")
    print("Rounding every value to a 0.05 grid cost 0.3pp (compare_matrices.py).")
    print("=> DIRECTION dominates PRECISION. Author the sign confidently;")
    print("   do not agonise over the second decimal.")

    json.dump(results, open(HERE / "noise_sensitivity.json", "w"), indent=1)
    print("\nsaved noise_sensitivity.json")


if __name__ == "__main__":
    main()
