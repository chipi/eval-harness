"""Quality, cost, speed and a project's own axes: what a goal weighs, and the decision they give.

    axes_of(goal, direction_of)            the goal's axes, built-ins first, then its own
    decide(goal, arms, direction_of, ...)  limits, the quality leader, the tie, the tie-break

A goal's `success_criteria.primary` is its quality axis. Cost and speed are built in: they need no
configuration and appear whenever runs record `cost_usd` (and token counts) and `latency_ms`. A
goal adds limits, a tie-break order and axes of its own under `success_criteria`:

    axes:
      cost:  {limit: 0.001}                                   # USD per item (mean)
      speed: {limit: 2000}                                    # ms, on the p95
      faithfulness: {measure: grounded_rate, direction: higher, limit: 0.9}
    tie_break: [cost, speed]

THE RULE (ADR-0006). An arm over a limit is out, with the reason; so is an arm measured on fewer
items than the group's most-measured arm, and one that shares fewer than two items with the
leader. Among the rest, the leader is the best on quality, and the goal's strategy says who is
tied with it (balanced: not separated by the paired test, Holm across them, and within the
margin; identical scores are always tied). Among the tied, the tie-break axes pick in order: the
lowest cost, then the lowest latency (or the best value of a project's axis). It recommends;
promoting stays a command. A number an arm does not record is "not recorded": never 0, never a
reason to drop it, and an axis some tied arm does not record cannot break the tie.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import math
import statistics
from typing import Any, Callable

from evaluation_harness import stats

#: The axes every goal has unless it ignores them: the measure, which way is better, and the
#: statistic a limit is read on (a speed limit is about the slow tail, so p95).
BUILTIN: dict[str, dict[str, Any]] = {
    "cost": {"measure": "cost_usd", "direction": "lower", "stat": "mean", "unit": "USD per item"},
    "speed": {"measure": "latency_ms", "direction": "lower", "stat": "p95", "unit": "ms"},
}
DEFAULT_TIE_BREAK = ("cost", "speed")
#: How a goal turns its axes into a recommendation: who counts as tied with the quality leader,
#: so that cost, speed or a project's axis may pick among them (limits always apply first).
STRATEGIES = {
    "balanced": "tied: not separated by the paired test AND within the quality margin (default)",
    "quality_first": "tied: only the same quality; cost and speed break exact ties only",
    "frugal": "tied: anything the paired test cannot separate from the leader; the cheaper wins",
}
DEFAULT_STRATEGY = "balanced"
#: How close to the leader's quality an unseparated arm must be to count as tied, when the goal sets
#: no margin: a share of the leader's mean, so it means the same on a 0-1 rate and a 1-5 score.
DEFAULT_MARGIN = 0.02
#: Shown beside cost: what a free local model still uses.
TOKENS = ("tokens_in", "tokens_out")


def axes_of(goal: dict, direction_of: Callable[[str], str | None] | None = None) -> list[dict]:
    """[{"name", "measure", "direction", "stat", "limit", "role", "note", "unit", "builtin"}]:
    quality (the primary measure) first, then cost and speed, then the goal's own, in its order.
    `direction_of(measure)` names a custom measure's direction when the goal does not."""
    crit = goal.get("success_criteria") or {}
    prim = crit.get("primary") or {}
    declared = crit.get("axes") or {}
    q = declared.get("quality") or {}
    out = [
        {
            "name": "quality",
            "measure": prim.get("measure", ""),
            "direction": "lower" if prim.get("direction") == "lower" else "higher",
            "stat": "mean",
            "limit": q.get("limit"),
            "margin": q.get("margin"),
            "role": "decides",
            "note": q.get("note", ""),
            "unit": "",
            "builtin": True,
        }
    ]
    for name, base in BUILTIN.items():
        own = declared.get(name) or {}
        out.append(
            {
                "name": name,
                "measure": own.get("measure") or base["measure"],
                "direction": own.get("direction") or base["direction"],
                "stat": own.get("stat") or base["stat"],
                "limit": own.get("limit"),
                "role": own.get("role") or "show",
                "note": own.get("note", ""),
                "unit": own.get("unit") or (base["unit"] if not own.get("measure") else ""),
                "builtin": True,
            }
        )
    for name, own in declared.items():
        if name in ("quality", *BUILTIN):
            continue
        measure = own.get("measure") or name
        out.append(
            {
                "name": name,
                "measure": measure,
                "direction": own.get("direction")
                or (direction_of(measure) if direction_of else None)
                or "higher",
                "stat": own.get("stat") or "mean",
                "limit": own.get("limit"),
                "role": own.get("role") or "show",
                "note": own.get("note", ""),
                "unit": own.get("unit", ""),
                "builtin": False,
            }
        )
    return out


def strategy_of(goal: dict) -> str:
    """The goal's strategy, or balanced."""
    return (goal.get("success_criteria") or {}).get("strategy") or DEFAULT_STRATEGY


def tie_break_of(goal: dict) -> list[str]:
    """The goal's tie-break order, or cost then speed."""
    tb = (goal.get("success_criteria") or {}).get("tie_break")
    return list(tb) if tb else list(DEFAULT_TIE_BREAK)


def percentile(values: list[float], q: float) -> float:
    """The q-th percentile (0..100), linear between the closest ranks."""
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def summarize(values: dict[str, float]) -> dict[str, float | int | None]:
    """{"mean", "p50", "p95", "n"} over an arm's per-item values; all None when there are none."""
    v = [float(x) for x in values.values() if isinstance(x, (int, float)) and not math.isnan(float(x))]
    if not v:
        return {"mean": None, "p50": None, "p95": None, "n": 0}
    return {"mean": statistics.fmean(v), "p50": percentile(v, 50), "p95": percentile(v, 95), "n": len(v)}


def tokens_per_item(scores: dict[str, dict]) -> dict[str, float]:
    """{item: tokens in + out}, for the items that report either."""
    tin = (scores.get("tokens_in") or {}).get("values") or {}
    tout = (scores.get("tokens_out") or {}).get("values") or {}
    return {i: float(tin.get(i, 0.0)) + float(tout.get(i, 0.0)) for i in set(tin) | set(tout)}


def builtin_axes() -> list[dict]:
    """Cost and speed as a goal with no `axes:` entry weighs them: for pages about an arm, not a goal."""
    return axes_of({})[1:]


def cell_of(axis: dict, scores: dict[str, dict]) -> dict:
    """One arm on one axis: {"mean", "p50", "p95", "n", "value" (the axis's statistic), "within"
    (its limit), "tokens" (cost only: tokens per item)}."""
    s = summarize((scores.get(axis["measure"]) or {}).get("values") or {})
    value = s["p95"] if axis["stat"] == "p95" else s["p50"] if axis["stat"] == "p50" else s["mean"]
    cell: dict[str, Any] = {**s, "value": value, "within": within(axis, value)}
    if axis["name"] == "cost":
        cell["tokens"] = summarize(tokens_per_item(scores))
    return cell


def within(axis: dict, value: float | None) -> bool | None:
    """True or False against the axis's limit; None when there is no limit or no value."""
    if axis.get("limit") is None or value is None:
        return None
    return value <= float(axis["limit"]) if axis["direction"] == "lower" else value >= float(axis["limit"])


def decide(
    goal: dict,
    arms: dict[str, dict],
    direction_of: Callable[[str], str | None] | None = None,
    machines: dict[str, str] | None = None,
) -> dict:
    """The goal's decision over one group of arms (one dataset, scored against one thing).

    arms: {arm: {"label", "flags": [str], "scores": {metric: {"values": {item: float}}}}}; a flagged
    arm (too few items, the wrong format, it wrote the reference) is shown but never recommended.
    machines: {arm: machine label}; with more than one, speed is never compared or tie-broken.

    Returns {"axes", "rows": {arm: {axis: {"value", "mean", "p50", "p95", "n", "within",
    "tokens"?, "vs_leader"?}}}, "out": {arm: [reason]}, "leader", "tied", "recommended", "why"}."""
    axes = [a for a in axes_of(goal, direction_of) if a["role"] != "ignore"]
    quality = axes[0]
    distinct_machines = {m for m in (machines or {}).values() if m}
    one_machine = len(distinct_machines) <= 1
    rows: dict[str, dict] = {}
    out: dict[str, list[str]] = {}
    for arm, a in arms.items():
        sc = a.get("scores") or {}
        row: dict[str, dict] = {}
        for ax in axes:
            cell = cell_of(ax, sc)
            value = cell["value"]
            row[ax["name"]] = cell
            if cell["within"] is False:
                which = f"{ax['stat']} " if ax["stat"] != "mean" else ""
                out.setdefault(arm, []).append(
                    f"{ax['name']} {which}{value_text(ax, value)} {'>' if ax['direction'] == 'lower' else '<'} "
                    f"limit {value_text(ax, float(ax['limit']))}"
                )
        rows[arm] = row
    # An arm measured on fewer items than the group's most-measured arm is out: its mean is over
    # other items, so it could lead on a part of the set (a 0.95 on 4 items over a 0.8 on 20).
    most = max((rows[x]["quality"]["n"] for x in arms), default=0)
    for arm in arms:
        n = rows[arm]["quality"]["n"]
        if 0 < n < most:
            out.setdefault(arm, []).append(f"n {n} of {most} items")
    eligible = [
        x
        for x in arms
        if x not in out and not arms[x].get("flags") and rows[x]["quality"]["value"] is not None
    ]
    why: list[str] = []
    for arm, reasons in out.items():
        why.append(f"{arms[arm]['label']} is out: {'; '.join(reasons)}.")
    if not eligible:
        why.append(_none_eligible(arms, rows, out))
        return {
            "axes": axes,
            "rows": rows,
            "out": out,
            "eligible": [],
            "leader": None,
            "tied": [],
            "recommended": None,
            "why": why,
        }
    better_high = quality["direction"] == "higher"
    # Equal quality: the first by label leads, so the order the arms come in never decides; the
    # strategy then ties identical arms and the tie-break picks among them.
    leader = max(
        sorted(eligible, key=lambda x: arms[x]["label"]),
        key=lambda x: rows[x]["quality"]["value"] * (1 if better_high else -1),
    )
    # Every axis against the leader, paired per item; Holm across the eligible arms on quality.
    family = max(len(eligible) - 1, 1)
    for ax in axes:
        # Quality decides the tie, so only the eligible arms are its family; every other axis is
        # shown for every arm.
        among = eligible if ax is quality else list(arms)
        series = {x: (arms[x]["scores"].get(ax["measure"]) or {}).get("values") or {} for x in among}
        if not series.get(leader):
            continue
        cmp = stats.compare(series, leader, higher_is_better=ax["direction"] == "higher", family=family)
        for r in cmp.get("rows") or []:
            note = "" if ax["name"] != "speed" or one_machine else "different machines: not compared"
            rows[r["arm"]][ax["name"]]["vs_leader"] = {
                "delta": r.get("delta"),
                "p": r.get("p"),
                "verdict": note or r.get("verdict"),
            }
    for x in [
        x for x in eligible if (rows[x]["quality"].get("vs_leader") or {}).get("verdict") == "untestable"
    ]:
        out.setdefault(x, []).append("shares fewer than 2 items with the leader")
        why.append(f"{arms[x]['label']} is out: shares fewer than 2 items with the leader.")
        eligible.remove(x)
    # WHO IS TIED WITH THE LEADER is the strategy's call (STRATEGIES); the tie-break then picks.
    strategy = strategy_of(goal)
    top = rows[leader]["quality"]["value"]
    values = [rows[x]["quality"]["value"] for x in eligible]
    if quality.get("margin") is not None:
        margin, margin_from = float(quality["margin"]), " (the goal's margin)"
    elif top != 0:
        margin, margin_from = abs(top) * DEFAULT_MARGIN, f" ({DEFAULT_MARGIN:.0%} of the leader)"
    else:
        # A perfect 0 on a lower-is-better measure: 2% of 0 ties nothing, so the share is of the
        # spread between the best and the worst eligible arm.
        margin = (max(values) - min(values)) * DEFAULT_MARGIN
        margin_from = f" ({DEFAULT_MARGIN:.0%} of the group's range, the leader being 0)"
        if len(eligible) == 2:
            # With one other arm the range is the gap itself, so a share of it never ties: say how.
            margin_from += "; with one other arm that ties nothing, so set axes.quality.margin"
    # Identical per-item scores are tied in every strategy: there is nothing to separate.
    unseparated = [
        x
        for x in eligible
        if x != leader
        and (rows[x]["quality"].get("vs_leader") or {}).get("verdict") in ("not separated", "identical")
    ]
    if strategy == "frugal":
        close = unseparated
        rule = "not separated by the paired test"
    elif strategy == "quality_first":
        close = [
            x
            for x in eligible
            if x != leader
            and (
                rows[x]["quality"]["value"] == top
                or (rows[x]["quality"].get("vs_leader") or {}).get("verdict") == "identical"
            )
        ]
        rule = "the same quality"
    else:
        close = [x for x in unseparated if abs(top - rows[x]["quality"]["value"]) <= margin]
        rule = f"not separated by the paired test and within {_num(margin)}{margin_from}"
    tied = [leader, *close]
    why.append(
        f"Strategy {strategy}. Quality leader: {arms[leader]['label']} ({quality['measure']} {_num(top)}). "
        f"Tied with it ({rule}): "
        + (", ".join(arms[x]["label"] for x in close) if close else "none")
        + "."
        + (
            f" Not separated but further off, so not tied: {', '.join(arms[x]['label'] for x in unseparated if x not in close)}."
            if strategy == "balanced" and len(close) < len(unseparated)
            else ""
        )
    )
    pick = list(tied)
    for name in tie_break_of(goal):
        if len(pick) == 1:
            break
        tb = next((a for a in axes if a["name"] == name), None)
        if tb is None:
            continue
        if name == "speed" and not one_machine:
            why.append("Speed was not used to break the tie: the arms ran on different machines.")
            continue
        missing = [x for x in pick if rows[x][name]["value"] is None]
        if missing:
            # A number nobody has is not a win for the arm that has one: an unpriced hosted call
            # must not lose on cost to a priced one.
            why.append(
                f"{name} is not recorded for {', '.join(arms[x]['label'] for x in missing)}: "
                "it cannot break the tie."
            )
            continue
        best = (min if tb["direction"] == "lower" else max)(rows[x][name]["value"] for x in pick)
        keep = [x for x in pick if rows[x][name]["value"] == best]
        if len(keep) < len(pick):
            why.append(
                f"By {name} ({tb['measure']}{' ' + tb['stat'] if tb['stat'] != 'mean' else ''}): "
                + ", ".join(
                    f"{arms[x]['label']} {value_text(tb, rows[x][name]['value'])}"
                    for x in sorted(pick, key=lambda x: rows[x][name]["value"])
                )
                + "."
            )
        pick = keep
    recommended = pick[0] if len(pick) == 1 else None
    if recommended:
        why.append(f"Recommended: {arms[recommended]['label']}.")
    else:
        why.append("Still tied after the tie-break: " + ", ".join(arms[x]["label"] for x in pick) + ".")
    return {
        "axes": axes,
        "rows": rows,
        "out": out,
        "eligible": eligible,
        "leader": leader,
        "tied": tied,
        "recommended": recommended,
        "why": why,
    }


def _none_eligible(arms: dict, rows: dict, out: dict) -> str:
    """Why no arm can be recommended, counted by reason: "every arm is flagged: n 31 < min_items 32
    (5 arms)", not a list of everything that could have happened."""
    flagged: dict[str, int] = {}
    unscored = 0
    for a in arms:
        if a in out:
            continue
        for f in arms[a].get("flags") or []:
            flagged[f] = flagged.get(f, 0) + 1
        if not arms[a].get("flags") and rows[a]["quality"]["value"] is None:
            unscored += 1
    parts = [f"{len(out)} over a limit (above)"] if out else []
    parts += [
        f"{f} ({n} arm{'s' if n > 1 else ''})" for f, n in sorted(flagged.items(), key=lambda kv: -kv[1])
    ]
    if unscored:
        parts.append(f"no quality score ({unscored} arm{'s' if unscored > 1 else ''})")
    return "No arm is eligible: " + "; ".join(parts) + "."


def value_text(axis: dict, v: float | None) -> str:
    """One value on an axis, in its unit: dollars for cost, milliseconds for latency."""
    if v is None:
        return "not recorded"
    if axis["name"] == "cost" and axis["measure"] == "cost_usd":
        return f"${v:.6f}"
    if axis["name"] == "speed" and axis["measure"] == "latency_ms":
        return f"{v:,.0f} ms"
    return _num(v) + (f" {axis['unit']}" if axis.get("unit") else "")


def cell_text(axis: dict, cell: dict) -> str:
    """One arm's value on one axis, in words for a table: cost as USD and tokens per item, speed as
    p50 and p95, a project axis as its statistic. "not recorded" when the arm has no number."""
    if axis["name"] == "cost" and axis["measure"] == "cost_usd":
        tok = (cell.get("tokens") or {}).get("mean")
        usd = f"${cell['mean']:.6f}" if cell.get("mean") is not None else ""
        both = " · ".join(x for x in (usd, f"{tok:,.0f} tok" if tok is not None else "") if x)
        return both or "not recorded"
    if cell.get("n", 0) == 0:
        return "not recorded"
    if axis["name"] == "speed" and axis["measure"] == "latency_ms":
        return f"p50 {_ms(cell['p50'])} · p95 {_ms(cell['p95'])} ms"
    stat = "" if axis["stat"] == "mean" else f"{axis['stat']} "
    return f"{stat}{_num(cell['value'])}" + (f" {axis['unit']}" if axis.get("unit") else "")


def axis_title(axis: dict) -> str:
    """The axis as a column head: its name, the measure when it is not the default, the limit."""
    base = BUILTIN.get(axis["name"], {})
    head = axis["name"] + (
        f" ({axis['measure']})" if axis["measure"] != base.get("measure", axis["name"]) else ""
    )
    if axis["name"] in BUILTIN and axis["measure"] == base["measure"]:
        head += " per item"  # the cost of one item, not of the run
    if axis.get("limit") is not None:
        op = "≤" if axis["direction"] == "lower" else "≥"
        head += f" · limit {op} {_num(float(axis['limit']))}"
    return head


def _ms(v: float) -> str:
    """Milliseconds: whole above 10, else significant digits (a keyword match takes 0.03 ms, not 0)."""
    return f"{v:,.0f}" if v >= 10 else f"{v:.2g}"


def _num(v: float | None) -> str:
    if v is None:
        return "—"
    if abs(v) >= 100:
        return f"{v:,.0f}"
    if abs(v) >= 1:
        return f"{v:.2f}"
    return f"{v:.4g}"
