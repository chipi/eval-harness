"""Type I error of non-inferiority tests for paired 0/1 measures at the margin, on the grid of
the final statistics review (runner/t1.py): Tango's score test (1998) beside the shifted
sign-flip test. One-sided 2.5%; the true difference equals -margin.

Tango (1998), Statistics in Medicine 17:891-908. 2x2 counts: x12 = new right / reference wrong,
x21 = new wrong / reference right, n items; delta = p12 - p21. Under H0: delta = d0,
  Z = (x12 - x21 - n*d0) / sqrt(n * (2*q21 + d0*(1 - d0)))
with q21 the restricted MLE: (sqrt(B^2 - 4AC) - B) / (2A),
  A = 2n, B = -x12 - x21 + (2n - x12 + x21)*d0, C = -x21*d0*(1 - d0).
Reject H0: delta <= d0 when Z > 1.959964.

python research/internal/stats-0.7.0/tango_binary.py
"""

import bisect
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "harness" / "scripts"))
import stats as S

Z975 = 1.959963984540054


def tango_z(x12: int, x21: int, n: int, d0: float) -> float:
    a = 2 * n
    b = -x12 - x21 + (2 * n - x12 + x21) * d0
    c = -x21 * d0 * (1 - d0)
    disc = max(b * b - 4 * a * c, 0.0)
    q21 = (math.sqrt(disc) - b) / (2 * a)
    var = n * (2 * q21 + d0 * (1 - d0))
    if var <= 0:
        return math.inf if (x12 - x21 - n * d0) > 0 else -math.inf
    return (x12 - x21 - n * d0) / math.sqrt(var)


def signflip_one_sided_p(x: list) -> float:
    n = len(x)
    obs = sum(x) - 1e-9
    h = n // 2
    left = S._signed_sums(x[:h])
    right = sorted(S._signed_sums(x[h:]))
    return sum(len(right) - bisect.bisect_left(right, obs - v) for v in left) / 2**n


GRID = [
    (16, 0.15, 0.05),
    (16, 0.30, 0.20),
    (24, 0.15, 0.05),
    (24, 0.05, 0.0),
    (30, 0.12, 0.02),
    (50, 0.12, 0.02),
    (100, 0.12, 0.02),
    (200, 0.05, 0.0),
    (200, 0.12, 0.02),
]
N_SIM = 3000
rng = random.Random(7)
print(
    f"{'n':>4} {'P(-1)':>6} {'P(+1)':>6} {'margin':>6}  {'tango':>7} {'signflip':>8}   (nominal 0.025, {N_SIM} sims)"
)
for n, pm, pp in GRID:
    m = pm - pp
    rej_t = rej_s = 0
    for _ in range(N_SIM):
        d = [-1 if (u := rng.random()) < pm else (1 if u < pm + pp else 0) for _ in range(n)]
        x12 = d.count(1)
        x21 = d.count(-1)
        rej_t += tango_z(x12, x21, n, -m) > Z975
        if n <= 30:
            rej_s += signflip_one_sided_p([v + m for v in d]) <= 0.025
    sf = f"{rej_s / N_SIM:8.4f}" if n <= 30 else "     n/a"
    print(f"{n:>4} {pm:>6} {pp:>6} {m:>6.2f}  {rej_t / N_SIM:7.4f} {sf}")
