#!/usr/bin/env python3
"""Run several arms over one dataset, then rank them.

Comparing four models should be one command, not four invocations and six
pairwise comparisons. This runs each config in turn, keeps going when one arm
fails — a provider outage on arm 3 should not throw away arms 1 and 2 — and
ends with the leaderboard.

    python scripts/sweep.py --configs data/configs/arm_*.yaml --repeat 2
    python scripts/sweep.py --configs data/configs/arm_*.yaml --dry-run

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
from pathlib import Path

from evaluation_harness import _jsonout, _spend, _store
from evaluation_harness._common import CODE, EXIT_PARTLY, EXIT_STOPPED, ROOT, die, evh_prog

try:
    import yaml
except ImportError:  # pragma: no cover
    die("pyyaml is required — pip install -r requirements.txt", "missing-dependency")


def main() -> int:
    """Generate a parameter sweep configuration."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--configs", nargs="+", required=True, type=Path)
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
        configs = [c for c in args.configs if _store.is_file(c)]
        if not configs:
            die(f"no config files matched: {' '.join(str(c) for c in args.configs)}", "not-found")

        # Every arm must sit on the SAME dataset, or the leaderboard is a list of
        # unrelated numbers. Refuse up front rather than producing one.
        datasets: dict = {}
        for c in configs:
            cfg = yaml.safe_load(_store.read_text(c, encoding="utf-8")) or {}
            datasets.setdefault(cfg.get("dataset_id"), []).append(c.name)
        if len(datasets) != 1:
            lines = "\n".join(f"    {d or '(missing)'}: {', '.join(n)}" for d, n in datasets.items())
            die(
                "REFUSED — the arms do not share one dataset_id:\n"
                + lines
                + "\n  A leaderboard across datasets ranks nothing. Re-run the odd ones out.",
                "mismatch",
            )
        dataset_id = next(iter(datasets))

        py = sys.executable
        print(f"sweep: {len(configs)} arm(s) on {dataset_id}, repeat={args.repeat}\n")

        failed: list[str] = []
        for i, c in enumerate(configs, 1):
            print(f"── [{i}/{len(configs)}] {c.name} " + "─" * max(0, 50 - len(c.name)))
            cmd = [py, str(CODE / "run.py"), "--config", str(c), "--repeat", str(args.repeat)]
            if args.dry_run:
                cmd.append("--dry-run")
            left = _spend.left()
            if not args.dry_run and left is not None and left <= 0:
                # The sweep's cap is spent (RFC-026 step 5): the arms after this one are not run.
                print(f"   NOT RUN — the cap is spent (${_spend.spent():.4f} of ${_spend.cap():.4f})")
                failed.append(c.name)
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
                failed.append(c.name)
                print(f"   ARM STOPPED at the cost cap (exit {r.returncode}) — its partial run is kept")
            elif r.returncode != 0:
                # Keep going: one provider's outage should not discard the arms
                # that already succeeded and were paid for.
                failed.append(c.name)
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
        _jsonout.values(
            {"arms": [c.name for c in configs], "not_finished": failed, "spent_usd": round(_spend.spent(), 8)}
        )
        return EXIT_PARTLY if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
