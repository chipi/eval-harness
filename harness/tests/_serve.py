"""`evh catalog-serve`'s output in the browser tests: its start-up lines, then everything after, read as it comes.

Left in the pipe after start-up, the access log (a line per API request) filled the pipe's buffer, the server blocked on
its next line and answered nothing more: a test that made a screen's worth more requests timed out in the steps after
it (2026-11-19).
"""

from __future__ import annotations

import subprocess
import threading


def startup(p: subprocess.Popen, lines: list[str]) -> list[str]:
    """Read `p`'s start-up lines into `lines`, up to its last, then keep reading the rest into it in the background."""
    assert p.stdout is not None
    while line := p.stdout.readline():
        lines.append(line.rstrip())
        if "rebuilt when the data changes" in line:
            break
    out = p.stdout

    def drain() -> None:
        for x in out:
            lines.append(x.rstrip())

    threading.Thread(target=drain, daemon=True).start()
    return lines
