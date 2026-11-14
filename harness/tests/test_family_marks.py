#!/usr/bin/env python3
"""family-test says per row whether a p is exact or a seeded estimate. $0, offline.

    python tests/test_family_marks.py

Opponents can share different numbers of items with the arm under test, so one family can
hold an exact p (30 items or fewer) and an estimate (more). The header used to state one for
the whole family, read from whichever row sorted first.
"""

import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runfix  # noqa: E402
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-family-"))
env = {k: v for k, v in os.environ.items() if not k.startswith("EVAL_") or k == "EVAL_STORE"}
env.update(EVAL_HOME=str(proj))


def run(config, items):
    rng = random.Random(config)
    _runfix.put_run(
        proj / "data",
        {
            "run_id": f"{config}_1",
            "dataset_id": "ds",
            "config_id": config,
            "primary_metric": "acc",
            "scores": {"acc": 0.5},
        },
        "".join(json.dumps({"item_id": f"i{i:03d}", "acc": rng.random()}) + "\n" for i in range(items)),
    )


try:
    run("arm_a", 50)  # the arm under test: 50 items
    run("arm_small", 12)  # shares 12 with it: exact
    run("arm_large", 50)  # shares 50: a seeded estimate
    r = subprocess.run(
        [
            sys.executable,
            str(HERE / "cli.py"),
            "family-test",
            "--dataset-id",
            "ds",
            "--a",
            "arm_a",
            "--against",
            "arm_",
        ],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
    )
    out = r.stdout + r.stderr
    small = next((ln for ln in out.splitlines() if ln.strip().startswith("arm_small")), "")
    large = next((ln for ln in out.splitlines() if ln.strip().startswith("arm_large")), "")
    check("family-test ran on a mixed family", r.returncode == 0, out[-500:])
    check(
        "the header says both kinds are in the family",
        "a seeded estimate above" in out and "marked ~" in out,
        out[:600],
    )
    check(
        "the estimated row is marked ~, the exact one is not",
        "~" in large and "~" not in small,
        small + " | " + large,
    )

    # Runs that disagree on a metric's direction, or on the primary metric, are named, not
    # settled silently by whichever was listed first.
    import contextlib
    import io

    from evaluation_harness import _runs

    err = io.StringIO()
    runs = [
        (Path("r1"), {"metric_directions": {"acc": "lower"}}),
        (Path("r2"), {"metric_directions": {"acc": "higher"}}),
    ]
    with contextlib.redirect_stderr(err):
        got = _runs.recorded_direction(runs, "acc")
    check(
        "runs that disagree on a direction are named",
        got == "lower" and "disagree on which way acc" in err.getvalue(),
        err.getvalue(),
    )
    _runfix.put_run(
        proj / "data",
        {
            "run_id": "arm_b_1",
            "dataset_id": "ds",
            "config_id": "arm_b",
            "primary_metric": "f1",
            "scores": {"f1": 0.5},
        },
    )
    err = io.StringIO()
    with contextlib.redirect_stderr(err), _runstore._InProject(proj):
        _runs.default_metric("ds")
    check(
        "runs that declare different primary metrics are named",
        "different primary metrics" in err.getvalue(),
        err.getvalue(),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
