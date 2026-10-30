#!/usr/bin/env python3
"""Capture records from a production system into data/captures/<capture>/ (RFC-019).

    evh capture --importer jsonl --query '{"path": "export.jsonl"}' --capture fleet_2026_10
    evh capture --importer fleet --query @query.json --capture fleet_2026_11 --since-capture fleet_2026_10

A capture is a candidate pool, never evidence: no run is scored on it. It records exactly what was
read: capture.json holds the importer, the sha256 of its code, the query verbatim and its window,
when, how many records, and per record its id, created_at, link, the sha256 of the whole record
(`sha256`) and of what would become the item (`body_sha256`); records/<id>.json holds each record.

--since-capture continues from an earlier capture: the query's `since` becomes that capture's
`until` (or its newest record's time), and records it already holds are skipped by id.

Commit a capture (and what is made from it) before any billed run: an untracked capture marks
runs dirty, and a dirty run cannot be promoted or author a reference.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import shutil

from evaluation_harness import _importers
from evaluation_harness._common import CAPTURES, dataset_id_ok, die, now, read_json, write_json
from evaluation_harness.importer_check import query_of


def earlier(capture_id: str) -> tuple[str | None, set]:
    """(where an earlier capture ended, the ids it holds)."""
    doc = read_json(CAPTURES / dataset_id_ok(capture_id) / "capture.json")
    times = [r["created_at"] for r in doc.get("records") or [] if r.get("created_at")]
    end = (doc.get("window") or {}).get("until") or (max(times) if times else None)
    return end, {r["id"] for r in doc.get("records") or []}


def main() -> int:
    """Read an importer's records and keep them as a capture."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--importer", required=True, help="a built-in name, a project importer's name, or path.py:Class"
    )
    ap.add_argument("--query", required=True, help="the importer's query: JSON, or @file.json")
    ap.add_argument("--capture", required=True, help="the capture's id: lowercase_with_underscores")
    ap.add_argument("--since-capture", metavar="CAPTURE", help="continue from an earlier capture")
    ap.add_argument("--force", action="store_true", help="replace an existing capture of the same id")
    args = ap.parse_args()

    out = CAPTURES / dataset_id_ok(args.capture)
    if (out / "capture.json").exists() and not args.force:
        die(
            f"{out} exists: a capture is not overwritten. Name a new one, or pass --force if nothing is made from it."
        )
    query = query_of(args.query)
    seen: set = set()
    if args.since_capture:
        end, seen = earlier(args.since_capture)
        if end:
            query = {**query, "since": end}
    try:
        recs, path = _importers.read(args.importer, query)
        raw = list(recs)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — the importer's own failure, named
        die(f"--importer {args.importer}: reading failed: {type(exc).__name__}: {exc}")
    bad = [p for r in raw for p in _importers.problems(r)]
    if bad:
        die(
            f"{len(bad)} malformed record(s), nothing written; `evh importer-check` says more:\n  "
            + "\n  ".join(bad[:10])
        )
    norm = [_importers.normalise(r) for r in raw if r["id"] not in seen]
    ids = [r["id"] for r in norm]
    if len(ids) != len(set(ids)):
        die("the importer yielded the same id twice; nothing written")

    if out.exists():
        shutil.rmtree(out)
    (out / "records").mkdir(parents=True)
    for r in norm:
        write_json(out / "records" / f"{r['id']}.json", r)
    doc = {
        "capture_id": args.capture,
        "importer": args.importer,
        "importer_sha256": _importers.code_sha256(path),
        "query": query,
        "window": _importers.window_of(query),
        "captured_at": now(),
        "n_records": len(norm),
        "skipped_as_already_captured": len(raw) - len(norm),
        "continues": args.since_capture,
        "records": [
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "url": (r["source"] or {}).get("url"),
                "sha256": _importers.record_sha256(r),
                "body_sha256": _importers.body_sha256(r),
            }
            for r in norm
        ],
    }
    write_json(out / "capture.json", doc)
    print(
        f"{out}: {len(norm)} record(s) from {args.importer}"
        + (
            f" ({doc['skipped_as_already_captured']} already in {args.since_capture})"
            if args.since_capture
            else ""
        )
    )
    print("  commit it (and what you make from it) before any billed run: untracked data marks runs dirty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
