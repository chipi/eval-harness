#!/usr/bin/env python3
"""The tests' p-values on several threads at once (RFC-040: the server renders the catalog's pages in its own process,
beside the API's threads, and keeps each goal's decisions for the state of the data).

    python tests/test_stats_threads.py

  - a p asked for on one thread while another thread is inside `prefetch` (collecting the tests it will draw) is the
    real p, never prefetch's stand-in: a thread's collecting is its own;
  - many threads asking for many p's at once, more than the in-process caches keep, all get the p a single thread
    gets, and none raises (the caches' check-then-move raced their eviction).
"""

import os
import random
import sys
import threading
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
os.environ["EVH_P_CACHE"] = ""  # computed here, not read back from a file
from evaluation_harness import stats  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

# Between the exact test and the normal limit: an estimate, the kind prefetch collects.
N = stats.EXACT_UP_TO + 10
rng = random.Random(3)
deltas = [0.05 + rng.random() * 0.1 for _ in range(N)]  # all one way: a p far below 1
alone = stats.sign_flip_p(deltas)
stats._P.clear()

entered, release = threading.Event(), threading.Event()


def collecting() -> None:
    entered.set()
    release.wait(30)


t = threading.Thread(target=lambda: stats.prefetch(collecting))
t.start()
entered.wait(30)
during = stats.sign_flip_p(deltas)
release.set()
t.join(30)
check(
    "a p asked for while another thread is inside prefetch is the real p, not its stand-in",
    during == alone and during < 0.01,
    (during, alone),
)

# More distinct tests than the caches keep, on eight threads, each asked twice.
stats._P.clear()
cases = [[(k % 7 + 1) * 0.01 + random.Random(k).random() * 0.1 for _ in range(N)] for k in range(300)]
expected = {k: stats.sign_flip_p(c) for k, c in enumerate(cases)}
saved = stats._P_MAX
stats._P_MAX = 16  # eviction on nearly every call
stats._P.clear()
wrong: list = []
errors: list = []


def worker(ks: list[int]) -> None:
    for k in ks:
        try:
            if stats.sign_flip_p(cases[k]) != expected[k]:
                wrong.append(k)
        except Exception as exc:  # noqa: BLE001 - reported by the check
            errors.append(repr(exc))


order = list(range(300)) * 2
random.Random(5).shuffle(order)
threads = [threading.Thread(target=worker, args=(order[i::8],)) for i in range(8)]
for th in threads:
    th.start()
for th in threads:
    th.join(300)
stats._P_MAX = saved
check(
    "eight threads, 600 asks, the cache evicting on nearly every one: every p is the single thread's, none raises",
    not wrong and not errors,
    (wrong[:5], errors[:3]),
)
sys.exit(summary())
