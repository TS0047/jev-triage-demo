#!/usr/bin/env python3
"""Wide two-level router: 1,878 conditions in 2 API calls.

SHAPE
    level 1   24 categories        one call
    level 2   up to 240 conditions one call
    total     1,878 addressable, ceiling 24 x 255 = 6,120

Two levels, not six. Routing error compounds as p^d, so depth is expensive:
at p=0.95, two levels reach the right leaf 90.3% of the time and four levels
81.5%. Width is free up to the 255-per-call cap, so the correct shape is the
widest tree that fits.

SAFETY
An escape hatch at BOTH levels, because a wrong turn at level 1 is
unrecoverable - the right answer is then not in the level-2 list at all, and
the model would be forced to pick the least-bad wrong option. Escalating on
an uncertain category is the whole point of having the hatch.

Level-1 confidence below --min-cat escalates rather than descending on a
guess. Multi-category cases (the level-1 distribution is flat) also escalate.
"""
import argparse, json, os, pathlib, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from hierarchical_router import Jev            # noqa: E402

KEY = os.environ.get("OPENJEV_API_KEY", "")
TAX = json.loads((HERE / "taxonomy.json").read_text())


def route(state, jev, min_cat=0.35, min_leaf=0.30, verbose=False,
          taxonomy=None):
    tax = taxonomy or TAX
    cats, tree = tax["categories"], tax["tree"]

    # ---------------------------------------------------- level 1: category
    crit = {c: d for c, d in cats.items() if tree.get(c)}
    crit["none_of_these"] = (
        "The presentation does not fit any of these categories, or fits "
        "several equally well and cannot be narrowed from the information given.")
    a = jev.ask(state, {"cat": {
        "type": "choice",
        "instructions": ("Which single category of disease best explains this "
                         "patient's presentation? Choose none_of_these if no "
                         "category clearly fits."),
        "criteria": crit}})["cat"]

    cat, cat_conf = a["choice"], a["confidence"]
    probs = sorted(a["probabilities"].items(), key=lambda x: -x[1])
    if verbose:
        print(f"  L1 {cat} ({cat_conf:.2f})  runners-up: "
              f"{[(k, round(v,2)) for k, v in probs[1:3]]}")

    if cat == "none_of_these":
        return {"escalated": True, "reason": "no_category_fits",
                "cat_conf": cat_conf}
    if cat_conf < min_cat:
        return {"escalated": True, "reason": f"category_uncertain_{cat_conf:.2f}",
                "cat": cat, "cat_conf": cat_conf}

    # ---------------------------------------------------- level 2: condition
    leaves = tree.get(cat, [])
    if not leaves:
        return {"escalated": True, "reason": f"empty_category_{cat}"}

    crit2 = {c: c for c in leaves}
    crit2["none_of_these"] = (
        "None of these specific conditions explains the presentation.")
    b = jev.ask(state, {"dx": {
        "type": "choice",
        "instructions": ("Within this category, which single condition best "
                         "explains this patient's illness? Choose none_of_these "
                         "if none fits."),
        "criteria": crit2}})["dx"]

    dx, dx_conf = b["choice"], b["confidence"]
    p2 = sorted(b["probabilities"].items(), key=lambda x: -x[1])
    if verbose:
        print(f"  L2 {dx} ({dx_conf:.2f}) from {len(leaves)} options")

    if dx == "none_of_these":
        return {"escalated": True, "reason": "no_condition_in_category",
                "cat": cat, "cat_conf": cat_conf}
    if dx_conf < min_leaf:
        return {"escalated": True, "reason": f"condition_uncertain_{dx_conf:.2f}",
                "cat": cat, "dx": dx, "conf": dx_conf}

    return {"escalated": False, "cat": cat, "cat_conf": cat_conf,
            "diagnosis": dx, "confidence": dx_conf,
            "n_options": len(leaves),
            "top3": [(k, round(v, 3)) for k, v in p2[:3]],
            "path": f"{cat} > {dx}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state", nargs="?")
    ap.add_argument("--min-cat", type=float, default=0.35)
    ap.add_argument("--min-leaf", type=float, default=0.30)
    args = ap.parse_args()
    if not KEY:
        sys.exit("no OPENJEV_API_KEY")

    tree = TAX["tree"]
    print(f"taxonomy: {len([c for c in tree if tree[c]])} categories, "
          f"{sum(len(v) for v in tree.values()):,} conditions")

    if not args.state:
        sys.exit("give a state file")
    state = pathlib.Path(args.state).read_text()
    jev = Jev(KEY)
    r = route(state, jev, args.min_cat, args.min_leaf, verbose=True)
    print(json.dumps(r, indent=1))
    print(f"cost ${jev.cost:.5f}  calls {jev.calls}")


if __name__ == "__main__":
    main()
