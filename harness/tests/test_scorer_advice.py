#!/usr/bin/env python3
"""The advice for arms scored by different scorers fits the runs (robotics-evals, 0.8.2).

    python tests/test_scorer_advice.py

Two imported arms of a goal's round, each imported with its own scorer: `evh comparison-show` and `evh round-evidence`
said "re-score them with one adapter (evh rescore)", which refuses an imported run (it has no adapter of the
harness's). They now say to import the runs again, scored by one scorer (`evh import-run`), and the round's promotion
hold no longer says to re-score. Runs the harness scored keep the rescore advice (`tests/test_catalog.py`).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cli
from evaluation_harness._check import check, summary

proj = Path(tempfile.mkdtemp(prefix="evh-scorer-advice-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-scorer-advice", EVH_ACTOR="person:tester")
for k in ("EVAL_DATA_DIR", "EVH_FOR"):
    env.pop(k, None)
env.setdefault("EVAL_STORE", "files")


def evh(*args: str):
    return _cli.run(proj, env, *args)


def out(r) -> str:
    return r.stdout + r.stderr


try:
    r = evh("init", "--store", env["EVAL_STORE"])
    check("setup: a project", r.returncode == 0, out(r)[-300:])
    src = proj / "sources" / "d"
    src.mkdir(parents=True)
    for i in range(1, 7):
        (src / f"i{i}.txt").write_text(f"item {i}\n", encoding="utf-8")
    evh("dataset-create", "--dataset-id", "d_v1", "--source-dir", str(src))
    r = evh("dataset-materialize", "--dataset-id", "d_v1")
    r = evh(
        "goal-new", "g", "--set", "title=G", "--set", "statement=s", "--set", "decision=d",
        "--set", "success_criteria.primary.measure=score", "--set", "success_criteria.primary.direction=higher",
        "--set", "datasets.0.dataset_id=d_v1",
    )  # fmt: skip
    check("setup: a goal", r.returncode == 0, out(r)[-300:])
    for arm, scorer, bump in (("arm_a", "scorer_one", ""), ("arm_b", "scorer_two", "5")):
        f = proj / f"{arm}.jsonl"
        f.write_text(
            "".join(f'{{"item_id": "i{i}", "score": 0.{i + 1}{bump}}}\n' for i in range(1, 7)),
            encoding="utf-8",
        )
        r = evh(
            "import-run", "--dataset-id", "d_v1", "--system-id", arm, "--scores", str(f),
            "--primary-metric", "score", "--build-ref", "r1", "--source", "elsewhere",
            "--scorer-id", scorer, "--goal", "g",
        )  # fmt: skip
        check(f"setup: {arm} imported", r.returncode == 0, out(r)[-300:])
    r = evh("round-open", "--goal", "g", "--dataset", "d_v1", "--adopt", "--hypothesis", "h")
    check("setup: a round of the two", r.returncode == 0, out(r)[-300:])

    r = evh("rescore", "--dataset-id", "d_v1")
    check("rescore cannot rescore an imported run", "adapter not found" in out(r), out(r)[-300:])
    for name, cmd in (
        ("comparison-show", ("comparison-show", "--runs", "arm_a,arm_b")),
        ("round-evidence", ("round-evidence", "g", "r1")),
    ):
        r = evh(*cmd)
        text = out(r)
        check(f"{name}: names the scorers as different", "different scorers" in text, text[-500:])
        check(
            f"{name}: for imported runs, says to import them again scored by one scorer",
            "evh import-run" in text and "one scorer" in text,
            text[-500:],
        )
        check(
            f"{name}: does not send an imported run to re-score",
            "evh rescore" not in text and "re-score the arms" not in text,
            text[-500:],
        )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
