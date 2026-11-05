"""The zenodo source: a table file of a Zenodo record (PLAN_0.8.0 P2).

    evh dataset-create --dataset-id D --source zenodo \\
        --query '{"record": 6857505, "file": "comments.csv", "text": "comment", "fields": ["label"], "limit": 200}'

Query: `record` (the record id: Zenodo gives each version its own); `file` (its key; may be left out when the record
has one readable file); `text`, `id`, `fields`, `offset`, `limit` as the other table sources. It reads one parquet,
CSV, JSON or JSON-lines file, checked against the md5 Zenodo lists for it. It records the source block (provider
zenodo, ref the concept record that spans the versions, the record id as `revision`, the DOI's address, the sha256 of
the description), the licence when `evh licences` knows Zenodo's id, and the title as the description. The API is
`ZENODO_ENDPOINT` (default https://zenodo.org).
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from typing import Any

from evaluation_harness import _licences
from evaluation_harness.sources import _tables


def _endpoint() -> str:
    return os.environ.get("ZENODO_ENDPOINT", "https://zenodo.org").rstrip("/")


class Source:
    """Items from one table file of a Zenodo record."""

    def __init__(self, options: dict) -> None:
        self.options = options

    @staticmethod
    def _record(query: dict) -> dict:
        if not query.get("record"):
            raise ValueError("the zenodo source needs a record (its id) in its query")
        return _tables.get_json(f"{_endpoint()}/api/records/{int(query['record'])}")

    @staticmethod
    def _file(rec: dict, query: dict) -> dict:
        files = rec.get("files") or []
        if query.get("file"):
            f = next((x for x in files if x.get("key") == query["file"]), None)
            if f is None:
                raise ValueError(
                    f"record {rec.get('id')} has no file {query['file']!r} (it has: {', '.join(x.get('key', '') for x in files)})"
                )
            return f
        readable = [x for x in files if _tables.kind_of(x.get("key", ""))]
        if len(readable) != 1:
            raise ValueError(
                f'record {rec.get("id")} has {len(readable)} readable files: name one with "file"'
            )
        return readable[0]

    def describe(self, query: dict) -> dict:
        """The record's words: the source block, licence, title."""
        rec = self._record(query)
        md = rec.get("metadata") or {}
        desc = str(md.get("description") or "")
        out: dict[str, Any] = {
            "source": {
                "provider": "zenodo",
                "ref": str(rec.get("conceptrecid") or rec.get("id")),
                "url": rec.get("doi_url") or (rec.get("links") or {}).get("html"),
                "revision": str(rec.get("id")),
                "description_sha256": hashlib.sha256(desc.encode("utf-8")).hexdigest() if desc else None,
            },
            "description": md.get("title") or None,
        }
        lic = _licences.canonical(str((md.get("license") or {}).get("id") or ""))
        if lic:
            out["licence"] = lic
        return out

    def items(self, query: dict) -> Iterator[dict]:
        """The file's rows: text, id, row and kept fields."""
        if not query.get("text"):
            raise ValueError('name the column that is an item\'s text: "text" in the query')
        rec = self._record(query)
        f = self._file(rec, query)
        kind = _tables.kind_of(f.get("key", ""))
        if not kind:
            raise ValueError(f"{f.get('key')}: only parquet, CSV, JSON and JSON lines files are read")
        data = _tables.fetched((f.get("links") or {}).get("self") or "")
        algo, _, want = str(f.get("checksum") or "").partition(":")
        if algo == "md5" and hashlib.md5(data, usedforsecurity=False).hexdigest() != want:
            raise ValueError(f"{f.get('key')}: its bytes are not the md5 Zenodo lists for it")
        cols = [query["text"], *([query["id"]] if query.get("id") else []), *(query.get("fields") or [])]
        yield from _tables.items(_tables.rows(data, kind, cols), query)
