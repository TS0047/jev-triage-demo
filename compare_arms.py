#!/usr/bin/env python3
"""Head-to-head: flat 255-option list vs hierarchical clinical routing.

Same states, same API, same day. The flat arm is given the BEST possible
flat setup - the full 255-option list from the scaling probe, which is the
largest the API allows - so this is not a straw man.

Reported per state: what each arm named, its confidence, and cost.
"""
import json, pathlib, sys, time
import requests

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from scaling_probe import BASE, HARD_D, EASY_D, load_key, ENDPOINT
import hierarchical_router as HR

KEY = load_key()

TRUTH = {
    "state_a.txt": ("dengue", "undetermined tropical fever, dengue favoured"),
    "state_b.txt": ("dengue", "NS1 positive dengue with warning signs"),
    "state_c.txt": ("malaria", "vivax on smear, NS1 negative"),
    "state_d.txt": ("sle_flare", "lupus - OUTSIDE the tropical differential"),
    "state_e.txt": ("EMERGENCY", "meningococcal meningitis - must escalate"),
    "state_f.txt": ("brucellosis", "chronic zoonotic fever, TB is the rival"),
}


def build_flat(n=255):
    opts = dict(BASE)
    pool = [x for pair in zip(list(HARD_D.items()), list(EASY_D.items())) for x in pair]
    i = 0
    while len(opts) < n - 1 and i < len(pool):
        k, v = pool[i]; i += 1
        opts.setdefault(k, v)
    j = 0
    while len(opts) < n - 1:
        j += 1
        opts[f"other_condition_{j:04d}"] = f"Other specified medical condition {j}"
    opts["other"] = "None of the listed conditions, or the data does not point to any one of them"
    return opts


FLAT = build_flat(255)


def flat_arm(state):
    q = {"primary_diagnosis": {
            "type": "choice",
            "instructions": "Based only on the information in the state, which single "
                            "condition best explains this patient's illness?",
            "criteria": FLAT}}
    t0 = time.time()
    r = requests.post(ENDPOINT,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json={"model": "openjev", "state": state, "questions": q}, timeout=180)
    dt = time.time() - t0
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}"}
    d = r.json(); a = d["answers"]["primary_diagnosis"]; u = d["usage"]
    return {"choice": a["choice"], "conf": a["confidence"],
            "cost": u["input_tokens"]/1e6*0.04 + u["output_tokens"]/1e6*0.4,
            "calls": 1, "secs": round(dt, 1),
            "top3": sorted(a["probabilities"].items(), key=lambda x: -x[1])[:3]}


def hier_arm(state):
    jev = HR.Jev(KEY)
    t0 = time.time()
    tr = HR.route(state, jev, verbose=False, gate=True)
    dt = time.time() - t0
    if tr.get("escalated"):
        return {"choice": f"ESCALATED:{tr['reason']}", "conf": None,
                "cost": jev.cost, "calls": jev.calls, "secs": round(dt, 1),
                "path": None}
    return {"choice": tr["diagnosis"], "conf": tr["confidence"],
            "cost": jev.cost, "calls": jev.calls, "secs": round(dt, 1),
            "path": " > ".join(tr["path"])}


rows = []
for sf, (truth, note) in TRUTH.items():
    state = (HERE / sf).read_text()
    print(f"\n=== {sf}  ({note}) ===", flush=True)
    f = flat_arm(state)
    print(f"  flat255  {f.get('choice','ERR'):28s} conf={f.get('conf',0):.2f} "
          f"${f.get('cost',0):.5f}  {f.get('secs')}s", flush=True)
    if f.get("top3"):
        print(f"           top3: {[(k, round(v,3)) for k,v in f['top3']]}", flush=True)
    h = hier_arm(state)
    cf = f"{h['conf']:.2f}" if h["conf"] is not None else " -- "
    print(f"  hier     {h['choice']:28s} conf={cf} ${h['cost']:.5f}  "
          f"{h['calls']} calls  {h['secs']}s", flush=True)
    if h.get("path"):
        print(f"           path: {h['path']}", flush=True)
    rows.append({"state": sf, "truth": truth, "note": note, "flat": f, "hier": h})

(HERE / "compare_results.json").write_text(json.dumps(rows, indent=2, default=str))

print("\n\n=== SUMMARY ===")
print(f"{'state':14s} {'truth':14s} {'flat255':30s} {'hierarchical':30s}")
for r in rows:
    fc = r["flat"].get("choice", "ERR")
    fconf = r["flat"].get("conf", 0)
    hc = r["hier"]["choice"]
    hconf = r["hier"]["conf"]
    fs = f"{fc} ({fconf:.2f})" if fconf else fc
    hs = f"{hc} ({hconf:.2f})" if hconf else hc
    print(f"{r['state']:14s} {r['truth']:14s} {fs:30s} {hs:30s}")

tf = sum(r["flat"].get("cost", 0) for r in rows)
th = sum(r["hier"]["cost"] for r in rows)
print(f"\ntotal cost   flat ${tf:.5f}   hierarchical ${th:.5f}   ({th/tf:.1f}x)")
print("saved compare_results.json")
