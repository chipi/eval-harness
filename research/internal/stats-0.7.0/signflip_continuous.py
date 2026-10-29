"""Type I error of the shifted sign-flip non-inferiority test on CONTINUOUS paired differences
whose mean is exactly -margin: symmetric (normal) vs skewed (centred lognormal, both tails).
One-sided 2.5%. Exact enumeration up to 30 items (stats._signed_sums), as runner/tango_sim.py.

python research/internal/stats-0.7.0/signflip_continuous.py
"""

import bisect
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "harness" / "scripts"))
import stats as S


def p_one_sided(x: list) -> float:
    n = len(x)
    obs = sum(x) - 1e-12
    h = n // 2
    left = S._signed_sums(x[:h])
    right = sorted(S._signed_sums(x[h:]))
    return sum(len(right) - bisect.bisect_left(right, obs - v) for v in left) / 2**n


def draw(rng: random.Random, kind: str, sd: float) -> float:
    if kind == "normal":
        return rng.gauss(0, sd)
    s = 1.0  # lognormal shape: mean exp(s^2/2), sd sqrt((exp(s^2)-1) exp(s^2))
    mean = math.exp(s * s / 2)
    scale = sd / math.sqrt((math.exp(s * s) - 1) * math.exp(s * s))
    v = (rng.lognormvariate(0, s) - mean) * scale
    return v if kind == "right" else -v


rng = random.Random(11)
N_SIM, MARGIN, SD = 2000, 0.02, 0.05
print(f"{'n':>4} {'shape':>7}  type I  (nominal 0.025, mean delta = -margin, sd {SD}, {N_SIM} sims)")
for n in (10, 20, 30):
    for kind in ("normal", "right", "left"):
        rej = 0
        for _ in range(N_SIM):
            d = [draw(rng, kind, SD) - MARGIN for _ in range(n)]
            rej += p_one_sided([v + MARGIN for v in d]) <= 0.025
        print(f"{n:>4} {kind:>7}  {rej / N_SIM:.4f}")
