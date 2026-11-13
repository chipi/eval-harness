"""Eval rounds (ADR-0004), optional: open, retire, close, and the status with suggestions.

    evh round-open   --goal G --dataset D [--from rN] [--hypothesis "..."] [--change "..."]...
                     [--keep cfg,...] [--retire cfg,... --reason "..."] [--budget-usd N] [--baseline cfg|run]
    evh round-carry  --goal G --round rN --arm cfg [--from rM]
    evh round-retire --goal G --round rN --arm cfg --reason "..."
    evh round-close  --goal G --round rN --conclusion "..." [--promote <run_id>]
    evh rounds       --goal G [--round rN]

A round is a record beside the goal, data/rounds/<goal>/<round>.yaml: what it sets out to learn,
what changed, its arms, the baseline it starts from, its conclusion. It stores its arms: each a system, the label it is
read under, the runs it is read through, how it entered (ran in the round, with `--round rN` on `evh run`; or carried
in unchanged: --keep, round-carry) and its retirement. `evh rounds` reads the evidence the way the inspector does and
suggests the next decision, each as the command that makes it; the commands are the only writers. A project that
never opens a round loses nothing.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import subprocess
import sys
import textwrap
from pathlib import Path

from evaluation_harness import _common, _jsonout, _rounds, _store
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
from evaluation_harness.stats import fmt_p

HERE = Path(__file__).resolve().parent


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


def open_round(argv: list[str]) -> int:
    """evh round-open: start a round of a goal, optionally continuing one."""
    ap = argparse.ArgumentParser(prog="evh round-open", description="Open a round of a goal.")
    ap.add_argument("--goal", required=True)
    ap.add_argument("--dataset", required=True, help="the dataset its arms run on")
    ap.add_argument("--from", dest="from_", help="the round it continues (closed first)")
    ap.add_argument("--hypothesis", default="", help="what this round sets out to learn")
    ap.add_argument("--change", action="append", default=[], help="what changed and why (repeatable)")
    ap.add_argument(
        "--keep",
        help="system ids already run (in an earlier round or in none) carried in unchanged, not run again; "
        "`all`: every arm of --from",
    )
    ap.add_argument(
        "--adopt",
        action="store_true",
        help="the goal's first round, from arms already run on the dataset before any round was opened",
    )
    ap.add_argument(
        "--scoring",
        default="",
        help="this round is judged by the scorer in this tree, and why (RFC-022): carried arms another scorer "
        "judged are re-scored first ($0)",
    )
    ap.add_argument("--retire", help="system ids from earlier rounds dropped here")
    ap.add_argument("--reason", default="", help="why the --retire arms are dropped")
    ap.add_argument("--budget-usd", type=float, help="what the round may spend")
    ap.add_argument(
        "--baseline",
        help="the run the round starts from, by its system id (its latest measured run on --dataset) or its run id; "
        "default: the dataset's promoted baseline. What `pair-test --round` and `rounds` read the round's arms against",
    )
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args(argv)
    with _jsonout.collect("round-open", args.json, live=sys.stderr):
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
                {m["config_id"] for _d, m in rs.measured_runs(args.dataset) if m.get("goal") == args.goal}
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
                m["run_id"] for _d, m in runs if m.get("config_id") == args.baseline
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
            + f" (code {str(h['code_sha256'])[:12]}): a run of the round on other harness code is named in evh rounds."
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
            f"--goal {args.goal} --round {rid}; then: evh rounds --goal {args.goal}"
        )
        print("  Commit the round file before the runs: an uncommitted file makes them dirty.")
        return 0


def _carry_in(doc: dict, systems: list[str], frm: dict | None) -> None:
    """The systems carried into the round unchanged: an arm of the round they come from keeps its label and its runs
    there; a system in none is read through its plain runs on the dataset."""
    from evaluation_harness._runs import runs_on  # noqa: PLC0415

    for c in systems:
        src = model_rounds.find_arm(frm, c) if frm else None
        if frm is not None and src is not None:
            model_rounds.carry(
                doc, c, src.get("label") or "", list(src.get("runs") or []), frm["round_id"], actor()
            )
            continue
        runs = sorted(m["run_id"] for _d, m in runs_on(doc["dataset_id"], label="", config_id=c))
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
        print(f"    {m['config_id']:52} {measure} {fmt(before)} -> {fmt(after)}  ({m['run_id']})")
    written = sorted({str(model_runs.meta(x).get("label") or "") for x, _ in done})
    _rounds.read_under_rescore(doc, done)
    doc["scoring"] = [{"at": now(), "scorer": scorer, "why": why, "written": written, "runs": len(done)}]


def carry(argv: list[str]) -> int:
    """evh round-carry: bring an arm of an earlier round into the open round, unchanged."""
    ap = argparse.ArgumentParser(
        prog="evh round-carry",
        description="Carry an arm of an earlier round of the goal into the open round: its system, the label it is "
        "read under and its runs, unchanged; nothing is run again.",
    )
    ap.add_argument("--goal", required=True)
    ap.add_argument("--round", required=True, help="the open round it joins")
    ap.add_argument("--arm", required=True, help="its system id")
    ap.add_argument(
        "--from", dest="from_", help="the earlier round it comes from (default: the latest round that has it)"
    )
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args(argv)
    with _jsonout.collect("round-carry", args.json, live=sys.stderr):
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
        found = next(((r, a) for r in frm if (a := model_rounds.find_arm(r, args.arm))), None)
        if found is None:
            where = args.from_ or "an earlier round"
            have = ", ".join(sorted({a["system"] for r in frm for a in model_rounds.arms(r)})) or "no arms"
            die(f"{where} of {args.goal} has no arm {args.arm!r} (it has: {have})", "not-found")
        src, arm = found
        if src["dataset_id"] != rnd["dataset_id"]:
            die(
                f"{src['round_id']} ran on {src['dataset_id']!r}, {args.round} on {rnd['dataset_id']!r}: "
                "an arm is carried between rounds of one dataset",
                "mismatch",
            )
        model_rounds.carry(
            rnd, args.arm, arm.get("label") or "", list(arm.get("runs") or []), src["round_id"], who
        )
        _rounds.save(rnd)
        print(
            f"{args.arm} carried from {src['round_id']} into {args.round}: {len(arm.get('runs') or [])} run(s), unchanged"
        )
        return 0


def retire(argv: list[str]) -> int:
    """evh round-retire: drop an arm from a round, with the reason."""
    ap = argparse.ArgumentParser(
        prog="evh round-retire",
        description="Drop an arm from a round, with the reason. An arm is retired whole (its system, its label and all "
        "its runs); a run of it made afterwards brings it back.",
    )
    ap.add_argument("--goal", required=True)
    ap.add_argument("--round", required=True)
    ap.add_argument("--arm", required=True, help="its system id")
    ap.add_argument(
        "--label",
        help='only the arm read under this label (a re-timing\'s "linux", say; "" the plain runs); default: every '
        "arm of the system in play",
    )
    ap.add_argument("--reason", required=True)
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args(argv)
    with _jsonout.collect("round-retire", args.json, live=sys.stderr):
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


def close(argv: list[str]) -> int:
    """evh round-close: record the round's conclusion, and promote the run it chose."""
    ap = argparse.ArgumentParser(prog="evh round-close", description="Close a round with its conclusion.")
    ap.add_argument("--goal", required=True)
    ap.add_argument("--round", required=True)
    ap.add_argument("--conclusion", required=True, help="what the round showed, and what it decided")
    ap.add_argument(
        "--promote",
        metavar="RUN_ID",
        help="promote this run to the goal's baseline on the round's dataset, the conclusion as its reason",
    )
    ap.add_argument(
        "--confirm-extra-look",
        action="store_true",
        help="--promote on a test set past its limit of looks (RFC-029): the person's consent (passed to run-promote)",
    )
    ap.add_argument(
        "--override-no-evidence",
        action="store_true",
        help="--promote on a test set whose items cannot show it: promote anyway, inconclusive (passed to run-promote)",
    )
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args(argv)
    with _jsonout.collect("round-close", args.json, live=sys.stderr):
        rnd = _round(args.goal, args.round)
        if rnd.get("status") == "closed":
            die(f"round {args.round} is already closed", "not-allowed")
        if rnd.get("study"):
            die(
                f"round {args.round} is study {rnd['study']}'s: it closes when the study ends (evh study-stop "
                f"{args.goal}/{rnd['study']})",
                "not-allowed",
            )
        if len(args.conclusion.split()) < 3:
            die("--conclusion must be a sentence: what did the round show?", "bad-argument")
        who = require_named("round-close")
        if args.promote:
            r = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "promote_baseline.py"),
                    "--run",
                    args.promote,
                    "--reason",
                    args.conclusion,
                    "--goal",
                    args.goal,
                    "--round",
                    args.round,
                    *(["--confirm-extra-look"] if args.confirm_extra_look else []),
                    *(["--override-no-evidence"] if args.override_no_evidence else []),
                ],
                capture_output=True,
                text=True,
            )
            sys.stdout.write(r.stdout)
            if r.returncode:
                sys.stderr.write(r.stderr)
                die("the round stays open: promotion was refused (above)", "not-allowed")
        rnd["status"] = "closed"
        rnd["closed_at"] = now()
        rnd["conclusion"] = {"text": args.conclusion, "promoted_run": args.promote, "actor": who}
        _rounds.save(rnd)
        print(
            f"round {args.round} of {args.goal} closed"
            + (f"; {args.promote} promoted" if args.promote else "")
        )
        return 0


def status(argv: list[str]) -> int:
    """evh rounds: every round of a goal, the open one with its evidence and suggestions."""
    ap = argparse.ArgumentParser(
        prog="evh rounds", description="A goal's rounds, and what the evidence suggests."
    )
    ap.add_argument("--goal", required=True)
    ap.add_argument("--round", help="one round in full (default: the open one, else the last)")
    ap.add_argument(
        "--json",
        action="store_true",
        help="the same answer as one JSON object: the printed lines as blocks, the tables as data, and "
        "the shown round, its evidence and suggestions under result.values",
    )
    args = ap.parse_args(argv)
    with _jsonout.collect("rounds", args.json):
        return _status(args)


def _status(args: argparse.Namespace) -> int:
    _goal(args.goal)
    rounds = _rounds.load_rounds(args.goal)
    if not rounds:
        print(
            f"{args.goal} has no rounds (they are optional). Open one: evh round-open --goal {args.goal} --dataset <dataset>"
        )
        _jsonout.values({"goal": args.goal, "rounds": []})
        return 0
    rows = [_rounds.summary(r) for r in rounds]
    if not _jsonout.table(list(rows[0]), [list(r.values()) for r in rows]):
        for r, row in zip(rounds, rows):
            c = row["conclusion"]
            print(
                f"  {r['round_id']:4} {r['status']:7} {row['dataset_id']}  {row['arms']} arm(s), {row['retired']} retired"
            )
            if c:
                print(textwrap.fill(c, 96, initial_indent="       ", subsequent_indent="       "))
    rnd = (
        _round(args.goal, args.round)
        if args.round
        else next((r for r in rounds if r["status"] == "open"), rounds[-1])
    )
    print(
        f"\n{rnd['round_id']} · {rnd['status']} · {rnd['dataset_id']}"
        + (f" · from {rnd['from']}" if rnd.get("from") else "")
    )
    for k in ("hypothesis",):
        if rnd.get(k):
            print(textwrap.fill(rnd[k], 96, initial_indent="  hypothesis: ", subsequent_indent="    "))
    for ch in rnd.get("changes") or []:
        print(textwrap.fill(str(ch), 100, initial_indent="  changed: ", subsequent_indent="           "))
    for a in model_rounds.arms(rnd):
        if a.get("retired"):
            print(f"  retired: {a['system']} ({a['retired']['reason']})")
    if rnd.get("harness"):
        h = rnd["harness"]
        print(
            f"  harness: {h.get('version')}"
            + (f" at {h['commit']}" if h.get("commit") and not h.get("installed") else "")
            + f" (code {str(h.get('code_sha256'))[:12]})"
        )
    if rnd.get("scorer"):
        print(f"  judged by: {rnd['scorer']}")
    for sc in rnd.get("scoring") or []:
        print(
            f"  scoring {str(sc.get('at', ''))[:10]}: {sc.get('why', '')} "
            f"({sc.get('scorer', '')}, {sc.get('runs', 0)} run(s) re-scored into {', '.join(sc.get('written') or []) or '—'})"
        )
    ev = evidence(args.goal, rnd)
    print(
        f"\n  on {ev['metric']}: {len(ev['arms'])} arm(s) in play"
        + (f", leader {ev['leader'].rsplit('/', 1)[-1]}" if ev.get("leader") else "")
    )
    if not _jsonout.table(
        ["arm", "verdict", "delta", "p"], [[r["arm"], r["verdict"], r["delta"], r["p"]] for r in ev["rows"]]
    ):
        for r in ev["rows"]:
            print(
                f"    {r['arm'].rsplit('/', 1)[-1]:32} {r['verdict']:18} Δ {r['delta']:+.4f}  p {fmt_p(r['p'])}"
            )
    if not _jsonout.table(
        ["label", "other", "verdict", "delta", "p"],
        [[v["label"], v["other"], v["verdict"], v["delta"], v["p"]] for v in ev["against"]],
    ):
        for v in ev["against"]:
            print(
                f"  against {v['label']} ({v['other'].rsplit('/', 1)[-1]}): {v['verdict']}, Δ {v['delta']:+.4f}, p {fmt_p(v['p'])}"
            )
    _jsonout.values(
        {"goal": args.goal, "rounds": rows, "round": _rounds.view(rnd)} | _rounds.evidence_values(rnd, ev)
    )
    for n in ev["notes"]:
        print(f"  NOTE: {n}")
    if rnd["status"] == "open" and ev["suggest"]:
        print("\n  suggested next:")
        for what, cmd in ev["suggest"]:
            print(f"    - {what}" + (f"\n        {cmd}" if cmd else ""))
    if rnd["status"] == "closed":
        text = str((rnd.get("conclusion") or {}).get("text", ""))
        print(
            "\n" + textwrap.fill(text, 100, initial_indent="  concluded: ", subsequent_indent="             ")
        )
    return 0


ACTIONS = {"open": open_round, "carry": carry, "retire": retire, "close": close, "status": status}


def run(action: str) -> int:
    """Entry point for the per-action scripts (`evh round-open` ... `evh rounds`)."""
    return ACTIONS[action](sys.argv[1:])
