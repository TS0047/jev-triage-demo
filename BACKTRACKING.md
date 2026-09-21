# Overlapping categories + backtracking with exclusion

Your two proposals, built and measured:

1. **Overlapping lists** - a condition filed under every category it could be
   reached from.
2. **Reverse traversal** - when level 2 finds nothing, go back to level 1 and
   pick a different branch, with the failed category removed so it cannot be
   chosen again.

Plus the corollary you drew: **"the disease doesn't exist" belongs at level
1**, because only level 1 can see the whole space.

## The semantic fix, which turned out to be the important one

The old router conflated two very different level-2 outcomes under one label:

    L2 none_of_these  ->  reported as an escalation

But level 2 sees one category of ~250 conditions. From inside it, it cannot
distinguish *"this disease is not in our system"* from *"you brought me to the
wrong shelf"*. Reporting both as escalation is why the audit found 7 of 11
"honest refusals" were really misroutes.

Now they are separate signals:

    L1 not_in_this_system  ->  ESCALATE. Level 1 saw all 24 categories and
                               declined. This is the only place that claim
                               can honestly be made.
    L2 wrong_branch        ->  BACKTRACK. A routing signal, not a refusal.

Exactly your point: the escape hatch belongs where the whole hypothesis space
is visible.

## Overlap: 0.3% -> 40.8%

    conditions                     2,498
    reachable from >1 category     7  ->  1,020   (0.3% -> 40.8%)
    single points of failure       2,491 -> 1,478
    unreachable conditions         0

Cross-filing is driven by *presentation* cues, not pathology: anything named
for an organ is reachable from that organ's category as well as its mechanism
category. Ocular cysticercosis now lives in both `infection_parasitic` and
`ophthalmic_ent`, which is the mosquito-vector case you described - the same
disease reachable from two honest directions.

Six categories exceeded the 250 cap after cross-filing and were trimmed, but
only by dropping entries that remain reachable elsewhere. Zero conditions
became unreachable.

## Backtracking works mechanically

Exclusion holds and there are no loops:

    Cysticercosis
      [try 1] L1 -> ophthalmic_ent (0.36)      L2 -> wrong_branch
      [try 2] L1 -> infection_bacterial (0.38) L2 -> wrong_branch
      [try 3] L1 -> neoplasm_benign (0.42)     L2 -> cystic lymphangioma (0.17)

Each retry excludes the previous category, so the model cannot re-pick its
favourite and spin.

## Results: 22 real cases

    arm           hit         escalated  confabulated  calls/case  backtracks
    multi+bt      10/22 45.5%     9           3           3.4          21
    multi only    10/22 45.5%    10           2           2.0           9
    single+bt     10/22 45.5%     5           7           3.3          17

**Accuracy is identical across all three. That is the honest headline.**

What changes is the safety profile, and there the result is clear:

    single-label + backtracking   7 confabulations
    multi-label + backtracking    3 confabulations

Backtracking on a *single-label* taxonomy is actively dangerous: with the right
category excluded by an earlier wrong turn, the model is pushed into a branch
that cannot contain the answer, and it commits to something wrong rather than
refusing. **Backtracking without overlap converts refusals into confident
errors.** The two ideas are not independent - overlap makes backtracking safe.

## Escalation honesty improved, but less than hoped

    before (single-label, L2 escalation)   3/11 honest
    after  (multi-label, L1-only)          4/11 honest

The bigger change is qualitative. Previously `none_of_these` fired on the first
guess. Now `not_in_this_system` fires only after the model has been walked
through two or three categories and rejected each - Gossypiboma escalated after
2 backtracks, Cysticercosis after 3. The refusals are *earned* now, even when
the answer technically existed somewhere in the tree.

## Where it still fails, honestly

Cysticercosis is the clearest remaining failure and worth stating plainly: the
condition IS cross-filed into `ophthalmic_ent`, level 1 DID choose
`ophthalmic_ent` first, and level 2 still returned `wrong_branch` from a
182-option list containing it. That is the same level-2 blindness that lost
Addison's disease in the previous audit - not a taxonomy problem, and not one
backtracking can fix.

Three cases were also lost that the non-backtracking arm got right (Thymic
carcinoma, epithelioid haemangioma, Primary mediastinal DLBCL): a borderline
first answer was rejected, and the retry landed somewhere worse. **Backtracking
can turn a marginal hit into a miss.**

Cost roughly doubles: 2.0 -> 3.4 calls per case, ~$0.001 per consultation.

## Verdict

    overlapping lists    keep - strictly better, free at query time, and it
                         makes backtracking safe rather than dangerous
    backtracking         marginal on accuracy, costs 70% more calls, and
                         earns the refusals it does make. Worth it only with
                         overlap in place.

The unresolved problem is level-2 blindness: the model refusing an answer that
is sitting in the list in front of it. Neither of these two ideas addresses
that, and it is now the dominant failure mode.

## Reproduce

    .venv/bin/python build_multilabel.py
    .venv/bin/python backtrack_router.py state_a.txt
    .venv/bin/python backtrack_router.py state_a.txt --single   # no overlap
