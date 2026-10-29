#!/usr/bin/env python3
"""Assertions for `evh mcp` (RFC-018), through the official SDK's own stdio client.

    python tests/test_mcp_server.py

In a throwaway project built from the tutorial ($0, offline): the server lists exactly the read
commands, each annotated read-only, none taking --adapter or --json; a tool answers what the
command prints, with its JSON as structured content; an unknown argument is refused before
anything runs; a command's refusal comes back as an error with its message; and every evh command
is either a tool or listed, with a reason, as not one.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
KIT = HERE.parent / "tutorial"
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.cli import COMMANDS  # noqa: E402
from evaluation_harness.mcp_server import NOT_TOOLS, READ_TOOLS  # noqa: E402

try:
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
except ImportError as exc:  # the package depends on mcp; a checkout's venv may predate it
    print(
        f"  FAIL test_mcp_server: {exc}: mcp is a dependency of the package (pip install -r requirements.txt)"
    )
    sys.exit(1)

proj = Path(tempfile.mkdtemp(prefix="evh-mcp-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-mcp")
env.pop("EVAL_DATA_DIR", None)
env.pop("EVAL_RUNS_DIR", None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


check(
    "every evh command is a tool or not one, with a reason; none is both",
    set(READ_TOOLS) | set(NOT_TOOLS) == set(COMMANDS) and not set(READ_TOOLS) & set(NOT_TOOLS),
    f"neither: {sorted(set(COMMANDS) - set(READ_TOOLS) - set(NOT_TOOLS))}; "
    f"unknown: {sorted((set(READ_TOOLS) | set(NOT_TOOLS)) - set(COMMANDS))}",
)

try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    (data / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset", r.returncode == 0, r.stderr[-300:])
    shutil.copytree(KIT / "gold", data / "references" / "gold" / "tickets_v1")
    shutil.copy(KIT / "goals" / "tickets_summary.yaml", data / "goals")
    cfg = (KIT / "configs" / "tickets_lead2.yaml").read_text()
    (data / "configs" / "lead2.yaml").write_text(cfg + "goal: tickets_summary\n")
    r = evh("experiment-run", "--config", str(data / "configs" / "lead2.yaml"))
    check("setup: one run", r.returncode == 0, r.stderr[-300:])

    async def session():
        params = StdioServerParameters(
            command=sys.executable, args=[str(HERE / "cli.py"), "mcp"], cwd=str(proj), env=env
        )
        async with stdio_client(params) as (rd, wr), ClientSession(rd, wr) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            by = {t.name: t for t in tools}
            check("tools: exactly the read commands", sorted(by) == sorted(READ_TOOLS), sorted(by))
            check(
                "tools: each read-only, not destructive",
                all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools),
            )
            check(
                "tools: no schema takes --adapter or --json",
                not any({"adapter", "json"} & set(t.input_schema.get("properties", {})) for t in tools),
            )
            check(
                "tools: the schema comes from the command's parser (datasets: dataset-id, period)",
                {"dataset-id", "period"} <= set(by["datasets"].input_schema["properties"]),
                by["datasets"].input_schema,
            )
            res = await s.call_tool("datasets", {})
            want = evh("datasets", "--json").stdout
            check(
                "datasets: the command's own answer, its JSON as structured content",
                not res.is_error
                and json.loads(res.content[0].text) == json.loads(want)
                and (res.structured_content or {}).get("command") == "datasets",
                res.content[0].text[:300],
            )
            rows = [r_ for b in res.structured_content["result"]["blocks"] for r_ in b.get("rows", [])]
            check(
                "datasets: its table's rows as data",
                any(r_.get("dataset") == "tickets_v1" for r_ in rows),
                rows,
            )
            res = await s.call_tool("datasets", {"dataset-id": "tickets_v1"})
            check(
                "datasets with an option: passed as the command line",
                not res.is_error and "tickets_v1" in res.content[0].text,
            )
            res = await s.call_tool("datasets", {"bogus": 1})
            check(
                "an unknown argument is refused before anything runs",
                res.is_error and "unknown argument" in res.content[0].text,
                res.content[0].text,
            )
            res = await s.call_tool("goals", {"goal": "no_such_goal"})
            check(
                "a command's refusal is an error, with its message and exit code",
                res.is_error and "no_such_goal" in res.content[0].text and "(exit 1)" in res.content[0].text,
                res.content[0].text[:300],
            )
            res = await s.call_tool("validate", {})
            check(
                "validate: runs, its text as the answer",
                "V1" in res.content[0].text,
                res.content[0].text[:200],
            )
            res = await s.call_tool("run-promote", {})
            check("a command that is not a tool is refused", res.is_error, res.content[0].text)
            # Values are data, never a way past the schema (an independent review's two holes).
            (proj / "outside.json").write_text('{"secret": "TOPSECRET"}')
            for bad in ["../outside", str(proj / "outside"), "..", "a/b"]:
                res = await s.call_tool("dataset-items", {"dataset-id": bad})
                check(
                    f"dataset-items: a path as the id is refused ({bad[:20]!r}), nothing outside data/ is read",
                    res.is_error
                    and "TOPSECRET" not in res.content[0].text
                    and "not a dataset id" in res.content[0].text,
                    res.content[0].text[:200],
                )
            for v in (["r1", "--item", "t01_login"], "--item"):
                res = await s.call_tool("inspect", {"runs": v})
                check(
                    f"inspect: an option smuggled in a value is refused ({v!r})",
                    res.is_error
                    and (
                        "may not start with '-'" in res.content[0].text or "not a list" in res.content[0].text
                    ),
                    res.content[0].text[:200],
                )
            res = await s.call_tool("datasets", {"dataset-id": ["tickets_v1", "x"]})
            check(
                "a list for an option that takes one value is refused",
                res.is_error and "one value, not a list" in res.content[0].text,
                res.content[0].text[:200],
            )
            flag = next(
                (
                    (t.name, k)
                    for t in tools
                    for k, v in t.input_schema["properties"].items()
                    if v.get("type") == "boolean"
                ),
                None,
            )
            if flag:
                res = await s.call_tool(flag[0], {flag[1]: "false"})
                check(
                    f"a flag given as the string 'false' is refused, not read as on ({flag[0]} {flag[1]})",
                    res.is_error and "true or false" in res.content[0].text,
                    res.content[0].text[:200],
                )
            res = await s.call_tool("datasets", {"dataset-id": "a\u0000b"})
            check(
                "a NUL byte in a value is refused before anything runs",
                res.is_error and "NUL" in res.content[0].text,
                res.content[0].text[:200],
            )
            res = await s.call_tool("datasets", {"dataset-id": "x" * 600})
            check(
                "an over-long value is refused before anything runs",
                res.is_error and "characters" in res.content[0].text,
                res.content[0].text[:200],
            )
            res = await s.call_tool("search", {"text": ["tickets_v1"]})
            check(
                "search: its text after '--', read as words, the answer found",
                not res.is_error and "tickets_v1" in res.content[0].text,
                res.content[0].text[:200],
            )

    anyio.run(session)
    from evaluation_harness.mcp_server import public_error

    tb = "Traceback (most recent call last):\n  File \"/srv/evals/releases/abc/pkg/x.py\", line 1\nKeyError: 'x'"
    check(
        "public: a crash is told as an internal error, no traceback or path",
        "internal error" in public_error(tb, proj) and "/srv" not in public_error(tb, proj),
    )
    msg = f"ERROR: no profile for d ({proj}/data/profiles/d.json): write one"
    check(
        "public: a refusal keeps its message, without the server's paths",
        public_error(msg, proj).startswith("ERROR: no profile for d")
        and str(proj) not in public_error(msg, proj),
        public_error(msg, proj),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
