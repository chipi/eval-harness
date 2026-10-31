#!/usr/bin/env python3
"""A reference for a triage dataset from verdicts.jsonl: one label per item, from the chosen sources.

    python examples/triage-fleet/write_gold.py --dataset-id orrery_triage_v1_labelled \\
        --verdicts data/sources/orrery_triage_v1.hf/verdicts.jsonl
    python examples/triage-fleet/write_gold.py --dataset-id orrery_triage_v1_labelled \\
        --verdicts ... --source fixture --name silver/orrery_triage_v1_labelled_hand

Default: gold/<dataset>, from the owner's rows (owner-issue-verdict, owner-item-label). A silver one from
another source carries its own caveat (ADR-0020). Each item's text is its label (file, dismiss, escalate,
cleanup, file-or-escalate), which adapter.score reads. An item no row of the sources labels has no text:
it is not scored. Run from the project (harness/); it refuses to overwrite a reference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "harness"))
from evaluation_harness._common import REFERENCES, die, load_dataset, now  # noqa: E402
from evaluation_harness._references import write_manifest  # noqa: E402

CAVEATS = {
    "fixture": "FIXTURE: the triage fleet's own earlier hand labels (2026-07), carried to these decisions by "
    "fingerprint; not the owner's verdicts. Shown beside gold, never deciding.",
}


def main() -> int:
    """Write the reference."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--verdicts", type=Path, required=True, help="verdicts.jsonl (Hugging Face, fetched)")
    ap.add_argument("--source", choices=("owner", "fixture"), default="owner")
    ap.add_argument("--name", help="the reference id (default gold/<dataset> for owner)")
    args = ap.parse_args()
    ds = load_dataset(args.dataset_id)
    name = args.name or (f"gold/{args.dataset_id}" if args.source == "owner" else None)
    if not name or name.split("/")[0] not in ("gold", "silver"):
        die("--name gold/<x> or silver/<x>")
    tier = name.split("/")[0]
    if args.source == "owner" and tier != "gold":
        die("the owner's labels are the gold reference")
    ref_dir = REFERENCES / name
    if ref_dir.exists():
        die(f"{ref_dir} exists: a reference is never overwritten")
    rows = [json.loads(x) for x in args.verdicts.read_text(encoding="utf-8").splitlines() if x.strip()]
    want = ("owner-issue-verdict", "owner-item-label") if args.source == "owner" else ("fixture",)
    label: dict[str, str] = {}
    for r in rows:
        if r["source"] in want:
            if r["id"] in label and label[r["id"]] != r["label"]:
                die(f"{r['id']}: two labels from {args.source} ({label[r['id']]}, {r['label']})")
            label[r["id"]] = r["label"]
    items = [it["item_id"] for it in ds["items"]]
    hit = [i for i in items if i in label]
    if not hit:
        die(f"no item of {args.dataset_id} has a {args.source} label")
    ref_dir.mkdir(parents=True)
    for i in hit:
        (ref_dir / f"{i}.txt").write_text(label[i] + "\n", encoding="utf-8")
    write_manifest(
        ref_dir,
        tier,
        args.dataset_id,
        caveat=CAVEATS.get(args.source) if tier == "silver" else None,
        source=(
            f"examples/triage-fleet/write_gold.py --source {args.source}: the rows of source "
            f"{', '.join(want)} in chipi-nbgd/orrery-triage@v1 data/verdicts.jsonl "
            f"(sha256 {hashlib.sha256(args.verdicts.read_bytes()).hexdigest()})"
        ),
        created_at=now(),
    )
    counts: dict[str, int] = {}
    for i in hit:
        counts[label[i]] = counts.get(label[i], 0) + 1
    print(f"{ref_dir}: {len(hit)} of {len(items)} item(s) labelled {json.dumps(counts, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
