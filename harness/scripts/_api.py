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
    **dict.fromkeys(
        ("jobs-start", "jobs-status", "jobs-logs", "jobs-stop", "jobs-resume"),
        "the terminal's jobs; the API has its own job routes",
    ),
}
#: The commands that call models and spend: a job of one must carry max_cost_usd (step 5).
SPENDS = {
    "run",
    "sweep",
    "arm-smoke",
    "judge",
    "judge-score",
    "model-onboard",
    "study-run",
    "study-tell",
    "study-confirm",
    "faithfulness",
}
#: Every path-typed argument a served command has, and its kind. Absent from this table: never taken.
NAME = "name"
UPLOAD = "upload"
ARTIFACT = "artifact"
PATH_KINDS: dict[tuple[str, str], str] = {
    ("run", "--config"): NAME,
    ("faithfulness", "--config"): NAME,
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
    ("prompt-version", "--from-file"): UPLOAD,
    ("study-run", "--spec"): UPLOAD,
    ("run", "--items"): UPLOAD,
    ("study-tell", "--proposal"): UPLOAD,
    ("study-import", "file"): UPLOAD,
    ("prompt-export", "--to"): ARTIFACT,
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
    # Written beside and renamed into place: a reader sees the old token or the new one, never an empty file (a
    # truncate and then a write left a moment between).
    tmp = p.with_name(f".{p.name}.{os.getpid()}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(tok + "\n")
    os.chmod(tmp, 0o600)  # the server's, never project data: on disk, not through the store
    os.replace(tmp, p)
    return tok


# ── jobs (RFC-026 step 3) ──────────────────────────────────────────────────────────────────────────────────────────

#: The decisions (RFC-027): a job of one needs `by`, refused at the call before a job exists.
DECISIONS = {
    "run-promote",
    "baseline-rollback",
    "round-close",
    "dataset-unseal",
    "study-confirm",
    "faithfulness-name",
}
MAX_UPLOAD = 50 * 1024 * 1024  # owner, 2026-11-08
#: Where `by` and the reason go on the command line, for the commands that take them as who acted and why.
BY_FLAG = {"label-import", "sheet-import", "pick", "reference-manifest", "reference-promote"}
REASON_FLAG = {
    "run-promote": "reason",
    "reference-promote": "reason",
    "reference-manifest": "reason",
    "round-retire": "reason",
    "dataset-unseal": "reason",
    "baseline-rollback": "reason",
    "round-close": "conclusion",
}


def _safe_name(name: str) -> str:
    import re  # noqa: PLC0415

    base = Path(str(name)).name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}", base):
        raise Refused(f"a file name of letters, digits, '.', '_' or '-', not {name!r}")
    return base


def _upload(value: Any, budget: list[int]) -> str:
    """An uploaded file, {"name", "content_base64"}, kept under .build/uploads/<sha256>/<name>: its path for the job."""
    import base64  # noqa: PLC0415
    import binascii  # noqa: PLC0415
    import hashlib  # noqa: PLC0415

    if not isinstance(value, dict) or set(value) != {"name", "content_base64"}:
        raise Refused('an upload is {"name": "<file name>", "content_base64": "<the bytes, base64>"}')
    try:
        data = base64.b64decode(value["content_base64"], validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise Refused("content_base64: not base64") from exc
    budget[0] += len(data)
    if budget[0] > MAX_UPLOAD:
        raise Refused(f"a call carries at most {MAX_UPLOAD // (1024 * 1024)} MB", 413)
    name = _safe_name(value["name"])
    d = _common.project_root() / ".build" / "uploads" / hashlib.sha256(data).hexdigest()
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(data)
    return str((d / name).relative_to(_common.project_root()))


def job_argv(command: str, arguments: Any, job_id: str) -> tuple[list[str], dict[str, Any]]:
    """A job call's argv, its arguments checked against the registry (a name mapped, an upload kept, an artifact
    placed in the job's folder), and the checked arguments by name (what the locks read)."""
    from evaluation_harness import _jobs  # noqa: PLC0415
    from evaluation_harness import mcp_server as ms  # noqa: PLC0415

    reg = registry().get(command)
    if reg is None:
        raise Refused(f"{command}: not a command the API serves", 404)
    if reg["served"] != "job":
        raise Refused(f"{command}: a read (POST /api/v1/read/{command}), not a job")
    if not isinstance(arguments, dict):
        raise Refused("args: a JSON object keyed by the argument's name")
    files = {a["name"]: a["kind"] for a in reg["arguments"] if a["kind"] in (UPLOAD, ARTIFACT)}
    budget = [0]
    plain = {k: v for k, v in arguments.items() if k not in files}
    checked = checked_args(command, plain)
    for k, v in arguments.items():
        if k not in files:
            continue
        if files[k] == UPLOAD:
            checked[k] = _upload(v, budget)
        else:
            checked[k] = str((_jobs.job_dir(job_id) / _safe_name(str(v))).relative_to(_common.project_root()))
    try:
        return ms.argv_of(ms.parser_of(command), checked), checked
    except ValueError as exc:
        raise Refused(str(exc)) from exc


def start_job(command: str, arguments: Any, by: Any, reason: Any, max_cost_usd: Any = None) -> dict[str, Any]:
    """POST /api/v1/jobs: checked, written, and started (202). Refused before a job exists when it cannot run."""
    from evaluation_harness import _jobs  # noqa: PLC0415

    if by is not None and not isinstance(by, str):
        raise Refused("by: person:NAME, or agent:NAME with for (RFC-027)")
    if command in DECISIONS and not by:
        raise Refused(f"{command} is a decision: name who made it (by: person:NAME)")
    env: dict[str, str] = {}
    if command in SPENDS:
        if not isinstance(max_cost_usd, (int, float)) or isinstance(max_cost_usd, bool) or max_cost_usd <= 0:
            raise Refused(f"{command} spends: a job of it carries max_cost_usd, the most it may spend")
        env["EVAL_MAX_COST_USD"] = str(max_cost_usd)
    job_id = _jobs.new_id()
    argv, checked = job_argv(command, arguments, job_id)
    if by and command in BY_FLAG and "by" not in checked:
        argv = ["--by", str(by), *argv]
    if reason and command in REASON_FLAG and REASON_FLAG[command] not in checked:
        argv = [f"--{REASON_FLAG[command]}", str(reason), *argv]
    run_id = None
    if command == "run" and "run-id" not in checked:
        cid = _jobs._config(str(checked.get("config"))).get("config_id") or "run"
        run_id = f"{cid}_{job_id}"  # the job's id: unique, where a second's timestamp is not (two runs started at once)
        argv = ["--run-id", run_id, *argv]
    elif command == "run":
        run_id = str(checked["run-id"])
    _jobs.create(command, argv, by, reason, _jobs.locks_for(command, checked), env, run_id, job_id=job_id)
    _jobs.start(job_id)
    return _jobs.read(job_id)


def resume_job(job_id: str) -> dict[str, Any]:
    """POST /api/v1/jobs/<id>/resume: a stopped or lost run, continued by a new job (`run --resume <its run id>`)."""
    from evaluation_harness import _jobs  # noqa: PLC0415

    j = _jobs.read(job_id)
    if j["command"] != "run" or not j.get("run_id"):
        raise Refused(f"only a run is resumed; {job_id} is {j['command']}", 409)
    argv = list(j["argv"])
    if "--repeat" in argv and argv[argv.index("--repeat") + 1] not in ("1",):
        raise Refused("a run with --repeat above 1 is not resumed (run refuses it)", 409)
    if j["state"] in ("queued", "running", "running (unsupervised)", "succeeded"):
        raise Refused(f"{job_id} is {j['state']}: nothing to resume", 409)
    if "--run-id" in argv:
        i = argv.index("--run-id")
        del argv[i : i + 2]
    new_id = _jobs.new_id()
    cid = (
        _jobs._config(argv[argv.index("--config") + 1] if "--config" in argv else None).get("config_id")
        or "run"
    )
    new_run = f"{cid}_{new_id}"
    argv = ["--run-id", new_run, "--resume", j["run_id"], *argv]
    _jobs.create(
        "run",
        argv,
        j.get("by"),
        j.get("reason"),
        [(k, bool(x)) for k, x in j["locks"]],
        j.get("env"),
        new_run,
        job_id=new_id,
    )
    _jobs.start(new_id)
    return _jobs.read(new_id)
