#!/usr/bin/env python3
"""The project's one pick list under writers at once (RFC-026's locks; a review, 2026-11-11).

    python tests/test_picks_concurrent.py

data/picks.jsonl is one list per project, appended by `pick` and by `dataset-extend --picks`. In the SQLite store an
append is a read and a rewrite, so two writers at once could each write back what they read and lose the other's lines;
`pick` locked per dataset and `dataset-extend` not at all. Eight processes append 25 lines each at once, in both stores:
all 200 are there.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

WORKER = """
import sys, time
from evaluation_harness import _picks
start = float(sys.argv[2])
while time.time() < start:
    time.sleep(0.001)
for i in range(25):
    _picks.append([{"action": "pick", "from": "d", "item": f"w{sys.argv[1]}-{i}", "for": "v2"}])
"""
COUNT = """
from evaluation_harness import _picks
print(len(_picks.lines()))
"""

for store in ("files", "sqlite"):
    proj = Path(tempfile.mkdtemp(prefix="evh-picks-"))
    try:
        (proj / "data").mkdir()
        (proj / "worker.py").write_text(WORKER)
        (proj / "count.py").write_text(COUNT)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("EVAL_", "EVH_"))}
        env.update(EVAL_HOME=str(proj), EVAL_STORE=store, PYTHONPATH=str(HARNESS))

        start = time.time() + 2.0
        procs = [
            subprocess.Popen(
                [sys.executable, str(proj / "worker.py"), str(n), str(start)],
                cwd=proj,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for n in range(8)
        ]
        errs = [p.communicate(timeout=120)[1] for p in procs]
        r = subprocess.run(
            [sys.executable, str(proj / "count.py")], cwd=proj, env=env, capture_output=True, text=True
        )
        n_lines = int(r.stdout.strip() or 0) if r.returncode == 0 else -1
        check(
            f"{store}: eight writers at once, 25 picks each: every one of the 200 lines kept",
            n_lines == 200 and all(p.returncode == 0 for p in procs),
            (n_lines, [e[-200:] for e in errs if e.strip()][:2], r.stderr[-200:]),
        )
    finally:
        shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
