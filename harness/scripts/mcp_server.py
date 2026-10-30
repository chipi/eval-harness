#!/usr/bin/env python3
"""evh mcp: the project's read commands as MCP tools, for an agent (RFC-018).

    evh mcp                       # stdio, the project the working directory is in
    evh mcp --project path/to/project

An MCP client (Claude Code, Claude Desktop, any agent) starts this as a stdio server. Its tools are
the commands a person reads the project with: the catalog's views, the inspector in the terminal,
the rounds, the runs, validate. Each call runs the command as a child process (`evh <command> …`,
with `--json` where the command has it), so a tool answers exactly what the command prints. No tool
writes, spends or runs a model: those stay commands a person runs (0.7.0 adds them, with consent).

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
import re
import runpy
import signal
import subprocess
import sys
import time
from collections import OrderedDict
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
    "captures",
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
    "importer-check": "reads a production system, not the project",
    "capture": "reads a production system and writes",
    "dataset-from-capture": "writes",
    "capture-scrub": "runs a project's command and writes",
    "reference-from-outcomes": "writes",
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
JSON |= {"dataset-items", "captures"}
#: Left out of every schema: the server uses the project's own adapter (an agent must not load an
#: arbitrary file), and sets --json itself.
HIDDEN = {"--adapter", "--json", "--help"}
TIMEOUT_S = 300
MAX_OUT = 1_000_000
#: A tool argument's bounds: no command takes a longer value (an id, a period, a search's words),
#: and a megabyte of argument only reached the kernel's limit and an error naming the interpreter.
MAX_VALUE = 512
MAX_VALUES = 64
#: The request body the HTTP endpoint reads (--max-body): a tool call is a few hundred bytes, and
#: the SDK's 4 MiB default let a few parallel bodies take the container past its memory limit.
MAX_BODY = 64 * 1024
#: --public: the answers kept, by their total size (least recently used out first).
#: Counted as the answers' text; resident memory measured ~5x that (the parsed structured content
#: beside it), so 16 MB here is ~80 MB of the container's 384 (an independent review, 2026-10-29).
ANSWERS_BYTES = 16 * 1024 * 1024
#: An answer kept is dropped after an hour: a view's default period (the last 14 days) moves with
#: the date, and a server runs for days.
ANSWERS_TTL = 3600


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
    missing = sorted(k for k, a in by.items() if (a.required or not a.option_strings) and k not in arguments)
    if missing:
        raise ValueError(f"missing argument(s): {', '.join(missing)}")
    out: list[str] = []
    tail: list[str] = []
    for k, v in sorted(arguments.items()):
        a = by[k]
        if isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
            if not isinstance(v, bool):
                raise ValueError(f"{k}: true or false, not {type(v).__name__}")
            if v:
                out.append(max(a.option_strings, key=len))
            continue
        many = a.nargs in ("*", "+") or isinstance(a, argparse._AppendAction)
        if isinstance(v, list) and not many:
            raise ValueError(f"{k}: one value, not a list")
        vals = v if isinstance(v, list) else [v]
        if any(isinstance(x, (bool, dict, list)) or x is None for x in vals):
            raise ValueError(f"{k}: each value is a string or a number")
        vals = [str(x) for x in vals]
        if any("\0" in x for x in vals):
            raise ValueError(f"{k}: a value may not hold a NUL byte")
        if len(vals) > MAX_VALUES or any(len(x) > MAX_VALUE for x in vals):
            raise ValueError(f"{k}: at most {MAX_VALUES} values of {MAX_VALUE} characters")
        # A value that starts with "-" would be read by the command as an option of its own (a
        # positional `["x", "--adapter", "mod:fn"]` would load code the schema leaves out): refused.
        bad = [x for x in vals if x.startswith("-")]
        if bad:
            raise ValueError(f"{k}: a value may not start with '-' ({bad[0][:40]!r})")
        if not a.option_strings:
            tail.extend(vals)
        elif isinstance(a, argparse._AppendAction):
            for x in vals:
                out += [max(a.option_strings, key=len), x]
        else:
            out += [max(a.option_strings, key=len), *vals]
    # Positionals after "--": whatever they hold, the command reads them as values, never options.
    return out + (["--", *tail] if tail else [])


def public_error(text: str, project: Path) -> str:
    """A command's refusal as a public caller is told it: its own message, with no server path and
    no traceback (a crash is "internal error"; the log and the error tracker have the rest)."""
    if "Traceback (most recent call last)" in text:
        return "internal error: the command failed; it is reported to the server's maintainers"
    lines = [ln for ln in text.splitlines() if ln.strip()]
    msg = next((ln for ln in reversed(lines) if ln.startswith("ERROR")), lines[-1] if lines else "")
    for root in sorted({str(project), str(project.resolve()), str(HERE.parent)}, key=len, reverse=True):
        msg = msg.replace(root + "/", "").replace(root, ".")
    return re.sub(r"/(?:[\w.-]+/)+", "", msg)[:2000]


def run_command(
    project: Path, command: str, argv: list[str], timeout: float = TIMEOUT_S, public: bool = False
) -> tuple[int, str, str]:
    """`evh <command> <argv>` in the project, in its own process group, stdin closed, with a timeout
    that kills the group. `public`: the command runs as a public server's would (EVH_PUBLIC), so it
    sees only the fields marked public."""
    cmd = [sys.executable, str(HERE / "cli.py"), command, *(["--json"] if command in JSON else []), *argv]
    # The goals' tests are the slow part of a view (~50 s for this repository's runs); each call is a
    # fresh process, so they are kept on disk (stats.EVH_P_CACHE), in the project's ignored .cache/
    # unless the deployment names its own precomputed file.
    env = dict(os.environ)
    env.setdefault("EVH_P_CACHE", str(project / ".cache" / "evh-p.jsonl"))
    env.pop("EVH_PUBLIC", None)
    if public:
        env["EVH_PUBLIC"] = "1"
    p = subprocess.Popen(
        cmd,
        cwd=project,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, err = p.communicate()
        return 124, out, err + f"\n(stopped after {timeout:g} s)"
    return p.returncode, out, err


#: In --public mode, the options that would answer with an item's text or an arm's output: a
#: public server answers with numbers and ids only, as catalog-serve --public does without --publish.
PUBLIC_HIDDEN = {"inspect": {"--item"}, "dataset-items": {"--item"}}
#: In --public mode, the tools left out, and why: a public server serves a copy of the data, not a
#: whole project (no corpora, no example code), so validate would only ever report what is not there.
PUBLIC_DROPPED = {"validate": "a public copy is not a whole project: validate fails by design"}


def tools_for(public: bool) -> tuple:
    """The tools this server offers."""
    return tuple(c for c in READ_TOOLS if not (public and c in PUBLIC_DROPPED))


#: What the log line leaves out of a call: who made it (its address, its user agent). The hooks
#: get both (analytics count a visitor by them); a log is kept and read by more hands.
PRIVATE = ("client", "agent")


def _log(**fields) -> None:
    """One JSON line per call on stderr (the deployment's log collector reads it)."""
    print(
        json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **fields}),
        file=sys.stderr,
        flush=True,
    )


class Hooks:
    """A deployment's observability (`--hooks`, the inspector's shape: catalog_serve.load_hooks):
    `start(info)`, `request(info)` after each call, `error(exc, info)`, and `routes` ({path:
    fn(query) -> (status, content_type, body)}, served beside the endpoint, not under it). A hook
    that raises is reported on stderr and never breaks the call it observes."""

    def __init__(self, obj=None):
        self.obj = obj

    def __call__(self, name: str, *args) -> None:
        fn = getattr(self.obj, name, None) if self.obj is not None else None
        if callable(fn):
            try:
                fn(*args)
            except Exception as exc:  # noqa: BLE001 -- a hook never breaks the call it observes
                print(f"hooks.{name} failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    def routes(self) -> dict:
        """The hooks' own routes, {path: fn(query) -> (status, content_type, body)}."""
        r = getattr(self.obj, "routes", None) if self.obj is not None else None
        r = r() if callable(r) else r
        return r if isinstance(r, dict) else {}


def _client(ctx, header: str | None) -> tuple[str, str]:
    """(the caller's address, its user agent) from the HTTP request; ("", "") over stdio. A header
    names the caller only when the deployment says so (--client-header), behind a proxy that sets it."""
    req = getattr(ctx, "request", None)
    if req is None:
        return "", ""
    peer = req.client.host if req.client else ""
    addr = ip_or_none(req.headers.get(header) if header else None) or peer
    return addr[:64], req.headers.get("user-agent", "")[:120]


def ip_or_none(value: str | None) -> str | None:
    """The value when it is an IP address, else None: a header that holds anything else (text,
    a value made up per request) never names a caller."""
    import ipaddress  # noqa: PLC0415

    try:
        return str(ipaddress.ip_address((value or "").strip()[:64]))
    except ValueError:
        return None


def caller_key(addr: str) -> str:
    """Whom the rate counts: an IPv4 address, or an IPv6 address's /64 (one host holds a whole
    /64, and rotating within it must not reset the count)."""
    import ipaddress  # noqa: PLC0415

    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return addr
    if ip.version == 6 and ip.ipv4_mapped:  # ::ffff:a.b.c.d is that IPv4 caller, not a /64 they share
        return str(ip.ipv4_mapped)
    return str(ipaddress.ip_network(f"{ip}/64", strict=False)) if ip.version == 6 else str(ip)


def build_server(
    project: Path,
    *,
    public: bool = False,
    timeout: float = TIMEOUT_S,
    concurrent: int = 4,
    rate: int = 0,
    rate_total: int = 0,
    client_header: str | None = None,
    hooks: Hooks | None = None,
):
    """The MCP server: its tools, and how a call runs. `public`: no option that answers with text;
    `concurrent`: how many commands run at once (a call that waits 30 s for a slot is refused);
    `rate`: calls a minute per caller, `rate_total`: from all callers together (0: no limit; nothing
    in front of a public server throttles for it, and a caller who can rotate its address is still
    held by the total)."""
    hooks = hooks or Hooks()
    recent: dict[str, list[float]] = {}
    everyone: list[float] = []
    answers: OrderedDict = OrderedDict()  # (tool, argv) -> its result, --public only
    answers_size = [0]
    inflight: dict[str, int] = {}
    import anyio  # noqa: PLC0415
    import mcp.types as types  # noqa: PLC0415
    from evaluation_harness._version import __version__  # noqa: PLC0415
    from evaluation_harness.cli import COMMANDS  # noqa: PLC0415
    from mcp.server import Server  # noqa: PLC0415

    parsers = {c: parser_of(c) for c in tools_for(public)}
    if public:
        for c, flags in PUBLIC_HIDDEN.items():
            p = parsers[c]
            p._actions = [a for a in p._actions if not set(a.option_strings) & flags]
    slots = anyio.CapacityLimiter(concurrent)
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
        for c in tools_for(public)
    ]

    async def list_tools(_ctx, _params) -> types.ListToolsResult:
        """tools/list: the read commands."""
        return types.ListToolsResult(tools=tools)

    def refuse(text: str, info: dict) -> types.CallToolResult:
        """A call refused before it ran: logged (without the caller) and told to the hooks."""
        _log(**{k: v for k, v in info.items() if k not in PRIVATE})
        hooks("request", info)
        return types.CallToolResult(content=[types.TextContent(text=text)], is_error=True)

    async def call_tool(ctx, params) -> types.CallToolResult:
        """tools/call: the command, run as a child process."""
        name, arguments = params.name, params.arguments or {}
        client, agent = _client(ctx, client_header)
        key = caller_key(client)
        # What is recorded of a call: the tool (a name the server does not have is "unknown": a
        # client's string never becomes a metric label, an event or a log key), the names of its
        # arguments (at most 16, never their values), how it ended. The caller's address goes to
        # the hooks (analytics derive a visitor from it), and neither it nor the user agent into the log line.
        known = name in parsers
        args = [str(k)[:40] for k in sorted(arguments)[:16]] if known else []
        info: dict = {"tool": name if known else "unknown", "args": args, "agent": agent, "client": client}
        try:
            # The rate counts every call, refused ones too: refusals are the cheap way to flood.
            if rate:
                now = time.monotonic()
                seen = [t for t in recent.get(key, []) if now - t < 60]
                if len(seen) >= rate:
                    return refuse(
                        f"more than {rate} calls a minute; wait a moment", {**info, "refused": "rate"}
                    )
                recent[key] = [*seen, now]
                if len(recent) > 4096:  # forget callers quiet for a minute
                    for k in [k for k, ts in recent.items() if not ts or now - ts[-1] >= 60]:
                        del recent[k]
            if not known:
                return refuse(f"no tool {name[:60]!r}", {**info, "refused": "tool"})
            try:
                argv = argv_of(parsers[name], arguments)
            except ValueError as exc:
                return refuse(str(exc), {**info, "refused": "arguments"})
            # M2: a public server reads a release that never changes under it, so an answer is
            # kept by its exact command line: a repeated heavy view costs nothing the second time.
            kept = answers.get((name, tuple(argv))) if public else None
            if kept is not None and time.monotonic() - kept[0] > ANSWERS_TTL:
                answers.pop((name, tuple(argv)), None)
                answers_size[0] -= len(kept[1].content[0].text)
                kept = None
            hit = kept[1] if kept is not None else None
            if hit is not None:
                answers.move_to_end((name, tuple(argv)))
                _log(**{k: v for k, v in info.items() if k not in PRIVATE}, exit=0, cached=True)
                hooks(
                    "request", {**info, "exit": 0, "ms": 0, "bytes": len(hit.content[0].text), "cached": True}
                )
                return hit
            # The total counts the calls that run a command: a flood of refusals (which costs
            # nothing) is held by the caller's own rate and never locks everyone else out.
            if rate_total:
                now = time.monotonic()
                everyone[:] = [t for t in everyone if now - t < 60]
                if len(everyone) >= rate_total:
                    return refuse(
                        "the server is answering as many calls as it takes a minute; try again shortly",
                        {**info, "refused": "rate_total"},
                    )
                everyone.append(now)
            if (
                client and inflight.get(key, 0) >= 1
            ):  # over HTTP: a local stdio client may run tools in parallel
                return refuse(
                    "one call at a time per caller: wait for the last to answer", {**info, "refused": "busy"}
                )
            inflight[key] = inflight.get(key, 0) + 1
            try:
                t0 = time.monotonic()
                with anyio.move_on_after(30) as waited:
                    await slots.acquire()
                if waited.cancelled_caught:
                    return refuse("the server is busy: try again in a minute", {**info, "refused": "busy"})
                try:
                    code, out, err = await anyio.to_thread.run_sync(
                        run_command, project, name, argv, timeout, public
                    )
                finally:
                    slots.release()
            finally:
                inflight[key] -= 1
                if not inflight[key]:
                    del inflight[key]
            done = {**info, "exit": code, "ms": round((time.monotonic() - t0) * 1000), "bytes": len(out)}
            # A command that refuses (exit 1, its ERROR: line, no traceback: a dataset id that is a
            # path, a goal that does not exist) answered as designed; a crash is the error.
            if code == 1 and "ERROR" in err and "Traceback" not in err:
                done["refused"] = "command"
            _log(**{k: v for k, v in done.items() if k not in PRIVATE})
            hooks("request", done)
        except Exception as exc:
            hooks("error", exc, info)
            raise
        if code != 0:
            text = (err.strip() or out.strip() or f"exit {code}")[-65536:]
            if public:
                text = public_error(text, project)
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
        if public and name == "dataset-items" and isinstance(structured, dict):
            # L2: a profile written --with-text carries item text; a public server serves none.
            for r in (structured.get("result") or {}).get("rows") or []:
                r.pop("text", None)
            out = json.dumps(structured, indent=1)
        res = types.CallToolResult(content=[types.TextContent(text=out)], structured_content=structured)
        if public:
            if (name, tuple(argv)) not in answers:
                answers[(name, tuple(argv))] = (time.monotonic(), res)
                answers_size[0] += len(out)
            while answers and answers_size[0] > ANSWERS_BYTES:
                _, (_t, old) = answers.popitem(last=False)
                answers_size[0] -= len(old.content[0].text)
        return res

    return Server(
        "evaluation-harness",
        version=__version__,
        instructions="The evaluation harness's read commands for this project: its datasets, goals, arms, "
        "runs and comparisons. Each tool is an `evh` command; none writes or spends.",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


LOOPBACK = ("127.0.0.1", "localhost", "::1")


def main(argv: list[str] | None = None) -> int:
    """evh mcp."""
    ap = argparse.ArgumentParser(prog="evh mcp", description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--project", type=Path, default=Path.cwd(), help="the project (default: the working directory)"
    )
    ap.add_argument(
        "--http", action="store_true", help="serve Streamable HTTP instead of stdio (a shared server)"
    )
    ap.add_argument("--bind", default="127.0.0.1", help="--http: the address (default: 127.0.0.1)")
    # Not 8765: catalog-serve takes it, and both may run on one machine.
    ap.add_argument("--port", type=int, default=8766, help="--http: the port (default: 8766)")
    ap.add_argument("--path", default="/mcp", help="--http: the endpoint's path (default: /mcp)")
    ap.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        help="--http: a Host header the server answers (repeat); required to bind beyond the loopback",
    )
    ap.add_argument(
        "--allowed-origin",
        action="append",
        default=[],
        help="--http: a browser Origin the server accepts (repeat)",
    )
    ap.add_argument(
        "--public",
        action="store_true",
        help="no option that answers with an item's text or an arm's output, and no validate tool "
        "(for a server anyone can reach)",
    )
    ap.add_argument(
        "--timeout", type=float, default=TIMEOUT_S, help=f"seconds per call (default: {TIMEOUT_S})"
    )
    ap.add_argument("--concurrent", type=int, default=4, help="commands run at once (default: 4)")
    ap.add_argument(
        "--rate", type=int, default=0, help="--http: calls a minute per caller (default: no limit)"
    )
    ap.add_argument(
        "--rate-total",
        type=int,
        default=0,
        help="--http: calls a minute from all callers together (default: no limit)",
    )
    ap.add_argument(
        "--max-body",
        type=int,
        default=MAX_BODY,
        help=f"--http: the largest request body read, in bytes (default: {MAX_BODY}); larger is answered 413",
    )
    ap.add_argument(
        "--max-connections",
        type=int,
        default=64,
        help="--http: connections served at once; more are answered 503 (default: 64)",
    )
    ap.add_argument(
        "--request-rate",
        type=int,
        default=0,
        help="--http: HTTP requests a minute per caller to the endpoint, every method (default: no limit); "
        "a tool call is about three",
    )
    ap.add_argument(
        "--client-header",
        help="--http: the header that names the caller, set by the proxy in front (e.g. CF-Connecting-IP)",
    )
    ap.add_argument(
        "--hooks",
        help="a deployment's observability: path/to/file.py[:NAME] or module[:NAME] (start, request, error, routes)",
    )
    args = ap.parse_args(argv)
    import anyio  # noqa: PLC0415

    project = args.project.resolve()
    if args.http and args.bind not in LOOPBACK and not args.allowed_host:
        raise SystemExit(
            f"--bind {args.bind} reaches beyond this machine: name the Host it answers with --allowed-host "
            "(the server checks it against DNS rebinding)"
        )
    hooks = Hooks()
    if args.hooks:
        from evaluation_harness.catalog_serve import load_hooks  # noqa: PLC0415

        hooks = Hooks(load_hooks(args.hooks))
    server = build_server(
        project,
        public=args.public,
        timeout=args.timeout,
        concurrent=args.concurrent,
        rate=args.rate,
        rate_total=args.rate_total,
        client_header=args.client_header,
        hooks=hooks,
    )
    from evaluation_harness._version import __version__  # noqa: PLC0415

    hooks(
        "start",
        {
            "version": __version__,
            "tools": list(tools_for(args.public)),
            "public": args.public,
            "transport": "http" if args.http else "stdio",
        },
    )
    args.hook_obj = hooks
    if not args.http:
        from mcp.server.stdio import stdio_server  # noqa: PLC0415

        async def serve() -> None:
            """The stdio transport, until the client closes it."""
            async with stdio_server() as (read, write):
                await server.run(read, write, server.create_initialization_options())

        anyio.run(serve)
        return 0
    return serve_http(server, args)


def serve_http(server, args) -> int:
    """Streamable HTTP, stateless, JSON responses: every request stands alone, so any client and any
    number of replicas serve it. `<path>/health` answers {"ok": true} for a load balancer."""
    import uvicorn  # noqa: PLC0415
    from evaluation_harness._version import __version__  # noqa: PLC0415
    from mcp.server.transport_security import TransportSecuritySettings  # noqa: PLC0415
    from starlette.requests import Request  # noqa: PLC0415
    from starlette.responses import JSONResponse, Response  # noqa: PLC0415
    from starlette.routing import Route  # noqa: PLC0415

    security = None
    if args.allowed_host:
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[*args.allowed_host, "127.0.0.1:*", "localhost:*"],
            allowed_origins=args.allowed_origin,
        )

    async def health(_request: Request) -> JSONResponse:
        """GET <path>/health."""
        return JSONResponse(
            {"ok": True, "version": __version__, "tools": len(tools_for(args.public)), "public": args.public}
        )

    def hook_route(fn):
        async def handle(request: Request) -> Response:
            """A route the hooks serve (e.g. /metrics), outside the MCP endpoint's path."""
            status, ctype, body = fn(request.url.query)
            return Response(body, status_code=status, media_type=ctype)

        return handle

    extra = [Route(f"{args.path.rstrip('/')}/health", health, methods=["GET"])]
    extra += [Route(p, hook_route(fn), methods=["GET"]) for p, fn in args.hook_obj.routes().items()]
    app = server.streamable_http_app(
        streamable_http_path=args.path,
        stateless_http=True,
        json_response=True,
        transport_security=security,
        host=args.bind,
        custom_starlette_routes=extra,
        max_request_body_size=args.max_body,
    )
    app = Gate(app, args.path, args.request_rate, args.client_header, args.max_body)
    print(f"evh mcp: http://{args.bind}:{args.port}{args.path}", file=sys.stderr, flush=True)
    uvicorn.run(
        app,
        host=args.bind,
        port=args.port,
        log_level="warning",
        proxy_headers=True,
        limit_concurrency=args.max_connections,
        timeout_keep_alive=5,
    )
    return 0


class Gate:
    """In front of the endpoint (ASGI): a GET on it is 405, since a stateless JSON server has no
    stream to open and every held GET cost ~85 KB; and with --request-rate, each caller's
    requests to it are counted, every method, before the SDK reads a byte of the body (ping and
    tools/list floods never reach call_tool's rate). A caller has at most OPEN_PER_CALLER requests
    open at once: --max-connections bounds them all, and without this one address holding slow
    requests could take every connection."""

    OPEN_PER_CALLER = 8
    #: Seconds a request's body may take to arrive: a request held open mid-body is never timed
    #: out by uvicorn's keep-alive, and eight callers holding eight each took every connection.
    BODY_DEADLINE = 10.0

    def __init__(self, app, path: str, rate: int, header: str | None, max_body: int = MAX_BODY):
        self.app, self.path, self.rate, self.header = app, path.rstrip("/") or "/", rate, header
        self.max_body = max_body
        self.seen: dict[str, list[float]] = {}
        self.open: dict[str, int] = {}

    def _caller(self, scope) -> str:
        peer = (scope.get("client") or ("", 0))[0]
        if self.header:
            want = self.header.lower().encode()
            for k, v in scope.get("headers") or []:
                if k == want:
                    return caller_key(ip_or_none(v.decode("latin-1")) or peer)
        return caller_key(peer)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].rstrip("/") == self.path:
            # `/mcp/` is `/mcp`: the SDK's own answer was a 307 to an http:// address behind the proxy.
            scope = dict(scope, path=self.path, raw_path=self.path.encode())
            if scope["method"] == "GET":
                return await _plain(send, 405, b"this server answers POST only (stateless, JSON)")
            key = self._caller(scope)
            if self.open.get(key, 0) >= self.OPEN_PER_CALLER:
                return await _plain(send, 429, b"too many requests open at once; wait for an answer")
            if self.rate:
                now = time.monotonic()
                hits = [t for t in self.seen.get(key, []) if now - t < 60]
                if len(hits) >= self.rate:
                    return await _plain(send, 429, b"too many requests a minute; wait a moment")
                self.seen[key] = [*hits, now]
                if len(self.seen) > 4096:
                    for k in [k for k, ts in self.seen.items() if now - ts[-1] >= 60]:
                        del self.seen[k]
            self.open[key] = self.open.get(key, 0) + 1
            try:
                # The body is read here, whole, within the deadline and the size bound, and handed
                # to the SDK in one piece: a stall is 408 and an oversize 413 from us, not a 500 from
                # inside the SDK, and the SDK never waits on a slow client.
                try:
                    body = await _read_body(receive, self.BODY_DEADLINE, self.max_body)
                except TimeoutError:
                    return await _plain(send, 408, b"the request's body did not arrive in time")
                if body is None:
                    return await _plain(send, 413, b"the request's body is too large")
                return await self.app(scope, _replay(body, receive), send)
            finally:
                self.open[key] -= 1
                if not self.open[key]:
                    del self.open[key]
        return await self.app(scope, receive, send)


async def _read_body(receive, seconds: float, limit: int) -> bytes | None:
    """The whole request body within `seconds` (TimeoutError past it); None when it is over `limit`."""
    import anyio  # noqa: PLC0415

    chunks, size = [], 0
    with anyio.fail_after(seconds):
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                raise TimeoutError
            part = msg.get("body", b"")
            size += len(part)
            if size > limit:
                return None
            chunks.append(part)
            if not msg.get("more_body"):
                return b"".join(chunks)


def _replay(body: bytes, receive):
    """`receive` that first gives the body read, whole, then the client's own messages (a disconnect)."""
    sent = [False]

    async def wrapped():
        if not sent[0]:
            sent[0] = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return wrapped


async def _plain(send, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


if __name__ == "__main__":
    sys.exit(main())
