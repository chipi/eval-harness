"""Roll a baseline back to an earlier version, as a new version (RFC-027 D2).

    evh baseline-rollback --goal triage_orrery --dataset orrery_v1 --to 2 --reason "v3's arm leaks the gold" --by ana

Writes the next version restoring version N: its run and what it carried, `restores: N`, and its own evidence (N's arm
against what is current now). Nothing is deleted or edited: the version rolled back from stays in the history. A
decision, so it needs a named actor.
"""

from __future__ import annotations

from typing import Any

from evaluation_harness import _baselines
from evaluation_harness._common import die, load_goals, now
from evaluation_harness.ops import legacy


def body(**inputs: Any) -> int:
    """Roll a baseline back."""
    args = legacy.namespace(inputs, "baseline-rollback")
    from evaluation_harness._actor import require_named  # noqa: PLC0415

    if bool(args.goal) == bool(args.no_goal):
        die("name the baseline: --goal G, or --no-goal for the dataset's own", "bad-argument")
    if len(args.reason.split()) < 3:
        die("--reason must be a sentence: why roll back?", "bad-argument")
    who = require_named("baseline-rollback")
    goal_id = None if args.no_goal else args.goal
    vs = _baselines.versions(goal_id, args.dataset)
    line = f"{goal_id or 'the dataset'}'s baseline on {args.dataset}"
    if not vs:
        die(f"{line}: no versions", "not-found")
    target = next((v for v in vs if v["version"] == args.to), None)
    if target is None:
        die(
            f"{line}: no version {args.to} (it has {', '.join(str(v['version']) for v in vs)})",
            "not-found",
        )
    if target["version"] == vs[-1]["version"]:
        die(f"{line}: version {args.to} is the current one", "not-allowed")
    from evaluation_harness.promote_baseline import evidence, run_record  # noqa: PLC0415

    m = run_record(str(target.get("promoted_from")))
    if m is None:
        die(
            f"version {args.to}'s run {target.get('promoted_from')} is gone: nothing to restore",
            "not-found",
        )
    goal = load_goals().get(goal_id) if goal_id else None

    def make(cur: dict | None, n: int) -> dict:
        keep = {
            k: target[k]
            for k in target
            if k
            not in (
                "version",
                "promoted_at",
                "actor",
                "reason",
                "replaces",
                "restores",
                "evidence",
                "migrated",
            )
        }
        return keep | {
            "promoted_at": now(),
            "actor": who,
            "reason": args.reason,
            "replaces": cur["version"] if cur else None,
            "restores": args.to,
            "evidence": evidence(m, cur, goal, None),
        }

    doc = _baselines.write_next(goal_id, args.dataset, make)
    print(
        f"{_baselines.folder(goal_id, args.dataset) / (str(doc['version']) + '.json')}  version {doc['version']} of {line}: restores version {args.to}"
    )
    return 0
