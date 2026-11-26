#!/usr/bin/env python3
"""`evh arm-list` on an arm that is the goal's baseline and that a round retired (SCENARIO, "From earlier runs").

    python tests/test_arm_list_baseline_retired.py

In a throwaway project ($0, offline): round r1 closes promoting a run of tickets_lead2_v1, so it is the goal's
baseline; round r2 opens from r1 keeping that arm, then retires it. A round retires an arm from its own line-up, never
from the goal: the baseline stays the goal's until a round promotes another (RFC-027, RFC-004). `arm-list` says both
facts of the arm in one cell, in the text, the `--json` roles and the API.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

KIT = HERE.parent / "tutorial"
proj = Path(tempfile.mkdtemp(prefix="evh-armlist-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-armlist")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args):
    return _cli.run(proj, env, *args)


def out(r):
    return r.stdout + r.stderr


try:
    data = proj / "data"
    (data / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    (data / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    _runstore.write_text(
        proj,
        "goals/tickets_summary.yaml",
        (KIT / "goals" / "tickets_summary.yaml").read_text(encoding="utf-8"),
    )
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset", r.returncode == 0, out(r)[-300:])
    r = evh(
        "label-import",
        "--sheet",
        str(KIT / "gold"),
        "--dataset-id",
        "tickets_v1",
        "--set",
        "owner_gold",
        "--by",
        "owner",
    )
    r = r if r.returncode else evh(
        "reference-promote", "--dataset-id", "tickets_v1", "--labels", "owner_gold", "--tier", "gold",
        "--reason", "The kit's hand-written summaries decide.", "--by", "owner",
    )  # fmt: skip
    check("setup: the kit's gold, promoted", r.returncode == 0, out(r)[-300:])
    for arm in ("lead1", "lead2"):
        _runstore.write_text(
            proj,
            f"systems/tickets_{arm}_v1.yaml",
            (KIT / "systems" / f"tickets_{arm}_v1.yaml").read_text(encoding="utf-8"),
        )
        r = evh("run", "--system", f"tickets_{arm}_v1", "--dataset", "tickets_v1")
        check(f"setup: {arm} ran", r.returncode == 0, out(r)[-300:])
    r = evh(
        "round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1", "--hypothesis", "how many sentences",
        "--keep", "tickets_lead1_v1,tickets_lead2_v1",
    )  # fmt: skip
    check("setup: r1 open", r.returncode == 0, out(r)[-300:])
    listed = json.loads(evh("runs-list", "--json").stdout)["result"]["runs"]
    run_id = next((x["run_id"] for x in listed if x["system_id"] == "tickets_lead2_v1"), "")
    check("setup: the lead2 run is listed", bool(run_id), listed)
    r = evh(
        "round-close", "--goal", "tickets_summary", "--round", "r1",
        "--conclusion", "two sentences lead on the tutorial's six tickets", "--promote", run_id,
    )  # fmt: skip
    check("setup: r1 closed, the lead2 run promoted", r.returncode == 0, out(r)[-300:])
    r = evh(
        "round-open",
        "--goal",
        "tickets_summary",
        "--dataset",
        "tickets_v1",
        "--from",
        "r1",
        "--keep",
        "tickets_lead2_v1",
    )
    check("setup: r2 open with the baseline arm kept", r.returncode == 0, out(r)[-300:])
    r = evh(
        "round-retire", "--goal", "tickets_summary", "--round", "r2", "--arm", "tickets_lead2_v1",
        "--reason", "the next round tries three sentences instead",
    )  # fmt: skip
    check("setup: r2 retires the baseline arm", r.returncode == 0, out(r)[-300:])

    r = evh("arm-list", "--json")
    arms = json.loads(r.stdout)["result"]["arms"] if r.returncode == 0 else []
    roles = {a["arm"].rsplit("/", 1)[-1]: a.get("roles") for a in arms}
    want = ["retired in r2; still the goal's baseline"]
    check(
        "arm-list --json: the baseline a round retired says both facts in one role",
        roles.get("tickets_lead2_v1") == want,
        roles,
    )
    check(
        "arm-list --json: the arm no round touched keeps its roles",
        roles.get("tickets_lead1_v1") == ["leader", "recommended"],
        roles,
    )
    text = out(evh("arm-list"))
    check(
        "arm-list: the text says it is retired in r2 and still the goal's baseline",
        "retired in r2; still the goal's baseline" in text and "baseline, retired" not in text,
        text[-700:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
