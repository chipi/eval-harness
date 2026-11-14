"""Faithfulness records (RFC-032 step 7, RFC-030): a replay of a code record's versions compared item by item with
production's arm, written once, and the exceptions a person names beside it, with one table of where each lives, read
through a data root (`under`) so the catalog reads them where its data directory is, a deployment's copy of the
project's included.

    data/faithfulness/<model_id>/<n>.json              the record, never edited
    data/faithfulness/<model_id>/<n>.exceptions.jsonl  the disagreements a person named (appended: who, when, cause)

A version's faithfulness, the summary the Models page and `evh models` show, is read from these records and never kept
in the model record: the newest record that replayed the version's commit says (`summaries`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness.model.entity import Entity

#: Its id is `<model_id>/<n>`: the code record it is of, and its number there.
FAITHFULNESS = Entity(
    name="faithfulness record",
    plural="faithfulness records",
    folder="faithfulness",
    id_field="",
    parent_field="model_id",
    schema="faithfulness.schema.json",
    suffix=".json",
    id_pattern=re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*"),
    editable=False,
)


def records_dir(model_id: str, data: Path | None = None) -> Path:
    """data/faithfulness/<model_id>/."""
    return FAITHFULNESS.under(data).base() / model_id


def record_file(model_id: str, n: int, data: Path | None = None) -> Path:
    """Record n."""
    return records_dir(model_id, data) / f"{n}.json"


def exceptions_file(model_id: str, n: int, data: Path | None = None) -> Path:
    """The disagreements named for record n."""
    return records_dir(model_id, data) / f"{n}.exceptions.jsonl"


def numbers(model_id: str, data: Path | None = None) -> list[int]:
    """The record numbers written for a code record, ascending."""
    d = records_dir(model_id, data)
    if not _store.is_dir(d):
        return []
    return sorted(int(p.stem) for p in _store.iterdir(d) if p.suffix == ".json" and p.stem.isdigit())


def model_ids(data: Path | None = None) -> list[str]:
    """The code records that have faithfulness records, sorted."""
    base = FAITHFULNESS.under(data).base()
    return sorted(p.name for p in _store.iterdir(base) if _store.is_dir(p)) if _store.is_dir(base) else []


def exceptions(model_id: str, n: int, data: Path | None = None) -> list[dict[str, Any]]:
    """The disagreements named for record n, in the order they were named."""
    p = exceptions_file(model_id, n, data)
    if not _store.is_file(p):
        return []
    out = []
    for line in _store.read_text(p, encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def load(model_id: str, n: int, data: Path | None = None) -> dict[str, Any]:
    """Record n, with its named exceptions under `exceptions`."""
    p = record_file(model_id, n, data)
    if not _store.is_file(p):
        _common.die(
            f"no faithfulness record {model_id}/{n} (made: {numbers(model_id, data) or 'none'})", "not-found"
        )
    rec = json.loads(_store.read_text(p, encoding="utf-8"))
    rec["exceptions"] = exceptions(model_id, n, data)
    return rec


def latest(
    model_id: str, dataset_id: str, adapter_sha256: Any = ..., data: Path | None = None
) -> dict[str, Any] | None:
    """The newest record of a code record on a dataset (made with this adapter, when one is given), or None."""
    for n in reversed(numbers(model_id, data)):
        rec = load(model_id, n, data)
        if rec.get("dataset_id") == dataset_id and (
            adapter_sha256 is ... or rec.get("adapter_sha256") == adapter_sha256
        ):
            return rec
    return None


def write(rec: dict[str, Any]) -> int:
    """Write a new record under the next number (never over one); returns the number."""
    for _ in range(50):
        n = (numbers(rec["model_id"]) or [0])[-1] + 1
        body = {**rec, "n": n}
        data = (json.dumps(body, indent=2, sort_keys=True) + "\n").encode()
        if _store.create_new(record_file(rec["model_id"], n), data):
            return n
    _common.die(f"faithfulness {rec['model_id']}: could not take a record number", "failed")
    return 0  # pragma: no cover - die exits


def append_exception(model_id: str, n: int, ev: dict[str, Any]) -> None:
    """One named disagreement at the end of record n's exceptions (the caller holds the code record's lock: in the
    SQLite store an append is a read and a rewrite)."""
    p = exceptions_file(model_id, n)
    before = _store.read_text(p, encoding="utf-8") if _store.is_file(p) else ""
    if before and not before.endswith("\n"):
        before += "\n"
    _store.write_text(p, before + json.dumps(ev, sort_keys=True) + "\n")


def summaries(model_id: str, data: Path | None = None) -> dict[str, dict[str, Any]]:
    """{full commit: how faithfully a replay reproduced it} from the records: the items that ran at the commit, how many
    agreed, the named exceptions among those that did not, the record and when. A later record's answer for a commit
    stands in for an earlier one's."""
    out: dict[str, dict[str, Any]] = {}
    for n in numbers(model_id, data):
        rec = load(model_id, n, data)
        named = {e.get("item_id") for e in rec.get("exceptions") or []}
        differ: dict[str, list[str]] = {}
        for d in rec.get("disagreements") or []:
            differ.setdefault(str(d.get("commit")), []).append(d["item_id"])
        for full, items in (rec.get("commits") or {}).items():
            mine = differ.get(full, [])
            out[full] = {
                "agreed": int(items) - len(mine),
                "items": int(items),
                "exceptions": sorted(i for i in mine if i in named),
                "run": f"{model_id}/{n}",
                "at": rec["at"],
            }
    return out


def with_summaries(rec: dict[str, Any], data: Path | None = None) -> dict[str, Any]:
    """A model record as the views read it: each version of a code record with its `faithfulness`, from the records
    (a version no replay has run has none)."""
    if not rec.get("versions") or not rec.get("model_id"):
        return rec
    found = summaries(str(rec["model_id"]), data)
    versions = []
    for v in rec["versions"]:
        if not isinstance(v, dict):
            versions.append(v)
            continue
        s = next((x for c, x in found.items() if c.startswith(str(v.get("commit")))), None)
        versions.append(
            {**{k: x for k, x in v.items() if k != "faithfulness"}, **({"faithfulness": s} if s else {})}
        )
    return {**rec, "versions": versions}
