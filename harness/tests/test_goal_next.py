#!/usr/bin/env python3
"""A goal that has rounds is not sent back to the dataset's first steps (robotics-evals, 0.8.2).

    python tests/test_goal_next.py

`evh goal-status` on a goal whose rounds were all closed said "fetch d_v1's items": its dataset was made but not
fetched onto this machine (its arms were imported: their scores need no items), and the first step not taken on the
dataset came before the rounds. Once a goal has a round, the dataset's setup (fetch, reference, a first run) is not
its next step: an open round is read, and a goal whose rounds are all closed opens the next one. A goal with no round
is still sent to the dataset's steps.
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

proj = Path(tempfile.mkdtemp(prefix="evh-goal-next-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-goal-next", EVH_ACTOR="person:tester")
for k in ("EVAL_DATA_DIR", "EVH_FOR"):
    env.pop(k, None)
env.setdefault("EVAL_STORE", "files")


def evh(*args: str):
    return _cli.run(proj, env, *args)


def out(r) -> str:
    return (r.stdout + r.stderr)[-400:]


def nxt() -> dict:
    r = evh("goal-status", "g", "--json")
    return json.loads(r.stdout)["result"]["next"] if r.returncode == 0 else {"error": out(r)}


try:
    r = evh("init", "--store", env["EVAL_STORE"])
    check("setup: a project", r.returncode == 0, out(r))
    src = proj / "sources" / "d"
    src.mkdir(parents=True)
    for i in range(1, 7):
        (src / f"i{i}.txt").write_text(f"item {i}\n", encoding="utf-8")
    r = evh("dataset-create", "--dataset-id", "d_v1", "--source-dir", str(src))
    check("setup: a dataset made, not fetched", r.returncode == 0, out(r))
    r = evh(
        "goal-new", "g", "--set", "title=G", "--set", "statement=s", "--set", "decision=d",
        "--set", "success_criteria.primary.measure=score", "--set", "success_criteria.primary.direction=higher",
        "--set", "datasets.0.dataset_id=d_v1",
    )  # fmt: skip
    check("setup: a goal", r.returncode == 0, out(r))
    n = nxt()
    check(
        "a goal with no round, its dataset not fetched: fetch it",
        "dataset-materialize" in n.get("command", ""),
        n,
    )
    for arm, scorer in (("arm_a", "scorer_one"), ("arm_b", "scorer_one")):
        f = proj / f"{arm}.jsonl"
        f.write_text(
            "".join(
                f'{{"item_id": "i{i}", "score": 0.{i + (5 if arm == "arm_b" else 1)}}}\n' for i in range(1, 7)
            ),
            encoding="utf-8",
        )
        r = evh(
            "import-run", "--dataset-id", "d_v1", "--system-id", arm, "--scores", str(f),
            "--primary-metric", "score", "--build-ref", "r1", "--source", "elsewhere",
            "--scorer-id", scorer, "--goal", "g",
        )  # fmt: skip
        check(f"setup: {arm} imported", r.returncode == 0, out(r))
    lead = next(
        (x.split()[0] for x in evh("runs-list").stdout.splitlines() if x.startswith("arm_b_")), "arm_b"
    )
    r = evh("run-promote", "--run", lead, "--goal", "g", "--reason", "the leader of the goal test's two arms")
    check("setup: a baseline", r.returncode == 0, out(r))
    r = evh("round-open", "--goal", "g", "--dataset", "d_v1", "--adopt", "--hypothesis", "h")
    check("setup: a round of the two", r.returncode == 0, out(r))
    n = nxt()
    check(
        "an open round, the dataset not fetched: read the round's evidence",
        n.get("command") == "evh round-show g r1",
        n,
    )
    r = evh(
        "round-close",
        "--goal",
        "g",
        "--round",
        "r1",
        "--conclusion",
        "arm_b leads on the score by a clear margin.",
    )
    check("setup: the round closed", r.returncode == 0, out(r))
    n = nxt()
    check(
        "every round closed, the dataset not fetched: where the goal stands, then a round to open",
        n.get("what") == "baseline arm_b (v1); to test a change, open a round with a question"
        and n.get("command", "").startswith("evh round-open --goal g "),
        n,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
