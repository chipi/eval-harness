"""What a judging pass needs from a judge, with no dependency outside this package.

`judge_score.py` used to borrow these from examples/summeval-judging/adapter.py and
examples/_shared/gateway.py, which an installed package does not have. They live here now:

  the task     `task_of`: what is judged, from the scorer's optional `task` block (the labels of
               the source and of the outputs, the dimensions, the scale). Without one it is
               SummEval's: an ARTICLE, numbered SUMMARIES, four dimensions on 1..5.
  prompt       `render_prompt` and `build_message`. A prompt with `{n}` has the count put there;
               one without is SummEval's, whose two count phrases are rewritten. At 16 summaries
               the message is byte-identical to the one SummEval's adapter builds (self-tested
               against it), so the validation a judge earned there still describes what is sent.
  parsing      `parse_block`: every dimension, exactly n numbers each, each inside the scale.
  statistics   `spearman`, `kendall_tau_b` (tie-corrected: a judge ties constantly).
  the call     `call_judge`: the provider the judge names (`provider:` in its params: openai,
               anthropic, openrouter or litellm), through the same `_providers` an arm's call
               uses. A judge reads its keys as EVAL_JUDGE_<NAME> first, then <NAME>, so judging
               can run on its own keys or share the experiments'.

`provider: fake` calls nothing and costs nothing: a deterministic stand-in for tests and for
trying a scorer end to end. It can never be validated (judge_score's gate refuses it), so
every number it produces is labelled "unvalidated judge".
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import hashlib
import json
import re
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from evaluation_harness import _providers
from evaluation_harness import stats as _stats

DIMS = ("coherence", "consistency", "fluency", "relevance")
FAKE = "fake"
COUNT = "{n}"

#: What a scorer without a `task` block judges: SummEval's task, which the committed
#: summarisation scorers and their judging sets were built on.
DEFAULT_TASK: dict[str, Any] = {
    "source_label": "ARTICLE",
    "output_label": "SUMMARIES",
    "dimensions": list(DIMS),
    "scale": [1, 5],
}


def task_of(scorer: dict[str, Any]) -> dict[str, Any]:
    """The scorer's `task` block over the defaults, checked. Raises ValueError on a bad one."""
    raw = scorer.get("task") or {}
    if not isinstance(raw, dict):
        raise ValueError("`task` must be a mapping")
    unknown = sorted(set(raw) - set(DEFAULT_TASK))
    if unknown:
        raise ValueError(f"`task` has unknown key(s) {unknown}; known: {sorted(DEFAULT_TASK)}")
    t = {**DEFAULT_TASK, **raw}
    for k in ("source_label", "output_label"):
        v = t[k]
        if not isinstance(v, str) or not v.strip() or "\n" in v or ":" in v:
            raise ValueError(f"task.{k} must be one line of text without ':', got {v!r}")
    dims = t["dimensions"]
    if (
        not isinstance(dims, list)
        or not dims
        or len(set(dims)) != len(dims)
        or not all(isinstance(d, str) and d.strip() for d in dims)
    ):
        raise ValueError(f"task.dimensions must be a list of distinct names, got {dims!r}")
    sc = t["scale"]
    # Whole numbers only: a judge rates on points, and a fractional bound such as [0.5, 3.5]
    # would make every integer reply at the bottom fall outside it.
    if (
        not isinstance(sc, list)
        or len(sc) != 2
        or not all(isinstance(x, int) and not isinstance(x, bool) for x in sc)
        or not sc[0] < sc[1]
    ):
        raise ValueError(f"task.scale must be [low, high], whole numbers with low < high, got {sc!r}")
    return {
        "source_label": t["source_label"],
        "output_label": t["output_label"],
        "dimensions": list(dims),
        "scale": [sc[0], sc[1]],
    }


# ── the prompt, generalised only in its count ────────────────────────────────
def render_prompt(base: str, n: int) -> str:
    """The prompt for `n` outputs. A prompt containing `{n}` gets the count there and nothing
    else changes. Otherwise it is SummEval's prompt, byte-identical to it when n == 16."""
    a, b = "16 numbered summaries", "a list of 16 integers"
    if COUNT in base:
        if a in base or b in base:
            raise SystemExit(
                f"the prompt has both {COUNT} and SummEval's fixed count phrases "
                f"({a!r} / {b!r}); the phrases would keep saying 16. Use one or the other"
            )
        return base.replace(COUNT, str(n))
    if n == 16:
        return base
    if a not in base or b not in base:
        raise SystemExit(
            f"the prompt has no {COUNT} where the count goes, and not SummEval's two "
            f"count phrases ({a!r}, {b!r}); it cannot be rendered for {n} outputs"
        )
    if n == 1:
        # Singular grammar, and an example showing one value per key: the 16-wide example
        # ("[3, 4, ...]") would invite a list that parse_block then rejects.
        ex = (
            '{"coherence": [3, 4, ...], "consistency": [5, 2, ...], '
            '"fluency": [4, 4, ...], "relevance": [2, 3, ...]}'
        )
        if ex not in base:
            raise SystemExit(
                "the prompt no longer contains the example line this pass rewrites for one summary"
            )
        return (
            base.replace(a, "1 numbered summary")
            .replace(b, "a list of 1 integer")
            .replace(ex, '{"coherence": [3], "consistency": [5], "fluency": [4], "relevance": [2]}')
            .replace("Rate every summary", "Rate the summary")
            .replace("the summaries may share mistakes", "the summary may contain mistakes")
            .replace("a list of 1 integer in summary order", "a list of 1 integer")
        )
    return base.replace(a, f"{n} numbered summaries").replace(b, f"a list of {n} integers")


def build_message(
    base: str,
    article: str,
    summaries: Sequence[str],
    source_label: str = "ARTICLE",
    output_label: str = "SUMMARIES",
) -> str:
    """The judge's input: the prompt for this many outputs, the source item, the numbered
    outputs. With the default labels, the layout of SummEval's `_judge_message`; references are
    left out on purpose (a judge shown them would be doing the code scorer's job)."""
    numbered = "\n".join(f"{i}. {s.strip()}" for i, s in enumerate(summaries, 1))
    return (
        f"{render_prompt(base, len(summaries))}\n\n{source_label}:\n{article.strip()}"
        f"\n\n{output_label}:\n{numbered}"
    )


_JSON = re.compile(r"\{.*\}", re.S)


def parse_block(
    output: str, n: int, dims: Sequence[str] = DIMS, scale: Sequence[float] = (1, 5)
) -> list[float] | None:
    """Per-output mean of the dimensions, or None.

    Lenient about wrapping (a fence, a sentence before the JSON), strict about content: a
    dimension counts only with exactly `n` numbers, and a block counts only with every
    dimension, each number inside the scale.
    """
    lo, hi = float(scale[0]), float(scale[1])
    m = _JSON.search(output or "")
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    cols = []
    for d in dims:
        v = obj.get(d)
        if not isinstance(v, list) or len(v) != n:
            return None
        # Numbers only: json gives True for `true`, and "4" is a string, neither a score.
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in v):
            return None
        f = [float(x) for x in v]
        if any(not (lo <= x <= hi) for x in f):
            return None
        cols.append(f)
    return [statistics.fmean(c[i] for c in cols) for i in range(n)]


# ── rank statistics ──────────────────────────────────────────────────────────
def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    """Spearman's rho (stats.spearman); 0.0 when either side is constant, as every judge report
    has stated it."""
    return _stats.spearman(a, b, constant=0.0)


def kendall_tau_b(a: list[float], b: list[float]) -> float:
    """Kendall's tau-b, which corrects for ties on both sides; 0 when either side is constant.

    An LLM judge gives integer scores 1-5, so it ties constantly, and tau-a would punish it
    for every tie as if it were a wrong ordering.
    """
    c = d = ta = tb = 0
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            x = (a[i] > a[j]) - (a[i] < a[j])
            y = (b[i] > b[j]) - (b[i] < b[j])
            if x == 0 and y == 0:
                continue
            if x == 0:
                ta += 1
            elif y == 0:
                tb += 1
            elif x == y:
                c += 1
            else:
                d += 1
    den = ((c + d + ta) * (c + d + tb)) ** 0.5
    return 0.0 if den == 0 else (c - d) / den


# ── quoting ──────────────────────────────────────────────────────────────────
#: A stored reply that repeats this many consecutive words of the item or an output is not
#: committed, only its hash: a judge that reasons aloud can copy the source text.
SHINGLE = 8


def _words(text: str | None) -> list[str]:
    # Word characters only: a quote inside a JSON string, or ending a sentence, is the same
    # eight words with or without the quote marks and commas around it.
    return re.findall(r"\w+", (text or "").lower())


def shingles(texts: Sequence[str]) -> set:
    """All 8-word shingles across multiple texts, lowercased."""
    out: set = set()
    for t in texts:
        w = _words(t)
        out.update(" ".join(w[i : i + SHINGLE]) for i in range(len(w) - SHINGLE + 1))
    return out


def quotes_source(output: str, source: set) -> bool:
    """Whether a reply repeats any SHINGLE consecutive words of the source texts."""
    w = _words(output)
    return any(" ".join(w[i : i + SHINGLE]) in source for i in range(len(w) - SHINGLE + 1))


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.S)


def json_only(output: str | None) -> bool:
    """A reply that is one JSON object and nothing else (a ```json fence allowed)."""
    t = (output or "").strip()
    m = _FENCE.match(t)
    t = m.group(1) if m else t
    if not (t.startswith("{") and t.endswith("}")):
        return False
    try:
        return isinstance(json.loads(t), dict)
    except json.JSONDecodeError:
        return False


def withheld_reason(output: str | None, source: set) -> str | None:
    """Why a reply must not be committed as text, or None. Only its hash is stored then: a
    reply that reasons aloud (not bare JSON) or repeats the source can carry the source's
    text, and validate checks every committed reply is bare JSON (V12)."""
    if output and quotes_source(output, source):
        return "repeats the source"
    if output and not json_only(output):
        return "not bare JSON"
    return None


# ── the call ─────────────────────────────────────────────────────────────────
@dataclass
class JudgeResult:
    """Result of a judge call: the output and token/cost metadata."""

    output: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    extra: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


def _fake_call(message: str, params: dict[str, Any]) -> JudgeResult:
    """Scores each numbered output on the task's scale from a hash of its text and the judge's
    model, so two fake judges disagree a little and a rerun reproduces itself. The task arrives
    in `params["_task"]` (judge_score puts it there for fake judges only)."""
    task = params.get("_task") or DEFAULT_TASK
    head = f"\n\n{task['output_label']}:\n"
    body = message.rsplit(head, 1)[1] if head in message else ""
    sums = re.findall(r"^\d+\. (.*)$", body, re.M)
    model = str(params.get("model", ""))
    lo, hi = int(task["scale"][0]), int(task["scale"][1])
    s = [lo + int(hashlib.sha256(f"{model}|{x}".encode()).hexdigest()[:8], 16) % (hi - lo + 1) for x in sums]
    out = json.dumps(dict.fromkeys(task["dimensions"], s))
    tin, tout = max(1, len(message) // 4), max(1, len(out) // 4)
    return JudgeResult(
        output=out,
        tokens_in=tin,
        tokens_out=tout,
        cost_usd=_providers.price(params, tin, tout),
        extra={"truncated": 0.0},
        meta={"finish_reason": "stop", "provider": FAKE, "response_model": model},
    )


def call_judge(message: str, params: dict[str, Any]) -> JudgeResult:
    """One judge reply to one message, from the provider the judge names (`_providers`, as an
    arm's call; its keys looked up as EVAL_JUDGE_<NAME> first). Retrying transient failures is
    the caller's job."""
    if params.get("provider") == FAKE:
        return _fake_call(message, params)
    c = _providers.complete(message, params, role="judge", max_tokens=1500)
    max_tokens = int(params.get("max_tokens", 1500))
    # A judgement cut off mid-JSON is a parse failure that would read as "this judge is
    # bad"; finish_reason says it was the token ceiling instead.
    truncated = c.finish_reason == "length" or (
        c.tokens_out is not None and c.tokens_out >= max_tokens * 0.98
    )
    return JudgeResult(
        output=c.text.strip(),
        tokens_in=c.tokens_in,
        tokens_out=c.tokens_out,
        cost_usd=c.cost_usd,
        extra={
            "truncated": 1.0 if truncated else 0.0,
            **({"reasoning_tokens": float(c.reasoning_tokens)} if c.reasoning_tokens is not None else {}),
        },
        meta={
            "usage": c.usage,
            "finish_reason": c.finish_reason,
            "response_model": c.response_model,
            "reasoning_tokens_reported": c.reasoning_tokens is not None,
            "provider": c.upstream_provider,
        },
    )
