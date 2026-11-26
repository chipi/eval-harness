#!/usr/bin/env python3
"""`evh mcp --no-agent-tools` and what the help and the docs say about the tools that write (0.8.2).

    python tests/test_mcp_no_agent_tools.py

A local server also offers the agent sampler's two tools (`AGENT_TOOLS`: they write, one runs a trial). The help names
them, derived from the code, and so do the places that say what an MCP tool does; the counts the guide gives are the
code's. `--no-agent-tools` serves everything a local server reads (text and outputs too) and none of them, on stdio and on
HTTP: no tool that is not read-only, and a call to one is refused as unknown.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore, _tmp, _cli
import _cli  # noqa: E402
import _runstore  # noqa: E402
import _tmp  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness import ops as _ops  # noqa: E402
from evaluation_harness._check import check, store_under_test, summary  # noqa: E402
from evaluation_harness.mcp_server import AGENT_TOOLS, tools_for  # noqa: E402

try:
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.client.streamable_http import streamable_http_client
except ImportError as exc:
    print(f"  FAIL test_mcp_no_agent_tools: {exc}: mcp is a dependency of the package")
    sys.exit(1)

tmp = Path(_tmp.mkdtemp(prefix="evh-mcp-noagent-"))
(tmp / "data" / "datasets").mkdir(parents=True)
_runstore.write_text(tmp, _format.NAME, f"format: {_format.FORMAT}\n")
os.environ.setdefault("EVAL_STORE", store_under_test())
env = dict(os.environ, EVAL_HOME=str(tmp))
env.pop("EVAL_DATA_DIR", None)

# The help, the command list and every place that says what an MCP tool does name the tools that write.
helped = _cli.run(tmp, env, "mcp", "--help").stdout
check("`evh mcp --help` documents --no-agent-tools", "--no-agent-tools" in helped, helped[:300])
flat = " ".join(helped.split())
check("`evh mcp --help` names every agent tool", all(t in flat for t in AGENT_TOOLS), flat[:400])
check(
    "`evh mcp --help` no longer says no tool writes",
    "No tool writes" not in flat and "none writes" not in flat,
    flat[:400],
)
from evaluation_harness.cli import COMMANDS  # noqa: E402

listing = " ".join(COMMANDS["mcp"][1].split())
check(
    "the command list names the agent tools and does not say none writes",
    all(t in listing for t in AGENT_TOOLS) and "none writes" not in listing,
    listing,
)
PLACES = {
    "harness/docs/INTEGRATION.md": None,
    "docs/tutorials/5-catalog-and-inspector.md": None,
    "docs/prd/PRD-004-catalog-and-inspector.md": None,
    "site/build.py": None,
}
for rel in PLACES:
    text = " ".join((ROOT / rel).read_text(encoding="utf-8").split())
    check(f"{rel} says which tools write", all(t in text for t in AGENT_TOOLS), rel)
guide = " ".join((ROOT / "harness/docs/INTEGRATION.md").read_text(encoding="utf-8").split())
local, public = len(tools_for(False)), len(tools_for(True))
check(
    "the guide's counts are the code's",
    f"{local} on your machine, {public} on a public server" in guide,
    f"{local}/{public}",
)
check("the guide documents --no-agent-tools", "--no-agent-tools" in guide)
upgrade = (ROOT / "harness/docs/UPGRADING.md").read_text(encoding="utf-8")
check("UPGRADING 0.8.2 names the flag", "--no-agent-tools" in upgrade.split("## From 0.8.0 to 0.8.1")[0])

READ = {op.name for op in _ops.of_kind("read")}
TEXT = {op.name for op in _ops.of_kind("read") if op.public_dropped}


async def check_session(label: str, streams) -> None:
    async with ClientSession(streams[0], streams[1]) as s:
        await s.initialize()
        tools = {t.name: t for t in (await s.list_tools()).tools}
        writers = sorted(n for n, t in tools.items() if not (t.annotations and t.annotations.read_only_hint))
        check(f"{label}: no tool that writes or runs", not writers, writers)
        check(
            f"{label}: no agent tool",
            not set(AGENT_TOOLS) & set(tools),
            sorted(set(AGENT_TOOLS) & set(tools)),
        )
        check(
            f"{label}: every read of a local server, the text-reading ones too",
            set(tools) == READ and TEXT and set(tools) >= TEXT,
            sorted(READ ^ set(tools)),
        )
        for name in AGENT_TOOLS:
            res = await s.call_tool(name, {})
            text = " ".join(getattr(c, "text", "") for c in res.content)
            check(
                f"{label}: a call to {name} is refused as unknown",
                res.is_error and "no tool" in text,
                text[:120],
            )


async def stdio() -> None:
    params = StdioServerParameters(
        command=sys.executable, args=[str(HERE / "cli.py"), "mcp", "--no-agent-tools"], cwd=str(tmp), env=env
    )
    async with stdio_client(params) as (rd, wr):
        await check_session("stdio", (rd, wr))


anyio.run(stdio)

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
srv = subprocess.Popen(
    [sys.executable, str(HERE / "cli.py"), "mcp", "--http", "--port", str(port), "--no-agent-tools"],
    cwd=tmp,
    env=env,
    stderr=subprocess.PIPE,
    text=True,
    start_new_session=True,
)
base = f"http://127.0.0.1:{port}"
try:
    health = ""
    for _ in range(100):
        try:
            with urllib.request.urlopen(base + "/mcp/health", timeout=5) as r:  # noqa: S310  # nosec B310 -- the test's own server on 127.0.0.1
                health = r.read().decode()
            break
        except OSError:
            time.sleep(0.2)
    check(
        "http health: the tool count is the read operations",
        f'"tools":{len(READ)}' in health.replace(" ", ""),
        health,
    )

    async def http() -> None:
        async with streamable_http_client(base + "/mcp") as streams:
            await check_session("http", streams)

    anyio.run(http)
finally:
    srv.terminate()
    try:
        srv.wait(timeout=10)
    except subprocess.TimeoutExpired:
        srv.kill()
        srv.wait()
sys.exit(summary("test_mcp_no_agent_tools"))
