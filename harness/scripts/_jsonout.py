"""`--json` for the view commands (RFC-018): the printing path, collected.

    with collect("datasets") as out:      # under --json
        ...the command prints and draws its tables as always...
    # stdout then carries one object:
    # {"command": "datasets", "version": "0.5.0", "result": {"blocks": [{"lines": [...]},
    #   {"columns": [...], "rows": [{column: value}, ...]}]}}

A table's values are kept as they were before being turned into text, every other printed line as
a string, in the order printed. Because the JSON is collected from the same calls that print the
text, the two cannot disagree. 0.7.0 (RFC-013) gives each command its own result and schema and
retires this generic form.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import sys
from collections.abc import Iterator

from evaluation_harness._version import __version__

#: The collector in force, or None (a table prints as text).
_ACTIVE: _Collector | None = None


class _Collector:
    def __init__(self) -> None:
        self.blocks: list[dict] = []
        self.buf = io.StringIO()

    def flush(self) -> None:
        text = self.buf.getvalue()
        self.buf.seek(0)
        self.buf.truncate()
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if lines:
            self.blocks.append({"lines": lines})

    def table(self, heads: list, rows: list) -> None:
        self.flush()
        cols = [str(h) for h in heads]
        self.blocks.append({"columns": cols, "rows": [dict(zip(cols, map(_plain, r))) for r in rows]})


def _plain(v):
    """A JSON value: NaN and infinities (which JSON cannot carry) as null."""
    return None if isinstance(v, float) and not math.isfinite(v) else v


def table(heads: list, rows: list) -> bool:
    """Record a table under --json; False when no collector is in force (print it as text)."""
    if _ACTIVE is None:
        return False
    _ACTIVE.table(heads, rows)
    return True


def take_flag(argv: list[str]) -> tuple[list[str], bool]:
    """argv without --json, and whether it was there."""
    return [a for a in argv if a != "--json"], "--json" in argv


@contextlib.contextmanager
def collect(command: str) -> Iterator[None]:
    """Run the body with its printing collected, then print the envelope. A refusal raises through
    and prints nothing to stdout: its message is on stderr, as without --json."""
    global _ACTIVE
    c = _Collector()
    _ACTIVE = c
    try:
        with contextlib.redirect_stdout(c.buf):
            yield
    finally:
        _ACTIVE = None
    c.flush()
    sys.stdout.write(
        json.dumps(
            {"command": command, "version": __version__, "result": {"blocks": c.blocks}},
            ensure_ascii=False,
            default=str,
        )
        + "\n"
    )
