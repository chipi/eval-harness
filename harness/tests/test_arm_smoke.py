#!/usr/bin/env python3
"""evh arm-smoke (RFC-020): the calls it reads, the projection, and every flag.

python tests/test_arm_smoke.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

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
bad_items = [
    {"s": 1.0, "error": "TimeoutError: timed out"},
    {"s": 1.0, "output_chars": 0},
    {"s": 1.0, "output_chars": 10, "scored": False, "score_error": "KeyError"},
]
bad_items[0]["deterministic"] = False
bad_calls = [
    {"s": 20.0, "tokens_out": 900, "reasoning_tokens": 500, "finish_reason": "length", "answered": False},
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

sys.exit(summary())
