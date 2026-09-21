#!/usr/bin/env python3
"""Does the wide tree beat the flat list on REAL cases? And is wide > deep?

Three arms on identical real case reports:

  flat49    our original 49-condition flat list (1 call)
  wide      24 categories x up to 250 conditions, 2 calls, 2,505 total
  deep      the same 2,505 conditions reached in 3 levels instead of 2,
            to test the p^d compounding claim directly rather than asserting it

Scoring is fuzzy-but-honest: a hit requires the predicted name and the truth
to share a significant clinical token, and every judgement is printed so the
scoring can be audited rather than trusted.
"""
import argparse, json, os, pathlib, re, sys, time

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import eval_realcases as E                       # noqa: E402
import wide_router as W                          # noqa: E402
from hierarchical_router import Jev              # noqa: E402

KEY = os.environ.get("OPENJEV_API_KEY", "")
TAX = json.loads((HERE / "taxonomy.json").read_text())

STOP = {"disease", "syndrome", "acute", "chronic", "primary", "secondary",
        "infection", "of", "the", "with", "and", "left", "right", "bilateral",
        "severe", "mild", "type", "cell", "s", "a", "in", "due", "to"}


def toks(s):
    return {w for w in re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split()
            if w not in STOP and len(w) > 3}


def match(pred, truth):
    """Shared significant token = hit. Prints let a human audit every call."""
    if not pred or pred.startswith("ESCALATED"):
        return False
    a, b = toks(pred), toks(truth)
    return bool(a & b)


def flat49(state):
    conds, _ = E.scope_index()
    crit = {c: c for c in conds}
    crit["outside_differential"] = "None of the listed conditions fits."
    jev = Jev(KEY)
    a = jev.ask(state, {"dx": {"type": "choice",
        "instructions": "Which single option best explains this illness?",
        "criteria": crit}})["dx"]
    return a["choice"], a["confidence"], jev.cost, jev.calls


def wide(state):
    jev = Jev(KEY)
    r = W.route(state, jev, min_cat=0.30, min_leaf=0.25)
    if r.get("escalated"):
        return f"ESCALATED:{r['reason']}", 0.0, jev.cost, jev.calls
    return r["diagnosis"], r["confidence"], jev.cost, jev.calls


def deep(state):
    """Same 2,505 conditions, but 3 levels: supergroup -> category -> leaf.
    Tests whether extra depth costs accuracy, as p^d predicts."""
    SUPER = {
        "infectious": ["infection_bacterial", "infection_viral",
                       "infection_fungal", "infection_parasitic"],
        "neoplastic": ["neoplasm_carcinoma", "neoplasm_sarcoma",
                       "neoplasm_lymphoid", "neoplasm_benign",
                       "neoplasm_neuroendocrine"],
        "organ_system": ["cardiac", "vascular", "respiratory", "neurological",
                         "gastrointestinal", "renal_urinary", "musculoskeletal",
                         "dermatological", "ophthalmic_ent",
                         "obstetric_gynaecological"],
        "systemic_other": ["autoimmune_rheumatic", "endocrine_metabolic",
                           "haematological", "psychiatric", "iatrogenic_toxic"],
    }
    jev = Jev(KEY)
    crit = {k: f"{k.replace('_',' ')} disease" for k in SUPER}
    crit["none_of_these"] = "None of these fits."
    a = jev.ask(state, {"g": {"type": "choice",
        "instructions": "Which broad class of disease best explains this?",
        "criteria": crit}})["g"]
    if a["choice"] == "none_of_these":
        return "ESCALATED:no_supergroup", 0.0, jev.cost, jev.calls
    cats = SUPER[a["choice"]]
    crit2 = {c: TAX["categories"][c] for c in cats}
    crit2["none_of_these"] = "None of these fits."
    b = jev.ask(state, {"c": {"type": "choice",
        "instructions": "Which category best explains this?",
        "criteria": crit2}})["c"]
    if b["choice"] == "none_of_these":
        return "ESCALATED:no_category", 0.0, jev.cost, jev.calls
    leaves = TAX["tree"][b["choice"]]
    crit3 = {c: c for c in leaves}
    crit3["none_of_these"] = "None of these fits."
    c = jev.ask(state, {"d": {"type": "choice",
        "instructions": "Which single condition best explains this?",
        "criteria": crit3}})["d"]
    if c["choice"] == "none_of_these":
        return "ESCALATED:no_condition", 0.0, jev.cost, jev.calls
    return c["choice"], c["confidence"], jev.cost, jev.calls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--arms", default="flat,wide")
    ap.add_argument("--out", default="wide_eval.json")
    args = ap.parse_args()
    if not KEY:
        sys.exit("no OPENJEV_API_KEY")

    arms = args.arms.split(",")
    fns = {"flat": flat49, "wide": wide, "deep": deep}
    cases = E.load_cases(args.n, args.offset, 5)
    print(f"{len(cases)} real cases | arms: {arms}")
    print(f"taxonomy: {sum(len(v) for v in TAX['tree'].values()):,} conditions\n")

    res, cost = [], 0.0
    score = {a: 0 for a in arms}
    calls = {a: 0 for a in arms}
    for i, (p, truth, pmcid) in enumerate(cases, 1):
        state = E.to_state(p)
        rec = {"truth": truth, "pmcid": pmcid}
        line = f"{i:3d}. {truth[:30]:30s}"
        for a in arms:
            try:
                pred, conf, c, nc = fns[a](state)
            except Exception as e:
                pred, conf, c, nc = f"ERR:{str(e)[:30]}", 0.0, 0.0, 0
            ok = match(pred, truth)
            score[a] += ok
            calls[a] += nc
            cost += c
            rec[a] = {"pred": pred, "conf": conf, "hit": ok}
            line += f" | {a}:{'HIT' if ok else '-  '} {str(pred)[:22]:22s}"
        print(line)
        res.append(rec)
        time.sleep(0.15)

    n = len(cases)
    print(f"\n{'='*70}")
    for a in arms:
        print(f"  {a:6s}  {score[a]:3d}/{n}  ({100*score[a]/n:5.1f}%)  "
              f"{calls[a]/n:.1f} calls/case")
    print(f"\ncost ${cost:.4f}")
    json.dump({"n": n, "score": score, "results": res},
              open(HERE / args.out, "w"), indent=1)
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
