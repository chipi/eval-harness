#!/usr/bin/env python3
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

    python scripts/promote_baseline.py --run <run_id> --reason "beat prev by 4% on n=40"
    evh run-promote --run <run_id> --reason "..." --goal G      # another of the dataset's goals
    evh run-promote --run <run_id> --reason "..." --no-goal     # the dataset's own baselines
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json
import os
import subprocess
import sys
from typing import Any

from evaluation_harness import _baselines, _common, _jsonout, _store
from evaluation_harness._common import (
    BOOKKEEPING_PREFIXES,
    RUNS,
    die,
    evh_prog,
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
    """The repeats of the promoted run's arm (same system, same base run id, `repeat_index` set):
    their run ids and the mean of each score over them; None for a run that is not a repeat."""
    import re  # noqa: PLC0415
    import statistics  # noqa: PLC0415

    if not m.get("repeat_index"):
        return None
    base = re.sub(r"_r\d+$", "", m["run_id"])
    sibs = []
    for d in sorted(_store.glob(RUNS, f"{base}_r*")):
        mm = run_record(d.name) or {}
        if mm.get("config_id") == m["config_id"] and mm.get("repeat_index"):
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
    return (run_record(run_id) or {}).get("config_id")


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
    a, b = m["config_id"], _config_of(cur["promoted_from"])
    prim = ((goal or {}).get("success_criteria") or {}).get("primary") or {}
    measure = prim.get("measure") or m.get("primary_metric")
    out["measure"] = measure
    if b is None:
        out |= {"verdict": None, "not_comparable": ["the current version's run is gone"]}
        return out
    if a == b:
        out |= {"verdict": None, "not_comparable": ["the same arm (another run of it)"]}
        return out
    argv = ["pair-test", "--dataset-id", m["dataset_id"], "--a", a, "--b", b, "--json"]
    if measure:
        argv += ["--metric", measure]
    if goal:
        cl = _common.goal_cluster(goal, m["dataset_id"])
        argv += ["--cluster", cl] if cl else []
        if isinstance(prim, dict) and prim.get("reduce"):
            argv += ["--reduce", str(prim["reduce"])]
        if prim.get("direction") in ("lower", "higher"):
            argv += ["--asc"] if prim["direction"] == "lower" else ["--desc"]
        if round_id:
            argv += ["--round", round_id, "--goal", goal["goal_id"]]
    if look is not None:  # a look at a test set (RFC-029): one-sided at its level
        argv += ["--look-level", repr(look["level"])]
    r = subprocess.run(
        [sys.executable, str(_Path(__file__).resolve().parent / "cli.py"), *argv],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    if r.returncode != 0:
        why = (r.stderr.strip().splitlines() or ["pair-test refused"])[-1]
        out |= {"verdict": None, "not_comparable": [why]}
        return out
    v = (json.loads(r.stdout).get("result") or {}).get("values") or {}
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


def main() -> int:
    """Promote a run to baseline status."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--reason", help="why this run earned promotion")
    # Reading the reason from the environment keeps it away from the shell entirely.
    # As a command-line argument interpolated by make, a backtick in the reason
    # executed and a double quote mangled it -- and this text is written into a
    # baseline, where it is the permanent record of why a number was promoted.
    ap.add_argument(
        "--reason-from-env",
        action="store_true",
        help="take the reason from $EVAL_PROMOTE_REASON (what `make "
        "run-promote` does, so the shell never re-parses it)",
    )
    ap.add_argument("--goal", help="the goal it is the baseline of (default: the run's own goal)")
    ap.add_argument(
        "--no-goal",
        action="store_true",
        help="the dataset's own baselines, not a goal's (a run with no goal goes there)",
    )
    ap.add_argument(
        "--round", help="the round whose conclusion this is: the evidence reads the arms as it does"
    )
    ap.add_argument("--allow-dirty", action="store_true", help="promote from a dirty tree anyway")
    ap.add_argument(
        "--confirm-extra-look",
        action="store_true",
        help="on a test set past its limit of looks (RFC-029): the person's consent to look again (an agent cannot)",
    )
    ap.add_argument(
        "--override-no-evidence",
        action="store_true",
        help="on a test set whose items could never show the comparison: promote anyway, labelled inconclusive",
    )
    ap.add_argument(
        "--allow-unknown-build",
        action="store_true",
        help="promote a run whose build could not be identified — a DIFFERENT and worse "
        "problem than a dirty tree, so it takes its own flag",
    )
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    ap.add_argument(
        "--unfaithful",
        action="store_true",
        help="promote a replay (RFC-030) whose faithfulness record does not agree with production, as a person (an "
        "agent is refused); the baseline says so",
    )
    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("run-promote", args.json, live=sys.stderr):
        if args.reason_from_env:
            args.reason = os.environ.get("EVAL_PROMOTE_REASON", "")
        if not (args.reason or "").strip():
            die(
                'a reason is required: --reason "..." or --reason-from-env with EVAL_PROMOTE_REASON set',
                "bad-argument",
            )
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
        goal = None
        if goal_id:
            goal = load_goals().get(goal_id)
            if goal is None:
                die(f"no goal {goal_id!r} (data/goals/)", "not-found")
            if m["dataset_id"] not in {d.get("dataset_id") for d in goal.get("datasets") or []}:
                die(
                    f"goal {goal_id} does not name dataset {m['dataset_id']}: --goal another, or --no-goal",
                    "mismatch",
                )

        look_ctx: dict = {}
        in_round: dict = {}
        if args.round and goal_id:
            from evaluation_harness import _rounds  # noqa: PLC0415
            from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415

            rnd = _rounds.find(goal_id, args.round)
            held = next(
                (a for a in model_rounds.arms(rnd or {}) if m["run_id"] in (a.get("runs") or [])), None
            )
            in_round = {"round": args.round, **({"arm": held["system"]} if held else {})}

        def make(cur: dict | None, n: int) -> dict:
            ev = evidence(m, cur, goal, args.round, look_ctx.get("look"))
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
        if cur and b_cfg and b_cfg != m["config_id"] and _looks.is_test_set(m["dataset_id"]):
            prim = ((goal or {}).get("success_criteria") or {}).get("primary") or {}
            measure = prim.get("measure") or m.get("primary_metric")
            k = _looks.key(m["dataset_id"], m["config_id"], b_cfg, measure, "superiority")
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
                f"  NOTE: {m['config_id']} has {len(repeats['runs'])} repeats; the catalog, the inspector and the tests read"
                f" their mean.\n        The baseline records this run's own scores and, under `repeats`, the mean:"
            )
            w0 = max([len(k) for k in shown] + [6])
            for k in sorted(shown):
                if k in repeats["mean_scores"]:
                    print(
                        f"    {k:{w0}} {shown[k]}   (mean of {len(repeats['runs'])}: {repeats['mean_scores'][k]:.6g})"
                    )
            return 0
        w = max([len(k) for k in shown] + [6])
        for k, v in sorted(shown.items()):
            print(f"    {k:{w}} {v}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
