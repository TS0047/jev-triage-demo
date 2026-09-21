# Nothing here is trained. So why does the option list matter so much?

The question: *"we are not training this right? we are literally just giving
it the option, why does it matter that much?"*

Correct on the premise, and it exposes an overstatement of mine that is now
corrected below.

## Confirmed: nothing is trained

    $ grep -rInE "\.fit\(|backward\(|optimizer|gradient|torch|sklearn" *.py

The only hits are `learning_curve.py` and `noise_sensitivity.py`, both calling
a local counting function in offline experiments that never touch the live
system. Jev is frozen behind an HTTP API. No weights are updated, ever.

## Why the list matters anyway: it is the sample space, not a hint

A `choice` call returns a probability distribution **over the options you
supply**. It is constrained to sum to 1 across that set. So a condition absent
from the list does not get a low score - it has no score, and cannot be
returned no matter how obvious the case.

`hypothesis_space.py`, same case, same frozen model, nothing in between:

    case: lymphangioma

    list WITHOUT the truth (49 options)
      -> outside_differential   conf 1.00

    list WITH the truth (50 options)
      -> lymphangioma           conf 1.00

Confidence 1.00 in both directions. The model was never uncertain and never
learned anything. The first answer was right *given what it was allowed to
say*. The list is not a prompt-engineering nicety - it defines what answers
exist.

This is why the earlier experiment rescued 8/12 cases by adding a name. Not
teaching, not fine-tuning. Making the answer representable.

## The correction this forced

BOTTLENECK.md claimed adding 2,000 diseases would require ~450,000
hand-authored likelihood cells. **That was wrong**, and it conflated two
components with different data requirements.

    classification        needs ONLY the option names
                          (one Jev call; the model supplies the knowledge)

    question selection    needs P(finding | disease) for expected information
                          gain (triage_loop.py) - this is what the 450,000
                          cells were about

Measured directly - a list of the top-200 diagnoses by corpus frequency, names
harvested from data, **zero authored likelihoods**, against real cases whose
truth lies outside our 49:

    our 49 conditions        0/14
    top-200 names, no matrix 6/14

    lymphangioma                  -> HIT
    IgG4-related disease          -> HIT
    Brown tumor                   -> HIT
    Kaposi sarcoma                -> HIT
    Langerhans cell histiocytosis -> HIT
    tuberculous osteomyelitis     -> HIT

And 6/14 understates it. "Hydatid cyst" was answered `echinococcosis` - the
same disease under its other name - and scored as a miss by exact-string
matching. Others are near misses of genuine clinical difficulty: Gossypiboma
(retained surgical sponge) answered `appendicitis`, schwannoma answered
`pleomorphic adenoma`.

## What this changes about the project

Growing the disease list is **much cheaper than I said**. Names can be
harvested from any diagnosis frequency table - no clinical authoring, no
epidemiological data, no matrix. The genuine constraints that survive:

1. **The 255-option API cap** (SCALING.md) - still hard, still the reason the
   hierarchical grid exists.
2. **Entropy grows with list length** (scaling_probe2.py) - 1.50 to 2.19 bits
   from list size alone, which degrades EIG question selection even when the
   ranking is unchanged.
3. **The question loop still needs likelihoods** - and for tail diseases seen
   once, those cannot be estimated. A 2,000-condition *classifier* is cheap; a
   2,000-condition *adaptive interviewer* is not.
4. **More options means more confident wrong answers available.** The escape
   hatch is what holds the safety line, and its 94% refusal rate was measured
   against 49 options, not 200. That number would need re-measuring.

## The honest reframe

The system is not a trained diagnostic model. It is a **frozen reasoner plus a
hypothesis space we control**. Almost everything this project has built -
grids, escape hatches, syndrome routing - is machinery for deciding *which
options to put in front of it*, because that is the only lever we actually
have.

Seen that way, "we are literally just giving it the option" is not a
limitation of the approach. It **is** the approach.

## Reproduce

    .venv/bin/python hypothesis_space.py --part a   # list as sample space
    .venv/bin/python hypothesis_space.py --part b   # names-only expansion
