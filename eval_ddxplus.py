#!/usr/bin/env python3
"""Evaluate the router against DDXPlus - real patients, real ground truth.

DDXPlus (Mila, CC-BY-4.0): 1.3M synthetic patients, 49 pathologies, 223
evidences, each with a ground-truth pathology AND a weighted differential.

Why this dataset earns its place here:
  - it gives SYMPTOMS + THE REAL ANSWER, which is exactly what we needed
  - it has a differential, not just a label, so calibration can be scored
  - CC-BY-4.0, no gating, no credentials
  - evidence codes decode to English question text, so cases render as prose

What this does NOT prove: DDXPlus patients are synthesised by a rule-based
system from a knowledge base. Scoring well here means the router agrees with
that rule engine, not that it is clinically correct.

Usage:
    python3 eval_ddxplus.py --n 30
    python3 eval_ddxplus.py --n 30 --arm flat
"""
import argparse, json, os, pathlib, random, sys, time, urllib.parse, urllib.request

HERE = pathlib.Path(__file__).parent
DATA = HERE / "datasets"
ROWS_API = "https://datasets-server.huggingface.co/rows"
DS = "aai530-group6/ddxplus"


# ----------------------------------------------------------------- rendering
def load_maps():
    ev = json.loads((DATA / "release_evidences.json").read_text())
    cond = json.loads((DATA / "release_conditions.json").read_text())
    return ev, cond


def decode_evidence(code, ev):
    """'E_54_@_V_112' -> (question_en, human readable value)."""
    if "_@_" in code:
        base, val = code.split("_@_", 1)
    else:
        base, val = code, None
    meta = ev.get(base)
    if not meta:
        return None, None
    q = meta.get("question_en", base)
    if val is None:
        return q, None
    vm = meta.get("value_meaning", {})
    if val in vm:
        return q, vm[val].get("en", val)
    return q, val.replace("V_", "").replace("_", " ")


def render_case(row, ev):
    """Turn a DDXPlus row into prose a clinician would recognise."""
    age, sex = row["AGE"], row["SEX"]
    sex_word = {"M": "man", "F": "woman"}.get(sex, "patient")
    lines = [f"Patient: {age}-year-old {sex_word}.", ""]

    evidences = row["EVIDENCES"]
    if isinstance(evidences, str):
        evidences = json.loads(evidences.replace("'", '"'))

    initial = row.get("INITIAL_EVIDENCE")
    if initial:
        q, v = decode_evidence(initial, ev)
        if q:
            lines += ["Reason for consulting:",
                      f"  {q} Yes." if v is None else f"  {q} {v}.", ""]

    pos, detail = [], []
    for code in evidences:
        q, v = decode_evidence(code, ev)
        if not q:
            continue
        if v is None:
            pos.append(q)
        else:
            detail.append((q, v))

    if pos:
        lines.append("Reported on history (answered yes):")
        lines += [f"  - {q}" for q in pos]
        lines.append("")
    if detail:
        lines.append("Details given:")
        seen = {}
        for q, v in detail:
            seen.setdefault(q, []).append(str(v))
        for q, vals in seen.items():
            lines.append(f"  - {q} {', '.join(vals)}")
        lines.append("")

    lines.append("No examination findings or laboratory tests are available.")
    return "\n".join(lines)


def fetch_rows(split="test", offset=0, length=20):
    url = (f"{ROWS_API}?dataset={urllib.parse.quote(DS)}&config=default"
           f"&split={split}&offset={offset}&length={length}")
    with urllib.request.urlopen(url, timeout=90) as r:
        return [x["row"] for x in json.loads(r.read())["rows"]]


# --------------------------------------------------------------------- arms
sys.path.insert(0, str(HERE))
import hierarchical_router as HR
from hierarchical_router import load_key, Jev

KEY = load_key()


def flat_arm(state, conditions):
    """All 49 DDXPlus pathologies in ONE flat choice - the fair flat baseline."""
    crit = {c: c for c in conditions}
    crit["none_of_these"] = "None of these conditions"
    jev = Jev(KEY)
    ans = jev.ask(state, {"dx": {
        "type": "choice",
        "instructions": "Based only on the information in the state, which single "
                        "condition best explains this patient's illness?",
        "criteria": crit}})
    a = ans["dx"]
    probs = sorted(a["probabilities"].items(), key=lambda x: -x[1])
    return {"pred": a["choice"], "conf": a["confidence"],
            "top5": [(k, round(v, 4)) for k, v in probs[:5]],
            "cost": jev.cost, "calls": jev.calls}


def hier_arm(state, conditions):
    jev = Jev(KEY)
    tr = HR.route(state, jev, verbose=False, gate=True)
    if tr.get("escalated"):
        return {"pred": f"ESCALATED:{tr['reason']}", "conf": None,
                "top5": [], "cost": jev.cost, "calls": jev.calls,
                "escalated": True}
    return {"pred": tr["diagnosis"], "label": tr["label"],
            "conf": tr["confidence"], "path": " > ".join(tr["path"]),
            "top5": [], "cost": jev.cost, "calls": jev.calls}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--arm", choices=["flat", "hier", "both"], default="flat")
    ap.add_argument("--out", default="ddxplus_eval.json")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if not KEY:
        sys.exit("no OPENJEV_API_KEY")

    ev, cond = load_maps()
    conditions = sorted(cond.keys())
    print(f"DDXPlus: {len(conditions)} pathologies, {len(ev)} evidences")

    rows = fetch_rows("test", args.offset, args.n)
    print(f"fetched {len(rows)} cases\n")

    results = []
    for i, row in enumerate(rows, 1):
        truth = row["PATHOLOGY"]
        state = render_case(row, ev)
        ddx = row["DIFFERENTIAL_DIAGNOSIS"]
        if isinstance(ddx, str):
            ddx = json.loads(ddx.replace("'", '"'))
        ddx_top = [d[0] for d in ddx[:5]] if ddx else []

        rec = {"i": i, "truth": truth, "ddx_top5": ddx_top,
               "state_chars": len(state)}

        if args.arm in ("flat", "both"):
            try:
                f = flat_arm(state, conditions)
            except Exception as e:
                f = {"error": str(e)[:120]}
            rec["flat"] = f
            ok = f.get("pred") == truth
            intop = truth in [k for k, _ in f.get("top5", [])]
            print(f"{i:3d}. truth={truth[:28]:28s} flat={str(f.get('pred'))[:26]:26s} "
                  f"{'HIT ' if ok else ('top5' if intop else 'MISS')} "
                  f"conf={f.get('conf', 0):.2f}", flush=True)

        if args.arm in ("hier", "both"):
            try:
                h = hier_arm(state, conditions)
            except Exception as e:
                h = {"error": str(e)[:120]}
            rec["hier"] = h
            print(f"     hier={str(h.get('pred'))[:40]:40s} "
                  f"{h.get('path', '')}", flush=True)

        results.append(rec)

    # ---- scoring
    out = {"dataset": DS, "n": len(results), "results": results}
    if args.arm in ("flat", "both"):
        hits = sum(1 for r in results if r.get("flat", {}).get("pred") == r["truth"])
        top5 = sum(1 for r in results
                   if r["truth"] in [k for k, _ in r.get("flat", {}).get("top5", [])])
        cost = sum(r.get("flat", {}).get("cost", 0) for r in results)
        out["flat_score"] = {"top1": hits, "top5": top5, "n": len(results),
                             "top1_pct": round(100 * hits / len(results), 1),
                             "top5_pct": round(100 * top5 / len(results), 1),
                             "cost_usd": round(cost, 5)}
        print(f"\nFLAT   top1 {hits}/{len(results)} ({100*hits/len(results):.0f}%)   "
              f"top5 {top5}/{len(results)} ({100*top5/len(results):.0f}%)   "
              f"${cost:.4f}")
    if args.arm in ("hier", "both"):
        esc = sum(1 for r in results if r.get("hier", {}).get("escalated"))
        cost = sum(r.get("hier", {}).get("cost", 0) for r in results)
        out["hier_score"] = {"escalated": esc, "n": len(results),
                             "cost_usd": round(cost, 5)}
        print(f"HIER   escalated {esc}/{len(results)}   ${cost:.4f}")

    (HERE / args.out).write_text(json.dumps(out, indent=2))
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
