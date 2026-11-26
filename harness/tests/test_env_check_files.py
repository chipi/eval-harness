#!/usr/bin/env python3
"""`evh env-check` says which file it read, and never prints a key.

python tests/test_env_check_files.py
"""

import os
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _tmp  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(_tmp.mkdtemp(prefix="evh-envcheck-"))
(proj / "data").mkdir()
SECRET = "sk-test-not-printed"
(proj / ".env").write_text(f"OPENROUTER_API_KEY={SECRET}\n", encoding="utf-8")
env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and k != "EVAL_MAX_COST_USD"}
env.update(EVH_ACTOR="person:test", EVAL_HOME=str(proj))
r = subprocess.run(
    [sys.executable, str(HARNESS / "scripts" / "cli.py"), "env-check"],
    cwd=proj,
    env=env,
    capture_output=True,
    text=True,
    timeout=120,
    stdin=subprocess.DEVNULL,
    encoding="utf-8",
)
out = r.stdout
check(
    "env-check names the files it read, plainly",
    "files read:" in out and str(proj / ".env") in out.split("files read:")[1].splitlines()[0],
    out[:400],
)
check("env-check says no other file is read", "no system names a key_file" in out, out[:400])
check("env-check prints no key", SECRET not in out)
sys.exit(summary())
