#!/usr/bin/env python3
"""Estimate P(evidence | pathology) from data instead of authoring it by hand.

THE PROBLEM
findings_bank.json holds a discrimination matrix: for each finding, how likely
it is given each disease. Those numbers were hand-authored - 20 distinct values
clustering on 0.05/0.10/0.15/0.20, which is what a human picking plausible
numbers produces. They are adequate for RANKING which question to ask next and
inadequate as a reported posterior.

THE RIGHT TOOL
This is not a reinforcement learning problem. It is density estimation with a
closed-form maximum-likelihood solution: count.

    P(e | d) = (patients with disease d who report evidence e) / (patients with d)

With Laplace / Jeffreys smoothing to keep zeros from annihilating the posterior:

    P(e | d) = (count(e, d) + a) / (count(d) + 2a)

No gradient, no reward signal, no exploration. One pass over the data and the
estimate is optimal for the observed sample. Anything iterative here would be a
slower route to the same answer.

WHAT THIS ALSO GIVES FREE
Mutual information I(E; D) per evidence - the data's own answer to "which
question discriminates best", replacing the hand-tuned EIG ordering.

Usage:
    python3 learn_likelihoods.py --out learned_bank.json
"""
import argparse, ast, csv, json, math, pathlib, sys
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).parent
DATA = HERE / "datasets"


def load_rows(path, limit=None):
    """Stream the DDXPlus csv; EVIDENCES is a python-literal list."""
    with open(path, newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            if limit and i >= limit:
                break
            try:
                ev = ast.literal_eval(row["EVIDENCES"])
            except (ValueError, SyntaxError):
                continue
            yield row["PATHOLOGY"], ev, row.get("AGE"), row.get("SEX")


def base_code(e):
    """'E_54_@_V_112' -> 'E_54'. Categorical values collapse to presence."""
    return e.split("_@_", 1)[0]


def estimate(path, limit=None, alpha=0.5, keep_values=False):
    n_d = Counter()                       # patients per pathology
    n_ed = defaultdict(Counter)           # evidence -> pathology -> count
    evidences = set()

    total = 0
    for pathology, ev, _age, _sex in load_rows(path, limit):
        total += 1
        n_d[pathology] += 1
        seen = {e if keep_values else base_code(e) for e in ev}
        for e in seen:
            evidences.add(e)
            n_ed[e][pathology] += 1

    diseases = sorted(n_d)
    # P(e | d) with Jeffreys smoothing
    like = {e: {d: (n_ed[e][d] + alpha) / (n_d[d] + 2 * alpha)
                for d in diseases}
            for e in sorted(evidences)}
    prior = {d: n_d[d] / total for d in diseases}
    return {"n_patients": total, "prior": prior, "likelihood": like,
            "counts_disease": dict(n_d), "alpha": alpha}


# --------------------------------------------------------------- information
def entropy(p):
    return -sum(x * math.log2(x) for x in p if x > 0)


def mutual_information(like, prior):
    """I(E; D) for a binary evidence E over the disease prior."""
    out = {}
    H_D = entropy(list(prior.values()))
    for e, per_d in like.items():
        # P(e) = sum_d P(d) P(e|d)
        p_e = sum(prior[d] * per_d[d] for d in prior)
        if p_e <= 0 or p_e >= 1:
            out[e] = 0.0
            continue
        # posterior given e present / absent
        post_pos = [prior[d] * per_d[d] / p_e for d in prior]
        post_neg = [prior[d] * (1 - per_d[d]) / (1 - p_e) for d in prior]
        out[e] = H_D - (p_e * entropy(post_pos) + (1 - p_e) * entropy(post_neg))
    return out


def separability(like, prior, top=None):
    """How far apart are the columns? max-min spread of P(e|d) across d."""
    out = {}
    for e, per_d in like.items():
        vals = list(per_d.values())
        out[e] = max(vals) - min(vals)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DATA / "ddx_test.csv"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--alpha", type=float, default=0.5)
    ap.add_argument("--out", default="learned_bank.json")
    ap.add_argument("--evidences", default=str(DATA / "release_evidences.json"))
    args = ap.parse_args()

    if not pathlib.Path(args.csv).exists():
        sys.exit(f"missing {args.csv} - download it first (see DATASETS.md)")

    print(f"estimating from {args.csv}"
          + (f" (first {args.limit})" if args.limit else " (full file)"))
    est = estimate(args.csv, args.limit, args.alpha)
    print(f"  {est['n_patients']} patients, {len(est['prior'])} pathologies, "
          f"{len(est['likelihood'])} evidences")

    ev_meta = {}
    p = pathlib.Path(args.evidences)
    if p.exists():
        ev_meta = json.loads(p.read_text())

    mi = mutual_information(est["likelihood"], est["prior"])
    sep = separability(est["likelihood"], est["prior"])

    ranked = sorted(mi.items(), key=lambda x: -x[1])
    print("\nTOP 15 QUESTIONS BY MUTUAL INFORMATION (data's own ranking):")
    print(f"{'evidence':12s} {'I(E;D)':>7s} {'spread':>7s}  question")
    for e, v in ranked[:15]:
        q = ev_meta.get(e, {}).get("question_en", "")[:62]
        print(f"{e:12s} {v:7.4f} {sep[e]:7.3f}  {q}")

    print("\nBOTTOM 5 (near-useless - flat across diseases):")
    for e, v in ranked[-5:]:
        q = ev_meta.get(e, {}).get("question_en", "")[:62]
        print(f"{e:12s} {v:7.4f} {sep[e]:7.3f}  {q}")

    out = {
        "source": args.csv,
        "n_patients": est["n_patients"],
        "alpha": args.alpha,
        "prior": est["prior"],
        "likelihood": est["likelihood"],
        "mutual_information": mi,
        "separability": sep,
        "questions": {e: ev_meta.get(e, {}).get("question_en", "")
                      for e in est["likelihood"]},
    }
    (HERE / args.out).write_text(json.dumps(out, indent=1))
    print(f"\nsaved {args.out}")


if __name__ == "__main__":
    main()
