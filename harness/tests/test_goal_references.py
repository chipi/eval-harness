#!/usr/bin/env python3
"""A goal's status lists a dataset's references by the dataset their manifest names (RFC-032 step 6).

    python tests/test_goal_references.py

In a throwaway project ($0, offline), in whichever store the suite runs in: a goal that names `gold/ds_a_adj1`, a
reference promoted under another name for ds_a (its manifest says ds_a), shows it for ds_a beside `gold/ds_a` (it
showed only `gold/ds_a`: the match was on the name's ending); a reference the goal names whose manifest names another
dataset is that dataset's; a goal that does not name the adjudicated one does not show it; a gold or silver reference
named like the dataset whose manifest names another one is not the dataset's; and the goal's link check finds a
reference's folder and refuses one that is not there.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _common, _format
from evaluation_harness._check import check, summary

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore

proj = Path(tempfile.mkdtemp(prefix="evh-goalrefs-"))
(proj / "data").mkdir(parents=True)
_runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")


def goal(goal_id, refs):
    lines = [
        f"goal_id: {goal_id}",
        "datasets:",
        "  - {dataset_id: ds_a}",
        "  - {dataset_id: ds_b}",
        "references:",
    ]
    lines += [f"  - {{reference_id: {r}, tier: {r.split('/')[0]}, format: label}}" for r in refs]
    _runstore.write_text(proj, f"goals/{goal_id}.yaml", "\n".join(lines) + "\n")


def reference(rid, dataset_id):
    _runstore.write_text(proj, f"references/{rid}/manifest.json", json.dumps({"dataset_id": dataset_id}))


try:
    for ds in ("ds_a", "ds_b", "ds_c"):
        _runstore.write_text(proj, f"datasets/{ds}.json", json.dumps({"dataset_id": ds, "items": []}))
    reference("gold/ds_a", "ds_a")
    reference("gold/ds_a_adj1", "ds_a")
    reference("gold/other", "ds_b")
    reference("silver/ds_a", "ds_c")  # named like ds_a, made for ds_c
    reference("gold/ds_b", "ds_b")
    goal("g_named", ["gold/ds_a", "gold/ds_a_adj1", "gold/other"])
    goal("g_plain", ["gold/ds_a"])

    with _runstore._InProject(proj):
        from evaluation_harness.model import goals

        def refs_of(goal_id):
            return {d["dataset"]: d["references"] for d in goals.status(goal_id)["datasets"]}

        named = refs_of("g_named")
        plain = refs_of("g_plain")
        link_ok = goals._links({"references": [{"reference_id": "gold/ds_a_adj1"}]})
        link_bad = goals._links({"references": [{"reference_id": "gold/nowhere"}, {"reference_id": "ds_a"}]})

    check(
        "the adjudicated reference the goal names is ds_a's, beside gold/ds_a",
        named["ds_a"] == ["gold/ds_a", "gold/ds_a_adj1"],
        named["ds_a"],
    )
    check(
        "a silver reference named like ds_a whose manifest names ds_c is not ds_a's",
        "silver/ds_a" not in named["ds_a"],
        named["ds_a"],
    )
    check(
        "a reference the goal names is the dataset its manifest names (gold/other is ds_b's), with gold/ds_b",
        named["ds_b"] == ["gold/ds_b", "gold/other"],
        named["ds_b"],
    )
    check(
        "a goal that does not name the adjudicated reference does not show it",
        plain["ds_a"] == ["gold/ds_a"],
        plain["ds_a"],
    )
    check("the link check finds a reference's folder", link_ok == [], link_ok)
    check(
        "... and refuses one that is not there and one that is no reference id",
        [p["path"] for p in link_bad]
        == [["references", 0, "reference_id"], ["references", 1, "reference_id"]],
        link_bad,
    )
finally:
    import shutil

    shutil.rmtree(proj, ignore_errors=True)
    _common.project_root.cache_clear()

sys.exit(summary())
