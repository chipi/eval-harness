#!/usr/bin/env python3
"""A cancelled `evh mcp` call stops the command it started (RFC-016).

    python tests/test_mcp_cancel.py

The SDK's stdio client calls a tool and gives up on it after a second, which sends
notifications/cancelled. The command is made slow by a sitecustomize on the children's
PYTHONPATH (it sleeps when argv names the slow command and records its pid), so the test needs
no slow data. Before the fix the server waited on the command's thread: the process ran to its
timeout and kept a slot.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

try:
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
except ImportError as exc:  # the package depends on mcp; a checkout's venv may predate it
    print(
        f"  FAIL test_mcp_cancel: {exc}: mcp is a dependency of the package (pip install -r requirements.txt)"
    )
    sys.exit(1)

tmp = Path(tempfile.mkdtemp(prefix="evh-mcp-cancel-"))
(tmp / "data").mkdir()
site = tmp / "site"
site.mkdir()
pid_file = tmp / "slow.pid"
(site / "sitecustomize.py").write_text(
    "import os, sys, time\n"
    "if sys.argv[1:2] == ['datasets'] and os.environ.get('EVH_TEST_SLOW_PID'):\n"
    "    open(os.environ['EVH_TEST_SLOW_PID'], 'w').write(str(os.getpid()))\n"
    "    time.sleep(120)\n"
)
env = dict(
    os.environ,
    EVAL_HOME=str(tmp),
    PYTHONPATH=os.pathsep.join([str(site), *filter(None, [os.environ.get("PYTHONPATH")])]),
    EVH_TEST_SLOW_PID=str(pid_file),
)
env.pop("EVAL_DATA_DIR", None)
env.pop("EVAL_RUNS_DIR", None)


slow: list[int] = []


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def session():
    params = StdioServerParameters(
        command=sys.executable, args=[str(HERE / "cli.py"), "mcp"], cwd=str(tmp), env=env
    )
    async with stdio_client(params) as (rd, wr), ClientSession(rd, wr) as s:
        await s.initialize()
        with anyio.move_on_after(20) as waited:
            while not pid_file.is_file():
                with anyio.move_on_after(1):
                    await s.call_tool("datasets", {})
                if not pid_file.is_file():
                    await anyio.sleep(0.2)
        check("the slow command started", not waited.cancelled_caught and pid_file.is_file())
        if not pid_file.is_file():
            return
        pid = int(pid_file.read_text())
        slow.append(pid)
        deadline = time.monotonic() + 10
        while alive(pid) and time.monotonic() < deadline:
            await anyio.sleep(0.1)
        check("a cancelled call stops its command within seconds, not at its timeout", not alive(pid), pid)
        # The slot came back: a fresh call answers (validate: the sleeper is only for datasets).
        pid_file.unlink()
        res = await s.call_tool("validate", {})
        check("the server answers the next call", res is not None)


try:
    anyio.run(session)
finally:
    for pid in slow:  # a failing run must not leave the sleeper behind
        if alive(pid):
            os.kill(pid, 9)
sys.exit(summary())
