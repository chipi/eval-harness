#!/usr/bin/env python3
"""A source's labels from verdicts.jsonl, one file per item, for `evh label-import`.

    python examples/triage-fleet/labels_from_verdicts.py --dataset-id orrery_triage_v1_labelled \\
        --verdicts data/sources/orrery_triage_v1.hf/verdicts.jsonl --source owner --out owner_labels/
    evh label-import owner_labels --dataset-id orrery_triage_v1_labelled --set owner_verdicts --by owner
    evh reference-promote --dataset-id orrery_triage_v1_labelled --labels owner_verdicts --tier gold \\
        --reason "the owner's verdicts are what the arms are judged by" --by owner

`--source owner` takes the owner's rows (owner-issue-verdict, owner-item-label); `--source fixture` the fleet's own
earlier hand labels. Each item's text is its label: file, dismiss, escalate or cleanup, or both right answers of an
issue fixed later, which verdicts.jsonl publishes as file-or-escalate: {"accept": ["escalate", "file"]} (filing and
escalating were both right). An item no row of the source labels gets no file. The tier is not this script's: a label
set is promoted on purpose, at the tier chosen then (ADR-0022). Run from the project (harness/); it never overwrites a
folder.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "harness"))
from evaluation_harness._common import die, load_dataset  # noqa: E402
from evaluation_harness._label_sets import label_text  # noqa: E402

SOURCES = {"owner": ("owner-issue-verdict", "owner-item-label"), "fixture": ("fixture",)}
#: The published verdicts' words for an item with more than one right answer.
ACCEPT = {"file-or-escalate": ["file", "escalate"]}


def main() -> int:
    """Write the chosen source's labels, one <item_id>.txt per labelled item."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--verdicts", type=Path, required=True, help="verdicts.jsonl (Hugging Face, fetched)")
    ap.add_argument("--source", choices=tuple(SOURCES), default="owner")
    ap.add_argument("--out", type=Path, required=True, help="the folder to write, for evh label-import")
    args = ap.parse_args()
    if args.out.exists():
        die(f"{args.out} exists: write the labels to a new folder")
    ds = load_dataset(args.dataset_id)
    want = SOURCES[args.source]
    label: dict[str, str] = {}
    for r in (json.loads(x) for x in args.verdicts.read_text(encoding="utf-8").splitlines() if x.strip()):
        if r["source"] in want:
            if r["id"] in label and label[r["id"]] != r["label"]:
                die(f"{r['id']}: two labels from {args.source} ({label[r['id']]}, {r['label']})")
            label[r["id"]] = r["label"]
    items = [it["item_id"] for it in ds["items"]]
    hit = [i for i in items if i in label]
    if not hit:
        die(f"no item of {args.dataset_id} has a {args.source} label")
    args.out.mkdir(parents=True)
    for i in hit:
        (args.out / f"{i}.txt").write_text(
            label_text(ACCEPT.get(label[i], [label[i]])) + "\n", encoding="utf-8"
        )
    counts: dict[str, int] = {}
    for i in hit:
        shown = " or ".join(ACCEPT.get(label[i], [label[i]]))
        counts[shown] = counts.get(shown, 0) + 1
    print(f"{args.out}: {len(hit)} of {len(items)} item(s) labelled {json.dumps(counts, sort_keys=True)}")
    print(f"  then: evh label-import {args.out} --dataset-id {args.dataset_id} --set <name> --by <who>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
