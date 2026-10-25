#!/usr/bin/env python3
"""A project's own module never replaces one of the harness's, and the harness's never replaces
a project's. $0, offline.

    python tests/test_no_shadowing.py

The package imported its siblings as bare top-level names (`import stats`), with its own
directory on sys.path: a project with a `stats.py` first on the path silently replaced the
harness's paired test inside `evaluation_harness.judging`, and under `evh` the harness's
`adapter`, `stats` or `rounds` hid a project's module of that name. Now the package imports
itself as `evaluation_harness.*`.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-shadow-"))
try:
    (proj / "stats.py").write_text("WHO = 'the project'\n")
    (proj / "adapter.py").write_text("WHO = 'the project'\n")
    probe = proj / "probe.py"
    probe.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(proj)!r})\n"  # the project first, as a project's own code runs
        f"sys.path.insert(1, {str(HERE.parent)!r})\n"
        "import evaluation_harness.judging as j\n"
        "import evaluation_harness.stats as s\n"
        "print('judging.stats is the harness:', j._stats is s)\n"
        "import evaluation_harness._adapter as a\n"
        "a.module_at(a.BUNDLED)\n"  # the bundled adapter, as a run without one loads it
        "import stats, adapter\n"
        "print('bare stats is the project:', getattr(stats, 'WHO', None) == 'the project')\n"
        "print('bare adapter is the project:', getattr(adapter, 'WHO', None) == 'the project')\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("EVAL_") and k != "PYTHONPATH"}
    r = subprocess.run([sys.executable, str(probe)], cwd=proj, env=env, capture_output=True, text=True)
    out = r.stdout + r.stderr
    check(
        "the harness's judging uses the harness's stats, not a project's stats.py",
        "judging.stats is the harness: True" in out,
        out[-500:],
    )
    check("a project's own stats.py is the project's", "bare stats is the project: True" in out, out[-500:])
    check(
        "a project's own adapter.py is the project's, after the harness loaded its bundled one",
        "bare adapter is the project: True" in out,
        out[-500:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
