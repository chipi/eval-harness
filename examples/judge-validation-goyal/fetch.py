#!/usr/bin/env python3
"""Bring back the texts of `goyal2022_cnn_v1` and of its gold reference, which the repository does not redistribute.

    python examples/judge-validation-goyal/fetch.py [--dataset-id goyal2022_cnn_v1]
    evh dataset-materialize --dataset-id goyal2022_cnn_v1

The dataset's record, its reference's manifest (the checksum of each text) and the runs are committed; the articles and
summaries (CNN's, via Goyal, Li & Durrett 2022, CC BY 4.0) and the annotators' ranks are not. This reads the archive
through the source (`source.py`, pinned by its sha256), writes each item's text under data/sources/<dataset>/ and its
reference under data/references/gold/<dataset>/, and `evh validate` (V4, V16) checks every one against the committed
hashes: a text that is not the one the dataset was frozen on is a different dataset.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[1] / "harness"
sys.path.insert(0, str(HARNESS))
os.environ.setdefault("EVAL_HOME", str(HARNESS))
sys.path.insert(0, str(HERE))

from evaluation_harness import _store  # noqa: E402
from evaluation_harness._common import DATA  # noqa: E402
from source import Source  # noqa: E402


def main() -> int:
    """Write the items and the gold reference of the dataset from the archive."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", default="goyal2022_cnn_v1")
    ap.add_argument(
        "--query", default="{}", help='the source\'s query as JSON (e.g. a local archive: {"file": ...})'
    )
    args = ap.parse_args()
    import json  # noqa: PLC0415

    sources, golds = DATA / "sources" / args.dataset_id, DATA / "references" / "gold" / args.dataset_id
    for d in (sources, golds):
        _store.mkdir(d, parents=True, exist_ok=True)
    n = 0
    for it in Source({}).items(json.loads(args.query)):
        _store.write_text(sources / f"{it['item_id']}.txt", it["text"], encoding="utf-8")
        _store.write_text(
            golds / f"{it['item_id']}.txt", it["answer"] + "\n", encoding="utf-8"
        )  # as reference-promote writes it
        n += 1
    print(
        f"{n} items written: {sources}\n  gold {golds}\nNext: evh dataset-materialize --dataset-id {args.dataset_id}"
    )
    return 0


if __name__ == "__main__":
    from evaluation_harness._console import degrade_unencodable

    degrade_unencodable()
    raise SystemExit(main())
