# OpenJEV adaptive medical triage

Testbed for TypeSafe's Jev (via the OpenJEV proxy) as a **calibrated decision
layer** for clinical history-taking.

    POST https://api.openjev.sh/v1/systemone

Not a diagnostic tool. Every run ends in a handoff to a clinician, and the
model itself agrees: `safe_to_act_without_clinician` came back 0.03-0.04 in
every single state tested, including the ones it was 100% certain about.

**Live demo:** https://ts0047.github.io/jev-triage-demo/

## Branches

    production                 hosted site source (GitHub Pages -> /docs). Stable.
    main                       research trunk, carries both arms
    flat-differential          flat option set + scaling measurements
    hierarchical-differential  clinical hierarchy (see HIERARCHY.md)

Deploy by merging into `production`; Pages builds from that branch only, so
research work on `main` never touches the live site.

## Files

    .env                  API keys, chmod 600, git-ignored (see .env.example)
    state_a.txt           day-5 tropical fever, no vitals, nothing tested (underdetermined)
    state_b.txt           same patient + NS1 positive, platelets 62k falling (dengue, decisive)
    state_c.txt           same symptoms, NS1 NEGATIVE, vivax on smear (contradicts the anchor)
    state_d.txt           lupus presentation -- deliberately OUTSIDE the differential
    questions.json        9-question battery, all three primitives
    run_test.py           single-shot: run the battery against one state
    findings_bank.json    25 history findings with per-disease likelihoods
    triage_loop.py        adaptive multi-round history-taking loop
    docs/                 static web demo (see Web demo below)
    SCALING.md            measured limits of the flat option set (255 cap)
    scaling_probe*.py     the probes behind SCALING.md
    HIERARCHY.md          clinical reasoning frameworks + head-to-head results
    grids.py              (syndrome, mechanism) -> conditions; tropical + ddxplus
    validate_grids.py     mechanical grid checks; exits non-zero on any failure
    DATASETS.md           public datasets + measured accuracy against DDXPlus
    MATRIX.md             how likelihoods are set, and how to learn them properly
    DATASET_SCALE.md      is a bigger dataset the answer? (measured: no)
    REALCASES.md          evaluation on REAL published cases: 94% refusal
    BOTTLENECK.md         too few diseases, or too little data? (measured)
    HYPOTHESIS_SPACE.md   nothing is trained: why the option list IS the model
    WIDE_TREE.md          2,505 conditions in 2 calls; wide beats deep
    build_taxonomy.py     harvests a 24 x 250 taxonomy from real corpus data
    wide_router.py        two-level router, escape hatch at both levels
    eval_wide.py          flat vs wide vs deep on real cases
    hypothesis_space.py   list-as-sample-space + names-only list expansion
    coverage_curve.py     how many conditions to cover X% of real cases
    shape_of_problem.py   the Zipf treadmill behind list growth
    eval_realcases.py     harness for MedCaseReasoning (real PMC case reports)
    learning_curve.py     accuracy vs training-set size; saturates at n=2,500
    dataset_structure.py  DDXPlus's 99.44% lookup ceiling
    learn_likelihoods_v2.py  applicability-aware MLE over 134k DDXPlus patients
    compare_matrices.py   held-out: learned vs hand-authored-granularity
    noise_sensitivity.py  direction-vs-precision sensitivity
    eval_ddxplus.py       evaluation harness against DDXPlus ground truth
    hierarchical_router.py  ROWS / qualifiers / syndrome / sieve / scripts routing
    compare_arms.py       flat-255 vs hierarchical, same states same day
    state_e.txt           meningococcal meningitis (red flags must fire)
    state_f.txt           chronic zoonotic fever (tempo + epi gate)

## Single-shot results

                                  state_a          state_b          state_c
    primary_diagnosis             dengue 0.63      dengue 1.00      malaria 1.00
    evidence_sufficient           0.04  no         0.75  yes        0.66  yes
    diagnostic_certainty          1.74 / 3         3.00 / 3         3.00 / 3
    most_useful_next_test         dengue_ns1       none_needed      none_needed
    warning_signs_present         0.21             0.96             0.43
    care_urgency                  1.97             2.91             2.48 (conf 0.48)
    safe_without_clinician        0.03             0.03             0.04

Two findings worth keeping:

- **Diagnosis and sufficiency decouple.** On state_a it leaned dengue at 0.68
  while simultaneously saying "evidence not sufficient" at 0.04. A leading
  hypothesis plus an explicit refusal to act on it.
- **It drops the anchor.** state_c has a symptom block byte-identical to
  state_b's, but NS1 negative + positive smear moved dengue to 0.000 and
  malaria to 1.000.

## Why a flat bank, not a decision tree

A tree hardcodes question order at authoring time. Jev gives you a live
posterior after every turn, so the best next question is whichever most splits
the *current* differential -- computable, not authorable. Trees also explode
combinatorially, have no node for "I don't know", and collapse a calibrated
0.68 into a binary branch, discarding the thing you're paying for.

## Loop architecture

    1. Jev scores the disease choice + one noul per unasked finding -- ONE call
    2. Python picks the finding with the highest expected information gain
    3. Phrasing layer turns it into a human sentence (template, Ollama, OpenRouter)
    4. Patient replies in free text
    5. Jev interprets the reply back into a structured fact
    6. Append to state, drop the finding, repeat

**The LLM never selects a question and never reads a reply.** It is a phrasing
layer at the edges only. Every clinical decision stays in the calibrated
component -- that is the whole point of the design.

Stop conditions (all four are needed):

    outside >= 0.60 or choice == "other"   -> escalate, bank cannot help
    max(posterior) >= 0.97                 -> dominance; needs a lab test now
    best_eig < 0.02 bits                   -> no question left worth asking
    round > cap                            -> hard ceiling (8 by default)

## Results: 25-finding bank, synthetic patients

    truth           questions  path                                          outcome
    scrub_typhus    1          eschar(+)                                     matched, 1.00
    typhoid         5          eschar- scrub- cough- stepladder+ water+      matched, 0.92
    leptospirosis   8          ...flood_water+ then confirmatory sweep       matched, 0.84
    lupus (state_d) 0          -- outside=0.95 on round 1                    escalated

Question ordering is genuinely evidence-driven: round 1 always opens with
`eschar` (0.185 bits, the single best splitter of this differential), but the
paths diverge immediately based on the answer. In the typhoid run,
`untreated_water` jumped to 0.352 bits at round 5 -- *after* stepladder fever
landed -- because confirming the exposure route only pays off once the disease
is plausible. Nothing in the bank encodes that ordering.

Cost: $0.0003 - $0.001 per full consultation, ~1.5s per round.

## Three bugs found and fixed during testing

1. **Saturation kills EIG.** Jev reports choice probabilities as exactly 1.00 /
   0.00. Entropy collapses to zero, every expected-gain score becomes 0.000,
   and the loop picks questions in arbitrary bank order -- it asked 5 useless
   questions after already being certain. Fixed with `temper()`, a 2% uniform
   floor. The saturation is an artefact of the *reported* distribution, not
   real certainty, so flooring it is the honest correction.
2. **`evidence_sufficient` never fires.** It stayed at 0.04-0.10 even at 100%
   posterior, because history alone genuinely cannot confirm a tropical fever --
   it wants a lab test, and no amount of questioning will produce one. Stopping
   on that alone loops forever. Added `--dominance` (posterior >= 0.97) and
   `--min-gain` (best question worth < 0.02 bits) as the real terminators.
3. **A closed option set produces confident wrong answers.** With six diseases
   and no escape hatch, the lupus state (`state_d.txt`) was answered
   **"dengue 0.42"** after three wasted rounds. Given an `other` option and an
   `outside_differential` noul, the same input returned **"other" at 1.00** and
   escalated on round one. Widening the disease list is the *second* fix; the
   escape hatch is the first, and it is what makes the system safe at any bank
   size.

The second one is the more interesting result: the model was right and the loop
design was wrong. `evidence_sufficient` is not a "stop asking" signal, it is a
"stop and order a test" signal.

## Web demo

Three static pages, no build step, no framework:

    docs/index.html        case studies -- pre-generated run transcripts
    docs/live.html         live consultation -- user types symptoms, loop runs in-browser
    docs/coverage.html     the six illnesses, discrimination matrix, what falls outside
    docs/live.js           the loop ported to client-side JS
    docs/data/*.json       transcripts + findings bank + disease notes
    docs/404.html          error page
    docs/.nojekyll         disables Jekyll on GitHub Pages

Serve locally:

    cd docs && python3 -m http.server 8777

### Case studies (`index.html`)

Fetches `data/*.json` at runtime and renders everything from it: verdict, final
differential, per-round question selection with the full candidate ranking, the
25-finding bank (asked findings highlighted), and measured cost. Regenerate the
data and the page updates -- nothing is hardcoded in the HTML.

    python3 triage_loop.py state_a.txt --rounds 8 --truth typhoid \
        --phraser openrouter --json docs/data/typhoid.json

### Live consultation (`live.html`)

The whole loop ported to JS, calling `api.openjev.sh` directly from the browser
(CORS is open -- verified). Users describe symptoms in plain language and answer
the questions the model chooses.

Deliberate design decisions:

- **A demo key is embedded in `live.js`** so visitors need no setup. It is
  public by construction on a static host -- anyone can read it in devtools.
  Rotate at openjev.sh if abused. A visitor-supplied key (Advanced disclosure)
  overrides it and is kept in `sessionStorage` only.
- **No phrasing LLM client-side.** Probes render verbatim, so no model rewords
  a clinical question unsupervised and no second credential is needed.
- **Consent gate** before the form; nothing identifying should be entered.
- **`red_flags` noul checked every round**, short-circuiting before any question
  is asked. Verified: breathless + confused + bleeding returned urgency 3.00/3
  with zero questions and routed straight to emergency care.

Known quirk: free-text intake is more suggestive than a structured state file.
The same case pushed the top outcome to 0.95 on round 1 versus 0.66 as
`state_a.txt`, so the live tab often hits dominance before asking much. Raise
`LIMITS.dominance` in `live.js` if you want it to work harder before conceding.

### Coverage (`coverage.html`)

Per-illness cards (vector, incubation, clinical picture, deterioration signs,
confirmatory test) with the findings that point to each, a 25x6 discrimination
matrix, and an explicit account of what falls outside the differential and what
happens then.

### Hosting

`docs/` is a static directory with no build step and no server-side code. It
works as-is on GitHub Pages (Settings -> Pages -> main branch, /docs folder),
Netlify, Vercel, Cloudflare Pages, or any static host.

`index.html` and `coverage.html` make no API calls at all. `live.html` calls
OpenJEV from the browser with the embedded demo key. If that key gets abused,
the fix that keeps zero-setup UX is a small Cloudflare Worker proxying the API
with the key server-side.

### Adding a case to the demo

1. Write a new `state_*.txt`.
2. Run the loop with `--json docs/data/<name>.json`.
3. Add `{file:'<name>.json', label:'...'}` to the `CASES` array in
   `docs/index.html`.

### Adding an illness

1. Add it to `diseases` in `findings_bank.json`.
2. Add `supports`/`against` entries on the findings that discriminate it.
3. Add a blurb to `docs/data/disease_notes.json` (used by the coverage page).
4. Copy the bank into `docs/data/findings_bank.json` -- the live and coverage
   pages read that copy.

## Usage

    python3 run_test.py state_c.txt

    python3 triage_loop.py state_a.txt --rounds 8 --truth leptospirosis
    python3 triage_loop.py state_a.txt --rounds 8 --phraser ollama --model qwen2.5:3b
    python3 triage_loop.py state_a.txt --rounds 8 --phraser openrouter
    python3 triage_loop.py state_d.txt --rounds 6            # escalation path

    python3 validate_grids.py                                # ALWAYS run after editing grids.py
    python3 hierarchical_router.py state_d.txt --grid tropical
    python3 eval_ddxplus.py --n 40 --offset 30 --arm both --grid ddxplus

`--truth` drives a SYNTHETIC patient that answers from a hidden profile. It
exists to observe question-selection behaviour and measures nothing about real
diagnostic accuracy.

### Setup

    cp .env.example .env && chmod 600 .env
    # fill in OPENJEV_API_KEY (https://openjev.sh)
    # optional: OPENROUTER_API_KEY for --phraser openrouter

## Known limits

- **The 255-option cap is solved by width, not depth** (WIDE_TREE.md):
  24 categories x up to 250 conditions = 2,505 addressable in 2 calls, 51x
  the original 49. On real cases: flat 1/22, wide 10/22. Wide also beats a
  3-level tree of the same conditions (50.0% vs 43.8%) while costing fewer
  calls - routing error compounds as p^d, so depth is paid for twice.
- **Nothing is trained.** Jev is frozen behind an API; the option list is the
  sample space, so an absent condition has no probability rather than a low
  one. Growing the list costs only the names: a 200-name list built from
  corpus frequency with zero authored likelihoods scored 6/14 on real cases
  where the 49-condition list scored 0/14 (HYPOTHESIS_SPACE.md).
- Evaluated on 85 real published case reports (REALCASES.md): 94% of
  out-of-scope diseases correctly escalated, and 3 of the 5 apparent
  confabulations were the scorer being stricter than medicine. Narrow but
  honest - it declines rather than guessing.
- DDXPlus is synthetic and near-deterministic: memorising every evidence set
  scores 99.44%, and only 3.09% of patients sit in an ambiguous set. High
  accuracy there measures generator inversion, not clinical reasoning
  (DATASET_SCALE.md).
- The findings bank is hand-authored and its likelihoods are plausible, not
  sourced from epidemiological data. Real use needs real priors. Measured
  consequence (MATRIX.md): exact decimals barely matter (rounding everything
  to a 0.05 grid costs 0.3pp) but DIRECTION dominates - flipping 5% of cells
  drops accuracy 99.3% -> 46.5%. Review the signs, not the second decimal.
- Six diseases, one clinical presentation (tropical fever). Anything else must
  hit the escape hatch -- which is tested, but the list is still narrow.
- **The API caps `choice` at 255 options.** A flat list cannot scale to a real
  differential, and on ambiguous states confidence decays as the list grows
  (0.65 -> 0.45 from 7 -> 255 options) even though ranking stays stable. See
  SCALING.md for the measurements and the hierarchical design that follows.
- `warning_signs_present` scored only 0.43 on the malaria state because the
  criteria wording listed dengue-flavoured danger signs. Prompt-design fault,
  not a model fault -- make warning-sign criteria disease-agnostic.
- Findings are treated as conditionally independent in the Bayes update. They
  are not (rash and petechiae correlate). Fine for ranking, wrong for
  reporting a true posterior.
- The embedded demo key in `live.js` is public and in git history permanently.

## Not a medical device

This is a research demonstration of calibrated decision-model architecture. It
provides no medical advice, is not validated for clinical use, and must not be
used to diagnose or treat any person. See LICENSE.
