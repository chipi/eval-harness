#!/usr/bin/env python3
"""Why a round's leader is not promoted, said when its paired test has no p (RFC-032 step 8): a leader whose items
score exactly as the baseline's has no variation to test, and the reason crashed on the missing p (TypeError).

    python tests/test_promote_hold.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary
from evaluation_harness.model import rounds

flat = {"label": "the baseline it started from", "verdict": "not significant", "delta": 0.0, "p": None}
try:
    said = rounds._promote_hold([flat], None)
except TypeError as exc:
    said = f"TypeError: {exc}"
check(
    "a leader no different from its baseline on any item is held, and says its test has no p",
    said.startswith("not ahead of the baseline it started from") and "no p" in said,
    said,
)
corrected = {**flat, "p": 0.04, "p_adjusted": None, "family": 3}
check(
    "a corrected row with no adjusted p says the raw p only",
    "p 0.0400" in rounds._promote_hold([corrected], None)
    and "Bonferroni" not in rounds._promote_hold([corrected], None),
    rounds._promote_hold([corrected], None),
)

sys.exit(summary())
