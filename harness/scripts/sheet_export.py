#!/usr/bin/env python3
"""A dataset's sheet written as a CSV to fill in (RFC-023): what each run wrote and scored beside every item, with the columns
to fill when --fill says so; read back by `evh sheet-import`.

    evh sheet-export --dataset-id D --runs A,B --csv sheet.csv [--fill label|pick|scores|tags]

The sheet's rows are what `evh sheet-show D --runs A,B` shows (the same selection: --wrong-against, --new-vs, --disagree,
--split, --unlabelled, --where, --scores-only). Never over a file that exists. A blind fill (pick, scores) writes the key beside
the sheet (sheet.key.json): keep it there, not with the sheet.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import re
from pathlib import Path

from evaluation_harness import _sheet, _store
from evaluation_harness import catalog_serve as cs
from evaluation_harness._common import die, evh_prog
from evaluation_harness.catalog_adapter import load_catalog_adapter


def _sheet_csv(args, model: dict, shown: list) -> int:
    """--csv FILE: the sheet written as CSV for a spreadsheet (UTF-8 with the mark Excel needs), with the columns to
    fill when --fill says so; for a blind fill the key beside it (sheet.key.json). Never over a file that exists."""

    from evaluation_harness._common import write_json  # noqa: PLC0415
    from evaluation_harness._sheets import write_csv  # noqa: PLC0415

    key_file = _sheet.key_path(args.csv)
    blind = args.fill in ("pick", "scores")
    for f in (args.csv, key_file if blind or args.fill == "tags" else None):
        if f is not None and _store.exists(f):
            die(f"{f} exists: a sheet is not overwritten (you may have filled it)", "would-overwrite")
    if args.fill == "tags":
        from evaluation_harness import _tags  # noqa: PLC0415

        modes = _tags.load_modes(args.modes)
        head, body, key = _tags.tag_sheet(model, shown, modes)
        write_csv(head, body, args.csv)
        write_json(key_file, key)
        print(
            f"{args.csv}: {len(body) - 1} row(s), a failure_modes column beside each of {len(model['arms'])} arm(s)' "
            f"outputs; the key is {key_file}"
        )
        print(
            f"  fill each failure_modes cell with modes of {args.modes} ({', '.join(_tags.mode_ids(modes))}; mode|mode "
            "for several), `ok` when the output is fine, blank when not read; then: "
            f"evh sheet-import --sheet {args.csv} --dataset-id {args.dataset_id} --by <who> --tags <name> --modes {args.modes}"
        )
        return 0
    if not blind:
        choices = [c.strip() for c in (args.choices or "").split(",") if c.strip()] or None
        head, body = _sheet.csv_sheet(
            model, shown, scores_only=args.scores_only, fill=args.fill, choices=choices
        )
        write_csv(head, body, args.csv)
        print(f"{args.csv}: {len(shown)} row(s), {len(head)} column(s)")
        if args.fill == "label":
            print(
                "  fill `label` (answers just as right in `also right`, separated by |), then: "
                f"evh sheet-import --sheet {args.csv} --dataset-id {args.dataset_id} --by <you> --set <name>"
            )
        return 0
    scale = (1, 5)
    if args.scale:
        m = re.fullmatch(r"(-?\d+)\.\.(-?\d+)", args.scale.strip())
        if not m or int(m.group(1)) >= int(m.group(2)):
            die(f"--scale {args.scale}: LO..HI, two whole numbers, LO below HI (e.g. 1..5)", "bad-argument")
        scale = (int(m.group(1)), int(m.group(2)))
    if args.rubric and not _store.is_file(args.rubric):
        die(f"--rubric: no file {args.rubric}", "not-found")
    rubric = _sheet.rubric_text(
        args.fill, scale, _store.read_text(args.rubric, encoding="utf-8") if args.rubric else None
    )
    head, body, key, left_out = _sheet.blind(
        model, shown, args.fill, seed=args.seed or 0, rubric=rubric, scale=scale
    )
    if len(body) < 2:
        die(
            f"--fill {args.fill}: no row has outputs to judge (a pick needs two outputs on a row)",
            "not-enough",
        )
    write_csv(head, body, args.csv)
    write_json(key_file, key)
    print(
        f"{args.csv}: {len(body) - 1} row(s) to judge, {len(model['arms'])} blind column(s)"
        + (f" ({left_out} row(s) left out: too few outputs)" if left_out else "")
        + f"\n  the key (which letter was which run on each row) is {key_file}: keep it here, not with the sheet"
    )
    what = "`pick` (the best letter, `A|B` for a tie)" if args.fill == "pick" else "`score: A`, `score: B`…"
    print(
        f"  fill {what}, then: evh sheet-import --sheet {args.csv} --dataset-id {args.dataset_id} --by <who> --scorer <name>"
    )
    return 0


def main() -> int:
    """Write the sheet as a CSV."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.split("\n\n")[0])
    ap.add_argument("--dataset-id", required=True, help="the dataset whose items are the rows")
    ap.add_argument(
        "--runs",
        required=True,
        help="runs: run ids or system ids (their latest run on the dataset), comma-separated; the first is production's",
    )
    ap.add_argument(
        "--csv",
        type=Path,
        required=True,
        metavar="FILE",
        help="the CSV to write (UTF-8 with the mark Excel needs)",
    )
    ap.add_argument("--metric", help="default: the arms' primary metric")
    ap.add_argument(
        "--label", default="", help="the label system ids are looked up under (default: the plain arm)"
    )
    ap.add_argument(
        "--where",
        action="append",
        default=[],
        help="FIELD:VALUE or FIELD:LO..HI, keep only matching items (repeatable)",
    )
    ap.add_argument(
        "--disagree",
        action="store_true",
        help="only the items where a run decided differently from the first",
    )
    ap.add_argument(
        "--split",
        action="store_true",
        help="only the items the candidates (the runs after the first) decided differently among themselves",
    )
    ap.add_argument(
        "--wrong-against",
        metavar="SET",
        help="only the items where the first run's decision is not this label set's (SET or DATASET/SET)",
    )
    ap.add_argument(
        "--new-vs", metavar="DATASET", help="only the items with a field value this dataset has never had"
    )
    ap.add_argument("--unlabelled", action="store_true", help="only the items no label set labels yet")
    ap.add_argument(
        "--scores-only", action="store_true", help="leave the runs' outputs out, keep their scores"
    )
    ap.add_argument(
        "--fill",
        choices=_sheet.FILLS,
        help="add the columns to fill. label: label, also right, note. pick, scores: the outputs as blind columns A, B, C... shuffled per row, a key beside the sheet (sheet.key.json), the rubric as its first row; tags: a failure_modes column beside each arm's output (with --modes), a key beside the sheet; evh sheet-import --sheet reads it back",
    )
    ap.add_argument(
        "--modes", help="with --fill tags: the failure-mode list the tags name (data/failure-modes/<id>.yaml)"
    )
    ap.add_argument(
        "--choices",
        help="with --fill label: the allowed answers, comma-separated (e.g. file,dismiss,escalate), written into the label column's header",
    )
    ap.add_argument(
        "--seed", type=int, default=None, help="with --fill pick or scores: the shuffle's seed (default 0)"
    )
    ap.add_argument(
        "--rubric",
        type=Path,
        help="with --fill pick or scores: a file saying what to judge (default: a plain one)",
    )
    ap.add_argument("--scale", help="with --fill scores: the scores' range, LO..HI (default 1..5)")
    args = ap.parse_args()
    A = load_catalog_adapter(None)
    cs.set_adapter(A)
    runs = [t.strip() for t in args.runs.split(",") if t.strip()]
    for flag, n, on in (
        ("--disagree", 2, args.disagree),
        ("--split", 3, args.split),
        ("--wrong-against", 1, args.wrong_against),
    ):
        if on and len(runs) < n:
            die(f"{flag} needs {n} run(s) or more in --runs (the first is production's)", "bad-argument")
    if args.choices and args.fill != "label":
        die("--choices: with --fill label", "bad-argument")
    if (args.fill == "tags") != bool(args.modes):
        die("--fill tags and --modes go together: name the failure-mode list the tags use", "bad-argument")
    if args.fill not in ("pick", "scores") and (args.seed is not None or args.rubric or args.scale):
        die("--seed, --rubric and --scale: with --fill pick or scores", "bad-argument")
    if args.scale and args.fill != "scores":
        die("--scale: with --fill scores", "bad-argument")
    model = _sheet.build(
        args.dataset_id,
        runs,
        cs._fields_of,
        metric=args.metric,
        label=args.label,
        wrong_against=args.wrong_against,
        new_vs=args.new_vs,
    )
    found = _sheet.by_where(model, args.where)
    wanted = [
        s
        for s, on in (
            ("wrong", args.wrong_against),
            ("disagree", args.disagree),
            ("split", args.split),
            ("new", args.new_vs),
            ("unlabelled", args.unlabelled),
        )
        if on
    ]
    shown = _sheet.by_signals(found, wanted)
    from evaluation_harness import _exposure  # noqa: PLC0415

    _exposure.read_by_harness(args.dataset_id, [r["item"] for r in shown], "sheet-export")
    return _sheet_csv(args, model, shown)


if __name__ == "__main__":
    raise SystemExit(main())
