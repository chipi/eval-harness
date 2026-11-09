#!/usr/bin/env python3
"""A filled label sheet, or a folder of answers, as a person's label set (RFC-023).

    evh label-import sheet.csv --dataset-id tickets_v1 --set owner_2026_11 --by owner
    evh label-import sheet.csv --dataset-id tickets_v1 --set owner_2026_11 --by owner --guideline labelling.md
    evh label-import answers/ --dataset-id tickets_v1 --set owner_gold --by owner

A sheet: CSV as Excel saves it (UTF-8 with or without its mark, `,` or `;` between columns; a workbook is refused,
saying how to save it as CSV). Every row with a `label` becomes one label; `yes` takes the row's `proposal`; a row
with no label is left out; a row's `note` is kept beside its label. When more than one answer is right for an item,
`also right` names the others, separated by `|` (`file` and `escalate`: the label accepts either, written
{"accept": [...]}). When the label column's header names the allowed answers (`label-sheet --choices`), any other is
refused, naming its rows, and nothing is written. A folder: each `<item_id>.txt` in it is that item's label. The
set's source is `person`: who (`--by`), and the sheet's (or the folder's files') sha256. A set is never edited: a
second pass is a new set.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
import sys
from pathlib import Path

from evaluation_harness import _jsonout, _store
from evaluation_harness._common import die, evh_prog
from evaluation_harness._label_sets import answers, label_text, write_set
from evaluation_harness._sheets import ALSO, read_csv


def labels_from_rows(
    rows: list[dict[str, str]], choices: list[str] | None
) -> tuple[dict[str, str], dict[str, str]]:
    """({item: label}, {item: note}) from a filled sheet's rows (read_csv's): a row with no `label` is left out, `yes`
    takes the row's `proposal`, `also right` joins the others a label accepts. Refused, nothing read further, for
    a `yes` with no proposal and for an answer outside the sheet's `choices`."""
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
        die(
            f"`yes` with no proposal on {len(no_proposal)} row(s): {', '.join(no_proposal[:8])}",
            "invalid-file",
        )
    if choices:
        off = [(i, a) for i, t in labels.items() for a in answers(t) if a not in choices]
        if off:
            die(
                f"{len(off)} answer(s) not among the sheet's choices ({', '.join(choices)}): "
                + "; ".join(f"{i}: {a!r}" for i, a in off[:8])
                + (" ..." if len(off) > 8 else "")
                + ". Correct them in the sheet and import it again; nothing was written.",
                "invalid-file",
            )
    return labels, notes


def main() -> int:
    """Import a filled sheet as a person's label set."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument(
        "sheet",
        type=Path,
        help="the filled sheet (.csv, as label-sheet writes it), or a folder of <item_id>.txt",
    )
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--set", required=True, dest="name", help="the label set's name (lowercase, _ . -)")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap, required=True, help="who labelled, and so who acted (person:NAME, or a bare name)")
    ap.add_argument(
        "--guideline",
        type=Path,
        help="a file: the instructions the labeller followed (its path and sha256 are recorded)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("label-import", args.json, live=sys.stderr):
        if _store.is_dir(args.sheet):
            return _folder(args)
        if not _store.is_file(args.sheet):
            die(f"no sheet {args.sheet}", "not-found")
        rows, choices = read_csv(args.sheet)
        if not rows or "item_id" not in rows[0] or "label" not in rows[0]:
            die(
                f"{args.sheet}: a sheet has the columns item_id and label (evh label-sheet writes one)",
                "invalid-file",
            )
        labels, notes = labels_from_rows(rows, choices)
        source = {
            "kind": "person",
            "by": args.by,
            "sheet": args.sheet.name,
            "sheet_sha256": hashlib.sha256(_store.read_bytes(args.sheet)).hexdigest(),
        }
        doc = write_set(args.dataset_id, args.name, labels, source, args.guideline, notes)
        print(
            f"data/labels/{args.dataset_id}/{args.name}: {doc['n_items']} label(s) of {len(rows)} row(s), source person · {args.by}"
        )
        return 0


def _folder(args: argparse.Namespace) -> int:
    """A folder of answers a person wrote, one <item_id>.txt per item, as a person's label set."""
    files = sorted(_store.glob(args.sheet, "*.txt"))
    if not files:
        die(f"{args.sheet}: no <item_id>.txt in it", "invalid-file")
    labels = {p.stem: _store.read_text(p, encoding="utf-8") for p in files}
    digest = hashlib.sha256()
    for p in files:
        digest.update(p.name.encode() + b"\0" + _store.read_bytes(p))
    source = {"kind": "person", "by": args.by, "folder": args.sheet.name, "folder_sha256": digest.hexdigest()}
    doc = write_set(args.dataset_id, args.name, labels, source, args.guideline)
    print(
        f"data/labels/{args.dataset_id}/{args.name}: {doc['n_items']} label(s) from {len(files)} file(s), source person · {args.by}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
