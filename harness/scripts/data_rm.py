#!/usr/bin/env python3
"""Delete a setting, or a whole run, from the project's data, in either store (UXS-004: the data page's delete).

    evh data-rm goals/old_goal.yaml --dry-run   what would go
    evh data-rm goals/old_goal.yaml             the setting
    evh data-rm runs/arm_v1_20261106T101010Z    the run: its record, outputs, scores and rows

Anything else under data/ is written by the harness's own commands and is refused here. A delete cannot be undone.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _data_page, _jsonout
from evaluation_harness._common import evh_prog


def main() -> int:
    """Delete a setting or a run."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument(
        "path", help="a setting (goals/x.yaml) or a run's folder (runs/<run id>), relative to data/"
    )
    ap.add_argument("--dry-run", action="store_true", help="say what would go; delete nothing")
    ap.add_argument("--json", action="store_true", help="the answer as one JSON object")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    args = ap.parse_args()
    try:
        with _jsonout.collect("data-rm", args.json):
            norm, _ = _data_page.resolve(args.path)
            if args.dry_run:
                kind = _data_page.deletable(norm)  # refuses what remove would refuse, deleting nothing
                if kind == "run":
                    s = _data_page.run_summary(norm)
                    print(
                        f"would delete the run {norm}: {s['files']} file(s), {s['outputs']} output(s), {s['rows']} row(s)"
                    )
                    _jsonout.value("would_delete", s)
                else:
                    print(f"would delete {norm}")
                    _jsonout.value("would_delete", {"path": norm})
                return 0
            gone = _data_page.remove(norm)
            if gone["kind"] == "run":
                print(
                    f"deleted the run {norm}: {gone['files']} file(s), {gone['outputs']} output(s), {gone['rows']} row(s)"
                )
            else:
                print(f"deleted {norm}")
            _jsonout.value("deleted", gone)
    except _data_page.Refused as exc:
        _data_page.refuse(exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
