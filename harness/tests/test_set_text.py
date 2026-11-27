#!/usr/bin/env python3
"""A `--set` value for a field the schema says is text is that text (a project of robotics-evals, 0.8.2).

    python tests/test_set_text.py

`evh model-new`, `model-set`, `goal-new` and `data-put --set` read a value as YAML (`aliases=[a, b]` is a list,
`n=3` a number), so `notes="duck: 50 Hz"` became a mapping and was refused "must be text". Where the schema says
the field is text, the value now is the text as typed (`notes=50` is "50", `statement="why: because"` a sentence); a
field that is not text keeps its YAML; the API's JSON body, typed already, is as before.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cli
from evaluation_harness._check import check, summary

proj = Path(tempfile.mkdtemp(prefix="evh-set-text-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-set-text", EVH_ACTOR="person:tester")
for k in ("EVAL_DATA_DIR", "EVH_FOR"):
    env.pop(k, None)
env.setdefault("EVAL_STORE", "files")


def evh(*args: str):
    return _cli.run(proj, env, *args)


def out(r) -> str:
    return (r.stdout + r.stderr)[-400:]


def shown(*args: str) -> dict:
    r = evh(*args, "--json")
    return json.loads(r.stdout)["result"]["record"] if r.returncode == 0 else {}


try:
    r = evh("init", "--store", env["EVAL_STORE"])
    check("setup: a project", r.returncode == 0, out(r))
    r = evh("model-new", "m2", "--set", "kind=llm", "--set", "aliases=[a, b]", "--set", "notes=duck: 50 Hz")
    rec = shown("model-show", "m2")
    evh("model-new", "m1", "--set", "kind=llm", "--set", "aliases=[a, b]")
    check(
        "model-new: a text field is the text typed, a list field is YAML",
        rec.get("notes") == "duck: 50 Hz" and rec.get("aliases") == ["a", "b"],
        out(r) + str(rec.get("notes")),
    )
    r = evh("model-set", "m1", "--set", "notes=50")
    check(
        "model-set: a number typed into a text field is its digits",
        shown("model-show", "m1").get("notes") == "50",
        out(r),
    )
    r = evh("model-set", "m1", "--set", "notes=- a: 1")
    check(
        "model-set: text that looks like a YAML list is text",
        shown("model-show", "m1").get("notes") == "- a: 1",
        out(r),
    )
    r = evh("model-set", "m1", "--set", "weights=open")
    check("model-set: a plain word is as it was", shown("model-show", "m1").get("weights") == "open", out(r))
    r = evh("model-set", "m1", "--set", "kind=[llm]")
    check(
        "model-set: a value that is not text is still read as YAML (so refused here as a list)",
        r.returncode != 0,
        out(r),
    )
    r = evh(
        "data-put", "--path", "goals/g1.yaml", "--new", "--set", "goal_id=g1", "--set", "title=T", "--set", "statement=why: because",
        "--set", "decision=d", "--set", "success_criteria.primary.measure=overlap_f1",
        "--set", "success_criteria.primary.direction=higher", "--set", "datasets.0.dataset_id=tk",
    )  # fmt: skip
    f = proj / "data" / "goals" / "g1.yaml"
    goal = shown("goal-show", "g1")
    check(
        "data-put --set: a text field of a goal is the text typed",
        goal.get("statement") == "why: because" and goal.get("datasets") == [{"dataset_id": "tk"}],
        out(r) + str(goal.get("statement")) + str(f),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
