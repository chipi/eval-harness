#!/usr/bin/env python3
"""Split a dataset into validation and test (RFC-019): two ordinary datasets, each a version of it.

    evh dataset-split triage_v1 --test 0.3 --seed 7
    evh dataset-split triage_v1 --test 0.3 --seed 7 --key fingerprint
    evh dataset-split triage_v1 --test 0.3 --by time --key decision_date

Writes <D>_validation and <D>_test. They point at the parent's own source files (nothing is copied),
record the parent as `derived_from` (with the items each leaves out) and the rule as `split`, and a
goal names them with the roles it has today.

--by hash (default): an item goes to test when the hash of (seed, its key) falls below the share.
The key is the item id, or with --key an item field, so all items sharing a value (one fingerprint)
land on one side. Items keep their side in every later version, and new items fall in proportion.
--by time: the newest share by --key (a date or time field) is test.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib

from evaluation_harness import _fields
from evaluation_harness._common import DATASETS, dataset_id_ok, die, evh_prog, load_dataset, read_json
from evaluation_harness.dataset_create import _lineage, _write


def side(seed: int, key: str, share: float) -> str:
    """validation or test for one key: stable for a seed, whatever else is in the dataset."""
    h = int(hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()[:15], 16) / 16**15
    return "test" if h < share else "validation"


def main() -> int:
    """Split a dataset into <D>_validation and <D>_test."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("dataset_id", help="the dataset to split")
    ap.add_argument("--test", type=float, required=True, help="the test share, between 0 and 1")
    ap.add_argument("--by", choices=("hash", "time"), default="hash")
    ap.add_argument(
        "--key",
        help="an item field: hash all items with one value to one side, or the time field for --by time",
    )
    ap.add_argument("--seed", type=int, default=0, help="with --by hash: the seed (default 0)")
    ap.add_argument(
        "--force", action="store_true", help="overwrite the two datasets if nothing cites them yet"
    )
    args = ap.parse_args()
    if not 0 < args.test < 1:
        die("--test is a share between 0 and 1", "bad-argument")
    if args.by == "time" and not args.key:
        die("--by time needs --key: the item field holding each item's date or time", "bad-argument")
    parent = load_dataset(dataset_id_ok(args.dataset_id))
    items = parent["items"]

    def key_of(it: dict) -> str:
        if not args.key:
            return it["item_id"]
        v = (it.get("fields") or {}).get(args.key)
        if v is None:
            die(f"--key {args.key}: item {it['item_id']} has no value for it", "not-found")
        return str(v)

    if args.by == "hash":
        assign = {it["item_id"]: side(args.seed, key_of(it), args.test) for it in items}
    else:
        order = sorted(items, key=lambda it: (key_of(it), it["item_id"]))
        n_held = round(len(order) * args.test)
        newest = {it["item_id"] for it in order[len(order) - n_held :]}
        assign = {it["item_id"]: "test" if it["item_id"] in newest else "validation" for it in items}

    fieldset = _fields.load_fieldset(parent["fieldset"]) if parent.get("fieldset") else None
    rule = {"from": args.dataset_id, "test": args.test, "by": args.by, "key": args.key}
    if args.by == "hash":
        rule["seed"] = args.seed
    written = []
    for part in ("validation", "test"):
        out_id = f"{args.dataset_id}_{part}"
        out = DATASETS / f"{dataset_id_ok(out_id)}.json"
        if out.exists() and not args.force:
            die(
                f"{out} already exists: a dataset is frozen. --force if nothing cites it yet.",
                "would-overwrite",
            )
        mine = [dict(it) for it in items if assign[it["item_id"]] == part]
        if not mine:
            die(f"the {part} side is empty: a larger dataset or another share", "not-enough")
        _write(
            out,
            out_id,
            mine,
            read_json(out) if out.exists() else {},
            fieldset,
            f"{part} of {args.dataset_id}: {len(mine)} of {len(items)} item(s), split by {args.by}"
            + (f" on {args.key}" if args.key else ""),
            parent.get("source_dir", ""),
            _lineage(args.dataset_id, out_id, mine),
            {"split": {**rule, "part": part}},
            licence=parent.get("licence"),
        )
        written.append((out_id, len(mine)))
    for out_id, n in written:
        print(f"data/datasets/{out_id}.json  ({n} item(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
