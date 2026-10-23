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

import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

# One price rule and one bill reader, shared with the judges: what the provider billed when
# the response carries it, else the config's declared prices, else unpriced (None).
from judging import billed, price


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
        litellm     a LiteLLM proxy: ONE key, many providers, central spend
        anthropic   Claude via the official SDK
        openai      anything OpenAI-compatible, including OpenRouter

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
# This adapter used to carry its own `_with_retries` loop, and `experiment_run` wraps
# every `call_system` in `call_with_retries` as well. Both read EVAL_MAX_RETRIES, both
# default to 8 -- so a genuinely failing item was attempted 8 x 8 = 64 times, with both
# backoffs compounding. On a paid provider that multiplies the bill for the one item
# least likely to ever succeed.
#
# The core's loop is the one to keep: it applies to EVERY adapter whether or not its
# author wrote retries, which was the reason it was added. An adapter that wants extra
# retryable signatures declares `TRANSIENT_MARKERS` and the core honours them -- that is
# the supported way to extend this, and it cannot multiply attempts.
#
# Found by external review.


# ── 2. HOW GOOD WAS IT ───────────────────────────────────────────────────────
#: The metric that answers "which arm is better": recorded on every run, it is what the
#: leaderboard ranks by, the catalog's headline number and the inspector's default. Name
#: yours when you replace score(); without one they fall back to name order.
PRIMARY_METRIC = "overlap_f1"


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
    return {"output_words": out_len, "overlap_f1": round(f1, 6)}


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


def _anthropic(text: str, params: dict[str, Any]) -> Result:
    import anthropic  # imported lazily so the demo needs no SDK  # noqa: PLC0415

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is not set")
    client = anthropic.Anthropic(api_key=key)
    model = params.get("model", "claude-sonnet-4-6")
    msg = client.messages.create(
        model=model,
        max_tokens=int(params.get("max_tokens", 600)),
        messages=[{"role": "user", "content": params.get("prompt", "Summarise:") + "\n\n" + text}],
        # The SDK dropped the `temperature` keyword in 1.x; the body carries it, so the request
        # is the same one every SDK version sends.
        extra_body={"temperature": float(params.get("temperature", 0.0))},
    )
    usage = getattr(msg, "usage", None)
    ti = getattr(usage, "input_tokens", None)
    to = getattr(usage, "output_tokens", None)
    return Result(
        output="".join(b.text for b in msg.content if b.type == "text"),
        tokens_in=ti,
        tokens_out=to,
        cost_usd=price(params, ti, to),
    )


def _litellm(text: str, params: dict[str, Any]) -> Result:
    """A LiteLLM proxy — one key, many providers, spend tracked centrally.

    Usually the best answer for a sweep: the proxy already holds the provider
    keys, so the harness carries ONE credential instead of four, and every call
    lands in the proxy's spend log under this key's alias. Point `.env` at it:

        LITELLM_BASE_URL=http://127.0.0.1:4001
        LITELLM_API_KEY=sk-...

    `model` is the proxy's model_name, not the upstream id — the mapping from
    `eval-claude-sonnet` to `openrouter/anthropic/...` is the proxy's business,
    which is the point of putting it there.
    """
    params = {
        **params,
        "base_url": (params.get("base_url") or os.environ.get("LITELLM_BASE_URL", "")).rstrip("/") + "/v1",
        "api_key_env": params.get("api_key_env", "LITELLM_API_KEY"),
    }
    if not params["base_url"].startswith("http"):
        raise SystemExit(
            "LITELLM_BASE_URL is not set. Copy .env.example to .env and point it at "
            "your proxy, e.g. http://127.0.0.1:4001"
        )
    return _openai_compatible(text, params)


def _openai_compatible(text: str, params: dict[str, Any]) -> Result:
    """OpenAI-shaped APIs, including OpenRouter — set `base_url` in params."""
    from openai import OpenAI  # lazy  # noqa: PLC0415

    env_key = params.get("api_key_env", "OPENAI_API_KEY")
    key = os.environ.get(env_key)
    if not key:
        raise SystemExit(f"{env_key} is not set")
    client = OpenAI(api_key=key, base_url=params.get("base_url") or None)
    resp = client.chat.completions.create(
        model=params["model"],
        temperature=float(params.get("temperature", 0.0)),
        max_tokens=int(params.get("max_tokens", 600)),
        messages=[{"role": "user", "content": params.get("prompt", "Summarise:") + "\n\n" + text}],
        # OpenRouter returns what it billed only when asked; the bill outranks the price table.
        extra_body={"usage": {"include": True}} if params.get("provider") == "openrouter" else None,
    )
    u = getattr(resp, "usage", None)
    ti = getattr(u, "prompt_tokens", None)
    to = getattr(u, "completion_tokens", None)
    bill = billed(u)
    return Result(
        output=resp.choices[0].message.content or "",
        tokens_in=ti,
        tokens_out=to,
        # Prices in the config, not in code: they change, and a run records what it was
        # costed at. A bill, when the provider sends one, is the cost itself.
        cost_usd=bill if bill is not None else price(params, ti, to),
    )


PROVIDERS: dict[str, Callable[[str, dict[str, Any]], Result]] = {
    "echo": _echo,
    "anthropic": _anthropic,
    "openai": _openai_compatible,
    "openrouter": _openai_compatible,
    "litellm": _litellm,
}
