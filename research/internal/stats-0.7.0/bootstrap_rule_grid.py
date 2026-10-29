"""Raw material for choosing the bootstrap-t's small-sample rule: for each sample size and shape, simulate the
paired differences at the margin (the null: every rejection is an error) and at no difference (the alternative:
a rejection is power), and record each simulation's skewness g1 and the bootstrap-t p (RFC-015's definition,
B = 999). Rules (a skew threshold, a level for skewed data, a minimum n) are then scored on the same simulations by
bootstrap_rule_eval.py, so the comparison between rules is not blurred by different random draws.

python research/internal/stats-0.7.0/bootstrap_rule_grid.py N OUT.jsonl
"""

import json
import math
import random
import statistics
import sys

MARGIN, SD, B, N_SIM = 0.02, 0.05, 999, 1000
SHAPES = [
    ("normal", None),
    ("lognormal 0.25", 0.25),
    ("lognormal 0.5", 0.5),
    ("lognormal 0.75", 0.75),
    ("lognormal 1.0", 1.0),
]


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
    n, out = int(sys.argv[1]), sys.argv[2]
    rng = random.Random(1000 + n)
    with open(out, "w", encoding="utf-8") as f:
        for name, sig in SHAPES:
            for truth, shift in (("null", -MARGIN), ("alt", 0.0)):
                for _ in range(N_SIM):
                    d = [shift + draw(rng, sig) for _ in range(n)]
                    f.write(
                        json.dumps(
                            {
                                "n": n,
                                "shape": name,
                                "truth": truth,
                                "g1": round(g1(d), 4),
                                "p": p_value(d, rng),
                            }
                        )
                        + "\n"
                    )
            f.flush()
            print(f"n={n} {name} done", flush=True)


if __name__ == "__main__":
    main()
