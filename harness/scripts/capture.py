#!/usr/bin/env python3
"""Capture records from a production system into data/captures/<capture>/ (RFC-019).

    evh capture --importer jsonl --query '{"path": "export.jsonl"}' --capture fleet_2026_10
    evh capture --importer fleet --query @query.json --capture fleet_2026_11 --since-capture fleet_2026_10
    evh capture --importer jsonl --query '{"path": "logs.jsonl"}' --capture logs_1101 --sample-rate 0.001 --seed 7

A capture is a candidate pool, never evidence: no run is scored on it. It records exactly what was
read: capture.json holds the importer, the sha256 of its code, the query verbatim and its window,
when, how many records, and per record its id, created_at, link, the sha256 of the whole record
(`sha256`) and of what would become the item (`body_sha256`); records/<id>.json holds each record.

--since-capture continues from an earlier capture: the query's `since` becomes that capture's
`until` (or its newest record's time), and records it already holds are skipped by id.

--sample-rate R --seed S keeps a share R of the records: those whose seeded hash of their id falls below R,
so the same rule draws the same sample again and an id keeps its side in every capture with that rule. It is
applied as the records arrive, so a source far larger than the sample is never held at once; the importer
receives it as its `sample` option ({"rate", "seed"}) and may sample at the source (a store's own query), and
every record it returns is checked against the rule. A continued capture keeps the earlier one's rule.

Every record must fall inside the window the capture records, [since, until): one outside it (an importer
that ignores `since`, or a record with no time) is named and nothing is written. --late keeps the records
older than `since` that the earlier capture does not hold (a record that became visible after it): they are
captured, and listed in capture.json as `late`.

Commit a capture (and what is made from it) before any billed run: an untracked capture marks
runs dirty, and a dirty run cannot be promoted or author a reference.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _importers, _store
from evaluation_harness._common import CAPTURES, dataset_id_ok, die, evh_prog, now, read_json, write_json
from evaluation_harness.importer_check import query_of


def earlier(capture_id: str) -> tuple[str | None, set, dict | None]:
    """(where an earlier capture ended, the ids it holds, its sample rule or None)."""
    doc = read_json(CAPTURES / dataset_id_ok(capture_id) / "capture.json")
    times = [r["created_at"] for r in doc.get("records") or [] if r.get("created_at")]
    end = (doc.get("window") or {}).get("until") or (max(times) if times else None)
    rule = doc.get("sample")
    return (
        end,
        {r["id"] for r in doc.get("records") or []},
        ({"rate": rule["rate"], "seed": rule["seed"]} if isinstance(rule, dict) else None),
    )


def main() -> int:
    """Read an importer's records and keep them as a capture."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument(
        "--importer", required=True, help="a built-in name, a project importer's name, or path.py:Class"
    )
    ap.add_argument("--query", required=True, help="the importer's query: JSON, or @file.json")
    ap.add_argument("--capture", required=True, help="the capture's id: lowercase_with_underscores")
    ap.add_argument("--since-capture", metavar="CAPTURE", help="continue from an earlier capture")
    ap.add_argument("--force", action="store_true", help="replace an existing capture of the same id")
    ap.add_argument(
        "--late",
        action="store_true",
        help="keep records older than the window's since, listed as late arrivals",
    )
    ap.add_argument(
        "--sample-rate", type=float, metavar="R", help="keep a share R (0 < R <= 1) of the records"
    )
    ap.add_argument(
        "--seed", type=int, help="with --sample-rate: the seed, so the same sample is drawn again"
    )
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    args = ap.parse_args()

    out = CAPTURES / dataset_id_ok(args.capture)
    sample = None
    if args.sample_rate is not None:
        if not 0 < args.sample_rate <= 1:
            die("--sample-rate is a share: more than 0, at most 1", "bad-argument")
        if args.seed is None:
            die("--sample-rate needs --seed, so the same sample can be drawn again", "bad-argument")
        sample = {"rate": args.sample_rate, "seed": args.seed}
    elif args.seed is not None:
        die("--seed goes with --sample-rate", "bad-argument")
    if _store.exists(out / "capture.json") and not args.force:
        die(
            f"{out} exists: a capture is not overwritten. Name a new one, or pass --force if nothing is made from it.",
            "would-overwrite",
        )
    query = query_of(args.query)
    seen: set = set()
    if args.since_capture:
        end, seen, rule = earlier(args.since_capture)
        if end:
            query = {**query, "since": end}
        if sample and rule and sample != rule:
            die(
                f"{args.since_capture} was captured with the sample {rule}: a continued capture keeps it",
                "mismatch",
            )
        sample = sample or rule
    n_read = 0
    try:
        recs, path = _importers.read(args.importer, query, {"sample": sample} if sample else None)
        raw = []
        for r in recs:
            n_read += 1
            if sample and not _importers.sampled(r.get("id") if isinstance(r, dict) else None, **sample):
                continue
            raw.append(r)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — the importer's own failure, named
        die(f"--importer {args.importer}: reading failed: {type(exc).__name__}: {exc}", "failed")
    bad = [p for r in raw for p in _importers.problems(r)]
    if bad:
        die(
            f"{len(bad)} malformed record(s), nothing written; `evh importer-check` says more:\n  "
            + "\n  ".join(bad[:10]),
            "invalid-file",
        )
    norm = [_importers.normalise(r) for r in raw if r["id"] not in seen]
    ids = [r["id"] for r in norm]
    if len(ids) != len(set(ids)):
        die("the importer yielded the same id twice; nothing written", "invalid-file")
    window = _importers.window_of(query)
    why = {r["id"]: _importers.outside(window, r["created_at"]) for r in norm}
    late = [i for i, w in why.items() if w == "before since"] if args.late else []
    out_of = {i: w for i, w in why.items() if w and i not in late}
    if out_of:
        die(
            f"{len(out_of)} record(s) outside the window {window}, nothing written: the importer must keep to "
            "since/until (evh importer-check tests it)"
            + (
                "; --late keeps the ones before since"
                if any(w == "before since" for w in out_of.values())
                else ""
            )
            + ":\n  "
            + "\n  ".join(f"{i}: {w}" for i, w in list(out_of.items())[:10]),
            "invalid-file",
        )

    if _store.exists(out):
        _store.rmtree(out)
    _store.mkdir(out / "records", parents=True)
    for r in norm:
        write_json(out / "records" / f"{r['id']}.json", r)
    doc = {
        "capture_id": args.capture,
        "importer": args.importer,
        "importer_sha256": _importers.code_sha256(path),
        "query": query,
        "window": window,
        "captured_at": now(),
        "n_records": len(norm),
        "skipped_as_already_captured": len(raw) - len(norm),
        **({"sample": {**sample, "read": n_read, "kept": len(raw)}} if sample else {}),
        "continues": args.since_capture,
        **({"late": late} if late else {}),
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
        + (f"; {len(late)} late (older than since)" if late else "")
        + (
            f"; a sample of {len(raw)} from {n_read} read (rate {sample['rate']}, seed {sample['seed']})"
            if sample
            else ""
        )
    )
    print("  commit it (and what you make from it) before any billed run: untracked data marks runs dirty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
