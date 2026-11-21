#!/usr/bin/env python3
"""A cancelled `evh mcp` call stops being waited for, and its work keeps its slot until it ends (RFC-016, RFC-032 step 9).

    python tests/test_mcp_cancel.py

The SDK's stdio client calls a tool and gives up on it after a second, which sends notifications/cancelled. The operation is
made slow by a sitecustomize on the server's PYTHONPATH (it makes `licences` sleep SLOW seconds), so the test needs no slow
data. A call answered in the server's own process cannot be stopped: it stops being waited for, and what it began runs to
its end holding its slot, so no more work runs than --concurrent allows. With one slot the next call waits for that work;
with two it is answered at once; a call over --timeout is told as stopped waiting.
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
SLOW = 8
patched = tmp / "slow.started.patched"
# The package is put on the path here, as cli.py puts it: sitecustomize runs before cli.py, and CI installs no package
# (only requirements.txt), so the import failed there, site.py swallowed it, and nothing was slow.
(site / "sitecustomize.py").write_text(
    f"import os, sys, time\nSLOW = {SLOW}\n"
    "if os.environ.get('EVH_TEST_SLOW') and sys.argv[1:2] != ['--help']:\n"
    f"    sys.path.insert(0, {str(HERE.parent)!r})\n"
    "    from evaluation_harness.ops import records\n"
    "    real = records.licences\n"
    "    def slow(*a, **k):\n"
    "        open(os.environ['EVH_TEST_SLOW'], 'w').write(str(os.getpid()))\n"
    "        time.sleep(SLOW)\n"
    "        return real(*a, **k)\n"
    "    records.licences = slow\n"
    "    open(os.environ['EVH_TEST_SLOW'] + '.patched', 'w').close()\n"
)
env = dict(
    os.environ,
    EVAL_HOME=str(tmp),
    PYTHONPATH=os.pathsep.join([str(site), *filter(None, [os.environ.get("PYTHONPATH")])]),
    EVH_TEST_SLOW=str(started),
)
env.pop("EVAL_DATA_DIR", None)


async def session(concurrent: int, extra: list[str], mode: str):
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(HERE / "cli.py"), "mcp", "--concurrent", str(concurrent), *extra],
        cwd=str(tmp),
        env=env,
    )
    async with stdio_client(params) as (rd, wr), ClientSession(rd, wr) as s:
        await s.initialize()
        check("the server's licences is the slow one (the sitecustomize applied)", patched.is_file())
        if mode == "timeout":
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
        check(
            f"the slow call started and was given up on (--concurrent {concurrent})",
            waited.cancelled_caught and started.is_file(),
        )
        t0 = time.monotonic()
        res = await s.call_tool("looks", {})
        took = time.monotonic() - t0
        if mode == "one slot":
            check(
                "with one slot, the next call waits for the given-up call's work to end: it held its slot",
                not res.is_error and SLOW - 4 < took < SLOW + 10,
                (res.is_error, took),
            )
        else:
            check(
                "with a slot free, the next call answers at once, beside the given-up call's work",
                not res.is_error and took < 3,
                (res.is_error, took),
            )


def fresh() -> None:
    started.unlink(missing_ok=True)
    patched.unlink(missing_ok=True)


try:
    anyio.run(session, 1, [], "one slot")
    fresh()
    anyio.run(session, 2, [], "two slots")
    fresh()
    anyio.run(session, 1, ["--timeout", "1"], "timeout")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
sys.exit(summary())
