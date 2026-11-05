#!/usr/bin/env python3
"""`--cluster FIELD` and a goal's `cluster:`, through the commands (A1 of PLAN_0.8.0).

    python tests/test_cluster_commands.py

In a throwaway project with the tutorial's six tickets, its gold and two arms: the tickets' `area` has five
values (two tickets are about `account`). pair-test and family-test with `--cluster area` test five units, and
pair-test's p is the sign-flip p of the five clusters' summed differences; a goal naming `cluster: area` says
so in `evh goals`; validate refuses a goal whose cluster field no item carries; an unknown field is refused.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
from evaluation_harness import stats  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-cluster-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-cluster")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )


def ok(r, what):
    check(f"setup: {what}", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    return r.returncode == 0


try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    (data / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    shutil.copytree(KIT / "fields", data / "fields")
    ready = ok(
        evh(
            "dataset-create",
            "--dataset-id",
            "tickets_v1",
            "--source-dir",
            "tutorial/tickets",
            "--fieldset",
            "tickets",
            "--fields",
            str(KIT / "ticket_fields.csv"),
        ),
        "the dataset",
    )
    ready = ready and ok(evh("dataset-materialize", "--dataset-id", "tickets_v1"), "materialized")
    ready = ready and ok(
        evh(
            "label-import",
            str(KIT / "gold"),
            "--dataset-id",
            "tickets_v1",
            "--set",
            "owner_gold",
            "--by",
            "owner",
        ),
        "gold labels",
    )
    ready = ready and ok(
        evh(
            "reference-promote",
            "--dataset-id",
            "tickets_v1",
            "--labels",
            "owner_gold",
            "--tier",
            "gold",
            "--reason",
            "The kit's hand-written summaries decide.",
            "--by",
            "owner",
        ),
        "gold promoted",
    )
    goal = (KIT / "goals" / "tickets_summary.yaml").read_text()
    goal = goal.replace(
        "{dataset_id: tickets_v1, role: validation,",
        "{dataset_id: tickets_v1, cluster: area, role: validation,",
    )
    (data / "goals" / "tickets_summary.yaml").write_text(goal)
    for arm in ("lead1", "lead2"):
        (data / "configs" / f"{arm}.yaml").write_text(
            (KIT / "configs" / f"tickets_{arm}.yaml").read_text() + "goal: tickets_summary\n"
        )
        ready = ready and ok(evh("run", "--config", str(data / "configs" / f"{arm}.yaml")), f"run {arm}")
    if not ready:
        sys.exit(summary())

    r = evh(
        "pair-test",
        "--dataset-id",
        "tickets_v1",
        "--a",
        "tickets_lead2_v1",
        "--b",
        "tickets_lead1_v1",
        "--cluster",
        "area",
        "--json",
    )
    v = json.loads(r.stdout)["result"]["values"] if r.returncode == 0 else {}
    # The expected p from the runs' own per-item scores: summed per area, five units.
    per = {}
    for arm in ("tickets_lead1_v1", "tickets_lead2_v1"):
        run = next((data / "runs").glob(f"{arm}_*"))
        rows = [json.loads(x) for x in (run / "predictions.jsonl").read_text().splitlines() if x.strip()]
        per[arm] = {x["item_id"]: x[v.get("metric", "overlap_f1")] for x in rows}
    area = {
        "t01_login": "account",
        "t02_invoice": "billing",
        "t03_export": "data",
        "t04_api": "api",
        "t05_delete": "account",
        "t06_mobile": "mobile",
    }
    diffs = {i: per["tickets_lead2_v1"][i] - per["tickets_lead1_v1"][i] for i in per["tickets_lead1_v1"]}
    totals, _ = stats.clustered(diffs, area)
    check(
        "pair-test --cluster area: 5 clusters of 6 items, p the sign-flip p of their sums",
        v.get("clusters") == 5
        and v.get("n") == 6
        and v.get("cluster") == "area"
        and v.get("p") == stats.sign_flip_p(totals),
        (r.stdout + r.stderr)[-400:],
    )
    r = evh(
        "pair-test",
        "--dataset-id",
        "tickets_v1",
        "--a",
        "tickets_lead2_v1",
        "--b",
        "tickets_lead1_v1",
        "--cluster",
        "area",
    )
    check(
        "pair-test prints the clusters it tested", "clusters           5 by area" in r.stdout, r.stdout[-400:]
    )
    r = evh(
        "pair-test",
        "--dataset-id",
        "tickets_v1",
        "--a",
        "tickets_lead2_v1",
        "--b",
        "tickets_lead1_v1",
        "--margin",
        "0.05",
        "--json",
    )
    ni = (json.loads(r.stdout)["result"]["values"].get("noninferior") or {}) if r.returncode == 0 else {}
    check(
        "pair-test --margin runs the goals' contender test: 6 items of a continuous score are too few",
        ni.get("verdict") == "too few" and ni.get("method") == "bootstrap-t" and ni.get("margin") == 0.05,
        (r.stdout + r.stderr)[-400:],
    )

    r = evh(
        "family-test",
        "--dataset-id",
        "tickets_v1",
        "--a",
        "tickets_lead2_v1",
        "--against",
        "lead1",
        "--cluster",
        "area",
        "--json",
    )
    fv = json.loads(r.stdout)["result"]["values"] if r.returncode == 0 else {}
    r = evh("inspect", "--runs", "tickets_lead1_v1,tickets_lead2_v1", "--json")
    check(
        "the inspector tests by the goal's cluster too, and says so",
        r.returncode == 0 and "Tested by area" in r.stdout and "(5 clusters)" in r.stdout,
        (r.stdout + r.stderr)[-400:],
    )
    check(
        "family-test --cluster area: recorded in its answer",
        fv.get("cluster") == "area",
        (r.stdout + r.stderr)[-300:],
    )

    r = evh("goals", "--goal", "tickets_summary", "--json")
    check(
        "a goal naming cluster: area says its tests are by area",
        r.returncode == 0 and "Tested by area" in r.stdout,
        (r.stdout + r.stderr)[-400:],
    )

    r = evh(
        "pair-test",
        "--dataset-id",
        "tickets_v1",
        "--a",
        "tickets_lead2_v1",
        "--b",
        "tickets_lead1_v1",
        "--cluster",
        "no_such_field",
    )
    check(
        "an unknown cluster field is refused (not-found)",
        r.returncode == 1 and "ERROR (not-found)" in r.stderr,
        r.stderr[-200:],
    )

    (data / "goals" / "tickets_summary.yaml").write_text(goal.replace("cluster: area", "cluster: araa"))
    r = evh("validate")
    check(
        "validate: a goal whose cluster field no item carries fails V14",
        r.returncode == 6 and "cluster 'araa' on tickets_v1: no item carries that field" in r.stdout,
        r.stdout[-400:],
    )
finally:
    if not os.environ.get("EVH_TEST_KEEP"):
        shutil.rmtree(proj, ignore_errors=True)
    else:
        print("kept", proj)
sys.exit(summary())
