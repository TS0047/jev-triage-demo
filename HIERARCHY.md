# Hierarchical routing: clinical basis and measured results

Companion to SCALING.md, which established that a flat `choice` is capped at
255 options and loses confidence as it grows on ambiguous states.

## What doctors actually use

The hierarchy clinicians use is **not a disease taxonomy**. Nobody ranks 2000
diseases and nobody walks an ICD tree. Six mechanisms, in application order:

1. **ROWS - "rule out worst-case scenario", worst first.** The first cut is by
   *danger*, not probability: exclude meningitis before considering the commoner
   viral fever. Deliberately anti-Bayesian - you chase the lethal tail first.
2. **Problem representation with semantic qualifiers** (Bordage). Compress the
   story into abstract, usually binary axes *before* naming any disease:
   acute/chronic, localised/diffuse, febrile/afebrile, immunocompetent/
   immunosuppressed.
3. **Syndrome routing.** That abstraction selects a *syndrome group* - acute
   undifferentiated fever, acute respiratory, acute abdomen - not a disease.
4. **The surgical sieve** (VINDICATE / MAGIC HAT PIN). Within the syndrome,
   enumerate by *mechanism*: vascular, infective, neoplastic, autoimmune,
   metabolic, toxic, structural, degenerative.
5. **Illness scripts.** Each candidate carries epidemiology, incubation and
   time course.
6. **Pivot and cluster.** Pick one discriminating pivot; cluster the few
   candidates it separates.

**The structurally important part: syndrome and sieve are orthogonal axes, not
a tree.** It is a grid. You land in a *cell* (acute febrile x infective) holding
~15-30 conditions - inside the 255 cap and inside the range where no
degradation was measured.

Incubation acts as a **hard gate**, not a reweighting: an exposure 60 days ago
excludes a 4-10 day incubation disease outright.

## Implementation

`hierarchical_router.py` implements all six levels, each with its own escape
hatch (`none_of_these`). An escape at any level escalates rather than forcing
a leaf.

    L0  ROWS red flags       1 call, before any differential reasoning
    L1  semantic qualifiers  tempo / febrile / localisation / host
    L2  syndrome             12 options
    L3  surgical sieve       mechanisms available in that syndrome
    L5  epidemiological gate hard exclusion by incubation vs days ill
    L4  condition            named conditions in the (syndrome, mechanism) cell

## Head-to-head, six states, same API, same day

The flat arm was given the **best possible** flat setup - the full 255-option
list, the largest the API allows - so this is not a straw man.

    state     truth           flat255                      hierarchical
    state_a   dengue          dengue (0.52)                dengue (0.78)
    state_b   dengue          dengue (1.00)                dengue (1.00)
    state_c   malaria         malaria (1.00)               malaria (1.00)
    state_d   sle_flare       sle_flare (1.00)             sle_flare (0.99)
    state_e   EMERGENCY       bacterial_meningitis (1.00)  ESCALATED: red_flags
    state_f   brucellosis     brucellosis (0.95)           brucellosis (0.79)

    total cost   flat $0.00832   hierarchical $0.00287   (0.3x - hierarchy is CHEAPER)

## The honest read

**Accuracy is a tie.** Both arms named the right condition on all five
diagnosable states. The hypothesis that a flat 255-list would produce wrong
answers was not supported - it produced *less confident* answers on ambiguous
input (state_a 0.52 vs 0.78) but never a wrong one. Anyone claiming hierarchy
"fixes accuracy" here would be overselling it.

What hierarchy actually buys:

1. **It removes the 255 ceiling.** 12 syndromes x 8 mechanisms x ~30
   conditions addresses ~2880 conditions with no level exceeding 30 options.
   This is the real answer to "what if the list were 2000".
2. **It is 2.9x cheaper.** $0.00287 vs $0.00832 for six states, because the
   leaf call carries ~25 options instead of 255. More levels, far fewer tokens.
3. **Sharper on ambiguous input.** state_a: 0.78 vs 0.52. Mass is not diluted
   across 249 irrelevant options.
4. **It produces an auditable path.** `musculoskeletal >
   autoimmune_inflammatory > sle_flare` can be inspected and disputed at each
   step. The flat arm produces a label with no reasoning trace - and for a
   clinical tool, a wrong answer you can audit beats a right answer you cannot.
5. **Danger is handled before diagnosis.** state_e stopped at L0 in 1 call and
   $0.00011 - 13x cheaper than the flat arm and far faster.

### Where the flat arm was arguably better

On state_e the flat list **named** `bacterial_meningitis` at 1.00, while the
hierarchy escalated on red flags without naming anything. For a triage tool the
escalation is the correct action - the patient needs an ambulance, not a label -
but it is a real trade-off, not a clean win. A production system should report
both: escalate AND carry the leading hypothesis forward.

### The failure this exposed

First run, state_d escalated with `no_sieve_content_for_musculoskeletal`. That
looked like a pass but was an **authoring gap, not reasoning** - the routing was
correct and the grid cell was simply empty. A hierarchy fails differently from a
flat list: a flat list gives a wrong answer, a hierarchy silently dead-ends in
an unpopulated cell. **Every reachable (syndrome, mechanism) cell must be
populated or explicitly marked unsupported**, otherwise coverage gaps masquerade
as safe escalations.

After filling the cell, state_d routed to `musculoskeletal >
autoimmune_inflammatory > sle_flare` at 0.99 - the flat system's best possible
answer was "other, escalate", so this is the one case where hierarchy is
strictly more informative.

## Reproduce

    python3 hierarchical_router.py state_d.txt
    python3 compare_arms.py
