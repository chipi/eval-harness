#!/usr/bin/env python3
"""`evh jobs-start run` says at the start what the job cannot do (0.8.1 scenario, step 12).

    python tests/test_jobs_start_warns.py

A run job over a dataset with no reference set scores nothing, and one with no goal is measured for none. The log said so,
but only after the job began; the terminal now says it as the job starts, as a warning: a refusal would break the
Workbench's and every script's runs of a free arm that only wants its outputs. A dataset with a reference and a run
with a goal get no warning.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("EVAL_STORE", "files")
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

KIT = HARNESS / "tutorial"
proj = Path(tempfile.mkdtemp(prefix="evh-jobwarn-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-jobwarn", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVH_ACTOR", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args):
    return _cli.run(proj, env, *args)


SERVERS: list[subprocess.Popen] = []


def serve() -> tuple[int, str]:
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), "catalog-serve", "--port", str(port)],
        cwd=proj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    SERVERS.append(p)
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    return port, (proj / ".build" / "api-token").read_text(encoding="utf-8").strip()


def start_job(port: int, token: str, inputs: dict) -> dict:
    """POST /api/v1/jobs a run, as the Workbench does: the 202's body, once the job it started has ended."""
    body = {"operation": "run", "inputs": inputs, "by": "person:t", "max_cost_usd": 0.01}
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/jobs",
        data=json.dumps(body).encode(),
        headers={"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}", "X-EVH-Data": "1"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 — the test's own server  # nosec B310
        assert r.status == 202, r.status
        j = json.loads(r.read())
    finished(j["id"])
    return j


def finished(out: str) -> None:
    """Let the job a start printed end, so the folder is not removed under it."""
    job = out.split()[0] if out.split() else ""
    path = proj / ".build" / "jobs" / job / "state.json"
    end = time.monotonic() + 120
    while time.monotonic() < end:
        if path.is_file() and json.loads(path.read_text(encoding="utf-8")).get("state") in (
            "succeeded", "failed", "cancelled", "lost",
        ):  # fmt: skip
            return
        time.sleep(0.3)


try:
    (proj / "data" / "systems").mkdir(parents=True)
    (proj / "data" / "goals").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    _runstore.write_text(
        proj,
        "goals/tickets_summary.yaml",
        (KIT / "goals" / "tickets_summary.yaml").read_text(encoding="utf-8"),
    )
    _runstore.write_text(
        proj,
        "systems/tickets_lead1_v1.yaml",
        (KIT / "systems" / "tickets_lead1_v1.yaml").read_text(encoding="utf-8"),
    )
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: a dataset with no reference", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    PORT, TOKEN = serve()
    j = start_job(PORT, TOKEN, {"system": "tickets_lead1_v1", "dataset": "tickets_v1"})
    check(
        "the API's 202 carries the same warnings jobs-start prints: no reference, no goal",
        any(
            "no reference set for tickets_v1" in w and "evh reference-promote" in w
            for w in j.get("warnings", [])
        )
        and any("no goal" in w and "--arg goal=" in w for w in j.get("warnings", [])),
        str(j.get("warnings")),
    )

    start = (
        "jobs-start",
        "--by",
        "person:t",
        "run",
        "--arg",
        "system=tickets_lead1_v1",
        "--arg",
        "dataset=tickets_v1",
    )
    r = evh(*start, "--max-cost-usd", "0.01")
    finished(r.stdout)
    check(
        "a run job on a dataset with no reference: still starts, and the warning names the missing reference and the fix",
        r.returncode == 0
        and "WARNING" in r.stdout
        and "no reference set for tickets_v1" in r.stdout
        and "nothing will be scored" in r.stdout
        and "evh reference-promote" in r.stdout,
        r.stdout + r.stderr,
    )
    check(
        "...and the missing goal, with the input that names it",
        "no goal" in r.stdout and "--arg goal=" in r.stdout,
        r.stdout,
    )

    r = evh(
        "label-import", "--sheet", str(KIT / "gold"), "--dataset-id", "tickets_v1", "--set", "g", "--by", "o"
    )
    r = r if r.returncode else evh(
        "reference-promote", "--dataset-id", "tickets_v1", "--labels", "g", "--tier", "gold",
        "--reason", "The kit's hand-written summaries decide.", "--by", "owner",
    )  # fmt: skip
    check("setup: gold promoted", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    r = evh(*start, "--arg", "goal=tickets_summary", "--max-cost-usd", "0.01")
    finished(r.stdout)
    check(
        "a reference and a goal: no warning",
        r.returncode == 0 and "WARNING" not in r.stdout,
        r.stdout + r.stderr,
    )
    j = start_job(
        PORT, TOKEN, {"system": "tickets_lead1_v1", "dataset": "tickets_v1", "goal": "tickets_summary"}
    )
    check(
        "the API, a reference and a goal: an empty warnings list",
        j.get("warnings") == [],
        str(j.get("warnings")),
    )
finally:
    for sp in SERVERS:
        sp.terminate()
        sp.wait(timeout=10)
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
