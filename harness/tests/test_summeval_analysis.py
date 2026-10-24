"""SummEval split-half (tools/summeval_analysis.py): a tied top is undecided, as in rank_stability.

Moved out of scripts/test_stats.py, which ships in the package: summeval_analysis is this
repository's report code and is not.
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))  # summeval_analysis
import summeval_analysis as _sea
from evaluation_harness._check import check, summary

_tied = {a: {f"i{k}": 1.0 for k in range(10)} for a in ("alpha", "beta")}
_sh = _sea.split_half(_tied, list(_tied["alpha"]), 3, random.Random(1))
check(
    "split-half: a tied top is undecided, never 'the same winner' by name",
    _sh["undecided"] == 1.0 and _sh["same_winner"] != _sh["same_winner"],
    _sh,
)
_clear = {"top": {f"i{k}": 1.0 for k in range(10)}, "low": {f"i{k}": 0.0 for k in range(10)}}
check(
    "split-half: a unique winner in both halves is agreement",
    _sea.split_half(_clear, list(_clear["top"]), 3, random.Random(1))["same_winner"] == 1.0,
)
_src = (Path(__file__).resolve().parents[1] / "tools" / "summeval_analysis.py").read_text()
check(
    "holm: summeval_analysis uses stats.holm, so it cannot disagree with the inspector",
    "holm(" in _src and "/ (m - i)" not in _src,
)

sys.exit(summary())
