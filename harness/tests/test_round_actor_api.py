#!/usr/bin/env python3
"""Which actor a round record names when the Workbench sends a typed name and the server has EVH_ACTOR of its own.

    python tests/test_round_actor_api.py

The rule (RFC-026 "Who acted", RFC-027): the actor of a job is the job's `by`, and nothing of the server's environment
reaches it (`jobs_supervisor.py`); a record a job writes names it, `from: api`. The Workbench sends the name typed in
its name field as `by: person:NAME`. In a throwaway tutorial project ($0, offline) behind a `evh catalog-serve` started
with EVH_ACTOR=person:server-user and EVH_FOR=person:server-boss, the same three POSTs the Workbench makes (open a round,
retire an arm, close it with the run promoted) are made with a typed name that has a space and an accent, and the
round's record, the retirement and the closure each name that person and no one of the server's.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
KIT = HERE.parent / "tutorial"
import _cli  # noqa: E402
import _runstore  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-roundactor-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-roundactor")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVAL_GOALS_DIR", "EVH_ACTOR_FROM"):
    env.pop(k, None)
SERVER_ENV = dict(env, EVH_ACTOR="person:server-user", EVH_FOR="person:server-boss")
TYPED = "Zoë Ana"
SERVERS: list[subprocess.Popen] = []


def evh(*args):
    return _cli.run(proj, env, *args)


def serve():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)],
        cwd=proj, env=SERVER_ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    SERVERS.append(p)
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    return port, (proj / ".build" / "api-token").read_text(encoding="utf-8").strip()


def call(method, path, body=None):
    h = {"Host": f"127.0.0.1:{PORT}", "Authorization": f"Bearer {TOKEN}", "X-EVH-Data": "1"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def post(path, body):
    """POST as the Workbench does (the typed name as `by: person:NAME`); the job's final state."""
    st, j = call("POST", f"/api/v1{path}", {**body, "by": f"person:{TYPED}"})
    if st != 202:
        return {"state": f"HTTP {st}", "refusal": j}
    end = time.monotonic() + 120
    while time.monotonic() < end:
        _st, done = call("GET", f"/api/v1/jobs/{j['id']}")
        if done.get("state") in ("succeeded", "failed", "cancelled", "lost"):
            return done
        time.sleep(0.2)
    return {"state": "timeout"}


def round_doc():
    return yaml.safe_load(_runstore.read_text(proj, "rounds/tickets_summary/r1.yaml")) or {}


def names(who) -> tuple:
    who = who or {}
    return who.get("name"), who.get("from"), who.get("for")


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
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    r = (
        r
        if r.returncode
        else evh(
            "label-import",
            "--sheet",
            str(KIT / "gold"),
            "--dataset-id",
            "tickets_v1",
            "--set",
            "g",
            "--by",
            "o",
        )
    )
    r = r if r.returncode else evh(
        "reference-promote", "--dataset-id", "tickets_v1", "--labels", "g", "--tier", "gold",
        "--reason", "The kit's hand-written summaries decide.", "--by", "owner",
    )  # fmt: skip
    for arm in ("lead1", "lead2"):
        _runstore.write_text(
            proj,
            f"systems/tickets_{arm}_v1.yaml",
            (KIT / "systems" / f"tickets_{arm}_v1.yaml").read_text(encoding="utf-8"),
        )
        r = r if r.returncode else evh("run", "--system", f"tickets_{arm}_v1", "--dataset", "tickets_v1")
    r = r if r.returncode else evh("catalog")
    check("setup: the tutorial dataset, gold, two arms run", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    lead2 = sorted(n for n in _runstore.listdir(proj, "runs") if n.startswith("tickets_lead2_v1_"))[-1]
    PORT, TOKEN = serve()

    done = post(
        "/goals/tickets_summary/rounds",
        {
            "dataset": "tickets_v1",
            "keep": "tickets_lead1_v1,tickets_lead2_v1",
            "hypothesis": "which summariser",
        },
    )
    check("round-open through the API succeeded", done.get("state") == "succeeded", done)
    doc = round_doc()
    check(
        "round-open: the round names the typed person, not the server's EVH_ACTOR or EVH_FOR",
        names(doc.get("actor")) == (TYPED, "api", None),
        doc.get("actor"),
    )
    done = post(
        "/goals/tickets_summary/rounds/r1/retire",
        {"arm": "tickets_lead1_v1", "reason": "one sentence is too few"},
    )
    check("round-retire through the API succeeded", done.get("state") == "succeeded", done)
    gone = next((a for a in round_doc().get("arms", []) if a["system"] == "tickets_lead1_v1"), {})
    check(
        "round-retire: the retirement names the typed person",
        names((gone.get("retired") or {}).get("actor")) == (TYPED, "api", None),
        gone.get("retired"),
    )
    done = post(
        "/goals/tickets_summary/rounds/r1/close",
        {"conclusion": "two sentences lead on the tutorial's six tickets", "promote": lead2},
    )
    check("round-close through the API succeeded", done.get("state") == "succeeded", done)
    doc = round_doc()
    shown = {k: v for k, v in doc.items() if "actor" in k or k in ("closed", "conclusion")}
    found = [names(v) for k, v in doc.items() if isinstance(v, dict) and "actor" in v] + [
        names(doc.get("actor"))
    ]
    check(
        "round-close: nothing in the closed round names the server's user or its boss",
        "server-user" not in json.dumps(doc) and "server-boss" not in json.dumps(doc) and bool(found),
        shown,
    )
    base = next(iter(_runstore.listdir(proj, "baselines/tickets_summary/tickets_v1")), "")
    promoted = (
        json.loads(_runstore.read_text(proj, f"baselines/tickets_summary/tickets_v1/{base}")) if base else {}
    )
    check(
        "round-close --promote: the baseline names the typed person",
        names(promoted.get("actor")) == (TYPED, "api", None),
        promoted.get("actor"),
    )
finally:
    for p in SERVERS:
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
