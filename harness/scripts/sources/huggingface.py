"""The huggingface source: a Hugging Face Hub dataset, read pinned to a commit (PLAN_0.8.0 P1).

    evh dataset-create --dataset-id D --source huggingface \\
        --query '{"ref": "fancyzhx/ag_news", "split": "test", "text": "text", "fields": ["label"], "limit": 200}'

Query: `ref` and `split` (required); `config` (default `default`); `text` (the column that is an item's text);
`id` (the column that is its id; default `row_<n>`); `fields`; `offset`, `limit`; `revision` (a commit of the Hub's
parquet conversion to read; default the one the Hub points to now).

What it reads: the Hub's parquet conversion of the split (`refs/convert/parquet`) at one commit, file by file, each
fetched by `resolve/<commit>/<path>` and checked against the sha256 the Hub lists for it, so the same query reads the
same bytes again. What it records: the source block (provider huggingface, the ref, the conversion's commit as
`revision`, config, split, gated, the sha256 of the Hub's description, the viewer page per row as `item_url`), the
licence when `evh licences` knows the card's, the card's metadata in the card's words, and the features with their
types. The Hub is `HF_ENDPOINT` (default https://huggingface.co); a gated dataset's token goes in
`EVAL_FETCH_HEADERS` (`{"huggingface.co": {"Authorization": "Bearer …"}}`), never in the query.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from evaluation_harness import _fetch, _licences


def _endpoint() -> str:
    return os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")


def _api(path: str) -> Any:
    """One Hub API call, as JSON; the project's headers for the host go with it (a gated dataset's token)."""
    url = f"{_endpoint()}{path}"
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"HF_ENDPOINT {_endpoint()!r} is not an http(s) address")
    req = urllib.request.Request(url, headers={"User-Agent": "evaluation-harness"})  # noqa: S310 — http(s) checked above
    # The project's headers for the host (_fetch's one table): a gated dataset's token.
    for k, v in _fetch._headers_for(url).items():
        req.add_unredirected_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310  # nosec B310 — http(s) checked above
            return json.loads(resp.read())
    except Exception as e:  # every failure to read the Hub is the same refusal
        raise ValueError(f"the Hub did not answer {path}: {e}") from e


def _list(v: Any) -> list:
    return v if isinstance(v, list) else [] if v is None else [v]


#: The Hub card's metadata keys, and the card question (Croissant RAI) each answers, in the card's words.
CARD = {
    "task_categories": ("dataUseCases", "tasks"),
    "annotations_creators": ("dataAnnotationProtocol", "annotations created by"),
    "language_creators": ("dataCollectionType", "language created by"),
    "source_datasets": ("dataCollectionRawData", "source datasets"),
}


class Source:
    """Items from a Hugging Face Hub dataset's parquet conversion, at one commit."""

    def __init__(self, options: dict) -> None:
        self.options = options

    @staticmethod
    def _need(query: dict) -> tuple[str, str, str]:
        ref, split = query.get("ref"), query.get("split")
        if not ref or not split:
            raise ValueError("the huggingface source needs a ref and a split in its query")
        return str(ref), str(query.get("config") or "default"), str(split)

    def _revision(self, ref: str, query: dict) -> str:
        if query.get("revision"):
            return str(query["revision"])
        refs = _api(f"/api/datasets/{ref}/refs")
        conv = next((c for c in refs.get("converts") or [] if c.get("name") == "parquet"), None)
        if not conv:
            raise ValueError(f"{ref} has no parquet conversion on the Hub (refs/convert/parquet)")
        return str(conv["targetCommit"])

    def describe(self, query: dict) -> dict:
        """The Hub's words for the dataset: the source block, licence, card metadata, features."""
        ref, config, split = self._need(query)
        info = _api(f"/api/datasets/{ref}")
        card = info.get("cardData") or {}
        desc = str(info.get("description") or "")
        out: dict[str, Any] = {
            "source": {
                "provider": "huggingface",
                "ref": ref,
                "url": f"{_endpoint()}/datasets/{ref}",
                "revision": self._revision(ref, query),
                "config": config,
                "split": split,
                "gated": bool(info.get("gated")),
                "description_sha256": hashlib.sha256(desc.encode("utf-8")).hexdigest() if desc else None,
                "item_url": f"{_endpoint()}/datasets/{ref}/viewer/{config}/{split}?row={{row}}",
            },
            "description": card.get("pretty_name") or None,
        }
        for given in _list(card.get("license")):
            lic = _licences.canonical(str(given))
            if lic:
                out["licence"] = lic
                break
        answers = {}
        for key, (question, words) in CARD.items():
            vals = [str(v) for v in _list(card.get(key))]
            if vals:
                answers[question] = f"{words}: {', '.join(vals)} (the Hub card's {key})"
        if answers:
            out["card"] = answers
        infos = _list(card.get("dataset_info"))
        mine = next(
            (d for d in infos if d.get("config_name", "default") == config), infos[0] if infos else {}
        )
        feats = {}
        for f in _list(mine.get("features")):
            dtype = f.get("dtype") or ("class_label" if "class_label" in f else "struct")
            feats[str(f.get("name"))] = "int64" if dtype == "class_label" else str(dtype)
        out["features"] = feats
        return out

    def items(self, query: dict) -> Iterator[dict]:
        """Each row of the split, in the conversion's file and row order: its text, id, row and kept fields."""
        import pyarrow.parquet as pq  # noqa: PLC0415

        ref, config, split = self._need(query)
        if not query.get("text"):
            raise ValueError('name the column that is an item\'s text: "text" in the query')
        rev = self._revision(ref, query)
        tree = _api(f"/api/datasets/{ref}/tree/{quote(rev, safe='')}/{quote(config)}/{quote(split)}")
        files = sorted(
            (e for e in tree if str(e.get("path", "")).endswith(".parquet")), key=lambda e: e["path"]
        )
        if not files:
            raise ValueError(f"{ref}: no parquet files for {config}/{split} at {rev}")
        cols = [query["text"], *([query["id"]] if query.get("id") else []), *(query.get("fields") or [])]
        offset, limit = int(query.get("offset") or 0), int(query.get("limit") or 0)
        n = 0
        for e in files:
            url = f"{_endpoint()}/datasets/{ref}/resolve/{rev}/{e['path']}"
            try:
                path, _sha = _fetch.fetch(url, (e.get("lfs") or {}).get("oid"))
            except _fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            data = Path(path).read_bytes()
            try:
                # One thread: with its thread pool, pyarrow 26 aborted the process at exit (examples/_shared/hf_rows.py).
                table = pq.read_table(io.BytesIO(data), columns=sorted(set(cols)), use_threads=False)
            except Exception as exc:  # a column the split does not have, or not parquet
                raise ValueError(f"{e['path']}: {exc}") from exc
            for row in table.to_pylist():
                if n < offset:
                    n += 1
                    continue
                if limit and n >= offset + limit:
                    return
                item: dict[str, Any] = {
                    "item_id": str(row[query["id"]]) if query.get("id") else f"row_{n}",
                    "text": str(row.get(query["text"]) or ""),
                    "row": n,
                }
                kept = {k: row.get(k) for k in query.get("fields") or []}
                if kept:
                    item["fields"] = kept
                yield item
                n += 1
