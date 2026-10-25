#!/usr/bin/env python3
"""A goal's axes and its decision: limits, the quality leader, the tie, the tie-break. $0, offline.

python tests/test_axes.py
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
from evaluation_harness import axes
from evaluation_harness._check import check, summary

ITEMS = [f"i{k:02d}" for k in range(12)]


def arm(label, quality, cost=None, latency=None, tokens=None, flags=(), **extra):
    """An arm with per-item scores: `quality` and the rest are per-item lists or a constant."""

    def series(v):
        if v is None:
            return None
        vals = v if isinstance(v, list) else [v] * len(ITEMS)
        return {"values": dict(zip(ITEMS, vals))}

    sc = {"q": series(quality), "cost_usd": series(cost), "latency_ms": series(latency)}
    if tokens is not None:
        sc["tokens_in"] = series(tokens)
        sc["tokens_out"] = series(0)
    for k, v in extra.items():
        sc[k] = series(v)
    return {"label": label, "flags": list(flags), "scores": {k: v for k, v in sc.items() if v}}


GOAL = {"success_criteria": {"primary": {"measure": "q", "direction": "higher"}}}

ax = axes.axes_of(GOAL)
check(
    "axes: quality, then cost and speed built in, with their measures and statistics",
    [(a["name"], a["measure"], a["stat"]) for a in ax]
    == [("quality", "q", "mean"), ("cost", "cost_usd", "mean"), ("speed", "latency_ms", "p95")],
    str(ax),
)
check("a percentile between ranks", axes.percentile([1, 2, 3, 4], 50) == 2.5)

# A big quality gap: the leader wins outright.
strong = [0.9 + 0.001 * k for k in range(12)]
weak = [0.2] * 12
d = axes.decide(GOAL, {"a": arm("A", strong, 0.01, 100), "b": arm("B", weak, 0.001, 50)})
check(
    "decide: a separated leader is recommended, whatever it costs",
    d["leader"] == "a" and d["tied"] == ["a"] and d["recommended"] == "a",
    d["why"],
)

# A quality tie: the cheaper one wins; equal cost goes to speed.
near = [0.9 + 0.001 * k + (0.0005 if k % 2 else -0.0005) for k in range(12)]
d = axes.decide(GOAL, {"a": arm("A", strong, 0.01, 100), "b": arm("B", near, 0.001, 300)})
check(
    "decide: arms not separated on quality are tied, and the cheaper is recommended",
    d["tied"] == ["a", "b"] or set(d["tied"]) == {"a", "b"},
    d["why"],
)
check("decide: ... recommended by cost", d["recommended"] == "b", d["why"])
d = axes.decide(GOAL, {"a": arm("A", strong, 0.0, 100), "b": arm("B", near, 0.0, 300)})
check("decide: equal cost (both free) falls to speed", d["recommended"] == "a", d["why"])
d = axes.decide(
    {**GOAL, "success_criteria": {**GOAL["success_criteria"], "tie_break": ["speed", "cost"]}},
    {"a": arm("A", strong, 0.01, 300), "b": arm("B", near, 0.001, 100)},
)
check("decide: the goal's tie-break order (speed first) is followed", d["recommended"] == "b", d["why"])

# Limits disqualify, with the reason.
limited = {"success_criteria": {**GOAL["success_criteria"], "axes": {"speed": {"limit": 200}}}}
d = axes.decide(limited, {"a": arm("A", strong, 0.01, 500), "b": arm("B", weak, 0.001, 50)})
check(
    "decide: an arm over a speed limit (on its p95) is out, and the reason is said",
    d["out"].get("a") and "speed p95 500 ms > limit 200 ms" in d["out"]["a"][0] and d["recommended"] == "b",
    d["why"],
)
tail = [100] * 11 + [5000]
d = axes.decide(limited, {"a": arm("A", strong, 0.01, tail)})
check("decide: a slow tail breaks a p95 limit the mean would pass", "a" in d["out"], d["rows"]["a"]["speed"])

# Missing numbers are not recorded, never 0, never a reason to drop an arm, and an axis a tied arm
# does not record cannot break the tie (an unpriced hosted call must not lose on cost).
d = axes.decide(limited, {"a": arm("A", strong, None, None), "b": arm("B", near, 0.001, 100)})
check(
    "decide: an arm with no cost or latency is not out for it, and those axes cannot break its tie",
    "a" not in d["out"]
    and d["rows"]["a"]["cost"]["value"] is None
    and d["recommended"] is None
    and "cost is not recorded for A: it cannot break the tie." in d["why"],
    d["why"],
)
d = axes.decide(GOAL, {"a": arm("A", strong, None, 300), "b": arm("B", near, 0.001, 100)})
check(
    "decide: a skipped axis falls to the next (cost unknown for A, so speed decides)",
    d["recommended"] == "b" and any(w.startswith("By speed") for w in d["why"]),
    d["why"],
)

# Identical per-item scores are tied in every strategy, whatever order the arms come in.
same = [1.0] * 12
for strategy in ("balanced", "quality_first", "frugal"):
    for order in (("a", "b"), ("b", "a")):
        both = {"a": arm("A", same, 0.01, 100), "b": arm("B", same, 0.001, 100)}
        d = axes.decide(
            {"success_criteria": {**GOAL["success_criteria"], "strategy": strategy}},
            {k: both[k] for k in order},
        )
        check(
            f"decide ({strategy}, order {order}): identical scores are tied and the cheaper is recommended",
            set(d["tied"]) == {"a", "b"} and d["recommended"] == "b" and d["leader"] == "a",
            d["why"],
        )

# An arm measured on part of the set is out, with the counts: it cannot lead on 4 items of 20.
ITEMS[:] = [f"p{k:02d}" for k in range(20)]
full = arm("A", [0.8] * 20, 0.0, 100)
part = arm("B", [0.95] * 4 + [None] * 16, 0.0, 100)
part["scores"]["q"]["values"] = {k: v for k, v in part["scores"]["q"]["values"].items() if v is not None}
d = axes.decide(GOAL, {"a": full, "b": part})
check(
    "decide: an arm with fewer items than the group's most-measured is out, said with the counts",
    d["out"].get("b") == ["n 4 of 20 items"] and d["recommended"] == "a",
    d["why"],
)

# No items shared with the leader: the paired test cannot run, so the arm is out and says why.
ITEMS[:] = [f"x{k:02d}" for k in range(10)]
left = arm("A", [0.9] * 10, 0.0, 100)
ITEMS[:] = [f"y{k:02d}" for k in range(10)]
right = arm("B", [0.9] * 10, 0.0, 100)
d = axes.decide(GOAL, {"a": left, "b": right})
check(
    "decide: an arm sharing fewer than 2 items with the leader is out, with the reason",
    "shares fewer than 2 items with the leader" in (d["out"].get("b") or []) and d["recommended"] == "a",
    d["why"],
)

# A perfect 0 on a lower-is-better measure: the margin is a share of the group's range.
ITEMS[:] = [f"w{k:02d}" for k in range(12)]
lower = {"success_criteria": {"primary": {"measure": "q", "direction": "lower"}}}
d = axes.decide(
    lower,
    {
        "a": arm("A", [0.0] * 12, 0.01, 100),
        "b": arm("B", [0.0] * 11 + [0.012], 0.0, 100),
        "c": arm("C", [0.5] * 12, 0.0, 100),
    },
)
check(
    "decide: a leader at 0 takes its margin from the group's range, and says so",
    "b" in d["tied"]
    and d["recommended"] == "b"
    and any("of the group's range, the leader being 0" in w for w in d["why"]),
    d["why"],
)
d = axes.decide(lower, {"a": arm("A", [0.0] * 12, 0.01, 100), "b": arm("B", [0.0] * 11 + [0.012], 0.0, 100)})
check(
    "decide: a leader at 0 with one other arm says the goal must set its margin",
    any("set axes.quality.margin" in w for w in d["why"]),
    d["why"],
)
ITEMS[:] = [f"i{k:02d}" for k in range(12)]

# Flagged arms are shown, never recommended.
d = axes.decide(
    GOAL, {"a": arm("A", strong, 0.0001, 10, flags=["wrote the reference"]), "b": arm("B", weak, 0.01, 50)}
)
check("decide: a flagged arm is never the leader", d["leader"] == "b", d["why"])

# Different machines: speed neither compared nor used to break a tie.
d = axes.decide(
    GOAL,
    {"a": arm("A", strong, 0.0, 100), "b": arm("B", near, 0.0, 300)},
    machines={"a": "laptop", "b": "dgx"},
)
check(
    "decide: on different machines, speed is not compared and breaks no tie",
    d["recommended"] is None
    and d["rows"]["b"]["speed"]["vs_leader"]["verdict"].startswith("different machines")
    and any("different machines" in w for w in d["why"]),
    d["why"],
)

# A project's own axis: one line in the goal, then limited and tie-broken like the built-ins.
custom = {
    "success_criteria": {
        **GOAL["success_criteria"],
        "axes": {"grounded": {"measure": "grounded_rate", "direction": "higher", "limit": 0.8}},
        "tie_break": ["grounded", "cost"],
    }
}
d = axes.decide(
    custom,
    {
        "a": arm("A", strong, 0.001, 100, grounded_rate=0.95),
        "b": arm("B", near, 0.0001, 100, grounded_rate=0.85),
        "c": arm("C", near, 0.0, 100, grounded_rate=0.5),
    },
)
check(
    "decide: a custom axis takes a limit and a tie-break place like the built-ins",
    "c" in d["out"] and d["recommended"] == "a" and [x["name"] for x in d["axes"]][-1] == "grounded",
    d["why"],
)
check(
    "decide: a custom axis's direction comes from the project when the goal does not say",
    axes.axes_of({"success_criteria": {**GOAL["success_criteria"], "axes": {"wer": {}}}}, lambda m: "lower")[
        -1
    ]["direction"]
    == "lower",
)
ignored = {"success_criteria": {**GOAL["success_criteria"], "axes": {"speed": {"role": "ignore"}}}}
d = axes.decide(ignored, {"a": arm("A", strong, 0.0, 100), "b": arm("B", near, 0.0, 300)})
check(
    "decide: an axis the goal ignores is neither shown nor used (an overnight batch: speed)",
    "speed" not in d["rows"]["a"] and d["recommended"] is None,
    d["why"],
)
d = axes.decide(GOAL, {"a": arm("A", strong, 0.0, 100, tokens=500), "b": arm("B", weak, 0.0, 50, tokens=100)})
check("cost: tokens per item shown beside the dollars", d["rows"]["a"]["cost"]["tokens"]["mean"] == 500)

# The strategies, on the case that made them: 32 items, a 1.000 leader and a free 0.875 arm the
# paired test cannot separate from it (4 items differ).
ITEMS[:] = [f"m{k:02d}" for k in range(32)]
top = [1.0] * 32
cheap = [1.0] * 28 + [0.0] * 4
pair = {"a": arm("Opus", top, 0.0025, 3000), "k": arm("keywords", cheap, 0.0, 1)}


def with_criteria(**extra):
    return {"success_criteria": {**GOAL["success_criteria"], **extra}}


d = axes.decide(GOAL, pair)
check(
    "balanced (default): not separated but 0.125 off is not tied; the leader is recommended",
    d["rows"]["k"]["quality"]["vs_leader"]["verdict"] == "not separated" and d["recommended"] == "a",
    d["why"],
)
check(
    "balanced: the reason says it was too far off to tie", any("further off" in w for w in d["why"]), d["why"]
)
d = axes.decide(with_criteria(strategy="frugal"), pair)
check(
    "frugal: anything the test cannot separate is tied, and the cheaper wins",
    d["recommended"] == "k",
    d["why"],
)
d = axes.decide(with_criteria(axes={"quality": {"margin": 0.15}}), pair)
check(
    "balanced with the goal's margin (0.15): the free arm is tied, and wins on cost",
    d["recommended"] == "k",
    d["why"],
)
d = axes.decide(with_criteria(strategy="quality_first", axes={"quality": {"margin": 0.15}}), pair)
check(
    "quality_first: the margin does not matter, the best quality is recommended",
    d["recommended"] == "a",
    d["why"],
)
check(
    "the strategy is named in the reasons",
    any(w.startswith("Strategy quality_first") for w in d["why"]),
    d["why"],
)

# Nobody eligible: the reason is named and counted, not a list of what might have happened.
d = axes.decide(
    GOAL,
    {
        "a": arm("A", top, 0.0, 100, flags=["n 31 < min_items 32"]),
        "b": arm("B", cheap, 0.0, 100, flags=["n 31 < min_items 32"]),
    },
)
check(
    "decide: with no eligible arm, the reason names the flag and how many arms carry it",
    d["recommended"] is None and d["why"][-1] == "No arm is eligible: n 31 < min_items 32 (2 arms).",
    d["why"],
)

# The home page's glance: the recommendation against the baseline, as ratios.
from evaluation_harness.catalog_build import axis_ratios  # noqa: E402

d = axes.decide(GOAL, {"a": arm("A", top, 0.01, 200), "b": arm("B", top, 0.001, 100)})
check(
    "ratios: the arm against the baseline per axis, the statistic named",
    axis_ratios(d, "a", "b") == ["cost 10×", "speed p95 2×"],
    str(axis_ratios(d, "a", "b")),
)
d = axes.decide(GOAL, {"a": arm("A", top, 0.0, 200), "b": arm("B", top, 0.0, None)})
check(
    "ratios: two zeros read same; an axis the baseline does not record is left out",
    axis_ratios(d, "a", "b") == ["cost same"],
    str(axis_ratios(d, "a", "b")),
)
check("ratios: none for the baseline itself", axis_ratios(d, "b", "b") == [])

# The goal page's line when the rule and the promoted baseline disagree (catalog_build.baseline_gap).
from evaluation_harness.catalog_build import baseline_gap  # noqa: E402
from evaluation_harness.catalog_charts import LABEL_H, label_y  # noqa: E402


class Scores:
    """Just enough of a catalog adapter for baseline_gap: per-item scores by arm."""

    def __init__(self, arms):
        self.arms = arms

    def scores(self, arm):
        return self.arms[arm]["scores"]


ITEMS[:] = [f"g{k:02d}" for k in range(20)]
v2 = [0.6] * 14 + [0.2] * 6
v1 = [0.2] * 14 + [0.6] * 6
pair = {"v2": arm("v2", v2, 0.0, 100), "v1": arm("v1", v1, 0.0, 100)}
d = axes.decide(GOAL, pair)
rows = [{"arm": "v2", "label": "v2"}, {"arm": "v1", "label": "v1", "baseline": True}]
fake: Any = Scores(pair)
gap = baseline_gap(fake, d, rows, "q")
check(
    "baseline gap: when the rule recommends another arm than the baseline, the page says by how much and the test",
    d["recommended"] == "v2"
    and gap.startswith("Differs from the promoted baseline, v1: v2 is +0.160 on q")
    and "(p " in gap,
    gap,
)
check(
    "baseline gap: nothing to say when the baseline is the recommendation",
    baseline_gap(fake, d, [{"arm": "v2", "label": "v2", "baseline": True}, {"arm": "v1", "label": "v1"}], "q")
    == "",
)

# A judge's group decides on the judge's own score: the goal's quality margin (written for its own
# measure's scale) does not apply there.
from evaluation_harness.catalog_build import group_decision  # noqa: E402


class Judged(Scores):
    """The fake adapter, plus the direction a group decision asks for."""

    def lower_is_better(self, m, ds):
        return False


ITEMS[:] = [f"j{k:02d}" for k in range(20)]
judged = {"x": arm("X", [5.0] * 20, 0.01, 100), "y": arm("Y", [5.0] * 17 + [4.0] * 3, 0.0, 100)}
for a in judged.values():
    a["scores"]["judge_score"] = a["scores"].pop("q")
goal = {
    "goal_id": "g",
    "success_criteria": {
        "primary": {"measure": "q", "direction": "higher"},
        "axes": {"quality": {"margin": 0.5}},
    },
}
rows_j = [{"arm": k, "label": v["label"], "flags": []} for k, v in judged.items()]
jfake: Any = Judged(judged)
d = group_decision(jfake, goal, "ds", rows_j, "judge_score", {})
check(
    "judge group: the goal's quality margin (0.5, for its own measure) is not used on the judge's score",
    "y" not in d["tied"] and any("2% of the leader" in w for w in d["why"]),
    d["why"],
)

# The glance's group tier: the references listing first, else the reference id's own prefix.
from evaluation_harness.catalog_build import ref_tier  # noqa: E402

check(
    "ref tier: listed tier wins; an unlisted gold/ or silver/ id names its tier; anything else has none",
    ref_tier({"gold/x": "gold"}, "gold/x") == "gold"
    and ref_tier({}, "gold/x") == "gold"
    and ref_tier({}, "silver/x") == "silver"
    and ref_tier({}, "no reference") == "",
)

# Chart labels: a name that would cover one already placed moves a line; a clear one stays.
placed = [(100.0, 200.0, 50.0)]
check("labels: a clear spot is kept", label_y(80.0, 100.0, 200.0, placed, 10, 200) == 80.0)
moved = label_y(52.0, 150.0, 260.0, placed, 10, 200)
check("labels: an overlapping name moves at least a line away", abs(moved - 50.0) >= LABEL_H, moved)
check(
    "labels: names that do not overlap in x share a line",
    label_y(50.0, 210.0, 300.0, placed, 10, 200) == 50.0,
)

sys.exit(summary())
