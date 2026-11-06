"""Run fixtures in the store the suite runs in (RFC-025): EVAL_RUNS_STORE, files by default.

What a test needs beyond `_outputs` and `_runs.item_rows`: raw rows text (a malformed line, an emptied file), every
line parsed, and a run copied with its outputs and rows. Where a run's data lives depends only on where the run is
(`_outputs.db_for`), so a fixture written here is the one the `evh` a test starts reads.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from evaluation_harness import _outputs


def sqlite() -> bool:
    """Whether the suite runs on the sqlite store."""
    return os.environ.get("EVAL_RUNS_STORE", "").strip() == "sqlite"


def put_rows_text(run_dir: Path, text: str, partial: bool = False) -> None:
    """A run's rows exactly as given, malformed lines included (a test of a reader's refusals)."""
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    _outputs.store().put_rows(Path(run_dir), text, partial)


def rows(run_dir: Path, partial: bool = False) -> list[dict[str, Any]]:
    """A run's rows, each non-blank line parsed (a row without an item id included)."""
    text = _outputs.rows_text(Path(run_dir), partial) or ""
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def drop_rows(run_dir: Path, partial: bool = False) -> None:
    """A run's rows (or its checkpoint) removed."""
    _outputs.store().drop_rows(Path(run_dir), partial)


def copy_run(src: Path, dst: Path) -> None:
    """A run copied, its directory and its outputs, rows and row checkpoint, wherever each run's store keeps them."""
    shutil.copytree(src, dst, dirs_exist_ok=True)
    st = _outputs.store()
    outs = st.lines(Path(src))
    if outs:
        st.write_all(Path(dst), {o["item_id"]: o["text"] for o in outs}, [o["item_id"] for o in outs])
    for partial in (False, True):
        text = st.rows_text(Path(src), partial)
        if text is not None:
            st.put_rows(Path(dst), text, partial)
