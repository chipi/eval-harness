#!/usr/bin/env python3
"""List runs (or baselines) with the three things that make a number mean something.

python scripts/list_runs.py
python scripts/list_runs.py --baselines
"""

from __future__ import annotations

import argparse

from _common import (
    BASELINES,
    BOOKKEEPING_PREFIXES,
    how,
    read_json,
)
from _runs import runs_on


def main() -> int:
    """List the runs, or with --baselines the baselines."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--baselines", action="store_true")
    args = ap.parse_args()

    if args.baselines:
        files = sorted(BASELINES.glob("*.json"))
        if not files:
            print(
                "no baselines yet — promote a run:  "
                + how('evh run-promote --run <id> --reason "..."', 'make run-promote RUN=<id> REASON="..."')
            )
            return 0
        for f in files:
            b = read_json(f)
            print(f"{b['baseline_id']}")
            print(f"    dataset  {b['dataset_id']}")
            print(f"    from     {b['promoted_from']}   build={b['build'].get('ref', '?')[:12]}")
            print(f"    scored   {b.get('reference_tier', '?')} references, adapter {b.get('adapter', '?')}")
            print(f"    why      {b.get('reason', '(none recorded)')}")
            print(
                "    scores   "
                + "  ".join(
                    f"{k}={v}"
                    for k, v in sorted(b["scores"].items())
                    if not k.startswith(BOOKKEEPING_PREFIXES)
                )
            )
        return 0

    dirs = [d for d, _m in runs_on()]
    if not dirs:
        print(
            "no runs yet — "
            + how("start with `evh experiment-run --config <arm>.yaml` (docs/GUIDE.md)", "try:  make demo")
        )
        return 0
    print(f"{'run_id':44} {'dataset_id':18} {'build':14} scores")
    for d in dirs:
        m = read_json(d / "metrics.json")
        scores = "  ".join(
            f"{k}={v}" for k, v in sorted(m["scores"].items()) if not k.startswith(BOOKKEEPING_PREFIXES)
        )
        dirty = "*" if m["build"].get("dirty") else " "
        print(f"{m['run_id']:44} {m['dataset_id']:18} {m['build'].get('ref', '?')[:12]}{dirty} {scores}")
    print("\n  * = produced by a dirty tree; its build ref does not describe what ran")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
