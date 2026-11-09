#!/usr/bin/env python3
"""Every `evh <command> --help` names the command, not the script behind it.

    python tests/test_help_names.py

43 of the 67 commands printed argparse's default, the script's file name: `evh run-promote
--help` said `usage: promote_baseline.py`, which is nothing a person or an agent can type.
"""

import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.cli import COMMANDS  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-help-"))
(proj / "data").mkdir()
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj))
env.pop("EVAL_DATA_DIR", None)
env.pop("EVAL_RUNS_DIR", None)


def usage(name: str) -> tuple[str, int, str]:
    r = subprocess.run(
        [sys.executable, str(HERE / "cli.py"), name, "--help"],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
    )
    first = next((ln for ln in r.stdout.splitlines() if ln.strip()), "")
    return name, r.returncode, first


with ThreadPoolExecutor(max_workers=8) as pool:
    for name, code, first in pool.map(usage, COMMANDS):
        check(
            f"evh {name} --help: exit 0, `usage: evh {name}`",
            code == 0 and first.startswith(f"usage: evh {name}"),
            (code, first[:100]),
        )

sys.exit(summary())
