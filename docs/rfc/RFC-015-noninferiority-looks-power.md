# RFC-015: The statistics of 0.5.0: non-inferiority, verdicts, heldout looks, power

- **Status**: Draft (0.5.0), revision 2 (2026-10-27): continuous non-inferiority from 100 items at half the level
  (one rule instead of a skew guard); looks counted from recorded decisions, with no look files
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-013](../prd/PRD-013-identity-and-ties.md) (FR3, FR5, FR6, FR9),
  [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) (FR3.2, FR4: acceptance and the heldout check)
- **Related RFCs**: RFC-014 (identity), RFC-017 (the record store: nothing derivable is stored), RFC-010 (studies),
  [RFC-004](RFC-004-experiment-rounds.md) (rounds)
- **Related ADRs**: [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md) (goal ties, superseded in part)
- **Code**: `harness/scripts/stats.py` (new functions), `catalog_views.py` and `catalog_build.py` (goal
  pages), `rounds.py`, `pair_test.py`, `family_test.py`, `rank_stability.py`, `holdout_significance.py`,
  `validate_tree.py` (margins, looks); new `harness/scripts/_looks.py` (counts looks from the records);
  `schemas/goal.schema.json` (`axes.<axis>.margin` without a default, `heldout_looks`); validation suite
  `harness/tests/test_stats_validity.py`

## Abstract

0.5.0 asks three statistical questions the harness did not ask before: is a cheaper arm **not worse** than
the leader by more than a declared margin (non-inferiority); has a **heldout item set** been looked at too
often; and **can** these items show anything at all. The 0.4.0 question, is one arm **better**, keeps its
test (the paired sign-flip test with Holm), which is exact for it. Non-inferiority is a different question
with no exact permutation test, so this RFC chooses tests by simulation: for 0/1 measures, Tango's score test
for paired proportions; for continuous measures, the studentized bootstrap at half the level, from 100 items. Verdicts are decided
by p, in a fixed order. Each heldout dataset spends its one-sided α = 2.5% over its looks, front-loaded: the first look
at 1.52%, the second at 0.38%, the tenth at 0.015%; only commands that write a decision take a look. The smallest
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
- Repeated comparisons on the same heldout items, choosing what to compare after seeing earlier results, inflate
  errors in a way Holm over a fixed family does not correct (Dwork et al., 2015).
- `min_attainable_p(len(shared))` counts zero differences, which cannot contribute to a superiority test, so it
  overstates what small sets can reach.

## Design

### Which test answers which question

| question | measure | test | level |
| --- | --- | --- | --- |
| better (superiority), H0: arms exchangeable | any | paired sign-flip, exact ≤ 30 items, Monte Carlo above (unchanged) | α of the family, Holm |
| not worse (non-inferiority), H0: Δ ≤ −margin | 0/1 | Tango's score test for paired proportions | one-sided α (2.5%, or a look's share) |
| not worse, H0: Δ ≤ −margin | continuous | studentized bootstrap (bootstrap-t), specified below, from 100 items | one-sided α/2 |
| no difference (equivalence) | either | both one-sided tests, at −margin and at +margin | one-sided α each (α/2 each for a continuous measure) |

- **0/1 or continuous**: a measure is 0/1 when every per-item value of both arms is 0 or 1, or when the adapter
  declares it in `METRIC_SCALES = {"correct": "binary"}`; otherwise continuous. Repeats are averaged per item
  first (as `pair_test` does), so a 0/1 measure with repeats becomes continuous, and is tested as such.
- **Tango** (1998). Counts x12 (arm right, reference wrong) and x21 (arm wrong, reference right) over n items, Δ =
  (x12 − x21)/n, d0 = −margin. With A = 2n, B = −x12 − x21 + (2n − x12 + x21)·d0, C = −x21·d0·(1 − d0), the
  restricted estimate q21 = (√(B² − 4AC) − B)/(2A), and Z = (x12 − x21 − n·d0)/√(n·(2·q21 + d0·(1 − d0))); p =
  1 − Φ(Z). Valid with zero off-diagonal cells, where McNemar-type tests are not. Its interval for Δ is the
  score interval (Tango 1998, the same restricted estimate inverted).
- **Bootstrap-t**, exactly:
  - d = the n paired differences (arm − reference, in the quality direction; repeats averaged per item first);
    m = mean(d), s = the sample standard deviation (n − 1). T = (m + margin)/(s/√n).
  - B resamples of n items with replacement; for each, t* = (m* − m)/(s*/√n). A resample with s* = 0 is dropped and
    counted; B counts the kept ones. p = (1 + #{t* ≥ T})/(B + 1).
  - B = 9999, raised to ⌈20/level⌉ − 1 (at most 199,999) when the level in force is below 0.002, so that at least
    about 20 resamples fall beyond the threshold; a Monte Carlo p near the level is then not decided by noise.
  - The seed is the first 16 hex digits of sha256(`<heldout dataset digest>|<arm a>|<arm b>|<measure>|<margin>`), so each
    comparison has its own resamples and the same comparison always gives the same p.
  - s = 0 (every difference equal): no test is possible; the verdict is **inconclusive (no variation)**, and the
    catalog says the arms measured the same on every item.
- **One rule for continuous measures**: the test runs from 100 items, at half the level in force; below 100 items
  the verdict is **inconclusive (fewer than 100 items for a continuous measure)**. It is one sentence a reader can
  apply, and it holds the level on every shape simulated, with or without a tail of losses (below). Below 100 items
  a continuous measure can still be shown **separated: better** by the sign-flip test, which is exact at any size.
- **Margins** are in the measure's units, declared by the goal per measure in the field 0.4.0 already has,
  `success_criteria.axes.<axis>.margin` (`axes.quality.margin` for the primary measure; a project axis for another
  measure) (PRD-013 FR3.1). What changes is its meaning and its default: in 0.4.0 it was a tie band defaulting to 2%
  of the leader's mean; from 0.5.0 it is the non-inferiority margin and has no default. The migration (RFC-014) leaves
  declared values where they are and lists them, since their meaning changes. With no margin, no non-inferiority test
  runs, and `validate` notes the goal. The `non_inferior` direction of PRD-005's goal axes uses
  this test.

**Evidence for Tango** (one-sided 2.5%, true difference at −margin; Monte Carlo error about ±0.003 at 3000 runs):

| items | 0/1 differences | Tango's error |
| --- | --- | --- |
| 16 | P(−1) .15, P(+1) .05 | 0.016 |
| 24 | P(−1) .05, P(+1) 0 | 0.000 |
| 30, 50, 100, 200 | P(−1) .12, P(+1) .02 | 0.011, 0.014, 0.024, 0.023 |

Tango is at or below the level everywhere (conservative at small n).

**Evidence for the bootstrap-t and its rule.** The bootstrap-t at the full level is anti-conservative on small
samples and on tails of losses (0.035 at 20 items on normal differences; 0.049 to 0.075 at 10 items on lognormal tails
of σ ≥ 0.5; 0.042 at 50 items for σ = 1.0: `bootstrap_spec_check.py`). Candidate rules were scored on one grid of
simulations (`bootstrap_rule_grid.py`: normal differences and lognormal tails of losses of σ 0.25 to 1.0, 1000
simulations per cell, B = 999, at the margin for the error and at no difference for the power; `bootstrap_rule_eval.py`,
its output in the README). A skew guard (inconclusive below 50 items, α/4 below 100, α/2 from 100) also held the level,
but needed a skewness threshold tuned on these shapes and could not be explained in a sentence. The rule adopted:

| items | worst error over the five shapes | power at no difference (normal; lognormal σ 0.25 to 1.0) |
| --- | --- | --- |
| below 100 | 0 (inconclusive) | 0 |
| 100 | 0.023 | 0.951; 0.910, 0.848, 0.753, 0.686 |
| 200 | 0.019 | 1.000; 0.999, 0.992, 0.967, 0.917 |

The worst error is below the level. The price is power: below 100 items a continuous measure cannot be shown not worse,
only better. The validation suite (Testing) reruns a fixed, smaller grid on every change to `stats.py`.

### Verdicts

`stats.verdict(deltas, *, kind, margin, level) -> Verdict(outcome, p, effect, interval, method, approximate,
note)`, with Δ = arm − reference in the quality direction:

The tests run as a fixed sequence at one level:

1. With a margin declared, the non-inferiority test first. If it rejects, the superiority test next: **separated: better**
   if that rejects too, else **non-inferior**; an arm that is non-inferior and separated as worse is
   **non-inferior (worse, within margin)**.
2. When non-inferiority does not reject: **separated: better** is not available after a failed non-inferiority
   test; **separated: worse** if the superiority test in the other direction rejects; else **inconclusive**, with the
   reason (the test did not reject; too few items). With no margin declared, the superiority test
   alone decides, exactly as in 0.4.0: **separated: better** / **separated: worse** / **not separated**.

Testing in a fixed sequence (non-inferiority, then superiority), each at the full level, needs no correction for
the pair: the second is tested only when the first has rejected (the closed-testing argument). It holds for one chain;
where several measures are tested together, the families are:

- **A study's heldout check and a confirmation**: with `test_rule: noninferiority`, F1 = {the primary measure's
  non-inferiority, each limit's non-inferiority against the baseline}, Holm at the look's level; the
  primary's superiority is tested, at the look's level, only when every hypothesis of F1 rejects (serial
  gatekeeping, which keeps the family's error at the level). With `test_rule: superiority`, F = {the primary's
  superiority, each limit's non-inferiority}, Holm at the look's level; no non-inferiority test of the primary runs.
  All tests are one-sided.
- **`run-promote`**: the promoted run against the current baseline on the goal's measure, the fixed sequence at the
  look's level.
- **Goal pages**: the candidates' non-inferiority tests against the leader are one family (below); "worse" there is
  descriptive (shown with its nominal p), not a tested claim. Superiority in a round keeps today's Holm-adjusted
  two-sided test at 5% on dev data.

`stats.verdict(…, rule)` takes the rule (`noninferiority`, `superiority`), and `stats.family_verdicts(…)` applies the
families above. The verdict is decided by p; the interval shown is the unadjusted 95% interval of
the test that decided (the sign-flip inversion `exact_ci` up to 30 items and its t interval above for
superiority; the score interval for Tango; the bootstrap-t interval otherwise), and at the look's level too when
it is below 2.5%.

### Goal pages and strategies

- `quality_first`: the quality leader only.
- `balanced` and `frugal`: among arms whose verdict against the leader is non-inferior (or separated: better), the best on
  the tie-break (cost, then speed); `frugal` uses the goal's cost margin when it declares a wider one.
- The candidates' non-inferiority tests against the leader are one family: Holm at the one-sided level. The
  leader is chosen from the same data, which biases arm − leader downwards: conservative, noted, not corrected.
- An inconclusive arm is never recommended on a tie-break.

### Heldout looks (`_looks.py`)

- **What owns the budget.** A test **dataset**, identified by the digest of its items (sorted item ids with their
  content hashes, so order does not matter). Any subset of it that a comparison uses (the heldout check's items minus
  dev and shown items, the items two runs share, a slice) spends the dataset's budget, never a fresh one, so a
  budget cannot be dodged by dropping an item. Two goals that test on one dataset share its budget; two datasets that
  share items are counted separately, and `validate` notes the overlap.
- **What is a look.** Only commands that write a decision take one: a confirmatory study's heldout check, a confirmation
  (`study-confirm`, RFC-010), `run-promote`, `round-close --promote`. A look is keyed by (dataset, the two arms'
  fingerprint hashes, the measure, the rule): a writing command that finds a recorded look with the same key reuses
  its verdict and takes none (promoting a study's confirmed winner against the same baseline is not a second look).
  Read commands and pages (goal pages, `rounds`, `pair-test`, the catalog) never take one: on a heldout dataset they
  show the nominal result labelled "not a look: nominal", and beside it the dataset's next look level. Their output
  depends only on the records, so it stays deterministic.
- **Levels.** One-sided α = 2.5% per dataset, spent front-loaded: look k is tested at α·γ_k with γ_k = 6/(π²k²)
  (Σγ_k = 1, so the total over every look ever taken is α): look 1 at 1.52%, 2 at 0.38%, 3 at 0.17%, 4 at 0.095%,
  5 at 0.061%, 10 at 0.015%. Comparisons within one look share its level by the families above.
- **Budget.** The series never runs out, but each look is stricter than the last, so a dataset wears out. K (default
  10; a goal may declare `heldout_looks: K`, and the smallest K of the goals sharing a dataset applies) is a protective
  limit: look K + 1 and later are refused unless the person consents (PRD-012 FR4.5), and their levels continue the
  series, so consent never inflates the error.
- **Counted, not stored** ([RFC-017](RFC-017-record-store.md)). A look is a decision recorded on a heldout dataset:
  a baseline version whose evidence was computed there (RFC-012), or a study's `heldout_check` line (RFC-010). The next
  look's number is one more than the decisions recorded on the dataset; there is no look file and no reservation.
- **Two decisions at once.** Two commands on one machine, or two people on two branches, can take the same number,
  and both are then tested at that look's level, which is too generous for the second. The files provider cannot
  prevent it without a centre; `validate` reports a **double-spent look** (two decisions with one number on one
  dataset), naming both, and every page shows it beside the dataset. The database provider will hand out the number in
  a transaction.
- **History before 0.5.0** (the owner's decision): earlier use is not counted as looks; each heldout dataset starts at
  look 0. How many distinct configurations had runs on it in the heldout role before 0.5.0 is computed from the runs
  (their fingerprints name a harness before 0.5.0), and pages show it beside the looks ("used by 29 configurations
  before 0.5.0; levels from 0.5.0 do not account for that").
- **Where it shows.** Goal pages and `evh goals` show per heldout dataset: looks taken, the next look's level, the protective
  limit, and the prior use; `evh goals --goal G --looks` lists every look of its heldout datasets (key, level, actor,
  what, verdict).

### Can these items show anything

- **Smallest attainable p**: superiority 1/2^n′ one-sided (n′ = items whose paired difference is not zero); for
  Tango, the p at the best case (every discordant item favouring the arm, x21 = 0) from the formula. Before any run,
  "at best" uses all items. `stats.min_attainable_p(deltas, test)` replaces `min_attainable_p(n)`. It is compared
  with the next look's level divided by the family's size.
- **Continuous non-inferiority** cannot be shown below 100 items, which the dry run says at once. From 100 items it
  has no useful attainable p (a bootstrap p reaches 1/(B + 1) on any data), so possibility is judged by power: the
  study is refused when the smallest margin provable at 80% power (the MDE below, at half the look's level) exceeds
  the goal's margin. The check runs at the start with σ_d from existing arm pairs on the heldout dataset, and again
  before the heldout check with σ_d from the study's own dev trials; with no σ_d at the start, the dry run says
  "cannot tell yet" and the check before the heldout look decides.
- **Minimum detectable effect** at 80% power: (z₁₋α/m + z₀.₈₀)·σ_d/√n (n all items; PRD-013 FR6.2's √n′ is amended to
  √n, since σ_d already counts the zero differences), σ_d the standard deviation of paired
  differences: the upper quartile over existing arm pairs on the dataset, or a pilot pair; for 0/1, σ_d² = p₊ + p₋ −
  (p₊ − p₋)². For non-inferiority it is the smallest margin provable at 80% power when Δ = 0. At 30 items or fewer,
  or fewer than 20 discordant items, it is simulated (resample the pilot's differences, shift them, run the
  test). `rank-stability` reports it; a dry run reports it when such data exists, and says so when it does not.

## Migration

No data changes for the statistics themselves: looks and prior use are computed, and declared `axes.*.margin` values
stay where they are (the migration lists them, since their meaning changes). Goal
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
- **Equal shares, α/K per look.** Rejected by the owner: every look, the first included, would be tested at 0.25%;
  the front-loaded series gives the first look 1.52% and still spends at most α in total.
- **Count 0.4.0's use as looks.** Rejected by the owner: every heldout set here (23 to 35 configurations each) would be
  spent on the first day; prior use is shown instead.
- **Every comparison on heldout data is a look, pages included.** Rejected: a page's level would change when another
  goal records a look, and a read command would write records.
- **Thresholdout (Dwork et al.) for heldout looks.** Deferred: it allows more looks, but adds noise to every reported
  number; a fixed budget is simpler to read.
- **Betting confidence sequences for bounded means** (valid for any distribution of a bounded measure). Deferred:
  valid at every n, but wide at the sample sizes evaluations use; a candidate for a later release.

## Testing

- `harness/tests/test_stats_validity.py` (seeded, under a minute): Tango's error at the margin ≤ 0.03 on a fixed
  0/1 grid; the bootstrap-t at half the level ≤ 0.035 on normal data and on a σ = 1.0 loss tail at 100 items;
  below 100 items inconclusive; superiority unchanged against the 0.4.0 values (bit for bit).
- `harness/tests/test_stats.py`: `verdict` order (each outcome, and "non-inferior (worse, within margin)"); the p
  definition and B for small levels; s = 0 inconclusive; the seed differs per arm pair and repeats per comparison;
  the serial gatekeeping family; Holm across candidates; attainable p with zeros; the MDE formula
  against a simulation on a fixed pilot.
- `harness/tests/test_looks.py`: γ_k levels; looks counted from baseline versions and heldout checks; a subset
  spends its dataset's budget; item order does not change the dataset; sharing across goals; reuse of a recorded look
  with the same key; read commands take none; two decisions with one number are reported as a double-spent look;
  refusal at K + 1 without consent and the level continuing the series; prior use computed from runs and shown, not
  counted.
- Goal-page tests in `test_catalog.py`: strategies under the new rule; an inconclusive arm never recommended.

## Decisions (ADR candidates)

1. Tie-breaks are non-inferiority tests against a goal-declared margin, decided by p in a fixed verdict order;
   supersedes ADR-0006's tie rule.
2. Tests by question and measure: sign-flip for superiority (unchanged); Tango for 0/1 non-inferiority;
   bootstrap-t at half the level for continuous non-inferiority, from 100 items.
3. Heldout datasets spend α = 2.5% one-sided over their looks, front-loaded (γ_k = 6/(π²k²)), with a protective limit of K
   looks; only commands that write a decision take a look, counted from the recorded decisions; subsets spend their
   dataset's budget; prior use is shown, not counted; a double-spent look is reported by `validate`.
4. Power is stated before spending: attainable p from the items that can contribute, and an MDE from data.
5. Families: serial gatekeeping (non-inferiority family by Holm, then superiority) for a heldout check; the bootstrap-t is
   specified exactly (p, B, seed, ties), its rule chosen on a simulation grid of tail weights.
