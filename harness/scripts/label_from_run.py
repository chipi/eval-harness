"""A finished run's outputs as a model's label set (RFC-023): what that model said each item's answer is.

    evh label-from-run --run tickets_author_v1_20261101T101500 --set author_v1
    evh label-from-run --run … --set author_v1 --guideline prompts/author.txt

It calls nothing: the outputs are the run's, so the labels are exactly what you read. It refuses what
`run-promote` refuses (an unknown build, a dirty tree), an unfinished, derived or partial run, an empty output,
and outputs that stopped at max_tokens (`--allow-cut-off` for outputs that end at the cap by design). The set's
source is `model`: the run, its system, fingerprint and build. Labels are not a reference (RFC-023).

--not-redistributed keeps the texts out of git (the corpus's licence, or the project's choice): the set's directory
gets a .gitignore for them, and labels.json records that and the command that rebuilds them; the same command on a
set whose texts are not here writes them again from the run and checks them against the set's checksums.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

from evaluation_harness import _outputs, _runs, _store
from evaluation_harness._common import die, load_dataset, read_json, tree_state
from evaluation_harness._label_sets import set_dir, write_set
from evaluation_harness._record import empty_at_cap_note
from evaluation_harness.model import runs as _model_runs
from evaluation_harness.ops import legacy


def _at_cap(tokens_out: object, max_tokens: object) -> bool:
    """Whether an item's tokens_out reached the system's max_tokens."""
    return (
        isinstance(max_tokens, (int, float))
        and max_tokens > 0
        and isinstance(tokens_out, (int, float))
        and tokens_out >= max_tokens
    )


def _unusable(rows: list[tuple[str, str, object]], max_tokens: object) -> tuple[list[str], list[str]]:
    """The items whose output is empty, and those that stopped at max_tokens.

    Both are refused. Opus at max_tokens 80 wrote 19 of 20 news summaries that stopped
    mid-sentence, and one reply that was empty, and they were frozen as the silver every other
    arm was scored against, with no word from the harness.
    """
    empty = [item for item, text, _ in rows if not text.strip()]
    reply_cap = int(max_tokens) if isinstance(max_tokens, (int, float)) and max_tokens > 0 else None
    cut = [
        item
        for item, text, out in rows
        if text.strip() and reply_cap and isinstance(out, (int, float)) and out >= reply_cap
    ]
    return empty, cut


def _refuse_unusable(
    rows: list[tuple[str, str, object]], max_tokens: object, allow_cut_off: bool, where: str
) -> None:
    """Die on an empty output, or on outputs cut off at max_tokens unless they are allowed."""
    empty, cut = _unusable(rows, max_tokens)
    if empty:
        spent = [item for item, _text, out in rows if item in empty and _at_cap(out, max_tokens)]
        why = f"\n  {empty_at_cap_note(spent)}" if spent else ""
        die(
            f"REFUSED: {len(empty)} empty output(s) ({', '.join(empty[:8])}"
            + (" ..." if len(empty) > 8 else "")
            + f").{why}\n  An empty reference is never the right answer. Raise max_tokens\n"
            f"  in the system (a new system id) and run it again. {where}",
            "not-enough",
        )
    if cut and not allow_cut_off:
        die(
            f"REFUSED: {len(cut)} of {len(rows)} output(s) stopped at max_tokens={max_tokens} "
            f"({', '.join(cut[:8])}" + (" ..." if len(cut) > 8 else "") + ").\n"
            "  A reference cut off mid-answer marks every complete answer down. Raise max_tokens\n"
            f"  in the system (a new system id) and run it again. {where}\n"
            "  (--allow-cut-off freezes them anyway, for outputs that end at the cap by design.)",
            "not-enough",
        )


def _finished(run_id: str) -> tuple[Path, dict]:
    """The score a finished run made when it ran, and its record; refused for a run that has none."""
    run_dir = _model_runs.first_score(run_id)
    m = _model_runs.record(run_dir) if run_dir else None
    if run_dir is None or m is None:
        hint = " (it has no score: it did not finish)" if _store.is_dir(_model_runs.run_dir(run_id)) else ""
        die(f"no finished run {run_id!r} under data/runs{hint}", "not-found")
    return run_dir, m


def _from_run(run_id: str, dataset_id: str, items: list[dict], args: argparse.Namespace) -> tuple[list, dict]:
    """A finished run's outputs, and the provenance its reference carries.

    The refusals are run-promote's: a reference is a decision every later score depends on,
    so it must name the code and the system that produced it.
    """
    run_dir, m = _finished(run_id)
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
    if tree_state(build) is None and not args.allow_dirty:
        die(
            f"REFUSED: git could not say whether the tree run {run_id} came from was clean; "
            f"build.ref={str(build.get('ref', '?'))[:12]}\n"
            "  is not proven to describe what ran. Run the arm again where git works, and use that run\n"
            "  (--allow-dirty overrides).",
            "not-allowed",
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
        "config_id": m.get("system_id"),  # hashed: a label set whole, a reference through from_run
        "fingerprint_hash": (m.get("fingerprint") or {}).get("hash"),
        "build": build,
        "reference_tier": m.get("reference_tier"),
        "cost_usd": (m.get("scores") or {}).get("total_cost_usd"),
    }
    meta = {
        "authored_by": m.get("system_id"),
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
    if not _store.is_file(lj) or any(_store.glob(d, "*.txt")):
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
        _store.write_text(d / f"{iid}.txt", text, encoding="utf-8")
    print(f"{d}: {len(texts)} label text(s) rebuilt from the run, matching the set (no calls)")
    return True


def body(**inputs: Any) -> int:
    """Take a finished run's outputs as a model's label set."""
    args = legacy.namespace(inputs, "label-from-run", {"set": "name"})
    dataset_id = _finished(args.run)[1].get("dataset_id")
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
    print(f"  every set on it: evh label-set-list {dataset_id}")
    return 0
