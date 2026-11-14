"""Baselines per goal, in versions written once (RFC-027 D2).

    data/baselines/<goal_id>/<dataset_id>/<n>.json      a goal's baseline on a dataset, version n
    data/baselines/_dataset/<dataset_id>/<n>.json       a dataset's own (a run with no goal), goal null

The current one is the highest n (compared as numbers). A promotion or a rollback writes n + 1 and never touches n;
the write is exclusive (`_store.create_new`), so two promotions at once land as n + 1 and n + 2, the second computed
against the first. Every reader of a baseline reads it here.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness._common import die

NO_GOAL = "_dataset"


def root(data_dir: Path | None = None) -> Path:
    """The baselines folder of a data root."""
    return (Path(data_dir) / "baselines") if data_dir else _common.BASELINES


def folder(goal: str | None, dataset: str, data_dir: Path | None = None) -> Path:
    """Where a goal's (or, with no goal, the dataset's own) versions on a dataset live."""
    return root(data_dir) / (goal or NO_GOAL) / dataset


def _read(p: Path) -> dict[str, Any] | None:
    try:
        doc = json.loads(_store.read_text(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def versions(goal: str | None, dataset: str, data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Every version of one line, oldest first (by number: 10 after 9)."""
    d = folder(goal, dataset, data_dir)
    if not _store.is_dir(d):
        return []
    out = []
    for p in _store.glob(d, "*.json"):
        if p.stem.isdigit() and (doc := _read(p)) is not None:
            out.append(doc | {"version": int(p.stem)})
    return sorted(out, key=lambda x: x["version"])


def current(goal: str | None, dataset: str, data_dir: Path | None = None) -> dict[str, Any] | None:
    """The current version of one line (the highest), or None."""
    vs = versions(goal, dataset, data_dir)
    return vs[-1] if vs else None


def lines(data_dir: Path | None = None) -> list[tuple[str | None, str]]:
    """Every (goal or None, dataset) with at least one version, sorted."""
    r = root(data_dir)
    if not _store.is_dir(r):
        return []
    out = []
    for g in sorted(_store.iterdir(r)):
        if not _store.is_dir(g):
            continue
        for ds in sorted(_store.iterdir(g)):
            if _store.is_dir(ds) and any(p.stem.isdigit() for p in _store.glob(ds, "*.json")):
                out.append((None if g.name == NO_GOAL else g.name, ds.name))
    return out


def all_current(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """The current version of every line."""
    return [c for g, ds in lines(data_dir) if (c := current(g, ds, data_dir)) is not None]


def all_versions(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Every version of every line, each marked `current`."""
    out = []
    for g, ds in lines(data_dir):
        vs = versions(g, ds, data_dir)
        out += [v | {"current": v is vs[-1]} for v in vs]
    return out


def of_run(run_id: str, data_dir: Path | None = None) -> list[dict[str, Any]]:
    """The current versions whose run is `run_id` (a run can be the baseline of several goals)."""
    return [b for b in all_current(data_dir) if b.get("promoted_from") == run_id]


def write_next(
    goal: str | None,
    dataset: str,
    make: Callable[[dict[str, Any] | None, int], dict[str, Any]],
    data_dir: Path | None = None,
    tries: int = 20,
) -> dict[str, Any]:
    """Write the next version: `make(current, n)` builds it against the current version; when another writer took n
    first, it is built again against theirs. Returns the version written."""
    d = folder(goal, dataset, data_dir)
    _store.mkdir(d, parents=True, exist_ok=True)
    for _ in range(tries):
        cur = current(goal, dataset, data_dir)
        n = (cur["version"] + 1) if cur else 1
        doc = make(cur, n)
        doc["version"] = n
        text = json.dumps(doc, indent=2, sort_keys=True) + "\n"  # as write_json writes every record
        if _store.create_new(d / f"{n}.json", text.encode("utf-8")):
            return doc
    die(
        f"baselines/{goal or NO_GOAL}/{dataset}: {tries} writers took the next version first; try again",
        "failed",
    )
    raise AssertionError  # unreachable: die exits
