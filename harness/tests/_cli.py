"""A harness command run from a test: `evh <args>` in a project, its output captured, its stdin closed, its time bounded.

    import _cli
    def evh(*args):
        return _cli.run(proj, env, *args)

Each test file keeps its own `evh()`, which names its project and environment. 49 of them had no timeout (a command
that hung held the whole suite until CI killed it) and 37 left stdin open (a command that asks waits for an answer
no test gives), 2026-11-19.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

CLI = Path(__file__).resolve().parents[1] / "scripts" / "cli.py"
WORKER = Path(__file__).resolve().parent / "_evh_worker.py"
#: The longest a test's command may take: a catalog build or a full run of a fixture project takes well under it.
TIMEOUT = 600


def run(cwd: Any, env: Any, *args: Any, timeout: float = TIMEOUT) -> subprocess.CompletedProcess:
    """`evh <args>` in `cwd` with `env`, its stdout and stderr captured as text."""
    return subprocess.run(
        [sys.executable, str(CLI), *map(str, args)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        encoding="utf-8",
    )


class Session:
    """Many `evh <args>` in one process, the project's and the environment's: for a test that reads a project a few hundred
    times and asks what each read says, not how a process starts (each `run` was a start of the interpreter and an import of
    the package, most of what a read cost: test_data_mutations took 1,000 CPU-seconds in 8,500 of them). The command is
    `cli.main`, as `evh` is; the process is not new for each, so a test of how one starts uses `run`. One at a time: a
    second caller waits."""

    def __init__(self, cwd: Any, env: Any) -> None:
        self.lock = threading.Lock()
        self.proc = subprocess.Popen(
            [sys.executable, str(WORKER)], cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, encoding="utf-8",
        )  # fmt: skip

    def run(self, *args: Any, public: bool | None = None) -> subprocess.CompletedProcess:
        """`evh <args>` as `run` gives it; `public` True or False sets or clears EVH_PUBLIC for this call."""
        req = json.dumps({"argv": [str(a) for a in args], "public": public})
        with self.lock:
            assert self.proc.stdin is not None and self.proc.stdout is not None
            self.proc.stdin.write(req + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"the evh worker ended while running {args}: exit {self.proc.wait(10)}")
        got = json.loads(line)
        return subprocess.CompletedProcess([*map(str, args)], got["rc"], got["out"], got["err"])

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(10)
        if self.proc.stdout:
            self.proc.stdout.close()
