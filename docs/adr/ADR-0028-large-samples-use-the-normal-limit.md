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
|z| ≈ 1 to 3.5, where decisions are made. A size counts units: items, or for the cluster kinds clusters (10,000
clusters of 8 are 80,000 items). Each is tested both ways, the sign-flip on the units' totals as `pair-test --cluster`
flips them: the resampled p as the harness computes it (the tool sets the threshold out of reach, so it resamples at
every size), and the limit. Seeded: the same command prints the same table. The run below (2026-11-08) took 1,128 s on
24 processes.

| size | the limit off by more than 3 Monte Carlo SE (of 40 per kind) | the worst kinds |
| --- | --- | --- |
| 1,000 | up to 12 (bootstrap-t), 4 (sign-flip) | sparse 12, heavy 8 (bootstrap-t); sparse 4, heavy 3 (sign-flip) |
| 2,000 | up to 7 | sparse 7, heavy 3 (bootstrap-t); heavy 3 (sign-flip) |
| 5,000 | up to 5 | heavy 5 (bootstrap-t); binary 2 (sign-flip) |
| 10,000 | none, of 280 per test | none |

Chance alone puts about one case in 280 beyond three standard errors (280 × 0.0027 ≈ 0.76). At 10,000 the two also
decide differently in some cases (10 sign-flip, 10 bootstrap-t, over four levels), and in every one of them the
resampled p is within 1.74 (sign-flip) and 1.18 (bootstrap-t) of its own Monte Carlo standard errors of the level:
there the resampling cannot tell which side the true p is on either, and the limit is at least as close to it.
Below 10,000 the split decisions reach 4.0 (sign-flip, 2,000) and 11.0 (bootstrap-t, 1,000) standard errors from
their level: real errors of the limit.

## Decision

From `LARGE_SAMPLE` = 10,000 units (items, or clusters when the test is clustered) both tests report their normal
limit. Below it nothing changes: the same draws, the same p, bit for bit; every committed result has at most 280
items and keeps its numbers. `family-test` draws its opponents from one random stream: the stream moves past an
opponent that takes the limit as if its signs were drawn, whenever a later opponent is still resampled, so a family
that mixes sizes keeps those p's too. Both commands say which way each p was found (`method`: `exact`, `sampled`,
`normal limit`). A p from the limit is not a count over draws: it is not a multiple of 1/(permutations + 1), and it
can be 0.0 (printed `<0.0001`; a consumer taking its logarithm must allow for it).

Beside it, the cost that remains below 10,000 is paid once: every `evh` command keeps its estimated p's in the
project's ignored `.cache/evh-p.jsonl`, as `evh mcp` already did (`EVH_P_CACHE` names another file; empty turns it
off). The key holds the data and the algorithm, so a kept p is never stale.

## Consequences

- Positive: at 10,000 items a comparison costs milliseconds instead of half a minute: the bench's 50-arm catalog took
  12.8 s (1,532 s before) and `family-test` 1.6 s (332.5 s); `goals` after `catalog` reads the p's the catalog drew
  (the p cache, now on by default). The intervals were already analytic above 30 items.
- Negative: below 10,000 items a first comparison still resamples, measured at 1,000 items about 1 s a sign-flip and
  2 s a bootstrap-t, at 10,000 8.1 s and 22.9 s (so up to about 23 s just below the threshold): heavy-tailed or
  sparse data need the resampling there. What a catalog, a goal or a comparison needs is drawn at once in child
  processes (`stats.prefetch`, the same p's bit for bit, each seeded by its data or its seed): the bench's 1,000-item
  catalog took 16.3 s instead of 150.4 s, with the same pages, on this 32-core machine; a machine with fewer cores
  gains less, and a container under one whole CPU (the deployment's inspector and MCP server run at `cpus: 0.5`,
  `mem_limit: 384m`) draws one by one as before: the workers are capped by the cgroup CPU quota, which the core
  count does not see, so they never multiply a capped container's memory (about 20 MB each). `EVH_WORKERS` sets it. A p from the limit is not a count over draws (above).
- Neutral: the threshold is a number the simulation supports, not a law: a kind of data the seven do not cover may
  need it higher; the tool reruns with other sizes.

## Alternatives considered

- **The limit from 1,000 items.** The simulation refutes it for heavy-tailed and sparse data.
- **Fewer resamples, or sequential stopping (Besag and Clifford).** It saves most where p is large and least near the
  decision levels, where the precision matters, and it changes the p's below 10,000 that are committed today.
- **numpy for the resampling.** A new dependency for the core (`stats` is standard library only); not asked for.
- **Only the parallel draws, no limit.** The same p's everywhere, but at 10,000 items each test still costs 8 to 23 s
  of CPU; taken beside the limit, for the sizes the limit cannot serve.
- **A faster draw of the bootstrap's picks** (the same values as `randrange`, from one `getrandbits` call): measured
  2.10 s to 1.78 s a test on Python 3.14, not worth its code.
