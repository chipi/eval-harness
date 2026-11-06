#!/usr/bin/env python3
"""Fetch the triage decisions from Hugging Face, pinned to each revision, and restore what git does not hold.

    python examples/triage-fleet/fetch.py                  # both revisions
    python examples/triage-fleet/fetch.py --revision v2    # one

`chipi-nbgd/orrery-triage` has two revisions, each with `data/decisions.jsonl` and `data/verdicts.jsonl`:

  v1  233 decisions as the fleet's builder rebuilt them on 2026-10-29: capture orrery_2026_10 and the datasets
      orrery_triage_v1, orrery_triage_v1_labelled, orrery_triage_smoke;
  v2  the same 233 decisions without the rebuild's hindsight (2026-11-04, signal-fleet's
      build_orrery_items_v2.py): capture orrery_2026_10_v2 and the dataset orrery_triage_v1_labelled_v2.

Each revision's files go to their own data/sources/orrery_triage_<rev>.hf/ (gitignored), and the fetch stops
unless each file's sha256 is the one pinned here (a moved tag fails). Then it restores, from those files,
everything the repository commits only the hashes of:

  - each capture's record files (data/captures/<id>/records/), rebuilt through importer.py with the query that
    capture recorded (so a field a past capture did not ask for stays out) and checked against the sha256 its
    committed capture.json recorded;
  - each dataset's item files (data/sources/<dataset>/), checked against the dataset file's sha256s.

Nothing it writes is committed: the decisions are published on Hugging Face (CC-BY-4.0), and git holds
the ids, the hashes, the references, the runs and the goal. A private revision needs a token:
HF_TOKEN, or the file `huggingface-cli login` writes (~/.cache/huggingface/token).
"""

from __future__ import annotations

import argparse
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
from evaluation_harness import (  # noqa: E402
    _importers,
    _store,
)
from importer import Importer  # noqa: E402

REPO = "chipi-nbgd/orrery-triage"
#: Per revision: the bytes of each file (checked on every fetch), where they go, and what is restored from them.
REVISIONS = {
    "v1": {
        "files": {
            "data/decisions.jsonl": "48a935cec543d0cf90cb0623208b4745ae573725a40c1ebe6616241b645cc8f6",
            "data/verdicts.jsonl": "144c955dff750bcd58f70b9ddb2e483a7a520770b3e58191e3deed359c8e55c3",
        },
        "out": ROOT / "data" / "sources" / "orrery_triage_v1.hf",
        "captures": ("orrery_2026_10",),
        "datasets": ("orrery_triage_v1", "orrery_triage_v1_labelled", "orrery_triage_smoke"),
    },
    "v2": {
        "files": {
            "data/decisions.jsonl": "d2b158e0d30669cc00aa699f8b831f46e885a1afa0c455f4396e2b69b31755ae",
            "data/verdicts.jsonl": "144c955dff750bcd58f70b9ddb2e483a7a520770b3e58191e3deed359c8e55c3",
        },
        "out": ROOT / "data" / "sources" / "orrery_triage_v2.hf",
        "captures": ("orrery_2026_10_v2",),
        "datasets": ("orrery_triage_v1_labelled_v2",),
    },
}


def _token() -> str | None:
    tok = os.environ.get("HF_TOKEN", "").strip()
    f = Path.home() / ".cache" / "huggingface" / "token"
    return tok or (_store.read_text(f, encoding="utf-8").strip() if _store.is_file(f) else None)


def download(rev: str, path: str) -> Path:
    """One file of the revision, checked against its pinned sha256."""
    spec = REVISIONS[rev]
    url = f"https://huggingface.co/datasets/{REPO}/resolve/{rev}/{path}"
    tok = _token()
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"} if tok else {})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310  # nosec B310 (a fixed https URL)
        data = r.read()
    got = hashlib.sha256(data).hexdigest()
    if got != spec["files"][path]:
        raise SystemExit(f"{REPO}@{rev}/{path}: sha256 {got}, pinned {spec['files'][path]}: refusing it")
    _store.mkdir(spec["out"], parents=True, exist_ok=True)
    dest = spec["out"] / Path(path).name
    _store.write_bytes(dest, data)
    print(f"  {path}: {len(data):,} bytes, sha256 ok")
    return dest


def restore_capture(capture_id: str, decisions: Path, verdicts: Path) -> dict:
    """The capture's record files, rebuilt with its recorded query and checked against its capture.json."""
    base = ROOT / "data" / "captures" / capture_id
    doc = json.loads(_store.read_text(base / "capture.json", encoding="utf-8"))
    # the recorded query's own keys (v2_fields, prompt_fields, ...), the files where this fetch put them
    query = dict(doc.get("query") or {}, path=str(decisions), verdicts=str(verdicts))
    recs = {r["id"]: _importers.normalise(r) for r in Importer({}).records(query)}
    _store.mkdir(base / "records", exist_ok=True)
    bad = []
    for entry in doc["records"]:
        rec = recs.get(entry["id"])
        if rec is None or _importers.record_sha256(rec) != entry["sha256"]:
            bad.append(entry["id"])
            continue
        _store.write_text(
            base / "records" / f"{entry['id']}.json",
            json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if bad:
        raise SystemExit(
            f"capture {capture_id}: {len(bad)} record(s) differ from what it recorded, e.g. {bad[:3]}"
        )
    print(f"  capture {capture_id}: {len(doc['records'])} records restored, hashes ok")
    return recs


def restore_dataset(dataset_id: str, recs: dict) -> None:
    """The dataset's item files, from the records' bodies, checked against its sha256s."""
    doc = json.loads(_store.read_text(ROOT / "data" / "datasets" / f"{dataset_id}.json", encoding="utf-8"))
    src = ROOT / doc["source_dir"]
    _store.mkdir(src, parents=True, exist_ok=True)
    bad = []
    for it in doc["items"]:
        rec = recs.get(it["item_id"])
        data = _importers.canonical(rec["body"]) if rec else b""
        if hashlib.sha256(data).hexdigest() != it["source_sha256"]:
            bad.append(it["item_id"])
            continue
        _store.write_bytes(src / it["source_path"], data)
    if bad:
        raise SystemExit(f"{dataset_id}: {len(bad)} item(s) differ from the dataset's hashes, e.g. {bad[:3]}")
    print(f"  {dataset_id}: {len(doc['items'])} items restored, hashes ok")


def fetch(rev: str) -> None:
    """One revision: fetch, check, restore."""
    spec = REVISIONS[rev]
    print(f"{REPO} @ {rev}")
    decisions = download(rev, "data/decisions.jsonl")
    verdicts = download(rev, "data/verdicts.jsonl")
    recs: dict = {}
    for c in spec["captures"]:
        if _store.is_file(ROOT / "data" / "captures" / c / "capture.json"):
            recs.update(restore_capture(c, decisions, verdicts))
    for d in spec["datasets"]:
        if _store.is_file(ROOT / "data" / "datasets" / f"{d}.json"):
            restore_dataset(d, recs)


def main() -> int:
    """Fetch each revision asked for (default: all)."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--revision", choices=sorted(REVISIONS), help="one revision (default: every one)")
    a = ap.parse_args()
    for rev in [a.revision] if a.revision else list(REVISIONS):
        fetch(rev)
    print("next: evh dataset-materialize --dataset-id <each>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
