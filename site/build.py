#!/usr/bin/env python3
"""Generate the static site in site/public/ from the committed runs.

    python site/build.py            # write site/public/
    python site/build.py --check    # rebuild into a temp dir and fail on any difference

Every figure comes from `figures.py`, which computes it from the runs and evidence the
reports are checked against. Prose that QUOTES a report goes through `q()`, which fails
the build if any number written in that prose is absent from the report it cites — so
the site can only repeat what a checked report says, never paraphrase a number into
something new. Charts are inline SVG generated here; the pages load nothing external.
"""

from __future__ import annotations

import argparse
import filecmp
import html
import json
import math
import re
import shutil
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import csp  # noqa: E402
import figures  # noqa: E402
import method  # noqa: E402
import releases  # noqa: E402
import remeasured  # noqa: E402

ROOT = HERE.parent
REPO = "https://github.com/chipi/eval-harness"
BLOB = f"{REPO}/blob/main"
SITE = "https://evals.humancopilot.eu"
#: The docs (mkdocs, GitHub Pages) and the harness's own deployment for these experiments
#: (catalog, goal pages, run inspector) live on their own subdomains, linked from the nav.
DOCS = "https://evals.humancopilot.eu/docs/"
CATALOG = "https://evals.humancopilot.eu/catalog/"
# The bar's icons, drawn the same on the site, in the catalog (catalog_build.ICON) and in the
# docs (site/docs_theme/partials/header.html): a glyph like ☰ or ◐ renders differently per font.
_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">'
ICON = {
    "menu": _SVG + '<path d="M4 7h16M4 12h16M4 17h16"/></svg>',
    "search": _SVG + '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg>',
    "theme": _SVG
    + '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/></svg>',
    # GitHub's mark (Octicons mark-github, MIT), filled, at the other icons' size.
    "github": '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor">'
    '<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49'
    "-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82"
    ".72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15"
    "-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82"
    " 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48"
    ' 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>',
}
OUT = HERE / "public"
#: The harness version the site describes, from the one place it is set.
VERSION = re.search(
    r'__version__ = "([^"]+)"', (ROOT / "harness" / "scripts" / "_version.py").read_text()
).group(1)
#: Replaced at deploy (pages.yml) with the commit being served; a local build says so.
BUILD_MARK = "build: local"


# ── the quote guard ─────────────────────────────────────────────────────────
_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
_REPORT_TEXT: dict = {}


def q(template: str, report: str, **vals) -> str:
    """Render prose that quotes `report`. Every number typed into `template` (outside
    {placeholders}) must appear in the report, or the build stops."""
    if report not in _REPORT_TEXT:
        _REPORT_TEXT[report] = (ROOT / report).read_text(encoding="utf-8").replace(",", "")
    literal = re.sub(r"\{[a-z_0-9]+\}", "", template)
    for n in _NUM.findall(literal):
        if n.replace(",", "") not in _REPORT_TEXT[report]:
            raise SystemExit(f"site copy quotes {n!r}, which {report} does not contain:\n  {template[:120]}")
    return template.format(**vals)


def _plain(text: str) -> str:
    """Text as a reader sees it: no markdown emphasis or code marks, one space between words."""
    return " ".join(re.sub(r"[`*]", "", text).split())


def qv(sentence: str, report: str) -> str:
    """A verbatim quote: the whole sentence must appear in `report`, formatting aside (code
    marks, emphasis, line breaks), or the build stops. q() checks only a quote's numbers, so
    a paraphrase passes it; anything the page presents as the report's own words uses this."""
    q(sentence, report)
    key = f"plain:{report}"
    if key not in _REPORT_TEXT:
        _REPORT_TEXT[key] = _plain((ROOT / report).read_text(encoding="utf-8"))
    if _plain(sentence) not in _REPORT_TEXT[key]:
        raise SystemExit(
            f"site copy quotes, as {report}'s own words, a sentence it does not contain:\n  {sentence[:160]}"
        )
    return sentence


def e(s) -> str:
    return html.escape(str(s), quote=True)


def money(x: float) -> str:
    return f"${x:,.2f}" if x >= 0.995 else f"${x:.4f}"


def times(x: float) -> str:
    # As the reports state them: whole multiples truncated (115.66 is "115×", never "116×"),
    # small ones to one decimal (2.49 is "2.5×").
    return f"{math.floor(x)}×" if x >= 10 else f"{x:.1f}×"


_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def word(n: int) -> str:
    """A small count as prose writes it: 6 is "six"."""
    return _WORDS[n] if 0 <= n < len(_WORDS) else str(n)


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


KIND = {"proprietary": "proprietary", "open": "open", "local": "local", "baseline": "baseline"}
KIND_LABEL = {
    "proprietary": "hosted · proprietary",
    "open": "hosted · open weights",
    "local": "local · free",
    "baseline": "baseline",
}


def kind_of(a: dict) -> str:
    return a["weights"] if a["kind"] == "hosted" and a["weights"] else a["kind"]


def legend(band: bool = True, reading: str = "", baseline: bool = True) -> str:
    kinds = ("proprietary", "open", "local") + (("baseline",) if baseline else ())
    items = "".join(f'<span><i style="background:var(--{k})"></i>{KIND_LABEL[k]}</span>' for k in kinds)
    if band:
        items += '<span><i class="sw-band"></i>not separated from the leader</span>'
    if reading:
        items += f'<span class="read">{reading}</span>'
    return f'<div class="legend">{items}</div>'


def both(wide: str, narrow: str) -> str:
    """A chart drawn twice: the wide layout, and a phone layout CSS swaps in under 700px."""
    return f'<div class="vw">{wide}</div><div class="vn">{narrow}</div>'


# ── charts ──────────────────────────────────────────────────────────────────
def dot(cx: float, cy: float, r: float, k: str, tip: str) -> str:
    """A data dot, plus a larger transparent circle on top so a fingertip can hit it."""
    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" class="dot k-{k}"><title>{e(tip)}</title></circle>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="12" class="hit" data-tip="{e(tip)}"/>'
    )


def off_scale(arms: list) -> tuple:
    """(on, off): a learned arm far below the field (beyond 1.5x the spread from the lower
    quartile to the top) is drawn at the axis's edge, past a break, so one outlier does not
    squash the other two dozen into a corner. Its tooltip still carries its score."""
    s = sorted(a["score"] for a in arms)
    floor_ = s[len(s) // 4] - 1.5 * (s[-1] - s[len(s) // 4])
    return [a for a in arms if a["score"] >= floor_], [a for a in arms if a["score"] < floor_]


def strip(exp: dict, width: int = 1000, height: int = 92, title: bool = True, compact: bool = False) -> str:
    """One experiment's field on one axis: every learned arm, the tie band, the dearest.
    compact: a phone-width layout, title above the axis instead of beside it."""
    arms = [a for a in exp["arms"] if a["kind"] != "baseline"]
    on, off = off_scale(arms)
    lo, hi = min(a["score"] for a in on), max(a["score"] for a in on)
    pad = (hi - lo) * 0.06 or 0.01
    lo, hi = lo - pad, hi + pad
    left, right, y = 190 if title else 20, width - 24, 50
    fs = 11
    if compact:
        width, fs = 400, 15
        left, right = 14, width - 14
        y = 74 if title else 48
        height = y + 50
    edge = left  # off-scale dots sit here, past a break in the axis
    if off:
        left += 34

    def x(v):
        return edge if v < lo else left + (v - lo) / (hi - lo) * (right - left)

    tied = [a for a in arms if a["arm"] in exp["tied"]] + [exp["leader_row"]]
    out = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{e(exp["bench"])}: every learned arm by {e(exp["metric_label"])}">'
    ]
    if title and compact:
        out.append(
            f'<text x="0" y="20" class="t-head" font-size="20">{e(exp["bench"])}</text>'
            f'<text x="{width}" y="20" text-anchor="end" class="t-muted" font-size="14">{e(exp["task"].lower())} · {e(exp["metric_label"])}</text>'
        )
    elif title:
        out.append(
            f'<text x="0" y="{y - 6}" class="t-head" font-size="17">{e(exp["bench"])}</text>'
            f'<text x="0" y="{y + 14}" class="t-muted" font-size="11">{e(exp["task"].lower())} · {e(exp["metric_label"])}</text>'
        )
    if len(tied) > 1:
        x0, x1 = x(min(a["score"] for a in tied)), x(max(a["score"] for a in tied))
        out.append(
            f'<rect x="{x0 - 8:.1f}" y="{y - 22}" width="{x1 - x0 + 16:.1f}" height="44" rx="10" class="band"/>'
        )
    out.append(f'<line x1="{left}" x2="{right}" y1="{y}" y2="{y}" class="axis"/>')
    if off:
        out.append(
            f'<line x1="{edge}" x2="{edge + 14}" y1="{y}" y2="{y}" class="axis"/>'
            f'<text x="{edge + 23}" y="{y + 5}" text-anchor="middle" class="t-muted" font-size="{fs + 2}">⫽</text>'
        )
    for a in sorted(arms, key=lambda a: a["arm"] == exp["dearest"]["arm"]):
        k = kind_of(a)
        tip = (
            f"{a['arm']} · {KIND_LABEL[k]}\n{exp['metric_label']} {a['score']:.4f} · rank {a['rank']}/{exp['n_arms']}"
            + (
                f"\nbilled {money(a['cost'])} for {exp['n_items']} items"
                if a["cost"] > 0
                else "\nfree: runs locally, nothing billed"
            )
            + ("\noff the scale: far below the field" if a in off else "")
        )
        r = 7 if a["arm"] in (exp["top"]["arm"], exp["dearest"]["arm"]) else 5.5
        out.append(dot(x(a["score"]), y, r, k, tip))
    d, t = exp["dearest"], exp["top"]
    half = 100 if compact else 70  # keep the centred label inside the frame
    dx = min(max(x(d["score"]), left + half), right - half)
    out.append(
        f'<circle cx="{x(d["score"]):.1f}" cy="{y}" r="11" class="ring"/>'
        f'<text x="{dx:.1f}" y="{y - 18}" text-anchor="middle" class="t-ink" font-size="{fs}">dearest · {ordinal(d["rank"])} · {d["score"]:.3f}</text>'
    )
    if t["arm"] != d["arm"]:
        out.append(
            f'<text x="{min(x(t["score"]), right - 4):.1f}" y="{y + 30}" text-anchor="end" class="t-ink" font-size="{fs}">{e(t["arm"])} · 1st · {t["score"]:.3f}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def forest(rows: list, width: int = 1000, compact: bool = False) -> str:
    """Calibration: our figure minus the published one, in points, with our 95% interval.
    compact: a phone-width layout, each row's label above its interval."""
    span = 4.0
    if compact:
        return _forest_compact(rows, span)
    row_h, top, left, right = 46, 30, 330, width - 150
    height = top + row_h * len(rows) + 30

    def x(v):
        return left + (v + span) / (2 * span) * (right - left)

    out = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Calibration: this repo against published values">'
    ]
    for t in (-4, -2, 0, 2, 4):
        cls = "axis" if t == 0 else "grid"
        out.append(
            f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top - 8}" y2="{height - 26}" class="{cls}"/>'
            f'<text x="{x(t):.1f}" y="{height - 8}" text-anchor="middle" class="t-muted" font-size="10">{t:+d}</text>'
        )
    out.append(
        f'<text x="{x(0):.1f}" y="{top - 16}" text-anchor="middle" class="t-muted" font-size="10">published value</text>'
    )
    for i, r in enumerate(rows):
        y = top + i * row_h + row_h / 2
        lo, hi = max(-span, r["delta"] - r["ci"]), min(span, r["delta"] + r["ci"])
        fmt = (lambda v: f"{v:.2f}") if r["scale"] == 1 else (lambda v: f"{v / 100:.4f}")
        tip = f"{r['bench']} · {r['what']}\nours {fmt(r['ours'])} ± {fmt(r['ci'])}\npublished {fmt(r['published'])}\nn = {r['n']}"
        out.append(
            f'<text x="0" y="{y - 3}" class="t-ink" font-size="13">{e(r["bench"])}</text>'
            f'<text x="0" y="{y + 13}" class="t-muted" font-size="11">{e(r["what"])}</text>'
            f'<line x1="{x(lo):.1f}" x2="{x(hi):.1f}" y1="{y}" y2="{y}" stroke="var(--ink-2)" stroke-width="2" stroke-linecap="round"/>'
            f'<circle cx="{x(r["delta"]):.1f}" cy="{y}" r="6.5" class="dot accent" data-tip="{e(tip)}"><title>{e(tip)}</title></circle>'
            f'<text x="{right + 18}" y="{y + 4}" class="t-ink" font-size="12">{fmt(r["ours"])}</text>'
            f'<text x="{right + 82}" y="{y + 4}" class="t-muted" font-size="12">{fmt(r["published"])}</text>'
        )
    out.append(
        f'<text x="{right + 18}" y="{top - 16}" class="t-muted" font-size="10">ours</text>'
        f'<text x="{right + 82}" y="{top - 16}" class="t-muted" font-size="10">published</text></svg>'
    )
    return "".join(out)


def _forest_compact(rows: list, span: float, width: int = 400) -> str:
    row_h, top, left, right = 84, 36, 14, width - 14
    height = top + row_h * len(rows) + 30

    def x(v):
        return left + (v + span) / (2 * span) * (right - left)

    out = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Calibration: this repo against published values">'
    ]
    for t in (-4, -2, 0, 2, 4):
        cls = "axis" if t == 0 else "grid"
        out.append(
            f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top - 6}" y2="{height - 26}" class="{cls}"/>'
            f'<text x="{x(t):.1f}" y="{height - 8}" text-anchor="middle" class="t-muted" font-size="14">{t:+d}</text>'
        )
    out.append(
        f'<text x="{x(0):.1f}" y="{top - 14}" text-anchor="middle" class="t-muted" font-size="14">published value</text>'
    )
    for i, r in enumerate(rows):
        y0 = top + i * row_h
        lo, hi = max(-span, r["delta"] - r["ci"]), min(span, r["delta"] + r["ci"])
        fmt = (lambda v: f"{v:.2f}") if r["scale"] == 1 else (lambda v: f"{v / 100:.4f}")
        tip = f"{r['bench']} · {r['what']}\nours {fmt(r['ours'])} ± {fmt(r['ci'])}\npublished {fmt(r['published'])}\nn = {r['n']}"
        yb = y0 + 38
        out.append(
            f'<text x="0" y="{y0 + 16}" class="t-ink" font-size="16">{e(r["bench"])} <tspan class="t-muted" font-size="14">{e(r["what"])}</tspan></text>'
            f'<text x="0" y="{y0 + 66}" class="t-muted" font-size="14">ours <tspan class="t-ink">{fmt(r["ours"])}</tspan> · published {fmt(r["published"])}</text>'
            f'<line x1="{x(lo):.1f}" x2="{x(hi):.1f}" y1="{yb}" y2="{yb}" stroke="var(--ink-2)" stroke-width="2" stroke-linecap="round"/>'
            f'<circle cx="{x(r["delta"]):.1f}" cy="{yb}" r="7" class="dot accent" data-tip="{e(tip)}"><title>{e(tip)}</title></circle>'
        )
    out.append("</svg>")
    return "".join(out)


def _spread(items: list, gap: float) -> dict:
    """Label y-positions with at least `gap` between neighbours: {key: y}."""
    out, last = {}, -1e9
    for k, yv in sorted(items, key=lambda t: t[1]):
        yv = max(yv, last + gap)
        out[k], last = yv, yv
    return out


def slope(rows: list, width: int = 640, height: int = 420, compact: bool = False) -> str:
    """The five local summarisation arms, CNN slice -> DailyMail slice."""
    top, bottom, x0, x1 = 44, height - 30, 120, width - 250
    if compact:
        width, height = 400, 380
        top, bottom, x0, x1 = 44, height - 24, 64, 196
    lo, hi = 0.12, 0.47
    fs = 16 if compact else 14

    def y(v):
        return bottom - (v - lo) / (hi - lo) * (bottom - top)

    out = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Local summarisers on CNN and on DailyMail">',
        f'<text x="{x0}" y="20" text-anchor="middle" class="t-muted" font-size="{fs}">CNN slice</text>',
        f'<text x="{x1}" y="20" text-anchor="middle" class="t-muted" font-size="{fs}">DailyMail slice</text>',
        f'<line x1="{x0}" x2="{x0}" y1="{top - 8}" y2="{bottom + 8}" class="axis"/>',
        f'<line x1="{x1}" x2="{x1}" y1="{top - 8}" y2="{bottom + 8}" class="axis"/>',
    ]
    # Ties share one label ("bart_l, bart_m"); then labels are spread so none overlap.
    groups: dict = {}
    for r in rows:
        groups.setdefault(round(r["dm"], 4), []).append(r["arm"])
    right = _spread([(v, y(v)) for v in groups], 20)
    left = _spread([(r["arm"], y(r["cnn"])) for r in rows], 18)
    for v, names in groups.items():
        out.append(
            f'<text x="{x1 + 16}" y="{right[v] + 5:.1f}" class="t-ink" font-size="{fs}">{e(", ".join(names))} {v:.3f}</text>'
        )
    for r in rows:
        out.append(
            f'<text x="{x0 - 16}" y="{left[r["arm"]] + 5:.1f}" text-anchor="end" class="t-muted" font-size="{fs - 1}">{r["cnn"]:.3f}</text>'
        )
    for r in rows:
        k = "baseline" if r["arm"] == "lead3" else "local"
        dash = ' stroke-dasharray="5 5"' if r["arm"] == "bart_l_xsum" else ""
        tip = f"{r['arm']}\ncoverage {r['cnn']:.4f} on CNN → {r['dm']:.4f} on DailyMail"
        out.append(
            f'<line x1="{x0}" y1="{y(r["cnn"]):.1f}" x2="{x1}" y2="{y(r["dm"]):.1f}" class="s-{k}" stroke-width="2"{dash}/>'
            f'<circle cx="{x0}" cy="{y(r["cnn"]):.1f}" r="5.5" class="dot k-{k}" data-tip="{e(tip)}"><title>{e(tip)}</title></circle>'
            f'<circle cx="{x1}" cy="{y(r["dm"]):.1f}" r="6" class="dot k-{k}" data-tip="{e(tip)}"><title>{e(tip)}</title></circle>'
        )
    out.append("</svg>")
    return "".join(out)


def scatter(exp: dict, width: int = 1000, height: int = 440, compact: bool = False) -> str:
    """Billed cost per 1,000 items (log) against quality. Free arms sit in their own lane."""
    arms = [a for a in exp["arms"] if a["kind"] != "baseline"]
    paid = [a for a in arms if a["cost"] > 0]
    free = [a for a in arms if a["cost"] <= 0]
    per_k = lambda a: a["cost"] / exp["n_items"] * 1000  # noqa: E731
    clo = math.floor(math.log10(min(per_k(a) for a in paid)))
    chi = math.ceil(math.log10(max(per_k(a) for a in paid)))
    on, off = off_scale(arms)
    lo = min(a["score"] for a in on)
    hi = max(a["score"] for a in on)
    pad = (hi - lo) * 0.08 or 0.01
    lo, hi = lo - pad, hi + pad
    left, right, top, bottom = 150, width - 30, 34, height - 50
    lane, fs, tick = 70, 11, 10
    if compact:
        width, height = 400, 430
        left, right, top, bottom = 140, width - 14, 36, height - 62
        lane, fs, tick = 92, 15, 14
    floor_y = bottom  # off-scale dots sit on this line, below a break in the y axis
    if off:
        bottom -= 30

    def x(c):
        return left + (math.log10(c) - clo) / (chi - clo) * (right - left)

    def y(v):
        return floor_y if v < lo else bottom - (v - lo) / (hi - lo) * (bottom - top)

    out = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{e(exp["bench"])}: cost against quality">'
    ]
    for p in range(clo, chi + 1):
        out.append(
            f'<line x1="{x(10**p):.1f}" x2="{x(10**p):.1f}" y1="{top}" y2="{bottom}" class="grid"/>'
            f'<text x="{x(10**p):.1f}" y="{floor_y + 22}" text-anchor="middle" class="t-muted" font-size="{tick}">${10**p:g}</text>'
        )
    for t in (lo + pad, (lo + hi) / 2, hi - pad):
        out.append(
            f'<line x1="{lane - 30}" x2="{right}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="grid"/>'
            f'<text x="{lane - 36}" y="{y(t) + 4:.1f}" text-anchor="end" class="t-muted" font-size="{tick}">{t:.3f}</text>'
        )
    out.append(
        f'<text x="{(left + right) / 2:.0f}" y="{height - 6}" text-anchor="middle" class="t-muted" font-size="{fs}">{"cost per 1,000 items (log)" if compact else "billed cost per 1,000 items (log scale)"}</text>'
        f'<text x="0" y="{top - 10}" class="t-muted" font-size="{fs}">↑ {e(exp["metric_label"])}</text>'
        f'<text x="{lane + 6}" y="{floor_y + 22}" text-anchor="middle" class="t-muted" font-size="{tick}">free</text>'
        f'<line x1="{left - 30}" x2="{left - 30}" y1="{top}" y2="{bottom}" class="axis"/>'
    )
    if off:
        out.append(
            f'<text x="{left - 30}" y="{(bottom + floor_y) / 2 + 5:.1f}" text-anchor="middle" class="t-muted" font-size="{fs + 2}">⫽</text>'
        )
    for a in free:
        k = kind_of(a)
        tip = f"{a['arm']} · {KIND_LABEL[k]}\n{exp['metric_label']} {a['score']:.4f} · $0" + (
            "\noff the scale: far below the field" if a in off else ""
        )
        out.append(dot(lane + 6, y(a["score"]), 6, k, tip))
    for a in paid:
        k = kind_of(a)
        tip = (
            f"{a['arm']} · {KIND_LABEL[k]}\n{exp['metric_label']} {a['score']:.4f}\n{money(per_k(a))} per 1,000 items"
            + ("\noff the scale: far below the field" if a in off else "")
        )
        out.append(dot(x(per_k(a)), y(a["score"]), 6, k, tip))
    # Both labels sit centred above their dots; if they would overlap, the dearest's drops
    # below its ring.
    d, t = exp["dearest"], exp["top"]
    dl, tl = f"{d['arm']} · dearest", f"{t['arm']} · 1st"
    w = lambda s: len(s) * fs * 0.62  # noqa: E731 -- monospace advance, roughly
    dx = min(max(x(per_k(d)), lane + w(dl) / 2), right - w(dl) / 2)
    tx = lane + 6 if t["cost"] <= 0 else x(per_k(t))
    tx = min(max(tx, w(tl) / 2), right - w(tl) / 2)
    dy, ty = y(d["score"]) - 18, y(t["score"]) - 14
    if t["arm"] != d["arm"] and abs(dy - ty) < fs + 4 and abs(dx - tx) < (w(dl) + w(tl)) / 2 + 8:
        dy = y(d["score"]) + 11 + fs + 4
    out.append(
        f'<circle cx="{x(per_k(d)):.1f}" cy="{y(d["score"]):.1f}" r="11" class="ring"/>'
        f'<text x="{dx:.1f}" y="{dy:.1f}" text-anchor="middle" class="t-ink" font-size="{fs}">{e(dl)}</text>'
    )
    if t["arm"] != d["arm"]:
        out.append(
            f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle" class="t-ink" font-size="{fs}">{e(tl)}</text>'
        )
    out.append("</svg>")
    return "".join(out)


# ── page chrome ─────────────────────────────────────────────────────────────
HEAD_JS = """<script>
(function(){var p=new URLSearchParams(location.search),t=p.get('theme');
try{t=t||localStorage.getItem('theme');}catch(e){}
if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;
if(!p.has('static'))document.documentElement.classList.add('js');})();
</script>"""

JS = """<script>
document.getElementById('theme').addEventListener('click',()=>{const r=document.documentElement;
const dark=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
r.dataset.theme=dark?'light':'dark';try{localStorage.setItem('theme',r.dataset.theme);}catch(e){}});
const tip=document.getElementById('tip');
function place(x,y){const w=tip.offsetWidth,h=tip.offsetHeight;tip.style.left=Math.max(8,Math.min(x+14,innerWidth-w-8))+'px';tip.style.top=(y+14+h>innerHeight?y-h-14:y+14)+'px';}
document.addEventListener('pointerover',ev=>{if(ev.pointerType==='touch')return;const t=ev.target.closest('[data-tip]');if(!t)return;tip.textContent=t.dataset.tip;tip.classList.add('on');place(ev.clientX,ev.clientY);});
document.addEventListener('pointermove',ev=>{if(ev.pointerType==='touch'||!tip.classList.contains('on'))return;place(ev.clientX,ev.clientY);});
document.addEventListener('pointerout',ev=>{if(ev.pointerType!=='touch'&&ev.target.closest('[data-tip]'))tip.classList.remove('on');});
// Touch: a tap shows the tip where the finger is; the next tap elsewhere, or a scroll, hides it.
document.addEventListener('pointerdown',ev=>{if(ev.pointerType!=='touch')return;const t=ev.target.closest('[data-tip]');if(!t){tip.classList.remove('on');return;}tip.textContent=t.dataset.tip;tip.classList.add('on');place(ev.clientX,ev.clientY);});
addEventListener('scroll',()=>tip.classList.remove('on'),{passive:true});
const io=new IntersectionObserver(es=>es.forEach(x=>{if(x.isIntersecting){x.target.classList.add('in');io.unobserve(x.target);}}),{rootMargin:'0px 0px -8% 0px'});
document.querySelectorAll('.reveal').forEach(el=>io.observe(el));
setTimeout(()=>document.querySelectorAll('.reveal').forEach(el=>el.classList.add('in')),2500);
</script>"""


def analytics_tag() -> str:
    """The Umami script tag from site/analytics.json, or nothing when it is not configured."""
    cfg = json.loads((HERE / "analytics.json").read_text())
    if not (cfg.get("umami_src") and cfg.get("website_id")):
        return ""
    domains = f' data-domains="{e(cfg["domains"])}"' if cfg.get("domains") else ""
    return f'<script defer src="{e(cfg["umami_src"])}" data-website-id="{e(cfg["website_id"])}"{domains}></script>'


# The author's own sites. Every link is tagged twice: UTM parameters, so humancopilot.eu's
# analytics can see visitors arriving from here, and an Umami event named by where on this
# site it was clicked, so this site's analytics can see which placement earns the click.
HUMAN = "https://www.humancopilot.eu/"
DWO = "https://www.devwhateverops.com/"

#: The family footer, shared with humancopilot.eu and devwhateverops.com: the operator's
#: other sites, then the places he can be found. Same links, order and analytics events as
#: the reference footer on humancopilot.eu; only the brand column is this site's own.
FAMILY = [
    ("https://www.orrerylearn.com/", "orrery", "Orrery", "A solar system explorer for the browser"),
    (HUMAN, "humancopilot", "Human Copilot", "Advisory for technology leaders"),
    (
        "https://www.devwhateverops.com/",
        "devwhateverops",
        "DevWhateverOps",
        "A manifesto for engineers who build end to end",
    ),
]
ELSEWHERE = [
    ("https://www.linkedin.com/in/markodragoljevic", "linkedin", "LinkedIn"),
    ("https://medium.com/@marko.dragoljevic", "medium", "Medium"),
    ("https://github.com/chipi", "github", "GitHub"),
    ("https://www.markodragoljevic.com/", "underwater-photography", "Underwater photography"),
]
UTM = "utm_source=eval-harness&utm_medium=referral&utm_content=footer"


def footer(up: str) -> str:
    projects = "".join(
        f'<a href="{e(url + "?" + UTM)}" data-umami-event="outbound" '
        f'data-umami-event-target="{tgt}" rel="noopener"><b>{e(name)}</b><span>{e(line)}</span></a>'
        for url, tgt, name, line in FAMILY
    )
    elsewhere = "".join(
        f'<a href="{e(url)}" data-umami-event="outbound" data-umami-event-target="{tgt}" '
        f'rel="noopener me">{e(label)}</a>'
        for url, tgt, label in ELSEWHERE
    )
    return f"""<footer><div class="wrap foot">
  <div class="foot-grid">
    <div class="foot-brand">
      <a class="brand" href="{up}index.html" aria-label="eval-harness home"><img class="mark" src="{up}assets/icon.svg" alt="" width="26" height="26"><span>eval-harness</span></a>
      <p>Is the ranking real, or a lucky sample?<br>Every number here is recomputed from the committed runs on each build.</p>
    </div>
    <nav class="foot-col" aria-label="Personal projects">
      <h2>Personal projects</h2>
      {projects}
    </nav>
    <nav class="foot-col" aria-label="Elsewhere">
      <h2>Elsewhere</h2>
      {elsewhere}
      <a href="mailto:marko@humancopilot.eu" data-umami-event="cta-email" data-umami-event-position="footer">Email</a>
    </nav>
  </div>
  <div class="foot-legal"><span>© Marko Dragoljevic · eval-harness <a href="{up}releases.html#v{VERSION}">v{VERSION}</a> · {BUILD_MARK} · <a href="{up}docs/DATA/">Data &amp; licences</a> · <a href="{up}releases.html">Release notes</a></span><span>Cookieless, self-hosted analytics (Umami). No cookies, no tracking across sites. <a href="{up}privacy.html">Privacy</a></span></div>
</div></footer>"""


def out(url: str, place: str, label: str, cls: str = "") -> str:
    """An outbound link to one of the author's sites, tagged for both analytics."""
    site = "humancopilot" if "humancopilot" in url else "devwhateverops"
    href = f"{url}?utm_source=eval-harness&utm_medium=site&utm_campaign=launch&utm_content={place}"
    c = f' class="{cls}"' if cls else ""
    return (
        f'<a href="{e(href)}"{c} data-umami-event="outbound-{site}" '
        f'data-umami-event-placement="{place}" rel="noopener">{label}</a>'
    )


def author(place: str) -> str:
    """Who built this, and where to find them: the closing section of the main pages."""
    return f"""
<section class="block author" id="author"><div class="wrap">
  <div class="eyebrow">Who built this</div>
  <h2>Built by Marko Dragoljevic.</h2>
  <p class="lede">I have led engineering teams for twenty years — at ServiceNow, EclecticIQ and Backbase — and through <b>Human Copilot</b> I now advise technology leaders. Which model, build or buy, own or rent: the questions this harness answers are the ones I help teams answer, on their own data.</p>
  <div class="btns">{out(HUMAN, f"author-{place}", "Work with Human Copilot →", "btn primary")}{out(DWO, f"author-{place}", "DevWhateverOps: principles for building end to end ↗", "btn")}</div>
</div></section>
"""


# The project mark (site/assets/icon.svg): an estimate with its interval, held in a harness.
# The same file in both themes -- lime tile, black marks -- exactly as designed.


def page(title: str, desc: str, body: str, depth: int = 0, here: str = "", card: str = "social.png") -> str:
    up = "../" * depth

    def nav(key: str, href: str, label: str, cls: str = "") -> str:
        cur = ' aria-current="page"' if key == here else ""
        c = f' class="{cls}"' if cls else ""
        return f'<a href="{href}"{c}{cur}>{label}</a>'

    # The site's own pages: the bar on wide screens, the ☰ menu on phones.
    links = (
        nav("harness", f"{up}index.html", "Overview")
        + nav("use", f"{up}use.html", "Use it")
        + nav("method", f"{up}method.html", "Method")
        + nav("experiments", f"{up}experiments.html", "Experiments")
        + nav("judging", f"{up}experiments/judging.html", "Re-measured")
    )
    # GitHub: a line in the phone menu, an icon button beside search and the theme on the bar.
    github_menu = f'<a href="{REPO}">GitHub ↗</a>'
    github_btn = f'<a class="hbtn" href="{REPO}" aria-label="eval-harness on GitHub" title="GitHub">{ICON["github"]}</a>'
    # Harness · Catalog · Docs, the same switcher in all three, this one marked.
    sections = (
        f'<a href="{up}index.html" aria-current="page">Harness</a>'
        f'<a href="{CATALOG}">Catalog</a><a href="{up}docs/">Docs</a>'
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="eval-harness">
<meta property="og:image" content="{SITE}/assets/{card}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="color-scheme" content="dark light">
{HEAD_JS}{analytics_tag()}
<link rel="stylesheet" href="{up}assets/style.css">
<link rel="icon" href="{up}assets/icon.svg" type="image/svg+xml">
<link rel="icon" href="{up}assets/icon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="{up}assets/apple-touch-icon.png">
</head>
<body>
<header class="bar"><div class="wrap">
  <a class="brand" href="{up}index.html" aria-label="eval-harness home"><img class="mark" src="{up}assets/icon.svg" alt="" width="28" height="28"><span>eval-harness</span></a>
  <nav class="sections" aria-label="Harness, catalog and docs">{sections}</nav>
  <details class="menu"><summary class="hbtn" aria-label="Menu">{ICON["menu"]}</summary><nav class="menu-links">{links}{github_menu}</nav></details>
  <nav class="nav">{links}{github_btn}<a class="hbtn search-btn" href="{up}docs/?q=" aria-label="Search the docs">{ICON["search"]}</a><button id="theme" class="theme hbtn" aria-label="Toggle light and dark">{ICON["theme"]}</button></nav>
</div></header>
<main>
{body}
</main>
{footer(up)}
<div id="tip" role="tooltip"></div>
{JS}
</body>
</html>
"""


#: The helpers method.py borrows, passed in rather than imported (no circular import).
H = types.SimpleNamespace(
    q=q,
    qv=qv,
    e=e,
    page=page,
    times=times,
    money=money,
    word=word,
    REPO=REPO,
    VERSION=VERSION,
    author=author,
    CATALOG=CATALOG,
)


# ── the landing page ────────────────────────────────────────────────────────
SYN = "research/REPORT_SYNTHESIS.md"
JUDGE = "research/REPORT_SUMMEVAL.md"


def marks(k: int, n: int) -> str:
    """k of n as n small marks, k filled: the count itself as data."""
    gap = 14
    dots = "".join(
        f'<circle cx="{6 + i * gap}" cy="6" r="4.5" class="{"on" if i < k else "off"}"/>' for i in range(n)
    )
    return (
        f'<svg class="marks" viewBox="0 0 {12 + (n - 1) * gap} 12" width="{12 + (n - 1) * gap}" '
        f'height="12" aria-hidden="true">{dots}</svg>'
    )


def sketch(exps: list, compact: bool = False) -> str:
    """Six benchmarks as one picture: each row on its own scale, from its weakest learned
    system to its best, so rows compare by shape, not score. Every other system is a faint
    tick; what carries the story is the shaded band (the systems the leader cannot be
    separated from), the leader, and the ringed most expensive model."""
    width = 400 if compact else 1000
    row = 50 if compact else 40
    top = 8
    height = top + row * len(exps) + 4
    if compact:
        left, right = 10, width - 10
    else:
        left, right = 170, width - 150
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-hidden="true" class="sketch">']
    for i, x in enumerate(exps):
        learned = [a for a in x["arms"] if a["kind"] != "baseline"]
        on, _off = off_scale(learned)
        lo, hi = min(a["score"] for a in on), max(a["score"] for a in on)
        y = top + row * i + (row - 14 if compact else row // 2)

        def px(v, lo=lo, hi=hi):
            return left if v <= lo else left + (v - lo) / (hi - lo) * (right - left)

        tied = [a for a in learned if a["arm"] in x["tied"]] + [x["leader_row"]]
        tag = f"leader + {x['n_tied']}" if x["n_tied"] else "clear winner"
        out.append(
            f'<a href="experiments/{x["slug"]}.html" class="sketch-row"><title>{e(x["bench"])}: '
            f'the experiment</title><rect x="0" y="{top + row * i}" width="{width}" height="{row}" class="hit-row"/>'
        )
        if compact:
            out.append(
                f'<text x="{left}" y="{y - 14}" class="t-head" font-size="15">{e(x["bench"])}</text>'
                f'<text x="{right}" y="{y - 14}" text-anchor="end" class="t-muted" font-size="13">{tag}</text>'
            )
        else:
            out.append(
                f'<text x="0" y="{y + 5}" class="t-head" font-size="16">{e(x["bench"])}</text>'
                f'<text x="{width}" y="{y + 5}" text-anchor="end" class="t-muted" font-size="13">{tag}</text>'
            )
        out.append(f'<line x1="{left}" x2="{right}" y1="{y}" y2="{y}" class="axis"/>')
        if len(tied) > 1:
            x0, x1 = px(min(a["score"] for a in tied)), px(max(a["score"] for a in tied))
            out.append(
                f'<rect x="{x0 - 6:.1f}" y="{y - 9}" width="{x1 - x0 + 12:.1f}" height="18" rx="9" class="band"/>'
            )
        for a in learned:
            if a["arm"] not in (x["top"]["arm"], x["dearest"]["arm"]):
                out.append(
                    f'<line x1="{px(a["score"]):.1f}" x2="{px(a["score"]):.1f}" y1="{y - 4}" y2="{y + 4}" class="tick"/>'
                )
        out.append(f'<circle cx="{px(x["dearest"]["score"]):.1f}" cy="{y}" r="7" class="ring"/>')
        out.append(f'<circle cx="{px(x["top"]["score"]):.1f}" cy="{y}" r="5" class="lead"/></a>')
    out.append("</svg>")
    return "".join(out)


def hero_sketch(exps: list) -> str:
    ties = sum(x["n_tied"] > 0 for x in exps)
    dear_first = sum(x["dearest"]["arm"] == x["top"]["arm"] for x in exps)
    finding = (
        f"In {ties} of {len(exps)} benchmarks the leader cannot be separated from a "
        f"group of others; the most expensive model came first in "
        f"{word(dear_first) if dear_first else 'none'}."
    )
    key = (
        '<div class="legend sketch-key"><span><i class="lead-i"></i>the leader</span>'
        '<span><i class="sw-band"></i>not separated from it</span>'
        '<span><i class="ring-i"></i>the most expensive model</span>'
        '<span class="read">each row: worst to best, on its own scale →</span></div>'
    )
    return (
        f'<figure class="chart hero-chart hero-sketch reveal" aria-label="{e(finding)}">'
        f"{key}{both(sketch(exps), sketch(exps, compact=True))}"
        f'<figcaption>{e(finding)} <a href="experiments.html#findings">See each one →</a>'
        f"</figcaption></figure>"
    )


def dearest_note(f: dict, up: str = "") -> str:
    """The qualifier the 'never won' headline needs: on the re-measured scores the dearest
    model leads in these experiments. Computed, so it cannot outlive the data."""
    r = f["remeasure"]
    by = {x["slug"]: x for x in f["experiments"]}
    pairs = (("ag-news", r["ag"]["arms"]), ("summarization", r["summ"]["arms"]))
    leads = [
        by[s]["bench"]
        for s, rows in pairs
        if by[s]["dearest"]["arm"] == max(rows, key=lambda a: a["v2"])["arm"]
    ]
    if not leads:
        return ""
    names = sorted({by[s]["dearest"]["arm"] for s, _ in pairs})
    return (
        f' The headline is on each experiment\'s primary metric. <a href="{up}experiments/judging.html">Re-measured</a>, '
        f"against labels a person corrected and by LLM judges, the dearest model, {' / '.join(names)}, is first "
        f"on the point estimate in {word(len(leads))}: {' and '.join(leads)}; neither re-measurement is confirmed."
    )


def remeasured_counts(f: dict) -> dict:
    """What the re-measured scores would do to the two headlines, taken at face value: how many
    experiments the dearest model would be first in, and how many a free model would lose
    (a local arm first on the primary, a hosted one first re-measured)."""
    r = f["remeasure"]
    by = {x["slug"]: x for x in f["experiments"]}
    pairs = (("ag-news", r["ag"]["arms"]), ("summarization", r["summ"]["arms"]))
    top = {s: max(rows, key=lambda a: a["v2"]) for s, rows in pairs}
    return {
        "dearest_first": sum(by[s]["dearest"]["arm"] == top[s]["arm"] for s, _ in pairs),
        "local_lost": sum(by[s]["top"]["kind"] == "local" and top[s]["kind"] == "hosted" for s, _ in pairs),
    }


def home(f: dict) -> str:
    """The front door: the harness -- what it is, what it asks, how to start -- and then
    what it found when pointed at 24 LLMs, which is the reason to believe it."""
    exps = f["experiments"]
    ties = sum(x["n_tied"] > 0 for x in exps)
    cal_n, cal_ok = len(f["calibration"]), f["calibration_consistent"]
    cal_in = f["calibration_inside"]
    hosted_n = max(x["n_hosted"] for x in exps)
    ideas = [
        (
            "01",
            "A frozen dataset",
            (
                "Items are hashed and every run records the hash. Change the data and you get a "
                "different id — not a silently different number."
            ),
        ),
        (
            "02",
            "A fingerprint per run",
            (
                "The model behind the alias, the prompt, the scoring code, library versions, the "
                "commit. So \u201cwe changed one thing\u201d is checkable, not asserted."
            ),
        ),
        (
            "03",
            "A leaderboard that argues with itself",
            (
                "Before it prints an order it tests every pair at once — a Friedman permutation test "
                "and a Nemenyi critical difference — and says plainly when nothing is distinguishable."
            ),
        ),
        (
            "04",
            "Re-scoring for $0",
            (
                "Scores are recomputed from stored outputs. Checking a metric should never cost "
                "another sweep of paid calls."
            ),
        ),
        (
            "05",
            "A goal that recommends",
            (
                "A goal says what the evaluation is for: the measure that decides, limits on cost and "
                "speed, how a tie is broken. Its rule recommends an arm and says why; a person promotes "
                "the baseline, the run later changes are measured against."
            ),
        ),
        (
            "06",
            "A catalog to look around in",
            (
                "The harness builds pages over your committed runs: every goal with what it recommends, "
                "every dataset, arm, reference and metric, and an inspector that compares any arms item "
                "by item. Every view is also an evh command."
            ),
            (CATALOG, "Ours, on the six worked examples"),
        ),
    ]
    idea_html = "".join(
        f'<div class="habit-card"><span class="n">{n}</span><b>{e(t)}</b><span>{e(d)}'
        + (f' <a href="{rest[0][0]}">{e(rest[0][1])} →</a>' if rest else "")
        + "</span></div>"
        for n, t, d, *rest in ideas
    )
    # Why it exists: the questions it was built to answer, each with what the experiments
    # found -- numbers computed, quoted prose checked by q(). How the harness answers them
    # is the method page's job.
    rc = remeasured_counts(f)
    why = [
        (
            "Agentic AI can do months of work in days. How do I trust what it builds?",
            (
                f"This project was built that way, with AI agents. A checker re-verifies "
                f"{f['claims_checked']} claims against the runs on every commit, the lab notebook "
                "records the findings that had to be retracted along the way, and git keeps every "
                "earlier version of the reports."
            ),
            f"{REPO}/tree/main/research/internal",
            "The lab notebook",
        ),
        (
            "Which model is best for what I need — not for someone else's benchmark?",
            (
                f"On each experiment's primary metric the most expensive model was not the best in any of "
                f"the {f['frontier_exps']} experiments where frontier models ran (the same model each time; "
                f"SciFact ran only the twelve cheapest hosted models); re-measured, against corrected labels "
                f"and by LLM judges, it is first on the point estimate in {word(rc['dearest_first'])}, "
                f"neither re-measurement confirmed. In {ties} of {len(exps)} "
                "the leader could not be separated from other arms (an arm is one system under test: "
                "a model with its prompt and settings) — at 100–280 items, which is not the same as equal."
            ),
            "experiments.html",
            "The experiments",
        ),
        (
            "Do I need an LLM — or a GPU — at all?",
            f"A free model that needs no GPU was first, or not separable from first, in "
            f"{f['local_first_or_tied']} of {len(exps)} on the primary metrics "
            f"({f['local_first_or_tied'] - rc['local_lost']} of {len(exps)} on the re-measured scores, "
            "unconfirmed), against LLMs run with one prompt and no "
            "examples; the clearest wins were on text like the text it was trained on. On judging "
            "summaries even a free model trained for the task lost, and an LLM judge scored above every "
            "free scorer measured: "
            + q(
                "judging summaries, the best LLM judges reach 93% of a human expert's agreement "
                "(the best of 24, chosen on the same articles; 92% held out), and UniEval, the best "
                "free scorer, 64%.",
                JUDGE,
            )
            + " "
            + q(
                "A no-model lookup of which system wrote each summary reaches 63%; the "
                "summaries are 2019-era and the judges ran with reasoning off.",
                JUDGE,
            )
            + " One task, so the direction, not the size.",
            "experiments.html#experiments",
            "Per experiment",
        ),
        (
            "Own it or rent it?",
            q(
                "The best proprietary arm never separated from the best open-weight arm in any of the "
                "six experiments",
                SYN,
            )
            + ". At native precision the best model that fits a 64 GB machine matched the "
            "unlimited-hardware answer on two of the six tasks, was not separated from it on two "
            "more, and was separated below it on summarisation and SummEval — as the providers "
            "served them: nothing was run on a 64 GB machine.",
            f"{BLOB}/research/REPORT_SYNTHESIS.md",
            "The synthesis",
        ),
    ]
    why_html = "".join(
        f'<div class="why-q reveal"><span class="n">{i:02d}</span><h3>{e(qn)}</h3>'
        f"<p><b>What it found</b>{found}</p>"
        f'<a href="{href}">{e(label)} →</a></div>'
        for i, (qn, found, href, label) in enumerate(why, 1)
    )
    goal_links = " · ".join(f'<a href="{CATALOG}{x["goal"]["goal_page"]}">{e(x["bench"])}</a>' for x in exps)
    # Step 2: each benchmark as its own field, the same strips as the experiments page.
    benches = "".join(
        f'<a class="bench-row reveal" href="experiments/{x["slug"]}.html" aria-label="{e(x["bench"])}: '
        f'{e(CARD[x["slug"]])}">{both(strip(x), strip(x, compact=True))}</a>'
        for x in exps
    )
    body = f"""
<section class="hero hero-grid"><div class="wrap">
  <div class="kicker"><b>eval-harness</b> · open source · MIT · by {out(HUMAN, "hero", "Marko Dragoljevic", "byline")}</div>
  <h1>Is the ranking real, or <em>a lucky sample?</em></h1>
  <p class="dek">A small, drop-in harness for evaluating AI systems on your own data. Freeze a dataset, run your system against it, and get the answer most leaderboards skip: whether one system is actually better than another, or only ahead on this sample.</p>
  <p class="dek-note">This is ongoing work: the harness and its method are the point, and the six experiments are worked examples of them, not a benchmark.</p>
  <p class="dek-note">Three parts: this site, why the harness exists and what it found; <a href="{CATALOG}">the catalog</a>, the harness's own pages over every run behind it, with an inspector that re-tests any comparison; and <a href="docs/">the docs</a>, how to do the same on your own system.</p>
  <div class="btns"><a class="btn primary" href="use.html">Use it on your problem</a><a class="btn" href="experiments.html">See it on {hosted_n} LLMs</a><a class="btn" href="{CATALOG}">Browse every run</a><a class="btn" href="{REPO}">GitHub ↗</a></div>
  {hero_sketch(exps)}
</div></section>

<section class="block" id="why"><div class="wrap">
  <div class="eyebrow"><span class="num">01</span>Why the harness exists</div>
  <h2>Four questions anyone building with AI ends up asking.</h2>
  <p class="lede">There are dozens of models, a leaderboard for each, and none of them measured on your problem. <a href="docs/GUIDE/">The harness</a> exists to answer these on your own data; below, what it answered when pointed at 24 LLMs. How it does that is in <a href="method.html">the method</a>.</p>
  <div class="why">{why_html}</div>
</div></section>

<section class="block" id="what"><div class="wrap">
  <div class="eyebrow"><span class="num">02</span>What the harness does</div>
  <h2>Six ideas, one adapter file.</h2>
  <p class="lede">Most eval code answers \u201cwhich scored highest\u201d. That is the easy half; the hard half is whether the answer survives being asked again. <a href="docs/GUIDE/">The harness</a> imports nothing domain-specific — everything about your system lives in one file, <code>adapter.py</code>, with two functions you write: <code>call_system()</code> and <code>score()</code>.</p>
  <div class="habits">{idea_html}</div>
  <div class="cols" style="margin-top:48px">
    <div class="prose"><h3 style="font-size:28px;line-height:1.15;margin-bottom:16px">Try the whole loop.</h3><p>Install the pinned release in a new folder; <code>evh init --tutorial</code> writes the project's folders and a six-ticket tutorial kit, and getting started takes it through the loop in about fifteen minutes — a dataset, arms, a reference from the best arm's run, a comparison, a choice — offline, no API key. Tutorials then add a local model, a hosted LLM with your own key, a frontier reference and judges, and rounds. Last, look at it all: <code>evh catalog</code> builds the catalog of your own runs and <code>evh catalog-serve</code> opens it with the inspector (<a href="docs/tutorials/5-catalog-and-inspector/">tutorial 5</a>); <a href="{CATALOG}">ours</a> shows the six worked examples. From a checkout of this repository, <code>make demo</code> runs the loop on bundled synthetic data in a minute.</p>
      <div class="btns"><a class="btn primary" href="docs/GUIDE/">Getting started</a><a class="btn" href="docs/GUIDE/#where-to-go-next">The tutorials</a><a class="btn" href="{CATALOG}">The catalog</a></div></div>
<pre class="term"><span class="p">$ </span>pip install "evaluation-harness @ git+{REPO}@v{VERSION}#subdirectory=harness"
<span class="p">$ </span>evh init --tutorial
<span class="c"># the guide walks the tutorial from here; then, on your own system</span>
<span class="p">$ </span>evh dataset-create --dataset-id my_v1 --source-dir data/sources
<span class="p">$ </span>evh experiment-run --config data/configs/arm_a.yaml --repeat 3
<span class="p">$ </span>evh leaderboard --dataset-id my_v1
<span class="p">$ </span>evh catalog && evh catalog-serve
<span class="c"># or, from a checkout: the bundled demo</span>
<span class="p">$ </span>git clone {REPO}
<span class="p">$ </span>cd eval-harness/harness
<span class="p">$ </span>make install
<span class="p">$ </span>make demo
<span class="p">$ </span>make leaderboard</pre>
  </div>
</div></section>

<section class="block" id="proof"><div class="wrap">
  <div class="eyebrow"><span class="num">03</span>Worked examples · {hosted_n} LLMs</div>
  <h2>The most expensive model <em style="font-style:normal;color:var(--accent)">never won.</em></h2>
  <p class="lede">These are examples of the harness and its method at work, not a leaderboard, and they are still being extended. To show the harness doing something real, it measured {hosted_n} hosted LLMs, proprietary and open-weight from small to frontier tiers, small fine-tuned models and baselines on {word(len(exps))} public benchmarks — {f["total_arms"]} runs, {money(f["total_billed"])} billed, every cost read off the provider's bill.{dearest_note(f)} Each is also a goal in <a href="{CATALOG}">the catalog</a>, with every run, dataset and reference behind it.</p>
  <div class="stats">
    <div class="stat"><div class="n">{f["dearest_not_best_frontier"]}<small>/{f["frontier_exps"]}</small></div>{marks(f["dearest_not_best_frontier"], f["frontier_exps"])}<div class="l">experiments with frontier models where the dearest model was not the best (the same model each time; SciFact ran only the twelve cheapest hosted models)</div></div>
    <div class="stat"><div class="n">{ties}<small>/{len(exps)}</small></div>{marks(ties, len(exps))}<div class="l">leaderboards where the leader cannot be separated from others (at 100–280 items)</div></div>
    <div class="stat"><div class="n">$0</div>{marks(f["local_first_or_tied"], len(exps))}<div class="l">for a model that is first, or not separable from first, in {f["local_first_or_tied"]} of the {len(exps)}; {f["local_first_or_tied"] - remeasured_counts(f)["local_lost"]} of {len(exps)} if the <a href="experiments/judging.html">re-measured scores</a> are taken at face value</div></div>
    <div class="stat"><div class="n">{cal_ok}<small>/{cal_n}</small></div>{marks(cal_in, cal_n)}<div class="l">calibration checks that agree with the published numbers, {cal_in} inside their own interval</div></div>
  </div>
  <div class="chart benches" style="margin-top:48px">{legend(reading="higher score: further right →", baseline=False)}{benches}</div>
  <p class="dek-note">In the catalog: {goal_links}.</p>
  <div class="btns"><a class="btn primary" href="experiments.html">All the findings</a><a class="btn" href="{CATALOG}">Browse them in the catalog</a><a class="btn" href="experiments.html#reproduce">Reproduce them</a></div>
</div></section>

{method.landing_teaser(H, f, "04")}
<section class="block"><div class="wrap">
  <p class="note"><b>No figure on this site is typed in by hand.</b> Every figure is recomputed from the committed runs each time the site is built, and every number the prose quotes must appear in the report it comes from, or the build fails. Behind the reports, a checker verifies {f["claims_checked"]} claims against the runs on every commit.</p>
</div></section>
{author("home")}"""
    return page(
        "eval-harness — is the ranking real, or a lucky sample?",
        "A drop-in harness for evaluating AI systems on your own data: frozen datasets, "
        "fingerprinted runs, and significance tests before any leaderboard is printed — "
        f"shown on 24 LLMs across {word(len(exps))} benchmarks.",
        body,
        here="harness",
        card="social-home.png",
    )


def landing(f: dict) -> str:
    exps = f["experiments"]
    by = {x["slug"]: x for x in exps}
    ties = sum(x["n_tied"] > 0 for x in exps)
    cal_n, cal_ok = len(f["calibration"]), f["calibration_consistent"]
    cal_in = f["calibration_inside"]
    hosted_n = max(x["n_hosted"] for x in exps)
    local_n = sum(x["n_arms"] - x["n_hosted"] for x in exps)
    billed_all = f"{f['total_billed']:.2f}"

    strips = "".join(
        f'<figure class="reveal" style="margin-bottom:10px">{both(strip(x), strip(x, compact=True))}</figure>'
        for x in exps
    )
    goal_links = " · ".join(f'<a href="{CATALOG}{x["goal"]["goal_page"]}">{e(x["bench"])}</a>' for x in exps)
    tie_rows = "".join(
        f'<tr><td class="exp"><a href="experiments/{x["slug"]}.html">{e(x["task"])} · {e(x["bench"])}</a></td>'
        f'<td class="num" data-label="first place">{e(x["top"]["arm"])}</td>'
        f'<td class="num big" data-label="tied with 1st">{x["n_tied"]}</td>'
        f'<td class="num" data-label="…of which paid">{x["n_tied_paid"]}</td>'
        f'<td class="num" data-label="cheapest paid tie">{e(x["cheapest_tied"]["arm"]) if x["cheapest_tied"] else "—"}</td>'
        f'<td class="num" data-label="cheaper than dearest">{times(x["tied_ratio"]) if x["tied_ratio"] else "no paid model ties"}</td>'
        f'<td class="num" data-label="dearest model">{e(x["dearest"]["arm"])} · {ordinal(x["dearest"]["rank"])} of {x["n_arms"]}</td></tr>'
        for x in exps
    )
    cards = "".join(
        f'<a class="card reveal" href="experiments/{x["slug"]}.html"><div class="task">{e(x["task"])}</div>'
        f"<h3>{e(x['bench'])}</h3><p>{e(CARD[x['slug']])}</p>"
        f'<div class="meta"><span>{x["n_items"]} items · {x["n_arms"]} arms</span><span>1st <b>{e(x["top"]["arm"])}</b></span></div></a>'
        for x in exps
    ) + (
        '<a class="card reveal" style="grid-column:1/-1" href="experiments/judging.html"><div class="task">Re-measured, not re-run · across experiments</div>'
        "<h3>Re-measured</h3><p>Three experiments scored again without re-running a model: validated LLM "
        "judges re-ranked summarisation, a person corrected AG News and DBpedia labels. Why a judge "
        "beat the metric on SummEval, and why one reader's check kept coverage primary.</p>"
        f'<div class="meta"><span>3 experiments · {money(f["remeasure"]["summ"]["billed_usd"] + f["remeasure"]["summ_v2"]["billed_usd"])} of judging, '
        f"{money(f['remeasure']['validation_usd'])} checking the judges</span>"
        "<span>primaries <b>unchanged</b></span></div></a>"
    )
    s = by["summarization"]
    hw_rows = "".join(
        f'<tr><td class="exp">{e(m["name"])}</td><td class="prose" data-label="what it is">{e(m["summary"])}</td>'
        f'<td class="num" data-label="committed runs">'
        + (
            f"{m['local'] + m['hosted']}<br><small>{m['local']} local, {m['hosted']} hosted</small>"
            if m["local"] + m["hosted"]
            else "none"
        )
        + f'</td><td class="prose" data-label="role">{e(m["role"])}</td></tr>'
        for m in f["hardware"]
    )
    hw_date = json.loads((ROOT / "docs" / "evidence" / "hardware.json").read_text())["captured"]
    require(
        sum(m["local"] + m["hosted"] for m in f["hardware"]) == f["total_arms"],
        "every measured run is attributed to a documented machine",
    )
    dear_x = max(exps, key=lambda x: x["dearest"]["cost"])
    dear = dear_x["dearest"]
    n_exp = word(len(exps))
    behind_cheaper = sum(
        any(a["cost"] < x["dearest"]["cost"] and a["rank"] < x["dearest"]["rank"] for a in x["arms"])
        for x in exps
    )
    behind_free = sum(
        any(a["kind"] != "hosted" and a["rank"] < x["dearest"]["rank"] for a in x["arms"]) for x in exps
    )
    in_all = "all " + n_exp if behind_cheaper == len(exps) else f"{word(behind_cheaper)} of {n_exp}"

    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>The experiments</b> · worked examples, ongoing · {len(exps)} tasks · {f["total_arms"]} measured runs · {money(f["total_billed"])} billed</div>
  <h1>The most expensive model <em>never won.</em></h1>
  <p class="dek">{hosted_n} hosted LLMs, proprietary and open-weight from small to frontier tiers, small fine-tuned models and the baselines they have to beat, run through {n_exp} public benchmarks as worked examples of the harness and its method. Every comparison is tested for significance, every cost is read off the provider's bill, and the instrument itself is checked against the published literature.{dearest_note(f)}</p>
  <div class="stats">
    <div class="stat"><div class="n">{f["dearest_not_best_frontier"]}<small>/{f["frontier_exps"]}</small></div><div class="l">experiments with frontier models where the dearest model was not the best (the same model each time; SciFact ran only the twelve cheapest hosted models)</div></div>
    <div class="stat"><div class="n">{ties}<small>/{len(exps)}</small></div><div class="l">leaderboards where the leader cannot be separated from others (at 100–280 items)</div></div>
    <div class="stat"><div class="n">$0</div><div class="l">for a model that is first, or not separable from first, in {f["local_first_or_tied"]} of the {len(exps)}; {f["local_first_or_tied"] - remeasured_counts(f)["local_lost"]} of {len(exps)} if the <a href="experiments/judging.html">re-measured scores</a> are taken at face value</div></div>
    <div class="stat"><div class="n">{cal_ok}<small>/{cal_n}</small></div><div class="l">calibration checks that agree with the published numbers, {cal_in} inside their own interval</div></div>
  </div>
</div></section>

<section class="block" id="findings"><div class="wrap">
  <div class="eyebrow"><span class="num">01</span>Price</div>
  <h2>The dearest model was never the best.</h2>
  <p class="lede">Each row is one benchmark; each dot is one system, placed by its score. The ringed dot is the most expensive hosted model. <strong>In {in_all} it finished behind something cheaper</strong> — and in {word(behind_free)}, behind something free. On SciFact only the twelve cheapest hosted models ran, so there it is the dearest of those; no Anthropic or OpenAI arm was run.</p>
  <div class="chart reveal">{legend(reading="higher score: further right →", baseline=False)}{strips}
  <figcaption>Baselines (lead-3, keyword rules, empty output) are left off the axis to keep the field readable; they are in each experiment's page. A dot left of the ⫽ break sits far below the rest, off the scale. Hover or tap any dot for its score, rank and bill.</figcaption></div>
</div></section>

<section class="block" id="ties"><div class="wrap">
  <div class="eyebrow"><span class="num">02</span>Ties</div>
  <h2>The top is a crowd, not a podium.</h2>
  <div>
    <div class="prose" style="margin-bottom:40px">
      <p>A leaderboard sorts, so something is always first. The question is whether first is <strong>distinguishable</strong> from second. Here every leader was tested against every other arm on the same items, with a paired permutation test and a correction for running many comparisons at once.</p>
      <p>In {ties} of {len(exps)} experiments the leader <strong>cannot be told apart</strong> from a group of others — on summarisation, from {s["n_tied"]} of them. The cheapest paid model inside that group cost a fraction of the dearest: {times(s["tied_ratio"])} less on summarisation.</p>
      <p>The one clean winner is a 499 MB tagger fine-tuned on Few-NERD's own training data, separated from all {by["few-nerd"]["n_arms"] - 1} rivals.</p>
    </div>
    <div class="chart scroll-x reveal"><table class="data ties cards">
      <thead><tr><th>experiment</th><th>first place</th><th>tied with 1st</th><th>…of which paid</th><th>cheapest paid tie</th><th>cheaper than dearest</th><th>dearest model</th></tr></thead>
      <tbody>{tie_rows}</tbody></table>
      <figcaption><b>Tied with 1st</b>: other systems the leader cannot be statistically separated from (paired permutation test, Holm-corrected). <b>…of which paid</b>: how many of those are hosted models that bill per call; the rest are free. <b>Cheapest paid tie</b>: the cheapest of them, and how many times less it cost than the most expensive model in the field. <b>0 tied</b> means a clean winner: separated from every rival.</figcaption></div>
  </div>
</div></section>

<section class="block" id="fine-tuning"><div class="wrap">
  <div class="eyebrow"><span class="num">03</span>Fine-tuning</div>
  <h2>Train a small model on your data. <em style="font-style:normal;color:var(--accent)">Yours.</em></h2>
  <ol class="findings reveal">
    <li><div><h3>A free local model was first, or not separable from first, in {f["local_first_or_tied"]} of {len(exps)}.</h3><p>Against hosted LLMs run with one prompt, no examples and no reasoning. {q("Every one is under 2 GB and needs no GPU", SYN)} — $0 per item — against hosted models billing up to {money(dear["cost"])} for {dear_x["n_items"]} items ({e(dear["arm"])}, {e(dear_x["bench"])}).</p></div></li>
    <li><div><h3>The clearest wins were on text like the text it was trained on.</h3><p>{q("The same BART architecture, fine-tuned on XSum's one-sentence BBC summaries instead of CNN/DailyMail's, finishes last of 29 — below copying the first three sentences.", "research/REPORT_SUMMARIZATION.md")}</p></div></li>
    <li><div><h3>On one task, even a free model trained for it lost to LLM judges — and the dearest judge was not needed.</h3><p>{q("Judging summaries, scored against the mean of two experts as one expert is against the other two, the best judges reach 93% of a human's agreement (the best of 24, chosen on the same articles; 92% held out); UniEval, the best free scorer and an evaluator trained for the task, reaches 64%.", JUDGE)} {q("The judges rank all 16 summaries in one call while UniEval scores one at a time, and a pointwise LLM judge was not run; a no-model lookup of which system wrote each summary reaches 63%.", JUDGE)} {q("The cheapest judge the leader cannot be separated from, gemma_l, has open weights and bills $278 per million articles — 1/23 of the leader.", JUDGE)} One task and one trained evaluator, and why it lost is not tested: the direction, not the size.</p></div></li>
    <li><div><h3>And part of a fine-tune's lead is learning the dataset's own conventions.</h3><p>{q("On AG News, the lead of the three fine-tunes is concentrated in 17 items the hosted field mostly gets wrong.", "research/REPORT_CLASSIFICATION.md")} Adjudicated by topic by one reader shown the hosted answer, the gold was wrong on all 17, and on that gold every hosted LLM scores above every fine-tune. {q("On Few-NERD, 57% of the winner's margin over openai_m is one entity type the prompt never defined (30–57% across the hosted arms).", "research/REPORT_NER.md")} The leaders are better at the benchmark; how much of that is better at the task is a separate question, measured in each report.</p></div></li>
  </ol>
</div></section>

<section class="block" id="trust"><div class="wrap">
  <div class="eyebrow"><span class="num">04</span>Trust</div>
  <h2>Can you trust any of this?</h2>
  <p class="lede">Five experiments score a sample of 200–280 items, not a full test set, and SummEval scores the whole of its 100. So each one also runs a <strong>calibration</strong>: one well-known model or metric, through this repo's own code, on the benchmark's full test set (or a large seeded sample), compared with the number its authors published.</p>
  <div class="chart reveal">{both(forest(f["calibration"]), forest(f["calibration"], compact=True))}
    <figcaption>Our figure minus the published one, in points of the metric (ROUGE-1 F1 for summarisation; accuracy, micro-F1, nDCG@10 or Kendall τ ×100 elsewhere). Bars are our 95% interval. {cal_ok} of {cal_n} agree with the published value within that interval plus a 2-point allowance for protocol differences; {cal_in} are inside the interval itself.</figcaption></div>
  <div class="cols" style="margin-top:64px">
    <div class="prose">
      <h3 style="font-size:28px;line-height:1.15;margin-bottom:16px">Calibration found one real error — in our sample, not our scorer.</h3>
      <p>The summarisation experiment took the first 200 articles of the CNN/DailyMail test set. The test set lists CNN's articles first, so <strong>all 200 were CNN's</strong>, while the benchmark is 91% DailyMail. Lead-3 scored ROUGE-1 30.20 on that slice against 39.94 on the full test set; CNN articles are simply harder to summarise from their lead.</p>
      <p>Re-run on 200 DailyMail articles drawn at random, the five local summarisers <strong>kept every verdict</strong> they had on CNN: the fine-tune still beats lead-3 by the same margin, and the XSum model is still last. The hosted models were not re-run, so the summarisation price findings are scoped to CNN's articles — and say so.</p>
    </div>
    <figure class="chart reveal">{both(slope(f["dailymail"]), slope(f["dailymail"], compact=True))}<figcaption>coverage of the five local summarisers on each slice. Dashed: BART trained on XSum.</figcaption></figure>
  </div>
  <p class="note" style="margin-top:48px"><b>No figure on this site is typed in by hand.</b> Every figure is recomputed from the committed runs each time the site is built, and every number the prose quotes must appear in the report it comes from, or the build fails. Behind the reports, a checker verifies {f["claims_checked"]} claims against the runs on every commit.</p>
  <p class="note"><b>Or test it yourself, in your browser.</b> Every run behind these charts is in <a href="{CATALOG}">the catalog</a>, and its inspector re-runs any comparison on this site, item by item, with the same paired test. Each experiment's page opens it on every arm against its leader.</p>
</div></section>

<section class="block" id="experiments"><div class="wrap">
  <div class="eyebrow"><span class="num">05</span>The experiments</div>
  <h2>{n_exp.capitalize()} benchmarks, one harness.</h2>
  <p class="lede">The same {hosted_n} hosted models — eight vendors, three price tiers each — on every task (the cheapest twelve on SciFact), beside the strongest free models each task allows.</p>
  <div class="cards">{cards}</div>
  <p class="dek-note">Each is a goal in the catalog, with every run behind it: {goal_links}.</p>
</div></section>

<section class="block" id="reproduce"><div class="wrap">
  <div class="eyebrow"><span class="num">06</span>Reproduce it</div>
  <h2>Built to be checked — by you.</h2>
  <p class="lede">The harness, every run, every model output and every analysis script are in the repository. Before any of it, <a href="{CATALOG}">the catalog</a> shows every run and its inspector re-tests any comparison, with nothing installed. Then five levels of checking, each optional, each a few commands.</p>
  <div class="cols">
    <ol class="ladder">
      <li><span class="lvl">00</span><div><h3>Verify</h3><p>Every number in every report, recomputed from the committed predictions.</p></div><span class="cost">$0 · one command</span></li>
      <li><span class="lvl">01</span><div><h3>Data</h3><p>Fetch the public benchmarks and hash-check every item against what was measured.</p></div><span class="cost">$0</span></li>
      <li><span class="lvl">02</span><div><h3>Local</h3><p>Rerun the {local_n} free arms — local models and baselines — on your CPU, pinned to the same weights.</p></div><span class="cost">$0 · CPU hours</span></li>
      <li><span class="lvl">03</span><div><h3>Hosted</h3><p>Rerun the {hosted_n} LLMs with one OpenRouter key. The test: does every separation still hold?</p></div><span class="cost">${billed_all} billed, all {n_exp}</span></li>
      <li><span class="lvl">04</span><div><h3>Extend</h3><p>Add a model of your own and test it against the whole committed field.</p></div><span class="cost">one config</span></li>
    </ol>
    <div>
<pre class="term"><span class="c"># every number, from the committed runs</span>
<span class="p">$ </span>make verify
<span class="c"># rerun an experiment and check its findings</span>
<span class="p">$ </span>make plan      EXP=scifact
<span class="p">$ </span>make data      EXP=scifact
<span class="p">$ </span>make reproduce EXP=scifact LEVEL=local
<span class="p">$ </span>make compare   EXP=scifact</pre>
      <div class="btns">
        <a class="btn primary" href="docs/REPRODUCE/">Reproduce it — the guide</a>
        <a class="btn" href="{BLOB}/research/REPORT_SYNTHESIS.md">The synthesis report</a>
        <a class="btn" href="docs/PROTOCOL/">The protocol</a>
        <a class="btn" href="docs/">Full documentation</a>
      </div>
      <p class="note" style="margin-top:32px">Reviewed in adversarial rounds: the <a href="{REPO}/tree/main/research/internal">lab notebook</a> records what was wrong, how it was found, and what changed; the reports state today's figures, and git keeps every earlier version.</p>
    </div>
  </div>
</div></section>
<section class="block" id="hardware"><div class="wrap">
  <div class="eyebrow"><span class="num">07</span>The hardware</div>
  <h2>Where the runs were made.</h2>
  <p class="lede">Every run on this site records the machine it ran on; the counts below are read from those records, and each machine's description from the machine itself. Most of it is a 2018 Mac mini. No open-weight LLM was run on any of these machines for these results: the "own it" figures elsewhere are provider-served scores, set against what would fit a given memory budget.</p>
  <div class="chart scroll-x reveal"><table class="data cards">
    <thead><tr><th>machine</th><th>what it is</th><th>runs on this site it measured</th><th>role</th></tr></thead>
    <tbody>{hw_rows}</tbody></table>
    <figcaption>Hosted runs are API calls made from that machine; the model ran at the provider. Local runs ran on the machine's own CPU. The DGX Spark and the MacBook measured none of these runs. Captured {hw_date}: <a href="{BLOB}/docs/evidence/hardware.json">docs/evidence/hardware.json</a>.</figcaption></div>
</div></section>
{author("experiments")}"""
    return page(
        "The most expensive model never won — eval-harness",
        f"24 LLMs, small fine-tuned models and baselines on {n_exp} public benchmarks, "
        "with significance tests, billed costs and calibration against the literature.",
        body,
        here="experiments",
    )


CARD = {
    "summarization": "Summarise a news article in two or three sentences. A 1.6 GB fine-tune is not separated from the best paid model (0.0001 apart) — on CNN's articles.",
    "ag-news": "Four-way topic labels. Three small fine-tunes lead on the point estimate, LLMs as run here; the lead is concentrated in 17 items the hosted field mostly gets wrong.",
    "dbpedia": "Fourteen-way ontology labels on a saturated benchmark: the leader cannot be separated from nineteen others (1 to 8 items behind), and the gold label is sometimes in dispute.",
    "few-nerd": "Find and type entities in a sentence. The only clean winner in the repo: a fine-tuned tagger, separated from every rival.",
    "scifact": "Retrieve the abstracts that support a scientific claim. The free e5_base retriever is not separated from the twelve LLM rerankers; reranking its top 20 adds about +0.07. The pick: build e5_base first.",
    "summeval": "Grade machine summaries the way experts do. The best LLM judges reach 93% of a human expert's agreement (best of 24, same articles), far ahead of the free evaluator trained for the task (64%), which scores one summary at a time while the judges rank all 16 at once; and an open-weight judge is not separated from the leader.",
}


# ── experiment pages ────────────────────────────────────────────────────────
def require(cond: bool, claim: str) -> None:
    """A structural claim written into the copy must hold in the data, or the build stops."""
    if not cond:
        raise SystemExit(f"site copy claims something the data no longer supports: {claim}")


# What remeasured.py borrows beyond method.py's set (defined above this point, so added here).
H.require, H.kind_of, H.both, H.legend, H.spread, H.ordinal, H.BLOB = (
    require,
    kind_of,
    both,
    legend,
    _spread,
    ordinal,
    BLOB,
)
H.remeasured_counts = remeasured_counts


def findings_for(x: dict, f: dict) -> list:
    rep = f"research/{x['report']}"
    d, t, b = x["dearest"], x["top"], x["best_hosted"]
    s = x["slug"]
    require(
        s != "summarization" or (t["arm"] == "bart_l" and b["arm"] in x["tied"]),
        "summarisation: bart_l first and tied with the best hosted arm",
    )
    require(
        s != "ag-news" or all(a["kind"] == "local" for a in x["arms"][:3]),
        "AG News: the top three are local fine-tunes",
    )
    require(
        s != "dbpedia" or ("bert_base_fy" in x["tied"] and x["n_tied"] == 19),
        "DBpedia: the leader plus nineteen others, including the fine-tune",
    )
    require(s != "few-nerd" or x["n_tied"] == 0, "Few-NERD: span_marker separated from all")
    require(
        s != "scifact" or ("e5_base" in x["tied"] and x["n_tied"] == 12),
        "SciFact: twelve tied, including e5_base",
    )
    require(
        s != "summeval"
        or sum(
            a["rank"] < min(b["rank"] for b in x["arms"] if b["kind"] != "hosted")
            for a in x["arms"]
            if a["kind"] == "hosted"
        )
        == 23,
        "SummEval: 23 of the 24 hosted judges rank above every free arm",
    )
    require(
        s != "summeval" or (x["cheapest_tied"] and x["cheapest_tied"]["weights"] == "open"),
        "SummEval: the cheapest judge tied with the leader has open weights",
    )
    common = [
        (
            f"The dearest model finished {ordinal(d['rank'])} of {x['n_arms']}.",
            f"{d['arm']} billed {money(d['cost'])} for {x['n_items']} items. "
            + (
                "Only the twelve cheapest hosted models ran here, so this is the dearest of those; no Anthropic or OpenAI arm was run. "
                if s == "scifact"
                else ""
            )
            + (
                f"The cheapest model not separated from the leader, {x['cheapest_tied']['arm']}, cost {times(x['tied_ratio'])} less."
                if x["cheapest_tied"]
                else "The leader is separated from every paid model."
            ),
        )
    ]
    if x["slug"] == "summarization":
        dm = {r["arm"]: r for r in f["dailymail"]}
        return [
            (
                "A 1.6 GB model fine-tuned on this corpus is not separated from the best paid model.",
                f"bart_l scores {t['score']:.4f} on coverage, {b['arm']} {b['score']:.4f} — "
                + q("a gap of 0.0001.", rep)
                + f" It cannot be separated from {x['n_tied']} of the other {x['n_arms'] - 1} arms.",
            ),
            *common,
            (
                "The same architecture trained on another corpus finishes last.",
                q(
                    "BART fine-tuned on XSum's one-sentence BBC summaries scores 0.2071 — 29th of 29, below lead-3.",
                    rep,
                )
                + " bart_l's lead is consistent with learning CNN's house style; the XSum control also decodes shorter, so it does not isolate style.",
            ),
            (
                "The winner depends on the metric.",
                q(
                    "On ROUGE-2 the three CNN-trained BARTs take the top three places; on ROUGE-1 the LLMs lead and bart_l is 12th.",
                    rep,
                ),
            ),
            (
                "Scope: these are CNN's articles.",
                (
                    f"All 200 come from CNN's 9% of the test set. On 200 DailyMail articles the five local models kept every verdict "
                    f"(bart_l {dm['bart_l']['dm']:.4f}, lead-3 {dm['lead3']['dm']:.4f}); the paid models were not re-run."
                ),
            ),
        ]
    if x["slug"] == "ag-news":
        return [
            (
                "Three small fine-tuned classifiers lead on the point estimate; only the first is separated from all but one paid arm.",
                f"bert_base_ta leads at {t['score']:.4f}; the best hosted model, {b['arm']}, scores {b['score']:.4f}.",
            ),
            *common,
            (
                "The lead is concentrated in 17 items the hosted field mostly gets wrong.",
                q(
                    "17 items are labelled against the judgement of most of the hosted field — business news about technology companies filed as Sci/Tech, Olympic results filed as World. The fine-tunes agree with the gold on most of them.",
                    rep,
                )
                + " "
                + q(
                    "On the other 183 items the arms cannot be told apart — anthropic_l 0.984, bert_base_ta 0.973 (discordant 3 vs 1, exact sign p = 0.625) — and that cut is selected by the hosted arms' own errors, so it flatters them.",
                    rep,
                )
                + " "
                + q(
                    "Against gold adjudicated by topic by one reader, who was shown the hosted field's answer (29 items reviewed from both sides, 17 changed), every hosted LLM scores above every fine-tune: anthropic_l leads at 0.9850 and is separated from all three (tied at 0.9050).",
                    rep,
                )
                + " The primary numbers stay on the dataset's own gold.",
            ),
        ]
    if x["slug"] == "dbpedia":
        return [
            (
                "No winner: the leader and nineteen others.",
                f"{t['arm']} leads at {t['score']:.4f}, not separated from {x['n_tied']} others, including the free fine-tune.",
            ),
            *common,
            (
                "The benchmark is saturated, and the gold is sometimes disputed.",
                q(
                    "Three items are disputed by 24 to 25 of 26 arms. Adjudicated by one reader shown the hosted answer, the gold was wrong on all three; the dataset's own gold stays primary.",
                    rep,
                ),
            ),
        ]
    if x["slug"] == "few-nerd":
        return [
            (
                "The one separated win in the repo.",
                f"span_marker, fine-tuned on Few-NERD's training split, scores {t['score']:.4f} and is separated from all {x['n_arms'] - 1} other arms.",
            ),
            *common,
            (
                "But its margin is partly the corpus's own conventions.",
                q(
                    "Against openai_m, 57% of its margin is one entity type, other, which the prompt never defined (30–57% across the hosted arms), and up to 38% of its lead is agreement with annotation the rest of the field rejects.",
                    rep,
                ),
            ),
        ]
    if x["slug"] == "scifact":
        return [
            (
                "LLM rerankers lead — and cannot be separated from eleven or twelve others.",
                f"{t['arm']} reranking BM25's top 20 scores {t['score']:.4f} nDCG@10; {x['n_tied']} arms cannot be separated from it, including the free retrievers e5_base and bge_small.",
            ),
            *common,
            (
                "The dev slice's winner finished 10th — inside a tie.",
                q(
                    "Tuned on a 40-query dev slice, the leaderboard's winner there, llama_s, finished 10th of 19 on the 200-query measurement slice, 0.0265 behind the leader and not separated from it under Holm: a rank inside a tie, not a wrong pick shown at this n.",
                    rep,
                ),
            ),
        ]
    if x["slug"] == "summeval":
        free = [a for a in x["arms"] if a["kind"] != "hosted"]
        best_free = min(free, key=lambda a: a["rank"])
        weakest = max((a for a in x["arms"] if a["kind"] == "hosted"), key=lambda a: a["rank"])
        ct = x["cheapest_tied"]
        return [
            (
                "On mean τ, 23 of 24 LLM judges score above a free evaluator trained for the task.",
                f"The best free scorer, {best_free['arm']} (UniEval, on its own inputs), scores "
                f"{best_free['score']:.4f}; the weakest judge, {weakest['arm']}, {weakest['score']:.4f}. "
                + q(
                    "In the paired test UniEval is separated below 23 of the 24 judges and cannot "
                    "be separated from the weakest, on either set of inputs.",
                    rep,
                )
                + " "
                + q(
                    "The judges rank all 16 summaries in one call while UniEval scores one at a time, "
                    "and a pointwise LLM judge was not run.",
                    rep,
                ),
            ),
            (
                "An open-weight judge is not separated from the leader.",
                f"{ct['arm']} scores {ct['score']:.4f} against {t['arm']}'s {t['score']:.4f}, and "
                f"the leader cannot be separated from it or from {x['n_tied'] - 1} others. "
                + q(
                    "No provider was pinned: one judge, run once on each of two providers, scored 0.0113 apart and billed 3.7× apart.",
                    rep,
                ),
            ),
            *common,
            (
                "The best judges come close to a single expert, and stay below one.",
                q(
                    "Scored against the mean of two experts, as one expert is against the other two, "
                    "the best judge reaches 0.5195 — 93% of one expert's 0.5587 (95% interval 89–97%), "
                    "and the gap excludes zero. It is the best of 24, chosen on the same articles "
                    "(92% when chosen on half and scored on the other half). "
                    "UniEval reaches 64%, BARTScore 44%; a no-model lookup of which system wrote each "
                    "summary reaches 63%. The summaries are 2019-era and reasoning was off.",
                    rep,
                ),
            ),
            (
                "The order is stable; the winner is not.",
                q(
                    "Two disjoint 20-article halves agree at ρ = 0.90 on the order of the 24 judges, "
                    "but name the same unique winner only 21% of the time.",
                    rep,
                ),
            ),
            (
                "This repository's own metric agrees with experts less than ROUGE does.",
                q("coverage agrees with the experts at τ 0.1011, below ROUGE-1's 0.1487.", rep),
            ),
        ]
    return common


def not_found_page() -> str:
    body = f"""
<section class="hero"><div class="wrap">
  <h1>Not here.</h1>
  <p class="dek">That page does not exist, or it moved. The documentation now lives at its own
  address, and the catalog of runs at another.</p>
  <div class="btns"><a class="btn primary" href="index.html">The harness</a><a class="btn" href="experiments.html">The experiments</a><a class="btn" href="docs/">Documentation</a><a class="btn" href="{CATALOG}">Catalog</a></div>
</div></section>"""
    return page("Not found — eval-harness", "This page does not exist.", body)


def privacy_page() -> str:
    """The family's standard privacy page (humancopilot.eu's wording), with this site's own
    facts: no cookies or forms; Umami, and Cloudflare Web Analytics because Cloudflare delivers
    the site; the server's request logs, kept 30 days; the docs on GitHub Pages, which keeps its
    own logs; and the theme choice kept in the browser."""
    gh = "https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement"
    umami = "https://umami.is/"

    def ext(url: str, label: str, tgt: str) -> str:
        return (
            f'<a href="{e(url)}" data-umami-event="outbound" data-umami-event-target="{tgt}" '
            f'rel="noopener">{label}</a>'
        )

    body = f"""
<section class="hero"><div class="wrap">
  <h1>Privacy</h1>
  <p class="dek">This site sets no cookies and has no forms.</p>
</div></section>
<section class="block"><div class="wrap prose">
  <h2>Analytics</h2>
  <p>Page views and clicks on links are counted with a self-hosted instance of {ext(umami, "Umami", "umami")}. It sets no cookies and stores no personal data. Counts are aggregate: pages, referrers, countries, browsers and devices.</p>
  <p>Cloudflare, which delivers this site, also measures visits and page speed with its Web Analytics. It sets no cookies either.</p>
  <h2>Server logs</h2>
  <p>The web server records requests (time, page, IP address, browser) to keep the site running and secure. That includes the catalog and its run inspector, which answer from the same server. Searchable logs are deleted after 30 days. Copies on the server are size-capped and overwritten as new requests come in. Logs are not shared.</p>
  <h2>Documentation</h2>
  <p>The documentation is hosted on GitHub Pages. GitHub keeps its own request logs under its {ext(gh, "privacy statement", "github-privacy")}.</p>
  <h2>Your browser</h2>
  <p>The light/dark switch remembers your choice in your browser's local storage. It is not a cookie and is never sent anywhere.</p>
  <h2>Email</h2>
  <p>If you email me, I use your message only to reply.</p>
  <h2>Contact</h2>
  <p><a href="mailto:marko@humancopilot.eu" data-umami-event="cta-email" data-umami-event-position="privacy">marko@humancopilot.eu</a></p>
</div></section>"""
    return page("Privacy — eval-harness", "What this site counts, and what it does not.", body)


#: One line in the hero of a re-measured experiment, under the report's pick, so a reader sees
#: before the findings that the pick rests on the primary measurement and what moved it.
REMEASURED_NOTE = {
    "ag-news": "On labels one reader corrected, every hosted LLM has a higher accuracy than every "
    "fine-tune, so the fine-tune pick holds only if your labels follow AG News's filing "
    "convention.",
    "dbpedia": "Three disputed labels were corrected; the top stays a crowd and the pick stands.",
    "summarization": "SummEval-validated LLM judges, cheap and frontier, rank every hosted LLM above every BART "
    "model; one reader's check went the other way. Neither is confirmed.",
}


def remeasured_note(x: dict) -> str:
    t = REMEASURED_NOTE.get(x["slug"])
    return (
        (
            f'\n  <p class="note"><b>Re-measured.</b> {e(t)} <a href="#remeasured">Below</a> · '
            f'<a href="judging.html">what it teaches</a></p>'
        )
        if t
        else ""
    )


def remeasured_block(x: dict, f: dict, num: int) -> str:
    """For an experiment that was re-measured (or whose judges did the re-measuring): what
    changed, in one paragraph, and the way to the judging page. Numbers are computed."""
    r = f["remeasure"]
    head, text = "", ""
    if x["slug"] == "summarization":
        a = {z["arm"]: z for z in r["summ"]["arms"]}
        hc, hc2 = r["summ"]["fig"]["human_check"], r["summ_v2"]["fig"]["human_check"]
        head = "Re-measured by SummEval-validated LLM judges, and checked by a person."
        text = (
            f"Scored again by two LLM judges validated on SummEval, every hosted LLM ranks above "
            f"every BART model: bart_l falls from {ordinal(a['bart_l']['r1'])} to "
            f"{ordinal(a['bart_l']['r2'])} of {r['summ']['n_arms']} (the hosted scores bunch near the "
            f"top of the scale, so their own order is not a finding). One reader's blind check of "
            f"{hc['pairs']} pairs on truncated articles went the other way, "
            f"{hc['human_prefers_bart_l']} to {hc['human_prefers_deepseek_m']} for bart_l over "
            f"deepseek_m, not significant either. Two frontier judges at "
            f"{times(r['summ_v2']['billed_usd'] / r['summ']['billed_usd'])} the price agreed with the first pair, "
            f"{hc2['judge_prefers_deepseek_m']} to {hc2['judge_prefers_bart_l']} on the same "
            "pairs. On crowd ratings of 2022 LLM summaries the judges track people better than one, "
            "noisy, rater does on coherence and relevance (not on faithfulness), while still ranking "
            "systems differently in both directions; on these "
            "outputs neither is confirmed, so coverage stays the primary metric."
        )
    elif x["slug"] in ("ag-news", "dbpedia"):
        d = r["ag" if x["slug"] == "ag-news" else "db"]
        if x["slug"] == "ag-news":
            fts = [z for z in d["arms"] if z["arm"].startswith("bert_")]
            lead = max(d["arms"], key=lambda z: z["v2"])
            head = "Re-measured against labels a person corrected."
            text = (
                f"One reader, the author, adjudicated by topic {d['n_items']} items, shown the hosted answer: "
                f"the {d['changed']} disputed ones, which at least 80% of the hosted LLMs got wrong, and the "
                f"{d['n_items'] - d['changed']} others a fine-tune got wrong. The gold was wrong on all "
                f"{d['changed']} disputed items and right on the {d['n_items'] - d['changed']}. On that gold "
                "every hosted LLM has "
                f"a higher accuracy than every fine-tune: the fine-tunes fall from "
                f"{min(z['r1'] for z in fts)}–{max(z['r1'] for z in fts)} to "
                f"{min(z['r2'] for z in fts)}–{max(z['r2'] for z in fts)} of {d['n_arms']}, and "
                f"{lead['arm']} rises to first (separated from the fine-tunes, not from most hosted "
                "arms). The dataset's own gold stays primary."
            )
        else:
            fy = next(z for z in d["arms"] if z["arm"] == "bert_base_fy")
            head = "Re-measured against labels a person corrected."
            text = (
                f"One reader, the author, adjudicated {d['n_items']} items, shown the hosted answer: the "
                f"{d['changed']} disputed ones, which at least 90% of the hosted LLMs got wrong, and the "
                f"{d['n_items'] - d['changed']} others bert_base_fy got wrong. The gold was wrong on all "
                f"{d['changed']} disputed items and right on the {d['n_items'] - d['changed']}. The top "
                "stays a crowd, and bert_base_fy moves "
                f"from {ordinal(fy['r1'])} to {ordinal(fy['r2'])} at an unchanged {fy['v1']:.4f}. "
                "The dataset's own gold stays primary."
            )
    elif x["slug"] == "summeval":
        se = r["summeval"]
        head = "These judges, put to work."
        text = (
            f"Two of these judges, gemma_l (τ {se['gemma_l']:.2f}) and qwen_s ({se['qwen_s']:.2f}), "
            "re-measured the summarisation experiment's summaries, where its own metric agrees with "
            f"the experts at τ {se['coverage']:.2f}. They re-ranked the field; one reader's blind check "
            f"of {r['summ']['fig']['human_check']['pairs']} pairs went the other way, not significantly. "
            "On crowd ratings of 2022 LLM summaries (Zhang et al.) the same judges track people better "
            "than one rater does on coherence and relevance, trail on faithfulness, and do not rank the "
            "systems the same way; on the summarisation experiment's own outputs neither is confirmed."
        )
    if not head:
        return ""
    return (
        f'<section class="block" id="remeasured"><div class="wrap"><div class="eyebrow">'
        f'<span class="num">{num:02d}</span>Re-measured</div><h2>{e(head)}</h2>'
        f'<div class="prose"><p>{e(text)}</p></div><div class="btns">'
        f'<a class="btn" href="judging.html">What re-measuring changed, and what it teaches →</a>'
        f"</div></div></section>"
    )


def catalog_dataset(x: dict) -> str:
    """The catalog's page for the experiment's dataset (every arm on it, with its own page)."""
    require(
        (figures.DATA / "datasets" / f"{x['dataset']}.json").is_file(),
        f"{x['slug']}: the catalog has a page for dataset {x['dataset']}",
    )
    return f"d/{x['dataset']}.html"


def catalog_inspect(x: dict) -> str:
    """The inspector, opened on every arm of the experiment against its leader: the same Holm
    family as the site's own test (a single pair would get only Holm's strictest step, and could
    call "not separated" what the site, testing the whole field, separates)."""
    keys = []
    for a in x["arms"]:
        cid = f"{x['prefix']}{a['arm']}{x['suffix']}"
        require(
            any(
                (m := json.loads(p.read_text())).get("config_id") == cid
                and m.get("dataset_id") == x["dataset"]
                for p in (figures.DATA / x["base"]).glob(f"{cid}*/metrics.json")
            ),
            f"{x['slug']}: a committed run of {cid} on {x['dataset']} for the inspector link",
        )
        keys.append(f"{x['base']}/{x['dataset']}/{cid}")
    base = f"{x['base']}/{x['dataset']}/{x['prefix']}{x['leader']}{x['suffix']}".replace("/", "%2F")
    return f"inspect.html?runs={','.join(keys)}&amp;baseline={base}&amp;metric={x['metric']}"


H.catalog_inspect = catalog_inspect


def goal_note(x: dict) -> str:
    """What the experiment's goal decides, as the catalog computes it (figures.goal_decisions),
    linked to its goal page. The build stops if the site's leader or the report's pick disagrees
    with the catalog."""
    g = x["goal"]
    require(
        g["leader"] == x["leader"],
        f"{x['slug']}: the site's leader {x['leader']} is the catalog's gold leader ({g['leader']})",
    )
    rec = g["recommended"]
    require(
        rec is None or re.search(rf"\b{re.escape(rec)}\b", PICK[x["slug"]]) is not None,
        f"{x['slug']}: the report's pick names the catalog's recommendation {rec}",
    )
    if rec:
        says = f"recommends <b>{e(rec)}</b>" + (", the promoted baseline" if rec == g["baseline"] else "")
    else:
        # The reasons after the strategy line (what broke the tie, or why nothing could), with
        # config ids shortened to the arm names this page uses.
        short = re.compile(rf"\b{re.escape(x['prefix'])}(\w+?){re.escape(x['suffix'])}\b")
        says = "recommends no single arm yet. " + e(
            " ".join(short.sub(r"\1", w) for w in g["why"][1:]).rstrip(".")
        )
    base = (
        f" The baseline a person promoted is <b>{e(g['baseline'])}</b>, with the reason recorded: "
        f"\u201c{e(g['baseline_reason'])}\u201d"
        if g["baseline"] and rec != g["baseline"]
        else ""
    )
    return (
        f'<p class="note"><b>The goal\'s rule, in the catalog.</b> {e(g["goal_title"])} ({e(g["strategy"])}, on '
        f'{e(g["measure"])}) {says}.{base} <a href="{CATALOG}{g["goal_page"]}">The goal page, with its reasons →</a></p>'
    )


def experiment_page(x: dict, f: dict) -> str:
    cal = [r for r in f["calibration"] if r["bench"] == x["bench"]]
    cal_txt = "; ".join(
        f"{r['what']} {r['ours'] / r['scale']:.4f} vs {r['published'] / r['scale']:.4f} published"
        if r["scale"] == 100
        else f"{r['what']} {r['ours']:.2f} vs {r['published']:.2f} published"
        for r in cal
    )
    facts = [
        ("Question", QUESTION[x["slug"]]),
        ("Data", f"{x['n_items']} items from the {x['bench']} test split"),
        (
            "Systems",
            f"{x['n_arms']} compared: {x['n_hosted']} hosted models billed per call; {x['n_arms'] - x['n_hosted']} local models and baselines, free",
        ),
        (
            "Metric",
            f"{x['metric_label']}" + METRIC_GLOSS.get(x["slug"], " — the field's standard; higher is better"),
        ),
        ("Calibration", cal_txt or "—"),
        ("Billed", f"{money(x['billed_total'])} for the whole sweep"),
    ]
    facts_html = "".join(
        f'<div class="fact"><div class="k">{e(k)}</div><div class="v">{e(v)}</div></div>' for k, v in facts
    )
    finds = "".join(f"<li><div><h3>{e(h)}</h3><p>{e(p)}</p></div></li>" for h, p in findings_for(x, f))
    free = x["n_arms"] - x["n_hosted"]
    lesson = method.experiment_lesson(H, x)
    n = 4
    extra = ""
    if x["slug"] == "summarization":
        extra = f"""<section class="block" id="dailymail"><div class="wrap"><div class="eyebrow"><span class="num">{n:02d}</span>Outside CNN</div>
<h2>Does it hold on DailyMail?</h2><div class="cols"><div class="prose"><p>The committed sample is all CNN. On 200 DailyMail articles drawn at random, the five local summarisers keep every verdict among themselves. The hosted models were not re-run there.</p></div>
<figure class="chart">{both(slope(f["dailymail"]), slope(f["dailymail"], compact=True))}</figure></div></div></section>"""
        n += 1
    rem = remeasured_block(x, f, n)
    if rem:
        extra += rem
        n += 1
    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>{e(x["task"])}</b> · {e(x["bench"])}</div>
  <h1 style="max-width:16ch">{e(HEADLINE[x["slug"]])}</h1>
  <p class="dek">{e(CARD[x["slug"]])}</p>
  <p class="note"><b>The report's pick, as run here.</b> {e(PICK[x["slug"]])}</p>{goal_note(x)}{remeasured_note(x)}
  <div class="facts">{facts_html}</div>
  <div class="btns"><a class="btn primary" href="{BLOB}/research/{x["report"]}">Read the full report</a><a class="btn" href="{CATALOG}{x["goal"]["goal_page"]}">In the catalog</a><a class="btn" href="{BLOB}/docs/PROTOCOL.md">Protocol</a><a class="btn" href="../experiments.html#experiments">All experiments</a></div>
</div></section>
<section class="block" id="field"><div class="wrap"><div class="eyebrow"><span class="num">01</span>The field</div>
  <h2>Every system, one axis.</h2>
  <div class="chart">{legend(reading="higher score: further right →", baseline=False)}{both(strip(x, title=False, height=80), strip(x, title=False, compact=True))}<figcaption>Each dot is one system, by {e(x["metric_label"])}. The ringed dot is the most expensive hosted model{" (of the twelve cheapest hosted models, the only ones run here)" if x["slug"] == "scifact" else ""}; the shaded band is the group the leader cannot be statistically separated from.{OFF_NOTE if off_scale([a for a in x["arms"] if a["kind"] != "baseline"])[1] else ""} Every system has its own page in <a href="{CATALOG}{catalog_dataset(x)}">the catalog</a>: its run, cost, speed and fingerprint.</figcaption></div>
</div></section>
<section class="block" id="cost"><div class="wrap"><div class="eyebrow"><span class="num">02</span>Cost</div>
  <h2>What the money bought.</h2>
  <div class="chart">{legend(band=False, reading="better: up · cheaper: left", baseline=False)}{both(scatter(x), scatter(x, compact=True))}<figcaption>Billed cost per 1,000 items, read from the provider's response, against {e(x["metric_label"])}. Free models sit in the left lane.{OFF_NOTE_Y if off_scale([a for a in x["arms"] if a["kind"] != "baseline"])[1] else ""}</figcaption></div>
</div></section>
<section class="block" id="findings"><div class="wrap"><div class="eyebrow"><span class="num">03</span>Findings</div>
  <h2>What this experiment found.</h2>
  <ol class="findings">{finds}</ol>
</div></section>
{extra}
<section class="block" id="habit"><div class="wrap"><div class="eyebrow"><span class="num">{n:02d}</span>The method, here</div>
  <div class="lesson"><h2>{e(lesson[1])}</h2><p>{lesson[2]}</p><a class="btn" href="../method.html#{lesson[0]}">This habit, in the method →</a></div>
</div></section>
<section class="block" id="reproduce"><div class="wrap"><div class="eyebrow"><span class="num">{n + 1:02d}</span>Reproduce it</div>
  <h2>Check it yourself.</h2>
  <div class="cols">
    <div class="prose">
      <p><strong>First, with nothing installed:</strong> <a href="{CATALOG}{catalog_inspect(x)}">test every arm against {e(x["leader"])}</a>, item by item, in the catalog's inspector, with the same paired test and Holm correction as this page; {e(x["dearest"]["arm"])}, the most expensive model, among them. <a href="{CATALOG}{x["goal"]["goal_page"]}">The goal page</a> has the rest: what the goal recommends, and why.</p>
      <p>The {free} free arms rerun on a laptop CPU for $0, pinned to the weights that were measured. The {x["n_hosted"]} hosted arms billed <strong>${x["billed_total"]:.2f}</strong> when measured and rerun with one OpenRouter key.</p>
      <p><code>make compare</code> writes a replication card: each rerun against its committed run, item by item, and every separation and tie on this page re-tested with your reruns in place.</p>
      <div class="btns"><a class="btn primary" href="../docs/REPRODUCE/">The guide</a><a class="btn" href="{REPO}/tree/main/examples/{x["example"]}">This example's code</a></div>
    </div>
<pre class="term"><span class="p">$ </span>make plan      EXP={x["slug"]}
<span class="p">$ </span>make data      EXP={x["slug"]}
<span class="p">$ </span>make reproduce EXP={x["slug"]} LEVEL=local
<span class="c"># with OPENROUTER_API_KEY set</span>
<span class="p">$ </span>make reproduce EXP={x["slug"]} LEVEL=hosted
<span class="p">$ </span>make compare   EXP={x["slug"]}</pre>
  </div>
</div></section>"""
    return page(
        f"{x['task']} · {x['bench']} — eval-harness", CARD[x["slug"]], body, depth=1, here="experiments"
    )


OFF_NOTE = " A dot left of the ⫽ break sits far below the rest, off the scale; tap it for its score."
OFF_NOTE_Y = " A dot below the ⫽ break sits far below the rest, off the scale; tap it for its score."

METRIC_GLOSS = {
    "summarization": " — how much of the reference summary's wording the summary recovers, at the reference's length (ROUGE-Lsum recall, clipped); this repo's own, see the protocol. Higher is better. Measured against human experts on SummEval, it agrees with them less than ROUGE-1 does",
    "few-nerd": " — entities found with the right type, set-matched per sentence and averaged, on 8 coarse types; this repo's own, see the protocol. Higher is better",
    "summeval": " — how well a judge's scores order the 16 summaries of an article the way the experts' do (Kendall τ-b per article, averaged over four dimensions); the field's standard. 1 is perfect agreement, 0 none",
}

QUESTION = {
    "summarization": "Summarise a news article in two or three short sentences, in a wire-service style.",
    "ag-news": "Label a news snippet World, Sports, Business or Sci/Tech.",
    "dbpedia": "Label a Wikipedia abstract with one of 14 ontology classes.",
    "few-nerd": "Find every named entity in a sentence and give it one of 8 types.",
    "scifact": "Rank 5,183 scientific abstracts by how well they bear on a claim.",
    "summeval": "Score 16 summaries of a news article on coherence, consistency, fluency and relevance, as three experts did.",
}
PICK = {
    "summarization": q(
        "Use bart_l if you can run a free 1.6 GB model on CPU and your text looks like CNN news; rent deepseek_m ($191 per 1M articles) if you need speed; do not buy anthropic_l.",
        "research/REPORT_SUMMARIZATION.md",
    ),
    "ag-news": q(
        "If your labels follow a house convention, fine-tune on them, starting with bert_mini; if they mean what the words say, use a hosted LLM. If you rent, start with gemma_m ($8 per 1M items).",
        "research/REPORT_CLASSIFICATION.md",
    ),
    "dbpedia": q(
        "Take the cheapest arm you can run at 0.9857: gemma_m (~$12 per 1M items), qwen_s (~$26) or the fine-tuned bert_base_fy.",
        "research/REPORT_CLASSIFICATION.md",
    ),
    "few-nerd": q(
        "If you have labelled data in a fixed taxonomy, fine-tune a small tagger (span_marker); do not rent a zero-shot hosted LLM for this job. If you do rent, take the cheapest, gemma_m.",
        "research/REPORT_NER.md",
    ),
    "scifact": q(
        "Build e5_base retrieval first (0.7191, $0 per query); add an LLM reranker on its top 20 only if about +0.07 nDCG@10 is worth about $732 per 1M queries. Only the twelve cheapest hosted LLMs were tried.",
        "research/REPORT_RETRIEVAL.md",
    ),
    "summeval": q(
        "Use an LLM judge, and start with gemma_l; before relying on any judge, check it against a small set of human judgements on your own outputs.",
        "research/REPORT_SUMMEVAL.md",
    ),
}
HEADLINE = {
    "summarization": "A free model not separated from the best paid one — on CNN's news.",
    "ag-news": "Small models lead, largely on disputed labels.",
    "dbpedia": "The leader cannot be separated from 19 others.",
    "few-nerd": "The one clean win.",
    "scifact": "Free retrieval first; a reranker adds about +0.07.",
    "summeval": "On mean τ, 23 of 24 LLM judges score above a trained free evaluator.",
}


# ── crawl files ─────────────────────────────────────────────────────────────
#: The docs site (MkDocs, built into /docs/) writes its own sitemap; robots.txt points
#: to both. No AI-training rules: whether this open research opts out is undecided.
ROBOTS = f"""User-agent: *
Allow: /

Sitemap: {SITE}/sitemap.xml
Sitemap: {SITE}/docs/sitemap.xml
"""


def sitemap_urls(out: Path) -> list:
    """Absolute URLs of every page this build writes, as Pages serves them. No lastmod:
    the build is deterministic and site-check compares it byte for byte, so a build date
    would make every day's check fail, and no other date here is reliable per page."""
    pages = sorted(
        (p.relative_to(out).as_posix() for p in out.rglob("*.html") if p.name != "404.html"),
        key=lambda p: (p != "index.html", p),
    )
    return [f"{SITE}/" if p == "index.html" else f"{SITE}/{p}" for p in pages]


def sitemap_xml(urls: list) -> str:
    rows = "".join(f"  <url><loc>{e(u)}</loc></url>\n" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{rows}</urlset>\n"
    )


def check_crawl_files(out: Path) -> list:
    """What is wrong with robots.txt and sitemap.xml in `out`: missing, or a sitemap
    URL that names no page the build wrote. (The deployed check in pages.yml asks the
    live domain for a 200 on each URL.)"""
    problems = []
    robots, smap = out / "robots.txt", out / "sitemap.xml"
    if not robots.is_file():
        problems.append("robots.txt is missing")
    elif f"Sitemap: {SITE}/sitemap.xml" not in robots.read_text(encoding="utf-8"):
        problems.append("robots.txt does not point to the sitemap")
    if not smap.is_file():
        problems.append("sitemap.xml is missing")
        return problems
    import re  # noqa: PLC0415

    urls = re.findall(r"<loc>([^<]+)</loc>", smap.read_text(encoding="utf-8"))
    if not urls:
        problems.append("sitemap.xml lists no URLs")
    for u in urls:
        rel = "index.html" if u == f"{SITE}/" else u[len(SITE) + 1 :] if u.startswith(SITE + "/") else None
        if rel is None or not (out / rel).is_file():
            problems.append(f"sitemap URL with no page behind it: {u}")
    return problems


#: Where a reader copies the install line from. Each pin must name the latest release, as the
#: site's own install line does: the docs said @v0.4.1 while the site said @v0.4.3 (found
#: reviewing the 0.4.4 render). UPGRADING and the CHANGELOG name old releases on purpose, and
#: infra/README.md's cutover steps record the release they were run with.
PIN_FILES = ("README.md", "harness/README.md", "docs/**/*.md", "harness/docs/*.md")
PIN_EXEMPT = {"harness/docs/UPGRADING.md", "harness/CHANGELOG.md"}
PIN = re.compile(r"eval-harness@v(\d+\.\d+\.\d+)#subdirectory=harness")


def check_pins() -> list:
    """Every install pin a reader can copy names the latest dated release in the changelog."""
    latest = next(r["version"] for r in releases.releases(releases.CHANGELOG.read_text()) if r["date"])
    problems = []
    for pattern in PIN_FILES:
        for p in sorted(ROOT.glob(pattern)):
            rel = p.relative_to(ROOT).as_posix()
            if rel in PIN_EXEMPT:
                continue
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                for v in PIN.findall(line):
                    if v != latest:
                        problems.append(f"{rel}:{n} pins v{v}; the latest release is v{latest}")
    return problems


def check_links(out: Path, catalog_pages: set) -> list:
    """What is broken among the built pages' links: a relative href or src naming no built file,
    a #anchor its page does not have, a catalog link that is neither the catalog's home nor a page
    the site names and checks against the data (catalog_pages: goal and dataset pages, the
    inspector links). The docs check their own (mkdocs build --strict)."""
    problems = []
    ids: dict = {}
    for page in sorted(out.rglob("*.html")):
        text = page.read_text(encoding="utf-8")
        ids[page] = set(re.findall(r'\sid="([^"]+)"', text))
    for page, _ in ids.items():
        text = page.read_text(encoding="utf-8")
        base = out if page.name == "404.html" else page.parent  # 404 resolves from the root (<base>)
        for link in re.findall(r'(?:href|src)="([^"]+)"', text):
            if link.startswith(CATALOG):
                rest = link[len(CATALOG) :]
                if rest and rest.replace("&amp;", "&") not in catalog_pages:
                    problems.append(f"{page.relative_to(out)}: {link} is no catalog page the site checks")
                continue
            if re.match(r"^[a-z]+:", link) or link.startswith("//"):
                continue  # another site (or mailto:)
            path, _, anchor = link.partition("#")
            # A root-relative path ("/", the 404 page's base) is the site's root.
            target = (
                (out / path.lstrip("/") if path.startswith("/") else base / path).resolve() if path else page
            )
            if path and target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                problems.append(f"{page.relative_to(out)}: {link} names no built file")
            elif anchor and target in ids and anchor not in ids[target]:
                problems.append(f"{page.relative_to(out)}: {link} has no #{anchor} there")
    return problems


def point_docs(out: Path) -> None:
    """The templates link the docs as `docs/<page>/`, relative, from when the docs were served
    under /docs/ on this host. They now live at DOCS: rewrite every such link there, in one
    place. Old /docs/... URLs elsewhere on the web are redirected by the server (infra/nginx)."""
    pat = re.compile(r'href="(?:\.\./)*docs/')
    for page in out.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        new = pat.sub(f'href="{DOCS}', text)
        if new != text:
            page.write_text(new, encoding="utf-8")


# ── build ───────────────────────────────────────────────────────────────────
def build(out: Path) -> dict:
    """Write the site into `out`; return the figures it was built from."""
    f = figures.compute()
    if out.exists():
        shutil.rmtree(out)
    (out / "experiments").mkdir(parents=True)
    shutil.copytree(HERE / "assets", out / "assets")
    (out / "index.html").write_text(home(f), encoding="utf-8")
    (out / "experiments.html").write_text(landing(f), encoding="utf-8")
    (out / "method.html").write_text(method.method_page(H, f), encoding="utf-8")
    (out / "use.html").write_text(method.use_page(H, f), encoding="utf-8")
    (out / "privacy.html").write_text(privacy_page(), encoding="utf-8")
    # Served for any missing path at any depth, so its relative links resolve from the root.
    (out / "404.html").write_text(
        not_found_page().replace("<head>", '<head>\n<base href="/">', 1), encoding="utf-8"
    )
    (out / "releases.html").write_text(releases.releases_page(H), encoding="utf-8")
    (out / "experiments" / "judging.html").write_text(remeasured.judging_page(H, f), encoding="utf-8")
    for x in f["experiments"]:
        (out / "experiments" / f"{x['slug']}.html").write_text(experiment_page(x, f), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    (out / "sitemap.xml").write_text(sitemap_xml(sitemap_urls(out)), encoding="utf-8")
    (out / "robots.txt").write_text(ROBOTS, encoding="utf-8")
    point_docs(out)
    # Last: no inline script or style survives, so the prod CSP needs no 'unsafe-inline'.
    csp.externalize(out)
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if site/public is stale")
    args = ap.parse_args()
    if not args.check:
        build(OUT)
        print(f"wrote {OUT.relative_to(ROOT)}")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / "public"
        f = build(fresh)
        diff = filecmp.dircmp(fresh, OUT)
        stale = []

        def walk(d, rel=""):
            stale.extend(f"{rel}{n}" for n in d.left_only + d.right_only + d.diff_files)
            for n, sub in d.subdirs.items():
                walk(sub, f"{rel}{n}/")

        walk(diff)
        if stale:
            print("FAIL  site/public is stale; run `python site/build.py`:", *stale, sep="\n  ")
            return 1
    crawl = check_crawl_files(OUT)
    if crawl:
        print("FAIL  robots.txt / sitemap.xml:", *crawl, sep="\n  ")
        return 1
    print("ok    robots.txt and sitemap.xml present; every sitemap URL is a built page")
    broken = check_links(
        OUT,
        {x["goal"]["goal_page"] for x in f["experiments"]}
        | {catalog_dataset(x) for x in f["experiments"]}
        | {catalog_inspect(x).replace("&amp;", "&") for x in f["experiments"]}
        | method.CATALOG_PAGES,
    )
    if broken:
        print("FAIL  links:", *broken, sep="\n  ")
        return 1
    print("ok    every link resolves: built files, their anchors, the catalog pages the site names")
    pins = check_pins()
    if pins:
        print("FAIL  install pins:", *pins, sep="\n  ")
        return 1
    print("ok    every install pin in the docs names the latest release")
    print("ok    site/public matches a fresh build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
