"""The jobs from the terminal (RFC-026 step 6): the same jobs the API starts, in the project's .build/jobs/.

    evh jobs-start OPERATION [--arg NAME=VALUE ...] [--max-cost-usd N] [--by WHO]
    evh jobs-status [JOB_ID] [--state STATE] [--json]
    evh jobs-logs JOB_ID [--follow] [--from BYTE]
    evh jobs-stop JOB_ID
    evh jobs-resume JOB_ID

`--arg` names an input as the API does: the operation's input name (`evh OPERATION --help` shows it as the option, its
dashes underscores: `--dataset-id` is `dataset_id`); a system by its id, `--arg repeat=3`, a flag as `--arg NAME=true`;
repeated, it makes a list; `@FILE` uploads a file. A decision's reason is one of its inputs. A job started here is listed
by the API and stopped by it, and one the Workbench started is followed here. No server is needed.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any

from evaluation_harness import _jsonout, _store
from evaluation_harness._common import die, evh_prog

TERMINAL = ("succeeded", "failed", "cancelled", "lost")


def _value(raw: str) -> Any:
    """A value as JSON when it reads as JSON (3, true, 0.5), else the text; `@FILE` is the file, uploaded."""
    if raw.startswith("@"):
        p = Path(raw[1:])
        if not _store.is_file(p):
            die(f"--arg ...=@{p}: no such file", "not-found")
        return {"name": p.name, "content_base64": base64.b64encode(_store.read_bytes(p)).decode()}
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def args_of(pairs: list[str]) -> dict[str, Any]:
    """`--arg NAME=VALUE` pairs as the API's inputs: a name given twice is a list."""
    out: dict[str, Any] = {}
    for pair in pairs:
        name, sep, raw = pair.partition("=")
        if not sep or not name:
            die(
                f"--arg {pair!r}: expected NAME=VALUE (the input as `evh OPERATION --help` shows it, its dashes "
                "underscores)",
                "bad-argument",
            )
        v = _value(raw)
        if name in out:
            out[name] = [*(out[name] if isinstance(out[name], list) else [out[name]]), v]
        else:
            out[name] = v
    return out


def _who() -> str:
    """Who asks for the job: --by (which sets EVH_ACTOR), else this process's actor (RFC-027)."""
    from evaluation_harness import _actor  # noqa: PLC0415

    a = _actor.actor()
    return f"{a['type']}:{a['name']}" if a["type"] != "unknown" else ""


def _for() -> str:
    """The person an agent acts for (EVH_FOR, RFC-027), as this process's actor carries it; "" for a person."""
    from evaluation_harness import _actor  # noqa: PLC0415

    whom = _actor.actor().get("for")
    return f"person:{whom}" if whom else ""


def _refused(exc: Exception) -> None:
    """An API refusal as the command line's: its status as the refusal kind."""
    status = getattr(exc, "status", 400)
    if status == 404:
        die(str(exc), "not-found")
    if status == 409:
        die(str(exc), "not-allowed")
    die(str(exc), "bad-argument")


def _line(j: dict[str, Any]) -> str:
    wait = j.get("waiting_for") or {}
    extra = f"  waiting for {wait.get('lock')} ({wait.get('job') or 'another process'})" if wait else ""
    if j.get("refusal"):
        extra += f"  refused: {j['refusal']}"

    return f"{j['id']}  {j.get('state_label') or j['state']:<22} {j['operation']:<18} by {j.get('by') or '-'}{extra}"


def start(argv: list[str]) -> int:
    """evh jobs-start: an operation started as a job, checked as the API checks it."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description="start an operation as a job (RFC-026)")
    ap.add_argument(
        "operation",
        help="the operation, as `evh --help` names it (a decision or a work operation, not a read)",
    )
    ap.add_argument("--arg", action="append", default=[], metavar="NAME=VALUE", help="an input (repeatable)")
    ap.add_argument("--max-cost-usd", type=float, help="an operation that spends: the most the job may spend")
    ap.add_argument("--json", action="store_true", help="the job's record as JSON")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    a = ap.parse_args(argv)
    from evaluation_harness import _actor, _api  # noqa: PLC0415

    with _jsonout.collect("jobs-start", a.json):
        try:
            op = _api.job_operation(a.operation)
            inputs = args_of(a.arg)
            # `--arg item=i1` given once is still a list for an input that takes one (the API's caller sends [..]).
            for name, value in inputs.items():
                if (op.inputs.get(name) or {}).get("type") == "array" and not isinstance(value, list):
                    inputs[name] = [value]
            j = _api.start_operation(
                op, inputs, _who() or None, a.max_cost_usd, _for() or None, origin=_actor.actor()["from"]
            )
        except _api.Refused as exc:
            _refused(exc)
        print(_line(j))
        print(f"follow it: evh jobs-logs {j['id']} --follow")
        _jsonout.value("job", j)
    return 0


def status(argv: list[str]) -> int:
    """evh jobs-status: every job, newest first, or one."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description="the jobs, or one job (RFC-026)")
    ap.add_argument("job_id", nargs="?", help="one job (default: every job, newest first)")
    ap.add_argument(
        "--state",
        action="append",
        help="only jobs in this state (repeatable, or comma-separated): queued, running, running (unsupervised), lost, "
        "succeeded, failed, cancelled",
    )
    ap.add_argument("--operation", help="only the jobs of this operation")
    ap.add_argument("--goal", help="only the jobs whose inputs name this goal")
    ap.add_argument("--json", action="store_true", help="the jobs' records as JSON")
    a = ap.parse_args(argv)
    from evaluation_harness import _jobs  # noqa: PLC0415

    with _jsonout.collect("jobs-status", a.json):
        if a.job_id:
            try:
                j = _jobs.read(a.job_id)
            except (FileNotFoundError, ValueError):
                die(f"no job {a.job_id!r} in {_jobs.jobs_dir()}", "not-found")
            print(_line(j))
            for k in ("inputs", "created_at", "started_at", "ended_at", "exit", "run_id"):
                if j.get(k) not in (None, "", [], {}):
                    shown = json.dumps(j[k]) if k == "inputs" else j[k]
                    print(f"  {k}: {shown}")
            if j.get("files"):
                print(f"  files: {', '.join(j['files'])}  (in {_jobs.job_dir(a.job_id)})")
            _jsonout.value("job", j)
        else:
            try:
                js = _jobs.list_jobs(a.state, a.operation, a.goal)
            except ValueError as exc:
                die(str(exc), "bad-argument")
            for j in js:
                print(_line(j))
            if not js:
                print("no jobs" + (f" {', '.join(a.state)}" if a.state else ""))
            _jsonout.value("jobs", js)
    return 0


def logs(argv: list[str]) -> int:
    """evh jobs-logs: a job's log, from a byte on, or followed until the job ends."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description="a job's log (RFC-026)")
    ap.add_argument("job_id")
    ap.add_argument("--from", dest="offset", type=int, default=0, metavar="BYTE", help="from this byte on")
    ap.add_argument("--follow", action="store_true", help="keep printing until the job ends")
    a = ap.parse_args(argv)
    from evaluation_harness import _jobs  # noqa: PLC0415

    try:
        _jobs.read(a.job_id)
    except (FileNotFoundError, ValueError):
        die(f"no job {a.job_id!r} in {_jobs.jobs_dir()}", "not-found")
    offset = a.offset
    while True:
        data, offset = _jobs.log_from(a.job_id, offset)
        if data:
            sys.stdout.write(data.decode("utf-8", "replace"))
            sys.stdout.flush()
        if not a.follow:
            return 0
        job = _jobs.read(a.job_id)
        if job["state"] in TERMINAL:
            data, offset = _jobs.log_from(a.job_id, offset)
            sys.stdout.write(data.decode("utf-8", "replace"))
            print(f"[{a.job_id} {job['state_label']}]")
            return 0
        time.sleep(0.5)


def stop(argv: list[str]) -> int:
    """evh jobs-stop: the job's process group stopped; it ends cancelled."""
    ap = argparse.ArgumentParser(
        prog=evh_prog(), description="stop a job (RFC-026): its process group, cancelled"
    )
    ap.add_argument("job_id")
    ap.add_argument("--json", action="store_true", help="the job's record as JSON")
    a = ap.parse_args(argv)
    from evaluation_harness import _jobs  # noqa: PLC0415

    with _jsonout.collect("jobs-stop", a.json):
        try:
            j = _jobs.stop(a.job_id)
        except (FileNotFoundError, ValueError):
            die(f"no job {a.job_id!r} in {_jobs.jobs_dir()}", "not-found")
        print(_line(j))
        _jsonout.value("job", j)
    return 0


def resume(argv: list[str]) -> int:
    """evh jobs-resume: a stopped or lost run continued by a new job."""
    ap = argparse.ArgumentParser(
        prog=evh_prog(), description="resume a stopped or lost run job, as a new job"
    )
    ap.add_argument("job_id")
    ap.add_argument("--json", action="store_true", help="the new job's record as JSON")
    a = ap.parse_args(argv)
    from evaluation_harness import _api, _jobs  # noqa: PLC0415

    with _jsonout.collect("jobs-resume", a.json):
        try:
            j = _api.resume_job(a.job_id)
        except (FileNotFoundError, ValueError):
            die(f"no job {a.job_id!r} in {_jobs.jobs_dir()}", "not-found")
        except _api.Refused as exc:
            _refused(exc)
        print(_line(j))
        _jsonout.value("job", j)
    return 0


def run(sub: str) -> int:
    """One of the jobs commands, by name."""
    return {"start": start, "status": status, "logs": logs, "stop": stop, "resume": resume}[sub](sys.argv[1:])
