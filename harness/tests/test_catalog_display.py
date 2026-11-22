#!/usr/bin/env python3
"""How the catalog's numbers and charts read (scenario 080d review): $0, offline, no project.

    python tests/test_catalog_display.py

The drawing rules, each as a check on the SVG a chart returns:
- no number drawn over another, no label cut off (a label is whole, or wrapped at a separator, or its tooltip carries it);
- a value that is the same everywhere gets an axis that says it is the same, not a +-0.5 axis;
- a ratio for a person is never scientific notation; a cost has one format; a latency one precision;
- an id breaks at a separator (_ / - .) with a <wbr>, never inside a word.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation_harness import axes
from evaluation_harness import catalog_charts as cc
from evaluation_harness._check import check, summary
from evaluation_harness.model import goal_views

NS = "{http://www.w3.org/2000/svg}"


def svg_of(html: str) -> ET.Element:
    m = re.search(r"<svg.*?</svg>", html, re.S)
    assert m
    return ET.fromstring(m.group(0).replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1))  # noqa: S314  # nosec B314


def boxes(svg: ET.Element) -> list[tuple[float, float, float, float, str]]:
    """(x0, x1, y0, y1, text) of every unrotated text, a character being LABEL_W wide: where it is drawn."""
    out = []
    for t in svg.iter(NS + "text"):
        if t.get("transform"):
            continue
        spans = list(t.iter(NS + "tspan")) or [t]
        for s in spans:
            txt = "".join(x for x in s.itertext() if x and not x.startswith("\n"))
            title = s.find(NS + "title")
            if title is not None:
                txt = txt.replace(title.text or "", "", 1)
            if not txt.strip():
                continue
            x, y = float(s.get("x") or t.get("x") or 0), float(s.get("y") or t.get("y") or 0)
            w = cc.LABEL_W * len(txt)
            anchor = t.get("text-anchor", "start")
            x0 = x - w if anchor == "end" else x - w / 2 if anchor == "middle" else x
            out.append((x0, x0 + w, y - 11, y + 3, txt))
    return out


def overlaps(bs: list) -> list:
    return [
        (a[4], b[4])
        for i, a in enumerate(bs)
        for b in bs[i + 1 :]
        if a[0] < b[1] - 0.5 and b[0] < a[1] - 0.5 and a[2] < b[3] - 0.5 and b[2] < a[3] - 0.5
    ]


def cut(svg: ET.Element) -> list:
    vb = [float(v) for v in svg.get("viewBox", "").split()]
    return [b[4] for b in boxes(svg) if b[0] < vb[0] - 0.5 or b[1] > vb[0] + vb[2] + 0.5 or b[2] < -0.5]


def alltext(html: str) -> str:
    return re.sub(r"<[^>]+>", "", re.sub(r"<title>.*?</title>", "", html, flags=re.S))


# -- one cost format, one latency precision, ratios for people --------------------------------------------------------
costs = [0, 0.0, 1.5e-7, 0.000018, 0.0027, 0.1992, 1.0, 12.345]
got = [axes.fmt_usd(v) for v in costs]
check(
    "cost: zero is $0, a tiny cost keeps two significant digits, the rest four places under a dollar, two above",
    got == ["$0", "$0", "$0.00000015", "$0.000018", "$0.0027", "$0.1992", "$1.00", "$12.35"],
    got,
)
lat = [0.0035, 0.004, 0.0085, 0.0095, 0.03, 1.234, 12.5, 118.4, 1988.0, 2222.6, 3882.7]
got = [axes.fmt_ms(v) for v in lat]
check(
    "latency: three significant digits to the hundred (the same count of digits in 0.00400 and 0.00850), whole above",
    got
    == [
        "0.00350",
        "0.00400",
        "0.00850",
        "0.00950",
        "0.0300",
        "1.23",
        "12.5",
        "118",
        "1,988",
        "2,223",
        "3,883",
    ],
    got,
)
check(
    "latency: the p50/p95 text and the single-value text use the same precision",
    axes.cell_text(
        {"name": "speed", "measure": "latency_ms", "stat": "p95"}, {"n": 3, "p50": 0.006, "p95": 0.0095}
    )
    == "p50 0.00600 · p95 0.00950 ms"
    and axes.value_text({"name": "speed", "measure": "latency_ms"}, 1988.0) == "1,988 ms",
    axes.cell_text(
        {"name": "speed", "measure": "latency_ms", "stat": "p95"}, {"n": 3, "p50": 0.006, "p95": 0.0095}
    ),
)
check(
    "cost: cell_text and value_text use the one cost format",
    axes.value_text({"name": "cost", "measure": "cost_usd"}, 0.0) == "$0"
    and axes.cell_text({"name": "cost", "measure": "cost_usd"}, {"mean": 0.0, "tokens": {"mean": 106}})
    == "$0 · 106 tok",
    axes.cell_text({"name": "cost", "measure": "cost_usd"}, {"mean": 0.0, "tokens": {"mean": 106}}),
)
r = [goal_views.ratio_text(x) for x in (0, 2.7e-06, 0.004, 0.0123, 0.35, 0.999, 1.0, 2.5, 9.99, 10.4, 209.0)]
check(
    "ratios: never scientific notation; under a hundredth says so; zero is 0×",
    r == ["0×", "<0.01×", "<0.01×", "0.012×", "0.35×", "1×", "1×", "2.5×", "10×", "10×", "209×"]
    and not any("e" in x.replace("×", "") for x in r),
    r,
)

# -- ids break at a separator -----------------------------------------------------------------------------------------
import evaluation_harness.catalog_build as cb  # noqa: E402

b = cb.breakable("briefs_v1_validation/gold-set.v2")
check(
    "ids: <wbr> after every _ / - . and nowhere inside a word",
    b == "briefs_<wbr>v1_<wbr>validation/<wbr>gold-<wbr>set.<wbr>v2",
    b,
)
check(
    "ids: the arm, dataset, reference and metric links wrap by default",
    "<wbr>" in cb.arm_link("a/briefs_v1/briefs_lead1_v1", "briefs_lead1_v1")
    and "<wbr>" in cb.dataset_link("briefs_v1_validation")
    and "<wbr>" in cb.reference_link("gold/briefs_v1")
    and "<wbr>" in cb.metric_link("judge_score_unvalidated"),
    cb.metric_link("judge_score_unvalidated"),
)

# -- a heatmap's numbers: none over another, none cut ----------------------------------------------------------------
rows = ["lead_length-t1", "briefs_lead2_v1", "lead_length-t2"]
for n in (6, 11, 14, 24):
    cols = [f"b{i:02d}_item" for i in range(n)]
    cells = {
        (r_, c): {"value": 0.25 + 0.0123 * ((i * 7 + j * 3) % 50)}
        for i, r_ in enumerate(rows)
        for j, c in enumerate(cols)
    }
    h = cc.heatmap(rows, cols, cells, "x", 0.0, 1.0)
    s = svg_of(h)
    bs = boxes(s)
    nums = [b_ for b_ in bs if re.fullmatch(r"-?[0-9.]+", b_[4])]
    check(
        f"heatmap {n} columns: no number over another, none cut; a number drawn is the whole value",
        not overlaps(bs) and not cut(s) and all(len(b_[4]) >= 4 for b_ in nums),
        (overlaps(bs)[:3], cut(s)[:3]),
    )
    if n <= 11:
        check(
            f"heatmap {n} columns: the values are drawn (the cells grow to hold them)",
            len(nums) == len(rows) * n,
            len(nums),
        )
    # every cell's value stays readable as its tooltip, whether or not it is drawn
    check(
        f"heatmap {n} columns: every cell carries its value in a tooltip",
        h.count("<title>") >= len(rows) * n,
        h.count("<title>"),
    )
long = ["briefs_mistral_small_v1 ×3", "briefs_mistral_small_hot_v1", "briefs_opus_v1"]
h = cc.heatmap(
    long,
    ["b01_flood", "b02_bakery"],
    {(r_, c): {"value": 0.5} for r_ in long for c in ("b01_flood", "b02_bakery")},
    "x",
    0,
    1,
)
s = svg_of(h)
check(
    "heatmap: a long row label is whole, not shortened with an ellipsis",
    all(x in alltext(h) for x in long) and not cut(s),
    (alltext(h)[:200], cut(s)),
)

# -- a trend's x label is whole ---------------------------------------------------------------------------------------
t = cc.lines({"the baseline": [(1.0, 0.4)]}, "t", "in the order", "rouge_l", x_names={1.0: "v1 briefs_v1"})
s = svg_of(t)
check(
    "trend: a single point's x label 'v1 briefs_v1' is whole (wrapped at its space, never cut with an ellipsis)",
    "…" not in alltext(t) and "v1" in alltext(t) and "briefs_v1" in alltext(t) and not cut(s),
    alltext(t)[:200],
)
t = cc.lines(
    {"a": [(1.0, 0.4), (2.0, 0.5), (3.0, 0.6)]},
    "t",
    "x",
    "y",
    x_names={1.0: "v1 briefs_v1", 2.0: "r2", 3.0: "v2 briefs_v1_validation"},
)
check(
    "trend: three x labels, none over another, none cut",
    not overlaps(boxes(svg_of(t))) and not cut(svg_of(t)) and "…" not in alltext(t),
    (overlaps(boxes(svg_of(t))), alltext(t)[:200]),
)

# -- constant values: an axis that says so ----------------------------------------------------------------------------
st = cc.strip(
    {"gold/briefs_v1": [(0.5, "a"), (0.5, "b")], "silver/briefs_v1": [(0.5, "c")]}, "acc", lower=False
)
txt = alltext(st)
check(
    "strip: every value the same draws no -0.5 / 1.5 axis and says the value is the same everywhere",
    "-0.5" not in txt and "1.5" not in txt and "same" in txt.lower() and "0.5" in txt,
    txt,
)
st = cc.strip({"g": [(0.0, "a"), (0.0, "b")], "s": [(0.0, "c")]}, "cost", lower=True, fmt=axes.fmt_usd)
check(
    "strip: all zero says '$0' for everyone, not '-0.5 · better … 0.5'",
    "-0.5" not in alltext(st) and "$0" in alltext(st) and "same" in alltext(st).lower(),
    alltext(st),
)
q = cc.quadrant(
    [
        {"name": "t1", "x": 0.0, "y": 0.12, "ylo": 0.02, "yhi": 0.19, "filled": False},
        {"name": "t2", "x": 0.0, "y": -0.08, "ylo": -0.12, "yhi": -0.03, "filled": False},
    ],
    "gain",
    "difference in cost per item (USD)",
    "difference in rouge_l",
    fmt_x=axes.fmt_usd,
)
check(
    "quadrant: a flat cost axis is not a -0.62 … +0.62 axis; it says the cost is the same",
    "0.62" not in alltext(q) and "same" in alltext(q).lower(),
    alltext(q),
)
sc = cc.scatter(
    [(0.0, 0.5, "a", "a"), (0.001, 0.5, "b", "b"), (0.002, 0.5, "c", "c")], "cost", "acc", fmt_x=axes.fmt_usd
)
check(
    "scatter: a flat quality axis says it is the same, with its value, not a padded -0.5 … 1.5 range",
    "1.5" not in alltext(sc) and "-0.5" not in alltext(sc) and "same" in alltext(sc).lower(),
    alltext(sc),
)
check(
    "scatter: the two ends of a cost axis read differently ($0 and $0.000012, not $0.0000 twice)",
    not re.search(
        r"\$0\.0000(?!\d)",
        alltext(
            cc.scatter([(0.0, 0.9, "a", "a"), (0.000012, 0.8, "b", "b")], "cost", "acc", fmt_x=axes.fmt_usd)
        ),
    ),
    alltext(cc.scatter([(0.0, 0.9, "a", "a"), (0.000012, 0.8, "b", "b")], "cost", "acc", fmt_x=axes.fmt_usd)),
)

# -- a strip's row labels are whole -----------------------------------------------------------------------------------
names = ["gold/briefs_v1_validation", "silver/briefs_v1_validation", "judge briefs-judge-v1"]
st = cc.strip({n: [(0.1, "a"), (0.4, "b")] for n in names}, "m", lower=False)
check(
    "strip: a long row label (gold/briefs_v1_validation) is whole, wrapped at a separator, none cut",
    all(re.sub(r"\s+", "", n) in re.sub(r"\s+", "", alltext(st)) for n in names)
    and "…" not in alltext(st)
    and not cut(svg_of(st))
    and not overlaps(boxes(svg_of(st))),
    (alltext(st)[:300], cut(svg_of(st))),
)
st = cc.strip(
    {"a": [(0.0035, "x"), (2222.6, "y")]},
    "latency",
    lower=True,
    fmt=axes.fmt_ms,
)
check(
    "strip: the axis ends use the caller's format (one latency precision)",
    "0.00350" in alltext(st) and "2,223" in alltext(st),
    alltext(st),
)


# -- a scatter's frontier line never runs through a name, no name over another or cut ---------------------------------
def segs(s: ET.Element) -> list:
    out = []
    for p in s.iter(NS + "polyline"):
        pts = [tuple(float(v) for v in xy.split(",")) for xy in p.get("points", "").split()]
        out += list(zip(pts, pts[1:]))
    return out


def crosses(seg, box) -> bool:
    (ax, ay), (bx, by) = seg
    x0, x1, y0, y1, _ = box
    for k in range(101):
        x, y = ax + (bx - ax) * k / 100, ay + (by - ay) * k / 100
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    return False


pts = [
    (0.0, 3.475, "briefs_lead1_v1", "t"),
    (0.0001, 4.575, "briefs_mistral_small_v1", "t"),
    (0.0027, 4.975, "briefs_opus_v1", "t"),
]
sc = cc.scatter(pts, "cost (USD per item)", "judge_score", fmt_x=axes.fmt_usd, width=520)
s = svg_of(sc)
named = [b_ for b_ in boxes(s) if b_[4].startswith("briefs_")]
check(
    "scatter: the frontier line crosses no name; names do not overlap each other nor leave the chart",
    not [(sg, nb[4]) for sg in segs(s) for nb in named if crosses(sg, nb)]
    and not overlaps(boxes(s))
    and not cut(s),
    ([nb[4] for sg in segs(s) for nb in named if crosses(sg, nb)], overlaps(boxes(s)), cut(s)),
)
pts = [(0.0, 0.906, "intents_keywords_v1", "t"), (0.00003, 0.938, "intents_mistral_small_v1", "t")]
sc = cc.scatter(pts, "cost", "accuracy", fmt_x=axes.fmt_usd, width=520)
s = svg_of(sc)
named = [b_ for b_ in boxes(s) if b_[4].startswith("intents_")]
check(
    "scatter: two arms on the frontier are both named in full",
    len(named) == 2 and not cut(s) and not [1 for sg in segs(s) for nb in named if crosses(sg, nb)],
    (alltext(sc)[:200], cut(s)),
)

# -- arm pages: no reference, rounds of a re-read arm ----------------------------------------------------------------
a0 = {
    "arm": "runs/briefs_v2/briefs_lead1_v1",
    "metric": "rouge_l",
    "mean": None,
    "reference": None,
    "judge": None,
}
scored, head = cb.arm_reading(a0, "briefs_v2")
check(
    "arm page: an arm on a dataset with no reference says why there is no score, not a bare '—' and a metric alone",
    "no reference set" in scored and scored != "—" and "not scored" in head and "reference" in head,
    (scored, head),
)
scored, head = cb.arm_reading(dict(a0, reference="gold/briefs_v1", mean=0.4123), "briefs_v1")
check("arm page: a scored arm reads as before", "0.412" in head and "not scored" not in head, head)

from evaluation_harness import catalog_periods as cp  # noqa: E402

judged_arm = {
    "arm": "judged/sc/ds/a",
    "judge": "sc",
    "run_list": [{"created_at": "2026-11-18T10:00:00Z", "derived": "judge"}],
}
check(
    "periods: a judge's score exists only as its pass: a metric only a judge records counts that pass as a run",
    cp.runs_of([judged_arm], {"judged/sc/ds/a": 0}, judged=True) == [["2026-11-18", 0]]
    and cp.runs_of([judged_arm], {"judged/sc/ds/a": 0}) == [],
    cp.runs_of([judged_arm], {"judged/sc/ds/a": 0}, judged=True),
)


class Stub:
    item_word = "item"

    def __init__(self, rounds):
        self._rounds = rounds

    def rounds(self):
        return self._rounds

    def arms(self):
        return []

    def scores(self, arm):
        return {}


def stub(rounds: list) -> Any:
    """A stand-in adapter: only the rounds."""
    return Stub(rounds)


def rnd(rid, records, ds="briefs_v1", status="closed", arms=None):
    return {
        "round_id": rid,
        "goal": "g",
        "dataset_id": ds,
        "status": status,
        "arm_records": records,
        "arms": arms
        if arms is not None
        else [f"runs/{ds}/{r['system']}" for r in records if not r.get("retired")],
        "retired_arms": [f"runs/{ds}/{r['system']}" for r in records if r.get("retired")],
        "conclusion": {"text": "c"},
    }


R = [
    rnd(
        "r1",
        [
            {"system": "lead1", "entered": {"how": "ran"}},
            {"system": "t5", "entered": {"how": "ran"}, "retired": {}},
        ],
    ),
    rnd("r2", [{"system": "lead1", "entered": {"how": "carried"}, "retired": {"reason": "floor"}}]),
    rnd("r3", [{"system": "other", "entered": {"how": "ran"}}], ds="intents_v1"),
]
goals = {"g": {"goal_id": "g", "title": "G"}}
silver = {"arm": "silver/briefs_v1/lead1"}
gold = {"arm": "runs/briefs_v1/lead1"}
h_gold, h_silver = (
    cb.arm_rounds_html(stub(R), gold, "briefs_v1", goals),
    cb.arm_rounds_html(stub(R), silver, "briefs_v1", goals),
)
check(
    "arm page rounds: the gold arm lists the rounds that ran its system on its dataset (r1 in play, r2 retired), no other dataset's",
    "r1" in h_gold
    and "r2" in h_gold
    and "retired" in h_gold
    and "r3" not in h_gold
    and "scored another way" not in h_gold,
    h_gold,
)
check(
    "arm page rounds: the same system scored another way (silver) lists the same rounds and says it is read there another way",
    "r1" in h_silver and "r2" in h_silver and h_silver.count("scored another way") == 2,
    h_silver,
)
check(
    "arm page rounds: a system no round ran lists none",
    cb.arm_rounds_html(stub(R), {"arm": "runs/briefs_v1/zzz"}, "briefs_v1", goals) == "",
)

# -- a goal's rounds: the counts read (grammar, and they add up) -------------------------------------------------------
from unittest import mock  # noqa: E402

from evaluation_harness.model import rounds as model_rounds  # noqa: E402

R4 = rnd(
    "r4",
    [
        {"system": "lead1", "entered": {"how": "carried"}},
        {"system": "hot", "entered": {"how": "ran"}, "retired": {"reason": "no"}},
    ],
)
R2 = rnd(
    "r2",
    [
        {"system": "a", "entered": {"how": "carried"}},
        {"system": "b", "entered": {"how": "carried"}},
        {"system": "c", "entered": {"how": "ran"}},
        {"system": "d", "entered": {"how": "carried"}, "retired": {"reason": "floor"}},
    ],
)
with mock.patch.object(model_rounds, "evidence", return_value={}):
    block = cb._rounds_block(stub([R4, R2]), {"goal_id": "g"}, "rouge_l")
check(
    "rounds: '1 arm in play', never '1 arms'; the retired count beside it",
    "1 arm in play" in block and "1 arms" not in block and "3 arms in play" in block,
    re.findall(r"\d+ arms?[^<]*", block),
)
counts = re.findall(r'<small class="muted">([^<]*(?:retired|carried|ran)[^<]*)</small>', block)
check(
    "rounds: the counts line adds up to the arms the round stored (retired + carried + ran)",
    counts == ["1 retired · 1 carried", "1 retired · 2 carried · 1 ran in it"],
    counts,
)

from evaluation_harness import catalog_scorers as csc  # noqa: E402

h_, r_ = csc.without_empty_note(["a", "note"], [["x", ""], ["y", ""]])
h2, r2 = csc.without_empty_note(["a", "note"], [["x", ""], ["y", "<small>bad</small>"]])
check(
    "scorers: the note column is dropped when every row's is blank, kept when one has something to say",
    h_ == ["a"]
    and r_ == [["x"], ["y"]]
    and h2 == ["a", "note"]
    and r2 == [["x", ""], ["y", "<small>bad</small>"]],
    (h_, r_, h2),
)

# -- the answer card: where the rule recommends another arm than the baseline it says so, beside the baseline ------------
by_ds = {
    "briefs_v1": {
        "arms": [{"arm": "runs/briefs_v1/mistral", "label": "mistral"}],
        "baselines": [
            {
                "goal": "g",
                "arm": "runs/briefs_v1/mistral",
                "run": "r",
                "promoted_at": "2026-11-21T07:00:00Z",
                "reason": "why",
                "tier": "gold",
            }
        ],
    }
}
goal = {"goal_id": "g", "datasets": [{"dataset_id": "briefs_v1"}]}
answers = [{"dataset": "briefs_v1", "groups": [{"rows": [], "dec": {}, "measure": "rouge_l", "key": "gold"}]}]
with (
    mock.patch.object(cb, "decided", return_value=answers),
    mock.patch.object(cb, "_baseline_facts", return_value=""),
    mock.patch.object(cb, "_sheet_fold", return_value=""),
    mock.patch.object(
        cb,
        "baseline_gap",
        return_value="Differs from the promoted baseline, mistral: lead1 is +0.2 on rouge_l.",
    ),
):
    card = cb._answer(stub([]), goal, by_ds, "rouge_l")
with (
    mock.patch.object(cb, "decided", return_value=answers),
    mock.patch.object(cb, "_baseline_facts", return_value=""),
    mock.patch.object(cb, "_sheet_fold", return_value=""),
    mock.patch.object(cb, "baseline_gap", return_value=""),
):
    quiet = cb._answer(stub([]), goal, by_ds, "rouge_l")
check(
    "answer card: the baseline and the rule's different recommendation are said together, not a section apart",
    "recommendation differs from the baseline" in card and "lead1 is +0.2" in card and "differs" not in quiet,
    card[-400:],
)

sys.exit(summary())
