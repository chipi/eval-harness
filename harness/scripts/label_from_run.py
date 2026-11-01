#!/usr/bin/env python3
"""A finished run's outputs as a model's label set (RFC-023): what that model said each item's answer is.

    evh label-from-run --run tickets_author_v1_20261101T101500 --set author_v1
    evh label-from-run --run … --set author_v1 --guideline prompts/author.txt

It calls nothing: the outputs are the run's, so the labels are exactly what you read. It refuses what
`run-promote` refuses (an unknown build, a dirty tree), an unfinished, derived or partial run, an empty output,
and outputs that stopped at max_tokens (`--allow-cut-off` for outputs that end at the cap by design). The set's
source is `model`: the run, its config, fingerprint and build. Labels are not a reference (RFC-023).
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
from pathlib import Path

from evaluation_harness._common import RUNS, die, load_dataset, read_json
from evaluation_harness._label_sets import write_set
from evaluation_harness.reference_create import _from_run


def main() -> int:
    """Take a finished run's outputs as a model's label set."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, help="the run whose outputs become the labels")
    ap.add_argument("--set", required=True, dest="name", help="the label set's name (lowercase, _ . -)")
    ap.add_argument("--guideline", type=Path, help="the prompt or instructions the model labelled by")
    ap.add_argument("--allow-cut-off", action="store_true", help="keep outputs that stopped at max_tokens")
    ap.add_argument("--allow-dirty", action="store_true", help="a run from a dirty tree")
    ap.add_argument("--allow-unknown-build", action="store_true", help="a run whose build is unknown")
    args = ap.parse_args()

    m = RUNS / args.run / "metrics.json"
    if not m.is_file():
        die(f"no finished run {args.run!r} under {RUNS}")
    dataset_id = read_json(m).get("dataset_id")
    if not dataset_id:
        die(f"run {args.run} names no dataset")
    rows, meta = _from_run(args.run, dataset_id, load_dataset(dataset_id)["items"], args)
    source = {"kind": "model", **meta["from_run"], "model": meta.get("model")}
    doc = write_set(dataset_id, args.name, {item: text for item, text, _ in rows}, source, args.guideline)
    print(f"data/labels/{dataset_id}/{args.name}: {doc['n_items']} label(s), source model · {args.run}")
    print(f"  every set on it: evh labels --dataset-id {dataset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
