#!/usr/bin/env python3
"""The option list IS the hypothesis space. Nothing here is trained.

The observation this tests: we never train anything. Jev is frozen behind an
API. We hand it a list of options and it returns a distribution over THAT list.
So why did adding a disease name rescue 8/12 real cases?

Because the list is not a hint. It is the sample space. A condition absent
from the list does not have a low probability - it has NO probability. The
model cannot return an answer it was not offered, no matter how obvious the
case. That is a representational limit, not a knowledge limit.

This script demonstrates the difference and measures its consequence.

PART A  same case, same model, list is the only variable
PART B  do we need authored likelihoods to add conditions? (no - and this
        corrects an overstatement in BOTTLENECK.md)
"""
import argparse, collections, json, os, pathlib, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import eval_realcases as E                      # noqa: E402
from hierarchical_router import Jev             # noqa: E402

KEY = os.environ.get("OPENJEV_API_KEY", "")


def ask(state, options, instructions=None):
    crit = {c: c for c in options}
    crit["outside_differential"] = (
        "None of the listed conditions explains this presentation.")
    jev = Jev(KEY)
    a = jev.ask(state, {"dx": {
        "type": "choice",
        "instructions": instructions or (
            "Based only on the information in the state, which single option "
            "best explains this patient's illness?"),
        "criteria": crit}})["dx"]
    probs = sorted(a["probabilities"].items(), key=lambda x: -x[1])
    return a["choice"], a["confidence"], probs[:3], jev.cost


def corpus_top(n):
    """Top-n diagnoses by frequency in the real corpus.

    This is a DATA-DERIVED list of NAMES. No likelihoods, no authoring, no
    clinical judgement from me - just 'these are the things that actually
    occur'. That is the whole point: names are cheap, matrices are not.
    """
    import pyarrow.parquet as pq
    t = pq.read_table(HERE / "datasets" / "mcr_train.parquet",
                      columns=["final_diagnosis"])
    c = collections.Counter(str(x).strip().lower()
                            for x in t.column("final_diagnosis").to_pylist()
                            if x and str(x).strip())
    return [d for d, _ in c.most_common(n)], c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["a", "b", "both"], default="both")
    ap.add_argument("--n", type=int, default=14)
    ap.add_argument("--listsize", type=int, default=200)
    args = ap.parse_args()
    if not KEY:
        sys.exit("no OPENJEV_API_KEY")

    ours, idx = E.scope_index()
    cost = 0.0

    # ---------------------------------------------------------------- PART A
    if args.part in ("a", "both"):
        print("PART A - the list is the sample space, not a hint\n")
        cases = E.load_cases(40, 0, 5)
        target = None
        for p, t, _ in cases:
            if not E.in_scope(t, idx) and len(p) > 400:
                target = (p, t)
                break
        prompt, truth = target
        state = E.to_state(prompt)
        print(f"case: {truth}\n")

        pred, conf, top, c = ask(state, ours)
        cost += c
        print(f"  list WITHOUT the truth ({len(ours)} options):")
        print(f"    -> {pred}  conf {conf:.2f}")
        print(f"       top3 {top}")

        pred2, conf2, top2, c = ask(state, ours + [truth])
        cost += c
        print(f"\n  list WITH the truth ({len(ours)+1} options):")
        print(f"    -> {pred2}  conf {conf2:.2f}")
        print(f"       top3 {top2}")
        print("\n  Same model. Same case. Same weights. Nothing was trained,")
        print("  fine-tuned, or updated between these two calls. The ONLY")
        print("  difference is whether the answer was representable.\n")

    # ---------------------------------------------------------------- PART B
    if args.part in ("b", "both"):
        print("=" * 66)
        print("PART B - can we add conditions with NAMES ONLY, no likelihoods?\n")
        names, counter = corpus_top(args.listsize)
        ours_l = {x.lower() for x in ours}
        # honest test set: truth is in the BIG list but NOT in our 49, and the
        # big list was built from corpus frequency, independent of these cases
        cases = E.load_cases(600, 0, 5)
        pool = [(p, t) for p, t, _ in cases
                if t.strip().lower() in set(names)
                and t.strip().lower() not in ours_l
                and not E.in_scope(t, idx)]
        pool = pool[:args.n]
        print(f"big list: top-{args.listsize} diagnoses by corpus frequency")
        print("          (names harvested from data; ZERO authored likelihoods)")
        print(f"test set: {len(pool)} real cases in the big list, outside our 49\n")

        base_hit = big_hit = 0
        for p, t in pool:
            state = E.to_state(p)
            p1, c1, _, c = ask(state, ours)
            cost += c
            p2, c2, _, c = ask(state, names)
            cost += c
            b1 = p1.strip().lower() == t.strip().lower()
            b2 = p2.strip().lower() == t.strip().lower()
            base_hit += b1
            big_hit += b2
            print(f"  {t[:34]:34s} | 49:{('HIT' if b1 else '-'):3s} {p1[:18]:18s}"
                  f" | {args.listsize}:{('HIT' if b2 else '-'):3s} {p2[:20]:20s}")

        n = len(pool)
        print(f"\n  our 49 conditions      : {base_hit}/{n}")
        print(f"  top-{args.listsize} names, no matrix: {big_hit}/{n}")
        print("\n  Adding conditions costs NOTHING but the name. The 450,000")
        print("  hand-authored cells in BOTTLENECK.md are only needed for the")
        print("  adaptive QUESTION loop (triage_loop.py), not for classifying.")

    print(f"\ntotal cost ${cost:.4f}")


if __name__ == "__main__":
    main()
