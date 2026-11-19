#!/usr/bin/env python3
"""The Workbench's production screen replays the code that ran (W3; RFC-030, RFC-031): $0 and offline.

    python tests/test_workbench_replay_browser.py

The replay example (examples/replay-filing), set up as test_replay.py sets it up: a filing system with three commits,
production's 20 decisions captured, made a dataset and run as production's recorded arm. Behind a real catalog-serve,
on the goal's production screen: the code record's periods and its (still empty) faithfulness are read; the replay's
plan is seen first (POST /estimate, the faithfulness dry run: 20 decisions, nothing called); the replay runs as a job
under a cap and its faithfulness record is written; read again, the record says what the replay found.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
EXAMPLE = HARNESS.parent / "examples" / "replay-filing"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _signin
import _serve  # noqa: E402
import _signin  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-wbreplay-"))
os.environ.setdefault("EVAL_STORE", "files")  # a project names its store; the suite's own, else files
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-wb-replay")
env["PYTHONPATH"] = str(HARNESS) + os.pathsep + env.get("PYTHONPATH", "")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVH_PUBLIC"):
    env.pop(k, None)
MINE = proj / "examples" / "replay-filing"


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project."""
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def serve() -> tuple[subprocess.Popen, int, list[str]]:
    """catalog-serve on a free port; its startup lines once it answers."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    lines: list[str] = []
    assert p.stdout is not None
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    return p, port, _serve.startup(p, lines)  # its start-up lines, the rest read as it comes


try:
    (proj / "data").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(EXAMPLE, MINE, ignore=shutil.ignore_patterns("__pycache__"))
    made = subprocess.run(
        [sys.executable, str(MINE / "make_history.py"), "--out", "replay-filing"], cwd=proj, env=env,
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip
    steps = [
        ("capture", "--importer", "jsonl", "--query", json.dumps({"path": "replay-filing/rows.jsonl"}), "--capture", "filing_prod"),
        ("dataset-from-capture", "--capture", "filing_prod", "--dataset-id", "filing_history_v1", "--fieldset", "filing",
         "--field", "ts", "--field", "started", "--field", "production_issue"),
        ("dataset-materialize", "--dataset-id", "filing_history_v1"),
        ("run", "--system", "filing_production_v1", "--dataset", "filing_history_v1", "--goal", "filing", "--json"),
        ("catalog",),
    ]  # fmt: skip
    r = made
    prod_id = None
    for argv in steps:
        r = evh(*argv)
        if r.returncode:
            break
        if argv[0] == "run":
            prod_id = (
                ((json.loads(r.stdout).get("result") or {}).get("values") or {})
                .get("runs", [{}])[0]
                .get("run_id")
            )
    check(
        "setup: the replay example's history captured, made a dataset, production's recorded arm run",
        made.returncode == 0 and r.returncode == 0 and bool(prod_id),
        (made.stderr[-300:], r.stderr[-400:]),
    )
    code = next(
        m["model"]
        for m in json.loads(evh("model-list", "--json").stdout)["result"]["models"]
        if m.get("kind") == "code"
    )

    from playwright.sync_api import sync_playwright

    srv, port, lines = serve()
    try:
        link = _signin.link(lines)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(str(link))
            page.wait_for_selector("h1:has-text('Your goals')", timeout=20000)
            page.goto(f"http://127.0.0.1:{port}/workbench/#production/filing")
            page.wait_for_selector("#rp-read", timeout=20000)
            page.select_option("#rp-model", code)
            page.click("#rp-read")
            page.wait_for_selector("#rp-out pre", timeout=60000)
            periods = page.locator("#rp-out").inner_text()
            check(
                "the code record's periods and faithfulness are read on the production screen (periods, faithfulness-show)",
                "Its periods" in periods
                and "Its newest faithfulness record" in periods
                and len(periods) > 60,
                periods[:500],
            )
            page.fill("#pd-by", "tester")
            page.select_option("#rf-sys", "filing_replay_v1")
            page.select_option("#rf-ds", "filing_history_v1")
            page.fill("#rf-prod", str(prod_id))
            page.click("#rf-est")
            page.wait_for_selector("#rf-out pre, #rf-out [role=alert]", timeout=120000)
            plan = page.locator("#rf-out").inner_text()
            check(
                "See the plan first: the replay's dry run through POST /estimate (its decisions and commits), nothing written",
                "20" in plan and not list((proj / "data" / "faithfulness").glob("*/*.json"))
                if (proj / "data" / "faithfulness").is_dir()
                else "20" in plan,
                plan[:500],
            )
            page.click("#rf-go")
            page.wait_for_selector("#rf-out:has-text('Replayed.')", timeout=300000)
            recs = (
                sorted((proj / "data" / "faithfulness").glob("*/*.json"))
                if (proj / "data" / "faithfulness").is_dir()
                else []
            )
            check(
                "Replay it: faithfulness as a job under a cap, its record written",
                bool(recs),
                (page.locator("#rf-out").inner_text()[:400], recs),
            )
            page.click("#rp-read")
            page.wait_for_function(
                "() => document.querySelector('#rp-out') && !document.querySelector('#rp-out').textContent.includes('reading')",
                timeout=60000,
            )
            check(
                "read again, the newest faithfulness record says what the replay found; no page error",
                "no faithfulness record yet" not in page.locator("#rp-out").inner_text() and not errors,
                (page.locator("#rp-out").inner_text()[-600:], errors[:2]),
            )
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=20)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
