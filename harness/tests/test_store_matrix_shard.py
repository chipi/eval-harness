#!/usr/bin/env python3
"""`tools/store_matrix.py --shard I/N` is a split: every test file is in exactly one part, the parts are about as long as
each other, and the split is the same every time and on every machine (CI runs each part in a job of its own).

    python tests/test_store_matrix_shard.py
"""

import argparse
import fnmatch
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

spec = importlib.util.spec_from_file_location("store_matrix", HARNESS / "tools" / "store_matrix.py")
assert spec and spec.loader
SM = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SM)

tests = sorted(
    p for p in (HARNESS / "tests").glob("test_*.py") if not any(fnmatch.fnmatch(p.name, s) for s in SM.SKIP)
)
weight = lambda t: SM.SECONDS.get(t.name, SM.DEFAULT_SECONDS)  # noqa: E731

for parts in (1, 2, 3, 4):
    got = [SM.shard(tests, i, parts) for i in range(1, parts + 1)]
    flat = [t for part in got for t in part]
    check(
        f"{parts} part(s): every test file is in exactly one",
        sorted(flat) == tests and len(flat) == len(set(flat)),
        (len(flat), len(tests)),
    )
    loads = [sum(weight(t) for t in part) for part in got]
    check(
        f"{parts} part(s): the longest and the shortest differ by no more than the longest file",
        max(loads) - min(loads) <= max(weight(t) for t in tests),
        loads,
    )
    check(
        f"{parts} part(s): the same split the second time",
        got == [SM.shard(tests, i, parts) for i in range(1, parts + 1)],
    )

check(
    "a file the table names is a file of tests/",
    all((HARNESS / "tests" / n).is_file() for n in SM.SECONDS),
    [n for n in SM.SECONDS if not (HARNESS / "tests" / n).is_file()],
)

bad = []
for text in ("0/2", "3/2", "x", "1", "1/x"):
    try:
        SM.parse_shard(text)
    except argparse.ArgumentTypeError:
        continue
    bad.append(text)
check("--shard refuses 0/2, 3/2, x, 1 and 1/x", not bad, bad)
check("--shard 2/3 is (2, 3)", SM.parse_shard("2/3") == (2, 3), SM.parse_shard("2/3"))

with tempfile.TemporaryDirectory() as tmp:
    env = {k: v for k, v in os.environ.items() if k != "EVAL_STORE"}
    r = subprocess.run(  # nosec B603 - this interpreter and the tool under test
        [sys.executable, str(HARNESS / "tools" / "store_matrix.py"), "--store", "sqlite", "--jobs", "1", "--only", "test_card.py", "--shard", "1/1", "--log", tmp],
        cwd=HARNESS, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300, check=False, encoding="utf-8",
    )  # fmt: skip
    check(
        "the matrix runs a shard: one file of one part, and passes",
        r.returncode == 0 and "1 test files × 1 store(s)" in r.stdout and "STORE MATRIX: PASS" in r.stdout,
        (r.stdout + r.stderr)[-400:],
    )

sys.exit(summary())
