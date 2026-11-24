#!/usr/bin/env python3
"""Every test file exits with its tally: a bare `summary()` prints the failures and exits 0, so the gate never sees them.

    python tests/test_tests_exit.py

`_check.summary` returns the exit code; it does not exit. Three test files ended on `summary()` alone (review,
2026-11-24): test_round_spend, test_leaderboard_prose_measure and test_no_nan_shown could not fail a gate.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from evaluation_harness._check import check, summary  # noqa: E402

BARE = re.compile(r"^summary\(", re.M)


def bare(text: str) -> bool:
    """Whether a file calls `summary(` at module level without exiting with what it returns."""
    return bool(BARE.search(text))


check(
    "the scan finds a bare summary() and passes sys.exit(summary())",
    bare("x = 1\nsummary()\n") and not bare("sys.exit(summary())\n") and not bare("    return summary()\n"),
)
found = sorted(
    p.name for p in HERE.glob("*.py") if p.name != Path(__file__).name and bare(p.read_text(encoding="utf-8"))
)
check("no test file ends on a bare summary(): each exits with its tally", not found, found)
sys.exit(summary())
