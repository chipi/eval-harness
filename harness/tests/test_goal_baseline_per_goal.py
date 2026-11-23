#!/usr/bin/env python3
"""A goal's baseline is its own: every place that names it names the arm the goal promoted (RFC-041 F6).

  EVAL_STORE=files python tests/test_goal_baseline_per_goal.py        (and EVAL_STORE=sqlite)

Two goals on one dataset (the fleet fixture): triage_a promoted arm_x's run, triage_b arm_y's. `by_dataset` flagged an arm
`baseline` when ANY goal promoted it, and a goal's view took the first flagged arm, so triage_b's goal-leaderboard said
arm_y in its `answer` and `datasets[].baseline` and arm_x in `groups[].baseline` and on arm_x's row; its catalog page tagged
both arms. The flag now comes from the goal being read (`goal_views.baseline_read`, the one the answer and `evh baselines`
give), so each goal shows its own baseline everywhere and its page tags one arm.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _foreign  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-baseline-goal-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVH_ACTOR="person:fixture")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_BUILD_REF"):
    env.pop(k, None)

DS = "queue_triage_v1"
WANT = {"triage_a": "runs/queue_triage_v1/arm_x_v1", "triage_b": "runs/queue_triage_v1/arm_y_v1"}


def evh(*args):
    return _cli.run(proj, env, *args)


def places(goal: str) -> dict:
    """The arm each place names as `goal`'s baseline on the dataset."""
    r = json.loads(evh("goal-leaderboard", goal, "--json").stdout)["result"]
    d = next(x for x in r["datasets"] if x["dataset"] == DS)
    got = {
        "datasets[].baseline": (d.get("baseline") or {}).get("arm"),
        "answer": next((a["baseline"] or {}).get("arm") for a in r["answer"] if a["dataset"] == DS),
        "groups[].baseline": sorted({g.get("baseline") for g in d["groups"]} - {None}),
        "arms[].baseline": sorted({a["arm"] for g in d["groups"] for a in g["arms"] if a.get("baseline")}),
    }
    rows = json.loads(evh("baselines", "--goal", goal, "--json").stdout)["result"]["baselines"]
    got["baselines"] = next(
        (b.get("arm") or b.get("promoted_from") for b in rows if b["dataset"] == DS), None
    )
    return got


try:
    _foreign.fleet(proj, dict(env))
    for goal, arm in WANT.items():
        got = places(goal)
        check(
            f"{goal}: the answer, the datasets, the group and every arm's flag name {arm.rpartition('/')[2]}",
            got["datasets[].baseline"] == arm
            and got["answer"] == arm
            and got["groups[].baseline"] == [arm]
            and got["arms[].baseline"] == [arm]
            and str(got["baselines"]).startswith(arm.rpartition("/")[2]),
            got,
        )
    out = proj / "catalog"
    r = evh("catalog", "--out", out)
    check("setup: the catalog builds", r.returncode == 0, r.stderr[-300:])
    for goal, arm in WANT.items():
        page = (
            (out / "g" / f"{goal}.html").read_text(encoding="utf-8")
            if (out / "g" / f"{goal}.html").exists()
            else ""
        )
        tagged = []
        for row in re.findall(r"<tr[^>]*>.*?</tr>", page, re.S):
            if 'tag-base">baseline' in row:
                tagged += [a for a in (WANT.values()) if a.rpartition("/")[2] + ".html" in row]
        check(
            f"{goal}'s catalog page tags one arm baseline: {arm.rpartition('/')[2]}",
            tagged == [arm],
            tagged,
        )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
