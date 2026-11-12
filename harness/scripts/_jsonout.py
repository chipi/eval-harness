"""`--json` for the view commands (RFC-018): the printing path, collected.

    with collect("datasets") as out:      # under --json
        ...the command prints and draws its tables as always...
    # stdout then carries one object:
    # {"command": "datasets", "version": "0.5.0", "result": {"blocks": [{"lines": [...]},
    #   {"columns": [...], "rows": [{column: value}, ...]}]}}

A table's values are kept as they were before being turned into text, every other printed line as
a string, in the order printed. Because the JSON is collected from the same calls that print the
text, the two cannot disagree. 0.8.0 (RFC-013) gives each command its own result and schema and
retires this generic form.

A command that has key results (a p-value, a verdict, the run ids it wrote) hands them over by name
with `value(name, v)`; they sit beside the blocks as `result["values"]`, present only when a command
gave some. `collect(..., live=sys.stderr)` is for a command that takes long (`evh run`): what it
prints reaches the terminal as it happens, on stderr, and is collected into the blocks too.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import os
import sys
from collections.abc import Iterator

from evaluation_harness._version import __version__

#: The collector in force, or None (a table prints as text).
_ACTIVE: _Collector | None = None


class _Collector:
    def __init__(self) -> None:
        self.blocks: list[dict] = []
        self.values: dict = {}
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
        self.blocks.append({"columns": cols, "rows": [dict(zip(cols, map(_clean, r))) for r in rows]})


def _plain(v):
    """A JSON value: NaN and infinities (which JSON cannot carry) as null."""
    return None if isinstance(v, float) and not math.isfinite(v) else v


def _clean(v):
    """A JSON value all the way down: NaN and infinities as null, tuples and sets as lists."""
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (set, frozenset)):
        return [_clean(x) for x in sorted(v)]
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return _plain(v)


def table(heads: list, rows: list) -> bool:
    """Record a table under --json; False when no collector is in force (print it as text)."""
    if _ACTIVE is None:
        return False
    _ACTIVE.table(heads, rows)
    return True


def value(name: str, v) -> None:
    """Hand over a named result beside the printed blocks (`result["values"][name]`). Nothing when
    no collector is in force, so a command calls it whether or not it was asked for --json."""
    if _ACTIVE is not None:
        _ACTIVE.values[name] = _clean(v)


def values(named: dict) -> None:
    """`value` for each name in turn."""
    for name, v in named.items():
        value(name, v)


def take_flag(argv: list[str]) -> tuple[list[str], bool]:
    """argv without --json, and whether it was there."""
    return [a for a in argv if a != "--json"], "--json" in argv


class _Tee:
    """What a command prints: kept for the blocks, and passed on to `live` as it is written."""

    def __init__(self, buf: io.StringIO, live) -> None:
        self.buf, self.live = buf, live

    def write(self, text: str) -> int:
        self.live.write(text)
        return self.buf.write(text)

    def flush(self) -> None:
        self.live.flush()


def _say_exposed() -> None:
    """After a command's body: the held-out items its scores left out (RFC-031 H1), said once, wherever it printed,
    and under result.values.left_out_exposed. Every score that leaves them out says so, whichever command."""
    from evaluation_harness import _exposure, _runs  # noqa: PLC0415

    if _runs.NOT_SCORABLE:
        for cid, ids in sorted(_runs.NOT_SCORABLE.items()):
            print(
                f"  note: {cid}: {len(ids)} item(s) not scorable under this variant (its action differs from "
                "production's, under which their labels hold; RFC-031)"
            )
        if _ACTIVE is not None:
            _ACTIVE.values["not_scorable"] = {c: len(ids) for c, ids in sorted(_runs.NOT_SCORABLE.items())}
    if not _exposure.LEFT:
        return
    _exposure.say()
    if _ACTIVE is not None:
        _ACTIVE.values["left_out_exposed"] = {ds: len(ids) for ds, ids in sorted(_exposure.LEFT.items())}


@contextlib.contextmanager
def collect(command: str, enabled: bool = True, live=None) -> Iterator[None]:
    """Run the body with its printing collected, then print the envelope. A refusal raises through
    and prints nothing to stdout: its message is on stderr, as without --json. `enabled=False` runs
    the body as it is (a command writes `with collect(name, args.json):`). `live`: a stream the
    printing also goes to as it happens; file descriptor 1 is pointed at it for the body, so nothing
    a library or a child process writes to stdout can reach the envelope's stream."""
    global _ACTIVE
    if not enabled:
        yield
        _say_exposed()
        return
    c = _Collector()
    _ACTIVE = c
    saved_fd = None
    if live is not None:
        live.flush()
        sys.stdout.flush()
        try:
            saved_fd = os.dup(1)
            os.dup2(live.fileno(), 1)
        except (OSError, ValueError, AttributeError):  # a stream without a descriptor (a test's)
            saved_fd = None
    try:
        with contextlib.redirect_stdout(c.buf if live is None else _Tee(c.buf, live)):
            yield
            _say_exposed()
    finally:
        _ACTIVE = None
        if saved_fd is not None:
            os.dup2(saved_fd, 1)
            os.close(saved_fd)
    c.flush()
    result: dict = {"blocks": c.blocks}
    if c.values:
        result["values"] = c.values
    sys.stdout.write(
        json.dumps(
            {"command": command, "version": __version__, "result": result},
            ensure_ascii=False,
            default=str,
        )
        + "\n"
    )
