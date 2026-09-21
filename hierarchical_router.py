#!/usr/bin/env python3
"""Hierarchical differential routing that mimics documented clinical reasoning.

The flat list is capped at 255 options and loses confidence as it grows
(see SCALING.md). Doctors never use a flat list either. This implements the
sequence they actually use, in their order:

  L0  ROWS / "worst first"   - danger before probability, anti-Bayesian by design
  L1  problem representation - semantic qualifiers (Bordage): acute/chronic,
                               localised/diffuse, febrile/afebrile...
  L2  syndrome routing       - the abstraction selects a SYNDROME, not a disease
  L3  surgical sieve         - mechanism within syndrome (VINDICATE):
                               infective / autoimmune / neoplastic / vascular...
  L4  illness scripts        - named conditions in that syndrome x mechanism cell
  L5  epidemiological gate   - incubation & exposure as HARD exclusions, not
                               soft reweighting

Syndrome and sieve are ORTHOGONAL AXES, not a tree. You land in a cell, and a
cell holds ~15-30 conditions - inside the 255 cap and inside the range where
no degradation was measured.

Every level carries its own escape hatch. An escape at any level escalates
rather than forcing a leaf.
"""
import argparse, json, math, os, pathlib, sys, time
import requests

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from grids import GRIDS, SYNDROMES as GRID_SYNDROMES, SIEVE as GRID_SIEVE

ENDPOINT = "https://api.openjev.sh/v1/systemone"


# ---------------------------------------------------------------- key / http
def load_key(name="OPENJEV_API_KEY"):
    key = os.environ.get(name, "").strip()
    if key:
        return key
    envfile = HERE / ".env"
    if envfile.exists():
        for line in envfile.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == name:
                return v.strip().strip("'\"")
    return ""


class Jev:
    """Thin client that tracks cost and call count."""

    def __init__(self, key):
        self.key = key
        self.calls = 0
        self.in_tok = 0
        self.out_tok = 0

    def ask(self, state, questions):
        r = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {self.key}",
                     "Content-Type": "application/json"},
            json={"model": "openjev", "state": state, "questions": questions},
            timeout=120,
        )
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        d = r.json()
        self.calls += 1
        u = d.get("usage", {})
        self.in_tok += u.get("input_tokens", 0)
        self.out_tok += u.get("output_tokens", 0)
        return d["answers"]

    @property
    def cost(self):
        # published OpenJEV pricing, same basis used elsewhere in this repo
        return self.in_tok / 1e6 * 0.04 + self.out_tok / 1e6 * 0.4


ESCAPE = "none_of_these"
ESCAPE_TEXT = ("None of these, or the information does not point to any one "
               "of them")


# ------------------------------------------------------- L0  ROWS / red flags
# "Worst first": these are checked before any probabilistic reasoning, because
# missing one is catastrophic even when it is unlikely.
RED_FLAGS = {
    "meningism": "Neck stiffness, photophobia, or a non-blanching rash",
    "altered_consciousness": "Confusion, drowsiness, disorientation or seizure",
    "shock": "Cold clammy peripheries, very low blood pressure, or fainting on standing",
    "respiratory_distress": "Breathlessness at rest, or unable to speak full sentences",
    "active_bleeding": "Bleeding from gums, nose, gut, or blood in vomit or stool",
    "severe_dehydration": "Not passing urine, sunken eyes, unable to keep fluids down",
    "jaundice_rapid": "Rapidly deepening yellowing of eyes or skin",
    "severe_abdominal_pain": "Severe, localised or rigid abdominal pain",
}


# ------------------------------------------- L1  semantic qualifiers (Bordage)
# Abstract binary axes. These do not name a disease; they build the problem
# representation that selects a syndrome.
QUALIFIERS = {
    "tempo": {
        "type": "choice",
        "instructions": "What is the time course of this illness?",
        "criteria": {
            "hyperacute": "Onset over minutes to hours",
            "acute": "Onset over days, present less than about 2 weeks",
            "subacute": "Present roughly 2 weeks to 3 months",
            "chronic": "Present longer than about 3 months",
        },
    },
    "febrile": {
        "type": "noul",
        "instructions": "Is fever a prominent part of this illness?",
        "criteria": {"true": "Fever is present and prominent",
                     "false": "There is no fever, or fever is incidental"},
    },
    "localisation": {
        "type": "choice",
        "instructions": "Do the findings point to one body system, or are they generalised?",
        "criteria": {
            "localised": "Findings point clearly to one organ or system",
            "diffuse": "Findings are systemic or generalised with no single focus",
            "multisystem": "Two or more unrelated systems are clearly involved",
        },
    },
    "host": {
        "type": "choice",
        "instructions": "What is the host status of this patient?",
        "criteria": {
            "immunocompetent": "No stated immune compromise",
            "immunosuppressed": "Immune compromise, chemotherapy, HIV, transplant or steroids",
            "pregnant": "Pregnancy is stated",
            "extremes_of_age": "Infant or frail elderly",
        },
    },
}


# ---------------- L2/L3/L4 content now lives in grids.py (validated) --------
# SYNDROMES, SIEVE and the (syndrome, mechanism) -> conditions grid are
# imported. Select with --grid; validate with validate_grids.py.
SYNDROMES = GRID_SYNDROMES
SIEVE = GRID_SIEVE
SCRIPTS = GRIDS["tropical"]          # default; overridden by set_grid()


def set_grid(name):
    """Swap the active condition grid (see grids.GRIDS)."""
    global SCRIPTS
    if name not in GRIDS:
        raise SystemExit(f"unknown grid {name!r}; have {sorted(GRIDS)}")
    SCRIPTS = GRIDS[name]
    return SCRIPTS


# ------------------------------------------------------------------ utilities
def entropy(dist):
    return -sum(p * math.log2(p) for p in dist.values() if p > 0)


def temper(dist, floor=0.02):
    """Same correction as the flat loop: Jev saturates to 1.00/0.00."""
    n = len(dist)
    if n == 0:
        return dist
    return {k: (1 - floor) * v + floor / n for k, v in dist.items()}


def choice_q(instructions, options):
    crit = dict(options)
    crit[ESCAPE] = ESCAPE_TEXT
    return {"type": "choice", "instructions": instructions, "criteria": crit}


def fmt(dist, n=4):
    top = sorted(dist.items(), key=lambda x: -x[1])[:n]
    return "  ".join(f"{k}={v:.2f}" for k, v in top)


# --------------------------------------------------------------- the pipeline
def route(state, jev, verbose=True, gate=True, grid=None):
    """grid=None uses the module default (set via set_grid or --grid)."""
    g = GRIDS[grid] if grid else SCRIPTS
    trace = {"levels": [], "escalated": False, "reason": None, "grid": grid or "default"}

    def say(*a):
        if verbose:
            print(*a, flush=True)

    # ---- L0  ROWS: danger before probability ----------------------------
    q = {f"rf_{k}": {"type": "noul",
                     "instructions": f"Is this present: {v}?",
                     "criteria": {"true": v, "false": f"No {v.lower()}"}}
         for k, v in RED_FLAGS.items()}
    ans = jev.ask(state, q)
    flags = {k[3:]: a["noul"] for k, a in ans.items() if a["noul"] >= 0.60}
    say(f"L0  ROWS            {len(flags)} red flag(s)"
        + (f"  -> {', '.join(flags)}" if flags else ""))
    trace["levels"].append({"level": "L0_rows", "flags": flags})
    if flags:
        trace["escalated"] = True
        trace["reason"] = "red_flags"
        trace["red_flags"] = flags
        say("    EMERGENCY - stopping before any differential reasoning")
        return trace

    # ---- L1  problem representation --------------------------------------
    ans = jev.ask(state, QUALIFIERS)
    rep = {}
    for k, a in ans.items():
        rep[k] = a["noul"] >= 0.5 if a["type"] == "noul" else a["choice"]
    say(f"L1  representation   {rep}")
    trace["levels"].append({"level": "L1_qualifiers", "representation": rep})

    # ---- L2  syndrome ------------------------------------------------------
    ans = jev.ask(state, {"syndrome": choice_q(
        "Which clinical syndrome best describes this presentation as a whole? "
        "Choose the syndrome, not a specific disease.", SYNDROMES)})
    a = ans["syndrome"]
    syn, syn_p = a["choice"], temper(a["probabilities"])
    say(f"L2  syndrome         {syn}  (conf {a['confidence']:.2f})   {fmt(syn_p)}")
    trace["levels"].append({"level": "L2_syndrome", "choice": syn,
                            "confidence": a["confidence"],
                            "entropy": entropy(syn_p),
                            "top": sorted(syn_p.items(), key=lambda x: -x[1])[:4]})
    if syn == ESCAPE:
        trace["escalated"] = True
        trace["reason"] = "no_syndrome_fits"
        say("    no syndrome fits -> escalate")
        return trace

    # ---- L3  surgical sieve ------------------------------------------------
    available = sorted({m for (s, m) in g if s == syn})
    if not available:
        trace["escalated"] = True
        trace["reason"] = f"no_sieve_content_for_{syn}"
        say(f"    no mechanism content authored for {syn} -> escalate")
        return trace
    sieve_opts = {m: SIEVE[m] for m in available}
    ans = jev.ask(state, {"mechanism": choice_q(
        f"Within {SYNDROMES[syn].lower()}, what KIND of process is this? "
        "Choose the mechanism, not a specific disease.", sieve_opts)})
    a = ans["mechanism"]
    mech, mech_p = a["choice"], temper(a["probabilities"])
    say(f"L3  sieve            {mech}  (conf {a['confidence']:.2f})   {fmt(mech_p)}")
    trace["levels"].append({"level": "L3_sieve", "choice": mech,
                            "confidence": a["confidence"],
                            "entropy": entropy(mech_p),
                            "offered": available,
                            "top": sorted(mech_p.items(), key=lambda x: -x[1])[:4]})
    if mech == ESCAPE:
        trace["escalated"] = True
        trace["reason"] = "no_mechanism_fits"
        say("    no mechanism fits -> escalate")
        return trace

    # ---- L5 gate (applied before L4 so the leaf set is pre-filtered) -------
    cell = g.get((syn, mech), {})
    if not cell:
        trace["escalated"] = True
        trace["reason"] = f"empty_cell_{syn}_{mech}"
        say(f"    cell ({syn}, {mech}) is empty -> escalate")
        return trace

    excluded = {}
    leaf = dict(cell)
    if gate:
        ans = jev.ask(state, {"days_ill": {
            "type": "score",
            "instructions": "How many days has this illness been going on, "
                            "counting from the first symptom?",
            "criteria": ["Less than 2 days", "About 2 to 5 days",
                         "About 6 to 14 days", "About 15 to 40 days",
                         "More than 40 days"]}})
        band = ans["days_ill"]["score"]
        day_est = [1, 3.5, 10, 27, 60][min(4, max(0, int(round(band))))]
        for k, v in list(leaf.items()):
            inc = v.get("incubation")
            # exclude only when the illness is clearly too OLD for the script;
            # never exclude on the short side, since exposure timing is unknown
            if inc and day_est > inc[1] * 3:
                excluded[k] = f"day~{day_est:.0f} vs incubation {inc[0]}-{inc[1]}d"
                leaf.pop(k)
        say(f"L5  epi gate         day~{day_est:.0f}  excluded {len(excluded)}"
            + (f" -> {', '.join(excluded)}" if excluded else ""))
        trace["levels"].append({"level": "L5_gate", "day_estimate": day_est,
                                "excluded": excluded})

    if not leaf:
        trace["escalated"] = True
        trace["reason"] = "all_candidates_excluded_by_gate"
        say("    every candidate excluded by the epidemiological gate -> escalate")
        return trace

    # ---- L4  named conditions in the cell ----------------------------------
    labels = {k: v["label"] for k, v in leaf.items()}
    ans = jev.ask(state, {"condition": choice_q(
        f"Within {SYNDROMES[syn].lower()} of {SIEVE[mech].lower()}, "
        "which single condition best explains this illness?", labels)})
    a = ans["condition"]
    dx, dx_p = a["choice"], temper(a["probabilities"])
    say(f"L4  condition        {dx}  (conf {a['confidence']:.2f})   {fmt(dx_p)}")
    trace["levels"].append({"level": "L4_condition", "choice": dx,
                            "confidence": a["confidence"],
                            "entropy": entropy(dx_p),
                            "n_options": len(labels) + 1,
                            "top": sorted(dx_p.items(), key=lambda x: -x[1])[:4]})
    if dx == ESCAPE:
        trace["escalated"] = True
        trace["reason"] = "no_condition_in_cell_fits"
        say("    no condition in this cell fits -> escalate")
        return trace

    trace["diagnosis"] = dx
    trace["label"] = leaf[dx]["label"]
    trace["path"] = [syn, mech, dx]
    trace["confidence"] = a["confidence"]
    return trace


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state", nargs="?", default="state_a.txt")
    ap.add_argument("--json", dest="jsonout")
    ap.add_argument("--no-gate", action="store_true")
    ap.add_argument("--grid", choices=sorted(GRIDS), default="tropical")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    key = load_key()
    if not key or key == "paste_your_key_here":
        sys.exit("No API key. Set OPENJEV_API_KEY or fill .env")

    set_grid(args.grid)
    state = (HERE / args.state).read_text()
    jev = Jev(key)
    t0 = time.time()
    print(f"=== {args.state}   grid={args.grid} ===")
    tr = route(state, jev, verbose=not args.quiet, gate=not args.no_gate)
    dt = time.time() - t0

    print()
    if tr.get("escalated"):
        print(f"RESULT   ESCALATED ({tr['reason']})")
    else:
        print(f"RESULT   {tr['label']}  via  {' > '.join(tr['path'])}")
        print(f"         confidence {tr['confidence']:.2f}")
    print(f"         {jev.calls} calls, {jev.in_tok} in / {jev.out_tok} out tokens, "
          f"${jev.cost:.5f}, {dt:.1f}s")

    tr["usage"] = {"calls": jev.calls, "input_tokens": jev.in_tok,
                   "output_tokens": jev.out_tok, "cost_usd": round(jev.cost, 6),
                   "seconds": round(dt, 1)}
    tr["state_file"] = args.state
    if args.jsonout:
        pathlib.Path(args.jsonout).write_text(json.dumps(tr, indent=2))
        print(f"         wrote {args.jsonout}")


if __name__ == "__main__":
    main()
