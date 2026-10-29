# ADR-0015 — Ties are non-inferiority; heldout datasets spend their level over looks (0.7.0)

**Status:** Accepted (2026-10-26), design; not yet built. Revision 3 (2026-10-27): no equivalence claim; the MDE is the formula. Revision 2:
continuous non-inferiority from 100 items at half the level; looks counted from decisions. Supersedes the tie rule of
[ADR-0006](ADR-0006-goal-axes-and-strategies.md).
**Date:** 2026-10-26
**Detail:** [PRD-013](../prd/PRD-013-identity-and-ties.md) FR3, FR5, FR6, FR9,
[RFC-015](../rfc/RFC-015-noninferiority-looks-power.md) (tests, simulations, looks, power),
[research/internal/stats-0.7.0](../../research/internal/stats-0.7.0/README.md) (the simulations)

## Context

ADR-0006 called an arm tied with the leader when the paired test did not separate them and the
difference was within a margin, by default 2% of the leader's mean: absence of evidence, against a
margin taken from the data being judged. The obvious non-inferiority test, the sign-flip test on the
shifted differences, was simulated and found invalid for 0/1 measures (error up to 0.299 at a nominal
0.025) and for continuous measures with a tail of losses (up to 0.151). Studies (ADR-0010) will compare
many arms on the same heldout items, which inflates errors in a way a fixed Holm family does not correct.

## Decision

- **A tie is non-inferiority against a margin the goal declares** per measure, in its units. With no
  margin there are no tie-breaks; an inconclusive arm is never recommended on one. An arm separated as
  worse but within the margin is eligible, labelled "non-inferior (worse, within margin)".
- **Tests by question and measure**: superiority keeps the exact paired sign-flip test; non-inferiority
  of a 0/1 measure uses Tango's score test; of a continuous measure, a studentized bootstrap specified
  exactly, at half the level, from 100 items (one rule, chosen on simulations across tail weights after
  the first draft's skew guard failed them). Verdicts are decided by p in a fixed order (non-inferiority,
  then superiority); a confirmation's families use serial gatekeeping.
- **Each heldout dataset spends a one-sided 2.5% over all its looks, front-loaded** (the owner's choice):
  look k at 2.5% · 6/(π²k²), so 1.52%, 0.38%, 0.17%, …; after a protective limit (10 by default) a look
  needs the person's consent. Only commands that record a decision take a look (a study's
  confirmation, a promotion), counted from those records with no look file; pages show nominal results
  labelled as not a look. Any subset of a heldout dataset spends the dataset's budget. Two decisions that
  took one look number (two machines, two branches) are reported by `validate`; a database store will
  prevent it.
- **Use before 0.7.0 is shown, not counted** (the owner's choice): each heldout dataset starts at look 0,
  with the number of configurations that used it before 0.7.0, computed from the runs, shown beside it.
- **Power before spending**: the smallest attainable p (0/1) or the smallest provable margin (continuous)
  is compared with the next look's level before anything runs; a study that cannot produce evidence is
  refused unless the person overrides it.

## Consequences

Recommendations change where an arm was "tied" and is now inconclusive or untested; the release notes
list each, and every goal here declares its margins before release. Small heldout sets yield
"inconclusive" more often, which is the honest answer: below 100 items a continuous measure cannot be
shown non-inferior, only better.
