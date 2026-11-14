#!/usr/bin/env python3
"""Krippendorff's alpha over any number of label sets (`_label_sets.alpha_all`, PLAN_0.8.0 B1).

    python tests/test_alpha_all.py

Krippendorff's own reliability example (Computing Krippendorff's Alpha-Reliability, 2011: 4 coders, 12 units,
missing values, nominal): alpha 0.743. Two sets give the pairwise `compare`'s alpha; perfect agreement is 1, with
an interval; free text has none. The interval is seeded by the labels, so it is the same each time.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary
from evaluation_harness._label_sets import alpha_all, compare

units = [
    ["1", "1", "1"],
    ["2", "2", "3", "2"],
    ["3", "3", "3", "3"],
    ["3", "3", "3", "3"],
    ["2", "2", "2", "2"],
    ["1", "2", "3", "4"],
    ["4", "4", "4", "4"],
    ["1", "1", "2", "1"],
    ["2", "2", "2", "2"],
    ["5", "5", "5"],
    ["1", "1"],
    ["3"],
]
got = alpha_all(units)
assert got is not None
check(
    "Krippendorff's 2011 example: nominal alpha 0.743",
    got is not None and round(got["alpha"], 3) == 0.743,
    got,
)
check(
    "... over the 11 units labelled twice or more, with an interval around it",
    got["items"] == 11 and got["ci"][0] < 0.743 < got["ci"][1],
    got,
)
check("the same labels give the same interval", alpha_all(units) == got)
pairs = [("a", "a"), ("a", "b"), ("b", "b"), ("c", "c"), ("b", "c"), ("a", "a")]
check(
    "two sets: alpha_all is the pairwise compare's alpha",
    (alpha_all([list(p) for p in pairs]) or {}).get("alpha") == compare(pairs)["alpha"],
    (alpha_all([list(p) for p in pairs]), compare(pairs)["alpha"]),
)
perfect = alpha_all([["x", "x", "x"], ["y", "y", "y"], ["x", "x", "x"]])
check("perfect agreement is 1", (perfect or {}).get("alpha") == 1.0, perfect)
long_text = "the customer cannot log in after the reset and asks for a call back today"
check("free text has no alpha", alpha_all([[long_text, long_text + " again"], ["a b c d e", "x"]]) is None)
sys.exit(summary())
