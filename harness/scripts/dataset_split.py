"""Split a dataset into validation and test (RFC-019): two ordinary datasets, each a version of it.

    evh dataset-split --dataset-id triage_v1 --test 0.3 --seed 7
    evh dataset-split --dataset-id triage_v1 --test 0.3 --seed 7 --key fingerprint
    evh dataset-split --dataset-id triage_v1 --test 0.3 --split-by time --key decision_date
    evh dataset-split --dataset-id triage_v1 --split-by time --key decision_date --at 2026-11-07T00:00:00Z --seal

Writes <D>_validation and <D>_test. They point at the parent's own source files (nothing is copied),
record the parent as `derived_from` (with the items each leaves out) and the rule as `split`, and a
goal names them with the roles it has today.

--split-by hash (default): an item goes to test when the hash of (seed, its key) falls below the share.
The key is the item id, or with --key an item field, so all items sharing a value (one fingerprint)
land on one side. Items keep their side in every later version, and new items fall in proportion.
--split-by time: the newest share by --key (a date or time field) is test, or with --at every item at or after
that time. --seal holds the test side out (_seal): nothing runs, is scored or labelled on it until
`evh dataset-unseal` names a candidate system whose hypothesis is committed.
"""

from __future__ import annotations

import hashlib
from typing import Any

from evaluation_harness import _fields, _seal, _store
from evaluation_harness._common import DATASETS, dataset_id_ok, die, load_dataset, now, read_json
from evaluation_harness._importers import parse_time
from evaluation_harness.dataset_create import _lineage, _write
from evaluation_harness.ops import legacy


def side(seed: int, key: str, share: float) -> str:
    """validation or test for one key: stable for a seed, whatever else is in the dataset."""
    h = int(hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()[:15], 16) / 16**15
    return "test" if h < share else "validation"


def body(**inputs: Any) -> int:
    """Split a dataset into <D>_validation and <D>_test."""
    args = legacy.namespace(inputs, "dataset-split")
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
        die("--split-by time needs --key: the item field holding each item's date or time", "bad-argument")
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
