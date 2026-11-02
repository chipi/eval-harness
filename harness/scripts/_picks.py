"""Picks (RFC-023, ADR-0023): production items marked as candidates for the next version of governed datasets.

One list per project, data/picks.jsonl, append-only: each line is an action on one item of one dataset —

    {"action": "pick", "item": ..., "from": <dataset>, "sha256": ..., "capture": ..., "for": [<datasets>],
     "tags": {...}, "note": ..., "by": ..., "at": ...}
    {"action": "drop", "item": ..., "from": ..., "by": ..., "at": ...}
    {"action": "used", "item": ..., "from": ..., "into": <dataset>, "at": ...}

The latest line for an item wins: picking it again retargets or retags it; a drop or a use takes it off the waiting
list; the history stays.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import json
from pathlib import Path
from typing import Any

from evaluation_harness._common import now


def picks_path() -> Path:
    """data/picks.jsonl (the project's)."""
    from evaluation_harness import _common  # noqa: PLC0415

    return _common.DATA / "picks.jsonl"


def lines() -> list[dict[str, Any]]:
    """Every line of the pick list, oldest first."""
    p = picks_path()
    if not p.is_file():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def append(rows: list[dict[str, Any]]) -> None:
    """Add lines to the pick list (it is never rewritten)."""
    p = picks_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({**r, "at": r.get("at") or now()}, ensure_ascii=False, sort_keys=True) + "\n")


def state() -> dict[tuple[str, str], dict[str, Any]]:
    """{(dataset, item): its latest line}: what each item's last action left."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for r in lines():
        out[(r.get("from", ""), r.get("item", ""))] = r
    return out


def waiting(for_dataset: str | None = None, tags: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """The picks waiting: the items whose latest line is a pick, for a target dataset and tags when given."""
    out = []
    for r in state().values():
        if r.get("action") != "pick":
            continue
        if for_dataset and for_dataset not in (r.get("for") or []):
            continue
        if tags and any((r.get("tags") or {}).get(k) != v for k, v in tags.items()):
            continue
        out.append(r)
    return sorted(out, key=lambda r: (r.get("from", ""), r.get("item", "")))
