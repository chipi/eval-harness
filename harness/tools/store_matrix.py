#!/usr/bin/env python3
"""Every test file in both stores (RFC-025): `tests/test_*.py` run with EVAL_STORE=files and again with
EVAL_STORE=sqlite, a few at a time, each in its own process. Prints one line per file and store as it finishes and a
table of the files whose result differs between the stores at the end; exits 1 when a file fails in either store.

    python tools/store_matrix.py [--jobs 6] [--only PATTERN] [--store sqlite] [--log DIR]

A test that builds its own project inherits EVAL_STORE; one that pins its store (test_store, test_outputs) keeps it.
The log of each run is kept in --log (default .build/store-matrix/).
"""

import argparse
import fnmatch
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]

#: Files that are not tests of the store's behaviour: a browser (needs Chromium, the browser gate runs them), the whole
#: self-test (it runs every file here, and checks this repository's own committed data, which is files), and the
#: inspector's budget (this repository's runs, files; its own CI job; two runs at once share .build/budget-catalog).
SKIP = ("test_*_browser.py", "self_test.py", "test_catalog_real_browser.py", "test_inspector_budget.py")


def run(test: Path, store: str, log: Path) -> tuple[str, str, int, float]:
    """One test file in one store, its output kept in `log`: (file, store, exit code, seconds)."""
    env = {k: v for k, v in os.environ.items() if k != "EVAL_STORE"}
    env["EVAL_STORE"] = store
    t0 = time.time()
    try:
        r = subprocess.run(  # nosec B603 - this interpreter and our own test files
            [sys.executable, str(test)], cwd=HARNESS, env=env, capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=1800, check=False,
        )  # fmt: skip
        code, out = r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:

        def text(x: str | bytes | None) -> str:
            return x.decode(errors="replace") if isinstance(x, bytes) else (x or "")

        code, out = 124, f"{text(e.stdout)}{text(e.stderr)}\nTIMEOUT after 1800 s"
    (log / f"{test.stem}.{store}.log").write_text(out if isinstance(out, str) else str(out))
    return test.name, store, code, time.time() - t0


def main() -> int:
    """Every test file in each store asked for, a few at a time; 1 when any fails."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--only", default="test_*.py", help="which test files (a glob on the name)")
    ap.add_argument("--store", action="append", choices=("files", "sqlite"), help="default: both")
    ap.add_argument("--log", default=str(HARNESS / ".build" / "store-matrix"))
    args = ap.parse_args()
    log = Path(args.log)
    log.mkdir(parents=True, exist_ok=True)
    tests = sorted(
        p for p in (HARNESS / "tests").glob(args.only) if not any(fnmatch.fnmatch(p.name, s) for s in SKIP)
    )
    stores = args.store or ["files", "sqlite"]
    got: dict[tuple[str, str], int] = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futs = [pool.submit(run, t, s, log) for t in tests for s in stores]
        for f in as_completed(futs):
            name, store, code, secs = f.result()
            got[(name, store)] = code
            print(f"{'ok  ' if code == 0 else 'FAIL'} {store:6} {name} ({secs:.0f} s)", flush=True)
    differ = [t.name for t in tests if len({got[(t.name, s)] == 0 for s in stores}) > 1]
    failed = sorted({n for (n, _s), c in got.items() if c != 0})
    print(f"\n{len(tests)} test files × {len(stores)} store(s); failing: {len(failed)}")
    for n in differ:
        print(
            f"  differs between the stores: {n} ("
            + ", ".join(f"{s} {'ok' if got[(n, s)] == 0 else 'FAIL'}" for s in stores)
            + ")"
        )
    for n in failed:
        if n not in differ:
            print(f"  fails in every store: {n}")
    print(f"logs: {log}")
    print("STORE MATRIX: " + ("PASS" if not failed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
