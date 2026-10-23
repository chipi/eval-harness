#!/usr/bin/env python3
"""`evh self-test`: does the installed harness work here?

    evh self-test

In a checkout of eval-harness this is the full development suite (self_test.py, also `make
test`). In a project that pins the package, that suite cannot run: it checks this
repository's own reports, runs and examples. What an upgrading project needs to know is
whether the package works in its environment, so here it runs, $0 and offline:

  - the paired test's own suite (test_stats.py), shipped in the package;
  - the tutorial end to end in a scratch folder, never in your project: init, a dataset with
    fields, materialize, two arms with repeats, pair-test on the recorded primary metric,
    rescore against gold, validate, catalog.

Every step must finish without a traceback. Exit 0 when all pass.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def in_checkout() -> bool:
    """Check whether we are running in an eval-harness checkout."""
    return (
        (HERE.parent / "Makefile").is_file()
        and (HERE.parent / "pyproject.toml").is_file()
        and (HERE.parent / "tests" / "self_test.py").is_file()
    )


def main() -> int:
    """Run a self-test of the installed harness."""
    sys.path.insert(0, str(HERE))
    from _common import no_options  # noqa: PLC0415

    no_options(__doc__)
    if in_checkout():
        return subprocess.run([sys.executable, str(HERE.parent / "tests" / "self_test.py")]).returncode
    print("evaluation-harness self-check (the installed package, in a scratch folder; $0, offline)\n")
    results = []

    def step(label: str, cmd: list, cwd: Path, env: dict) -> bool:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=900)
        out = r.stdout + r.stderr
        good = r.returncode == 0 and "Traceback" not in out
        results.append(good)
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good:
            print("       " + "\n       ".join(out.strip().splitlines()[-8:]))
        return good

    tmp = Path(tempfile.mkdtemp(prefix="evh-self-check-"))
    try:
        env = {
            **os.environ,
            "EVAL_HOME": str(tmp),
            "PYTHONDONTWRITEBYTECODE": "1",
            "EVAL_BUILD_REF": "self-check",
            "EVAL_MAX_COST_USD": "",
        }
        for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR"):
            env.pop(k, None)
        evh = [sys.executable, "-m", "evaluation_harness"]
        step(
            "the paired test's own suite (test_stats.py)",
            [sys.executable, str(HERE / "test_stats.py")],
            tmp,
            env,
        )
        if step("init --tutorial", [*evh, "init", "--tutorial"], tmp, env):
            shutil.copy(tmp / "tutorial/fields/tickets.yaml", tmp / "data/fields/")
            for f in (tmp / "tutorial/configs").glob("tickets_lead*.yaml"):
                if "noisy" not in f.name:
                    shutil.copy(f, tmp / "data/configs/")
            shutil.copytree(tmp / "tutorial/gold", tmp / "data/references/gold/tickets_v1")
            steps = [
                (
                    "dataset-create with fields",
                    [
                        "dataset-create",
                        "--dataset-id",
                        "tickets_v1",
                        "--source-dir",
                        "tutorial/tickets",
                        "--fieldset",
                        "tickets",
                        "--fields",
                        "tutorial/ticket_fields.csv",
                    ],
                ),
                ("dataset-materialize", ["dataset-materialize", "--dataset-id", "tickets_v1"]),
                (
                    "experiment-run lead1 x2",
                    ["experiment-run", "--config", "data/configs/tickets_lead1.yaml", "--repeat", "2"],
                ),
                (
                    "experiment-run lead2 x2",
                    ["experiment-run", "--config", "data/configs/tickets_lead2.yaml", "--repeat", "2"],
                ),
                (
                    "pair-test on the recorded primary metric",
                    [
                        "pair-test",
                        "--dataset-id",
                        "tickets_v1",
                        "--a",
                        "tickets_lead2_v1",
                        "--b",
                        "tickets_lead1_v1",
                    ],
                ),
                (
                    "rescore against gold",
                    [
                        "rescore",
                        "--dataset-id",
                        "tickets_v1",
                        "--reference-id",
                        "gold/tickets_v1",
                        "--out",
                        "data/runs-gold",
                    ],
                ),
                ("validate", ["validate"]),
                ("catalog", ["catalog"]),
            ]
            for label, args in steps:
                if not step(label, evh + args, tmp, env):
                    break
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    failed = results.count(False)
    print(
        f"\nself-check: {len(results) - failed}/{len(results)} passed"
        + ("" if not failed else " — the harness does not work as installed here; the lines above say where")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
