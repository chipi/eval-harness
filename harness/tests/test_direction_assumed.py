#!/usr/bin/env python3
"""A measure nobody declares is read as higher-is-better, and the readers say so (RFC-041 F1).

  EVAL_STORE=files python tests/test_direction_assumed.py        (and EVAL_STORE=sqlite)

`_runs.direction` ends on "higher" for a measure no goal, no run and no name in the name table speaks for. The default
stays (a result must not move), but a ranking or a verdict that rests on it is not silent:

- `direction_source` names it (`_runs.ASSUMED`), and `assumed_note` is the one line every reader prints;
- on a project with a measure `weird_score` that nobody declares: `leaderboard`, `run-compare` and `goal-leaderboard`
  print that line, and `evh validate` notes it for the goal's primary measure and the runs' primary_metric (V14);
- with a goal declaring it, or --asc / --desc passed, or a measure the name table knows: no line, in any of them.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format, _runs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

LINE = "weird_score: no goal or adapter says which way is better; read as higher-is-better (declare it)"

# -- the helper -----------------------------------------------------------------------------------------------------
check(
    "direction_source: a measure nothing knows is the bare default, and says so",
    _runs.direction_source("weird_score", goals={}) == ("higher", _runs.ASSUMED),
    _runs.direction_source("weird_score", goals={}),
)
check(
    "direction_source: a name the table knows (cost, an error rate, a count) is not the bare default",
    all(
        _runs.direction_source(m, goals={})[1] == "the name table"
        for m in ("cost_usd", "wer", "output_chars")
    ),
)
check(
    "assumed_note: one line for the bare default, nothing for any other source",
    _runs.assumed_note("weird_score", _runs.ASSUMED) == LINE
    and _runs.assumed_note("weird_score", "goal g") is None
    and _runs.assumed_note("cost_usd", "the name table") is None
    and _runs.assumed_note("weird_score", "the runs' directions") is None,
)

# -- one project, every reader --------------------------------------------------------------------------------------
proj = Path(tempfile.mkdtemp(prefix="evh-assumed-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-assumed", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

ADAPTER = """
from types import SimpleNamespace

def call_system(text, params):
    v = float(params["v"])
    return SimpleNamespace(output=f"{v}|x", tokens_in=10, tokens_out=5, cost_usd=v / 100, latency_ms=None, extra={}, meta={})

def score(output, reference):
    return {"weird_score": float(output.split("|")[0])}

PRIMARY_METRIC = "weird_score"
"""


def evh(*args):
    return _cli.run(proj, env, *args)


def said(r) -> str:
    return r.stdout + r.stderr


def write_goal(primary: str) -> None:
    _runstore.write_text(
        proj,
        "goals/g_weird.yaml",
        'goal_id: g_weird\nschema_version: "0.1"\ntitle: g_weird\nstatement: g_weird\ndecision: g_weird\n'
        f"status: active\ndatasets:\n  - dataset_id: tickets_v1\nsuccess_criteria:\n  primary: {primary}\n",
    )


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
        (proj / "data" / "models").mkdir()
    shutil.copytree(HARNESS / "tutorial" / "tickets", proj / "tutorial" / "tickets")
    (proj / "weird_adapter.py").write_text(ADAPTER)
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: a frozen dataset", r.returncode == 0, r.stderr[-300:])
    for name, v in (("good", 0.1), ("bad", 0.4)):
        _runstore.write_text(
            proj,
            f"systems/{name}_v1.yaml",
            f"system_id: {name}_v1\nadapter: weird_adapter.py\nparams:\n  v: {v}\n",
        )
        r = evh("run", "--system", f"{name}_v1", "--dataset", "tickets_v1", "--run-id", name)
        check(f"setup: the run {name}", r.returncode == 0, r.stderr[-300:])

    # -- nobody declares weird_score ---------------------------------------------------------------------------------
    r = evh("leaderboard", "tickets_v1", "--sort", "weird_score")
    check(
        "leaderboard: a ranking on a measure nobody declares prints the NOTE", LINE in said(r), said(r)[-500:]
    )
    r = evh("leaderboard", "tickets_v1", "--sort", "weird_score", "--desc")
    check(
        "leaderboard --desc: the reader decided, no NOTE",
        r.returncode == 0 and LINE not in said(r),
        said(r)[-300:],
    )
    r = evh("leaderboard", "tickets_v1", "--sort", "cost_usd")
    check(
        "leaderboard: a measure the name table knows, no NOTE",
        r.returncode == 0 and "which way is better" not in said(r),
    )

    r = evh("run-compare", "--baseline", "good", "--candidate", "bad")
    check(
        "run-compare: a verdict on a measure nobody declares prints the NOTE", LINE in said(r), said(r)[-500:]
    )
    check(
        "run-compare: the NOTE once, and the verdict is the default's (a rise is better)",
        said(r).count(LINE) == 1 and "better" in said(r),
        said(r)[-500:],
    )

    write_goal(
        "{measure: cost_usd, direction: lower}"
    )  # V14 reads goals: one that says nothing of weird_score
    r = evh("validate")
    check(
        "V14: the runs' primary_metric nobody declares is a note, which does not fail the check",
        r.returncode == 0
        and "V14 runs: weird_score: no goal or adapter says which way is better" in r.stdout,
        r.stdout[-600:],
    )

    write_goal(
        "{measure: weird_score}"
    )  # a goal that names the measure and no direction (its schema fails on that)
    r = evh("goal-leaderboard", "g_weird")
    check(
        "goal-leaderboard: a goal with no direction for its measure prints the NOTE",
        LINE in said(r),
        said(r)[-600:],
    )

    r = evh("validate")
    check(
        "V14: a note for the goal's primary measure that has no direction, beside the runs' primary_metric",
        "V14 goal g_weird: primary weird_score: no goal or adapter says which way is better" in r.stdout
        and "V14 runs: weird_score: no goal or adapter says which way is better" in r.stdout,
        "\n".join(x for x in r.stdout.splitlines() if "V14" in x or "FAIL" in x or "goals/" in x)[:1500],
    )

    # -- a goal declares it ------------------------------------------------------------------------------------------
    write_goal("{measure: weird_score, direction: higher}")
    r = evh("leaderboard", "tickets_v1", "--sort", "weird_score")
    check("declared: leaderboard has no NOTE", r.returncode == 0 and LINE not in said(r), said(r)[-400:])
    r = evh("run-compare", "--baseline", "good", "--candidate", "bad")
    check(
        "declared: run-compare has no NOTE",
        r.returncode == 0 and "which way is better" not in said(r),
        said(r)[-400:],
    )
    r = evh("goal-leaderboard", "g_weird")
    check("declared: goal-leaderboard has no NOTE", r.returncode == 0 and LINE not in said(r), said(r)[-400:])
    r = evh("validate")
    check(
        "declared: V14 has no note for it",
        r.returncode == 0 and "weird_score: no goal or adapter says" not in r.stdout,
        r.stdout[-900:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
