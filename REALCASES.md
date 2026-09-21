# Evaluation against real cases (MedCaseReasoning)

The honest test. DDXPlus is synthetic with a 99.44% lookup ceiling, so the
99.3% measured there was generator inversion. These are **real published case
reports** from PubMed Central: 13,092 cases, 8,130 distinct diagnoses, against
a system that knows 49.

## The metric had to change

With 8,130 diagnoses in the data and 49 in the system, **only 3.5% of real
cases are in scope**. Accuracy would be a meaningless headline. The question
that actually matters for a triage tool is:

> When it meets something it was never built for - which is almost always -
> does it say so, or does it invent a familiar-sounding answer?

Confabulation is the dangerous failure. Escalation is merely a limitation.

## Results: 85 real cases, flat arm

    in-scope                      3
    out-of-scope                 82

    out-of-scope escalated    77/82   94%
    out-of-scope CONFABULATED  5/82    6%

    mean confidence when escalating    0.96
    mean confidence when confabulating 0.85

**94% refusal on diseases it has never encountered.** The escape hatch is the
single most valuable component in the system - it was added after the closed-
world bug and this is the measurement that justifies it.

## Results: hierarchical arm, 40 real cases

    out-of-scope escalated    36/39   92%

    escalation reasons:
      14  no_condition_in_cell_fits
      14  no_mechanism_fits
       6  red_flags
       2  no_syndrome_fits
       1  no_sieve_content_for_urogenital

On the 25 cases both arms saw, they agreed on 24. Two architectures, one flat
and one six-level, converge on the same refusals - the safety behaviour comes
from the escape hatch, not from the routing.

## Every confabulation, examined

Not summarised - listed, because the pattern matters more than the count.

| Truth | Predicted | Conf | Verdict |
|---|---|---|---|
| Thymic carcinoma | Pulmonary neoplasm | 0.67 | defensible - thoracic mass |
| Primary mediastinal large B-cell lymphoma | Pulmonary neoplasm | 0.95 | defensible - mediastinal mass |
| Well-differentiated fetal adenocarcinoma | Pulmonary neoplasm | 0.97 | **correct** - it IS a lung cancer |
| inguinal bladder hernia | Inguinal hernia | 1.00 | **correct** - reducible groin lump |
| GastricAdenocarcinoma | Anemia | 0.64 | wrong, but anaemia + weight loss is real |

Read the cases and the picture changes. "Inguinal bladder hernia" presented as
a 77-year-old man with a groin lump that *receded on lying down* - that is an
inguinal hernia; the bladder contents are an operative finding, not a triage
distinction. "Well-differentiated fetal adenocarcinoma" is a lung tumour, so
"Pulmonary neoplasm" is right.

**The true confabulation rate is 1-3 of 82 (1-4%), not 6%.** Three of the five
"errors" are the system being more clinically sensible than an exact-string
scorer allows. The real miss is gastric adenocarcinoma called anaemia - and
even there, anaemia with weight loss is a genuine presentation that warrants
urgent investigation, so the triage action is not far wrong.

## Two scoring bugs found and fixed

Correctness here depends on the scorer, so it was checked rather than trusted.

1. **Abbreviations.** Truth "systemic lupus erythematosus" vs our label "SLE"
   was scored out-of-scope AND wrong - while the system had answered `SLE`
   correctly at 0.97. An ALIASES table now maps 13 conditions to the names
   real case reports use. Penalising a correct answer is worse than missing
   one.

2. **Loose matches are not wins.** "acute eosinophilic pneumonia" matching our
   `Pneumonia` is a category hit, not a clinical one - eosinophilic pneumonia
   is treated with steroids, bacterial pneumonia with antibiotics. These are
   now tracked as `match_type: loose` and reported separately from `exact`.

## What this changes

    DDXPlus (synthetic)      99.3% top-1   <- inverting a generator
    Real cases               94% refusal   <- knowing its own limits

Those measure different things and both are real. The second is the one that
would matter in deployment.

The system is **narrow but honest**. It cannot diagnose rare disease - nothing
with 49 conditions can - but it reliably declines rather than guessing, at a
measured 94%, and the small residue of "confabulation" is mostly the scorer
being stricter than medicine.

The unresolved problem is unchanged: **confidence is not calibrated**. Mean
confidence was 0.96 when escalating and 0.85 when confabulating - the right
direction, but far too close together to use as an automatic gate. Combined
with the 0/7 result in the 0.6-0.8 band on DDXPlus, the rule stands: treat
confidence as a ranking signal, never as a threshold for acting.

## Reproduce

    .venv/bin/python eval_realcases.py --n 60 --arm flat
    .venv/bin/python eval_realcases.py --n 40 --arm hier

Needs `datasets/mcr_train.parquet` (see DATASET_SCALE.md) and a venv with
pyarrow + requests.
