#!/usr/bin/env python3
"""An idle Workbench is idle: it reaches Playwright's `networkidle`, and a followed job is not polled while the tab is
hidden (0.8.1 newcomer scenario: "the Workbench never reaches networkidle (it polls)").

    python tests/test_workbench_idle_browser.py

Behind a real catalog-serve, in a project with one goal and no job running:

  - Home and the goal's eval screen each reach `networkidle` within a few seconds (a read whose body nobody consumed
    never ends in Chromium's eyes: the page's first read of /api/v1/goals read only its status);
  - a job being followed (its page; the log and the job asked every second while it runs) is not asked while the tab is
    hidden, and is asked again when the tab shows; the job page still updates while the tab is visible.
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
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _signin
import _cli  # noqa: E402
import _serve  # noqa: E402
import _signin  # noqa: E402
import _slow  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-wbidle-"))
env = dict(
    os.environ,
    EVH_ACTOR="person:tester",
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-wb-idle",
    EVAL_STORE="files",
)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    env.pop(k, None)

IDLE_MS = 5000
JOB = "job_idle_probe"


def evh(*args: str) -> subprocess.CompletedProcess:
    return _cli.run(proj, env, *args, timeout=600)


def serve() -> tuple[subprocess.Popen, int, list[str]]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL, encoding="utf-8",
    )  # fmt: skip
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    return p, port, _serve.startup(p, [])


def reaches_idle(page, url: str, ready: str) -> tuple[bool, float]:
    """Open `url`, wait for `ready`, and say whether the page is network-idle within IDLE_MS (and how long it took)."""
    page.goto(url)
    page.reload()
    page.wait_for_selector(ready, timeout=20000)
    t0 = time.time()
    try:
        page.wait_for_load_state("networkidle", timeout=IDLE_MS)
        return True, time.time() - t0
    except Exception:  # noqa: BLE001 - a timeout is the answer
        return False, time.time() - t0


def set_visibility(page, hidden: bool) -> None:
    page.evaluate(
        """(hidden) => {
          Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
          Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => (hidden ? 'hidden' : 'visible') });
          document.dispatchEvent(new Event('visibilitychange'));
        }""",
        hidden,
    )


try:
    r = evh("init", "--store", "files", "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        ("goal-new", "tickets_summary", "--set", "title=Ticket summaries", "--set", "statement=A one-line summary of a ticket.",
         "--set", "decision=Which system writes it.", "--set", "success_criteria.primary.measure=overlap_f1",
         "--set", "success_criteria.primary.direction=higher", "--set", "datasets.0.dataset_id=tk_v1",
         "--set", "datasets.0.role=pilot"),
        ("catalog",),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    check(
        "setup: a project with one goal and no job running", r.returncode == 0, (r.stdout + r.stderr)[-300:]
    )

    from playwright.sync_api import sync_playwright

    srv, port, lines = serve()
    try:
        link = _signin.link(lines)
        with sync_playwright() as pw:
            browser = _slow.launch(pw)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(str(link))
            page.wait_for_selector("h1:has-text('Your goals')", timeout=20000)
            base = f"http://127.0.0.1:{port}/workbench/"

            ok, took = reaches_idle(page, base + "#start", "h1:has-text('Your goals')")
            check(
                f"Home reaches networkidle within {IDLE_MS // 1000} s with no job running ({took:.1f}s)", ok
            )
            ok, took = reaches_idle(page, base + "#eval/tickets_summary", "main h1")
            check(f"an idle eval screen reaches networkidle within {IDLE_MS // 1000} s ({took:.1f}s)", ok)
            for route in ("goal/tickets_summary", "systems/tickets_summary", "models", "jobs", "settings"):
                ok, took = reaches_idle(page, base + f"#{route}", "main h1")
                check(f"#{route} reaches networkidle within {IDLE_MS // 1000} s ({took:.1f}s)", ok)

            # a running job, stubbed: the job page follows it every second while the tab shows
            asked = {"job": 0, "log": 0}

            def stub(route) -> None:
                url = route.request.url
                if f"/api/v1/jobs/{JOB}/log" in url:
                    asked["log"] += 1
                    route.fulfill(json={"log": f"line {asked['log']}\n", "next": asked["log"]})
                elif f"/api/v1/jobs/{JOB}" in url:
                    asked["job"] += 1
                    route.fulfill(
                        json={
                            "id": JOB,
                            "operation": "run",
                            "state": "running",
                            "created_at": "2026-11-26T10:00:00",
                            "inputs": {},
                            "locks": [],
                        }
                    )
                else:
                    route.continue_()

            page.route("**/api/v1/jobs/**", stub)
            page.goto(base + f"#jobs/{JOB}")
            page.wait_for_selector("#jb-log", timeout=20000)
            page.wait_for_function(
                "() => document.querySelector('#jb-log').textContent.includes('line 3')", timeout=15000
            )
            check(
                "a running job's page keeps updating its log while the tab shows",
                asked["log"] >= 3 and "line 3" in page.locator("#jb-log").inner_text(),
                (asked, page.locator("#jb-log").inner_text()[:80]),
            )
            set_visibility(page, True)
            page.wait_for_timeout(1500)  # a request in flight when the tab hid
            hidden_at = dict(asked)
            page.wait_for_timeout(3500)
            check(
                "hidden, the job page asks the server nothing",
                asked == hidden_at,
                (hidden_at, asked),
            )
            set_visibility(page, False)
            page.wait_for_function(
                f"() => document.querySelector('#jb-log').textContent.includes('line {hidden_at['log'] + 2}')",
                timeout=15000,
            )
            check(
                "shown again, it follows the job again",
                asked["log"] >= hidden_at["log"] + 2,
                (hidden_at, asked),
            )
            check("no page error", not errors, errors[:2])
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=20)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
