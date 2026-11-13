#!/usr/bin/env python3
"""The API's registry and its read side (RFC-026 step 2).

    python tests/test_api.py

The registry on its own: every command is served or named as not served; every path-typed argument of a served
command has a kind; the options that load code or reach outside the project are never taken. Then a real `evh
catalog-serve` in a throwaway tutorial project ($0, offline): no token, a wrong one, another Host and a foreign Origin
are refused; the token works as a bearer and as the cookie the session route sets; the registry lists reads and jobs;
a read answers exactly what the command answers with --json (parity); a job asked as a read, an argument the
registry does not take, and a config id that does not exist are refused before anything runs; a server started
--public or --behind-proxy answers no /api/v1/ call.
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
from evaluation_harness import _api  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.cli import COMMANDS  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

reg = _api.registry()
check(
    "every command is served or named as not served, with why",
    set(reg) | set(_api.NOT_SERVED) == set(COMMANDS) and not set(reg) & set(_api.NOT_SERVED),
    sorted(set(COMMANDS) - set(reg) - set(_api.NOT_SERVED)),
)
check(
    "every path-typed argument of a served command has a kind",
    _api.unkinded_paths() == [],
    _api.unkinded_paths(),
)
from evaluation_harness import mcp_server as _ms  # noqa: E402

no_json = sorted(
    c
    for c in reg
    if c not in _ms.JSON and not any("--json" in a.option_strings for a in _ms.parser_of(c)._actions)
)
check("every command the API serves answers --json (RFC-026 step 7)", not no_json, no_json)
names = {c: {a["name"] for a in v["arguments"]} for c, v in reg.items()}
check(
    "never taken: --adapter, --runs-dir, a sweep or rescore output folder, a source folder",
    "adapter" not in names["run"]
    and "runs-dir" not in names["pair-test"]
    and "out" not in names["rescore"]
    and "source-dir" not in names["dataset-create"]
    and "json" not in names["leaderboard"],
)
check(
    "kinds: run's config is a name, label-import's sheet an upload, label-sheet's out an artifact; spenders marked",
    {a["name"]: a["kind"] for a in reg["run"]["arguments"]}.get("config") == "name"
    and {a["name"]: a["kind"] for a in reg["label-import"]["arguments"]}.get("sheet") == "upload"
    and {a["name"]: a["kind"] for a in reg["label-sheet"]["arguments"]}.get("out") == "artifact"
    and reg["run"]["spends"]
    and not reg["datasets"]["spends"]
    and reg["leaderboard"]["served"] == "read"
    and reg["run"]["served"] == "job",
)

proj = Path(tempfile.mkdtemp(prefix="evh-api-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-api")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
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
    (proj / "data" / "configs").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tickets")
    r = evh("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tk_v1")
    r = (
        r
        if r.returncode
        else evh("label-import", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t")
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
            f"configs/{cid}.yaml",
            f"config_id: {cid}\ndataset_id: tk_v1\nparams:\n  provider: echo\n  sentences: {n}\n",
        )
        r = r if r.returncode else evh("run", "--config", f"data/configs/{cid}.yaml")
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
        st, _b, _h = call(port, "GET", "/api/v1/commands")
        st2, _b, _h = call(port, "GET", "/api/v1/commands", headers={"Authorization": "Bearer nope"})
        st3, _b, _h = call(port, "GET", "/api/v1/commands", headers=bearer, host="evil.example")
        st4, _b, _h = call(
            port, "GET", "/api/v1/commands", headers={**bearer, "Origin": "http://evil.example"}
        )
        check(
            "refused: no token (401), a wrong one (401), another Host (403), a foreign Origin (403)",
            (st, st2, st3, st4) == (401, 401, 403, 403),
            (st, st2, st3, st4),
        )
        st, body, _h = call(port, "GET", "/api/v1/commands", headers=bearer)
        cmds = json.loads(body).get("commands", {}) if st == 200 else {}
        check(
            "GET /api/v1/commands: the registry, reads and jobs",
            cmds.get("leaderboard", {}).get("served") == "read"
            and cmds.get("run", {}).get("served") == "job",
            (st, body[:200]),
        )
        st, _b, hd = call(port, "GET", f"/api/v1/session?token={token}")
        cookie = (hd.get("Set-Cookie") or "").split(";")[0]
        st2, _b, _h = call(port, "GET", "/api/v1/commands", headers={"Cookie": cookie})
        check(
            "the session route trades the token for an HttpOnly, SameSite=Strict cookie, which then works",
            st == 204
            and "HttpOnly" in (hd.get("Set-Cookie") or "")
            and "SameSite=Strict" in (hd.get("Set-Cookie") or "")
            and st2 == 200,
            (st, hd.get("Set-Cookie"), st2),
        )
        parity = {}
        for c, a in (
            ("datasets", {}),
            ("arms", {}),
            ("leaderboard", {"dataset-id": "tk_v1"}),
            ("pair-test", {"dataset-id": "tk_v1", "a": "two_v1", "b": "one_v1"}),
        ):
            st, body, _h = call(port, "POST", f"/api/v1/read/{c}", {"args": a}, bearer)
            argv = [x for k, v in a.items() for x in (f"--{k}", v)]
            cli = evh(c, *argv, "--json")
            parity[c] = (st, cli.returncode) == (200, 0) and json.loads(body) == json.loads(cli.stdout)
        check(
            "parity: a read through the API answers exactly the command's --json",
            all(parity.values()),
            parity,
        )
        st, body, _h = call(port, "POST", "/api/v1/read/validate", {"args": {}}, bearer)
        check(
            "validate through the API: its envelope, with whether it passed",
            st == 200 and json.loads(body).get("result", {}).get("values", {}).get("passed") is True,
            body[:300],
        )
        refusals = {
            "a job asked as a read": call(
                port, "POST", "/api/v1/read/run", {"args": {"config": "one_v1"}}, bearer
            )[0],
            "an argument it does not take": call(
                port,
                "POST",
                "/api/v1/read/pair-test",
                {"args": {"dataset-id": "tk_v1", "runs-dir": "/etc"}},
                bearer,
            )[0],
            "a value starting with -": call(
                port, "POST", "/api/v1/read/leaderboard", {"args": {"dataset-id": "--adapter=x"}}, bearer
            )[0],
            "not a command": call(port, "POST", "/api/v1/read/nope", {"args": {}}, bearer)[0],
        }
        check(
            "refused before anything runs: a job as a read, an argument it does not take, a value like an option, no such command",
            refusals
            == {
                "a job asked as a read": 404,
                "an argument it does not take": 400,
                "a value starting with -": 400,
                "not a command": 404,
            },
            refusals,
        )
        try:
            _api.checked_args("run", {"config": "nope_v1"})
            ok = False
        except _api.Refused as exc:
            ok = exc.status == 404 and "no arm config" in str(exc)
        check("a name that does not exist (a config id) is refused", ok)

        def refused(command: str, args: dict) -> bool:
            try:
                _api.checked_args(command, args)
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
        kinds = {a["name"]: a["kind"] for a in _api.registry()["data-put"]["arguments"]}
        check(
            "data-put's file is an upload, never a path on the server",
            kinds.get("file") == _api.UPLOAD,
            kinds,
        )
        check(
            "a name is still taken (capture --importer jsonl, dataset-create --source folder)",
            not refused("capture", {"importer": "jsonl", "query": "{}", "capture": "c1"})
            and not refused("dataset-create", {"source": "folder", "dataset-id": "d1"}),
        )
        check(
            "every served argument whose help offers path.py:Class or @file has a rule",
            _api.unruled_values() == [],
            _api.unruled_values(),
        )
    finally:
        srv.terminate()
        srv.wait(timeout=10)

    for mode in (("--public", "a.example"), ("--behind-proxy", "evals.example")):
        srv, port = serve(*mode, *(("--bind", "0.0.0.0") if mode[0] == "--behind-proxy" else ()))  # noqa: S104 - a mode under test  # nosec B104
        try:
            host = mode[1]
            st, _b, _h = call(
                port, "GET", "/api/v1/commands", headers={"Authorization": "Bearer x"}, host=host
            )
            check(f"a server started {mode[0]} answers no /api/v1/ call", st == 404, st)
        finally:
            srv.terminate()
            srv.wait(timeout=10)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
