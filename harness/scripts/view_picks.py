#!/usr/bin/env python3
"""evh picks: the picks waiting for the next version of governed datasets (RFC-023, ADR-0023).

    evh picks
    evh picks --for orrery_triage_v1_labelled
    evh picks --tag case=missed-regression --json

Per target dataset (and those with none yet): each pick's item, the dataset and capture it came from, its labels by
source ("none yet": label it before the next version), its tags and note, who picked it and when.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json

from evaluation_harness._common import die
from evaluation_harness._label_sets import labels_for, source_line
from evaluation_harness._picks import waiting


def main() -> int:
    """List the picks waiting."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--for", dest="target", help="only the picks for this dataset")
    ap.add_argument(
        "--tag", action="append", default=[], help="KEY=VALUE: only picks with this tag (repeatable)"
    )
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args()

    tags = {}
    for t in args.tag:
        k, sep, v = t.partition("=")
        if not sep:
            die(f"--tag {t!r}: KEY=VALUE")
        tags[k] = v
    rows = waiting(args.target, tags or None)
    labels_by_ds: dict = {}
    for r in rows:
        ds = r["from"]
        if ds not in labels_by_ds:
            labels_by_ds[ds] = labels_for(ds)
        r["labels"] = [
            {"set": f"{x['dataset_id']}/{x['set']}", "source": source_line(x["source"]), "label": x["text"]}
            for x in labels_by_ds[ds].get(r["item"], [])
        ]
    if args.json:
        print(json.dumps({"picks": rows}, indent=2, default=str))
        return 0
    if not rows:
        print("No picks waiting (evh pick --dataset-id D --item X --for V).")
        return 0
    groups: dict[str, list] = {}
    for r in rows:
        for t in r.get("for") or [""]:
            if not args.target or t == args.target:
                groups.setdefault(t, []).append(r)
    for t in sorted(groups, key=lambda x: (x == "", x)):
        print(f"{t or 'no target yet'}: {len(groups[t])} pick(s) waiting")
        for r in groups[t]:
            labels = "; ".join(f"{x['source']}: {x['label']}" for x in r["labels"]) or "none yet"
            tag = " ".join(f"{k}={v}" for k, v in sorted((r.get("tags") or {}).items()))
            print(
                f"  {r['item']}  from {r['from']}"
                + (f" (capture {r['capture']})" if r.get("capture") else "")
                + f"  labels: {labels}"
                + (f"  [{tag}]" if tag else "")
                + (f'  "{r["note"]}"' if r.get("note") else "")
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
