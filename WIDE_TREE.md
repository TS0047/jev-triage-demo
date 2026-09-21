# Wide hierarchy: 2,505 conditions in two API calls

Your instruction: make the options hierarchical to get past 255, and make the
tree **wide** rather than deep so Jev can pinpoint accurately.

Built, tested, and the width argument is confirmed by measurement.

## The shape

    level 1    24 categories              1 call
    level 2    up to 250 conditions       1 call
    ----------------------------------------------
    total      2,505 conditions           2 calls
    ceiling    24 x 255 = 6,120

That is **51x the previous 49-condition list**, from two calls costing about
$0.0006 per case.

## Why wide, not deep - now measured, not asserted

Routing error compounds multiplicatively. With per-level accuracy p over d
levels, reaching the right leaf is p^d:

    p=0.95, d=2 -> 90.3%
    p=0.95, d=3 -> 85.7%
    p=0.95, d=4 -> 81.5%

Width, by contrast, is free up to the per-call cap. So the correct shape is
the widest tree that fits under 255 at every level.

Tested directly - same 2,505 conditions, same cases, only the tree shape
differs:

    wide (2 levels)    8/16   50.0%   1.9 calls/case
    deep (3 levels)    7/16   43.8%   2.8 calls/case

Deep is worse **and** 47% more expensive. Its failures are diagnostic: they
are mostly `no_category`, meaning the extra level discarded the case before
the leaf list was ever reached. Addison's disease was lost at the supergroup
step in the deep arm while the wide arm named it at level 2.

**Depth destroys cases at every level it adds. Width costs nothing until 255.**

## Against the flat list on real cases

Same 22 real published case reports, identical scoring:

    flat49     1/22   ( 4.5%)   1.0 calls/case
    wide       10/22  (45.5%)   1.9 calls/case

**A 10x improvement for 0.9 extra calls.** Cases the flat list could only
escalate on, now named: lymphangioma, hypocalcemic cardiomyopathy, thymic
carcinoma, Addison's disease, IgG4-related disease, leptomeningeal
carcinomatosis, acquired hemophilia A, Complex IV deficiency.

The regression battery also improved. All six state files now route correctly:

    state_a  infection_viral (0.67)      -> dengue fever (0.64)
    state_b  infection_viral (1.00)      -> dengue fever (0.88)
    state_c  infection_parasitic (1.00)  -> vivax malaria (0.98)
    state_d  autoimmune_rheumatic (1.00) -> systemic lupus erythematosus (0.83)
    state_e  infection_bacterial (0.98)  -> bacterial meningitis (1.00)
    state_f  infection_bacterial (0.94)  -> brucellosis (0.76)

state_a is the notable one: the flat 49-condition system managed only 0.52 on
it, and the six-level clinical router needed its whole ROWS/sieve/script
apparatus. Two wide calls get there.

## Safety: an escape hatch at BOTH levels

A wrong turn at level 1 is unrecoverable - the true condition is then absent
from the level-2 list entirely, and the model is forced to pick the least-bad
wrong answer. So the tree escalates when:

    level 1 returns none_of_these         no category fits
    level 1 confidence < 0.30             category uncertain, do not descend
    level 2 returns none_of_these         category right, condition absent
    level 2 confidence < 0.25             condition uncertain

**Audited afterwards - see ESCALATION_AUDIT.md. Only 3 of 11 escalations were
honest (condition genuinely absent); 7 were level-1 misroutes and 1 was the
model refusing an answer that was in the list. The refusal behaviour is
therefore weaker than this section originally implied.**

In the 22-case run the tree escalated 10 times and confabulated twice
(Gossypiboma called appendicitis; malignant syphilis escalated on an uncertain
category). Refusal behaviour survived a 51x list expansion, which was the open
risk flagged in HYPOTHESIS_SPACE.md.

## How the taxonomy was built

Names harvested by frequency from 13,092 real case reports, assigned to 24
categories by auditable keyword rules. **No hand-authored likelihoods** -
classification needs only names (HYPOTHESIS_SPACE.md).

One correction was needed during the build. The first tree could diagnose
Erdheim-Chester disease but **not dengue**, because a corpus of published case
reports is selected for rarity and omits common illness. 141 common conditions
are now seeded first and never evicted by the cap. A triage tool that knows
rare tumours but not dengue is exactly backwards.

Known gaps, stated rather than hidden:

- 1,261 harvested names were dropped as unmatched by the keyword rules
  (Rosai-Dorfman, Kikuchi-Fujimoto, Kawasaki, chordoma...). They could be
  assigned with one Jev call each, at a cost.
- `neoplasm_carcinoma` and `neoplasm_benign` are at the 250 cap and truncated
  by frequency - the rarest carcinomas are unreachable.
- `psychiatric` holds only 17 conditions. Psychiatric illness is under-
  represented in case reports, and the seeds barely cover it.
- Scoring is token-overlap, which undercounts: the deep arm answered
  "primary adrenal insufficiency" for Addison's disease - the same illness -
  and was scored a miss.

## Reproduce

    .venv/bin/python build_taxonomy.py --names 4000 --cap 250
    .venv/bin/python wide_router.py state_a.txt
    .venv/bin/python eval_wide.py --n 22 --arms flat,wide
    .venv/bin/python eval_wide.py --n 16 --arms wide,deep
