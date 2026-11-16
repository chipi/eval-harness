"""Derive the run inputs for a dataset, verifying every item against its hash.

`materialized/` is DERIVED and regenerable from `sources/` + the dataset. If it
cannot be rebuilt, it does not belong there.

The hash check is the point. A dataset records what the bytes were when it was
frozen; if a source file has changed underneath it, every number measured on
that dataset is describing something that no longer exists. That is a hard
failure, not a warning.

    python scripts/materialize.py --dataset-id smoke_v1
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation_harness import _fetch, _store
from evaluation_harness._common import (
    die,
    load_dataset,
    now,
    sha256,
    write_json,
)
from evaluation_harness.model import datasets as _datasets
from evaluation_harness.ops import legacy


def body(**inputs: Any) -> int:
    """Materialize a dataset from sources and verify hashes."""
    args = legacy.namespace(inputs, "dataset-materialize")
    ds = load_dataset(args.dataset_id)
    out = _datasets.materialized_dir(args.dataset_id)

    if _store.exists(out) and not args.force:
        print(f"{out} exists — nothing to do (--force to rebuild)")
        return 0
    # Built beside the old copy and put in its place only when every item is verified: a failed run leaves what was
    # there (a --force that failed deleted the good copy; one without it left an empty folder that `exists` then
    # took for a copy).
    stage = _store.staging(out, f".{args.dataset_id}.")
    try:
        _build(ds, _datasets.source_dir(ds), stage)
        if _store.exists(out):
            _store.rmtree(out)
        _store.adopt(stage, out)
    finally:
        _store.rmtree(stage, ignore_errors=True)
    print(f"{out}  ({len(ds['items'])} item(s), all hashes verified)")
    return 0


def _build(ds: dict, src_root: Path, stage: Path) -> None:
    """Every item of `ds` read from `src_root`, hash-checked and copied into `stage`, with its meta.json; dies (exit 1,
    each item that failed named) when any is missing, changed or not fetched as pinned."""
    drifted, missing, unfetched = [], [], []
    for item in ds["items"]:
        rel = item.get("source_path") or item["item_id"]
        if item.get("source_url"):
            # A URL item (ADR-0003): fetched once into the cache, and refused unless its bytes
            # are the pinned ones. A changed file at the URL is the same failure as a changed
            # file under sources/.
            try:
                src, _ = _fetch.fetch(item["source_url"], item["source_sha256"])
            except _fetch.FetchError as exc:
                unfetched.append((rel, str(exc)))
                continue
            dst = stage / rel
            _store.mkdir(dst.parent, parents=True, exist_ok=True)
            _store.copy_file(src, dst)
            continue
        src = src_root / rel
        if not _store.is_file(src):
            missing.append(rel)
            continue
        actual = sha256(src)
        if actual != item["source_sha256"]:
            drifted.append((rel, item["source_sha256"][:12], actual[:12]))
            continue
        dst = stage / rel
        _store.mkdir(dst.parent, parents=True, exist_ok=True)
        _store.copy_file(src, dst)

    if missing or drifted or unfetched:
        for rel in missing:
            print(f"  MISSING  {rel}")
        for rel, was, now_ in drifted:
            print(f"  CHANGED  {rel}  frozen={was} actual={now_}")
        for rel, why in unfetched:
            print(f"  FETCH    {rel}  {why}")
        die(
            f"{len(missing)} missing, {len(drifted)} changed, {len(unfetched)} not fetched as pinned "
            "since the dataset was frozen.\n"
            "  sources/ is immutable. If an input genuinely changed, that is a NEW\n"
            "  dataset (_v2) — every number already published was measured on the old bytes.",
            "not-materialized",
        )

    write_json(
        stage / "meta.json",
        {
            "dataset_id": ds["dataset_id"],
            "materialized_at": now(),
            "n_items": len(ds["items"]),
            "verified": "every item matched its frozen sha256",
        },
    )
