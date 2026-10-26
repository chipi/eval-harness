"""The final statistics review's check: type I error of the shifted sign-flip non-inferiority
test on paired 0/1 differences at the margin, one-sided 2.5%.

python research/internal/stats-0.5.0/signflip_binary.py
"""

import bisect
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "harness" / "scripts"))
import stats as S


def p1(x):
    n = len(x)
    obs = sum(x) - 1e-9
    h = n // 2
    L = S._signed_sums(x[:h])
    R = sorted(S._signed_sums(x[h:]))
    return sum(len(R) - bisect.bisect_left(R, obs - v) for v in L) / 2**n


rng = random.Random(7)
for n, (pm, pp) in [
    (16, (0.15, 0.05)),
    (16, (0.30, 0.20)),
    (24, (0.15, 0.05)),
    (24, (0.05, 0.0)),
    (30, (0.12, 0.02)),
]:
    m = pm - pp
    rej = 0
    N = 3000
    for _ in range(N):
        d = [-1 if (u := rng.random()) < pm else (1 if u < pm + pp else 0) for _ in range(n)]
        rej += p1([x + m for x in d]) <= 0.025
    print(f"n={n} P(-1)={pm} P(+1)={pp} true delta=-margin={-m:.2f}: type I = {rej / N:.4f} (nominal 0.025)")
