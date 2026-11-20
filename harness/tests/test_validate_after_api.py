#!/usr/bin/env python3
"""A project the Workbench wrote still validates (scenario 080b, B1).

    python tests/test_validate_after_api.py

In a throwaway tutorial project ($0, offline) behind a real `evh catalog-serve`: `evh validate` passes first; then jobs
are started through the API as the Workbench starts them (open a round, run an arm, carry one in) with a typed name, so
every record they write says `from: api`; `evh validate` must still pass. Every schema that has the actor object also
lists `api` among the places a name can come from.
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
SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
KIT = HERE.parent / "tutorial"
os.environ.setdefault("EVAL_STORE", "files")
import _cli  # noqa: E402
import _runstore  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._actor import ORIGINS  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402


def origins(node, found):
    """Every `from` enum in a schema (the actor object's), however deep."""
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict) and "from" in node["properties"]:
            enum = node["properties"]["from"].get("enum")
            if enum:
                found.append(enum)
        for v in node.values():
            origins(v, found)
    elif isinstance(node, list):
        for v in node:
            origins(v, found)
    return found


with_actor = {}
for sp in sorted(SCHEMAS.glob("*.schema.json")):
    enums = origins(json.loads(sp.read_text()), [])
    if enums:
        with_actor[sp.name] = enums
check("setup: schemas with the actor object are found", len(with_actor) >= 6, sorted(with_actor))
check(
    "every schema's actor `from` enum names every origin a job may carry (and `migration`)",
    all(set(ORIGINS) | {"migration"} <= set(e) for es in with_actor.values() for e in es),
    {n: es for n, es in with_actor.items() if not all(set(ORIGINS) | {"migration"} <= set(e) for e in es)},
)

proj = Path(tempfile.mkdtemp(prefix="evh-vapi-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-vapi")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVAL_GOALS_DIR"):
    env.pop(k, None)
SERVERS: list[subprocess.Popen] = []


def evh(*args):
    return _cli.run(proj, env, *args)


def serve():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)],
        cwd=proj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    SERVERS.append(p)
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    return port, (proj / ".build" / "api-token").read_text().strip()


def call(method, path, body=None):
    h = {"Host": f"127.0.0.1:{PORT}", "Authorization": f"Bearer {TOKEN}", "X-EVH-Data": "1"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 — the test's own server  # nosec B310
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def job(path, body):
    """POST a route as a typed name and wait for the job's end: its state."""
    st, j = call("POST", f"/api/v1{path}", {**body, "by": "person:wb-typed"})
    if st != 202:
        return f"HTTP {st} {j}"
    end = time.monotonic() + 120
    while time.monotonic() < end:
        _st, rec = call("GET", f"/api/v1/jobs/{j['id']}")
        if rec.get("state") in ("succeeded", "failed", "cancelled", "lost"):
            if rec["state"] != "succeeded":
                log = proj / ".build" / "jobs" / j["id"] / "log"
                return (
                    f"{rec['state']} {rec.get('refusal')} {log.read_text()[-400:] if log.is_file() else ''}"
                )
            return rec["state"]
        time.sleep(0.2)
    return "timeout"


try:
    (proj / "data" / "systems").mkdir(parents=True)
    (proj / "data" / "goals").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    _runstore.write_text(
        proj, "goals/tickets_summary.yaml", (KIT / "goals" / "tickets_summary.yaml").read_text()
    )
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    r = r if r.returncode else evh(
        "label-import", "--sheet", str(KIT / "gold"), "--dataset-id", "tickets_v1", "--set", "g", "--by", "o"
    )  # fmt: skip
    r = r if r.returncode else evh(
        "reference-promote", "--dataset-id", "tickets_v1", "--labels", "g", "--tier", "gold",
        "--reason", "The kit's hand-written summaries decide.", "--by", "owner",
    )  # fmt: skip
    for arm in ("lead1", "lead2"):
        _runstore.write_text(
            proj, f"systems/tickets_{arm}_v1.yaml", (KIT / "systems" / f"tickets_{arm}_v1.yaml").read_text()
        )
        r = r if r.returncode else evh("run", "--system", f"tickets_{arm}_v1", "--dataset", "tickets_v1")
    _runstore.write_text(
        proj,
        "systems/tickets_lead3_v1.yaml",
        (KIT / "systems" / "tickets_lead2_v1.yaml")
        .read_text()
        .replace("tickets_lead2_v1", "tickets_lead3_v1"),
    )  # not run yet: its run through the API is its first (two runs of one system fail V8)
    r = r if r.returncode else evh("catalog")
    check("setup: dataset, gold, two arms run", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    v = evh("validate")
    check("before any API write, `evh validate` passes", v.returncode == 0, (v.stdout + v.stderr)[-600:])

    PORT, TOKEN = serve()
    states = [
        job(
            "/goals/tickets_summary/rounds",
            {"dataset": "tickets_v1", "keep": "tickets_lead1_v1", "hypothesis": "h"},
        ),
        job(
            "/systems/tickets_lead3_v1/runs",
            {"dataset": "tickets_v1", "max_cost_usd": 1, "round": "r1", "goal": "tickets_summary"},
        ),
    ]
    check("the jobs the Workbench starts succeed", states == ["succeeded", "succeeded"], states)
    doc = yaml.safe_load(_runstore.read_text(proj, "rounds/tickets_summary/r1.yaml"))
    check(
        "the round the API wrote records `from: api`",
        (doc.get("actor") or {}).get("from") == "api",
        doc.get("actor"),
    )
    v = evh("validate")
    check(
        "after API writes (round, run), `evh validate` passes",
        v.returncode == 0,
        (v.stdout + v.stderr)[:1800],
    )
finally:
    for p in SERVERS:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
