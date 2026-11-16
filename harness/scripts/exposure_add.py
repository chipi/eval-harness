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

import csv
import io
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluation_harness import _exposure, _jsonout, _store
from evaluation_harness._common import die, load_dataset
from evaluation_harness.ops import legacy


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


def body(**inputs: Any) -> int:
    """Record reads."""
    args = legacy.namespace(inputs, "exposure-add", {"from": "tsv"})
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
