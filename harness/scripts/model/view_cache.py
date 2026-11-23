"""What a view reads from the data, kept for as long as the data is what it was read from (RFC-032 step 9).

A process that answers more than one view (catalog-serve's API, MCP in the server's process, a notebook) used to read
every arm's scores, and index every run, again for each question: 2 s of a 2 s view. This keeps them, once, per process.

A kept value is valid for one STATE, the tuple a lookup compares before it reuses anything:

- the data root, the project's store and the code's version (a test that moves the project, a store changed by
  data-migrate, a new release in the same process);
- `_store.generation()`, which every write through the store bumps (`Entity.save`, the operations' writes,
  `model.runs.write_*`, the migrations: all of them write through `_store`, in either store), so this process's own
  write clears it at once, and the sqlite store's `data_version`, which does not move for a process's own writes, is
  not what this depends on;
- the data's fingerprint (`_store.fingerprint`, the one catalog-serve's FRESH reads): another process's write. A look
  is due after `begin()`, which every entry point calls (one operation, one request, one command); in the sqlite store
  it costs 0.02 ms, so it is taken at every lookup, and in the files store (a stat of every entry, ~25 ms) once per
  `begin()`. What it covers: the data directory and the goals directory when it is elsewhere, and the project's
  config.yaml and .gitignore, which decide which runs are read.

Bounded: every entry says what it weighs (`weigh`: the number of per-item values for scores, else 1), the total stays
under BUDGET (least recently used out first), and a value heavier than the whole budget is not kept. A value built for
an older epoch (a slow reader that a write overtook) is returned to its caller and never kept. What `get` returns is
shared: a caller only reads it. One thread computes a value at a time: another that asks for it meanwhile waits for it
(two callers of a server asking for the same view at once pay for one computation, not two on the same CPU).
"""

from __future__ import annotations

import contextlib
import json
import os
import pickle  # nosec B403 - the answers this process kept, never bytes from elsewhere
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterator
from datetime import date
from pathlib import Path
from typing import Any, TypeVar

from evaluation_harness import _common, _store, _visibility
from evaluation_harness._version import __version__

T = TypeVar("T")

#: The most the kept values may weigh, in per-item scores (a dict slot, a float and its key: ~72 bytes measured, 1.39
#: million scores of this repository's 266 arms are ~100 MB of a 162 MB process). A catalog that does not fit gets no
#: speed from it, LRU being the worst policy for a view that reads every arm in turn, and is still answered right;
#: `EVH_VIEW_CACHE_VALUES` sets it for a process with less room (the public inspector's 384 MB container).
BUDGET = int(os.environ.get("EVH_VIEW_CACHE_VALUES", "2000000"))
#: Off for a process that asks it (tests that compare a view with and without the cache; EVH_VIEW_CACHE=0).
ON = os.environ.get("EVH_VIEW_CACHE", "1") != "0"

_LOCK = threading.RLock()
_LOCAL = threading.local()
_ITEMS: OrderedDict[Hashable, tuple[Any, int]] = OrderedDict()
#: The keys being computed now, each with the event its computer sets when it is done (under _LOCK).
_FLIGHT: dict[Hashable, threading.Event] = {}
#: [the state the items were read in, the fingerprint last taken, the epoch, the total weight, a look is due]
_HELD: list[Any] = [None, None, 0, 0, True]
_STATE, _PRINT, _EPOCH, _WEIGHT, _DUE = range(5)
#: What the cache did since the process started (under _LOCK): a value given from it, one computed, a call that waited for
#: another's computation, a value dropped for room, everything dropped because the data changed.
_COUNTS = {"hit": 0, "miss": 0, "wait": 0, "eviction": 0, "invalidation": 0}


def _state() -> tuple:
    return (str(_common.DATA), _common.store(), __version__, _store.generation())


def _print() -> tuple:
    """The data's fingerprint, and the project's own files that change what is read."""
    roots = [_common.DATA]
    goals = getattr(_common, "GOALS", None)
    if goals is not None and not Path(goals).resolve().is_relative_to(Path(_common.DATA).resolve()):
        roots.append(Path(goals))
    seen: list[Any] = [_store.fingerprint(r)[:2] for r in roots]
    for name in ("config.yaml", ".gitignore"):
        try:
            st = _store.stat(_common.ROOT / name)
            seen.append((st.st_mtime_ns, st.st_size))
        except OSError:
            seen.append(None)
    return tuple(seen)


def begin() -> None:
    """A new operation, request or command starts: the data is looked at again before anything kept is reused. Inside
    an `operation()` it does nothing: that one already asked."""
    if getattr(_LOCAL, "depth", 0):
        return
    with _LOCK:
        _HELD[_DUE] = True


@contextlib.contextmanager
def operation() -> Iterator[None]:
    """One operation, request or command: the data is looked at once, before anything kept is used (a stat of every
    entry in the files store, ~25 ms), however many views it starts."""
    begin()
    _LOCAL.depth = getattr(_LOCAL, "depth", 0) + 1
    try:
        yield
    finally:
        _LOCAL.depth -= 1


def clear() -> None:
    """Everything forgotten (a new epoch)."""
    with _LOCK:
        _ITEMS.clear()
        _HELD[_STATE] = _HELD[_PRINT] = None
        _HELD[_WEIGHT] = 0
        _HELD[_EPOCH] += 1
        _HELD[_DUE] = True
        _COUNTS["invalidation"] += 1


def _sync() -> int:
    """The epoch the data is in now: a new one (everything dropped) when the state or the data changed since the items
    were read. Under the lock."""
    state = _state()
    if _HELD[_STATE] != state:
        clear()
        _HELD[_STATE] = state
        _HELD[_PRINT] = _print()
        _HELD[_DUE] = False
    elif _HELD[_DUE] or _common.store() == "sqlite":
        _HELD[_DUE] = False
        seen = _print()
        if seen != _HELD[_PRINT]:
            clear()
            _HELD[_STATE] = state
            _HELD[_PRINT] = seen
            _HELD[_DUE] = False
    return int(_HELD[_EPOCH])


def epoch() -> int:
    """The epoch the data is in now; a value built in an earlier one is not kept."""
    with _LOCK:
        return _sync()


def get(
    key: Hashable,
    compute: Callable[[], T],
    weigh: Callable[[T], int] | None = None,
    epoch_of: int | None = None,
) -> T:
    """The value kept under `key`, else `compute()`, kept. `weigh`: what the value weighs against BUDGET (default 1).
    `epoch_of`: the epoch a caller's own state (an adapter) was made in; a value is kept only while it is still the
    current one. Never raises for the cache: when it is off, `compute` is the answer."""
    if not ON:
        return compute()
    while True:
        with _LOCK:
            now = _sync()
            if key in _ITEMS:
                _ITEMS.move_to_end(key)
                _COUNTS["hit"] += 1
                return _ITEMS[key][0]
            flying = _FLIGHT.get(key)
            if flying is None:
                _FLIGHT[key] = mine = threading.Event()
                _COUNTS["miss"] += 1
                break
            _COUNTS["wait"] += 1
        flying.wait()  # another thread computes it: look again when it is done (it keeps it, or it failed and this one tries)
    try:
        value = compute()
        weight = max(1, weigh(value)) if weigh else 1
        with _LOCK:
            if _HELD[_EPOCH] != (now if epoch_of is None else epoch_of) or weight > BUDGET:
                return value
            if key in _ITEMS:
                _HELD[_WEIGHT] -= _ITEMS.pop(key)[1]
            _ITEMS[key] = (value, weight)
            _HELD[_WEIGHT] += weight
            while _HELD[_WEIGHT] > BUDGET and len(_ITEMS) > 1:
                _HELD[_WEIGHT] -= _ITEMS.popitem(last=False)[1][1]
                _COUNTS["eviction"] += 1
        return value
    finally:
        with _LOCK:
            _FLIGHT.pop(key, None)
        mine.set()


def result(name: str, args: dict[str, Any], compute: Callable[[], T]) -> T:
    """An operation's answer, kept for as long as the data is what it was computed from, and given back as a copy: kept
    pickled (its size is its weight, one per 64 bytes), so a caller that changes what it was given changes nothing kept,
    and a hit is a new object equal to what `compute()` returns. Keyed by the operation, its inputs, the day (a view that
    counts back from today is another view tomorrow) and the public mode; what refuses is raised, never kept."""
    if not ON:
        return compute()
    box: list[T] = []

    def build() -> bytes | None:
        box.append(compute())
        try:
            return pickle.dumps(box[0], pickle.HIGHEST_PROTOCOL)
        except Exception:  # noqa: BLE001 -- an answer that cannot be pickled is given, not kept
            return None

    key = (
        "result",
        name,
        json.dumps(args, sort_keys=True, default=str),
        date.today().toordinal(),
        _visibility.public(),
    )
    blob = get(key, build, weigh=lambda b: len(b or b"") // 64 + 1)
    if box:  # this call computed it: the caller gets what was computed, as without the cache
        return box[0]
    if blob is None:
        return compute()
    return pickle.loads(blob)  # noqa: S301  # nosec B301 - this process's own bytes


def weight() -> int:
    """What is kept weighs this much against BUDGET."""
    with _LOCK:
        return int(_HELD[_WEIGHT])


def stats() -> dict[str, Any]:
    """What the cache holds and has done since the process started, for a deployment's metrics: its entries, their
    weight and the budget, and how many hits, misses (computed), waits, evictions and invalidations."""
    with _LOCK:
        return {
            "on": ON,
            "entries": len(_ITEMS),
            "weight": int(_HELD[_WEIGHT]),
            "budget": BUDGET,
            **_COUNTS,
        }
