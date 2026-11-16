#!/usr/bin/env python3
"""A read tool is answered in the server's own process, never by a command it starts (RFC-032 step 9).

    python tests/test_mcp_in_process.py

The SDK's stdio client starts `evh mcp`; a sitecustomize on the server's PYTHONPATH writes a line for every interpreter that
starts under it, the server's and any child's. After calls of reads of every kind (an operation that answers in words, one
that answers in blocks, one that refuses, the registry's listings) the log holds the server's line alone, the answers are
the operations' structured results, and the tool names are the operations' (`goal-list`, not `goals`).
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

try:
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
except ImportError as exc:  # the package depends on mcp; a checkout's venv may predate it
    print(
        f"  FAIL test_mcp_in_process: {exc}: mcp is a dependency of the package (pip install -r requirements.txt)"
    )
    sys.exit(1)

tmp = Path(tempfile.mkdtemp(prefix="evh-mcp-inproc-"))
(tmp / "data").mkdir()
_runstore.write_text(tmp, _format.NAME, f"format: {_format.FORMAT}\n")
site = tmp / "site"
site.mkdir()
starts = tmp / "starts.log"
(site / "sitecustomize.py").write_text(
    "import os, sys\n"
    "with open(os.environ['EVH_TEST_STARTS'], 'a') as f:\n"
    "    f.write(f'{os.getpid()} {os.getppid()} {\" \".join(sys.argv[:3])}\\n')\n"
)
env = dict(
    os.environ,
    EVAL_HOME=str(tmp),
    PYTHONPATH=os.pathsep.join([str(site), *filter(None, [os.environ.get("PYTHONPATH")])]),
    EVH_TEST_STARTS=str(starts),
)
env.pop("EVAL_DATA_DIR", None)

#: A read of each kind: words (`licences`), blocks (`runs-list`), a listing of the data's records (`goal-list`, `dataset-list`),
#: the same with an argument (`looks`), and one that refuses (a dataset that is not there).
CALLS: tuple[tuple[str, dict], ...] = (
    ("licences", {}),
    ("runs-list", {}),
    ("goal-list", {}),
    ("dataset-list", {}),
    ("looks", {}),
    ("leaderboard", {"dataset": "nothing_v1"}),
)


async def session():
    params = StdioServerParameters(
        command=sys.executable, args=[str(HERE / "cli.py"), "mcp", "--concurrent", "2"], cwd=str(tmp), env=env
    )
    async with stdio_client(params) as (rd, wr), ClientSession(rd, wr) as s:
        await s.initialize()
        tools = {t.name for t in (await s.list_tools()).tools}
        check(
            "the tools are named as the operations; the commands that were views are not tools",
            {"goal-list", "dataset-list", "leaderboard", "comparison-show"} <= tools
            and not {"goals", "datasets", "inspect", "labels", "rounds", "overview"} & tools,
            sorted(tools)[:12],
        )
        answers = {}
        for name, args in CALLS:
            res = await s.call_tool(name, args)
            answers[name] = res
        ok = all(
            not answers[n].is_error for n in ("licences", "runs-list", "goal-list", "dataset-list", "looks")
        )
        check(
            "reads answer, with the operation's structured result in the envelope",
            ok
            and answers["goal-list"].structured_content["command"] == "goal-list"
            and answers["goal-list"].structured_content["result"] == {"goals": []}
            and "licences" in answers["licences"].structured_content["result"]
            and answers["runs-list"].structured_content["result"]["runs"] == [],
            {n: (a.is_error, (a.content[0].text if a.content else "")[:100]) for n, a in answers.items()},
        )
        check(
            "a refusal is the operation's own, an error to the caller",
            answers["leaderboard"].is_error and "nothing_v1" in answers["leaderboard"].content[0].text,
            answers["leaderboard"].content[0].text[:200],
        )


try:
    anyio.run(session)
    lines = [ln for ln in starts.read_text().splitlines() if ln.strip()]
    check(
        "no process was started for a read: the server's interpreter is the only one that ran",
        len(lines) == 1 and "cli.py" in lines[0] and " mcp" in lines[0],
        lines,
    )
finally:
    shutil.rmtree(tmp, ignore_errors=True)
sys.exit(summary())
