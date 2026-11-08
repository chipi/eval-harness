# ADR-0028 — From 10,000 items a paired test's p is its normal limit, not resampled (0.8.0)

**Status:** Proposed (2026-11-08); built in 0.8.0 (S2).
**Date:** 2026-11-08
**Detail:** `harness/tools/large_sample_check.py` (the simulation, rerunnable), `stats.LARGE_SAMPLE`, the plan in
`research/internal/PLAN_0.8.0.md` (S1, S2)

## Context

Above 30 items the paired sign-flip test estimates its p from 20,000 seeded permutations, and the contender test
(ADR-0026) from 9,999 bootstrap-t resamples, both in pure Python. S1 measured what that costs at scale: at 10,000 items
one sign-flip p took 8.1 s and one bootstrap-t p 22.9 s; a 50-arm catalog took 1,532 s and every `evh goals` as long
again, almost all of it these draws. The plan (S2): a large-sample approximation where simulation shows it accurate,
else cheaper resampling.

Both statistics have a normal limit. The sign-flip distribution of the mean of ±d_i has mean 0 and variance
sum(d_i²)/n², so z = sum(d) / sqrt(sum(d²)) and p = erfc(|z| / sqrt 2). The bootstrap-t estimates the distribution
of T = (m + margin) / se, whose limit is the standard normal, so p = 1 − Φ(T).

## What the simulation found

`tools/large_sample_check.py` draws datasets of seven kinds the harness meets (a continuous score; one bounded to
[−1, 1] with a third of items tied at 0; a 0/1 outcome; heavy tails, Student t with 3 degrees of freedom; sparse,
95% of items unchanged; clusters of 3 and of 8 with a shared effect), 40 of each per size, with effects spread over
|z| ≈ 1 to 3.5, where decisions are made. Each is tested both ways: the resampled p as the harness computes it, and the
limit. Seeded: the same command prints the same table.

| size | the limit off by more than 3 Monte Carlo SE (of 40 per kind) | the worst kinds |
| --- | --- | --- |
| 1,000 | up to 12 (bootstrap-t), 4 (sign-flip) | sparse 12, heavy 8 (bootstrap-t); sparse 4, heavy 3 (sign-flip) |
| 2,000 | up to 7 | sparse 7, heavy 3 (bootstrap-t); heavy 3 (sign-flip) |
| 5,000 | up to 5 | heavy 5 (bootstrap-t); binary 2 (sign-flip) |
| 10,000 | at most 1, of 280 per test | clusters3 1 (bootstrap-t); none for the sign-flip |

One case in 280 beyond three standard errors is what chance alone gives (280 × 0.0027 ≈ 0.76). At 10,000 the two
also decide differently in some cases (9 sign-flip, 10 bootstrap-t, over four levels), and in every one of them the
resampled p is within 1.7 of its own Monte Carlo standard errors of the level: there the resampling cannot tell
which side the true p is on either, and the limit is at least as close to it.

## Decision

From `LARGE_SAMPLE` = 10,000 units (items, or clusters when the test is clustered) both tests report their normal
limit. Below it nothing changes: the same draws, the same p, bit for bit; every committed result has at most 280
items and keeps its numbers.

Beside it, the cost that remains below 10,000 is paid once: every `evh` command keeps its estimated p's in the
project's ignored `.cache/evh-p.jsonl`, as `evh mcp` already did (`EVH_P_CACHE` names another file; empty turns it
off). The key holds the data and the algorithm, so a kept p is never stale.

## Consequences

- Positive: at 10,000 items a comparison costs milliseconds instead of half a minute: the bench's 50-arm catalog took
  12.8 s (1,532 s before) and `family-test` 1.6 s (332.5 s); `goals` after `catalog` reads the p's the catalog drew
  (the p cache, now on by default). The intervals were already analytic above 30 items.
- Negative: below 10,000 items a first comparison still resamples, measured at 1,000 items about 1 s a sign-flip and
  2 s a bootstrap-t, at 10,000 8.1 s and 22.9 s (so up to about 23 s just below the threshold); the bench's 1,000-item
  catalog still took 146 s the first time. Heavy-tailed or sparse data need the resampling there. A p reported from the limit is not a count over draws, so it is not a multiple of
  1/(permutations + 1).
- Neutral: the threshold is a number the simulation supports, not a law: a kind of data the seven do not cover may
  need it higher; the tool reruns with other sizes.

## Alternatives considered

- **The limit from 1,000 items.** The simulation refutes it for heavy-tailed and sparse data.
- **Fewer resamples, or sequential stopping (Besag and Clifford).** It saves most where p is large and least near the
  decision levels, where the precision matters, and it changes the p's below 10,000 that are committed today.
- **numpy for the resampling.** A new dependency for the core (`stats` is standard library only); not asked for.
