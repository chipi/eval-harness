#!/usr/bin/env python3
"""Promote labels to a reference (RFC-023, ADR-0022): the chosen labels, at the tier you decide, with a reason.

    evh reference-promote --dataset-id tickets_v1 --labels owner_v1 --tier gold --by owner \\
        --reason "the owner's labels of all six tickets, checked twice"
    evh reference-promote --dataset-id tickets_v2 --labels tickets_v1/author_v1 --tier silver --name tickets_v2_author \\
        --items t01_login --items t02_invoice --by owner --reason "the author model's answers on the two new tickets"

A reference is made only this way. The labels are the dataset's in the named set (`SET`, made on this dataset, or
`DATASET/SET`, made on another holding the same items: labels follow the item by its sha256), all of them or those
named with --items. They are written to data/references/<tier>/<name>/ (name: the dataset's id by default), the
layout runs, rescore and goals read, and its manifest records `promoted_from` (the set, its dataset and source), the
reason, who and when; for a set a model's run made, the run, its config and model too, so a run scored against it
is known to be graded against that model's answers. No rule ties the tier to the source: the promotion decides, and
records the source beside the tier. A reference is never overwritten.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness._common import REFERENCES, die, load_dataset, now
from evaluation_harness._label_sets import labels_for, source_line
from evaluation_harness._references import write_manifest

CAVEAT = {
    "gold": "GOLD: promoted as gold from {set} ({source}): the answers a decision rests on.",
    "silver": (
        "SILVER: promoted as silver from {set} ({source}): consistent, not a claim that any arm is right. Good "
        "enough to RANK arms against each other; say so wherever a number scored against it is published."
    ),
}


def main() -> int:
    """Promote a label set's labels to a reference."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True, help="the dataset the reference is for")
    ap.add_argument("--labels", required=True, help="SET (made on this dataset) or DATASET/SET")
    ap.add_argument("--tier", required=True, choices=("gold", "silver"))
    ap.add_argument("--reason", required=True, help="why these labels are the yardstick (a sentence)")
    ap.add_argument(
        "--items", action="append", default=[], help="only this item (repeatable; default all labelled)"
    )
    ap.add_argument("--name", help="the reference's name under its tier (default: the dataset's id)")
    ap.add_argument("--by", required=True, help="who promotes (recorded in the manifest)")
    args = ap.parse_args()

    if len(args.reason.split()) < 3:
        die(
            'REFUSED: --reason must be a sentence, not a word. It answers "why is this the yardstick?" later.'
        )
    set_ds, _, set_name = args.labels.rpartition("/")
    set_ds = set_ds or args.dataset_id
    name = args.name or args.dataset_id
    if "/" in name or name.startswith(".") or not name:
        die(f"--name {name!r}: one name, no path")
    ref_dir = REFERENCES / args.tier / name
    if ref_dir.exists() and any(ref_dir.iterdir()):
        die(f"{ref_dir} exists: a reference is never overwritten. Name another with --name.")
    ds = load_dataset(args.dataset_id)
    ids = [it["item_id"] for it in ds.get("items") or []]
    mine = {
        iid: r
        for iid, rows in labels_for(args.dataset_id).items()
        for r in rows
        if r["dataset_id"] == set_ds and r["set"] == set_name
    }
    if not mine:
        die(
            f"no labels of {set_ds}/{set_name} on {args.dataset_id}'s items (evh labels --dataset-id {args.dataset_id})"
        )
    if args.items:
        unknown = sorted(set(args.items) - set(ids))
        if unknown:
            die(f"--items: not in {args.dataset_id}: {', '.join(unknown[:8])}")
        missing = sorted(set(args.items) - set(mine))
        if missing:
            die(f"--items: {set_ds}/{set_name} has no label for {', '.join(missing[:8])}")
        chosen = [i for i in ids if i in set(args.items)]
    else:
        chosen = [i for i in ids if i in mine]
    source = next(iter(mine.values()))["source"]
    ref_dir.mkdir(parents=True, exist_ok=True)
    for iid in chosen:
        (ref_dir / f"{iid}.txt").write_text(mine[iid]["text"] + "\n", encoding="utf-8")
    authorship = {}
    if source.get("kind") == "model":
        # Who authored the texts is part of a reference's identity (the fingerprint hashes it): a run scored against
        # a model's answers is graded against that model.
        authorship = {
            "authored_by": source.get("config_id"),
            "model": source.get("model"),
            "from_run": {k: source.get(k) for k in ("run_id", "config_id", "fingerprint_hash", "build")},
        }
    write_manifest(
        ref_dir,
        args.tier,
        args.dataset_id,
        caveat=CAVEAT[args.tier].format(set=f"{set_ds}/{set_name}", source=source_line(source)),
        created_at=now(),
        promoted_from={"labels": set_name, "dataset_id": set_ds, "source": source},
        reason=args.reason,
        promoted_by=args.by,
        **authorship,
    )
    print(
        f"{ref_dir}: {len(chosen)} of {len(ids)} item(s), {args.tier}, promoted from {set_ds}/{set_name} "
        f"({source_line(source)})"
    )
    print("  commit it before the next run: an untracked reference marks every run scored against it dirty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
