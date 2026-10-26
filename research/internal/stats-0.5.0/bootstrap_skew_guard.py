"""Bootstrap-t non-inferiority with a skewness guard: when the sample skewness of the paired
differences is below -1 (a long tail of losses), test at half the level (1.25% instead of 2.5%).
Type I at the margin (left skew, the failing case) and how often the guard fires; plus normal
data, where the guard should rarely fire. Companion to runner/skew_sim2.py.

python research/internal/stats-0.5.0/bootstrap_skew_guard.py
"""

import math
import random
import statistics


def draw(rng, kind, sd):
    if kind == "normal":
        return rng.gauss(0, sd)
    s = 1.0
    mean = math.exp(s * s / 2)
    scale = sd / math.sqrt((math.exp(s * s) - 1) * math.exp(s * s))
    v = (rng.lognormvariate(0, s) - mean) * scale
    return v if kind == "right" else -v


def skew(d):
    m = statistics.fmean(d)
    s = statistics.pstdev(d)
    return 0.0 if s == 0 else statistics.fmean([((x - m) / s) ** 3 for x in d])


def boot_t_lower(d, rng, level, B=400):
    n = len(d)
    m, s = statistics.fmean(d), statistics.stdev(d)
    ts = []
    for _ in range(B):
        x = [d[rng.randrange(n)] for _ in range(n)]
        sx = statistics.stdev(x)
        if sx > 0:
            ts.append((statistics.fmean(x) - m) / (sx / math.sqrt(n)))
    ts.sort()
    q = ts[min(len(ts) - 1, int((1 - level) * len(ts)))]
    return m - q * s / math.sqrt(n)


rng = random.Random(17)
N_SIM, MARGIN, SD = 1500, 0.02, 0.05
print(f"{'n':>4} {'shape':>7} {'type I':>7} {'guard fired':>11}  (nominal 0.025, {N_SIM} sims)")
for n in (10, 20, 30, 50, 100):
    for kind in ("left", "normal"):
        rej = fired = 0
        for _ in range(N_SIM):
            d = [draw(rng, kind, SD) - MARGIN for _ in range(n)]
            g = skew(d) < -1.0
            fired += g
            rej += boot_t_lower(d, rng, 0.0125 if g else 0.025) > -MARGIN
        print(f"{n:>4} {kind:>7} {rej / N_SIM:7.4f} {fired / N_SIM:11.3f}")
