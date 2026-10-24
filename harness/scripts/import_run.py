#!/usr/bin/env python3
"""Import per-item scores produced OUTSIDE the harness, as a run the harness can test.

    evh import-run --dataset-id my_v1 --config-id arm_a \\
        --scores scores.jsonl --primary-metric wer --asc \\
        --build-ref <commit of the system that produced the outputs> \\
        --source path/to/original/run --scorer-id my_scorer --scorer-file path/to/scorer.py

WHY THIS EXISTS
  A project that already has runs -- made by its own pipeline, scored by its own scorers
  -- should not have to re-run anything to get significance tests on them. What the
  paired tests need is one score per item per arm, on the same frozen items. This writes
  exactly that as an ordinary run directory (metrics.json + predictions.jsonl + run.json),
  so pair-test, family-test, leaderboard, rank-stability and validate read it like any
  other run.

WHAT IT REFUSES
  * a dataset that is not frozen here (the items, and their hashes, are the contract);
  * scores for an item the dataset does not have, or the same item twice;
  * a non-numeric score, or a NaN;
  * items missing from the scores, unless --allow-subset, and then the coverage is
    recorded on the run, so a test on 40 of 50 items cannot pass for a test on 50;
  * a build ref that is not given: the system that produced the outputs is half of what
    the numbers mean, and the project's own commit is not it.

WHAT IT RECORDS
  The fingerprint marks the run `imported`, with where it came from (`--source`), which
  scorer produced the numbers and that scorer's hash, and the harness version that
  imported it. The harness did not call the system or score the outputs; the run says so.

INPUT
  --scores is JSONL, one row per item: {"item_id": "...", "<metric>": <number>, ...}.
  Every key but item_id is a metric; a key starting with "_" is carried as metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from _common import (
    DATA,
    DATASETS,
    ROOT,
    RUNS,
    die,
    now,
    read_json,
    sha256,
    write_json,
    write_text_atomic,
)
from _fingerprint import build_fingerprint
from _record import run_record


def _rows(path: Path) -> list:
    rows = []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            die(f"{path}:{n}: not JSON ({exc})")
        if not isinstance(row, dict) or "item_id" not in row:
            die(f"{path}:{n}: each row must be an object with an item_id")
        rows.append(row)
    return rows


def main() -> int:
    """Import external scores as a harness run."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--config-id", required=True, help="the arm's name, as tests will refer to it")
    ap.add_argument("--scores", required=True, type=Path, help="JSONL: item_id + numeric metrics")
    ap.add_argument("--primary-metric", required=True)
    ap.add_argument("--asc", action="store_true", help="lower is better for the primary metric")
    ap.add_argument(
        "--build-ref",
        required=True,
        help="identity of the system that produced the outputs (commit, version, digest)",
    )
    ap.add_argument("--source", required=True, help="where the outputs and scores came from")
    ap.add_argument("--scorer-id", required=True, help="the scoring code that produced the numbers")
    ap.add_argument(
        "--scorer-file",
        type=Path,
        action="append",
        default=[],
        help="a file of that scoring code (repeatable, in a fixed order); hashed by what it does, "
        "docstrings and comments not counted, and recorded as the instrument",
    )
    ap.add_argument("--reference-id", help="the references the scores are against, e.g. gold/my_v1")
    ap.add_argument("--reference-tier", choices=("gold", "silver"))
    ap.add_argument(
        "--metric-kind",
        action="append",
        default=[],
        metavar="METRIC=KIND",
        help="quality | descriptive | cost | speed (repeatable)",
    )
    ap.add_argument(
        "--allow-subset",
        action="store_true",
        help="accept scores for only part of the dataset, recorded as coverage",
    )
    ap.add_argument("--run-id", help="default: <config-id>_<timestamp>")
    args = ap.parse_args()

    ds_file = DATASETS / f"{args.dataset_id}.json"
    if not ds_file.is_file():
        die(
            f"dataset {args.dataset_id} is not frozen: {ds_file} does not exist. "
            f"Freeze the items first (evh dataset-create)."
        )
    dataset = read_json(ds_file)
    known = {it["item_id"] for it in dataset["items"]}

    rows = _rows(args.scores)
    seen, metrics = set(), set()
    for row in rows:
        iid = row["item_id"]
        if iid in seen:
            die(f"item {iid!r} is scored twice in {args.scores}")
        if iid not in known:
            die(f"item {iid!r} is not in dataset {args.dataset_id}")
        seen.add(iid)
        for k, v in row.items():
            if k == "item_id" or k.startswith("_"):
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v):
                die(f"item {iid!r}: {k}={v!r} is not a number")
            metrics.add(k)
    if args.primary_metric not in metrics:
        die(f"--primary-metric {args.primary_metric!r} is not among the scored metrics: {sorted(metrics)}")
    missing = sorted(known - seen)
    if missing and not args.allow_subset:
        die(
            f"{len(missing)} of {len(known)} items have no scores (first: {missing[0]}). "
            f"Pass --allow-subset to import anyway; the coverage is recorded on the run."
        )

    kinds = {}
    for spec in args.metric_kind:
        k, _, v = spec.partition("=")
        if v not in ("quality", "descriptive", "cost", "speed"):
            die(f"--metric-kind {spec!r}: kind must be quality, descriptive, cost or speed")
        kinds[k] = v

    scores = {}
    for m in sorted(metrics):
        vals = [r[m] for r in rows if m in r]
        scores[m] = round(sum(vals) / len(vals), 6)

    run_id = args.run_id or f"{args.config_id}_{now().replace('-', '').replace(':', '')}"
    run_dir = RUNS / run_id
    if run_dir.exists():
        die(f"{run_dir} already exists")

    scorer_sha256 = None
    if args.scorer_file:
        from _codeid import file_sha256  # noqa: PLC0415

        parts = []
        for f in args.scorer_file:
            h = file_sha256(f)
            if h is None:
                die(f"cannot read --scorer-file {f}")
            parts.append(h)
        # One file: its own hash. Several: one hash over theirs, in the order given.
        scorer_sha256 = parts[0] if len(parts) == 1 else hashlib.sha256("\n".join(parts).encode()).hexdigest()
    imported = {
        "source": args.source,
        "scorer_id": args.scorer_id,
        "scorer_sha256": scorer_sha256,
        "scores_file": args.scores.name,
        # The exact bytes imported: a name can be reused, a hash cannot.
        "scores_sha256": sha256(args.scores),
        "items_scored": len(seen),
        "items_in_dataset": len(known),
    }
    params = {"imported": True, "source": args.source}
    fingerprint = build_fingerprint(
        root=ROOT,
        data_dir=DATA,
        dataset=dataset,
        reference_id=args.reference_id,
        reference_tier=args.reference_tier,
        config_id=args.config_id,
        params=params,
        adapter_id=f"imported:{args.scorer_id}",
        adapter_path=None,
        # The scoring code is the instrument: inside the hash, so two imports scored by different
        # versions of it are not "the same conditions". `imported` (added below) stays outside:
        # its scores_sha256 is the result, unique to every run.
        adapter_sha256=scorer_sha256,
    )
    fingerprint["imported"] = imported

    run_dir.mkdir(parents=True)
    write_json(
        run_dir / "run.json",
        {
            "config_id": args.config_id,
            "dataset_id": args.dataset_id,
            "run_id": run_id,
            "started_at": now(),
            "imported": True,
        },
    )
    write_text_atomic(
        run_dir / "predictions.jsonl", "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
    )
    metrics_doc = run_record(
        run_id=run_id,
        dataset_id=args.dataset_id,
        config_id=args.config_id,
        build={"ref": args.build_ref, "dirty": None, "source": "import-run --build-ref"},
        scores=scores,
        n_items=len(rows),
        params=params,
        adapter=f"imported:{args.scorer_id}",
        metric_kinds=kinds,
        # --asc is the importer's way of saying what an adapter says with METRIC_DIRECTIONS.
        metric_directions={args.primary_metric: "lower"} if args.asc else None,
        primary_metric=args.primary_metric,
        fingerprint=fingerprint,
        imported=imported,
        reference_tier=args.reference_tier or None,
    )
    write_json(run_dir / "metrics.json", metrics_doc)
    cover = f"{len(seen)}/{len(known)} items" + (" (subset)" if missing else "")
    print(
        f"imported {run_id}: {cover}, {len(metrics)} metric(s), "
        f"{args.primary_metric}={scores[args.primary_metric]}"
    )
    print(f"  {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
