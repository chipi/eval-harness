#!/usr/bin/env python3
"""Run several systems on one dataset, then rank them.

Comparing four models should be one command, not four invocations and six
pairwise comparisons. This runs each system in turn, keeps going when one
fails — a provider outage on the third should not throw away the first two —
and ends with the leaderboard.

    evh sweep --systems arm_a_v1 arm_b_v1 --dataset smoke_v1 --repeat 2
    evh sweep --systems arm_a_v1 arm_b_v1 --dataset smoke_v1 --dry-run

Always dry-run first. It costs nothing and tells you what the sweep will.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import subprocess
import sys

from evaluation_harness import _jsonout, _spend
from evaluation_harness._common import CODE, EXIT_PARTLY, EXIT_STOPPED, ROOT, die, evh_prog


def main() -> int:
    """Run several systems on one dataset, then rank them."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument(
        "--systems", nargs="+", required=True, help="the systems to run: their ids (evh system-list)"
    )
    ap.add_argument("--dataset", required=True, help="the one dataset they all run on")
    ap.add_argument("--goal", help="the goal the runs are measured for")
    ap.add_argument("--round", help="the round of its goal the runs belong to (needs --goal)")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true", help="cost it without calling anything")
    ap.add_argument("--sort", help="leaderboard metric")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("sweep", args.json, live=sys.stderr):
        from evaluation_harness.model.systems import SYSTEM  # noqa: PLC0415

        # Every system is known before the first one runs: a typo found after three paid runs wastes them.
        known = set(SYSTEM.ids())
        missing = [s for s in args.systems if s not in known]
        if missing:
            die(f"no system {', '.join(missing)} (evh system-list)", "not-found")
        configs = list(dict.fromkeys(args.systems))
        dataset_id = args.dataset

        py = sys.executable
        print(f"sweep: {len(configs)} arm(s) on {dataset_id}, repeat={args.repeat}\n")

        failed: list[str] = []
        for i, c in enumerate(configs, 1):
            print(f"── [{i}/{len(configs)}] {c} " + "─" * max(0, 50 - len(c)))
            cmd = [
                py,
                str(CODE / "run.py"),
                "--system",
                c,
                "--dataset",
                dataset_id,
                "--repeat",
                str(args.repeat),
            ]
            cmd += [
                *(["--goal", args.goal] if args.goal else []),
                *(["--round", args.round] if args.round else []),
            ]
            if args.dry_run:
                cmd.append("--dry-run")
            left = _spend.left()
            if not args.dry_run and left is not None and left <= 0:
                # The sweep's cap is spent (RFC-026 step 5): the arms after this one are not run.
                print(f"   NOT RUN — the cap is spent (${_spend.spent():.4f} of ${_spend.cap():.4f})")
                failed.append(c)
                continue
            if args.dry_run:
                r = subprocess.run(cmd, cwd=ROOT)
            else:
                # Each arm gets what the arms before it left of the cap, from what each wrote it spent.
                r, paid = _spend.run_child(cmd, cwd=ROOT)
                if paid:
                    print(
                        f"   spent ${paid:.4f}"
                        + (f", ${_spend.left():.4f} left" if _spend.left() is not None else "")
                    )
            if r.returncode == EXIT_STOPPED:
                # Stopped at the cap (the sweep's, or the round's): its partial run is kept and resumable.
                failed.append(c)
                print(f"   ARM STOPPED at the cost cap (exit {r.returncode}) — its partial run is kept")
            elif r.returncode != 0:
                # Keep going: one provider's outage should not discard the arms
                # that already succeeded and were paid for.
                failed.append(c)
                print(f"   ARM FAILED (exit {r.returncode}) — continuing with the rest")
            print()

        if failed:
            print(f"  {len(failed)} arm(s) failed: {', '.join(failed)}")
            print("  The rest still ran; their results are on the leaderboard below.\n")

        if args.dry_run:
            print("Dry run — nothing was called and nothing was spent.")
            return 0

        lb = [py, str(CODE / "leaderboard.py"), "--dataset-id", dataset_id]
        if args.sort:
            lb += ["--sort", args.sort]
        subprocess.run(lb, cwd=ROOT)
        _jsonout.values({"arms": configs, "not_finished": failed, "spent_usd": round(_spend.spent(), 8)})
        return EXIT_PARTLY if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
