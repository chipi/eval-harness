#!/usr/bin/env python3
"""A stop that lands while a job's command is starting stops the command (the browser check's Resume timeout on CI).

    python tests/test_job_stop_race.py

The supervisor starts the command, then writes `running` with the command's process group. A stop between the two
read a job with no group: it ended the supervisor (a queued job's way) and the command went on, its job `cancelled`,
its locks held, its calls still made (on CI the browser test's second run queued behind the first one's orphan, or
found its one permitted call taken, and the run never answered an item). Every write the supervisor makes is
fsynced, so the stretch is as long as the disk's fsync: here each fsync of a job's own processes takes 0.4 s (a
sitecustomize on their PYTHONPATH), which makes the stretch last long enough to stop in it every time.
"""

import fcntl
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _cli
os.environ.setdefault("EVAL_STORE", "files")
import _cli  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

SLOW_FSYNC_S = 0.4
SITECUSTOMIZE = f"""import os, time
_real = os.fsync
if b"--inputs-file" in open("/proc/self/cmdline", "rb").read():
    time.sleep(20)  # a job's command: it lives long enough to be seen alive after the stop


def _slow(fd):
    time.sleep({SLOW_FSYNC_S})
    return _real(fd)


os.fsync = _slow
"""

proj = Path(tempfile.mkdtemp(prefix="evh-stoprace-"))
slow = Path(tempfile.mkdtemp(prefix="evh-slowfs-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj))
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def command_of(job_id: str) -> int | None:
    """The pid of the job's command (a live `cli.py ... --inputs-file <the job's inputs>`), None when there is none."""
    mark = f"jobs/{job_id}/inputs.json"
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            cmd = (p / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            state = (p / "stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
        except (OSError, IndexError):
            continue
        if mark in cmd and "--inputs-file" in cmd and state != "Z":
            return int(p.name)
    return None


try:
    r = _cli.run(proj, env, "init", "--store", "files")
    assert r.returncode == 0, r.stdout + r.stderr
    (slow / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
    os.environ["EVAL_HOME"] = str(proj)
    os.environ["PYTHONPATH"] = os.pathsep.join(x for x in (str(slow), os.environ.get("PYTHONPATH", "")) if x)
    from evaluation_harness import _common, _jobs

    _common.project_root.cache_clear()
    jid = _jobs.new_id()
    _jobs.create("prompt-version", {"name": "who_q", "text": "x", "note": "n"}, "person:ana", [("prompt:who_q", True)], {}, None, jid)  # fmt: skip
    _jobs.start(jid)
    end = time.monotonic() + 60
    pid = None
    while pid is None and time.monotonic() < end:
        pid = command_of(jid)
        time.sleep(0.005)
    check(
        "the job's command started (the stop below lands while its supervisor writes `running`)",
        pid is not None,
        pid,
    )
    stop_began = time.monotonic()
    stopped = _jobs.stop(jid)
    stop_took = time.monotonic() - stop_began
    alive_after = command_of(jid)
    held = None
    try:
        for fd in _jobs.take_locks([("prompt:who_q", True)], "the test"):
            os.close(fd)
        held = False
    except _jobs.Busy:
        held = True
    ok = stopped.get("state") == "cancelled" and alive_after is None and held is False
    why: tuple = (stopped.get("state"), alive_after, held)
    if (
        not ok
    ):  # what a failure under load needs to be read: the job's own files, and the command as /proc has it
        d = _jobs.job_dir(jid)
        why += tuple(
            (f.name, f.read_text(encoding="utf-8", errors="replace")[-600:])
            for f in (d / "state.json", d / "log")
            if f.is_file()
        )
        if alive_after:
            seen = Path(f"/proc/{alive_after}/stat").read_text(encoding="utf-8")[:60]
            end = time.monotonic() + 30  # dies late (a slow stop) or never (an orphan)?
            while command_of(jid) and time.monotonic() < end:
                time.sleep(0.2)
            why += (f"stop took {stop_took:.1f} s", seen, f"alive 30 s on: {command_of(jid) is not None}")
    check(
        "a stop while the command is starting: cancelled, the command gone, the job's lock free",
        ok,
        why,
    )

    # The stop's own read of the job, made certain here as the pool's CPUs made it twice in three runs: stop() read the job
    # (no group yet), wrote its stop file, and in between the supervisor recorded the command's group. The group it acts on
    # is the one recorded when the stop file was written: a stale read left the command running, 20 s of its own, under a
    # job stop() then wrote `cancelled` after 5 s of waiting for a supervisor that had never seen the stop either.
    sleeper = subprocess.Popen(["sleep", "60"], start_new_session=True)
    jid2 = _jobs.new_id()
    _jobs.create("prompt-version", {"name": "who_q2", "text": "x", "note": "n"}, "person:ana", [("prompt:who_q2", True)], {}, None, jid2)  # fmt: skip
    d2 = _jobs.job_dir(jid2)
    lock = os.open(str(d2 / "supervisor.lock"), os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(lock, fcntl.LOCK_EX)  # a live supervisor's: the job reads queued, not lost
    _jobs._write_json(
        d2 / "state.json", {"state": "queued", "waiting_for": None, "supervisor_pid": os.getpid()}
    )

    def supervisor() -> None:
        """What the supervisor does once the command is gone: ends the job and lets go of its lock."""
        sleeper.wait()
        _jobs._write_json(
            d2 / "state.json", {"state": "cancelled", "ended_at": "2026-11-24T00:00:00Z", "exit": -15}
        )
        os.close(lock)

    threading.Thread(target=supervisor, daemon=True).start()
    real_read = _jobs.read
    calls: list[int] = []

    def read_then_record_the_group(job_id: str) -> dict:
        got = real_read(job_id)  # queued, no group: what stop() first sees
        if not calls:
            calls.append(1)
            _jobs._write_json(
                d2 / "state.json",
                {"state": "running", "pgid": sleeper.pid, "waiting_for": None, "supervisor_pid": os.getpid()},
            )
        return got

    _jobs.read = read_then_record_the_group
    try:
        began = time.monotonic()
        stopped2 = _jobs.stop(jid2, grace=5)
    finally:
        _jobs.read = real_read
    took = time.monotonic() - began
    try:
        sleeper.wait(timeout=1)
        gone = True
    except subprocess.TimeoutExpired:
        gone = False
        sleeper.kill()
    check(
        "a stop that reads the job before the supervisor records the command's group still stops the command",
        gone and stopped2.get("state") == "cancelled" and took < 4,
        (stopped2.get("state"), gone, round(took, 1)),
    )
finally:
    pid = command_of(jid) if "jid" in globals() else None
    if pid:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
    shutil.rmtree(proj, ignore_errors=True)
    shutil.rmtree(slow, ignore_errors=True)
sys.exit(summary())
