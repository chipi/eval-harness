"""The catalog's static charts: inline SVG drawn at build time, in the inspector's colour tokens
(`--s1`..`--s8`, `--muted`, `--axis`), so they follow the theme and need no script.

    stacked_bars(days, series)   counts per day, one colour per series (activity)
    cumulative(days, series)     running totals per day, one line per series (spend)
    strip(groups, lower)         one dot per value on a shared axis, a row per group

Every mark carries a <title>, which is what a pointer or a screen reader reads.
"""

from __future__ import annotations

import html
import math
from datetime import date, timedelta

SLOTS = 8
W, LEFT, RIGHT, TOP, BOTTOM = 1000, 84, 16, 12, 28


def _e(s) -> str:
    return html.escape(str(s), quote=True)


def colour(i: int) -> str:
    """The i-th series' colour: the inspector's slots, then muted."""
    return f"var(--s{i + 1})" if i < SLOTS else "var(--muted)"


def day_range(first: str, last: str) -> list[str]:
    """Every day from first to last inclusive (ISO dates)."""
    a, b = date.fromisoformat(first[:10]), date.fromisoformat(last[:10])
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def _nice(top: float) -> float:
    """A round axis maximum at or above `top`."""
    if top <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(top))
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= top:
            return m * mag
    return 10 * mag


def _axis(h: int, top: float, fmt, w: int = W) -> str:
    """Horizontal grid lines at 0, half and the top, labelled on the left."""
    out = []
    for frac in (0.0, 0.5, 1.0):
        y = TOP + (h - TOP - BOTTOM) * (1 - frac)
        out.append(
            f'<line x1="{LEFT}" x2="{w - RIGHT}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--axis)" '
            f'stroke-width="{1 if frac == 0 else 0.5}"/>'
            f'<text x="{LEFT - 6}" y="{y + 4:.1f}" text-anchor="end" class="tick">{_e(fmt(top * frac))}</text>'
        )
    return "".join(out)


def _day_labels(days: list[str], x_of, h: int) -> str:
    """The first and last day under the plot, and a middle one when there is room."""
    picks = sorted({0, len(days) - 1} | ({len(days) // 2} if len(days) > 6 else set()))
    return "".join(
        f'<text x="{x_of(i):.1f}" y="{h - 8}" text-anchor="middle" class="tick">{_e(days[i][5:])}</text>'
        for i in picks
    )


def legend(names: list[str]) -> str:
    """The series' names in their colours."""
    return (
        '<p class="legend">'
        + "".join(f'<span><i style="background:{colour(i)}"></i>{_e(n)}</span>' for i, n in enumerate(names))
        + "</p>"
    )


def stacked_bars(
    days: list[str], series: dict[str, list[float]], label: str, unit: str = "", width: int = W
) -> str:
    """One bar per day, stacked by series, its height the day's total."""
    h = 200
    names = list(series)
    totals = [sum(series[n][i] for n in names) for i in range(len(days))]
    top = _nice(max(totals, default=0))
    plot_w = width - LEFT - RIGHT
    bw = plot_w / max(len(days), 1)

    def x_of(i: int) -> float:
        return LEFT + bw * (i + 0.5)

    def y_of(v: float) -> float:
        return TOP + (h - TOP - BOTTOM) * (1 - v / top)

    bars = []
    for i, d in enumerate(days):
        base = 0.0
        for k, n in enumerate(names):
            v = series[n][i]
            if not v:
                continue
            y0, y1 = y_of(base), y_of(base + v)
            bar_w = min(max(bw * 0.76, 1), 48)  # a bar as wide as one day, never a wall
            bars.append(
                f'<rect x="{x_of(i) - bar_w / 2:.1f}" y="{y1:.1f}" width="{bar_w:.1f}" '
                f'height="{max(y0 - y1, 0.5):.1f}" fill="{colour(k)}"><title>{_e(d)} · {_e(n)}: {_e(_num(v))}'
                f"{_e(unit)}</title></rect>"
            )
            base += v
    return (
        f'<figure class="chart"><svg viewBox="0 0 {width} {h}" role="img" aria-label="{_e(label)}">'
        f"{_axis(h, top, _num, width)}{''.join(bars)}{_day_labels(days, x_of, h)}</svg>"
        f"{legend(names)}</figure>"
    )


def cumulative(days: list[str], series: dict[str, list[float]], label: str, fmt=None, width: int = W) -> str:
    """One line per series: its running total over the days."""
    fmt = fmt or _num
    h = 200
    names = list(series)
    runs = {n: _running(series[n]) for n in names}
    top = _nice(max((r[-1] for r in runs.values() if r), default=0))
    plot_w = width - LEFT - RIGHT
    step = plot_w / max(len(days) - 1, 1)

    def x_of(i: int) -> float:
        return LEFT + step * i if len(days) > 1 else LEFT + plot_w / 2

    def y_of(v: float) -> float:
        return TOP + (h - TOP - BOTTOM) * (1 - v / top)

    lines = []
    for k, n in enumerate(names):
        pts = " ".join(f"{x_of(i):.1f},{y_of(v):.1f}" for i, v in enumerate(runs[n]))
        end = runs[n][-1] if runs[n] else 0
        lines.append(
            f'<polyline points="{pts}" fill="none" stroke="{colour(k)}" stroke-width="2">'
            f"<title>{_e(n)}: {_e(fmt(end))} by {_e(days[-1] if days else '')}</title></polyline>"
            + "".join(
                f'<circle cx="{x_of(i):.1f}" cy="{y_of(v):.1f}" r="2.5" fill="{colour(k)}">'
                f"<title>{_e(days[i])} · {_e(n)}: {_e(fmt(v))} so far</title></circle>"
                for i, v in enumerate(runs[n])
                if series[n][i]
            )
        )
    return (
        f'<figure class="chart"><svg viewBox="0 0 {width} {h}" role="img" aria-label="{_e(label)}">'
        f"{_axis(h, top, fmt, width)}{''.join(lines)}{_day_labels(days, x_of, h) if days else ''}</svg>"
        f"{legend(names)}</figure>"
    )


def strip(groups: dict[str, list[tuple[float, str]]], label: str, lower: bool = False) -> str:
    """A row per group, one dot per (value, title) on one shared axis; the best end is marked."""
    vals = [v for g in groups.values() for v, _ in g]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if hi == lo:
        lo, hi = lo - 0.5, hi + 0.5
    row, left = 30, 180
    h = TOP + row * len(groups) + BOTTOM

    def x_of(v: float) -> float:
        return left + (W - left - RIGHT) * (v - lo) / (hi - lo)

    rows = []
    for r, (name, pts) in enumerate(groups.items()):
        y = TOP + row * r + row / 2
        rows.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" class="tick">{_e(name)}</text>'
            f'<line x1="{left}" x2="{W - RIGHT}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--axis)" stroke-width="0.5"/>'
            + "".join(
                f'<circle cx="{x_of(v):.1f}" cy="{y:.1f}" r="4.5" fill="{colour(r)}"><title>{_e(t)}: {_e(_num(v))}</title></circle>'
                for v, t in pts
            )
        )
    ends = (
        f'<text x="{left}" y="{h - 8}" class="tick">{_e(_num(lo))}{" · better" if lower else ""}</text>'
        f'<text x="{W - RIGHT}" y="{h - 8}" text-anchor="end" class="tick">{"" if lower else "better · "}{_e(_num(hi))}</text>'
    )
    return (
        f'<figure class="chart"><svg viewBox="0 0 {W} {h}" role="img" aria-label="{_e(label)}">'
        f"{''.join(rows)}{ends}</svg></figure>"
    )


def _running(xs: list[float]) -> list[float]:
    out, s = [], 0.0
    for x in xs:
        s += x
        out.append(s)
    return out


def _num(v: float) -> str:
    """A tick or tooltip value: whole numbers bare, small ones to their first significant digits."""
    if v == int(v) and abs(v) >= 1:
        return str(int(v))
    if abs(v) >= 10:
        return f"{v:.1f}"
    if abs(v) >= 0.01 or v == 0:
        return f"{v:.3f}".rstrip("0").rstrip(".") if v else "0"
    return f"{v:.2g}"
