"""Promote a run to a baseline.

A baseline belongs to a goal on a dataset (or, for a run with no goal, to the dataset alone), in
versions written once (RFC-027): promoting writes the next version beside the current one, with
the comparison that justified it (the paired test against the version it replaces) frozen in.
It is the number future work is judged against, so promoting one is a decision, not a copy.

Two things are refused, because both produce a baseline nobody can act on:

  * a run whose build is unknown or dirty — you cannot later say WHICH code
    earned the number
  * a promotion with no reason — six months on, "why is this the baseline?"
    has no answer, and the number gets cargo-culted

    evh run-promote --run <run_id> --reason "beat prev by 4% on n=40"
    evh run-promote --run <run_id> --reason "..." --goal G      # another of the dataset's goals
    evh run-promote --run <run_id> --reason "..." --no-goal     # the dataset's own baselines
"""

from __future__ import annotations

import argparse
from typing import Any

from evaluation_harness import _baselines, _common, _jsonout, _store
from evaluation_harness._common import (
    BOOKKEEPING_PREFIXES,
    RUNS,
    die,
    how,
    load_goals,
    now,
)
from evaluation_harness.model import runs as model_runs


def run_record(run_id: str) -> dict | None:
    """The record of a run's measurement (its first score's: what a baseline is promoted from), None when the run
    is not there or was never scored."""
    d = RUNS / run_id
    if not _store.is_file(d / model_runs.RUN):
        return None
    sd = model_runs.first_score(d) or next(iter(model_runs.scores_of(d)), None)
    return model_runs.record(sd) if sd else None


def _repeats(m: dict) -> dict | None:
    """The repeat set of the promoted run's arm (`model.runs.set_of`: the runs `--repeat` made and the repeats joined to
    the run they repeat): their run ids and the mean of each score over them; None for a run that is not in one."""
    import statistics  # noqa: PLC0415

    d = RUNS / m["run_id"]
    mine = model_runs.first_score(d) or next(iter(model_runs.scores_of(d)), None)
    if mine is None:
        return None
    arm = model_runs.arm_of(mine, m)
    members = model_runs.set_of(
        [
            (sd, rec)
            for sd, rec in model_runs.scored(m["dataset_id"], system_id=m["system_id"], label_is=None)
            if model_runs.arm_of(sd, rec) == arm
        ]
    )
    if m["run_id"] not in {rec["run_id"] for _sd, rec in members}:
        return None
    sibs = []
    for run_id in sorted({rec["run_id"] for _sd, rec in members}):
        mm = run_record(run_id) or {}
        if mm.get("system_id") == m["system_id"]:
            sibs.append(mm)
    if len(sibs) < 2:
        return None
    keys = set.intersection(*(set(x.get("scores") or {}) for x in sibs))
    return {
        "runs": [x["run_id"] for x in sibs],
        "mean_scores": {k: statistics.fmean(x["scores"][k] for x in sibs) for k in sorted(keys)},
    }


def carried(m: dict) -> dict:
    """What a baseline keeps of its run beyond the scores: the reference tier, the adapter
    that scored it, its fingerprint's hash, and the goal and format it answers. V6 checks
    they still match the run."""
    tier = m.get("reference_tier") or ((m.get("derived") or {}).get("with") or {}).get(
        "source_reference_tier"
    )
    out = {
        "reference_tier": tier,
        "adapter": m.get("adapter"),
        "fingerprint_hash": (m.get("fingerprint") or {}).get("hash"),
        "goal": m.get("goal"),
        "format": m.get("format"),
    }
    return {k: v for k, v in out.items() if v}


def _config_of(run_id: str) -> str | None:
    return (run_record(run_id) or {}).get("system_id")


def evidence(
    m: dict, cur: dict | None, goal: dict | None, round_id: str | None, look: dict | None = None
) -> dict[str, Any]:
    """The comparison that justifies the promotion (RFC-027 D3), as `pair-test` answers it: the promoted run's arm
    against the current version's, on the goal's primary measure (else the run's), with the goal's cluster and
    reducer, pooled as pair-test pools them; with a round, as `pair-test --round` reads it. Frozen: never recomputed."""
    if cur is None:
        return {"compared_to": None}
    out: dict[str, Any] = {"compared_to": cur["version"]}
    if round_id:
        out["round"] = round_id
    a, b = m["system_id"], _config_of(cur["promoted_from"])
    prim = ((goal or {}).get("success_criteria") or {}).get("primary") or {}
    measure = prim.get("measure") or m.get("primary_metric")
    out["measure"] = measure
    if b is None:
        out |= {"verdict": None, "not_comparable": ["the current version's run is gone"]}
        return out
    if a == b:
        out |= {"verdict": None, "not_comparable": ["the same arm (another run of it)"]}
        return out
    inputs: dict[str, Any] = {"a": a, "b": b}
    if measure:
        inputs["metric"] = measure
    if goal:
        cl = _common.goal_cluster(goal, m["dataset_id"])
        if cl:
            inputs["cluster"] = cl
        if isinstance(prim, dict) and prim.get("reduce"):
            inputs["reduce"] = str(prim["reduce"])
        if prim.get("direction") in ("lower", "higher"):
            inputs["asc" if prim["direction"] == "lower" else "desc"] = True
        if round_id:
            inputs |= {"round": round_id, "goal": goal["goal_id"]}
    if look is not None:  # a look at a test set (RFC-029): one-sided at its level
        inputs["look_level"] = float(look["level"])
    from evaluation_harness import ops  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    try:
        v = (ops.OPS["pair-test"].call(dataset=m["dataset_id"], **inputs).get("values")) or {}
    except Problem as exc:
        why = (f"ERROR ({exc.kind}): {exc}".splitlines() or ["pair-test refused"])[-1]
        out |= {"verdict": None, "not_comparable": [why]}
        return out
    if look is not None:
        lv = v.get("look") or {}
        if not lv.get("can_reach") and not look.get("override"):
            die(
                f"{m['dataset_id']} is a test set: this promotion is look {look['number']}, tested one-sided at "
                f"{look['level']:.4%}, and these {v.get('n')} items reach p {lv.get('attainable_p')} at best: it could "
                "never be shown. Fresh items are the way out; --override-no-evidence (the person) promotes it labelled "
                "inconclusive",
                "not-enough",
            )
        out["look"] = {k: x for k, x in look.items() if k not in ("reused", "override")}
        out["look"]["verdict"] = lv.get("verdict") if lv.get("can_reach") else "INCONCLUSIVE"
        out["look"]["p_one_sided"] = lv.get("p_one_sided")
        out["look"]["attainable_p"] = lv.get("attainable_p")
    out |= {
        "n": v.get("n"),
        "items_sha256": v.get("items_sha256"),
        "verdict": {
            "outcome": v.get("verdict"),
            "delta": v.get("delta"),
            "p": v.get("p"),
            "method": v.get("method"),
            "direction": v.get("direction"),
        },
        "computed_with": {
            "harness": _version(),
            "runs_a": v.get("run_ids_a"),
            "runs_b": v.get("run_ids_b"),
            "reduce": v.get("reduce"),
            "cluster": v.get("cluster"),
            "permutations": v.get("permutations"),
            "seed": v.get("seed"),
        },
    }
    return out


def _version() -> str:
    from evaluation_harness._version import __version__  # noqa: PLC0415

    return __version__


def body(
    run: str,
    reason: str | None = None,
    goal: str | None = None,
    no_goal: bool = False,
    round: str | None = None,
    allow_dirty: bool = False,
    confirm_extra_look: bool = False,
    override_no_evidence: bool = False,
    allow_unknown_build: bool = False,
    unfaithful: bool = False,
) -> int:
    """Promote a run to baseline status: print what was written, answer the exit code. A refusal is `die`."""
    args = argparse.Namespace(
        run=run,
        reason=reason,
        goal=goal,
        no_goal=no_goal,
        round=round,
        allow_dirty=allow_dirty,
        confirm_extra_look=confirm_extra_look,
        override_no_evidence=override_no_evidence,
        allow_unknown_build=allow_unknown_build,
        unfaithful=unfaithful,
    )
    if not (args.reason or "").strip():
        die('a reason is required: --reason "..."', "bad-argument")
    from evaluation_harness._actor import require_named  # noqa: PLC0415

    who = require_named("run-promote")

    m = run_record(args.run)
    if m is None:
        die(f"no scored run {args.run!r} (looked for {RUNS / args.run})", "not-found")
    from evaluation_harness import _faith  # noqa: PLC0415

    faith = _faith.allow_scoring(m, "promoting", args.unfaithful)

    build = m.get("build") or {}
    if build.get("ref", "unknown") == "unknown" and not args.allow_unknown_build:
        die(
            "REFUSED — this run does not identify its build.\n"
            "  A baseline whose build is unknown cannot be attributed to any code.\n"
            "  Declare it and re-run:  EVAL_BUILD_REF=<version|digest|sha> "
            + how("evh run ...", "make run ...")
            + "\n"
            "  (--allow-unknown-build overrides, but then the baseline names no system.)",
            "not-configured",
        )
    # No ref at all (not a git project) was refused above, and --allow-unknown-build already says so: one flag, not two.
    if (
        _common.tree_state(build) is None
        and build.get("ref", "unknown") != "unknown"
        and not args.allow_dirty
    ):
        die(
            f"REFUSED — git could not say whether the tree run {args.run} came from was clean.\n"
            f"  build.ref={build.get('ref', '?')[:12]} is not proven to describe what actually ran.\n"
            "  Re-run where git works and promote that — or --allow-dirty and say why in --reason.",
            "not-allowed",
        )
    if build.get("dirty") and not args.allow_dirty:
        die(
            f"REFUSED — run {args.run} was produced by a DIRTY tree.\n"
            f"  build.ref={build.get('ref', '?')[:12]} does not describe what actually ran.\n"
            "  Commit, re-run, and promote that — or --allow-dirty and say why in --reason.",
            "not-allowed",
        )
    if len(args.reason.split()) < 3:
        die(
            "REFUSED — --reason must be a sentence, not a word. It is the answer to "
            '"why is this the baseline?" in six months.',
            "bad-argument",
        )

    # AN ARM RUN WITH --repeat: the catalog, the inspector and every test read the mean of its
    # repeats, while a baseline is promoted from one run. Record which runs the arm has and their
    # mean beside the run's own scores (V6 keeps comparing `scores` with the run), and say so.
    repeats = _repeats(m)
    if args.goal and args.no_goal:
        die("--goal and --no-goal: one or the other", "bad-argument")
    goal_id = None if args.no_goal else (args.goal or m.get("goal"))
    goal_doc = None
    if goal_id:
        goal_doc = load_goals().get(goal_id)
        if goal_doc is None:
            die(f"no goal {goal_id!r} (data/goals/)", "not-found")
        if m["dataset_id"] not in {d.get("dataset_id") for d in goal_doc.get("datasets") or []}:
            die(
                f"goal {goal_id} does not name dataset {m['dataset_id']}: --goal another, or --no-goal",
                "mismatch",
            )

    if goal_doc is not None:
        measure = ((goal_doc.get("success_criteria") or {}).get("primary") or {}).get("measure")
        if measure and measure not in m["scores"]:
            print(
                f"  WARNING: goal {goal_id}'s primary measure {measure!r} is none of the scores of {m['run_id']} "
                f"({', '.join(k for k in m['scores'] if not k.startswith(BOOKKEEPING_PREFIXES))}): this baseline "
                "answers nothing on it"
            )
    look_ctx: dict = {}
    in_round: dict = {}
    if args.round and goal_id:
        from evaluation_harness import _rounds  # noqa: PLC0415
        from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415

        rnd = _rounds.find(goal_id, args.round)
        held = next((a for a in model_rounds.arms(rnd or {}) if m["run_id"] in (a.get("runs") or [])), None)
        in_round = {"round": args.round, **({"arm": held["system"]} if held else {})}

    def make(cur: dict | None, n: int) -> dict:
        ev = evidence(m, cur, goal_doc, args.round, look_ctx.get("look"))
        doc = {
            "dataset_id": m["dataset_id"],
            "goal": goal_id,
            "promoted_from": m["run_id"],
            **in_round,
            "promoted_at": now(),
            "actor": who,
            "reason": args.reason,
            "replaces": cur["version"] if cur else None,
            "evidence": ev,
            "scores": m["scores"],
            "build": build,
            # Carried from the run: what the number means. A baseline is compared against, and
            # a silver baseline beside a gold run, or one scored by another adapter, is not the
            # same number.
            **{k: v for k, v in carried(m).items() if k != "goal"},
            **({"repeats": repeats} if repeats else {}),
            **({"faithfulness": faith} if faith is not None else {}),
        }
        return doc

    # A promotion on a test set compared with its current version is a look (RFC-029): numbered under the set's
    # lock while the version is written, tested one-sided at the look's level; one question is one look.
    from evaluation_harness import _looks  # noqa: PLC0415

    cur = _baselines.current(goal_id, m["dataset_id"])
    b_cfg = _config_of(cur["promoted_from"]) if cur else None
    if cur and b_cfg and b_cfg != m["system_id"] and _looks.is_test_set(m["dataset_id"]):
        prim = ((goal_doc or {}).get("success_criteria") or {}).get("primary") or {}
        measure = prim.get("measure") or m.get("primary_metric")
        k = _looks.key(m["dataset_id"], m["system_id"], b_cfg, measure, "superiority")
        with _looks.taking(m["dataset_id"], k, consent=args.confirm_extra_look) as look:
            look_ctx["look"] = {**look, "override": args.override_no_evidence}
            print(
                f"  look {look['number']} at test set {m['dataset_id']}, one-sided at {look['level']:.4%}"
                + (" (the same question as before: its look reused)" if look["reused"] else "")
            )
            doc = _baselines.write_next(goal_id, m["dataset_id"], make)
    else:
        doc = _baselines.write_next(goal_id, m["dataset_id"], make)
    line = f"{goal_id or 'the dataset'}'s baseline on {m['dataset_id']}"
    out = _baselines.folder(goal_id, m["dataset_id"]) / f"{doc['version']}.json"
    print(f"{out}  version {doc['version']} of {line}")
    _jsonout.values(
        {
            "goal": goal_id,
            "dataset_id": m["dataset_id"],
            "version": doc["version"],
            "path": str(out),
            "evidence": doc["evidence"],
        }
    )
    ev = doc["evidence"]
    if ev.get("compared_to") is not None:
        vd = ev.get("verdict")
        print(
            f"  against version {ev['compared_to']}: "
            + (
                f"{vd['outcome']}, delta {vd['delta']:+.4f}, p {vd['p']:.4g} on {ev.get('measure')} (n={ev.get('n')})"
                if vd
                else "no test (" + "; ".join(ev.get("not_comparable") or []) + ")"
            )
        )
    # The scores it reads by, not the bookkeeping (`resumed`, `self_family_*`): the baseline file
    # keeps every key, as its run has them (V6 compares the two).
    shown = {k: v for k, v in m["scores"].items() if not k.startswith(BOOKKEEPING_PREFIXES)}
    if repeats:
        print(
            f"  NOTE: {m['system_id']} has {len(repeats['runs'])} repeats; the catalog, the inspector and the tests read"
            f" their mean.\n        The baseline records this run's own scores and, under `repeats`, the mean:"
        )
        print("\n".join(repeats_lines(shown, repeats)))
        return 0
    from evaluation_harness.ops.records import _num  # noqa: PLC0415

    w = max([len(k) for k in shown] + [6])
    for k, v in sorted(shown.items()):
        print(f"    {k:{w}} {_num(v)}")
    return 0


def repeats_lines(shown: dict[str, Any], repeats: dict[str, Any]) -> list[str]:
    """A score a line: this run's, then the mean of its repeats, both as `evh baselines` prints a score."""
    from evaluation_harness.ops.records import _num  # noqa: PLC0415

    w0 = max([len(k) for k in shown] + [6])
    return [
        f"    {k:{w0}} {_num(shown[k])}   (mean of {len(repeats['runs'])}: {_num(repeats['mean_scores'][k])})"
        for k in sorted(shown)
        if k in repeats["mean_scores"]
    ]
