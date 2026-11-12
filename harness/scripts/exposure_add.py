#!/usr/bin/env python3
"""Record reads of a held-out side's items in its exposure register (RFC-031 H1).

    evh exposure-add --dataset-id triage_v1_test --item 2026-11-08T18-45-12Z --what "decision and reason" \\
        --read-by agent:homelab --at 2026-11-11T09:00:00Z
    evh exposure-add --dataset-id triage_v1_test --from exposed.tsv

A read is anything that showed a person or an agent an item's content, or the system's output or a label on it: an
inspection, a sheet, a page, a file opened, a fixture written. Each read item is left out of every later score on that
side, with the count said (once read, always read). `--from` takes a TSV with a header naming `item_id` and `what`
(and, optionally, `by` and `at`). A person or an agent records; every row names who recorded it, and nobody removes
one. Only a held-out side (a dataset `dataset-split --seal` made) has a register.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import csv
import io
import sys
from collections import defaultdict
from pathlib import Path

from evaluation_harness import _exposure, _jsonout, _store
from evaluation_harness._common import die, evh_prog, load_dataset


def _from_tsv(path: Path) -> list[dict[str, str]]:
    if not _store.is_file(path):
        die(f"--from: no file {path}", "not-found")
    reader = csv.DictReader(io.StringIO(_store.read_text(path, encoding="utf-8")), delimiter="\t")
    cols = set(reader.fieldnames or [])
    if not {"item_id", "what"} <= cols:
        die(
            f"{path}: a TSV whose header names item_id and what (and optionally by, at); it has {sorted(cols)}",
            "invalid-file",
        )
    out = []
    for n, r in enumerate(reader, 2):
        if not (r.get("item_id") or "").strip() or not (r.get("what") or "").strip():
            die(f"{path}:{n}: item_id and what are both needed", "invalid-file")
        out.append({k: (r.get(k) or "").strip() for k in ("item_id", "what", "by", "at")})
    return out


def main() -> int:
    """Record reads."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True, help="the held-out side")
    ap.add_argument("--item", action="append", default=[], help="an item read (repeatable)")
    ap.add_argument("--what", help='what was read: "decision and reason", "label in a test fixture", ...')
    ap.add_argument("--at", help="when it was read (ISO 8601; default: now)")
    ap.add_argument(
        "--read-by", help="who read it: person:NAME or agent:NAME (default: who records it, as --by says)"
    )
    ap.add_argument(
        "--from", dest="tsv", type=Path, help="a TSV of reads (item_id, what, and optionally by, at)"
    )
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("exposure-add", args.json, live=sys.stderr):
        if not _exposure.applies(args.dataset_id):
            die(
                f"{args.dataset_id} is not a held-out side (no seal): only a dataset `dataset-split --seal` made has "
                "an exposure register",
                "not-allowed",
            )
        if args.tsv and (args.item or args.what):
            die("--from, or --item with --what: one of them", "bad-argument")
        if args.tsv:
            reads = _from_tsv(args.tsv)
        elif args.item and args.what:
            reads = [
                {"item_id": i, "what": args.what, "by": args.read_by or "", "at": args.at or ""}
                for i in args.item
            ]
        else:
            die("--item ID --what TEXT (repeatable --item), or --from FILE.tsv", "bad-argument")
        known = {str(it["item_id"]) for it in load_dataset(args.dataset_id)["items"]}
        unknown = sorted({r["item_id"] for r in reads} - known)
        if unknown:
            die(
                f"{len(unknown)} id(s) are not items of {args.dataset_id}; nothing recorded (a held-out side's ids "
                "are not printed: check them against the dataset)",
                "not-found",
            )
        groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        for r in reads:
            groups[(r["what"], r.get("by") or "", r.get("at") or "")].append(r["item_id"])
        added = 0
        for (what, by, at), items in groups.items():
            added += _exposure.record(args.dataset_id, items, what, by=by or None, at=at or None)
        total = len(_exposure.exposed(args.dataset_id))
        n_items = len(known)
        print(
            f"{args.dataset_id}: {added} read(s) recorded ({len(reads) - added} already in the register); "
            f"{total} of {n_items} item(s) now exposed, left out of every score on it"
        )
        _jsonout.values({"dataset_id": args.dataset_id, "added": added, "exposed": total, "items": n_items})
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
