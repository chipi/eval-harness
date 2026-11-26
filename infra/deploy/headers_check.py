#!/usr/bin/env python3
"""The one header of the publication: the site, the catalog, the Workbench and the docs of a rendered release, read in
a browser at desktop and phone width, must carry the same bar.

    python3 infra/deploy/headers_check.py <release-dir> [--shots DIR]

--shots: each page's top 260 px at each width, as PNGs in DIR, to look at.

The release is served as Caddy routes it on the box (infra/caddy/evals.caddy): /catalog/api/* and the Workbench by the
release's own inspector, started as compose.yml starts it (smoke_release.py), and everything else from the site's
folder. The bar is the site's (the reference, site/build.py):

- the logo, then the switcher's five pills, Harness · Catalog · Workbench · Docs · MCP, in that order, every one
  visible on the bar's one row at 1440 and at 390 px, the part shown marked;
- the logo and the switcher at the same place on all four, the bar 56 px high, no sideways scroll on a phone;
- on a phone, theme and search are in the ☰ menu, not on the bar (the pills need the room);
- the second row: the page's own sections on the site's home and the catalog's overview, the screens in the
  Workbench (its screens have few sections; the operator, 2026-11-25).

The operator found the four apart on 0.8.1 (2026-11-25): no Workbench pill on the site and the docs, the Workbench with
neither the switcher nor the second row, the catalog's bar on two rows on a phone. Needs docker and Playwright.
"""

from __future__ import annotations

import http.server
import sys
import threading
import urllib.error
import urllib.request
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke_release

PILLS = ["Harness", "Catalog", "Workbench", "Docs", "MCP"]
SITE = "evals.humancopilot.eu"
#: surface -> (path, the pill marked, a second row expected)
PAGES = {
    "site": ("/", "Harness", True),
    "catalog": ("/catalog/", "Catalog", True),
    "workbench": ("/workbench/#home", "Workbench", True),
    "docs": ("/docs/", "Docs", False),
}
PROBE = """() => {
  const bar = document.querySelector('header'); const r = bar.getBoundingClientRect();
  const vis = (el) => { if (!el) return false; const s = getComputedStyle(el), b = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && b.width > 0 && b.height > 0; };
  const box = (el) => { const b = el.getBoundingClientRect(); return {x: Math.round(b.x), y: Math.round(b.y),
    r: Math.round(b.right), h: Math.round(b.height)}; };
  const sec = bar.querySelector('nav.sections');
  const pills = sec ? [...sec.querySelectorAll('a')].map(a => ({t: a.innerText.trim(), vis: vis(a), ...box(a),
    cur: a.getAttribute('aria-current') === 'page'})) : [];
  const mark = bar.querySelector('img.mark, .eh-brand img, .brand img');
  const row1 = sec ? sec.parentElement : bar;
  const inBar = (sel) => [...bar.querySelectorAll(sel)].some(el => vis(el) && !el.closest('.menu-links, details:not([open]) > :not(summary), .md-sidebar, [hidden]'));
  const onpage = bar.querySelector('.onpage');
  return {
    row1: Math.round(row1.getBoundingClientRect().height), barH: Math.round(r.height),
    mark: mark && vis(mark) ? box(mark) : null, sections: sec && vis(sec) ? box(sec) : null, pills,
    themeOnBar: inBar('#theme, .eh-theme, button[aria-label*="light" i]'),
    searchOnBar: inBar('.search-btn, .eh-search, a[aria-label="Search the docs"]'),
    onpage: onpage && vis(onpage) ? [...onpage.querySelectorAll('a')].filter(vis).length : 0,
    scroll: document.documentElement.scrollWidth - innerWidth,
    themeInMenu: !!document.querySelector('[data-theme-toggle]'),
    // the first row's items side by side, none over another or past the screen's edge
    crowded: (() => { const xs = [...row1.children].filter(vis).filter(el => getComputedStyle(el).position !== 'absolute')
      .map(el => [el.className || el.tagName, el.getBoundingClientRect()]).sort((a, b) => a[1].left - b[1].left);
      const bad = xs.filter(([, b]) => b.left < -0.5 || b.right > innerWidth + 0.5).map(([c]) => c + ' past the edge');
      for (let i = 1; i < xs.length; i++) if (xs[i][1].left < xs[i - 1][1].right - 0.5) bad.push(xs[i - 1][0] + ' over ' + xs[i][0]);
      return bad; })(),
  };
}"""


class Proxy(http.server.SimpleHTTPRequestHandler):
    """The box's routes: the inspector for the catalog's API and the Workbench, the site's folder for the rest."""

    inspector = 0

    def do_GET(self):
        path = self.path
        if path.startswith("/catalog/api/"):
            path = path[len("/catalog") :]
        elif not (path.startswith(("/workbench", "/api/v1/"))):
            return super().do_GET()
        req = urllib.request.Request(f"http://127.0.0.1:{self.inspector}{path}", headers={"Host": SITE})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310  # nosec B310 - the release's own
                code, body, kind = r.status, r.read(), r.headers.get("Content-Type", "")
                extra = {k: v for k, v in r.headers.items() if k.lower().startswith("x-evh-")}
        except urllib.error.HTTPError as exc:
            code, body, kind, extra = exc.code, exc.read(), exc.headers.get("Content-Type", ""), {}
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class Server(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            super().handle_error(request, client_address)


def main() -> int:
    args = sys.argv[1:]
    shots = None
    if "--shots" in args:
        i = args.index("--shots")
        shots = Path(args[i + 1])
        shots.mkdir(parents=True, exist_ok=True)
        del args[i : i + 2]
    if len(args) != 1:
        print(__doc__.splitlines()[2].strip())
        return 2
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    release = Path(args[0])
    port, cname, why = smoke_release.start(release, "inspector")
    if why:
        smoke_release.stop(cname)
        print(f"HEADERS: FAIL - {why}")
        return 1
    Proxy.inspector = port
    public = release / "sites" / SITE / "public"
    httpd = Server(("127.0.0.1", 0), partial(Proxy, directory=str(public)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    failed: list[str] = []

    def check(label: str, ok: bool, detail="") -> None:
        print(f"  {'ok' if ok else 'FAIL'}  {label}" + ("" if ok else f"  {detail}"))
        if not ok:
            failed.append(label)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for width, height in ((1440, 900), (1024, 768), (860, 800), (390, 844), (360, 740)):
                ctx = browser.new_context(viewport={"width": width, "height": height})
                pg = ctx.new_page()
                seen = {}
                for name, (path, here, second) in PAGES.items():
                    pg.goto(base + path, wait_until="load")
                    pg.wait_for_timeout(2500 if name == "workbench" else 300)
                    s = pg.evaluate(PROBE)
                    if shots:
                        pg.screenshot(
                            path=str(shots / f"{name}-{width}.png"),
                            clip={"x": 0, "y": 0, "width": width, "height": 260},
                        )
                    seen[name] = s
                    at = f"{name}@{width}"
                    check(
                        f"{at}: the five pills, in order",
                        [x["t"] for x in s["pills"]] == PILLS,
                        [x["t"] for x in s["pills"]],
                    )
                    check(
                        f"{at}: every pill visible, on the bar's row, inside the screen",
                        len(s["pills"]) == 5
                        and all(x["vis"] and x["x"] >= 0 and x["r"] <= width for x in s["pills"])
                        and len({x["y"] for x in s["pills"]}) == 1,
                        [(x["t"], x["vis"], x["x"], x["r"], x["y"]) for x in s["pills"]],
                    )
                    check(
                        f"{at}: {here} marked", [x["t"] for x in s["pills"] if x["cur"]] == [here], s["pills"]
                    )
                    check(f"{at}: the logo shown", s["mark"] is not None)
                    check(f"{at}: the bar's first row 56 px (one row)", s["row1"] == 56, s["row1"])
                    check(f"{at}: no sideways scroll", s["scroll"] <= 0, s["scroll"])
                    check(
                        f"{at}: the first row's items side by side, inside the screen",
                        not s["crowded"],
                        s["crowded"],
                    )
                    if width <= 760:
                        check(f"{at}: theme and search in the menu, not on the bar", not s["themeOnBar"] and not s["searchOnBar"],
                              (s["themeOnBar"], s["searchOnBar"]))  # fmt: skip
                        check(f"{at}: the menu has the theme", s["themeInMenu"])
                    else:
                        check(f"{at}: the theme button on the bar", s["themeOnBar"])
                    if second:
                        check(f"{at}: the second row, the page's sections", s["onpage"] >= 2, s["onpage"])
                ref = seen["site"]
                for name, s in seen.items():
                    if name != "site" and s["mark"] and ref["mark"] and s["sections"] and ref["sections"]:
                        check(
                            f"{name}@{width}: the logo and the switcher where the site has them",
                            abs(s["mark"]["x"] - ref["mark"]["x"]) <= 1 and abs(s["sections"]["x"] - ref["sections"]["x"]) <= 1
                            and abs(s["sections"]["y"] - ref["sections"]["y"]) <= 1,
                            (s["mark"], s["sections"], "site:", ref["mark"], ref["sections"]),
                        )  # fmt: skip
                ctx.close()
            browser.close()
    finally:
        httpd.shutdown()
        smoke_release.stop(cname)
    print(f"HEADERS: {'FAIL' if failed else 'PASS'} ({len(failed)} failed)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
