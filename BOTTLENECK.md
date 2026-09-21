# Is the problem too few diseases, or too little data?

Your question: *"we don't have enough data or labels to pin the disease - the
diseases we have is less?"*

It splits into two claims. One is measurably false. The other is true but does
not have the fix it appears to have.

## Claim 1: "not enough data" - FALSE, measurably

Already settled by `learning_curve.py`: the likelihood matrix saturates at
2,500 patients and we have 1,292,579 available.

    n=250      77.7%
    n=2,500    99.1%
    n=131,529  99.3%

More data buys 0.2pp. Data volume is not the constraint for the diseases we
already model.

## Claim 2: "too few diseases" - TRUE, and it is the real one

`coverage_curve.py` over 13,092 real case reports:

    a list of    49 conditions covers  10.9% of real cases
    a list of   100 conditions covers  16.2%
    a list of   250 conditions covers  25.6%
    a list of   500 conditions covers  34.9%
    a list of 1,000 conditions covers  46.3%

So yes - 49 is why 96.5% of real cases fell out of scope.

### But the benchmark is publication-biased, and the check proves it

**26 of our 49 conditions never appear once in that corpus.** No panic attack,
no viral pharyngitis, no stable angina, no whooping cough. Its top diagnoses
are schwannoma, hydatid cyst, actinomycosis, angiosarcoma.

Journals publish cases *because* they are unusual. Nobody publishes "patient
had a cold". So 10.9% coverage measures **rarity of the corpus**, not
inadequacy of the list. Against a primary-care population the same 49
conditions cover 100% by construction, and the top 20 alone account for 60.5%
of patients.

Both numbers are real. They answer different questions.

## The test that settles what is actually broken

If the list is the bottleneck, then *adding the true diagnosis to the options*
should rescue the case. If reasoning is the bottleneck, it will not. Run on 12
real out-of-scope cases:

    HIT  lymphangioma                    -> lymphangioma                  1.00
    HIT  malignant syphilis              -> malignant syphilis            0.53
    HIT  hypocalcemic cardiomyopathy     -> hypocalcemic cardiomyopathy   0.96
    HIT  renal arteriovenous malformation-> renal arteriovenous malform.  0.89
    MISS Complex IV deficiency           -> outside_differential          0.70
    HIT  Thymic carcinoma                -> Thymic carcinoma              0.79
    HIT  Gossypiboma                     -> Gossypiboma                   0.61
    HIT  atlanto-occipital assimilation  -> atlanto-occipital assimilation 0.97
    HIT  Addison disease                 -> Addison disease               0.99
    MISS diffuse large B-cell lymphoma   -> outside_differential          0.94
    MISS Addison's disease               -> outside_differential          0.62
    MISS Pyoderma gangrenosum            -> outside_differential          0.59

    rescued by list extension: 8/12 (67%)

**This is the key result.** The model diagnosed Gossypiboma - a retained
surgical sponge - correctly, having never been trained on it by us, purely
because the name was in the list. The reasoning was never the limit. **The
list was.**

Note the same case appears twice with different outcomes ("Addison disease"
HIT at 0.99, "Addison's disease" MISS) - two different patients, and the
apostrophe variant is a different case report. Rare-disease performance is
unstable, which is itself informative.

## So why not just add 2,000 diseases?

Three measured reasons.

**1. The API caps `choice` at 255 options** (SCALING.md). A flat list cannot
go past it. The hierarchical grid is the workaround: 12 syndromes x 8
mechanisms x ~30 conditions = ~2,880 addressable with no level over 30.

**2. Coverage is Zipf-shaped - the treadmill is real.**

    list size    coverage    cost of the next +10pp
           49       45.8%
          100       53.0%    51 more conditions
          255       62.5%    155 more
          500       69.4%    245 more
        1,000       76.5%    500 more
        5,000       92.9%    2,500 more

Every fixed gain costs exponentially more conditions.

**3. Each added condition needs likelihoods, and wrong ones are worse than
none.** From `noise_sensitivity.py`: flipping the *direction* of 5% of cells
drops accuracy 99.3% -> 46.5%. Hand-authoring 2,000 diseases means ~450,000
cells authored without data. At even a 5% direction-error rate that is a
system worse than the 49-condition one.

And the data to do it properly does not exist: **74% of real diagnoses appear
exactly once.** You cannot estimate P(finding | disease) from a single case, at
any list length. *That* is the real data bottleneck - not total volume, but
cases per disease in the tail.

## The honest summary

    "not enough data"        false for what we model (saturated at 2,500)
                             true for the tail (74% singletons - unfixable
                             by downloading more)

    "too few diseases"       true, and the binding constraint: 8/12 real
                             cases were rescued by adding the name alone

    "so add more diseases"   right direction, wrong magnitude. 255 is a hard
                             API cap; Zipf makes each increment cost more;
                             and unlabelled hand-authored likelihoods are
                             actively dangerous when the direction is wrong.

The defensible move is **more conditions where real labelled data exists, via
the hierarchical grid to beat the 255 cap, and escalation for the tail** - not
because escalation is a cop-out, but because for a disease seen once in 13,092
cases, "this needs a clinician" is the correct clinical answer.

## Reproduce

    .venv/bin/python coverage_curve.py    # coverage curve + publication bias
    .venv/bin/python shape_of_problem.py  # Zipf treadmill + which bottleneck
