#!/usr/bin/env python3
"""The release smoke (tools/release_smoke.py, `make release-smoke`) is wired, without running the whole of it.

    python tests/test_release_smoke.py

Its --help and --list name every check (the version, the wheel's install, the newcomer's project per store, the
servers, the deployment); a wrong expected version fails its check, prints a FAIL line and the verdict
`RELEASE SMOKE: FAIL (n of m)` and exits 1; the right one passes the version check alone; an unknown check is
refused; and the root Makefile has the target and lists it in `make help`. The wheel, the venv and the servers are
the smoke's own run (RELEASING.md), not this test's.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
REPO = HARNESS.parent
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

SMOKE = HARNESS / "tools" / "release_smoke.py"


def run(*args: str) -> tuple[int, str]:
    """The smoke with `args`; (exit code, both streams)."""
    r = subprocess.run(
        [sys.executable, str(SMOKE), *args], capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    return r.returncode, r.stdout + r.stderr


PHRASES = {
    "1": ("version agreement", "CHANGELOG", "UPGRADING", "pin"),
    "2": ("build and install", "wheel", "fresh venv", "evh docs"),
    "3": ("newcomer path", "files then sqlite", "run --dry-run", "leaderboard", "validate"),
    "4": ("servers", "catalog-serve", "/api/v1/goals", "/workbench/", "mcp --http", "--no-agent-tools"),
    "5": ("the deployment", "render.sh", "smoke_release.py", "headers_check.py"),
}

code, helptext = run("--help")
check("--help exits 0 and shows the verdict line and the flags", code == 0 and "RELEASE SMOKE: PASS" in helptext
      and all(f in helptext for f in ("--list", "--only", "--expect-version", "--release", "--online-deps")), helptext[:300])  # fmt: skip
code, listing = run("--list")
rows = dict(re.findall(r"^(\d)  (.*)$", listing, re.M))
check(
    "--list prints the five checks, in order, and runs none",
    code == 0 and list(rows) == list("12345"),
    listing,
)
for n, words in PHRASES.items():
    missing = [w for w in words if w not in helptext or w not in rows.get(n, "")]
    check(f"check {n} is named in --help and --list ({words[0]})", not missing, missing)

code, out = run("--only", "1", "--expect-version", "0.0.0")
fails = re.findall(r"^\s*FAIL\s", out, re.M)
verdict = re.search(r"^RELEASE SMOKE: FAIL \((\d+) of (\d+)\)$", out, re.M)
check(
    "a wrong expected version: exit 1, FAIL lines, and a verdict that counts them",
    code == 1 and bool(fails) and verdict is not None and int(verdict.group(1)) == len(fails),
    out[-600:],
)
check(
    "the failing line names the version it wanted",
    "0.0.0" in out and "_version.py is 0.0.0" in out,
    out[-600:],
)

code, out = run("--only", "1")
check(
    "the right version: the version check passes alone, exit 0",
    code == 0 and out.rstrip().endswith("RELEASE SMOKE: PASS"),
    out[-600:],
)
code, out = run("--only", "9")
check("an unknown check is refused, not skipped", code == 2 and "unknown check" in out, out[-300:])

makefile = (REPO / "Makefile").read_text(encoding="utf-8")
check(
    "the root Makefile has the release-smoke target, on .PHONY, running the script",
    re.search(r"^release-smoke:.*\n\t.*release_smoke\.py", makefile, re.M) is not None
    and re.search(r"^\.PHONY:.*\brelease-smoke\b", makefile, re.M) is not None,
)
helped = subprocess.run(
    ["make", "-s", "-C", str(REPO), "help"], capture_output=True, text=True, encoding="utf-8"
).stdout
check("`make help` lists it", "make release-smoke" in helped, helped[-400:])
check("the script is executable", SMOKE.stat().st_mode & 0o111 != 0)
sys.exit(summary("test_release_smoke"))
