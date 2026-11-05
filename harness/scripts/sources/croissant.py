"""The croissant source: any Croissant dataset description, a file or a URL (PLAN_0.8.0 E7).

    evh dataset-create --dataset-id D --source croissant \\
        --query '{"url": "https://…/croissant.json", "record_set": "default", "text": "text", "id": "id", "limit": 200}'

Query: `url` or `path` (the description); `record_set` (its @id or name; default the first); `text` (the field whose
value is an item's text; required); `id` (the field that is an item's id; default its row number); `fields` (fields
kept as item fields, which need a field set); `limit`. Hugging Face, Kaggle and OpenML publish such descriptions.

What it reads: the record set's fields that take a `column` from one FileObject of parquet, CSV, JSON or JSON lines;
the FileObject is fetched and checked against its sha256 when it has one. A FileSet (many files) is refused: which files
it holds is the host's to say, so a Hugging Face description (its parquet in a FileSet) is refused. What it records: the source
block (provider croissant, ref the dataset's name, url, revision the publisher's version), the licence when it is one
`evh licences` knows, the `rai:` properties as the card, and the fields with their types as features.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from evaluation_harness import _fetch, _licences
from evaluation_harness._card import QUESTIONS

READABLE = {
    "application/x-parquet": "parquet",
    "application/vnd.apache.parquet": "parquet",
    "text/csv": "csv",
    "application/json": "json",
    "application/jsonlines": "jsonl",
    "application/x-ndjson": "jsonl",
}


def _key(k: str) -> str:
    """A JSON-LD key without its prefix: `cr:fileObject` and `fileObject` are the same key."""
    return k.split(":", 1)[1] if k.startswith(("cr:", "sc:", "schema:", "dct:")) else k


def _plain(v: Any) -> Any:
    """A JSON-LD node with its keys unprefixed, all the way down."""
    if isinstance(v, dict):
        return {_key(k): _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


def _list(v: Any) -> list:
    return v if isinstance(v, list) else [] if v is None else [v]


def _ref(v: Any) -> str | None:
    """The @id a reference names."""
    return v.get("@id") if isinstance(v, dict) else v if isinstance(v, str) else None


class Source:
    """Items from a Croissant dataset's record set."""

    def __init__(self, options: dict) -> None:
        self.options = options
        self._doc: dict | None = None

    def _load(self, query: dict) -> tuple[dict, str]:
        """(the description with plain keys, the base its relative URLs resolve against)."""
        if query.get("path"):
            p = Path(query["path"])
            raw, base = p.read_text(encoding="utf-8"), p.resolve().parent.as_uri() + "/"
        elif query.get("url"):
            path, _sha = _fetch.fetch(str(query["url"]), None)
            raw, base = Path(path).read_text(encoding="utf-8"), str(query["url"])
        else:
            raise ValueError("the croissant source needs a url or a path in its query")
        try:
            doc = json.loads(raw)
        except ValueError as e:
            raise ValueError(f"the description is not JSON: {e}") from e
        return _plain(doc), base

    def describe(self, query: dict) -> dict:
        """The dataset's own words: name, url, version, licence, rai: properties, the record set's fields."""
        doc, _base = self._load(query)
        rai = {
            k[4:]: v
            for k, v in doc.items()
            if k.startswith("rai:") and k[4:] in QUESTIONS and isinstance(v, str)
        }
        lic = None
        for given in _list(doc.get("license")):
            s = str(_ref(given) or given)
            tail = s.rstrip("/").rsplit("/", 1)[-1].removesuffix(".html")
            lic = _licences.canonical(s) or _licences.canonical(tail)
            if lic:
                break
        rs = self._record_set(doc, query)
        out: dict[str, Any] = {
            "source": {
                "provider": "croissant",
                "ref": doc.get("name"),
                "url": doc.get("url")
                if str(doc.get("url", "")).startswith(("http://", "https://"))
                else query.get("url"),
                "revision": str(doc["version"]) if doc.get("version") is not None else None,
            },
            "description": doc.get("description") or None,
            "features": {
                f.get("name") or _ref(f.get("@id")): str(f.get("dataType")) for f in _list(rs.get("field"))
            },
        }
        if lic:
            out["licence"] = lic
        if rai:
            out["card"] = rai
        return out

    def _record_set(self, doc: dict, query: dict) -> dict:
        sets = _list(doc.get("recordSet"))
        if not sets:
            raise ValueError("the description has no record set")
        want = query.get("record_set")
        if not want:
            return sets[0]
        for rs in sets:
            if want in (rs.get("@id"), rs.get("name")):
                return rs
        raise ValueError(
            f"no record set {want!r} (there are: {', '.join(str(r.get('name') or r.get('@id')) for r in sets)})"
        )

    def items(self, query: dict) -> Iterator[dict]:
        """One item per row of the record set's file: its text, id, row and kept fields."""
        doc, base = self._load(query)
        rs = self._record_set(doc, query)
        if not query.get("text"):
            raise ValueError('name the field that is an item\'s text: "text" in the query')
        by_name = {
            (f.get("name") or _ref(f.get("@id")) or "").rsplit("/", 1)[-1]: f for f in _list(rs.get("field"))
        }
        wanted = [query["text"], *([query["id"]] if query.get("id") else []), *(query.get("fields") or [])]
        missing = [n for n in wanted if n not in by_name]
        if missing:
            raise ValueError(
                f"the record set has no field {', '.join(missing)} (it has: {', '.join(by_name)})"
            )
        files = {d.get("@id") or d.get("name"): d for d in _list(doc.get("distribution"))}
        cols, file_id = {}, None
        for n in wanted:
            src = by_name[n].get("source") or {}
            fid = _ref(src.get("fileObject"))
            col = (src.get("extract") or {}).get("column")
            if not fid or not col:
                fs = files.get(_ref(src.get("fileSet")))
                raise ValueError(
                    f"field {n}: only a column of one FileObject is read"
                    + (
                        f"; this one is a FileSet of {fs.get('encodingFormat')} (which files it holds is the host's to"
                        " say, and only the Hub lists a Hugging Face description's files)"
                        if fs
                        else f" (this one is {json.dumps(src)[:120]})"
                    )
                )
            if file_id not in (None, fid):
                raise ValueError("the fields come from different files: one file per record set is read")
            file_id, cols[n] = fid, col
        f = files.get(file_id)
        if not f:
            raise ValueError(f"no FileObject {file_id!r} in the distribution")
        kind = READABLE.get(str(f.get("encodingFormat")))
        if not kind:
            raise ValueError(
                f"{file_id} is {f.get('encodingFormat')}: only parquet, CSV, JSON and JSON lines are read"
            )
        url = urljoin(base, str(f.get("contentUrl")))
        if url.startswith("file:"):
            data = Path(url[len("file://") :]).read_bytes()
            if f.get("sha256"):
                import hashlib  # noqa: PLC0415

                if hashlib.sha256(data).hexdigest() != f["sha256"]:
                    raise ValueError(f"{file_id}: its bytes are not the sha256 the description gives")
        else:
            path, _sha = _fetch.fetch(url, f.get("sha256"))
            data = Path(path).read_bytes()
        if kind == "parquet":
            import pyarrow.parquet as pq  # noqa: PLC0415

            # One thread: with its thread pool, pyarrow 26 aborted the process at exit (examples/_shared/hf_rows.py).
            table = pq.read_table(io.BytesIO(data), columns=sorted(set(cols.values())), use_threads=False)
            rows: list[dict] = table.to_pylist()
        elif kind == "csv":
            rows = list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
        elif kind == "jsonl":
            rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
        else:
            loaded = json.loads(data.decode("utf-8"))
            rows = loaded if isinstance(loaded, list) else [loaded]
        limit = int(query.get("limit") or 0)
        for n, row in enumerate(rows):
            if limit and n >= limit:
                return
            item: dict[str, Any] = {
                "item_id": str(row.get(cols[query["id"]])) if query.get("id") else f"row_{n}",
                "text": str(row.get(cols[query["text"]], "")),
                "row": n,
            }
            kept = {k: row.get(cols[k]) for k in query.get("fields") or []}
            if kept:
                item["fields"] = kept
            yield item
