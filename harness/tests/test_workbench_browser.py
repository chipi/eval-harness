#!/usr/bin/env python3
"""The Workbench mockup (harness/workbench) in a real browser. It had no test of its own, and its skip link shipped
changing the route (its screens are routes in the hash); this is the guard for that and for what its critiques fixed.

    python tests/test_workbench_browser.py
    make browser-check

Served from a static server on a free port, with Chromium:

  - every screen opens with no page error and no sideways scroll, at a desktop and at a phone width;
  - the skip link is the first Tab stop, keeps its ink when hovered, and focuses the screen without changing it;
  - the help panel opens with focus on its close button and gives it back to what opened it; a glossary word opens
    on Space without scrolling the page;
  - round r4's results fit a desktop screen, each arm on its own Linux re-run (bart_l's too), with one statement when
    no arm can be the baseline;
  - a retire's empty reason is an error tied to its field;
  - closing the round keeps the standing answer and amends it.
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

WORKBENCH = HARNESS / "workbench"
# A goal set up to step 5 on the project's real summarisation goal (the mockup reads mock.js, the project's data).
STATE = {
    "goal": {
        "goal_id": "news_summary_cnn",
        "title": "Short news summaries (CNN)",
        "statement": "Pick a model that writes a short summary of a CNN-style news article, at a known cost.",
        "decision": "Which models can be told apart on summary quality, and what each costs per article.",
        "measure": "coverage",
        "direction": "higher",
        "strategy": "balanced",
    },
    "dataset": {"id": "cnn_dailymail_200"},
    "fetched": True,
    "looked": True,
    "reference": {"id": "gold/cnn_dailymail_200"},
    "hints": True,
    "checked": ["eval-claude-haiku", "eval-claude-sonnet", "eval-deepseek-flash"],
}
ROUTES = ("home", "goal-new", "hub", "dataset", "dataset-hf", "prepare", "models", "eval", "glossary")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def serve() -> tuple:
    srv = socketserver.TCPServer(("127.0.0.1", 0), partial(Quiet, directory=str(WORKBENCH)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/index.html"


def seeded(browser, base: str, state: dict, **page_args):
    page = browser.new_page(**page_args)
    errors: list = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "#start")
    page.evaluate("(s) => localStorage.setItem('wb-mock-r1', JSON.stringify(s))", state)
    page.reload()
    return page, errors


def check_screens(browser, base: str) -> None:
    for name, vp, mobile in (
        ("desktop", {"width": 1280, "height": 900}, False),
        ("phone", {"width": 390, "height": 844}, True),
    ):
        page, errors = seeded(browser, base, STATE, viewport=vp, is_mobile=mobile)
        bad = []
        for route in ROUTES:
            page.goto(f"{base}#{route}")
            page.wait_for_timeout(250)
            over = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            if over > 0 or not page.locator("main h1").count():
                bad.append((route, over))
        check(
            f"workbench ({name}): every screen opens with a heading, no sideways scroll, no page error",
            not bad and not errors,
            (bad, errors[:2]),
        )
        page.close()


def check_skip_link(browser, base: str) -> None:
    page, errors = seeded(browser, base, STATE, viewport={"width": 1280, "height": 900})
    page.goto(base + "#eval")
    page.reload()
    page.wait_for_timeout(300)
    page.keyboard.press("Tab")
    first = page.evaluate("document.activeElement.className")
    page.locator("a.skip").hover()
    fg, bg = page.evaluate(
        "(() => { const s = getComputedStyle(document.querySelector('a.skip')); return [s.color, s.backgroundColor]; })()"
    )
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    check(
        "workbench: the skip link is the first stop, keeps its ink when hovered, and focuses the screen without changing it",
        first == "skip"
        and fg != bg
        and page.evaluate("location.hash") == "#eval"
        and page.evaluate("document.activeElement.id") == "main",
        f"first {first}, {fg} on {bg}, hash {page.evaluate('location.hash')}, focus {page.evaluate('document.activeElement.id')}",
    )
    page.goto(
        base + "#eval"
    )  # on its own footing: a skip link that changed the route must not hide what follows
    page.wait_for_timeout(200)
    page.locator(".q").first.focus()
    page.keyboard.press("Enter")
    into = page.evaluate("document.activeElement.matches('[data-close]')")
    page.keyboard.press("Escape")
    back = page.evaluate("document.activeElement.classList.contains('q')")
    check(
        "workbench: the help panel opens with focus on its close button and gives it back",
        into and back,
        (into, back),
    )
    page.locator("dfn[data-word]").first.focus()
    y = page.evaluate("scrollY")
    page.keyboard.press(" ")
    page.wait_for_timeout(100)
    check(
        "workbench: a glossary word opens on Space, and the page does not scroll",
        page.evaluate("!document.getElementById('help').hidden")
        and page.evaluate("scrollY") == y
        and not errors,
        errors[:2],
    )
    page.close()


def check_round(browser, base: str) -> None:
    state = {
        **STATE,
        "r4": {"question": "Does a smaller local model match bart_l?", "ran": True},
        "tab": "r4",
    }
    page, errors = seeded(browser, base, state, viewport={"width": 1280, "height": 900})
    page.goto(base + "#eval")
    page.wait_for_timeout(300)
    over = page.evaluate(
        "(() => { const w = document.querySelector('table.r4res').closest('.tablewrap'); return w.scrollWidth - w.clientWidth; })()"
    )
    base_row = page.locator("table.r4res tbody tr").filter(has_text="baseline").first.inner_text()
    check(
        "workbench: r4's results fit the screen, bart_l on its own Linux re-run, one statement that none can be the baseline",
        over <= 0
        and "its re-run" in base_row
        and "6.3 s" in base_row
        and page.locator(".note", has_text="None of the").count() == 1,
        f"overflow {over}px, baseline row {base_row!r}",
    )
    page.locator("[data-retire]").first.click()
    page.locator("#actok").click()
    msg_colour, bad = page.evaluate(
        "[getComputedStyle(document.getElementById('actmsg')).color,"
        " getComputedStyle(document.documentElement).getPropertyValue('--bad').trim()]"
    )
    check(
        "workbench: a retire's empty reason is an error tied to its field, said in the bad status",
        page.get_attribute("#actwhy", "aria-invalid") == "true"
        and page.get_attribute("#actwhy", "aria-describedby") == "actmsg"
        and page.locator("#actmsg").inner_text().startswith("Error:")
        and msg_colour != page.evaluate("getComputedStyle(document.querySelector('.muted')).color"),
        (msg_colour, bad),
    )
    page.keyboard.press("Escape")
    check("workbench: Escape cancels the retire prompt", page.locator("tr.askrow").count() == 0)
    page.locator("#r4c").fill("No local arm was shown ahead of bart_l.")
    check(
        "workbench: the close hint stops asking for a conclusion once one is written",
        "write the conclusion first" not in page.locator("#closehint").inner_text(),
    )
    page.locator("#closer4").click()
    check(
        "workbench: the confirm shows one 'Close the round', not two",
        page.locator("button:visible", has_text="Close the round").count() == 1,
        page.locator("button:visible", has_text="Close the round").count(),
    )
    page.locator("#closeok").click()
    page.wait_for_timeout(200)
    answer = page.locator(".answer").inner_text()
    check(
        "workbench: closing the round keeps the standing answer and amends it",
        "rent deepseek_m" in answer
        and "r4 added:" in answer
        and "No local arm was shown ahead of bart_l." in answer
        and not errors,
        (answer[:200], errors[:2]),
    )
    page.locator("#openr5").click()
    page.wait_for_timeout(200)
    check(
        "workbench: a closed round leads on: the next round opens from it, its question in focus",
        page.evaluate("document.activeElement.id") == "r5q"
        and page.locator("[data-tab=r5][aria-selected=true]").count() == 1
        and "from r4" in page.locator(".roundhead").inner_text().lower()  # the kicker is set in capitals
        and not errors,
        (page.evaluate("document.activeElement.id"), errors[:2]),
    )
    page.close()


def check_verdicts_and_reading(browser, base: str) -> None:
    """r4's verdicts are the harness's: Bonferroni across the round's arms, as `round-close --promote` tests (a Holm
    step-down here once called bart_s significantly worse at 0.0316; the harness says 0.0632). r1 sorts; an opened
    command stays open; on a phone the rail is one line."""
    state = {
        **STATE,
        "r4": {"question": "Does a smaller local model match bart_l?", "ran": True},
        "tab": "r4",
    }
    page, errors = seeded(browser, base, state, viewport={"width": 1280, "height": 900})
    page.goto(base + "#eval")
    page.wait_for_timeout(300)
    rows = page.evaluate(
        "[...document.querySelectorAll('table.r4res tbody tr')].map(t => t.cells[0].firstChild.textContent.trim() + ': ' + t.cells[3].textContent.replace(/\\s+/g, ' ').trim())"
    )
    bart_s = next((r for r in rows if r.startswith("bart_s:")), "")
    check(
        "workbench: r4 gives each arm a verdict with its corrected p, as promotion tests it (bart_s: 0.0632, not significant)",
        "not significantly different" in bart_s
        and "p 0.0632" in bart_s
        and any("significantly worse" in r for r in rows),
        rows,
    )
    page.locator('[data-tab="r1"]').click()
    page.wait_for_timeout(200)
    page.locator('[data-sort="speed"]').click()
    page.wait_for_timeout(200)
    speeds = page.evaluate(
        "[...document.querySelectorAll('table.cmp tbody tr[data-arm]')].map(r => r.cells[5].textContent.trim())"
    )
    check(
        "workbench: r1's table sorts by a column (speed, fastest first)",
        bool(speeds) and page.get_attribute('th:has([data-sort="speed"])', "aria-sort") == "ascending",
        speeds[:4],
    )
    page.locator("details.cmd > summary").first.click()
    page.locator('[data-sort="arm"]').click()
    page.wait_for_timeout(200)
    check(
        "workbench: a command opened stays open across a redraw",
        page.evaluate("document.querySelector('details.cmd').open") and not errors,
        errors[:2],
    )
    page.close()
    page, errors = seeded(browser, base, STATE, viewport={"width": 390, "height": 844}, is_mobile=True)
    page.goto(base + "#eval")
    page.wait_for_timeout(300)
    folded = page.evaluate(
        "[...document.querySelectorAll('#rail > a.step')].filter(a => a.offsetParent).length"
    )
    page.locator(".railtoggle").click()
    opened = page.evaluate(
        "[...document.querySelectorAll('#rail > a.step')].filter(a => a.offsetParent).length"
    )
    check(
        "workbench: on a phone the rail is one line naming the step, and opens to every step",
        folded == 0
        and opened > 5
        and "Step 5 of 5" in page.locator(".railtoggle").inner_text()
        and not errors,
        (folded, opened),
    )
    page.close()


def main() -> int:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    srv, base = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            check_screens(browser, base)
            check_skip_link(browser, base)
            check_round(browser, base)
            check_verdicts_and_reading(browser, base)
            browser.close()
    finally:
        srv.shutdown()
    return summary()


if __name__ == "__main__":
    raise SystemExit(main())
