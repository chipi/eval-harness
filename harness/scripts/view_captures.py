#!/usr/bin/env python3
"""evh captures: every capture, or one: what it read, when, how many records, scrubbed or not, and
the datasets made from it (RFC-019).

    evh captures
    evh captures --capture fleet_2026_10
    evh captures --json
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json

from evaluation_harness._common import dataset_id_ok, die, evh_prog
from evaluation_harness.model.dataset_views import capture_views


def main() -> int:
    """List captures, or show one."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--capture", help="show one capture")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args()
    rows = capture_views(check_format=False)
    if args.capture:
        ids = [c["capture"] for c in rows]
        if dataset_id_ok(args.capture) not in ids:
            die(
                f"no capture {args.capture!r}" + (f"; there are: {', '.join(ids)}" if ids else ""),
                "not-found",
            )
        rows = [c for c in rows if c["capture"] == args.capture]
    if args.json:
        print(json.dumps({"captures": rows}, indent=2))
        return 0
    if not rows:
        print("No captures (evh capture --importer ... --query ... --capture <id>).")
        return 0
    for c in rows:
        print(
            f"{c['capture']}: {c['records']} record(s) from {c['importer']}, captured {c['captured_at']}"
            + (" · scrubbed" if c["scrubbed"] else "")
        )
        if c["first"]:
            print(f"  records from {c['first']} to {c['last']}")
        if c["continues"]:
            print(f"  continues {c['continues']}")
        if c["sample"]:
            s = c["sample"]
            print(f"  a sample: rate {s['rate']}, seed {s['seed']} ({s.get('kept')} of {s.get('read')} read)")
        print(f"  datasets made from it: {', '.join(c['datasets']) or 'none'}")
        if args.capture:
            print(f"  query: {json.dumps(c['query'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
