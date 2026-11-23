#!/usr/bin/env python3
"""The Workbench's studies screens keep unknown, zero and empty apart (RFC-041 F3): $0 offline.

    python tests/test_workbench_spend_browser.py

- a trial whose cost nobody recorded shows `—`, one that cost $0 shows `$0.0000` (it read `$0.0000` for both), and a
  study with no spend recorded the same;
- an empty cap box is `Number("") = 0`, which the server refuses with "above 0": the page says "Say the most it may
  spend first." before it sends anything, on the study's check and its run.
"""

from __future__ import annotations

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
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/
import _cli  # noqa: E402
import _serve  # noqa: E402
import _signin  # noqa: E402
import _slow  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-wbspend-"))
env = dict(
    os.environ,
    EVH_ACTOR="person:tester",
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-wb-spend",
    EVAL_STORE="files",
)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_MAX_COST_USD", "EVH_FOR"):
    env.pop(k, None)


def evh(*args: str) -> subprocess.CompletedProcess:
    return _cli.run(proj, env, *args)


try:
    r = evh("init", "--store", "files", "--tutorial")
    r = r if r.returncode else evh(
        "goal-new", "g", "--set", "title=A goal", "--set", "statement=s.", "--set", "decision=d.",
        "--set", "success_criteria.primary.measure=overlap_f1", "--set", "success_criteria.primary.direction=higher",
        "--set", "datasets=[]",
    )  # fmt: skip
    check("setup: a project with a goal", r.returncode == 0, (r.stdout + r.stderr)[-300:])

    from playwright.sync_api import sync_playwright

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)],
        cwd=proj, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    lines: list[str] = []
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    lines = _serve.startup(srv, lines)
    try:
        link = _signin.link(lines)
        with sync_playwright() as pw:
            browser = _slow.launch(pw)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(str(link))
            page.wait_for_selector("main h1", timeout=30000)
            sent: list[str] = []
            page.on(
                "request",
                lambda q: sent.append(q.url) if q.method == "POST" and "/api/" in q.url else None,
            )

            page.goto(f"http://127.0.0.1:{port}/workbench/#study/g")
            page.wait_for_selector("#sn6-go", timeout=30000)
            page.fill("#st6-by", "tester")
            page.fill("#sn6-id", "s1")
            page.fill("#sn6-cap", "")
            for button in ("#sn6-dry", "#sn6-go"):
                page.click(button)
                page.wait_for_selector("#sn6-out [role=alert]", timeout=10000)
                check(
                    f"an empty cap box: {button} says what is missing, before the server says 'above 0'",
                    page.locator("#sn6-out").inner_text().strip() == "Say the most it may spend first."
                    and not sent,
                    (page.locator("#sn6-out").inner_text()[:200], sent),
                )

            # A study list and a study with an unrecorded cost, a $0 one and an amount, as the API gives them.
            page.evaluate(
                """() => {
                  LIVE.cache["studies:g"] = {studies: [
                    {study: "g/none", status: "ended", dataset: "d", baseline: "b", trials: 1, kept: 0, spent_usd: null, confirms: 0},
                    {study: "g/zero", status: "ended", dataset: "d", baseline: "b", trials: 1, kept: 0, spent_usd: 0, confirms: 0},
                    {study: "g/some", status: "ended", dataset: "d", baseline: "b", trials: 1, kept: 0, spent_usd: 0.25, confirms: 0},
                  ]};
                  WB.render(true);
                }"""
            )
            page.wait_for_selector("a:has-text('g/zero')", timeout=10000)
            spent = {
                row.locator("a").inner_text(): row.locator("td").nth(6).inner_text()
                for row in page.locator("main table tbody tr").all()
            }
            check(
                "the study list: spend unrecorded is —, $0 is $0.0000, an amount is its dollars",
                spent == {"g/none": "—", "g/zero": "$0.0000", "g/some": "$0.2500"},
                spent,
            )

            page.evaluate(
                """() => {
                  LIVE.cache["study:g/none"] = {study: "g/none", status: "ended", baseline: "b", spec: {dataset: "d", measure: "m"},
                    round: "r1", spent_usd: null, trials: [], confirms: [],
                    rows: [{k: 1, change: "c", outcome: "kept", reason: "r", delta: 0.1, cost_usd: null},
                           {k: 2, change: "c", outcome: "discarded", reason: "r", delta: 0, cost_usd: 0},
                           {k: 3, change: "c", outcome: "discarded", reason: "r", delta: 0, cost_usd: 0.5}]};
                  location.hash = "#study/g/none";
                  WB.render(true);
                }"""
            )
            page.wait_for_selector("h1:has-text('The study none')", timeout=10000)
            main = page.locator("main").inner_text()
            costs = [row.locator("td").last.inner_text() for row in page.locator("main table tbody tr").all()]
            check(
                "a study's trials: the cost unrecorded is —, $0 is $0.0000, an amount is its dollars",
                costs[:3] == ["—", "$0.0000", "$0.5000"] and "spent —." in main,
                (costs, main[:500]),
            )
            check("no page error", not errors, errors[:2])
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
