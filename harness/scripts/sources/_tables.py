"""Rows of a data file a source fetched: parquet, CSV, JSON or JSON lines (shared by the sources that read tables)."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

#: A media type or a file suffix, as the kind of table it holds.
KINDS = {
    "application/x-parquet": "parquet",
    "application/vnd.apache.parquet": "parquet",
    ".parquet": "parquet",
    ".pq": "parquet",
    "text/csv": "csv",
    ".csv": "csv",
    "application/json": "json",
    ".json": "json",
    "application/jsonlines": "jsonl",
    "application/x-ndjson": "jsonl",
    ".jsonl": "jsonl",
}


def kind_of(media_type_or_name: str) -> str | None:
    """The table kind of a media type or a file name, None when none of these is readable."""
    s = str(media_type_or_name or "").lower()
    if s in KINDS:
        return KINDS[s]
    return next((k for suffix, k in KINDS.items() if suffix.startswith(".") and s.endswith(suffix)), None)


def rows(data: bytes, kind: str, columns: list[str] | None = None) -> list[dict[str, Any]]:
    """The file's rows as dicts; for parquet only `columns` are read."""
    if kind == "parquet":
        import pyarrow.parquet as pq  # noqa: PLC0415

        # One thread: with its thread pool, pyarrow 26 aborted the process at exit (examples/_shared/hf_rows.py).
        table = pq.read_table(
            io.BytesIO(data), columns=sorted(set(columns)) if columns else None, use_threads=False
        )
        return table.to_pylist()
    text = data.decode("utf-8")
    if kind == "csv":
        return list(csv.DictReader(io.StringIO(text)))
    if kind == "jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    loaded = json.loads(text)
    return loaded if isinstance(loaded, list) else [loaded]


def items(
    table: list[dict[str, Any]], query: dict, cols: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """The query's items from a table's rows: `text`, `id` (default row_<n>), `fields`, `offset`, `limit`; `cols` maps a
    query name to its column when they differ."""
    col = cols or {}
    offset, limit = int(query.get("offset") or 0), int(query.get("limit") or 0)
    out = []
    for n, row in enumerate(table):
        if n < offset:
            continue
        if limit and n >= offset + limit:
            break
        item: dict[str, Any] = {
            "item_id": str(row.get(col.get(query["id"], query["id"]))) if query.get("id") else f"row_{n}",
            "text": str(row.get(col.get(query["text"], query["text"])) or ""),
            "row": n,
        }
        kept = {k: row.get(col.get(k, k)) for k in query.get("fields") or []}
        if kept:
            item["fields"] = kept
        out.append(item)
    return out


def get_json(url: str) -> Any:
    """One JSON GET from a source's API; the project's headers for the host go with it (_fetch's table)."""
    import urllib.request  # noqa: PLC0415
    from urllib.parse import urlparse  # noqa: PLC0415

    from evaluation_harness import _fetch  # noqa: PLC0415

    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"{url}: only http(s) addresses are read")
    req = urllib.request.Request(url, headers={"User-Agent": "evaluation-harness"})  # noqa: S310 — http(s) checked
    for k, v in _fetch._headers_for(url).items():
        req.add_unredirected_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310  # nosec B310 — http(s) checked above
            return json.loads(resp.read())
    except Exception as e:  # every failure to read the API is the same refusal
        raise ValueError(f"{url} did not answer: {e}") from e


def fetched(url: str) -> bytes:
    """A file's bytes through the item cache (_fetch), as a source's refusal when it cannot be read."""
    from pathlib import Path  # noqa: PLC0415

    from evaluation_harness import _fetch  # noqa: PLC0415

    try:
        path, _sha = _fetch.fetch(url, None)
    except _fetch.FetchError as e:
        raise ValueError(str(e)) from e
    return Path(path).read_bytes()
