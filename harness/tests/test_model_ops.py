#!/usr/bin/env python3
"""The model's models and deployments (RFC-032 step 2), through both surfaces.

    python tests/test_model_ops.py

In a project `evh init` makes: a model made with `evh model-new` and a deployment with `evh deployment-new`, each in
its own file; an id that is taken, a deployment of no model, and a deployment's checks edited by hand are refused with
nothing written; `deployment-accept` keeps the acceptance and the decision (who, why) in the deployment's checks, and
refuses a why that is not a sentence; the deployment's saves are its history; the API's resources give the command
line's answers, and its writes go through the same model, recorded as who sent them.
"""

from __future__ import annotations

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

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
import yaml  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-models-"))
env = dict(
    os.environ,
    EVH_ACTOR="person:tester",
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-model-ops",
    EVAL_STORE="files",
)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project."""
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def result(r: subprocess.CompletedProcess) -> dict:
    """A --json command's result."""
    return json.loads(r.stdout)["result"]


def serve() -> tuple[subprocess.Popen, int]:
    """catalog-serve on a free port, once it answers."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return p, port
        except OSError:
            time.sleep(0.1)
    p.kill()
    raise RuntimeError(f"the server did not start: {(p.communicate()[0] or '')[-500:]}")


def call(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """One API call with the server's token."""
    token = (proj / ".build" / "api-token").read_text().strip()
    h = {"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}", "X-EVH-Data": "1"}
    raw = json.dumps(body).encode() if body is not None else None
    if raw is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1{path}", data=raw, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b"{}"
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"text": raw.decode(errors="replace")[-500:]}


MODEL = proj / "data" / "models" / "gem.yaml"
DEP = proj / "data" / "deployments" / "gem" / "mac.yaml"


def stored(p: Path) -> dict:
    return yaml.safe_load(p.read_text()) if p.is_file() else {}


try:
    r = evh("init")
    r = r if r.returncode else evh("catalog")
    check("setup: a project and its catalog", r.returncode == 0, (r.stdout + r.stderr)[-300:])

    made = evh("model-new", "gem", "--set", "kind=llm", "--set", "aliases.0=gem:1b", "--set", "weights=open")
    check(
        "model-new makes the model's own record, no deployments in it",
        made.returncode == 0
        and stored(MODEL).get("aliases") == ["gem:1b"]
        and "deployments" not in stored(MODEL),
        (made.stdout + made.stderr)[-300:],
    )
    again = evh("model-new", "gem", "--set", "kind=llm", "--set", "aliases.0=x")
    check(
        "model-new refuses an id that is taken",
        again.returncode == 1 and "ERROR (would-overwrite)" in again.stderr,
        again.stderr[-200:],
    )
    dep = evh("deployment-new", "gem", "mac", "--set", "where=mac", "--set", "backend=metal")
    check(
        "deployment-new makes the deployment's own record, under its model",
        dep.returncode == 0
        and {k: stored(DEP).get(k) for k in ("model_id", "deployment_id", "where")}
        == {"model_id": "gem", "deployment_id": "mac", "where": "mac"},
        (dep.stdout + dep.stderr)[-300:],
    )
    orphan = evh("deployment-new", "nope", "mac", "--set", "where=mac")
    check(
        "deployment-new refuses a deployment of a model that does not exist; nothing written",
        orphan.returncode == 1
        and "no model 'nope' in this project" in orphan.stderr
        and not (proj / "data" / "deployments" / "nope").exists(),
        orphan.stderr[-300:],
    )
    before = DEP.read_text()
    hand = evh("deployment-set", "gem", "mac", "--set", "checks.0.kind=smoke")
    check(
        "deployment-set refuses the checks: they are the deployment's history; nothing written",
        hand.returncode == 1 and "ERROR (not-allowed)" in hand.stderr and DEP.read_text() == before,
        hand.stderr[-300:],
    )
    short = evh("deployment-accept", "gem", "mac", "--flag", "reasoning: 3 calls", "--why", "fine")
    check(
        "deployment-accept refuses a why that is not a sentence; nothing written",
        short.returncode == 1 and "must be a sentence" in short.stderr and DEP.read_text() == before,
        short.stderr[-300:],
    )
    acc = evh(
        "deployment-accept",
        "gem",
        "mac",
        "--flag",
        "reasoning: 3 calls",
        "--why",
        "it cannot stop reasoning at all",
    )
    rec = stored(DEP)
    last = (rec.get("checks") or [{}])[-1]
    check(
        "deployment-accept: the kind is accepted with why, and the decision is a check with who made it",
        acc.returncode == 0
        and rec.get("accepted") == {"reasoning": "it cannot stop reasoning at all"}
        and last.get("kind") == "approval"
        and last.get("accepted") == ["reasoning"]
        and last.get("by") == "person:tester"
        and last.get("at"),
        (acc.stderr[-300:], rec),
    )
    shown = evh("deployment-show", "gem", "mac")
    check(
        "deployment-show says what the deployment accepts, and why",
        shown.returncode == 0 and "accepted    reasoning: it cannot stop reasoning at all" in shown.stdout,
        shown.stdout[-400:],
    )
    h = result(evh("deployment-history", "gem", "mac", "--json"))
    check(
        "each save of the deployment is in its history, newest first, with who made it",
        [x["by"] for x in h["saves"]] == ["person:tester", "person:tester"] and h["saves"][1]["was"] is None,
        h,
    )

    srv, port = serve()
    try:
        cli = {
            name: result(evh(name, *args, "--json"))
            for name, args in (
                ("model-list", ()),
                ("model-show", ("gem",)),
                ("deployment-show", ("gem", "mac")),
                ("deployment-history", ("gem", "mac")),
            )
        }
        api = {
            "model-list": call(port, "GET", "/models")[1].get("result"),
            "model-show": call(port, "GET", "/models/gem")[1].get("result"),
            "deployment-show": call(port, "GET", "/models/gem/deployments/mac")[1].get("result"),
            "deployment-history": call(port, "GET", "/models/gem/deployments/mac/history")[1].get("result"),
        }
        check("the API's resources give the command line's answers", api == cli, (api, cli))
        code, body = call(
            port,
            "POST",
            "/models/gem/deployments/mac/accept",
            {"flag": "where it ran: not pinned", "why": "a gateway has no build to pin", "by": "person:api"},
        )
        last = (stored(DEP).get("checks") or [{}])[-1]
        check(
            "the API's accept goes through the model, recorded as who sent it",
            code == 200 and last.get("by") == "person:api" and last.get("accepted") == ["where it ran"],
            (code, body),
        )
        before = DEP.read_text()
        code, _ = call(
            port,
            "PATCH",
            "/models/gem/deployments/mac",
            {"set": {"checks.0.kind": "smoke"}, "by": "person:api"},
        )
        missing = call(port, "GET", "/models/gem/deployments/nope")[0]
        check(
            "the API refuses: the checks edited by hand, a deployment that does not exist; nothing written",
            400 <= code < 500 and missing == 404 and DEP.read_text() == before,
            (code, missing),
        )
    finally:
        srv.terminate()
        srv.wait(timeout=20)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
