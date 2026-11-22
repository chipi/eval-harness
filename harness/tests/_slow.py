"""A slow machine for the browser tests: `_slow.launch(pw)` is `pw.chromium.launch()`, and with these set it is slower.

    EVH_TEST_FETCH_DELAY_MS=200   hold every GET of /api/v1/ and of a .json file back that long, in every page and context
                                  the browser opens (a screen's reads then land after the screen is drawn and after the
                                  test has acted on it, as on CI)
    EVH_TEST_SLOW_MO=30           Playwright's slow_mo: each action waits that long

Unset, nothing changes.
"""

from __future__ import annotations

import os
from typing import Any


def _script(ms: int) -> str:
    return (
        "(() => { const f = window.fetch.bind(window), ms = " + str(ms) + ";"
        " window.fetch = (u, o) => (((o && o.method) || 'GET') === 'GET'"
        " && /\\/api\\/v1\\/|\\.json(\\?|$)/.test(String(u))"
        " ? new Promise((r) => setTimeout(r, ms)).then(() => f(u, o)) : f(u, o)); })();"
    )


def launch(pw: Any) -> Any:
    """chromium, slowed as the environment says."""
    browser = pw.chromium.launch(slow_mo=int(os.environ.get("EVH_TEST_SLOW_MO", "0")))
    ms = int(os.environ.get("EVH_TEST_FETCH_DELAY_MS", "0"))
    if not ms:
        return browser
    new_context, new_page = browser.new_context, browser.new_page

    def context(**kwargs: Any) -> Any:
        ctx = new_context(**kwargs)
        ctx.add_init_script(_script(ms))
        return ctx

    def page(**kwargs: Any) -> Any:
        pg = new_page(**kwargs)
        pg.context.add_init_script(_script(ms))
        return pg

    browser.new_context, browser.new_page = context, page
    return browser
