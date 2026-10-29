"""Non-inferiority on CONTINUOUS paired differences with mean exactly -margin: type I error of
(a) the paired t-test, (b) the studentized (bootstrap-t) bootstrap, one-sided 2.5%, under normal,
right-skewed and left-skewed differences. Companion to runner/skew_sim.py (the shifted sign-flip).

python research/internal/stats-0.7.0/ttest_bootstrap_continuous.py
"""

import math
import random
import statistics

T975 = {10: 2.262157, 20: 2.093024, 30: 2.045230, 50: 2.009575, 100: 1.984217, 200: 1.971957}


def draw(rng, kind, sd):
    if kind == "normal":
        return rng.gauss(0, sd)
    s = 1.0
    mean = math.exp(s * s / 2)
    scale = sd / math.sqrt((math.exp(s * s) - 1) * math.exp(s * s))
    v = (rng.lognormvariate(0, s) - mean) * scale
    return v if kind == "right" else -v


def t_reject(d, margin):
    n = len(d)
    m, s = statistics.fmean(d), statistics.stdev(d)
    return s > 0 and (m + margin) / (s / math.sqrt(n)) > T975[n]


def boot_t_reject(d, margin, rng, B=400):
    n = len(d)
    m, s = statistics.fmean(d), statistics.stdev(d)
    if s == 0:
        return m > -margin
    ts = []
    for _ in range(B):
        x = [d[rng.randrange(n)] for _ in range(n)]
        sx = statistics.stdev(x)
        if sx > 0:
            ts.append((statistics.fmean(x) - m) / (sx / math.sqrt(n)))
    ts.sort()
    q = ts[int(0.975 * len(ts)) - 1]
    lower = m - q * s / math.sqrt(n)
    return lower > -margin


rng = random.Random(13)
N_SIM, MARGIN, SD = 1500, 0.02, 0.05
print(f"{'n':>4} {'shape':>7} {'t-test':>7} {'boot-t':>7}  (nominal 0.025, {N_SIM} sims)")
for n in (10, 20, 30, 50, 100):
    for kind in ("normal", "right", "left"):
        rt = rb = 0
        for _ in range(N_SIM):
            d = [draw(rng, kind, SD) - MARGIN for _ in range(n)]
            rt += t_reject(d, MARGIN)
            rb += boot_t_reject(d, MARGIN, rng)
        print(f"{n:>4} {kind:>7} {rt / N_SIM:7.4f} {rb / N_SIM:7.4f}")
