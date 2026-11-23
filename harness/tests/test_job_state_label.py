#!/usr/bin/env python3
"""A job that ended with exit 6 (its checks ran and flagged something) reads "checked, flagged", not "failed", in every
listing: `evh jobs-status` (one job and all), the API's record, and the Workbench (scenario 080b N10).

    python tests/test_job_state_label.py

Three job records written as the supervisor writes them ($0, no server): a failed one with exit 6, a failed one with
exit 1 and a succeeded one. The state a job is filtered by stays the stored one (`failed`).
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore, _cli
os.environ.setdefault("EVAL_STORE", "files")
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-joblabel-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj))
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args):
    return _cli.run(proj, env, *args)


try:
    (proj / "data").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    for jid, state, code in (
        ("20261120T100000-a00006", "failed", 6),
        ("20261120T100001-a00001", "failed", 1),
        ("20261120T100002-a00000", "succeeded", 0),
    ):
        d = proj / ".build" / "jobs" / jid
        d.mkdir(parents=True)
        (d / "job.json").write_text(
            json.dumps({"id": jid, "operation": "arm-smoke", "inputs": {}, "by": "person:t"}),
            encoding="utf-8",
        )
        (d / "state.json").write_text(
            json.dumps({"state": state, "exit": code, "ended_at": "2026-11-20T10:00:00Z"}), encoding="utf-8"
        )
        (d / "log").write_text("", encoding="utf-8")
    from evaluation_harness import _jobs

    os.environ["EVAL_HOME"] = str(proj)
    one = evh("jobs-status", "20261120T100000-a00006")
    allj = evh("jobs-status")
    row = {x.split()[0]: x for x in allj.stdout.splitlines() if x.strip()}
    check(
        "jobs-status of one job: exit 6 reads 'checked, flagged', and the line still says exit: 6",
        "checked, flagged" in one.stdout
        and "failed" not in one.stdout.splitlines()[0]
        and "exit: 6" in one.stdout,
        one.stdout + one.stderr[-300:],
    )
    check(
        "jobs-status (all): exit 6 is 'checked, flagged', exit 1 stays 'failed', a pass 'succeeded'",
        "checked, flagged" in row.get("20261120T100000-a00006", "")
        and "failed" in row.get("20261120T100001-a00001", "")
        and "succeeded" in row.get("20261120T100002-a00000", ""),
        allj.stdout,
    )
    failed = evh("jobs-status", "--state", "failed")
    check(
        "--state failed still filters on the stored state: both failed jobs, the pass not",
        "100000-a00006" in failed.stdout
        and "100001-a00001" in failed.stdout
        and "100002-a00000" not in failed.stdout,
        failed.stdout,
    )
    got = {j["id"].split("-")[-1]: j.get("state_label") for j in _jobs.list_jobs()}
    check(
        "the API's job record carries the label the Workbench shows (one definition: _jobs.state_label)",
        got == {"a00006": "checked, flagged", "a00001": "failed", "a00000": "succeeded"},
        got,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
