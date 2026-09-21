#!/usr/bin/env python3
"""Backtracking router: 'the disease does not exist' is a LEVEL-1 decision only.

TWO CORRECTIONS THIS IMPLEMENTS

1. ESCALATION BELONGS AT LEVEL 1.
   Level 2 sees one category of ~250 conditions. From inside that category it
   cannot tell 'this disease is not in our system' from 'you brought me to the
   wrong shelf'. Only level 1 sees all 24 categories, so only level 1 can
   honestly say the disease is absent.

   The old router conflated the two: L2's none_of_these was reported as an
   escalation, which is why the audit found 7 of 11 'honest refusals' were
   really misroutes. Now:

       L1 none_of_these  -> ESCALATE. Genuinely nothing fits. Honest.
       L2 wrong_branch   -> BACKTRACK. Not an escalation, a routing signal.

2. BACKTRACK WITH EXCLUSION.
   When L2 says wrong_branch we return to L1 and re-ask - with the failed
   category REMOVED from the options, so it cannot be chosen again. Without
   exclusion the model re-picks its previous favourite and loops.

   This is depth-first search with backtracking over the taxonomy, not a
   one-shot descent. Cost is bounded by --max-tries.

Escalation is therefore only ever reported when level 1, looking at every
remaining category, declines to commit - which is the only place that claim
can honestly be made.
"""
import argparse, json, os, pathlib, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from hierarchical_router import Jev            # noqa: E402

KEY = os.environ.get("OPENJEV_API_KEY", "")


def load_tax(multi=True):
    f = "taxonomy_multi.json" if multi else "taxonomy.json"
    return json.loads((HERE / f).read_text())


def route(state, jev, tax, max_tries=3, min_cat=0.25, min_leaf=0.25,
          verbose=False):
    cats, tree = tax["categories"], tax["tree"]
    excluded, trail = [], []

    for attempt in range(1, max_tries + 1):
        # ---------------------------------------------------------- level 1
        available = {c: d for c, d in cats.items()
                     if tree.get(c) and c not in excluded}
        if not available:
            return {"escalated": True, "reason": "all_categories_exhausted",
                    "trail": trail, "attempts": attempt - 1}

        crit = dict(available)
        # The ONLY honest escalation point: level 1 can see everything left.
        crit["not_in_this_system"] = (
            "This illness does not belong to any of these categories. It is "
            "outside what this system can assess and needs a clinician.")
        if excluded:
            crit["not_in_this_system"] += (
                f" (Already ruled out: {', '.join(excluded)}.)")

        a = jev.ask(state, {"cat": {
            "type": "choice",
            "instructions": (
                "Which single category of disease best explains this patient's "
                "presentation? Choose not_in_this_system only if the illness "
                "fits none of the categories listed."),
            "criteria": crit}})["cat"]
        cat, cconf = a["choice"], a["confidence"]

        if verbose:
            print(f"  [try {attempt}] L1 -> {cat} ({cconf:.2f})"
                  + (f"  excluded={excluded}" if excluded else ""))

        # L1 escalation: honest, because L1 saw every remaining category
        if cat == "not_in_this_system":
            return {"escalated": True, "reason": "not_in_this_system",
                    "cat_conf": cconf, "trail": trail, "attempts": attempt,
                    "backtracks": len(trail), "honest": True}
        if cconf < min_cat:
            return {"escalated": True,
                    "reason": f"no_category_confident_enough_{cconf:.2f}",
                    "trail": trail, "attempts": attempt,
                    "backtracks": len(trail), "honest": True}

        # ---------------------------------------------------------- level 2
        leaves = tree[cat]
        crit2 = {c: c for c in leaves}
        # NOT an escalation - a routing signal meaning 'wrong shelf'.
        crit2["wrong_branch"] = (
            "None of these conditions fits. The patient's illness belongs to a "
            "different category of disease, not this one.")

        b = jev.ask(state, {"dx": {
            "type": "choice",
            "instructions": (
                "Within this category, which single condition best explains "
                "this patient's illness? Choose wrong_branch if the illness "
                "clearly belongs to a different category of disease."),
            "criteria": crit2}})["dx"]
        dx, dconf = b["choice"], b["confidence"]
        p2 = sorted(b["probabilities"].items(), key=lambda x: -x[1])

        if verbose:
            print(f"           L2 -> {dx} ({dconf:.2f}) from {len(leaves)} options")

        if dx == "wrong_branch" or dconf < min_leaf:
            why = "wrong_branch" if dx == "wrong_branch" else f"low_conf_{dconf:.2f}"
            trail.append({"category": cat, "cat_conf": cconf, "rejected": why})
            excluded.append(cat)          # never offer this category again
            continue                      # back up to level 1

        return {"escalated": False, "diagnosis": dx, "confidence": dconf,
                "cat": cat, "cat_conf": cconf, "attempts": attempt,
                "backtracks": len(trail), "trail": trail,
                "n_options": len(leaves),
                "top3": [(k, round(v, 3)) for k, v in p2[:3]],
                "path": f"{cat} > {dx}"}

    return {"escalated": True, "reason": f"exhausted_after_{max_tries}_tries",
            "trail": trail, "attempts": max_tries,
            "backtracks": len(trail), "honest": False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state", nargs="?")
    ap.add_argument("--max-tries", type=int, default=3)
    ap.add_argument("--single", action="store_true",
                    help="use the single-label taxonomy instead")
    args = ap.parse_args()
    if not KEY:
        sys.exit("no OPENJEV_API_KEY")
    if not args.state:
        sys.exit("give a state file")

    tax = load_tax(multi=not args.single)
    print(f"taxonomy: {sum(len(v) for v in tax['tree'].values()):,} entries "
          f"across {len(tax['tree'])} categories")
    jev = Jev(KEY)
    r = route(pathlib.Path(args.state).read_text(), jev, tax,
              max_tries=args.max_tries, verbose=True)
    print(json.dumps(r, indent=1))
    print(f"cost ${jev.cost:.5f}  calls {jev.calls}")


if __name__ == "__main__":
    main()
