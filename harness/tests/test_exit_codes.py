#!/usr/bin/env python3
"""The exit codes a run ends with (RUNBOOK, Exit codes): one meaning each.

    python tests/test_exit_codes.py

In a throwaway project with the tutorial's six tickets and an adapter that costs $0.01 a call:
a run the cost cap stops after some items exits 4 (stopped early, partial results kept), a cap
that stops it before any item exits 7 (nothing measured), a run under no cap exits 0, an
unknown argument 2, and `validate` over a broken tree 6, not 1 (a refusal). Before 0.8.0 the
cap's partial stop was 2, the same number as a usage error, and nothing tested it.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
KIT = HERE.parent / "tutorial"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-exit-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-exit-codes")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args, **extra):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env={**env, **extra},
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )


try:
    data = proj / "data"
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    (data / "systems").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    (proj / "priced_adapter.py").write_text(
        "from evaluation_harness.adapter import Result, score  # noqa: F401  (score: the bundled overlap)\n\n\n"
        "def call_system(text, params):\n"
        "    return Result(output=text[:80], cost_usd=0.01)\n",
        encoding="utf-8",
    )
    _runstore.write_text(
        proj,
        "systems/priced_v1.yaml",
        "system_id: priced_v1\nadapter: priced_adapter.py\nparams: {}\n",
    )

    r = evh("run", "--system", "priced_v1", "--dataset", "tickets_v1", EVAL_MAX_COST_USD="0.025")
    out = r.stdout + r.stderr
    check(
        "the cost cap stops a run after some items: exit 4",
        r.returncode == 4,
        f"exit {r.returncode}: {out[-300:]}",
    )
    check(
        "... and says so, keeping the partial results", "COST CAP HIT" in out and "exit 4" in out, out[-300:]
    )

    r = evh("run", "--system", "priced_v1", "--dataset", "tickets_v1", EVAL_MAX_COST_USD="0")
    check(
        "a cap that stops it before any item: exit 7 (nothing measured)",
        r.returncode == 7,
        f"exit {r.returncode}",
    )

    r = evh("run", "--system", "priced_v1", "--dataset", "tickets_v1", EVAL_MAX_COST_USD="5")
    check("under the cap: exit 0", r.returncode == 0, (r.stdout + r.stderr)[-300:])

    r = evh("run", "--system", "priced_v1", "--dataset", "tickets_v1", "--no-such-flag")
    check("an unknown argument: exit 2", r.returncode == 2 and "usage: evh run" in r.stderr, r.stderr[-200:])

    r = evh("datasets", "--dataset-id", "no_such_dataset")
    check("a refusal: exit 1 with its ERROR line", r.returncode == 1 and "ERROR" in r.stderr, r.stderr[-200:])

    _runstore.write_text(proj, "datasets/tickets_v1.json", "{not json")
    r = evh("validate")
    check(
        "validate over a broken tree: exit 6, the file named, every later check still run",
        r.returncode == 6
        and "VALIDATION FAILED" in r.stdout
        and "tickets_v1.json: does not parse" in r.stdout
        and " V4 " in r.stdout
        and "Traceback" not in r.stderr,
        f"exit {r.returncode}: {(r.stdout + r.stderr)[-300:]}",
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
