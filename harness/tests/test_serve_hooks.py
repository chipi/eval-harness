#!/usr/bin/env python3
"""catalog-serve --hooks: a deployment's hooks are called, never break a request, and are off by
default.

    python tests/test_serve_hooks.py

A real server in public mode on a free port, with a hooks file that records every call: start
once, a request per request with its route and status, error when a route raises (answered 500),
a hook route answered before the host check; a hook that raises breaks nothing; without --hooks
the hook route does not exist.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
from evaluation_harness._check import check, summary

SERVE = Path(__file__).resolve().parents[1] / "scripts" / "catalog_serve.py"

HOOKS = """
import json, os
LOG = os.environ["HOOKS_LOG"]


def _w(kind, **kw):
    with open(LOG, "a") as f:
        f.write(json.dumps({"kind": kind, **kw}) + "\\n")


def start(info):
    _w("start", info=info)


def request(info):
    _w("request", info=info)
    if info["path"] == "/api/health" and os.environ.get("HOOKS_RAISE"):
        raise RuntimeError("a hook that fails")


def error(exc, info):
    _w("error", exc=type(exc).__name__, info=info)


def _ping(query):
    return 200, "text/plain", b"pong " + query.encode()


def _boom(query):
    raise ValueError("a route that fails")


routes = {"/x/ping": _ping, "/x/boom": _boom}
"""


def port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(tmp: Path, hooks: bool, **env) -> tuple:
    p = port()
    cmd = [sys.executable, str(SERVE), "--public", "localhost", "--port", str(p)]
    if hooks:
        cmd += ["--hooks", str(tmp / "hooks.py")]
    proc = subprocess.Popen(
        cmd,
        env={**os.environ, "HOOKS_LOG": str(tmp / "log.jsonl"), **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for _ in range(100):
        try:
            get(p, "/api/health")
            break
        except OSError:
            time.sleep(0.1)
    return proc, p


def get(p: int, path: str, host: str = "localhost") -> tuple:
    req = urllib.request.Request(f"http://127.0.0.1:{p}{path}", headers={"Host": host})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 — http to 127.0.0.1 only  # nosec B310
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def stop(proc) -> str:
    proc.terminate()
    out, _ = proc.communicate(timeout=10)
    return out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="evh-hooks-"))
    (tmp / "hooks.py").write_text(HOOKS)
    log = tmp / "log.jsonl"

    proc, p = serve(tmp, hooks=True)
    health = get(p, "/api/health")
    ping = get(p, "/x/ping?a=1", host="10.0.0.9:8080")  # not a served Host: a hook route still answers
    boom = get(p, "/x/boom")
    other = get(p, "/x/ping", host="evil.example")
    stop(proc)
    calls = [json.loads(x) for x in log.read_text().splitlines()]
    starts = [c for c in calls if c["kind"] == "start"]
    reqs = [c["info"] for c in calls if c["kind"] == "request"]
    errs = [c for c in calls if c["kind"] == "error"]
    check(
        "start: called once, before serving, with the version",
        len(starts) == 1 and starts[0]["info"]["public"] is True and starts[0]["info"]["version"],
        str(starts),
    )
    check(
        "a hook route is answered, before the host check",
        ping == (200, b"pong a=1") and other[0] == 200,
        f"{ping} {other}",
    )
    check(
        "a route that raises: error is called with the exception, the request answered 500",
        boom[0] == 500
        and len(errs) == 1
        and errs[0]["exc"] == "ValueError"
        and errs[0]["info"]["route"] == "/x/boom",
        f"{boom} {errs}",
    )
    check(
        "request: every request, with its route, status and time",
        {(r["route"], r["status"]) for r in reqs}
        >= {("/api/health", 200), ("/x/ping", 200), ("/x/boom", 500)}
        and all(r["ms"] >= 0 and r["method"] == "GET" for r in reqs),
        str(reqs[-4:]),
    )
    check("health still answers with hooks", health[0] == 200)

    log.unlink()
    proc, p = serve(tmp, hooks=True, HOOKS_RAISE="1")
    first, second = get(p, "/api/health"), get(p, "/api/health")
    out = stop(proc)
    check(
        "a hook that raises breaks nothing: the request is answered, the failure printed",
        first[0] == 200 and second[0] == 200 and "hooks.request failed: RuntimeError" in out,
        out[-300:],
    )

    proc, p = serve(tmp, hooks=False)
    none = get(p, "/x/ping")
    health = get(p, "/api/health")
    stop(proc)
    check(
        "without --hooks: no hook route, the server as before",
        none[0] in (403, 404) and health[0] == 200,
        f"{none} {health}",
    )
    return summary()


if __name__ == "__main__":
    sys.exit(main())
