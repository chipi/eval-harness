#!/usr/bin/env python3
"""A filled label sheet, or a folder of answers, as a person's label set (RFC-023).

    evh label-import sheet.csv --dataset-id tickets_v1 --set owner_2026_11 --by owner
    evh label-import sheet.csv --dataset-id tickets_v1 --set owner_2026_11 --by owner --guideline labelling.md
    evh label-import answers/ --dataset-id tickets_v1 --set owner_gold --by owner

A sheet: every row with a `label` becomes one label; `yes` takes the row's `proposal`; a row with no label is left
out; a row's `note` is kept beside its label. When more than one answer is right for an item, `also right` names
the others, separated by `|` (`file` and `escalate`: the label accepts either, written {"accept": [...]}). A folder: each `<item_id>.txt` in it is that item's label. The set's
source is `person`: who (`--by`), and the sheet's (or the folder's files') sha256. A set is never edited: a second
pass is a new set.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import csv
import hashlib
from pathlib import Path

from evaluation_harness._common import die
from evaluation_harness._label_sets import answers, label_text, write_set

#: The sheet's column for the other right answers of an item that has more than one, separated by |.
ALSO = "also right"


def main() -> int:
    """Import a filled sheet as a person's label set."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "sheet",
        type=Path,
        help="the filled sheet (.csv, as label-sheet writes it), or a folder of <item_id>.txt",
    )
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--set", required=True, dest="name", help="the label set's name (lowercase, _ . -)")
    ap.add_argument("--by", required=True, help="who labelled")
    ap.add_argument("--guideline", type=Path, help="the instructions the labeller followed")
    args = ap.parse_args()

    if args.sheet.is_dir():
        return _folder(args)
    if not args.sheet.is_file():
        die(f"no sheet {args.sheet}")
    with args.sheet.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows or "item_id" not in rows[0] or "label" not in rows[0]:
        die(f"{args.sheet}: a sheet has the columns item_id and label (evh label-sheet writes one)")
    labels, notes, no_proposal = {}, {}, []
    for r in rows:
        text = (r.get("label") or "").strip()
        if not text:
            continue
        if text.lower() == "yes":
            text = (r.get("proposal") or "").strip()
            if not text:
                no_proposal.append(r["item_id"])
                continue
        also = [a.strip() for a in (r.get(ALSO) or "").split("|") if a.strip()]
        labels[r["item_id"]] = label_text([*answers(text), *also]) if also else text
        if (r.get("note") or "").strip():
            notes[r["item_id"]] = r["note"].strip()
    if no_proposal:
        die(f"`yes` with no proposal on {len(no_proposal)} row(s): {', '.join(no_proposal[:8])}")
    source = {
        "kind": "person",
        "by": args.by,
        "sheet": args.sheet.name,
        "sheet_sha256": hashlib.sha256(args.sheet.read_bytes()).hexdigest(),
    }
    doc = write_set(args.dataset_id, args.name, labels, source, args.guideline, notes)
    print(
        f"data/labels/{args.dataset_id}/{args.name}: {doc['n_items']} label(s) of {len(rows)} row(s), source person · {args.by}"
    )
    return 0


def _folder(args: argparse.Namespace) -> int:
    """A folder of answers a person wrote, one <item_id>.txt per item, as a person's label set."""
    files = sorted(args.sheet.glob("*.txt"))
    if not files:
        die(f"{args.sheet}: no <item_id>.txt in it")
    labels = {p.stem: p.read_text(encoding="utf-8") for p in files}
    digest = hashlib.sha256()
    for p in files:
        digest.update(p.name.encode() + b"\0" + p.read_bytes())
    source = {"kind": "person", "by": args.by, "folder": args.sheet.name, "folder_sha256": digest.hexdigest()}
    doc = write_set(args.dataset_id, args.name, labels, source, args.guideline)
    print(
        f"data/labels/{args.dataset_id}/{args.name}: {doc['n_items']} label(s) from {len(files)} file(s), source person · {args.by}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
