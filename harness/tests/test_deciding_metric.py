#!/usr/bin/env python3
"""The metric that decides on a dataset is answered once (RFC-041's class: a fact worked out by each reader).

  EVAL_STORE=files python tests/test_deciding_metric.py        (and EVAL_STORE=sqlite)

`_runs.deciding_metric`: the goal naming the dataset whose measure a run records, else the runs' primary metric, else a
refusal that names the candidates. Before it, `evh leaderboard` read the goal's measure while `pair-test`, `family-test`
and `rank-stability` refused ("no run records a primary metric") when the adapter set no PRIMARY_METRIC, and the sheet,
the inspector and `period-compare` each chose their own way (the sheet: the first metric by name).

- the rule, on records;
- one project, the tutorial 9 shape (a custom adapter with no PRIMARY_METRIC, a goal on `words_out`): the leaderboard,
  pair-test, family-test, rank-stability, goal-leaderboard, the inspector and the sheet all read `words_out`, and
  run-compare judges it by the goal's direction;
- a source check: the readers that pick a default metric ask `deciding_metric`.
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
import _runstore  # noqa: E402
from evaluation_harness import _format, _runs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

D = Path(".")


def rec(dataset: str, scores: list[str], primary: str | None = None) -> tuple:
    return (D, {"dataset_id": dataset, "scores": dict.fromkeys(scores, 1.0), "primary_metric": primary})


def goal(measure: str, datasets: list[str]) -> dict:
    return {
        "success_criteria": {"primary": {"measure": measure}},
        "datasets": [{"dataset_id": d} for d in datasets],
    }


def refusal(**kw) -> str:
    try:
        _runs.deciding_metric("d", **kw)
    except SystemExit as e:
        return str(e)
    return ""


# -- the rule ----------------------------------------------------------------------------------------------------------
runs = [rec("d", ["a", "words_out"], "a")]
check(
    "rule: the goal naming the dataset, whose measure a run records, beats the runs' primary metric",
    _runs.deciding_metric("d", runs=runs, goals={"g": goal("words_out", ["d"])}) == "words_out",
)
check(
    "rule: with no goal, the runs' primary metric",
    _runs.deciding_metric("d", runs=runs, goals={}) == "a",
)
check(
    "rule: a goal on another dataset decides nothing here",
    _runs.deciding_metric("d", runs=runs, goals={"g": goal("words_out", ["other"])}) == "a",
)
check(
    "rule: a goal whose measure no run records (a prose name) is skipped, the next goal or the primary metric decides",
    _runs.deciding_metric("d", runs=runs, goals={"g1": goal("DER", ["d"]), "g2": goal("words_out", ["d"])})
    == "words_out"
    and _runs.deciding_metric("d", runs=runs, goals={"g1": goal("DER", ["d"])}) == "a",
)
check(
    "rule: no goal and no primary metric: None when asked not to refuse",
    _runs.deciding_metric("d", runs=[rec("d", ["x"])], goals={}, refuse=False) is None,
)
said = refusal(runs=[rec("d", ["x", "y"])], goals={"g": goal("DER", ["d"])})
check(
    "rule: no goal and no primary metric: refused, naming what is recorded, the goal's unrecorded measure and --metric",
    "recorded: x, y" in said and "DER" in said and "--metric" in said,
    said,
)

# -- one project, the tutorial 9 shape ---------------------------------------------------------------------------------
proj = Path(tempfile.mkdtemp(prefix="evh-deciding-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-deciding", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

ADAPTER = """
from evaluation_harness.adapter import Result

METRIC_KINDS = {"words_out": "quality"}

def call_system(text, params):
    words = []
    for word in text.split()[: params["words"]]:
        words.append(word)
        if word.endswith("."):
            break
    return Result(output=" ".join(words), tokens_in=len(text.split()), tokens_out=len(words), cost_usd=0.0)

def score(output, reference):
    return {"words_out": float(len(output.split()))}
"""


def evh(*args):
    return _cli.run(proj, env, *args)


def result(r):
    return json.loads(r.stdout).get("result", {}) if r.returncode == 0 and r.stdout.strip() else {}


def metric_in(text: str) -> str | None:
    m = re.search(r"(?:ranked by: |metric=|read on )(\w+)", text)
    return m.group(1) if m else None


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
        (proj / "data" / "models").mkdir()
    shutil.copytree(HARNESS / "tutorial" / "tickets", proj / "tutorial" / "tickets")
    (proj / "adapters").mkdir()
    (proj / "adapters" / "headline.py").write_text(ADAPTER, encoding="utf-8")
    r = evh("dataset-create", "--dataset-id", "headlines_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "headlines_v1")
    _runstore.write_text(
        proj,
        "goals/headline_short.yaml",
        'goal_id: headline_short\nschema_version: "0.1"\ntitle: t\nstatement: s\ndecision: d\nstatus: active\n'
        "datasets:\n  - dataset_id: headlines_v1\nsuccess_criteria:\n  primary: {measure: words_out, direction: lower}\n",
    )
    for name, words in (("h6", 6), ("h9", 9), ("h12", 12)):
        _runstore.write_text(
            proj,
            f"systems/{name}_v1.yaml",
            f"system_id: {name}_v1\nadapter: adapters/headline.py\nparams:\n  words: {words}\n",
        )
        r = (
            r
            if r.returncode
            else evh(
                "run",
                "--system",
                f"{name}_v1",
                "--dataset",
                "headlines_v1",
                "--run-id",
                name,
                "--goal",
                "headline_short",
            )
        )
    check(
        "setup: three arms of an adapter with no PRIMARY_METRIC, run for a goal on words_out",
        r.returncode == 0,
        r.stderr[-300:],
    )

    read: dict = {}
    lb = evh("leaderboard", "headlines_v1")
    read["leaderboard"] = metric_in(lb.stdout)
    pt = evh("pair-test", "headlines_v1", "--a", "h6_v1", "--b", "h12_v1")
    read["pair-test"] = metric_in(pt.stdout) if pt.returncode == 0 else pt.stderr[-200:]
    ft = evh("family-test", "headlines_v1", "--a", "h6_v1", "--against", "h9_v1,h12_v1")
    read["family-test"] = metric_in(ft.stdout + ft.stderr) if ft.returncode == 0 else ft.stderr[-200:]
    rs = evh("rank-stability", "headlines_v1", "--draws", "20")
    # Six items are too few for it to rank (it says so and stops): what matters here is that it got past choosing a metric.
    text = rs.stdout + rs.stderr
    read["rank-stability"] = (
        metric_in(rs.stdout)
        if rs.returncode == 0
        else "words_out"
        if "too few for two disjoint halves" in text
        else text[-200:]
    )
    gl = result(evh("goal-leaderboard", "headline_short", "--json"))
    read["goal-leaderboard"] = gl.get("measure")
    read["inspector"] = result(evh("comparison-show", "--runs", "h6_v1,h12_v1", "--json")).get("metric")
    sh = result(evh("sheet-show", "headlines_v1", "--runs", "h6_v1,h12_v1", "--json"))
    read["sheet"] = metric_in(" ".join(ln for b in sh.get("blocks", []) for ln in b.get("lines", [])))
    check(
        "every reader that picks a metric reads words_out: leaderboard, pair-test, family-test, rank-stability, "
        "goal-leaderboard, the inspector, the sheet",
        set(read.values()) == {"words_out"},
        read,
    )
    rc = result(evh("run-compare", "--baseline", "h6", "--candidate", "h12", "--json"))
    rows = {
        x["metric"]: x["verdict"] for b in rc.get("blocks", []) for x in b.get("rows", []) if "verdict" in x
    }
    check(
        "run-compare lists every metric, and judges words_out by the goal's direction (more words: worse)",
        rows.get("words_out") == "worse",
        rows,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

# -- the source: nobody picks a default metric itself --------------------------------------------------------------------
SCRIPTS = HARNESS / "scripts"
#: Readers that choose a metric when none is named, and what each asks.
ASKS = (
    "pair_test.py",
    "family_test.py",
    "holdout_significance.py",
    "rank_stability.py",
    "period_compare.py",
    "_sheet.py",
    "leaderboard.py",
    "model/compare.py",
)
missing = [f for f in ASKS if "deciding_metric(" not in (SCRIPTS / f).read_text(encoding="utf-8")]
check("source: each reader that picks a default metric asks deciding_metric", not missing, missing)
old = [
    f.relative_to(SCRIPTS).as_posix()
    for f in sorted(SCRIPTS.rglob("*.py"))
    if re.search(r"\bdefault_metric\(", f.read_text(encoding="utf-8")) and f.name != "compare.py"
]
check(
    "source: `_runs.default_metric` is gone (one function answers)",
    not old and not hasattr(_runs, "default_metric"),
    old,
)

sys.exit(summary())
