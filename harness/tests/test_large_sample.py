#!/usr/bin/env python3
"""The paired tests at 10,000 items and more (PLAN_0.8.0 S2, ADR-0028): the normal limit, not resampling.

    python tests/test_large_sample.py

tools/large_sample_check.py measured, over seven kinds of data, the normal approximation against the harness's
resampled p: at 10,000 units it agrees within the resampling's own Monte Carlo error, at 1,000 to 5,000 it does not
for heavy-tailed or sparse data. So from LARGE_SAMPLE units the sign-flip p is erfc(|z| / sqrt 2), z = sum d /
sqrt(sum d^2), and the bootstrap-t p is 1 - Phi(T) with the same cluster-robust se; below it nothing changes.
"""

import math
import random
import sys
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness import stats  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

N = stats.LARGE_SAMPLE
rng = random.Random(7)
d = [rng.gauss(0.004, 0.2) for _ in range(N)]
s, q = math.fsum(d), math.fsum(x * x for x in d)
t0 = time.time()
p = stats.sign_flip_p(d)
fast = time.time() - t0
check(
    f"sign-flip at {N} items: the normal limit, in well under a second",
    p == math.erfc(abs(s) / math.sqrt(q) / math.sqrt(2)) and fast < 0.5,
    (p, fast),
)
below = d[: N - 1]
t0 = time.time()
p_below = stats.sign_flip_p(below, permutations=2000)
s2, q2 = math.fsum(below), math.fsum(x * x for x in below)
check(
    f"below {N} items: resampled as before (a count over the permutations, not the formula)",
    p_below != math.erfc(abs(s2) / math.sqrt(q2) / math.sqrt(2)) and round(p_below * 2001) == p_below * 2001,
    p_below,
)
m, se = stats._mean_se(d, [1] * N)
t0 = time.time()
pb = stats.bootstrap_t_p(d, [1] * N, 0.01)
fast = time.time() - t0
check(
    f"bootstrap-t at {N} units: 1 - Phi(T), in well under a second",
    pb == 0.5 * math.erfc(((m + 0.01) / se) / math.sqrt(2)) and fast < 0.5,
    (pb, fast),
)
clustered = [sum(d[i : i + 3]) for i in range(0, 3 * (N // 3), 3)]
pc = stats.bootstrap_t_p(clustered, [3] * len(clustered), 0.01)
check(
    f"clusters are the units: {len(clustered)} clusters of 3 are below {N}, so they are resampled",
    len(clustered) < N and pc is not None and pc != 0.5 * math.erfc(0),
    pc,
)
check("no difference at all is still no test", stats.bootstrap_t_p([0.0] * N, [1] * N, 0.01) is None)
check("all differences zero: p 1", stats.sign_flip_p([0.0] * N) == 1.0)
sys.exit(summary())
