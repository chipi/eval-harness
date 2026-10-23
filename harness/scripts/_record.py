"""The run record (metrics.json): one constructor for a measured run, one for a derived one.

Four writers built the record by hand: experiment-run and import-run field by field, rescore
and judge-score by copying the source run and patching it, each with its own provenance
fields (`rescored_*`, `judged_*`, and the scifact example's `reparsed_*`). A derived run kept
its source's `created_at`, so "made after the goal policy's cut-over" was read off the wrong
date. Now:

    run_record(...)          a measured run: experiment-run, import-run
    derived_record(...)      a run computed from another run's stored outputs: rescore,
                             judge-score, the scifact reparse. It records
                             derived = {kind, from, at, with} and its own created_at, and
                             keeps the source's as source_created_at.

The fields are specified in schemas/metrics.schema.json.
"""

from __future__ import annotations

import json
from typing import Any

from _common import now

#: The kinds of derivation, and what each one's `with` names.
DERIVED_KINDS = ("rescore", "judge", "reparse")


def run_record(
    *,
    run_id: str,
    dataset_id: str,
    config_id: str,
    build: dict[str, Any],
    scores: dict[str, float],
    n_items: int,
    created_at: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """A measured run's record. `fields` are the optional core fields (params, adapter,
    metric_kinds, metric_directions, primary_metric, fingerprint, reference_tier, goal,
    format, ...); one passed as None is left out rather than recorded as null."""
    record: dict[str, Any] = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "config_id": config_id,
        "created_at": created_at or now(),
        "build": build,
        "scores": scores,
        "n_items": n_items,
    }
    record.update({k: v for k, v in fields.items() if v is not None})
    return record


def derived_record(
    source: dict[str, Any],
    *,
    kind: str,
    source_dir: str,
    with_: dict[str, Any],
    scores: dict[str, float],
    n_items: int,
    at: str | None = None,
    drop: tuple[str, ...] = (),
    **changes: Any,
) -> dict[str, Any]:
    """A run computed from `source` (the record in `source_dir`) by a `kind` of derivation,
    `with_` naming what computed it. Its own created_at is the derivation's; the source's is
    kept as source_created_at. A source that was itself derived keeps its block, nested as
    `derived.source`. `drop` removes source fields that do not describe the new scores;
    `changes` sets fields (metric_kinds, primary_metric, fingerprint, ...)."""
    if kind not in DERIVED_KINDS:
        raise ValueError(f"unknown derivation {kind!r}; one of {', '.join(DERIVED_KINDS)}")
    when = at or now()
    record = json.loads(json.dumps(source))
    for key in drop:
        record.pop(key, None)
    block: dict[str, Any] = {"kind": kind, "from": source_dir, "at": when, "with": with_}
    if isinstance(source.get("derived"), dict):
        block["source"] = source["derived"]
    record.update(
        {
            "created_at": when,
            "source_created_at": source.get("source_created_at") or source.get("created_at"),
            "derived": block,
            "scores": scores,
            "n_items": n_items,
        }
    )
    record.update({k: v for k, v in changes.items() if v is not None})
    return record


def derived_with(record: dict[str, Any], kind: str) -> dict[str, Any]:
    """What computed a derived run of `kind` ({} for any other run)."""
    block = record.get("derived") or {}
    return dict(block.get("with") or {}) if block.get("kind") == kind else {}
