"""`evh catalog-serve` in the tests: started on a free port, its output read as it comes.

Left in the pipe after start-up, the access log (a line per API request) filled the pipe's buffer, the server blocked on
its next line and answered nothing more: a test that made a screen's worth more requests timed out in the steps after
it (2026-11-19). A test that never read the pipe at all would block the same way once its requests passed the buffer.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "scripts" / "cli.py"


_READERS: dict[int, threading.Thread] = {}


def drain(p: subprocess.Popen, lines: list[str]) -> list[str]:
    """Read the rest of `p`'s output into `lines` in the background; `finished(p)` waits for its last line."""
    out = p.stdout

    def read() -> None:
        for x in out or ():
            lines.append(x.rstrip())

    t = threading.Thread(target=read, daemon=True)
    t.start()
    _READERS[p.pid] = t
    return lines


def finished(p: subprocess.Popen, timeout: float = 10) -> None:
    """Once `p` has ended, wait until every line it wrote has been read."""
    t = _READERS.pop(p.pid, None)
    if t is not None:
        t.join(timeout)


def startup(p: subprocess.Popen, lines: list[str]) -> list[str]:
    """Read `p`'s start-up lines into `lines`, up to its last, then keep reading the rest into it in the background."""
    assert p.stdout is not None
    while line := p.stdout.readline():
        lines.append(line.rstrip())
        if "rendered when it is asked for" in line:
            break
    drain(p, lines)
    return lines


def start(cwd: Path, env: dict, *extra: str) -> tuple[subprocess.Popen, int, list[str]]:
    """`evh catalog-serve` for the project at `cwd` on a free port, once it answers: (the process, the port, its
    output so far and as it comes). Raises with its output when it does not answer within 30 s."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(CLI), "catalog-serve", "--port", str(port), *extra],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    lines = drain(p, [])
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return p, port, lines
        except OSError:
            if p.poll() is not None:
                break
            time.sleep(0.1)
    p.kill()
    p.wait(timeout=10)
    finished(p)
    raise RuntimeError("the server did not start: " + "\n".join(lines)[-600:])


def jobs_done(proj: Path, timeout: float = 120) -> bool:
    """Wait until none of the project's jobs is queued or running (a catalog rebuild the server started goes on after
    it stops); False when one still is after `timeout` seconds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        live = []
        for st in (Path(proj) / ".build" / "jobs").glob("*/state.json"):
            try:
                live += [st] if json.loads(st.read_text()).get("state") in ("queued", "running") else []
            except (OSError, ValueError):
                live.append(st)  # being written
        if not live:
            return True
        time.sleep(0.2)
    return False


def stop(p: subprocess.Popen, proj: Path | None = None, timeout: float = 20) -> None:
    """Stop the server, read its last lines, and, given its project, wait for the jobs it started."""
    p.terminate()
    try:
        p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(timeout=10)
    finished(p)
    if proj is not None:
        jobs_done(proj)
