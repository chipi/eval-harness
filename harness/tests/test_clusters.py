#!/usr/bin/env python3
"""The clustered paired test (`stats.clustered`, `cluster_ci`, `compare(clusters=)`).

    python tests/test_clusters.py

One item per cluster is the item-level test exactly. When items share a cluster and the clusters
differ by chance, testing items one by one rejects a true "no difference" far more often than 5%;
the cluster test stays near 5% (a seeded simulation, about 10 s). The large-sample interval is the
cluster-robust one, checked against the formula by hand.
"""

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import stats
from evaluation_harness._check import check, summary

rng = random.Random(7)
d = [rng.gauss(0.05, 0.2) for _ in range(20)]
items = {f"i{k:02d}": v for k, v in enumerate(d)}
totals, sizes = stats.clustered(items, {})
check("no cluster keys: every item is its own cluster", sizes == [1] * 20 and sorted(totals) == sorted(d))
check(
    "one item per cluster: the interval is exact_ci's",
    all(
        abs(a - b) < 1e-9
        for a, b in zip(stats.cluster_ci(totals, sizes), stats.exact_ci(list(items.values())), strict=True)
    ),
)
base = dict.fromkeys(items, 0.0)
plain = stats.compare({"a": items, "b": base}, "b")["rows"][0]
own = stats.compare({"a": items, "b": base}, "b", clusters={i: i for i in items})["rows"][0]
check(
    "one item per cluster: compare gives the same p and verdict",
    plain["p"] == own["p"] and plain["verdict"] == own["verdict"] and own["clusters"] == 20,
    (plain["p"], own["p"]),
)

grouped = stats.clustered({"a": 1.0, "b": 2.0, "c": 4.0, "d": -1.0}, {"a": "x", "b": "x", "c": "y"})
check(
    "a cluster sums its items; an item with no key stands alone",
    sorted(zip(*grouped, strict=True)) == [(-1.0, 1), (3.0, 2), (4.0, 1)],
    grouped,
)

# CR1 by hand on 40 clusters of 3.
g_tot = [rng.gauss(0.1, 1.0) for _ in range(40)]
g_size = [3] * 40
n = sum(g_size)
mean = sum(g_tot) / n
var = 40 / 39 * sum((t - m * mean) ** 2 for t, m in zip(g_tot, g_size, strict=True)) / n**2
z = 1.959964
t = z + (z**3 + z) / (4 * 39)
lo, hi = stats.cluster_ci(g_tot, g_size)
check(
    "above 30 clusters: the cluster-robust (CR1) interval",
    abs(lo - (mean - t * math.sqrt(var))) < 1e-12 and abs(hi - (mean + t * math.sqrt(var))) < 1e-12,
)
check("below 2 clusters there is no interval", stats.cluster_ci([1.0], [5]) is None)


# Type I error with clusters: 12 clusters of 5 items, a cluster effect (sd 1) and item noise (sd 0.3),
# no true difference. Exact cluster test (12 <= 30); the item-level test sees 60 "independent" items.
def draw(r):
    out, keys = {}, {}
    for c in range(12):
        shift = r.gauss(0, 1.0)
        for k in range(5):
            iid = f"c{c}_{k}"
            out[iid] = shift + r.gauss(0, 0.3)
            keys[iid] = f"c{c}"
    return out, keys


sim = random.Random(20261105)
runs = 400
naive_runs = 100  # the item-level test estimates p by 20,000 permutations: the slow side, and far off anyway
naive = clus = 0
for k in range(runs):
    a, keys = draw(sim)
    b = dict.fromkeys(a, 0.0)
    if k < naive_runs:
        naive += stats.compare({"a": a, "b": b}, "b")["rows"][0]["p"] <= stats.ALPHA
    clus += stats.compare({"a": a, "b": b}, "b", clusters=keys)["rows"][0]["p"] <= stats.ALPHA
check(
    f"no true difference, clustered items: the item-level test rejects far above 5% ({naive / naive_runs:.2f})",
    naive / naive_runs > 0.25,
)
check(
    f"... and the cluster test stays near 5% ({clus / runs:.3f}; Monte Carlo sd about 0.011)",
    clus / runs <= 0.075,
)
sys.exit(summary())
