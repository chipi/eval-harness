"""The bootstrap-t non-inferiority test exactly as RFC-015 specifies it, at a true difference exactly at
-margin (so every rejection is a type I error), on normal differences and on lognormal tails of losses of
several weights.

The specification: T = (m + margin)/(s/sqrt(n)); t* = (m* - m)/(s*/sqrt(n)), resamples with s* = 0 dropped;
p = (1 + #{t* >= T})/(B + 1). Skew guard: g1 = mean(((d - m)/sigma)^3) with the population sigma; g1 < -1
halves the level, and with n < 50 makes the verdict inconclusive (not a rejection). s = 0 is inconclusive.

B is 999 here, not RFC-015's 9999: at a level of 2.5% the p granularity of 0.001 does not change a decision
that matters to the error rate, and 9999 would make the grid take hours in pure Python.

python research/internal/stats-0.5.0/bootstrap_spec_check.py
"""

import math
import random
import statistics

ALPHA, MARGIN, SD, B, N_SIM = 0.025, 0.02, 0.05, 999, 1000


def draw(rng, sigma_log):
    if sigma_log is None:
        return rng.gauss(0, SD)
    mean = math.exp(sigma_log * sigma_log / 2)
    scale = SD / math.sqrt((math.exp(sigma_log * sigma_log) - 1) * math.exp(sigma_log * sigma_log))
    return -(rng.lognormvariate(0, sigma_log) - mean) * scale


def g1(d):
    m = statistics.fmean(d)
    sig = statistics.pstdev(d)
    return 0.0 if sig == 0 else statistics.fmean([((x - m) / sig) ** 3 for x in d])


def p_value(d, rng):
    n = len(d)
    m, s = statistics.fmean(d), statistics.stdev(d)
    if s == 0:
        return None
    t_obs = (m + MARGIN) / (s / math.sqrt(n))
    kept = beyond = 0
    for _ in range(B):
        x = [d[rng.randrange(n)] for _ in range(n)]
        sx = statistics.stdev(x)
        if sx == 0:
            continue
        kept += 1
        if (statistics.fmean(x) - m) / (sx / math.sqrt(n)) >= t_obs:
            beyond += 1
    return (1 + beyond) / (kept + 1)


def main():
    rng = random.Random(20261026)
    shapes = [
        ("normal", None),
        ("lognormal 0.25", 0.25),
        ("lognormal 0.5", 0.5),
        ("lognormal 0.75", 0.75),
        ("lognormal 1.0", 1.0),
    ]
    print(f"type I at the margin, nominal {ALPHA}, {N_SIM} simulations, B = {B}")
    print(f"{'n':>4} {'shape':>15} {'type I':>7} {'guard fired':>11} {'inconclusive (guard, n<50)':>27}")
    for n in (10, 20, 30, 50, 100):
        for name, sig in shapes:
            rej = fired = inconc = 0
            for _ in range(N_SIM):
                d = [-MARGIN + draw(rng, sig) for _ in range(n)]
                guard = g1(d) < -1
                fired += guard
                if guard and n < 50:
                    inconc += 1
                    continue
                p = p_value(d, rng)
                if p is not None and p <= (ALPHA / 2 if guard else ALPHA):
                    rej += 1
            print(
                f"{n:>4} {name:>15} {rej / N_SIM:>7.3f} {fired / N_SIM:>11.0%} {inconc / N_SIM:>27.0%}",
                flush=True,
            )


if __name__ == "__main__":
    main()
