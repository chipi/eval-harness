#!/usr/bin/env python3
"""How each arm fails: the failure modes tagged on its outputs (PLAN_0.8.0 D1).

    evh tags                         every tag set
    evh tags --dataset-id D          per arm on D: outputs read, outputs with a failure, each mode's count
    evh tags --dataset-id D --json

Tags come from a sheet: `evh inspect --sheet --dataset-id D --runs A,B --csv f.csv --fill tags --modes M`, then
`evh sheet-import f.csv --dataset-id D --by <who> --tags <name> --modes M`. The modes are the project's list,
`data/failure-modes/<M>.yaml`.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json

from evaluation_harness._common import evh_prog, load_dataset
from evaluation_harness._label_sets import source_line
from evaluation_harness._tags import counts, tag_sets


def main() -> int:
    """List tag sets, or count one dataset's failure modes per arm."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.split("\n\n")[0])
    ap.add_argument("--dataset-id", help="count this dataset's tags per arm")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args()
    if args.dataset_id:
        load_dataset(args.dataset_id)
        found = tag_sets(args.dataset_id)
        per_arm = counts(args.dataset_id)
        if args.json:
            print(
                json.dumps(
                    {
                        "dataset_id": args.dataset_id,
                        "sets": [
                            {
                                k: d.get(k)
                                for k in ("set", "failure_modes", "source", "created_at", "n_tagged")
                            }
                            for d in found
                        ],
                        "arms": per_arm,
                    },
                    indent=2,
                    default=str,
                )
            )
            return 0
        if not found:
            print(
                f"{args.dataset_id}: no tags yet (evh inspect --sheet … --fill tags --modes <id>, then evh sheet-import)"
            )
            return 0
        print(f"{args.dataset_id}: {len(found)} tag set(s)")
        for d in found:
            print(
                f"  {d['set']}: {source_line(d.get('source') or {})}, modes {d['failure_modes']}, {d['n_tagged']} output(s)"
            )
        for arm, c in per_arm.items():
            modes = ", ".join(f"{m} {n}" for m, n in c["modes"].items()) or "none"
            print(f"  {arm}: {c['tagged']} of {c['outputs']} output(s) read have a failure: {modes}")
        return 0
    found = tag_sets()
    if args.json:
        print(
            json.dumps(
                {"sets": [{k: v for k, v in d.items() if k != "runs"} for d in found]}, indent=2, default=str
            )
        )
        return 0
    if not found:
        print(
            "No tag sets yet (evh inspect --sheet … --fill tags --modes <id>, then evh sheet-import … --tags <name>)."
        )
        return 0
    for d in found:
        print(
            f"{d['dataset_id']}/{d['set']}: {source_line(d.get('source') or {})}, modes {d['failure_modes']}, "
            f"{d['n_tagged']} output(s), made {str(d.get('created_at'))[:10]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
