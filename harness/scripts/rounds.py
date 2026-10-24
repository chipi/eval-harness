"""Experiment rounds (ADR-0004), optional: open, retire, close, and the status with suggestions.

    evh round-open   --goal G --dataset D [--from rN] [--hypothesis "..."] [--change "..."]...
                     [--keep cfg,...] [--retire cfg,... --reason "..."] [--budget-usd N]
    evh round-retire --goal G --round rN --arm cfg --reason "..."
    evh round-close  --goal G --round rN --conclusion "..." [--promote <run_id>]
    evh rounds       --goal G [--round rN]

A round is a record beside the goal, data/rounds/<goal>/<round>.yaml: what it sets out to learn,
what changed, the arms it drops and why, the baseline it starts from, its conclusion. Its arms are
the configs whose runs name it (`round: rN` in the config) and those carried in unchanged
(--keep). `evh rounds` reads the evidence the way the inspector does and suggests the next
decision, each as the command that makes it; the commands are the only writers. A project that
never opens a round loses nothing.
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import _common
import _rounds
import catalog_serve as cs
from _common import die, load_goals, now, read_json
from catalog_adapter import HarnessAdapter

HERE = Path(__file__).resolve().parent


def _goal(goal: str) -> dict:
    goals = load_goals()
    if goal not in goals:
        die(f"no goal {goal!r}: one of {', '.join(sorted(goals)) or '(none: add data/goals/<id>.yaml)'}")
    return goals[goal]


def _round(goal: str, rid: str) -> dict:
    rnd = _rounds.find(goal, rid)
    if rnd is None:
        have = ", ".join(r["round_id"] for r in _rounds.load_rounds(goal)) or "none"
        die(f"no round {rid!r} for goal {goal!r} (it has: {have})")
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
    ap.add_argument("--keep", help="config ids from earlier rounds carried in unchanged, not run again")
    ap.add_argument("--retire", help="config ids from earlier rounds dropped here")
    ap.add_argument("--reason", default="", help="why the --retire arms are dropped")
    ap.add_argument("--budget-usd", type=float, help="what the round may spend")
    args = ap.parse_args(argv)
    _goal(args.goal)
    if not (_common.DATASETS / f"{args.dataset}.json").is_file():
        die(f"no dataset {args.dataset!r} (evh dataset-create first)")
    open_ones = [r["round_id"] for r in _rounds.load_rounds(args.goal) if r.get("status") == "open"]
    if open_ones:
        die(
            f'round {open_ones[0]} of {args.goal} is still open: close it first (evh round-close --goal {args.goal} --round {open_ones[0]} --conclusion "...")'
        )
    if args.from_:
        _round(args.goal, args.from_)
    if args.retire and len(args.reason.split()) < 3:
        die("--retire needs --reason, a sentence: why are these arms dropped?")
    base = _common.BASELINES / f"{args.dataset}_baseline.json"
    rid = _rounds.next_id(args.goal)
    doc = {
        "round_id": rid,
        "goal": args.goal,
        "dataset_id": args.dataset,
        "from": args.from_,
        "hypothesis": args.hypothesis,
        "changes": args.change,
        "baseline": read_json(base).get("promoted_from") if base.is_file() else None,
        "budget_usd": args.budget_usd,
        "carried": _ids(args.keep),
        "status": "open",
        "opened_at": now(),
        "retired": [{"config_id": c, "reason": args.reason, "at": now()} for c in _ids(args.retire)],
    }
    p = _rounds.save(doc)
    print(
        f"{p.relative_to(_common.ROOT) if p.is_relative_to(_common.ROOT) else p}: round {rid} of {args.goal}, open"
    )
    print(
        f"  Name it in each arm's config (round: {rid}, beside goal: {args.goal}), run them, then: evh rounds --goal {args.goal}"
    )
    print("  Commit the round file before the runs: an uncommitted file makes them dirty.")
    return 0


def retire(argv: list[str]) -> int:
    """evh round-retire: drop an arm from a round, with the reason."""
    ap = argparse.ArgumentParser(prog="evh round-retire", description="Drop an arm from a round.")
    ap.add_argument("--goal", required=True)
    ap.add_argument("--round", required=True)
    ap.add_argument("--arm", required=True, help="its config id")
    ap.add_argument("--reason", required=True)
    args = ap.parse_args(argv)
    rnd = _round(args.goal, args.round)
    if rnd.get("status") == "closed":
        die(f"round {args.round} is closed")
    if len(args.reason.split()) < 3:
        die("--reason must be a sentence: what did the tests show?")
    if args.arm not in _rounds.arms_of(rnd):
        die(
            f"{args.arm!r} is not in play in {args.round}: {', '.join(_rounds.arms_of(rnd)) or '(no arms yet)'}"
        )
    rnd.setdefault("retired", []).append({"config_id": args.arm, "reason": args.reason, "at": now()})
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
        help="promote this run to the dataset's baseline, the conclusion as its reason",
    )
    args = ap.parse_args(argv)
    rnd = _round(args.goal, args.round)
    if rnd.get("status") == "closed":
        die(f"round {args.round} is already closed")
    if len(args.conclusion.split()) < 3:
        die("--conclusion must be a sentence: what did the round show?")
    if args.promote:
        r = subprocess.run(
            [
                sys.executable,
                str(HERE / "promote_baseline.py"),
                "--run",
                args.promote,
                "--reason",
                args.conclusion,
            ],
            capture_output=True,
            text=True,
        )
        sys.stdout.write(r.stdout)
        if r.returncode:
            sys.stderr.write(r.stderr)
            die("the round stays open: promotion was refused (above)")
    rnd["status"] = "closed"
    rnd["closed_at"] = now()
    rnd["conclusion"] = {"text": args.conclusion, "promoted_run": args.promote}
    _rounds.save(rnd)
    print(
        f"round {args.round} of {args.goal} closed" + (f"; {args.promote} promoted" if args.promote else "")
    )
    return 0


def _best(A, arms: list[str], metric: str, lower: bool) -> str | None:
    means = {}
    for a in arms:
        vals = (A.scores(a).get(metric) or {}).get("values") or {}
        if vals:
            means[a] = statistics.fmean(vals.values())
    if not means:
        return None
    return (min if lower else max)(means, key=lambda a: means[a])


def evidence(goal: str, rnd: dict) -> dict:
    """What the evidence says about a round, read as the inspector reads it: its arms against its
    leader, its leader against the previous round's best and the baseline it started from, its
    spend, and the decisions that follow, each with its command."""
    g = _goal(goal)
    prim = (g.get("success_criteria") or {}).get("primary") or {}
    metric, lower = prim.get("measure", ""), prim.get("direction") == "lower"
    A = HarnessAdapter()
    cs.set_adapter(A)
    ds = rnd["dataset_id"]
    arm = {c: f"runs/{ds}/{c}" for c in _rounds.arms_of(rnd)}
    known = set(A.arms())
    arms = [a for a in arm.values() if a in known]
    out: dict[str, Any] = {"metric": metric, "arms": arms, "rows": [], "suggest": [], "notes": []}
    spent = sum((m.get("scores") or {}).get("total_cost_usd") or 0 for _, m in _rounds.runs_of(rnd))
    out["spent"] = spent
    if rnd.get("budget_usd") is not None:
        line = f"spent ${spent:.4f} of ${rnd['budget_usd']:.2f}"
        out["notes"].append(line + (" — over budget" if spent > rnd["budget_usd"] else ""))
    leader = _best(A, arms, metric, lower)
    out["leader"] = leader
    if not leader:
        out["notes"].append(
            f"no arm in {rnd['round_id']} records {metric} yet: run them (config: round: {rnd['round_id']})"
        )
        return out
    if len(arms) > 1:
        d = cs.compare({"runs": [",".join(arms)], "baseline": [leader], "metric": [metric]})
        out["rows"] = d.get("rows") or []
        out["notes"] += list((d.get("conditions") or {}).get("warnings") or [])
        for r in out["rows"]:
            cid = r["arm"].rsplit("/", 1)[-1]
            if r["verdict"] == "separated: worse":
                reason = f"separated worse than {leader.rsplit('/', 1)[-1]} on {metric} after Holm (p {r['p']:.3g})"
                out["suggest"].append(
                    (
                        f"retire {cid}",
                        f'evh round-retire --goal {goal} --round {rnd["round_id"]} --arm {cid} --reason "{reason}"',
                    )
                )
        ties = [r["arm"].rsplit("/", 1)[-1] for r in out["rows"] if r["verdict"] == "not separated"]
        if ties:
            out["suggest"].append(
                (
                    f"{len(ties)} arm(s) tie with the leader ({', '.join(ties)}): more items would separate them",
                    f"evh rank-stability --dataset-id {ds}",
                )
            )
    prev = _rounds.find(goal, rnd["from"]) if rnd.get("from") else None
    if prev:
        pbest = _best(A, [f"runs/{prev['dataset_id']}/{c}" for c in _rounds.arms_of(prev)], metric, lower)
        if pbest and pbest != leader and prev["dataset_id"] == ds:
            d = cs.compare({"runs": [f"{pbest},{leader}"], "baseline": [pbest], "metric": [metric]})
            row = next(iter(d.get("rows") or []), None)
            if row:
                out["vs_previous"] = {
                    "previous": pbest,
                    "verdict": row["verdict"],
                    "p": row["p"],
                    "delta": row["delta"],
                }
                if row["verdict"] != "separated: better":
                    out["suggest"].append(
                        (
                            f"{rnd['round_id']}'s best is not separated from {prev['round_id']}'s ({pbest.rsplit('/', 1)[-1]}): change course, or close",
                            "",
                        )
                    )
    base_run = rnd.get("baseline")
    if base_run:
        barm = next(
            (a for a in known if a.startswith(f"runs/{ds}/") and any(d.name == base_run for d in A._dirs(a))),
            None,
        )
        if barm and barm != leader:
            d = cs.compare({"runs": [f"{barm},{leader}"], "baseline": [barm], "metric": [metric]})
            row = next(iter(d.get("rows") or []), None)
            if row:
                out["vs_baseline"] = {
                    "baseline": barm,
                    "verdict": row["verdict"],
                    "p": row["p"],
                    "delta": row["delta"],
                }
    lead_run = sorted(d.name for d in A._dirs(leader))[0] if A._dirs(leader) else "<run_id>"
    out["suggest"].append(
        (
            "close the round with what it showed",
            f'evh round-close --goal {goal} --round {rnd["round_id"]} --conclusion "..." --promote {lead_run}',
        )
    )
    return out


def status(argv: list[str]) -> int:
    """evh rounds: every round of a goal, the open one with its evidence and suggestions."""
    ap = argparse.ArgumentParser(
        prog="evh rounds", description="A goal's rounds, and what the evidence suggests."
    )
    ap.add_argument("--goal", required=True)
    ap.add_argument("--round", help="one round in full (default: the open one, else the last)")
    args = ap.parse_args(argv)
    _goal(args.goal)
    rounds = _rounds.load_rounds(args.goal)
    if not rounds:
        print(
            f"{args.goal} has no rounds (they are optional). Open one: evh round-open --goal {args.goal} --dataset <dataset>"
        )
        return 0
    for r in rounds:
        c = (r.get("conclusion") or {}).get("text", "")
        print(
            f"  {r['round_id']:4} {r['status']:7} {r.get('dataset_id', '')}  {len(_rounds.arms_of(r))} arm(s), {len(r.get('retired') or [])} retired  {c[:70]}"
        )
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
        print(f"  changed: {ch}")
    for x in rnd.get("retired") or []:
        print(f"  retired: {x['config_id']} ({x['reason']})")
    ev = evidence(args.goal, rnd)
    print(
        f"\n  on {ev['metric']}: {len(ev['arms'])} arm(s) in play"
        + (f", leader {ev['leader'].rsplit('/', 1)[-1]}" if ev.get("leader") else "")
    )
    for r in ev["rows"]:
        print(f"    {r['arm'].rsplit('/', 1)[-1]:32} {r['verdict']:18} Δ {r['delta']:+.4f}  p {r['p']:.3g}")
    for key, label in (
        ("vs_previous", "previous round's best"),
        ("vs_baseline", "the baseline it started from"),
    ):
        v = ev.get(key)
        if v:
            other = v.get("previous") or v.get("baseline")
            print(
                f"  against {label} ({other.rsplit('/', 1)[-1]}): {v['verdict']}, Δ {v['delta']:+.4f}, p {v['p']:.3g}"
            )
    for n in ev["notes"]:
        print(f"  NOTE: {n}")
    if rnd["status"] == "open" and ev["suggest"]:
        print("\n  suggested next:")
        for what, cmd in ev["suggest"]:
            print(f"    - {what}" + (f"\n        {cmd}" if cmd else ""))
    if rnd["status"] == "closed":
        print(f"\n  concluded: {(rnd.get('conclusion') or {}).get('text', '')}")
    return 0


ACTIONS = {"open": open_round, "retire": retire, "close": close, "status": status}


def run(action: str) -> int:
    """Entry point for the per-action scripts (`evh round-open` ... `evh rounds`)."""
    return ACTIONS[action](sys.argv[1:])
