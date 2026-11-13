#!/usr/bin/env python3
"""Every refusal names its kind (RUNBOOK, Refusals): `ERROR (<kind>): <why>`.

    python tests/test_refusal_kinds.py

A script or an agent branches on the kind, so a message can be reworded without breaking it.
Read from the source: every `die(...)` in the package, its tools and the examples passes a kind
the registry knows as a literal, and no evh command (scripts/) refuses with a bare
`SystemExit("...")`, which carries no kind. The repository's own tools and the examples' fetch
scripts still may: they are not evh commands. Then one command refuses for real.
"""

import ast
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
ROOT = HARNESS.parent
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness._common import REFUSALS, die  # noqa: E402

files = [
    *sorted((HARNESS / "scripts").glob("*.py")),
    *sorted((HARNESS / "tools").glob("*.py")),
    *sorted(p for p in (ROOT / "examples").rglob("*.py") if ".venv" not in p.parts),
]
no_kind, unknown, bare = [], [], []
n = 0
for f in files:
    src = f.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        where = f"{f.relative_to(ROOT)}:{node.lineno}"
        if node.func.id == "die":
            n += 1
            if len(node.args) != 2 or not isinstance(node.args[1], ast.Constant):
                no_kind.append(where)
            elif node.args[1].value not in REFUSALS:
                unknown.append(f"{where} {node.args[1].value!r}")
        elif node.func.id == "SystemExit" and node.args and f.parent.name == "scripts":
            arg = node.args[0]
            text = isinstance(arg, (ast.JoinedStr, ast.BinOp)) or (
                isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            )
            the_one_in_die = f.name == "_common.py" and "ERROR (" in (ast.get_source_segment(src, arg) or "")
            if text and not the_one_in_die:
                bare.append(where)

check(f"every die() of {n} names a kind as a literal", not no_kind, no_kind[:10])
check("every kind is one of REFUSALS", not unknown, unknown[:10])
check("no refusal is a bare SystemExit(text)", not bare, bare[:10])
try:
    die("x", "no-such-kind")
except ValueError:
    check("die() with an unknown kind is a bug, not a refusal", True)
except SystemExit:
    check("die() with an unknown kind is a bug, not a refusal", False)

runbook = (HARNESS / "docs" / "RUNBOOK.md").read_text(encoding="utf-8").split("## Refusals", 1)[-1]
documented = dict(re.findall(r"^\| `([a-z-]+)` \| (.+?) \|$", runbook.split("\n## ", 1)[0], re.M))
check("the Runbook's Refusals table is REFUSALS, word for word", documented == REFUSALS, documented)

proj = Path(tempfile.mkdtemp(prefix="evh-refusal-"))
(proj / "data").mkdir()
env = dict(os.environ, EVAL_HOME=str(proj))
for k in ("EVAL_DATA_DIR",):
    env.pop(k, None)
r = subprocess.run(
    [sys.executable, str(HARNESS / "scripts" / "cli.py"), "goals", "--goal", "no_such_goal"],
    cwd=proj,
    env=env,
    capture_output=True,
    text=True,
    stdin=subprocess.DEVNULL,
)
check(
    "a refusal prints its kind: `ERROR (not-found): no goal ...`, exit 1",
    r.returncode == 1 and r.stderr.strip().splitlines()[-1].startswith("ERROR (not-found): no goal"),
    r.stderr[-200:],
)
sys.exit(summary())
