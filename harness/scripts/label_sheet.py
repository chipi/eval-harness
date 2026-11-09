#!/usr/bin/env python3
"""A sheet of a dataset's items to label (RFC-023): what production or an arm decided, a proposal, an empty label.

    evh label-sheet --dataset-id tickets_v1 --out sheet.csv
    evh label-sheet --dataset-id prod_2026_11 --items disagree --runs production_2026_11,triage_lead_v1 \\
        --propose issue_verdicts --choices file,dismiss,escalate,cleanup --out sheet.csv
    evh label-sheet --dataset-id prod_2026_11 --item a1 --item a7 --out sheet.csv

One row per item: `item_id`, `item` (the start of the item itself, when it is materialized here), one column per
run in --runs (what it decided, its output), `proposal` (a label set's label, or a run's output) and the empty
columns `label`, `also right` and `note`. Open it in Excel or any spreadsheet (it is UTF-8 CSV with the mark Excel
needs), fill `label` (or write `yes` to take the proposal) and, where more than one answer is fully right (each as
right as the label, not "unsure which"), the others in `also right` (separated by `|`); save it as CSV and run `evh
label-import`. --choices writes the allowed answers into the label column's header (`label [file|dismiss|…]`), and
label-import refuses any other. Which items: --items unlabelled (the default: no label in any set yet), all, or
disagree (the runs in --runs decided differently); or exactly those named with --item. A run is a run id or a config
id (its latest run on the dataset). Nothing is written but the sheet.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json
import sys
from pathlib import Path

from evaluation_harness import _common, _jsonout, _outputs, _store
from evaluation_harness._common import die, evh_prog, item_path, load_dataset, read_json
from evaluation_harness._label_sets import labels_for, sets, text_of
from evaluation_harness._runs import runs_on
from evaluation_harness._sheets import ALSO, NOTE, label_header, write_csv

VIEW = 160


def run_dir(name: str, dataset_id: str) -> Path:
    """A run by its id, or a config's latest run on the dataset: in data/runs, else in a label set's runs
    (data/runs-labels-<dataset>-<set>/, where a run scored against labels lands)."""
    bases = [_common.RUNS, *sorted(_store.glob(_common.DATA, f"runs-labels-{dataset_id}-*"))]
    # An arm id, as the catalog names it (catalog_adapter._index): <runs dir>/<dataset>/<config_id>, the runs dir
    # nested for a judging or a re-scoring pass (runs-judged/<scorer>, runs-rescored/<scoring>/runs).
    if name.count("/") >= 2:
        where, ds, config_id = name.rsplit("/", 2)
        base = _common.RUNS if where == "runs" else _common.DATA / where
        if (
            ds != dataset_id
            or not where.startswith("runs")
            or ".." in where.split("/")
            or not _store.is_dir(base)
        ):
            die(f"--runs {name}: not an arm on {dataset_id}", "not-found")
        found = runs_on(dataset_id, runs_dir=base, config_id=config_id)
        if not found:
            die(f"--runs {name}: no run of that arm", "not-found")
        return found[-1][0]
    for base in bases:
        d = base / name
        if _store.is_file(d / "metrics.json"):
            if read_json(d / "metrics.json").get("dataset_id") != dataset_id:
                die(f"--runs {name}: that run is not on {dataset_id}", "mismatch")
            return d
    for base in bases:
        found = runs_on(dataset_id, runs_dir=base, config_id=name)
        if found:
            return found[-1][0]
    die(f"--runs {name}: no run with that id, and no run of that config on {dataset_id}", "not-found")


def output(d: Path, item_id: str) -> str | None:
    """A run's output for one item (what it decided), or None when it has none."""
    text = _outputs.output(d, item_id)
    return text.strip() if text is not None else None


def view(dataset_id: str, item_id: str, limit: int | None = VIEW) -> str:
    """The start of the item itself (`limit` characters; all of it for None), on one line, or "" when it is not
    materialized here."""
    p = item_path(dataset_id, item_id)
    if p is None:
        return ""
    text = _store.read_text(p, encoding="utf-8", errors="replace")
    if p.suffix == ".json":
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False)
        except ValueError:
            pass
    one = " ".join(text.split())
    return one if limit is None or len(one) <= limit else one[: limit - 1] + "…"


def main() -> int:
    """Write a sheet of items to label."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
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
    ap.add_argument(
        "--choices",
        help="the allowed answers, comma-separated (e.g. file,dismiss,escalate): written into the label column's "
        "header; label-import refuses any other",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("label-sheet", args.json, live=sys.stderr):
        if _store.exists(args.out):
            die(f"{args.out} exists: a sheet is not overwritten (you may have filled it)", "would-overwrite")
        choices = [c.strip() for c in (args.choices or "").split(",") if c.strip()] or None
        from evaluation_harness import _seal  # noqa: PLC0415

        _seal.refuse_if_sealed(args.dataset_id, "a label sheet")
        header, rows, n = build(args.dataset_id, args.items, args.item, args.runs, args.propose, choices)
        write_csv(header, rows, args.out)
        print(f"{args.out}: {len(rows)} item(s) of {n} to label")
        print(
            "  fill `label` (or `yes` for the proposal; answers just as right in `also right`, separated by |), "
            f"then: evh label-import {args.out} --dataset-id {args.dataset_id} --set <name> --by <you>"
        )
        return 0


def build(
    dataset_id: str,
    items: str = "unlabelled",
    item: list[str] | None = None,
    runs: str = "",
    propose: str | None = None,
    choices: list[str] | None = None,
) -> tuple[list[str], list[list[str]], int]:
    """The sheet's header and rows, and how many items the dataset has: `label-sheet` writes them to a file, the
    inspector serves them as a download."""
    ds = load_dataset(dataset_id)
    ids = [it["item_id"] for it in ds.get("items") or []]
    names = [x.strip() for x in runs.split(",") if x.strip()]
    dirs = {n: run_dir(n, dataset_id) for n in names}
    if items == "disagree" and len(dirs) < 2:
        die("--items disagree needs two runs or more in --runs", "bad-argument")
    proposal: dict[str, str] = {}
    if propose:
        doc = next((d for d in sets() if d["dataset_id"] == dataset_id and d["set"] == propose), None)
        if doc is not None:
            proposal = {i: t for i in ids if (t := text_of(doc, i)) is not None}
        else:
            pd = run_dir(propose, dataset_id)
            proposal = {i: t for i in ids if (t := output(pd, i)) is not None}
    if item:
        unknown = sorted(set(item) - set(ids))
        if unknown:
            die(f"--item: not in {dataset_id}: {', '.join(unknown[:8])}", "not-found")
        chosen = [i for i in ids if i in set(item)]
    elif items == "unlabelled":
        have = labels_for(dataset_id)
        chosen = [i for i in ids if i not in have]
    elif items == "disagree":
        from evaluation_harness._adapter import same_of  # noqa: PLC0415

        first = next(iter(dirs.values()))
        same = same_of(read_json(first / "metrics.json").get("adapter"))
        chosen = []
        for i in ids:
            outs = [o for d in dirs.values() if (o := output(d, i)) is not None]
            if len(outs) > 1 and any(not same(outs[0], o) for o in outs[1:]):
                chosen.append(i)
    else:
        chosen = ids
    header = [
        "item_id",
        "item",
        *[f"decided: {n}" for n in names],
        "proposal",
        label_header(choices),
        ALSO,
        NOTE,
    ]
    rows = [
        [
            i,
            view(dataset_id, i),
            *[output(d, i) or "" for d in dirs.values()],
            proposal.get(i, ""),
            "",
            "",
            "",
        ]
        for i in chosen
    ]
    return header, rows, len(ids)


if __name__ == "__main__":
    raise SystemExit(main())
