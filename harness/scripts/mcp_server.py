#!/usr/bin/env python3
"""evh mcp: the harness's reads as MCP tools, for an agent (RFC-018, RFC-032 step 9).

    evh mcp                       # stdio, the project the working directory is in
    evh mcp --project path/to/project

An MCP client (Claude Code, Claude Desktop, any agent) starts this as a stdio server. Its tools are the read operations of
the harness (`evh operations`; the same names as the command line and the API's resources): the catalog's views, the rounds,
the runs, the statistics. Each call is answered in the server's own process, from the data the project holds, and the answer
is the operation's result, structured: `{"command", "version", "result"}`. No tool writes the project, spends or runs a model:
those stay commands a person runs (0.8.0 adds them, with consent). The server keeps what it computed in memory, for as long as
the data is what it was computed from, and the paired tests of the goals in the project's ignored .cache/.

For Claude Code, in the project:  claude mcp add evh -- evh mcp
"""

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import contextvars
import json
import math
import os
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from evaluation_harness import _store
from evaluation_harness import ops as _ops  # the model's operations (RFC-032), no project code
from evaluation_harness._cmdline import (
    MAX_VALUE,
    MAX_VALUES,
    PATH_VARS,
    TIMEOUT_S,
    TOOL_HIDDEN,
    argv_of,
    input_schema,
    kill_group,
    parser_of,
    public_error,
    run_command,
)

HERE = Path(__file__).resolve().parent
MAX_OUT = 1_000_000

#: Tools that write, for the agent sampler of a study alone (owner, 2026-11-09, RFC-029): offered by a local server
#: only, never a public one, and named as not read-only. They are commands, run as a process (the jobs: RFC-032 step 9,
#: P3). Every other write is the command line's or a job's.
AGENT_TOOLS = ("study-ask", "study-tell")

NOT_TOOLS = {
    "study-run": "runs a study's loop and spends: a job (the agent sampler's own steps are tools)",
    "study-stop": "stops a study",
    "study-confirm": "a decision that spends a look and money: a person's command or a job",
    "study-import": "writes a study",
    "prompt-version": "records a prompt version",
    "prompt-export": "writes a file",
    "jobs-start": "starts a job: the agents act through the command line or the API (RFC-026)",
    "jobs-status": "the jobs of this machine's project, not its data",
    "jobs-logs": "a job's log, which can hold anything its command printed",
    "jobs-stop": "stops a job",
    "jobs-resume": "starts a job",
    "migrate": "rewrites the project's data to this release's formats",
    "data-migrate": "moves the project's data between files and its database",
    "data-put": "writes a setting",
    "data-rm": "deletes a setting or a run",
    "init": "writes a project",
    "skills-install": "writes the skills into a project",
    "env-check": "reads the environment and keys, not the project",
    "capture-scrub": "runs a project's command and writes",
    "catalog": "writes the pages",
    "catalog-serve": "never returns",
    "self-test": "runs the test suite",
    "mcp": "this server",
    "openapi": "the API's own description, made from the operations (RFC-032)",
}
NOT_TOOLS.update(
    dict.fromkeys(
        (op.name for op in _ops.of_kind("edit", "decision", "work")),
        "a write of the model: the command line, or its API resource (RFC-032)",
    )
)
NOT_TOOLS["sheet-export"] = "writes a file: the sheet as a CSV to fill in"

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


def read_ops(public: bool) -> list[Any]:
    """The registry's reads this server offers: every read, but those a public server does not offer (`public_dropped`)."""
    return [op for op in _ops.of_kind("read") if not (public and op.public_dropped)]


def tools_for(public: bool) -> tuple:
    """The tools this server offers: a read operation each, named as the operation (the name the command line and the API
    use), and for a local server the agent sampler's two."""
    return tuple(op.name for op in read_ops(public)) + (() if public else AGENT_TOOLS)


#: The reads whose answer with no input depends on today's date (a period counted from today, by default): never written
#: ahead, since an answer kept past the day would read the wrong period.
DATED = {"overview-show", "activity-show"}


def tool_schema(op: Any, public: bool) -> dict:
    """An operation's input as the tool's JSON Schema: the parts of its route, then its own inputs (and the inputs of which
    a call names one, `anyOf`)."""
    own = op.schema(public)
    parts = op.path_params()
    return {
        "type": "object",
        "properties": {
            **{p: {"type": "string", "description": f"the {p.replace('_', ' ')}'s id"} for p in parts},
            **own["properties"],
        },
        "required": [*parts, *own["required"]],
        **({"anyOf": own["anyOf"]} if "anyOf" in own else {}),
        "additionalProperties": False,
    }


def answerable_ahead(public: bool) -> list[str]:
    """The tools whose answer can be written ahead for a release that never changes (--write-answers): each read that takes no
    input it must be given (none required, none of several to name), but those whose default depends on the date (DATED)."""
    return [
        op.name
        for op in read_ops(public)
        if op.name not in DATED and not tool_schema(op, public)["required"] and not op.one_of
    ]


def check_arguments(op: Any, arguments: dict, public: bool) -> None:
    """A call's arguments against the tool's schema: a name the schema does not have, a missing one, a wrong type, a value
    longer than any input takes, are refused before anything runs. ValueError says which."""
    import jsonschema  # noqa: PLC0415

    schema = tool_schema(op, public)
    try:
        jsonschema.validate(arguments, schema)
    except jsonschema.ValidationError as exc:
        unknown = sorted(set(arguments) - set(schema["properties"]))
        if unknown:
            raise ValueError(
                f"unknown argument(s): {', '.join(unknown)}; this tool takes {', '.join(sorted(schema['properties'])) or 'none'}"
            ) from None
        from evaluation_harness.ops.registry import input_problem  # noqa: PLC0415

        raise ValueError(input_problem(exc)) from None

    def strings(v: Any) -> list[str]:
        return [x for x in (v if isinstance(v, list) else [v]) if isinstance(x, str)]

    for k, v in arguments.items():
        vals = strings(v)
        if any("\0" in x for x in vals):
            raise ValueError(f"{k}: a value may not hold a NUL byte")
        if len(vals) > MAX_VALUES or any(len(x) > MAX_VALUE for x in vals):
            raise ValueError(f"{k}: at most {MAX_VALUES} values of {MAX_VALUE} characters")


def run_op(op: Any, arguments: dict, public: bool) -> dict:
    """An operation answered in this process, as the public flag of the server says: its result, as the envelope every
    surface gives it (`command`, `version`, `result`), as JSON holds it (NaN and infinities as null)."""
    from evaluation_harness import _jsonout, _visibility  # noqa: PLC0415
    from evaluation_harness._version import __version__  # noqa: PLC0415
    from evaluation_harness.ops.legacy import refusing  # noqa: PLC0415

    parts = {p: arguments[p] for p in op.path_params()}
    inputs = {k: v for k, v in arguments.items() if k not in parts}
    try:
        with _visibility.public_call(public), _jsonout.own_notes(), refusing():
            result = op.call(**parts, **inputs)
    except SystemExit as exc:  # a command's exit that is not a refusal: a crash, not the server's end
        raise RuntimeError(f"{op.name} exited: {exc.code}") from None
    return _jsonout.plain({"command": op.name, "version": __version__, "result": result})


def _answer(types, envelope: dict | None, text: str):
    """An answer as the tool gives it: its text, and the envelope as structured content."""
    return types.CallToolResult(content=[types.TextContent(text=text)], structured_content=envelope)


def write_answers(project: Path, path: Path, public: bool) -> int:
    """--write-answers: each read answerable ahead, answered once with no argument as a call would be, in this process, its
    answer one JSON line {tool, args, out, harness}. A tool that fails or answers past MAX_OUT is left out: a call runs it.
    A first call after a start used to take tens of seconds on a deployment that limits the server's CPU (every arm's
    scores read again); an answer written ahead is read from the release."""
    from evaluation_harness._version import __version__  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    ops = {op.name: op for op in read_ops(public)}
    calls: list[tuple[str, dict]] = [(c, {}) for c in answerable_ahead(public)]
    # A tool whose one input is a dataset is answerable ahead for each dataset: a finite set. The first public
    # `leaderboard` took 47-60 s on 2026-11-04 (a seeded permutation test, 5 s of CPU here).
    calls += [(c, {"dataset": ds}) for c in BY_DATASET if c in ops for ds in dataset_ids(project)]
    lines, left, failed, no_runs, large = [], [], [], 0, 0
    for name, args in calls:
        try:
            envelope = run_op(ops[name], args, public)
            out = json.dumps(envelope, ensure_ascii=False)
        except Problem as exc:
            if not args:
                left.append(f"{name} ({exc.kind})")
            elif "no runs on dataset" in str(exc):  # nothing to say about it: a call answers that itself
                no_runs += 1
            else:  # named, so a broken render says why (every one failed from 0.6.2 to 0.7.1, unnoticed)
                failed.append(f"{name} {args} ({exc.kind}: {str(exc)[:120]})")
            continue
        except Exception as exc:  # noqa: BLE001 - a crash is the harness's bug: the release fails, the tool named, the rest still tried
            failed.append(f"{name} {args} ({type(exc).__name__}: {str(exc)[:120]})")
            continue
        if len(out) > MAX_OUT:
            if not args:
                left.append(f"{name} ({len(out):,} bytes)")
            else:
                large += 1
            continue
        lines.append(json.dumps({"tool": name, "args": args, "out": out, "harness": __version__}))
    _store.mkdir(path.parent, parents=True, exist_ok=True)
    _store.write_text(path, "".join(x + "\n" for x in lines), encoding="utf-8")
    print(
        f"{path}: {len(lines)} answer(s) written ahead"
        + (f"; left out: {', '.join(left)}" if left else "")
        + (f"; {no_runs} per-dataset call(s) on a dataset with no runs" if no_runs else "")
        + (f"; {large} too large to keep" if large else "")
        + (f"; {len(failed)} FAILED: {'; '.join(failed[:3])}" if failed else "")
    )
    return 1 if failed else 0


#: The tools written ahead once per dataset (--write-answers), with `dataset` their only input.
BY_DATASET = ("leaderboard",)


def dataset_ids(project: Path) -> list[str]:
    """The project's dataset ids (data/datasets/*.json), sorted."""
    return sorted(p.stem for p in _store.glob(project / "data" / "datasets", "*.json"))


def use_project(project: Path) -> None:
    """Make this process the project's: its working directory, EVAL_HOME, the paired tests' cache and its .env, as a command
    run in the project had them. A relative path the caller set is made absolute from where the caller stands first."""
    for k in PATH_VARS:
        if os.environ.get(k) and not os.path.isabs(os.environ[k]):
            os.environ[k] = os.path.abspath(os.environ[k])
    os.chdir(project)
    os.environ["EVAL_HOME"] = str(project)
    os.environ["EVAL_VIA_EVH"] = (
        "1"  # the hints an answer gives name `evh <command>`: an agent has no Makefile
    )
    from evaluation_harness import _common  # noqa: PLC0415

    _common.project_root.cache_clear()
    _common._paths.cache_clear()
    _common.load_dotenv()
    _common.use_p_cache()


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
    answers_file: Path | None = None,
):
    """The MCP server: its tools, and how a call is answered. Every read operation of the registry is a tool, answered in this
    process (`public`: the call is a public server's, so what a public server must not show stays hidden, and the operations
    that show it are not offered); `concurrent`: how many calls are answered at once (a call that waits 30 s for a slot is
    refused); `rate`: calls a minute per caller, `rate_total`: from all callers together (0: no limit; nothing in front of a
    public server throttles for it, and a caller who can rotate its address is still held by the total). `answers_file`
    (--public): answers written ahead for this release (--write-answers), served without computing them; a line another
    harness version wrote is not read."""
    hooks = hooks or Hooks()
    recent: dict[str, list[float]] = {}
    everyone: list[float] = []
    answers: OrderedDict = OrderedDict()  # (tool, args as JSON) -> its result, --public only
    answers_size = [0]
    inflight: dict[str, int] = {}
    import anyio  # noqa: PLC0415
    import mcp.types as types  # noqa: PLC0415
    from evaluation_harness._version import __version__  # noqa: PLC0415
    from evaluation_harness.cli import COMMANDS  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415
    from mcp.server import Server  # noqa: PLC0415

    ops = {op.name: op for op in read_ops(public)}
    agent = {} if public else {c: parser_of(c) for c in AGENT_TOOLS}
    for c, flags in TOOL_HIDDEN.items():
        if c in agent:
            agent[c]._actions = [a for a in agent[c]._actions if not set(a.option_strings) & flags]
    known_tools = {*ops, *agent}

    def key_of(name: str, arguments: dict) -> tuple:
        return (name, json.dumps(arguments, sort_keys=True, ensure_ascii=False))

    if public and answers_file is not None:
        for line in _store.read_text(answers_file, encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue  # a torn line: that tool is answered when called
            if not isinstance(rec, dict) or rec.get("harness") != __version__ or rec.get("tool") not in ops:
                continue
            text = str(rec.get("out") or "")
            try:
                envelope = json.loads(text)
            except ValueError:
                continue
            # Written for this release, which never changes under the server: kept for as long as it runs,
            # never past ANSWERS_TTL (its time is infinitely recent).
            answers[key_of(rec["tool"], rec.get("args") or {})] = (math.inf, _answer(types, envelope, text))
            answers_size[0] += len(text)
    # Held by a call's work, released by that work when it ends, not when its caller stops waiting: a call answered in this
    # process cannot be stopped, so a slot freed at the timeout let repeated slow calls run past --concurrent (and the
    # callers' one-at-a-time with them), unbounded, on a server with half a CPU.
    slots = threading.BoundedSemaphore(concurrent)
    tally = threading.Lock()  # inflight, which a call's work changes from its own thread
    tools = [
        types.Tool(
            name=op.name,
            description=op.about,
            input_schema=tool_schema(op, public),
            annotations=types.ToolAnnotations(
                read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
            ),
        )
        for op in ops.values()
    ] + [
        types.Tool(
            name=c,
            description=f"{COMMANDS[c][1]}." + (f" {agent[c].description}" if agent[c].description else ""),
            input_schema=input_schema(agent[c]),
            annotations=types.ToolAnnotations(
                read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
            ),
        )
        for c in agent
    ]

    async def list_tools(_ctx, _params) -> types.ListToolsResult:
        """tools/list: the read operations."""
        return types.ListToolsResult(tools=tools)

    def refuse(text: str, info: dict) -> types.CallToolResult:
        """A call refused before it ran: logged (without the caller) and told to the hooks."""
        _log(**{k: v for k, v in info.items() if k not in PRIVATE})
        hooks("request", info)
        return types.CallToolResult(content=[types.TextContent(text=text)], is_error=True)

    def remember(k: tuple, res) -> None:
        if k not in answers:
            answers[k] = (time.monotonic(), res)
            answers_size[0] += len(res.content[0].text)
        while answers and answers_size[0] > ANSWERS_BYTES:
            _, (_t, old) = answers.popitem(last=False)
            answers_size[0] -= len(old.content[0].text)

    async def call_tool(ctx, params) -> types.CallToolResult:
        """tools/call: the operation, answered in this process."""
        name, arguments = params.name, params.arguments or {}
        client, agent_name = _client(ctx, client_header)
        key = caller_key(client)
        # What is recorded of a call: the tool (a name the server does not have is "unknown": a
        # client's string never becomes a metric label, an event or a log key), the names of its
        # arguments (at most 16, never their values), how it ended. The caller's address goes to
        # the hooks (analytics derive a visitor from it), and neither it nor the user agent into the log line.
        known = name in known_tools
        args = [str(k)[:40] for k in sorted(arguments)[:16]] if known else []
        info: dict = {
            "tool": name if known else "unknown",
            "args": args,
            "agent": agent_name,
            "client": client,
        }
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
            argv: list[str] = []
            try:
                if name in agent:
                    argv = argv_of(agent[name], arguments)
                else:
                    check_arguments(ops[name], arguments, public)
            except ValueError as exc:
                return refuse(str(exc), {**info, "refused": "arguments"})
            # M2: a public server reads a release that never changes under it, so an answer is kept by what was asked: a
            # repeated heavy view costs nothing the second time.
            answer_key = key_of(name, arguments)
            kept = answers.get(answer_key) if public and name in ops else None
            if kept is not None and time.monotonic() - kept[0] > ANSWERS_TTL:
                answers.pop(answer_key, None)
                answers_size[0] -= len(kept[1].content[0].text)
                kept = None
            hit = kept[1] if kept is not None else None
            if hit is not None:
                answers.move_to_end(answer_key)
                _log(**{k2: v for k2, v in info.items() if k2 not in PRIVATE}, exit=0, cached=True)
                hooks(
                    "request", {**info, "exit": 0, "ms": 0, "bytes": len(hit.content[0].text), "cached": True}
                )
                return hit
            # The total counts the calls that are answered: a flood of refusals (which costs
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
            with tally:  # over HTTP: a local stdio client may run tools in parallel
                busy = bool(client) and inflight.get(key, 0) >= 1
                if not busy:
                    inflight[key] = inflight.get(key, 0) + 1
            if busy:
                return refuse(
                    "one call at a time per caller: wait for the last to answer", {**info, "refused": "busy"}
                )

            def caller_done() -> None:
                """The caller's call is over: another may start (one at a time per caller)."""
                with tally:
                    inflight[key] -= 1
                    if not inflight[key]:
                        del inflight[key]

            code, err, out, envelope = 0, "", "", None
            acquired = handed = False
            try:
                t0 = time.monotonic()
                with anyio.move_on_after(30):
                    while not (acquired := slots.acquire(blocking=False)):
                        await anyio.sleep(0.05)
                if not acquired:
                    return refuse("the server is busy: try again in a minute", {**info, "refused": "busy"})
                started: list[subprocess.Popen] = []
                result: dict[str, Any] = {}
                finished = threading.Event()

                def work() -> None:
                    """The call's work, in its own thread: the slot and the caller's count are given back when it ends."""
                    try:
                        if name in agent:
                            result["value"] = run_command(project, name, argv, timeout, False, started)
                        else:
                            result["value"] = run_op(ops[name], arguments, public)
                    except Exception as exc:  # noqa: BLE001 - handed to the call waiting for it, raised there
                        result["error"] = exc
                    finally:
                        slots.release()
                        caller_done()
                        finished.set()

                # The call's own thread, in a copy of this context: from here the slot and the caller's count are the
                # work's, given back when it ends.
                worker = threading.Thread(target=contextvars.copy_context().run, args=(work,), daemon=True)
                worker.start()
                handed = True
                try:
                    # A cancelled call (notifications/cancelled, or the client gone) stops being waited for, as does one
                    # past --timeout; what has begun in this process runs to its end, holding its slot.
                    with anyio.fail_after(None if name in agent else timeout):
                        while not finished.is_set():
                            await anyio.sleep(0.02)
                    if "error" in result:
                        raise result["error"]
                    if name in agent:
                        code, out, err = result["value"]
                    else:
                        envelope = result["value"]
                except TimeoutError:
                    code, err = 124, f"(stopped waiting after {timeout:g} s)"
                except (
                    Problem
                ) as exc:  # the operation's own refusal: a thing that is not there, an input that is wrong
                    code, err = 1, f"ERROR ({exc.kind}): {exc}"
                except anyio.get_cancelled_exc_class():
                    for p in started:
                        kill_group(p)
                    _log(**{k2: v for k2, v in info.items() if k2 not in PRIVATE}, cancelled=True)
                    raise
                except Exception as exc:  # noqa: BLE001 -- a crash is the server's: told to the hooks, "internal error" to a public caller
                    hooks("error", exc, info)
                    code, err = 70, f"{type(exc).__name__}: {exc}"
            finally:
                if not handed:
                    if acquired:
                        slots.release()
                    caller_done()
            if envelope is not None:
                out = json.dumps(envelope, ensure_ascii=False)
            done = {**info, "exit": code, "ms": round((time.monotonic() - t0) * 1000), "bytes": len(out)}
            # An operation that refuses (exit 1, its ERROR: line: a dataset id that is a path, a goal that does not exist)
            # answered as designed; a crash is the error.
            if code == 1 and "ERROR" in err:
                done["refused"] = "command"
            _log(**{k2: v for k2, v in done.items() if k2 not in PRIVATE})
            hooks("request", done)
        except Exception as exc:
            hooks("error", exc, info)
            raise
        if code != 0:
            text = (err.strip() or out.strip() or f"exit {code}")[-65536:]
            if public:
                text = (
                    public_error(text, project)
                    if code != 70
                    else "internal error: the call failed; it is reported to the server's maintainers"
                )
            return types.CallToolResult(content=[types.TextContent(text=text)], is_error=True)
        if len(out) > MAX_OUT:
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        text=f"the answer is {len(out):,} bytes, over {MAX_OUT:,}: narrow it with the tool's filters"
                    )
                ],
                is_error=True,
            )
        if name in agent:
            try:
                envelope = json.loads(out)
            except ValueError:
                envelope = None
        res = _answer(types, envelope, out)
        if public and name in ops:
            remember(answer_key, res)
        return res

    return Server(
        "evaluation-harness",
        version=__version__,
        instructions="The evaluation harness's reads for this project: its datasets, goals, arms, runs and comparisons. "
        "Each tool is an operation of the harness, named as `evh <operation>` and its API resource; none writes or spends.",
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
    ap.add_argument(
        "--port", type=int, help="--http: the port (default: the project's own, the same every time)"
    )
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
        help="no tool that answers with an item's text, an arm's output or a label, none that reads the project's files, "
        "and no input that would (for a server anyone can reach)",
    )
    ap.add_argument(
        "--timeout", type=float, default=TIMEOUT_S, help=f"seconds per call (default: {TIMEOUT_S})"
    )
    ap.add_argument("--concurrent", type=int, default=4, help="calls answered at once (default: 4)")
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
    ap.add_argument(
        "--write-answers",
        type=Path,
        metavar="FILE",
        help="write ahead the answer of every tool that takes no argument and does not depend on the date, then "
        "exit: for a release that never changes, served with --answers",
    )
    ap.add_argument(
        "--answers",
        type=Path,
        metavar="FILE",
        help="--public: serve the answers --write-answers wrote for this release without computing them "
        "(a line another harness version wrote is not read)",
    )
    args = ap.parse_args(argv)
    use_project(args.project.resolve())
    if args.write_answers:
        return write_answers(args.project.resolve(), args.write_answers, args.public)
    if args.answers and not args.public:
        from evaluation_harness._common import die  # noqa: PLC0415

        die("--answers serves a release that never changes: it needs --public", "not-allowed")
    if args.http and args.port is None:
        from evaluation_harness._common import project_port  # noqa: PLC0415

        args.port = project_port("mcp", args.project)
    import anyio  # noqa: PLC0415

    project = args.project.resolve()
    if args.http and args.bind not in LOOPBACK and not args.allowed_host:
        from evaluation_harness._common import die  # noqa: PLC0415

        die(
            f"--bind {args.bind} reaches beyond this machine: name the Host it answers with --allowed-host "
            "(the server checks it against DNS rebinding)",
            "not-allowed",
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
        answers_file=args.answers,
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
