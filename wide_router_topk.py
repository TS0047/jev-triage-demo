#!/usr/bin/env python3
"""Fix for the dominant failure: descend into the top-K categories, not one.

The audit found 7 of 11 escalations were level-1 misroutes - the condition
existed but in a category we never opened. Two structural causes, and neither
is the model being stupid:

  1. A disease can legitimately sit in several categories. 'Malignant syphilis'
     is an infection whose NAME contains 'malignant', so the keyword rules
     filed it under neoplasm_carcinoma; Jev sensibly chose infection_bacterial.
     The taxonomy was wrong, not the routing.

  2. A presentation is genuinely multi-category. The cysticercosis case was
     ocular cysticercosis - Jev chose ophthalmic_ent, which is where an eye
     presentation belongs. It just is not where the parasite was filed.

Single-category descent turns both into unrecoverable losses. Descending into
the top-K categories and pooling the candidates fixes both at the cost of
K-1 extra calls, and lets the final choice be made across categories rather
than inside a guessed one.
"""
import argparse, json, os, pathlib, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from hierarchical_router import Jev            # noqa: E402

KEY = os.environ.get("OPENJEV_API_KEY", "")
TAX = json.loads((HERE / "taxonomy.json").read_text())


def route_topk(state, jev, k=2, min_cat=0.12, min_leaf=0.25, pool_cap=250,
               verbose=False, taxonomy=None):
    tax = taxonomy or TAX
    cats, tree = tax["categories"], tax["tree"]

    crit = {c: d for c, d in cats.items() if tree.get(c)}
    crit["none_of_these"] = ("The presentation fits no category, or fits "
                             "several and cannot be narrowed.")
    a = jev.ask(state, {"cat": {
        "type": "choice",
        "instructions": ("Which single category of disease best explains this "
                         "patient's presentation? Choose none_of_these if no "
                         "category clearly fits."),
        "criteria": crit}})["cat"]
    probs = sorted(a["probabilities"].items(), key=lambda x: -x[1])
    if a["choice"] == "none_of_these" and probs[0][0] == "none_of_these":
        return {"escalated": True, "reason": "no_category_fits"}

    chosen = [c for c, p in probs
              if c != "none_of_these" and p >= min_cat and tree.get(c)][:k]
    if not chosen:
        chosen = [c for c, _ in probs if c != "none_of_these" and tree.get(c)][:1]
    if verbose:
        print(f"  L1 descending into {chosen} "
              f"(from {[(c, round(p,2)) for c, p in probs[:4]]})")

    # pool candidates from every chosen category, keeping provenance
    pool, origin = [], {}
    for c in chosen:
        for leaf in tree[c]:
            if leaf not in origin:
                origin[leaf] = c
                pool.append(leaf)
    if len(pool) > pool_cap:                      # stay under the 255 cap
        per = pool_cap // len(chosen)
        pool, origin = [], {}
        for c in chosen:
            for leaf in tree[c][:per]:
                if leaf not in origin:
                    origin[leaf] = c
                    pool.append(leaf)

    crit2 = {c: c for c in pool}
    crit2["none_of_these"] = "None of these conditions explains the presentation."
    b = jev.ask(state, {"dx": {
        "type": "choice",
        "instructions": ("Which single condition best explains this patient's "
                         "illness? Choose none_of_these if none fits."),
        "criteria": crit2}})["dx"]
    dx, conf = b["choice"], b["confidence"]
    if verbose:
        print(f"  L2 {dx} ({conf:.2f}) from {len(pool)} pooled options")

    if dx == "none_of_these":
        return {"escalated": True, "reason": "no_condition_in_pool",
                "cats": chosen}
    if conf < min_leaf:
        return {"escalated": True, "reason": f"condition_uncertain_{conf:.2f}",
                "cats": chosen, "dx": dx}
    return {"escalated": False, "diagnosis": dx, "confidence": conf,
            "cat": origin.get(dx), "cats": chosen, "n_options": len(pool),
            "path": f"{origin.get(dx)} > {dx}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state", nargs="?")
    ap.add_argument("--k", type=int, default=2)
    args = ap.parse_args()
    if not KEY:
        sys.exit("no OPENJEV_API_KEY")
    if not args.state:
        sys.exit("give a state file")
    jev = Jev(KEY)
    r = route_topk(pathlib.Path(args.state).read_text(), jev, k=args.k,
                   verbose=True)
    print(json.dumps(r, indent=1))
    print(f"cost ${jev.cost:.5f} calls {jev.calls}")


if __name__ == "__main__":
    main()
