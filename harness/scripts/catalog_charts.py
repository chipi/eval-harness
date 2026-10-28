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


def swatch(i: int) -> str:
    """The i-th series' swatch class (catalog.css: .sw1 to .sw8, then .swm): a class, never a
    style="" attribute, which the deployed pages' Content-Security-Policy forbids."""
    return f"sw{i + 1}" if i < SLOTS else "swm"


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
        + "".join(f'<span><i class="{swatch(i)}"></i>{_e(n)}</span>' for i, n in enumerate(names))
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


def histogram(bins: list[list[int]], label: str, unit: str, width: int = W) -> str:
    """One bar per bin of [low, high, count], labelled with its range under it."""
    h = 180
    top = _nice(max((b[2] for b in bins), default=0))
    plot_w = width - LEFT - RIGHT
    bw = plot_w / max(len(bins), 1)
    bars, ticks = [], []
    for i, (lo, hi, n) in enumerate(bins):
        y1 = TOP + (h - TOP - BOTTOM) * (1 - n / top)
        span = f"{lo}" if lo == hi else f"{lo}–{hi}"
        if n:
            bars.append(
                f'<rect x="{LEFT + bw * i + bw * 0.08:.1f}" y="{y1:.1f}" width="{bw * 0.84:.1f}" '
                f'height="{max(h - BOTTOM - y1, 0.5):.1f}" fill="{colour(0)}"><title>{_e(span)} {_e(unit)}: '
                f"{n}</title></rect>"
            )
        ticks.append(
            f'<text x="{LEFT + bw * (i + 0.5):.1f}" y="{h - 8}" text-anchor="middle" class="tick">{_e(span)}</text>'
        )
    return (
        f'<figure class="chart"><svg viewBox="0 0 {width} {h}" role="img" aria-label="{_e(label)}">'
        f"{_axis(h, top, _num, width)}{''.join(bars)}{''.join(ticks)}</svg></figure>"
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


def frontier(points: list[tuple[float, float]], lower_x: bool = True, higher_y: bool = True) -> set[int]:
    """The indexes of the points no other point beats on both axes (at least as good on each,
    better on one): the trade-offs worth considering, everything else is dominated."""

    def better_eq(a, b, low):
        return a <= b if low else a >= b

    out = set()
    for i, (x, y) in enumerate(points):
        dominated = any(
            j != i and better_eq(x2, x, lower_x) and better_eq(y2, y, not higher_y) and (x2 != x or y2 != y)
            for j, (x2, y2) in enumerate(points)
        )
        if not dominated:
            out.add(i)
    return out


def scatter(
    points: list[tuple[float, float, str, str]],
    x_label: str,
    y_label: str,
    lower_x: bool = True,
    higher_y: bool = True,
    x_limit: float | None = None,
    y_limit: float | None = None,
    fmt_x=None,
    width: int = W,
) -> str:
    """One dot per (x, y, label, tooltip): quality against a cost or a speed, the frontier (no arm
    better on both) drawn and named, a limit as a dashed line. The better corner is said."""
    fmt_x = fmt_x or _num
    if len(points) < 2:
        return ""
    h, left, bottom = 260, 70, 40
    xs = [p[0] for p in points] + ([x_limit] if x_limit is not None else [])
    ys = [p[1] for p in points] + ([y_limit] if y_limit is not None else [])
    x_lo, x_hi, y_lo, y_hi = min(xs), max(xs), min(ys), max(ys)
    if x_hi == x_lo:
        x_lo, x_hi = x_lo - 1, x_hi + 1
    if y_hi == y_lo:
        y_lo, y_hi = y_lo - 1, y_hi + 1
    pad_x, pad_y = (x_hi - x_lo) * 0.06, (y_hi - y_lo) * 0.08

    def x_of(v: float) -> float:
        return left + (width - left - RIGHT) * (v - x_lo + pad_x) / (x_hi - x_lo + 2 * pad_x)

    def y_of(v: float) -> float:
        return TOP + (h - TOP - bottom) * (1 - (v - y_lo + pad_y) / (y_hi - y_lo + 2 * pad_y))

    front = frontier([(p[0], p[1]) for p in points], lower_x, higher_y)
    marks = []
    if x_limit is not None:
        marks.append(
            f'<line x1="{x_of(x_limit):.1f}" x2="{x_of(x_limit):.1f}" y1="{TOP}" y2="{h - bottom}" stroke="var(--local)" '
            f'stroke-dasharray="4 4"><title>limit {_e(fmt_x(x_limit))}</title></line>'
        )
    if y_limit is not None:
        marks.append(
            f'<line x1="{left}" x2="{width - RIGHT}" y1="{y_of(y_limit):.1f}" y2="{y_of(y_limit):.1f}" '
            f'stroke="var(--local)" stroke-dasharray="4 4"><title>limit {_e(_num(y_limit))}</title></line>'
        )
    line = sorted((points[i] for i in front), key=lambda p: p[0])
    if len(line) > 1:
        marks.append(
            '<polyline fill="none" stroke="var(--accent)" stroke-width="1.5" points="'
            + " ".join(f"{x_of(p[0]):.1f},{y_of(p[1]):.1f}" for p in line)
            + '"/>'
        )
    placed: list[tuple[float, float, float]] = []
    for i, (x, y, lab, tip) in enumerate(points):
        on = i in front
        marks.append(
            f'<circle cx="{x_of(x):.1f}" cy="{y_of(y):.1f}" r="{5 if on else 4}" '
            f'fill="{"var(--s1)" if on else "var(--muted)"}"><title>{_e(tip)}</title></circle>'
        )
        if on:
            # Named beside the dot, on its left when it sits in the right third (never cut off),
            # moved up or down a line when it would cover a name already placed.
            right = x_of(x) > left + (width - left - RIGHT) * 2 / 3
            tx = x_of(x) + (-7 if right else 7)
            x0, x1 = (tx - LABEL_W * len(lab), tx) if right else (tx, tx + LABEL_W * len(lab))
            ty = label_y(y_of(y) - 6, x0, x1, placed, TOP + 10, h - bottom - 4)
            placed.append((x0, x1, ty))
            marks.append(
                f'<text x="{tx:.1f}" y="{ty:.1f}" class="tick name"'
                f"{' text-anchor=end' if right else ''}>{_e(lab)}</text>"
            )
    corner = ("left" if lower_x else "right") + (" top" if higher_y else " bottom")
    frame = (
        f'<line x1="{left}" x2="{width - RIGHT}" y1="{h - bottom}" y2="{h - bottom}" stroke="var(--axis)"/>'
        f'<line x1="{left}" x2="{left}" y1="{TOP}" y2="{h - bottom}" stroke="var(--axis)"/>'
        f'<text x="{x_of(x_lo):.1f}" y="{h - bottom + 16}" text-anchor="middle" class="tick">{_e(fmt_x(x_lo))}</text>'
        f'<text x="{x_of(x_hi):.1f}" y="{h - bottom + 16}" text-anchor="middle" class="tick">{_e(fmt_x(x_hi))}</text>'
        f'<text x="{(left + width) / 2:.0f}" y="{h - 6}" text-anchor="middle" class="tick">{_e(x_label)}</text>'
        f'<text x="{left - 6}" y="{y_of(y_hi) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_hi))}</text>'
        f'<text x="{left - 6}" y="{y_of(y_lo) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_lo))}</text>'
    )
    return (
        f'<figure class="chart"><svg viewBox="0 0 {width} {h}" role="img" aria-label="{_e(y_label)} against {_e(x_label)}">'
        f"{frame}{''.join(marks)}</svg>"
        f'<figcaption class="small muted">{_e(y_label)} against {_e(x_label)}: better is {corner}. '
        "Named and joined: the frontier, the arms no other arm beats on both.</figcaption></figure>"
    )


#: About one character of a tick label, in viewBox units: enough to tell when two names overlap.
LABEL_W = 6.2
#: The height of one label line.
LABEL_H = 12.0


def label_y(want: float, x0: float, x1: float, placed: list, top: float, bottom: float) -> float:
    """Where a label spanning x0..x1 goes: at `want` if no label already placed covers it, else the
    nearest line above or below that is clear, within top..bottom."""

    def clear(y: float) -> bool:
        return all(abs(y - py) >= LABEL_H or x1 <= px0 or x0 >= px1 for px0, px1, py in placed)

    for k in range(12):
        for y in (want,) if k == 0 else (want + k * LABEL_H, want - k * LABEL_H):
            if top <= y <= bottom and clear(y):
                return y
    return want


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
