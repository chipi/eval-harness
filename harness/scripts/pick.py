#!/usr/bin/env python3
"""Pick production items for the next version of governed datasets (RFC-023, ADR-0023), or drop a pick.

    evh pick --dataset-id orrery_triage_2026_11 --item orrery-ORRERY-PROD-2A-… --for orrery_triage_v1_labelled \\
        --tag case=missed-regression --note "dismissed a real regression; v1 has no case like it" --by owner
    evh pick --dataset-id orrery_triage_2026_11 --item orrery-ORRERY-PROD-2A-… --for other_dataset_v1   # retarget
    evh pick --dataset-id orrery_triage_2026_11 --item orrery-ORRERY-PROD-2A-… --drop

Every pick is a line of the project's one list, data/picks.jsonl, which is never rewritten: the latest line for an
item wins, so picking it again retargets or retags it, and a drop takes it off the waiting list with its history
kept. A pick may name several target datasets (--for, repeatable) or none yet. `evh picks` lists what waits;
`evh dataset-extend` makes a version of a governed dataset from the picks you choose.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _store
from evaluation_harness._common import DATASETS, dataset_id_ok, die, evh_prog, load_dataset
from evaluation_harness._picks import append, state


def main() -> int:
    """Pick items, or drop picks."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument(
        "--dataset-id", required=True, help="the dataset the items are in (usually a production one)"
    )
    ap.add_argument("--item", action="append", required=True, help="an item to pick (repeatable)")
    ap.add_argument(
        "--for", dest="targets", action="append", default=[], help="a dataset it may join (repeatable)"
    )
    ap.add_argument("--tag", action="append", default=[], help="KEY=VALUE, to group candidates (repeatable)")
    ap.add_argument("--note", default="", help="why it is worth keeping")
    ap.add_argument("--by", default="", help="who picks")
    ap.add_argument("--drop", action="store_true", help="take these items off the waiting list")
    args = ap.parse_args()

    ds = load_dataset(args.dataset_id)
    items = {it["item_id"]: it for it in ds.get("items") or []}
    unknown = sorted(set(args.item) - set(items))
    if unknown:
        die(f"not in {args.dataset_id}: {', '.join(unknown[:8])}", "not-found")
    if args.drop:
        now_state = state()
        missing = [
            i for i in args.item if (now_state.get((args.dataset_id, i)) or {}).get("action") != "pick"
        ]
        if missing:
            die(f"not waiting, so nothing to drop: {', '.join(missing[:8])} (evh picks)", "not-found")
        append(
            [{"action": "drop", "item": i, "from": args.dataset_id, "by": args.by or None} for i in args.item]
        )
        print(f"dropped {len(args.item)} pick(s) of {args.dataset_id}")
        return 0
    tags = {}
    for t in args.tag:
        k, sep, v = t.partition("=")
        if not sep or not k:
            die(f"--tag {t!r}: KEY=VALUE", "bad-argument")
        tags[k] = v
    for t in args.targets:
        if not _store.is_file(DATASETS / f"{dataset_id_ok(t)}.json"):
            die(f"--for {t}: no such dataset", "not-found")
    capture = (ds.get("made_from") or {}).get("capture")
    append(
        [
            {
                "action": "pick",
                "item": i,
                "from": args.dataset_id,
                "sha256": items[i].get("source_sha256"),
                "capture": capture,
                "for": sorted(set(args.targets)),
                "tags": tags,
                "note": args.note or None,
                "by": args.by or None,
            }
            for i in args.item
        ]
    )
    where = f" for {', '.join(sorted(set(args.targets)))}" if args.targets else " (no target yet)"
    print(f"picked {len(args.item)} item(s) of {args.dataset_id}{where}; evh picks lists what waits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
