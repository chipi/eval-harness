#!/usr/bin/env python3
"""`evh metric-show` says what each goal link means: a goal that decides on the metric (its primary measure) and a goal
that weighs it as an axis are two facts, and a metric that one goal decides on is weighed as an axis by none.

  EVAL_STORE=files python tests/test_metric_show_wording.py        (and EVAL_STORE=sqlite)

`words_out` is the primary measure of `headline_short`, and no goal lists it as an axis (cost, speed or its own). The page
printed `decides headline_short` beside `weighed by no goal`, which reads as a contradiction. Both are right (`decides` is
the goals whose primary measure it is, `weighs` the goals that take it as an axis); the words now say so, on the command, the
metric's page and the metrics table.
"""

import json
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
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-metric-words-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-metric-words", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

ADAPTER = """
from evaluation_harness.adapter import Result

METRIC_KINDS = {"words_out": "quality", "chars_out": "quality"}

def call_system(text, params):
    words = text.split()[: params["words"]]
    return Result(output=" ".join(words), tokens_in=len(text.split()), tokens_out=len(words), cost_usd=0.0)

def score(output, reference):
    return {"words_out": float(len(output.split())), "chars_out": float(len(output))}
"""
GOAL = (
    'goal_id: {gid}\nschema_version: "0.1"\ntitle: {gid}\nstatement: s\ndecision: d\nstatus: active\n'
    "datasets:\n  - dataset_id: headlines_v1\nsuccess_criteria:\n  primary: {{measure: words_out, direction: lower}}\n{axes}"
)


def evh(*args):
    return _cli.run(proj, env, *args)


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
        (proj / "data" / "models").mkdir()
    shutil.copytree(HARNESS / "tutorial" / "tickets", proj / "tutorial" / "tickets")
    (proj / "adapters").mkdir()
    (proj / "adapters" / "headline.py").write_text(ADAPTER)
    r = evh("dataset-create", "--dataset-id", "headlines_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "headlines_v1")
    _runstore.write_text(proj, "goals/headline_short.yaml", GOAL.format(gid="headline_short", axes=""))
    _runstore.write_text(
        proj,
        "goals/headline_tight.yaml",
        GOAL.format(gid="headline_tight", axes="  axes:\n    size: {measure: chars_out, direction: lower}\n"),
    )
    _runstore.write_text(
        proj, "systems/h6_v1.yaml", "system_id: h6_v1\nadapter: adapters/headline.py\nparams:\n  words: 6\n"
    )
    r = (
        r
        if r.returncode
        else evh("run", "--system", "h6_v1", "--dataset", "headlines_v1", "--goal", "headline_short")
    )
    check("setup: a run of an adapter whose goal decides on words_out", r.returncode == 0, r.stderr[-300:])

    shown = evh("metric-show", "words_out").stdout
    check(
        "metric-show words_out: decides names the goals whose primary measure it is, and says so",
        "decides      goals headline_short, headline_tight (their primary measure)" in shown,
        shown,
    )
    check(
        "metric-show words_out: no goal takes it as an axis, said as that (not a bare `weighed by no goal`)",
        "weighed as an axis by  no goal" in shown and "weighed by" not in shown,
        shown,
    )
    axis = evh("metric-show", "chars_out").stdout
    check(
        "metric-show chars_out: a goal that takes it as an axis is named as that, and it decides nothing",
        "weighed as an axis by  headline_tight" in axis and "decides      no goal" in axis,
        axis,
    )
    got = json.loads(evh("metric-show", "words_out", "--json").stdout).get("result", {})
    check(
        "metric-show --json: the same two facts, as data",
        got.get("decides") == ["headline_short", "headline_tight"] and got.get("weighs") == [],
        {k: got.get(k) for k in ("decides", "weighs")},
    )
    listed = evh("metric-list").stdout
    check(
        "metric-list: the same words",
        "weighed as an axis by: headline_tight" in listed and "weighed by:" not in listed,
        listed,
    )
    out = proj / "catalog"
    r = evh("catalog", "--out", out)
    page = (out / "m" / "words_out.html").read_text() if (out / "m" / "words_out.html").exists() else ""
    check(
        "the metric's page: decides names its primary measure, the axis line says as an axis",
        r.returncode == 0
        and "<dt>decides</dt>" in page
        and "(their primary measure)" in page
        and "<dt>weighed as an axis by</dt><dd>no goal</dd>" in page
        and "<dt>weighed by</dt>" not in page,
        r.stderr[-300:],
    )
    table = (out / "metrics.html").read_text() if (out / "metrics.html").exists() else ""
    check(
        "the metrics table: the axis note says as an axis",
        "weighed as an axis by" in table and ">weighed by<" not in table,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
