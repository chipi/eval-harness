"""Run several systems on one dataset, then rank them.

Comparing four models should be one command, not four invocations and six
pairwise comparisons. This runs each system in turn, keeps going when one
fails — a provider outage on the third should not throw away the first two —
and ends with the leaderboard.

    evh sweep --systems arm_a_v1 arm_b_v1 --dataset smoke_v1 --repeat 2
    evh sweep --systems arm_a_v1 arm_b_v1 --dataset smoke_v1 --dry-run
    evh sweep --systems arm_a_v1 arm_b_v1 --dataset smoke_v1 --scratch   # a smoke: no run kept, nothing ranked

Always dry-run first. It costs nothing and tells you what the sweep will.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import Any

from evaluation_harness import _jsonout, _progress, _spend
from evaluation_harness._common import CODE, EXIT_PARTLY, EXIT_STOPPED, ROOT, die
from evaluation_harness.ops import legacy


def body(**inputs: Any) -> int:
    """Run several systems on one dataset, then rank them."""
    args = legacy.namespace(inputs, "sweep")
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
    # The notes a dry run of one arm says once for a model (no model record) are said once for the whole sweep: the
    # arms are processes of their own, and share this file to tell each other.
    seen = ""
    if args.dry_run:
        fd, seen = tempfile.mkstemp(prefix="evh-dry-seen-")
        os.close(fd)
    for i, c in enumerate(configs, 1):
        _progress.step(i - 1, len(configs))
        print(f"── [{i}/{len(configs)}] {c} " + "─" * max(0, 50 - len(c)))
        cmd = [
            py,
            str(CODE / "cli.py"),
            "run",
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
        if args.allow_unpriced:
            cmd.append("--allow-unpriced")
        if args.scratch:
            cmd.append("--scratch")
        sys_params = SYSTEM.get(c).get("params")
        if not args.dry_run and _spend.exhausted(sys_params):
            # The sweep's cap is spent (RFC-026 step 5), or 0 for a system not known to be free: not run.
            print(
                f"   NOT RUN — the cap is spent (${_spend.spent():.4f} of ${_spend.cap():.4f})"
                + (f": {_spend.ZERO_CAP_HINT}" if _spend.zero_blocked(_spend.cap(), sys_params) else "")
            )
            failed.append(c)
            continue
        if args.dry_run:
            r = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "EVH_DRY_SEEN": seen})
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

    _progress.step(len(configs), len(configs))
    if seen:
        os.unlink(seen)
    if failed:
        print(f"  {len(failed)} arm(s) failed: {', '.join(failed)}")
        print("  The rest still ran; their results are on the leaderboard below.\n")

    if args.dry_run:
        print("Dry run — nothing was called and nothing was spent.")
        return 0
    if args.scratch:
        # The leaderboard reads data/runs: after a scratch sweep it would rank the real arms, not these.
        print(
            "Scratch sweep — the runs are under .build/scratch/runs, which nothing that reads runs sees: no ranking."
        )
        _jsonout.values({"arms": configs, "not_finished": failed, "spent_usd": round(_spend.spent(), 8)})
        return EXIT_PARTLY if failed else 0

    # The ranking is the operation's own, printed as the command prints it, not a command line run in another process.
    from evaluation_harness import ops  # noqa: PLC0415

    ops.OPS["leaderboard"].print_text(dataset=dataset_id, **({"sort": args.sort} if args.sort else {}))
    _jsonout.values({"arms": configs, "not_finished": failed, "spent_usd": round(_spend.spent(), 8)})
    return EXIT_PARTLY if failed else 0
