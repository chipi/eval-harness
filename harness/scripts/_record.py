"""The record of a scored run (the run's run.json and its score's metrics.json): one constructor for a measured run,
one for a derived one.

Four writers built the record by hand: evh run and import-run field by field, rescore
and judge-score by copying the source run and patching it, each with its own provenance
fields (`rescored_*`, `judged_*`, and the scifact example's `reparsed_*`). A derived run kept
its source's `created_at`, so "made after the goal policy's cut-over" was read off the wrong
date. Now:

    run_record(...)          a measured run: evh run, import-run
    derived_record(...)      a run computed from another run's stored outputs: rescore,
                             judge-score, the scifact reparse. It records
                             derived = {kind, from, at, with} and its own created_at, and
                             keeps the source's as source_created_at.

The fields are specified in schemas/metrics.schema.json.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import json
import statistics
from pathlib import Path
from typing import Any

from evaluation_harness._common import now
from evaluation_harness.model.runs import RUN_ONLY

#: The kinds of derivation, and what each one's `with` names.
DERIVED_KINDS = ("rescore", "judge", "reparse")


def aggregate_scores(rows: list[dict[str, Any]], digits: int = 10) -> dict[str, float]:
    """A run's `scores` from its per-item rows: each metric's mean over the rows that carry
    it, and totals, not means, for what is billed (`total_cost_usd`, `total_tokens_in`,
    `total_tokens_out`). Keys starting with `_` are not metrics. evh run rounds means
    to 6 digits, as its runs always have; the derived records to 10."""
    keys = sorted({k for r in rows for k in r if k != "item_id" and not k.startswith("_")})
    scores = {k: round(statistics.fmean(float(r[k]) for r in rows if k in r), digits) for k in keys}
    for k in ("cost_usd", "tokens_in", "tokens_out"):
        vals = [float(r[k]) for r in rows if k in r]
        if vals:
            scores[f"total_{k}"] = round(sum(vals), 8)
    return scores


def run_scorer(adapter_path: Path | None) -> Any:
    """The adapter's optional `score_run(items)`, beside its `score()` (the fleet's feedback 20): a metric of the
    run as a whole, such as precision and recall over the pairs a grouping makes, which no mean of per-item scores
    can be. Read from the adapter's own module (its `score` may be the default one, imported). None when it has
    none."""
    from evaluation_harness._adapter import _module_or_none  # noqa: PLC0415

    fn = getattr(_module_or_none(adapter_path), "score_run", None)
    return fn if callable(fn) else None


def run_level_scores(fn: Any, items: list[dict[str, Any]], per_item: dict[str, float]) -> dict[str, float]:
    """`score_run(items)` called once over every item ({item_id, output, reference, scores}), checked: a dict of
    finite numbers whose names are new (a per-item metric's name would be overwritten by a number of another
    kind). Refused, naming what is wrong, otherwise."""
    import math  # noqa: PLC0415

    from evaluation_harness._common import die  # noqa: PLC0415

    try:
        got = fn(items)
    except Exception as exc:  # noqa: BLE001
        die(f"the adapter's score_run() raised: {type(exc).__name__}: {exc}", "failed")
    if not isinstance(got, dict):
        die(f"the adapter's score_run() returned {type(got).__name__}, not a dict of named numbers", "failed")
    bad = [
        k
        for k, v in got.items()
        if not isinstance(k, str)
        or k.startswith("_")
        or isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
    ]
    if bad:
        die(f"score_run(): not a name and a finite number: {', '.join(map(str, bad))}", "failed")
    clash = sorted(set(got) & set(per_item))
    if clash:
        die(
            f"score_run(): {', '.join(clash)} is also a per-item metric of score(); a run-level metric needs its own "
            "name",
            "failed",
        )
    return {k: round(float(v), 10) for k, v in got.items()}


def run_level_names(m: dict[str, Any]) -> list[str]:
    """The metrics a run's record holds as one number for the whole run (`run_metrics`), not a mean of items."""
    names = m.get("run_metrics")
    return [str(x) for x in names] if isinstance(names, list) else []


def cut_off_items(predictions: list[dict[str, Any]], cap: Any) -> list[str]:
    """The items whose output stopped at max_tokens: the provider's finish_reason says so when the adapter records
    it; tokens_out reaching the cap says so otherwise. A row replayed on a resume is not counted (it was not called)."""
    return [
        p["item_id"]
        for p in predictions
        if not p.get("resumed")
        and (
            (p.get("_meta") or {}).get("finish_reason") == "length"
            or (isinstance(cap, (int, float)) and cap > 0 and (p.get("tokens_out") or 0) >= cap)
        )
    ]


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
    from evaluation_harness import _seal  # noqa: PLC0415

    _seal.refuse_if_sealed(dataset_id, "a run record", config_id)
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
    from evaluation_harness._actor import actor  # noqa: PLC0415

    record["actor"] = actor()  # who ran it (RFC-027): outside the fingerprint, as goal and round are
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
    `changes` sets fields (metric_kinds, primary_metric, fingerprint, ...). `source_dir` is the run the score is of:
    `derived.from_dir` names it, `runs/<id>`. The fields a run holds for what a folder used to mean (purpose,
    machine, of) are the run's, not the score's: left off."""
    if kind not in DERIVED_KINDS:
        raise ValueError(f"unknown derivation {kind!r}; one of {', '.join(DERIVED_KINDS)}")
    from evaluation_harness import _seal  # noqa: PLC0415

    _seal.refuse_if_sealed(source.get("dataset_id"), f"a {kind}", source.get("config_id"))
    when = at or now()
    record = json.loads(json.dumps(source))
    for key in (*drop, *RUN_ONLY):
        record.pop(key, None)
    block: dict[str, Any] = {
        "kind": kind,
        "from": source_dir,
        "at": when,
        "with": with_,
        "from_dir": f"runs/{source_dir}",
    }
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
    from evaluation_harness._actor import actor  # noqa: PLC0415

    record["actor"] = (
        actor()
    )  # who derived it, not who ran the source (that stays in the source's own record)
    return record


def derived_with(record: dict[str, Any], kind: str) -> dict[str, Any]:
    """What computed a derived run of `kind` ({} for any other run)."""
    block = record.get("derived") or {}
    return dict(block.get("with") or {}) if block.get("kind") == kind else {}
