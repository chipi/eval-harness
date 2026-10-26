# RFC-015: The statistics of 0.5.0: non-inferiority, verdicts, test looks, power

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-013](../prd/PRD-013-identity-and-ties.md) (FR3, FR5, FR6, FR9),
  [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) (FR3.2, FR4: acceptance and the test check)
- **Related RFCs**: RFC-014 (identity; the migration seeds the look counts), RFC-010 (studies),
  [RFC-004](RFC-004-experiment-rounds.md) (rounds)
- **Related ADRs**: [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md) (goal ties, superseded in part)
- **Code**: `harness/scripts/stats.py` (new functions), `catalog_views.py` and `catalog_build.py` (goal
  pages), `rounds.py`, `pair_test.py`, `family_test.py`, `rank_stability.py`; new `harness/scripts/_looks.py`;
  validation suite `harness/tests/test_stats_validity.py`

## Abstract

0.5.0 asks three statistical questions the harness did not ask before: is a cheaper arm **not worse** than
the leader by more than a declared margin (non-inferiority); has a **test item set** been looked at too
often; and **can** these items show anything at all. The 0.4.0 question, is one arm **better**, keeps its
test (the paired sign-flip test with Holm), which is exact for it. Non-inferiority is a different question
with no exact permutation test, so this RFC chooses tests by simulation: for 0/1 measures, Tango's score test
for paired proportions; for continuous measures, the studentized bootstrap, at half the level when the paired
differences have a long tail of losses, and "inconclusive" below 50 items in that case. Verdicts are decided
by p, in a fixed order. Each test item set gets a budget of looks, each at its share of α. The smallest
attainable p and the minimum detectable effect are computed before anything is spent.

## Problem Statement

- ADR-0006 calls an arm tied with the leader when "not separated, and within the margin" (2% of the leader's
  mean): absence of evidence, against a margin computed from the data being judged.
- The obvious non-inferiority test, the sign-flip test applied to Δ + margin, assumes the paired differences
  are symmetric about −margin. Simulated at a true difference exactly at −margin, one-sided 2.5% (seeded
  scripts and their full output in
  [research/internal/stats-0.5.0](../../research/internal/stats-0.5.0/README.md)):

  | measure | items | shape | sign-flip error |
  | --- | --- | --- | --- |
  | 0/1 | 16 | P(−1) .15, P(+1) .05 | 0.078 |
  | 0/1 | 24 | P(−1) .05, P(+1) 0 | **0.299** |
  | 0/1 | 30 | P(−1) .12, P(+1) .02 | 0.107 |
  | continuous | 10 / 20 / 30 | long tail of losses | 0.151 / 0.142 / 0.127 |
  | continuous | 10 / 20 / 30 | normal | 0.025 / 0.032 / 0.027 |

  It is invalid for 0/1 measures and for skewed continuous ones.
- The superiority test is not affected: its null is that the two arms are exchangeable item by item, and the
  sign-flip test is exact for that null.
- Repeated comparisons on the same test items, choosing what to compare after seeing earlier results, inflate
  errors in a way Holm over a fixed family does not correct (Dwork et al., 2015).
- `min_attainable_p(len(shared))` counts zero differences, which cannot contribute to a superiority test, so it
  overstates what small sets can reach.

## Design

### Which test answers which question

| question | measure | test | level |
| --- | --- | --- | --- |
| better (superiority), H0: arms exchangeable | any | paired sign-flip, exact ≤ 30 items, Monte Carlo above (unchanged) | α of the family, Holm |
| not worse (non-inferiority), H0: Δ ≤ −margin | 0/1 | Tango's score test for paired proportions | one-sided α (2.5%, or a look's share) |
| not worse, H0: Δ ≤ −margin | continuous | studentized bootstrap (bootstrap-t), B = 4000, seeded by the items' digest | one-sided α; α/2 when the skew guard fires |
| no difference (equivalence) | either | both one-sided non-inferiority tests, at −margin and at +margin | one-sided α each |

- **0/1 or continuous**: a measure is 0/1 when every per-item value of both arms is 0 or 1, or when the adapter
  declares it in `METRIC_SCALES = {"correct": "binary"}`; otherwise continuous. Repeats are averaged per item
  first (as `pair_test` does), so a 0/1 measure with repeats becomes continuous, and is tested as such.
- **Tango** (1998). Counts x12 (arm right, reference wrong) and x21 (arm wrong, reference right) over n items, Δ =
  (x12 − x21)/n, d0 = −margin. With A = 2n, B = −x12 − x21 + (2n − x12 + x21)·d0, C = −x21·d0·(1 − d0), the
  restricted estimate q21 = (√(B² − 4AC) − B)/(2A), and Z = (x12 − x21 − n·d0)/√(n·(2·q21 + d0·(1 − d0))); p =
  1 − Φ(Z). Valid with zero off-diagonal cells, where McNemar-type tests are not. Its interval for Δ is the
  score interval (Tango 1998, the same restricted estimate inverted).
- **Bootstrap-t**. For differences d (n items), t* over B resamples of (mean* − mean)/(sd*/√n); p = the share of
  t* ≥ (mean + margin)/(sd/√n). Seeded by the item set's digest, so a verdict is reproducible.
- **The skew guard**: when the sample skewness of the paired differences is below −1 (a long tail of losses),
  the test uses α/2; when that holds and n < 50, the verdict is **inconclusive (too few items for a skewed
  measure)**, whatever p says. A right skew (a long tail of gains) needs no guard: the tests are conservative
  there.
- **Margins** are in the measure's units, declared by the goal per measure (PRD-013 FR3.1). With no margin, no
  non-inferiority test runs.

**Evidence** (one-sided 2.5%, true difference at −margin; Monte Carlo error about ±0.003 at 3000 runs, ±0.004 at
1500):

| items | 0/1, P(−1) .12 P(+1) .02: Tango | continuous, long loss tail: bootstrap-t (with guard) | continuous, normal: bootstrap-t |
| --- | --- | --- | --- |
| 10 | — | 0.083 (guard fired in 62%) → inconclusive | 0.023 |
| 16 | 0.016 (P(−1) .15, P(+1) .05) | — | — |
| 24 | 0.000 (P(−1) .05, P(+1) 0) | — | — |
| 30 | 0.011 | 0.048 (93%) → inconclusive | 0.033 |
| 50 | 0.014 | 0.030 (99%) | 0.029 |
| 100 | 0.024 | 0.027 (100%) | 0.021 |
| 200 | 0.023 | — | — |

Tango is at or below the level everywhere (conservative at small n). The bootstrap-t is at the level on normal
data and, with the guard, from 50 items on a long loss tail; below 50 the guard turns that case into
"inconclusive". The validation suite (Testing) reruns a fixed, smaller grid on every change to `stats.py`.

### Verdicts

`stats.verdict(deltas, *, kind, margin, level) -> Verdict(outcome, p, effect, interval, method, approximate,
note)`, with Δ = arm − reference in the quality direction:

The tests run as a fixed sequence at one level:

1. With a margin declared, the non-inferiority test first. If it rejects, the superiority test next: **superior**
   if that rejects too, else **non-inferior**; an arm that is non-inferior and separated as worse is
   **non-inferior (worse, within margin)**.
2. With no margin, or when non-inferiority does not reject: **superior** is not available after a failed
   non-inferiority test; **worse** if the superiority test in the other direction rejects; else **inconclusive**,
   with the reason (the test did not reject; too few items; the skew guard). With no margin declared, the
   superiority test alone decides **superior** / **worse** / **inconclusive**.

Testing in a fixed sequence (non-inferiority, then superiority), each at the full level, needs no correction for
the pair: the second is tested only when the first has rejected (the closed-testing argument). In a study's test
check the tests are one-sided; in a family (a round, a goal page) superiority keeps today's Holm-adjusted
two-sided test. The verdict is decided by p; the interval shown is the unadjusted 95% interval of
the test that decided (the sign-flip inversion `exact_ci` up to 30 items and its t interval above for
superiority; the score interval for Tango; the bootstrap-t interval otherwise), and at the look's level too when
it is below 2.5%.

### Goal pages and strategies

- `quality_first`: the quality leader only.
- `balanced` and `frugal`: among arms whose verdict against the leader is non-inferior (or superior), the best on
  the tie-break (cost, then speed); `frugal` uses the goal's cost margin when it declares a wider one.
- The candidates' non-inferiority tests against the leader are one family: Holm at the one-sided level. The
  leader is chosen from the same data, which biases arm − leader downwards: conservative, noted, not corrected.
- An inconclusive arm is never recommended on a tie-break.

### Test looks (`_looks.py`)

- **What is counted.** An item set is identified by its items' content digest (`items_sha256`). A look is a
  recorded comparison on that item set, in a test role, that involves an arm not compared there before: a
  confirmatory study's check, a confirmation, `run-promote`, `round-close --promote`, a round summary computed on
  a test dataset. Showing a recorded comparison again is not a look.
- **Storage.** `data/looks/<items_sha256 first 16>.json`: `{items_sha256, budget, looks: [{n, at, actor, what,
  goal, arms, level}]}`; one file per item set, shared by every goal that tests on it.
- **Budget.** K looks per item set (default 10; a goal may declare `test_looks: K` for a test dataset, and the
  smallest K of the goals sharing an item set applies). Look k is tested at α/K (online Bonferroni: Σ α/K = α).
  Comparisons within one look share α/K by Holm. When k > K, the comparison is refused unless the person
  consents (PRD-012 FR4.5), and the record says so.
- **Seeding** (the migration, RFC-014 step 8): the number of distinct non-baseline configurations with runs on
  the item set in the test role; the plan prints it beside the promotion count.
- **Where it shows.** Goal pages and `evh goals` show "test looks: used / budget" per test dataset.

### Can these items show anything

- **Smallest attainable p**: superiority 1/2^n′ one-sided (n′ = items whose paired difference is not zero);
  non-inferiority with the sign-flip family is not used, so for Tango the attainable p at the best case (every
  discordant item favouring the arm) is computed from the formula with x21 = 0, and for bootstrap-t the dry run
  states that a p below the level needs at least the items the MDE (below) requires. Before any run, "at best"
  uses all items. `stats.min_attainable_p(deltas, test)` replaces `min_attainable_p(n)`.
- **Minimum detectable effect** at 80% power: (z₁₋α/m + z₀.₈₀)·σ_d/√n, σ_d the standard deviation of paired
  differences: the upper quartile over existing arm pairs on the dataset, or a pilot pair; for 0/1, σ_d² = p₊ + p₋ −
  (p₊ − p₋)². For non-inferiority it is the smallest margin provable at 80% power when Δ = 0. At 30 items or fewer,
  or fewer than 20 discordant items, it is simulated (resample the pilot's differences, shift them, run the
  test). `rank-stability` reports it; a dry run reports it when such data exists, and says so when it does not.

## Migration

No data changes for the statistics themselves. The look counts are seeded by the migration script (RFC-014). Goal
recommendations change where an arm was "tied" and is now inconclusive or not tested (no margin declared); the
release notes list each change on this repository's goals with its reason, and every goal here gains a declared
margin before release (the owner sets each; RFC-014's plan prints the goals without one).

## Alternatives Considered

- **The sign-flip test on Δ + margin.** Rejected: invalid for 0/1 measures (error up to 0.299 at 2.5%) and for
  continuous measures with a long tail of losses (up to 0.151).
- **The paired t-test.** Rejected: 0.171 at 10 items and 0.077 at 100 on a long loss tail; worse than the
  bootstrap-t everywhere it was tried.
- **Two-sided equivalence (the interval inside ±margin) for tie-breaks.** Rejected: a cheaper arm that is better
  falls outside the band; the question is "not worse".
- **Alpha-spending (Lan–DeMets) across looks.** Rejected: it plans one comparison on growing data to a fixed end,
  not different arms on a fixed set without an end.
- **Thresholdout (Dwork et al.) for test looks.** Deferred: it allows more looks, but adds noise to every reported
  number; a fixed budget is simpler to read.
- **Betting confidence sequences for bounded means** (valid for any distribution of a bounded measure). Deferred:
  valid at every n, but wide at the sample sizes evaluations use; a candidate for a later release.

## Testing

- `harness/tests/test_stats_validity.py` (seeded, under a minute): Tango's error at the margin ≤ 0.03 on a fixed
  0/1 grid; the bootstrap-t with the guard ≤ 0.035 on normal data and at 50 items on a long loss tail; the guard
  turns the 10-item long-tail case inconclusive; superiority unchanged against the 0.4.0 values (bit for bit).
- `harness/tests/test_stats.py`: `verdict` order (each outcome, and "non-inferior (worse, within margin)"); Holm
  across candidates; attainable p with zeros; the MDE formula against a simulation on a fixed pilot.
- `harness/tests/test_looks.py`: counting, sharing across goals, the α/K level, refusal at K + 1 without consent,
  seeding from configurations.
- Goal-page tests in `test_catalog.py`: strategies under the new rule; an inconclusive arm never recommended.

## Decisions (ADR candidates)

1. Tie-breaks are non-inferiority tests against a goal-declared margin, decided by p in a fixed verdict order;
   supersedes ADR-0006's tie rule.
2. Tests by question and measure: sign-flip for superiority (unchanged); Tango for 0/1 non-inferiority;
   bootstrap-t with a skew guard for continuous non-inferiority, inconclusive below 50 items on a long loss tail.
3. Test items are a budget: K looks per item set at α/K, shared across goals, seeded from past configurations.
4. Power is stated before spending: attainable p from the items that can contribute, and an MDE from data.
