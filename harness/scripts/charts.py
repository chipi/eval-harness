"""The evidence charts (RFC-034): one function per kind, each answering what it draws (`rows`, with every number a
reader needs to check it, under `columns`), a title and a caption that say what the marks claim, and the drawing
(`svg`, made by catalog_charts). `evh chart`, the API's `/charts/{kind}`, the catalog's pages and the Workbench all
call `chart` here, so a picture and its table never disagree.

    gain-cost       a round's arms or a study's trials against their baseline: the difference in quality (better up,
                    with its interval) against the difference in cost per item (cheaper left); a filled mark only when
                    the difference is significant, the quadrant named only then
    intervals       a goal's arms against its leader on one dataset: each difference with its 95% interval, the
                    non-inferiority margin, the verdict in words
    study-progress  a study's trials in order, kept, dropped or neither, with the best so far from the baseline
    rank-stability  how often two disjoint halves of n items agree on the order, as n grows
    latency         every item's latency per arm, its p50 and p95 marked
    agreement       a dataset's label sets compared pairwise (a confusion matrix each), or a judge scorer's controls
    items           a goal's arms by items, coloured by score, the items where the arms disagree most first
    trend           a goal's baseline across its versions and its closed rounds; a code record's faithfulness per
                    deployed period

A chart with too little to draw refuses (`not-enough`) with the reason, never an empty frame.
"""

from __future__ import annotations

import contextlib
import statistics
from collections.abc import Iterator
from typing import Any

from evaluation_harness import catalog_charts as cc
from evaluation_harness.model.entity import Problem

KINDS = (
    "gain-cost",
    "intervals",
    "study-progress",
    "rank-stability",
    "latency",
    "agreement",
    "items",
    "trend",
)

#: The items a heat map shows: the ones where the arms disagree most (a table holds the rest).
ITEMS_SHOWN = 40


#: The adapter a catalog build reads through (`using`), else the one the server serves, else the project's.
_USING: list = []
#: A goal's leaderboard, kept while a catalog build draws several charts of it (`using`): it is the costly part.
_BOARDS: dict = {}


@contextlib.contextmanager
def using(A) -> Iterator[None]:
    """Draw from this adapter (and its data directory, a deployment's copy of the project's) while inside; a goal's
    leaderboard is computed once for all the charts drawn of it."""
    _USING.append(A)
    try:
        yield
    finally:
        _USING.pop()
        if not _USING:
            _BOARDS.clear()


def _adapter():
    if _USING:
        return _USING[-1]
    from evaluation_harness import catalog_serve  # noqa: PLC0415
    from evaluation_harness.catalog_adapter import shared_adapter  # noqa: PLC0415

    return getattr(catalog_serve, "A", None) or shared_adapter()


def _data():
    """The data directory the adapter reads (None: the project's)."""
    return getattr(_adapter(), "data_dir", None)


def _goal(A, goal: str) -> dict[str, Any]:
    g = next((x for x in A.goals() if x["goal_id"] == goal), None)
    if g is None:
        raise Problem(
            f"no goal {goal!r}: one of {', '.join(x['goal_id'] for x in A.goals()) or '(none)'}", "not-found"
        )
    return g


def _values(A, arm: str, metric: str) -> dict[str, float]:
    return dict((A.scores(arm).get(metric) or {}).get("values") or {})


def _mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def _shown(labels: dict) -> tuple[dict, str]:
    """Arms' labels as the goal page shows them (catalog_build.shown_labels): when most are read through one re-score,
    the scorer is named once (returned) and dropped from each arm's label."""
    from evaluation_harness.catalog_build import shown_labels  # noqa: PLC0415

    return shown_labels(labels)


def _through(scorer: str) -> str:
    """The caption's sentence naming the re-score the arms are read through, once."""
    return f" Every arm is read through the re-score by scorer {scorer}." if scorer else ""


def _label(A, arm: str) -> str:
    return str(A.describe(arm).get("label") or arm.rsplit("/", 1)[-1])


def _word(verdict: str | None) -> str:
    v = verdict or ""
    return {
        "significant: better": "better",
        "significant: worse": "worse",
        "not significant": "not separated",
        "identical": "identical",
        "untestable": "too few items",
    }.get(v, v)


def _out(
    kind: str, title: str, caption: str, columns: list[str], rows: list[dict], svg: str, **extra
) -> dict:
    if not svg:
        raise Problem(f"{kind}: nothing to draw ({caption})", "not-enough")
    return {
        "kind": kind,
        "title": title,
        "caption": caption,
        "columns": columns,
        "rows": rows,
        "svg": svg,
        **extra,
    }


# ── a goal's group ───────────────────────────────────────────────────────────
def _group(goal: str, dataset: str | None) -> dict[str, Any]:
    """The leaderboard group the goal decides on (on `dataset` when named): the first group of the first dataset that
    decides, else the first group."""
    from evaluation_harness.model import goal_views  # noqa: PLC0415

    A = _adapter()
    key = (id(A), goal)
    lb = _BOARDS.get(key) if _USING else None
    if lb is None:
        lb = goal_views.leaderboard(A, goal)
        if _USING:
            _BOARDS[key] = lb
    dss = [d for d in lb["datasets"] if not dataset or d["dataset"] == dataset]
    if not dss:
        raise Problem(f"goal {goal} has no arms on {dataset or 'any dataset'} yet", "not-enough")
    d = next((x for x in dss if x["decides"] and x["groups"]), None) or next(
        (x for x in dss if x["groups"]), None
    )
    if d is None:
        raise Problem(f"goal {goal} has no arms on {dataset or 'its datasets'} yet", "not-enough")
    grp = d["groups"][0]
    named, scorer = _shown({a["arm"]: a["label"] for a in grp["arms"]})
    return {**grp, "arms": [{**a, "label": named[a["arm"]]} for a in grp["arms"]], "scorer": scorer}


def intervals(goal: str, dataset: str | None = None) -> dict:
    """Each arm's difference from the leader with its interval; the margin when the goal decides by non-inferiority."""
    grp = _group(goal, dataset)
    flip = -1.0 if grp["direction"] == "lower" else 1.0
    rows, draw = [], []
    margin, against, base_row = None, "leader", None
    for a in grp["arms"]:
        vs = a.get("vs_leader") or {}
        ni = a.get("noninferior") or {}
        if ni.get("margin") is not None:
            margin, against = float(ni["margin"]), str(ni.get("against") or "leader")
        if a["leader"]:
            row = {
                "arm": a["label"],
                "difference": 0.0,
                "low": None,
                "high": None,
                "p": None,
                "verdict": "the leader",
            }
        elif vs.get("delta") is None:
            continue
        else:
            ci = vs.get("ci") or [None, None]
            lo, hi = (ci[0] * flip, ci[1] * flip) if ci[0] is not None else (None, None)
            row = {
                "arm": a["label"],
                "difference": vs["delta"] * flip,
                "low": min(lo, hi) if lo is not None else None,
                "high": max(lo, hi) if lo is not None else None,
                "p": vs.get("p"),
                "verdict": _word(vs.get("verdict")) + (", a contender" if a.get("contender") else ""),
            }
        rows.append(row)
        if a.get("baseline"):
            base_row = row
        draw.append(
            {
                "name": row["arm"],
                "est": row["difference"],
                "lo": row["low"],
                "hi": row["high"],
                # Filled is a significant difference, as the caption says; the leader is the zero it is measured from.
                "filled": not a["leader"] and str(vs.get("verdict") or "").startswith("significant"),
                "word": row["verdict"],
                "tip": f"{row['arm']}: {row['difference']:+.4g}"
                + (f", 95% interval {row['low']:.4g} to {row['high']:.4g}" if row["low"] is not None else "")
                + (f", p {row['p']:.4g}" if row["p"] is not None else "")
                + f" ({row['verdict']})",
            }
        )
    if len(rows) < 2:
        raise Problem(f"goal {goal}: one arm only on {grp['dataset']}: nothing to compare", "not-enough")
    # The margin is measured from the arm contenders are tested against: the leader (at 0), or the promoted baseline
    # (axes.quality.reference: baseline), at the baseline's own difference from the leader.
    margin_at, margin_said = None, ""
    if margin is not None and against == "baseline":
        b = base_row
        if b is not None:
            margin_at = b["difference"] - abs(margin)
            margin_said = (
                f" The dashed line is the margin a contender must stay within ({margin:.4g}), measured from the promoted "
                f"baseline {b['arm']}, which contenders are tested against."
            )
        else:
            margin_said = f" Contenders are tested against the promoted baseline, within {margin:.4g}; it is not drawn here."
    elif margin is not None:
        margin_at = -abs(margin)
        margin_said = (
            f" The dashed line is the margin a contender must stay within ({margin:.4g}), from the leader."
        )
    caption = (
        f"Each arm's mean difference from the leader on {grp['measure']} ({grp['dataset']}, against "
        f"{grp['scored_against']}), oriented so right is better. The line is its 95% interval from the paired test, "
        "before Holm's correction across the arms; the verdict is after it, so an interval clear of zero can still be "
        "not separated. A filled dot: a significant difference; the leader is the hollow dot at 0."
        + _through(grp["scorer"])
        + margin_said
    )
    svg = cc.forest(
        draw,
        f"{grp['measure']}: each arm against the leader",
        "difference from the leader (← worse · better →)",
        margin_at=margin_at,
        caption=cc._e(caption),
    )
    return _out(
        "intervals",
        f"{goal}: each arm against the leader",
        caption,
        ["arm", "difference", "low", "high", "p", "verdict"],
        rows,
        svg,
        dataset=grp["dataset"],
        measure=grp["measure"],
    )


def latency(goal: str, dataset: str | None = None) -> dict:
    """Every item's latency per arm, its p50 and p95 marked; the cost per item beside it in the table."""
    A = _adapter()
    grp = _group(goal, dataset)
    groups, marks, rows = {}, {}, []
    for a in grp["arms"]:
        lat = _values(A, a["arm"], "latency_ms")
        if not lat:
            continue
        from evaluation_harness.axes import percentile  # noqa: PLC0415

        # The leaderboard's p50 and p95 (axes.percentile, linear between the closest ranks), so a chart and the
        # speed column never differ on one arm.
        vals = list(lat.values())
        p50, p95 = percentile(vals, 50), percentile(vals, 95)
        groups[a["label"]] = [(v, f"{a['label']} · {i}") for i, v in lat.items()]
        marks[a["label"]] = [(p50, "p50"), (p95, "p95")]
        rows.append(
            {
                "arm": a["label"],
                "items": len(vals),
                "p50_ms": p50,
                "p95_ms": p95,
                "cost_per_item_usd": _mean(_values(A, a["arm"], "cost_usd").values()),
            }
        )
    if not rows:
        raise Problem(f"goal {goal}: no arm records a latency per item", "not-enough")
    caption = (
        f"Every {A.item_word}'s latency in milliseconds per arm on {grp['dataset']} (the mean of its repeats), lower "
        "is better; the ticks are its median (p50) and its 95th percentile (p95). Latencies measured on different "
        "machines are not comparable: the goal never tie-breaks on them then." + _through(grp["scorer"])
    )
    svg = cc.strip(
        groups, f"latency per {A.item_word}", lower=True, marks=marks, width=cc.NARROW, caption=cc._e(caption)
    )
    return _out(
        "latency",
        f"{goal}: latency per {A.item_word}",
        caption,
        ["arm", "items", "p50_ms", "p95_ms", "cost_per_item_usd"],
        rows,
        svg,
    )


def items(goal: str, dataset: str | None = None, href=None) -> dict:
    """Arms by items, coloured by score: the items where the arms disagree most first (ITEMS_SHOWN of them drawn)."""
    A = _adapter()
    grp = _group(goal, dataset)
    m = grp["measure"]
    series = {a["label"]: _values(A, a["arm"], m) for a in grp["arms"]}
    series = {k: v for k, v in series.items() if v}
    if len(series) < 2:
        raise Problem(f"goal {goal}: fewer than 2 arms with per-item {m}", "not-enough")
    shared = sorted(set.intersection(*(set(v) for v in series.values())))
    if not shared:
        raise Problem(f"goal {goal}: the arms share no {A.item_word}", "not-enough")
    spread = {i: statistics.pstdev([series[a][i] for a in series]) for i in shared}
    order = sorted(shared, key=lambda i: (-spread[i], i))
    shown = order[:ITEMS_SHOWN]
    allv = [series[a][i] for a in series for i in shared]
    lo, hi = min(allv), max(allv)
    arms_by = {a["label"]: a["arm"] for a in grp["arms"]}
    cells = {
        (a, i): {
            "value": series[a][i],
            "tip": f"{a} · {i}: {cc._num(series[a][i])}",
            **({"href": href(arms_by[a], i)} if href else {}),
        }
        for a in series
        for i in shown
    }
    lower = grp["direction"] == "lower"
    caption = (
        f"{m} per {A.item_word} and arm on {grp['dataset']}, the darker the higher ({'lower' if lower else 'higher'} "
        f"is better). The {len(shown)} of {len(shared)} {A.item_word}s where the arms differ most, most first: where "
        "to read outputs side by side." + _through(grp["scorer"])
    )
    svg = cc.heatmap(
        list(series), shown, cells, f"{m} by arm and {A.item_word}", lo, hi, caption=cc._e(caption)
    )
    rows = [{"item": i, "spread": spread[i], **{a: series[a][i] for a in series}} for i in order]
    return _out("items", f"{goal}: where the arms differ", caption, ["item", "spread", *series], rows, svg)


# ── rounds and studies against their baseline ────────────────────────────────
def _against(A, arms: list[str], base: str, metric: str, lower: bool, dataset: str) -> list[dict]:
    """Each arm against `base`: its paired test on the measure (Holm across the arms), its interval, and its mean
    difference in cost per item on the items both have."""
    from evaluation_harness import stats  # noqa: PLC0415
    from evaluation_harness.model import compare as model_compare  # noqa: PLC0415

    model_compare.set_adapter(A)
    series = {a: _values(A, a, metric) for a in [base, *arms]}
    cmp = stats.compare(
        series,
        base,
        higher_is_better=not lower,
        family=max(len(arms), 1),
        clusters=model_compare.goal_clusters_on(dataset)[0],
    )
    cost_b = _values(A, base, "cost_usd")
    tok_b = _tokens(A, base)
    out = []
    for r in cmp["rows"]:
        cost_a = _values(A, r["arm"], "cost_usd")
        both = sorted(set(cost_a) & set(cost_b))
        tok_a = _tokens(A, r["arm"])
        tboth = sorted(set(tok_a) & set(tok_b))
        out.append(
            r
            | {
                "cost_delta": _mean(cost_a[i] - cost_b[i] for i in both) if both else None,
                "cost_items": len(both),
                "tokens_delta": _mean(tok_a[i] - tok_b[i] for i in tboth) if tboth else None,
            }
        )
    return out


def _tokens(A, arm: str) -> dict[str, float]:
    """An arm's tokens per item (in plus out), on the items that record both: the cost axis when no arm has a price."""
    tin, tout = _values(A, arm, "tokens_in"), _values(A, arm, "tokens_out")
    return {i: tin[i] + tout[i] for i in tin if i in tout}


def _claim(filled: bool, y: float, x: float | None) -> str:
    """What a point may be called (RFC-034 §3): a quadrant only for a significant difference."""
    if not filled:
        return "no gain shown, costs more" if (x or 0) > 0 else "not separated"
    up = y > 0
    # A cost no different from the base's is not "cheaper": named as the same cost (review, 2026-11-19: arms with no
    # cost at all were called "better and cheaper"), and a cost not recorded on the items both share as that.
    if x is None:
        return ("better" if up else "worse") + ", its cost not compared"
    if abs(x) <= 1e-12:
        return ("better" if up else "worse") + " at the same cost"
    return cc.QUADRANTS[(0 if up else 2) + (1 if x > 0 else 0)]


def gain_cost(goal: str, round: str | None = None, study: str | None = None) -> dict:
    """A round's arms (against the run it started from, else its leader) or a study's trials (against its baseline):
    the difference in quality against the difference in cost per item (in tokens when no arm records a cost)."""
    if bool(round) == bool(study):
        raise Problem("gain-cost: name a round or a study", "bad-argument")
    A = _adapter()
    g = _goal(A, goal)
    prim = (g.get("success_criteria") or {}).get("primary") or {}
    metric, lower = str(prim.get("measure", "")), prim.get("direction") == "lower"
    rows: list[dict] = []

    def row(name: str, r: dict, flip: float, filled: bool, **extra: Any) -> dict:
        """One arm or trial against the base: its difference, flipped so up is better, its interval and its claim; an
        arm that shares no item with the base (no difference) is a row that says so, never a point."""
        ci, d = r.get("ci"), r.get("delta")
        y = d * flip if d is not None else None
        return {
            "arm": name,
            **{k: v for k, v in extra.items() if k in ("change",)},
            "quality_delta": y,
            "low": min(ci[0] * flip, ci[1] * flip) if ci else None,
            "high": max(ci[0] * flip, ci[1] * flip) if ci else None,
            "p": extra.get("p", r.get("p")),
            "verdict": _word(extra.get("verdict", r.get("verdict"))),
            "cost_delta_per_item": r["cost_delta"],
            "tokens_delta_per_item": r.get("tokens_delta"),
            "claim": "not compared: no shared item" if y is None else "",
            "_significant": filled,
            **{k: v for k, v in extra.items() if k in ("outcome", "reason")},
        }

    if round:
        from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415
        from evaluation_harness.ops.rounds import _round  # noqa: PLC0415

        rnd = _round(goal, round)
        ev = model_rounds.evidence(goal, rnd, A)
        base = ev.get("baseline_arm") or ev.get("leader")
        if not base:
            raise Problem(f"round {round}: no arm records {metric} yet", "not-enough")
        against = "the run it started from" if ev.get("baseline_arm") else "its leader (it names no baseline)"
        arms = [a for a in ev["arms"] if a != base]
        flip = -1.0 if lower else 1.0
        names, scorer = _shown({a: _label(A, a) for a in [base, *arms]})
        for r in _against(A, arms, base, metric, lower, rnd["dataset_id"]):
            rows.append(row(names[r["arm"]], r, flip, str(r.get("verdict") or "").startswith("significant")))
        title, base_name, ds = f"{goal} {round}: gain against cost", names[base], rnd["dataset_id"]
        tests = "the paired test, Holm across the arms"
    else:
        from evaluation_harness.model import studies as ms  # noqa: PLC0415

        scorer = ""  # a study's trials are its own systems' runs, read as they ran
        sid = str(study)
        st, spec = ms.state(goal, sid, _data()), ms.spec(goal, sid, _data())
        ds = str(spec.get("dataset"))
        # A study decides on its own measure, in that measure's direction (as study-progress draws it): drawn on the
        # goal's primary instead, a trial better on the study's measure was plotted down and called worse.
        metric = str(spec.get("measure") or metric)
        lower = ms_lower(goal, metric)
        flip = -1.0 if lower else 1.0
        base = _arm_of(A, ds, st["baseline"])
        if base is None:
            raise Problem(f"study {study}: its baseline {st['baseline']} has no run on {ds}", "not-enough")
        trials = [t for t in st["trials"] if t.get("system_id") and t.get("outcome") != "failed"]
        trial_arms = {t["system_id"]: _arm_of(A, ds, t["system_id"]) for t in trials}
        by_arm = {
            r["arm"]: r for r in _against(A, [a for a in trial_arms.values() if a], base, metric, lower, ds)
        }
        for t in trials:
            tr = by_arm.get(trial_arms[t["system_id"]] or "")
            if tr is None:
                continue
            vs = t.get("vs_baseline") or {}
            rows.append(
                row(
                    f"t{t['k']}",
                    tr,
                    flip,
                    str(vs.get("verdict") or "").startswith("significant"),
                    change=t.get("change"),
                    p=vs.get("p"),
                    verdict=vs.get("verdict"),
                    outcome=t.get("outcome"),
                    reason=t.get("reason"),
                )
            )
        title, base_name, against = (
            f"{goal}/{study}: each trial's gain against its cost",
            _label(A, base),
            "its baseline",
        )
        tests = "each trial's nominal paired test against the baseline (a study is research: its confirmation on the test set is the evidence)"
    if not rows:
        raise Problem(f"{round or study}: no arm or trial measured against {base_name} yet", "not-enough")
    drawn = [r for r in rows if r["quality_delta"] is not None]
    if not drawn:
        raise Problem(
            f"{round or study}: no arm or trial shares an {A.item_word} with {base_name}: nothing to compare",
            "not-enough",
        )
    priced = any((r["cost_delta_per_item"] or 0) != 0 for r in drawn)
    by_tokens = not priced and any((r["tokens_delta_per_item"] or 0) != 0 for r in drawn)
    x_key = "tokens_delta_per_item" if by_tokens else "cost_delta_per_item"
    for r in drawn:  # the quadrant named on the axis drawn: cost, else tokens
        r["claim"] = _claim(r["_significant"], r["quality_delta"], r[x_key])
    for r in rows:
        r.pop("_significant", None)
    points = []
    for r in drawn:
        filled = not r["claim"].startswith(("not separated", "no gain"))
        x = r[x_key] if r[x_key] is not None else 0.0
        cost = f"{x:+.0f} tokens" if by_tokens else f"{x:+.6f} USD"
        points.append(
            {
                "name": r["arm"],
                "x": x,
                "y": r["quality_delta"],
                "ylo": r["low"],
                "yhi": r["high"],
                "filled": filled,
                "tip": f"{r['arm']}: {metric} {r['quality_delta']:+.4g}, per {A.item_word} {cost} ({r['claim']})"
                + (f"; {r['outcome']}: {r['reason']}" if r.get("reason") else ""),
            }
        )
    left_out = [r["arm"] for r in rows if r["quality_delta"] is None]
    flipped = " (lower is better: flipped, so up is better)" if lower else ""
    caption = (
        f"Against {base_name} ({against}) on {ds}: up is better on {metric}{flipped}, with the 95% interval as a "
        f"whisker; left is cheaper per {A.item_word}"
        + (" in tokens, as no arm recorded a cost" if by_tokens else "")
        + f". A filled mark is a difference {tests} supports, and only those are named by their quadrant; a hollow "
        "one is not separated from the baseline, whatever side it falls on."
        + (
            ""
            if priced or by_tokens
            else " No arm recorded a cost or tokens different from the baseline's: the cost axis is flat."
        )
        + (
            f" Not drawn, sharing no {A.item_word} with the baseline: {', '.join(left_out)}."
            if left_out
            else ""
        )
        + _through(scorer)
    )
    svg = cc.quadrant(
        points,
        title,
        f"difference in {'tokens' if by_tokens else 'cost'} per {A.item_word}"
        + ("" if by_tokens else " (USD)"),
        f"difference in {metric}" + (", flipped (lower is better)" if lower else ""),
        fmt_x=lambda v: f"{v:+.4g}",
        caption=cc._e(caption),
    )
    return _out(
        "gain-cost",
        title,
        caption,
        [
            "arm",
            *(["change"] if study else []),
            "quality_delta",
            "low",
            "high",
            "p",
            "verdict",
            "cost_delta_per_item",
            "tokens_delta_per_item",
            "claim",
            *(["outcome", "reason"] if study else []),
        ],
        rows,
        svg,
        baseline=base_name,
    )


def _arm_of(A, dataset: str, system: str) -> str | None:
    """The catalog's arm of a system's measured runs on a dataset."""
    want = f"runs/{dataset}/{system}"
    return want if want in set(A.arms()) else None


def study_progress(goal: str, study: str) -> dict:
    """A study's trials in order, each one's measure marked by its outcome, the best so far from the baseline."""
    from evaluation_harness.model import studies as ms  # noqa: PLC0415

    A = _adapter()
    st, spec = ms.state(goal, study, _data()), ms.spec(goal, study, _data())
    ds, metric = str(spec.get("dataset")), str(spec.get("measure"))
    base = _arm_of(A, ds, st["baseline"])
    base_mean = _mean(_values(A, base, metric).values()) if base else None
    points, rows = [], []
    best = [(0.0, base_mean)] if base_mean is not None else []
    for t in st["trials"]:
        arm = _arm_of(A, ds, t.get("system_id") or "")
        y = _mean(_values(A, arm, metric).values()) if arm else None
        outcome = str(t.get("outcome") or "")
        rows.append(
            {
                "trial": t["k"],
                "change": t.get("change"),
                "mean": y,
                "outcome": outcome,
                "reason": t.get("reason"),
            }
        )
        if y is None:
            continue
        points.append(
            {
                "k": t["k"],
                "y": y,
                "mark": outcome if outcome in ("kept", "dropped") else "other",
                "tip": f"t{t['k']}: {metric} {cc._num(y)}, {outcome}"
                + (f": {t['reason']}" if t.get("reason") else ""),
            }
        )
        if outcome == "kept":
            best.append((float(t["k"]), y))
    if not points:
        raise Problem(f"study {study}: no trial measured yet", "not-enough")
    lower = ms_lower(goal, metric)
    caption = (
        f"{metric} on {ds} per trial ({'lower' if lower else 'higher'} is better): filled kept, hollow dropped, a cross "
        "for no effect or a trial that did not decide. The line is the best so far, from the baseline at 0; a trial is "
        "kept by the study's rule, not by its mark's height."
    )
    svg = cc.progress(points, best, f"{goal}/{study}: trials", metric, caption=cc._e(caption))
    return _out(
        "study-progress",
        f"{goal}/{study}: the trials so far",
        caption,
        ["trial", "change", "mean", "outcome", "reason"],
        rows,
        svg,
    )


def ms_lower(goal: str, metric: str) -> bool:
    """Whether the study's measure is better lower, as the study decides it."""
    from evaluation_harness import _study  # noqa: PLC0415

    return bool(_study.lower_is_better(goal, metric))


# ── datasets ─────────────────────────────────────────────────────────────────
def rank_stability(dataset: str, metric: str | None = None) -> dict:
    """How often two disjoint halves of n items agree on the order, and on the winner, as n grows."""
    from evaluation_harness import rank_stability as rs  # noqa: PLC0415

    m = rs.measure(dataset, metric)
    rows = m["rows"]
    if not rows:
        raise Problem(f"{dataset}: too few items for two halves of {rs.SMALLEST}", "not-enough")
    series = {
        "rank agreement (Spearman's rho, mean)": [(r["n_per_half"], r["rho_mean"]) for r in rows],
        "the same winner (share of decided draws)": [(r["n_per_half"], r["p_same_winner"]) for r in rows],
    }
    lo = min(0.0, *(v for s in series.values() for _, v in s if v is not None and v == v))
    caption = (
        f"{m['arms']} arms, {m['items']} {m['metric']} items, {m['draws']} random pairs of disjoint halves per size: "
        "where the lines flatten, more items stop buying a steadier order. Two honest measurements disagree a little "
        "even when both are right, so the ceiling is below 1."
    )
    svg = cc.lines(
        series,
        f"{dataset}: rank stability",
        "items in each half",
        "agreement",
        y_range=(lo, 1.0),
        caption=cc._e(caption),
    )
    return _out(
        "rank-stability", f"{dataset}: how many items the order needs", caption, list(rows[0]), rows, svg
    )


def agreement(dataset: str | None = None, scorer: str | None = None) -> dict:
    """A dataset's label sets compared pairwise (each pair's confusion matrix), or a judge scorer's controls (each judge
    re-asked in another order and as it was, and the judges with each other)."""
    if bool(dataset) == bool(scorer):
        raise Problem("agreement: name a dataset or a scorer", "bad-argument")
    if scorer:
        return _judge_agreement(scorer)
    from evaluation_harness import _label_sets, _visibility  # noqa: PLC0415

    if not dataset:
        raise Problem("agreement: name a dataset or a scorer", "bad-argument")
    if _visibility.hidden(dataset):
        raise Problem(
            f"{dataset} is hidden: its labels are per-item text, and their matrices name them", "not-allowed"
        )
    pairs = _label_sets.agreement(dataset, _data())
    if not pairs:
        raise Problem(f"{dataset}: fewer than two label sets cover the same items", "not-enough")
    # A pair of free-text sets has no confusion matrix (no answer is shared): counted in the table, not drawn.
    svgs = [pair_heatmap(a) for a in pairs if a.get("confusion")]
    rows = [{k: a.get(k) for k in ("a", "b", "both", "same", "share", "kappa", "alpha")} for a in pairs]
    caption = f"{dataset}: each pair of label sets, a confusion matrix each, the darker the more items."
    return _out(
        "agreement",
        f"{dataset}: do the labels agree?",
        caption,
        ["a", "b", "both", "same", "share", "kappa", "alpha"],
        rows,
        "".join(svgs),
    )


def pair_heatmap(a: dict) -> str:
    """Two label sets' confusion matrix as a heat map (`_label_sets.agreement`'s pair: `a` down, `b` across)."""
    conf = a.get("confusion") or {}
    down = sorted(conf)
    across = sorted({k for row in conf.values() for k in row})
    cells = {
        (x, y): {
            "value": conf[x].get(y, 0),
            "tip": f"{a['a']} said {x}, {a['b']} said {y}: {conf[x].get(y, 0)}",
        }
        for x in down
        for y in across
    }
    top = max([c["value"] for c in cells.values()] or [1])
    cap = (
        f"{a['a']} down, {a['b']} across: how many of the {a.get('both')} items both label fall on each pair of answers, "
        f"the darker the more; the diagonal is agreement. Cohen's kappa {a.get('kappa')}, Krippendorff's alpha "
        f"{a.get('alpha')}."
    )
    return cc.heatmap(down, across, cells, f"{a['a']} against {a['b']}", 0, top, caption=cc._e(cap))


def _judge_agreement(scorer: str) -> dict:
    import json  # noqa: PLC0415

    from evaluation_harness import _store  # noqa: PLC0415
    from evaluation_harness.model.scorers import judging_sets_of, summary_file  # noqa: PLC0415

    sums = []
    for sid in judging_sets_of(scorer, _data()):
        f = summary_file(scorer, sid, _data())
        if _store.is_file(f):
            sums.append((sid, json.loads(_store.read_text(f, encoding="utf-8"))))
    if not sums:
        raise Problem(
            f"scorer {scorer} has no judging summary yet: evh judge-score --scorer {scorer}", "not-enough"
        )
    sid, s = sums[-1]
    cols = ["reordered τ", "re-asked τ", "length ρ"]
    judges = sorted(s.get("controls") or {})
    cells, rows = {}, []
    for j in judges:
        c = (s.get("controls") or {}).get(j) or {}
        vals = [
            (c.get("position") or {}).get("mean_tau"),
            (c.get("noise") or {}).get("mean_tau"),
            ((s.get("length_bias") or {}).get(j) or {}).get("spearman_length"),
        ]
        for col, v in zip(cols, vals, strict=True):
            if v is not None:
                cells[(j, col)] = {"value": float(v), "tip": f"{j}, {col}: {v}"}
        rows.append({"judge": j, **dict(zip(("position_tau", "noise_tau", "length_rho"), vals, strict=True))})
    for pair, v in (s.get("judge_agreement") or {}).items():
        a, b = pair.split("~", 1)
        rows.append(
            {
                "judge": pair,
                "items": v.get("n_items"),
                "arm_spearman": v.get("arm_mean_spearman"),
                "item_tau": v.get("mean_item_tau"),
            }
        )
        # A pair with no τ (too few shared items) is an empty cell, as the controls are: drawn as 0 it read as two
        # judges that do not agree at all (review, 2026-11-19).
        if v.get("mean_item_tau") is not None:
            cells[(pair, "each other τ")] = {
                "value": float(v["mean_item_tau"]),
                "tip": f"{a} and {b}: τ per item {v['mean_item_tau']}",
            }
    cols = cols + (["each other τ"] if s.get("judge_agreement") else [])
    names = judges + list(s.get("judge_agreement") or {})
    caption = (
        f"{scorer} on {sid}: each judge's rank correlation (-1 to 1, the darker the higher) with itself shown the "
        "outputs in another order (reordered τ) and asked the same again (re-asked τ), near 1 when it is steady; with "
        "the outputs' length (length ρ), near 1 when it follows length, a bias rather than a virtue; and the judges with "
        "each other per item (each other τ). Whether it agrees with people is its validation (scorer-show)."
    )
    svg = cc.heatmap(names, cols, cells, f"{scorer}: its judges' controls", -1.0, 1.0, caption=cc._e(caption))
    return _out(
        "agreement",
        f"{scorer}: do its judges agree?",
        caption,
        ["judge", "position_tau", "noise_tau", "length_rho", "items", "arm_spearman", "item_tau"],
        rows,
        svg,
    )


# ── over time ────────────────────────────────────────────────────────────────
def trend(goal: str | None = None, model: str | None = None, dataset: str | None = None) -> dict:
    """A goal's baseline across its versions and the promoted run of each closed round; or a code record's
    faithfulness per deployed period."""
    if bool(goal) == bool(model):
        raise Problem("trend: name a goal or a code record (model)", "bad-argument")
    if model:
        return _faith_trend(model)
    if not goal:
        raise Problem("trend: name a goal or a code record (model)", "bad-argument")
    from evaluation_harness import _baselines, _rounds  # noqa: PLC0415
    from evaluation_harness.model import runs as model_runs  # noqa: PLC0415

    A = _adapter()
    g = _goal(A, goal)
    metric = str(((g.get("success_criteria") or {}).get("primary") or {}).get("measure", ""))

    def of_run(run: str | None) -> tuple[float | None, str]:
        """The run's value of the goal's measure as it was when it ran (the score it made then), and where it was read.
        A measure added after the run was measured is only in a re-score: then the latest one, named (fleet,
        2026-11-18: triage_cost, and the trend said no closed round had one)."""
        from evaluation_harness import rescore  # noqa: PLC0415

        first = model_runs.first_score(run, _data()) if run else None
        rec = model_runs.record(first) if first else None
        if not first or not rec:
            return None, ""
        sc = (rec.get("scores") or {}).get(metric)
        if sc is not None:
            return float(sc), "the run's own score"
        scorer, read_from = rescore.latest_scoring(first, rec)
        later = ((model_runs.record(read_from) if read_from else None) or {}).get("scores") or {}
        if later.get(metric) is not None:
            return float(later[metric]), f"re-scored {str(scorer)[:8]} (the measure came after the run)"
        return None, ""

    # Every event on one time line: a baseline version when it was promoted, a closed round when it closed. Each x is
    # one event, named by it (v1, r2): a round's point under a version's name, or a second dataset's names written over
    # the first's, read as something it was not.
    events: list[dict[str, Any]] = []
    versions = 0
    for d in g.get("datasets") or []:
        ds = d.get("dataset_id", "")
        if dataset and ds != dataset:
            continue
        for v in _baselines.versions(goal, ds, _data()):
            versions += 1
            sc = ((v.get("repeats") or {}).get("mean_scores") or v.get("scores") or {}).get(metric)
            src = "the version's record"
            if sc is None:
                sc, src = of_run(v.get("promoted_from"))
            events.append(
                {
                    "line": f"the baseline on {ds}",
                    "at": v.get("promoted_at"),
                    "name": f"v{v.get('version')}" + (f" {ds}" if len(g.get("datasets") or []) > 1 else ""),
                    "version": v.get("version"),
                    "run": v.get("promoted_from"),
                    "value": sc,
                    "read": src if sc is not None else "",
                }
            )
    all_closed = [r for r in _rounds.load_rounds(goal, _data()) if r.get("status") == "closed"]
    closed = [r for r in all_closed if (r.get("conclusion") or {}).get("promoted_run")]
    for r in closed:
        run = r["conclusion"]["promoted_run"]
        sc, src = of_run(run)
        events.append(
            {
                "line": "each closed round's promoted run",
                "at": r.get("closed_at"),
                "name": str(r["round_id"]),
                "version": r["round_id"],
                "run": run,
                "value": sc,
                "read": src,
            }
        )
    events.sort(key=lambda e: (e["at"] is None, str(e["at"] or "")))
    series: dict[str, list[tuple[float, float]]] = {}
    names: dict[float, str] = {}
    rows = []
    for x, e in enumerate(events, 1):
        rows.append(
            {k: e[k] for k in ("line", "at", "version", "run")} | {metric: e["value"], "read": e["read"]}
        )
        if e["value"] is None:
            continue
        series.setdefault(str(e["line"]), []).append((float(x), float(e["value"])))
        names[float(x)] = str(e["name"])
    if not series:
        raise Problem(
            f"goal {goal}: nothing to draw: {versions} baseline version(s) and {len(closed)} of {len(all_closed)} closed "
            f"round(s) that promoted a run, none of them with a {metric} score (not in the runs' scores nor in a "
            "re-scoring of them)",
            "not-enough",
        )
    rescored = any(str(e["read"]).startswith("re-scored") for e in events)
    caption = (
        f"{metric} of {goal}'s baseline at each of its versions and of the run each closed round promoted, in the order "
        "they happened, each as it was then: a version's record, a run's own score. A step up is a promotion the "
        "evidence supported at the time; versions measured on different dataset versions are not on one scale."
        + (
            " A run measured before the measure existed is read from its latest re-score, as its row says."
            if rescored
            else ""
        )
    )
    svg = cc.lines(
        series,
        f"{goal} over time",
        "in the order they happened",
        metric,
        x_names=names,
        caption=cc._e(caption),
    )
    return _out(
        "trend", f"{goal} over time", caption, ["line", "at", "version", "run", metric, "read"], rows, svg
    )


def _faith_trend(model: str) -> dict:
    from evaluation_harness import _coderec  # noqa: PLC0415
    from evaluation_harness.model import faithfulness as model_faithfulness  # noqa: PLC0415

    rec = model_faithfulness.with_summaries(_coderec.load(model))
    spans, bad = _coderec.periods(rec)
    if bad:
        raise Problem(f"code record {model}: {bad[0]}", "invalid-file")
    by_commit = {str(v.get("commit")): v for v in rec.get("versions") or []}
    rows, line, names = [], [], {}
    for n, (f, t, c) in enumerate(spans, 1):
        faith = by_commit.get(c, {}).get("faithfulness") or {}
        share = (faith["agreed"] / faith["items"]) if faith.get("items") else None
        rows.append(
            {
                "period": n,
                "from": f.isoformat(),
                "to": t.isoformat() if t else None,
                "commit": c[:12],
                "agreed": faith.get("agreed"),
                "items": faith.get("items"),
                "share": share,
            }
        )
        if share is not None:
            line.append((float(n), share))
            names[float(n)] = f.isoformat()[:10]
    if not line:
        raise Problem(
            f"code record {model}: no deployed period has a faithfulness record yet (evh faithfulness)",
            "not-enough",
        )
    caption = (
        f"For each period {model} was deployed, the share of production's recorded decisions its replay at that "
        "commit reproduced: below 1, production did something the code alone does not explain (a model's drift, an "
        "input that changed, a person's override), named in faithfulness-show."
    )
    svg = cc.lines(
        {"agreed with production": line},
        f"{model}: faithfulness per period",
        "deployed from",
        "share agreed",
        x_names=names,
        y_range=(0.0, 1.0),
        caption=cc._e(caption),
    )
    return _out(
        "trend",
        f"{model}: faithfulness per period",
        caption,
        ["period", "from", "to", "commit", "agreed", "items", "share"],
        rows,
        svg,
    )


# ── the one entry ────────────────────────────────────────────────────────────
def chart(
    kind: str,
    goal: str | None = None,
    round: str | None = None,
    study: str | None = None,
    dataset: str | None = None,
    scorer: str | None = None,
    model: str | None = None,
    metric: str | None = None,
) -> dict:
    """One chart of `kind` from the inputs it takes; a Problem names an input it lacks."""

    def need(name: str, value: str | None) -> str:
        if not value:
            raise Problem(f"{kind} needs --{name}", "bad-argument")
        return value

    if kind == "gain-cost":
        return gain_cost(need("goal", goal), round=round, study=study)
    if kind == "intervals":
        return intervals(need("goal", goal), dataset)
    if kind == "study-progress":
        return study_progress(need("goal", goal), need("study", study))
    if kind == "rank-stability":
        return rank_stability(need("dataset", dataset), metric)
    if kind == "latency":
        return latency(need("goal", goal), dataset)
    if kind == "agreement":
        return agreement(dataset=dataset, scorer=scorer)
    if kind == "items":
        return items(need("goal", goal), dataset)
    if kind == "trend":
        return trend(goal=goal, model=model, dataset=dataset)
    raise Problem(f"no chart {kind!r}: one of {', '.join(KINDS)}", "bad-argument")
