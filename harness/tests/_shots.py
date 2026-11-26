"""Screenshots for the tests and the scenario: a full-page capture with the header where the page puts it.

    _shots.full_page(page, path)        the whole page as a PNG (bytes returned; written to `path` when it is not None)
    with _shots.static_sticky(page):    every `position: sticky` element is static inside the block, as it was before

The bar is `position: sticky; top: 0`. A tool that captures a tall page by scrolling and stitching a viewport at a time
meets it at the top of every slice and draws it again mid-page (0.8.1 scenario). Held static for the capture, it is drawn
once, at the top.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_HOLD = """() => { window.__stickyHeld = [];
  for (const e of document.querySelectorAll('*'))
    if (getComputedStyle(e).position === 'sticky') { window.__stickyHeld.push([e, e.style.position, e.style.getPropertyPriority('position')]); e.style.setProperty('position', 'static', 'important'); } }"""
_RELEASE = """() => { for (const [e, v, p] of window.__stickyHeld || []) e.style.setProperty('position', v, p);
  window.__stickyHeld = []; }"""


@contextmanager
def static_sticky(page: Any) -> Iterator[None]:
    """Every element whose computed position is sticky held static for the block, its inline value given back after."""
    page.evaluate(_HOLD)
    try:
        yield
    finally:
        page.evaluate(_RELEASE)


def full_page(page: Any, path: str | None) -> bytes:
    """A full-page screenshot with the sticky header held static, so a tool that stitches viewports shows it once."""
    with static_sticky(page):
        return page.screenshot(path=path, full_page=True)
