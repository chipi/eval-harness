"""Layout checks for the Workbench's browser tests: what a screenshot review sees, measured in the page.

    cut_placeholders(page)   the text inputs whose placeholder does not fit its box (the review's "placeholders cut")
    touching(page)           pairs of form controls with no gap between them (cramped rows)
    small_targets(page)      at a phone's width, the controls under 40 px (a finger)

Each returns a list of short descriptions: empty is the pass. A screen is measured once its reads have landed.
"""

from __future__ import annotations

from typing import Any

_COMMON = r"""
const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && !e.closest('[hidden]') && !e.closest('details:not([open]) > :not(summary)'); };
const name = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.getAttribute('placeholder') ? '[' + e.getAttribute('placeholder').slice(0, 28) + ']' : '')
  + ((e.tagName === 'BUTTON' || e.tagName === 'A') ? '{' + e.textContent.trim().slice(0, 28) + '}' : '');
"""

CUT = (
    "() => {"
    + _COMMON
    + r"""
  const cv = document.createElement('canvas').getContext('2d'), out = [];
  for (const e of document.querySelectorAll('main input[placeholder]')) {
    if (!vis(e) || e.value) continue;
    const s = getComputedStyle(e); cv.font = s.font;
    const need = cv.measureText(e.getAttribute('placeholder')).width, have = e.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight);
    if (need > have + 1) out.push(name(e) + ` needs ${Math.round(need)}px, has ${Math.round(have)}px`);
  }
  return out; }"""
)

TOUCH = (
    "() => {"
    + _COMMON
    + r"""
  const ctl = [...document.querySelectorAll('main input:not([type=hidden]):not([type=checkbox]):not([type=radio]), main select, main textarea, main button, main a.btn')].filter(vis), out = [];
  for (let i = 0; i < ctl.length; i++) for (let j = i + 1; j < ctl.length; j++) {
    if (ctl[i].contains(ctl[j]) || ctl[j].contains(ctl[i])) continue;
    const a = ctl[i].getBoundingClientRect(), b = ctl[j].getBoundingClientRect();
    const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left), oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    const gapY = Math.max(b.top - a.bottom, a.top - b.bottom), gapX = Math.max(b.left - a.right, a.left - b.right);
    if ((ox > 4 && gapY >= -0.5 && gapY < 4 && oy <= 0) || (oy > 4 && gapX >= -0.5 && gapX < 4 && ox <= 0))
      out.push(name(ctl[i]) + ' | ' + name(ctl[j]) + ` gap ${Math.round(Math.max(gapY, gapX))}px`);
  }
  return out; }"""
)

SMALL = (
    "() => {"
    + _COMMON
    + r"""
  const out = [];
  for (const e of document.querySelectorAll('button, .btn, .q, .menubtn, select, input:not([type=hidden]):not([type=checkbox]):not([type=radio])')) {
    if (!vis(e)) continue;
    const r = e.getBoundingClientRect();
    if (r.height < 39.5 || (e.classList.contains('q') && r.width < 39.5)) out.push(name(e) + ` ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  return out; }"""
)


def settled(page: Any, timeout: int = 30000) -> None:
    """Wait until the screen has drawn and every read it asked for has landed."""
    page.wait_for_function(
        "() => !document.querySelector('[data-lands]') && !document.querySelector('main [role=status]')",
        timeout=timeout,
    )
    page.wait_for_timeout(400)


def cut_placeholders(page: Any) -> list[str]:
    """Text inputs whose placeholder does not fit their box."""
    return page.evaluate(CUT)


def touching(page: Any) -> list[str]:
    """Pairs of form controls with no gap between them."""
    return sorted(set(page.evaluate(TOUCH)))


def small_targets(page: Any) -> list[str]:
    """Controls under 40 px high (a finger), meant for a phone's width."""
    return sorted(set(page.evaluate(SMALL)))
