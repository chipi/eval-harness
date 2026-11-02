#!/usr/bin/env python3
"""evh labels: every label set, or a dataset's (RFC-023): its source, coverage, guideline, and how two sets agree.

    evh labels
    evh labels --dataset-id tickets_v1
    evh labels --dataset-id tickets_v1 --confusion
    evh labels --json

With --dataset-id, the sets are every one that labels any of the dataset's items, matched by the item's sha256
(labels follow the item), with how many of its items each covers and, for each pair, on how many items both label,
on how many they accept the same answers and share one, and two chance-corrected coefficients (Cohen's kappa;
Krippendorff's alpha, with MASI distance when a label accepts several answers). Free-text labels are not compared as
text.
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


def pair_line(p: dict) -> str:
    """Two label sets compared, in words: both label, the same answers, sharing one, kappa and alpha."""
    if p.get("kind") != "categories":
        return f"both label {p['both']}; free text, not compared as text"

    def coef(k: str) -> str:
        return "undefined" if p.get(k) is None else f"{p[k]:.2f}"

    alpha = coef("alpha") + (" (MASI)" if p.get("alpha_distance") == "MASI" else "")
    return (
        f"both label {p['both']}, the same answers on {p['same']}, sharing one on {p['share']}; "
        f"Cohen's kappa {coef('kappa')}, Krippendorff's alpha {alpha}"
    )


def confusion_lines(p: dict) -> str:
    """A pair's confusion matrix: the first set's labels down, the second's across."""
    conf = p["confusion"]
    cols = sorted({c for row in conf.values() for c in row})
    corner = f"{p['a'].split('/')[-1]} ↓ · {p['b'].split('/')[-1]} →"
    first = max(len(x) for x in [*conf, corner]) + 2
    widths = [len(c) + 3 for c in cols]
    lines = ["    " + corner.ljust(first) + "".join(c.rjust(w) for c, w in zip(cols, widths))]
    for r in sorted(conf):
        lines.append(
            "    " + r.ljust(first) + "".join(str(conf[r].get(c, 0)).rjust(w) for c, w in zip(cols, widths))
        )
    return "\n".join(lines)


def main() -> int:
    """List label sets."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", help="the sets covering this dataset's items")
    ap.add_argument("--json", action="store_true", help="print JSON")
    ap.add_argument(
        "--confusion", action="store_true", help="with --dataset-id: each pair's confusion matrix too"
    )
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
            print(f"  {p['a']} and {p['b']}: {pair_line(p)}")
            if args.confusion and p.get("confusion"):
                print(confusion_lines(p))
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
