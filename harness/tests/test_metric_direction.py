#!/usr/bin/env python3
"""Which way is better for a measure a goal decides on and no run records yet (the podcast eval-data project on v0.8.0:
`metric-list` said "DER (higher is better)" while its goal says `direction: lower`).

    EVAL_STORE=files python tests/test_metric_direction.py

  - `metric-list`, `metric-show` and the catalog's metrics page and metric page say lower when the goal deciding on the
    measure says lower, with no run recording it;
  - a measure no goal gives a direction to falls back to the name table as before (`cost_usd`: lower).
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-metric-direction-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-metric-direction")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args):
    return _cli.run(proj, env, *args)


def goal(gid: str, measure: str, direction: str | None) -> None:
    primary = f"{{measure: {measure}" + (f", direction: {direction}" if direction else "") + "}"
    _runstore.write_text(
        proj,
        f"goals/{gid}.yaml",
        f'goal_id: {gid}\nschema_version: "0.1"\ntitle: {gid}\nstatement: {gid}\ndecision: {gid}\nstatus: active\n'
        f"datasets: []\nsuccess_criteria:\n  primary: {primary}\n",
    )


def better(view: dict, metric: str) -> str:
    return next((m["better"] for m in view.get("metrics", []) if m["metric"] == metric), "")


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    goal("speaker_attribution", "der", "lower")
    goal("spend", "cost_usd", None)

    r = evh("metric-list", "--json")
    listed = json.loads(r.stdout).get("result", {}) if r.returncode == 0 else {}
    check(
        "metric-list: a measure only a goal names, the goal saying lower, is lower",
        better(listed, "der") == "lower",
        r.stdout[-600:] + r.stderr[-300:],
    )
    check(
        "metric-list: a goal with no direction leaves the name table's (cost_usd: lower)",
        better(listed, "cost_usd") == "lower",
        r.stdout[-600:],
    )
    r = evh("metric-show", "der", "--json")
    shown = json.loads(r.stdout).get("result", {}) if r.returncode == 0 else {}
    check(
        "metric-show: the same measure is lower",
        str(shown.get("better", "")).startswith("lower"),
        r.stdout[-600:] + r.stderr[-300:],
    )

    out = proj / "catalog"
    r = evh("catalog", "--out", out)
    page = (out / "metrics.html").read_text(encoding="utf-8") if (out / "metrics.html").exists() else ""
    row = page[page.find('id="m-der"') :][:3000] if 'id="m-der"' in page else ""
    row = row[: row.find("</tr>")]
    check(
        "the catalog's metrics page: der's row says lower",
        r.returncode == 0 and ">lower<" in row and ">higher<" not in row,
        r.stderr[-400:] + row[-800:],
    )
    own = (out / "m" / "der.html").read_text(encoding="utf-8") if (out / "m" / "der.html").exists() else ""
    check(
        "the catalog's page for der says lower is better",
        ">lower<" in own and ">higher<" not in own,
        own[own.find("better") :][:300] if own else "no m/der.html",
    )
    r = evh("validate")
    check(
        "validate: the goal that leaves `direction` out fails, naming direction (goal.schema.json)",
        r.returncode == 6 and "goals/spend.yaml: 'direction' is a required property" in r.stdout,
        "\n".join(x for x in r.stdout.splitlines() if "FAIL" in x or "goals/" in x)[:800],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
