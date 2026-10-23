#!/usr/bin/env python3
"""Promote a run to a baseline.

A baseline is never edited: promoting another run replaces it, and git keeps the one it
replaced. It is the number future work is judged against, so promoting one is a decision,
not a copy.

Two things are refused, because both produce a baseline nobody can act on:

  * a run whose build is unknown or dirty — you cannot later say WHICH code
    earned the number
  * a promotion with no reason — six months on, "why is this the baseline?"
    has no answer, and the number gets cargo-culted

    python scripts/promote_baseline.py --run <run_id> --reason "beat prev by 4% on n=40"
"""

from __future__ import annotations

import argparse
import os

from _common import (
    BASELINES,
    RUNS,
    die,
    how,
    now,
    read_json,
    write_json,
)


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


def main() -> int:
    """Promote a run to baseline status."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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
    ap.add_argument("--baseline-id", help="default: <dataset_id>_baseline")
    ap.add_argument("--allow-dirty", action="store_true", help="promote from a dirty tree anyway")
    ap.add_argument(
        "--allow-unknown-build",
        action="store_true",
        help="promote a run whose build could not be identified — a DIFFERENT and worse "
        "problem than a dirty tree, so it takes its own flag",
    )
    args = ap.parse_args()
    if args.reason_from_env:
        args.reason = os.environ.get("EVAL_PROMOTE_REASON", "")
    if not (args.reason or "").strip():
        die('a reason is required: --reason "..." or --reason-from-env with EVAL_PROMOTE_REASON set')

    src = RUNS / args.run / "metrics.json"
    if not src.is_file():
        die(f"no run {args.run!r} (looked for {src})")
    m = read_json(src)

    build = m.get("build") or {}
    if build.get("ref", "unknown") == "unknown" and not args.allow_unknown_build:
        die(
            "REFUSED — this run does not identify its build.\n"
            "  A baseline whose build is unknown cannot be attributed to any code.\n"
            "  Declare it and re-run:  EVAL_BUILD_REF=<version|digest|sha> "
            + how("evh experiment-run ...", "make experiment-run ...")
            + "\n"
            "  (--allow-unknown-build overrides, but then the baseline names no system.)"
        )
    if build.get("dirty") and not args.allow_dirty:
        die(
            f"REFUSED — run {args.run} was produced by a DIRTY tree.\n"
            f"  build.ref={build.get('ref', '?')[:12]} does not describe what actually ran.\n"
            "  Commit, re-run, and promote that — or --allow-dirty and say why in --reason."
        )
    if len(args.reason.split()) < 3:
        die(
            "REFUSED — --reason must be a sentence, not a word. It is the answer to "
            '"why is this the baseline?" in six months.'
        )

    baseline_id = args.baseline_id or f"{m['dataset_id']}_baseline"
    out = BASELINES / f"{baseline_id}.json"
    if out.is_file():
        print(f"  replaces the baseline promoted from {read_json(out).get('promoted_from')} (git keeps it)")

    write_json(
        out,
        {
            "baseline_id": baseline_id,
            "dataset_id": m["dataset_id"],
            "promoted_from": m["run_id"],
            "promoted_at": now(),
            "reason": args.reason,
            "scores": m["scores"],
            "build": build,
            # Carried from the run: what the number means. A baseline is compared against, and
            # a silver baseline beside a gold run, or one scored by another adapter, is not the
            # same number.
            **carried(m),
        },
    )
    print(f"{out}")
    w = max([len(k) for k in m["scores"]] + [6])
    for k, v in sorted(m["scores"].items()):
        print(f"    {k:{w}} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
