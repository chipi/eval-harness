#!/usr/bin/env python3
"""Bring a project's data to this release's formats, once (idempotent).

    evh migrate --dry-run     what each step would change; nothing written
    evh migrate               write it

The steps, in this order; each changes nothing on data already in its format, so a second run changes nothing:

  runs          a run's outputs/ folder of <item>.txt becomes one outputs.jsonl (RFC-024)
  datasets      a dataset record's version from its lineage, its source block from its profile (PLAN_0.8.0 E1, E3)
  records       baselines per goal in versions, an actor on every record, split.split_by (RFC-027)
  fingerprints  a run's fingerprint at version 5, and the fingerprint_hash its baseline carries (RFC-021)

The records step comes before the fingerprints step: a baseline's hash is updated where the records step puts it.
Moving the data between files and the SQLite database is `evh data-migrate`, not a format step.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import sys

from evaluation_harness import _jsonout, baselines_migrate, dataset_migrate, fingerprint_migrate, run_migrate
from evaluation_harness._common import evh_prog

STEPS = (
    ("runs", run_migrate.step),
    ("datasets", dataset_migrate.step),
    ("records", baselines_migrate.step),
    ("fingerprints", fingerprint_migrate.step),
)


def main() -> int:
    """Run every step in order."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="say what each step would change; write nothing")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("migrate", args.json, live=sys.stderr):
        for name, step in STEPS:
            print(f"{name}:")
            step(args.dry_run)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
