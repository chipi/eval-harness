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
import contextvars
import io
import json
import math
import os
import sys
import threading
from collections.abc import Iterator

from evaluation_harness._console import dump_json
from evaluation_harness._version import __version__

# The call's, not the process's: the MCP server answers calls at once, in threads of one process.
#: The collector in force, or None (a table prints as text).
_ACTIVE: contextvars.ContextVar[_Collector | None] = contextvars.ContextVar("evh_collector", default=None)
#: Where this call's printing goes while `capture` holds it; None: the stdout `_Routed` stands in for.
_OUT: contextvars.ContextVar[io.StringIO | None] = contextvars.ContextVar("evh_stdout", default=None)
_ROUTING = threading.Lock()


class _Routed:
    """sys.stdout while calls are captured: a call's printing goes to that call's buffer, anything else to the stdout
    this stands in for. `redirect_stdout` swaps the one stdout every thread prints to: two calls at once printed into
    each other's answers."""

    def __init__(self, base) -> None:
        self.base = base

    def _to(self):
        out = _OUT.get()
        return self.base if out is None else out

    def write(self, text: str) -> int:
        return self._to().write(text)

    def flush(self) -> None:
        self._to().flush()

    def __getattr__(self, name: str):
        return getattr(self._to(), name)


@contextlib.contextmanager
def printing_to(buf: io.StringIO) -> Iterator[None]:
    """The body's printing goes to `buf`, and only this call's: another thread prints where it did."""
    with _ROUTING:
        if not isinstance(sys.stdout, _Routed):
            sys.stdout = _Routed(sys.stdout)
    token = _OUT.set(buf)
    try:
        yield
    finally:
        _OUT.reset(token)


@contextlib.contextmanager
def own_notes() -> Iterator[None]:
    """The body's notes (held-out items left out, items not scorable, history confounds) start empty and are its own:
    a process that answers many calls is not a process per call."""
    from evaluation_harness import _exposure, _runs  # noqa: PLC0415

    left, not_scorable, confound = (
        _exposure._LEFT.set({}),
        _runs._NOT_SCORABLE.set({}),
        _runs._CONFOUND.set({}),
    )
    try:
        yield
    finally:
        _runs._CONFOUND.reset(confound)
        _runs._NOT_SCORABLE.reset(not_scorable)
        _exposure._LEFT.reset(left)


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

    def result(self) -> dict:
        """What the command answered: the printed lines and tables in order, and its named values when it gave some."""
        out: dict = {"blocks": self.blocks}
        if self.values:
            out["values"] = self.values
        return out


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


def plain(v):
    """A view's data as JSON holds it, which is what its resource gives: NaN and infinities as null, tuples and sets as
    lists, a date as its text."""
    return json.loads(json.dumps(_clean(v), default=str))


def table(heads: list, rows: list) -> bool:
    """Record a table under --json; False when no collector is in force (print it as text)."""
    c = _ACTIVE.get()
    if c is None:
        return False
    c.table(heads, rows)
    return True


def value(name: str, v) -> None:
    """Hand over a named result beside the printed blocks (`result["values"][name]`). Nothing when
    no collector is in force, so a command calls it whether or not it was asked for --json."""
    c = _ACTIVE.get()
    if c is not None:
        c.values[name] = _clean(v)


def values(named: dict) -> None:
    """`value` for each name in turn."""
    for name, v in named.items():
        value(name, v)


class _Tee:
    """What a command prints: kept for the blocks, and passed on to `live` as it is written."""

    def __init__(self, buf: io.StringIO, live) -> None:
        self.buf, self.live = buf, live

    def write(self, text: str) -> int:
        self.live.write(text)
        return self.buf.write(text)

    def flush(self) -> None:
        self.live.flush()

    def isatty(self) -> bool:
        """What is collected is no terminal, whatever `live` is (a body that asks before it line-buffers)."""
        return False


def _say_exposed() -> None:
    """After a command's body: the held-out items its scores left out (RFC-031 H1), said once, wherever it printed,
    and under result.values.left_out_exposed. Every score that leaves them out says so, whichever command."""
    from evaluation_harness import _exposure, _runs  # noqa: PLC0415

    active = _ACTIVE.get()
    not_scorable, confound, left = _runs.not_scorable(), _runs.confound(), _exposure.left()
    if not_scorable:
        for cid, ids in sorted(not_scorable.items()):
            print(
                f"  note: {cid}: {len(ids)} item(s) not scorable under this variant (its action differs from "
                "production's, under which their labels hold; RFC-031)"
            )
        if active is not None:
            active.values["not_scorable"] = {c: len(ids) for c, ids in sorted(not_scorable.items())}
    for cid, hc in sorted(confound.items()):
        print(
            f"  note: {cid}: history confound: {hc['items']} of {hc['of']} item(s) met a human reaction to an action "
            "production took and this variant did not (RFC-031)"
        )
    if confound and active is not None:
        active.values["history_confound"] = dict(sorted(confound.items()))
    if not left:
        return
    _exposure.say()
    if active is not None:
        active.values["left_out_exposed"] = {ds: len(ids) for ds, ids in sorted(left.items())}


@contextlib.contextmanager
def capture() -> Iterator[_Collector]:
    """Run the body in this process with its printing collected and hand the answer back (`.result()`), where `collect`
    prints it as an envelope: how an operation answers a call (RFC-032 step 9). Its printing, its collector and its
    notes are its own, whatever else the process answers at the same time."""
    c = _Collector()
    token = _ACTIVE.set(c)
    try:
        with own_notes(), printing_to(c.buf):
            yield c
            _say_exposed()
    finally:
        _ACTIVE.reset(token)
    c.flush()


@contextlib.contextmanager
def collect(command: str, enabled: bool = True, live=None) -> Iterator[None]:
    """Run the body with its printing collected, then print the envelope. A refusal raises through
    and prints nothing to stdout: its message is on stderr, as without --json. `enabled=False` runs
    the body as it is (a command writes `with collect(name, args.json):`). `live`: a stream the
    printing also goes to as it happens; file descriptor 1 is pointed at it for the body, so nothing
    a library or a child process writes to stdout can reach the envelope's stream."""
    if not enabled:
        yield
        _say_exposed()
        return
    c = _Collector()
    token = _ACTIVE.set(c)
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
        _ACTIVE.reset(token)
        if saved_fd is not None:
            os.dup2(saved_fd, 1)
            os.close(saved_fd)
    c.flush()
    result = c.result()
    sys.stdout.write(
        dump_json({"command": command, "version": __version__, "result": result}, default=str) + "\n"
    )
