# Were the escalations honest?

Your question: when the tree escalated, was the disease genuinely missing, or
was it sitting in the taxonomy somewhere and we failed to reach it?

Audited all 11 escalations from the 22-case run. The answer is unflattering.

## Result

    honest escalation (condition truly absent)      3/11
    L1 misroute (condition existed, wrong branch)   7/11
    L2 blind (right branch, condition in the list,
              model still refused)                  1/11

**Only 3 of 11 escalations were honest.** The other 8 were routing failures
wearing a safety costume - the system said "I cannot diagnose this" when the
answer was in the tree the whole time.

That materially changes the earlier claim. "11 escalations, 1 confabulation"
sounded like a system that knows its limits. It is really a system that
mostly knows its limits for 3 cases and got lost for 8.

## The 8 failures, individually

    malignant syphilis          L1 chose infection_bacterial; filed under neoplasm_carcinoma
    diffuse large B-cell lymph  L1 chose neoplasm_sarcoma; filed under neoplasm_lymphoid
    Pyoderma gangrenosum        L1 chose iatrogenic_toxic; filed under dermatological
    Cysticercosis               L1 chose ophthalmic_ent; filed under infection_parasitic
    Primary mediastinal DLBCL   L1 chose neoplasm_carcinoma; filed under neoplasm_lymphoid
    Warty dyskeratoma           L1 chose ophthalmic_ent; filed under dermatological
    adenomatoid odontogenic tu  L1 chose ophthalmic_ent; filed under neoplasm_benign
    Addison's disease           L1 chose endocrine_metabolic CORRECTLY, the
                                condition was in the 113-option list, L2 still
                                refused  <- the model, not the taxonomy

## Most of these are the taxonomy's fault, not the routing's

Read the misroutes closely and Jev is mostly right and the filing is wrong:

- **malignant syphilis** is an infection. The keyword rules saw "malignant"
  and filed it under carcinoma. Jev chose `infection_bacterial` - correct
  medicine, wrong shelf.
- **Cysticercosis**: the case was *ocular* cysticercosis. Jev chose
  `ophthalmic_ent`, which is where an eye presentation belongs. The parasite
  was filed by organism, the patient presented by organ.
- **adenomatoid odontogenic tumor** is a jaw tumour. Jev chose
  `ophthalmic_ent` (which holds dental); it was filed under `neoplasm_benign`.

Same disease, two defensible categories. **Single-category descent forces a
choice the medicine does not support**, and a wrong turn at level 1 is
unrecoverable because the true condition is then absent from the level-2 list
entirely.

The one genuine model failure is Addison's disease: right category, condition
present in the list, and level 2 still returned `none_of_these`.

## The obvious fix, and why it did not work

Descend into the top-2 categories and pool the candidates, so a single L1 slip
is survivable:

    single-category descent   10/22  (45.5%)   1 confabulation
    top-2 pooled descent       9/22  (40.9%)   2 confabulations

**Worse, not better.** Pooling two categories doubles the option list, which
dilutes the posterior - the same confidence decay measured in
scaling_probe2.py (0.650 -> 0.450 as options grow). Cases that previously
cleared the 0.25 threshold now fell under it and escalated as
`condition_uncertain`. Three previously-correct answers were lost
(Complex IV deficiency, Addison disease, leptomeningeal carcinomatosis
survived, but malignant syphilis and DLBCL still failed on confidence).

Recorded as a negative result rather than quietly dropped: **more options at
the leaf is not free, and top-K descent trades a routing error for a
confidence error.**

## What would actually fix it

Ordered by expected value, none of them yet done:

1. **Fix the filing, not the router.** Multi-label categories - let a
   condition live in every category a clinician might route it from
   (`cysticercosis` in both `infection_parasitic` and `ophthalmic_ent`). This
   is the same fragility fix already applied to the small clinical grid, where
   17 single-entry pathologies became 12. It costs nothing at query time.
2. **Keyword rules are too crude.** "malignant syphilis" filed as a carcinoma
   is a lexical accident. Assigning the 4,000 harvested names with one Jev
   call each would cost ~$0.28 once and remove this whole error class.
3. **Re-check the L2 threshold.** Addison's was the only true model failure,
   and 0.25 may be too aggressive when the list is long.

## Honest revised numbers

    reported earlier    10/22 hit, 11 escalated, 1 confabulated
    after audit         10/22 hit,  3 honest escalations,
                         8 routing failures, 1 confabulated

The headline 45.5% is unchanged - those were real hits. What changed is the
interpretation of the misses: they are mostly fixable engineering, not the
system correctly recognising its limits. That is better news for the ceiling
and worse news for the current build.

## Reproduce

    .venv/bin/python audit_escalations.py
