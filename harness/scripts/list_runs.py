#!/usr/bin/env python3
"""List runs with the three things that make a number mean something (the baselines: evh baselines).

python scripts/list_runs.py
python scripts/list_runs.py --json
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _jsonout
from evaluation_harness._common import (
    BOOKKEEPING_PREFIXES,
    data_rel,
    how,
    read_json,
)
from evaluation_harness._runs import runs_on


def _common_prog() -> str | None:
    """`evh <command>` for --help (see _common.evh_prog)."""
    from evaluation_harness._common import evh_prog  # noqa: PLC0415

    return evh_prog()


def _shown(scores: dict) -> dict:
    """The scores a person reads: all but the bookkeeping ones."""
    return {k: v for k, v in sorted(scores.items()) if not k.startswith(BOOKKEEPING_PREFIXES)}


_RUN_COLUMNS = [
    "run_id",
    "config_id",
    "dataset_id",
    "created_at",
    "build_ref",
    "dirty",
    "directory",
    "scores",
]


def main() -> int:
    """List the runs."""
    ap = argparse.ArgumentParser(prog=_common_prog(), description=__doc__.splitlines()[0])
    ap.add_argument(
        "--json",
        action="store_true",
        help="the same answer as one JSON object: one row per run, with its scores as numbers",
    )
    args = ap.parse_args()
    with _jsonout.collect("runs-list", args.json):
        return _runs()


def _runs() -> int:
    dirs = [d for d, _m in runs_on()]
    if not dirs:
        print(
            "no runs yet — "
            + how("start with `evh run --system <id> --dataset <id>` (docs/GUIDE.md)", "try:  make demo")
        )
        _jsonout.table(_RUN_COLUMNS, [])
        _jsonout.values({"kind": "runs", "count": 0})
        return 0
    metrics = [(d, read_json(d / "metrics.json")) for d in dirs]
    _jsonout.values({"kind": "runs", "count": len(metrics)})
    if _jsonout.table(
        _RUN_COLUMNS,
        [
            [
                m["run_id"],
                m.get("config_id"),
                m["dataset_id"],
                m.get("created_at"),
                m["build"].get("ref"),
                bool(m["build"].get("dirty")),
                data_rel(d),
                _shown(m["scores"]),
            ]
            for d, m in metrics
        ],
    ):
        return 0
    print(f"{'run_id':44} {'dataset_id':18} {'build':14} scores")
    for _d, m in metrics:
        scores = "  ".join(f"{k}={v}" for k, v in _shown(m["scores"]).items())
        dirty = "*" if m["build"].get("dirty") else " "
        print(f"{m['run_id']:44} {m['dataset_id']:18} {m['build'].get('ref', '?')[:12]}{dirty} {scores}")
    print("\n  * = produced by a dirty tree; its build ref does not describe what ran")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
