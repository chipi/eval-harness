"""The arms, as data (RFC-032 step 8): every arm with how it was measured, its model and provider, its roles under the
goals and its cost and speed, every system across the datasets it ran on, and one arm in full (its metrics, runs,
config, conditions, siblings and rounds). `evh arms`, the arms page's rows and `GET /arms` read them; the rows are
catalog_arms.arm_rows, the one listing."""

from __future__ import annotations

from datetime import date
from typing import Any

from evaluation_harness import catalog_arms as ca
from evaluation_harness import catalog_build as cb
from evaluation_harness.axes import axis_title, builtin_axes, cell_of, cell_text
from evaluation_harness.model import goal_views as gv
from evaluation_harness.model import period_views
from evaluation_harness.model import runs as model_runs
from evaluation_harness.model.entity import Problem

KINDS = {"t-silver": "silver", "t-judged": "judged", "t-author": "wrote its reference"}
#: What `quality` names, in the words the rows carry.
QUALITY = {"contender": "a contender", "below": "below the leader"}


def scored(a: dict) -> str:
    """What an arm is scored by: its judge, else its reference."""
    return f"judge {a['judge']}" if a.get("judge") else (a.get("reference") or "—")


def kind(a: dict, tiers: dict) -> str:
    """How a row is scored, in words: silver, judged, wrote its reference, or nothing to say."""
    return KINDS.get(cb.row_kind(a, tiers), "")


def arm_ids(A, tokens: list, label: str) -> list:
    """Arm ids from what the user typed: a full arm id, or a system id looked up among the arms read under `label`."""
    known = A.arms()
    out = []
    for t in tokens:
        if t in known:
            out.append(t)
            continue
        prefix = model_runs.arm_prefix(label)
        hits = [a for a in known if a.rsplit("/", 1)[-1] == t and a.split("/", 1)[0] == prefix]
        if len(hits) != 1:
            near = [a for a in known if a.rsplit("/", 1)[-1] == t]
            raise Problem(
                f"{t!r}: "
                + (
                    f"{len(hits)} arms read as {label or 'the plain label'} match; name the arm id: {', '.join(near)}"
                    if near
                    else "no arm with that id; `evh datasets --dataset-id <id>` lists them"
                ),
                "not-found",
            )
        out.append(hits[0])
    return out


def arms(
    A,
    by_ds: dict,
    dataset: str | None = None,
    where: str | None = None,
    tier: str | None = None,
    weights: str | None = None,
    quality: str | None = None,
    systems: bool = False,
    period: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Every arm that fits, by dataset, then system, the system's own measurement first: {"arms": catalog_arms.arm_rows,
    "systems": one row per system across the datasets it ran on, with its rank on each goal (with `systems`, else None); a row's
    `goal` is its goal's id, and its `against` (the page's link) is left out,
    "period": {"line", "rows"}, "has_record", "item_word", "filters"}. `where` is local or hosted, `weights` open or
    proprietary, `quality` contender or below."""
    rows = [
        r
        for r in ca.arm_rows(A, by_ds, dataset or None)
        if (not dataset or r["dataset"] == dataset)
        and (not where or r["local"] == (where == "local"))
        and (not tier or r["tier"] == tier)
        and (not weights or r["weights"] == weights)
        and (not quality or r["quality"] == QUALITY[quality])
    ]
    per = (
        period_views.rows_in(A, by_ds, ca.period_arms(A, by_ds, rows), period, today)
        if rows and period
        else {"rows": {}, "line": ""}
    )
    by_system = (
        [
            {
                **c,
                "ranks": [
                    {"goal": g["goal_id"], "dataset": d, "rank": i, "of": n} for g, d, i, n in c["ranks"]
                ],
            }
            for c in ca.system_rows(A, by_ds, rows, cb.window(A, by_ds)["spend"])
        ]
        if systems and rows
        else None
    )
    return {
        "filters": {
            "dataset": dataset,
            "where": where,
            "tier": tier,
            "weights": weights,
            "quality": quality,
            "systems": systems,
            "period": period,
        },
        "item_word": A.item_word,
        "has_record": any(r["record"] for r in rows),
        "period": per,
        "arms": [
            {**{k: v for k, v in r.items() if k != "against"}, "goal": (r["goal"] or {}).get("goal_id")}
            for r in rows
        ],
        "systems": by_system,
    }


def arm(A, by_ds: dict, arm_id: str) -> dict[str, Any]:
    """One arm in full: where it ran, what it was scored against, its headline, its cost and speed, its metrics, its
    runs, its config (credentials are never shown) and conditions, the same system scored other ways, the rounds it is
    in, and the notes on it. Refused when no arm has the id."""
    hit = next(((ds, a) for ds, v in by_ds.items() for a in v["arms"] if a["arm"] == arm_id), None)
    if hit is None:
        raise Problem(f"no arm {arm_id!r}: `evh arms` lists them", "not-found")
    ds, a = hit
    v = by_ds[ds]
    goals = {g["goal_id"]: g for g in A.goals()}
    sc = A.scores(a["arm"])
    cells = [(ax, cell_of(ax, sc)) for ax in builtin_axes()]
    cfg_fn = getattr(A, "arm_config", None)
    cfg = cfg_fn(a["arm"]) if callable(cfg_fn) else {}
    cond_fn = getattr(A, "conditions", None)
    tiers = {r["id"]: r["tier"] for r in v["refs"]}
    rounds = []
    rfn = getattr(A, "rounds", None)
    for r in rfn() if callable(rfn) else []:
        retired = a["arm"] in gv.retired_arms(r)
        if a["arm"] in (r.get("arms") or []) or retired:
            g = goals.get(r.get("goal", ""), {})
            rounds.append(
                {
                    "round": r["round_id"],
                    "goal": g.get("goal_id", r.get("goal", "")),
                    "retired": retired,
                    "status": r.get("status", ""),
                }
            )
    return {
        "arm": a["arm"],
        "label": a["label"],
        "baseline": bool(a.get("baseline")),
        "dataset": ds,
        "scored_against": scored(a),
        "goal": a.get("goal") or None,
        "runs": a["runs"],
        "headline": {"metric": a["metric"], "mean": a["mean"]},
        "last": a["last"],
        "wrote": bool(a.get("wrote")),
        "superseded_by": a.get("superseded_by") or None,
        "item_word": A.item_word,
        "cost_speed": (
            [{"axis": axis_title(ax), "text": cell_text(ax, c)} for ax, c in cells]
            if any(c["n"] or (c.get("tokens") or {}).get("n") for _, c in cells)
            else []
        ),
        "metrics": [
            {
                "metric": m,
                "mean": mean,
                "shown": cb.metric_value(A, m, mean),
                "n": k,
                "better": "lower"
                if A.lower_is_better(m, ds)
                else ("neutral" if A.is_neutral(m, ds) else "higher"),
            }
            for m, (mean, k) in sorted(a["means"].items(), key=lambda kv: (kv[0] != a["metric"], kv[0]))
        ],
        "run_list": [
            {
                "run": r["run_id"],
                "made": r.get("created_at") or "",
                "items": r.get("items"),
                "cost_usd": r.get("cost_usd") if isinstance(r.get("cost_usd"), (int, float)) else None,
                "how": r.get("derived") or "measured",
            }
            for r in a["run_list"]
        ],
        "config": {k: cfg.get(k) for k in ("system_id", "adapter", "deployment", "params")}
        if cfg.get("params")
        else None,
        "conditions": (cond_fn(a["arm"]) if callable(cond_fn) else {}) or {},
        "siblings": [
            {
                "arm": x["arm"],
                "scored_against": scored(x),
                "metric": x["metric"],
                "mean": x["mean"],
                "row": kind(x, tiers),
            }
            for x in cb._siblings(by_ds, a, ds)
        ],
        "rounds": rounds,
        "notes": list(A.notes(a["arm"])),
    }
