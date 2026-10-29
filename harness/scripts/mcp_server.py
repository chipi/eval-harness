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
import time
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
    missing = sorted(k for k, a in by.items() if (a.required or not a.option_strings) and k not in arguments)
    if missing:
        raise ValueError(f"missing argument(s): {', '.join(missing)}")
    out: list[str] = []
    tail: list[str] = []
    for k, v in arguments.items():
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


def run_command(
    project: Path, command: str, argv: list[str], timeout: float = TIMEOUT_S
) -> tuple[int, str, str]:
    """`evh <command> <argv>` in the project, in its own process group, stdin closed, with a timeout
    that kills the group."""
    cmd = [sys.executable, str(HERE / "cli.py"), command, *(["--json"] if command in JSON else []), *argv]
    # The goals' tests are the slow part of a view (~50 s for this repository's runs); each call is a
    # fresh process, so they are kept on disk (stats.EVH_P_CACHE), in the project's ignored .cache/
    # unless the deployment names its own precomputed file.
    env = dict(os.environ)
    env.setdefault("EVH_P_CACHE", str(project / ".cache" / "evh-p.jsonl"))
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
    addr = (req.headers.get(header) if header else None) or (req.client.host if req.client else "")
    return addr[:64], req.headers.get("user-agent", "")[:120]


def caller_key(addr: str) -> str:
    """Whom the rate counts: an IPv4 address, or an IPv6 address's /64 (one host holds a whole
    /64, and rotating within it must not reset the count)."""
    import ipaddress  # noqa: PLC0415

    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return addr
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
            if rate_total:
                now = time.monotonic()
                everyone[:] = [t for t in everyone if now - t < 60]
                if len(everyone) >= rate_total:
                    return refuse(
                        "the server is answering as many calls as it takes a minute; try again shortly",
                        {**info, "refused": "rate_total"},
                    )
                everyone.append(now)
            if not known:
                return refuse(f"no tool {name[:60]!r}", {**info, "refused": "tool"})
            try:
                argv = argv_of(parsers[name], arguments)
            except ValueError as exc:
                return refuse(str(exc), {**info, "refused": "arguments"})
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
                    code, out, err = await anyio.to_thread.run_sync(run_command, project, name, argv, timeout)
                finally:
                    slots.release()
            finally:
                inflight[key] -= 1
                if not inflight[key]:
                    del inflight[key]
            done = {**info, "exit": code, "ms": round((time.monotonic() - t0) * 1000), "bytes": len(out)}
            _log(**{k: v for k, v in done.items() if k not in PRIVATE})
            hooks("request", done)
        except Exception as exc:
            hooks("error", exc, info)
            raise
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
    ap.add_argument("--port", type=int, default=8765, help="--http: the port (default: 8765)")
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
        help="no option that answers with an item's text or an arm's output (for a server anyone can reach)",
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
    )
    print(f"evh mcp: http://{args.bind}:{args.port}{args.path}", file=sys.stderr, flush=True)
    uvicorn.run(app, host=args.bind, port=args.port, log_level="warning", proxy_headers=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
