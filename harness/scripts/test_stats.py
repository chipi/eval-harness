#!/usr/bin/env python3
"""Assertions for the paired test (stats.py): exact where it can count, seeded estimate above.

python scripts/test_stats.py
"""

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import itertools
import random
import statistics
import sys
from pathlib import Path

from evaluation_harness import stats
from evaluation_harness._check import check, summary


def brute_p(deltas):
    obs = abs(sum(deltas))
    hits = sum(
        1
        for signs in itertools.product((1, -1), repeat=len(deltas))
        if abs(sum(s * d for s, d in zip(signs, deltas))) >= obs - 1e-12
    )
    return hits / 2 ** len(deltas)


for n in (1, 2, 5, 9, 10, 13, 16):
    r = random.Random(n)
    d = [r.gauss(0.2, 1) for _ in range(n)]
    check(f"exact p equals counting every sign pattern (n={n})", abs(stats.exact_p(d) - brute_p(d)) < 1e-12)

check(
    "no difference at all: p is 1",
    stats.exact_p([0.0, 0.0, 0.0]) == 1.0 and stats.exact_p([0.1, -0.1, 0.05, -0.05]) == 1.0,
)
check(
    "ten identical wins: p is the smallest attainable, 2/2^10",
    abs(stats.exact_p([1.0] * 10) - 2 / 2**10) < 1e-15 and stats.min_attainable_p(10) == 2 / 2**10,
)


def estimate(deltas, rng, perms=stats.PERMUTATIONS):
    obs = statistics.fmean(deltas)
    hits = sum(
        1
        for _ in range(perms)
        if abs(statistics.fmean(d if rng.random() < 0.5 else -d for d in deltas)) >= abs(obs)
    )
    return (hits + 1) / (perms + 1)


r = random.Random(7)
d40 = [r.gauss(0.1, 1) for _ in range(40)]
check(
    "above 30 items: the pre-0.4.0 seeded estimate, bit for bit",
    stats.sign_flip_p(d40) == estimate(d40, random.Random(stats.SEED)),
)
shared, again = random.Random(5), random.Random(5)
two = [stats.sign_flip_p(d40, permutations=500, rng=shared) for _ in range(2)]
check(
    "above 30 items, a shared generator draws one stream (family_test's published numbers)",
    two == [estimate(d40, again, 500), estimate(d40, again, 500)],
)
check(
    "at or below 30 items the generator is not consumed",
    stats.sign_flip_p(d40[:30], rng=shared) == stats.exact_p(d40[:30]) and shared.random() == again.random(),
)

v = stats.holm({"a": 0.001, "b": 0.02, "c": 0.03})
check(
    "holm: steps alpha/3, alpha/2, alpha",
    [round(v[k][0], 6) for k in "abc"] == [0.016667, 0.025, 0.05] and all(v[k][1] for k in "abc"),
)
v = stats.holm({"a": 0.001, "b": 0.06, "c": 0.01})
check("holm: stops at the first p over its threshold", v["c"][1] and not v["b"][1])
check(
    "holm: a declared family larger than the p-values passed",
    stats.holm({"a": 0.02}, family=3)["a"] == (0.05 / 3, False),
)
check(
    "holm: a p exactly at its threshold is separated (family_test and bootstrap_test said not)",
    all(sep for _, sep in stats.holm({"a": 0.025, "b": 0.05}).values()),
)
_here = Path(__file__).resolve().parent
for _script in ("family_test.py", "bootstrap_test.py"):
    check(
        f"holm: {_script} uses stats.holm, so it cannot disagree with the inspector",
        "holm(" in (_here / _script).read_text() and "/ (m - i)" not in (_here / _script).read_text(),
    )

arms = {
    "base": {f"e{i}": 0.5 for i in range(10)},
    "better": {f"e{i}": 0.6 for i in range(10)},
    "one_item": {"e0": 0.9},
}
rows = {x["arm"]: x for x in stats.compare(arms, "base")["rows"]}
check(
    "compare: direction and wins",
    rows["better"]["verdict"] == "separated: better" and rows["better"]["wins"] == 10,
)
check("compare: one shared item is untestable", rows["one_item"]["verdict"] == "untestable")
low = {x["arm"]: x for x in stats.compare(arms, "base", higher_is_better=False)["rows"]}
check("compare: lower is better flips the verdict", low["better"]["verdict"] == "separated: worse")

check(
    "interval: none at 5 items (no shift can be rejected)",
    stats.exact_ci([0.1, 0.2, 0.15, 0.3, 0.25]) is None,
)
d = [0.1, 0.3, -0.05, 0.2, 0.15, 0.25, 0.12, 0.18, 0.05, 0.22]
lo, hi = stats.exact_ci(d)
check("interval: contains the mean", lo < statistics.fmean(d) < hi)
check(
    "interval: excludes zero exactly when the test separates",
    (lo > 0) == (stats.sign_flip_p(d) <= stats.ALPHA),
)
check(
    "interval: its edge is where the test starts rejecting",
    stats.sign_flip_p([x - (lo - 1e-6) for x in d])
    <= stats.ALPHA
    < stats.sign_flip_p([x - (lo + 1e-6) for x in d]),
)
r, miss = random.Random(7), 0
for _ in range(400):
    ci = stats.exact_ci([r.gauss(0, 1) for _ in range(8)])
    miss += ci[0] > 0 or ci[1] < 0
check(f"interval: misses zero at about the nominal rate under no difference ({miss}/400)", miss / 400 <= 0.08)

# compare_by: the paired test per group of items, one Holm over every (group, arm) test
# Three groups of 10 items. Arm a: p 0.0020 on short, 0.0039 on mid, 0.0156 on long; arm b ties
# the baseline in sign everywhere (p 1.0). Long alone: a's 0.0156 is under its 0.025 threshold;
# jointly (6 tests) it ranks third, under 0.0125, and is not separated.
g1, g3, g2 = ([f"i{k:02d}" for k in range(s, s + 10)] for s in (0, 10, 20))
base = dict.fromkeys(g1 + g2 + g3, 0.0)
arm_a = {
    **dict.fromkeys(g1, 1.0),
    **dict(zip(g3, [1.0] * 9 + [-0.2])),
    **dict(zip(g2, [1.0] * 7 + [-0.1] * 3)),
}
arm_b = {i: (0.1 if k % 2 else -0.1) for k, i in enumerate(g1 + g2 + g3)}
three = {"base": base, "a": arm_a, "b": arm_b}
by = stats.compare_by(three, "base", {"short": set(g1), "mid": set(g3), "long": set(g2)})
joint = {(g["group"], r["arm"]): r["p"] for g in by["groups"] for r in g["rows"] if r["p"] is not None}
want = stats.holm(joint)
check("compare_by: the family is every (group, arm) test", by["family_size"] == len(joint) == 6)
check(
    "compare_by: each threshold and verdict is the joint Holm's",
    all(
        (r["threshold"], r["verdict"].startswith("separated")) == want[(g["group"], r["arm"])]
        for g in by["groups"]
        for r in g["rows"]
        if r["p"] is not None
    ),
)
alone = {
    g: {
        r["arm"]: r["verdict"]
        for r in stats.compare({k: {i: v for i, v in s.items() if i in m} for k, s in three.items()}, "base")[
            "rows"
        ]
    }
    for g, m in (("short", set(g1)), ("mid", set(g3)), ("long", set(g2)))
}
flipped = [
    (g["group"], r["arm"])
    for g in by["groups"]
    for r in g["rows"]
    if alone[g["group"]][r["arm"]].startswith("separated") and not r["verdict"].startswith("separated")
]
check("compare_by: a group tested alone can separate where the joint correction does not", bool(flipped))
check("compare_by: items per group", [g["items"] for g in by["groups"]] == [10, 10, 10])


# The estimate's fast path (signs drawn once per item count, sums in C) must give the p the
# straightforward loop gives, bit for bit: it made the catalog build 7x faster and may move nothing.
def _loop_p(deltas, permutations=stats.PERMUTATIONS, seed=stats.SEED):
    obs = statistics.fmean(deltas)
    rng = random.Random(seed)
    hits = sum(
        1
        for _ in range(permutations)
        if abs(statistics.fmean(d if rng.random() < 0.5 else -d for d in deltas)) >= abs(obs)
    )
    return (hits + 1) / (permutations + 1)


gen = random.Random(7)
cases = [
    [gen.choice([-1.0, 0.0, 0.0, 1.0]) for _ in range(60)],  # 0/1 accuracy: ties at the threshold
    [round(gen.gauss(0.01, 0.05), 6) for _ in range(45)],
    [gen.uniform(-0.3, 0.2) for _ in range(31)],
]
check(
    "sign_flip_p: the fast estimate is the loop's p, bit for bit (ties, rounded and raw deltas)",
    all(stats.sign_flip_p(c, permutations=2000) == _loop_p(c, permutations=2000) for c in cases),
)
check(
    "sign_flip_p: the same deltas again come from the cache with the same p",
    stats.sign_flip_p(cases[1], permutations=2000) == _loop_p(cases[1], permutations=2000),
)

sys.exit(summary())
