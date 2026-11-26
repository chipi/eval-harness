#!/usr/bin/env python3
"""The tests share the machine they run on (homelab, 2026-11-26: a test run on the X3, 32 CPUs, starved robotics-lab
of CPU on 2026-11-24).

    python tests/test_share.py

- tests/_share.py: on a machine of more than 8 CPUs the runners run 4 suites side by side, not one per CPU;
  EVH_TEST_JOBS overrides it; a small machine (CI's 4) keeps its count;
- share() lowers the run's priority once (EVH_TEST_NICE, default 10; 0 leaves it), never twice when a runner starts
  another, and caps each test process's permutation workers (stats.py's EVH_WORKERS) at 2 on a big machine, unless
  set;
- self_test.py, store_matrix.py and test_data_mutations.py take their worker counts from it.
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
from evaluation_harness._check import check, summary  # noqa: E402

if not (HERE / "_share.py").is_file():
    check("tests/_share.py exists", False)
    sys.exit(summary())


def probe(env: dict, cpus: int) -> list[str]:
    """jobs(), EVH_WORKERS, the niceness gained in a fresh process that thinks it has `cpus` CPUs after share() called
    twice, and the most +10 can gain from where it started (19 is the ceiling: a run started under `nice` or by a niced
    runner, as the store matrix starts this file, has less room)."""
    code = (
        f"import os, sys; sys.path.insert(0, {str(HERE)!r}); import _share; _share.cpus = lambda: {cpus}; "
        "before = os.nice(0); _share.share(); _share.share(); "
        "print(_share.jobs(), _share.jobs(6), os.environ.get('EVH_WORKERS', '-'), os.nice(0) - before, min(10, 19 - before))"
    )
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("EVH_TEST_", "EVH_WORKERS"))}
    r = subprocess.run(
        [sys.executable, "-c", code],
        env={**clean, **env},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return r.stdout.split() or [r.stderr[-300:]]


check(
    "the X3 (32 CPUs): 4 suites side by side, the stats workers 2, niceness +10",
    (got := probe({}, 32))[:3] == ["4", "4", "2"] and got[3:4] == got[4:5],
    probe({}, 32),
)
check(
    "EVH_TEST_JOBS overrides the count; EVH_WORKERS set stays; EVH_TEST_NICE=0 leaves the priority",
    probe({"EVH_TEST_JOBS": "12", "EVH_WORKERS": "6", "EVH_TEST_NICE": "0"}, 32)[:4]
    == ["12", "12", "6", "0"],
    probe({"EVH_TEST_JOBS": "12", "EVH_WORKERS": "6", "EVH_TEST_NICE": "0"}, 32),
)
check(
    "CI's runner (4 CPUs): its own count, a runner's default kept, the stats workers its own",
    (got := probe({}, 4))[:3] == ["4", "6", "-"] and got[3:4] == got[4:5],
    probe({}, 4),
)
check(
    "a runner started by a runner is not lowered again (the niceness is taken once)",
    probe({"EVH_TEST_NICED": "1"}, 32)[3:4] == ["0"],
    probe({"EVH_TEST_NICED": "1"}, 32),
)
for f, needles in (
    ("tests/self_test.py", ("_share.jobs()", "_share.share()")),
    ("tools/store_matrix.py", ("_share.jobs(6)", "_share.share()")),
    ("tests/test_data_mutations.py", ("_share.jobs()",)),  # run by self_test or store_matrix, which share()
):
    text = (HARNESS / f).read_text(encoding="utf-8")
    check(f"{f} takes its worker count from tests/_share.py", all(n in text for n in needles))
sys.exit(summary())
