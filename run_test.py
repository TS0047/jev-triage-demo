#!/usr/bin/env python3
"""Test OpenJEV on a medical triage state.

Usage:
    export OPENJEV_API_KEY=...            # get one at https://openjev.sh
    python3 run_test.py state_a.txt       # vague symptoms, nothing tested
    python3 run_test.py state_b.txt       # same patient, exam + labs available

Prints every answer with its probability distribution, then a short read on
whether the model committed to a diagnosis or held back for more data.
"""
import json
import os
import sys
import pathlib
import requests

HERE = pathlib.Path(__file__).parent
ENDPOINT = "https://api.openjev.sh/v1/systemone"

state_file = HERE / (sys.argv[1] if len(sys.argv) > 1 else "state_a.txt")
state = state_file.read_text()
questions = json.loads((HERE / "questions.json").read_text())

def load_key():
    """Prefer the shell environment; fall back to the local .env file."""
    key = os.environ.get("OPENJEV_API_KEY", "").strip()
    if key:
        return key
    envfile = HERE / ".env"
    if envfile.exists():
        for line in envfile.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == "OPENJEV_API_KEY":
                return value.strip().strip("'\"")
    return ""


key = load_key()
if not key or key == "paste_your_key_here":
    sys.exit(
        "No API key found.\n"
        f"Edit {HERE / '.env'} and replace paste_your_key_here with your key\n"
        "(get one at https://openjev.sh), or export OPENJEV_API_KEY in your shell."
    )

resp = requests.post(
    ENDPOINT,
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    json={"model": "openjev", "state": state, "questions": questions},
    timeout=60,
)
if resp.status_code != 200:
    sys.exit(f"HTTP {resp.status_code}: {resp.text[:500]}")

data = resp.json()
answers = data["answers"]

print(f"=== {state_file.name} ===\n")
for qid, a in answers.items():
    t = a["type"]
    if t == "noul":
        p = a["noul"]
        print(f"{qid:34s} noul = {p:.2f}  ({'yes' if p > 0.5 else 'no'})")
    elif t == "choice":
        print(f"{qid:34s} {a['choice']}   confidence {a['confidence']:.2f}")
        for k, v in sorted(a["probabilities"].items(), key=lambda x: -x[1]):
            print(f"{'':36s}  {k:28s} {v:.3f}")
    elif t == "score":
        print(f"{qid:34s} score = {a['score']:.2f}   confidence {a['confidence']:.2f}")
        for k, v in sorted(a["legend"].items()):
            print(f"{'':36s}  [{k}] {v[:52]:54s} {a['probabilities'][k]:.3f}")
    print()

# --- interpretation -------------------------------------------------------
dx = answers["primary_diagnosis"]
suff = answers["evidence_sufficient"]["noul"]
cert = answers["diagnostic_certainty"]["score"]

print("--- read ---")
print(f"names {dx['choice']!r} at confidence {dx['confidence']:.2f}")
if suff < 0.5:
    print("model says the evidence is NOT sufficient -> it held back rather than guessing")
else:
    print("model says the evidence IS sufficient -> it committed to a diagnosis")
print(f"certainty level {cert:.2f} / 3")
print(f"wants next: {answers['most_useful_next_test']['choice']}")
print(f"missing:    {answers['most_important_missing_information']['choice']}")
print(f"would ask:  {answers['question_to_ask_patient']['choice']}")
print(f"usage: {data.get('usage')}")
