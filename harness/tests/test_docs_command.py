#!/usr/bin/env python3
"""`evh docs`: the docs that ship in the wheel, listed, located and printable; `evh --help` starts with where to start.

python tests/test_docs_command.py
"""

import os
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HARNESS / "tools"))
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.cli import COMMANDS  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _tmp
import _tmp  # noqa: E402

proj = Path(_tmp.mkdtemp(prefix="evh-docs-"))
(proj / "data").mkdir()
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj))
env.pop("EVAL_DATA_DIR", None)
SITE = "https://evals.humancopilot.eu/docs/"


def evh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
        encoding="utf-8",
    )


check("docs is a registered command", "docs" in COMMANDS)

r = evh("docs")
check(
    "docs: lists the three, with the site",
    r.returncode == 0 and SITE in r.stdout,
    (r.returncode, r.stdout[:300]),
)
for name in ("UPGRADING", "RUNBOOK", "INTEGRATION"):
    check(f"docs: lists {name}", f"{name}.md" in r.stdout, r.stdout[:300])

r = evh("docs", "upgrading")
check(
    "docs upgrading: path and the site's URL",
    r.returncode == 0 and "UPGRADING.md" in r.stdout and SITE + "harness/UPGRADING/" in r.stdout,
    r.stdout,
)
r = evh("docs", "Runbook.MD")
check(
    "docs Runbook.MD: case and suffix free",
    r.returncode == 0 and SITE + "harness/RUNBOOK/" in r.stdout,
    r.stdout,
)

r = evh("docs", "integration", "--print")
text = (HARNESS / "docs" / "INTEGRATION.md").read_text(encoding="utf-8")
check(
    "docs --print: the file's text on stdout",
    r.returncode == 0 and r.stdout.strip() == text.strip(),
    r.stderr[:200],
)

r = evh("docs", "nope")
check(
    "docs nope: refused, naming the known ones",
    r.returncode != 0 and all(n in r.stdout + r.stderr for n in ("upgrading", "runbook", "integration")),
    (r.returncode, r.stderr[:300]),
)

import zipfile  # noqa: E402

import _wheel  # noqa: E402

with zipfile.ZipFile(_wheel.wheel()) as z:
    names = set(z.namelist())
for n in ("UPGRADING", "RUNBOOK", "INTEGRATION"):
    check(f"the wheel ships docs/{n}.md", f"evaluation_harness/docs/{n}.md" in names)
check(
    "the wheel ships no other doc",
    not {n for n in names if n.startswith("evaluation_harness/docs/")}
    - {f"evaluation_harness/docs/{n}.md" for n in ("UPGRADING", "RUNBOOK", "INTEGRATION")},
)

r = evh("--help")
out = r.stdout
start, rest = out.find("Start here"), out.find("All commands:")
block = out[start:rest] if 0 <= start < rest else ""
check(
    "--help: a Start here block comes before the full list",
    0 <= start < rest < out.find("\n  env-check"),
    out[:200],
)
firsts = ["init", "dataset-create", "dataset-materialize", "run", "leaderboard", "catalog-serve", "docs"]
at = [block.find(f"evh {c}") for c in firsts]
check("--help: the block names the first commands, in order", -1 not in at and at == sorted(at), at)
check(
    "--help: the full list is still there",
    all(f"\n  {c} " in out[rest:] for c in COMMANDS),
    out[rest : rest + 80],
)

sys.exit(summary())
