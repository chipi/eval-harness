"""The jsonl importer: one JSON object per line of a file. Query keys: see importers/_rows.py.

evh capture --importer jsonl --query '{"path": "export.jsonl"}' --capture c1
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from evaluation_harness.importers import _rows


class Importer:
    """Records from a JSON-lines file."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def records(self, query: dict) -> Iterator[dict]:
        """Each line of the query's `path`, mapped by its keys."""
        if not query.get("path"):
            raise ValueError("the jsonl importer needs a path in its query")
        path = Path(query["path"])
        with path.open(encoding="utf-8") as f:
            rows = (json.loads(line) for line in f if line.strip())
            yield from _rows.records(rows, query)
