#!/usr/bin/env python3
"""Adaptive history-taking loop driven by OpenJEV.

Design (see README):
  - Jev ranks a FLAT bank of findings, not a decision tree. Ordering is
    recomputed every round from the live disease posterior.
  - Question SELECTION is expected-information-gain maths in Python, using
    Jev's calibrated nouls. No LLM touches the clinical choice.
  - The LLM (or a template stub) only rephrases the chosen finding into a
    human sentence. One direction, phrasing only.
  - The patient's free-text reply is interpreted back into a structured fact
    by Jev, never by the LLM.
  - Loop stops on evidence_sufficient, on stalled certainty, or at max rounds.
    It always ends with a handoff to a clinician.

Usage:
    python3 triage_loop.py state_a.txt --rounds 6
    python3 triage_loop.py state_a.txt --rounds 6 --truth scrub_typhus
    python3 triage_loop.py state_a.txt --phraser ollama --model qwen2.5:3b

The simulated patient is SYNTHETIC. It answers from a hidden ground-truth
profile so the question-selection behaviour can be observed. Nothing here
measures real diagnostic accuracy.
"""
import argparse
import json
import math
import os
import pathlib
import subprocess
import sys

import requests

HERE = pathlib.Path(__file__).parent
ENDPOINT = "https://api.openjev.sh/v1/systemone"
DEFAULT_LIKELIHOOD = 0.15


# --------------------------------------------------------------------------
# credentials
# --------------------------------------------------------------------------
def load_key(name="OPENJEV_API_KEY"):
    """Shell environment wins; otherwise read the chmod-600 .env file."""
    key = os.environ.get(name, "").strip()
    if key:
        return key
    envfile = HERE / ".env"
    if envfile.exists():
        for line in envfile.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, value = line.partition("=")
            if k.strip() == name:
                return value.strip().strip("'\"")
    return ""


KEY = load_key()
if not KEY or KEY == "paste_your_key_here":
    sys.exit(f"No API key. Edit {HERE / '.env'} or export OPENJEV_API_KEY.")

USAGE = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}


def jev(state, questions):
    r = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json={"model": "openjev", "state": state, "questions": questions},
        timeout=90,
    )
    if r.status_code != 200:
        sys.exit(f"HTTP {r.status_code}: {r.text[:400]}")
    data = r.json()
    u = data.get("usage", {}) or {}
    USAGE["calls"] += 1
    USAGE["input_tokens"] += u.get("input_tokens", 0)
    USAGE["output_tokens"] += u.get("output_tokens", 0)
    USAGE["cost"] += u.get("cost", 0.0)
    return data["answers"]


# --------------------------------------------------------------------------
# information theory
# --------------------------------------------------------------------------
def entropy(dist):
    return -sum(p * math.log2(p) for p in dist.values() if p > 1e-12)


def temper(dist, floor=0.02):
    """Jev saturates choice probabilities to exactly 1.00/0.00, which collapses
    entropy to zero and makes every expected-information-gain score 0. That is
    an artefact of the reported distribution, not real certainty. Mix in a small
    uniform floor so the differential stays alive and EIG remains meaningful."""
    n = len(dist)
    return {d: (1 - floor * n) * p + floor for d, p in dist.items()}


def likelihood(finding, disease):
    if disease in finding.get("supports", {}):
        return finding["supports"][disease]
    if disease in finding.get("against", {}):
        return finding["against"][disease]
    return DEFAULT_LIKELIHOOD


def posterior(prior, finding, present):
    """Bayes update of the disease distribution for one binary finding."""
    out = {}
    for d, p in prior.items():
        lk = likelihood(finding, d)
        out[d] = p * (lk if present else 1.0 - lk)
    total = sum(out.values())
    if total <= 0:
        return dict(prior)
    return {d: v / total for d, v in out.items()}


def expected_info_gain(prior, finding, p_present):
    """EIG using Jev's calibrated noul as P(finding present)."""
    h0 = entropy(prior)
    h_yes = entropy(posterior(prior, finding, True))
    h_no = entropy(posterior(prior, finding, False))
    return h0 - (p_present * h_yes + (1 - p_present) * h_no)


# --------------------------------------------------------------------------
# phrasing layer (LLM or template) -- phrasing ONLY, never selection
# --------------------------------------------------------------------------
def phrase_template(finding):
    return finding["probe"]


PHRASE_PROMPT = (
    "Rewrite the clinical question below as one warm, plain-English question a "
    "nurse would ask a patient face to face. Keep the exact clinical meaning. "
    "Do not add any new medical content, do not diagnose, do not explain, do not "
    "offer reassurance. Reply with the question only.\n\nClinical question: "
)


def phrase_openrouter(finding, model):
    """Phrasing ONLY. This model never selects a question and never reads a reply."""
    key = load_key("OPENROUTER_API_KEY")
    if not key or key == "paste_your_openrouter_key_here":
        print("    [no OPENROUTER_API_KEY -- falling back to template]")
        return phrase_template(finding)
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"model": model,
                  "messages": [{"role": "user",
                                "content": PHRASE_PROMPT + finding["probe"]}],
                  "max_tokens": 120, "temperature": 0.4},
            timeout=60,
        )
        if r.status_code != 200:
            print(f"    [openrouter HTTP {r.status_code}: {r.text[:160]} -- template]")
            return phrase_template(finding)
        text = r.json()["choices"][0]["message"]["content"].strip()
        text = text.strip('"').split("\n")[0].strip()
        if len(text) > 15 and "?" in text:
            return text
        print("    [openrouter reply unusable -- template]")
    except Exception as e:
        print(f"    [openrouter error: {e} -- template]")
    return phrase_template(finding)


def phrase_ollama(finding, model):
    prompt = (
        "Rewrite the clinical question below as one warm, plain-English question "
        "a nurse would ask a patient. Keep the exact clinical meaning. Do not add "
        "any new medical content, do not diagnose, do not explain. Reply with the "
        "question only.\n\nClinical question: " + finding["probe"]
    )
    try:
        r = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, timeout=120,
        )
        text = (r.stdout or "").strip().split("\n")[0].strip().strip('"')
        if len(text) > 15 and "?" in text:
            return text
    except Exception as e:
        print(f"    [phraser fell back to template: {e}]")
    return phrase_template(finding)


# --------------------------------------------------------------------------
# SYNTHETIC patient -- answers from a hidden ground truth. Not a real patient.
# --------------------------------------------------------------------------
def simulated_reply(finding, truth):
    lk = likelihood(finding, truth)
    if lk >= 0.55:
        return "Yes, now that you mention it, that is true."
    if lk <= 0.12:
        return "No, nothing like that at all."
    if lk >= 0.3:
        return "Maybe, a little, I am not really sure."
    return "No, I do not think so."


# --------------------------------------------------------------------------
# main loop
# --------------------------------------------------------------------------
def build_round_questions(bank, remaining):
    criteria = {d: d.replace("_", " ") for d in bank["diseases"]}
    criteria["other"] = ("None of the listed conditions explains this illness, "
                         "or the picture points outside this differential entirely")
    q = {
        "primary_diagnosis": {
            "type": "choice",
            "instructions": "Based only on the information in the state, which condition best explains this patient's illness? Answer 'other' if none of the listed conditions fits.",
            "criteria": criteria,
        },
        "outside_differential": {
            "type": "noul",
            "instructions": "Does this illness most likely lie OUTSIDE the differential of acute tropical febrile illness (dengue, malaria, typhoid, leptospirosis, scrub typhus, influenza)?",
            "criteria": {
                "true": "The features point to a condition outside this differential, such as an autoimmune, haematological, malignant or surgical cause",
                "false": "The illness fits within acute tropical febrile illness",
            },
        },
        "evidence_sufficient": {
            "type": "noul",
            "instructions": "Is the information in the state sufficient to commit to a single diagnosis without gathering any further history or test?",
            "criteria": {
                "true": "Decisive enough to name one diagnosis and act",
                "false": "Still compatible with more than one condition",
            },
        },
        "diagnostic_certainty": {
            "type": "score",
            "instructions": "How certain can a clinician be about the diagnosis given only what is recorded in the state?",
            "criteria": [
                "Pure guesswork",
                "A differential can be formed but nothing stands out",
                "One condition leads but needs confirmation",
                "One condition is strongly supported",
            ],
        },
    }
    for f in remaining:
        q["f_" + f["id"]] = {
            "type": "noul",
            "instructions": f"Based on the state, is this true of the patient: {f['probe']}",
            "criteria": {
                "true": "The state indicates this is present",
                "false": "The state indicates this is absent, or does not say",
            },
        }
    return q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state", nargs="?", default="state_a.txt")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--threshold", type=float, default=0.80,
                    help="evidence_sufficient noul at which to stop asking")
    ap.add_argument("--dominance", type=float, default=0.97,
                    help="stop when one disease reaches this posterior probability")
    ap.add_argument("--min-gain", dest="min_gain", type=float, default=0.02,
                    help="stop when the best question is worth fewer bits than this")
    ap.add_argument("--outside", type=float, default=0.60,
                    help="escalate when P(outside this differential) reaches this")
    ap.add_argument("--truth", default="scrub_typhus",
                    help="hidden ground truth for the SYNTHETIC patient")
    ap.add_argument("--phraser", choices=["template", "ollama", "openrouter"],
                    default="template")
    ap.add_argument("--model", default=None,
                    help="phrasing model; defaults per phraser "
                         "(ollama: qwen2.5:3b, openrouter: OPENROUTER_MODEL in .env)")
    ap.add_argument("--json", default=None,
                    help="write a structured transcript of the run to this path")
    args = ap.parse_args()

    if args.model is None:
        if args.phraser == "openrouter":
            args.model = (load_key("OPENROUTER_MODEL")
                          or "meta-llama/llama-3.3-70b-instruct")
        else:
            args.model = "qwen2.5:3b"

    bank = json.loads((HERE / "findings_bank.json").read_text())
    state = (HERE / args.state).read_text()
    remaining = list(bank["findings"])
    asked = []

    print(f"=== adaptive triage on {args.state} ===")
    print(f"bank: {len(remaining)} findings | phraser: {args.phraser}"
          f"{'/' + args.model if args.phraser != 'template' else ''} | "
          f"SYNTHETIC patient truth: {args.truth}\n")

    stop_reason = "max rounds reached"
    prev_certainty = None
    transcript = []

    for rnd in range(1, args.rounds + 1):
        ans = jev(state, build_round_questions(bank, remaining))
        dx = ans["primary_diagnosis"]
        prior = temper(dx["probabilities"])
        suff = ans["evidence_sufficient"]["noul"]
        cert = ans["diagnostic_certainty"]["score"]
        outside = ans["outside_differential"]["noul"]
        lead_p = max(dx["probabilities"].values())

        top = sorted(dx["probabilities"].items(), key=lambda x: -x[1])[:3]
        top_s = "  ".join(f"{d}={p:.2f}" for d, p in top)
        print(f"[round {rnd}] H={entropy(prior):.2f} bits | sufficient={suff:.2f} | "
              f"certainty={cert:.2f} | outside={outside:.2f} | {top_s}")

        # Escape hatch: the bank cannot help if the illness is not in its world.
        if outside >= args.outside or dx["choice"] == "other":
            stop_reason = (f"illness appears to lie OUTSIDE this differential "
                           f"(outside={outside:.2f}, choice={dx['choice']}); "
                           f"the findings bank does not cover it -- escalate")
            break
        if suff >= args.threshold:
            stop_reason = f"evidence_sufficient {suff:.2f} >= {args.threshold}"
            break
        if lead_p >= args.dominance:
            stop_reason = (f"leading diagnosis at {lead_p:.2f} >= {args.dominance} "
                           f"(history alone cannot go further; needs a test)")
            break
        prev_certainty = cert
        if not remaining:
            stop_reason = "findings bank exhausted"
            break

        # --- selection: pure maths on Jev's calibrated nouls ---------------
        scored = []
        for f in remaining:
            p = ans["f_" + f["id"]]["noul"]
            scored.append((expected_info_gain(prior, f, p), p, f))
        scored.sort(key=lambda x: -x[0])
        gain, p_present, chosen = scored[0]

        if gain < args.min_gain:
            stop_reason = (f"best remaining question yields only {gain:.3f} bits "
                           f"(< {args.min_gain}); no question left worth asking")
            break

        runners = "; ".join(f"{f['id']}:{g:.3f}" for g, _, f in scored[1:4])
        print(f"    pick {chosen['id']}  EIG={gain:.3f} bits  (prior p={p_present:.2f})")
        print(f"    runners-up  {runners}")

        # --- phrasing: LLM or template, no clinical authority --------------
        if args.phraser == "ollama":
            question = phrase_ollama(chosen, args.model)
        elif args.phraser == "openrouter":
            question = phrase_openrouter(chosen, args.model)
        else:
            question = phrase_template(chosen)
        reply = simulated_reply(chosen, args.truth)
        print(f"    ask > {question}")
        print(f"    sim < {reply}")

        # --- interpretation: back through Jev, not the LLM -----------------
        interp = jev(
            {"question_asked": question, "patient_reply": reply},
            {"present": {
                "type": "noul",
                "instructions": f"Does `patient_reply` indicate the presence of {chosen['topic']}?",
                "criteria": {"true": "The reply affirms it", "false": "The reply denies it or is non-committal"},
            }},
        )["present"]["noul"]

        verdict = "present" if interp > 0.6 else ("absent" if interp < 0.4 else "uncertain")
        print(f"    jev reads reply as {verdict} ({interp:.2f})\n")

        transcript.append({
            "round": rnd,
            "entropy": round(entropy(prior), 3),
            "sufficient": suff,
            "certainty": cert,
            "outside": outside,
            "posterior": {d: round(p, 3) for d, p in dx["probabilities"].items()},
            "chosen": chosen["id"],
            "eig": round(gain, 3),
            "prior_p": p_present,
            "candidates": [{"id": f["id"], "eig": round(g, 3), "p": p}
                           for g, p, f in scored[:6]],
            "question": question,
            "reply": reply,
            "interpreted": verdict,
            "interp_p": interp,
            "probe": chosen["probe"],
        })

        state += (f"\nFollow-up history taken (round {rnd}):\n"
                  f"- Asked: {chosen['probe']}\n"
                  f"- Patient replied: {reply}\n"
                  f"- Interpreted as: {chosen['topic']} -> {verdict}\n")
        asked.append((chosen["id"], verdict, round(gain, 3)))
        remaining = [f for f in remaining if f["id"] != chosen["id"]]

    # --- handoff ----------------------------------------------------------
    final = jev(state, {
        "primary_diagnosis": {
            "type": "choice",
            "instructions": "Which condition best explains this patient's illness, given everything in the state? Answer 'other' if none of the listed conditions fits.",
            "criteria": {**{d: d.replace("_", " ") for d in bank["diseases"]},
                         "other": "None of the listed conditions fits this illness"},
        },
        "safe_to_act_without_clinician": {
            "type": "noul",
            "instructions": "Would it be safe for an automated system to act on this assessment without a qualified clinician reviewing it?",
            "criteria": {"true": "Low risk and unambiguous", "false": "A clinician must review"},
        },
        "care_urgency": {
            "type": "score",
            "instructions": "How urgently does this patient need to be seen?",
            "criteria": ["Home care and review in a few days",
                         "Outpatient review within 24 hours",
                         "Same day assessment",
                         "Immediate hospital admission"],
        },
    })

    fdx = final["primary_diagnosis"]
    print("--- handoff ---")
    print(f"stopped because: {stop_reason}")
    print(f"questions asked: {len(asked)} -> " +
          ", ".join(f"{i}({v})" for i, v, _ in asked))
    print(f"leading: {fdx['choice']} at confidence {fdx['confidence']:.2f}")
    for d, p in sorted(fdx["probabilities"].items(), key=lambda x: -x[1])[:4]:
        print(f"    {d:16s} {p:.3f}")
    print(f"urgency {final['care_urgency']['score']:.2f}/3 | "
          f"safe_without_clinician {final['safe_to_act_without_clinician']['noul']:.2f}")
    print(f"SYNTHETIC truth was {args.truth} -> "
          f"{'matched' if fdx['choice'] == args.truth else 'NOT matched'}")
    print(f"usage: {USAGE['calls']} calls, {USAGE['input_tokens']} in / "
          f"{USAGE['output_tokens']} out, ${USAGE['cost']:.5f}")
    print("\nThis is a triage summary for a clinician, not a diagnosis.")

    if args.json:
        import datetime
        payload = {
            "case": args.state,
            "generated_utc": datetime.datetime.now(datetime.timezone.utc)
                                     .strftime("%Y-%m-%d %H:%M UTC"),
            "phraser": args.phraser,
            "phrase_model": args.model if args.phraser != "template" else None,
            "truth": args.truth,
            "diseases": bank["diseases"],
            "bank_size": len(bank["findings"]),
            "bank": [{"id": f["id"], "probe": f["probe"],
                      "supports": f.get("supports", {})} for f in bank["findings"]],
            "thresholds": {"sufficient": args.threshold, "dominance": args.dominance,
                           "min_gain": args.min_gain, "outside": args.outside},
            "rounds": transcript,
            "stop_reason": stop_reason,
            "final": {
                "choice": fdx["choice"],
                "confidence": fdx["confidence"],
                "probabilities": {d: round(p, 3)
                                  for d, p in fdx["probabilities"].items()},
                "urgency": final["care_urgency"]["score"],
                "urgency_legend": final["care_urgency"]["legend"],
                "safe_without_clinician":
                    final["safe_to_act_without_clinician"]["noul"],
                "matched": fdx["choice"] == args.truth,
            },
            "usage": dict(USAGE),
        }
        out = pathlib.Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2))
        print(f"transcript written to {out}")


if __name__ == "__main__":
    main()
