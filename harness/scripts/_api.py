"""The API's jobs (RFC-026, RFC-032 P3): a job runs a decision or a work operation, named with its inputs, as a detached
process. Each input is checked against the operation's schema before a job exists, and a file is one of two kinds:

  upload     a file the call carries (at most 50 MB), kept under .build/uploads/<sha256> for the job
  artifact   a file the job writes under .build/jobs/<id>/, fetched from there

A path of the server's is never an input (an operation names such an input `tool_hidden`: only the command line takes it),
and the path a query names (`{"path": ...}`, read by an importer or a source, or a publisher's folder) is refused when it
is outside the project.
The commands that are not operations (the servers, the setup commands, the terminal's jobs) are not served, each with why.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation_harness import _common

#: The commands that are not operations, none served, and why (a test fails on a command in neither this nor the
#: operations).
NOT_SERVED = {
    "catalog-serve": "it is the server",
    "mcp": "the agents' server",
    "init": "makes a project; the Workbench opens one",
    "skills-install": "writes the agents' skills into a project",
    "env-check": "the server's own environment",
    "self-test": "checks the installed package",
    "capture-scrub": "runs a program it is given",
    "openapi": "the API's own description: GET /api/v1/openapi.json",
    **dict.fromkeys(
        ("jobs-start", "jobs-status", "jobs-logs", "jobs-stop", "jobs-resume"),
        "the terminal's jobs; the API has its own job routes",
    ),
}
MAX_UPLOAD = 50 * 1024 * 1024  # owner, 2026-11-08


class Refused(ValueError):
    """A call refused before anything runs: its message, and the HTTP status it answers."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _systems_exist(ids: list[str]) -> None:
    """Each id names a system of the project, else refused (404) before a job is made."""
    from evaluation_harness._hypothesis import system_ids  # noqa: PLC0415

    known = system_ids()
    missing = [i for i in ids if i not in known]
    if missing:
        raise Refused(f"no system {', '.join(repr(i) for i in missing)} (evh system-list)", 404)


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


# ── jobs (RFC-026 step 3, RFC-032 P3) ───────────────────────────────────────────────────────────────────────────────


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


def _who_env(by: Any, for_: Any) -> dict[str, str]:
    """The environment a job gets for who acted (RFC-027): an agent (`by: agent:NAME`) names the person it acts for
    (`for: person:NAME`), refused here without it, where the job's command would fail only when it first records who
    acted (a run: after its last item)."""
    if by is not None and not isinstance(by, str):
        raise Refused("by: person:NAME, or agent:NAME with for (RFC-027)")
    env: dict[str, str] = {}
    agent = isinstance(by, str) and by.startswith("agent:")
    if for_ is not None and (not isinstance(for_, str) or not for_.strip()):
        raise Refused("for: person:NAME, the person an agent acts for")
    if agent and not for_:
        raise Refused(f"{by} is an agent: name the person it acts for (for: person:NAME, RFC-027)")
    if for_ and not agent:
        raise Refused("for names the person an agent acts for; by is not an agent")
    if agent:
        whom = str(for_).strip()
        env["EVH_FOR"] = whom if whom.startswith("person:") else f"person:{whom}"
    return env


def _spend_env(name: str, max_cost_usd: Any) -> dict[str, str]:
    if not isinstance(max_cost_usd, (int, float)) or isinstance(max_cost_usd, bool) or max_cost_usd <= 0:
        raise Refused(
            f"{name} spends: a job of it carries max_cost_usd, the most it may spend, above 0 (the cap is checked before"
            " each call, so 0 would stop even an arm that costs nothing; such an arm spends nothing under any cap,"
            " e.g. 0.01)"
        )
    return {"EVAL_MAX_COST_USD": str(max_cost_usd)}


def job_operation(name: str) -> Any:
    """The decision or work operation a job of `name` runs; refused (404) when no such operation is, or when it is a
    read or an edit, which answers in its own resource."""
    from evaluation_harness import ops  # noqa: PLC0415

    op = ops.get(name)
    if op is None:
        raise Refused(f"{name}: not an operation that runs as a job", 404)
    if not op.is_job():
        raise Refused(f"{name}: not a job: a {op.kind}, answered at {op.method} /api/v1{op.route}", 404)
    return op


def id_problem(value: str) -> str:
    """Why a value a call gives as an id (a route's part, or the input it fills) is no id, or "": an absolute path, a
    `..` segment, a backslash or a NUL would name a file outside the folder the id is looked up in. A `/` inside is an
    id's own (a label `judged/<scorer>`, a study `<goal>/<id>`)."""
    if "\0" in value or "\\" in value:
        return "an id holds no NUL and no backslash"
    if value.startswith("/") or ".." in value.split("/"):
        return "an id is not a path (no leading /, no ..)"
    return ""


def operation_inputs(op: Any, inputs: Any, job_id: str) -> dict[str, Any]:
    """A job's inputs, checked against the operation's schema (names, types, required, `pattern`, `enum`), each system
    it names found, a file kept (an upload under .build/uploads, an artifact placed in the job's folder), and every default
    filled: what the job's record holds and its command reads. Refused before anything runs."""
    import jsonschema  # noqa: PLC0415
    from evaluation_harness import _jobs  # noqa: PLC0415
    from evaluation_harness.ops import registry  # noqa: PLC0415

    if not isinstance(inputs, dict):
        raise Refused("inputs: a JSON object keyed by the input's name")
    try:
        jsonschema.validate(inputs, op.job_schema())
    except jsonschema.ValidationError as exc:
        raise Refused(f"{op.name}: {registry.input_problem(exc)}") from exc
    named = {(op.parts or {}).get(p, p) for p in op.path_params()}
    for name in sorted(named | {n for n, s in op.inputs.items() if s.get("x-ref")}):
        given = inputs.get(name)
        for v in given if isinstance(given, list) else [given]:
            if isinstance(v, str) and id_problem(v):
                raise Refused(f"{op.name}: {name} {v!r}: {id_problem(v)}")
    out = op.with_defaults(inputs)
    budget = [0]
    for name, spec in op.inputs.items():
        if name not in out:
            continue
        if spec.get("x-ref") == "system":
            _systems_exist([str(x) for x in (out[name] if isinstance(out[name], list) else [out[name]])])
        if spec.get("x-file") == "upload":
            out[name] = (
                [_upload(x, budget) for x in out[name]]
                if spec.get("type") == "array"
                else _upload(out[name], budget)
            )
        elif spec.get("x-file") == "artifact":
            out[name] = str(
                (_jobs.job_dir(job_id) / _safe_name(str(out[name]))).relative_to(_common.project_root())
            )
    for p in _query_paths(out.get("query")) if "query" in op.inputs else ():
        root = _common.project_root().resolve()
        if not (root / p).resolve().is_relative_to(root):
            raise Refused(
                f"{op.name}: the query's path {p!r} is outside the project; a job reads only the project's files "
                "(no input is a free path): copy the file into the project and name it from there"
            )
    return out


def _query_paths(query: Any) -> list[str]:
    """The paths a query names for its importer, source or publisher to read or write (`path`): from its JSON text, or
    from capture-restore's KEY=VALUE overrides. A query that is not JSON is the operation's own to refuse."""
    import json  # noqa: PLC0415

    found: list[Any] = []
    if isinstance(query, str):
        try:
            doc = json.loads(query)
        except ValueError:
            return []
        if isinstance(doc, dict):
            found.append(doc.get("path"))
    elif isinstance(query, list):
        for pair in query:
            key, sep, raw = str(pair).partition("=")
            if sep and key.strip() == "path":
                try:
                    found.append(json.loads(raw))
                except ValueError:
                    found.append(raw)
    return [str(p) for p in found if p not in (None, "")]


def start_operation(
    op: Any, inputs: Any, by: Any, max_cost_usd: Any = None, for_: Any = None, origin: str = "api"
) -> dict[str, Any]:
    """A job of a decision or a work operation: who asked (`by`, required: every job records who acted), the cap when it
    spends, the inputs checked, its locks, started (202). A decision's reason is one of its inputs (`Op.why`)."""
    from evaluation_harness import _jobs  # noqa: PLC0415
    from evaluation_harness.ops import locks as op_locks  # noqa: PLC0415

    if not isinstance(by, str) or not by.strip():
        raise Refused(f"{op.name}: name who asked (by: person:NAME, or agent:NAME with for; RFC-027)")
    env = _who_env(by, for_)
    env["EVH_ACTOR_FROM"] = (
        origin  # where `by` came from: the actor of the records the job writes says so (RFC-027)
    )
    if op.spends:
        env.update(_spend_env(op.name, max_cost_usd))
    elif max_cost_usd is not None:
        raise Refused(f"{op.name} does not spend: it takes no max_cost_usd")
    job_id = _jobs.new_id()
    checked = operation_inputs(op, inputs, job_id)
    run_id = None
    if op.resume:
        run_input = op.resume[1]
        if run_input not in checked:
            # The job's id: unique, where a second's timestamp is not (two runs started at once).
            checked[run_input] = f"{checked.get('system') or 'run'}_{job_id}"
        run_id = str(checked[run_input])
    _jobs.create(op.name, checked, by.strip(), op_locks.locks_for(op, checked), env, run_id, job_id)
    _jobs.start(job_id)
    return _jobs.read(job_id)


def resume_job(job_id: str) -> dict[str, Any]:
    """POST /api/v1/jobs/<id>/resume: a stopped or lost run, continued by a new job (`run --resume <its run id>`), with
    what the stopped job left of its cap (a call in flight when it was killed is not counted: its cost was never
    reported)."""
    from evaluation_harness import _jobs, ops  # noqa: PLC0415

    j = _jobs.read(job_id)
    op = ops.get(j["operation"])
    if op is None or not op.resume or not j.get("run_id"):
        raise Refused(f"only a run is resumed; {job_id} is {j['operation']}", 409)
    inputs = dict(j["inputs"])
    if inputs.get("repeat") not in (None, 1):
        raise Refused("a run with repeat above 1 is not resumed (run refuses it)", 409)
    if j["state"] in ("queued", "running", "running (unsupervised)", "succeeded"):
        raise Refused(f"{job_id} is {j['state']}: nothing to resume", 409)
    from evaluation_harness import _outputs  # noqa: PLC0415

    if not _outputs.own(_common.RUNS / j["run_id"]):  # run --resume would start, then refuse the same
        raise Refused(
            f"{job_id} stopped before its run wrote anything: nothing to resume (start the run again)", 409
        )
    # The cap is the job's, not each attempt's: the new job is given what this one left.
    env = dict(j.get("env") or {})
    if env.get("EVAL_MAX_COST_USD") is not None:
        given, paid = float(env["EVAL_MAX_COST_USD"]), _jobs.spent(job_id)
        if given - paid <= 0:
            raise Refused(
                f"{job_id} spent ${paid:.4f} of its ${given:.4f}: nothing is left to resume with "
                "(start a new job with a cap of its own)",
                409,
            )
        env["EVAL_MAX_COST_USD"] = f"{given - paid:.8f}"
    new_id = _jobs.new_id()
    resume_input, run_input = op.resume
    new_run = f"{inputs.get('system') or 'run'}_{new_id}"
    inputs |= {resume_input: j["run_id"], run_input: new_run}
    inputs.pop(
        "recall_failed", None
    )  # the items it recalled were called by that job: a person names them again
    _jobs.create(op.name, inputs, j.get("by"), [(k, bool(x)) for k, x in j["locks"]], env, new_run, new_id)
    _jobs.start(new_id)
    return _jobs.read(new_id)
