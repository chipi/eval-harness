#!/usr/bin/env python3
"""A cancelled `evh mcp` call gives its slot back (RFC-016, RFC-032 step 9).

    python tests/test_mcp_cancel.py

The SDK's stdio client calls a tool and gives up on it after a second, which sends notifications/cancelled. The operation is
made slow by a sitecustomize on the server's PYTHONPATH (it makes `licences` sleep), so the test needs no slow data. A call
answered in the server's own process cannot be stopped, so what is kept is that it stops being waited for: the server, with
one slot (--concurrent 1), answers the next call at once, and a call over --timeout is told as stopped waiting.
"""

import os
import shutil
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
started = tmp / "slow.started"
(site / "sitecustomize.py").write_text(
    "import os, sys, time\n"
    "if os.environ.get('EVH_TEST_SLOW') and sys.argv[1:2] != ['--help']:\n"
    "    from evaluation_harness.ops import records\n"
    "    real = records.licences\n"
    "    def slow(*a, **k):\n"
    "        open(os.environ['EVH_TEST_SLOW'], 'w').write(str(os.getpid()))\n"
    "        time.sleep(20)\n"
    "        return real(*a, **k)\n"
    "    records.licences = slow\n"
)
env = dict(
    os.environ,
    EVAL_HOME=str(tmp),
    PYTHONPATH=os.pathsep.join([str(site), *filter(None, [os.environ.get("PYTHONPATH")])]),
    EVH_TEST_SLOW=str(started),
)
env.pop("EVAL_DATA_DIR", None)


async def session(extra: list[str], timeout_check: bool):
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(HERE / "cli.py"), "mcp", "--concurrent", "1", *extra],
        cwd=str(tmp),
        env=env,
    )
    async with stdio_client(params) as (rd, wr), ClientSession(rd, wr) as s:
        await s.initialize()
        if timeout_check:
            res = await s.call_tool("licences", {})
            said = getattr(res.content[0], "text", "")
            check(
                "a call over --timeout is told as stopped waiting, an error",
                res.is_error and "stopped waiting after" in said,
                said[:200],
            )
            return
        with anyio.move_on_after(1) as waited:
            await s.call_tool("licences", {})
        check("the slow call started and was given up on", waited.cancelled_caught and started.is_file())
        t0 = time.monotonic()
        res = await s.call_tool("looks", {})
        check(
            "a cancelled call gives its slot back: the next call answers at once, not when the slow one ends",
            not res.is_error and time.monotonic() - t0 < 5,
            (res.is_error, time.monotonic() - t0),
        )


try:
    anyio.run(session, [], False)
    started.unlink(missing_ok=True)
    anyio.run(session, ["--timeout", "1"], True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
sys.exit(summary())
