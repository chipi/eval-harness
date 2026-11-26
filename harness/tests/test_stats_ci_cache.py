#!/usr/bin/env python3
"""The exact interval of a pair is worked out once (the Workbench's eval screen read "Reading the chart…" for 2.5 s).

    python tests/test_stats_ci_cache.py

Inverting the sign-flip test (`cluster_ci`, up to EXACT_UP_TO units) is a bisection of ~60 exact p-values, about half a
second at 15 items; the intervals, items and latency charts of one dataset each ran it for the same arms. The same
differences give the same interval, so the second chart asks the first one's answer.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation_harness import stats
from evaluation_harness._check import check, summary

deltas = [0.31, -0.05, 0.22, 0.4, 0.18, -0.12, 0.27, 0.09, 0.35, 0.02, 0.14, -0.08, 0.2, 0.11, 0.3]
calls = {"n": 0}
real = stats.exact_p


def counting(d):
    calls["n"] += 1
    return real(d)


stats.exact_p = counting
first = stats.cluster_ci(deltas, [1] * len(deltas))
made = calls["n"]
again = stats.cluster_ci(list(deltas), [1] * len(deltas))
check(
    "the exact interval of the same differences is worked out once: the second ask runs no test and answers the same",
    made > 30 and calls["n"] == made and again == first and first is not None and first[0] < first[1],
    (made, calls["n"], first, again),
)
again[0] = 99.0
check(
    "the answer kept is not the caller's to change",
    stats.cluster_ci(deltas, [1] * len(deltas)) == first,
    first,
)
calls["n"] = 0
other = stats.cluster_ci([*deltas[:-1], 0.31], [1] * len(deltas))
check("other differences are worked out", calls["n"] > 30 and other != first, (calls["n"], other))

# the server asks on many threads at once: each gets the interval, and it is worked out once, not once per thread
stats._CI.clear()
fresh = [0.5 - i * 0.03 for i in range(16)]
calls["n"] = 0
alone = stats.cluster_ci(fresh, [1] * 16)
single = calls["n"]
stats._CI.clear()
calls["n"] = 0
got: list = []
threads = [threading.Thread(target=lambda: got.append(stats.cluster_ci(fresh, [1] * 16))) for _ in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check(
    "four threads asking at once for the same interval run its tests once, as one thread does",
    len(got) == 4 and all(g == alone for g in got) and single > 30 and calls["n"] == single,
    (single, calls["n"]),
)
stats.exact_p = real
sys.exit(summary())
