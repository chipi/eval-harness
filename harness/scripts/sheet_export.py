"""A dataset's sheet written as a CSV to fill in (RFC-023): what each run wrote and scored beside every item, with the columns
to fill when --fill says so; read back by `evh sheet-import`. An operation (`POST /datasets/{dataset}/sheets`): as a job,
the sheet and its key are written in the job's folder; the sheet is served as the job's file, the key never is, and
`sheet-import --export-job` reads it there (owner, 2026-11-17: the Workbench submits a filled sheet).

    evh sheet-export --dataset-id D --runs A,B --csv sheet.csv [--fill label|pick|scores|tags]

The sheet's rows are what `evh sheet-show D --runs A,B` shows (the same selection: --wrong-against, --new-vs, --disagree,
--split, --unlabelled, --where, --scores-only). Never over a file that exists. A blind fill (pick, scores) writes the key beside
the sheet (sheet.key.json): keep it there, not with the sheet.
"""

from __future__ import annotations

import re
from typing import Any

from evaluation_harness import _sheet, _store
from evaluation_harness import catalog_serve as cs
from evaluation_harness._common import die
from evaluation_harness.catalog_adapter import load_catalog_adapter
from evaluation_harness.ops import legacy


def _sheet_csv(args: Any, model: dict, shown: list) -> int:
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


def body(**inputs: Any) -> int:
    """Write the sheet as a CSV (and a blind fill's key beside it)."""
    args = legacy.namespace(inputs, "sheet-export")
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
