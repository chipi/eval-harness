#!/usr/bin/env python3
"""Write the manifest of a reference built outside the harness (a fetch script's gold).

    evh reference-manifest --reference-id gold/<dataset> --source examples/<example>/fetch.py [--not-redistributed]

The manifest (schemas/reference.schema.json) holds the checksum of every item's text. It is
committed even when the text is not: anyone who rebuilds the reference proves they rebuilt the
same one (validate's V16). A reference made by `evh reference-create` already has one.
"""

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _common
from evaluation_harness._common import die, now
from evaluation_harness._references import write_manifest


def main() -> int:
    """Write the manifest of the named reference from the texts in its directory."""
    ap = argparse.ArgumentParser(
        prog="evh reference-manifest",
        description="Write the manifest of a reference built outside the harness.",
    )
    ap.add_argument("--reference-id", required=True, help="<tier>/<dataset_id>, e.g. gold/ag_news_200")
    ap.add_argument(
        "--source",
        required=True,
        help="how to rebuild its text, e.g. examples/classification-ag-news/fetch.py",
    )
    ap.add_argument(
        "--not-redistributed",
        action="store_true",
        help="the text is not committed (its licence, or the project's choice); the manifest is",
    )
    ap.add_argument(
        "--dataset-id",
        help="the dataset it is a reference for, when its name is not the dataset's (a second gold "
        "for one dataset, e.g. gold/ag_news_200_adj1 for ag_news_200); default: the name",
    )
    args = ap.parse_args()
    tier, _, name = args.reference_id.partition("/")
    if tier not in ("gold", "silver") or not name:
        die(f"--reference-id {args.reference_id!r}: expected gold/<name> or silver/<name>")
    dataset_id = args.dataset_id or name
    ref_dir = _common.DATA / "references" / tier / name
    if not any(ref_dir.glob("*.txt")):
        die(f"{ref_dir} has no reference texts: build them first ({args.source})")
    doc = write_manifest(
        ref_dir,
        tier,
        dataset_id,
        source=args.source,
        redistributed=not args.not_redistributed,
        created_at=now(),
    )
    print(f"{ref_dir / 'manifest.json'}  ({doc['n_items']} item(s), tier={tier})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
