"""A browser for the tests: `_slow.launch(pw)` is `pw.chromium.launch()` with one font on every machine, and with these
set it is slower.

    EVH_TEST_FETCH_DELAY_MS=200   hold every GET of /api/v1/ and of a .json file back that long, in every page and context
                                  the browser opens (a screen's reads then land after the screen is drawn and after the
                                  test has acted on it, as on CI)
    EVH_TEST_SLOW_MO=30           Playwright's slow_mo: each action waits that long

Unset, nothing is slowed. The font is always on: every page and context the browser opens lays its text out in Lato
(tests/fonts/), which stands in for the product's `--text` and `--display` stacks ("Inter", then whatever the machine
has). Fit checks (a box wide enough, a page that does not scroll sideways) were measured in the local machine's
fallback font and failed in CI's wider one (PLAN_0.8.1 C2). The product is unchanged: the stylesheet is the test's, added
to the page by the browser. `--mono` is not replaced (no monospace font is bundled): text in it still takes the machine's.

A page's goto and reload are asked again (up to 5 times, each retry printed) when Chromium drops them with
ERR_NETWORK_CHANGED: it does so when the machine's network changes during the request (an address or a link going up or down, on any
interface), loopback requests included (PLAN_0.8.1 C1; reproduced in a private network namespace with an address
toggled, 0 of 600 reloads failing without the toggle). A page's GET that fails to connect is asked again too (3 times):
the same event fails the reads in flight, and a screen keeps a failed read until the page reloads, so its wait ends in a
timeout. A test's own steps are not retried.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

FONTS = Path(__file__).resolve().parent / "fonts"
FONT_PATH = "/__evh_test_font/"  # same origin as the page, so a Content-Security-Policy's font-src 'self' lets it load
FAMILY = "EvhTestLato"
_FACES = (("lato-regular.woff2", "100 500"), ("lato-bold.woff2", "600 900"))

NETWORK_CHANGED = "ERR_NETWORK_CHANGED"
_NAV_TRIES = 5


def _network_changed(exc: Exception) -> bool:
    return NETWORK_CHANGED in str(exc) or "chrome-error://chromewebdata" in str(exc)


def _renavigating(call: Any) -> Any:
    """`call` (a page's goto or reload), asked again when Chromium drops it with ERR_NETWORK_CHANGED."""

    def run(*args: Any, **kwargs: Any) -> Any:
        for left in range(_NAV_TRIES, 0, -1):
            try:
                return call(*args, **kwargs)
            except Exception as exc:
                if left == 1 or not _network_changed(exc):
                    raise
                print(f"  (retry: {str(exc).splitlines()[0][:100]})", flush=True)

    return run


def _patch_page(pg: Any) -> None:
    pg.goto, pg.reload = _renavigating(pg.goto), _renavigating(pg.reload)


def _font_script() -> str:
    faces = "".join(
        f'@font-face{{font-family:"{FAMILY}";src:url({FONT_PATH}{name}) format("woff2");font-weight:{weight};}}'
        for name, weight in _FACES
    )
    css = faces + f':root{{--text:"{FAMILY}",sans-serif;--display:"{FAMILY}",sans-serif;}}'
    return (
        "(() => { const s = new CSSStyleSheet(); s.replaceSync(" + repr(css) + ");"
        " document.adoptedStyleSheets = [...document.adoptedStyleSheets, s]; })();"
    )


def _serve_font(route: Any) -> None:
    name = route.request.url.rsplit("/", 1)[-1]
    if name in {n for n, _ in _FACES}:
        route.fulfill(path=str(FONTS / name), content_type="font/woff2")
    else:
        route.fulfill(status=404)


def _retry_script() -> str:
    """A GET that fails to connect is asked again, up to 3 times: a network change drops the requests in flight, and a
    screen keeps a failed read until the page reloads. A request that was answered, whatever the status, is not asked
    again, and nothing but a GET is."""
    return (
        "(() => { const f = window.fetch.bind(window);"
        " window.fetch = async (u, o) => { const get = ((o && o.method) || 'GET') === 'GET';"
        " for (let i = 0; ; i++) { try { return await f(u, o); }"
        " catch (e) { if (!get || i >= 3 || !(e instanceof TypeError)) throw e;"
        " await new Promise((r) => setTimeout(r, 200)); } } }; })();"
    )


def _script(ms: int) -> str:
    return (
        "(() => { const f = window.fetch.bind(window), ms = " + str(ms) + ";"
        " window.fetch = (u, o) => (((o && o.method) || 'GET') === 'GET'"
        " && /\\/api\\/v1\\/|\\.json(\\?|$)/.test(String(u))"
        " ? new Promise((r) => setTimeout(r, ms)).then(() => f(u, o)) : f(u, o)); })();"
    )


def font_in_use(page: Any) -> dict:
    """What the page lays out in, read from the page: the family its body computes to, and whether the font's faces
    (regular and bold) are loaded."""
    return page.evaluate(
        "async (fam) => { await document.fonts.ready; return {"
        " family: getComputedStyle(document.body).fontFamily,"
        " loaded: [...document.fonts].filter((f) => f.family.replace(/\"/g, '') === fam && f.status === 'loaded').length }; }",
        FAMILY,
    )


def launch(pw: Any) -> Any:
    """chromium, with the test font on every page and slowed as the environment says."""
    browser = pw.chromium.launch(slow_mo=int(os.environ.get("EVH_TEST_SLOW_MO", "0")))
    ms = int(os.environ.get("EVH_TEST_FETCH_DELAY_MS", "0"))
    new_context, new_page = browser.new_context, browser.new_page

    def dress(ctx: Any) -> Any:
        ctx.route(f"**{FONT_PATH}*", _serve_font)
        ctx.add_init_script(_font_script())
        ctx.add_init_script(_retry_script())
        if ms:
            ctx.add_init_script(_script(ms))
        ctx.on("page", _patch_page)
        for pg in ctx.pages:
            _patch_page(pg)
        return ctx

    def context(**kwargs: Any) -> Any:
        return dress(new_context(**kwargs))

    def page(**kwargs: Any) -> Any:
        pg = new_page(**kwargs)
        dress(pg.context)
        return pg

    browser.new_context, browser.new_page = context, page
    return browser
