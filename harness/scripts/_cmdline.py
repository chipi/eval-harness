"""A command's command line, for what still runs a command as a process (RFC-032 step 9): the jobs (`_api`) and the agent
sampler's two MCP tools (`study-ask`, `study-tell`). Reads are not here: each is an operation (ops/), answered in the
server's own process. Its parser read without running it, its arguments as the line a person would type, the command run in
its own process group with a timeout that kills the group (P3 makes the jobs operations, and this goes)."""

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import contextlib
import os
import re
import runpy
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

#: The commands that print JSON a caller reads: the agent sampler's.
JSON = {"study-ask", "study-tell"}
#: Left out of every schema: the server uses the project's own adapter (an agent must not load an
#: arbitrary file), and sets --json itself.
HIDDEN = {"--adapter", "--json", "--help"}
TIMEOUT_S = 300
#: A tool argument's bounds: no command takes a longer value (an id, a period, a search's words),
#: and a megabyte of argument only reached the kernel's limit and an error naming the interpreter.
MAX_VALUE = 512
MAX_VALUES = 64


class _Parser(Exception):
    def __init__(self, parser: argparse.ArgumentParser):
        self.parser = parser


def parser_of(command: str) -> argparse.ArgumentParser:
    """The command's argparse parser, read without running it: its script runs until it parses
    its arguments, and the parser is handed back there. A command made from an operation (RFC-032) has its parser
    made from the operation."""
    from evaluation_harness import ops  # noqa: PLC0415
    from evaluation_harness.cli import COMMANDS  # noqa: PLC0415
    from evaluation_harness.ops import cli as ops_cli  # noqa: PLC0415

    if (op := ops.get(command)) is not None:
        return ops_cli.parser(op)

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


#: The environment variables that name a path from where a command stands (EVAL_DATA_DIR is relative to
#: the project root, _common._paths, so it stays as it is).
PATH_VARS = ("EVAL_HOME", "EVH_P_CACHE")


def run_command(
    project: Path,
    command: str,
    argv: list[str],
    timeout: float = TIMEOUT_S,
    public: bool = False,
    started: list[subprocess.Popen] | None = None,
) -> tuple[int, str, str]:
    """`evh <command> <argv>` in the project, in its own process group, stdin closed, with a timeout
    that kills the group. `public`: the command runs as a public server's would (EVH_PUBLIC), so it
    sees only the fields marked public. `started` receives the process, for a caller that may have
    to stop it (a cancelled call, kill_group)."""
    cmd = [sys.executable, str(HERE / "cli.py"), command, *(["--json"] if command in JSON else []), *argv]
    # The goals' tests are the slow part of a view (~50 s for this repository's runs); each call is a
    # fresh process, so they are kept on disk (stats.EVH_P_CACHE), in the project's ignored .cache/
    # unless the deployment names its own precomputed file.
    env = dict(os.environ)
    # The command runs in the project, so a relative path the caller set is made absolute from where the
    # caller stands: render.sh ran `EVAL_HOME=_release/inspector`, the commands resolved it inside the project
    # and read an empty one, and every answer written ahead for 0.6.2 to 0.7.1 said there were no goals.
    for k in PATH_VARS:
        if env.get(k) and not os.path.isabs(env[k]):
            env[k] = os.path.abspath(env[k])
    from evaluation_harness._common import p_cache_path  # noqa: PLC0415

    env.setdefault("EVH_P_CACHE", p_cache_path(project))
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
    if started is not None:
        started.append(p)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(p)
        out, err = p.communicate()
        return 124, out, err + f"\n(stopped after {timeout:g} s)"
    return p.returncode, out, err


def kill_group(p: subprocess.Popen) -> None:
    """Stop a command and everything it started (its own process group); one already gone is fine."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(p.pid, signal.SIGKILL)


#: Options no tool offers: they name a path of the server's, and a tool names none.
TOOL_HIDDEN = {
    "study-tell": {"--proposal"},  # a path of the server's: a call sends --proposal-json
}
