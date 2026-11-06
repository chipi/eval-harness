#!/usr/bin/env python3
"""Publish a dataset where a source can write it: a new repo, checked by reading it back (PLAN_0.8.0 P1).

    evh dataset-publish --dataset-id D --to huggingface --query '{"repo": "owner/name"}'       private
    evh dataset-publish --dataset-id D --to huggingface --query '{"repo": "owner/name", "public": true}'

The items must be materialized here (their bytes are what is written, each checked against its sha256 first). A
dataset whose text is hidden is refused: publishing is the one thing hidden text never allows. The source writes the
items, the record and the card in one commit, reads them back, and the record keeps where it went (`published`:
provider, repo, revision, url, private, when, each file's sha256); no new version, the items are the same.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
import json

from evaluation_harness import _sources, _store
from evaluation_harness._common import (
    DATASETS,
    dataset_id_ok,
    die,
    evh_prog,
    item_path,
    now,
    read_json,
    write_json,
)


def main() -> int:
    """Publish one dataset through a source's publish(), and record where it went."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--to", required=True, metavar="SOURCE", help="the source that writes it (huggingface)")
    ap.add_argument(
        "--query", default="{}", help='where to write it, as JSON (huggingface: {"repo": "owner/name"})'
    )
    args = ap.parse_args()
    f = DATASETS / f"{dataset_id_ok(args.dataset_id)}.json"
    if not _store.is_file(f):
        die(f"no dataset {args.dataset_id!r} (evh datasets lists them)", "not-found")
    record = read_json(f)
    if record.get("text") == "hidden":
        die(f"{args.dataset_id}: its text is hidden; a hidden dataset is never published", "not-public")
    try:
        query = json.loads(args.query)
    except ValueError as e:
        die(f"--query is not JSON: {e}", "bad-argument")
    cls, _path = _sources.resolve(args.to)
    if not callable(getattr(cls, "publish", None)):
        die(f"--to {args.to}: that source cannot publish (it has no publish())", "bad-argument")
    items, bad = [], []
    for it in record.get("items") or []:
        p = item_path(args.dataset_id, it["item_id"])
        if p is None:
            bad.append(f"{it['item_id']}: not materialized here")
            continue
        data = _store.read_bytes(p)
        if hashlib.sha256(data).hexdigest() != it["source_sha256"]:
            bad.append(f"{it['item_id']}: its bytes are not its sha256")
            continue
        items.append((it, data))
    if bad:
        die(
            f"{len(bad)} item(s) cannot be published: "
            + "; ".join(bad[:5])
            + f" (evh dataset-materialize --dataset-id {args.dataset_id} first)",
            "not-materialized",
        )
    try:
        got = cls({}).publish(record, items, query)
    except Exception as e:  # noqa: BLE001 — every failure of the publish (the Hub's own errors too) is the same refusal
        if "exists" in str(e):
            die(f"--to {args.to}: {e}", "would-overwrite")
        die(f"--to {args.to}: {e}", "failed")
    record.setdefault("published", []).append({**got, "at": now()})
    write_json(f, record)
    print(
        f"{args.dataset_id}: published to {got['repo']} at {got['revision']} "
        f"({'private' if got.get('private') else 'public'}), {len(items)} item(s), every file read back and matching"
    )
    print(f"  {got['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
