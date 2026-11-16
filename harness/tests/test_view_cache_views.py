#!/usr/bin/env python3
"""Every view, with the view cache on and off (RFC-032 step 9): the same answer, in either store.

    python tests/test_view_cache_views.py

In a throwaway tutorial project ($0, offline) with a goal, a gold reference and two systems run on it, in whichever
store EVAL_STORE names (the store matrix runs both): each read operation that is computed from the arms' scores is
answered with the cache off, then on (cold), then on again (kept): three identical answers, and the third reads no
scores at all. Then the data changes, and the cache never answers from before: a write through the model in this
process (a goal's title) is in the next answer at once; a run another process makes, and a goal another process
makes, are in the answer after the next look; and the answer is again the one the cache-off read gives.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

proj = Path(tempfile.mkdtemp(prefix="evh-vcviews-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-view-cache")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR", "EVH_P_CACHE", "EVH_VIEW_CACHE"):
    env.pop(k, None)
    os.environ.pop(k, None)
os.environ.update(env)

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KIT = HERE.parent / "tutorial"
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness._check import check, store_under_test, summary  # noqa: E402
from evaluation_harness.catalog_adapter import HarnessAdapter  # noqa: E402
from evaluation_harness.model import view_cache as vc  # noqa: E402
from evaluation_harness.ops import registry  # noqa: E402

GOAL = "tickets_summary"
DS = "tk_v1"
DS2 = "tk_v2"
SETS = [
    "title=Ticket summaries", "statement=A one-line summary of a support ticket for the person triaging it.",
    "decision=Which system writes the summary.", "success_criteria.primary.measure=overlap_f1",
    "success_criteria.primary.direction=higher", f"datasets.0.dataset_id={DS}", "datasets.0.role=test",
]  # fmt: skip
#: Every read computed from the arms' scores or the data's listings, with what it is asked.
VIEWS: list[tuple[str, dict]] = [
    ("overview-show", {}),
    ("arm-list", {}),
    ("dataset-arm-list", {"dataset": DS}),
    ("dataset-arm-list", {"dataset": DS2}),
    ("arm-list", {"dataset": DS2, "systems": "1"}),
    ("goal-list", {}),
    ("goal-show", {"goal": GOAL}),
    ("goal-status", {"goal": GOAL}),
    ("goal-leaderboard", {"goal": GOAL}),
    ("metric-list", {}),
    ("dataset-list", {}),
    ("dataset-show", {"dataset": DS}),
    ("system-list", {}),
    ("reference-list", {}),
    ("round-list", {"goal": GOAL}),
    ("activity-show", {}),
    ("scorer-list", {}),
    ("model-list", {}),
    ("leaderboard", {"dataset": DS}),
    ("capture-list", {}),
]


def evh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=900,
    )  # fmt: skip


def answers() -> dict[str, str]:
    """Each view's answer as JSON text (an error is part of the answer)."""
    out = {}
    for name, kwargs in VIEWS:
        op = registry.get(name)
        assert op is not None, name
        label = name + "".join(f" {k}={v}" for k, v in kwargs.items())
        try:
            out[label] = json.dumps(op.call(**kwargs), sort_keys=True, default=str)
        except Exception as exc:  # noqa: BLE001 - a view that refuses must refuse the same way with the cache
            out[label] = f"{type(exc).__name__}: {exc}"
    return out


def same(a: dict[str, str], b: dict[str, str]) -> list[str]:
    return [k for k in a if a[k] != b[k]]


reads = [0]
real_scores = HarnessAdapter.scores


def counting(self: HarnessAdapter, arm: str, rescore: bool = False) -> dict:
    reads[0] += 1
    return real_scores(self, arm, rescore)


try:
    r = evh("init", "--store", store_under_test(), "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    for step in (
        ("dataset-create", "--dataset-id", DS, "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", DS),
        ("label-import", str(KIT / "gold"), "--dataset-id", DS, "--set", "g", "--by", "t"),
        ("reference-promote", "--dataset-id", DS, "--labels", "g", "--tier", "gold", "--reason", "the kit's summaries, for the view cache's test", "--by", "t"),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    r = r if r.returncode else evh("dataset-create", "--dataset-id", DS2, "--source-dir", "tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", DS2)
    for cid, n in (("one_v1", 1), ("two_v1", 2)):
        _runstore.write_text(
            proj, f"systems/{cid}.yaml", f"system_id: {cid}\nparams:\n  provider: echo\n  sentences: {n}\n"
        )
    r = r if r.returncode else evh("run", "--system", "one_v1", "--dataset", DS)
    r = r if r.returncode else evh("run", "--system", "two_v1", "--dataset", DS)
    r = r if r.returncode else evh("run", "--system", "one_v1", "--dataset", DS2)
    r = r if r.returncode else evh("goal-new", GOAL, *(x for s in SETS for x in ("--set", s)))
    check(
        "setup: a project with a goal, a reference and two runs",
        r.returncode == 0,
        (r.stdout + r.stderr)[-400:],
    )

    HarnessAdapter.scores = counting  # type: ignore[method-assign]
    vc.ON = False
    vc.clear()
    off = answers()
    check(
        "with the cache off: every view answers",
        len(off) == len(VIEWS) and reads[0] > 0,
        (len(off), reads[0]),
    )
    check(
        "the views have something to show (not all empty): arms and a goal",
        "overlap_f1" in off["arm-list"] and GOAL in off["goal-list"],
        off["arm-list"][:200],
    )
    reads_off = reads[0]

    vc.ON = True
    vc.clear()
    reads[0] = 0
    cold = answers()
    reads_cold = reads[0]
    reads[0] = 0
    kept = answers()
    reads_kept = reads[0]
    check("cache on, cold: every answer is the cache-off answer", not same(off, cold), same(off, cold))
    check("cache on, kept: every answer is the cache-off answer", not same(off, kept), same(off, kept))
    check(
        "cache on: the scores are read once for every view that needs them, and not at all the second time",
        0 < reads_cold < reads_off and reads_kept == 0,
        (reads_off, reads_cold, reads_kept),
    )

    # ── the server's adapter: its scores held under a token, dropped by its refresh() and by cache_clear() ───────────
    from evaluation_harness import catalog_serve as cs
    from evaluation_harness.catalog_adapter import load_catalog_adapter, scores_once

    held = scores_once(load_catalog_adapter(None), held=True)
    one_arm = held.arms()[0]
    reads[0] = 0
    held.scores(one_arm)
    held.scores(one_arm)
    check("a held adapter reads an arm's scores once", reads[0] == 1, reads[0])
    held.refresh()
    held.scores(one_arm)
    check("its refresh() makes the next read read the data again", reads[0] == 2, reads[0])
    cs.cache_clear()
    held.scores(one_arm)
    check("and so does the server's cache_clear()", reads[0] == 3, reads[0])

    # ── a dataset's arms: its decisions alone ─────────────────────────────────────────────────────────────────────────
    from evaluation_harness import catalog_arms

    seen: list[list[str]] = []
    real_glance = catalog_arms.gv.glance

    def spy(A, by_ds, *a, **k):
        seen.append(sorted(by_ds))
        return real_glance(A, by_ds, *a, **k)

    catalog_arms.gv.glance = spy
    try:
        registry.get("dataset-arm-list").call(dataset=DS2)  # type: ignore[union-attr]
        one = list(seen)
        seen.clear()
        registry.get("arm-list").call()  # type: ignore[union-attr]
        every = list(seen)
    finally:
        catalog_arms.gv.glance = real_glance
    check(
        "a dataset's arms are decided on that dataset alone; every arm, on every dataset",
        one == [[DS2]] and every and sorted(every[0]) == sorted([DS, DS2]),
        (one, every),
    )

    # ── a write through the model, in this process ────────────────────────────────────────────────────────────────
    registry.get("goal-set").call(goal=GOAL, by="person:test", set={"title": "A new title"})  # type: ignore[union-attr]
    after = answers()
    check(
        "a write in this process: the next answer has it, with no look at the data",
        "A new title" in after["goal-list"] and "A new title" not in kept["goal-list"],
    )
    vc.ON = False
    fresh = answers()
    vc.ON = True
    check("and every answer is the one the cache-off read gives", not same(fresh, after), same(fresh, after))

    vc.epoch()  # a look at the data has just been taken: the next one is due only when an operation starts
    # ── another process: a run, a goal ────────────────────────────────────────────────────────────────────────────
    r = evh(
        "system-new", "three_v1", "--set", "params.provider=echo", "--set", "params.sentences=3", "--by", "t"
    )
    r = r if r.returncode else evh("run", "--system", "three_v1", "--dataset", DS)
    r = r if r.returncode else evh("goal-new", "second_goal", "--set", "title=Second", "--set", "statement=Another one.", "--set", "decision=Which one.", "--set", "success_criteria.primary.measure=overlap_f1", "--set", "success_criteria.primary.direction=higher", "--set", f"datasets.0.dataset_id={DS}", "--set", "datasets.0.role=test")  # fmt: skip
    check("setup: another process made a run and a goal", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    later = answers()  # each operation looks at the data first (Op.call: begin())
    check(
        "another process's run and goal: the next answer has both (an operation looks at the data first)",
        "three_v1" in later["arm-list"]
        and "second_goal" in later["goal-list"]
        and "three_v1" not in after["arm-list"],
        (
            "three_v1" in later["arm-list"],
            "second_goal" in later["goal-list"],
            "three_v1" not in after["arm-list"],
        ),
    )
    vc.ON = False
    fresh = answers()
    vc.ON = True
    check("and every answer is the one the cache-off read gives", not same(fresh, later), same(fresh, later))
finally:
    HarnessAdapter.scores = real_scores  # type: ignore[method-assign]
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
