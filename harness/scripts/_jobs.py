"""Jobs (RFC-026 step 3, RFC-032 P3): one decision or work operation each, run by a detached supervisor, in the
project's .build/jobs/.

    .build/jobs/<id>/job.json         the operation and its inputs, who asked, its locks, when, the harness version
    .build/jobs/<id>/inputs.json      an operation's inputs, which its command reads (`--inputs-file`)
    .build/jobs/<id>/state.json       queued | running | succeeded | failed | cancelled, rewritten whole
    .build/jobs/<id>/log              what the command printed (its stderr, and its stdout when it prints no envelope)
    .build/jobs/<id>/stdout           what the command printed on stdout, read for its envelope when it ends
    .build/jobs/<id>/result.json      its --json envelope, when it prints one
    .build/jobs/<id>/progress.json    how far it has got, {done, total, at}, for the commands that say
    .build/jobs/<id>/stop             left by jobs-stop: the job ended because it was asked to
    .build/jobs/<id>/supervisor.lock  held by the supervisor for its life: free on a running job = the supervisor is gone
    .build/jobs/<id>/<name>           a file the command wrote for the person (a sheet, an export): the job's `files`
    .build/locks/<key>.lock           one per thing written; shared to read, exclusive to write, taken in key order

A job does not depend on the server: the server can stop and restart and the job goes on. Its locks are held by the
command itself (their descriptors are passed to it), so they outlive the supervisor and are freed however the command
ends. Jobs are not project data: they live in .build/, the same in either store.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from evaluation_harness import _common

STATES = ("queued", "running", "succeeded", "failed", "cancelled")
STOP_GRACE_S = 10.0


def jobs_dir() -> Path:
    """The project's jobs folder."""
    return _common.project_root() / ".build" / "jobs"


def locks_dir() -> Path:
    """The project's lock files."""
    return _common.project_root() / ".build" / "locks"


#: The job's own files, beside what its command wrote: never listed as the job's files.
OWN = frozenset({
    "job.json", "inputs.json", "state.json", "log", "stdout", "result.json", "progress.json", "stop", "supervisor.lock",
    "supervisor.pid", "supervisor.log",
})  # fmt: skip


def files(job_id: str) -> list[str]:
    """The files the job's command wrote into its folder (a sheet, an export), by name: what GET /jobs/<id>/files/<name>
    gives. A blind sheet's key stays with the job and is not one of them."""
    from evaluation_harness._sheet import KEY_SUFFIX  # noqa: PLC0415

    d = job_dir(job_id)
    return (
        sorted(
            f.name
            for f in d.iterdir()
            if f.is_file() and f.name not in OWN and not f.name.endswith(KEY_SUFFIX)
        )
        if d.is_dir()
        else []
    )


def job_dir(job_id: str) -> Path:
    """One job's folder (an id is checked: no path can be named)."""
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}-[0-9a-f]{6}", job_id or ""):
        raise ValueError(f"not a job id: {job_id!r}")
    return jobs_dir() / job_id


def _write_json(p: Path, doc: dict) -> None:
    """A job's record, written whole (a reader never sees half of it)."""
    _common.write_text_atomic(p, json.dumps(doc, indent=2, sort_keys=True) + "\n")


def _read_json(p: Path) -> dict:
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


# ── the locks ──────────────────────────────────────────────────────────────────────────────────────────────────────


def _lock_file(key: str) -> Path:
    return locks_dir() / (
        re.sub(r"[^A-Za-z0-9_.:-]", "_", key).replace(":", "__").replace("/", "_") + ".lock"
    )


class Busy(Exception):
    """A lock is held by someone else (a job, or the server) and the caller does not wait."""

    def __init__(self, key: str, holder: str) -> None:
        super().__init__(f"{key} is held by {holder or 'another process'}")
        self.key, self.holder = key, holder


def take_locks(
    locks: list[tuple[str, bool]], job_id: str, waiting: Callable[[str, str], None] | None = None
) -> list[int]:
    """Take the locks in key order and return their descriptors: whoever holds a descriptor holds the lock (flock
    belongs to the open file). A held one is waited for (`waiting(key, holder)` is told first), or, with no `waiting`,
    every lock taken so far is let go and `Busy` raised."""
    locks_dir().mkdir(parents=True, exist_ok=True)
    fds: list[int] = []
    for key, exclusive in sorted(locks):
        f = _lock_file(key)
        fd = os.open(str(f), os.O_RDWR | os.O_CREAT, 0o644)
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(fd, mode | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = ""
            with contextlib.suppress(OSError):
                holder = f.with_suffix(".holder").read_text().strip()
            if waiting is None:
                for x in (*fds, fd):
                    os.close(x)
                raise Busy(key, holder) from None
            waiting(key, holder)
            fcntl.flock(fd, mode)
        if exclusive:
            f.with_suffix(".holder").write_text(job_id + "\n")
        fds.append(fd)
    return fds


def say_waiting(key: str, holder: str) -> None:
    """What a command prints when it waits for a lock (on stderr): a command waiting in silence on a job that holds its
    lock for an hour looked hung (a review, 2026-11-11)."""
    print(
        f"  waiting for {key}, held by {holder or 'another process'}: it goes on when that lets go",
        file=sys.stderr,
        flush=True,
    )


@contextlib.contextmanager
def holding(locks: list[tuple[str, bool]], who: str, waiting: Callable[[str, str], None] | None = None):
    """The server's own writes (RFC-026 step 4): these locks and `project` shared, for the block; `Busy` at once when
    one is held and `waiting` is None."""
    keys = dict(locks)
    keys["project"] = keys.get("project", False)
    fds = take_locks(sorted(keys.items()), who, waiting)
    try:
        yield
    finally:
        for fd in fds:
            os.close(fd)


def migration_mark() -> int | None:
    """When a migration last took the whole project (the `project` holder file is written at each exclusive take):
    a server that polls sees a migration that began and ended between two looks."""
    try:
        return _lock_file("project").with_suffix(".holder").stat().st_mtime_ns
    except OSError:
        return None


def migrating() -> bool:
    """Whether a migration holds the whole project (`project` exclusive): what the server answers 503 for."""
    try:
        fd = os.open(str(_lock_file("project")), os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


# ── a job's life ────────────────────────────────────────────────────────────────────────────────────────────────────


def new_id() -> str:
    """A job id: when it was made, and six hex digits."""
    return time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + secrets.token_hex(3)


def spent(job_id: str) -> float:
    """What a job's command counted as spent, as it went (0 when it made no paid call)."""
    try:
        return float(_read_json(job_dir(job_id) / "spent.json").get("spent_usd") or 0)
    except (OSError, ValueError, TypeError):
        return 0.0


def create(
    operation: str,
    inputs: dict[str, Any],
    by: str | None,
    locks: list[tuple[str, bool]],
    env: dict[str, str] | None = None,
    run_id: str | None = None,
    job_id: str | None = None,
) -> str:
    """Write the record of a job of an operation (queued) and return its id; `start` runs it. A job names an operation
    and its typed inputs, never a command line: the inputs are kept in the record and in inputs.json, which the command
    reads (`cli.py <operation> --json --inputs-file`). `run_id` only for an operation that can be resumed."""
    from evaluation_harness._version import __version__  # noqa: PLC0415

    job_id = job_id or new_id()
    d = job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    _write_json(d / "inputs.json", inputs)
    # job.json is written last: `read` takes a folder without it as no job, so a reader never sees a job without a state.
    _write_json(d / "state.json", {"state": "queued", "waiting_for": None})
    _write_json(
        d / "job.json",
        {
            "id": job_id,
            "operation": operation,
            "inputs": inputs,
            "by": by,
            "locks": [[k, ex] for k, ex in locks],
            "env": env or {},
            **({"run_id": run_id} if run_id is not None else {}),
            "created_at": _common.now(),
            "harness": __version__,
        },
    )
    return job_id


def start(job_id: str) -> int:
    """Start the job's supervisor, detached: a new session, stdin from /dev/null, its output to supervisor.log,
    every other descriptor closed. Returns its pid."""
    d = job_dir(job_id)
    with open(d / "supervisor.log", "ab") as log:
        p = subprocess.Popen(
            [sys.executable, "-m", "evaluation_harness.jobs_supervisor", job_id],
            cwd=_common.project_root(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
            # The package where this one is, whatever the project's own path holds.
            env={
                **os.environ,
                "PYTHONPATH": os.pathsep.join(
                    x
                    for x in (str(Path(__file__).resolve().parents[1]), os.environ.get("PYTHONPATH", ""))
                    if x
                ),
            },
        )
    (d / "supervisor.pid").write_text(f"{p.pid}\n")
    return p.pid


def _starting(d: Path, st: dict[str, Any]) -> bool:
    """A job whose supervisor is started but has not yet taken its lock (it has written no state of its own): the
    process `start` began is alive and not a zombie."""
    if st.get("supervisor_pid"):
        return False
    try:
        pid = int((d / "supervisor.pid").read_text().strip())
        stat = Path(f"/proc/{pid}/stat")
        if stat.exists():
            return stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def _held(path: Path) -> bool:
    """Whether another process holds an exclusive flock on `path`."""
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _alive(pgid: int | None) -> bool:
    if not pgid:
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _ended(pid: int) -> bool:
    """The process is gone, or a zombie its parent has not reaped: it holds nothing any more."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        with contextlib.suppress(OSError, IndexError):
            return stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"
        return False
    out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False)
    return not out.stdout.strip() or out.stdout.strip().startswith("Z")


def read(job_id: str) -> dict[str, Any]:
    """A job: its record and its state, with what the files cannot say by themselves: a `running` or `queued` job
    whose supervisor is gone reads `running (unsupervised)` while its command lives, else `lost`. How far it has got
    (`progress`: {done, total, at}, or None when its command reports none) and what it has spent so far (`spent_usd`)
    are as the command last wrote them. A record without an `operation` (one from before jobs were operations, left in
    .build/jobs) reads as a job of the operation `unknown`, its state as recorded; `create` always writes one."""
    d = job_dir(job_id)
    job = _read_json(d / "job.json")
    if not job:
        raise FileNotFoundError(job_id)
    st = _read_json(d / "state.json")
    if st.get("state") in ("queued", "running") and not _held(d / "supervisor.lock") and not _starting(d, st):
        st = {**st, "state": "running (unsupervised)" if _alive(st.get("pgid")) else "lost"}
    res = _read_json(d / "result.json") or None
    progress = _read_json(d / "progress.json") or None
    return {
        **job,
        **st,
        "state_label": state_label(st),
        "operation": job.get("operation") or "unknown",
        "progress": progress,
        "spent_usd": spent(job_id),
        "result": res,
        "files": files(job_id),
    }


#: The states a job is read in: its stored ones, and the two `read` works out (a supervisor gone).
SHOWN_STATES = ("queued", "running", "running (unsupervised)", "lost", "succeeded", "failed", "cancelled")


def state_label(job: dict[str, Any]) -> str:
    """The state a person reads. A job that ended `failed` with exit 6 (EXIT_PROBLEMS: its checks ran and flagged
    something, as arm-smoke, model-onboard and exposure-check do) is "checked, flagged": its flags are its answer, not a
    failure. Every other state is the stored one. The one definition: the listings, the API and the Workbench read it."""
    if job.get("state") == "failed" and job.get("exit") == _common.EXIT_PROBLEMS:
        return "checked, flagged"
    return str(job.get("state"))


def states_of(values: list[str] | str | None) -> list[str]:
    """The states a query asks for: each value, or several separated by commas (`queued,running`); refused (ValueError)
    for one a job is never in."""
    given = [values] if isinstance(values, str) else list(values or [])
    wanted = [s.strip() for v in given for s in str(v).split(",") if s.strip()]
    unknown = [s for s in wanted if s not in SHOWN_STATES]
    if unknown:
        raise ValueError(f"state {', '.join(map(repr, unknown))}: one of {', '.join(SHOWN_STATES)}")
    return wanted


def list_jobs(
    state: list[str] | str | None = None, operation: str | None = None, goal: str | None = None
) -> list[dict[str, Any]]:
    """Every job, newest first; `state` keeps those in any of these states (one, a list, or comma-separated: the home
    page's "running now" is queued, running and running (unsupervised)), `operation` those of one operation, `goal`
    those whose inputs name the goal."""
    wanted = set(states_of(state))
    root = jobs_dir()
    out = []
    for d in sorted(root.iterdir(), reverse=True) if root.is_dir() else []:
        with contextlib.suppress(FileNotFoundError, ValueError):
            j = read(d.name)
            if wanted and j["state"] not in wanted:
                continue
            if operation and j.get("operation") != operation:
                continue
            if goal and (j.get("inputs") or {}).get("goal") != goal:
                continue
            out.append({k: v for k, v in j.items() if k not in ("env", "result")})
    return out


def log_from(job_id: str, offset: int = 0) -> tuple[bytes, int]:
    """The job's log from a byte offset, and the offset to ask from next."""
    p = job_dir(job_id) / "log"
    if not p.is_file():
        return b"", offset
    with open(p, "rb") as fh:
        fh.seek(max(offset, 0))
        data = fh.read()
    return data, max(offset, 0) + len(data)


def stop(job_id: str, grace: float = STOP_GRACE_S) -> dict[str, Any]:
    """Stop a job: SIGTERM to its command's process group, SIGKILL after `grace` seconds; a queued job's supervisor is
    ended (the locks it took go with it); it ends `cancelled`."""
    d = job_dir(job_id)
    j = read(job_id)
    if j["state"] in ("succeeded", "failed", "cancelled", "lost"):
        return j
    (d / "stop").write_text(_common.now() + "\n")
    st0 = _read_json(d / "state.json")
    spid = st0.get("supervisor_pid")
    if not st0.get("pgid") and st0.get("state") == "queued" and spid:
        # A queued job's supervisor waits for a lock in flock and holds every lock it took before it: stopping only the
        # command it has not started left those held, behind a job that read `cancelled`. It is ended; its descriptors,
        # and so its locks, go with it.
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(int(spid), signal.SIGTERM)
        # Its locks go free while it exits, before it has ended: wait for the process, not only the lock.
        end = time.monotonic() + grace
        while not _ended(int(spid)) and time.monotonic() < end:
            time.sleep(0.05)
        if not _ended(int(spid)):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(int(spid), signal.SIGKILL)
            end = time.monotonic() + grace
            while not _ended(int(spid)) and time.monotonic() < end:
                time.sleep(0.05)
        j = read(job_id)  # it may have started the command just before: that is stopped below
    pgid = j.get("pgid")
    if pgid and _alive(pgid):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGTERM)
        end = time.monotonic() + grace
        while _alive(pgid) and time.monotonic() < end:
            time.sleep(0.1)
        if _alive(pgid):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(pgid, signal.SIGKILL)
    # A queued job, or one whose supervisor is gone: nobody else will write its end.
    for _ in range(50):
        if _read_json(d / "state.json").get("state") == "cancelled" or not _held(d / "supervisor.lock"):
            break
        time.sleep(0.1)
    st = _read_json(d / "state.json")
    if st.get("state") != "cancelled":
        _write_json(d / "state.json", {**st, "state": "cancelled", "ended_at": _common.now()})
    return read(job_id)


REFUSAL = re.compile(r"^ERROR \(([a-z-]+)\)", re.M)


def refusal_kind(log: str) -> str | None:
    """The refusal kind the command printed last (`ERROR (<kind>): ...`), or None."""
    kinds = REFUSAL.findall(log)
    return kinds[-1] if kinds else None
