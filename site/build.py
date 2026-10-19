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
import figures  # noqa: E402
import method  # noqa: E402

ROOT = HERE.parent
REPO = "https://github.com/chipi/eval-harness"
BLOB = f"{REPO}/blob/main"
SITE = "https://evals.humancopilot.eu"
OUT = HERE / "public"


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


def e(s) -> str:
    return html.escape(str(s), quote=True)


def money(x: float) -> str:
    return f"${x:,.2f}" if x >= 0.995 else f"${x:.4f}"


def times(x: float) -> str:
    # As the reports state them: whole multiples truncated (115.66 is "115×", never "116×"),
    # small ones to one decimal (2.49 is "2.5×").
    return f"{math.floor(x)}×" if x >= 10 else f"{x:.1f}×"


_WORDS = ("zero one two three four five six seven eight nine ten").split()


def word(n: int) -> str:
    """A small count as prose writes it: 6 is "six"."""
    return _WORDS[n] if 0 <= n < len(_WORDS) else str(n)


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


KIND = {"proprietary": "proprietary", "open": "open", "local": "local", "baseline": "baseline"}
KIND_LABEL = {"proprietary": "hosted · proprietary", "open": "hosted · open weights",
              "local": "local · free", "baseline": "baseline"}


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
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" class="dot k-{k}"><title>{e(tip)}</title></circle>'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="12" class="hit" data-tip="{e(tip)}"/>')


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
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{e(exp["bench"])}: every learned arm by {e(exp["metric_label"])}">']
    if title and compact:
        out.append(f'<text x="0" y="20" class="t-head" font-size="20">{e(exp["bench"])}</text>'
                   f'<text x="{width}" y="20" text-anchor="end" class="t-muted" font-size="14">{e(exp["task"].lower())} · {e(exp["metric_label"])}</text>')
    elif title:
        out.append(f'<text x="0" y="{y - 6}" class="t-head" font-size="17">{e(exp["bench"])}</text>'
                   f'<text x="0" y="{y + 14}" class="t-muted" font-size="11">{e(exp["task"].lower())} · {e(exp["metric_label"])}</text>')
    if len(tied) > 1:
        x0, x1 = x(min(a["score"] for a in tied)), x(max(a["score"] for a in tied))
        out.append(f'<rect x="{x0 - 8:.1f}" y="{y - 22}" width="{x1 - x0 + 16:.1f}" height="44" rx="10" class="band"/>')
    out.append(f'<line x1="{left}" x2="{right}" y1="{y}" y2="{y}" class="axis"/>')
    if off:
        out.append(f'<line x1="{edge}" x2="{edge + 14}" y1="{y}" y2="{y}" class="axis"/>'
                   f'<text x="{edge + 23}" y="{y + 5}" text-anchor="middle" class="t-muted" font-size="{fs + 2}">⫽</text>')
    for a in sorted(arms, key=lambda a: a["arm"] == exp["dearest"]["arm"]):
        k = kind_of(a)
        tip = (f'{a["arm"]} · {KIND_LABEL[k]}\n{exp["metric_label"]} {a["score"]:.4f} · rank {a["rank"]}/{exp["n_arms"]}'
               + (f'\nbilled {money(a["cost"])} for {exp["n_items"]} items' if a["cost"] > 0 else "\nfree: runs locally, nothing billed") + ("\noff the scale: far below the field" if a in off else ""))
        r = 7 if a["arm"] in (exp["top"]["arm"], exp["dearest"]["arm"]) else 5.5
        out.append(dot(x(a["score"]), y, r, k, tip))
    d, t = exp["dearest"], exp["top"]
    half = 100 if compact else 70  # keep the centred label inside the frame
    dx = min(max(x(d["score"]), left + half), right - half)
    out.append(f'<circle cx="{x(d["score"]):.1f}" cy="{y}" r="11" class="ring"/>'
               f'<text x="{dx:.1f}" y="{y - 18}" text-anchor="middle" class="t-ink" font-size="{fs}">dearest · {ordinal(d["rank"])} · {d["score"]:.3f}</text>')
    if t["arm"] != d["arm"]:
        out.append(f'<text x="{min(x(t["score"]), right - 4):.1f}" y="{y + 30}" text-anchor="end" class="t-ink" font-size="{fs}">{e(t["arm"])} · 1st · {t["score"]:.3f}</text>')
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

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Calibration: this repo against published values">']
    for t in (-4, -2, 0, 2, 4):
        cls = "axis" if t == 0 else "grid"
        out.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top - 8}" y2="{height - 26}" class="{cls}"/>'
                   f'<text x="{x(t):.1f}" y="{height - 8}" text-anchor="middle" class="t-muted" font-size="10">{t:+d}</text>')
    out.append(f'<text x="{x(0):.1f}" y="{top - 16}" text-anchor="middle" class="t-muted" font-size="10">published value</text>')
    for i, r in enumerate(rows):
        y = top + i * row_h + row_h / 2
        lo, hi = max(-span, r["delta"] - r["ci"]), min(span, r["delta"] + r["ci"])
        fmt = (lambda v: f"{v:.2f}") if r["scale"] == 1 else (lambda v: f"{v / 100:.4f}")
        tip = f'{r["bench"]} · {r["what"]}\nours {fmt(r["ours"])} ± {fmt(r["ci"])}\npublished {fmt(r["published"])}\nn = {r["n"]}'
        out.append(f'<text x="0" y="{y - 3}" class="t-ink" font-size="13">{e(r["bench"])}</text>'
                   f'<text x="0" y="{y + 13}" class="t-muted" font-size="11">{e(r["what"])}</text>'
                   f'<line x1="{x(lo):.1f}" x2="{x(hi):.1f}" y1="{y}" y2="{y}" stroke="var(--ink-2)" stroke-width="2" stroke-linecap="round"/>'
                   f'<circle cx="{x(r["delta"]):.1f}" cy="{y}" r="6.5" class="dot accent" data-tip="{e(tip)}"><title>{e(tip)}</title></circle>'
                   f'<text x="{right + 18}" y="{y + 4}" class="t-ink" font-size="12">{fmt(r["ours"])}</text>'
                   f'<text x="{right + 82}" y="{y + 4}" class="t-muted" font-size="12">{fmt(r["published"])}</text>')
    out.append(f'<text x="{right + 18}" y="{top - 16}" class="t-muted" font-size="10">ours</text>'
               f'<text x="{right + 82}" y="{top - 16}" class="t-muted" font-size="10">published</text></svg>')
    return "".join(out)


def _forest_compact(rows: list, span: float, width: int = 400) -> str:
    row_h, top, left, right = 84, 36, 14, width - 14
    height = top + row_h * len(rows) + 30

    def x(v):
        return left + (v + span) / (2 * span) * (right - left)

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Calibration: this repo against published values">']
    for t in (-4, -2, 0, 2, 4):
        cls = "axis" if t == 0 else "grid"
        out.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top - 6}" y2="{height - 26}" class="{cls}"/>'
                   f'<text x="{x(t):.1f}" y="{height - 8}" text-anchor="middle" class="t-muted" font-size="14">{t:+d}</text>')
    out.append(f'<text x="{x(0):.1f}" y="{top - 14}" text-anchor="middle" class="t-muted" font-size="14">published value</text>')
    for i, r in enumerate(rows):
        y0 = top + i * row_h
        lo, hi = max(-span, r["delta"] - r["ci"]), min(span, r["delta"] + r["ci"])
        fmt = (lambda v: f"{v:.2f}") if r["scale"] == 1 else (lambda v: f"{v / 100:.4f}")
        tip = f'{r["bench"]} · {r["what"]}\nours {fmt(r["ours"])} ± {fmt(r["ci"])}\npublished {fmt(r["published"])}\nn = {r["n"]}'
        yb = y0 + 38
        out.append(f'<text x="0" y="{y0 + 16}" class="t-ink" font-size="16">{e(r["bench"])} <tspan class="t-muted" font-size="14">{e(r["what"])}</tspan></text>'
                   f'<text x="0" y="{y0 + 66}" class="t-muted" font-size="14">ours <tspan class="t-ink">{fmt(r["ours"])}</tspan> · published {fmt(r["published"])}</text>'
                   f'<line x1="{x(lo):.1f}" x2="{x(hi):.1f}" y1="{yb}" y2="{yb}" stroke="var(--ink-2)" stroke-width="2" stroke-linecap="round"/>'
                   f'<circle cx="{x(r["delta"]):.1f}" cy="{yb}" r="7" class="dot accent" data-tip="{e(tip)}"><title>{e(tip)}</title></circle>')
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

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Local summarisers on CNN and on DailyMail">',
           f'<text x="{x0}" y="20" text-anchor="middle" class="t-muted" font-size="{fs}">CNN slice</text>',
           f'<text x="{x1}" y="20" text-anchor="middle" class="t-muted" font-size="{fs}">DailyMail slice</text>',
           f'<line x1="{x0}" x2="{x0}" y1="{top - 8}" y2="{bottom + 8}" class="axis"/>',
           f'<line x1="{x1}" x2="{x1}" y1="{top - 8}" y2="{bottom + 8}" class="axis"/>']
    # Ties share one label ("bart_l, bart_m"); then labels are spread so none overlap.
    groups: dict = {}
    for r in rows:
        groups.setdefault(round(r["dm"], 4), []).append(r["arm"])
    right = _spread([(v, y(v)) for v in groups], 20)
    left = _spread([(r["arm"], y(r["cnn"])) for r in rows], 18)
    for v, names in groups.items():
        out.append(f'<text x="{x1 + 16}" y="{right[v] + 5:.1f}" class="t-ink" font-size="{fs}">{e(", ".join(names))} {v:.3f}</text>')
    for r in rows:
        out.append(f'<text x="{x0 - 16}" y="{left[r["arm"]] + 5:.1f}" text-anchor="end" class="t-muted" font-size="{fs - 1}">{r["cnn"]:.3f}</text>')
    for r in rows:
        k = "baseline" if r["arm"] == "lead3" else "local"
        dash = ' stroke-dasharray="5 5"' if r["arm"] == "bart_l_xsum" else ""
        tip = f'{r["arm"]}\ncoverage {r["cnn"]:.4f} on CNN → {r["dm"]:.4f} on DailyMail'
        out.append(f'<line x1="{x0}" y1="{y(r["cnn"]):.1f}" x2="{x1}" y2="{y(r["dm"]):.1f}" class="s-{k}" stroke-width="2"{dash}/>'
                   f'<circle cx="{x0}" cy="{y(r["cnn"]):.1f}" r="5.5" class="dot k-{k}" data-tip="{e(tip)}"><title>{e(tip)}</title></circle>'
                   f'<circle cx="{x1}" cy="{y(r["dm"]):.1f}" r="6" class="dot k-{k}" data-tip="{e(tip)}"><title>{e(tip)}</title></circle>')
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

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{e(exp["bench"])}: cost against quality">']
    for p in range(clo, chi + 1):
        out.append(f'<line x1="{x(10 ** p):.1f}" x2="{x(10 ** p):.1f}" y1="{top}" y2="{bottom}" class="grid"/>'
                   f'<text x="{x(10 ** p):.1f}" y="{floor_y + 22}" text-anchor="middle" class="t-muted" font-size="{tick}">${10 ** p:g}</text>')
    for t in (lo + pad, (lo + hi) / 2, hi - pad):
        out.append(f'<line x1="{lane - 30}" x2="{right}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="grid"/>'
                   f'<text x="{lane - 36}" y="{y(t) + 4:.1f}" text-anchor="end" class="t-muted" font-size="{tick}">{t:.3f}</text>')
    out.append(f'<text x="{(left + right) / 2:.0f}" y="{height - 6}" text-anchor="middle" class="t-muted" font-size="{fs}">{"cost per 1,000 items (log)" if compact else "billed cost per 1,000 items (log scale)"}</text>'
               f'<text x="0" y="{top - 10}" class="t-muted" font-size="{fs}">↑ {e(exp["metric_label"])}</text>'
               f'<text x="{lane + 6}" y="{floor_y + 22}" text-anchor="middle" class="t-muted" font-size="{tick}">free</text>'
               f'<line x1="{left - 30}" x2="{left - 30}" y1="{top}" y2="{bottom}" class="axis"/>')
    if off:
        out.append(f'<text x="{left - 30}" y="{(bottom + floor_y) / 2 + 5:.1f}" text-anchor="middle" class="t-muted" font-size="{fs + 2}">⫽</text>')
    for a in free:
        k = kind_of(a)
        tip = f'{a["arm"]} · {KIND_LABEL[k]}\n{exp["metric_label"]} {a["score"]:.4f} · $0' + ("\noff the scale: far below the field" if a in off else "")
        out.append(dot(lane + 6, y(a["score"]), 6, k, tip))
    for a in paid:
        k = kind_of(a)
        tip = f'{a["arm"]} · {KIND_LABEL[k]}\n{exp["metric_label"]} {a["score"]:.4f}\n{money(per_k(a))} per 1,000 items' + ("\noff the scale: far below the field" if a in off else "")
        out.append(dot(x(per_k(a)), y(a["score"]), 6, k, tip))
    # Both labels sit centred above their dots; if they would overlap, the dearest's drops
    # below its ring.
    d, t = exp["dearest"], exp["top"]
    dl, tl = f'{d["arm"]} · dearest', f'{t["arm"]} · 1st'
    w = lambda s: len(s) * fs * 0.62  # noqa: E731 -- monospace advance, roughly
    dx = min(max(x(per_k(d)), lane + w(dl) / 2), right - w(dl) / 2)
    tx = lane + 6 if t["cost"] <= 0 else x(per_k(t))
    tx = min(max(tx, w(tl) / 2), right - w(tl) / 2)
    dy, ty = y(d["score"]) - 18, y(t["score"]) - 14
    if t["arm"] != d["arm"] and abs(dy - ty) < fs + 4 and abs(dx - tx) < (w(dl) + w(tl)) / 2 + 8:
        dy = y(d["score"]) + 11 + fs + 4
    out.append(f'<circle cx="{x(per_k(d)):.1f}" cy="{y(d["score"]):.1f}" r="11" class="ring"/>'
               f'<text x="{dx:.1f}" y="{dy:.1f}" text-anchor="middle" class="t-ink" font-size="{fs}">{e(dl)}</text>')
    if t["arm"] != d["arm"]:
        out.append(f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle" class="t-ink" font-size="{fs}">{e(tl)}</text>')
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
    ("https://www.devwhateverops.com/", "devwhateverops", "DevWhateverOps", "A manifesto for engineers who build end to end"),
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
        for url, tgt, name, line in FAMILY)
    elsewhere = "".join(
        f'<a href="{e(url)}" data-umami-event="outbound" data-umami-event-target="{tgt}" '
        f'rel="noopener me">{e(label)}</a>' for url, tgt, label in ELSEWHERE)
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
  <div class="foot-legal"><span>© Marko Dragoljevic · eval-harness · <a href="{up}docs/DATA/">Data &amp; licences</a></span><span>Cookieless, self-hosted analytics. No cookies, no tracking across sites.</span></div>
</div></footer>"""


def out(url: str, place: str, label: str, cls: str = "") -> str:
    """An outbound link to one of the author's sites, tagged for both analytics."""
    site = "humancopilot" if "humancopilot" in url else "devwhateverops"
    href = f"{url}?utm_source=eval-harness&utm_medium=site&utm_campaign=launch&utm_content={place}"
    c = f' class="{cls}"' if cls else ""
    return (f'<a href="{e(href)}"{c} data-umami-event="outbound-{site}" '
            f'data-umami-event-placement="{place}" rel="noopener">{label}</a>')


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


def page(title: str, desc: str, body: str, depth: int = 0, here: str = "",
         card: str = "social.png") -> str:
    up = "../" * depth

    def nav(key: str, href: str, label: str, cls: str = "") -> str:
        cur = ' aria-current="page"' if key == here else ""
        c = f' class="{cls}"' if cls else ""
        return f'<a href="{href}"{c}{cur}>{label}</a>'
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
  <nav class="nav">{nav("harness", f"{up}index.html", "Harness")}{nav("use", f"{up}use.html", "Use it")}{nav("method", f"{up}method.html", "Method", "hide-sm")}{nav("experiments", f"{up}experiments.html", "Experiments")}<a href="{up}docs/" class="hide-sm">Docs</a><a href="{REPO}" class="hide-sm">GitHub ↗</a><button id="theme" class="theme" aria-label="Toggle light and dark">◐</button></nav>
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
H = types.SimpleNamespace(q=q, e=e, page=page, times=times, money=money, word=word, REPO=REPO,
                          author=author)


# ── the landing page ────────────────────────────────────────────────────────
SYN = "research/REPORT_SYNTHESIS.md"
JUDGE = "research/REPORT_SUMMEVAL.md"


def home(f: dict) -> str:
    """The front door: the harness -- what it is, what it asks, how to start -- and then
    what it found when pointed at 24 LLMs, which is the reason to believe it."""
    exps = f["experiments"]
    ties = sum(x["n_tied"] > 0 for x in exps)
    cal_n, cal_ok = len(f["calibration"]), f["calibration_consistent"]
    cal_in = f["calibration_inside"]
    hosted_n = max(x["n_hosted"] for x in exps)
    ideas = [
        ("01", "A frozen dataset",
         "Items are hashed and every run records the hash. Change the data and you get a "
         "different id — not a silently different number."),
        ("02", "A fingerprint per run",
         "The model behind the alias, the prompt, the scoring code, library versions, the "
         "commit. So \u201cwe changed one thing\u201d is checkable, not asserted."),
        ("03", "A leaderboard that argues with itself",
         "Before it prints an order it tests every pair at once — a Friedman permutation test "
         "and a Nemenyi critical difference — and says plainly when nothing is distinguishable."),
        ("04", "Re-scoring for $0",
         "Scores are recomputed from stored outputs. Checking a metric should never cost "
         "another sweep of paid calls."),
    ]
    idea_html = "".join(
        f'<div class="habit-card"><span class="n">{n}</span><b>{e(t)}</b><span>{e(d)}</span></div>'
        for n, t, d in ideas)
    # Why it exists: the questions it was built to answer, each with what the harness gives
    # and what the experiments found -- numbers computed, quoted prose checked by q().
    why = [
        ("Agentic AI can do months of work in days. How do I trust what it builds?",
         "Frozen data, a fingerprint on every run, refusals when a comparison is unsound — so "
         "an agent can iterate at full speed without a regression slipping through as progress.",
         f"This project was built that way, with AI agents. A checker re-verifies "
         f"{f['claims_checked']} claims against the runs on every commit, and the lab notebook "
         "keeps every finding that had to be retracted along the way.",
         f"{REPO}/tree/main/research/internal", "The lab notebook"),
        ("Which model is best for what I need — not for someone else's benchmark?",
         "Run five, ten or twenty-four models on your own frozen data and see quality, cost and "
         "latency side by side, with a test that says whether the ranking is real.",
         f"The most expensive model was not the best in {f['dearest_never_best']} of "
         f"{len(exps)} experiments (five times the same model), and in {ties} of {len(exps)} "
         "the leader could not be separated from a group of others — at 100–280 items, which "
         "is not the same as equal.",
         "experiments.html", "The experiments"),
        ("Do I need an LLM — or a GPU — at all?",
         "Put a small classic model, or a plain baseline, in the same comparison as the LLMs: "
         "same data, same scoring, same test.",
         f"A free model that needs no GPU was first, or not separable from first, in "
         f"{f['local_first_or_tied']} of {len(exps)}, against LLMs run with one prompt and no "
         "examples; the clearest wins were on text like the text it was trained on. On judging "
         "summaries even a free model trained for the task lost, and the LLM earned its bill: "
         + q("judging summaries, the best LLM judges reach 93% of a human expert's agreement "
             "(the best of 24, on the same articles), and UniEval, the best free scorer, 64%.", JUDGE)
         + " One task, so the direction, not the size.",
         "experiments.html#experiments", "Per experiment"),
        ("Own it or rent it?",
         "Every cost is read off the provider's bill and set beside quality, so renting an API "
         "can be weighed against running open weights on hardware you own.",
         q("A proprietary model never separated from the best open-weight model in any of the "
           "six experiments", SYN) + ", and on four of the six tasks the best model that fits a "
         "64 GB machine scored the same as the unlimited-hardware answer — two of them at int8 "
         "or int4 precision, which was not measured, and as the providers served them: nothing "
         "was run on a 64 GB machine.",
         f"{BLOB}/research/REPORT_SYNTHESIS.md", "The synthesis"),
    ]
    why_html = "".join(
        f'<div class="why-q reveal"><span class="n">{i:02d}</span><h3>{e(qn)}</h3>'
        f'<p><b>The harness</b>{e(gives)}</p><p><b>What it found</b>{found}</p>'
        f'<a href="{href}">{e(label)} →</a></div>'
        for i, (qn, gives, found, href, label) in enumerate(why, 1))
    cards = "".join(
        f'<a class="card reveal" href="experiments/{x["slug"]}.html"><div class="task">{e(x["task"])}</div>'
        f'<h3>{e(x["bench"])}</h3><p>{e(CARD[x["slug"]])}</p>'
        f'<div class="meta"><span>{x["n_items"]} items · {x["n_arms"]} systems</span><span>1st <b>{e(x["top"]["arm"])}</b></span></div></a>'
        for x in exps)
    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>eval-harness</b> · open source · MIT · by {out(HUMAN, "hero", "Marko Dragoljevic", "byline")}</div>
  <h1>Is the ranking real, or <em>a lucky sample?</em></h1>
  <p class="dek">A small, drop-in harness for evaluating AI systems on your own data. Freeze a dataset, run your system against it, and get the answer most leaderboards skip: whether one system is actually better than another, or only ahead on this sample.</p>
  <div class="btns"><a class="btn primary" href="use.html">Use it on your problem</a><a class="btn" href="experiments.html">See it on {hosted_n} LLMs</a><a class="btn" href="{REPO}">GitHub ↗</a></div>
</div></section>

<section class="block" id="why"><div class="wrap">
  <div class="eyebrow"><span class="num">01</span>Why it exists</div>
  <h2>Four questions anyone building with AI ends up asking.</h2>
  <p class="lede">There are dozens of models, a leaderboard for each, and none of them measured on your problem. This harness exists to answer these on your own data — and the experiments are what it answered when pointed at 24 LLMs.</p>
  <div class="why">{why_html}</div>
</div></section>

<section class="block" id="what"><div class="wrap">
  <div class="eyebrow"><span class="num">02</span>What it does</div>
  <h2>Four ideas, one adapter file.</h2>
  <p class="lede">Most eval code answers \u201cwhich scored highest\u201d. That is the easy half; the hard half is whether the answer survives being asked again. The harness imports nothing domain-specific — everything about your system lives in one file, <code>adapter.py</code>, with four functions.</p>
  <div class="habits">{idea_html}</div>
  <div class="cols" style="margin-top:48px">
    <div class="prose"><h3 style="font-size:28px;line-height:1.15;margin-bottom:16px">Try the whole loop in a minute.</h3><p>The demo runs on bundled synthetic data — no API key, no network. It freezes a dataset, runs an arm three times and checks the record; <code>make leaderboard</code> then shows the ranking and whether it is real.</p>
      <div class="btns"><a class="btn primary" href="docs/GUIDE/">Your first evaluation — the guide</a></div></div>
<pre class="term"><span class="p">$ </span>git clone {REPO}
<span class="p">$ </span>cd eval-harness/harness
<span class="p">$ </span>make install
<span class="p">$ </span>make demo
<span class="p">$ </span>make leaderboard
<span class="c"># then, on your own system</span>
<span class="p">$ </span>make dataset-create DATASET_ID=my_v1
<span class="p">$ </span>make experiment-run CONFIG=data/configs/arm_a.yaml
<span class="p">$ </span>make leaderboard DATASET_ID=my_v1</pre>
  </div>
</div></section>

<section class="block" id="proof"><div class="wrap">
  <div class="eyebrow"><span class="num">03</span>Pointed at {hosted_n} LLMs</div>
  <h2>The most expensive model <em style="font-style:normal;color:var(--accent)">never won.</em></h2>
  <p class="lede">To show the harness doing something real, it measured {hosted_n} hosted LLMs, proprietary and open-weight from small to frontier tiers, small fine-tuned models and baselines on {word(len(exps))} public benchmarks — {f["total_arms"]} runs, {money(f["total_billed"])} billed, every cost read off the provider's bill.</p>
  <div class="stats">
    <div class="stat"><div class="n">{f["dearest_never_best"]}<small>/{len(exps)}</small></div><div class="l">experiments where the dearest model was not the best (five times the same model)</div></div>
    <div class="stat"><div class="n">{ties}<small>/{len(exps)}</small></div><div class="l">leaderboards where the leader cannot be separated from others (at 100–280 items)</div></div>
    <div class="stat"><div class="n">$0</div><div class="l">for a model that is first, or not separable from first, in {f["local_first_or_tied"]} of the {len(exps)}</div></div>
    <div class="stat"><div class="n">{cal_ok}<small>/{cal_n}</small></div><div class="l">calibration checks that agree with the published numbers, {cal_in} inside their own interval</div></div>
  </div>
  <div class="cards" style="margin-top:48px">{cards}</div>
  <div class="btns"><a class="btn primary" href="experiments.html">All the findings</a><a class="btn" href="experiments.html#reproduce">Reproduce them</a></div>
</div></section>

{method.landing_teaser(H, f, "04")}
<section class="block"><div class="wrap">
  <p class="note"><b>No figure on this site is typed in by hand.</b> Every figure is recomputed from the committed runs each time the site is built, and every number the prose quotes must appear in the report it comes from, or the build fails. Behind the reports, a checker verifies {f["claims_checked"]} claims against the runs on every commit.</p>
</div></section>
{author("home")}"""
    return page("eval-harness — is the ranking real, or a lucky sample?",
                "A drop-in harness for evaluating AI systems on your own data: frozen datasets, "
                "fingerprinted runs, and significance tests before any leaderboard is printed — "
                f"shown on 24 LLMs across {word(len(exps))} benchmarks.", body, here="harness",
                card="social-home.png")


def landing(f: dict) -> str:
    exps = f["experiments"]
    by = {x["slug"]: x for x in exps}
    ties = sum(x["n_tied"] > 0 for x in exps)
    cal_n, cal_ok = len(f["calibration"]), f["calibration_consistent"]
    cal_in = f["calibration_inside"]
    hosted_n = max(x["n_hosted"] for x in exps)
    local_n = sum(x["n_arms"] - x["n_hosted"] for x in exps)
    billed_all = f'{f["total_billed"]:.2f}'

    strips = "".join(f'<figure class="reveal" style="margin-bottom:10px">{both(strip(x), strip(x, compact=True))}</figure>' for x in exps)
    tie_rows = "".join(
        f'<tr><td class="exp"><a href="experiments/{x["slug"]}.html">{e(x["task"])} · {e(x["bench"])}</a></td>'
        f'<td class="num" data-label="first place">{e(x["top"]["arm"])}</td>'
        f'<td class="num big" data-label="tied with 1st">{x["n_tied"]}</td>'
        f'<td class="num" data-label="…of which paid">{x["n_tied_paid"]}</td>'
        f'<td class="num" data-label="cheapest paid tie">{e(x["cheapest_tied"]["arm"]) if x["cheapest_tied"] else "—"}</td>'
        f'<td class="num" data-label="cheaper than dearest">{times(x["tied_ratio"]) if x["tied_ratio"] else "no paid model ties"}</td>'
        f'<td class="num" data-label="dearest model">{e(x["dearest"]["arm"])} · {ordinal(x["dearest"]["rank"])} of {x["n_arms"]}</td></tr>'
        for x in exps)
    cards = "".join(
        f'<a class="card reveal" href="experiments/{x["slug"]}.html"><div class="task">{e(x["task"])}</div>'
        f'<h3>{e(x["bench"])}</h3><p>{e(CARD[x["slug"]])}</p>'
        f'<div class="meta"><span>{x["n_items"]} items · {x["n_arms"]} arms</span><span>1st <b>{e(x["top"]["arm"])}</b></span></div></a>'
        for x in exps)
    s = by["summarization"]
    hw_rows = "".join(
        f'<tr><td class="exp">{e(m["name"])}</td><td data-label="what it is">{e(m["summary"])}</td>'
        f'<td class="num" data-label="committed runs">'
        + (f'{m["local"] + m["hosted"]} ({m["local"]} local, {m["hosted"]} hosted)' if m["local"] + m["hosted"] else "none")
        + f'</td><td data-label="role">{e(m["role"])}</td></tr>'
        for m in f["hardware"])
    hw_date = json.loads((ROOT / "docs" / "evidence" / "hardware.json").read_text())["captured"]
    require(sum(m["local"] + m["hosted"] for m in f["hardware"]) == f["total_arms"],
            "every measured run is attributed to a documented machine")
    dear_x = max(exps, key=lambda x: x["dearest"]["cost"])
    dear = dear_x["dearest"]
    n_exp = word(len(exps))
    behind_cheaper = sum(any(a["cost"] < x["dearest"]["cost"] and a["rank"] < x["dearest"]["rank"]
                             for a in x["arms"]) for x in exps)
    behind_free = sum(any(a["kind"] != "hosted" and a["rank"] < x["dearest"]["rank"]
                          for a in x["arms"]) for x in exps)
    in_all = "all " + n_exp if behind_cheaper == len(exps) else f"{word(behind_cheaper)} of {n_exp}"

    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>The experiments</b> · {len(exps)} tasks · {f["total_arms"]} measured runs · {money(f["total_billed"])} billed</div>
  <h1>The most expensive model <em>never won.</em></h1>
  <p class="dek">{hosted_n} hosted LLMs, proprietary and open-weight from small to frontier tiers, small fine-tuned models and the baselines they have to beat, run through {n_exp} public benchmarks. Every comparison is tested for significance, every cost is read off the provider's bill, and the instrument itself is checked against the published literature.</p>
  <div class="stats">
    <div class="stat"><div class="n">{f["dearest_never_best"]}<small>/{len(exps)}</small></div><div class="l">experiments where the dearest model was not the best (five times the same model)</div></div>
    <div class="stat"><div class="n">{ties}<small>/{len(exps)}</small></div><div class="l">leaderboards where the leader cannot be separated from others (at 100–280 items)</div></div>
    <div class="stat"><div class="n">$0</div><div class="l">for a model that is first, or not separable from first, in {f["local_first_or_tied"]} of the {len(exps)}</div></div>
    <div class="stat"><div class="n">{cal_ok}<small>/{cal_n}</small></div><div class="l">calibration checks that agree with the published numbers, {cal_in} inside their own interval</div></div>
  </div>
</div></section>

<section class="block" id="findings"><div class="wrap">
  <div class="eyebrow"><span class="num">01</span>Price</div>
  <h2>The dearest model was never the best.</h2>
  <p class="lede">Each row is one benchmark; each dot is one system, placed by its score. The ringed dot is the most expensive hosted model. <strong>In {in_all} it finished behind something cheaper</strong> — and in {word(behind_free)}, behind something free.</p>
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
    <div class="chart scroll-x reveal"><table class="data ties">
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
    <li><div><h3>On one task, even a free model trained for it lost, and an LLM earned its bill — but not the dearest one.</h3><p>{q("Judging summaries, scored against the mean of two experts as one expert is against the other two, the best judges reach 93% of a human's agreement (the best of 24, on the same articles); UniEval, the best free scorer and an evaluator trained for the task, reaches 64%.", JUDGE)} {q("The cheapest judge in the top tie, gemma_l, has open weights and bills $278 per million articles — 1/23 of the leader.", JUDGE)} One task and one trained evaluator, and why it lost is not tested: the direction, not the size.</p></div></li>
    <li><div><h3>And part of a fine-tune's lead is learning the dataset's own conventions.</h3><p>{q("On AG News, the lead of the three fine-tunes is concentrated in 17 items the hosted field mostly gets wrong — about half a learnable convention, half mislabels.", "research/REPORT_CLASSIFICATION.md")} {q("On Few-NERD, 57% of the winner's margin over openai_m is one entity type the prompt never defined (30–57% across the hosted arms).", "research/REPORT_NER.md")} The leaders are better at the benchmark; how much of that is better at the task is a separate question, measured in each report.</p></div></li>
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
</div></section>

<section class="block" id="experiments"><div class="wrap">
  <div class="eyebrow"><span class="num">05</span>The experiments</div>
  <h2>{n_exp.capitalize()} benchmarks, one harness.</h2>
  <p class="lede">The same {hosted_n} hosted models — eight vendors, three price tiers each — on every task (the cheapest twelve on SciFact), beside the strongest free models each task allows.</p>
  <div class="cards">{cards}</div>
</div></section>

<section class="block" id="reproduce"><div class="wrap">
  <div class="eyebrow"><span class="num">06</span>Reproduce it</div>
  <h2>Built to be checked — by you.</h2>
  <p class="lede">The harness, every run, every model output and every analysis script are in the repository. Five levels of checking, each optional, each a few commands.</p>
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
      <p class="note" style="margin-top:32px">Reviewed in adversarial rounds, every correction kept: the <a href="{REPO}/tree/main/research/internal">lab notebook</a> records what was wrong, how it was found, and what changed.</p>
    </div>
  </div>
</div></section>
<section class="block" id="hardware"><div class="wrap">
  <div class="eyebrow"><span class="num">07</span>The hardware</div>
  <h2>Where the runs were made.</h2>
  <p class="lede">Every run on this site records the machine it ran on; the counts below are read from those records, and each machine's description from the machine itself. Most of it is a 2018 Mac mini. No open-weight LLM was run on any of these machines for these results: the "own it" figures elsewhere are provider-served scores, set against what would fit a given memory budget.</p>
  <div class="chart scroll-x reveal"><table class="data">
    <thead><tr><th>machine</th><th>what it is</th><th>runs on this site it measured</th><th>role</th></tr></thead>
    <tbody>{hw_rows}</tbody></table>
    <figcaption>Hosted runs are API calls made from that machine; the model ran at the provider. Local runs ran on the machine's own CPU. The DGX Spark and the MacBook measured none of these runs. Captured {hw_date}: <a href="{BLOB}/docs/evidence/hardware.json">docs/evidence/hardware.json</a>.</figcaption></div>
</div></section>
{author("experiments")}"""
    return page("The most expensive model never won — eval-harness",
                f"24 LLMs, small fine-tuned models and baselines on {n_exp} public benchmarks, "
                "with significance tests, billed costs and calibration against the literature.", body, here="experiments")


CARD = {
    "summarization": "Summarise a news article in two or three sentences. A 1.6 GB fine-tune is not separated from the best paid model (0.0001 apart) — on CNN's articles.",
    "ag-news": "Four-way topic labels. Three small fine-tunes lead on the point estimate, LLMs as run here; the lead is concentrated in 17 items the hosted field mostly gets wrong.",
    "dbpedia": "Fourteen-way ontology labels on a saturated benchmark: the leader cannot be separated from nineteen others (1 to 8 items behind), and the gold label is sometimes in dispute.",
    "few-nerd": "Find and type entities in a sentence. The only clean winner in the repo: a fine-tuned tagger, separated from every rival.",
    "scifact": "Retrieve the abstracts that support a scientific claim. An LLM reranker leads, tied with twelve others; two of them are free retrievers.",
    "summeval": "Grade machine summaries the way experts do. The best LLM judges reach 93% of a human expert's agreement (best of 24, same articles), far ahead of a free evaluator trained for the task (64%), and an open-weight judge ties the leader.",
}


# ── experiment pages ────────────────────────────────────────────────────────
def require(cond: bool, claim: str) -> None:
    """A structural claim written into the copy must hold in the data, or the build stops."""
    if not cond:
        raise SystemExit(f"site copy claims something the data no longer supports: {claim}")


def findings_for(x: dict, f: dict) -> list:
    rep = f'research/{x["report"]}'
    d, t, b = x["dearest"], x["top"], x["best_hosted"]
    s = x["slug"]
    require(s != "summarization" or (t["arm"] == "bart_l" and b["arm"] in x["tied"]),
            "summarisation: bart_l first and tied with the best hosted arm")
    require(s != "ag-news" or all(a["kind"] == "local" for a in x["arms"][:3]),
            "AG News: the top three are local fine-tunes")
    require(s != "dbpedia" or ("bert_base_fy" in x["tied"] and x["n_tied"] == 19),
            "DBpedia: the leader plus nineteen others, including the fine-tune")
    require(s != "few-nerd" or x["n_tied"] == 0, "Few-NERD: span_marker separated from all")
    require(s != "scifact" or ("e5_base" in x["tied"] and x["n_tied"] == 12),
            "SciFact: twelve tied, including e5_base")
    require(s != "summeval" or sum(a["rank"] < min(b["rank"] for b in x["arms"] if b["kind"] != "hosted")
                                   for a in x["arms"] if a["kind"] == "hosted") == 23,
            "SummEval: 23 of the 24 hosted judges rank above every free arm")
    require(s != "summeval" or (x["cheapest_tied"] and x["cheapest_tied"]["weights"] == "open"),
            "SummEval: the cheapest judge tied with the leader has open weights")
    common = [(f"The dearest model finished {ordinal(d['rank'])} of {x['n_arms']}.",
               f"{d['arm']} billed {money(d['cost'])} for {x['n_items']} items. "
               + (f"The cheapest model not separated from the leader, {x['cheapest_tied']['arm']}, cost {times(x['tied_ratio'])} less."
                  if x["cheapest_tied"] else "No paid model is not separated from the leader: the leader is separated from every one."))]
    if x["slug"] == "summarization":
        dm = {r["arm"]: r for r in f["dailymail"]}
        return [
            ("A 1.6 GB model fine-tuned on this corpus is not separated from the best paid model.",
             f"bart_l scores {t['score']:.4f} on coverage, {b['arm']} {b['score']:.4f} — "
             + q("a gap of 0.0001.", rep) + f" It cannot be separated from {x['n_tied']} of the other {x['n_arms'] - 1} arms."),
            *common,
            ("The same architecture trained on another corpus finishes last.",
             q("BART fine-tuned on XSum's one-sentence BBC summaries scores 0.2071 — 29th of 29, below lead-3.", rep)
             + " bart_l's lead is consistent with learning CNN's house style; the XSum control also decodes shorter, so it does not isolate style."),
            ("The winner depends on the metric.",
             q("On ROUGE-2 the three CNN-trained BARTs take the top three places; on ROUGE-1 the LLMs lead and bart_l is 12th.", rep)),
            ("Scope: these are CNN's articles.",
             f"All 200 come from CNN's 9% of the test set. On 200 DailyMail articles the five local models kept every verdict "
             f"(bart_l {dm['bart_l']['dm']:.4f}, lead-3 {dm['lead3']['dm']:.4f}); the paid models were not re-run."),
        ]
    if x["slug"] == "ag-news":
        return [
            ("Three small fine-tuned classifiers lead on the point estimate; only the first is separated from all but one paid arm.",
             f"bert_base_ta leads at {t['score']:.4f}; the best hosted model, {b['arm']}, scores {b['score']:.4f}."),
            *common,
            ("The lead is concentrated in 17 items the hosted field mostly gets wrong.",
             q("17 items are labelled against the judgement of most of the hosted field — business news about technology companies filed as Sci/Tech, Olympic results filed as World. The fine-tunes agree with the gold on most of them.", rep)
             + " " + q("On the other 183 items the order reverses — anthropic_l 0.984, bert_base_ta 0.973 — though that cut is selected by the hosted arms' own errors and so flatters them.", rep)),
        ]
    if x["slug"] == "dbpedia":
        return [
            ("No winner: the leader and nineteen others.",
             f"{t['arm']} leads at {t['score']:.4f}, not separated from {x['n_tied']} others, including the free fine-tune."),
            *common,
            ("The benchmark is saturated, and the gold is sometimes wrong.",
             q("Three items are disputed by 24 to 25 of 26 arms, and reading them, the gold label is the error.", rep)),
        ]
    if x["slug"] == "few-nerd":
        return [
            ("The only unambiguous winner in the repo.",
             f"span_marker, fine-tuned on Few-NERD's training split, scores {t['score']:.4f} and is separated from all {x['n_arms'] - 1} other arms."),
            *common,
            ("But its margin is partly the corpus's own conventions.",
             q("Against openai_m, 57% of its margin is one entity type, other, which the prompt never defined (30–57% across the hosted arms), and up to 38% of its lead is agreement with annotation the rest of the field rejects.", rep)),
        ]
    if x["slug"] == "scifact":
        return [
            ("LLM rerankers lead — and cannot be separated from eleven or twelve others.",
             f"{t['arm']} reranking BM25's top 20 scores {t['score']:.4f} nDCG@10; {x['n_tied']} arms cannot be separated from it, including the free retrievers e5_base and bge_small."),
            *common,
            ("The dev slice picked the wrong winner.",
             q("Tuned on a 40-query dev slice, the leaderboard's winner there was not the winner on the 160 queries it never saw.", rep)),
        ]
    if x["slug"] == "summeval":
        free = [a for a in x["arms"] if a["kind"] != "hosted"]
        best_free = min(free, key=lambda a: a["rank"])
        weakest = max((a for a in x["arms"] if a["kind"] == "hosted"), key=lambda a: a["rank"])
        ct = x["cheapest_tied"]
        return [
            ("On mean τ, 23 of 24 LLM judges beat a free evaluator trained for the task.",
             f"The best free scorer, {best_free['arm']} (UniEval, on its own inputs), scores "
             f"{best_free['score']:.4f}; the weakest judge, {weakest['arm']}, {weakest['score']:.4f}. "
             + q("In the paired test UniEval is separated below 23 of the 24 judges and cannot "
                 "be separated from the weakest, on either set of inputs.", rep)),
            ("An open-weight judge ties the leader.",
             f"{ct['arm']} scores {ct['score']:.4f} against {t['arm']}'s {t['score']:.4f}, and "
             f"the leader cannot be separated from it or from {x['n_tied'] - 1} others. "
             + q("No provider was pinned: one judge, run once on each of two providers, scored 0.0113 apart and billed 3.7× apart.", rep)),
            *common,
            ("The best judges come close to a single expert, and stay below one.",
             q("Scored against the mean of two experts, as one expert is against the other two, "
               "the best judge reaches 0.5195 — 93% of one expert's 0.5587 (95% interval 89–97%), "
               "and the gap excludes zero. It is the best of 24, chosen on the same articles. "
               "UniEval reaches 64%, BARTScore 44%.", rep)),
            ("The order is stable; the winner is not.",
             q("Two disjoint 20-article halves agree at ρ = 0.90 on the order of the 24 judges, "
               "but name the same unique winner only 21% of the time.", rep)),
            ("This repository's own metric agrees with experts less than ROUGE does.",
             q("coverage agrees with the experts at τ 0.1011, below ROUGE-1's 0.1487.", rep)),
        ]
    return common


def experiment_page(x: dict, f: dict) -> str:
    cal = [r for r in f["calibration"] if r["bench"] == x["bench"]]
    cal_txt = "; ".join(f'{r["what"]} {r["ours"] / r["scale"]:.4f} vs {r["published"] / r["scale"]:.4f} published'
                        if r["scale"] == 100 else f'{r["what"]} {r["ours"]:.2f} vs {r["published"]:.2f} published'
                        for r in cal)
    facts = [
        ("Question", QUESTION[x["slug"]]),
        ("Data", f'{x["n_items"]} items from the {x["bench"]} test split'),
        ("Systems", f'{x["n_arms"]} compared: {x["n_hosted"]} hosted models billed per call; {x["n_arms"] - x["n_hosted"]} local models and baselines, free'),
        ("Metric", f'{x["metric_label"]}' + METRIC_GLOSS.get(x["slug"], " — the field's standard; higher is better")),
        ("Calibration", cal_txt or "—"),
        ("Billed", f'{money(x["billed_total"])} for the whole sweep'),
    ]
    facts_html = "".join(f'<div class="fact"><div class="k">{e(k)}</div><div class="v">{e(v)}</div></div>' for k, v in facts)
    finds = "".join(f'<li><div><h3>{e(h)}</h3><p>{e(p)}</p></div></li>' for h, p in findings_for(x, f))
    free = x["n_arms"] - x["n_hosted"]
    lesson = method.experiment_lesson(H, x)
    extra = ""
    if x["slug"] == "summarization":
        extra = f"""<section class="block" id="dailymail"><div class="wrap"><div class="eyebrow"><span class="num">04</span>Outside CNN</div>
<h2>Does it hold on DailyMail?</h2><div class="cols"><div class="prose"><p>The committed sample is all CNN. On 200 DailyMail articles drawn at random, the five local summarisers keep every verdict among themselves. The hosted models were not re-run there.</p></div>
<figure class="chart">{both(slope(f["dailymail"]), slope(f["dailymail"], compact=True))}</figure></div></div></section>"""
    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>{e(x["task"])}</b> · {e(x["bench"])}</div>
  <h1 style="max-width:16ch">{e(HEADLINE[x["slug"]])}</h1>
  <p class="dek">{e(CARD[x["slug"]])}</p>
  <div class="facts">{facts_html}</div>
  <div class="btns"><a class="btn primary" href="{BLOB}/research/{x["report"]}">Read the full report</a><a class="btn" href="{BLOB}/docs/PROTOCOL.md">Protocol</a><a class="btn" href="../experiments.html#experiments">All experiments</a></div>
</div></section>
<section class="block" id="field"><div class="wrap"><div class="eyebrow"><span class="num">01</span>The field</div>
  <h2>Every system, one axis.</h2>
  <div class="chart">{legend(reading="higher score: further right →", baseline=False)}{both(strip(x, title=False, height=80), strip(x, title=False, compact=True))}<figcaption>Each dot is one system, by {e(x["metric_label"])}. The ringed dot is the most expensive hosted model; the shaded band is the group the leader cannot be statistically separated from.{OFF_NOTE if off_scale([a for a in x["arms"] if a["kind"] != "baseline"])[1] else ""}</figcaption></div>
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
<section class="block" id="habit"><div class="wrap"><div class="eyebrow"><span class="num">{"05" if extra else "04"}</span>The method, here</div>
  <div class="lesson"><h2>{e(lesson[1])}</h2><p>{lesson[2]}</p><a class="btn" href="../method.html#{lesson[0]}">This habit, in the method →</a></div>
</div></section>
<section class="block" id="reproduce"><div class="wrap"><div class="eyebrow"><span class="num">{"06" if extra else "05"}</span>Reproduce it</div>
  <h2>Check it yourself.</h2>
  <div class="cols">
    <div class="prose">
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
    return page(f'{x["task"]} · {x["bench"]} — eval-harness', CARD[x["slug"]], body, depth=1, here="experiments")


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
HEADLINE = {
    "summarization": "A free model level with the best paid one — on CNN's news.",
    "ag-news": "Small models lead, largely on disputed labels.",
    "dbpedia": "Twenty-way tie at the top.",
    "few-nerd": "The one clean win.",
    "scifact": "Rerankers lead a crowd.",
    "summeval": "On mean τ, 23 of 24 LLM judges beat a trained free evaluator.",
}


# ── build ───────────────────────────────────────────────────────────────────
def build(out: Path) -> None:
    f = figures.compute()
    if out.exists():
        shutil.rmtree(out)
    (out / "experiments").mkdir(parents=True)
    shutil.copytree(HERE / "assets", out / "assets")
    (out / "index.html").write_text(home(f), encoding="utf-8")
    (out / "experiments.html").write_text(landing(f), encoding="utf-8")
    (out / "method.html").write_text(method.method_page(H, f), encoding="utf-8")
    (out / "use.html").write_text(method.use_page(H, f), encoding="utf-8")
    for x in f["experiments"]:
        (out / "experiments" / f'{x["slug"]}.html').write_text(experiment_page(x, f), encoding="utf-8")
    (out / ".nojekyll").write_text("")


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
        build(fresh)
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
    print("ok    site/public matches a fresh build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
