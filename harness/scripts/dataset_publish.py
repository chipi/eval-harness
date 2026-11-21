"""Publish a dataset where a source can write it: a new repo, checked by reading it back (PLAN_0.8.0 P1).

    evh dataset-publish --dataset-id D --to huggingface --query '{"repo": "owner/name"}'       private
    evh dataset-publish --dataset-id D --to huggingface --query '{"repo": "owner/name", "public": true}'

The items must be materialized here (their bytes are what is written, each checked against its sha256 first). A
dataset whose text is hidden is refused: publishing is the one thing hidden text never allows. The source writes the
items, the record and the card in one commit, reads them back, and the record keeps where it went (`published`:
provider, repo, revision, url, private, when, each file's sha256); no new version, the items are the same.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from evaluation_harness import _sources, _store
from evaluation_harness._common import (
    DATASETS,
    dataset_id_ok,
    die,
    item_path,
    now,
    read_json,
    write_json,
)
from evaluation_harness.ops import legacy


def body(**inputs: Any) -> int:
    """Publish one dataset through a source's publish(), and record where it went."""
    args = legacy.namespace(inputs, "dataset-publish")
    f = DATASETS / f"{dataset_id_ok(args.dataset_id)}.json"
    if not _store.is_file(f):
        die(f"no dataset {args.dataset_id!r} (evh dataset-list lists them)", "not-found")
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
