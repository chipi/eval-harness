#!/usr/bin/env python3
"""PLAN_0.8.1 S1: one rule for an arm's name in every inspector view, the sheet included.

    .venv/bin/python tests/test_inspector_names_browser.py

The sheet's names are paths (`rescored-5f2c057c/orrery_triage_v1_labelled/triage_baseline_pro_v1`). The rule: the name
is the path's last segment (the system id), its dataset id's prefix dropped, the whole path the tooltip.
"""

from __future__ import annotations

import os
import shutil
import signal
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _slow
from evaluation_harness._check import check, summary
from test_inspector_browser import project, serve

TWO = "runs/tickets_v1/tickets_lead1_v1,runs/tickets_v1/tickets_author_v1"
ORRERY = "rescored-5f2c057c/orrery_triage_v1_labelled/triage_baseline_pro_v1"
ORRERY2 = "rescored-cd35dc1f/orrery_triage_v1_labelled/triage_stub_dismiss_v1"


def heads_of(page) -> list:
    return page.locator("#sheettable thead th.outc > span").evaluate_all(
        "els => els.map(e => [e.textContent, e.title])"
    )


def drive(base: str) -> None:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as pw:
        browser = _slow.launch(pw)
        page = browser.new_page()
        errors: list = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(f"{base}inspect.html?dataset=tickets_v1&sheet=1&runs={TWO}")
        page.wait_for_selector("#sheettable", timeout=15000)
        got = heads_of(page)
        check(
            "sheet: a runs/ arm is named by its system id without the dataset id prefix",
            [t for t, _ in got] == ["lead1_v1", "author_v1"],
            got,
        )

        def as_paths(route):
            body = route.fetch().text()
            body = body.replace("runs/tickets_v1/tickets_lead1_v1", ORRERY).replace(
                "runs/tickets_v1/tickets_author_v1", ORRERY2
            )
            body = body.replace('"dataset": "tickets_v1"', '"dataset": "orrery_triage_v1_labelled"')
            route.fulfill(status=200, content_type="application/json", body=body)

        page.route("**/api/sheet**", as_paths)
        page.goto(f"{base}inspect.html?dataset=tickets_v1&sheet=1&runs={TWO}")
        page.wait_for_selector("#sheettable", timeout=15000)
        got = heads_of(page)
        check(
            "sheet: a path name keeps its system id, the dataset's own words dropped (triage_, not rescored-.../...)",
            [t for t, _ in got] == ["baseline_pro_v1", "stub_dismiss_v1"],
            got,
        )
        check("... the whole path is the tooltip", [t for _, t in got] == [ORRERY, ORRERY2], got)
        page.unroute("**/api/sheet**")

        def same_system(route):
            body = route.fetch().text()
            body = body.replace(
                "runs/tickets_v1/tickets_lead1_v1", "rescored-aaaaaaaa/tickets_v1/tickets_lead1_v1"
            )
            body = body.replace(
                "runs/tickets_v1/tickets_author_v1", "rescored-bbbbbbbb/tickets_v1/tickets_lead1_v1"
            )
            route.fulfill(status=200, content_type="application/json", body=body)

        page.route("**/api/sheet**", same_system)
        page.goto(f"{base}inspect.html?dataset=tickets_v1&sheet=1&runs={TWO}")
        page.wait_for_selector("#sheettable", timeout=15000)
        got = heads_of(page)
        check(
            "sheet: two arms with one system id stay apart (the path is kept for both)",
            len({t for t, _ in got}) == 2 and all("rescored-" in t for t, _ in got),
            got,
        )
        check("no page error", not errors, errors)
        browser.close()


def main() -> int:
    try:
        import playwright  # noqa: F401, PLC0415
    except ImportError:
        print("  FAIL Playwright is not installed: `make browser-install` (requirements-browser.txt)")
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="evh-names-"))
    server = None
    try:
        proj, env = project(tmp)
        server, base = serve(proj, env, tmp / "serve.log")
        drive(base)
    finally:
        if server is not None:
            os.killpg(server.pid, signal.SIGTERM)
            server.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
