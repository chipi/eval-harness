#!/usr/bin/env python3
"""Assertions for `evh mcp --http` (RFC-018), through the official SDK's streamable HTTP client.

    python tests/test_mcp_http.py

A server on the loopback, --public, --rate 3, with a hooks file that records what it is told:
its health answers; a request for another Host is refused (DNS rebinding); --public leaves out the
options that answer with text; the fourth call in a minute is refused; the hooks see each call
(tool, argument names, never values; the caller) and serve their own route beside the endpoint;
and a bind beyond the loopback without --allowed-host is refused before it starts.
"""

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

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

try:
    import anyio
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
except ImportError as exc:
    print(f"  --   test_mcp_http skipped: {exc} (pip install -r requirements.txt)")
    sys.exit(0)

tmp = Path(tempfile.mkdtemp(prefix="evh-mcp-http-"))
(tmp / "data" / "datasets").mkdir(parents=True)
seen = tmp / "seen.jsonl"
(tmp / "hooks.py").write_text(
    f"""
import json
def _w(kind, info):
    with open({str(seen)!r}, "a") as fh:
        fh.write(json.dumps({{"kind": kind, **{{k: v for k, v in info.items() if k != "version"}}}}) + "\\n")
def start(info): _w("start", info)
def request(info): _w("request", info)
def error(exc, info): _w("error", info)
routes = {{"/metrics": lambda q: (200, "text/plain", b"evals_mcp_calls_total 1\\n")}}
"""
)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
env = dict(os.environ, EVAL_HOME=str(tmp))
env.pop("EVAL_DATA_DIR", None)
cmd = [sys.executable, str(HERE / "cli.py"), "mcp", "--http", "--port", str(port), "--public", "--rate", "3"]
cmd += ["--allowed-host", "evals.example.test", "--hooks", str(tmp / "hooks.py")]
srv = subprocess.Popen(cmd, cwd=tmp, env=env, stderr=subprocess.PIPE, text=True, start_new_session=True)
base = f"http://127.0.0.1:{port}"


def get(path: str, host: str | None = None) -> tuple[int, str]:
    req = urllib.request.Request(base + path, headers={"Host": host} if host else {})  # noqa: S310 -- the test's own server on 127.0.0.1
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310  # nosec B310
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


try:
    for _ in range(100):
        try:
            if get("/mcp/health")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(0.2)
    code, body = get("/mcp/health")
    check(
        "health: answers, saying it is public", code == 200 and json.loads(body).get("public") is True, body
    )
    req = urllib.request.Request(  # noqa: S310 -- the test's own server
        base + "/mcp", data=b"{}", headers={"Host": "evil.example", "Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=10)  # noqa: S310  # nosec B310
        code = 200
    except urllib.error.HTTPError as e:
        code = e.code
    check("another Host is refused (DNS rebinding)", code == 421, code)
    code, body = get("/metrics")
    check(
        "a hooks route is served beside the endpoint", code == 200 and "evals_mcp_calls_total" in body, body
    )

    async def session():
        async with (
            streamable_http_client(base + "/mcp") as streams,
            ClientSession(streams[0], streams[1]) as s,
        ):
            await s.initialize()
            tools = {t.name: t for t in (await s.list_tools()).tools}
            check(
                "--public: no option answers with an item's text",
                "item" not in tools["inspect"].input_schema["properties"]
                and "item" not in tools["dataset-items"].input_schema["properties"],
            )
            check(
                "--public: validate is not offered (a public copy is not a whole project)",
                "validate" not in tools,
            )
            res = await s.call_tool("rounds", {})
            check(
                "a missing required argument is refused before anything runs",
                res.is_error and "missing argument(s): goal" in res.content[0].text,
                res.content[0].text,
            )
            results = [await s.call_tool("datasets", {"dataset-id": f"d{i}"}) for i in range(4)]
            check(
                "--rate 3: three calls answer, the fourth in the minute is refused",
                "a minute" in results[3].content[0].text
                and results[3].is_error
                and not any("a minute" in r.content[0].text for r in results[:3]),
                [r.content[0].text[:80] for r in results],
            )

    anyio.run(session)
    lines = [json.loads(ln) for ln in seen.read_text().splitlines()] if seen.is_file() else []
    starts = [x for x in lines if x["kind"] == "start"]
    calls = [x for x in lines if x["kind"] == "request"]
    check(
        "hooks: start, with the tools and the transport",
        starts and starts[0].get("transport") == "http",
        starts,
    )
    calls = [c for c in calls if c["tool"] == "datasets"]
    check(
        "hooks: each call, its tool and argument names, never their values",
        len(calls) == 4 and all(c["args"] == ["dataset-id"] for c in calls) and "d0" not in seen.read_text(),
        calls,
    )
    check("hooks: the caller's address", all(c.get("client") == "127.0.0.1" for c in calls), calls)
    check("hooks: the refused call says why", calls[-1].get("refused") == "rate", calls[-1])
finally:
    os.killpg(srv.pid, 15)
    srv.wait(timeout=10)

r = subprocess.run(
    [sys.executable, str(HERE / "cli.py"), "mcp", "--http", "--bind", "0.0.0.0"],  # noqa: S104  # nosec B104 -- refused, never bound
    cwd=tmp,
    env=env,
    capture_output=True,
    text=True,
    timeout=60,
)
check(
    "a bind beyond the loopback needs --allowed-host",
    r.returncode != 0 and "--allowed-host" in r.stderr,
    r.stderr[-200:],
)
sys.exit(summary())
