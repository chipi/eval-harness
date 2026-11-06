#!/usr/bin/env python3
"""Migrate the references made before labels existed (RFC-023 step 3): each records how it was promoted.

    python tools/migrate_references_to_labels.py --dry-run
    python tools/migrate_references_to_labels.py

For every reference without a `promoted_from`:

- its manifest gains `promoted_from` (the label set, its dataset, the source read from how it was made) and the
  reason "promoted before labels existed (0.6.0)". Only the manifest changes: a run's fingerprint hashes a
  reference's texts and its manifest's authorship fields, and neither moves, so no run's score or hash moves;
- when its texts are here, they are copied byte for byte into a label set, data/labels/<dataset>/<tier>_<name>/,
  with that source; when they are fetched (a dataset's own labels, not redistributed), the promotion records no set:
  the texts are rebuilt by the example's fetcher, and a label set is never made of text that is not here.

The source: a run's outputs (`from_run`, or `authored_by` alone) are `model`; outcomes by rules (`from_outcomes`)
are `rule`; a fetcher's, the owner's verdicts or fixture labels are `person`. Idempotent: a reference that has its
`promoted_from` is left as it is.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package

import argparse
import hashlib

from evaluation_harness import _common, _store
from evaluation_harness._common import now, read_json, write_json

REASON = "promoted before labels existed (0.6.0): its tier was given when it was made"


def source_of(m: dict) -> dict:
    """The label source a reference's manifest says made it."""
    src = str(m.get("source") or "")
    if m.get("from_outcomes"):
        outcomes = m["from_outcomes"]
        return {
            "kind": "rule",
            **{
                k: outcomes.get(k)
                for k in ("capture", "capture_sha256", "captured_at", "mapping", "mapping_sha256")
            },
        }
    if m.get("from_run"):
        fr = m["from_run"]
        return {
            "kind": "model",
            **{k: fr.get(k) for k in ("run_id", "config_id", "fingerprint_hash", "build")},
            "model": m.get("model"),
        }
    if m.get("authored_by"):
        return {"kind": "model", "config_id": m.get("authored_by"), "model": m.get("model")}
    if "--source owner" in src:
        return {"kind": "person", "by": "owner", "via": src.split(":")[0]}
    if "--source fixture" in src:
        return {"kind": "person", "by": "fixture labels", "via": src.split(":")[0]}
    if "adjudicate" in src:
        return {"kind": "person", "by": "adjudication of the dataset's labels", "via": src}
    return {"kind": "person", "by": "the dataset's authors", "via": src}


def main() -> int:
    """Migrate every reference that has no promotion record."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="say what would change, change nothing")
    args = ap.parse_args()
    refs = sorted(_store.glob(_common.REFERENCES, "*/*/manifest.json"))
    done = sets = 0
    for mf in refs:
        m = read_json(mf)
        tier, name = mf.parent.parent.name, mf.parent.name
        if m.get("promoted_from"):
            continue
        ds_id = m.get("dataset_id")
        texts = sorted(_store.glob(mf.parent, "*.txt"))
        source = source_of(m)
        set_name = f"{tier}_{name}" if texts else None
        print(
            f"{tier}/{name}: {source['kind']} · {source.get('by') or source.get('run_id') or source.get('config_id') or source.get('capture')}"
            + (
                f", {len(texts)} label(s) into data/labels/{ds_id}/{set_name}"
                if set_name
                else ", texts fetched elsewhere: no label set"
            )
        )
        if args.dry_run:
            continue
        if set_name:
            ds = read_json(_common.DATASETS / f"{ds_id}.json")
            item_sha = {it["item_id"]: it.get("source_sha256") or "" for it in ds.get("items") or []}
            out = _common.LABELS / ds_id / set_name
            _store.mkdir(out, parents=True, exist_ok=True)
            rows = {}
            for t in texts:
                data = _store.read_bytes(t)
                _store.write_bytes(out / t.name, data)
                rows[t.stem] = {
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "item_sha256": item_sha.get(t.stem, ""),
                }
            write_json(
                out / "labels.json",
                {
                    "dataset_id": ds_id,
                    "set": set_name,
                    "source": source,
                    "created_at": now(),
                    "guideline": None,
                    "n_items": len(rows),
                    "items": rows,
                    "note": f"made from the reference {tier}/{name}, which existed before labels did",
                },
            )
            sets += 1
        m["promoted_from"] = {"labels": set_name, "dataset_id": ds_id, "source": source}
        m["reason"] = REASON
        write_json(mf, m)
        done += 1
    print(
        ("would migrate" if args.dry_run else "migrated")
        + f" {sum(1 for f in refs if not read_json(f).get('promoted_from')) if args.dry_run else done} reference(s), {sets} label set(s) made"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
