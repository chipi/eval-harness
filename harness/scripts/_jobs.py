"""Jobs (RFC-026 step 3): one `evh` command each, run by a detached supervisor, in the project's .build/jobs/.

    .build/jobs/<id>/job.json         the command, its argv, who asked and why, its locks, when, the harness version
    .build/jobs/<id>/state.json       queued | running | succeeded | failed | cancelled, rewritten whole
    .build/jobs/<id>/log              what the command printed (its stderr, and its stdout when it prints no envelope)
    .build/jobs/<id>/result.json      its --json envelope, when it prints one
    .build/jobs/<id>/supervisor.lock  held by the supervisor for its life: free on a running job = the supervisor is gone
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


# ── what each job locks ────────────────────────────────────────────────────────────────────────────────────────────


def _config(path: str | None) -> dict:
    """A config file's fields (config_id, dataset_id, params), {} when it cannot be read."""
    import yaml  # noqa: PLC0415
    from evaluation_harness import _store  # noqa: PLC0415

    if not path:
        return {}
    p = Path(path)
    p = p if p.is_absolute() else _common.project_root() / p
    try:
        doc = yaml.safe_load(_store.read_text(p, encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _run_meta(run_id: str | None) -> dict:
    from evaluation_harness import _store  # noqa: PLC0415

    if not run_id:
        return {}
    f = _common.RUNS / run_id / "metrics.json"
    try:
        return json.loads(_store.read_text(f, encoding="utf-8")) if _store.is_file(f) else {}
    except (OSError, ValueError):
        return {}


def _first(v: Any) -> Any:
    return v[0] if isinstance(v, list) and v else v


def _ds(a: dict) -> list[tuple[str, bool]]:
    d = _first(a.get("dataset-id")) or _first(a.get("dataset_id"))
    return [(f"dataset:{d}", True)] if d else []


def _run_locks(a: dict) -> list[tuple[str, bool]]:
    c = _config(_first(a.get("config")))
    out = []
    if c.get("config_id"):
        out.append((f"config:{c['config_id']}", True))
    if c.get("dataset_id"):
        out.append((f"dataset:{c['dataset_id']}", False))
    return out


def _model_locks(a: dict) -> list[tuple[str, bool]]:
    c = _config(_first(a.get("config")))
    m = c.get("model_record") or (c.get("params") or {}).get("model")
    return [(f"model:{m}", True)] if m else []


def _sweep_locks(a: dict) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    for f in a.get("configs") or []:
        out += _run_locks({"config": f})
    return out


def _split_locks(a: dict) -> list[tuple[str, bool]]:
    d = _first(a.get("dataset_id")) or _first(a.get("dataset-id"))
    return [(f"dataset:{x}", True) for x in (d, f"{d}_validation", f"{d}_test")] if d else []


def _rescore_locks(a: dict) -> list[tuple[str, bool]]:
    out = _ds(a)
    if a.get("round") and a.get("goal"):
        out.append((f"goal:{a['goal']}", True))
        if not out[:-1]:
            from evaluation_harness import _rounds  # noqa: PLC0415

            rnd = _rounds.find(str(a["goal"]), str(a["round"])) or {}
            if rnd.get("dataset_id"):
                out.append((f"dataset:{rnd['dataset_id']}", True))
    return out


def _promote_locks(a: dict) -> list[tuple[str, bool]]:
    m = _run_meta(_first(a.get("run")))
    goal = None if a.get("no-goal") else (a.get("goal") or m.get("goal"))
    d = m.get("dataset_id") or _first(a.get("dataset"))
    return [(f"baselines:{goal or '_dataset'}/{d}", True)] if d else []


def _label_from_run_locks(a: dict) -> list[tuple[str, bool]]:
    d = _run_meta(_first(a.get("run"))).get("dataset_id")
    return [(f"dataset:{d}", True)] if d else []


def _capture_ds_locks(a: dict) -> list[tuple[str, bool]]:
    return [("captures", False), *_ds(a)]


def _arm_from_capture_locks(a: dict) -> list[tuple[str, bool]]:
    out = [("captures", False), *_ds(a)]
    if a.get("as"):
        out.append((f"config:{a['as']}", True))
    return out


def _data_rm_locks(a: dict) -> list[tuple[str, bool]]:
    out = [("settings", True)]
    path = str(_first(a.get("path")) or "")
    run = path.split("/")[1] if path.startswith("runs/") and path.count("/") >= 1 else None
    cid = _run_meta(run).get("config_id") if run else None
    if cid:
        out.append((f"config:{cid}", True))
    return out


#: command -> its locks from the call's arguments (names as the API takes them). `project` shared is added to every
#: job; a migration takes it exclusive. A job command in neither this nor PROJECT_ONLY fails a test.
LOCK_RULES: dict[str, Callable[[dict], list[tuple[str, bool]]]] = {
    "run": _run_locks,
    "arm-smoke": _model_locks,
    "model-onboard": _model_locks,
    "sweep": _sweep_locks,
    **dict.fromkeys(
        (
            "dataset-create",
            "dataset-extend",
            "dataset-materialize",
            "dataset-describe",
            "dataset-profile",
            "reference-manifest",
            "reference-promote",
            "label-import",
            "label-sheet",
            "sheet-import",
            "label-from-capture",
            "dataset-publish",
            "fieldset-propose",
        ),
        _ds,
    ),
    "dataset-split": _split_locks,
    "dataset-unseal": _split_locks,
    "label-from-run": _label_from_run_locks,
    "rescore": _rescore_locks,
    "judge-score": _rescore_locks,
    "round-open": lambda a: [(f"goal:{a['goal']}", True)] if a.get("goal") else [],
    "round-retire": lambda a: [(f"goal:{a['goal']}", True)] if a.get("goal") else [],
    "round-close": lambda a: [(f"goal:{a['goal']}", True)] if a.get("goal") else [],
    "run-promote": _promote_locks,
    "baseline-rollback": _promote_locks,
    "pick": lambda a: [(f"picks:{_first(a.get('dataset-id'))}", True)] if a.get("dataset-id") else [],
    "capture": lambda a: [("captures", True)],
    "capture-restore": lambda a: [("captures", True)],
    "dataset-from-capture": _capture_ds_locks,
    "arm-from-capture": _arm_from_capture_locks,
    "import-run": _ds,
    "catalog": lambda a: [("catalog", True)],
    "data-put": lambda a: [("settings", True)],
    "data-rm": _data_rm_locks,
}
#: Migrations: the whole project, exclusive (every other job holds it shared, so each waits for the other).
MIGRATIONS = {"data-migrate", "run-migrate", "dataset-migrate", "fingerprint-migrate", "baselines-migrate"}
#: Job commands that write nothing another job writes (reports, checks, estimates): `project` shared only.
PROJECT_ONLY = {
    "prompt-version",  # a version is written once, named by its content (RFC-028): two at once write one
    "prompt-export",  # into the job's own folder
    "bootstrap-test",
    "holdout",
    "cost-report",
    "importer-check",
    "score-preview",
    "silver-calibrate",
    "judge",
}


def locks_for(command: str, args: dict) -> list[tuple[str, bool]]:
    """(key, exclusive) for a job of `command` with these (checked) arguments, `project` included, sorted by key."""
    if command in MIGRATIONS:
        return [("project", True)]
    rule = LOCK_RULES.get(command)
    got = rule(args) if rule else []
    out: dict[str, bool] = {"project": False}
    for k, ex in got:
        out[k] = out.get(k, False) or ex
    return sorted(out.items())


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


def create(
    command: str,
    argv: list[str],
    by: str | None,
    reason: str | None,
    locks: list[tuple[str, bool]],
    env: dict[str, str] | None = None,
    run_id: str | None = None,
    job_id: str | None = None,
) -> str:
    """Write a job's record (queued) and return its id; `start` runs it. `job_id`: one made beforehand (new_id),
    when the call's arguments name a file in the job's own folder (an artifact)."""
    from evaluation_harness._version import __version__  # noqa: PLC0415

    job_id = job_id or new_id()
    d = job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    _write_json(
        d / "job.json",
        {
            "id": job_id,
            "command": command,
            "argv": argv,
            "by": by,
            "reason": reason,
            "locks": [[k, ex] for k, ex in locks],
            "env": env or {},
            "run_id": run_id,
            "created_at": _common.now(),
            "harness": __version__,
        },
    )
    _write_json(d / "state.json", {"state": "queued", "waiting_for": None})
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


def read(job_id: str) -> dict[str, Any]:
    """A job: its record and its state, with what the files cannot say by themselves: a `running` or `queued` job
    whose supervisor is gone reads `running (unsupervised)` while its command lives, else `lost`."""
    d = job_dir(job_id)
    job = _read_json(d / "job.json")
    if not job:
        raise FileNotFoundError(job_id)
    st = _read_json(d / "state.json")
    if st.get("state") in ("queued", "running") and not _held(d / "supervisor.lock") and not _starting(d, st):
        st = {**st, "state": "running (unsupervised)" if _alive(st.get("pgid")) else "lost"}
    res = _read_json(d / "result.json") or None
    return {**job, **st, "result": res}


def list_jobs(state: str | None = None) -> list[dict[str, Any]]:
    """Every job, newest first; `state` keeps one state."""
    root = jobs_dir()
    out = []
    for d in sorted(root.iterdir(), reverse=True) if root.is_dir() else []:
        with contextlib.suppress(FileNotFoundError, ValueError):
            j = read(d.name)
            if state is None or j["state"] == state:
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
    """Stop a job: SIGTERM to its command's process group, SIGKILL after `grace` seconds; it ends `cancelled`."""
    d = job_dir(job_id)
    j = read(job_id)
    if j["state"] in ("succeeded", "failed", "cancelled", "lost"):
        return j
    (d / "stop").write_text(_common.now() + "\n")
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
