"""How far a job's command has got, for the job's record (RFC-032: a job reports progress as it goes).

    _progress.step(done, total)      in a command's loop: items (or arms) done of how many

Written atomically to the file the job's supervisor names (EVH_PROGRESS_LIVE, read by `_common`), as {done, total, at};
nothing outside a job. `_jobs.read` puts it in the job's record beside what it has spent.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

from evaluation_harness import _common


def step(done: int, total: int | None) -> None:
    """`done` of `total` (None when the total is not known)."""
    if not _common.PROGRESS_LIVE:
        return
    with contextlib.suppress(OSError):
        tmp = Path(_common.PROGRESS_LIVE + ".tmp")
        tmp.write_text(json.dumps({"done": int(done), "total": total, "at": _common.now()}) + "\n")
        os.replace(tmp, _common.PROGRESS_LIVE)
