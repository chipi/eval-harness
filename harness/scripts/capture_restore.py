#!/usr/bin/env python3
"""Rebuild a capture's record files from its source, checked against what it recorded (RFC-019).

    evh capture-restore --capture orrery_2026_10
    evh capture-restore --capture orrery_2026_10 --query path=exports/decisions.jsonl --query verdicts=exports/verdicts.jsonl

A capture commits capture.json and, often, not its records/ (they can hold what a repository must not).
This reads them again: the importer capture.json names, with the query it recorded (--query KEY=VALUE
replaces one key: the same files somewhere else, e.g. a download), the same sample rule, and only the ids
it holds. A capture that was scrubbed has its recorded scrubber run again. Every record must then have the
sha256 capture.json records; one that differs or is missing is named and nothing is written. The records
are written to a folder beside records/ first and renamed into place, so records/ is whole or untouched.

Then the item files of every dataset made from the capture (`made_from.capture`, under its source_dir, which
git does not hold either) are written from the records, each checked against the dataset's source_sha256; an
item from another capture (a version made with --from) is counted and left to that capture's restore.

An existing records/ whose files already match is not rewritten; one that does not match is replaced only
with --force.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from evaluation_harness import _importers
from evaluation_harness._common import (
    CAPTURES,
    DATASETS,
    ROOT,
    dataset_id_ok,
    die,
    evh_prog,
    read_json,
    write_json,
)


def overrides(pairs: list[str]) -> dict:
    """--query KEY=VALUE pairs as a dict; a VALUE that parses as JSON is taken as JSON, else as text."""
    out: dict = {}
    for p in pairs:
        key, sep, raw = p.partition("=")
        if not sep or not key.strip():
            die(f"--query {p!r}: KEY=VALUE, e.g. --query path=exports/decisions.jsonl", "bad-argument")
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw
        out[key.strip()] = value
    return out


def mismatched(records: Path, entries: list[dict], key: str = "sha256") -> list[str]:
    """The ids whose file in `records` is missing or whose hash is not the entry's `key`."""
    bad = []
    for e in entries:
        f = records / f"{e['id']}.json"
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad.append(e["id"])
            continue
        if _importers.record_sha256(rec) != e.get(key, e["sha256"]):
            bad.append(e["id"])
    return bad


def named(ids: list[str], why: str) -> str:
    """'3 record(s) <why>, e.g. a, b, c'."""
    return f"{len(ids)} record(s) {why}, e.g. {', '.join(ids[:5])}"


def dataset_files(capture_id: str, recs: dict) -> tuple[list[tuple[Path, bytes]], list[str], list[str]]:
    """For every dataset made from the capture: (the item files to write, the items that differ from the
    dataset's hashes, one line per dataset). Nothing is written here."""
    writes: list[tuple[Path, bytes]] = []
    bad: list[str] = []
    said: list[str] = []
    for f in sorted(DATASETS.glob("*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict) or (doc.get("made_from") or {}).get("capture") != capture_id:
            continue
        src = ROOT / doc["source_dir"]
        here = other = 0
        for it in doc.get("items") or []:
            rec = recs.get(it["item_id"])
            if rec is None:
                other += 1
                continue
            body = rec["body"] if rec.get("body") is not None else rec["fields"]
            data = _importers.canonical(body)
            if hashlib.sha256(data).hexdigest() != it.get("source_sha256"):
                bad.append(f"{doc['dataset_id']}/{it['item_id']}")
                continue
            writes.append((src / it["source_path"], data))
            here += 1
        said.append(
            f"  {doc['dataset_id']}: {here} item file(s) to {doc['source_dir']}"
            + (f"; {other} item(s) from another capture, not restored here" if other else "")
        )
    return writes, bad, said


def main() -> int:
    """Read a capture's records again and keep them only if every hash matches."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--capture", required=True, help="the capture's id")
    ap.add_argument(
        "--query",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="replace one key of the recorded query (repeatable), e.g. path=exports/decisions.jsonl",
    )
    ap.add_argument("--force", action="store_true", help="replace a records/ whose files do not match")
    args = ap.parse_args()

    base = CAPTURES / dataset_id_ok(args.capture)
    if not (base / "capture.json").is_file():
        die(f"no capture {args.capture!r} at {base}", "not-found")
    doc = read_json(base / "capture.json")
    entries = doc.get("records") or []
    records = base / "records"
    if records.is_dir() and any(records.iterdir()) and mismatched(records, entries) and not args.force:
        die(
            f"{records} exists and does not match capture.json ({named(mismatched(records, entries), 'differ')}). "
            "Pass --force to replace it with the records read again.",
            "would-overwrite",
        )

    query = {**(doc.get("query") or {}), **overrides(args.query)}
    rule = doc.get("sample")
    sample = {"rate": rule["rate"], "seed": rule["seed"]} if isinstance(rule, dict) else None
    try:
        recs, path = _importers.read(doc["importer"], query, {"sample": sample} if sample else None)
        wanted = {e["id"] for e in entries}
        got = {}
        for r in recs:
            if isinstance(r, dict) and r.get("id") in wanted and r["id"] not in got:
                got[r["id"]] = _importers.normalise(r)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — the importer's own failure, named
        die(
            f"--capture {args.capture}: the importer {doc['importer']} failed: {type(exc).__name__}: {exc}",
            "failed",
        )
    code_note = (
        ""
        if _importers.code_sha256(path) == doc.get("importer_sha256")
        else f"  note: {path} is not the code that captured it (sha256 differs); the record hashes decide\n"
    )

    missing = sorted(wanted - set(got))
    if missing:
        die(
            f"{code_note}{named(missing, 'not returned by the importer for this query')}; nothing written",
            "mismatch",
        )
    tmp = Path(tempfile.mkdtemp(prefix=".records.partial-", dir=base))
    try:
        for rid, rec in got.items():
            write_json(tmp / f"{rid}.json", rec)
        bad = mismatched(tmp, entries, "sha256_before_scrub")
        if bad:
            die(
                f"{code_note}{named(bad, 'differ from what the capture recorded')}; nothing written",
                "mismatch",
            )
        scrub = (doc.get("scrubbed") or {}).get("command")
        if scrub:
            argv = [a.replace("{records}", str(tmp)) for a in shlex.split(scrub)]
            proc = subprocess.run(argv, capture_output=True, text=True)
            if proc.returncode != 0:
                die(
                    f"the recorded scrubber exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[-300:]}",
                    "failed",
                )
            bad = mismatched(tmp, entries)
            if bad:
                die(
                    f"{named(bad, 'differ from what the capture recorded after its scrubber ran')}; nothing written",
                    "mismatch",
                )
        # The datasets were cut from the records as kept (scrubbed, when they were): checked from those,
        # every one before anything is written.
        final = {e["id"]: read_json(tmp / f"{e['id']}.json") for e in entries}
        writes, bad_items, said = dataset_files(args.capture, final)
        if bad_items:
            die(
                f"{len(bad_items)} dataset item(s) differ from their dataset's hashes, e.g. "
                f"{', '.join(bad_items[:5])}; nothing written",
                "mismatch",
            )
        if records.exists():
            shutil.rmtree(records)
        tmp.rename(records)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for dest, data in writes:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    print(
        f"{code_note}capture {args.capture}: {len(entries)} records restored to {records}, hashes ok"
        + (" (scrubbed again with the recorded command)" if scrub else "")
    )
    print("\n".join(said) if said else "  no dataset is made from it")
    if said:
        print("next: evh dataset-materialize --dataset-id <each>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
