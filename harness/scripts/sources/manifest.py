"""The manifest source: a .csv or .jsonl of items at web addresses (what `dataset-create --manifest` reads).

    evh dataset-create --dataset-id D --source manifest --query '{"path": "items.csv"}'

Query: `path` (required). Each row has `item_id` and `source_url`, optionally `source_sha256` (pins it; without one the
bytes are fetched when the dataset is made) and `row`; other columns are field values (they need `--fieldset`).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from evaluation_harness import _fields

KNOWN = {"item_id", "source_url", "source_sha256", "row"}


class Source:
    """Items listed in a manifest file, each fetched from its address."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def describe(self, query: dict) -> dict:
        """The manifest, as a source block."""
        return {"source": {"provider": "url", "ref": Path(str(query.get("path"))).name}}

    def items(self, query: dict) -> Iterator[dict]:
        """Each row: its id, address, pinned hash and row when given, the other columns as fields."""
        if not query.get("path"):
            raise ValueError("the manifest source needs a path in its query")
        for row in _fields.read_rows(Path(query["path"])):
            item: dict = {
                "item_id": str(row.get("item_id") or "").strip(),
                "source_url": str(row.get("source_url") or ""),
            }
            if row.get("source_sha256"):
                item["source_sha256"] = str(row["source_sha256"]).strip().lower()
            if row.get("row") not in (None, ""):
                item["row"] = row["row"]
            extra = {k: v for k, v in row.items() if k not in KNOWN}
            if extra:
                item["fields"] = extra
            yield item
