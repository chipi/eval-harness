"""The metric `comparison-show` compares on when none is named, on stub adapters (the fleet's G2, 2026-11-18, and its
review, 2026-11-19): the compared arms' own primary metric among those every arm scores; a primary some arm lacks said
so, never in silence; a metric named with its reference (`oracle_pass vs gold`) is that metric.

    python tests/test_compare_default.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation_harness._check import check, summary
from evaluation_harness.model import compare as C

V = {"values": {"i1": 1.0, "i2": 0.0}, "source": "recorded"}


class Fake:
    item_word = "item"
    shape_metrics = ("latency_ms",)
    can_rescore = False
    preferred_metrics = ()

    def __init__(self, primary: dict, keys: dict):
        self.primary, self.keys = primary, keys

    def arms(self):
        return list(self.primary)

    def describe(self, a):
        return {"id": a, "label": a.rsplit("/", 1)[1], "dataset": "ds", "primary": self.primary[a]}

    def scores(self, a, rescore=False):
        return dict.fromkeys(self.keys[a], V)

    def recorded_means(self, a):
        return {}

    def is_neutral(self, k, ds=None):
        return False

    def reference_format(self, r):
        return ""

    def output_format(self, a):
        return {"asked": ""}


def pick(primary: dict, keys: dict) -> tuple[str, str | None]:
    C.A = Fake(primary, keys)  # type: ignore[assignment]  # a stub with the methods compare reads
    arms = list(primary)
    per_arm = {a: C.A.scores(a) for a in arms}
    counts = Counter(k for s in per_arm.values() for k in s)
    m = C._default_metric(counts, per_arm, arms, "", "ds")
    return m, C._primary_not_read(arms, m, per_arm)


m, note = pick(
    {"runs/ds/a": "x", "runs/ds/b": "y", "runs/ds/c": "z"},
    {"runs/ds/a": ["x", "w"], "runs/ds/b": ["y", "w"], "runs/ds/c": ["z", "w"]},
)
check(
    "arms with different primaries, each scored by one arm: the metric every arm scores, not one arm's primary",
    m == "w" and note is not None and "has no score per item for b, c as read" in note,
    (m, note),
)

m, note = pick(
    {"runs/ds/a": "oracle_pass", "runs/ds/b": "oracle_pass"},
    {"runs/ds/a": ["oracle_pass vs gold", "actionable"], "runs/ds/b": ["oracle_pass vs gold", "actionable"]},
)
check(
    "a primary scored under its reference's name ('oracle_pass vs gold') is the primary: chosen, and no note",
    m == "oracle_pass vs gold" and note is None,
    (m, note),
)

m, note = pick(
    {"runs/ds/a": "late", "runs/ds/b": "late"},
    {"runs/ds/a": ["words"], "runs/ds/b": ["words"]},
)
check(
    "an adapter that cannot say its readings (no read_as): the note names the arms lacking the primary, and no --label",
    m == "words"
    and note is not None
    and "late" in note
    and "--label" not in note
    and "any reading" not in note,
    (m, note),
)

sys.exit(summary())
