#!/usr/bin/env python3
"""Run the project's own scrubber over a capture's records, and record it (RFC-019).

    evh capture-scrub fleet_2026_10 --command "python signal-fleet/mvp/scrub.py --dir {records}"

{records} is replaced by the capture's records folder; the scrubber edits the JSON files in place.
The records are re-hashed afterwards: capture.json keeps each record's new `sha256` and
`body_sha256`, and the old hash as `sha256_before_scrub`, and records the command, the sha256 of
every file it names, when, and how many records changed. If the scrubber fails, or leaves a record
that is not valid JSON or no longer the same record, the records are put back as they were and
nothing is recorded.

The harness claims nothing about what a scrubber missed.
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
from evaluation_harness._common import CAPTURES, ROOT, dataset_id_ok, die, now, read_json, write_json


def _label(arg: str) -> str:
    """A file the command names, as the capture records it: relative to the project, or its name."""
    p = Path(arg).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.name


def main() -> int:
    """Scrub a capture's records with the project's command."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("capture", help="the capture's id")
    ap.add_argument("--command", required=True, help="the scrubber; {records} is the records folder")
    args = ap.parse_args()
    if "{records}" not in args.command:
        die("--command must name {records}, the folder the scrubber works on")
    base = CAPTURES / dataset_id_ok(args.capture)
    if not (base / "capture.json").is_file():
        die(f"no capture {args.capture!r} at {base}")
    doc = read_json(base / "capture.json")
    records = base / "records"
    argv = [a.replace("{records}", str(records)) for a in shlex.split(args.command)]
    with tempfile.TemporaryDirectory() as td:
        backup = Path(td) / "records"
        shutil.copytree(records, backup)

        def restore(why: str) -> None:
            shutil.rmtree(records)
            shutil.copytree(backup, records)
            die(f"{why}; the records are as they were, nothing recorded")

        r = subprocess.run(argv, capture_output=True, text=True)
        if r.returncode != 0:
            restore(f"the scrubber exited {r.returncode}: {(r.stderr or r.stdout).strip()[-300:]}")
        changed = 0
        for entry in doc["records"]:
            f = records / f"{entry['id']}.json"
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                restore(f"{f.name} is not valid JSON after scrubbing")
            if not isinstance(rec, dict) or rec.get("id") != entry["id"] or _importers.problems(rec):
                restore(f"{f.name} is no longer the same well-formed record after scrubbing")
            new = _importers.record_sha256(rec)
            if new != entry["sha256"]:
                changed += 1
                entry.setdefault("sha256_before_scrub", entry["sha256"])
                entry["sha256"] = new
                entry["body_sha256"] = _importers.body_sha256(rec)
    # Keyed relative to the project (never a machine's absolute path in a committed file).
    named = {_label(a): hashlib.sha256(Path(a).read_bytes()).hexdigest() for a in argv if Path(a).is_file()}
    doc["scrubbed"] = {
        "command": args.command,
        "files_sha256": named,
        "at": now(),
        "records_changed": changed,
    }
    write_json(base / "capture.json", doc)
    print(f"{base}: scrubbed, {changed} of {len(doc['records'])} record(s) changed")
    if r.stdout.strip():
        print("  the scrubber said:", r.stdout.strip().splitlines()[-1][:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
