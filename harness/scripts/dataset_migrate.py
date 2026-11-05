#!/usr/bin/env python3
"""Bring the project's dataset records to this release's format, once (idempotent).

    evh dataset-migrate --dry-run     what would change, per dataset
    evh dataset-migrate               write it

0.8.0 (PLAN_0.8.0 E3): each record's `version` is recomputed from its lineage (MAJOR.MINOR: 1.0 made from
nothing or a side of a split; from a parent, MINOR + 1 when items were only added, MAJOR + 1 when any was removed or
changed), parents first, and a split side records its parent's version. The items, and so every run measured on
them, are untouched: neither key is in a run's fingerprint. `validate` (V22) then holds the records to it.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
from typing import Any

from evaluation_harness import _dataset_version
from evaluation_harness._common import DATASETS, evh_prog, read_json, write_json


def _order(docs: dict[str, dict[str, Any]]) -> list[str]:
    """Dataset ids, every parent before the datasets made from it (a parent that is gone counts as a root)."""

    def parent(i: str) -> str | None:
        d = docs[i]
        p = (d.get("split") or {}).get("from") or (d.get("derived_from") or {}).get("dataset_id")
        return p if p in docs and p != i else None

    out: list[str] = []
    seen: set[str] = set()
    for i in sorted(docs):
        chain = []
        while i and i not in seen:
            seen.add(i)
            chain.append(i)
            i = parent(i)  # type: ignore[assignment]
        out.extend(reversed(chain))
    return out


def migrate(docs: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """The records brought to the format, in place: {dataset_id: [what changed]} for those that changed."""
    changes: dict[str, list[str]] = {}

    def version_of(i: str | None) -> str | None:
        return (docs.get(i) or {}).get("version") if i else None

    for i in _order(docs):
        d, said = docs[i], []
        if d.get("split"):
            pv = version_of(d["split"].get("from"))
            if d["split"].get("from_version") != pv:
                d["split"]["from_version"] = pv
                said.append(f"split.from_version {pv}")
        v = _dataset_version.expected(d, version_of)
        if d.get("version") != v:
            said.append(f"version {d.get('version')!r} -> {v}")
            d["version"] = v
        if said:
            changes[i] = said
    return changes


def main() -> int:
    """Migrate every dataset record under data/datasets/."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print what would change; write nothing")
    args = ap.parse_args()
    files = {f.stem: f for f in sorted(DATASETS.glob("*.json"))} if DATASETS.is_dir() else {}
    docs = {i: read_json(f) for i, f in files.items()}
    changes = migrate(docs)
    for i, said in changes.items():
        print(f"{i}: {'; '.join(said)}")
        if not args.dry_run:
            write_json(files[i], docs[i])
    verb = "would change" if args.dry_run else "changed"
    print(f"{len(files)} dataset(s), {len(changes)} {verb}" + ("" if changes else ": already in this format"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
