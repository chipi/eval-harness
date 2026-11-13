"""The goal's operations (RFC-032 step 1): list, show, status, history (reads); new, set (edits). Each is
`evh goal-<verb>` and a resource under /api/v1/goals."""

from __future__ import annotations

from typing import Any

from evaluation_harness.ops.registry import Op

_GOAL = {"type": "string", "description": "the goal's id"}
_SET = {
    "type": "object",
    "description": "fields to set, by dotted key (success_criteria.primary.measure); the command takes KEY=VALUE",
    "additionalProperties": True,
}
_UNSET = {"type": "array", "items": {"type": "string"}, "description": "fields to remove, by dotted key"}

OPS = (
    Op("goal-list", "read", "every goal: its title, status and measure", "GET", "/goals",
       "evaluation_harness.ops.goals:list_goals", "evaluation_harness.ops.goals:say_list"),
    Op("goal-show", "read", "one goal, as stored", "GET", "/goals/{goal}",
       "evaluation_harness.ops.goals:show", "evaluation_harness.ops.goals:say_record"),
    Op("goal-status", "read", "where a goal stands: its datasets, reference, runs, baseline, rounds, what runs now, and the next step",
       "GET", "/goals/{goal}/status", "evaluation_harness.ops.goals:status", "evaluation_harness.ops.goals:say_status"),
    Op("goal-history", "read", "a goal's saves, newest first: when, by whom, what it was", "GET", "/goals/{goal}/history",
       "evaluation_harness.ops.goals:history", "evaluation_harness.ops.goals:say_history"),
    Op("goal-new", "edit", "make a goal, checked against its schema and the datasets and references it names", "POST",
       "/goals/{goal}", "evaluation_harness.ops.goals:new", "evaluation_harness.ops.goals:say_saved",
       inputs={"set": _SET}, required=("set",)),
    Op("goal-set", "edit", "change a goal's fields, checked as a new one is; its comments kept", "PATCH", "/goals/{goal}",
       "evaluation_harness.ops.goals:change", "evaluation_harness.ops.goals:say_saved",
       inputs={"set": _SET, "unset": _UNSET}),
)  # fmt: skip


def list_goals() -> dict[str, Any]:
    """Every goal: its id, title, status and primary measure."""
    from evaluation_harness.model.goals import GOAL  # noqa: PLC0415

    return {
        "goals": [
            {
                "goal": g.get("goal_id"),
                "title": g.get("title"),
                "status": g.get("status"),
                "measure": (g.get("success_criteria") or {}).get("primary"),
            }
            for g in GOAL.all()
        ]
    }


def show(goal: str) -> dict[str, Any]:
    """One goal, as stored."""
    from evaluation_harness.model.goals import GOAL  # noqa: PLC0415

    return {"goal": goal, "record": GOAL.get(goal)}


def status(goal: str) -> dict[str, Any]:
    """Where the goal stands (the model's view)."""
    from evaluation_harness.model import goals  # noqa: PLC0415

    return goals.status(goal)


def history(goal: str) -> dict[str, Any]:
    """The goal's saves, newest first."""
    from evaluation_harness.model.goals import GOAL  # noqa: PLC0415

    GOAL.get(goal)
    return {"goal": goal, "saves": GOAL.history(goal)}


def new(goal: str, set: dict[str, Any], by: str) -> dict[str, Any]:
    """Make the goal from its fields (dotted keys), checked; an id that is taken is refused."""
    from evaluation_harness import _settings_form  # noqa: PLC0415
    from evaluation_harness.model.goals import GOAL  # noqa: PLC0415

    record = _settings_form.set_values({"goal_id": goal}, list(set.items()), [])
    return GOAL.save(goal, record, by, new=True)


def change(
    goal: str, by: str, set: dict[str, Any] | None = None, unset: list[str] | None = None
) -> dict[str, Any]:
    """Set and remove the goal's fields (dotted keys), checked; its comments kept."""
    from evaluation_harness.model.goals import GOAL  # noqa: PLC0415

    return GOAL.patch(goal, list((set or {}).items()), list(unset or []), by)


def say_list(r: dict[str, Any]) -> str:
    """goal-list's answer as text: one goal a line."""
    rows = r["goals"]
    if not rows:
        return "no goals yet: evh goal-new <id> --set title=... (the GUIDE's step 1)"
    w = max(len(str(g["goal"])) for g in rows)
    return "\n".join(
        f"{g['goal']:<{w}}  {g.get('status') or '':<10}  {(g.get('measure') or {}).get('measure', '')}  {g.get('title') or ''}"
        for g in rows
    )


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
        lines.append(f"  running     {j['command']} ({j['state']}), job {j['job']}")
    lines.append(f"  next        {r['next']['what']}: {r['next']['command']}")
    return "\n".join(lines)


def say_history(r: dict[str, Any]) -> str:
    """goal-history's answer as text: one save a line."""
    if not r["saves"]:
        return f"{r['goal']}: no saves recorded (made before 0.8.0, or by hand)"
    return "\n".join(f"{s['at']}  {s['by']}  {'made' if s['was'] is None else 'changed'}" for s in r["saves"])


def say_saved(r: dict[str, Any]) -> str:
    """A save's answer as text: saved, or unchanged."""
    return f"{r['id']}: {'saved' if r['changed'] else 'unchanged (nothing to save)'}"
