#!/usr/bin/env python3
"""Assertions for `evh mcp --http` (RFC-018), through the official SDK's streamable HTTP client.

    python tests/test_mcp_http.py

A server on the loopback, --public, --rate 6, with a hooks file that records what it is told:
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
    print(
        f"  FAIL test_mcp_http: {exc}: mcp is a dependency of the package (pip install -r requirements.txt)"
    )
    sys.exit(1)

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
cmd = [sys.executable, str(HERE / "cli.py"), "mcp", "--http", "--port", str(port), "--public", "--rate", "6"]
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
            res = await s.call_tool("search", {"text": ["x", "--adapter", "os:getcwd"]})
            check(
                "a value that starts with '-' is refused (it would be read as an option the schema hides)",
                res.is_error and "may not start with '-'" in res.content[0].text,
                res.content[0].text,
            )
            res = await s.call_tool('a"} 1\nforged 0', {})
            check("an unknown tool is refused", res.is_error and "no tool" in res.content[0].text)
            results = [await s.call_tool("datasets", {"dataset-id": f"d{i}"}) for i in range(4)]
            check(
                "--rate 6: the three refused calls count; three datasets calls answer, the fourth is refused",
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
    check(
        "hooks: an unknown tool is told as 'unknown', never the client's string",
        any(c["tool"] == "unknown" for c in calls) and "forged" not in seen.read_text(),
        [c["tool"] for c in calls],
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
log = [ln for ln in (srv.stderr.read() if srv.stderr else "").splitlines() if ln.startswith("{")]
check(
    "the log line: a line per call, never the caller's address or user agent",
    len(log) >= 7 and not any('"client"' in ln or '"agent"' in ln or "127.0.0.1" in ln for ln in log),
    log[:3],
)

# --rate-total: everyone together, whoever they are.
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port2 = s.getsockname()[1]
cmd2 = [
    sys.executable,
    str(HERE / "cli.py"),
    "mcp",
    "--http",
    "--port",
    str(port2),
    "--public",
    "--rate-total",
    "2",
    "--request-rate",
    "14",
    "--max-body",
    "4096",
]
srv2 = subprocess.Popen(cmd2, cwd=tmp, env=env, stderr=subprocess.DEVNULL, text=True, start_new_session=True)
base = f"http://127.0.0.1:{port2}"
try:
    for _ in range(100):
        try:
            if get("/mcp/health")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(0.2)

    async def total():
        async with (
            streamable_http_client(base + "/mcp") as streams,
            ClientSession(streams[0], streams[1]) as s,
        ):
            await s.initialize()
            # Refusals first: they cost nothing and never count toward the total.
            for _ in range(3):
                await s.call_tool("no-such-tool", {})
            res = [await s.call_tool("datasets", {"period": p}) for p in ("all", "30d", "week")]
            check(
                "--rate-total 2: the third call in a minute is refused, from anyone",
                not res[0].is_error
                and not res[1].is_error
                and res[2].is_error
                and "as many calls" in res[2].content[0].text,
                [r.content[0].text[:60] for r in res],
            )
            again = await s.call_tool("datasets", {"period": "all"})
            check(
                "--public: a repeated call is answered from what was kept, and is not counted",
                not again.is_error and again.content[0].text == res[0].content[0].text,
                again.content[0].text[:80],
            )

    anyio.run(total)

    def post(body: bytes) -> int:
        req = urllib.request.Request(  # noqa: S310 -- the test's own server
            base + "/mcp",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310  # nosec B310
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    check(
        "GET on the endpoint is 405 (stateless: no stream to hold open)", get("/mcp")[0] == 405, get("/mcp")
    )
    big = b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"' + b"a" * 8000 + b'"}}'
    check("--max-body 4096: a larger body is refused (413) before it is read", post(big) == 413)
    ping = b'{"jsonrpc":"2.0","id":1,"method":"ping"}'
    codes = [post(ping) for _ in range(16)]
    check(
        "--request-rate 14: every request counts, ping too; past it, 429",
        429 in codes and codes[0] != 429,
        codes,
    )
finally:
    os.killpg(srv2.pid, 15)
    srv2.wait(timeout=10)

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
from types import SimpleNamespace  # noqa: E402

from evaluation_harness.mcp_server import Hooks, _client, caller_key, run_command  # noqa: E402

stopped, _out, err = run_command(tmp, "datasets", [], timeout=0.05)
check(
    "a call over its time is stopped: exit 124, saying so",
    stopped == 124 and "stopped after" in err,
    (stopped, err[-120:]),
)


class Raises:
    def request(self, info):
        raise RuntimeError("hook broke")


Hooks(Raises())("request", {})  # must not raise
check("a hook that raises never breaks the call it observes", True)
fake = SimpleNamespace(
    headers={"CF-Connecting-IP": "203.0.113.9", "user-agent": "x" * 500},
    client=SimpleNamespace(host="10.0.0.1"),
)
addr, ua = _client(SimpleNamespace(request=fake), "CF-Connecting-IP")
check(
    "--client-header names the caller; the address and user agent are capped",
    addr == "203.0.113.9" and len(ua) == 120,
    (addr, len(ua)),
)
check(
    "without the header, the connection's own address",
    _client(
        SimpleNamespace(request=SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.1"))),
        "CF-Connecting-IP",
    )[0]
    == "10.0.0.1",
)

check(
    "the rate counts an IPv6 caller by its /64, an IPv4 caller by its address",
    caller_key("2001:db8:1:2::7") == caller_key("2001:db8:1:2:ffff::1") != caller_key("2001:db8:1:3::7")
    and caller_key("203.0.113.7") == "203.0.113.7",
)
sys.exit(summary())
