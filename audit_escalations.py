#!/usr/bin/env python3
"""Diagnose every escalation: was the answer really absent, or did we lose it?

An escalation is only honest if the condition genuinely was not reachable.
If the condition WAS in the tree and we escalated anyway, that is a routing
failure wearing a safety costume - and it has two very different causes:

  L1 MISROUTE  level 1 picked the wrong category, so the true condition was
               never in the level-2 list. Unrecoverable by design.
  L2 BLINDNESS level 1 picked the RIGHT category and the condition was
               sitting in the list, and level 2 still said none_of_these.
               That is the model failing to see an available answer.

The second is much worse, and the fix is different: L1 misroutes argue for
multi-category descent, L2 blindness argues for the threshold or the prompt.
"""
import argparse, json, os, pathlib, re, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import eval_realcases as E                      # noqa: E402
import wide_router as W                         # noqa: E402
from hierarchical_router import Jev             # noqa: E402

KEY = os.environ.get("OPENJEV_API_KEY", "")
TAX = json.loads((HERE / "taxonomy.json").read_text())


def norm(s):
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(s))
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def locate(truth, tree):
    """Strict: same disease only - exact, or one name contains the other."""
    t = norm(truth)
    out = []
    for cat, leaves in tree.items():
        for leaf in leaves:
            l = norm(leaf)
            if l == t or (len(t.split()) >= 2 and t in l) or \
               (len(l.split()) >= 2 and l in t):
                out.append((cat, leaf))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=22)
    ap.add_argument("--out", default="escalation_audit.json")
    args = ap.parse_args()
    if not KEY:
        sys.exit("no OPENJEV_API_KEY")

    tree = TAX["tree"]
    prev = json.loads((HERE / "wide_eval.json").read_text())["results"]
    esc = [r for r in prev
           if not r["wide"]["hit"] and str(r["wide"]["pred"]).startswith("ESCALATED")]

    cases = {t: p for p, t, _ in E.load_cases(args.n, 0, 5)}
    print(f"auditing {len(esc)} escalations\n")

    rows, cost = [], 0.0
    tally = {"absent": 0, "l1_misroute": 0, "l2_blind": 0, "l1_lowconf": 0}
    for r in esc:
        truth = r["truth"]
        where = locate(truth, tree)
        if not where:
            tally["absent"] += 1
            print(f"OK   {truth[:40]:40s} genuinely absent from the tree")
            rows.append({"truth": truth, "verdict": "absent"})
            continue

        true_cat = where[0][0]
        true_leaf = where[0][1]
        jev = Jev(KEY)
        res = W.route(cases[truth], jev, min_cat=0.30, min_leaf=0.25)
        cost += jev.cost
        picked = res.get("cat")
        reason = res.get("reason", "")

        if picked is None:
            verdict = "l1_lowconf"
            detail = f"L1 refused ({reason})"
        elif picked != true_cat:
            verdict = "l1_misroute"
            detail = f"L1 chose {picked}, answer lives in {true_cat}"
        else:
            verdict = "l2_blind"
            detail = (f"L1 chose {picked} CORRECTLY; '{true_leaf}' was in the "
                      f"{len(tree[picked])}-option list and L2 still refused")
        tally[verdict] += 1
        flag = {"l1_lowconf": "WARN", "l1_misroute": "BAD ", "l2_blind": "WORST"}[verdict]
        print(f"{flag} {truth[:40]:40s} {detail}")
        rows.append({"truth": truth, "verdict": verdict, "picked": picked,
                     "true_cat": true_cat, "true_leaf": true_leaf,
                     "reason": reason})

    n = len(esc)
    print(f"\n{'='*70}")
    print(f"  honest escalations (answer absent)      {tally['absent']:2d}/{n}")
    print(f"  L1 refused to commit to a category      {tally['l1_lowconf']:2d}/{n}")
    print(f"  L1 misrouted (answer unreachable)       {tally['l1_misroute']:2d}/{n}")
    print(f"  L2 blind (answer present, still refused){tally['l2_blind']:3d}/{n}")
    print(f"\ncost ${cost:.4f}")
    json.dump({"tally": tally, "rows": rows}, open(HERE / args.out, "w"), indent=1)
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
