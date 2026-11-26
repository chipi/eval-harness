#!/usr/bin/env python3
"""`evh mcp --http`: every field of `<path>/health`, with and without --no-agent-tools and --public (0.8.2).

    python tests/test_mcp_health.py

The answer is exactly {ok, version, tools, public}: ok is true, version the package's, public the flag, and tools the
number of tools the same server lists over MCP (counted by the SDK's own client, not by the code that fills the field).
Four servers: a local one, one without the agent tools, a public one, and a public one without them (a public server
has no agent tools: the flag changes nothing there).
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore, _tmp
import _runstore  # noqa: E402
import _tmp  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, store_under_test, summary  # noqa: E402
from evaluation_harness._version import __version__  # noqa: E402
from evaluation_harness.mcp_server import AGENT_TOOLS  # noqa: E402

try:
    import anyio
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client
except ImportError as exc:
    print(f"  FAIL test_mcp_health: {exc}: mcp is a dependency of the package")
    sys.exit(1)

tmp = Path(_tmp.mkdtemp(prefix="evh-mcp-health-"))
(tmp / "data" / "datasets").mkdir(parents=True)
_runstore.write_text(tmp, _format.NAME, f"format: {_format.FORMAT}\n")
os.environ.setdefault("EVAL_STORE", store_under_test())
env = dict(os.environ, EVAL_HOME=str(tmp))
env.pop("EVAL_DATA_DIR", None)

CASES: tuple[tuple[str, list[str], bool], ...] = (
    ("local", [], False),
    ("--no-agent-tools", ["--no-agent-tools"], False),
    ("--public", ["--public"], True),
    ("--public --no-agent-tools", ["--public", "--no-agent-tools"], True),
)


async def listed(base: str) -> list[str]:
    async with streamable_http_client(base + "/mcp") as streams, ClientSession(streams[0], streams[1]) as s:
        await s.initialize()
        return [t.name for t in (await s.list_tools()).tools]


counts = {}
for label, flags, public in CASES:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    srv = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "mcp", "--http", "--port", str(port), *flags],
        cwd=tmp,
        env=env,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        start_new_session=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        body, ctype, status = "", "", 0
        for _ in range(100):
            try:
                with urllib.request.urlopen(base + "/mcp/health", timeout=5) as r:  # noqa: S310  # nosec B310 -- the test's own server on 127.0.0.1
                    body, ctype, status = r.read().decode(), r.headers.get("Content-Type", ""), r.status
                break
            except OSError:
                time.sleep(0.2)
        names = anyio.run(listed, base)
        counts[label] = len(names)
        try:
            health = json.loads(body)
        except ValueError:
            health = {}
        check(
            f"health ({label}): 200 and JSON",
            status == 200 and ctype.startswith("application/json"),
            (status, ctype),
        )
        check(
            f"health ({label}): exactly ok, version, tools, public, with their values",
            health == {"ok": True, "version": __version__, "tools": len(names), "public": public},
            body,
        )
        check(
            f"health ({label}): the tools it counts are the ones listed (agent tools {'absent' if public or flags else 'present'})",
            (set(AGENT_TOOLS) <= set(names)) == (not public and "--no-agent-tools" not in flags),
            sorted(set(AGENT_TOOLS) & set(names)),
        )
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
            srv.wait()

check(
    "the four servers' counts differ as the flags say",
    counts["local"] == counts["--no-agent-tools"] + len(AGENT_TOOLS)
    and counts["--public"] == counts["--public --no-agent-tools"]
    and counts["--public"] < counts["--no-agent-tools"],
    counts,
)
sys.exit(summary("test_mcp_health"))
