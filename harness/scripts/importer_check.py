#!/usr/bin/env python3
"""Check an importer against the record contract: does what it reads make a valid capture?

    evh importer-check jsonl --query '{"path": "export.jsonl"}'
    evh importer-check fleet --query @query.json --limit 50

It reads the records twice and checks that every record is well-formed (an id that can be a file
name, a body or fields, a parsable created_at), that no id repeats, that both reads give the
same hashes (an importer whose records change between two reads cannot be captured), and that it
keeps to a window: every record inside the query's [since, until), and, when the query names no
since, a third read from the middle record's time on returns nothing older (`evh capture
--since-capture` relies on it). One PASS or FAIL line per check; exit 1 on any failure. Nothing is
written.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

from evaluation_harness import _importers
from evaluation_harness._common import EXIT_PROBLEMS, die, evh_prog


def query_of(text: str) -> dict:
    """A query given as JSON, or as @path to a JSON file."""
    try:
        q = json.loads(Path(text[1:]).read_text(encoding="utf-8") if text.startswith("@") else text)
    except (OSError, json.JSONDecodeError) as exc:
        die(f"--query: {exc}", "bad-argument")
    if not isinstance(q, dict):
        die("--query is a JSON object", "bad-argument")
    return q


def read_all(name: str, query: dict, limit: int | None) -> list:
    """The importer's records (at most `limit`), as it yields them."""
    try:
        recs, _ = _importers.read(name, query)
        return list(itertools.islice(recs, limit) if limit else recs)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — an importer's own failure is the check's answer
        die(f"--importer {name}: reading failed: {type(exc).__name__}: {exc}", "failed")


def main() -> int:
    """Check an importer; exit 1 on any failure."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("importer", help="a built-in name, a project importer's name, or path.py:Class")
    ap.add_argument("--query", required=True, help="the query: JSON, or @file.json")
    ap.add_argument("--limit", type=int, help="check only the first N records")
    args = ap.parse_args()
    query = query_of(args.query)
    first = read_all(args.importer, query, args.limit)
    second = read_all(args.importer, query, args.limit)

    failed = 0

    def line(ok: bool, label: str, detail: str = "") -> None:
        nonlocal failed
        failed += not ok
        print(f"  {'PASS' if ok else 'FAIL'} {label}" + (f": {detail}" if detail and not ok else ""))

    print(f"importer {args.importer}: {len(first)} record(s)")
    line(bool(first), "it yields records", "none")
    bad = [p for rec in first for p in _importers.problems(rec)]
    line(
        not bad,
        "every record is well-formed",
        "; ".join(bad[:5]) + (f" (+{len(bad) - 5})" if len(bad) > 5 else ""),
    )
    ids = Counter(r.get("id") for r in first if isinstance(r, dict))
    dupes = [i for i, n in ids.items() if n > 1]
    line(not dupes, "no id repeats", ", ".join(map(str, dupes[:5])))
    if not bad:
        h1 = [_importers.record_sha256(_importers.normalise(r)) for r in first]
        h2 = [_importers.record_sha256(_importers.normalise(r)) for r in second]
        line(h1 == h2, "two reads give the same records", f"{sum(a != b for a, b in zip(h1, h2))} differ")
        window = _importers.window_of(query)
        if window:
            out = [
                r["id"] for r in first if _importers.outside(window, _importers.normalise(r)["created_at"])
            ]
            line(
                not out,
                f"every record is inside the window {window}",
                f"{len(out)} outside: {', '.join(out[:5])}",
            )
        times = sorted(t for t in (_importers.normalise(r)["created_at"] for r in first) if t)
        if not query.get("since") and len(times) > 1:
            mid = times[len(times) // 2]
            probe = read_all(args.importer, {**query, "since": mid}, args.limit)
            old = [
                r["id"]
                for r in probe
                if _importers.outside({"since": mid}, _importers.normalise(r)["created_at"])
            ]
            line(
                not old,
                "it keeps to since (read again from the middle record's time)",
                f"{len(old)} older than {mid}: {', '.join(old[:5])}",
            )
    print("PASS" if not failed else f"FAIL: {failed} check(s)")
    return EXIT_PROBLEMS if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
