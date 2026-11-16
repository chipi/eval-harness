#!/usr/bin/env python3
"""What the API serves and its read side (RFC-026 step 2, RFC-032).

    python tests/test_api.py

Every command is an operation or named as not served, with why; how a job takes each input (a value, an upload, an
artifact, or not at all: what loads code or reaches outside the project). Each input that names a file says how a call
carries it, and one whose description offers path.py:Class or @file has a pattern: test_op_declarations.py checks both
for every operation. Then a real `evh
catalog-serve` in a throwaway tutorial project ($0, offline): no token, a wrong one, another Host and a foreign Origin
are refused (on a read resource of the model, GET /api/v1/goals); the token works as a bearer and as the cookie the
session route sets; the operations that list datasets and arms and compare arms answer, through the API, exactly what
their command answers with --json (parity); a system id that does not exist is refused before anything runs; a
server started --public or --behind-proxy answers no /api/v1/ call. (RFC-032 step 9 removed POST /api/v1/read/<command>
and GET /api/v1/commands: test_openapi.py checks they answer 404.)
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
KIT = HERE.parent / "tutorial"
from evaluation_harness import _api, ops  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.cli import COMMANDS  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402

check(
    "every command is an operation or named as not served, with why (and none is both)",
    set(COMMANDS) == set(ops.OPS) | set(_api.NOT_SERVED) and not set(ops.OPS) & set(_api.NOT_SERVED),
    (
        sorted(set(COMMANDS) - set(ops.OPS) - set(_api.NOT_SERVED)),
        sorted(set(ops.OPS) & set(_api.NOT_SERVED)),
    ),
)
from evaluation_harness.ops import OPS  # noqa: E402


def takes(command: str, name: str) -> str | None:
    """How a job of `command` takes the input `name` (as the option is spelled): value, upload, artifact, or None
    when it takes none (an operation's `tool_hidden`, or no such input)."""
    op = OPS[command]
    key = name.replace("-", "_")
    spec = op.inputs.get(key)
    if spec is None or key in op.tool_hidden:
        return None
    return {"upload": "upload", "artifact": "artifact"}.get(spec.get("x-file"), "value")


check(
    "never taken: --adapter, a sweep or rescore output folder, a source folder",
    takes("run", "adapter") is None
    and takes("rescore", "out") is None
    and takes("dataset-create", "source-dir") is None,
)
check(
    "kinds: run's system is a plain value (found by id, not a path), a dataset's fields file an upload, exposure-check's out an artifact; spenders marked",
    takes("run", "system") == "value"
    and takes("dataset-create", "fields") == "upload"
    and takes("exposure-check", "out") == "artifact"
    and OPS["run"].spends
    and not OPS["leaderboard"].is_job()  # a read answers in its own resource, never as a job
    and OPS["run"].is_job(),
)

proj = Path(tempfile.mkdtemp(prefix="evh-api-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-api")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(*extra):
    port = free_port()
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port), *extra],
        cwd=proj,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    for _ in range(200):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return p, port
        except OSError:
            time.sleep(0.1)
    p.kill()
    raise RuntimeError(p.stdout.read() if p.stdout else "server did not start")


def call(port, method, path, body=None, headers=None, host=None):
    h = {"Host": host or f"127.0.0.1:{port}", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 — the test's own server  # nosec B310
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(), dict(exc.headers)


try:
    (proj / "data" / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    r = evh("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tk_v1")
    r = (
        r
        if r.returncode
        else evh(
            "label-import", "--sheet", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t"
        )
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold",
            "--reason", "the kit's summaries, for the API test", "--by", "t",
        )
    )  # fmt: skip
    for cid, n in (("one_v1", 1), ("two_v1", 2)):
        _runstore.write_text(
            proj,
            f"systems/{cid}.yaml",
            f"system_id: {cid}\nparams:\n  provider: echo\n  sentences: {n}\n",
        )
        r = r if r.returncode else evh("run", "--system", cid, "--dataset", "tk_v1")
    r = r if r.returncode else evh("catalog")
    check("setup: a project with two arms and its catalog", r.returncode == 0, (r.stdout + r.stderr)[-300:])

    srv, port = serve()
    try:
        tok_file = proj / ".build" / "api-token"
        token = tok_file.read_text().strip() if tok_file.exists() else ""
        check(
            "the token: written to .build/api-token, readable by its owner only",
            bool(token) and (tok_file.stat().st_mode & 0o777) == 0o600,
            oct(tok_file.stat().st_mode & 0o777) if tok_file.exists() else "missing",
        )
        bearer = {"Authorization": f"Bearer {token}"}
        st, _b, _h = call(port, "GET", "/api/v1/goals")
        st2, _b, _h = call(port, "GET", "/api/v1/goals", headers={"Authorization": "Bearer nope"})
        st3, _b, _h = call(port, "GET", "/api/v1/goals", headers=bearer, host="evil.example")
        st4, _b, _h = call(port, "GET", "/api/v1/goals", headers={**bearer, "Origin": "http://evil.example"})
        check(
            "refused: no token (401), a wrong one (401), another Host (403), a foreign Origin (403)",
            (st, st2, st3, st4) == (401, 401, 403, 403),
            (st, st2, st3, st4),
        )
        st, _b, hd = call(port, "GET", f"/api/v1/session?token={token}")
        cookie = (hd.get("Set-Cookie") or "").split(";")[0]
        st2, _b, _h = call(port, "GET", "/api/v1/goals", headers={"Cookie": cookie})
        check(
            "the session route trades the token for an HttpOnly, SameSite=Strict cookie, which then works",
            st == 204
            and "HttpOnly" in (hd.get("Set-Cookie") or "")
            and "SameSite=Strict" in (hd.get("Set-Cookie") or "")
            and st2 == 200,
            (st, hd.get("Set-Cookie"), st2),
        )

        def arm_ids(node):
            """The ids of the arms an arm-list answer holds."""
            if isinstance(node, dict):
                yield from ([node["arm"]] if isinstance(node.get("arm"), str) else [])
                for v in node.values():
                    yield from arm_ids(v)
            elif isinstance(node, list):
                for v in node:
                    yield from arm_ids(v)

        arms = sorted(set(arm_ids(json.loads(evh("arm-list", "--json").stdout))))
        parity = {"two arms to compare": len(arms) == 2}
        for op, route, argv in (
            ("dataset-list", "/api/v1/datasets", []),
            ("arm-list", "/api/v1/arms", []),
            ("arm-list", "/api/v1/arms?dataset=tk_v1", ["--dataset", "tk_v1"]),
            (
                "comparison-show",
                f"/api/v1/compare?runs={','.join(arms)}&baseline={arms[0]}",
                ["--runs", ",".join(arms), "--baseline", arms[0]],
            ),
        ):
            st, body, _h = call(port, "GET", route, headers=bearer)
            cli = evh(op, *argv, "--json")
            parity[route] = (st, cli.returncode) == (200, 0) and json.loads(body) == json.loads(cli.stdout)
        check(
            "parity: an operation through the API answers exactly the command's --json (dataset-list, arm-list, comparison-show)",
            all(parity.values()),
            parity,
        )
        try:
            _api.operation_inputs(
                OPS["run"], {"system": "nope_v1", "dataset": "tk_v1"}, "20261116T000000-000000"
            )
            ok = False
        except _api.Refused as exc:
            ok = exc.status == 404 and "no system" in str(exc)
        check("a name that does not exist (a system id) is refused", ok)

        def refused(command: str, args: dict) -> bool:
            """Whether a job of `command` with these arguments is refused before it exists, by the operation's schema
            (the pattern of an input)."""
            try:
                _api.operation_inputs(
                    OPS[command], {k.replace("-", "_"): v for k, v in args.items()}, "20261116T000000-000000"
                )
            except _api.Refused:
                return True
            return False

        # Values the command line takes as a file to read or code to load, which the API never takes (RFC-026,
        # "No argument is a free path"): each was passed to its command as a plain value until 2026-11-13.
        never = {
            "capture --importer path.py:Class (code)": refused(
                "capture", {"importer": "importers/x.py:Importer", "query": "{}", "capture": "c1"}
            ),
            "importer-check importer path.py:Class (code)": refused(
                "importer-check", {"importer": "x.py:Importer"}
            ),
            "dataset-create --source path.py:Class (code)": refused(
                "dataset-create", {"source": "sources/x.py:Source", "dataset-id": "d1"}
            ),
            "capture --query @file (a server file)": refused(
                "capture", {"importer": "jsonl", "query": "@/etc/hostname", "capture": "c1"}
            ),
            "importer-check --query @file (a server file)": refused(
                "importer-check", {"importer": "jsonl", "query": "@/etc/hostname"}
            ),
        }
        check("a code path or an @file is refused before anything runs", all(never.values()), never)
        put_file = ops.OPS["data-put"].inputs["file"]
        check(
            "data-put's file is an upload, never a path on the server",
            put_file.get("x-file") == "upload",
            put_file,
        )
        check(
            "a name is still taken (capture --importer jsonl, dataset-create --source folder)",
            not refused("capture", {"importer": "jsonl", "query": "{}", "capture": "c1"})
            and not refused("dataset-create", {"source": "folder", "dataset-id": "d1"}),
        )
    finally:
        srv.terminate()
        srv.wait(timeout=10)

    for mode in (("--public", "a.example"), ("--behind-proxy", "evals.example")):
        srv, port = serve(*mode, *(("--bind", "0.0.0.0") if mode[0] == "--behind-proxy" else ()))  # noqa: S104 - a mode under test  # nosec B104
        try:
            host = mode[1]
            st, _b, _h = call(port, "GET", "/api/v1/goals", headers={"Authorization": "Bearer x"}, host=host)
            check(f"a server started {mode[0]} answers no /api/v1/ call", st == 404, st)
        finally:
            srv.terminate()
            srv.wait(timeout=10)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
