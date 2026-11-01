#!/usr/bin/env python3
"""A sheet of a dataset's items to label (RFC-023): what production or an arm decided, a proposal, an empty label.

    evh label-sheet --dataset-id tickets_v1 --out sheet.csv
    evh label-sheet --dataset-id prod_2026_11 --items disagree --runs production_2026_11,triage_lead_v1 \\
        --propose issue_verdicts --out sheet.csv
    evh label-sheet --dataset-id prod_2026_11 --item a1 --item a7 --out sheet.csv

One row per item: `item_id`, `item` (the start of the item itself, when it is materialized here), one column per
run in --runs (what it decided, its output), `proposal` (a label set's label, or a run's output) and the empty
columns `label` and `note`. Fill `label` (or write `yes` to take the proposal) in any spreadsheet, then
`evh label-import`. Which items: --items unlabelled (the default: no label in any set yet), all, or disagree (the
runs in --runs decided differently); or exactly those named with --item. A run is a run id or a config id (its
latest run on the dataset). Nothing is written but the sheet.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import csv
import json
from pathlib import Path

from evaluation_harness import _common
from evaluation_harness._common import die, item_path, load_dataset, read_json
from evaluation_harness._label_sets import labels_for, sets, text_of
from evaluation_harness._runs import runs_on

VIEW = 160


def run_dir(name: str, dataset_id: str) -> Path:
    """A run by its id, or a config's latest run on the dataset."""
    d = _common.RUNS / name
    if (d / "metrics.json").is_file():
        if read_json(d / "metrics.json").get("dataset_id") != dataset_id:
            die(f"--runs {name}: that run is not on {dataset_id}")
        return d
    found = runs_on(dataset_id, config_id=name)
    if not found:
        die(f"--runs {name}: no run with that id, and no run of that config on {dataset_id}")
    return found[-1][0]


def output(d: Path, item_id: str) -> str | None:
    f = d / "outputs" / f"{item_id}.txt"
    return f.read_text(encoding="utf-8").strip() if f.is_file() else None


def view(dataset_id: str, item_id: str) -> str:
    """The start of the item itself, on one line, or "" when it is not materialized here."""
    p = item_path(dataset_id, item_id)
    if p is None:
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix == ".json":
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False)
        except ValueError:
            pass
    one = " ".join(text.split())
    return one if len(one) <= VIEW else one[: VIEW - 1] + "…"


def main() -> int:
    """Write a sheet of items to label."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--out", required=True, type=Path, help="the sheet to write (.csv)")
    ap.add_argument("--items", choices=("unlabelled", "all", "disagree"), default="unlabelled")
    ap.add_argument("--item", action="append", default=[], help="exactly this item (repeatable)")
    ap.add_argument(
        "--runs", default="", help="runs (or configs) whose decisions the sheet shows, comma-separated"
    )
    ap.add_argument(
        "--propose", help="a label set (by name, on this dataset) or a run whose answers are proposed"
    )
    args = ap.parse_args()

    ds = load_dataset(args.dataset_id)
    ids = [it["item_id"] for it in ds.get("items") or []]
    names = [x.strip() for x in args.runs.split(",") if x.strip()]
    dirs = {n: run_dir(n, args.dataset_id) for n in names}
    if args.out.exists():
        die(f"{args.out} exists: a sheet is not overwritten (you may have filled it)")
    if args.items == "disagree" and len(dirs) < 2:
        die("--items disagree needs two runs or more in --runs")
    proposal: dict[str, str] = {}
    if args.propose:
        doc = next(
            (d for d in sets() if d["dataset_id"] == args.dataset_id and d["set"] == args.propose), None
        )
        if doc is not None:
            proposal = {i: t for i in ids if (t := text_of(doc, i)) is not None}
        else:
            pd = run_dir(args.propose, args.dataset_id)
            proposal = {i: t for i in ids if (t := output(pd, i)) is not None}
    if args.item:
        unknown = sorted(set(args.item) - set(ids))
        if unknown:
            die(f"--item: not in {args.dataset_id}: {', '.join(unknown[:8])}")
        chosen = [i for i in ids if i in set(args.item)]
    elif args.items == "unlabelled":
        have = labels_for(args.dataset_id)
        chosen = [i for i in ids if i not in have]
    elif args.items == "disagree":
        chosen = [i for i in ids if len({output(d, i) for d in dirs.values()}) > 1]
    else:
        chosen = ids
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "item", *[f"decided: {n}" for n in names], "proposal", "label", "note"])
        for i in chosen:
            w.writerow(
                [
                    i,
                    view(args.dataset_id, i),
                    *[output(d, i) or "" for d in dirs.values()],
                    proposal.get(i, ""),
                    "",
                    "",
                ]
            )
    print(f"{args.out}: {len(chosen)} item(s) of {len(ids)} to label")
    print(
        f"  fill `label` (or `yes` for the proposal), then: evh label-import {args.out} --dataset-id {args.dataset_id} --set <name> --by <you>"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
