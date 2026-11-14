"""The openml source: an OpenML dataset, read from its parquet copy (PLAN_0.8.0 P2).

    evh dataset-create --dataset-id D --source openml \\
        --query '{"dataset": 61, "text": "class", "fields": ["sepallength"], "limit": 50}'

Query: `dataset` (its OpenML id: OpenML gives each version its own); `text`, `id`, `fields`, `offset`, `limit` as the
other table sources (`text` names a column; a tabular dataset's text is one of its columns). It reads the dataset's
parquet copy (`parquet_url`). OpenML lists an md5 only for the ARFF file, so the parquet bytes are not checked
against the source; each item is still frozen by its own sha256. It records the source block (provider openml, ref
the dataset's name, its version as `revision`, its page), the licence when `evh licences` knows OpenML's, and the
features with OpenML's types. The API is `OPENML_ENDPOINT` (default https://www.openml.org).
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from typing import Any

from evaluation_harness import _licences
from evaluation_harness.sources import _tables


def _endpoint() -> str:
    return os.environ.get("OPENML_ENDPOINT", "https://www.openml.org").rstrip("/")


class Source:
    """Items from an OpenML dataset's rows."""

    def __init__(self, options: dict) -> None:
        self.options = options

    @staticmethod
    def _desc(query: dict) -> dict:
        if not query.get("dataset"):
            raise ValueError("the openml source needs a dataset (its id) in its query")
        return (
            _tables.get_json(f"{_endpoint()}/api/v1/json/data/{int(query['dataset'])}").get(
                "data_set_description"
            )
            or {}
        )

    def describe(self, query: dict) -> dict:
        """The dataset's words: the source block, licence, name, its features and their OpenML types."""
        d = self._desc(query)
        desc = str(d.get("description") or "")
        out: dict[str, Any] = {
            "source": {
                "provider": "openml",
                "ref": d.get("name"),
                "url": f"{_endpoint()}/d/{d.get('id')}",
                "revision": str(d["version"]) if d.get("version") is not None else None,
                "description_sha256": hashlib.sha256(desc.encode("utf-8")).hexdigest() if desc else None,
            },
            "description": d.get("name") or None,
        }
        lic = _licences.canonical(str(d.get("licence") or ""))
        if lic:
            out["licence"] = lic
        feats = _tables.get_json(f"{_endpoint()}/api/v1/json/data/features/{int(query['dataset'])}")
        out["features"] = {
            f["name"]: {"numeric": "float64", "nominal": "string", "string": "string", "date": "date"}.get(
                f.get("data_type"), "string"
            )
            for f in ((feats.get("data_features") or {}).get("feature") or [])
            if f.get("name")
        }
        return out

    def items(self, query: dict) -> Iterator[dict]:
        """The dataset's rows from its parquet copy: text, id, row and kept fields."""
        if not query.get("text"):
            raise ValueError('name the column that is an item\'s text: "text" in the query')
        d = self._desc(query)
        if not d.get("parquet_url"):
            raise ValueError(f"OpenML dataset {query['dataset']} has no parquet copy")
        data = _tables.fetched(str(d["parquet_url"]))
        cols = [query["text"], *([query["id"]] if query.get("id") else []), *(query.get("fields") or [])]
        yield from _tables.items(_tables.rows(data, "parquet", cols), query)
