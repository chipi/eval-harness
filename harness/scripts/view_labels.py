#!/usr/bin/env python3
"""evh labels: every label set, or a dataset's (RFC-023): its source, coverage, guideline, and how often two agree.

    evh labels
    evh labels --dataset-id tickets_v1
    evh labels --json

With --dataset-id, the sets are every one that labels any of the dataset's items, matched by the item's sha256
(labels follow the item), with how many of its items each covers and, for each pair, on how many items both label
and how many they agree.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json

from evaluation_harness._common import load_dataset
from evaluation_harness._label_sets import agreement, coverage, sets, source_line


def main() -> int:
    """List label sets."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", help="the sets covering this dataset's items")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args()

    if args.dataset_id:
        n = len(load_dataset(args.dataset_id).get("items") or [])
        cov = coverage(args.dataset_id)
        pairs = agreement(args.dataset_id)
        if args.json:
            print(
                json.dumps(
                    {"dataset_id": args.dataset_id, "items": n, "sets": cov, "agreement": pairs},
                    indent=2,
                    default=str,
                )
            )
            return 0
        if not cov:
            print(f"{args.dataset_id}: no labels yet (evh label-sheet, evh label-import, evh label-from-run)")
            return 0
        print(f"{args.dataset_id}: {n} item(s), {len(cov)} label set(s)")
        for c in cov:
            g = (c.get("guideline") or {}).get("path") or "no guideline"
            print(
                f"  {c['dataset_id']}/{c['set']}: {source_line(c['source'])}, {len(c['items'])} of {n} item(s), {g}"
            )
        for p in pairs:
            print(f"  {p['a']} and {p['b']}: both label {p['both']}, agree on {p['agree']}")
        return 0
    found = sets()
    if args.json:
        print(
            json.dumps(
                {"sets": [{k: v for k, v in d.items() if k != "_dir"} for d in found]}, indent=2, default=str
            )
        )
        return 0
    if not found:
        print(
            "No label sets yet (evh label-sheet, evh label-import, evh label-from-run, evh label-from-capture)."
        )
        return 0
    for d in found:
        g = (d.get("guideline") or {}).get("path") or "no guideline"
        print(
            f"{d['dataset_id']}/{d['set']}: {source_line(d.get('source') or {})}, {d.get('n_items')} label(s), {g}, made {str(d.get('created_at'))[:10]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
