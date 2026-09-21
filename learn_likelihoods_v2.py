#!/usr/bin/env python3
"""Corrected likelihood estimation: handle DDXPlus's conditional question tree.

WHY THE NAIVE ESTIMATE IS WRONG
DDXPlus evidences are not all independently askable. Sub-questions ("what
colour is the rash?") are only recorded when a parent is positive ("do you
have any lesions?"). Counting them across ALL patients makes them look
deterministic: P(E_130 | disease-with-rash) = 1.0, P = 0 elsewhere. Maximum
likelihood then ranks "what colour is the rash" as the single most informative
question in medicine, which is nonsense - it is measuring the question tree,
not the clinical world.

THE FIX
Estimate each evidence only over the patients for whom it was APPLICABLE, and
report the applicability rate separately:

    P(e | d)            over patients with disease d where e could be asked
    P(applicable | d)   how often the question is reachable at all

A question that is rarely applicable can still be decisive when it applies
(eschar), and one that is always applicable can be useless (travel history in
this dataset). Conflating the two is what produced the bogus ranking.

Detection of conditional structure is empirical, not hardcoded: an evidence
is treated as conditional on a parent when its presence is a near-subset of
the parent's presence across the whole corpus.
"""
import argparse, ast, csv, json, math, pathlib, sys
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).parent
DATA = HERE / "datasets"


def base_code(e):
    return e.split("_@_", 1)[0]


def load(path, limit=None):
    with open(path, newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            if limit and i >= limit:
                break
            try:
                ev = ast.literal_eval(row["EVIDENCES"])
            except (ValueError, SyntaxError):
                continue
            yield row["PATHOLOGY"], {base_code(x) for x in ev}


def find_parents(sets, evidences, ev_meta):
    """Read the declared question tree from the dataset schema.

    DDXPlus states the parent explicitly: release_evidences.json gives each
    evidence a `code_question`, which is the evidence it hangs off. When that
    differs from the evidence's own name, it is a conditional sub-question.

    An earlier version tried to INFER this from co-occurrence (presence(child)
    is a subset of presence(parent)). That silently produced nonsense: E_204
    (travel history) is recorded for 100% of patients, so it is trivially a
    superset of everything and became the "parent" of all 203 other evidences.
    Use the declared structure; do not infer what the data already tells you.
    """
    support = Counter()
    for s in sets:
        for e in s:
            support[e] += 1
    parent = {}
    for e in evidences:
        cq = ev_meta.get(e, {}).get("code_question")
        if cq and cq != e and cq in evidences:
            parent[e] = cq
    return parent, support


def estimate(path, limit=None, alpha=0.5, ev_meta=None):
    rows = list(load(path, limit))
    total = len(rows)
    evidences = sorted({e for _, s in rows for e in s})
    sets = [s for _, s in rows]

    parent, support = find_parents(sets, evidences, ev_meta or {})

    n_d = Counter()
    applicable = defaultdict(Counter)   # evidence -> disease -> n applicable
    present = defaultdict(Counter)      # evidence -> disease -> n present
    for path_, s in rows:
        n_d[path_] += 1
        for e in evidences:
            par = parent.get(e)
            if par is not None and par not in s:
                continue                # question was never reachable
            applicable[e][path_] += 1
            if e in s:
                present[e][path_] += 1

    diseases = sorted(n_d)
    like, applic = {}, {}
    for e in evidences:
        like[e] = {}
        applic[e] = {}
        for d in diseases:
            na = applicable[e][d]
            np_ = present[e][d]
            like[e][d] = (np_ + alpha) / (na + 2 * alpha) if na else 0.0
            applic[e][d] = na / n_d[d] if n_d[d] else 0.0
    prior = {d: n_d[d] / total for d in diseases}
    return {"n": total, "prior": prior, "likelihood": like,
            "applicability": applic, "parent": parent,
            "support": dict(support), "diseases": diseases}


def entropy(p):
    return -sum(x * math.log2(x) for x in p if x > 0)


def expected_information(est):
    """MI weighted by how often the question can actually be asked."""
    prior, like, applic = est["prior"], est["likelihood"], est["applicability"]
    H0 = entropy(list(prior.values()))
    out, raw = {}, {}
    for e in like:
        # average applicability under the prior
        app = sum(prior[d] * applic[e][d] for d in prior)
        p_e = sum(prior[d] * like[e][d] for d in prior)
        if p_e <= 0 or p_e >= 1:
            out[e] = raw[e] = 0.0
            continue
        post_pos = [prior[d] * like[e][d] / p_e for d in prior]
        post_neg = [prior[d] * (1 - like[e][d]) / (1 - p_e) for d in prior]
        mi = H0 - (p_e * entropy(post_pos) + (1 - p_e) * entropy(post_neg))
        raw[e] = mi
        out[e] = mi * app          # expected gain before you know the parent
    return out, raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DATA / "ddx_test.csv"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--alpha", type=float, default=0.5)
    ap.add_argument("--out", default="learned_bank_v2.json")
    args = ap.parse_args()

    ev_meta = json.loads((DATA / "release_evidences.json").read_text())
    print(f"estimating (conditional-aware) from {args.csv}")
    est = estimate(args.csv, args.limit, args.alpha, ev_meta)
    print(f"  {est['n']} patients, {len(est['diseases'])} pathologies, "
          f"{len(est['likelihood'])} evidences")
    print(f"  detected {len(est['parent'])} conditional sub-questions")

    eff, raw = expected_information(est)
    ranked = sorted(eff.items(), key=lambda x: -x[1])

    print("\nTOP 15 BY EXPECTED INFORMATION (applicability-weighted):")
    print(f"{'evidence':9s} {'eff':>6s} {'raw MI':>7s} {'cond?':>6s}  question")
    for e, v in ranked[:15]:
        q = ev_meta.get(e, {}).get("question_en", "")[:56]
        c = "sub" if e in est["parent"] else ""
        print(f"{e:9s} {v:6.4f} {raw[e]:7.4f} {c:>6s}  {q}")

    print("\nWHAT THE NAIVE ESTIMATE PUT ON TOP (now corrected):")
    for e in ["E_130", "E_131", "E_136", "E_54", "E_56"]:
        q = ev_meta.get(e, {}).get("question_en", "")[:56]
        par = est["parent"].get(e, "-")
        print(f"{e:9s} {eff[e]:6.4f} {raw[e]:7.4f} parent={par:7s}  {q}")

    out = {"source": args.csv, "n_patients": est["n"], "alpha": args.alpha,
           "prior": est["prior"], "likelihood": est["likelihood"],
           "applicability": est["applicability"], "parent": est["parent"],
           "expected_information": eff, "raw_mi": raw,
           "questions": {e: ev_meta.get(e, {}).get("question_en", "")
                         for e in est["likelihood"]}}
    (HERE / args.out).write_text(json.dumps(out, indent=1))
    print(f"\nsaved {args.out}")


if __name__ == "__main__":
    main()
