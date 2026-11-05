#!/usr/bin/env python3
"""The non-inferiority tests behind contenders (`stats.noninferior`, PLAN_0.8.0 A2).

    python tests/test_noninferiority.py

Tango's score test agrees with the simulation's copy (research/internal/stats-0.8.0/tango_binary.py) and
is used for 0/1 scores; a continuous measure below 100 items, or 100 clusters, is "too few", never a guess;
identical arms are tested like any (60 identical items cannot show a 0.02 margin, 600 can). Simulated at a true difference exactly at -margin, the bootstrap-t at half
the level keeps its error at or below the one-sided 2.5% it stands for, with one item per unit and with
clusters of 3 (B reduced to 499 here to keep the test near 30 s; the p granularity, 1/500, is under the
level).
"""

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import stats
from evaluation_harness._check import check, summary


def tango_z_sim(x12, x21, n, d0):  # the simulation's formula, copied to compare against
    a = 2 * n
    b = -x12 - x21 + (2 * n - x12 + x21) * d0
    c = -x21 * d0 * (1 - d0)
    q21 = (math.sqrt(max(b * b - 4 * a * c, 0.0)) - b) / (2 * a)
    return (x12 - x21 - n * d0) / math.sqrt(n * (2 * q21 + d0 * (1 - d0)))


ok = all(
    abs(stats.tango_p(x12, x21, n, m) - 0.5 * math.erfc(tango_z_sim(x12, x21, n, -m) / math.sqrt(2))) < 1e-12
    for x12, x21, n, m in [(3, 5, 40, 0.1), (0, 2, 24, 0.05), (10, 4, 200, 0.02), (0, 0, 30, 0.1)]
)
check("tango_p is the simulations' Tango score test", ok)

a = {f"i{k}": float(k % 2) for k in range(60)}
same = stats.noninferior(a, dict(a), 0.02)
check(
    "0/1 scores use Tango at any size; 60 identical items cannot show a gap under 0.02 (decide counts "
    "identical arms as contenders on their own)",
    same["method"] == "tango" and same["verdict"] == "not shown" and 0.1 < same["p"] < 0.2,
    same,
)
big = {f"i{k}": float(k % 2) for k in range(600)}
check(
    "600 identical 0/1 items do show it",
    stats.noninferior(big, dict(big), 0.02)["verdict"] == "non-inferior",
    stats.noninferior(big, dict(big), 0.02),
)
cont = {f"i{k}": 0.5 + k / 1000 for k in range(60)}
few = stats.noninferior(cont, {i: v - 0.001 for i, v in cont.items()}, 0.02)
check(
    "a continuous measure on 60 items is 'too few', with no p",
    few["verdict"] == "too few" and few["p"] is None,
    few,
)
clus = stats.noninferior(a, dict(a), 0.02, clusters={i: i[:2] for i in a})
check(
    "with clusters, 0/1 scores are tested as clustered sums: 'too few' below 100 clusters",
    clus["verdict"] == "too few",
    clus,
)
worse = {i: v - 0.2 for i, v in {f"i{k}": 0.5 + (k % 7) / 10 for k in range(150)}.items()}
ref = {f"i{k}": 0.5 + (k % 7) / 10 for k in range(150)}
far = stats.noninferior(worse, ref, 0.02)
check("an arm 0.2 worse is not shown non-inferior at a 0.02 margin", far["verdict"] == "not shown", far)
one = stats.noninferior(big, dict(big), 0.02, clusters={i: i for i in big})
check(
    "clusters of one item each are the item-level test exactly: Tango, as without clusters",
    one["method"] == "tango" and one == stats.noninferior(big, dict(big), 0.02),
    one,
)
ref150 = {f"u{k}": 0.5 + (k % 9) / 20 for k in range(300)}
arm150 = {i: v - 0.001 for i, v in ref150.items()}
uneven = {
    i: ("big" if k < 120 else i) for k, i in enumerate(ref150)
}  # 1 cluster of 120 + 180 of 1: ~2.2 effective
eq = {i: f"c{k // 3}" for k, i in enumerate(ref150)}  # 100 clusters of 3
u = stats.noninferior(arm150, ref150, 0.02, clusters=uneven)
q = stats.noninferior(arm150, ref150, 0.02, clusters=eq)
check(
    "clusters of unequal size need 250 effective clusters; 100 equal ones are enough",
    u["verdict"] == "too few"
    and u["floor"] == stats.NONINF_MIN_UNEQUAL
    and q["floor"] == stats.NONINF_MIN_UNITS
    and q["verdict"] != "too few",
    (u, q),
)

# One family at one level: a 0/1 candidate (Tango at 0.025) and a continuous one (bootstrap-t at 0.0125) are judged
# together, the bootstrap-t's p doubled, not both at the first one's level.
from evaluation_harness import axes  # noqa: E402

ids = [f"m{k:03d}" for k in range(150)]
lead_v = {i: float(k % 5 != 0) for k, i in enumerate(ids)}
bin_v = dict(lead_v)
cont_v = {i: v - 0.01 + (0.004 if k % 2 else -0.004) for k, (i, v) in enumerate(lead_v.items())}


def scored(label, vals):
    return {"label": label, "flags": [], "scores": {"q": {"values": vals}}}


goal = {
    "success_criteria": {
        "primary": {"measure": "q", "direction": "higher"},
        "axes": {"quality": {"margin": 0.1}},
    }
}
d = axes.decide(goal, {"L": scored("A", lead_v), "B": scored("B", bin_v), "C": scored("C", cont_v)})
tb, tc = d["rows"]["B"]["quality"]["noninferior"], d["rows"]["C"]["quality"]["noninferior"]
check(
    "a mixed group: each test keeps its own level, and Holm's threshold is reported in it",
    tb["method"] == "tango"
    and tc["method"] == "bootstrap-t"
    and tc["level"] == stats.NONINF_LEVEL / 2
    and tc["holm_threshold"] <= stats.NONINF_LEVEL / 2 + 1e-12
    and tb["holm_threshold"] <= stats.NONINF_LEVEL + 1e-12,
    (tb, tc),
)

MARGIN, SD = 0.02, 0.05


def type_one(units: int, per: int, sims: int, rng: random.Random) -> float:
    """Share of rejections at a true difference of exactly -MARGIN (each a type I error)."""
    rej = 0
    for _ in range(sims):
        totals, sizes = [], []
        for _u in range(units):
            shift = rng.gauss(0, SD) if per > 1 else 0.0
            vals = [-MARGIN + shift + rng.gauss(0, SD) for _ in range(per)]
            totals.append(math.fsum(vals))
            sizes.append(per)
        p = stats.bootstrap_t_p(totals, sizes, MARGIN, draws=499)
        rej += p is not None and p <= stats.NONINF_LEVEL / 2
    return rej / sims


rng = random.Random(20261105)
e1 = type_one(100, 1, 300, rng)
check(f"bootstrap-t at the margin, 100 items: error {e1:.3f} <= 0.025 (+ Monte Carlo 0.009)", e1 <= 0.034)
e3 = type_one(100, 3, 300, rng)
check(
    f"bootstrap-t at the margin, 100 clusters of 3: error {e3:.3f} <= 0.025 (+ Monte Carlo 0.009)",
    e3 <= 0.034,
)
sys.exit(summary())
