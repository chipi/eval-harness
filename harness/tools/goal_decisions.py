#!/usr/bin/env python3
"""Each goal's decision on the datasets it decides on, as the catalog's glance computes it: JSON.

    python tools/goal_decisions.py

One row per goal and dataset: the measure, the gold group's leader, the promoted baseline and
its recorded reason, what the goal's strategy recommends and its reasons. The site reads this,
so an experiment page says what the catalog says (site/figures.py).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
from evaluation_harness import catalog_build as cb
from evaluation_harness.catalog_adapter import HarnessAdapter

DATA = Path(__file__).resolve().parents[1] / "data"


def main() -> int:
    """Print the glance's rows, reduced to what a page can quote."""
    A = HarnessAdapter(DATA)
    rows = cb.glance(A, cb.collect(A))
    out = [
        {
            "goal_id": r["goal"]["goal_id"],
            "goal_title": r["goal"].get("title") or r["goal"]["goal_id"],
            "goal_page": cb.goal_page(r["goal"]["goal_id"]),
            "dataset": r["dataset"],
            "measure": r["measure"],
            "gold": r["gold"],
            "strategy": r["strategy"],
            "leader": r["leader"],
            "baseline": r["baseline"],
            "baseline_reason": r["baseline_reason"],
            "recommended": r["recommended"],
            "why": r["why"],
        }
        for r in rows
    ]
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
