#!/usr/bin/env python3
"""A stand-in for `harbor run`, for the example's tests: no Docker, no model, no network.

It takes the flags the adapter passes (and no other: an unknown flag is an error, as in Harbor), copies a recorded job
directory from `fixtures/jobs/` to `<-o>/<--job-name>`, and exits 0. `harbor dataset download NAME[@V] -o DIR [--overwrite]`
is stood in for too: it puts this example's three tasks at `DIR/<NAME without its owner and version>/`, as Harbor's export
mode lays a registry dataset out. Which job, and what else it does, is the environment's:

    FAKE_HARBOR_MODE   pass (default)  the `oracle-<task>` job: the verifier gave reward 1
                       fail            the `nop-<task>` job: the verifier gave reward 0
                       timeout         the `timeout-<task>` job: the agent timed out, the verifier ran (reward 0)
                       exception       the `exception-<task>` job: the trial's exception, no reward (a synthetic fixture)
                       crash           exit 1 with an error and no directory
                       reset           exit 1 with "Connection reset by peer", a message a retrying caller reads as transient
                       hang            make the trial's directory, start a child, and sleep: a call that never ends
                       stubborn        as hang, and ignore SIGTERM (only SIGKILL ends it)
    FAKE_HARBOR_ONLY   task names, comma-separated: the mode applies to them, every other task passes
    FAKE_HARBOR_LOG    a file: one JSON line per invocation (argv, pid), so a test counts the calls
    FAKE_HARBOR_PIDS   a file: the pids a hang started (this process and its child), one per line
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "jobs"
WITH_VALUE = {
    "-p": "path",
    "--path": "path",
    "-d": "dataset",
    "--dataset": "dataset",
    "-i": "task",
    "--include-task-name": "task",
    "-a": "agent",
    "--agent": "agent",
    "-m": "model",
    "--model": "model",
    "-o": "jobs_dir",
    "--jobs-dir": "jobs_dir",
    "--job-name": "job_name",
    "-n": "n_concurrent",
    "-r": "max_retries",
    "--env-file": "env_file",
    "--ae": "agent_env",
}
FLAGS = {"-q", "-y"}


def parse(argv: list[str]) -> dict[str, object]:
    """The flags of `harbor run`, as the adapter passes them; anything else is refused."""
    if argv[:1] != ["run"]:
        sys.exit(f"fake harbor: only `harbor run` is stood in for, got {argv[:1]}")
    got: dict[str, object] = {"agent_env": []}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in FLAGS:
            got[a] = True
            i += 1
        elif a in WITH_VALUE and i + 1 < len(argv):
            if WITH_VALUE[a] == "agent_env":
                got["agent_env"].append(argv[i + 1])  # type: ignore[union-attr]
            else:
                got[WITH_VALUE[a]] = argv[i + 1]
            i += 2
        else:
            sys.exit(f"fake harbor: unknown flag or missing value: {a}")
    for need in ("agent", "jobs_dir", "job_name"):
        if need not in got:
            sys.exit(f"fake harbor: missing {need}")
    if not (got.get("path") or (got.get("dataset") and got.get("task"))):
        sys.exit("fake harbor: needs -p PATH or -d DATASET -i TASK")
    return got


def task_of(got: dict[str, object]) -> str:
    return str(got["task"]) if got.get("task") else Path(str(got["path"])).name


def download(argv: list[str]) -> int:
    """`harbor dataset download NAME[@V] -o DIR [--overwrite]`: the example's tasks, laid out as a registry dataset is."""
    rest = argv[2:]
    if not rest or "-o" not in rest or rest.index("-o") + 1 >= len(rest):
        sys.exit("fake harbor: dataset download NAME -o DIR [--overwrite]")
    out = Path(rest[rest.index("-o") + 1])
    name = next(a for a in rest if not a.startswith("-") and a != rest[rest.index("-o") + 1])
    shutil.copytree(HERE / "tasks", out / name.split("@")[0].split("/")[-1], dirs_exist_ok=True)
    return 0


def main(argv: list[str]) -> int:
    if argv[:2] == ["dataset", "download"]:
        return download(argv)
    got = parse(argv)
    task = task_of(got)
    mode = os.environ.get("FAKE_HARBOR_MODE", "pass")
    only = [t for t in os.environ.get("FAKE_HARBOR_ONLY", "").split(",") if t]
    if only and task not in only:
        mode = "pass"
    if os.environ.get("FAKE_HARBOR_LOG"):
        with open(os.environ["FAKE_HARBOR_LOG"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"argv": argv, "pid": os.getpid(), "task": task, "mode": mode}) + "\n")
    job = Path(str(got["jobs_dir"])) / str(got["job_name"])
    if mode == "crash":
        print("harbor: error: the environment could not be started", file=sys.stderr)
        return 1
    if mode == "reset":
        print("ConnectionResetError: [Errno 104] Connection reset by peer", file=sys.stderr)
        return 1
    if mode in ("hang", "stubborn"):
        trial = job / f"{task}__hang001"
        trial.mkdir(parents=True)
        (trial / "config.json").write_text("{}", encoding="utf-8")
        child = subprocess.Popen(["sleep", "300"])
        if os.environ.get("FAKE_HARBOR_PIDS"):
            with open(os.environ["FAKE_HARBOR_PIDS"], "a", encoding="utf-8") as fh:
                fh.write(f"{os.getpid()}\n{child.pid}\n")
        if mode == "stubborn":
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(300)
        return 0
    kind = {"pass": "oracle", "fail": "nop", "timeout": "timeout", "exception": "exception"}.get(mode)
    if kind is None:
        sys.exit(f"fake harbor: unknown FAKE_HARBOR_MODE {mode!r}")
    src = FIXTURES / f"{kind}-{task}"
    if not src.is_dir():
        sys.exit(f"fake harbor: no recorded job for {kind} on {task}: {src}")
    job.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, job)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
