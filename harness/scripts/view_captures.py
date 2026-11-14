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

from evaluation_harness import _store
from evaluation_harness._common import CAPTURES, DATASETS, dataset_id_ok, die, evh_prog, read_json


def summary(capture_id: str, made: dict, root: _Path | None = None) -> dict:
    """One capture, as the view shows it."""
    doc = read_json((root or CAPTURES) / capture_id / "capture.json")
    times = sorted(r["created_at"] for r in doc.get("records") or [] if r.get("created_at"))
    return {
        "capture": capture_id,
        "importer": doc.get("importer"),
        "captured_at": doc.get("captured_at"),
        "window": doc.get("window") or {},
        "records": doc.get("n_records"),
        "first": times[0] if times else None,
        "last": times[-1] if times else None,
        "continues": doc.get("continues"),
        "scrubbed": bool(doc.get("scrubbed")),
        "sample": doc.get("sample"),
        "datasets": made.get(capture_id, []),
        "query": doc.get("query") or {},
    }


def listing(data_dir: _Path | None = None) -> list[dict]:
    """Every capture under a data tree (default: the project's), with the datasets made from each: what `evh
    captures` prints and the catalog's Captures page shows."""
    caps = data_dir / "captures" if data_dir else CAPTURES
    dsets = data_dir / "datasets" if data_dir else DATASETS
    made: dict = {}
    for f in sorted(_store.glob(dsets, "*.json")) if _store.is_dir(dsets) else []:
        cap = (read_json(f).get("made_from") or {}).get("capture")
        if cap:
            made.setdefault(cap, []).append(f.stem)
    ids = sorted(p.parent.name for p in _store.glob(caps, "*/capture.json")) if _store.is_dir(caps) else []
    return [summary(i, made, caps) for i in ids]


def main() -> int:
    """List captures, or show one."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--capture", help="show one capture")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args()
    rows = listing()
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
