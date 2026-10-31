#!/usr/bin/env python3
"""The triage results doc's table is the harness's own (research/internal/triage_results.py --check), and
`evh goals --goal` prints a dataset's notes, among them how many arms it reads from their re-score.

python tests/test_triage_results_doc.py
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from evaluation_harness._check import check, summary  # noqa: E402

GEN = HERE.parent / "research" / "internal" / "triage_results.py"
r = subprocess.run([sys.executable, str(GEN), "--check"], capture_output=True, text=True, cwd=HERE)
check(
    "TRIAGE_RESULTS_LIVE.md: its table matches what the harness ranks now",
    r.returncode == 0 and "up to date" in r.stdout,
    (r.stdout + r.stderr)[-400:],
)
g = subprocess.run(
    [sys.executable, "-m", "evaluation_harness", "goals", "--goal", "triage_orrery"],
    capture_output=True,
    text=True,
    cwd=HERE,
)
check(
    "evh goals --goal: a dataset's notes are printed, with the arms read from their re-score",
    g.returncode == 0 and "mostly rebuilt" in g.stdout and "read from their re-score" in g.stdout,
    g.stdout[:600],
)

sys.exit(summary())
