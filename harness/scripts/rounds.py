"""Eval rounds (ADR-0004), optional: open, retire, close, and the status with suggestions.

    evh round-open   --goal G --dataset D [--from rN] [--hypothesis "..."] [--change "..."]...
                     [--keep cfg,...] [--retire cfg,... --reason "..."] [--budget-usd N] [--baseline cfg|run]
    evh round-carry  --goal G --round rN --arm cfg [--from rM]
    evh round-retire --goal G --round rN --arm cfg --reason "..."
    evh round-close  --goal G --round rN --conclusion "..." [--promote <run_id>]   (an operation: ops/rounds.py)
    evh round-show G rN

A round is a record beside the goal, data/rounds/<goal>/<round>.yaml: what it sets out to learn,
what changed, its arms, the baseline it starts from, its conclusion. It stores its arms: each a system, the label it is
read under, the runs it is read through, how it entered (ran in the round, with `--round rN` on `evh run`; or carried
in unchanged: --keep, round-carry) and its retirement. `evh round-list` reads the evidence the way the inspector does and
suggests the next decision, each as the command that makes it; the commands are the only writers. A project that
never opens a round loses nothing.
"""

from __future__ import annotations

import sys
from typing import Any

from evaluation_harness import _common, _rounds, _store
from evaluation_harness._actor import actor, require_named
from evaluation_harness._common import die, load_goals, now
from evaluation_harness.model import rounds as model_rounds
from evaluation_harness.model import runs as model_runs
from evaluation_harness.model.rounds import (  # noqa: F401  (rounds' evidence lives in the model)
    _against,
    _arm,
    _best,
    _dirs,
    _promote_hold,
    _silver_authors,
    evidence,
)
from evaluation_harness.ops import legacy


def _goal(goal: str) -> dict:
    goals = load_goals()
    if goal not in goals:
        die(
            f"no goal {goal!r}: one of {', '.join(sorted(goals)) or '(none: add data/goals/<id>.yaml)'}",
            "not-found",
        )
    return goals[goal]


def _round(goal: str, rid: str) -> dict:
    rnd = _rounds.find(goal, rid)
    if rnd is None:
        have = ", ".join(r["round_id"] for r in _rounds.load_rounds(goal)) or "none"
        die(f"no round {rid!r} for goal {goal!r} (it has: {have})", "not-found")
    return rnd


def _ids(spec: str | None) -> list[str]:
    return [t.strip() for t in (spec or "").split(",") if t.strip()]


def open_body(**inputs: Any) -> int:
    """evh round-open: start a round of a goal, optionally continuing one."""
    args = legacy.namespace(inputs, "round-open", {"from": "from_"})
    _goal(args.goal)
    if not _store.is_file(_common.DATASETS / f"{args.dataset}.json"):
        die(f"no dataset {args.dataset!r} (evh dataset-create first)", "not-found")
    if args.from_:
        _round(args.goal, args.from_)
    from evaluation_harness import rescore as rs  # noqa: PLC0415

    carried = _ids(args.keep)
    from_rnd = _round(args.goal, args.from_) if args.from_ else None
    if args.adopt:
        if args.from_ or _rounds.load_rounds(args.goal):
            die(
                f"--adopt records a goal's first round; {args.goal} has rounds already (use --from)",
                "bad-argument",
            )
        carried = sorted(
            {m["system_id"] for _d, m in rs.measured_runs(args.dataset) if m.get("goal") == args.goal}
        )
        if not carried:
            die(f"--adopt: no run on {args.dataset} names goal {args.goal}", "not-found")
    elif carried == ["all"]:
        if from_rnd is None:
            die("--keep all needs --from: the round whose arms are carried", "bad-argument")
        carried = _rounds.arms_of(from_rnd)
    if args.scoring and len(args.scoring.split()) < 3:
        die("--scoring needs a sentence: what changed in the scoring, and why?", "bad-argument")
    # A study's round (RFC-029) opens and closes with its study: it holds no other round back.
    open_ones = [
        r["round_id"]
        for r in _rounds.load_rounds(args.goal)
        if r.get("status") == "open" and not r.get("study")
    ]
    if open_ones:
        die(
            f'round {open_ones[0]} of {args.goal} is still open: close it first (evh round-close --goal {args.goal} --round {open_ones[0]} --conclusion "...")',
            "not-allowed",
        )
    if args.retire and len(args.reason.split()) < 3:
        die("--retire needs --reason, a sentence: why are these arms dropped?", "bad-argument")
    from evaluation_harness import _baselines  # noqa: PLC0415

    cur = _baselines.current(args.goal, args.dataset)  # the goal's own baseline on the dataset (RFC-027)
    start = cur.get("promoted_from") if cur else None
    if args.baseline:
        # Fleet feedback 22: a round opened with --keep carried its baseline arm in but recorded no baseline, and
        # `pair-test --round` then refused ("records no other baseline run").
        runs = rs.measured_runs(args.dataset)
        named = [m["run_id"] for _d, m in runs if m["run_id"] == args.baseline] or sorted(
            m["run_id"] for _d, m in runs if m.get("system_id") == args.baseline
        )
        if not named:
            die(
                f"--baseline {args.baseline}: no measured run of that system or with that run id on {args.dataset}",
                "not-found",
            )
        start = named[-1]
    rid = _rounds.next_id(args.goal)
    doc = {
        "round_id": rid,
        "goal": args.goal,
        "dataset_id": args.dataset,
        "from": args.from_,
        "hypothesis": args.hypothesis,
        "changes": args.change,
        "baseline": start,
        "budget_usd": args.budget_usd,
        "harness": _rounds.harness_now(),
        "arms": [],
        "status": "open",
        "opened_at": now(),
        "actor": actor(),
    }
    dropped = _ids(args.retire)
    _carry_in(doc, list(dict.fromkeys([*carried, *dropped])), from_rnd)
    for c in dropped:
        model_rounds.retire(doc, c, args.reason, actor())
    if args.scoring:
        _adopt_scoring(doc, args.scoring, rs)
    p = _rounds.save(doc)
    print(
        f"{p.relative_to(_common.ROOT) if p.is_relative_to(_common.ROOT) else p}: round {rid} of {args.goal}, open"
    )
    print(
        f"  It starts from {start}."
        if start
        else "  It starts from no baseline run (none promoted; --baseline names one)."
    )
    h = doc["harness"]
    print(
        f"  On harness {h['version']}"
        + (f" at {h['commit']}" if h.get("commit") and not h.get("installed") else "")
        + f" (code {str(h['code_sha256'])[:12]}): a run of the round on other harness code is named in evh round-evidence."
    )
    if carried:
        print(
            f"  Carried in as they are, their runs already count: {', '.join(carried)} "
            "(they need not run again)."
        )
    if dropped:
        print(f"  Dropped here: {', '.join(dropped)} ({args.reason})")
    print(
        f"  A NEW system joins it by running in it: evh run --system <id> --dataset {args.dataset} "
        f"--goal {args.goal} --round {rid}; then: evh round-evidence {args.goal} {rid}"
    )
    print("  Commit the round file before the runs: an uncommitted file makes them dirty.")
    return 0


def _carry_in(doc: dict, systems: list[str], frm: dict | None) -> None:
    """The systems carried into the round unchanged: an arm of the round they come from keeps its label and its runs
    there, when that round ran on the same dataset; any other system is read through its plain runs on the dataset
    (an earlier round's runs on another dataset are never read in this one)."""
    from evaluation_harness._runs import runs_on  # noqa: PLC0415

    same = frm is not None and frm.get("dataset_id") == doc["dataset_id"]
    for c in systems:
        src = model_rounds.find_arm(frm, c) if frm and same else None
        if frm is not None and src is not None:
            model_rounds.carry(
                doc, c, src.get("label") or "", list(src.get("runs") or []), frm["round_id"], actor()
            )
            continue
        runs = sorted(m["run_id"] for _d, m in runs_on(doc["dataset_id"], label="", system_id=c))
        if not runs:
            die(f"{c!r}: no run of it on {doc['dataset_id']} to carry in", "not-found")
        model_rounds.carry(doc, c, "", runs, None, actor())


def _adopt_scoring(doc: dict, why: str, rs) -> None:
    """The round is judged by the scorer in this tree (RFC-022): every carried arm whose runs another scorer judged
    is re-scored first ($0), so the round compares like with like; each one's deciding measure before and after is
    printed, and the round records the scorer and the change."""
    goal = _goal(doc["goal"])
    measure = ((goal.get("success_criteria") or {}).get("primary") or {}).get("measure", "")
    runs = rs.measured_runs(doc["dataset_id"], set(_rounds.arms_of(doc)))
    adapters: dict = {}
    todo: list = []
    now_by: dict[str, int] = {}
    for d, m in runs:
        cur = rs.current_scorer(m, adapters)
        was, read_from = rs.latest_scoring(d, m)
        now_by[cur] = now_by.get(cur, 0) + 1
        if cur and cur != was:
            todo.append((d, m, read_from))
    todo.sort(
        key=lambda t: (t[1]["run_id"], t[0].name)
    )  # rescore_runs returns in this order; zip below pairs them
    scorer = max(now_by, key=lambda k: now_by[k]) if now_by else ""
    doc["scorer"] = scorer
    doc["changes"] = [*doc.get("changes", []), f"scoring: {why}"]
    print(
        f"  scoring: judged by {scorer or '(no adapter found)'}; {len(todo)} of {len(runs)} carried run(s) re-scored"
    )
    done = rs.rescore_runs([(d, m) for d, m, _r in todo], quiet=True)
    for (_d, m, read_from), (_new_dir, new) in zip(todo, done):
        old = (model_runs.record(read_from) if read_from else None) or m
        before = (old.get("scores") or {}).get(measure)
        after = (new.get("scores") or {}).get(measure)
        fmt = lambda v: "—" if v is None else f"{v:.4g}"  # noqa: E731
        print(f"    {m['system_id']:52} {measure} {fmt(before)} -> {fmt(after)}  ({m['run_id']})")
    written = sorted({str(model_runs.meta(x).get("label") or "") for x, _ in done})
    _rounds.read_under_rescore(doc, done)
    doc["scoring"] = [{"at": now(), "scorer": scorer, "why": why, "written": written, "runs": len(done)}]


def carry_body(**inputs: Any) -> int:
    """evh round-carry: bring an arm of an earlier round (or a system already measured on the dataset) into the open
    round, unchanged."""
    args = legacy.namespace(inputs, "round-carry", {"from": "from_"})
    rnd = _round(args.goal, args.round)
    if rnd.get("status") == "closed":
        die(f"round {args.round} is closed", "not-allowed")
    who = require_named("round-carry")
    if args.arm in {a["system"] for a in model_rounds.in_play(rnd)}:
        die(f"{args.arm!r} is in play in {args.round} already", "not-allowed")
    earlier = [
        r
        for r in _rounds.load_rounds(args.goal)
        if _rounds._num(r["round_id"]) < _rounds._num(rnd["round_id"])
    ]
    if args.from_:
        src = _round(args.goal, args.from_)
        if src not in earlier:
            die(f"--from {args.from_}: not an earlier round than {args.round}", "bad-argument")
        frm = [src]
    else:
        frm = sorted(earlier, key=lambda r: -_rounds._num(r["round_id"]))
    found = next(
        (
            (r, a)
            for r in frm
            if r["dataset_id"] == rnd["dataset_id"] and (a := model_rounds.find_arm(r, args.arm))
        ),
        None,
    )
    if found is not None:
        src, arm = found
        model_rounds.carry(
            rnd, args.arm, arm.get("label") or "", list(arm.get("runs") or []), src["round_id"], who
        )
        _rounds.save(rnd)
        print(
            f"{args.arm} carried from {src['round_id']} into {args.round}: {len(arm.get('runs') or [])} run(s), "
            "unchanged"
        )
        return 0
    # A system measured outside the rounds on this dataset (or in a round on another one) is read through its plain
    # runs here, as round-open --keep reads it: the Workbench offers a measured system to carry in, never to run again.
    from evaluation_harness._runs import runs_on  # noqa: PLC0415

    ds = rnd["dataset_id"]
    runs = sorted(m["run_id"] for _d, m in runs_on(ds, label="", system_id=args.arm))
    if not runs:
        where = args.from_ or "an earlier round"
        have = ", ".join(sorted({a["system"] for r in frm for a in model_rounds.arms(r)})) or "no arms"
        die(
            f"{where} of {args.goal} has no arm {args.arm!r} on {ds} (it has: {have}), and {args.arm} has no run on "
            f"{ds} to carry in",
            "not-found",
        )
    model_rounds.carry(rnd, args.arm, "", runs, None, who)
    _rounds.save(rnd)
    print(f"{args.arm} carried into {args.round}: its {len(runs)} run(s) on {ds}, unchanged")
    return 0


def retire_body(**inputs: Any) -> int:
    """evh round-retire: drop an arm from a round, with the reason."""
    args = legacy.namespace(inputs, "round-retire")
    rnd = _round(args.goal, args.round)
    if rnd.get("status") == "closed":
        die(f"round {args.round} is closed", "not-allowed")
    if len(args.reason.split()) < 3:
        die("--reason must be a sentence: what did the tests show?", "bad-argument")
    gone = 0
    while model_rounds.retire(rnd, args.arm, args.reason, actor(), args.label) is not None:
        gone += 1  # every arm of the system in play (or the one under --label)
    if not gone:
        die(
            f"{args.arm!r}{'' if args.label is None else f' read under {args.label!r}'} is not in play in "
            f"{args.round}: {', '.join(_rounds.arms_of(rnd)) or '(no arms yet)'}",
            "not-found",
        )
    _rounds.save(rnd)
    print(f"{args.arm} retired from {args.round}: {args.reason}")
    return 0


def close_body(
    goal: str,
    round: str,
    conclusion: str,
    promote: str | None = None,
    confirm_extra_look: bool = False,
    override_no_evidence: bool = False,
) -> int:
    """evh round-close: record the round's conclusion, and promote the run it chose."""
    rnd = _round(goal, round)
    if rnd.get("status") == "closed":
        die(f"round {round} is already closed", "not-allowed")
    if rnd.get("study"):
        die(
            f"round {round} is study {rnd['study']}'s: it closes when the study ends (evh study-stop "
            f"{goal}/{rnd['study']})",
            "not-allowed",
        )
    if len(conclusion.split()) < 3:
        die("--conclusion must be a sentence: what did the round show?", "bad-argument")
    who = require_named("round-close")
    if promote:
        from evaluation_harness import promote_baseline  # noqa: PLC0415

        try:
            refused = promote_baseline.body(
                run=promote,
                reason=conclusion,
                goal=goal,
                round=round,
                confirm_extra_look=confirm_extra_look,
                override_no_evidence=override_no_evidence,
            )
        except SystemExit as exc:  # the promotion's own refusal, said as it said it
            print(exc.code, file=sys.stderr)
            refused = 1
        if refused:
            die("the round stays open: promotion was refused (above)", "not-allowed")
    rnd["status"] = "closed"
    rnd["closed_at"] = now()
    rnd["conclusion"] = {"text": conclusion, "promoted_run": promote, "actor": who}
    _rounds.save(rnd)
    print(f"round {round} of {goal} closed" + (f"; {promote} promoted" if promote else ""))
    return 0
