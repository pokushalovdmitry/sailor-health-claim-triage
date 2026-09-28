---
name: denial-appeal-matching-and-calculation
description: Matches an extracted denial claim against the historical denial/appeal dataset and computes the win-probability, expected-value, NPV, feasibility, and pursue/don't-pursue recommendation the chat layer displays.
---

# Denial Appeal Matching & Calculation Skill

You are Agent 2 of the Sailor Health Denial Appeal Prioritization Tool. You
take Agent 1's structured output for one claim and turn it into the numbers
and recommendation a staff member acts on. Every step below is a fixed
formula or an exact-match filter -- there is no judgment call anywhere in
this skill, which is why this agent runs as deterministic code rather than a
model call. This document is the authoritative spec for that code; if the
two ever disagree, the code has a bug.

## Step 1 -- Segment matching

Filter the historical denials dataset (`historical_denials.json`) to the
subset of rows matching this claim's:

- Denial reason category (Technical / Clinical)
- Payer (exact string match)
- Plan (exact string match)
- Date-of-service bucket (exact string match, e.g. `"This Year (2026)"`)

All four must match exactly. By the dataset's construction, every one of the
36 possible (category x payer/plan x bucket) combinations has at least 25
historical rows, so a genuinely empty subset should never occur for a claim
whose date of service falls in the two years the dataset covers. Treat an
empty subset as an input error to surface clearly, not as a silent zero.

## Step 2 -- Statistics from the matched subset

Compute, over the matched subset only:

- **Sample size** -- count of rows in the subset.
- **Win probability** -- count(`Appealed - Won` = true) / sample size.
- **Average payout %** -- mean of `Payout % (if Won)` over the *won* rows
  only (lost rows have no payout and must be excluded from this average, not
  treated as zero).
- **Average days: denial to appeal filed** -- mean of
  `Days: Denial to Appeal Filed` over the whole subset.
- **Average days: appeal filed to resolution** -- mean of
  `Days: Appeal Filed to Resolution` over the whole subset.
- **Average appeal cost** -- mean of `Appeal Cost ($)` over the whole subset.

## Step 3 -- Payer deadline lookup

Using the claim's payer and plan, look up the appeal filing deadline (days
from denial date) from `payer_rules.json`. This is a separate lookup from
Step 1/2 -- it is not part of the historical-denials subset and does not
vary by denial reason or date bucket, only by payer/plan.

## Step 4 -- Final calculations

Using the claim's own billed amount (from Agent 1's output) plus the Step 2
subset statistics:

- **Expected recovery** = billed amount x win probability x average payout %
- **Net expected value** = expected recovery - average appeal cost
- **Time to resolution** = average days (denial->filed) + average days
  (filed->resolution)
- **NPV** = net expected value / (1.10) ^ (time to resolution / 365) --
  10% annualized discount rate, a fixed constant, never user-configurable in
  this prototype.
- **Feasibility flag** = payer's appeal deadline >= average days
  (denial->filed). This compares the deadline to the *typical* filing pace
  for this claim type/payer/plan, not to any date on the uploaded notice
  itself -- the notice's denial date is only ever used as the anchor for
  the deadline lookup context, never as an input to this comparison.

## Step 5 -- Recommendation

`MIN_NET_VALUE_THRESHOLD_USD = 50` is a named constant, not a magic number:
a round, easy-to-read placeholder. The spec's initial suggestion was $100,
tied to an industry finding that claims below roughly that size are commonly
written off regardless of win probability; lowered to $50 per product
decision to let more of the thin-but-positive middle through while still
screening out negligible claims. It is expected to be revisited once real
Sailor claims data is available.

Apply, in this order, using net expected value (from Step 4) and the
feasibility flag:

1. **Pursue** -- net expected value > threshold, **and** feasibility flag is
   true. Rationale: *"Expected net value is above $50, and filing pace
   meets the deadline."*
2. **Pursue, but expedite filing** -- net expected value > threshold, **but**
   feasibility flag is false. This is not a clean pursue and not a
   do-not-pursue -- it is a real third case: the economics justify the
   effort, but only if filed faster than this claim type's typical pace.
   Rationale: *"Expected net value is above $50. Average filing time
   typically exceeds the remaining deadline for this claim type --
   expediting would be required to make the deadline, but the expected
   value justifies the effort if that's achievable."*
3. **Do not pursue** -- net expected value <= threshold, regardless of
   feasibility. State every reason that actually applies rather than
   stopping at the first:
   - Feasible: *"Expected net value is below $50."*
   - Not feasible: *"Expected net value is below $50, and average filing
     time also exceeds the remaining deadline for this claim type."*

A claim failing on both value and feasibility is different information from
one failing on only one -- always say which is true, never collapse both
into a single generic "do not pursue."

## Output

Sample size, win probability, average payout %, expected recovery, average
appeal cost, net expected value, time to resolution, NPV, feasibility flag,
and the recommendation (`pursue` / `pursue_expedite` / `do_not_pursue`) with
its rationale sentence -- all passed to the chat layer for display in its
fixed output structure.
