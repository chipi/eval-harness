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
import re
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
        f'<figure class="chart"><svg width="{width}" viewBox="0 0 {width} {h}" role="img" aria-label="{_e(label)}">'
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
        f'<figure class="chart"><svg width="{width}" viewBox="0 0 {width} {h}" role="img" aria-label="{_e(label)}">'
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
        f'<figure class="chart"><svg width="{width}" viewBox="0 0 {width} {h}" role="img" aria-label="{_e(label)}">'
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
    fmt=None,
) -> str:
    """A row per group, one dot per (value, title) on one shared axis; the best end is marked. `marks`: per group,
    (value, name) drawn as a labelled tick across its row (a p50, a p95). `fmt` writes the axis's ends (one format for
    the measure). Every value the same: no axis to draw, one label says so."""
    fmt = fmt or _num
    vals = [v for g in groups.values() for v, _ in g]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    flat = hi == lo
    base_left, row = (150, 34) if width < W else (180, 30)
    left, room = _left_for(list(groups), base_left, width, 0.42)
    if any(len(wrap_id(g, room)) > 1 for g in groups):
        row = max(row, 34)
    top = TOP + (12 if marks else 0)
    h = top + row * len(groups) + BOTTOM

    def x_of(v: float) -> float:
        return left + (width - left - RIGHT) * (0.5 if flat else (v - lo) / (hi - lo))

    def mark_labels(ms: list[tuple[float, str]]) -> list[tuple[float, str, str]]:
        """Where each mark's name is written, (x, anchor, text): centred on its tick, unless the next mark is nearer
        than a label is wide, then the pair leans apart (the earlier ends at its tick, the later starts at its), or, with
        no room to lean left (a name of the row is there), they are one label, "p50 · p95"; a label that would run into
        the row's name at the left or out of the drawing at the right starts or ends at its tick."""
        out: list[tuple[float, str, str] | None] = [(x_of(v), "middle", m) for v, m in ms]
        order = sorted(range(len(ms)), key=lambda i: ms[i][0])
        for a, b in zip(order, order[1:]):
            (xa, _, ma), (xb, _, mb) = out[a] or (0, "", ""), out[b] or (0, "", "")
            if out[a] is None or out[b] is None or xb - xa >= 28:
                continue
            if xa - 4 - LABEL_W * len(ma) >= left:
                out[a], out[b] = (xa - 4, "end", ma), (xb + 4, "start", mb)
            else:
                out[a], out[b] = (xa, "start", f"{ma} · {mb}"), None
        for k, o in enumerate(out):
            if o and o[1] == "middle":
                half = LABEL_W * len(o[2]) / 2
                if o[0] - half < left:
                    out[k] = (o[0], "start", o[2])
                elif o[0] + half > width - RIGHT:
                    out[k] = (o[0], "end", o[2])
        out = [o for o in out if o]

        def extent(o: tuple[float, str, str]) -> tuple[float, float]:
            w_ = LABEL_W * len(o[2])
            return (
                (o[0], o[0] + w_)
                if o[1] == "start"
                else (o[0] - w_, o[0])
                if o[1] == "end"
                else (o[0] - w_ / 2, o[0] + w_ / 2)
            )

        done = [o for o in out if o]
        done.sort(key=lambda o: extent(o)[0])
        k = 0
        while k + 1 < len(done):  # a leaning or clamped label can still touch its neighbour: one label then
            if extent(done[k])[1] + 2 > extent(done[k + 1])[0]:
                done[k : k + 2] = [
                    (max(extent(done[k])[0], left), "start", f"{done[k][2]} · {done[k + 1][2]}")
                ]
            else:
                k += 1
        return done

    rows = []
    for r, (name, pts) in enumerate(groups.items()):
        y = top + row * r + row / 2
        ms = (marks or {}).get(name, [])
        rows.append(
            _label_text(left - 8, y, name, room)
            + f'<line x1="{left}" x2="{width - RIGHT}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--axis)" stroke-width="0.5"/>'
            + "".join(
                f'<circle cx="{x_of(v):.1f}" cy="{y:.1f}" r="4.5" fill="{colour(r)}"><title>{_e(t)}: {_e(fmt(v))}</title></circle>'
                for v, t in pts
            )
            + "".join(
                f'<line x1="{x_of(v):.1f}" x2="{x_of(v):.1f}" y1="{y - 11:.1f}" y2="{y + 11:.1f}" stroke="var(--ink)" '
                f'stroke-width="2"><title>{_e(name)} {_e(m)}: {_e(fmt(v))}</title></line>'
                for v, m in ms
            )
            + "".join(
                f'<text x="{lx:.1f}" y="{y - 13:.1f}" text-anchor="{an}" class="tick">{_e(txt)}</text>'
                for lx, an, txt in mark_labels(ms)
            )
        )
    if flat:
        ends = (
            f'<text x="{(left + width - RIGHT) / 2:.1f}" y="{h - 8}" text-anchor="middle" class="tick">'
            f"{_e(fmt(lo))} · the same for every point</text>"
        )
    else:
        ends = (
            f'<text x="{left}" y="{h - 8}" class="tick">{_e(fmt(lo))}{" · better" if lower else ""}</text>'
            f'<text x="{width - RIGHT}" y="{h - 8}" text-anchor="end" class="tick">{"" if lower else "better · "}{_e(fmt(hi))}</text>'
        )
    if width < W:
        return _evidence(f"{''.join(rows)}{ends}", width, h, label, caption)
    return (
        f'<figure class="chart"><svg width="{W}" viewBox="0 0 {W} {h}" role="img" aria-label="{_e(label)}">'
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
    fmt_y=None,
) -> str:
    """One dot per (x, y, label, tooltip): quality against a cost or a speed, the frontier (no arm
    better on both) drawn and named, a limit as a dashed line. The better corner is said. A name is placed beside its
    dot where it covers no other name and no stretch of the frontier line; an axis whose value is the same for every
    dot is not drawn as a range, one label says so."""
    fmt_x = fmt_x or _num
    fmt_y = fmt_y or _num
    if len(points) < 2:
        return ""
    h, left, bottom = 260, 70, 40
    xs = [p[0] for p in points] + ([x_limit] if x_limit is not None else [])
    ys = [p[1] for p in points] + ([y_limit] if y_limit is not None else [])
    raw_lo, raw_hi = min(xs), max(xs)
    xt = math.log10 if log_x else (lambda v: v)
    x_lo, x_hi, y_lo, y_hi = xt(raw_lo), xt(raw_hi), min(ys), max(ys)
    flat_x, flat_y = x_hi == x_lo, y_hi == y_lo
    if flat_x:
        x_lo, x_hi = x_lo - 1, x_hi + 1
    if flat_y:
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
            f'stroke="var(--local)" stroke-dasharray="4 4"><title>limit {_e(fmt_y(y_limit))}</title></line>'
        )
    line = sorted((points[i] for i in front), key=lambda p: p[0])
    joined = [(x_of(p[0]), y_of(p[1])) for p in line]
    if len(joined) > 1:
        marks.append(
            '<polyline fill="none" stroke="var(--ink-2)" stroke-width="1.5" points="'
            + " ".join(f"{x:.1f},{y:.1f}" for x, y in joined)
            + '"/>'
        )
    segments = list(zip(joined, joined[1:]))
    placed: list[tuple[float, float, float]] = []
    flat_note = f"{fmt_y(ys[0])} · the same for every dot"
    if flat_y:
        placed.append((left + 8, left + 8 + LABEL_W * len(flat_note), y_of(ys[0]) - 8))
    dots = [(x_of(p[0]), y_of(p[1]), 5 if i in front else 4) for i, p in enumerate(points)]
    # Names are drawn after every dot: a dot drawn later would cover a name placed before it.
    names: list[str] = []
    unnamed: list[str] = []
    for i, (x, y, lab, tip) in enumerate(points):
        on = i in front
        marks.append(
            f'<circle cx="{x_of(x):.1f}" cy="{y_of(y):.1f}" r="{5 if on else 4}" '
            f'fill="{"var(--ink)" if on else "var(--muted)"}"><title>{_e(tip)}</title></circle>'
        )
        if on:
            # Named beside the dot on the side the name fits inside the plot (never cut off, never over
            # the y axis: a name too long for either side is shortened, the dot's tooltip keeps it
            # whole), moved up or down a line when it would cover a name already placed, a dot or a stretch of the line.
            room_r, room_l = width - RIGHT - (x_of(x) + 7), x_of(x) - 7 - left
            need = LABEL_W * len(lab)
            prefer_left = need > room_r and (need <= room_l or room_l > room_r)
            # a side where the whole name fits first (the nearer to the dot's preferred side); a place clear of the line
            # first, one the line crosses (the halo keeps it readable) only when none is; a name is never drawn over a
            # dot. With no clear place beside the dot: the name goes where there is one, a leader line to its dot; then
            # a shortened name beside it; where there is none, the caption names it (the tooltip and the points table too)
            done = False
            for whole_only in (True, False):
                if not whole_only:
                    spot = _leader_spot(
                        (x_of(x), y_of(y)),
                        need,
                        dots,
                        placed,
                        segments,
                        (left + 4, width - RIGHT - 4, TOP + 14, h - bottom - 4),
                    )
                    if spot is not None:
                        x0, ty, sx, sy, ex, ey = spot
                        placed.append((x0, x0 + need, ty))
                        names.append(
                            f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" class="leader" '
                            f'stroke="var(--muted)" stroke-width="1"/>'
                            f'<text x="{x0:.1f}" y="{ty:.1f}" class="tick name">{_e(lab)}</text>'
                        )
                        done = True
                        break
                for strict in (True, False):
                    for left_side in sorted(
                        (True, False), key=lambda ls: (need > (room_l if ls else room_r), ls != prefer_left)
                    ):
                        room = room_l if left_side else room_r
                        if whole_only and need > room:
                            continue
                        keep = max(1, int(room / LABEL_W) - 1)
                        if need > room and keep < min(5, len(lab) - 1):
                            continue  # "b…" names nothing: the caption does
                        text = lab if need <= room else lab[:keep] + "…"
                        tx = x_of(x) + (-7 if left_side else 7)
                        x0, x1 = (
                            (tx - LABEL_W * len(text), tx) if left_side else (tx, tx + LABEL_W * len(text))
                        )
                        at = label_y(
                            y_of(y) - 6,
                            x0,
                            x1,
                            placed,
                            TOP + 2,
                            h - bottom - 4,
                            lambda yy, x0=x0, x1=x1, strict=strict: (
                                not _dot_under(dots, x0, x1, yy)
                                and not (strict and _crossed(segments, x0, x1, yy))
                            ),
                            NEAR,
                        )
                        if at is not None:
                            placed.append((x0, x1, at))
                            names.append(
                                f'<text x="{tx:.1f}" y="{at:.1f}" class="tick name"'
                                f"{END if left_side else ''}>{_e(text)}</text>"
                            )
                            done = True
                            break
                    if done:
                        break
                if done:
                    break
            if not done:
                unnamed.append(f"{lab} ({fmt_x(x)}, {fmt_y(y)})")
    marks.extend(names)
    corner = ("left" if lower_x else "right") + (" top" if higher_y else " bottom")
    if flat_x:
        x_ticks = (
            f'<text x="{(left + width - RIGHT) / 2:.1f}" y="{h - bottom + 16}" text-anchor="middle" class="tick">'
            f"{_e(fmt_x(raw_lo))} · the same for every dot</text>"
        )
    else:
        x_ticks = (
            f'<text x="{x_of(raw_lo):.1f}" y="{h - bottom + 16}" text-anchor="middle" class="tick">{_e(fmt_x(raw_lo))}</text>'
            f'<text x="{x_of(raw_hi):.1f}" y="{h - bottom + 16}" text-anchor="middle" class="tick">{_e(fmt_x(raw_hi))}</text>'
        )
    if flat_y:
        y_ticks = f'<text x="{left + 8}" y="{y_of(ys[0]) - 8:.1f}" class="tick">{_e(flat_note)}</text>'
    else:
        y_ticks = (
            f'<text x="{left - 6}" y="{y_of(y_hi) + 4:.1f}" text-anchor="end" class="tick">{_e(fmt_y(y_hi))}</text>'
            f'<text x="{left - 6}" y="{y_of(y_lo) + 4:.1f}" text-anchor="end" class="tick">{_e(fmt_y(y_lo))}</text>'
        )
    frame = (
        # the axes in Muted: Axis was 1.6-1.75:1 on the card, under the 3:1 a graphic needs
        f'<line x1="{left}" x2="{width - RIGHT}" y1="{h - bottom}" y2="{h - bottom}" stroke="var(--muted)"/>'
        f'<line x1="{left}" x2="{left}" y1="{TOP}" y2="{h - bottom}" stroke="var(--muted)"/>'
        + x_ticks
        + f'<text x="{(left + width) / 2:.0f}" y="{h - 6}" text-anchor="middle" class="tick">{_e(x_label)}{" (log)" if log_x else ""}</text>'
        + y_ticks
    )
    return (
        f'<figure class="chart"><svg width="{width}" viewBox="0 0 {width} {h}" role="img" aria-label="{_e(y_label)} against {_e(x_label)}">'
        f"{frame}{''.join(marks)}</svg>"
        f'<figcaption class="small muted">{_e(y_label)} against {_e(x_label)}: better is {corner}. '
        "Named and joined: the frontier, the arms no other arm beats on both."
        + (f" No clear place on the chart for: {_e('; '.join(unnamed))} (hover its dot)." if unnamed else "")
        + "</figcaption></figure>"
    )


#: The attribute of a label that ends at its x.
END = ' text-anchor="end"'

#: About one character of a tick label (12.5 units, so it renders at 11px or more), in viewBox units: enough to tell
#: when two names overlap.
LABEL_W = 7.8
#: The height of one label line.
LABEL_H = 16.0
#: How many lines a name may move from its dot (up or down) before it goes to a leader line.
NEAR = 4
#: The clear space between two names on one line: a real font is wider than LABEL_W, so names that only touch overlap.
LABEL_GAP = 6.0


def label_y(
    want: float, x0: float, x1: float, placed: list, top: float, bottom: float, ok=None, reach: int = 12
) -> float | None:
    """Where a label spanning x0..x1 goes: at `want` if no label already placed covers it, else the
    nearest line above or below that is clear, within top..bottom; None when no line is clear (the label is
    left off rather than drawn over another). `ok(y)` can refuse a line for another reason (a stretch of a line
    drawn there)."""

    def clear(y: float) -> bool:
        return all(
            abs(y - py) >= LABEL_H or x1 + LABEL_GAP <= px0 or x0 >= px1 + LABEL_GAP
            for px0, px1, py in placed
        ) and (ok is None or ok(y))

    for k in range(reach):
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
        f'<figure class="chart evidence"><div class="scroll-x"><svg class="wide" width="{w:.0f}" viewBox="0 0 {w:.0f} {h:.0f}" '
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
    """`name` in at most `n` characters, the middle left out: what tells two arms apart is mostly at the end (v1, v2)."""
    if len(name) <= n:
        return name
    tail = (n - 1) * 2 // 3
    return f"{name[: n - 1 - tail]}…{name[len(name) - tail :]}"


def _room(px: float) -> int:
    """How many characters of a row label fit in `px` pixels."""
    return max(4, int(px / LABEL_W))


_BREAK = re.compile(r"(?<=[_/.\- ])")


def wrap_id(name: str, n: int, max_lines: int = 2) -> list[str]:
    """`name` in lines of at most `n` characters, broken only after a separator (_ / . - or a space), never inside a
    word. An id that has no room even so is shortened in its middle (its tooltip keeps it whole)."""
    lines: list[str] = []
    cur = ""
    for part in (p for p in _BREAK.split(name) if p):
        if cur and len(cur) + len(part.rstrip()) > n:
            lines.append(cur.rstrip())
            cur = part
        else:
            cur += part
    lines.append(cur.rstrip())
    if len(lines) > max_lines:
        lines = [*lines[: max_lines - 1], "".join(lines[max_lines - 1 :])]
    return [ln if len(ln) <= n else _short(ln, n) for ln in lines]


def _label_text(x: float, y: float, name: str, n: int, anchor: str = "end", lh: float = 13.0) -> str:
    """A row's name at its (x, y) centre, wrapped at a separator over up to two lines; the full name is its tooltip."""
    ls = wrap_id(name, n)
    y0 = y + 4 - (len(ls) - 1) * lh / 2
    spans = "".join(f'<tspan x="{x:.1f}" y="{y0 + k * lh:.1f}">{_e(t)}</tspan>' for k, t in enumerate(ls))
    return f'<text x="{x:.1f}" y="{y0:.1f}" text-anchor="{anchor}" class="tick"><title>{_e(name)}</title>{spans}</text>'


def _left_for(names: list[str], base: float, width: float, frac: float = 0.34) -> tuple[int, int]:
    """(the room left of a plot, characters per line there) for row names: wide enough for the longest on one line,
    at most `frac` of the chart; a longer one wraps."""
    longest = max((len(n) for n in names), default=0)
    left = int(min(max(base, longest * LABEL_W + 14), max(base, width * frac)))
    return left, _room(left - 8)


def _dot_under(dots: list, x0: float, x1: float, yy: float) -> bool:
    """Whether any dot (cx, cy, r) is under a label spanning x0..x1 at baseline yy (the box _crossed uses)."""
    return any(x0 - r < cx < x1 + r and yy - 13 - r < cy < yy + 5 + r for cx, cy, r in dots)


def _leader_spot(
    dot: tuple[float, float],
    w: float,
    dots: list,
    placed: list,
    segments: list,
    bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float, float, float] | None:
    """The nearest place for a label `w` wide, clear of every dot, name and stretch of the line, and a straight leader
    to it clear of the other dots: (x0, baseline, leader start at the dot's edge, leader end), or None."""
    cx, cy = dot
    xa, xb, ya, yb = bounds
    best: tuple[float, tuple[float, float, float, float, float, float]] | None = None
    x0 = xa
    while x0 + w <= xb:
        for y in range(int(ya), int(yb) + 1, 8):
            if (
                _dot_under(dots, x0, x0 + w, y)
                or _crossed(segments, x0, x0 + w, y)
                or any(
                    abs(y - py) < LABEL_H and x0 < px1 + LABEL_GAP and x0 + w + LABEL_GAP > px0
                    for px0, px1, py in placed
                )
            ):
                continue
            ex, ey = min(max(cx, x0), x0 + w), min(max(cy, y - 13), y + 5)
            d = math.hypot(ex - cx, ey - cy)
            if d == 0 or (best is not None and d >= best[0]):
                continue
            sx, sy = cx + (ex - cx) / d * 5, cy + (ey - cy) / d * 5
            along = [(sx + (ex - sx) * k / 20, sy + (ey - sy) * k / 20) for k in range(21)]
            if any(
                math.hypot(px - ox, py - oy) < r + 1.5 and (ox, oy) != (cx, cy)
                for px, py in along
                for ox, oy, r in dots
            ):
                continue
            best = (d, (x0, y, sx, sy, ex, ey))
        x0 += 6
    return best[1] if best else None


def _crossed(segments: list, x0: float, x1: float, y: float) -> bool:
    """Whether any of the line `segments` ((x, y) to (x, y)) passes through a label spanning x0..x1 at baseline y."""
    for (ax, ay), (bx, by) in segments:
        # Every sample lies in the segment's box (give or take a rounding, which the 1e-6 covers): one that misses the
        # label's box has none in it. 36,180 calls on this repository's goal pages.
        if (
            max(ax, bx) + 1e-6 < x0 - 2
            or min(ax, bx) - 1e-6 > x1 + 2
            or max(ay, by) + 1e-6 < y - 13
            or min(ay, by) - 1e-6 > y + 5
        ):
            continue
        for k in range(41):
            px, py = ax + (bx - ax) * k / 40, ay + (by - ay) * k / 40
            if x0 - 2 <= px <= x1 + 2 and y - 13 <= py <= y + 5:
                return True
    return False


def _dot(x: float, y: float, filled: bool, tip: str, r: float = 5.0) -> str:
    """A filled mark (the tests support it) or a hollow one (not separated), with its title."""
    paint = 'fill="var(--ink)"' if filled else 'fill="none" stroke="var(--ink)" stroke-width="1.6"'
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" {paint}><title>{_e(tip)}</title></circle>'


def forest(
    rows: list[dict], label: str, x_label: str, margin_at: float | None = None, caption: str = ""
) -> str:
    """A row per arm: its difference (`est`) as a dot, its interval (`lo`..`hi`, when it has one) as a line, zero and
    the margin as vertical lines, its words (`word`) at the right. rows: {name, est, lo, hi, filled, word, tip}. The
    drawing is as wide as its names and words need (a phone scrolls it): a name is wrapped at a separator, a word never
    cut at the edge."""
    rows = [r for r in rows if r.get("est") is not None]
    if not rows:
        return ""
    words = [f"{'+' if r['est'] > 0 else ''}{_num(r['est'])} {r.get('word') or ''}" for r in rows]
    right = int(min(max(210, LABEL_W * max(len(t) for t in words) + 16), 470))
    left, room = _left_for([r["name"] for r in rows], 150, 900, 0.3)
    rh = 32 if any(len(wrap_id(r["name"], room)) > 1 for r in rows) else 28
    top = 22
    w = left + 280 + right
    vals = (
        [r["est"] for r in rows]
        + [v for r in rows for v in (r.get("lo"), r.get("hi")) if v is not None]
        + [0.0]
    )
    if margin_at is not None:
        vals.append(margin_at)
    lo, hi = _domain(vals)
    h = top + rh * len(rows) + 46

    def x_of(v: float) -> float:
        return left + (w - left - right) * (v - lo) / (hi - lo)

    body = [
        f'<line x1="{x_of(0):.1f}" x2="{x_of(0):.1f}" y1="{top - 4}" y2="{top + rh * len(rows)}" stroke="var(--muted)"/>'
    ]
    if margin_at is not None:
        mx = x_of(margin_at)
        body.append(
            f'<line x1="{mx:.1f}" x2="{mx:.1f}" y1="{top - 4}" y2="{top + rh * len(rows)}" stroke="var(--local)" '
            f'stroke-dasharray="4 4"><title>the margin: {_e(_num(margin_at))}</title></line>'
            f'<text x="{mx:.1f}" y="{top - 4}" text-anchor="middle" class="tick t-muted">margin</text>'
        )
    for i, r in enumerate(rows):
        y = top + rh * i + rh / 2
        body.append(_label_text(left - 8, y, r["name"], room))
        if r.get("lo") is not None and r.get("hi") is not None:
            body.append(
                f'<line x1="{x_of(r["lo"]):.1f}" x2="{x_of(r["hi"]):.1f}" y1="{y:.1f}" y2="{y:.1f}" '
                f'stroke="var(--ink-2)" stroke-width="2"><title>{_e(r["name"])}: interval {_e(_num(r["lo"]))} to '
                f"{_e(_num(r['hi']))}</title></line>"
            )
        body.append(
            _dot(x_of(r["est"]), y, bool(r.get("filled")), r.get("tip") or f"{r['name']}: {_num(r['est'])}")
        )
        body.append(f'<text x="{w - right + 8}" y="{y + 4:.1f}" class="tick">{_e(words[i])}</text>')
    base = top + rh * len(rows)

    def end(v: float, anchor: str) -> str:
        """An end of the axis, labelled unless its label would sit on zero's ("0" and "0.002" read "0002")."""
        if abs(x_of(v) - x_of(0)) < LABEL_W * (len(_num(v)) + 2):
            return ""
        return f'<text x="{x_of(v):.1f}" y="{base + 16}"{anchor} class="tick">{_e(_num(v))}</text>'

    body.append(
        end(lo, "")
        + f'<text x="{x_of(0):.1f}" y="{base + 16}" text-anchor="middle" class="tick">0</text>'
        + end(hi, ' text-anchor="end"')
        + f'<text x="{(left + w - right) / 2:.0f}" y="{base + 38}" text-anchor="middle" class="tick">{_e(x_label)}</text>'
    )
    return _evidence("".join(body), w, h, label, caption)


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
    # Every point at a difference of 0 on x (no cost recorded that differs): a range of -0.62 .. +0.62 would be made up
    flat_x = all(q["x"] == 0 for q in pts)
    flat_y = all(v == 0 for v in ys)

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
                f'<text x="{tx:.1f}" y="{ty:.1f}" class="tick t-ink"{"" if right_side else END}>'
                f"{_e(lab)}</text>"
            )
    body.extend(names)
    x_ticks = (
        f'<text x="{x_of(0):.1f}" y="{h - bottom + 16}" text-anchor="middle" class="tick">the same for every point: {_e(fmt_x(0.0).lstrip("+"))}</text>'
        if flat_x
        else f'<text x="{left}" y="{h - bottom + 16}" class="tick">{_e(fmt_x(x_lo))}</text>'
        f'<text x="{w - right}" y="{h - bottom + 16}" text-anchor="end" class="tick">{_e(fmt_x(x_hi))}</text>'
    )
    y_ticks = (
        f'<text x="{left - 6}" y="{y_of(0) + 4:.1f}" text-anchor="end" class="tick">0</text>'
        if flat_y
        else f'<text x="{left - 6}" y="{y_of(y_hi) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_hi))}</text>'
        f'<text x="{left - 6}" y="{y_of(y_lo) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_lo))}</text>'
        f'<text x="{left - 6}" y="{y_of(0) + 4:.1f}" text-anchor="end" class="tick">0</text>'
    )
    body.append(
        x_ticks
        + y_ticks
        + f'<text x="{(left + w) / 2:.0f}" y="{h - 6}" text-anchor="middle" class="tick">{_e(x_label)}</text>'
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
    if len(set(ys)) == 1:
        y_ticks = f'<text x="{left + 8}" y="{y_of(ys[0]) - 8:.1f}" class="tick">{_e(_num(ys[0]))} · the same at every trial</text>'
    else:
        y_ticks = (
            f'<text x="{left - 6}" y="{y_of(y_hi) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_hi))}</text>'
            f'<text x="{left - 6}" y="{y_of(y_lo) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_lo))}</text>'
        )
    body.append(
        f'<text x="{(left + w) / 2:.0f}" y="{h - 4}" text-anchor="middle" class="tick">trial (0: the baseline)</text>'
        + y_ticks
        + f'<text x="12" y="{(top + h - bottom) / 2:.0f}" class="tick" transform="rotate(-90 12 '
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
    id, a period's date) instead of their numbers, wrapped at a separator where the ticks are close; `y_range` fixes
    the y axis (0..1 for a share). A y that is the same at every point is not drawn as a range: one label says so."""
    pts = [(x, y) for s in series.values() for x, y in s if y is not None]
    if not pts:
        return ""
    xs = sorted({x for x, _ in pts})
    shown = xs if len(xs) <= 8 else [xs[round(i * (len(xs) - 1) / 7)] for i in range(8)]
    w, left, right, top = NARROW, 64, 16, 14
    span = w - left - right - 20
    room = max(6, int((span / max(len(shown) - 1, 1)) / LABEL_W) - 1)
    ticks = {x: wrap_id(str((x_names or {}).get(x, _num(x))), room, 3) for x in shown}
    extra = max(len(t) for t in ticks.values()) - 1
    h, bottom = 244 + 13 * extra, 44 + 13 * extra
    x_lo, x_hi = (xs[0], xs[-1]) if xs[-1] != xs[0] else (xs[0] - 1, xs[0] + 1)
    flat = y_range is None and len({y for _, y in pts}) == 1 and len(pts) > 1
    y_lo, y_hi = y_range or _domain([y for _, y in pts], 0.1)

    def x_of(v: float) -> float:
        return left + 10 + span * (v - x_lo) / (x_hi - x_lo)

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
    for x in shown:
        half = LABEL_W * max(len(t) for t in ticks[x]) / 2
        cx = min(max(x_of(x), 2 + half), w - 2 - half)
        body.append(
            f'<text x="{cx:.1f}" y="{h - bottom + 20}" text-anchor="middle" class="tick"><title>'
            f"{_e((x_names or {}).get(x, _num(x)))}</title>"
            + "".join(
                f'<tspan x="{cx:.1f}" y="{h - bottom + 20 + 13 * k}">{_e(t)}</tspan>'
                for k, t in enumerate(ticks[x])
            )
            + "</text>"
        )
    if flat:
        y_ticks = f'<text x="{left + 8}" y="{y_of(pts[0][1]) - 8:.1f}" class="tick">{_e(_num(pts[0][1]))} · the same at every point</text>'
    else:
        y_ticks = (
            f'<text x="{left - 6}" y="{y_of(y_hi) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_hi))}</text>'
            f'<text x="{left - 6}" y="{y_of(y_lo) + 4:.1f}" text-anchor="end" class="tick">{_e(_num(y_lo))}</text>'
        )
    body.append(
        f'<text x="{(left + w) / 2:.0f}" y="{h - 4}" text-anchor="middle" class="tick">{_e(x_label)}</text>'
        + y_ticks
        + f'<text x="12" y="{(top + h - bottom) / 2:.0f}" class="tick" transform="rotate(-90 12 '
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
    tip, href?}}; a missing cell is drawn empty. The cells grow to hold the values (a phone scrolls the drawing
    sideways); with so many columns that they would not fit in a thousand units, no value is written, each stays in
    its cell's tooltip. A row's name is wrapped at a separator, never shortened."""
    if not rows or not cols:
        return ""
    left, room = _left_for(rows, 150, 900, 0.3)
    col_chars = max(len(c) for c in cols)
    top = max(100, int(col_chars * LABEL_W * 0.64) + 24)
    pad = max(84, int(col_chars * LABEL_W * 0.77) + 8)
    rh = 30 if any(len(wrap_id(r, room)) > 1 for r in rows) else 22
    cw = max(18.0, min(64.0, (NARROW - left - pad) / len(cols)))
    written = max((len(_num(c["value"])) for c in cells.values() if c.get("value") is not None), default=0)
    need = LABEL_W * written + 8
    draw = show_values and written > 0
    if draw and cw < need:
        if left + need * len(cols) + pad <= 1000:
            cw = need
        else:
            draw = False
    w = left + cw * len(cols) + pad
    h = top + rh * len(rows) + 8
    span = (hi - lo) or 1.0
    body = []
    for j, c in enumerate(cols):
        cx = left + cw * (j + 0.5)
        body.append(
            f'<text x="{cx:.1f}" y="{top - 8}" class="tick" transform="rotate(-40 {cx:.1f} {top - 8})">'
            f"<title>{_e(c)}</title>{_e(c)}</text>"
        )
    for i, r in enumerate(rows):
        y = top + rh * i
        body.append(_label_text(left - 8, y + rh / 2, r, room))
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
            if draw:
                rect += (
                    f'<text x="{x + cw / 2:.1f}" y="{y + rh / 2 + 4:.1f}" text-anchor="middle" class="tick t-ink">'
                    f"{_e(_num(v))}</text>"
                )
            body.append(f'<a href="{_e(cell["href"])}">{rect}</a>' if cell.get("href") else rect)
    return _evidence("".join(body), w, h, label, caption)
