#!/usr/bin/env python3
"""Bring a project's data to this release's format (RFC-032), by its numbered steps.

    evh migrate --check       the data's format against this release's; exit 1 when they differ (a deploy's gate)
    evh migrate --dry-run     what each step would change; nothing written
    evh migrate               write it

The project's format is one number, `data/project.yaml`'s `format` (0 when it has none: the data releases before
0.8.0 wrote). Each step in `evaluation_harness.migrations` brings it one format on, and the format is recorded after
each, so a step that fails leaves the project at the last one that held. Before the first change a SQLite project's
database is copied beside it (the undo); a files project's undo is git, and uncommitted changes under data/ are named
first. There is no way back down: a rollback restores that copy, or git.

Moving the data between files and the SQLite database is `evh data-migrate`, not a format step.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import shutil
import subprocess  # nosec B404 - git status, read-only
import sys
import time

from evaluation_harness import _common, _format, _jsonout, _store, migrations
from evaluation_harness._common import evh_prog


def _backup() -> None:
    """The undo before the first change: a copy of the database, or the uncommitted changes named."""
    if _common.store() == "sqlite":
        db = _store.db_path()
        if db.is_file():
            _store.close()
            copy = db.with_name(
                f"{db.name}.before-format-{_format.FORMAT}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
            )
            shutil.copy2(db, copy)
            print(f"backup: {copy} (restore it to undo)")
        return
    try:
        out = subprocess.run(  # nosec B603 B607 - git, fixed arguments
            ["git", "status", "--porcelain", "--", str(_common.DATA)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            cwd=_common.DATA,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("backup: git not found; the files have no undo but a copy you make", file=sys.stderr)
        return
    if out.returncode != 0:
        print("backup: data/ is not in git; the files have no undo but a copy you make", file=sys.stderr)
    elif out.stdout.strip():
        n = len(out.stdout.splitlines())
        print(
            f"backup: {n} uncommitted change(s) under data/: git cannot tell them from the migration's",
            file=sys.stderr,
        )


def main() -> int:
    """Check the format, or run the steps the data needs."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    how = ap.add_mutually_exclusive_group()
    how.add_argument(
        "--check", action="store_true", help="only compare the data's format with this release's"
    )
    how.add_argument("--dry-run", action="store_true", help="say what each step would change; write nothing")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("migrate", args.json, live=sys.stderr):
        have = _format.data_format()
        _jsonout.values({"format": have, "release_format": _format.FORMAT})
        print(f"data format {have}; this release reads {_format.FORMAT}")
        if args.check or have > _format.FORMAT:
            _format.require()
            return 0
        todo = [m for m in migrations.steps() if have < m.NUMBER]
        if not todo:
            print("nothing to do")
            return 0
        if not args.dry_run:
            _backup()
        for m in todo:
            print(f"{m.NUMBER}: {m.ABOUT}")
            m.run(args.dry_run)
            if not args.dry_run:
                _format.stamp(m.NUMBER)
        print(f"{'would bring' if args.dry_run else 'brought'} the data to format {todo[-1].NUMBER}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
