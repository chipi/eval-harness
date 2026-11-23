"""What each metric measures, as data (RFC-032 step 8): which way is better, what it is, where it is recorded, the goals
that decide on it or weigh it, and, for one metric, the arms recording it, best first. `evh metric-list`, the metric pages'
numbers and `GET /metrics` read it."""

from __future__ import annotations

from datetime import date
from typing import Any

from evaluation_harness import catalog_build as cb
from evaluation_harness._runs import better_word
from evaluation_harness.model import arm_views, period_views
from evaluation_harness.model.entity import Problem

NOT_DESCRIBED = "not described: add it to the adapter's METRIC_DESCRIPTIONS"


def _project(A) -> dict:
    fn = getattr(A, "metric_descriptions", None)
    return fn() if callable(fn) else {}


def metrics(
    A, by_ds: dict, dataset: str | None = None, period: str | None = None, today: date | None = None
) -> dict[str, Any]:
    """Every metric recorded (on `dataset`, when given): {"metrics": [{"metric", "better", "description", "datasets":
    {dataset: arms}, "decides": [goal], "weighs": [goal], "period": {"arms", "arms_prev", "new"} | None}], "period":
    the line saying the period, or ""}. `better` is lower, higher or neutral."""
    project = _project(A)
    idx = cb.metric_index(A, by_ds)
    per: dict[str, Any] = (
        period_views.rows_in(A, by_ds, cb.period_metrics(A, by_ds), period, today)
        if period
        else {"rows": {}, "line": ""}
    )
    out = []
    for m in sorted(idx, key=lambda k: (k.startswith(("total_", "self_family_", "resumed", "failed")), k)):
        where = idx[m]
        if dataset and dataset not in where["datasets"]:
            continue
        out.append(
            {
                "metric": m,
                "better": cb.metric_direction(A, m, where),
                "description": cb.describe_metric(m, project) or None,
                "datasets": dict(sorted(where["datasets"].items())),
                "decides": [g["goal_id"] for g in where["goals"]],
                "weighs": [g["goal_id"] for g in where["weighs"]],
                "period": per["rows"].get(m),
            }
        )
    return {"period": per["line"], "metrics": out}


def metric(A, by_ds: dict, name: str, dataset: str | None = None) -> dict[str, Any]:
    """One metric in full: how it is described and computed, which way is better, its kind, the goals that decide on it
    and weigh it, and on each dataset the arms recording it, best first (the reference-scored rows ahead of the rest).
    Refused when no arm records it."""
    project = _project(A)
    idx = cb.metric_index(A, by_ds)
    where = idx.get(name)
    if where is None:
        raise Problem(f"no metric {name!r} is recorded: one of {', '.join(sorted(idx))}", "not-found")
    which = cb.metric_direction(A, name, where)
    lower = which == "lower"
    on = []
    for ds in sorted(where["datasets"]):
        if dataset and ds != dataset:
            continue
        v = by_ds[ds]
        tiers = {r["id"]: r["tier"] for r in v["refs"]}
        arms = [a for a in v["arms"] if name in a["means"]]
        arms.sort(
            key=lambda a: (
                cb.scored_by_rank(a, tiers),
                a.get("reference") or "",
                a["means"][name][0] * (1 if lower else -1),
            )
        )
        on.append(
            {
                "dataset": ds,
                "arms": [
                    {
                        "arm": a["label"],
                        "mean": a["means"][name][0],
                        "shown": cb.metric_value(A, name, a["means"][name][0]),
                        "n": a["means"][name][1],
                        "scored_against": arm_views.scored(a),
                        "row": arm_views.kind(a, tiers),
                    }
                    for a in arms
                ],
            }
        )
    return {
        "metric": name,
        "better": better_word(which),
        "description": cb.describe_metric(name, project) or None,
        "details": cb.metric_details(name, project),
        "kind": cb._kind_of(A, name, where["datasets"]),
        "decides": [g["goal_id"] for g in where["goals"]],
        "weighs": [g["goal_id"] for g in where["weighs"]],
        "item_word": A.item_word,
        "datasets": on,
    }
