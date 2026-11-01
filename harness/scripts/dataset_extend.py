#!/usr/bin/env python3
"""The next version of a governed dataset, from its items and the picks you choose (RFC-023, ADR-0023).

    evh dataset-extend orrery_triage_v1_labelled --dataset-id orrery_triage_v2_labelled --picks
    evh dataset-extend orrery_triage_v1_labelled --dataset-id orrery_triage_v2_labelled \\
        --pick orrery-ORRERY-PROD-2A-… --pick orrery_triage_2026_12:orrery-ORRERY-PROD-3C-…

V2 is V1's items plus the chosen picks: --picks takes every pick waiting for V1; --pick takes one (ITEM, or
DATASET:ITEM when two datasets hold that id), whatever its target. Each picked item is copied from its dataset as it
was picked (its sha256 is checked), and V2 records where every added item came from (`extended_from`: V1, and per
item its dataset, capture and note), with the lineage dataset-create --from records. The picks used leave the
waiting list. V2 keeps V1's field set and tags (a picked item keeps its fields only when its dataset has the same
field set), and its text is hidden when V1's or any picked item's is. Nothing is promoted: an item's labels follow
it by its sha256; promote the ones you choose (evh reference-promote).
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import shutil
from pathlib import Path

from evaluation_harness._common import DATASETS, ROOT, SOURCES, dataset_id_ok, die, how, load_dataset, sha256
from evaluation_harness._picks import append, waiting
from evaluation_harness.dataset_create import _fieldset, _lineage, _relative_source_dir, _say_lineage, _write


def source_dir(ds: dict) -> Path:
    """Where a dataset's item files are."""
    p = Path(ds.get("source_dir") or SOURCES / ds["dataset_id"])
    return p if p.is_absolute() else ROOT / p


def main() -> int:
    """Make the next version of a dataset from it and chosen picks."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dataset", help="the governed dataset this version grows from (V1)")
    ap.add_argument("--dataset-id", required=True, help="the new version's id (V2)")
    pick = ap.add_mutually_exclusive_group(required=True)
    pick.add_argument("--picks", action="store_true", help="every pick waiting for V1")
    pick.add_argument("--pick", action="append", help="one pick: ITEM, or DATASET:ITEM (repeatable)")
    ap.add_argument("--description", help="what this version is")
    args = ap.parse_args()

    v1 = load_dataset(args.dataset)
    out = DATASETS / f"{dataset_id_ok(args.dataset_id)}.json"
    if out.exists():
        die(f"{out} exists: a version is a new dataset; name it another way")
    src = SOURCES / args.dataset_id
    if src.exists() and any(src.iterdir()):
        die(f"{src} exists and is not empty")
    pool = waiting()
    if args.picks:
        chosen = [p for p in pool if args.dataset in (p.get("for") or [])]
        if not chosen:
            die(f"no pick is waiting for {args.dataset} (evh picks --for {args.dataset})")
    else:
        chosen = []
        for spec in args.pick:
            ds_id, _, item = (
                spec.rpartition(":") if ":" in spec and not spec.startswith(":") else ("", "", spec)
            )
            hits = [p for p in pool if p["item"] == item and (not ds_id or p["from"] == ds_id)]
            if not hits and ds_id:
                # An item id may itself contain ':' (a fingerprint and a time): try the whole spec as the id.
                hits = [p for p in pool if p["item"] == spec]
            if not hits:
                die(f"--pick {spec}: not waiting (evh picks)")
            if len(hits) > 1:
                die(f"--pick {spec}: waiting from {len(hits)} datasets; name one: DATASET:ITEM")
            chosen.append(hits[0])
    v1_items = {it["item_id"]: it for it in v1.get("items") or []}
    src.mkdir(parents=True, exist_ok=True)
    v1_src = source_dir(v1)
    items: list[dict] = []
    for it in v1.get("items") or []:
        p = v1_src / it.get("source_path", it["item_id"])
        if not p.is_file():
            die(f"{args.dataset}: no source file {p} for {it['item_id']}; fetch or materialize it first")
        shutil.copyfile(p, src / it["source_path"])
        items.append(dict(it))
    added, hidden = [], v1.get("text") == "hidden"
    for p in chosen:
        ds = load_dataset(p["from"])
        it = next((x for x in ds.get("items") or [] if x["item_id"] == p["item"]), None)
        if it is None:
            die(f"{p['from']} no longer has {p['item']}")
        if p["item"] in v1_items:
            if v1_items[p["item"]].get("source_sha256") == it.get("source_sha256"):
                print(f"  {p['item']} is already in {args.dataset}: kept once")
                continue
            die(f"{p['item']} is in {args.dataset} with other content: an id names one item")
        f = source_dir(ds) / it.get("source_path", it["item_id"])
        if not f.is_file() or sha256(f) != p.get("sha256"):
            die(f"{p['from']}/{p['item']}: its file is not the one picked (missing, or changed since)")
        shutil.copyfile(f, src / it["source_path"])
        new = {k: it[k] for k in ("item_id", "source_path", "source_sha256") if k in it}
        if it.get("fields") and ds.get("fieldset") == v1.get("fieldset"):
            new["fields"] = it["fields"]
        items.append(new)
        hidden = hidden or ds.get("text") == "hidden"
        added.append(
            {"item_id": p["item"], "from": p["from"], "capture": p.get("capture"), "note": p.get("note")}
        )
    if not added:
        die("no item to add: every chosen pick is already in V1")
    lineage = _lineage(args.dataset, args.dataset_id, items)
    _write(
        out,
        args.dataset_id,
        items,
        {},
        _fieldset(v1.get("fieldset")),
        args.description or f"{args.dataset} and {len(added)} picked item(s)",
        _relative_source_dir(src),
        lineage,
        {
            "extended_from": {"dataset": args.dataset, "picks": added},
            **({"tags": v1["tags"]} if v1.get("tags") else {}),
            **({"text": "hidden"} if hidden else {}),
        },
    )
    append(
        [{"action": "used", "item": a["item_id"], "from": a["from"], "into": args.dataset_id} for a in added]
    )
    print(
        f"{out.relative_to(DATASETS.parents[1])}  ({len(items)} item(s): {len(v1_items)} of {args.dataset}, {len(added)} picked)"
    )
    _say_lineage(lineage)
    print(
        "Next: "
        + how(
            f"evh dataset-materialize --dataset-id {args.dataset_id}",
            f"make dataset-materialize DATASET_ID={args.dataset_id}",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
