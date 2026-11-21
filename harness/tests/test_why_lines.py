#!/usr/bin/env python3
"""A goal page's reasons with many arms (catalog_build.why_lines): the scorer named once, long lists as a count.

    python tests/test_why_lines.py

The triage goal once had 51 contenders, then the same 51 undecided: the page listed them twice, each with its
scorer's hash. Its data no longer has them (65 items are too few for the non-inferiority test), so the real-catalog
browser check cannot see the folding any more; this keeps it checked on a decision made for the purpose.
"""

import sys
from pathlib import Path
from typing import Any, cast

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness import catalog_build as cb  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

arms = [f"arm_{i:02d}" for i in range(12)]
labels = {a: f"{a} · rescored 5f2c057c" for a in arms}
labels["arm_11"] = "arm_11 · rescored 0a1b2c3d, repeats ×3"  # read through another scorer: keeps its suffix
close = arms[1:11]  # ten contenders beside the leader, more than LONG_LIST


def listed(xs):
    return ", ".join(labels[x] for x in xs)


def dec(undecided):
    return {
        "rows": arms,
        "leader": arms[0],
        "contenders": [arms[0], *close],
        "undecided": undecided,
        "why": [
            f"Strategy frugal. Quality leader: {labels[arms[0]]}. Contenders beside it: {listed(close)}.",
            f"Still undecided after the tie-break: {listed(undecided)}.",
        ],
    }


same = cb.why_lines(dec([arms[0], *close]), labels)
html = "\n".join(same)
check(
    "the scorer most arms are read through is named once, first, and after no arm",
    same[0].startswith("Every arm here is read through its re-score by scorer 5f2c057c")
    and "rescored 5f2c057c" not in html,
    same[:1],
)
check(
    "more than LONG_LIST contenders: a count, the names folded under it",
    f"{len(close)} arms<details><summary>which</summary>" in html and len(close) > cb.LONG_LIST,
    html[:400],
)
check(
    "the undecided are the contenders: said as all of them, not listed again",
    "Still undecided after the tie-break: all 11 contenders." in html,
    html[-300:],
)
other = cb.why_lines(dec(arms[2:12]), labels)
check(
    "an arm read through another scorer keeps its own suffix, the common one is dropped",
    "arm_11 · rescored 0a1b2c3d, repeats ×3" in "\n".join(other) and "5f2c057c" not in "\n".join(other[1:]),
    other[-1:],
)
check(
    "a long undecided list that is not the contenders: a count, folded",
    any(x.startswith("Still undecided after the tie-break: 10 arms<details>") for x in other),
    other[-1:],
)


class Scores:
    """An adapter with only what baseline_gap reads: each arm's per-item scores."""

    def __init__(self, values: dict) -> None:
        self.values = values

    def scores(self, arm: str) -> dict:
        return {"f1": {"values": self.values[arm]}}


items = [f"i{k:02d}" for k in range(40)]
A = Scores(
    {"base": dict.fromkeys(items, 0.5), "rec": {i: 0.5 + 0.01 * (k % 7 + 1) for k, i in enumerate(items)}}
)
rows = [
    {"arm": "base", "label": "base · rescored 5f2c057c", "baseline": True},
    {"arm": "rec", "label": "rec · rescored 5f2c057c"},
]
gap = cb.baseline_gap(  # a stand-in adapter: only scores() is read
    cast(Any, A),
    {"recommended": "rec", "axes": [{"direction": "higher"}], "goal": {}, "dataset": "d"},
    rows,
    "f1",
)
check(
    "the baseline's gap names both arms as the page does: the common scorer suffix dropped",
    gap.startswith("Differs from the promoted baseline, base: rec is +") and "5f2c057c" not in gap,
    gap,
)
sys.exit(summary())
