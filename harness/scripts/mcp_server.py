#!/usr/bin/env python3
"""evh mcp: the project's read commands as MCP tools, for an agent (RFC-018).

    evh mcp                       # stdio, the project the working directory is in
    evh mcp --project path/to/project

An MCP client (Claude Code, Claude Desktop, any agent) starts this as a stdio server. Its tools are
the commands a person reads the project with: the catalog's views, the inspector in the terminal,
the rounds, the runs, validate. Each call runs the command as a child process (`evh <command> …`,
with `--json` where the command has it), so a tool answers exactly what the command prints. No tool
writes, spends or runs a model: those stay commands a person runs (0.5.0 adds them, with consent).

For Claude Code, in the project:  claude mcp add evh -- evh mcp
"""

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import contextlib
import json
import os
import runpy
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

#: The commands that are tools: they only read. Every other command is in NOT_TOOLS with the
#: reason (tests/test_mcp_server.py fails on a command in neither).
READ_TOOLS = (
    "overview",
    "datasets",
    "dataset-items",
    "arms",
    "goals",
    "references",
    "metrics",
    "activity",
    "search",
    "inspect",
    "rounds",
    "runs-list",
    "validate",
)
NOT_TOOLS = {
    "init": "writes a project",
    "env-check": "reads the environment and keys, not the project",
    "dataset-create": "writes",
    "dataset-materialize": "writes",
    "dataset-profile": "writes",
    "reference-create": "writes, and may call a model",
    "reference-manifest": "writes",
    "experiment-run": "runs a system and may spend",
    "sweep": "runs systems and may spend",
    "rescore": "writes runs",
    "judge": "calls models and spends",
    "judge-score": "calls models and spends",
    "silver-calibrate": "writes",
    "cost-report": "a report tool; not yet a tool",
    "leaderboard": "a report tool; not yet a tool",
    "pair-test": "a statistics command; not yet a tool",
    "family-test": "a statistics command; not yet a tool",
    "bootstrap-test": "a statistics command; not yet a tool",
    "holdout": "a statistics command; not yet a tool",
    "rank-stability": "a statistics command; not yet a tool",
    "import-run": "writes runs",
    "run-compare": "a statistics command; not yet a tool",
    "run-promote": "a decision: a person's",
    "round-open": "a decision: a person's",
    "round-retire": "a decision: a person's",
    "round-close": "a decision: a person's",
    "catalog": "writes the pages",
    "catalog-serve": "never returns",
    "self-test": "runs the test suite",
    "mcp": "this server",
}
#: The views that take --json (catalog_views via _jsonout; dataset-items its profile).
JSON = {"overview", "datasets", "arms", "goals", "references", "metrics", "activity", "search", "inspect"}
JSON |= {"dataset-items"}
#: Left out of every schema: the server uses the project's own adapter (an agent must not load an
#: arbitrary file), and sets --json itself.
HIDDEN = {"--adapter", "--json", "--help"}
TIMEOUT_S = 300
MAX_OUT = 1_000_000


class _Parser(Exception):
    def __init__(self, parser: argparse.ArgumentParser):
        self.parser = parser


def parser_of(command: str) -> argparse.ArgumentParser:
    """The command's argparse parser, read without running it: its script runs until it parses
    its arguments, and the parser is handed back there."""
    from evaluation_harness.cli import COMMANDS  # noqa: PLC0415

    script = HERE / COMMANDS[command][0]
    real = argparse.ArgumentParser.parse_args

    def grab(self, *_a, **_k):
        raise _Parser(self)

    argparse.ArgumentParser.parse_args = grab  # type: ignore[method-assign]
    argv = sys.argv
    sys.argv = [str(script)]
    try:
        # stdout is the protocol's channel: nothing the script prints may reach it.
        with contextlib.redirect_stdout(sys.stderr):
            runpy.run_path(str(script), run_name="__main__")
    except _Parser as got:
        return got.parser
    finally:
        argparse.ArgumentParser.parse_args = real  # type: ignore[method-assign]
        sys.argv = argv
    raise RuntimeError(f"{command}: its script never parsed arguments")


def _name(a: argparse.Action) -> str:
    longest = max(a.option_strings, key=len) if a.option_strings else a.dest
    return longest.lstrip("-")


def _actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    return [
        a
        for a in parser._actions
        if not isinstance(a, argparse._HelpAction) and not (set(a.option_strings) & HIDDEN)
    ]


def input_schema(parser: argparse.ArgumentParser) -> dict:
    """A JSON Schema for the parser's options: a property per option, named as on the command line."""
    props: dict[str, Any] = {}
    required = []
    for a in _actions(parser):
        if isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
            p: dict[str, Any] = {"type": "boolean"}
        else:
            t = {int: "integer", float: "number"}.get(a.type, "string")  # type: ignore[call-overload]
            p = {"type": t}
            if a.choices:
                p["enum"] = list(a.choices)
            if a.nargs in ("*", "+") or isinstance(a, argparse._AppendAction):
                p = {"type": "array", "items": p}
        if a.help and a.help != argparse.SUPPRESS:
            p["description"] = a.help % {"default": a.default} if "%(default)" in a.help else a.help
        props[_name(a)] = p
        if a.required or not a.option_strings:
            required.append(_name(a))
    schema: dict[str, Any] = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def argv_of(parser: argparse.ArgumentParser, arguments: dict) -> list[str]:
    """The command line a person would type for these arguments; a name the schema does not have
    is refused before anything runs."""
    by = {_name(a): a for a in _actions(parser)}
    unknown = sorted(set(arguments) - set(by))
    if unknown:
        raise ValueError(
            f"unknown argument(s): {', '.join(unknown)}; this tool takes {', '.join(sorted(by)) or 'none'}"
        )
    out: list[str] = []
    tail: list[str] = []
    for k, v in arguments.items():
        a = by[k]
        if isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
            if v:
                out.append(max(a.option_strings, key=len))
            continue
        vals = [str(x) for x in v] if isinstance(v, list) else [str(v)]
        if not a.option_strings:
            tail.extend(vals)
        elif isinstance(a, argparse._AppendAction):
            for x in vals:
                out += [max(a.option_strings, key=len), x]
        else:
            out += [max(a.option_strings, key=len), *vals]
    return out + tail


def run_command(project: Path, command: str, argv: list[str]) -> tuple[int, str, str]:
    """`evh <command> <argv>` in the project, in its own process group, stdin closed, with a timeout
    that kills the group."""
    cmd = [sys.executable, str(HERE / "cli.py"), command, *argv, *(["--json"] if command in JSON else [])]
    p = subprocess.Popen(
        cmd,
        cwd=project,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        out, err = p.communicate(timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, err = p.communicate()
        return 124, out, err + f"\n(stopped after {TIMEOUT_S} s)"
    return p.returncode, out, err


def build_server(project: Path):
    """The MCP server: its tools, and how a call runs."""
    import anyio  # noqa: PLC0415
    import mcp.types as types  # noqa: PLC0415
    from evaluation_harness._version import __version__  # noqa: PLC0415
    from evaluation_harness.cli import COMMANDS  # noqa: PLC0415
    from mcp.server import Server  # noqa: PLC0415

    parsers = {c: parser_of(c) for c in READ_TOOLS}
    tools = [
        types.Tool(
            name=c,
            description=f"{COMMANDS[c][1]}."
            + (f" {parsers[c].description}" if parsers[c].description else ""),
            input_schema=input_schema(parsers[c]),
            annotations=types.ToolAnnotations(
                read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
            ),
        )
        for c in READ_TOOLS
    ]

    async def list_tools(_ctx, _params) -> types.ListToolsResult:
        """tools/list: the read commands."""
        return types.ListToolsResult(tools=tools)

    async def call_tool(_ctx, params) -> types.CallToolResult:
        """tools/call: the command, run as a child process."""
        name, arguments = params.name, params.arguments or {}
        if name not in parsers:
            return types.CallToolResult(content=[types.TextContent(text=f"no tool {name!r}")], is_error=True)
        try:
            argv = argv_of(parsers[name], arguments)
        except ValueError as exc:
            return types.CallToolResult(content=[types.TextContent(text=str(exc))], is_error=True)
        code, out, err = await anyio.to_thread.run_sync(run_command, project, name, argv)
        if code != 0:
            text = (err.strip() or out.strip() or f"exit {code}")[-65536:]
            return types.CallToolResult(
                content=[types.TextContent(text=f"{text}\n(exit {code})")], is_error=True
            )
        if len(out) > MAX_OUT:
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        text=f"the answer is {len(out):,} bytes, over {MAX_OUT:,}: narrow it with the command's filters"
                    )
                ],
                is_error=True,
            )
        structured = None
        if name in JSON:
            try:
                structured = json.loads(out)
            except ValueError:
                structured = None
        return types.CallToolResult(content=[types.TextContent(text=out)], structured_content=structured)

    return Server(
        "evaluation-harness",
        version=__version__,
        instructions="The evaluation harness's read commands for this project: its datasets, goals, arms, "
        "runs and comparisons. Each tool is an `evh` command; none writes or spends.",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def main(argv: list[str] | None = None) -> int:
    """evh mcp."""
    ap = argparse.ArgumentParser(prog="evh mcp", description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--project", type=Path, default=Path.cwd(), help="the project (default: the working directory)"
    )
    args = ap.parse_args(argv)
    import anyio  # noqa: PLC0415
    from mcp.server.stdio import stdio_server  # noqa: PLC0415

    project = args.project.resolve()
    server = build_server(project)

    async def serve() -> None:
        """The stdio transport, until the client closes it."""
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(serve)
    return 0


if __name__ == "__main__":
    sys.exit(main())
