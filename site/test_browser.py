#!/usr/bin/env python3
"""The public harness site in a real browser (headless Chromium, through Playwright).

    make browser-check                     # from the repository root: the inspector, then this
    harness/.venv/bin/python site/test_browser.py

`site-check` proves site/public is what build.py makes; this proves what a reader gets from it.
site/public is served with the headers production sends, read from
infra/nginx/snippets/evals.humancopilot.eu-headers.conf (the Content-Security-Policy with no
'unsafe-inline', so an inline script or style that slipped past site/csp.py fails here as it
would on the box). Requests to other hosts (the analytics) are answered locally, empty.

For every page in sitemap.xml, and 404.html:
  - no console error, no CSP violation, no same-site request that fails;
  - every same-site link resolves, and every #anchor exists on its page;
  - at phone width (390px), no sideways scroll.
And the two pieces that run code: the theme toggle switches and survives a reload; the
lifecycle explorer on use.html shows a panel and switches it on click.
"""

from __future__ import annotations

import functools
import http.server
import re
import sys
import threading
from pathlib import Path
from typing import ClassVar
from urllib.parse import urldefrag, urljoin, urlparse

SITE = Path(__file__).resolve().parent
PUBLIC = SITE / "public"
HEADERS_CONF = SITE.parent / "infra" / "nginx" / "snippets" / "evals.humancopilot.eu-headers.conf"
ok: list = []


def check(label: str, cond, detail: str = "") -> None:
    ok.append((label, bool(cond)))
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"  ({detail})" if detail and not cond else ""))


def prod_headers() -> dict:
    """The headers the deploy adds, as nginx would send them (the CSP report target, rendered at
    deploy time, left out)."""
    out = {}
    for name, value in re.findall(r'^add_header\s+(\S+)\s+"([^"]*)"', HEADERS_CONF.read_text(), re.M):
        out[name] = value.replace("__CSP_REPORT__", "").strip()
    if "Content-Security-Policy" not in out:
        raise SystemExit(f"no Content-Security-Policy in {HEADERS_CONF}")
    return out


class Handler(http.server.SimpleHTTPRequestHandler):
    headers_to_add: ClassVar[dict] = {}  # set once in main(), before the server starts

    def end_headers(self):
        for k, v in self.headers_to_add.items():
            self.send_header(k, v)
        super().end_headers()

    def log_message(self, *a):
        pass


def pages() -> list:
    locs = re.findall(r"<loc>([^<]+)</loc>", (PUBLIC / "sitemap.xml").read_text())
    return [urlparse(u).path.lstrip("/") or "index.html" for u in locs] + ["404.html"]


def drive(base: str) -> None:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context()
        # Other hosts (the analytics scripts) answer locally and empty: no network, no noise.
        ctx.route(
            lambda url: urlparse(url).hostname not in ("127.0.0.1", None),
            lambda route: route.fulfill(status=200, body="", content_type="application/javascript"),
        )
        page = ctx.new_page()
        problems: list = []
        page.on("console", lambda m: problems.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(f"error: {e}"))
        page.on("requestfailed", lambda r: problems.append(f"failed: {r.url}"))
        page.on(
            "response",
            lambda r: (
                problems.append(f"{r.status}: {r.url}")
                if r.url.startswith(base) and r.status >= 400 and not r.url.endswith("/404.html")
                else None
            ),
        )

        links: set = set()
        for path in pages():
            problems.clear()
            page.goto(base + path, wait_until="load")
            check(
                f"{path}: no console error, CSP violation or failed request",
                not problems,
                "; ".join(problems[:3]),
            )
            for href in page.eval_on_selector_all("a[href]", "as => as.map(a => a.getAttribute('href'))"):
                full = urljoin(base + path, href)
                if full.startswith(base):
                    links.add(full)

        bad = []
        for link in sorted(links):
            url, frag = urldefrag(link)
            target = PUBLIC / (urlparse(url).path.lstrip("/") or "index.html")
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file() or (
                frag and not re.search(rf'\bid="{re.escape(frag)}"', target.read_text(encoding="utf-8"))
            ):
                bad.append(link)
        check(f"links: all {len(links)} same-site links and anchors resolve", not bad, ", ".join(bad[:5]))

        # The theme toggle, and that the choice survives a reload.
        page.goto(base + "index.html")
        before = page.evaluate("document.documentElement.dataset.theme || ''")
        page.click("#theme")
        after = page.evaluate("document.documentElement.dataset.theme")
        page.reload()
        kept = page.evaluate("document.documentElement.dataset.theme")
        check(
            "theme: the toggle switches the theme",
            after in ("light", "dark") and after != before,
            f"{before!r} -> {after!r}",
        )
        check("theme: the choice survives a reload", kept == after, f"{after!r} then {kept!r}")

        # The lifecycle explorer on use.html: live, a panel shown, another on click.
        page.goto(base + "use.html")
        check("explorer: the script made it live", page.locator(".lc-explorer.live").count() == 1)
        check(
            "explorer: the dataset panel shows first",
            page.locator('.lc-panel.on[data-node="dataset"]').count() == 1,
        )
        page.locator('.lc-map .lc-node[data-node="sources"]').click()
        check(
            "explorer: clicking a node shows its panel",
            page.locator('.lc-panel.on[data-node="sources"]').count() == 1
            and page.locator(".lc-panel.on").count() == 1,
        )

        phone = browser.new_context(viewport={"width": 390, "height": 844})
        phone.route(
            lambda url: urlparse(url).hostname not in ("127.0.0.1", None),
            lambda route: route.fulfill(status=200, body="", content_type="application/javascript"),
        )
        p = phone.new_page()
        wide = []
        for path in pages():
            p.goto(base + path, wait_until="load")
            over = p.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            if over > 1:
                wide.append(f"{path} +{over}px")
        check("phone width: no page scrolls sideways", not wide, ", ".join(wide))
        browser.close()


def main() -> int:
    try:
        import playwright  # noqa: F401, PLC0415
    except ImportError:
        print("  FAIL Playwright is not installed: `make -C harness browser-install`")
        return 1
    Handler.headers_to_add = prod_headers()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(PUBLIC)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        drive(f"http://127.0.0.1:{srv.server_address[1]}/")
    finally:
        srv.shutdown()
    bad = [lb for lb, c in ok if not c]
    print(f"\n{len(ok) - len(bad)}/{len(ok)} assertions passed")
    if bad:
        print("FAILED:", *bad, sep="\n  ")
    return 1 if bad or not ok else 0


if __name__ == "__main__":
    sys.exit(main())
