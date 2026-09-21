#!/usr/bin/env python3
"""Evaluate against REAL published cases (MedCaseReasoning), not a generator.

WHY THIS IS THE HARD TEST
DDXPlus is synthetic with a 99.44% lookup ceiling (DATASET_SCALE.md). These
are 13,092 real PMC case reports covering 8,130 distinct diagnoses. Our system
knows 49. So for most cases the CORRECT answer is "I cannot diagnose this -
escalate", and the headline metric is not accuracy. It is:

    does the system know what it does not know?

A triage tool that confabulates a familiar-sounding diagnosis for a rare
disease is dangerous. One that escalates is merely limited. This measures the
ratio directly.

PARTITION
  in-scope      truth maps to one of our 49 -> we should NAME it
  out-of-scope  truth does not              -> we should ESCALATE

Scope matching is deliberately conservative and reported explicitly, because a
sloppy matcher would manufacture whichever result I wanted.
"""
import argparse, json, os, pathlib, random, re, sys, time

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import hierarchical_router as HR                # noqa: E402
from hierarchical_router import Jev             # noqa: E402
from grids import GRIDS                         # noqa: E402

DATA = HERE / "datasets"
KEY = os.environ.get("OPENJEV_API_KEY", "")


# ----------------------------------------------------------------- scope map
def norm(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s)


# our 49 DDXPlus pathologies -> the words that identify them in free text
# Abbreviated / alternate names for our conditions as they appear in real
# case reports. Without these the matcher scores a CORRECT answer as wrong:
# truth "systemic lupus erythematosus" vs our label "SLE".
ALIASES = {
    "SLE": ["systemic lupus erythematosus", "lupus erythematosus", "lupus"],
    "GERD": ["gastroesophageal reflux disease", "gastro esophageal reflux",
             "gastroesophageal reflux"],
    "URTI": ["upper respiratory tract infection", "common cold"],
    "HIV (initial infection)": ["acute hiv infection", "primary hiv infection"],
    "PSVT": ["paroxysmal supraventricular tachycardia",
             "supraventricular tachycardia"],
    "Boerhaave": ["boerhaave syndrome", "spontaneous esophageal rupture"],
    "Chagas": ["chagas disease", "american trypanosomiasis"],
    "Guillain-Barré syndrome": ["guillain barre syndrome", "guillain barre"],
    "Myasthenia gravis": ["myasthenic crisis"],
    "Pulmonary embolism": ["pulmonary thromboembolism"],
    "Pancreatic neoplasm": ["pancreatic cancer", "pancreatic carcinoma"],
    "Pulmonary neoplasm": ["lung cancer", "lung carcinoma"],
    "Tuberculosis": ["tb", "mycobacterium tuberculosis infection"],
}


def scope_index():
    conds = sorted({c for cell in GRIDS["ddxplus"].values() for c in cell})
    idx = {}
    for c in conds:
        idx[norm(c)] = c
        for a in ALIASES.get(c, []):
            idx[norm(a)] = c
    return conds, idx


def in_scope(truth, idx):
    """Conservative: exact normalised match, or our label is a whole-phrase
    substring of the truth (>=2 words so 'anemia' does not swallow everything).
    Returns the matched condition or None."""
    t = norm(truth)
    if t in idx:
        return idx[t]
    for key, c in idx.items():
        if len(key.split()) >= 2 and key in t:
            return c
    # single-word labels need an exact token match, not a substring
    toks = set(t.split())
    for key, c in idx.items():
        if len(key.split()) == 1 and key in toks and len(key) > 4:
            return c
    return None


# ----------------------------------------------------------------- data load
def load_cases(n, offset, seed):
    import pyarrow.parquet as pq
    path = DATA / "mcr_train.parquet"
    if not path.exists():
        sys.exit("missing datasets/mcr_train.parquet - see DATASET_SCALE.md")
    t = pq.read_table(path, columns=["case_prompt", "final_diagnosis", "pmcid"])
    rows = list(zip(t.column("case_prompt").to_pylist(),
                    t.column("final_diagnosis").to_pylist(),
                    t.column("pmcid").to_pylist()))
    rows = [r for r in rows if r[0] and r[1] and len(r[0]) > 200]
    random.Random(seed).shuffle(rows)
    return rows[offset:offset + n]


def to_state(prompt):
    return f"PATIENT PRESENTATION (from a published clinical case report)\n\n{prompt.strip()}\n"


# ------------------------------------------------------------------ the arms
def flat_arm(state, conditions):
    """Closed list + an explicit escape hatch that NAMES the in-scope set."""
    crit = {c: c for c in conditions}
    crit["outside_differential"] = (
        "None of the listed conditions explains this presentation. The illness "
        "is outside this differential and needs a clinician's assessment.")
    jev = Jev(KEY)
    ans = jev.ask(state, {"dx": {
        "type": "choice",
        "instructions": ("Based only on the information in the state, which single "
                         "option best explains this patient's illness? Choose "
                         "outside_differential if none of the named conditions fits."),
        "criteria": crit}})
    a = ans["dx"]
    probs = sorted(a["probabilities"].items(), key=lambda x: -x[1])
    return {"pred": a["choice"], "conf": a["confidence"],
            "top3": [(k, round(v, 3)) for k, v in probs[:3]],
            "cost": jev.cost}


def hier_arm(state):
    jev = Jev(KEY)
    tr = HR.route(state, jev, verbose=False, gate=True, grid="ddxplus")
    if tr.get("escalated"):
        return {"pred": "ESCALATED", "reason": tr["reason"], "conf": None,
                "escalated": True, "cost": jev.cost}
    return {"pred": tr["diagnosis"], "conf": tr["confidence"],
            "path": " > ".join(tr.get("path", [])), "escalated": False,
            "cost": jev.cost}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--arm", choices=["flat", "hier", "both"], default="both")
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--out", default="mcr_eval.json")
    args = ap.parse_args()
    if not KEY:
        sys.exit("no OPENJEV_API_KEY")

    conditions, idx = scope_index()
    cases = load_cases(args.n, args.offset, args.seed)
    print(f"{len(conditions)} known conditions, {len(cases)} real cases\n")

    results = []
    for i, (prompt, truth, pmcid) in enumerate(cases, 1):
        matched = in_scope(truth, idx)
        state = to_state(prompt)
        # exact == the truth IS our condition; loose == ours is a broader
        # category containing it ("acute eosinophilic pneumonia" -> Pneumonia).
        # A loose match is NOT a clinical win: eosinophilic pneumonia is
        # treated with steroids, bacterial pneumonia with antibiotics. Scored
        # separately so the headline number is not quietly inflated.
        strictness = None
        if matched:
            strictness = "exact" if norm(truth) == norm(matched) else "loose"
        rec = {"i": i, "pmcid": pmcid, "truth": truth,
               "scope": "in" if matched else "out", "matched": matched,
               "match_type": strictness}
        try:
            if args.arm in ("flat", "both"):
                rec["flat"] = flat_arm(state, conditions)
            if args.arm in ("hier", "both"):
                rec["hier"] = hier_arm(state)
        except Exception as e:
            rec["error"] = str(e)[:200]
        results.append(rec)

        f = rec.get("flat", {})
        tag = "IN " if matched else "OUT"
        print(f"{i:3d}. [{tag}] {truth[:38]:38s} -> {str(f.get('pred'))[:30]:30s} "
              f"{f.get('conf') or 0:.2f}")
        time.sleep(0.2)

    # ------------------------------------------------------------- scoring
    ins = [r for r in results if r["scope"] == "in" and "error" not in r]
    outs = [r for r in results if r["scope"] == "out" and "error" not in r]
    print(f"\n{'='*64}\nin-scope {len(ins)}   out-of-scope {len(outs)}")

    if args.arm in ("flat", "both"):
        esc = sum(1 for r in outs if r["flat"]["pred"] == "outside_differential")
        conf_wrong = [r for r in outs
                      if r["flat"]["pred"] != "outside_differential"]
        print(f"\nFLAT")
        print(f"  out-of-scope correctly escalated : {esc}/{len(outs)} "
              f"({100*esc/max(len(outs),1):.0f}%)")
        print(f"  out-of-scope CONFABULATED        : {len(conf_wrong)}/{len(outs)}")
        if ins:
            hit = sum(1 for r in ins if r["flat"]["pred"] == r["matched"])
            ex = [r for r in ins if r["match_type"] == "exact"]
            ex_hit = sum(1 for r in ex if r["flat"]["pred"] == r["matched"])
            print(f"  in-scope named correctly         : {hit}/{len(ins)}")
            print(f"    of which exact-match cases     : {ex_hit}/{len(ex)}")
        if conf_wrong:
            avg = sum(r["flat"]["conf"] or 0 for r in conf_wrong) / len(conf_wrong)
            print(f"  mean confidence when confabulating: {avg:.2f}  "
                  f"(<- the dangerous number)")

    if args.arm in ("hier", "both"):
        esc = sum(1 for r in outs if r["hier"].get("escalated"))
        print(f"\nHIERARCHICAL")
        print(f"  out-of-scope correctly escalated : {esc}/{len(outs)} "
              f"({100*esc/max(len(outs),1):.0f}%)")
        if ins:
            hit = sum(1 for r in ins if r["hier"].get("pred") == r["matched"])
            e_in = sum(1 for r in ins if r["hier"].get("escalated"))
            print(f"  in-scope named correctly         : {hit}/{len(ins)}")
            print(f"  in-scope escalated instead       : {e_in}/{len(ins)}")

    cost = sum((r.get("flat", {}).get("cost", 0) or 0)
               + (r.get("hier", {}).get("cost", 0) or 0) for r in results)
    print(f"\ncost ${cost:.4f}")

    json.dump({"n": len(results), "conditions": len(conditions),
               "results": results}, open(HERE / args.out, "w"), indent=1)
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
