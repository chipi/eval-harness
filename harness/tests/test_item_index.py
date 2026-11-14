#!/usr/bin/env python3
"""Where an item's copy is, asked once per item (PLAN_0.8.0 S1/S3): the dataset read once, not once per item.

    python tests/test_item_index.py

S1 measured `inspect --sheet` at 1,000 items loading and parsing the whole dataset record 1,002 times
(`_common.item_path`, quadratic: each call read the record and scanned its items). Now 1,000 lookups read it once;
a changed record is read again; an item it does not hold, or one not materialized, is None as before.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
proj = Path(tempfile.mkdtemp(prefix="evh-item-index-"))
os.environ["EVAL_HOME"] = str(proj)
os.environ.pop("EVAL_DATA_DIR", None)
from evaluation_harness import _common, _outputs, _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

_common.project_root.cache_clear()
_common._paths.cache_clear()
_outputs.reset()
data = proj / "data"


def put(path: Path, text: str) -> None:
    _store.mkdir(path.parent, parents=True, exist_ok=True)
    _store.write_text(path, text)


try:
    n = 1000
    items = [
        {"item_id": f"i{k:04d}", "source_path": f"i{k:04d}.txt", "source_sha256": "0" * 64} for k in range(n)
    ]
    put(data / "datasets" / "big.json", json.dumps({"dataset_id": "big", "items": items}))
    for it in items[:-1]:  # every item materialized but the last
        put(data / "materialized" / "big" / it["source_path"], "x")

    reads = {"n": 0}
    real = _common.read_json

    def counting(path, *a, **k):
        if str(path).endswith("big.json"):
            reads["n"] += 1
        return real(path, *a, **k)

    _common.read_json = counting
    found = [_common.item_path("big", it["item_id"]) for it in items]
    check(
        "1,000 lookups read the dataset record once",
        reads["n"] == 1,
        reads,
    )
    check(
        "each found where it is; one not materialized is None; one the dataset has not is None",
        found[0] == data / "materialized" / "big" / "i0000.txt"
        and found[-1] is None
        and _common.item_path("big", "nope") is None
        and all(f is not None for f in found[:-1]),
        (found[0], found[-1]),
    )
    items.append({"item_id": "i_new", "source_path": "new.txt", "source_sha256": "0" * 64})
    put(data / "datasets" / "big.json", json.dumps({"dataset_id": "big", "items": items}, indent=1))
    put(data / "materialized" / "big" / "new.txt", "y")
    check(
        "a changed record is read again: its new item is found",
        _common.item_path("big", "i_new") == data / "materialized" / "big" / "new.txt" and reads["n"] == 2,
        reads,
    )
    dup = [*items, {"item_id": "i0000", "source_path": "other.txt", "source_sha256": "0" * 64}]
    put(data / "datasets" / "big.json", json.dumps({"dataset_id": "big", "items": dup}))
    put(data / "materialized" / "big" / "other.txt", "z")
    check(
        "two items with one id: the first one's file, as the search over the items found it",
        _common.item_path("big", "i0000") == data / "materialized" / "big" / "i0000.txt",
        _common.item_path("big", "i0000"),
    )
    _common.read_json = real
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
