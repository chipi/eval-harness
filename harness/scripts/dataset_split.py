#!/usr/bin/env python3
"""Split a dataset into validation and test (RFC-019): two ordinary datasets, each a version of it.

    evh dataset-split triage_v1 --test 0.3 --seed 7
    evh dataset-split triage_v1 --test 0.3 --seed 7 --key fingerprint
    evh dataset-split triage_v1 --test 0.3 --split-by time --key decision_date
    evh dataset-split triage_v1 --split-by time --key decision_date --at 2026-11-07T00:00:00Z --seal

Writes <D>_validation and <D>_test. They point at the parent's own source files (nothing is copied),
record the parent as `derived_from` (with the items each leaves out) and the rule as `split`, and a
goal names them with the roles it has today.

--split-by hash (default): an item goes to test when the hash of (seed, its key) falls below the share.
The key is the item id, or with --key an item field, so all items sharing a value (one fingerprint)
land on one side. Items keep their side in every later version, and new items fall in proportion.
--split-by time: the newest share by --key (a date or time field) is test, or with --at every item at or after
that time. --seal holds the test side out (_seal): nothing runs, is scored or labelled on it until
`evh dataset-unseal` names a candidate config whose hypothesis is committed.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
import sys

from evaluation_harness import _fields, _jsonout, _seal, _store
from evaluation_harness._common import DATASETS, dataset_id_ok, die, evh_prog, load_dataset, now, read_json
from evaluation_harness._importers import parse_time
from evaluation_harness.dataset_create import _lineage, _write


def side(seed: int, key: str, share: float) -> str:
    """validation or test for one key: stable for a seed, whatever else is in the dataset."""
    h = int(hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()[:15], 16) / 16**15
    return "test" if h < share else "validation"


def main() -> int:
    """Split a dataset into <D>_validation and <D>_test."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("dataset_id", help="the dataset to split")
    ap.add_argument(
        "--test", type=float, help="the test share, between 0 and 1 (or --at with --split-by time)"
    )
    ap.add_argument("--split-by", choices=("hash", "time"), default="hash", help="the split rule")
    ap.add_argument(
        "--key",
        help="an item field: hash all items with one value to one side, or the time field for --split-by time",
    )
    ap.add_argument("--seed", type=int, default=0, help="with --split-by hash: the seed (default 0)")
    ap.add_argument(
        "--at",
        help="with --split-by time: the boundary, an ISO time; items at or after it are the test side (instead of --test)",
    )
    ap.add_argument(
        "--seal",
        action="store_true",
        help="seal the test side: no run, score or label on it until evh dataset-unseal names a candidate config "
        "with a committed hypothesis",
    )
    ap.add_argument(
        "--count-by",
        help="with --seal: item fields a counts-only report (evh sealed-counts) may group the held-out side by, "
        "comma-separated; fixed now, so whoever reads the counts does not choose what they show (RFC-031)",
    )
    ap.add_argument(
        "--force", action="store_true", help="overwrite the two datasets if nothing cites them yet"
    )
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("dataset-split", args.json, live=sys.stderr):
        if args.at is not None and args.split_by != "time":
            die("--at is a time boundary: with --split-by time", "bad-argument")
        if (args.test is None) == (args.at is None):
            die("one of --test (a share) or --at (a time boundary, with --split-by time)", "bad-argument")
        if args.test is not None and not 0 < args.test < 1:
            die("--test is a share between 0 and 1", "bad-argument")
        boundary = parse_time(args.at) if args.at is not None else None
        if args.at is not None and boundary is None:
            die(f"--at {args.at!r}: not an ISO time (2026-11-07T00:00:00Z)", "bad-argument")
        count_by = [f.strip() for f in (args.count_by or "").split(",") if f.strip()]
        if count_by and not args.seal:
            die("--count-by names what a sealed side's counts may show: with --seal", "bad-argument")
        if args.split_by == "time" and not args.key:
            die(
                "--split-by time needs --key: the item field holding each item's date or time", "bad-argument"
            )
        parent = load_dataset(dataset_id_ok(args.dataset_id))
        items = parent["items"]

        def key_of(it: dict) -> str:
            if not args.key:
                return it["item_id"]
            v = (it.get("fields") or {}).get(args.key)
            if v is None:
                die(f"--key {args.key}: item {it['item_id']} has no value for it", "not-found")
            return str(v)

        if args.split_by == "hash":
            assign = {it["item_id"]: side(args.seed, key_of(it), args.test) for it in items}
        elif boundary is not None:
            when = {it["item_id"]: parse_time(key_of(it)) for it in items}
            bad = [i for i, t in when.items() if t is None]
            if bad:
                die(f"--key {args.key}: not an ISO time on {len(bad)} item(s), e.g. {bad[0]}", "invalid-file")
            assign = {i: "test" if t >= boundary else "validation" for i, t in when.items()}  # type: ignore[operator]
        else:
            order = sorted(items, key=lambda it: (key_of(it), it["item_id"]))
            n_held = round(len(order) * args.test)
            newest = {it["item_id"] for it in order[len(order) - n_held :]}
            assign = {it["item_id"]: "test" if it["item_id"] in newest else "validation" for it in items}

        missing = [f for f in count_by if not any(f in (it.get("fields") or {}) for it in items)]
        if missing:
            die(f"--count-by: no item has the field(s) {', '.join(missing)}", "not-found")
        fieldset = _fields.load_fieldset(parent["fieldset"]) if parent.get("fieldset") else None
        share = (
            args.test
            if args.test is not None
            else round(sum(1 for v in assign.values() if v == "test") / len(items), 6)
        )
        rule = {"from": args.dataset_id, "test": share, "split_by": args.split_by, "key": args.key}
        if args.at is not None:
            rule["at"] = args.at
        if args.split_by == "hash":
            rule["seed"] = args.seed
        written = []
        open_items = [dict(it) for it in items if assign[it["item_id"]] == "validation"]
        for part in ("validation", "test"):
            out_id = f"{args.dataset_id}_{part}"
            out = DATASETS / f"{dataset_id_ok(out_id)}.json"
            if _store.exists(out) and not args.force:
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
                read_json(out) if _store.exists(out) else {},
                fieldset,
                f"{part} of {args.dataset_id}: {len(mine)} of {len(items)} item(s), split by {args.split_by}"
                + (f" on {args.key}" if args.key else ""),
                parent.get("source_dir", ""),
                _lineage(args.dataset_id, out_id, mine),
                {"split": {**rule, "part": part}}
                | (
                    {
                        "sealed": {
                            "at": now(),
                            "open_side": f"{args.dataset_id}_validation",
                            "open_sha256": _seal.items_digest(open_items),
                            **({"count_by": count_by} if count_by else {}),
                        }
                    }
                    if args.seal and part == "test"
                    else {}
                ),
                licence=parent.get("licence"),
                source=parent.get("source") or {},
            )
            written.append((out_id, len(mine)))
        for out_id, n in written:
            print(
                f"data/datasets/{out_id}.json  ({n} item(s))"
                + (
                    "  SEALED: no run, score or label until evh dataset-unseal"
                    if args.seal and out_id.endswith("_test")
                    else ""
                )
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
