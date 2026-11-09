#!/usr/bin/env python3
"""Roll a baseline back to an earlier version, as a new version (RFC-027 D2).

    evh baseline-rollback --goal triage_orrery --dataset orrery_v1 --to 2 --reason "v3's arm leaks the gold" --by ana

Writes the next version restoring version N: its run and what it carried, `restores: N`, and its own evidence (N's arm
against what is current now). Nothing is deleted or edited: the version rolled back from stays in the history. A
decision, so it needs a named actor.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import sys

from evaluation_harness import _baselines, _jsonout, _store
from evaluation_harness._common import RUNS, die, evh_prog, load_goals, now, read_json


def main() -> int:
    """Roll a baseline back."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--goal", help="the goal whose baseline it is")
    ap.add_argument("--no-goal", action="store_true", help="the dataset's own baseline (a run with no goal)")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--to", type=int, required=True, help="the version to restore")
    ap.add_argument("--reason", required=True, help="why: a sentence")
    from evaluation_harness._actor import add_by, require_named  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("baseline-rollback", args.json, live=sys.stderr):
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
        src = RUNS / str(target.get("promoted_from")) / "metrics.json"
        if not _store.is_file(src):
            die(
                f"version {args.to}'s run {target.get('promoted_from')} is gone: nothing to restore",
                "not-found",
            )
        m = read_json(src)
        goal = load_goals().get(goal_id) if goal_id else None
        from evaluation_harness.promote_baseline import evidence  # noqa: PLC0415

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


if __name__ == "__main__":
    raise SystemExit(main())
