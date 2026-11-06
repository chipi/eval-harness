#!/usr/bin/env python3
"""A finished run's outputs as a model's label set (RFC-023): what that model said each item's answer is.

    evh label-from-run --run tickets_author_v1_20261101T101500 --set author_v1
    evh label-from-run --run … --set author_v1 --guideline prompts/author.txt

It calls nothing: the outputs are the run's, so the labels are exactly what you read. It refuses what
`run-promote` refuses (an unknown build, a dirty tree), an unfinished, derived or partial run, an empty output,
and outputs that stopped at max_tokens (`--allow-cut-off` for outputs that end at the cap by design). The set's
source is `model`: the run, its config, fingerprint and build. Labels are not a reference (RFC-023).

--not-redistributed keeps the texts out of git (the corpus's licence, or the project's choice): the set's directory
gets a .gitignore for them, and labels.json records that and the command that rebuilds them; the same command on a
set whose texts are not here writes them again from the run and checks them against the set's checksums.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
from pathlib import Path

from evaluation_harness import _outputs, _runs
from evaluation_harness._common import RUNS, die, evh_prog, load_dataset, read_json
from evaluation_harness._label_sets import set_dir, write_set


def _unusable(rows: list[tuple[str, str, object]], max_tokens: object) -> tuple[list[str], list[str]]:
    """The items whose output is empty, and those that stopped at max_tokens.

    Both are refused. Opus at max_tokens 80 wrote 19 of 20 news summaries that stopped
    mid-sentence, and one reply that was empty, and they were frozen as the silver every other
    arm was scored against, with no word from the harness.
    """
    empty = [item for item, text, _ in rows if not text.strip()]
    cap = int(max_tokens) if isinstance(max_tokens, (int, float)) and max_tokens > 0 else None
    cut = [
        item
        for item, text, out in rows
        if text.strip() and cap and isinstance(out, (int, float)) and out >= cap
    ]
    return empty, cut


def _refuse_unusable(
    rows: list[tuple[str, str, object]], max_tokens: object, allow_cut_off: bool, where: str
) -> None:
    """Die on an empty output, or on outputs cut off at max_tokens unless they are allowed."""
    empty, cut = _unusable(rows, max_tokens)
    if empty:
        die(
            f"REFUSED: {len(empty)} empty output(s) ({', '.join(empty[:8])}"
            + (" ..." if len(empty) > 8 else "")
            + f").\n  An empty reference is never the right answer. {where}",
            "not-enough",
        )
    if cut and not allow_cut_off:
        die(
            f"REFUSED: {len(cut)} of {len(rows)} output(s) stopped at max_tokens={max_tokens} "
            f"({', '.join(cut[:8])}" + (" ..." if len(cut) > 8 else "") + ").\n"
            "  A reference cut off mid-answer marks every complete answer down. Raise max_tokens\n"
            f"  in the config (a new config_id) and run it again. {where}\n"
            "  (--allow-cut-off freezes them anyway, for outputs that end at the cap by design.)",
            "not-enough",
        )


def _from_run(run_id: str, dataset_id: str, items: list[dict], args: argparse.Namespace) -> tuple[list, dict]:
    """A finished run's outputs, and the provenance its reference carries.

    The refusals are run-promote's: a reference is a decision every later score depends on,
    so it must name the code and the system that produced it.
    """
    run_dir = RUNS / run_id
    if not (run_dir / "metrics.json").is_file():
        hint = " (it has no metrics.json: it did not finish)" if run_dir.is_dir() else ""
        die(f"no finished run {run_id!r} under {RUNS}{hint}", "not-found")
    m = read_json(run_dir / "metrics.json")
    if m.get("dataset_id") != dataset_id:
        die(f"REFUSED: run {run_id} is on {m.get('dataset_id')!r}, not {dataset_id!r}", "mismatch")
    if (m.get("derived") or {}).get("kind"):
        die(
            f"REFUSED: run {run_id} is {m['derived']['kind']}d from {m['derived'].get('from')}; "
            "make the reference from the run that produced the outputs",
            "not-allowed",
        )
    build = m.get("build") or {}
    if build.get("ref", "unknown") == "unknown" and not args.allow_unknown_build:
        die(
            f"REFUSED: run {run_id} does not identify its build, so the reference could not say\n"
            "  which system wrote it. Set EVAL_BUILD_REF and run the arm again\n"
            "  (--allow-unknown-build overrides).",
            "not-configured",
        )
    if build.get("dirty") and not args.allow_dirty:
        die(
            f"REFUSED: run {run_id} was produced by a dirty tree; build.ref={str(build.get('ref', '?'))[:12]}\n"
            "  does not describe what ran. Commit, run the arm again, and use that run\n"
            "  (--allow-dirty overrides).",
            "not-allowed",
        )
    tokens: dict[str, object] = {}
    for row in _runs.item_rows(run_dir):
        tokens[row["item_id"]] = row.get("tokens_out")
    rows, missing = [], []
    for item in items:
        text = _outputs.output(run_dir, item["item_id"])
        if text is None:
            missing.append(item["item_id"])
            continue
        rows.append((item["item_id"], text, tokens.get(item["item_id"])))
    if missing:
        die(
            f"REFUSED: run {run_id} has no output for {len(missing)} item(s) "
            f"({', '.join(missing[:8])}" + (" ..." if len(missing) > 8 else "") + ")",
            "not-enough",
        )
    params = dict(m.get("params") or {})
    _refuse_unusable(rows, params.get("max_tokens"), args.allow_cut_off, f"Run {run_id}.")
    source = {
        "run_id": run_id,
        "config_id": m.get("config_id"),
        "fingerprint_hash": (m.get("fingerprint") or {}).get("hash"),
        "build": build,
        "reference_tier": m.get("reference_tier"),
        "cost_usd": (m.get("scores") or {}).get("total_cost_usd"),
    }
    meta = {
        "authored_by": m.get("config_id"),
        "authored_with": m.get("adapter"),
        "model": params.get("model", params.get("provider", "unknown")),
        "system_under_test": (m.get("fingerprint") or {}).get("deployment"),
        "params": params,
        "from_run": source,
        "cost_usd": 0.0,
    }
    return rows, meta


def _rebuild(dataset_id: str, name: str, rows: list) -> bool:
    """A set kept out of git (--not-redistributed) whose texts are not here: write them from the run and check them
    against the set's checksums. False when this is not that case."""
    d = set_dir(dataset_id, name)
    lj = d / "labels.json"
    if not lj.is_file() or any(d.glob("*.txt")):
        return False
    doc = read_json(lj)
    if doc.get("redistributed") is not False:
        return False
    want = {iid: row.get("sha256") for iid, row in (doc.get("items") or {}).items()}
    texts = {iid: str(text).strip() + "\n" for iid, text, _ in rows if iid in want}
    bad = [iid for iid in want if hashlib.sha256(texts.get(iid, "").encode()).hexdigest() != want[iid]]
    if bad:
        die(
            f"REFUSED: the texts rebuilt from the run do not match {lj}'s checksums ({len(bad)} of {len(want)} differ):"
            " the run's outputs changed since the set was made. Nothing was written.",
            "mismatch",
        )
    for iid, text in texts.items():
        (d / f"{iid}.txt").write_text(text, encoding="utf-8")
    print(f"{d}: {len(texts)} label text(s) rebuilt from the run, matching the set (no calls)")
    return True


def main() -> int:
    """Take a finished run's outputs as a model's label set."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, help="the run whose outputs become the labels")
    ap.add_argument("--set", required=True, dest="name", help="the label set's name (lowercase, _ . -)")
    ap.add_argument(
        "--guideline",
        type=Path,
        help="a file: the prompt or instructions the model labelled by (its path and sha256 are recorded)",
    )
    ap.add_argument("--allow-cut-off", action="store_true", help="keep outputs that stopped at max_tokens")
    ap.add_argument("--allow-dirty", action="store_true", help="a run from a dirty tree")
    ap.add_argument("--allow-unknown-build", action="store_true", help="a run whose build is unknown")
    ap.add_argument(
        "--not-redistributed",
        action="store_true",
        help="keep the texts out of git (a .gitignore beside them); labels.json says how to rebuild them",
    )
    args = ap.parse_args()

    m = RUNS / args.run / "metrics.json"
    if not m.is_file():
        die(f"no finished run {args.run!r} under {RUNS}", "not-found")
    dataset_id = read_json(m).get("dataset_id")
    if not dataset_id:
        die(f"run {args.run} names no dataset", "invalid-file")
    rows, meta = _from_run(args.run, dataset_id, load_dataset(dataset_id)["items"], args)
    if _rebuild(dataset_id, args.name, rows):
        return 0
    source = {"kind": "model", **meta["from_run"], "model": meta.get("model")}
    rebuild = (
        f"evh label-from-run --run {args.run} --set {args.name} --not-redistributed"
        if args.not_redistributed
        else None
    )
    doc = write_set(
        dataset_id,
        args.name,
        {item: text for item, text, _ in rows},
        source,
        args.guideline,
        rebuild=rebuild,
    )
    print(f"data/labels/{dataset_id}/{args.name}: {doc['n_items']} label(s), source model · {args.run}")
    if rebuild:
        print(f"  its texts are kept out of git; commit labels.json. They are rebuilt with: {rebuild}")
    print(f"  every set on it: evh labels --dataset-id {dataset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
