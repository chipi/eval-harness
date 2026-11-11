"""The jobs from the terminal (RFC-026 step 6): the same jobs the API starts, in the project's .build/jobs/.

    evh jobs-start COMMAND [--arg NAME=VALUE ...] [--max-cost-usd N] [--reason TEXT] [--by WHO]
    evh jobs-status [JOB_ID] [--state STATE] [--json]
    evh jobs-logs JOB_ID [--follow] [--from BYTE]
    evh jobs-stop JOB_ID
    evh jobs-resume JOB_ID

`--arg` names an argument as the API does (its name without the dashes, as `GET /api/v1/commands` lists it): a
config by its id, `--arg repeat=3`, a flag as `--arg NAME=true`; repeated, it makes a list; `@FILE` uploads a
file. A job started here is listed by the API and stopped by it, and one the Workbench started is followed here. No
server is needed.
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
    """`--arg NAME=VALUE` pairs as the API's args: a name given twice is a list."""
    out: dict[str, Any] = {}
    for pair in pairs:
        name, sep, raw = pair.partition("=")
        if not sep or not name:
            die(
                f"--arg {pair!r}: expected NAME=VALUE (the name as GET /api/v1/commands lists it)",
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
    return f"{j['id']}  {j['state']:<22} {j['command']:<18} by {j.get('by') or '-'}{extra}"


def start(argv: list[str]) -> int:
    """evh jobs-start: a command started as a job, checked as the API checks it."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description="start a command as a job (RFC-026)")
    ap.add_argument("command", help="the command, as GET /api/v1/commands names it (served: job)")
    ap.add_argument(
        "--arg", action="append", default=[], metavar="NAME=VALUE", help="an argument (repeatable)"
    )
    ap.add_argument("--max-cost-usd", type=float, help="a command that spends: the most the job may spend")
    ap.add_argument("--reason", help="why (a decision's reason, a round's conclusion)")
    ap.add_argument("--json", action="store_true", help="the job's record as JSON")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    a = ap.parse_args(argv)
    from evaluation_harness import _api  # noqa: PLC0415

    with _jsonout.collect("jobs-start", a.json):
        try:
            j = _api.start_job(
                a.command, args_of(a.arg), _who() or None, a.reason, a.max_cost_usd, _for() or None
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
    ap.add_argument("--state", choices=("queued", "running", "running (unsupervised)", "lost", *TERMINAL[:3]))
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
            for k in ("argv", "reason", "created_at", "started_at", "ended_at", "exit", "run_id"):
                if j.get(k) not in (None, "", []):
                    print(f"  {k}: {' '.join(j[k]) if k == 'argv' else j[k]}")
            _jsonout.value("job", j)
        else:
            js = _jobs.list_jobs(a.state)
            for j in js:
                print(_line(j))
            if not js:
                print("no jobs" + (f" {a.state}" if a.state else ""))
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
        state = _jobs.read(a.job_id)["state"]
        if state in TERMINAL:
            data, offset = _jobs.log_from(a.job_id, offset)
            sys.stdout.write(data.decode("utf-8", "replace"))
            print(f"[{a.job_id} {state}]")
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
