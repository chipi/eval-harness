#!/usr/bin/env python3
"""evh arm-smoke (RFC-020): the calls it reads, the projection, and every flag.

python tests/test_arm_smoke.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import arm_smoke
from evaluation_harness._check import check, summary

# the calls an item made: an adapter's list, a built-in provider's single call, or none
listed = SimpleNamespace(meta={"calls": [{"s": 1.0, "tokens_out": 40}]}, output="x", latency_ms=1000)
check(
    "calls: an adapter's meta['calls'] as it is", arm_smoke.calls_of(listed) == [{"s": 1.0, "tokens_out": 40}]
)
single = SimpleNamespace(
    meta={
        "finish_reason": "length",
        "usage": {"completion_tokens": 900, "completion_tokens_details": {"reasoning_tokens": 700}},
    },
    output="",
    latency_ms=2500,
    tokens_out=None,
)
got = arm_smoke.calls_of(single)[0]
check(
    "calls: a built-in provider's one call, from its _meta",
    got["s"] == 2.5
    and got["tokens_out"] == 900
    and got["reasoning_tokens"] == 700
    and got["finish_reason"] == "length"
    and got["answered"] is False,
    got,
)
check(
    "calls: an ML adapter's result has none",
    arm_smoke.calls_of(SimpleNamespace(meta={"device": "cpu"}, output="y")) == [],
)

# the projection
proj = arm_smoke.projection([{"s": 6.0, "cost_usd": 0.001}, {"s": 12.0, "cost_usd": 0.003}], 65)
check(
    "projection: mean and slowest times all items, mean cost",
    proj == {"items": 65, "minutes": 9.8, "worst_minutes": 13.0, "usd": 0.13},
    proj,
)

# the flags
clean_items = [{"s": 5.0, "output_chars": 300, "scored": True, "deterministic": True}]
clean_calls = [
    {"s": 5.0, "tokens_out": 120, "reasoning_tokens": 0, "finish_reason": "stop", "answered": True}
]
check(
    "flags: a clean arm raises none",
    arm_smoke.flags_for(clean_items, clean_calls, {"call_timeout_s": 30, "reasoning_effort": "none"}) == [],
)
bad_items: list[dict[str, Any]] = [
    {"s": 1.0, "error": "TimeoutError: timed out"},
    {"s": 1.0, "output_chars": 0},
    {"s": 1.0, "output_chars": 10, "scored": False, "score_error": "KeyError"},
]
bad_items[0]["deterministic"] = False
normal = {"s": 2.0, "tokens_out": 100, "reasoning_tokens": 0, "finish_reason": "stop", "answered": True}
bad_calls = [
    {"s": 20.0, "tokens_out": 900, "reasoning_tokens": 500, "finish_reason": "length", "answered": False},
    normal,
    normal,
    normal,
]
text = " ".join(arm_smoke.flags_for(bad_items, bad_calls, {"call_timeout_s": 30, "_build_pinned": False}))
for word in (
    "runs:",
    "valid output:",
    "determinism:",
    "where it ran:",
    "reasoning:",
    "slow call:",
    "long reply:",
    "cut off:",
    "no answer:",
):
    check(f"flags: {word[:-1]} is raised", word in text, text)
check(
    "flags: reasoning is not flagged when the arm sets reasoning_effort",
    "reasoning:" not in " ".join(arm_smoke.flags_for(clean_items, bad_calls, {"reasoning_effort": "high"})),
)

summaries = [{**normal, "tokens_out": n} for n in (700, 800, 900)]
check(
    "flags: long is relative to the arm's own replies; a summarising arm's are all long, none is flagged",
    not any(
        "long reply" in f for f in arm_smoke.flags_for(clean_items, summaries, {"reasoning_effort": "none"})
    ),
)
check(
    "flags: with fewer calls than a median needs, no reply is called long",
    not any(
        "long reply" in f
        for f in arm_smoke.flags_for(clean_items, bad_calls[:1], {"reasoning_effort": "none"})
    ),
)

# with a reply cap, long is half the cap: a fleet's short probe calls beside its answers made every answer look long
fleet = [{**normal, "tokens_out": n} for n in (20, 20, 20, 20, 300, 350)]
check(
    "flags: with a reply cap, answers under half the cap are not long, however short the other calls",
    not any(
        "long reply" in f
        for f in arm_smoke.flags_for(clean_items, fleet, {"reasoning_effort": "none", "max_tokens": 1024})
    ),
)
check(
    "flags: without a cap, the same calls are long against their median (the rule the cap replaces)",
    any("long reply" in f for f in arm_smoke.flags_for(clean_items, fleet, {"reasoning_effort": "none"})),
)
over = arm_smoke.flags_for(
    clean_items, [*fleet, {**normal, "tokens_out": 700}], {"reasoning_effort": "none", "max_tokens": 1024}
)
check(
    "flags: with a reply cap, a reply over half of it is long, naming the cap",
    any("long reply" in f and "1024" in f and "700" in f for f in over),
    over,
)

# a hosted deployment's route
served = [{"s": 1.0, "tokens_out": 50, "finish_reason": "stop", "answered": True, "upstream": "novita"}]
check(
    "flags: a call served by an upstream the deployment's route does not pin is raised, naming both",
    any(
        "route:" in f and "novita" in f and "nebius" in f
        for f in arm_smoke.flags_for(clean_items, served, {"_route": ["nebius"], "reasoning_effort": "none"})
    ),
)
check(
    "flags: a call served by the pinned upstream, or with no route pinned, raises nothing",
    arm_smoke.flags_for(clean_items, served, {"_route": ["novita"], "reasoning_effort": "none"}) == []
    and arm_smoke.flags_for(clean_items, served, {"reasoning_effort": "none"}) == [],
)
check(
    "route_of: a list, or the provider's routing object (only, else order), else nothing",
    arm_smoke.route_of({"provider_routing": ["a", "b"]}) == ["a", "b"]
    and arm_smoke.route_of({"provider_routing": {"only": ["a"], "order": ["b"]}}) == ["a"]
    and arm_smoke.route_of({"provider_routing": {"order": ["b"]}}) == ["b"]
    and arm_smoke.route_of({}) == []
    and arm_smoke.route_of(None) == [],
)
check(
    "calls_of: the upstream a call reports is kept",
    arm_smoke.calls_of(SimpleNamespace(meta={"finish_reason": "stop", "provider": "novita"}, output="y"))[0][
        "upstream"
    ]
    == "novita",
)

sys.exit(summary())
