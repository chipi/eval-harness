#!/usr/bin/env python3
"""Rules over a capture's recorded outcomes as a rule label set (RFC-023): what production recorded afterwards.

    evh label-from-capture --dataset-id triage_v1 --capture fleet_2026_10 --map outcomes.yaml --set issue_verdicts

For each item of the dataset, the capture's record of the same id is read, and the mapping's rules are tried in
order against its outcome's fields; the first that matches gives the item's label, or skips it; an item no rule
matches has no label. The rules are the outcome rule language (`_outcome_rules`: when, unless, exists, absent, range,
min_age_days; label or skip). The set's source is `rule`, whoever wrote the outcome: the capture, its sha256, the
mapping and its hash, and the counts. Newer outcomes are a fresh capture of the same query and a new set.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
from collections import Counter
from pathlib import Path

from evaluation_harness._common import CAPTURES, die, load_dataset
from evaluation_harness._importers import parse_time
from evaluation_harness._label_sets import label_text, write_set
from evaluation_harness._outcome_rules import load_rules, matches
from evaluation_harness.dataset_from_capture import load_capture


def main() -> int:
    """Label a dataset's items from a capture's outcomes, by rules."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--capture", required=True, help="the capture whose records hold the outcomes")
    ap.add_argument("--map", required=True, type=Path, help="the mapping: YAML rules")
    ap.add_argument("--set", required=True, dest="name", help="the label set's name (lowercase, _ . -)")
    args = ap.parse_args()

    rules = load_rules(args.map)
    ds = load_dataset(args.dataset_id)
    doc, recs = load_capture(args.capture)
    by_id = {r["id"]: r for r in recs}
    captured = parse_time(doc.get("captured_at"))
    labels: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for it in ds["items"]:
        rec = by_id.get(it["item_id"])
        if rec is None:
            counts["no_record"] += 1
            continue
        out = rec.get("outcome") if isinstance(rec.get("outcome"), dict) else {}
        t = parse_time(rec.get("created_at"))
        age = (captured - t).total_seconds() / 86400 if captured and t else None
        rule = next((r for r in rules if matches(r, out, age)), None)
        if rule is None:
            counts["unmatched"] += 1
        elif rule.get("skip"):
            counts["skipped"] += 1
        else:
            counts["matched"] += 1
            labels[it["item_id"]] = (
                label_text([str(a) for a in rule["label"]])
                if isinstance(rule["label"], list)
                else str(rule["label"])
            )
    if not labels:
        die(f"no item got a label ({dict(counts)}): nothing written")
    source = {
        "kind": "rule",
        "capture": args.capture,
        "capture_sha256": hashlib.sha256((CAPTURES / args.capture / "capture.json").read_bytes()).hexdigest(),
        "captured_at": doc.get("captured_at"),
        "mapping": args.map.as_posix(),
        "mapping_sha256": hashlib.sha256(args.map.read_bytes()).hexdigest(),
        **{k: counts[k] for k in ("matched", "skipped", "unmatched", "no_record")},
    }
    out = write_set(args.dataset_id, args.name, labels, source, args.map)
    print(
        f"data/labels/{args.dataset_id}/{args.name}: {out['n_items']} of {len(ds['items'])} item(s) labelled "
        f"({counts['skipped']} skipped, {counts['unmatched']} matched no rule, {counts['no_record']} not in the capture)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
