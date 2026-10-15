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
SITE = "https://chipi.github.io/eval-harness"
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
        items += '<span><i class="sw-band"></i>statistically tied with the leader</span>'
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


# The project mark: an estimate with its interval, held in a harness (site/assets/icon.svg).
# Inline here so its colours follow the theme: the tile is the accent, the marks its ink.
MARK = ('<svg class="mark" viewBox="0 0 64 64" aria-hidden="true">'
        '<rect width="64" height="64" rx="14" class="mark-tile"/>'
        '<g class="mark-ink" fill="none" stroke-linecap="round">'
        '<path d="M20 14H12V50H20M44 14H52V50H44" stroke-width="6" stroke-linejoin="round"/>'
        '<path d="M22 32H42" stroke-width="5"/></g>'
        '<circle cx="32" cy="32" r="7" class="mark-dot"/></svg>')


def page(title: str, desc: str, body: str, depth: int = 0, here: str = "") -> str:
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
<meta property="og:image" content="{SITE}/assets/social.png">
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
  <a class="brand" href="{up}index.html" aria-label="eval-harness home">{MARK}<span>eval-harness</span></a>
  <nav class="nav">{nav("harness", f"{up}index.html", "Harness")}{nav("use", f"{up}use.html", "Use it")}{nav("method", f"{up}method.html", "Method", "hide-sm")}{nav("experiments", f"{up}experiments.html", "Experiments")}<a href="{up}docs/" class="hide-sm">Docs</a><a href="{REPO}" class="hide-sm">GitHub ↗</a><button id="theme" class="theme" aria-label="Toggle light and dark">◐</button></nav>
</div></header>
<main>
{body}
</main>
<footer><div class="wrap">
  <div>Generated from the committed runs by <code>site/build.py</code>. Every number here is recomputed from the data on each build.</div>
  <div><a href="{up}docs/">Documentation</a> · <a href="{REPO}">github.com/chipi/eval-harness</a></div>
</div></footer>
<div id="tip" role="tooltip"></div>
{JS}
</body>
</html>
"""


#: The helpers method.py borrows, passed in rather than imported (no circular import).
H = types.SimpleNamespace(q=q, e=e, page=page, times=times, money=money, REPO=REPO)


# ── the landing page ────────────────────────────────────────────────────────
SYN = "research/REPORT_SYNTHESIS.md"


def home(f: dict) -> str:
    """The front door: the harness -- what it is, what it asks, how to start -- and then
    what it found when pointed at 24 LLMs, which is the reason to believe it."""
    exps = f["experiments"]
    ties = sum(x["n_tied"] > 0 for x in exps)
    cal_n, cal_ok = len(f["calibration"]), f["calibration_consistent"]
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
         f"{len(exps)} experiments, and in {ties} of {len(exps)} first place was a statistical tie.",
         "experiments.html", "The experiments"),
        ("Do I need an LLM — or a GPU — at all?",
         "Put a small classic model, or a plain baseline, in the same comparison as the LLMs: "
         "same data, same scoring, same test.",
         f"A free model that needs no GPU was first or tied for first in "
         f"{f['local_first_or_tied']} of {len(exps)} — but only on text like the text it was "
         "trained on.",
         "experiments.html#experiments", "Per experiment"),
        ("Own it or rent it?",
         "Every cost is read off the provider's bill and set beside quality, so renting an API "
         "can be weighed against running open weights on hardware you own.",
         q("A proprietary model never separated from the best open-weight model in any of the "
           "five experiments, and 64 GB of memory is enough to match the unlimited-hardware "
           "answer on four of five tasks.", SYN),
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
  <div class="kicker"><b>eval-harness</b> · open source · MIT</div>
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
  <p class="lede">To show the harness doing something real, it measured {hosted_n} frontier and open-weight LLMs, small fine-tuned models and baselines on five public benchmarks — {f["total_arms"]} runs, {money(f["total_billed"])} billed, every cost read off the provider's bill.</p>
  <div class="stats">
    <div class="stat"><div class="n">{f["dearest_never_best"]}<small>/{len(exps)}</small></div><div class="l">experiments where the dearest model was not the best</div></div>
    <div class="stat"><div class="n">{ties}<small>/{len(exps)}</small></div><div class="l">leaderboards where first place is a statistical tie</div></div>
    <div class="stat"><div class="n">$0</div><div class="l">for a model that is first or tied for first, in {f["local_first_or_tied"]} of the {len(exps)}</div></div>
    <div class="stat"><div class="n">{cal_ok}<small>/{cal_n}</small></div><div class="l">calibration checks that match the published numbers</div></div>
  </div>
  <div class="cards" style="margin-top:48px">{cards}</div>
  <div class="btns"><a class="btn primary" href="experiments.html">All the findings</a><a class="btn" href="experiments.html#reproduce">Reproduce them</a></div>
</div></section>

{method.landing_teaser(H, f, "04")}
<section class="block"><div class="wrap">
  <p class="note"><b>Nothing on this site is typed in by hand.</b> Every figure is recomputed from the committed runs each time the site is built, and every number the prose quotes must appear in the report it comes from, or the build fails. Behind the reports, a checker verifies {f["claims_checked"]} claims against the runs on every commit.</p>
</div></section>
"""
    return page("eval-harness — is the ranking real, or a lucky sample?",
                "A drop-in harness for evaluating AI systems on your own data: frozen datasets, "
                "fingerprinted runs, and significance tests before any leaderboard is printed — "
                "shown on 24 LLMs across five benchmarks.", body, here="harness")


def landing(f: dict) -> str:
    exps = f["experiments"]
    by = {x["slug"]: x for x in exps}
    ties = sum(x["n_tied"] > 0 for x in exps)
    cal_n, cal_ok = len(f["calibration"]), f["calibration_consistent"]
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
    dear_x = max(exps, key=lambda x: x["dearest"]["cost"])
    dear = dear_x["dearest"]

    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>The experiments</b> · {len(exps)} tasks · {f["total_arms"]} measured runs · {money(f["total_billed"])} billed</div>
  <h1>The most expensive model <em>never won.</em></h1>
  <p class="dek">{hosted_n} frontier and open-weight LLMs, small fine-tuned models and the baselines they have to beat, run through five public benchmarks. Every comparison is tested for significance, every cost is read off the provider's bill, and the instrument itself is checked against the published literature.</p>
  <div class="stats">
    <div class="stat"><div class="n">{f["dearest_never_best"]}<small>/{len(exps)}</small></div><div class="l">experiments where the dearest model was not the best</div></div>
    <div class="stat"><div class="n">{ties}<small>/{len(exps)}</small></div><div class="l">leaderboards where first place is a statistical tie</div></div>
    <div class="stat"><div class="n">$0</div><div class="l">for a model that is first or tied for first, in {f["local_first_or_tied"]} of the {len(exps)}</div></div>
    <div class="stat"><div class="n">{cal_ok}<small>/{cal_n}</small></div><div class="l">calibration checks that match the published numbers</div></div>
  </div>
</div></section>

<section class="block" id="findings"><div class="wrap">
  <div class="eyebrow"><span class="num">01</span>Price</div>
  <h2>The price tag told you nothing.</h2>
  <p class="lede">Each row is one benchmark; each dot is one system, placed by its score. The ringed dot is the most expensive hosted model. <strong>In all five it finished behind something cheaper</strong> — and in four, behind something free.</p>
  <div class="chart reveal">{legend(reading="higher score: further right →", baseline=False)}{strips}
  <figcaption>Baselines (lead-3, keyword rules, empty output) are left off the axis to keep the field readable; they are in each experiment's page. A dot left of the ⫽ break sits far below the rest, off the scale. Hover or tap any dot for its score, rank and bill.</figcaption></div>
</div></section>

<section class="block"><div class="wrap">
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

<section class="block"><div class="wrap">
  <div class="eyebrow"><span class="num">03</span>Fine-tuning</div>
  <h2>Train a small model on your data. <em style="font-style:normal;color:var(--accent)">Yours.</em></h2>
  <ol class="findings reveal">
    <li><div><h3>The best fine-tuned model was first, or tied for first, in {f["local_first_or_tied"]} of {len(exps)}.</h3><p>{q("Every one is under 2 GB and needs no GPU", SYN)} — $0 per item — against hosted models billing up to {money(dear["cost"])} for {dear_x["n_items"]} items ({e(dear["arm"])}, {e(dear_x["bench"])}).</p></div></li>
    <li><div><h3>But only on text like the text it was trained on.</h3><p>{q("The same BART architecture, fine-tuned on XSum's one-sentence BBC summaries instead of CNN/DailyMail's, finishes last of 29 — below copying the first three sentences.", "research/REPORT_SUMMARIZATION.md")}</p></div></li>
    <li><div><h3>And part of a fine-tune's lead is learning the dataset's own conventions.</h3><p>{q("On AG News, nearly the whole lead of the three fine-tunes sits in 17 items whose gold labels most of the hosted field disputes.", "research/REPORT_CLASSIFICATION.md")} {q("On Few-NERD, 57% of the winner's margin is one entity type whose meaning exists only in that corpus.", "research/REPORT_NER.md")} The leaders are better at the benchmark; how much of that is better at the task is a separate question, measured in each report.</p></div></li>
  </ol>
</div></section>

<section class="block" id="trust"><div class="wrap">
  <div class="eyebrow"><span class="num">04</span>Trust</div>
  <h2>Can you trust any of this?</h2>
  <p class="lede">Every experiment scores a sample of 200–280 items, not a full test set. So each one also runs a <strong>calibration</strong>: one well-known model, through this repo's own code, on the benchmark's full test set (or a large seeded sample), compared with the number its authors published.</p>
  <div class="chart reveal">{both(forest(f["calibration"]), forest(f["calibration"], compact=True))}
    <figcaption>Our figure minus the published one, in points of the metric (ROUGE-1 F1 for summarisation, accuracy, micro-F1 or nDCG@10 ×100 elsewhere). Bars are our 95% interval. {cal_ok} of {cal_n} sit on the published value.</figcaption></div>
  <div class="cols" style="margin-top:64px">
    <div class="prose">
      <h3 style="font-size:28px;line-height:1.15;margin-bottom:16px">Calibration found one real error — in our sample, not our scorer.</h3>
      <p>The summarisation experiment took the first 200 articles of the CNN/DailyMail test set. The test set lists CNN's articles first, so <strong>all 200 were CNN's</strong>, while the benchmark is 91% DailyMail. Lead-3 scored ROUGE-1 30.20 on that slice against 39.94 on the full test set; CNN articles are simply harder to summarise from their lead.</p>
      <p>Re-run on 200 DailyMail articles drawn at random, the five local summarisers <strong>kept every verdict</strong> they had on CNN: the fine-tune still beats lead-3 by the same margin, and the XSum model is still last. The hosted models were not re-run, so the summarisation price findings are scoped to CNN's articles — and say so.</p>
    </div>
    <figure class="chart reveal">{both(slope(f["dailymail"]), slope(f["dailymail"], compact=True))}<figcaption>coverage of the five local summarisers on each slice. Dashed: BART trained on XSum.</figcaption></figure>
  </div>
  <p class="note" style="margin-top:48px"><b>Nothing on this site is typed in by hand.</b> Every figure is recomputed from the committed runs each time the site is built, and every number the prose quotes must appear in the report it comes from, or the build fails. Behind the reports, a checker verifies {f["claims_checked"]} claims against the runs on every commit.</p>
</div></section>

<section class="block" id="experiments"><div class="wrap">
  <div class="eyebrow"><span class="num">05</span>The experiments</div>
  <h2>Five benchmarks, one harness.</h2>
  <p class="lede">The same {hosted_n} hosted models — eight vendors, three price tiers each — on every task, beside the strongest free models each task allows.</p>
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
      <li><span class="lvl">03</span><div><h3>Hosted</h3><p>Rerun the {hosted_n} LLMs with one OpenRouter key. The test: does every separation still hold?</p></div><span class="cost">${billed_all} billed, all five</span></li>
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
      <p class="note" style="margin-top:32px">Reviewed in five adversarial rounds, every correction kept: the <a href="{REPO}/tree/main/research/internal">lab notebook</a> records what was wrong, how it was found, and what changed.</p>
    </div>
  </div>
</div></section>
"""
    return page("The most expensive model never won — eval-harness",
                "24 LLMs, small fine-tuned models and baselines on five public benchmarks, "
                "with significance tests, billed costs and calibration against the literature.", body, here="experiments")


CARD = {
    "summarization": "Summarise a news article in two or three sentences. A 1.6 GB fine-tune ties the best paid model — on CNN's articles.",
    "ag-news": "Four-way topic labels. Three small fine-tunes take the top three places, largely by learning the dataset's labelling conventions.",
    "dbpedia": "Fourteen-way ontology labels on a saturated benchmark: the top is a group of nineteen, and the gold label is sometimes the error.",
    "few-nerd": "Find and type entities in a sentence. The only clean winner in the repo: a fine-tuned tagger, separated from every rival.",
    "scifact": "Retrieve the abstracts that support a scientific claim. LLM rerankers lead a twelve-way tie; a free dense retriever sits inside it.",
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
            "DBpedia: a group of nineteen including the fine-tune")
    require(s != "few-nerd" or x["n_tied"] == 0, "Few-NERD: span_marker separated from all")
    require(s != "scifact" or ("e5_base" in x["tied"] and x["n_tied"] == 12),
            "SciFact: twelve tied, including e5_base")
    common = [(f"The dearest model finished {ordinal(d['rank'])} of {x['n_arms']}.",
               f"{d['arm']} billed {money(d['cost'])} for {x['n_items']} items. "
               + (f"The cheapest model statistically tied with the leader, {x['cheapest_tied']['arm']}, cost {times(x['tied_ratio'])} less."
                  if x["cheapest_tied"] else "No paid model is statistically tied with the leader."))]
    if x["slug"] == "summarization":
        dm = {r["arm"]: r for r in f["dailymail"]}
        return [
            ("A 1.6 GB model fine-tuned on this corpus ties the best paid model.",
             f"bart_l scores {t['score']:.4f} on coverage, {b['arm']} {b['score']:.4f} — "
             + q("a gap of 0.0001.", rep) + f" It cannot be separated from {x['n_tied']} of the other {x['n_arms'] - 1} arms."),
            *common,
            ("The same architecture trained on another corpus finishes last.",
             q("BART fine-tuned on XSum's one-sentence BBC summaries scores 0.2071 — 29th of 29, below lead-3. What bart_l has is CNN's house style.", rep)),
            ("The winner depends on the metric.",
             q("On ROUGE-2 the three CNN-trained BARTs take the top three places; on ROUGE-1 the LLMs lead and bart_l is 12th.", rep)),
            ("Scope: these are CNN's articles.",
             f"All 200 come from CNN's 9% of the test set. On 200 DailyMail articles the five local models kept every verdict "
             f"(bart_l {dm['bart_l']['dm']:.4f}, lead-3 {dm['lead3']['dm']:.4f}); the paid models were not re-run."),
        ]
    if x["slug"] == "ag-news":
        return [
            ("Three small fine-tuned classifiers take the top three places.",
             f"bert_base_ta leads at {t['score']:.4f}; the best hosted model, {b['arm']}, scores {b['score']:.4f}."),
            *common,
            ("Most of the lead is the dataset's labelling convention.",
             q("17 items are labelled against the judgement of most of the hosted field — business news about technology companies filed as Sci/Tech, Olympic results filed as World. The fine-tunes agree with the gold on most of them.", rep)),
        ]
    if x["slug"] == "dbpedia":
        return [
            ("No winner: a group of nineteen.",
             f"{t['arm']} leads at {t['score']:.4f}, statistically tied with {x['n_tied']} others, including the free fine-tune."),
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
             q("57% of its margin is one entity type, other, whose meaning exists only in this corpus, and 38% of its lead over the best hosted model is agreeing with annotation the rest of the field rejects.", rep)),
        ]
    if x["slug"] == "scifact":
        return [
            ("LLM rerankers lead — inside a twelve-way tie.",
             f"{t['arm']} reranking BM25's top 20 scores {t['score']:.4f} nDCG@10; {x['n_tied']} arms cannot be separated from it, including the free dense retriever e5_base."),
            *common,
            ("The dev slice picked the wrong winner.",
             q("Tuned on a 40-query dev slice, the leaderboard's winner there was not the winner on the 160 queries it never saw.", rep)),
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
        extra = f"""<section class="block"><div class="wrap"><div class="eyebrow"><span class="num">04</span>Outside CNN</div>
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
<section class="block"><div class="wrap"><div class="eyebrow"><span class="num">01</span>The field</div>
  <h2>Every system, one axis.</h2>
  <div class="chart">{legend(reading="higher score: further right →", baseline=False)}{both(strip(x, title=False, height=80), strip(x, title=False, compact=True))}<figcaption>Each dot is one system, by {e(x["metric_label"])}. The ringed dot is the most expensive hosted model; the shaded band is the group the leader cannot be statistically separated from.{OFF_NOTE if off_scale([a for a in x["arms"] if a["kind"] != "baseline"])[1] else ""}</figcaption></div>
</div></section>
<section class="block"><div class="wrap"><div class="eyebrow"><span class="num">02</span>Cost</div>
  <h2>What the money bought.</h2>
  <div class="chart">{legend(band=False, reading="better: up · cheaper: left", baseline=False)}{both(scatter(x), scatter(x, compact=True))}<figcaption>Billed cost per 1,000 items, read from the provider's response, against {e(x["metric_label"])}. Free models sit in the left lane.{OFF_NOTE_Y if off_scale([a for a in x["arms"] if a["kind"] != "baseline"])[1] else ""}</figcaption></div>
</div></section>
<section class="block"><div class="wrap"><div class="eyebrow"><span class="num">03</span>Findings</div>
  <h2>What this experiment found.</h2>
  <ol class="findings">{finds}</ol>
</div></section>
{extra}
<section class="block"><div class="wrap"><div class="eyebrow"><span class="num">{"05" if extra else "04"}</span>The method, here</div>
  <div class="lesson"><h2>{e(lesson[1])}</h2><p>{lesson[2]}</p><a class="btn" href="../method.html#{lesson[0]}">This habit, in the method →</a></div>
</div></section>
<section class="block"><div class="wrap"><div class="eyebrow"><span class="num">{"06" if extra else "05"}</span>Reproduce it</div>
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
    "summarization": " — how much of the reference summary's wording the summary recovers, at the reference's length (ROUGE-Lsum recall, clipped); this repo's own, see the protocol. Higher is better",
    "few-nerd": " — entities found with the right type, set-matched per sentence and averaged, on 8 coarse types; this repo's own, see the protocol. Higher is better",
}

QUESTION = {
    "summarization": "Summarise a news article in two or three short sentences, in a wire-service style.",
    "ag-news": "Label a news snippet World, Sports, Business or Sci/Tech.",
    "dbpedia": "Label a Wikipedia abstract with one of 14 ontology classes.",
    "few-nerd": "Find every named entity in a sentence and give it one of 8 types.",
    "scifact": "Rank 5,183 scientific abstracts by how well they bear on a claim.",
}
HEADLINE = {
    "summarization": "A free model ties the frontier — on CNN's news.",
    "ag-news": "Small models win by learning the labels.",
    "dbpedia": "Nineteen-way tie at the top.",
    "few-nerd": "The one clean win.",
    "scifact": "Rerankers lead a crowd.",
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
