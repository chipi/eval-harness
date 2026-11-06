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

`publish` (`evh dataset-publish --to huggingface --query '{"repo": "owner/name"}'`) writes a dataset to a new repo,
private unless `"public": true`: its items as `data/test.parquet` (item_id, text, source_sha256, each field), the
record as `evh/<dataset_id>.json` and the card as README.md, in one commit; then reads each file back at that commit
and checks its sha256, and each item's text against its own. It refuses a repo that exists. The token is
huggingface_hub's (HF_TOKEN, or `hf auth login`); it is never printed.
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


#: A split's parquet files at a revision, and each file's table (per columns read), kept for the process: a fetcher
#: pages through a split, and each page must not fetch and read its files again.
_FILES: dict[tuple, list[dict]] = {}
_TABLES: dict[tuple, Any] = {}

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

    def rows(self, query: dict, columns: list[str] | None = None) -> Iterator[tuple[int, dict]]:
        """(row number, row) of the split's rows [offset, offset + limit), every column unless `columns` names some,
        read from the parquet conversion at the query's revision (or the current one). Each file is fetched once and
        read once a process."""
        import pyarrow.parquet as pq  # noqa: PLC0415

        ref, config, split = self._need(query)
        rev = self._revision(ref, query)
        key = (_endpoint(), ref, rev, config, split)
        if key not in _FILES:
            tree = _api(f"/api/datasets/{ref}/tree/{quote(rev, safe='')}/{quote(config)}/{quote(split)}")
            files = sorted(
                (e for e in tree if str(e.get("path", "")).endswith(".parquet")), key=lambda e: e["path"]
            )
            if not files:
                raise ValueError(f"{ref}: no parquet files for {config}/{split} at {rev}")
            _FILES[key] = files
        offset, limit = int(query.get("offset") or 0), int(query.get("limit") or 0)
        start = 0
        for e in _FILES[key]:
            oid = (e.get("lfs") or {}).get("oid")
            tkey = (oid or e["path"], tuple(sorted(set(columns))) if columns else None)
            if tkey not in _TABLES:
                url = f"{_endpoint()}/datasets/{ref}/resolve/{rev}/{e['path']}"
                try:
                    path, _sha = _fetch.fetch(url, oid)
                except _fetch.FetchError as exc:
                    raise ValueError(str(exc)) from exc
                try:
                    # One thread: with its thread pool, pyarrow 26 aborted the process at exit (examples/_shared/hf_rows.py).
                    _TABLES[tkey] = pq.read_table(
                        io.BytesIO(Path(path).read_bytes()),
                        columns=sorted(set(columns)) if columns else None,
                        use_threads=False,
                    )
                except Exception as exc:  # a column the split does not have, or not parquet
                    raise ValueError(f"{e['path']}: {exc}") from exc
            table = _TABLES[tkey]
            lo = max(offset, start)
            hi = start + table.num_rows if not limit else min(offset + limit, start + table.num_rows)
            if lo < hi:
                for i, row in enumerate(table.slice(lo - start, hi - lo).to_pylist()):
                    yield lo + i, row
            start += table.num_rows
            if limit and start >= offset + limit:
                return

    def items(self, query: dict) -> Iterator[dict]:
        """Each row of the split, in the conversion's file and row order: its text, id, row and kept fields."""
        if not query.get("text"):
            raise ValueError('name the column that is an item\'s text: "text" in the query')
        cols = [query["text"], *([query["id"]] if query.get("id") else []), *(query.get("fields") or [])]
        for n, row in self.rows(query, cols):
            item: dict[str, Any] = {
                "item_id": str(row[query["id"]]) if query.get("id") else f"row_{n}",
                "text": str(row.get(query["text"]) or ""),
                "row": n,
            }
            kept = {k: row.get(k) for k in query.get("fields") or []}
            if kept:
                item["fields"] = kept
            yield item

    def publish(self, record: dict, items: list[tuple[dict, bytes]], query: dict) -> dict:
        """Write the dataset to a new Hub repo in one commit and read it back; {repo, revision, url, private, files}."""
        import pyarrow as pa  # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415
        from evaluation_harness import _hf_readme  # noqa: PLC0415

        repo = str(query.get("repo") or "")
        if repo.count("/") != 1 or not all(repo.split("/")):
            raise ValueError('name the repo to write: "repo": "owner/name" in the query')
        private = not query.get("public")
        api = self.options.get("api")
        if api is None:
            from huggingface_hub import HfApi  # noqa: PLC0415
            from huggingface_hub.utils import disable_progress_bars  # noqa: PLC0415

            disable_progress_bars()  # a command's output is its result lines, not upload bars
            api = HfApi(endpoint=_endpoint())
        if api.repo_exists(repo, repo_type="dataset"):
            raise ValueError(f"{repo} exists on the Hub: a publish writes a new repo, never over one")
        fields = sorted({k for it, _b in items for k in (it.get("fields") or {})})
        clash = [f for f in fields if f in ("item_id", "text", "source_sha256")]
        if clash:
            raise ValueError(f"field(s) {', '.join(clash)} would overwrite a column of the published table")
        table = pa.table(
            {
                "item_id": [it["item_id"] for it, _b in items],
                "text": [b.decode("utf-8") for _it, b in items],
                "source_sha256": [it["source_sha256"] for it, _b in items],
                **{f: [(it.get("fields") or {}).get(f) for it, _b in items] for f in fields},
            }
        )
        buf = io.BytesIO()
        pq.write_table(table, buf)
        files = {
            "data/test.parquet": buf.getvalue(),
            f"evh/{record['dataset_id']}.json": (
                json.dumps(record, indent=1, sort_keys=True) + "\n"
            ).encode(),
            "README.md": _hf_readme.readme(record, data_file="data/test.parquet").encode(),
        }
        from huggingface_hub import CommitOperationAdd  # noqa: PLC0415

        api.create_repo(repo, repo_type="dataset", private=private, exist_ok=False)
        info = api.create_commit(
            repo,
            [CommitOperationAdd(path_in_repo=k, path_or_fileobj=v) for k, v in files.items()],
            commit_message=f"{record['dataset_id']} version {record.get('version')}, from the evaluation harness",
            repo_type="dataset",
        )
        rev = info.oid
        bad = []
        for path, data in files.items():
            got = Path(api.hf_hub_download(repo, path, repo_type="dataset", revision=rev)).read_bytes()
            if hashlib.sha256(got).hexdigest() != hashlib.sha256(data).hexdigest():
                bad.append(path)
        back = pq.read_table(
            api.hf_hub_download(repo, "data/test.parquet", repo_type="dataset", revision=rev),
            use_threads=False,
        )
        for row in back.to_pylist():
            if hashlib.sha256(row["text"].encode("utf-8")).hexdigest() != row["source_sha256"]:
                bad.append(f"item {row['item_id']}")
        if bad:
            raise ValueError(f"{repo}@{rev}: read back, {', '.join(bad[:5])} not the bytes written")
        return {
            "provider": "huggingface",
            "repo": repo,
            "revision": rev,
            "url": f"{_endpoint()}/datasets/{repo}",
            "private": private,
            "files": {k: hashlib.sha256(v).hexdigest() for k, v in files.items()},
        }
