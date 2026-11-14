#!/usr/bin/env python3
"""What a judging pass may spend (RFC-032 step 7): the smallest of its scorer's `cost_cap_usd`, judging's own
`EVAL_JUDGE_MAX_COST_USD` and a command's `EVAL_MAX_COST_USD` (a job's max_cost_usd); judging is never charged to a
round's budget (owner, 2026-11-14: judging keeps its own budget and its own keys).

    python tests/test_judge_cap.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import judge_score as js
from evaluation_harness._check import check, summary

KEYS = ("EVAL_JUDGE_MAX_COST_USD", "EVAL_MAX_COST_USD")


def cap(scorer_cap: float | None, **env: str) -> float | None:
    """The cap a scorer with `scorer_cap` gets under `env` (only these two variables set)."""
    saved = {k: os.environ.pop(k, None) for k in KEYS}
    try:
        os.environ.update(env)
        return js.effective_cap({} if scorer_cap is None else {"cost_cap_usd": scorer_cap})
    finally:
        for k in KEYS:
            os.environ.pop(k, None)
            if (was := saved[k]) is not None:
                os.environ[k] = was


check("the scorer's cap alone", cap(1.0) == 1.0, cap(1.0))
check(
    "judging's own cap alone",
    cap(None, EVAL_JUDGE_MAX_COST_USD="2.5") == 2.5,
    cap(None, EVAL_JUDGE_MAX_COST_USD="2.5"),
)
check(
    "judging's cap below the scorer's wins; the scorer's below judging's wins",
    cap(5.0, EVAL_JUDGE_MAX_COST_USD="2") == 2.0 and cap(1.0, EVAL_JUDGE_MAX_COST_USD="2") == 1.0,
    [cap(5.0, EVAL_JUDGE_MAX_COST_USD="2"), cap(1.0, EVAL_JUDGE_MAX_COST_USD="2")],
)
check(
    "a command's cap (a job's max_cost_usd) still holds when judging's is larger",
    cap(5.0, EVAL_JUDGE_MAX_COST_USD="3", EVAL_MAX_COST_USD="0.5") == 0.5,
    cap(5.0, EVAL_JUDGE_MAX_COST_USD="3", EVAL_MAX_COST_USD="0.5"),
)
check("no cap anywhere: none (judge-score then refuses to call)", cap(None) is None, cap(None))
check(
    "the refusal names judging's own cap",
    "EVAL_JUDGE_MAX_COST_USD"
    in (Path(js.__file__).read_text(encoding="utf-8").split("no cost cap:", 1)[1][:120]),
    "",
)

sys.exit(summary())
