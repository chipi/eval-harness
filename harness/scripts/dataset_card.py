#!/usr/bin/env python3
"""A dataset's card: what it is, where it came from and the datasheet's answers; or the same as Croissant 1.1.

    evh dataset-card --dataset-id D                         the card, as text
    evh dataset-card --dataset-id D --format croissant      Croissant 1.1 JSON-LD on stdout
    evh dataset-card --dataset-id D --format croissant --creator "Ada L." --out D.croissant.json
    evh dataset-card --dataset-id D --format hf-readme --out README.md     a Hugging Face dataset README

The Croissant document maps the record (name, description, version, licence, source url, made at, parent, the card as
`rai:` properties), its files (the record itself and the items, each with its sha256) and one record set of the
items (id and fields from the record, text from its file). A required property the record cannot give (a creator,
a url, a licence) is left out and named on stderr; nothing is invented. Read-only.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json

from evaluation_harness import _card, _croissant, _fields, _hf_readme, _licences, _store
from evaluation_harness._common import DATASETS, dataset_id_ok, die, evh_prog, read_json, write_text_atomic


def _text(record: dict) -> str:
    """The card as a reader reads it: what, where from, then each answered question."""
    src = record.get("source") or {}
    lic = record.get("licence")
    lines = [
        f"{record['dataset_id']}  version {record.get('version')}  ({len(record.get('items') or [])} items)",
        record.get("description") or "",
        "licence: " + (f"{lic}  {_licences.url(lic) or ''}".rstrip() if lic else "(not given)"),
        "source: "
        + (
            "  ".join(str(x) for x in (src.get("provider"), src.get("ref"), src.get("url")) if x)
            or "(not recorded)"
        )
        + (f"  revision {src['revision']}" if src.get("revision") else ""),
    ]
    card = record.get("card") or {}
    lines.append(f"\ncard: {len(card)} of {len(_card.QUESTIONS)} questions answered")
    for k, q in _card.QUESTIONS.items():
        if k in card:
            lines.append(f"  {q}\n    {card[k]}")
    if len(card) < len(_card.QUESTIONS):
        lines.append("  answer the rest: evh dataset-describe --card-template, then --card FILE")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Print a dataset's card, or write it as Croissant."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--format", choices=("text", "croissant", "hf-readme"), default="text")
    ap.add_argument(
        "--creator", help="with --format croissant: who made the dataset (a record has no creator)"
    )
    ap.add_argument("--out", type=_Path, help="write to this file instead of stdout")
    args = ap.parse_args()
    f = DATASETS / f"{dataset_id_ok(args.dataset_id)}.json"
    if not _store.is_file(f):
        die(f"no dataset {args.dataset_id!r} (evh datasets lists them)", "not-found")
    record = read_json(f)
    if args.format == "text":
        out = _text(record)
    elif args.format == "hf-readme":
        out = _hf_readme.readme(record)
    else:
        fs = _fields.load_fieldset(record["fieldset"]) if record.get("fieldset") else None
        types = {x["name"]: x["type"] for x in (fs or {}).get("fields") or []}
        doc, missing = _croissant.export(record, f, record.get("source_dir") or "", types, args.creator)
        out = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        if missing:
            print(
                f"{args.dataset_id}: Croissant asks for {', '.join(missing)}, which the record does not give: left out"
                + (" (--creator names who made it)" if "creator" in missing else ""),
                file=_sys.stderr,
            )
    if args.out:
        write_text_atomic(args.out, out)
        print(f"wrote {args.out}")
    else:
        print(out, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
