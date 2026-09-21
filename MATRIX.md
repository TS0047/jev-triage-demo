# Discrimination matrices: how they are populated, and how to do better

Answering three questions with measurements, not opinion:
how are the current values set, what is the principled alternative, and is
there a role for RL.

## 1. How the current values were populated

Badly, and by hand. `findings_bank.json` holds 25 findings x 6 diseases. Every
number in it was typed by me in one sitting from clinical knowledge, with no
data behind it. The distribution gives it away:

    20 distinct values across the whole matrix
    most common: 0.10 (x34), 0.15 (x18), 0.20 (x17), 0.05 (x13)

That is the signature of a human reaching for round numbers, not of anything
estimated. The README already says these are "plausible, not sourced" - this
file quantifies what that costs.

## 2. The principled alternative: count, do not guess

This is **not** a reinforcement learning problem. It is density estimation, and
it has a closed-form maximum-likelihood solution:

    P(e | d) = (count(e, d) + a) / (count(d) + 2a)        Jeffreys, a = 0.5

One pass over labelled data gives the optimal estimate for that sample. No
gradients, no reward, no exploration. `learn_likelihoods_v2.py` does this over
134,529 DDXPlus patients, 49 pathologies, 223 evidences.

### Held-out test: does it actually matter?

`compare_matrices.py` fits on 60,000 patients and scores on 3,000 disjoint
ones, using naive Bayes over the matrix alone - no API, so this isolates the
quality of the numbers from everything else.

    matrix                        top-1    top-3    top-5
    uniform (no information)       6.9%    19.1%    24.1%
    handish (0.05 grid)           99.1%   100.0%   100.0%
    handish (0.10 grid)           98.9%   100.0%   100.0%
    learned (MLE + Jeffreys)      99.4%   100.0%   100.0%

Learned wins, but **rounding every value to a 0.05 grid costs only 0.3pp**.
The exact decimals barely matter.

## 3. What actually matters: direction, not precision

`noise_sensitivity.py` corrupts the learned matrix two ways - *swap* (replace a
cell with another disease's plausible value) and *flip* (replace P with 1-P,
i.e. assert the opposite of the truth):

    corruption              top-1    top-5
    none (learned)          99.3%   100.0%
    swap  5% of cells       97.8%   100.0%
    swap 20% of cells       87.2%    99.3%
    flip  2% of cells       78.5%    96.0%
    flip  5% of cells       46.5%    74.1%
    flip 10% of cells       12.1%    51.6%
    flip 20% of cells        0.0%    27.9%

**Flipping 5% of cells destroys the system: 99.3% -> 46.5%.** Rounding every
cell costs 0.3pp.

The practical rule that falls out: *get the sign right and stop agonising over
the second decimal*. Hand-authoring fails when it asserts a finding favours a
disease it does not - not when it says 0.6 instead of 0.55. Review effort
belongs on direction, not on precision.

## 4. A trap in learning from data: conditional questions

The first estimator ranked "What colour is the rash?" as the most informative
question in medicine (MI 0.72). It is not - it is a **sub-question**, recorded
only when "do you have any skin lesions?" was already positive. Counting it
over all patients makes it look deterministic.

The fix is to estimate each evidence only over patients for whom it was
*applicable*, and report applicability separately:

    evidence  raw MI   applicability-weighted   question
    E_130     0.6793   0.1145                   What colour is the rash?
    E_53      0.6914   0.6914                   Do you have pain somewhere?
    E_129     0.6078   0.6078                   Any lesions or skin problems?
    E_201     0.5257   0.5257                   Do you have a cough?
    E_91      0.4420   0.4420                   Do you have a fever?

After correction the top of the list is pain, skin lesions, cough, fever,
breathlessness - clinically sensible.

**A second-order lesson, learned the hard way.** The first attempt *inferred*
the question tree from co-occurrence: "if presence(child) is a subset of
presence(parent), it is conditional". That silently produced garbage, because
`E_204` (travel history) is recorded for 100% of patients and is therefore
trivially a superset of everything - it became the declared parent of all 203
other evidences. DDXPlus states the real structure explicitly in
`release_evidences.json` under `code_question`. **Do not infer what the data
already tells you.**

## 5. So where could RL legitimately fit?

Not in the matrix. The matrix is supervised estimation with a closed form;
using RL there would be a slower route to a worse version of the same answer.

RL has one defensible target in this system: **the question-selection policy**,
not the likelihoods. Selecting the next question is a sequential decision
problem with a real cost structure:

    state    the current posterior + which questions have been asked
    action   which question to ask next, or stop and commit, or escalate
    reward   -c per question asked
             +1 correct commit, large negative for a wrong commit
             small negative for escalating a case that was answerable
             VERY large negative for committing on a case needing escalation

Greedy expected-information-gain - what this repo does now - is myopic. It
picks the single best next question, which is not the best *sequence*. A policy
could learn that asking a cheap low-yield question first unlocks a decisive
one, which EIG cannot see one step ahead. That is a genuine sequential-decision
gain, and DDXPlus is a usable simulator because it contains full evidence sets
per patient, so an agent can "ask" any question and get that patient's true
answer.

Honest caveat: greedy EIG is a strong baseline and usually close to optimal for
tree-structured diagnosis. Expect single-digit improvement in questions asked,
not a transformation. Do the supervised estimation first - it is a one-pass
count that moved accuracy far more than any policy will.

### The ordering that follows from the measurements

1. Fix directions in the hand-authored bank (biggest win by far)
2. Replace values with counts wherever labelled data exists
3. Weight by applicability so conditional questions rank honestly
4. Only then consider a learned question-selection policy
5. RL on the likelihoods themselves: never

## 6. What none of this fixes

The calibration problem measured in DATASETS.md - the 0.6-0.8 confidence band
scoring 0/7 - is a property of the model's reported confidence, not of the
matrix. Better likelihoods give better rankings; they do not make a stated
0.7 mean 70%. That needs post-hoc calibration (Platt scaling or isotonic
regression on held-out data), which is a separate piece of work.

Also: DDXPlus is synthesised by a rule-based system. 99.4% means the matrix
recovered that generator almost exactly. Real clinical data is noisier, the
conditional-independence assumption is false there, and these numbers would
drop. The *relative* findings - direction beats precision, applicability
matters, counting beats guessing - are what transfer.

## Reproduce

    python3 learn_likelihoods_v2.py          # applicability-aware estimation
    python3 compare_matrices.py              # held-out comparison
    python3 noise_sensitivity.py             # direction vs precision
