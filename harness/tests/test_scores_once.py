#!/usr/bin/env python3
"""Each arm's scores read once per view and per build (scores_once).

    python tests/test_scores_once.py

On this repository's runs, `evh goal-list` read 1,054 arms' scores for 686 arms (the collect, the goals' groups and the
adapter's own `describe` asking again): 79% of its CPU, which the evals MCP server pays at cpus 0.5 on every fresh
call. With a counting adapter behind the views' loader: no arm's scores are read twice by a view or by a catalog
build, the adapter's own methods included (a wrapper around it missed those: arms read three times).
"""

import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

# reads this repository's own committed runs (harness/data), which are files by definition
os.environ["EVAL_STORE"] = "files"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _ops
import _ops
from evaluation_harness import catalog_build as cb
from evaluation_harness._check import check, summary
from evaluation_harness._rounds import load_rounds
from evaluation_harness.catalog_adapter import HarnessAdapter, scores_once
from evaluation_harness.model import rounds as model_rounds

READS: Counter = Counter()  # each arm's scores reads, by Counting


def narrowed() -> Counter:
    """How many rounds read each arm through only the runs they recorded, fewer than the arm has (a later run joined to
    it, a repeat of the same measurement, RFC-041 F2): each such round view reads the arm's scores once for itself."""
    found: Counter = Counter()
    adapter = HarnessAdapter()
    for rnd in load_rounds():
        for a in model_rounds.arms(rnd):
            arm = model_rounds.arm_id(rnd, a)
            if a.get("runs") and {adapter._run_id(d) for d in adapter._dirs(arm)} - set(a["runs"]):
                found[arm] += 1
    return found


EXTRA = narrowed()


class Counting(HarnessAdapter):
    """The harness's adapter, counting each arm's scores reads."""

    def scores(self, arm, rescore=False):
        READS[arm] += 1
        return super().scores(arm, rescore)


# The memo itself: one read for two asks, the same dict back, the adapter's own methods reading it too.
inner = Counting()
arm = next(iter(inner.arms()))
READS.clear()
w = scores_once(inner)
first, again = w.scores(arm), w.scores(arm)
check(
    "scores_once: an arm asked twice is read once, the same answer both times, by the adapter's own methods too",
    READS[arm] == 1 and first is again and w is inner and w.describe(arm) is not None and READS[arm] == 1,
    dict(READS),
)

# A view: evh goal-list, in this process, with the counting adapter behind it (scores read once per arm, as the
# project's shared adapter does).
READS.clear()
_ops.result("goal-list", scores_once(Counting()))
twice = {a: n for a, n in READS.items() if n > 1 + EXTRA[a]}
check(
    f"evh goal-list: no arm's scores read twice ({len(READS)} arms read)",
    READS and not twice,
    dict(list(twice.items())[:5]),
)

# A build: every page, each arm read once.
READS.clear()
with tempfile.TemporaryDirectory() as out:
    cb.build(Counting(), Path(out) / "catalog")
twice = {a: n for a, n in READS.items() if n > 1 + EXTRA[a]}
check(
    f"catalog build: no arm's scores read twice, but once for each round that reads it narrower ({len(READS)} arms read)",
    READS and not twice,
    dict(list(twice.items())[:5]),
)

sys.exit(summary())
