#!/usr/bin/env python3
"""A sheet filled elsewhere, read back: labels or judgements (RFC-023).

    evh sheet-import sheet.csv --dataset-id tickets_v1 --by owner --set owner_2026_11
    evh sheet-import sheet.csv --dataset-id tickets_v1 --by claude --kind model --set claude_labels
    evh sheet-import sheet.csv --dataset-id tickets_v1 --by owner --scorer owner_picks
    evh sheet-import sheet.csv --dataset-id tickets_v1 --by owner --tags first --modes summaries

A person, or any AI tool, fills the empty columns of a sheet `evh inspect --sheet … --csv sheet.csv --fill …` wrote,
and one command reads back whatever was filled. The records stay two kinds, because they mean different things: a
label says what is right for the item and scores any arm, a later one too; a judgement says which of these arms did
best and cannot score an arm added next week.

- a filled `label` column (with `also right` and `note`, as label-import reads them) becomes a label set, `--set`; its
  source is `person`, or `model` with `--kind model` (`--by` then names the tool);
- a filled `pick` column (the letter of the best output; `A|B` for a tie, each then taking half) or `score: X` columns
  (a number on the rubric's scale) become judged runs under data/runs-judged/<scorer>/, `--scorer`: one run per arm,
  `judge_won_unvalidated` (1 for the pick, 0 for the others, split on a tie) or `judge_score_unvalidated` per item,
  mapped back through the key (`sheet.key.json`, beside the sheet; `--key` names another). Such runs are
  unvalidated, labelled so as judge-score's `--unvalidated` runs are, until the same judge is validated as any is;
- filled `failure_modes: X` columns (modes of a failure-mode list, `mode|mode` for several, `ok` for an output read
  and found fine; a blank cell was not read) become a tag set under data/tags/<dataset>/<name>/, `--tags`, checked
  against its key and the list `--modes` names. A tag says what went wrong in that arm's output; it scores nothing.

The sheet's blind columns are checked against the key first: a row the key does not have, a column whose text is not
the one the key recorded (another sheet, or an edited output), a pick naming a letter that is not on its row, a score
off the rubric's scale, and a name already used are refused, naming the rows, and nothing is written. The rows
whose `item_id` starts `#` (the rubric, a footer) are not items and are left out.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _outputs, _tags
from evaluation_harness._codeid import file_sha256
from evaluation_harness._common import (
    BOOKKEEPING_PREFIXES,
    classify_metrics,
    die,
    evh_prog,
    load_dataset,
    read_json,
    write_json,
)
from evaluation_harness._fingerprint import seal
from evaluation_harness._label_sets import set_dir, write_set
from evaluation_harness._record import aggregate_scores, derived_record
from evaluation_harness._runs import item_rows
from evaluation_harness._sheet import NOT_AN_ITEM, key_path, read_key, text_sha256
from evaluation_harness._sheets import read_csv
from evaluation_harness.label_import import labels_from_rows
from evaluation_harness.label_sheet import run_dir

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
#: What describes the call that made an arm's output, not how it was judged: carried across, as judge-score carries
#: them, so the judged runs have their cost and speed.
CARRY = ("latency_ms", "tokens_in", "tokens_out", "cost_usd")
SUFFIX = "_unvalidated"


def main() -> int:
    """Read a filled sheet back as a label set, or as judged runs."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("sheet", type=Path, help="the filled sheet (.csv)")
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--by", required=True, help="who filled it: a person, or the tool")
    ap.add_argument(
        "--kind", choices=("person", "model"), default="person", help="who filled it (default: person)"
    )
    ap.add_argument("--set", dest="name", help="the label set's name, for a filled `label` column")
    ap.add_argument(
        "--scorer", help="the name of the judged runs (data/runs-judged/<scorer>/), for `pick`/`score:`"
    )
    ap.add_argument(
        "--tags", help="the tag set's name, for filled `failure_modes:` columns (data/tags/<dataset>/<name>/)"
    )
    ap.add_argument(
        "--modes", help="with --tags: the failure-mode list the tags name (data/failure-modes/<id>.yaml)"
    )
    ap.add_argument("--key", type=Path, help="the sheet's key (default: sheet.key.json beside it)")
    ap.add_argument(
        "--guideline",
        type=Path,
        help="with --set, a file: the instructions the labeller followed (its path and sha256 are recorded)",
    )
    args = ap.parse_args()

    if not args.sheet.is_file():
        die(f"no sheet {args.sheet}", "not-found")
    load_dataset(args.dataset_id)
    rows, choices = read_csv(args.sheet)
    if not rows or "item_id" not in rows[0]:
        die(
            f"{args.sheet}: a sheet has the column item_id (evh inspect --sheet … --csv writes one)",
            "invalid-file",
        )
    head = list(rows[0])
    rows = [r for r in rows if not r["item_id"].startswith(NOT_AN_ITEM)]
    sha = hashlib.sha256(args.sheet.read_bytes()).hexdigest()

    def filled(col: str) -> bool:
        return any((r.get(col) or "").strip() for r in rows)

    score_cols = [h for h in head if h.startswith("score: ")]
    has_label = "label" in head and filled("label")
    has_pick = "pick" in head and filled("pick")
    has_scores = any(filled(h) for h in score_cols)
    if any(h.startswith(_tags.COLUMN) for h in head):
        return _import_tags(args, rows, sha, any(filled(h) for h in head if h.startswith(_tags.COLUMN)))
    if args.tags or args.modes:
        die(
            f"{args.sheet}: --tags and --modes read `failure_modes:` columns, and the sheet has none",
            "bad-argument",
        )
    if not (has_label or has_pick or has_scores):
        die(f"{args.sheet}: nothing filled: no `label`, `pick` or `score:` cell has an answer", "not-enough")
    if has_pick and has_scores:
        die(f"{args.sheet}: both `pick` and `score:` are filled: a sheet is judged one way", "invalid-file")
    if has_label and not args.name:
        die("the sheet has labels: name the label set with --set", "bad-argument")
    if (has_pick or has_scores) and not args.scorer:
        die(
            "the sheet has judgements: name the judged runs with --scorer (data/runs-judged/<scorer>/)",
            "bad-argument",
        )

    labels: dict[str, str] = {}
    notes: dict[str, str] = {}
    if has_label:
        labels, notes = labels_from_rows(rows, choices)
        out = set_dir(args.dataset_id, args.name)
        if out.exists() and any(out.iterdir()):
            die(
                f"{out} exists: a label set is never edited. A correction is a new set: name another.",
                "would-overwrite",
            )
    judged: dict[str, Any] | None = None
    if has_pick or has_scores:
        if not NAME.match(args.scorer):
            die(
                f"--scorer {args.scorer!r}: letters, digits, _ . - (at most 100), starting with a letter or digit",
                "bad-argument",
            )
        target = _common.DATA / "runs-judged" / args.scorer
        if target.exists() and any(target.iterdir()):
            die(
                f"{target} exists: judged runs are never overwritten. Name another --scorer.",
                "would-overwrite",
            )
        judged = _judgements(args, rows, has_pick)

    if has_label:
        source = {"kind": args.kind, "by": args.by, "sheet": args.sheet.name, "sheet_sha256": sha}
        doc = write_set(args.dataset_id, args.name, labels, source, args.guideline, notes)
        print(
            f"data/labels/{args.dataset_id}/{args.name}: {doc['n_items']} label(s) of {len(rows)} row(s), "
            f"source {args.kind} · {args.by}"
        )
    if judged is not None:
        _write(args, judged, sha)
    return 0


def _import_tags(
    args: argparse.Namespace, rows: list[dict[str, str]], sheet_sha: str, any_filled: bool
) -> int:
    """A filled tag sheet read back as a tag set, after its key and the failure-mode list are checked."""
    if not (args.tags and args.modes):
        die(
            "the sheet has `failure_modes:` columns: name the tag set with --tags and its list with --modes",
            "bad-argument",
        )
    if not any_filled:
        die(f"{args.sheet}: nothing filled: no `failure_modes:` cell has an answer", "not-enough")
    key = read_key(args.key or key_path(args.sheet))
    if key["dataset_id"] != args.dataset_id:
        die(f"the key is for {key['dataset_id']}, not {args.dataset_id}", "mismatch")
    if key["fill"] != "tags":
        die(f"the key is for a sheet made with --fill {key['fill']}, not --fill tags", "mismatch")
    if key.get("failure_modes") != args.modes:
        die(
            f"the sheet was written for the modes of {key.get('failure_modes')}, not {args.modes}", "mismatch"
        )
    tags = _tags.tags_from_sheet(rows, key)
    if not tags:
        die("nothing filled in the failure_modes columns", "not-enough")
    source = {"kind": args.kind, "by": args.by, "sheet": args.sheet.name, "sheet_sha256": sheet_sha}
    doc = _tags.write_tags(args.dataset_id, args.tags, args.modes, tags, source)
    print(
        f"data/tags/{args.dataset_id}/{args.tags}: {doc['n_tagged']} output(s) read in {len(tags)} run(s), "
        f"modes of {args.modes} · {args.kind} {args.by}"
    )
    print(f"  the counts: evh tags --dataset-id {args.dataset_id}")
    return 0


def _judgements(args: argparse.Namespace, rows: list[dict[str, str]], pick: bool) -> dict[str, Any]:
    """The key checked against the sheet, and what was judged: {key, metric, values {arm index: {item: value}}}."""
    key = read_key(args.key or key_path(args.sheet))
    if key["dataset_id"] != args.dataset_id:
        die(f"the key is for {key['dataset_id']}, not {args.dataset_id}", "mismatch")
    if key["fill"] != ("pick" if pick else "scores"):
        die(
            f"the key is for a sheet made with --fill {key['fill']}, but the sheet has {'picks' if pick else 'scores'}",
            "mismatch",
        )
    letters: list[str] = key["letters"]
    unknown = [r["item_id"] for r in rows if r["item_id"] not in key["rows"]]
    if unknown:
        die(f"{len(unknown)} row(s) not in the key (another sheet's): {', '.join(unknown[:8])}", "mismatch")
    changed = [
        r["item_id"]
        for r in rows
        if any(
            text_sha256(r.get(letter) or "") != info["text_sha256"]
            for letter, info in key["rows"][r["item_id"]].items()
        )
    ]
    if changed:
        die(
            f"{len(changed)} row(s) whose outputs are not the key's (an edited sheet, or another key): "
            f"{', '.join(changed[:8])}",
            "mismatch",
        )
    values: dict[int, dict[str, float]] = {}
    bad: list[str] = []
    lo, hi = key["scale"] or (None, None)
    for r in rows:
        item, on_row = r["item_id"], key["rows"][r["item_id"]]
        if pick:
            cell = (r.get("pick") or "").strip()
            if not cell:
                continue
            named = [x.strip().upper() for x in re.split(r"[|,]", cell) if x.strip()]
            off = [x for x in named if x not in on_row]
            if off or not named:
                bad.append(f"{item}: pick {cell!r}" + (f" (no {', '.join(off)} on the row)" if off else ""))
                continue
            for letter, info in on_row.items():
                values.setdefault(info["arm"], {})[item] = 1 / len(set(named)) if letter in named else 0.0
        else:
            for letter in letters:
                cell = (r.get(f"score: {letter}") or "").strip()
                if not cell:
                    continue
                try:
                    v = float(cell.replace(",", ".") if "," in cell and "." not in cell else cell)
                except ValueError:
                    bad.append(f"{item}: score {letter} {cell!r} is not a number")
                    continue
                if letter not in on_row:
                    bad.append(f"{item}: a score for {letter}, which is not on the row")
                elif not lo <= v <= hi:  # type: ignore[operator]
                    bad.append(f"{item}: score {letter} {cell!r} is outside the scale {lo}..{hi}")
                else:
                    values.setdefault(on_row[letter]["arm"], {})[item] = v
    if bad:
        die(
            f"{len(bad)} answer(s) refused, nothing written: "
            + "; ".join(bad[:8])
            + (" ..." if len(bad) > 8 else ""),
            "invalid-file",
        )
    if not values:
        die("nothing filled in the blind columns", "not-enough")
    return {
        "key": key,
        "metric": ("judge_won" if pick else "judge_score") + SUFFIX,
        "values": values,
    }


def _write(args: argparse.Namespace, judged: dict[str, Any], sheet_sha: str) -> None:
    """One run per arm under data/runs-judged/<scorer>/, named as its source run, shaped as judge-score's."""
    key, metric, values = judged["key"], judged["metric"], judged["values"]
    root = _common.DATA / "runs-judged" / args.scorer
    kinds_known = classify_metrics()
    written = 0
    for k, per_item in sorted(values.items()):
        arm = key["arms"][k]
        src = _common.DATA / arm["path"] if arm.get("path") else None
        if src is None or not (src / "metrics.json").is_file():
            src = run_dir(arm["run"], args.dataset_id)
        m = read_json(src / "metrics.json")
        old = {r["item_id"]: r for r in item_rows(src, strict=False)}
        recs = []
        for item in sorted(per_item):
            rec: dict[str, Any] = {"item_id": item, metric: per_item[item]}
            rec.update({c: old[item][c] for c in CARRY if c in (old.get(item) or {})})
            recs.append(rec)
        names = sorted({k_ for r in recs for k_ in r if k_ != "item_id"})
        kinds = {c: v for c, v in (m.get("metric_kinds") or {}).items() if c in names}
        for c in names:
            kinds[c] = (
                "descriptive"
                if c.startswith(BOOKKEEPING_PREFIXES)
                else kinds.get(c)
                or kinds_known.get(c)
                or ("quality" if c.startswith("judge_") else "descriptive")
            )
        new = derived_record(
            m,
            kind="judge",
            source_dir=src.name,
            source_path=src,
            scores=aggregate_scores(recs),
            n_items=len(recs),
            drop=("reference_tier",),
            metric_kinds=kinds,
            primary_metric=metric,
            with_={
                "scorer_id": args.scorer,
                "source": "sheet",
                "filled_by": args.by,
                "kind": args.kind,
                "fill": key["fill"],
                "rubric_sha256": key["rubric_sha256"],
                "sheet_sha256": sheet_sha,
                "scale": key["scale"],
                "validated": False,
                "unvalidated": True,
                "label": f"unvalidated: filled in a sheet by {args.by}",
                "source_reference_tier": m.get("reference_tier"),
            },
        )
        fp = new.get("fingerprint")
        if isinstance(fp, dict):
            fp = json.loads(json.dumps(fp))
            fp.setdefault("instrument", {})["adapter"] = {
                "id": f"sheet-import:{args.scorer}",
                "sha256": file_sha256(Path(__file__)),
            }
            seal(fp, whole=False)
            fp["hash_invalid_because"] = (
                "scores were entered in a sheet, not produced by the adapter this fingerprint was built from; "
                "see derived.with"
            )
            new["fingerprint"] = fp
        out = root / src.name
        out.mkdir(parents=True, exist_ok=True)  # no outputs of its own: they are its source's (RFC-024)
        _outputs.write_rows(out, recs)
        write_json(out / "metrics.json", new)
        written += 1
    n = sum(len(v) for v in values.values())
    print(
        f"data/runs-judged/{args.scorer}: {written} run(s), {n} judgement(s), {metric}, unvalidated · {args.kind} {args.by}"
    )
    print(
        f"  look at it: evh inspect --sheet --dataset-id {args.dataset_id} --runs {','.join(a['arm'] for a in key['arms'])}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
