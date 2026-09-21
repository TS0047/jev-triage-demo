# Scaling the option set: measured limits

Question: the disease list is a flat set of options. What happens at 2000?

Everything below is measured against the live API, not reasoned about.
Reproduce with `scaling_probe.py`, `scaling_probe2.py`, `scaling_probe3.py`.

## 1. There is a hard ceiling at 255

    n=400  HTTP 400: {"detail":"Too many choices. Must have at most 255 choices."}

So 2000 is not a design question, it is rejected by the API. The ceiling is
255 options per `choice` question, `other` included.

## 2. On a DECISIVE state, size costs nothing

`state_b.txt` (NS1 positive, platelets 62k falling). Ground truth is dengue at
every size, so any drift is pure scaling damage:

    options   choice   conf    p(dengue)  rank   input tokens
      7       dengue   1.000   1.000      1        938
     25       dengue   1.000   1.000      1       1282
     50       dengue   1.000   1.000      1       1774
    100       dengue   1.000   1.000      1       2792
    200       dengue   1.000   1.000      1       4802

No degradation at all, even with 194 acute-febrile distractors that overlap
dengue clinically. Hard evidence pins the answer regardless of list length.

## 3. On an AMBIGUOUS state, confidence decays measurably

`state_a.txt` (day-5 fever, no vitals, nothing tested). This is where the
posterior is genuinely spread and scaling damage shows:

    options   choice   conf    p(dengue)  mass on the 6 real   leak to distractors
      7       dengue   0.650   0.70       0.970                0.000
     25       dengue   0.730   0.75       0.980                0.010
     50       dengue   0.740   0.75       1.000                0.000
    100       dengue   0.630   0.65       0.980                0.020
    200       dengue   0.570   0.58       0.960                0.040
    255       dengue   0.450   0.46       0.930                0.070

Confidence falls 0.65 -> 0.45 and leak to distractors rises 0.000 -> 0.070.

**But the ranking is stable.** dengue > scrub_typhus > typhoid >
leptospirosis > malaria at every size. The model is not confused about the
differential; it is spreading mass thinner over more plausible-sounding
options. That is arguably correct behaviour - with 255 candidates on thin
evidence, 0.46 is more honest than 0.70.

This matters for the loop because **EIG is computed from entropy**. Entropy
rose 1.50 -> 2.19 bits purely from list size, which changes which question
looks most informative. The question-selection layer is more sensitive to
option-set size than the diagnosis itself.

## 4. The escape hatch survives - the real safety result

`state_d.txt` (lupus), with all lupus-like options removed so `other` is the
only correct answer:

    options   choice   conf    p(other)   escalates
      7       other    1.00    1.000      yes
     25       other    1.00    1.000      yes
    100       other    0.99    1.000      yes
    255       other    0.86    0.870      yes

Still correct at 255, with 249 wrong options competing. And when lupus IS in
the list, it picks `sle_flare` at 1.00 every time and `other` drops to 0.000 -
so `other` is not a dumping ground, it is used only when genuinely nothing
fits.

## 5. Noul wording matters more than option count

A real finding from this probe. Same lupus state, same question, two wordings:

    "Does this presentation lie outside the listed conditions?"        0.25 - 0.30
    "...OUTSIDE the differential of acute tropical febrile illness
     (dengue, malaria, typhoid, leptospirosis, scrub typhus,
     influenza)?" + named outside categories in the criteria            0.95

The generic wording scores below the 0.60 escalation threshold - it would
have failed to escalate. Naming the in-scope conditions explicitly, and
giving concrete examples of what "outside" means, more than triples the
signal. **Prompt specificity beats option-set engineering.**

## What this implies for scaling to a real differential

A 2000-disease flat list is impossible (255 cap) and would be the wrong shape
anyway. The right architecture is hierarchical:

    1. One `choice` over ~10-20 SYNDROME groups
       (acute febrile, respiratory, abdominal-surgical, autoimmune,
        haematological, neurological, ...) - each with an `other`
    2. Route to a second `choice` over the ~20-40 conditions in the winning
       group - again with an `other`
    3. Escape at either level escalates

Two calls instead of one, each with a small well-separated option set, and
every level retains its escape hatch. Cost is ~2x a single call, which is
still under $0.0002. The flat bank in this repo is correct for one syndrome;
it should not be stretched to cover medicine.
