"""A harness command run from a test: `evh <args>` in a project, its output captured, its stdin closed, its time bounded.

    import _cli
    def evh(*args):
        return _cli.run(proj, env, *args)

Each test file keeps its own `evh()`, which names its project and environment. 49 of them had no timeout (a command
that hung held the whole suite until CI killed it) and 37 left stdin open (a command that asks waits for an answer
no test gives), 2026-11-19.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

CLI = Path(__file__).resolve().parents[1] / "scripts" / "cli.py"
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
    )
