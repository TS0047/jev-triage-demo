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


# ------------------------------------------------------- L2  syndrome routing
SYNDROMES = {
    "acute_febrile_undifferentiated":
        "Acute fever with no clear localising focus",
    "acute_respiratory":
        "Cough, breathlessness, sore throat or chest symptoms predominate",
    "acute_abdominal":
        "Abdominal pain, vomiting or bowel disturbance predominate",
    "acute_neurological":
        "Headache, confusion, weakness, fits or altered consciousness predominate",
    "acute_diarrhoeal":
        "Diarrhoea is the dominant problem",
    "jaundice_hepatic":
        "Jaundice or liver dysfunction predominates",
    "urogenital":
        "Urinary or genital symptoms predominate",
    "skin_soft_tissue":
        "Rash, skin lesions or soft tissue swelling predominate",
    "musculoskeletal":
        "Joint or muscle pain predominates",
    "haematological":
        "Bleeding, bruising, pallor or lymph node enlargement predominate",
    "cardiovascular":
        "Chest pain, palpitations or swelling of the legs predominate",
    "constitutional_chronic":
        "Long-standing weight loss, night sweats or fatigue predominate",
}


# ------------------------------------------ L3  surgical sieve (VINDICATE-ish)
SIEVE = {
    "infective": "Caused by an infection",
    "autoimmune_inflammatory": "Autoimmune or inflammatory process",
    "neoplastic": "Cancer or a blood malignancy",
    "vascular": "Blocked, burst or inflamed blood vessels, or a clot",
    "metabolic_endocrine": "A metabolic, hormonal or electrolyte disturbance",
    "toxic_drug": "A drug reaction, poisoning, or toxin",
    "structural_surgical": "An obstruction, perforation, abscess or other surgical problem",
    "degenerative_functional": "A degenerative or functional disorder",
}


# ---------------------------------- L4  illness scripts, indexed by grid cell
# Each entry: label, plus the script fields a clinician carries.
SCRIPTS = {
    ("acute_febrile_undifferentiated", "infective"): {
        "dengue": {"label": "Dengue fever", "incubation": (4, 10),
                   "exposure": "day-biting Aedes mosquito, urban"},
        "malaria": {"label": "Malaria", "incubation": (7, 30),
                    "exposure": "night-biting Anopheles mosquito"},
        "typhoid": {"label": "Enteric fever (typhoid)", "incubation": (6, 30),
                    "exposure": "contaminated food or water"},
        "leptospirosis": {"label": "Leptospirosis", "incubation": (2, 30),
                          "exposure": "flood water, mud, animal urine"},
        "scrub_typhus": {"label": "Scrub typhus", "incubation": (6, 21),
                         "exposure": "mite bite in scrub or grassland"},
        "influenza": {"label": "Influenza", "incubation": (1, 4),
                      "exposure": "ill contacts, airborne"},
        "chikungunya": {"label": "Chikungunya", "incubation": (2, 12),
                        "exposure": "day-biting Aedes mosquito"},
        "covid19": {"label": "COVID-19", "incubation": (2, 14),
                    "exposure": "ill contacts, airborne"},
        "brucellosis": {"label": "Brucellosis", "incubation": (5, 60),
                        "exposure": "unpasteurised dairy, livestock"},
        "q_fever": {"label": "Q fever", "incubation": (14, 39),
                    "exposure": "livestock, birth products"},
        "murine_typhus": {"label": "Murine typhus", "incubation": (6, 14),
                          "exposure": "rat flea"},
        "visceral_leishmaniasis": {"label": "Visceral leishmaniasis (kala-azar)",
                                   "incubation": (60, 180),
                                   "exposure": "sandfly bite"},
        "melioidosis": {"label": "Melioidosis", "incubation": (1, 21),
                        "exposure": "soil and surface water, paddy fields"},
        "ebv_mono": {"label": "EBV infectious mononucleosis", "incubation": (30, 50),
                     "exposure": "saliva contact"},
        "hiv_seroconversion": {"label": "Acute HIV seroconversion",
                               "incubation": (14, 28), "exposure": "sexual or blood"},
        "tuberculosis": {"label": "Tuberculosis", "incubation": (30, 3650),
                         "exposure": "prolonged contact"},
        "hepatitis_a": {"label": "Acute hepatitis A", "incubation": (15, 50),
                        "exposure": "contaminated food or water"},
        "amoebic_liver_abscess": {"label": "Amoebic liver abscess",
                                  "incubation": (14, 150),
                                  "exposure": "contaminated food or water"},
    },
    ("acute_febrile_undifferentiated", "autoimmune_inflammatory"): {
        "sle_flare": {"label": "Systemic lupus erythematosus flare"},
        "stills_disease": {"label": "Adult-onset Still's disease"},
        "vasculitis": {"label": "Systemic vasculitis"},
        "rheumatic_fever": {"label": "Acute rheumatic fever"},
        "sarcoidosis": {"label": "Sarcoidosis"},
        "kawasaki": {"label": "Kawasaki disease"},
        "haemophagocytic": {"label": "Haemophagocytic lymphohistiocytosis"},
    },
    ("acute_febrile_undifferentiated", "neoplastic"): {
        "lymphoma_fever": {"label": "Lymphoma presenting as fever"},
        "leukaemia_fever": {"label": "Acute leukaemia presenting as fever"},
        "solid_tumour_fever": {"label": "Solid tumour with paraneoplastic fever"},
    },
    ("acute_febrile_undifferentiated", "toxic_drug"): {
        "drug_fever": {"label": "Drug fever"},
        "serotonin_syndrome": {"label": "Serotonin syndrome"},
        "neuroleptic_malignant": {"label": "Neuroleptic malignant syndrome"},
        "heat_stroke": {"label": "Heat stroke"},
    },
    ("acute_febrile_undifferentiated", "metabolic_endocrine"): {
        "thyroid_storm": {"label": "Thyroid storm"},
        "adrenal_crisis": {"label": "Adrenal crisis"},
    },
    ("acute_febrile_undifferentiated", "structural_surgical"): {
        "appendicitis": {"label": "Acute appendicitis"},
        "cholangitis": {"label": "Acute cholangitis"},
        "liver_abscess_pyogenic": {"label": "Pyogenic liver abscess"},
        "deep_abscess": {"label": "Deep-seated abscess"},
        "endocarditis": {"label": "Infective endocarditis"},
    },
    ("acute_respiratory", "infective"): {
        "influenza": {"label": "Influenza", "incubation": (1, 4)},
        "covid19": {"label": "COVID-19", "incubation": (2, 14)},
        "bacterial_pneumonia": {"label": "Community-acquired bacterial pneumonia"},
        "tuberculosis": {"label": "Tuberculosis", "incubation": (30, 3650)},
        "mycoplasma": {"label": "Mycoplasma pneumonia"},
        "legionella": {"label": "Legionnaires disease", "incubation": (2, 10)},
        "pertussis": {"label": "Pertussis"},
    },
    ("acute_abdominal", "structural_surgical"): {
        "appendicitis": {"label": "Acute appendicitis"},
        "cholecystitis": {"label": "Acute cholecystitis"},
        "perforation": {"label": "Perforated viscus"},
        "obstruction": {"label": "Intestinal obstruction"},
        "diverticulitis": {"label": "Diverticulitis"},
    },
    ("musculoskeletal", "autoimmune_inflammatory"): {
        "sle_flare": {"label": "Systemic lupus erythematosus flare"},
        "rheumatoid_arthritis": {"label": "Rheumatoid arthritis"},
        "stills_disease": {"label": "Adult-onset Still's disease"},
        "vasculitis": {"label": "Systemic vasculitis"},
        "reactive_arthritis": {"label": "Reactive arthritis"},
        "psoriatic_arthritis": {"label": "Psoriatic arthritis"},
        "polymyalgia": {"label": "Polymyalgia rheumatica"},
        "gout_pseudogout": {"label": "Gout or pseudogout"},
        "dermatomyositis": {"label": "Dermatomyositis"},
    },
    ("musculoskeletal", "infective"): {
        "septic_arthritis": {"label": "Septic arthritis"},
        "osteomyelitis": {"label": "Osteomyelitis"},
        "chikungunya": {"label": "Chikungunya arthritis", "incubation": (2, 12)},
        "rheumatic_fever": {"label": "Acute rheumatic fever"},
        "tb_spine": {"label": "Spinal tuberculosis"},
    },
    ("constitutional_chronic", "autoimmune_inflammatory"): {
        "sle_flare": {"label": "Systemic lupus erythematosus flare"},
        "sarcoidosis": {"label": "Sarcoidosis"},
        "vasculitis": {"label": "Systemic vasculitis"},
        "ibd": {"label": "Inflammatory bowel disease"},
    },
    ("constitutional_chronic", "neoplastic"): {
        "lymphoma": {"label": "Lymphoma"},
        "leukaemia": {"label": "Leukaemia"},
        "solid_tumour": {"label": "Occult solid tumour"},
        "myeloma": {"label": "Multiple myeloma"},
    },
    ("constitutional_chronic", "infective"): {
        "tuberculosis": {"label": "Tuberculosis", "incubation": (30, 3650)},
        "hiv_chronic": {"label": "Chronic HIV infection"},
        "brucellosis": {"label": "Brucellosis", "incubation": (5, 60)},
        "visceral_leishmaniasis": {"label": "Visceral leishmaniasis", "incubation": (60, 180)},
        "endocarditis": {"label": "Subacute infective endocarditis"},
    },
    ("acute_neurological", "infective"): {
        "bacterial_meningitis": {"label": "Bacterial meningitis"},
        "viral_meningitis": {"label": "Viral meningitis"},
        "cerebral_malaria": {"label": "Cerebral malaria"},
        "japanese_encephalitis": {"label": "Japanese encephalitis"},
        "hsv_encephalitis": {"label": "HSV encephalitis"},
        "tuberculous_meningitis": {"label": "Tuberculous meningitis"},
    },
}


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
def route(state, jev, verbose=True, gate=True):
    trace = {"levels": [], "escalated": False, "reason": None}

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
    available = sorted({m for (s, m) in SCRIPTS if s == syn})
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
    cell = SCRIPTS.get((syn, mech), {})
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
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    key = load_key()
    if not key or key == "paste_your_key_here":
        sys.exit("No API key. Set OPENJEV_API_KEY or fill .env")

    state = (HERE / args.state).read_text()
    jev = Jev(key)
    t0 = time.time()
    print(f"=== {args.state} ===")
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
