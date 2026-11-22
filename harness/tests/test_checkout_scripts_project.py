#!/usr/bin/env python3
"""The repository's own scripts that import the harness name its project, from wherever they run.

    python tests/test_checkout_scripts_project.py

project_root() is the same for a checkout as for an install: EVAL_HOME, else the nearest directory up with data/,
else the current one. The repository's project is harness/, so a script outside it that puts harness/ on sys.path
and imports the package sets EVAL_HOME to it (unless it is set). reproduce.py did not, and every rerun job, run
from the repository's root, stopped with not-configured (CI on a285b61db, 2026-11-17). Checked here: every such
script carries the default, and reproduce.py run from the root with no EVAL_HOME lists the experiments.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
ROOT = HARNESS.parent
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

PUTS = re.compile(r"^sys\.path\.insert\(0, str\((.*)\)\)(.*)$", re.M)
missing = []
for d in ("examples", "harness/tools", "research", "site"):
    for f in sorted((ROOT / d).rglob("*.py")):
        if ".venv" in f.parts:
            continue
        text = f.read_text(encoding="utf-8")
        puts = [
            m
            for m in PUTS.finditer(text)
            if not m.group(1).endswith('"scripts"')
            and ("harness" in m.group(1) or "HARNESS" in m.group(1) or "evaluation_harness" in m.group(2))
        ]
        if puts and "from evaluation_harness" in text and 'os.environ.setdefault("EVAL_HOME"' not in text:
            missing.append(str(f.relative_to(ROOT)))
check(
    "every script outside harness/ that imports the package names harness/ as its project",
    not missing,
    missing,
)

env = {k: v for k, v in os.environ.items() if not k.startswith("EVAL_")}
r = subprocess.run(
    [sys.executable, "examples/reproduce.py", "list"], cwd=ROOT, env=env, capture_output=True, text=True,
    stdin=subprocess.DEVNULL, timeout=120,
)  # fmt: skip
check(
    "reproduce.py run from the repository's root, no EVAL_HOME, finds the project",
    r.returncode == 0 and "scifact" in r.stdout,
    (r.returncode, r.stderr[-300:]),
)
sys.exit(summary())
