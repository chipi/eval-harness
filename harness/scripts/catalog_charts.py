"""The catalog's static charts: inline SVG drawn at build time, in the inspector's colour tokens
(`--s1`..`--s8`, `--muted`, `--axis`), so they follow the theme and need no script.

    stacked_bars(days, series)   counts per day, one colour per series (activity)
    cumulative(days, series)     running totals per day, one line per series (spend)
    strip(groups, lower)         one dot per value on a shared axis, a row per group

The evidence charts (RFC-034), drawn NARROW units wide inside a box that scrolls on a phone rather than shrinking
its text: `forest` (differences with intervals), `quadrant` (a difference in quality against one in cost),
`progress` (a study's trials and the best so far), `lines` (series over a shared x) and `heatmap` (a grid of values).
A filled mark is a difference the tests support; a hollow one is not separated.

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


def strip(
    groups: dict[str, list[tuple[float, str]]],
    label: str,
    lower: bool = False,
    marks: dict[str, list[tuple[float, str]]] | None = None,
    width: int = W,
    caption: str = "",
) -> str:
    """A row per group, one dot per (value, title) on one shared axis; the best end is marked. `marks`: per group,
    (value, name) drawn as a labelled tick across its row (a p50, a p95)."""
    vals = [v for g in groups.values() for v, _ in g]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if hi == lo:
        lo, hi = lo - 0.5, hi + 0.5
    row, left = (34, 150) if width < W else (30, 180)
    top = TOP + (12 if marks else 0)
    h = top + row * len(groups) + BOTTOM

    def x_of(v: float) -> float:
        return left + (width - left - RIGHT) * (v - lo) / (hi - lo)

    rows = []
    for r, (name, pts) in enumerate(groups.items()):
        y = top + row * r + row / 2
        rows.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" class="tick">{_e(name)}</text>'
            f'<line x1="{left}" x2="{width - RIGHT}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--axis)" stroke-width="0.5"/>'
            + "".join(
                f'<circle cx="{x_of(v):.1f}" cy="{y:.1f}" r="4.5" fill="{colour(r)}"><title>{_e(t)}: {_e(_num(v))}</title></circle>'
                for v, t in pts
            )
            + "".join(
                f'<line x1="{x_of(v):.1f}" x2="{x_of(v):.1f}" y1="{y - 11:.1f}" y2="{y + 11:.1f}" stroke="var(--ink)" '
                f'stroke-width="2"><title>{_e(name)} {_e(m)}: {_e(_num(v))}</title></line>'
                f'<text x="{x_of(v):.1f}" y="{y - 13:.1f}" text-anchor="middle" class="tick">{_e(m)}</text>'
                for v, m in (marks or {}).get(name, [])
            )
        )
    ends = (
        f'<text x="{left}" y="{h - 8}" class="tick">{_e(_num(lo))}{" · better" if lower else ""}</text>'
        f'<text x="{width - RIGHT}" y="{h - 8}" text-anchor="end" class="tick">{"" if lower else "better · "}{_e(_num(hi))}</text>'
    )
    if width < W:
        return _evidence(f"{''.join(rows)}{ends}", width, h, label, caption)
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
    log_x: bool = False,
) -> str:
    """One dot per (x, y, label, tooltip): quality against a cost or a speed, the frontier (no arm
    better on both) drawn and named, a limit as a dashed line. The better corner is said."""
    fmt_x = fmt_x or _num
    if len(points) < 2:
        return ""
    h, left, bottom = 260, 70, 40
    xs = [p[0] for p in points] + ([x_limit] if x_limit is not None else [])
    ys = [p[1] for p in points] + ([y_limit] if y_limit is not None else [])
    raw_lo, raw_hi = min(xs), max(xs)
    xt = math.log10 if log_x else (lambda v: v)
    x_lo, x_hi, y_lo, y_hi = xt(raw_lo), xt(raw_hi), min(ys), max(ys)
    if x_hi == x_lo:
        x_lo, x_hi = x_lo - 1, x_hi + 1
    if y_hi == y_lo:
        y_lo, y_hi = y_lo - 1, y_hi + 1
    pad_x, pad_y = (x_hi - x_lo) * 0.06, (y_hi - y_lo) * 0.08

    def x_of(v: float) -> float:
        return left + (width - left - RIGHT) * (xt(v) - x_lo + pad_x) / (x_hi - x_lo + 2 * pad_x)

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
            '<polyline fill="none" stroke="var(--ink-2)" stroke-width="1.5" points="'
            + " ".join(f"{x_of(p[0]):.1f},{y_of(p[1]):.1f}" for p in line)
            + '"/>'
        )
    placed: list[tuple[float, float, float]] = []
    # Names are drawn after every dot: a dot drawn later would cover a name placed before it.
    names: list[str] = []
    for i, (x, y, lab, tip) in enumerate(points):
        on = i in front
        marks.append(
            f'<circle cx="{x_of(x):.1f}" cy="{y_of(y):.1f}" r="{5 if on else 4}" '
            f'fill="{"var(--ink)" if on else "var(--muted)"}"><title>{_e(tip)}</title></circle>'
        )
        if on:
            # Named beside the dot on the side the name fits inside the plot (never cut off, never over
            # the y axis: a name too long for either side is shortened, the dot's tooltip keeps it
            # whole), moved up or down a line when it would cover a name already placed.
            room_r, room_l = width - RIGHT - (x_of(x) + 7), x_of(x) - 7 - left
            need = LABEL_W * len(lab)
            right = need > room_r and (need <= room_l or room_l > room_r)
            room = room_l if right else room_r
            if need > room:
                lab = lab[: max(1, int(room / LABEL_W) - 1)] + "…"
            tx = x_of(x) + (-7 if right else 7)
            x0, x1 = (tx - LABEL_W * len(lab), tx) if right else (tx, tx + LABEL_W * len(lab))
            ty = label_y(y_of(y) - 6, x0, x1, placed, TOP + 10, h - bottom - 4)
            if ty is not None:  # no clear line: the dot stays, its tooltip and the points table name it
                placed.append((x0, x1, ty))
                names.append(
                    f'<text x="{tx:.1f}" y="{ty:.1f}" class="tick name"'
                    f"{' text-anchor=end' if right else ''}>{_e(lab)}</text>"
                )
    marks.extend(names)
    corner = ("left" if lower_x else "right") + (" top" if higher_y else " bottom")
    frame = (
        # the axes in Muted: Axis was 1.6-1.75:1 on the card, under the 3:1 a graphic needs
        f'<line x1="{left}" x2="{width - RIGHT}" y1="{h - bottom}" y2="{h - bottom}" stroke="var(--muted)"/>'
        f'<line x1="{left}" x2="{left}" y1="{TOP}" y2="{h - bottom}" stroke="var(--muted)"/>'
        f'<text x="{x_of(raw_lo):.1f}" y="{h - bottom + 16}" text-anchor="middle" class="tick">{_e(fmt_x(raw_lo))}</text>'
        f'<text x="{x_of(raw_hi):.1f}" y="{h - bottom + 16}" text-anchor="middle" class="tick">{_e(fmt_x(raw_hi))}</text>'
        f'<text x="{(left + width) / 2:.0f}" y="{h - 6}" text-anchor="middle" class="tick">{_e(x_label)}{" (log)" if log_x else ""}</text>'
        f'<text x="{left - 6}" y="{y_of(y_hi) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_hi))}</text>'
        f'<text x="{left - 6}" y="{y_of(y_lo) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_lo))}</text>'
    )
    return (
        f'<figure class="chart"><svg viewBox="0 0 {width} {h}" role="img" aria-label="{_e(y_label)} against {_e(x_label)}">'
        f"{frame}{''.join(marks)}</svg>"
        f'<figcaption class="small muted">{_e(y_label)} against {_e(x_label)}: better is {corner}. '
        "Named and joined: the frontier, the arms no other arm beats on both.</figcaption></figure>"
    )


#: About one character of a tick label (12.5 units, so it renders at 11px or more), in viewBox units: enough to tell
#: when two names overlap.
LABEL_W = 7.8
#: The height of one label line.
LABEL_H = 16.0


def label_y(want: float, x0: float, x1: float, placed: list, top: float, bottom: float) -> float | None:
    """Where a label spanning x0..x1 goes: at `want` if no label already placed covers it, else the
    nearest line above or below that is clear, within top..bottom; None when no line is clear (the label is
    left off rather than drawn over another)."""

    def clear(y: float) -> bool:
        return all(abs(y - py) >= LABEL_H or x1 <= px0 or x0 >= px1 for px0, px1, py in placed)

    for k in range(12):
        for y in (want,) if k == 0 else (want + k * LABEL_H, want - k * LABEL_H):
            if top <= y <= bottom and clear(y):
                return y
    return None


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


# ── the evidence charts (RFC-034) ────────────────────────────────────────────
#: Their drawing width: a phone scrolls it sideways (`.chart .scroll-x svg.wide`, at least 520px wide) rather than
#: shrinking its text below what reads.
NARROW = 640


def _evidence(body: str, w: float, h: float, label: str, caption: str = "") -> str:
    """One evidence chart: the drawing in its scroll box, the caption under it."""
    return (
        f'<figure class="chart evidence"><div class="scroll-x"><svg class="wide" viewBox="0 0 {w:.0f} {h:.0f}" '
        f'role="img" aria-label="{_e(label)}">{body}</svg></div>'
        + (f'<figcaption class="small muted">{caption}</figcaption>' if caption else "")
        + "</figure>"
    )


def _domain(vals: list[float], pad: float = 0.08) -> tuple[float, float]:
    """The range of `vals`, padded, never empty."""
    lo, hi = min(vals), max(vals)
    if hi == lo:
        d = abs(lo) or 1.0
        lo, hi = lo - d / 2, hi + d / 2
    p_ = (hi - lo) * pad
    return lo - p_, hi + p_


def _short(name: str, n: int = 22) -> str:
    return name if len(name) <= n else name[: n - 1] + "…"


def _dot(x: float, y: float, filled: bool, tip: str, r: float = 5.0) -> str:
    """A filled mark (the tests support it) or a hollow one (not separated), with its title."""
    paint = 'fill="var(--ink)"' if filled else 'fill="none" stroke="var(--ink)" stroke-width="1.6"'
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" {paint}><title>{_e(tip)}</title></circle>'


def forest(rows: list[dict], label: str, x_label: str, margin: float | None = None, caption: str = "") -> str:
    """A row per arm: its difference (`est`) as a dot, its interval (`lo`..`hi`, when it has one) as a line, zero and
    the margin as vertical lines, its words (`word`) at the right. rows: {name, est, lo, hi, filled, word, tip}."""
    rows = [r for r in rows if r.get("est") is not None]
    if not rows:
        return ""
    left, right, rh, top = 150, 210, 28, 22
    vals = (
        [r["est"] for r in rows]
        + [v for r in rows for v in (r.get("lo"), r.get("hi")) if v is not None]
        + [0.0]
    )
    if margin is not None:
        vals.append(-abs(margin))
    lo, hi = _domain(vals)
    h = top + rh * len(rows) + 46

    def x_of(v: float) -> float:
        return left + (NARROW - left - right) * (v - lo) / (hi - lo)

    body = [
        f'<line x1="{x_of(0):.1f}" x2="{x_of(0):.1f}" y1="{top - 4}" y2="{top + rh * len(rows)}" stroke="var(--muted)"/>'
    ]
    if margin is not None:
        mx = x_of(-abs(margin))
        body.append(
            f'<line x1="{mx:.1f}" x2="{mx:.1f}" y1="{top - 4}" y2="{top + rh * len(rows)}" stroke="var(--local)" '
            f'stroke-dasharray="4 4"><title>the margin: {_e(_num(-abs(margin)))}</title></line>'
            f'<text x="{mx:.1f}" y="{top - 4}" text-anchor="middle" class="tick t-muted">margin</text>'
        )
    for i, r in enumerate(rows):
        y = top + rh * i + rh / 2
        body.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" class="tick"><title>{_e(r["name"])}</title>'
            f"{_e(_short(r['name']))}</text>"
        )
        if r.get("lo") is not None and r.get("hi") is not None:
            body.append(
                f'<line x1="{x_of(r["lo"]):.1f}" x2="{x_of(r["hi"]):.1f}" y1="{y:.1f}" y2="{y:.1f}" '
                f'stroke="var(--ink-2)" stroke-width="2"><title>{_e(r["name"])}: interval {_e(_num(r["lo"]))} to '
                f"{_e(_num(r['hi']))}</title></line>"
            )
        body.append(
            _dot(x_of(r["est"]), y, bool(r.get("filled")), r.get("tip") or f"{r['name']}: {_num(r['est'])}")
        )
        body.append(
            f'<text x="{NARROW - right + 8}" y="{y + 4:.1f}" class="tick">{"+" if r["est"] > 0 else ""}'
            f"{_e(_num(r['est']))} {_e(r.get('word') or '')}</text>"
        )
    base = top + rh * len(rows)
    body.append(
        f'<text x="{x_of(lo):.1f}" y="{base + 16}" class="tick">{_e(_num(lo))}</text>'
        f'<text x="{x_of(0):.1f}" y="{base + 16}" text-anchor="middle" class="tick">0</text>'
        f'<text x="{x_of(hi):.1f}" y="{base + 16}" text-anchor="end" class="tick">{_e(_num(hi))}</text>'
        f'<text x="{(left + NARROW - right) / 2:.0f}" y="{base + 38}" text-anchor="middle" class="tick">{_e(x_label)}</text>'
    )
    return _evidence("".join(body), NARROW, h, label, caption)


#: The quadrants' names (RFC-034 §3): claims, so a hollow mark sits in one by its estimate without being named by it.
QUADRANTS = ("better and cheaper", "better, costs more", "worse and cheaper", "worse, costs more")


def quadrant(
    points: list[dict], label: str, x_label: str, y_label: str, fmt_x=None, caption: str = ""
) -> str:
    """A point per arm or trial: its difference in cost (x, cheaper to the left) against its difference in quality
    (y, better up), its interval as a whisker, zero on both axes, the quadrants named in their corners.
    points: {name, x, y, ylo, yhi, filled, tip}."""
    fmt_x = fmt_x or _num
    pts = [q for q in points if q.get("x") is not None and q.get("y") is not None]
    if not pts:
        return ""
    w, h, left, right, top, bottom = NARROW, 340, 64, 16, 22, 44
    xs = [q["x"] for q in pts] + [0.0]
    ys = (
        [q["y"] for q in pts]
        + [v for q in pts for v in (q.get("ylo"), q.get("yhi")) if v is not None]
        + [0.0]
    )
    x_lo, x_hi = _domain(xs, 0.12)
    y_lo, y_hi = _domain(ys, 0.12)

    def x_of(v: float) -> float:
        return left + (w - left - right) * (v - x_lo) / (x_hi - x_lo)

    def y_of(v: float) -> float:
        return top + (h - top - bottom) * (1 - (v - y_lo) / (y_hi - y_lo))

    body = [
        f'<line x1="{left}" x2="{w - right}" y1="{y_of(0):.1f}" y2="{y_of(0):.1f}" stroke="var(--muted)"/>',
        f'<line x1="{x_of(0):.1f}" x2="{x_of(0):.1f}" y1="{top}" y2="{h - bottom}" stroke="var(--muted)"/>',
        f'<text x="{left + 4}" y="{top - 6}" class="tick t-muted">{QUADRANTS[0]}</text>',
        f'<text x="{w - right - 4}" y="{top - 6}" text-anchor="end" class="tick t-muted">{QUADRANTS[1]}</text>',
        f'<text x="{left + 4}" y="{h - bottom - 6}" class="tick t-muted">{QUADRANTS[2]}</text>',
        f'<text x="{w - right - 4}" y="{h - bottom - 6}" text-anchor="end" class="tick t-muted">{QUADRANTS[3]}</text>',
    ]
    for q in pts:
        if q.get("ylo") is not None and q.get("yhi") is not None:
            body.append(
                f'<line x1="{x_of(q["x"]):.1f}" x2="{x_of(q["x"]):.1f}" y1="{y_of(q["ylo"]):.1f}" '
                f'y2="{y_of(q["yhi"]):.1f}" stroke="var(--ink-2)" stroke-width="1.5"/>'
            )
    placed: list[tuple[float, float, float]] = []
    names = []
    for q in pts:
        cx, cy = x_of(q["x"]), y_of(q["y"])
        body.append(_dot(cx, cy, bool(q.get("filled")), q.get("tip") or q["name"]))
        lab = _short(q["name"], 18)
        right_side = cx + 8 + LABEL_W * len(lab) <= w - right
        tx = cx + 8 if right_side else cx - 8
        x0, x1 = (tx, tx + LABEL_W * len(lab)) if right_side else (tx - LABEL_W * len(lab), tx)
        ty = label_y(cy - 7, x0, x1, placed, top + 10, h - bottom - 4)
        if ty is not None:
            placed.append((x0, x1, ty))
            names.append(
                f'<text x="{tx:.1f}" y="{ty:.1f}" class="tick t-ink"{"" if right_side else " text-anchor=end"}>'
                f"{_e(lab)}</text>"
            )
    body.extend(names)
    body.append(
        f'<text x="{left}" y="{h - bottom + 16}" class="tick">{_e(fmt_x(x_lo))}</text>'
        f'<text x="{w - right}" y="{h - bottom + 16}" text-anchor="end" class="tick">{_e(fmt_x(x_hi))}</text>'
        f'<text x="{(left + w) / 2:.0f}" y="{h - 6}" text-anchor="middle" class="tick">{_e(x_label)}</text>'
        f'<text x="{left - 6}" y="{y_of(y_hi) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_hi))}</text>'
        f'<text x="{left - 6}" y="{y_of(y_lo) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_lo))}</text>'
        f'<text x="{left - 6}" y="{y_of(0) + 4:.1f}" text-anchor="end" class="tick">0</text>'
        f'<text x="12" y="{(top + h - bottom) / 2:.0f}" class="tick" transform="rotate(-90 12 '
        f'{(top + h - bottom) / 2:.0f})" text-anchor="middle">{_e(y_label)}</text>'
    )
    return _evidence("".join(body), w, h, label, caption)


def progress(
    points: list[dict], best: list[tuple[float, float]], label: str, y_label: str, caption: str = ""
) -> str:
    """A study's trials in order: each one's measure as a mark (`kept` filled, `dropped` hollow, anything else a small
    cross), the best so far as a step line from the baseline (trial 0). points: {k, y, mark, tip}."""
    pts = [q for q in points if q.get("y") is not None]
    if not pts and not best:
        return ""
    w, h, left, right, top, bottom = NARROW, 260, 64, 16, 14, 40
    ks = [q["k"] for q in pts] + [k for k, _ in best] + [0]
    ys = [q["y"] for q in pts] + [v for _, v in best]
    k_hi = max(ks) or 1
    y_lo, y_hi = _domain(ys, 0.1)

    def x_of(k: float) -> float:
        return left + (w - left - right) * k / k_hi

    def y_of(v: float) -> float:
        return top + (h - top - bottom) * (1 - (v - y_lo) / (y_hi - y_lo))

    body = [
        f'<line x1="{left}" x2="{w - right}" y1="{h - bottom}" y2="{h - bottom}" stroke="var(--muted)"/>',
        f'<line x1="{left}" x2="{left}" y1="{top}" y2="{h - bottom}" stroke="var(--muted)"/>',
    ]
    if best:
        step = []
        for i, (k, v) in enumerate(best):
            if i:
                step.append(f"{x_of(k):.1f},{y_of(best[i - 1][1]):.1f}")
            step.append(f"{x_of(k):.1f},{y_of(v):.1f}")
        step.append(f"{x_of(k_hi):.1f},{y_of(best[-1][1]):.1f}")
        body.append(
            f'<polyline points="{" ".join(step)}" fill="none" stroke="var(--s1)" stroke-width="2">'
            f"<title>the best so far: {_e(_num(best[-1][1]))}</title></polyline>"
        )
    for q in pts:
        cx, cy = x_of(q["k"]), y_of(q["y"])
        if q.get("mark") in ("kept", "dropped"):
            body.append(_dot(cx, cy, q["mark"] == "kept", q.get("tip") or f"trial {q['k']}"))
        else:
            body.append(
                f'<path d="M{cx - 4:.1f} {cy - 4:.1f}L{cx + 4:.1f} {cy + 4:.1f}M{cx - 4:.1f} {cy + 4:.1f}L{cx + 4:.1f} '
                f'{cy - 4:.1f}" stroke="var(--muted)" stroke-width="1.6"><title>{_e(q.get("tip") or "")}</title></path>'
            )
    every = max(1, round(k_hi / 10))
    body += [
        f'<text x="{x_of(k):.1f}" y="{h - bottom + 16}" text-anchor="middle" class="tick">{k}</text>'
        for k in range(0, int(k_hi) + 1, every)
    ]
    body.append(
        f'<text x="{(left + w) / 2:.0f}" y="{h - 4}" text-anchor="middle" class="tick">trial (0: the baseline)</text>'
        f'<text x="{left - 6}" y="{y_of(y_hi) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_hi))}</text>'
        f'<text x="{left - 6}" y="{y_of(y_lo) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_lo))}</text>'
        f'<text x="12" y="{(top + h - bottom) / 2:.0f}" class="tick" transform="rotate(-90 12 '
        f'{(top + h - bottom) / 2:.0f})" text-anchor="middle">{_e(y_label)}</text>'
    )
    return _evidence("".join(body), w, h, label, caption)


def lines(
    series: dict[str, list[tuple[float, float]]],
    label: str,
    x_label: str,
    y_label: str,
    x_names: dict | None = None,
    y_range: tuple[float, float] | None = None,
    caption: str = "",
) -> str:
    """One line per series over a shared x, a dot per point with its title; `x_names` labels the x values (a round's
    id, a period's date) instead of their numbers; `y_range` fixes the y axis (0..1 for a share)."""
    pts = [(x, y) for s in series.values() for x, y in s if y is not None]
    if not pts:
        return ""
    w, h, left, right, top, bottom = NARROW, 240, 64, 16, 14, 40
    xs = sorted({x for x, _ in pts})
    x_lo, x_hi = (xs[0], xs[-1]) if xs[-1] != xs[0] else (xs[0] - 1, xs[0] + 1)
    y_lo, y_hi = y_range or _domain([y for _, y in pts], 0.1)

    def x_of(v: float) -> float:
        return left + 10 + (w - left - right - 20) * (v - x_lo) / (x_hi - x_lo)

    def y_of(v: float) -> float:
        return top + (h - top - bottom) * (1 - (v - y_lo) / (y_hi - y_lo))

    body = [
        f'<line x1="{left}" x2="{w - right}" y1="{h - bottom}" y2="{h - bottom}" stroke="var(--muted)"/>',
        f'<line x1="{left}" x2="{left}" y1="{top}" y2="{h - bottom}" stroke="var(--muted)"/>',
    ]
    for i, (name, s) in enumerate(series.items()):
        s = [(x, y) for x, y in s if y is not None]
        if len(s) > 1:
            body.append(
                f'<polyline points="{" ".join(f"{x_of(x):.1f},{y_of(y):.1f}" for x, y in s)}" fill="none" '
                f'stroke="{colour(i)}" stroke-width="2"/>'
            )
        body += [
            f'<circle cx="{x_of(x):.1f}" cy="{y_of(y):.1f}" r="3.5" fill="{colour(i)}"><title>{_e(name)} · '
            f"{_e((x_names or {}).get(x, _num(x)))}: {_e(_num(y))}</title></circle>"
            for x, y in s
        ]
    shown = xs if len(xs) <= 8 else [xs[round(i * (len(xs) - 1) / 7)] for i in range(8)]
    body += [
        f'<text x="{x_of(x):.1f}" y="{h - bottom + 16}" text-anchor="middle" class="tick">'
        f"{_e(_short(str((x_names or {}).get(x, _num(x))), 10))}</text>"
        for x in shown
    ]
    body.append(
        f'<text x="{(left + w) / 2:.0f}" y="{h - 4}" text-anchor="middle" class="tick">{_e(x_label)}</text>'
        f'<text x="{left - 6}" y="{y_of(y_hi) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_hi))}</text>'
        f'<text x="{left - 6}" y="{y_of(y_lo) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_lo))}</text>'
        f'<text x="12" y="{(top + h - bottom) / 2:.0f}" class="tick" transform="rotate(-90 12 '
        f'{(top + h - bottom) / 2:.0f})" text-anchor="middle">{_e(y_label)}</text>'
    )
    return _evidence("".join(body), w, h, label, caption) + (legend(list(series)) if len(series) > 1 else "")


def heatmap(
    rows: list[str],
    cols: list[str],
    cells: dict[tuple[str, str], dict],
    label: str,
    lo: float,
    hi: float,
    caption: str = "",
    show_values: bool = True,
) -> str:
    """A grid: a row per `rows`, a column per `cols`, each cell shaded by its value between `lo` and `hi` (the darker,
    the higher), its value written when the cell is wide enough, a link when it has one. cells: {(row, col): {value,
    tip, href?}}; a missing cell is drawn empty."""
    if not rows or not cols:
        return ""
    left, top, rh, pad = 150, 100, 22, 84
    cw = max(18.0, min(64.0, (NARROW - left - pad) / len(cols)))
    w = left + cw * len(cols) + pad
    h = top + rh * len(rows) + 8
    span = (hi - lo) or 1.0
    body = []
    for j, c in enumerate(cols):
        cx = left + cw * (j + 0.5)
        body.append(
            f'<text x="{cx:.1f}" y="{top - 8}" class="tick" transform="rotate(-40 {cx:.1f} {top - 8})">'
            f"<title>{_e(c)}</title>{_e(_short(c, 14))}</text>"
        )
    for i, r in enumerate(rows):
        y = top + rh * i
        body.append(
            f'<text x="{left - 8}" y="{y + rh / 2 + 4:.1f}" text-anchor="end" class="tick"><title>{_e(r)}</title>'
            f"{_e(_short(r))}</text>"
        )
        for j, c in enumerate(cols):
            x = left + cw * j
            cell = cells.get((r, c))
            if cell is None or cell.get("value") is None:
                body.append(
                    f'<rect x="{x + 1:.1f}" y="{y + 1}" width="{cw - 2:.1f}" height="{rh - 2}" fill="var(--axis)" '
                    f'fill-opacity="0.25"><title>{_e(r)} · {_e(c)}: none</title></rect>'
                )
                continue
            v = cell["value"]
            op = 0.08 + 0.87 * min(1.0, max(0.0, (v - lo) / span))
            rect = (
                f'<rect x="{x + 1:.1f}" y="{y + 1}" width="{cw - 2:.1f}" height="{rh - 2}" fill="var(--s1)" '
                f'fill-opacity="{op:.2f}"><title>{_e(cell.get("tip") or f"{r} · {c}: {_num(v)}")}</title></rect>'
            )
            if show_values and cw >= 34:
                rect += (
                    f'<text x="{x + cw / 2:.1f}" y="{y + rh / 2 + 4:.1f}" text-anchor="middle" class="tick t-ink">'
                    f"{_e(_num(v))}</text>"
                )
            body.append(f'<a href="{_e(cell["href"])}">{rect}</a>' if cell.get("href") else rect)
    return _evidence("".join(body), w, h, label, caption)
