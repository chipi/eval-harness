#!/usr/bin/env python3
"""Fetch the de-duplication signals from Hugging Face, pinned to a revision, and restore what git does not hold.

    python examples/signal-fleet-dedup/fetch.py

Downloads `data/signals.jsonl` of `chipi-nbgd/signal-fleet-dedup` at revision `v1` into
data/sources/fleet_dedup_v1.hf/ (gitignored), stops unless its sha256 is the one pinned here, and restores the
capture's record files and the dataset's item files from it, each checked against the hashes git holds.
A private revision needs a token: HF_TOKEN, or ~/.cache/huggingface/token.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "harness"
sys.path.insert(0, str(ROOT))
from evaluation_harness import _importers  # noqa: E402
from evaluation_harness.importers.jsonl import Importer  # noqa: E402

REPO, REVISION, PATH = "chipi-nbgd/signal-fleet-dedup", "v1", "data/signals.jsonl"
SHA256 = "0f21cea78cae61faffaae1988d1389dbc5fb0f3b97b292e40bd0c3e2ad7ba8cd"
OUT = ROOT / "data" / "sources" / "fleet_dedup_v1.hf"
CAPTURE, DATASET = "fleet_dedup_2026_08", "fleet_dedup_v1"
#: The capture's query, as `evh capture` recorded it (each signal's fingerprint is its id, the whole row its body).
QUERY = {"path": "data/sources/fleet_dedup_v1.hf/signals.jsonl", "id": "fingerprint", "body": "row"}


def main() -> int:
    """Fetch, check, restore."""
    tok = os.environ.get("HF_TOKEN", "").strip() or (
        (Path.home() / ".cache/huggingface/token").read_text().strip()
        if (Path.home() / ".cache/huggingface/token").is_file()
        else ""
    )
    url = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{PATH}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"} if tok else {})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310  # nosec B310 (a fixed https URL)
        data = r.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise SystemExit(f"{REPO}@{REVISION}/{PATH}: sha256 differs from the pinned {SHA256}: refusing it")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "signals.jsonl").write_bytes(data)
    print(f"{REPO} @ {REVISION}: {PATH}, {len(data):,} bytes, sha256 ok")
    cap = ROOT / "data" / "captures" / CAPTURE
    if not (cap / "capture.json").is_file():
        print(f"next: evh capture --importer jsonl --query '{json.dumps(QUERY)}' --capture {CAPTURE}")
        return 0
    query = {**QUERY, "path": str(OUT / "signals.jsonl")}
    recs = {r["id"]: _importers.normalise(r) for r in Importer({}).records(query)}
    doc = json.loads((cap / "capture.json").read_text())
    (cap / "records").mkdir(exist_ok=True)
    for entry in doc["records"]:
        rec = recs.get(entry["id"])
        if rec is None or _importers.record_sha256(rec) != entry["sha256"]:
            raise SystemExit(f"capture {CAPTURE}: {entry['id']} differs from what it recorded")
        (cap / "records" / f"{entry['id']}.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    print(f"  capture {CAPTURE}: {len(doc['records'])} records restored, hashes ok")
    dsf = ROOT / "data" / "datasets" / f"{DATASET}.json"
    if dsf.is_file():
        ds = json.loads(dsf.read_text())
        src = ROOT / ds["source_dir"]
        src.mkdir(parents=True, exist_ok=True)
        for it in ds["items"]:
            body = _importers.canonical(recs[it["item_id"]]["body"])
            if hashlib.sha256(body).hexdigest() != it["source_sha256"]:
                raise SystemExit(f"{DATASET}: {it['item_id']} differs from the dataset's hash")
            (src / it["source_path"]).write_bytes(body)
        print(f"  {DATASET}: {len(ds['items'])} items restored, hashes ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
