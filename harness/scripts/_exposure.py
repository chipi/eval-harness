"""The exposure register of a sealed side (RFC-031 H1): which held-out items a person or an agent has read.

    data/exposure/<dataset_id>.jsonl   append-only, a row per read:
        {"item_id", "what", "at", "by", "recorded_at", "recorded_by", "source": "hand" | "harness"}

A seal (RFC-029) refuses runs, scores and labels on the held-out side; a read is none of those, and on the fleet's
triage set 78 of 91 sealed items were read (a comparison, a test fixture) before anyone noticed (2026-11-11). So a
read is recorded (by hand, `evh exposure-add`, or by the harness when one of its commands shows an item's content or
an output on it), and every score on that side leaves the read items out and says how many: once read, always read.
Nobody removes a row. A dataset that was never sealed has no register.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from evaluation_harness import _store
from evaluation_harness._common import die, now

DATASET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$")
#: Items left out of the scores this process computed, per dataset (the commands print it).
LEFT: dict[str, set[str]] = {}
#: --include-exposed: the scores keep the exposed items (a command shows that number beside the clean one, marked).
INCLUDE = [False]


def path(dataset_id: str) -> Path:
    """data/exposure/<dataset_id>.jsonl; the id is checked first, so it can never leave data/exposure/."""
    from evaluation_harness import _common  # noqa: PLC0415

    if not DATASET_ID.match(dataset_id or ""):
        die(f"not a dataset id: {dataset_id!r}", "bad-argument")
    return _common.DATA / "exposure" / f"{dataset_id}.jsonl"


_APPLIES: dict[str, bool] = {}


def applies(dataset_id: str | None) -> bool:
    """Whether a dataset is a held-out side (sealed now, or sealed and since unsealed); asked once per process."""
    from evaluation_harness import _seal  # noqa: PLC0415

    if not dataset_id:
        return False
    if dataset_id not in _APPLIES:
        _APPLIES[dataset_id] = bool(_seal.record_of(dataset_id).get("sealed"))
    return _APPLIES[dataset_id]


def rows(dataset_id: str) -> list[dict[str, Any]]:
    """Every row of a dataset's register, oldest first."""
    p = path(dataset_id)
    if not _store.is_file(p):
        return []
    return [json.loads(x) for x in _store.read_text(p, encoding="utf-8").splitlines() if x.strip()]


def exposed(dataset_id: str | None) -> frozenset[str]:
    """The item ids read on a held-out side (none for any other dataset). Read each time: a server that runs for days
    must leave out a read recorded after it started (a register is a few hundred lines)."""
    if not dataset_id or not applies(dataset_id):
        return frozenset()
    return frozenset(str(r.get("item_id")) for r in rows(dataset_id))


def _who(actor: dict[str, Any]) -> str:
    who = f"{actor.get('type')}:{actor.get('name')}"
    return who + (f" for person:{actor['for']}" if actor.get("for") else "")


def append(dataset_id: str, new: list[dict[str, Any]]) -> int:
    """Add rows (never rewritten), under the dataset's `exposure:<id>` lock: in the SQLite store an append is a read and
    a rewrite. Returns how many were added."""
    from evaluation_harness import _jobs  # noqa: PLC0415

    if not new:
        return 0
    p = path(dataset_id)
    _store.mkdir(p.parent, parents=True, exist_ok=True)
    key = f"exposure:{dataset_id}"
    held = key in (os.environ.get("EVH_LOCKS") or "").split(",")
    ctx = (
        contextlib.nullcontext()
        if held
        else _jobs.holding(
            [(key, True)], os.environ.get("EVH_JOB") or f"pid {os.getpid()}", _jobs.say_waiting
        )
    )
    with ctx, _store.open_file(p, "a", encoding="utf-8") as f:
        for r in new:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return len(new)


def record(
    dataset_id: str,
    items: Iterable[str],
    what: str,
    *,
    by: str | None = None,
    at: str | None = None,
    source: str = "hand",
) -> int:
    """Record reads of items on a held-out side; `by` the reader (default: this process's actor). A read already
    recorded for the same reader and what is not recorded twice."""
    from evaluation_harness._actor import actor  # noqa: PLC0415

    me = _who(actor())
    reader = by or me
    have = {(str(r.get("item_id")), r.get("by"), r.get("what")) for r in rows(dataset_id)}
    stamp = now()
    new = [
        {
            "item_id": str(i),
            "what": what,
            "at": at or stamp,
            "by": reader,
            "recorded_at": stamp,
            "recorded_by": me,
            "source": source,
        }
        for i in dict.fromkeys(str(i) for i in items)
        if (str(i), reader, what) not in have
    ]
    return append(dataset_id, new)


def read_by_harness(dataset_id: str | None, items: Iterable[str], what: str) -> None:
    """A harness command showed these items' content, or an output or label on them: on a held-out side, that is a
    read, recorded with this process's actor. Nothing for any other dataset."""
    items = list(items)
    if items and dataset_id and applies(dataset_id):
        record(dataset_id, items, what, source="harness")


def keep(dataset_id: str | None, item_ids: Iterable[str]) -> set[str] | None:
    """The items a score on `dataset_id` keeps: every one but the exposed (None: keep all). What it leaves out is
    counted in LEFT for the command to say."""
    gone = exposed(dataset_id)
    if not gone or INCLUDE[0]:
        return None
    ids = set(item_ids)
    out = ids & gone
    if out:
        LEFT.setdefault(str(dataset_id), set()).update(out)
    return ids - gone


def said() -> list[str]:
    """One line per dataset whose scores this process left exposed items out of."""
    return [
        f"{ds}: {len(ids)} item(s) left out (exposed: read on the held-out side; RFC-031)"
        for ds, ids in sorted(LEFT.items())
    ]


def line(dataset_id: str | None) -> str | None:
    """A held-out side's reads in one line, for its pages and `evh goals`; None for any other dataset."""
    if not dataset_id or not applies(dataset_id):
        return None
    from evaluation_harness._common import load_dataset  # noqa: PLC0415

    n = len(load_dataset(dataset_id).get("items") or [])
    read = len(exposed(dataset_id))
    return (
        f"held out: {read} of {n} item(s) read (the exposure register); every score here leaves them out "
        "(evh exposure)"
        if read
        else f"held out: none of its {n} item(s) read (evh exposure)"
    )


def say() -> None:
    """Print said() (to stdout, where the scores went)."""
    for line in said():
        print(f"  note: {line}")
