"""The tsv importer: a tab-separated file with a header row; one row is one record (a ledger, an
export). Query keys: see importers/_rows.py; `delimiter` reads a comma-separated file instead.

evh capture --importer tsv --query '{"path": "ledger.tsv", "id": "occurrence_id", "created_at": "ts"}' --capture c1
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from evaluation_harness.importers import _rows


class Importer:
    """Records from a delimited text file with a header row."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def records(self, query: dict) -> Iterator[dict]:
        """Each row of the query's `path`, mapped by its keys."""
        if not query.get("path"):
            raise ValueError("the tsv importer needs a path in its query")
        path = Path(query["path"])
        csv.field_size_limit(1 << 24)
        with path.open(encoding="utf-8", newline="") as f:
            yield from _rows.records(csv.DictReader(f, delimiter=query.get("delimiter", "\t")), query)
