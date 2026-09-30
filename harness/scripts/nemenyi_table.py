#!/usr/bin/env python3
"""The Nemenyi critical values, computed rather than copied. Stdlib only, $0.

    python scripts/nemenyi_table.py            # print the table and the check
    python scripts/nemenyi_table.py --max 40   # extend it

WHY THIS EXISTS

  `leaderboard.py` carried 24 values transcribed from Demsar (2006), k = 2..25, and
  REFUSED to print a critical difference above k = 25 rather than reuse a smaller k's
  value -- which would understate the CD and overstate how many pairs differ.

  The refusal was right and the scope was wrong. Four of this repo's five experiments
  have 26-28 arms, so four of five had no pairwise verdict at all, and two reports
  published CDs from the pre-refusal code that were biased toward significance. An
  external reviewer pointed out that the values are about thirty lines of stdlib.

WHAT IS COMPUTED

  The Nemenyi CD is  q_alpha * sqrt(k(k+1) / 6N), where q_alpha is the studentised
  range statistic at infinite degrees of freedom divided by sqrt(2). For k independent
  standard normals the range R has

      P(R <= q) = k * INTEGRAL phi(z) [Phi(z) - Phi(z - q)]^(k-1) dz

  which is a one-dimensional integral of smooth bounded functions -- Simpson over
  [-9, 9] is far more accuracy than three decimals needs. Bisect for the q where the
  CDF is 1 - alpha.

  Infinite degrees of freedom is the right table here and not an approximation for
  convenience: the Friedman/Nemenyi procedure compares MEAN RANKS over N items, and
  the reference distribution for those is the studentised range with nu = infinity.

HOW IT IS CHECKED

  Against the 24 published values it replaces. Worst disagreement 0.0007, which is
  below the precision Demsar prints. `test_nemenyi_table` in the self-test asserts
  that, so a change to this file that moved the numbers would fail rather than quietly
  restate the literature.
"""

from __future__ import annotations

import argparse
import math

SQRT2 = math.sqrt(2.0)

#: Demsar (2006), Table 5(a), alpha = 0.05. Kept ONLY as the validation target.
PUBLISHED = {
    2: 1.960, 3: 2.343, 4: 2.569, 5: 2.728, 6: 2.850, 7: 2.949, 8: 3.031, 9: 3.102,
    10: 3.164, 11: 3.219, 12: 3.268, 13: 3.313, 14: 3.354, 15: 3.391, 16: 3.426,
    17: 3.458, 18: 3.489, 19: 3.517, 20: 3.544, 21: 3.569, 22: 3.593, 23: 3.616,
    24: 3.637, 25: 3.658,
}


def _phi(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _Phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def studentised_range_cdf(q: float, k: int, lo: float = -9.0, hi: float = 9.0,
                          n: int = 4000) -> float:
    """P(range of k iid standard normals <= q), nu = infinity. Simpson, n even."""
    if q <= 0:
        return 0.0
    h = (hi - lo) / n
    total = 0.0
    for i in range(n + 1):
        z = lo + i * h
        weight = 1 if i in (0, n) else (4 if i % 2 else 2)
        total += weight * _phi(z) * (_Phi(z) - _Phi(z - q)) ** (k - 1)
    return k * total * h / 3.0


def q_alpha(k: int, alpha: float = 0.05) -> float:
    """The Nemenyi constant for k arms: studentised range / sqrt(2)."""
    lo, hi = 0.1, 12.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if studentised_range_cdf(mid, k) < 1.0 - alpha:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi) / SQRT2


def table(k_max: int = 40, alpha: float = 0.05) -> dict:
    return {k: round(q_alpha(k, alpha), 4) for k in range(2, k_max + 1)}


def max_error_against_published() -> float:
    """Worst absolute disagreement with Demsar over k = 2..25."""
    return max(abs(q_alpha(k) - v) for k, v in PUBLISHED.items())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--alpha", type=float, default=0.05)
    args = ap.parse_args()

    err = max_error_against_published()
    print(f"  validation against Demsar (2006), k = 2..25:")
    print(f"    worst absolute disagreement: {err:.4f}   "
          f"({'OK' if err < 0.002 else 'TOO LARGE'})\n")
    t = table(args.max, args.alpha)
    print(f"  alpha = {args.alpha}, nu = infinity")
    for k in sorted(t):
        mark = "" if k in PUBLISHED else "   <- beyond the published table"
        print(f"    {k:>3}: {t[k]:.4f}{mark}")
    return 0 if err < 0.002 else 1


if __name__ == "__main__":
    raise SystemExit(main())
