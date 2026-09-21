#!/usr/bin/env python3
"""The harder scaling test: an UNDERDETERMINED state.

state_b was decisive (NS1 positive) so the option set could not hurt it.
state_a is the honest stress test - day-5 fever, no vitals, nothing tested.
The posterior there is genuinely spread (dengue 0.68 at N=7), so if a large
option set damages calibration, THIS is where it shows.

Measures, at each size, against the N=7 reference:
  - does the top choice change?
  - how much probability mass leaks to distractors?
  - does the top-6 ordering (the actual differential) survive?
"""
import json, math, os, pathlib, time
import requests
from scaling_probe import BASE, build, load_key, entropy, ENDPOINT  # reuse

HERE = pathlib.Path(__file__).parent
KEY = load_key()
state = (HERE / "state_a.txt").read_text()

def probe(n, regime):
    opts = build(n, regime)
    q = {"primary_diagnosis": {
            "type": "choice",
            "instructions": "Based only on the information in the state, which single condition best explains this patient's illness?",
            "criteria": opts}}
    t0 = time.time()
    r = requests.post(ENDPOINT,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json={"model": "openjev", "state": state, "questions": q}, timeout=180)
    dt = time.time() - t0
    if r.status_code != 200:
        return {"n": len(opts), "error": f"HTTP {r.status_code}: {r.text[:160]}"}
    a = r.json()["answers"]["primary_diagnosis"]
    p = a["probabilities"]
    base_mass = sum(p.get(k, 0.0) for k in BASE)
    ranked = sorted(p.items(), key=lambda x: -x[1])
    base_ranked = [k for k, _ in ranked if k in BASE]
    return {"n": len(opts), "regime": regime, "choice": a["choice"],
            "conf": a["confidence"],
            "base_mass": base_mass,
            "leak": 1.0 - base_mass - p.get("other", 0.0),
            "p_other": p.get("other", 0.0),
            "entropy": entropy(p),
            "base_order": base_ranked,
            "top5": [(k, round(v, 4)) for k, v in ranked[:5]],
            "in_tok": r.json()["usage"]["input_tokens"], "secs": round(dt, 1)}

PLAN = [(7,"hard"),(25,"hard"),(50,"hard"),(100,"hard"),(200,"mixed"),(255,"mixed")]
out = []
ref_order = None
for n, regime in PLAN:
    res = probe(n, regime)
    out.append(res)
    if "error" in res:
        print(f"n={res['n']:4d}  ERROR {res['error']}", flush=True); continue
    if ref_order is None:
        ref_order = res["base_order"]
    same = "same" if res["base_order"] == ref_order else "CHANGED"
    print(f"n={res['n']:4d} {regime:6s} choice={res['choice']:16s} conf={res['conf']:.3f} "
          f"base_mass={res['base_mass']:.3f} leak={res['leak']:.3f} other={res['p_other']:.3f} "
          f"H={res['entropy']:.2f} order={same} tok={res['in_tok']} {res['secs']}s", flush=True)
    print(f"        top5: {res['top5']}", flush=True)

(HERE / "scaling_ambiguous.json").write_text(json.dumps(out, indent=2))
print("\nsaved scaling_ambiguous.json")
