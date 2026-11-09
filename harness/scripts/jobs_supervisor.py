"""A job's supervisor (RFC-026 step 3): `python -m evaluation_harness.jobs_supervisor <job id>`, started detached.

It holds the job's supervisor.lock for its life, takes the job's locks (waiting, `queued`, while another job holds
one, and saying which), starts the command in a process group of its own with the lock descriptors passed to it (so
the command holds its locks for as long as it lives, whatever happens to the supervisor), writes `running` with that
group, waits, and writes how it ended: `succeeded`, `failed` (the exit code and the refusal kind), or `cancelled` when
it was stopped. The command's envelope, when it prints one, goes to result.json.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _jobs


def main(job_id: str) -> int:
    """Run one job to its end."""
    d = _jobs.job_dir(job_id)
    job = json.loads((d / "job.json").read_text(encoding="utf-8"))
    sup = os.open(str(d / "supervisor.lock"), os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(sup, fcntl.LOCK_EX)  # held for the supervisor's life; never passed to the command
    state: dict[str, Any] = {"state": "queued", "waiting_for": None, "supervisor_pid": os.getpid()}
    _jobs._write_json(d / "state.json", state)

    def waiting(key: str, holder: str) -> None:
        state.update(waiting_for={"lock": key, "job": holder or None})
        _jobs._write_json(d / "state.json", state)

    if (d / "stop").exists():
        _jobs._write_json(d / "state.json", {**state, "state": "cancelled", "ended_at": _common.now()})
        return 0
    fds = _jobs.take_locks([(k, bool(ex)) for k, ex in job["locks"]], job_id, waiting)
    if (d / "stop").exists():  # stopped while it waited
        _jobs._write_json(d / "state.json", {**state, "state": "cancelled", "ended_at": _common.now()})
        return 0
    from evaluation_harness.mcp_server import parser_of  # noqa: PLC0415

    command = job["command"]
    has_json = any("--json" in a.option_strings for a in parser_of(command)._actions)
    cmd = [sys.executable, str(Path(__file__).resolve().parent / "cli.py"), command]
    cmd += [*(["--json"] if has_json else []), *job["argv"]]
    env = {**os.environ, **{k: str(v) for k, v in (job.get("env") or {}).items()}}
    by = job.get("by")
    if by:  # who acted (RFC-027): a job has no terminal, so the actor comes from the call
        env["EVH_ACTOR"] = by if ":" in by else f"person:{by}"
    with open(d / "log", "ab") as log, open(d / "stdout", "wb") as out:
        p = subprocess.Popen(
            cmd,
            cwd=_common.project_root(),
            stdin=subprocess.DEVNULL,
            stdout=out if has_json else log,
            stderr=log,
            start_new_session=True,
            pass_fds=tuple(fds),
            env=env,
        )
        for fd in fds:  # the command holds them now; the supervisor's copies go
            os.close(fd)
        state.update(state="running", pgid=p.pid, waiting_for=None, started_at=_common.now())
        _jobs._write_json(d / "state.json", state)
        code = p.wait()
    text = (d / "stdout").read_text(encoding="utf-8", errors="replace") if has_json else ""
    if text.strip():
        try:
            _jobs._write_json(d / "result.json", json.loads(text))
        except ValueError:
            with open(d / "log", "a", encoding="utf-8") as log_text:
                log_text.write(text)
    stopped = (d / "stop").exists()
    end = "cancelled" if stopped else ("succeeded" if code == 0 else "failed")
    log_tail = (d / "log").read_text(encoding="utf-8", errors="replace")[-20000:]
    state.update(
        state=end,
        exit=code,
        ended_at=_common.now(),
        refusal=None if code == 0 else _jobs.refusal_kind(log_tail),
    )
    _jobs._write_json(d / "state.json", state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
