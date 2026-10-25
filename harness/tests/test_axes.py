#!/usr/bin/env python3
"""A goal's axes and its decision: limits, the quality leader, the tie, the tie-break. $0, offline.

python tests/test_axes.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
from evaluation_harness import _axes
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

ax = _axes.axes_of(GOAL)
check(
    "axes: quality, then cost and speed built in, with their measures and statistics",
    [(a["name"], a["measure"], a["stat"]) for a in ax]
    == [("quality", "q", "mean"), ("cost", "cost_usd", "mean"), ("speed", "latency_ms", "p95")],
    str(ax),
)
check("a percentile between ranks", _axes.percentile([1, 2, 3, 4], 50) == 2.5)

# A big quality gap: the leader wins outright.
strong = [0.9 + 0.001 * k for k in range(12)]
weak = [0.2] * 12
d = _axes.decide(GOAL, {"a": arm("A", strong, 0.01, 100), "b": arm("B", weak, 0.001, 50)})
check(
    "decide: a separated leader is recommended, whatever it costs",
    d["leader"] == "a" and d["tied"] == ["a"] and d["recommended"] == "a",
    d["why"],
)

# A quality tie: the cheaper one wins; equal cost goes to speed.
near = [0.9 + 0.001 * k + (0.0005 if k % 2 else -0.0005) for k in range(12)]
d = _axes.decide(GOAL, {"a": arm("A", strong, 0.01, 100), "b": arm("B", near, 0.001, 300)})
check(
    "decide: arms not separated on quality are tied, and the cheaper is recommended",
    d["tied"] == ["a", "b"] or set(d["tied"]) == {"a", "b"},
    d["why"],
)
check("decide: ... recommended by cost", d["recommended"] == "b", d["why"])
d = _axes.decide(GOAL, {"a": arm("A", strong, 0.0, 100), "b": arm("B", near, 0.0, 300)})
check("decide: equal cost (both free) falls to speed", d["recommended"] == "a", d["why"])
d = _axes.decide(
    {**GOAL, "success_criteria": {**GOAL["success_criteria"], "tie_break": ["speed", "cost"]}},
    {"a": arm("A", strong, 0.01, 300), "b": arm("B", near, 0.001, 100)},
)
check("decide: the goal's tie-break order (speed first) is followed", d["recommended"] == "b", d["why"])

# Limits disqualify, with the reason.
limited = {"success_criteria": {**GOAL["success_criteria"], "axes": {"speed": {"limit": 200}}}}
d = _axes.decide(limited, {"a": arm("A", strong, 0.01, 500), "b": arm("B", weak, 0.001, 50)})
check(
    "decide: an arm over a speed limit (on its p95) is out, and the reason is said",
    d["out"].get("a") and "speed p95 500 ms > limit 200 ms" in d["out"]["a"][0] and d["recommended"] == "b",
    d["why"],
)
tail = [100] * 11 + [5000]
d = _axes.decide(limited, {"a": arm("A", strong, 0.01, tail)})
check("decide: a slow tail breaks a p95 limit the mean would pass", "a" in d["out"], d["rows"]["a"]["speed"])

# Missing numbers are not recorded, never 0, never a reason to drop an arm.
d = _axes.decide(limited, {"a": arm("A", strong, None, None), "b": arm("B", near, 0.001, 100)})
check(
    "decide: an arm with no cost or latency is not out for it, and is tied-broken after the known",
    "a" not in d["out"] and d["rows"]["a"]["cost"]["value"] is None and d["recommended"] == "b",
    d["why"],
)

# Flagged arms are shown, never recommended.
d = _axes.decide(
    GOAL, {"a": arm("A", strong, 0.0001, 10, flags=["wrote the reference"]), "b": arm("B", weak, 0.01, 50)}
)
check("decide: a flagged arm is never the leader", d["leader"] == "b", d["why"])

# Different machines: speed neither compared nor used to break a tie.
d = _axes.decide(
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
d = _axes.decide(
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
    _axes.axes_of({"success_criteria": {**GOAL["success_criteria"], "axes": {"wer": {}}}}, lambda m: "lower")[
        -1
    ]["direction"]
    == "lower",
)
ignored = {"success_criteria": {**GOAL["success_criteria"], "axes": {"speed": {"role": "ignore"}}}}
d = _axes.decide(ignored, {"a": arm("A", strong, 0.0, 100), "b": arm("B", near, 0.0, 300)})
check(
    "decide: an axis the goal ignores is neither shown nor used (an overnight batch: speed)",
    "speed" not in d["rows"]["a"] and d["recommended"] is None,
    d["why"],
)
d = _axes.decide(
    GOAL, {"a": arm("A", strong, 0.0, 100, tokens=500), "b": arm("B", weak, 0.0, 50, tokens=100)}
)
check("cost: tokens per item shown beside the dollars", d["rows"]["a"]["cost"]["tokens"]["mean"] == 500)

# The strategies, on the case that made them: 32 items, a 1.000 leader and a free 0.875 arm the
# paired test cannot separate from it (4 items differ).
ITEMS[:] = [f"m{k:02d}" for k in range(32)]
top = [1.0] * 32
cheap = [1.0] * 28 + [0.0] * 4
pair = {"a": arm("Opus", top, 0.0025, 3000), "k": arm("keywords", cheap, 0.0, 1)}


def with_criteria(**extra):
    return {"success_criteria": {**GOAL["success_criteria"], **extra}}


d = _axes.decide(GOAL, pair)
check(
    "balanced (default): not separated but 0.125 off is not tied; the leader is recommended",
    d["rows"]["k"]["quality"]["vs_leader"]["verdict"] == "not separated" and d["recommended"] == "a",
    d["why"],
)
check(
    "balanced: the reason says it was too far off to tie", any("further off" in w for w in d["why"]), d["why"]
)
d = _axes.decide(with_criteria(strategy="frugal"), pair)
check(
    "frugal: anything the test cannot separate is tied, and the cheaper wins",
    d["recommended"] == "k",
    d["why"],
)
d = _axes.decide(with_criteria(axes={"quality": {"margin": 0.15}}), pair)
check(
    "balanced with the goal's margin (0.15): the free arm is tied, and wins on cost",
    d["recommended"] == "k",
    d["why"],
)
d = _axes.decide(with_criteria(strategy="quality_first", axes={"quality": {"margin": 0.15}}), pair)
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

# The home page's glance: the recommendation against the baseline, as ratios.
from evaluation_harness.catalog_build import axis_ratios  # noqa: E402

d = _axes.decide(GOAL, {"a": arm("A", top, 0.01, 200), "b": arm("B", top, 0.001, 100)})
check(
    "ratios: the arm against the baseline per axis, the statistic named",
    axis_ratios(d, "a", "b") == ["cost 10×", "speed p95 2×"],
    str(axis_ratios(d, "a", "b")),
)
d = _axes.decide(GOAL, {"a": arm("A", top, 0.0, 200), "b": arm("B", top, 0.0, None)})
check(
    "ratios: two zeros read same; an axis the baseline does not record is left out",
    axis_ratios(d, "a", "b") == ["cost same"],
    str(axis_ratios(d, "a", "b")),
)
check("ratios: none for the baseline itself", axis_ratios(d, "b", "b") == [])

sys.exit(summary())
