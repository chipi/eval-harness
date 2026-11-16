"""The rounds' reads (RFC-032 step 5): `evh round-list`, `round-show`, `round-evidence`, and the resources under
/api/v1/goals/{goal}/rounds. Each answers what `evh round-list --json` answers for the same thing: both read the round
through `_rounds.summary`, `view` and `evidence_values`. Opening, carrying and retiring a round are the commands
`round-open`, `round-carry` and `round-retire`; `round-close` is a decision (RFC-032 step 9 P3): a job, `POST
/api/v1/goals/{goal}/rounds/{round}/close`."""

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
    Op("round-close", "decision", "close a round with its conclusion, promoting the run it chose",
       "POST", "/goals/{goal}/rounds/{round}/close", "evaluation_harness.rounds:close_body", "",
       locks=(("goal:{goal}", True),), why="conclusion",
       required=("goal", "round", "conclusion"), inputs={
           "goal": {"type": "string", "description": "the goal the round belongs to"},
           "round": {"type": "string", "description": "the round to close"},
           "conclusion": {"type": "string", "description": "what the round showed, and what it decided"},
           "promote": {"type": "string", "x-metavar": "RUN_ID", "description": "promote this run to the goal's baseline on the round's dataset, the conclusion as its reason"},
           "confirm_extra_look": {"type": "boolean", "description": "--promote on a test set past its limit of looks (RFC-029): the person's consent (passed to run-promote)"},
           "override_no_evidence": {"type": "boolean", "description": "--promote on a test set whose items cannot show it: promote anyway, inconclusive (passed to run-promote)"},
       }),
)  # fmt: skip


def _goal(goal: str) -> None:
    from evaluation_harness._common import load_goals  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    goals = load_goals()
    if goal not in goals:
        raise Problem(f"no goal {goal!r}: one of {', '.join(sorted(goals)) or '(none)'}", "not-found")


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
    if x.get("harness"):
        h = x["harness"]
        lines.append(
            f"  harness: {h.get('version')}"
            + (f" at {h['commit']}" if h.get("commit") and not h.get("installed") else "")
            + f" (code {str(h.get('code_sha256'))[:12]})"
        )
    if x.get("scorer"):
        lines.append(f"  judged by: {x['scorer']}")
    for sc in x.get("scoring") or []:
        lines.append(
            f"  scoring {str(sc.get('at', ''))[:10]}: {sc.get('why', '')} "
            f"({sc.get('scorer', '')}, {sc.get('runs', 0)} run(s) re-scored into {', '.join(sc.get('written') or []) or '—'})"
        )
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
