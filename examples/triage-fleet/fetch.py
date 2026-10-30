#!/usr/bin/env python3
"""Fetch the triage decisions from Hugging Face, pinned to a revision, and restore what git does not hold.

    python examples/triage-fleet/fetch.py

Downloads `data/decisions.jsonl` and `data/verdicts.jsonl` of `chipi-nbgd/orrery-triage` at revision
`v1` into data/sources/orrery_triage_v1.hf/ (gitignored) and stops unless each file's sha256 is the one
pinned here. Then it restores, from those files, everything the repository commits only the hashes of:

  - each capture's record files (data/captures/<id>/records/), rebuilt through importer.py and checked
    against the sha256 the committed capture.json recorded;
  - each dataset's item files (data/sources/<dataset>/), checked against the dataset file's sha256s.

Nothing it writes is committed: the decisions are published on Hugging Face (CC-BY-4.0), and git holds
the ids, the hashes, the references, the runs and the goal. A private revision needs a token:
HF_TOKEN, or the file `huggingface-cli login` writes (~/.cache/huggingface/token).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] / "harness"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT.parent / "harness"))
from evaluation_harness import _importers  # noqa: E402
from importer import Importer  # noqa: E402

REPO = "chipi-nbgd/orrery-triage"
REVISION = "v1"
#: The bytes of each file at the revision (checked on every fetch: a moved tag fails here).
FILES = {
    "data/decisions.jsonl": "48a935cec543d0cf90cb0623208b4745ae573725a40c1ebe6616241b645cc8f6",
    "data/verdicts.jsonl": "144c955dff750bcd58f70b9ddb2e483a7a520770b3e58191e3deed359c8e55c3",
}
OUT = ROOT / "data" / "sources" / "orrery_triage_v1.hf"
#: The captures made from these files, and the datasets made from them.
CAPTURES = ("orrery_2026_10",)
DATASETS = ("orrery_triage_v1", "orrery_triage_v1_labelled")


def _token() -> str | None:
    tok = os.environ.get("HF_TOKEN", "").strip()
    f = Path.home() / ".cache" / "huggingface" / "token"
    return tok or (f.read_text(encoding="utf-8").strip() if f.is_file() else None)


def download(path: str) -> Path:
    """One file of the revision, checked against its pinned sha256."""
    url = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{path}"
    tok = _token()
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"} if tok else {})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310  # nosec B310 (a fixed https URL)
        data = r.read()
    got = hashlib.sha256(data).hexdigest()
    if got != FILES[path]:
        raise SystemExit(f"{REPO}@{REVISION}/{path}: sha256 {got}, pinned {FILES[path]}: refusing it")
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / Path(path).name
    dest.write_bytes(data)
    print(f"  {path}: {len(data):,} bytes, sha256 ok")
    return dest


def restore_capture(capture_id: str, decisions: Path, verdicts: Path) -> dict:
    """The capture's record files, rebuilt and checked against its capture.json. {id: record}."""
    base = ROOT / "data" / "captures" / capture_id
    doc = json.loads((base / "capture.json").read_text(encoding="utf-8"))
    query = {"path": str(decisions), "verdicts": str(verdicts)}
    recs = {r["id"]: _importers.normalise(r) for r in Importer({}).records(query)}
    (base / "records").mkdir(exist_ok=True)
    bad = []
    for entry in doc["records"]:
        rec = recs.get(entry["id"])
        if rec is None or _importers.record_sha256(rec) != entry["sha256"]:
            bad.append(entry["id"])
            continue
        (base / "records" / f"{entry['id']}.json").write_text(
            json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    if bad:
        raise SystemExit(
            f"capture {capture_id}: {len(bad)} record(s) differ from what it recorded, e.g. {bad[:3]}"
        )
    print(f"  capture {capture_id}: {len(doc['records'])} records restored, hashes ok")
    return recs


def restore_dataset(dataset_id: str, recs: dict) -> None:
    """The dataset's item files, from the records' bodies, checked against its sha256s."""
    doc = json.loads((ROOT / "data" / "datasets" / f"{dataset_id}.json").read_text(encoding="utf-8"))
    src = ROOT / doc["source_dir"]
    src.mkdir(parents=True, exist_ok=True)
    bad = []
    for it in doc["items"]:
        rec = recs.get(it["item_id"])
        data = _importers.canonical(rec["body"]) if rec else b""
        if hashlib.sha256(data).hexdigest() != it["source_sha256"]:
            bad.append(it["item_id"])
            continue
        (src / it["source_path"]).write_bytes(data)
    if bad:
        raise SystemExit(f"{dataset_id}: {len(bad)} item(s) differ from the dataset's hashes, e.g. {bad[:3]}")
    print(f"  {dataset_id}: {len(doc['items'])} items restored, hashes ok")


def main() -> int:
    """Fetch, check, restore."""
    print(f"{REPO} @ {REVISION}")
    decisions = download("data/decisions.jsonl")
    verdicts = download("data/verdicts.jsonl")
    recs: dict = {}
    for c in CAPTURES:
        if (ROOT / "data" / "captures" / c / "capture.json").is_file():
            recs.update(restore_capture(c, decisions, verdicts))
    for d in DATASETS:
        if (ROOT / "data" / "datasets" / f"{d}.json").is_file():
            restore_dataset(d, recs)
    print("next: evh dataset-materialize --dataset-id <each>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
