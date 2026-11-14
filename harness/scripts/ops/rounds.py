"""The rounds' reads (RFC-032 step 5): `evh round-list`, `round-show`, `round-evidence`, and the resources under
/api/v1/goals/{goal}/rounds. Each answers what `evh rounds --json` answers for the same thing: both read the round
through `_rounds.summary`, `view` and `evidence_values`. Opening, carrying, retiring and closing a round are the
commands `round-open`, `round-carry`, `round-retire` and `round-close`."""

from __future__ import annotations

from typing import Any

from evaluation_harness.ops.registry import Op

_R = "evaluation_harness.ops.rounds"

OPS = (
    Op("round-list", "read", "a goal's rounds: each one's status, dataset, arms in play and retired, and conclusion",
       "GET", "/goals/{goal}/rounds", f"{_R}:list_rounds", f"{_R}:say_list"),
    Op("round-show", "read", "one round as stored: what it set out to learn, its arms (how each entered, its runs, its retirement) and its conclusion",
       "GET", "/goals/{goal}/rounds/{round}", f"{_R}:show_round", f"{_R}:say_round"),
    Op("round-evidence", "read", "what the evidence says about a round: its arms read, the leader, the tests against it and what to decide next",
       "GET", "/goals/{goal}/rounds/{round}/evidence", f"{_R}:round_evidence", f"{_R}:say_evidence"),
)  # fmt: skip


def _goal(goal: str) -> None:
    from evaluation_harness._common import load_goals  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    if goal not in load_goals():
        raise Problem(f"no goal {goal!r}", "not-found")


def _round(goal: str, round: str) -> dict[str, Any]:
    from evaluation_harness import _rounds  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    _goal(goal)
    rnd = _rounds.find(goal, round)
    if rnd is None:
        have = ", ".join(r["round_id"] for r in _rounds.load_rounds(goal)) or "none"
        raise Problem(f"no round {round!r} for goal {goal!r} (it has: {have})", "not-found")
    return rnd


def list_rounds(goal: str) -> dict[str, Any]:
    """Every round of the goal: its arms in play and retired counted from its stored arms."""
    from evaluation_harness import _rounds  # noqa: PLC0415

    _goal(goal)
    return {"goal": goal, "rounds": [_rounds.summary(r) for r in _rounds.load_rounds(goal)]}


def show_round(goal: str, round: str) -> dict[str, Any]:
    """One round with its arms."""
    from evaluation_harness import _rounds  # noqa: PLC0415

    return {"goal": goal, "round": _rounds.view(_round(goal, round))}


def round_evidence(goal: str, round: str) -> dict[str, Any]:
    """The round's evidence (`model.rounds.evidence`), read with the adapter the server serves when one is set."""
    from evaluation_harness import _rounds, catalog_serve  # noqa: PLC0415
    from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415

    rnd = _round(goal, round)
    ev = model_rounds.evidence(goal, rnd, getattr(catalog_serve, "A", None))
    return {"goal": goal, "round": rnd["round_id"]} | _rounds.evidence_values(rnd, ev)


def say_list(r: dict[str, Any]) -> str:
    """round-list's answer as text: one round a line."""
    if not r["rounds"]:
        return f"{r['goal']} has no rounds (they are optional): evh round-open --goal {r['goal']} --dataset <dataset>"
    return "\n".join(
        f"{x['round_id']:<4} {x['status']:<7} {x['dataset_id']}  {x['arms']} arm(s), {x['retired']} retired"
        + (f"\n       {x['conclusion']}" if x["conclusion"] else "")
        for x in r["rounds"]
    )


def say_round(r: dict[str, Any]) -> str:
    """round-show's answer as text: the round, then each arm a line."""
    x = r["round"]
    lines = [
        f"{x['round_id']} · {x['status']} · {x['dataset_id']}"
        + (f" · from {x['from']}" if x.get("from") else "")
    ]
    if x.get("hypothesis"):
        lines.append(f"  hypothesis: {x['hypothesis']}")
    lines += [f"  changed: {c}" for c in x["changes"]]
    for a in x["arms"]:
        how = a["entered"]["how"] + (f" from {a['entered']['from']}" if a["entered"].get("from") else "")
        gone = f"; retired: {a['retired']['reason']}" if a.get("retired") else ""
        lines.append(f"  arm {a['arm']}: {len(a['runs'])} run(s), {how}{gone}")
    if x.get("conclusion"):
        lines.append(f"  concluded: {x['conclusion']}")
    return "\n".join(lines)


def say_evidence(r: dict[str, Any]) -> str:
    """round-evidence's answer as text: the leader, each arm against it, the tests, the notes and what to decide."""
    lines = [
        f"{r['round']} on {r['metric']}: {len(r['arms'])} arm(s) in play"
        + (f", leader {r['leader'].rsplit('/', 1)[-1]}" if r.get("leader") else "")
    ]
    lines += [
        f"  {x['arm'].rsplit('/', 1)[-1]:<32} {x['verdict']:<18} delta {x['delta']:+.4f}  p {x['p']}"
        for x in r["rows"]
    ]
    lines += [
        f"  against {x['label']} ({x['other'].rsplit('/', 1)[-1]}): {x['verdict']}, delta {x['delta']:+.4f}, p {x['p']}"
        for x in r["against"]
    ]
    lines += [f"  NOTE: {n}" for n in r["notes"]]
    for s in r["suggest"]:
        lines.append(f"  next: {s['what']}" + (f"\n        {s['command']}" if s["command"] else ""))
    return "\n".join(lines)
