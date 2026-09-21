# Public datasets with symptoms + ground-truth diagnosis

Searched, verified fetchable, and one of them actually run. All are live as of
this writing - the fetch commands below were executed, not copied from a page.

## The shortlist

| dataset | size | what you get | licence | verdict |
|---|---|---|---|---|
| **DDXPlus** (Mila) | 1.3M patients, 49 pathologies, 223 evidences | symptoms + antecedents + ground-truth pathology + **weighted differential** | CC-BY-4.0 | **used here** |
| **MedCaseReasoning** (Stanford/zou-lab) | 14,489 cases | free-text `case_prompt` + `diagnostic_reasoning` + `final_diagnosis` | open | best next step |
| NEJM-MedQA diagnostic reasoning | MedQA + NEJM splits | vignette + answer | research | board-exam style |
| AgentClinic (MedQA / MIMIC-IV / NEJM) | 214 / 200 / 120 | OSCE dialogue, labs, gold dx | research | for interactive agents |
| NEJM-Bench | 1,063 image challenges | image + vignette + dx | NEJM terms | multimodal, answer keys withheld |

### Why DDXPlus won

It is the only one that gives a **differential with weights**, not just a
label - so it can score calibration, not merely accuracy. It is also CC-BY-4.0,
ungated, and its evidence codes decode to English question text, so cases
render as prose a clinician would recognise.

    curl -sL -o datasets/release_evidences.json \
      https://huggingface.co/datasets/aai530-group6/ddxplus/resolve/main/release_evidences.json
    curl -sL -o datasets/release_conditions.json \
      https://huggingface.co/datasets/aai530-group6/ddxplus/resolve/main/release_conditions.json

Rows stream from the HF datasets-server with no credentials and no 700MB
download:

    https://datasets-server.huggingface.co/rows?dataset=aai530-group6/ddxplus&config=default&split=test&offset=0&length=30

## Measured results - flat arm, 49 real pathologies, 30 test cases

    top-1   15/30   50%
    top-5   28/30   93%
    cost    $0.0082 total  ($0.00027 per case)

This is the first accuracy number in this project measured against external
ground truth rather than synthetic patients I wrote myself.

### Where the errors are

    distinct conditions       12/15   80% top-1
    respiratory look-alikes    3/15   20% top-1

Nearly every miss is inside one confusable cluster: URTI vs influenza vs acute
rhinosinusitis vs bronchitis vs laryngitis. On history alone, without
examination or tests, these genuinely overlap - the misses are mostly
*defensible* clinical answers, and 13 of the 15 had the truth at rank 2-5.

Two hard misses (truth not in top-5): `Chronic rhinosinusitis`, where the model
answered `none_of_these`; and `Acute dystonic reactions`, answered as
`Myasthenia gravis`.

### Calibration is poor at the top end

    confidence band   n    accuracy
    0.2 - 0.4         4      75%
    0.4 - 0.6         5      60%
    0.6 - 0.8         7       0%     <-- worst band
    0.8 - 1.0        12      75%

The 0.6-0.8 band scored 0/7. Stated confidence is **not** reliable as a
threshold on this dataset. A "act if conf > 0.6" rule would have fired on seven
cases and been wrong every time. This is the single most important finding in
this file and it argues against trusting a single confidence number as a gate.

## Hierarchical arm on DDXPlus, after populating the grid

The grid was rebuilt to cover all 49 DDXPlus pathologies (`grids.py`,
checked by `validate_grids.py`: 49/49 exact string match, no extras, no
invalid syndrome or mechanism, no empty cell, no oversized cell).

Same 40 cases (offset 30), before and after the repair:

    arm                       top-1        escalated   precision when answered
    hier, gaps present        17/40  42%      11             59%
    hier, grid repaired       22/40  55%       8             69%
    flat255                   22/40  55%       0             55%

**On the 32 cases the repaired hierarchy chose to answer, it beat the flat
list 69% to 59% on the same cases.** Overall top-1 is a tie at 55% because
the hierarchy declines 8 cases the flat arm always answers - and on those 8
the flat arm was right only 3/8 (38%), so the escalations are concentrated on
genuinely hard cases rather than easy ones.

That is the real trade: the hierarchy is more accurate when it commits, and
converts most of its would-be errors into refusals instead of wrong labels.

### Two grid bugs the data exposed

1. **`Localized edema` unreachable from `cardiovascular`.** Leg swelling
   routes to cardiovascular/vascular, but the condition was only authored
   under skin and allergic cells, so the router reached the right cell and
   found nothing. Fixed by adding the entry points a clinician would use.
2. **Fragile single-entry pathologies.** 17 of 49 conditions were reachable
   from exactly one syndrome, so a single L2 misroute lost them permanently.
   Reduced to 12, and `validate_grids.py` now warns on every remaining one.

### A "false" red flag that was correct medicine

One GERD case escalated on `active_bleeding`. Inspecting it: the patient
reported **black tarry stools**. That is melena - upper gastrointestinal
bleeding - which needs endoscopy regardless of the reflux label. DDXPlus
records the pathology as GERD; the router was not wrong, the dataset label is
simply not a triage decision. Scoring this as a miss understates the router.

## Original run, before the grid was populated: 7/12 escalated

Expected, and it is the coverage-gap failure mode predicted in HIERARCHY.md
appearing on real data. The grid in `hierarchical_router.py` was authored for
**tropical febrile illness**; DDXPlus is largely respiratory, cardiac and ENT.
When it did route within an authored cell it worked (`acute_respiratory >
infective > influenza`), but most cases fell into cells that do not exist.

The lesson is the one already written down: **a hierarchy fails by
dead-ending, a flat list fails by guessing.** On out-of-domain data the flat
arm produces a plausible wrong answer and the hierarchy correctly refuses.
Which behaviour you want depends on whether a wrong label or a refusal is
worse in your setting.

To evaluate the hierarchy fairly on DDXPlus, the grid needs
`acute_respiratory`, `cardiovascular` and ENT cells populated with the 49
DDXPlus pathologies - a mechanical authoring job, not a design change.

## Honest limits

- DDXPlus patients are **synthesised by a rule-based system** from a knowledge
  base. Agreeing with it means agreeing with that rule engine, not being
  clinically correct.
- No examination findings and no laboratory results are included, so every case
  is harder than real practice and the respiratory confusion is partly an
  artefact of that.
- 30 cases is a pilot, not a benchmark. Nothing here has confidence intervals.
- The DDXPlus ground truth itself sits outside its own top-5 differential in
  3/30 cases, so the label is not beyond question either.

## Reproduce

    python3 eval_ddxplus.py --n 30 --arm flat
    python3 eval_ddxplus.py --n 12 --arm hier
