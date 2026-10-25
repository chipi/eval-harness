"""THE INTEGRATION SEAM. This is the file you edit; the rest is bookkeeping.

You already have a system — a summariser, a classifier, an extractor, a RAG
chain. This file is where you hand it to the harness. Two functions:

    call_system(text, params)  -> what your system produces, plus what it cost
    score(output, reference)   -> how good that output was

Everything else — freezing datasets, hashing, provenance, timing, aggregation,
the refusals — is generic and does not change.

`call_system` returns a `Result`, and the fields beyond `output` are optional.
Return what your system can tell you; the harness records whatever arrives and
skips what does not. Cost and token counts are the difference between "model B
is better" and "model B is better and costs 4x", which is usually the actual
decision.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# The hosted providers, shared with the judges: one way to call them, read their keys and cost
# a call (the bill when the response carries one, else the config's prices, else unpriced).
from evaluation_harness import _providers


@dataclass
class Result:
    """What one call to your system produced, and what it cost."""

    output: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    extra: dict[str, float] = field(default_factory=dict)
    # Raw provider metadata, kept verbatim and never averaged: the `usage` object,
    # `finish_reason`, the model string the provider actually reports back. Anything
    # numeric belongs in `extra` (it becomes a metric); anything you want preserved
    # for forensics belongs here. Without this the harness could not answer "were
    # reasoning tokens billed?" or "was this output cut off at max_tokens?" -- both
    # of which silently corrupt a comparison.
    meta: dict[str, Any] = field(default_factory=dict)


# ── 1. YOUR SYSTEM ───────────────────────────────────────────────────────────
def call_system(text: str, params: dict[str, Any]) -> Result:
    """Run YOUR system over one item. Replace the body.

    `params` is whatever the experiment config put under `params:` — model name,
    temperature, prompt version, thresholds. Keep the knobs in the config, not
    in here, so an arm is a YAML file rather than a code edit.

    The default dispatches on `params["provider"]` so the bundled demo and the
    example adapters work out of the box:

        echo        no network, deterministic — proves the plumbing
        openai      OpenAI, or any OpenAI-compatible endpoint (`base_url`)
        anthropic   Anthropic
        openrouter  OpenRouter, asked for what it billed
        litellm     your own LiteLLM proxy: one key, many providers, central spend

    A real integration usually deletes all of this and calls one function:

        from myproject.summarise import summarise
        return Result(output=summarise(text, model=params["model"]))
    """
    provider = params.get("provider", "echo")
    # An unknown provider is an error. It fell back to echo, so a typo in a config recorded
    # the echoed input as that model's output.
    if provider not in PROVIDERS:
        raise SystemExit(f"unknown provider {provider!r}; this adapter knows {', '.join(sorted(PROVIDERS))}")
    fn: Callable[[str, dict[str, Any]], Result] = PROVIDERS[provider]
    started = time.perf_counter()
    # No retry wrapper here: the core retries every adapter. See the note below.
    result = fn(text, params)
    if result.latency_ms is None:
        result.latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return result


# RETRIES LIVE IN THE CORE, NOT HERE.
#
# `experiment_run` wraps every `call_system` in its own retry loop (EVAL_MAX_RETRIES), for
# every adapter. Do not add a second loop in an adapter: the two multiply, and a failing item
# on a paid provider is then attempted many times over. To make more errors retryable, declare
# `TRANSIENT_MARKERS` (substrings of the error message); the core honours them.


# ── 2. HOW GOOD WAS IT ───────────────────────────────────────────────────────
#: The metric that answers "which arm is better": recorded on every run, it is what the
#: leaderboard ranks by, the catalog's headline number and the inspector's default. Name
#: yours when you replace score(); without one they fall back to name order.
PRIMARY_METRIC = "overlap_f1"
#: A quality metric that improves going DOWN (WER, error rate) says so here, e.g.
#: METRIC_DIRECTIONS = {"wer": "lower"}. Costs, latencies and token counts already do; anything
#: else is taken to improve going up. Recorded on every run.


def score(output: str, reference: str | None) -> dict[str, float]:
    """Score one output. Replace with whatever "good" means for you.

    Called with the golden reference when one exists for the item, and with
    None when it does not — so the same adapter works before and after you have
    ground truth.

    The default is deliberately crude: token-overlap F1 against the reference,
    plus the output length. It is a placeholder that produces a real number so
    the loop runs end to end. Swap it for ROUGE, exact match, an embedding
    cosine, a rubric — whatever your domain actually rewards.

    Do not mistake the default for a metric you can defend in a decision.
    """
    out_len = float(len(output.split()))
    if reference is None:
        return {"output_words": out_len}
    a, b = set(output.lower().split()), set(reference.lower().split())
    if not a or not b:
        return {"output_words": out_len, "overlap_f1": 0.0}
    overlap = len(a & b)
    precision, recall = overlap / len(a), overlap / len(b)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {"output_words": out_len, "overlap_f1": f1}


# ── example adapters — delete the ones you do not use ────────────────────────
def _echo(text: str, params: dict[str, Any]) -> Result:
    """No network. Returns the first N sentences — a stand-in 'summary'.

    Deterministic BY DEFAULT: `--repeat 3` reports spread 0.000000, which is the
    reading you want to contrast against a real model.

    `noise` (0.0 default) makes it genuinely non-deterministic by dropping each word
    with that probability, so repeats differ in both output_words and overlap_f1.

    That parameter had to be added. `data/configs/demo_noisy.yaml` set `noise: 0.05`
    and described itself as showing "a non-zero spread — and `make run-compare` can
    flag a delta as noise", but nothing read the key: measured at REPEAT=3 it reported
    overlap_f1 spread=0.000000, deterministic. The bundled example for the harness's
    headline discipline — a delta below the arm's own jitter is not an improvement —
    demonstrated the opposite, silently, to anyone who followed the README.
    """
    n = int(params.get("sentences", 3))
    parts = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    out = ". ".join(parts[:n]) + ("." if parts else "")

    noise = float(params.get("noise", 0.0))
    if noise > 0.0:
        # Unseeded on purpose: a seeded "noisy" arm is just a slower deterministic one,
        # and the whole point is that two repeats of the SAME input disagree.
        kept = [w for w in out.split() if random.random() >= noise]
        # Never return nothing — an empty output scores 0.0 and would read as a broken
        # arm rather than a noisy one.
        out = " ".join(kept) or out
    return Result(output=out, cost_usd=0.0)


def _hosted(text: str, params: dict[str, Any]) -> Result:
    """A hosted model, through the harness's providers (openai, anthropic, openrouter, litellm):
    the arm's `prompt`, then the item. Keys, addresses and cost: `evaluation_harness._providers`."""
    c = _providers.complete(
        params.get("prompt", "Summarise:") + "\n\n" + text, params, role="arm", max_tokens=600
    )
    return Result(
        output=c.text,
        tokens_in=c.tokens_in,
        tokens_out=c.tokens_out,
        cost_usd=c.cost_usd,
        extra={**({"reasoning_tokens": float(c.reasoning_tokens)} if c.reasoning_tokens is not None else {})},
        # "length" means the output stopped at max_tokens; experiment-run warns about it. The bill,
        # when the provider sent one, is kept where cost-report and rescore read it.
        meta={
            **({"finish_reason": c.finish_reason} if c.finish_reason else {}),
            **({"usage": {"cost": c.cost_usd}} if c.billed else {}),
            **({"response_model": c.response_model} if c.response_model else {}),
            **({"provider": c.upstream_provider} if c.upstream_provider else {}),
        },
    )


PROVIDERS: dict[str, Callable[[str, dict[str, Any]], Result]] = {
    "echo": _echo,
    **dict.fromkeys(_providers.PROVIDERS, _hosted),
}
