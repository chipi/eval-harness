#!/usr/bin/env python3
"""A full-page screenshot does not repeat the sticky header mid-page (0.8.1 scenario: "Full-page screenshots repeat the
sticky header mid-page").

    python tests/test_screenshot_sticky_browser.py

A tool that captures a tall page by scrolling and stitching a viewport at a time sees `position: sticky` at the top of
every slice. Playwright's own `full_page=True` does not (one bar in the image), so the bar is counted here the way a
stitching tool meets it: at each scroll offset, whether the header sits at the top of the viewport. `_shots.static_sticky`
holds every sticky element where the page puts it for the capture and gives it back after. Run on the Workbench's and the
catalog's own stylesheets.
"""

from __future__ import annotations

import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _shots  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

SHEETS = {
    "workbench": HARNESS / "workbench" / "workbench.css",
    "catalog": HARNESS / "catalog_assets" / "style.css",
}
SLICES = """() => { const out = [], h = innerHeight;
  for (let y = 0; y < document.documentElement.scrollHeight; y += h) { scrollTo({top: y, behavior: 'instant'});
    const b = document.querySelector('.bar').getBoundingClientRect(); out.push([y, b.top, b.bottom > 0]); }
  scrollTo({top: 0, behavior: 'instant'}); return out; }"""


def stuck(slices: list) -> int:
    return sum(1 for _, top, shown in slices if shown and top == 0)


from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for name, css in SHEETS.items():
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_content(
            f"<style>{css.read_text(encoding='utf-8')}</style><header class=bar><div class=wrap>bar</div></header>"
            "<main><div style='height:5000px'>tall</div></main>"
        )
        before = stuck(page.evaluate(SLICES))
        check(
            f"{name}: scrolled in slices, the header is at the top of every one (the symptom)",
            before > 3,
            before,
        )
        with _shots.static_sticky(page):
            during = stuck(page.evaluate(SLICES))
            check(
                f"{name}: held static for the capture, the header is at the top of the first slice only",
                during == 1,
                during,
            )
        check(
            f"{name}: given back after the capture",
            page.eval_on_selector(".bar", "e => getComputedStyle(e).position") == "sticky"
            and stuck(page.evaluate(SLICES)) == before,
        )
        png = _shots.full_page(page, None)
        check(
            f"{name}: full_page returns the image and leaves the header sticky",
            png[:4] == b"\x89PNG"
            and page.eval_on_selector(".bar", "e => getComputedStyle(e).position") == "sticky",
        )
        page.close()
    browser.close()
sys.exit(summary())
