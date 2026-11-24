#!/usr/bin/env python3
"""The Workbench as a viewer, in a browser (RFC-039, UXS-005 "The viewer"): $0 and offline.

    python tests/test_workbench_viewer_browser.py

A project with a goal, a round, two arms, a model and a prompt, over a dataset marked `text: hidden` whose every text
carries a marker word (tests/_viewer_fixture.py), behind `evh catalog-serve --public`; Chromium at 1280 and at 390 px:

- the page knows it is a viewer with no token, no cookie and no setting: the server's header says so;
- the one-line notice is on every screen; the menu has the screens that read and none that only act;
- every screen the menu and the screens reach (every link, to a fixed point) draws no control that acts: nothing but the
  help's ?, the rail's fold and what the page's own settings are; nothing is sent that is not a read;
- the screens whose job is to act say "not shown publicly" at their address, with the command; a screen that needs a refused
  read (the sheet, a judge's reasons, a held-out count) says so in that place;
- the marker word is nowhere on any screen; no page error, no console error, no answer of 400 or more (a screen does not
  ask for what it knows is refused).
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/
import _slow  # noqa: E402
import _viewer_fixture as fx  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-wbviewer-"))
env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-wb-viewer")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_STORE", "EVAL_MAX_COST_USD", "EVH_FOR", "EVH_PUBLIC"):
    env.pop(k, None)

#: A control that does not act: the help's ?, the rail's fold on a phone, and a control marked as only changing the view.
READS = ".q, .railtoggle, [data-view]"
#: What a button or a link that acts is called on a screen.
ACTING = re.compile(
    r"open the|run them|run the probes|see the cost|see the plan|close the round|retire|carry it in|promote|save|delete|"
    r"make the|make it|fetch them|profile it|bring in|roll back|check it on three|clone it|submit|record it|seal it|"
    r"split it|judge the arms|validate it|replay it|new goal|start with a goal|edit the goal|pick them|label from|allow it",
    re.I,
)
SIZES = ((1280, 900), (390, 844))


def settled(page) -> None:
    """The screen is drawn: a heading, and nothing still reading."""
    page.wait_for_selector("main h1", timeout=30000)
    page.wait_for_function(
        "() => !/Reading |Opening this project/.test(document.querySelector('main').innerText)", timeout=30000
    )


try:
    fx.build(proj, env)
    from playwright.sync_api import sync_playwright

    # The deployment serves the catalog at /catalog/, not at the root the local server uses (infra/caddy/evals.caddy).
    srv, port, _lines = fx.serve_public(
        proj, env, "--publish", "outputs,references", "--catalog-at", "/catalog/"
    )
    base = f"http://127.0.0.1:{port}/workbench/"
    try:
        with sync_playwright() as pw:
            browser = _slow.launch(pw)
            for width, height in SIZES:
                tag = f"{width}px"
                ctx = browser.new_context(viewport={"width": width, "height": height})
                page = ctx.new_page()
                errors: list[str] = []
                refused: list[str] = []
                sent: list[str] = []
                page.on("pageerror", lambda e, errors=errors: errors.append(f"pageerror: {e}"))
                page.on(
                    "console",
                    lambda m, errors=errors: (
                        errors.append(f"console: {m.text}") if m.type == "error" else None
                    ),
                )
                page.on(
                    "response",
                    lambda r, refused=refused: (
                        refused.append(f"{r.status} {r.url}") if r.status >= 400 else None
                    ),
                )
                page.on(
                    "request",
                    lambda r, sent=sent: (
                        sent.append(f"{r.method} {r.url}")
                        if r.url.startswith(f"http://127.0.0.1:{port}/api/") and r.method != "GET"
                        else None
                    ),
                )

                page.goto(base)
                settled(page)
                check(
                    f"{tag}: the Workbench opens with no token and no sign-in",
                    "Your goals" in page.inner_text("main"),
                    page.inner_text("main")[:200],
                )
                check(f"{tag}: it sets no cookie", ctx.cookies() == [], ctx.cookies())

                menu = page.locator("#nav a").all_inner_texts()
                labels = [m.strip() for m in menu]
                check(
                    f"{tag}: the menu has the screens that read, and none that only act (no Jobs, no Settings)",
                    labels == ["Home", "Models", "Prompts", "Words", "Catalog ↗"],
                    labels,
                )
                to_catalog = page.eval_on_selector_all(
                    "a",
                    "els => els.filter((e) => /catalog/i.test(e.textContent)).map((e) => new URL(e.href).pathname)",
                )
                check(
                    f"{tag}: every link to the catalog goes where the deployment serves it (/catalog/)",
                    bool(to_catalog) and all(p.startswith("/catalog/") for p in to_catalog),
                    to_catalog,
                )
                # the catalog's place comes from a response header: put into an href escaped, and only as a path
                kept_at = page.evaluate("LIVE.catalogAt")
                hrefs = {}
                for hostile in ('/c/"><i id=injected>', "javascript:alert(1)"):
                    page.evaluate("(at) => { LIVE.catalogAt = at; WB.render(true); }", hostile)
                    page.wait_for_selector("main h1", timeout=20000)
                    hrefs[hostile] = [
                        page.locator("main a.btn:has-text('The catalog')").get_attribute("href"),
                        page.locator("#injected").count(),
                    ]
                page.evaluate("(at) => { LIVE.catalogAt = at; WB.render(true); }", kept_at)
                check(
                    f"{tag}: a hostile catalog place is escaped in the link, and one that is not a path is not used",
                    hrefs['/c/"><i id=injected>'][1] == 0
                    and hrefs['/c/"><i id=injected>'][0] == base.split("/workbench")[0] + '/c/"><i id=injected>'
                    and hrefs["javascript:alert(1)"][0] == base.split("/workbench")[0] + "/",
                    hrefs,
                )

                seen: dict[str, str] = {}
                todo = ["#home", "#models", "#prompts", "#glossary", "#goal/hg"]
                notices = 0
                acting: list[str] = []
                marked: list[str] = []
                loose: list[str] = []
                overflow: list[str] = []
                while todo and len(seen) < 90:
                    route = todo.pop(0)
                    if route in seen:
                        continue
                    page.goto(base + route)
                    settled(page)
                    body = page.inner_text("body")
                    seen[route] = body
                    if page.locator(
                        "#wb-viewer"
                    ).count() == 1 and "read-only view of a published project" in page.inner_text(
                        "#wb-viewer"
                    ):
                        notices += 1
                    for sel in ("main", "#rail"):
                        for el in page.locator(
                            f"{sel} button, {sel} input, {sel} select, {sel} textarea, {sel} form"
                        ).all():
                            if not el.evaluate(f"e => e.matches('{READS}') || !!e.closest('[data-view]')"):
                                acting.append(f"{route}: {el.evaluate('e => e.outerHTML')[:120]}")
                    for el in page.locator("main a.btn, #rail a, main button").all():
                        text = el.inner_text().strip()
                        if ACTING.search(text):
                            acting.append(f"{route}: {text!r}")
                    html = page.content()
                    if fx.MARK.lower() in (body + html).lower():
                        marked.append(route)
                    if page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth + 1"):
                        overflow.append(route)
                    for href in page.eval_on_selector_all(
                        "#main a[href^='#'], #rail a[href^='#']",
                        "els => els.map(e => e.getAttribute('href'))",
                    ):
                        if href not in seen and href not in todo and href != "#":
                            todo.append(href)
                    loose.extend(re.findall(r"undefined|\[object Object\]|NaN", body))

                check(
                    f"{tag}: every screen was walked ({len(seen)} of them), from the menu and every link on a screen",
                    len(seen) >= 12,
                    sorted(seen),
                )
                check(
                    f"{tag}: the one-line notice is on every screen",
                    notices == len(seen),
                    (notices, len(seen)),
                )
                check(
                    f"{tag}: no screen draws a control that acts, or a link that is a button for acting",
                    not acting,
                    acting[:6],
                )
                check(f"{tag}: the marker word is on no screen", not marked, marked)
                check(f"{tag}: no screen shows undefined, [object Object] or NaN", not loose, loose[:5])
                if width < 500:
                    check(f"{tag}: no screen scrolls sideways", not overflow, overflow)
                check(
                    f"{tag}: no screen of the menu and its links is the dead end of a refused read",
                    all("Could not read it" not in b for b in seen.values()),
                    [r for r, b in seen.items() if "Could not read it" in b],
                )

                # the screens whose job is to act: said at their address, with the command
                for route, title in (
                    ("#jobs", "Jobs"),
                    ("#settings", "Settings"),
                    ("#model-new", "Bring in a model"),
                    ("#goal-new", "Set the goal"),
                    ("#goal-edit/hg", "The goal"),
                    ("#dataset/hg", "Add a dataset"),
                    ("#label/tk_h", "Label it here"),
                    ("#reference/tk_h", "Change the reference set"),
                    ("#review/hg", "Review the outputs"),
                ):
                    page.goto(base + route)
                    page.wait_for_selector("main h1", timeout=20000)
                    shown = page.inner_text("main")
                    check(
                        f"{tag}: {route} says it is not shown publicly, with its command and a way home",
                        title in shown
                        and "not shown publicly" in shown.lower()
                        and "evh " in page.text_content("main")
                        and page.locator("main a[href='#home']").count() == 1
                        and page.locator("#wb-viewer").count() == 1,
                        shown[:200],
                    )

                # a prompt's text is published only with --publish prompts: its views say so, not an empty box
                page.goto(base + "#prompts/hg%2Fprompt")
                settled(page)
                shown = page.inner_text("main")
                check(
                    f"{tag}: a prompt's version says the text is not published here (--publish prompts), and shows none",
                    "the text is not published here (--publish prompts)" in shown
                    and "Keep what support needs." not in shown
                    and "Keep what support needs." not in page.content(),
                    shown[:400],
                )

                # a screen that needs a refused read says so where the read would have shown
                page.goto(base + "#home")
                settled(page)
                home = page.inner_text("main")
                check(
                    f"{tag}: Home's running jobs, a refused read, say not shown publicly in that place",
                    re.search(r"running now.*?not shown publicly", home, re.I | re.S) is not None,
                    home[:400],
                )
                page.goto(base + "#heldout/hg")
                settled(page)
                held = page.inner_text("main")
                check(
                    f"{tag}: the held-out screen's refused counts say not shown publicly",
                    "not shown publicly" in held.lower(),
                    held[:400],
                )
                page.goto(base + "#judge/hg")
                settled(page)
                check(
                    f"{tag}: the judge screen draws and holds no marker",
                    fx.MARK.lower() not in page.content().lower(),
                )

                # the page itself sends nothing that is not a read, whatever a script on it asks
                before = len(sent)
                result = page.evaluate(
                    "async () => { const r = await fetch('/api/v1/estimate', {method: 'POST', body: '{}'}); const j = await r.json(); return [r.status, j.kind]; }"
                )
                check(
                    f"{tag}: a call that writes is refused in the page, before it is sent",
                    result == [403, "not-public"] and len(sent) == before,
                    (result, sent[before:]),
                )
                check(f"{tag}: no request that is not a read was sent", not sent, sent)
                # A hidden dataset's agreement chart is refused 409 by the local server too (its labels are per-item text): the
                # one answer of 400 or more, and its console line, that this project's prepare screen asks for.
                hidden_chart = [
                    r for r in refused if re.fullmatch(r"409 \S+/api/v1/charts/agreement\?dataset=tk_h\S*", r)
                ]
                refused = [r for r in refused if r not in hidden_chart]
                errors = [e for e in errors if not (hidden_chart and "409" in e)]
                check(
                    f"{tag}: no answer of 400 or more (a screen does not ask for what it knows is refused)",
                    not refused,
                    refused[:5],
                )
                check(f"{tag}: no page error, no console error", not errors, errors[:5])
                ctx.close()
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
