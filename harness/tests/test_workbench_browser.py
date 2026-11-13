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
  - round r4's results fit a desktop screen, each arm on its own Linux re-run (bart_l carried, read through its own),
    the round's answer in one line above them;
  - r4's verdicts are `evh rounds`': each arm against the leader, Holm across the arms in play, so a retire narrows
    it; the commands carry the round (--keep, round: r4);
  - a retire's reason is a sentence, an empty or one-word one an error tied to its field;
  - Close needs a sentence, as round-close does; its confirm is an alertdialog, and Escape backs out of it;
  - an added clone keeps its fold and focus; Escape closes an arm's panel; a phone's chart keeps its words apart;
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
        "workbench: r4's results fit the screen, bart_l carried and read through its Linux re-run, the answer in one line",
        over <= 0
        and "carried · its Linux re-run" in base_row
        and "6.3 s" in base_row
        and page.locator(".roundanswer").inner_text().startswith("No arm was shown ahead of bart_l")
        and "suggests retiring" in page.locator(".roundanswer").inner_text(),
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
    page.locator("#actwhy").fill("slow")
    page.locator("#actok").click()
    check(
        "workbench: a one-word retire reason is refused, as round-retire refuses it",
        page.locator("tr.askrow").count() == 1 and "three words" in page.locator("#actmsg").inner_text(),
    )
    page.keyboard.press("Escape")
    check("workbench: Escape cancels the retire prompt", page.locator("tr.askrow").count() == 0)
    page.locator("details.cmd > summary").last.click()
    cmds = page.locator("details.cmd").last.inner_text()
    check(
        "workbench: r4's commands carry the round: bart_l kept, each config naming round r4",
        "--keep cnn_bart_l_n200_v1" in cmds and "round: r4" in cmds and "--promote" not in cmds,
        cmds[:300],
    )
    page.locator("#r4c").fill("bart_l stays")
    short_off = (
        page.locator("#closer4").is_disabled()
        and "write a sentence" in page.locator("#closehint").inner_text()
    )
    page.locator("#r4c").fill("No local arm was shown ahead of bart_l.")
    check(
        "workbench: Close needs a sentence of three words or more, as round-close does",
        short_off
        and page.locator("#closer4").is_enabled()
        and not page.locator("#closehint").inner_text().strip(),
    )
    page.locator("#closer4").click()
    page.locator("#closeno").focus()
    page.keyboard.press("Escape")
    check(
        "workbench: Escape backs out of the close confirm, focus back on Close",
        page.locator("#closeok").count() == 0 and page.evaluate("document.activeElement.id") == "closer4",
    )
    page.locator("#closer4").click()
    check(
        "workbench: the close confirm is an alertdialog that says what it decides, its button 'Yes, close r4'",
        page.locator("button:visible", has_text="Close the round").count() == 0
        and page.locator("#closeok").inner_text() == "Yes, close r4"
        and page.get_attribute(".confirm", "role") == "alertdialog"
        and page.evaluate("document.activeElement.id") == "closeok",
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
    """r4's verdicts are `evh rounds`': every arm in play against the round's leader (bart_l), Holm across them
    (rounds.evidence; stats.holm reports a raw p and its threshold). bart_s, raw p 0.0158, is third of four and under
    its 0.025; a Bonferroni reading once shown here called it not significant. Retiring bart_m leaves three, and bart_s's
    threshold is then 0.05. r1 sorts; an opened command stays open; Escape closes an arm's panel; on a phone the rail is
    one line and the chart's words do not collide or leave it."""
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
        "workbench: r4's verdicts are evh rounds' (bart_s significantly worse: raw p 0.0158 under its Holm threshold 0.025)",
        "significantly worse" in bart_s
        and "raw p 0.0158 · threshold 0.025" in bart_s
        and any("not significantly different" in r for r in rows),
        rows,
    )
    page.locator("table.r4res tbody tr").filter(has_text="bart_m").locator("[data-retire]").click()
    page.locator("#actwhy").fill("slower than bart_s at the same coverage")
    page.locator("#actok").click()
    page.wait_for_timeout(200)
    rows = page.evaluate(
        "[...document.querySelectorAll('table.r4res tbody tr')].map(t => t.cells[0].firstChild.textContent.trim() + ': ' + t.cells[3].textContent.replace(/\\s+/g, ' ').trim())"
    )
    bart_s = next((r for r in rows if r.startswith("bart_s:")), "")
    check(
        "workbench: a retire narrows r4's Holm family, as evh rounds leaves the retired out (bart_s's threshold 0.05)",
        "threshold 0.05" in bart_s
        and any(r.startswith("bart_m:") and "retired: not tested" in r for r in rows)
        and "across the 3" in page.locator(".cmpnote").inner_text(),
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
    page.locator("[data-armbtn]").first.click()
    page.wait_for_timeout(200)
    opened_panel = page.locator(".armpanel").count()
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    check(
        "workbench: Escape closes an arm's panel",
        opened_panel == 1 and page.locator(".armpanel").count() == 0,
        opened_panel,
    )
    page.close()
    page, errors = seeded(
        browser,
        base,
        {**STATE, "r4": {"question": "Does a smaller local model match bart_l?"}, "tab": "r4"},
        viewport={"width": 1280, "height": 900},
    )
    page.goto(base + "#eval")
    page.wait_for_timeout(300)
    page.locator("#clonebox > summary").click()
    page.locator("#cladd").click()
    empty_err = page.get_attribute("#clto", "aria-invalid") == "true" and page.locator(
        "#clmsg"
    ).inner_text().startswith("Error:")
    page.locator("#clto").fill("0.7")
    page.locator("#cladd").click()
    page.wait_for_timeout(200)
    check(
        "workbench: an empty clone is an error; an added one keeps the fold open and focus on its Remove",
        empty_err
        and page.evaluate("document.querySelector('#clonebox').open")
        and page.evaluate("document.activeElement.dataset.unclone") == "0",
        page.evaluate("document.activeElement.outerHTML.slice(0, 80)"),
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
    chart = page.evaluate(
        """(() => { const svg = [...document.querySelectorAll('svg.scatter')].find(s => s.getBoundingClientRect().width);
          const box = svg.getBoundingClientRect(), r = [...svg.querySelectorAll('text')].map(t => t.getBoundingClientRect());
          const outside = r.filter(b => b.left < box.left - 0.5 || b.right > box.right + 0.5 || b.top < box.top - 0.5 || b.bottom > box.bottom + 0.5).length;
          let hits = 0; r.forEach((a, i) => r.slice(i + 1).forEach(b => { if (a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom) hits++; }));
          const px = Math.min(...[...svg.querySelectorAll('text')].map(t => parseFloat(getComputedStyle(t).fontSize) * box.width / svg.viewBox.baseVal.width));
          return { cls: svg.getAttribute('class'), outside, hits, px: +px.toFixed(2) }; })()"""
    )
    check(
        "workbench: on a phone r1's chart is the phone's own, its words 11px or more, none leaving it or on another",
        chart["cls"].endswith("phone") and chart["outside"] == 0 and chart["hits"] == 0 and chart["px"] >= 11,
        chart,
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
