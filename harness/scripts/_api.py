"""The API's registry (RFC-026): every command it serves, made from the command's own argument parser.

A command is served as a `read` (the MCP server's read tools: answered at once) or a `job` (everything else that
works on the project: a detached process, RFC-026 step 3), or not at all (the servers, the commands that set up a
project or check the installation, `capture-scrub`, which runs a program it is given). Every argument the registry
keeps has a kind:

  value      typed as the parser types it (choices, numbers, true/false)
  name       a thing that must exist: a config id (the server maps it to the config's file), a dataset, a goal
  upload     a file the call carries (at most 50 MB), kept under .build/uploads/<sha256> for the job
  artifact   a file the job writes under .build/jobs/<id>/, fetched from there

and an argument with none (a path the command would read or write on the server: `--runs-dir`, `--source-dir`,
`--out` folders) is never taken. A path-typed argument the table below does not name fails a test, so a command that
gains one cannot be served by accident.
"""

from __future__ import annotations

import argparse
import functools
from pathlib import Path
from typing import Any

from evaluation_harness import _common

#: Not served, and why (a test fails on a command in neither this nor the registry).
NOT_SERVED = {
    "catalog-serve": "it is the server",
    "mcp": "the agents' server",
    "init": "makes a project; the Workbench opens one",
    "skills-install": "writes the agents' skills into a project",
    "env-check": "the server's own environment",
    "self-test": "checks the installed package",
    "capture-scrub": "runs a program it is given",
}
#: The commands that call models and spend: a job of one must carry max_cost_usd (step 5).
SPENDS = {"run", "sweep", "arm-smoke", "judge", "judge-score", "model-onboard"}
#: Every path-typed argument a served command has, and its kind. Absent from this table: never taken.
NAME = "name"
UPLOAD = "upload"
ARTIFACT = "artifact"
PATH_KINDS: dict[tuple[str, str], str] = {
    ("run", "--config"): NAME,
    ("arm-smoke", "--config"): NAME,
    ("model-onboard", "--config"): NAME,
    ("sweep", "--configs"): NAME,
    ("dataset-create", "--fields"): UPLOAD,
    ("dataset-create", "--manifest"): UPLOAD,
    ("dataset-describe", "--card"): UPLOAD,
    ("import-run", "--scores"): UPLOAD,
    ("import-run", "--scorer-file"): UPLOAD,
    ("label-coverage", "--map"): UPLOAD,
    ("label-from-capture", "--map"): UPLOAD,
    ("label-from-run", "--guideline"): UPLOAD,
    ("label-import", "sheet"): UPLOAD,
    ("label-import", "--guideline"): UPLOAD,
    ("sheet-import", "sheet"): UPLOAD,
    ("sheet-import", "--key"): UPLOAD,
    ("sheet-import", "--guideline"): UPLOAD,
    ("label-sheet", "--out"): ARTIFACT,
    ("dataset-card", "--out"): ARTIFACT,
}
#: Path-typed arguments never taken, each a decision (RFC-026 revision 2): another runs folder or output folder,
#: a file of the server's, a page's own assets. A path-typed argument in neither table fails a test.
NEVER_PATHS = {
    ("arm-from-capture", "--like"),
    ("bootstrap-test", "--items"),
    ("pair-test", "--items"),
    ("family-test", "--items"),
    ("catalog", "--out"),
    ("catalog", "--head"),
    ("catalog", "--about"),
    ("inspect", "--csv"),
    ("inspect", "--rubric"),
    ("judge-score", "--out"),
    ("rescore", "--out"),
}
#: Paths the parser types as text, never taken either.
TEXT_PATHS = {("round-retire", "--runs-dir"), ("judge", "--config")}
#: Options never taken from any command: they load code or reach outside the project.
NEVER = {"--adapter", "--help", "--json", "--runs-dir", "--source-dir", "--data-dir", "--config-dir"}


def _name(a: argparse.Action) -> str:
    longest = max(a.option_strings, key=len) if a.option_strings else a.dest
    return longest.lstrip("-")


def _key(a: argparse.Action) -> str:
    """The argument as PATH_KINDS names it: its longest option string, or a positional's dest."""
    return max(a.option_strings, key=len) if a.option_strings else a.dest


def _is_path(a: argparse.Action) -> bool:
    return a.type is Path


def served_as(command: str) -> str | None:
    """`read`, `job`, or None (not served)."""
    from evaluation_harness.mcp_server import READ_TOOLS  # noqa: PLC0415

    if command in NOT_SERVED:
        return None
    return "read" if command in READ_TOOLS else "job"


def kind_of(command: str, a: argparse.Action) -> str | None:
    """An argument's kind, or None when the API never takes it."""
    from evaluation_harness.mcp_server import TOOL_HIDDEN  # noqa: PLC0415

    key = _key(a)
    if set(a.option_strings) & NEVER or key in TOOL_HIDDEN.get(command, set()):
        return None
    if (command, key) in TEXT_PATHS:
        return None
    if _is_path(a):
        return PATH_KINDS.get((command, key))
    return "value"


def _argument(command: str, a: argparse.Action, kind: str) -> dict[str, Any]:
    flag = isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction))
    t = "boolean" if flag else {int: "integer", float: "number"}.get(a.type, "string")  # type: ignore[call-overload]
    help_ = a.help if a.help and a.help != argparse.SUPPRESS else ""
    if "%(default)" in help_:
        help_ = help_ % {"default": a.default}
    return {
        "name": _name(a),
        "kind": kind,
        "type": t,
        "many": a.nargs in ("*", "+") or isinstance(a, argparse._AppendAction),
        "choices": list(a.choices) if a.choices else None,
        "default": a.default if isinstance(a.default, (str, int, float, bool, type(None))) else None,
        "required": bool(a.required or not a.option_strings),
        "help": help_,
    }


@functools.lru_cache(maxsize=1)
def registry() -> dict[str, dict[str, Any]]:
    """{command: {"served": "read"|"job", "spends", "about", "arguments": [...]}} for every served command."""
    from evaluation_harness.cli import COMMANDS  # noqa: PLC0415
    from evaluation_harness.mcp_server import parser_of  # noqa: PLC0415

    out: dict[str, dict[str, Any]] = {}
    for c in sorted(COMMANDS):
        how = served_as(c)
        if how is None:
            continue
        parser = parser_of(c)
        args = [
            _argument(c, a, k)
            for a in parser._actions
            if not isinstance(a, argparse._HelpAction) and (k := kind_of(c, a)) is not None
        ]
        out[c] = {"served": how, "spends": c in SPENDS, "about": COMMANDS[c][1], "arguments": args}
    return out


def unkinded_paths() -> list[str]:
    """Every path-typed argument of a served command that the API would take but no kind names: empty, or a
    test fails (a command that gains a path argument is not served by accident)."""
    from evaluation_harness.cli import COMMANDS  # noqa: PLC0415
    from evaluation_harness.mcp_server import parser_of  # noqa: PLC0415

    out = []
    for c in sorted(COMMANDS):
        if served_as(c) is None:
            continue
        for a in parser_of(c)._actions:
            key = (c, _key(a))
            if (
                _is_path(a)
                and not (set(a.option_strings) & NEVER)
                and key not in PATH_KINDS
                and key not in NEVER_PATHS
            ):
                out.append(f"{c} {_key(a)}")
    return out


class Refused(ValueError):
    """A call refused before anything runs: its message, and the HTTP status it answers."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def checked_args(command: str, arguments: Any) -> dict[str, Any]:
    """The call's arguments, checked against the registry (names, kinds, types, choices, required) and with each
    `name` mapped to what the command takes (a config id to its file). Refused before anything runs."""
    reg = registry().get(command)
    if reg is None:
        raise Refused(f"{command}: not a command the API serves", 404)
    if not isinstance(arguments, dict):
        raise Refused("args: a JSON object keyed by the argument's name")
    by = {a["name"]: a for a in reg["arguments"]}
    unknown = sorted(set(arguments) - set(by))
    if unknown:
        raise Refused(f"{command}: not an argument the API takes: {', '.join(unknown)}")
    out: dict[str, Any] = {}
    for k, v in arguments.items():
        a = by[k]
        if a["kind"] in (UPLOAD, ARTIFACT):
            raise Refused(f"{command} {k}: a file ({a['kind']}); a job takes it (POST /api/v1/jobs)")
        vals = v if isinstance(v, list) else [v]
        if isinstance(v, list) and not a["many"]:
            raise Refused(f"{command} {k}: one value, not a list")
        if a["choices"] and any(str(x) not in map(str, a["choices"]) for x in vals):
            raise Refused(f"{command} {k}: one of {', '.join(map(str, a['choices']))}")
        if a["kind"] == NAME:
            vals = [_config_file(str(x)) for x in vals]
            v = vals if isinstance(v, list) else vals[0]
        out[k] = v
    return out


def _config_file(config_id: str) -> str:
    """A config id as the command takes it: its file, relative to the project (refused when no config has it)."""
    from evaluation_harness._hypothesis import config_ids  # noqa: PLC0415

    f = config_ids().get(config_id)
    if f is None:
        raise Refused(f"no arm config with config_id {config_id!r}", 404)
    try:
        return Path(f).resolve().relative_to(_common.project_root().resolve()).as_posix()
    except ValueError:
        return str(f)


def token_path() -> Path:
    """Where the server writes its token: the project's .build/, readable by its owner only."""
    return _common.project_root() / ".build" / "api-token"


def new_token() -> str:
    """A new random token, written to token_path() with mode 600."""
    import os  # noqa: PLC0415
    import secrets  # noqa: PLC0415

    tok = secrets.token_urlsafe(32)
    p = token_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(tok + "\n")
    os.chmod(p, 0o600)  # the server's, never project data: on disk, not through the store
    return tok
