"""The studies' reads (RFC-032 step 7): `evh study-list`, `study-show`, and the resources under
/api/v1/goals/{goal}/studies. `evh studies` stays what it is (every study with its counts, or one as its log says);
these answer the API a goal's studies and one study as resources, read through model/study_views. Running, asking,
telling, stopping, confirming and importing a study are the commands `study-run`, `study-ask`, `study-tell`,
`study-stop`, `study-confirm` and `study-import`."""

from __future__ import annotations

from typing import Any

from evaluation_harness.ops.registry import Op

_S = "evaluation_harness.ops.studies"

OPS = (
    Op("study-list", "read", "a goal's studies: where each stands, its dataset and measure, its trials kept, what it spent and its confirmations",
       "GET", "/goals/{goal}/studies", f"{_S}:list_studies", f"{_S}:say_list"),
    Op("study-show", "read", "one study: its spec as written, its trials with how each was decided, the best so far, how it ended and its confirmations",
       "GET", "/goals/{goal}/studies/{study}", f"{_S}:show_study", f"{_S}:say_study"),
)  # fmt: skip


def _goal(goal: str) -> None:
    from evaluation_harness._common import load_goals  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    if goal not in load_goals():
        raise Problem(f"no goal {goal!r}", "not-found")


def list_studies(goal: str) -> dict[str, Any]:
    """Every study of the goal, from its log."""
    from evaluation_harness.model import study_views  # noqa: PLC0415

    _goal(goal)
    return {"goal": goal, "studies": study_views.list_studies(goal)}


def show_study(goal: str, study: str) -> dict[str, Any]:
    """One study: its spec, its state from its log, its confirmations."""
    from evaluation_harness.model import study_views  # noqa: PLC0415
    from evaluation_harness.model.studies import STUDY  # noqa: PLC0415

    _goal(goal)
    STUDY.get(f"{goal}/{study}")
    return study_views.show_study(goal, study)


def say_list(r: dict[str, Any]) -> str:
    """study-list's answer as text: one study a line."""
    if not r["studies"]:
        return f"{r['goal']} has no studies: evh study-run {r['goal']}/<id> --spec FILE"
    return "\n".join(
        f"{x['study']:<28} {x['status']:<11} {x['trials']} trial(s), {x['kept']} kept, ${x['spent_usd']:.4f}"
        + (f", {x['confirms']} confirm line(s)" if x["confirms"] else "")
        for x in r["studies"]
    )


def say_study(r: dict[str, Any]) -> str:
    """study-show's answer as text: where it stands, each trial a line, how it ended and its confirmations."""
    spec = r["spec"]
    lines = [
        f"{r['study']}: {r['status']}, round {r['round']}, from {r['baseline']}, ${r['spent_usd']:.4f} spent  ({r['file']})",
        f"  on {spec.get('dataset')}, decided on {spec.get('measure')}",
    ]
    lines += [
        f"  t{t['k']}  {t['outcome']!s:<9} {t['change'] or t['hypothesis']}  - {t['reason']}"
        for t in r["rows"]
    ]
    lines.append(f"  best so far: {r['best'] or str(r['baseline']) + ' (the baseline)'}")
    lines += [
        f"  confirm on {c.get('test')}: {c.get('outcome', 'started')} (look {(c.get('look') or {}).get('number')})"
        for c in r["confirms"]
    ]
    if r["end"]:
        lines.append(f"  ended: {r['end']}. {r['summary']}")
    return "\n".join(lines)
