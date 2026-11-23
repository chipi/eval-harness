"""The goal's operations (RFC-032 step 1): list, show, status, history (reads); new, set (edits). Each is
`evh goal-<verb>` and a resource under /api/v1/goals."""

from __future__ import annotations

from typing import Any

from evaluation_harness.catalog_periods import PERIODS
from evaluation_harness.ops.registry import Op

_GOAL = {"type": "string", "description": "the goal's id"}
_SET = {
    "type": "object",
    "description": "fields to set, by dotted key (success_criteria.primary.measure); the command takes KEY=VALUE",
    "additionalProperties": True,
}
_UNSET = {"type": "array", "items": {"type": "string"}, "description": "fields to remove, by dotted key"}
_PERIOD = {
    "type": "string",
    "enum": [k for k, *_ in PERIODS],
    "description": "add each goal's numbers in a period counted from today: "
    + ", ".join(f"{k} ({label})" for k, label, _ in PERIODS),
}

OPS = (
    Op("goal-list", "read", "every goal: its title, status and measure, its datasets, how many systems were filed for it, the arm it recommends, and its studies; with a period, each goal's runs and spend in it and what happened to it",
       "GET", "/goals", "evaluation_harness.ops.goals:list_goals", "evaluation_harness.ops.goals:say_list",
       inputs={"period": _PERIOD}),
    Op("goal-show", "read", "one goal, as stored", "GET", "/goals/{goal}",
       "evaluation_harness.ops.goals:show", "evaluation_harness.ops.goals:say_record"),
    Op("goal-status", "read", "where a goal stands: its datasets, reference, runs, baseline, rounds, what runs now, and the next step",
       "GET", "/goals/{goal}/status", "evaluation_harness.ops.goals:status", "evaluation_harness.ops.goals:say_status"),
    Op("goal-leaderboard", "read", "where each arm of a goal stands on each of its datasets, per reference scored against: its means on the goal's axes, flags and tests, the leader, the contenders, the recommended arm and the baseline; with arms or top, only the arms chosen (the baseline, the leader and the recommended arm stay)",
       "GET", "/goals/{goal}/leaderboard", "evaluation_harness.ops.goals:leaderboard", "evaluation_harness.ops.goals:say_leaderboard",
       inputs={
           "arms": {"type": "array", "items": {"type": "string"}, "description": "only arms whose arm or system id contains PATTERN (or fits it, as a glob when it has * ? or [); comma-separated within a value"},
           "top": {"type": "integer", "minimum": 1, "description": "only the first N arms in the goal's own order"},
       }),
    Op("goal-history", "read", "a goal's saves, newest first: when, by whom, what it was", "GET", "/goals/{goal}/history",
       "evaluation_harness.ops.goals:history", "evaluation_harness.ops.goals:say_history"),
    Op("goal-new", "edit", "make a goal, checked against its schema and the datasets and references it names", "POST",
       "/goals/{goal}", "evaluation_harness.ops.goals:new", "evaluation_harness.ops.goals:say_saved",
       inputs={"set": _SET}, required=("set",)),
    Op("goal-set", "edit", "change a goal's fields, checked as a new one is; its comments kept", "PATCH", "/goals/{goal}",
       "evaluation_harness.ops.goals:change", "evaluation_harness.ops.goals:say_saved",
       inputs={"set": _SET, "unset": _UNSET}),
)  # fmt: skip


def _adapter_view() -> tuple[Any, dict]:
    from evaluation_harness.ops.views import _view  # noqa: PLC0415

    return _view()


def list_goals(period: str | None = None) -> dict[str, Any]:
    """Every goal: its id, title, status and primary measure, its datasets, how many systems were filed for it, the arm each
    of its decisions recommends (with what it costs and how fast it is against the baseline), and its studies; with
    `period`, each goal's runs and spend in the period against the one before, and what happened in it."""
    from evaluation_harness import _common, _jsonout  # noqa: PLC0415
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415
    from evaluation_harness.model import goal_views as gv  # noqa: PLC0415
    from evaluation_harness.model import period_views  # noqa: PLC0415
    from evaluation_harness.model.goals import GOAL  # noqa: PLC0415
    from evaluation_harness.ops.views import _period  # noqa: PLC0415

    A, by_ds = _adapter_view()
    seen = gv.glance(A, by_ds)
    studies = getattr(A, "studies", None)
    rows = []
    for g in GOAL.all():
        gid = g.get("goal_id")
        full = next((x for x in A.goals() if x["goal_id"] == gid), g)
        rows.append(
            {
                "goal": gid,
                "title": g.get("title"),
                "status": g.get("status"),
                "measure": (g.get("success_criteria") or {}).get("primary"),
                "datasets": [d.get("dataset_id", "") for d in full.get("datasets") or []],
                "systems_filed": gv.systems_filed(by_ds, full),
                "recommended": [
                    {
                        "dataset": r["dataset"],
                        "arm": r["recommended"],
                        "label": r["recommended_label"],
                        "vs_baseline": r["vs_baseline"],
                    }
                    for r in seen
                    if r["goal"]["goal_id"] == gid and r["recommended"]
                ],
                "studies": [
                    {k: s.get(k) for k in ("study", "status", "baseline", "spent_usd", "end")}
                    | {"trials": len(s.get("rows") or []), "confirms": len(s.get("confirms") or [])}
                    for s in ((studies(gid) if callable(studies) else []) or [])
                ],
            }
        )
    out: dict[str, Any] = {"goals": _jsonout.plain(rows)}
    key = _period(period)
    if key:
        rows_p = cb.period_goals(A, by_ds)
        got = period_views.rows_in(A, by_ds, rows_p, key)
        for row in out["goals"]:
            row["period"] = _jsonout.plain(got["rows"].get(row["goal"]))
        b = cp.bounds(key, _common.today(), cb.window(A, by_ds)["first"])
        out["period"] = {
            "key": key,
            "line": got["line"],
            "happened": _jsonout.plain(
                sorted(
                    (
                        {"when": day, "goal": gid, "what": cb.plain(h)}
                        for gid in rows_p
                        for day, h in rows_p[gid]["events"]
                        if b["since"] <= day <= b["until"]
                    ),
                    key=lambda x: (x["when"], x["goal"]),
                    reverse=True,
                )
            ),
        }
    return out


def show(goal: str) -> dict[str, Any]:
    """One goal, as stored."""
    from evaluation_harness.model.goals import GOAL  # noqa: PLC0415

    return {"goal": goal, "record": GOAL.get(goal)}


def status(goal: str) -> dict[str, Any]:
    """Where the goal stands (the model's view)."""
    from evaluation_harness.model import goals  # noqa: PLC0415

    return goals.status(goal)


def leaderboard(goal: str, arms: list[str] | None = None, top: int | None = None) -> dict[str, Any]:
    """The goal's decision on each of its datasets (the model's view: what the goal page and `evh goal-list` show), read
    with the adapter the server serves when one is set."""
    from evaluation_harness import catalog_serve  # noqa: PLC0415
    from evaluation_harness.catalog_adapter import shared_adapter  # noqa: PLC0415
    from evaluation_harness.model import goal_views  # noqa: PLC0415

    A = getattr(catalog_serve, "A", None) or shared_adapter()
    return goal_views.leaderboard(A, goal, arms=arms, top=top)


def history(goal: str) -> dict[str, Any]:
    """The goal's saves, newest first."""
    from evaluation_harness.model.goals import GOAL  # noqa: PLC0415

    GOAL.get(goal)
    return {"goal": goal, "saves": GOAL.history(goal)}


def new(goal: str, set: dict[str, Any], by: str) -> dict[str, Any]:
    """Make the goal from its fields (dotted keys), checked; an id that is taken is refused."""
    from evaluation_harness.model.goals import GOAL  # noqa: PLC0415

    return GOAL.make(goal, {"goal_id": goal}, list(set.items()), by)


def change(
    goal: str, by: str, set: dict[str, Any] | None = None, unset: list[str] | None = None
) -> dict[str, Any]:
    """Set and remove the goal's fields (dotted keys), checked; its comments kept."""
    from evaluation_harness.model.goals import GOAL  # noqa: PLC0415

    return GOAL.patch(goal, list((set or {}).items()), list(unset or []), by)


def say_list(r: dict[str, Any]) -> str:
    """goal-list's answer as text: one goal a row, with its recommendation and, with a period, what moved in it."""
    if not r["goals"]:
        return "no goals yet: evh goal-new <id> --set title=... (the GUIDE's step 1)"
    from evaluation_harness import catalog_views  # noqa: PLC0415

    return catalog_views.say(catalog_views.print_goals, r)


def say_record(r: dict[str, Any]) -> str:
    """goal-show's answer as text: the goal as YAML."""
    import yaml  # noqa: PLC0415

    return yaml.safe_dump(r["record"], sort_keys=False, allow_unicode=True, width=110).rstrip()


def say_status(r: dict[str, Any]) -> str:
    """goal-status's answer as text: the datasets, rounds, jobs and the next step."""
    lines = [f"{r['goal']}: {r.get('title') or ''}"]
    m = r.get("measure") or {}
    if m:
        lines.append(f"  measure     {m.get('measure')} ({m.get('direction')} is better)")
    for d in r["datasets"]:
        made = "made" if d["made"] else "not made"
        mat = ", materialized" if d["materialized"] else ""
        ref = ", reference " + ", ".join(d["references"]) if d["references"] else ", no reference"
        base = f", baseline v{d['baseline']['version']}" if d["baseline"] else ", no baseline"
        role = f"{d['role']}" + ("" if d["decides"] else ", does not decide")
        lines.append(
            f"  dataset     {d['dataset']} ({role}): {made}{mat}{ref}, {d['runs']} run(s) of {d['arms']} arm(s){base}"
        )
    for rd in r["rounds"]:
        lines.append(
            f"  round       {rd['round']} {rd['status']}, {rd['arms']} arm(s) in play, {rd['retired']} retired: "
            f"{rd.get('question') or ''}"
        )
    for j in r["running"]:
        lines.append(f"  running     {j['operation']} ({j['state']}), job {j['job']}")
    lines.append(f"  next        {r['next']['what']}: {r['next']['command']}")
    return "\n".join(lines)


def say_leaderboard(r: dict[str, Any]) -> str:
    """goal-leaderboard's answer as text: the goal's statement, its decision rule, its studies and where each arm stands on
    each dataset, per reference scored against, with what the baseline is and how the recommended arm stands against it."""
    from evaluation_harness import catalog_views  # noqa: PLC0415

    return catalog_views.say(catalog_views.print_goal, r)


def say_history(r: dict[str, Any]) -> str:
    """goal-history's answer as text: one save a line."""
    if not r["saves"]:
        return f"{r['goal']}: no saves recorded (made before 0.8.0, or by hand)"
    return "\n".join(f"{s['at']}  {s['by']}  {'made' if s['was'] is None else 'changed'}" for s in r["saves"])


def say_saved(r: dict[str, Any]) -> str:
    """A save's answer as text: saved, or unchanged."""
    return f"{r['id']}: {'saved' if r['changed'] else 'unchanged (nothing to save)'}"
