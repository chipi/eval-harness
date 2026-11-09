#!/usr/bin/env python3
"""How an arm's repeats make one score per item (PLAN_0.8.0 A4): mean, majority, at_least_K.

    python tests/test_reducers.py

`stats.reduce_repeats` on its own; a goal's `primary.reduce` through `axes.decide`, reading the repeats the catalog
keeps beside each mean; and `_runs.per_item(reduce=)`, which pair-test and family-test read. Without a reducer every
number is what it was: the mean.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import axes, stats
from evaluation_harness._check import check, summary
from evaluation_harness._runs import per_item, repeat_agreement, say_agreement

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore

r = stats.reduce_repeats
check(
    "mean is the default and the old number",
    r([1, 0, 1]) == 2 / 3 and r([0.2, 0.4], "mean") == 0.30000000000000004,
)
check("majority: more than half right", r([1, 0, 1], "majority") == 1.0 and r([1, 0], "majority") == 0.0)
check(
    "at_least_K: K of the repeats right (at_least_1 is pass@k's question)",
    r([0, 0, 1], "at_least_1") == 1.0 and r([0, 1, 1], "at_least_3") == 0.0,
)
for bad, how in (([0.5, 1], "majority"), ([1, 0], "best_of")):
    try:
        r(bad, how)
        refused = False
    except ValueError:
        refused = True
    check(f"refused: {how} on {bad}", refused)

# decide with repeats: B is right on 2 of 3 repeats of every item, so its mean is 0.667 and its majority 1.
items = [f"i{k:03d}" for k in range(120)]


def arm(label, reps):
    vals = {i: sum(v) / len(v) for i, v in reps.items()}
    return {"label": label, "flags": [], "scores": {"q": {"values": vals, "repeats": reps}}}


arms = {
    "a": arm("A", {i: [1.0, 1.0, 1.0] for i in items}),
    "b": arm("B", {i: [1.0, 1.0, 0.0] for i in items}),
}
goal = {"success_criteria": {"primary": {"measure": "q", "direction": "higher"}}}
mean = axes.decide(goal, arms)
maj = axes.decide(
    {"success_criteria": {"primary": {"measure": "q", "direction": "higher", "reduce": "majority"}}}, arms
)
check(
    "decide: by the mean B is 0.667; by majority every item is right, B ties A",
    abs(mean["rows"]["b"]["quality"]["value"] - 2 / 3) < 1e-12
    and maj["rows"]["b"]["quality"]["value"] == 1.0,
    (mean["rows"]["b"]["quality"], maj["rows"]["b"]["quality"]),
)

# per_item reads runs from disk: three repeats of one arm.
with tempfile.TemporaryDirectory() as tmp:
    runs: list = []
    for k, vals in enumerate(([1, 0, 1], [1, 0, 0], [1, 1, 0])):
        d = Path(tmp) / f"arm_r{k}"
        d.mkdir()
        rows = [{"item_id": f"x{j}", "correct": v} for j, v in enumerate(vals)]
        _runstore.put_rows_text(d, "".join(json.dumps(x) + "\n" for x in rows))
        runs.append((d, {}))
    m = per_item(runs, "correct")
    ag = repeat_agreement(runs, "correct")
    one_run = repeat_agreement(runs[:1], "correct")
    mj = per_item(runs, "correct", reduce="majority")
    one = per_item(runs, "correct", reduce="at_least_1")
check(
    "repeat_agreement: items scored the same in every run (x0 only), and the item-runs behind them (feedback 33)",
    ag == {"runs": 3, "items": 3, "same": 1, "item_runs": 9} and one_run is None,
    ag,
)
check(
    "say_agreement: near-copies named only when nearly every item agrees",
    "near-copies" not in say_agreement("A", ag or {})
    and "near-copies" in say_agreement("A", {"runs": 3, "items": 10, "same": 9, "item_runs": 30}),
)

check(
    "per_item: the mean by default; majority and at_least_1 from the same repeats",
    m == {"x0": 1.0, "x1": 1 / 3, "x2": 1 / 3}
    and mj == {"x0": 1.0, "x1": 0.0, "x2": 0.0}
    and one == {"x0": 1.0, "x1": 1.0, "x2": 1.0},
    (m, mj, one),
)
sys.exit(summary())
