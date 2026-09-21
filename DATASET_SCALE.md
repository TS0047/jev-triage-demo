# Is there anything bigger than DDXPlus?

Short answer: yes, but **bigger is the wrong axis**, and I can show that with
numbers rather than opinion.

## First: I was only using 10% of DDXPlus

    split      rows
    train    1,025,602
    test       134,529   <- everything so far used only this
    validate   132,448
    TOTAL    1,292,579

So before looking elsewhere there was already 8x more DDXPlus available.

## Does more data help? No - it saturates at 2,500 patients

`learning_curve.py` fits the likelihood matrix on increasing sample sizes and
scores every fit on the same held-out 3,000 patients:

    train n     top-1    top-3    top-5
         50     28.9%    40.3%    45.6%
        100     47.3%    54.7%    69.2%
        250     77.7%    83.1%    86.6%
        500     93.3%    96.8%    97.6%
      1,000     97.1%    99.0%    99.1%
      2,500     99.1%   100.0%   100.0%
      5,000     99.3%   100.0%   100.0%
     10,000     99.3%   100.0%   100.0%
     50,000     99.3%   100.0%   100.0%
    131,529     99.3%   100.0%   100.0%

**Within 1pp of the best at n = 2,500. Everything past that buys 0.2pp.**
Downloading the 1M-row train split would add nothing measurable. A matrix of
49 x 223 cells has ~11k parameters; a few thousand patients is plenty to fill
it. This is what statistical saturation looks like.

## Why the 99% is not as good as it sounds

`dataset_structure.py` asks how much of DDXPlus is a lookup table:

    patients                      134,529
    pathologies                        49
    evidences                         223
    evidences per patient      2 / 15 / 38  (min/median/max)
    class balance                  242.9x  (8,743 most common vs 36 rarest)

    distinct evidence sets         43,921
    sets mapping to >1 pathology      340   (0.77%)
    patients in an ambiguous set    4,153   (3.09%)

    LOOKUP-TABLE CEILING            99.44%

Memorising every evidence set and guessing its majority class scores 99.44%.
My learned matrix scored 99.3%. **I was not doing medicine - I was inverting a
rule-based generator, and nearly perfectly.**

Only 3.09% of patients sit in an evidence set that is diagnostically ambiguous.
Real clinical practice is mostly ambiguity; that is why diagnosis is hard. A
dataset where identical symptoms almost always imply an identical diagnosis
cannot teach or measure that.

**This is the real ceiling, and it is a property of the dataset, not of size.**
A 10x bigger synthetic dataset from the same generator would have the same
ceiling.

## What actually exists, verified

Checked programmatically, not copied from a blog. "Fetchable" = the HF
datasets-server answered with real row counts, or the file downloaded here.

| Dataset | Size | Real? | Access | Symptom->diagnosis? |
|---|---|---|---|---|
| **DDXPlus** | 1,292,579 patients, 49 pathologies | synthetic | open, no auth | yes, structured |
| **MedCaseReasoning** | 14,489 cases, 8,130 diagnoses | **real** (PMC case reports) | open, no auth | yes, free text |
| MedMCQA | 193,155 | real exam items | open | no - MCQ |
| MedQuAD | 47,441 | real | open | no - QA pairs |
| MedQA-USMLE | 11,451 | real exam items | open | partly - vignettes |
| **MIMIC-IV** | 364,627 patients / 546k admissions | **real** | **credentialed**: PhysioNet + CITI training | ICU/ED, ICD codes |
| eICU-CRD | 200,859 ICU stays | real | credentialed | ICU only |
| Synthea | **unlimited** (you generate it) | synthetic | open | yes, but same-generator problem |

Failed the availability check: `Kevinkrs/MedDialog`, `bio-nlp-umass/medalign`,
`hpe-ai/medical-cases-open` - gated or removed. Listing them as options without
checking would have been wrong.

## The genuinely better dataset is smaller, not bigger

**MedCaseReasoning**: 14,489 real published case reports. Downloaded and
measured here:

    cases                        13,092  (train split)
    distinct final diagnoses      8,130
    seen exactly once             6,305  (78% of distinct)
    mean cases per diagnosis       1.61

Compare the diagnosis space: **8,130 vs DDXPlus's 49.** That is 166x the
clinical breadth in 1% of the rows.

It also contains the thing DDXPlus structurally cannot. A sampled case:
phototoxic drug reaction, where *cellulitis was diagnosed first*, treated with
dicloxacillin, which then caused a drug eruption that confounded the picture
further. Anchoring, a treatment complication, and a revised diagnosis - none of
which can occur in a dataset with a 99.44% lookup ceiling.

**But you cannot learn likelihoods from it.** With 1.61 cases per diagnosis and
78% singletons, counting P(finding | disease) is hopeless - there is nothing to
count. It is an *evaluation* set, not an *estimation* set.

## The conclusion that actually follows

The two needs are different and no single dataset serves both:

    estimating likelihoods   needs many patients per disease, few diseases
                             -> DDXPlus is already saturated at 2,500. Done.

    evaluating a triage      needs many diseases, real ambiguity, real errors
    system honestly          -> MedCaseReasoning, and it is deliberately hard

Chasing a bigger version of DDXPlus optimises a number that is already 0.2pp
from its ceiling. The honest next step is to evaluate against **real** cases
and expect the accuracy to fall a long way - that fall is the measurement, not
a regression.

MIMIC-IV is the strongest real option (364,627 patients) but needs PhysioNet
credentialing plus a CITI human-subjects course. That is days of process, not a
download, and it is ICU/ED-focused - the patient is already in hospital, which
is the wrong population for a pre-hospital triage tool.

## Reproduce

    python3 learning_curve.py      # saturation at n=2,500
    python3 dataset_structure.py   # the 99.44% lookup ceiling
