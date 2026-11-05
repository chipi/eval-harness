# ADR-0026 — A contender is shown no worse than the leader; a strategy is a default margin (0.8.0)

**Status:** Accepted (owner, 2026-11-05); built in 0.8.0. Replaces the contender rules of
[ADR-0006](ADR-0006-goal-axes-and-strategies.md); its axes, limits, leader and tie-break stand.
**Date:** 2026-11-05
**Detail:** [RUNBOOK, goal keys](../../harness/docs/RUNBOOK.md), the simulations in
`research/internal/stats-0.8.0/`, the plan in `research/internal/PLAN_0.8.0.md` (A2)

## Context

A contender, an arm the tie-break may pick instead of the quality leader, had to be "not significantly
different" from the leader (`frugal`), and within 2% of it on the mean (`balanced`). A non-significant
difference is not evidence of equivalence (Lakens 2017): it also comes from too few items. So the smaller or
noisier a dataset, the more arms tied, and `frugal` then recommended the cheapest. On the committed goals,
dbpedia had 20 contenders of 21 and triage 52. The simulations (re-run on 0.8.0's code, identical to their
first runs) showed the shifted sign-flip test rejecting up to 30% at a nominal 2.5% on 0/1 scores.

## Decision

- **A contender is shown no worse than the leader by more than the margin**: a one-sided non-inferiority test
  (`stats.noninferior`). 0/1 scores: Tango's score test, at any size. Other scores, repeats averaged to fractions,
  or clusters: the bootstrap-t at half the level, from 100 items or equal clusters, or 250 effective clusters
  ((sum k)^2 / sum k^2) when clusters differ in size; below that, "too few items to call a tie" (owner: no
  fallback to the old rule). Identical per-item scores stay contenders.
- **Holm across the candidates, at one level** (owner). The tie-break picks the cheapest arm that passed, so the
  recommendation is wrong whenever any candidate passes wrongly: simulated with every candidate exactly at the
  margin, testing each arm on its own recommended a too-weak arm 7%, 17%, 24% and 40% of the time with 3, 8, 13
  and 20 candidates; Holm 2% to 3%, against 2.5%. A bootstrap-t p, tested at half the level, enters the family
  doubled. Each arm on its own was chosen first, on a wrong argument (that the recommended arm's own test is all
  that matters), and reversed the same day.
- **A strategy is a default margin** (owner): `quality_first` 0 (the same quality only), `balanced` 5% of the
  leader's mean, `frugal` 10%. A goal's `axes.quality.margin`, in the measure's units, always wins. 2% admitted
  only the leader on every committed goal; 10% as the general default admitted 25 on dbpedia.
- **Every test is visible:** the decision names the margin and where it came from; `evh goals` and the goal
  page show each arm's contender test (p, its Holm threshold, shown or not, or too few); `evh validate` notes each
  goal on a default margin.

## Consequences

- Recommendations change on the committed goals (before/after in PLAN_0.8.0 A2).
- **The leader is chosen from the same data it is then tested against.** With many arms that are truly equal, the
  best-looking one is ahead by chance, so every candidate looks worse against it: simulated (0/1, 200 items), the
  gap was about −0.03 to −0.045 for 3 to 20 equal arms, the size of a 5% margin. This is conservative (no false
  contender comes from it) but costs power: on ag_news, 29 candidates on 200 items, nobody but the leader can be
  shown within 5%. A goal can test against its promoted baseline instead (`axes.quality.reference: baseline`,
  owner: an opt-in), which removes it and asks the deployment question; and every decision says which margin its
  group can detect at all (A3).
- A goal on fewer than 100 items with a continuous measure recommends its leader and says why; adding items is
  the way to a tie.
- A non-inferiority p is a bootstrap estimate for continuous scores: seeded by the data, the same comparison
  always gives the same verdict, kept in the p cache and in the process.
