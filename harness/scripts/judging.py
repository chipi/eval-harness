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
  the call     `call_judge`: an OpenAI-compatible client, routed as examples/_shared/gateway.py
               routes (below), billed cost read from the response, price table as the fallback.

ROUTING, in this order
  proxy   LITELLM_BASE_URL (or the judge's own `base_url`) + LITELLM_API_KEY (or the judge's
          `api_key_env`): the judge's `model` is sent as-is, the proxy owns the mapping.
  direct  OPENROUTER_API_KEY alone: `model` is an OpenRouter id (`vendor/model`), or an alias in
          a models table ($EVAL_MODELS_FILE, <project>/models.json, or the checkout's
          examples/models.json), and the request carries `usage: {include: true}` so the billed
          cost comes back.
  Neither is an error that names both.

`provider: fake` calls nothing and costs nothing: a deterministic stand-in for tests and for
trying a scorer end to end. It can never be validated (judge_score's gate refuses it), so
every number it produces is labelled "unvalidated judge".
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DIMS = ("coherence", "consistency", "fluency", "relevance")
OPENROUTER = "https://openrouter.ai/api/v1"
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
def _ranks(x: Sequence[float]) -> list[float]:
    order = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) ** 0.5


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    """Spearman's rho with average ranks for ties; 0 when either side is constant."""
    return _pearson(_ranks(a), _ranks(b))


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


# ── routing ──────────────────────────────────────────────────────────────────
def _models_table() -> dict[str, str]:
    """alias -> upstream id, from the first models file that exists; {} when none does."""
    try:  # imported as evaluation_harness.judging, or as a script beside _common.py
        from ._common import CODE, ROOT  # noqa: PLC0415
    except ImportError:
        from _common import CODE, ROOT  # noqa: PLC0415

    cands = [os.environ.get("EVAL_MODELS_FILE", "").strip(), ROOT / "models.json"]
    # The repository's own table, only in a checkout of it: in a project elsewhere,
    # ROOT.parent is whatever directory the project happens to sit in.
    if (ROOT / "scripts").resolve() == CODE:
        cands.append(ROOT.parent / "examples" / "models.json")
    for c in cands:
        if c and Path(c).is_file():
            return json.loads(Path(c).read_text(encoding="utf-8")).get("aliases", {})
    return {}


def _upstream_for(alias: str | None) -> str | None:
    """An alias from the table, or -- to name a model of your own -- an OpenRouter id as-is."""
    if not alias:
        return None
    table = _models_table()
    if alias in table:
        return table[alias]
    return f"openrouter/{alias}" if "/" in alias else None


def route(params: dict[str, Any]) -> dict[str, Any]:
    """{mode, base_url, key, model, endpoint} for this judge, or SystemExit saying how to fix it."""
    alias = params.get("model")
    base = (params.get("base_url") or os.environ.get("LITELLM_BASE_URL", "")).rstrip("/")
    if base.startswith("http"):
        key_env = params.get("api_key_env", "LITELLM_API_KEY")
        key = os.environ.get(key_env)
        if not key:
            raise SystemExit(f"{key_env} is not set (a proxy base_url is, so the proxy route was chosen)")
        return {"mode": "proxy", "base_url": f"{base}/v1", "key": key, "model": alias, "endpoint": base}
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        upstream = _upstream_for(alias)
        if not upstream:
            raise SystemExit(
                f"{alias!r} is neither an alias in a models table nor an "
                "OpenRouter id (vendor/model), so it cannot be sent to "
                "OpenRouter directly"
            )
        return {
            "mode": "direct",
            "base_url": OPENROUTER,
            "key": key,
            "model": upstream.removeprefix("openrouter/"),
            "endpoint": OPENROUTER,
        }
    raise SystemExit(
        f"No route to hosted model {alias!r}. Set ONE of:\n"
        "  OPENROUTER_API_KEY=sk-or-...           one key, no proxy\n"
        "  LITELLM_BASE_URL + LITELLM_API_KEY     your own LiteLLM proxy\n"
        "in the project's .env or the environment (a judge may also carry base_url / "
        "api_key_env)."
    )


def client(params: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    """An OpenAI-compatible client for this judge, and the route it was built for."""
    try:
        from openai import OpenAI  # noqa: PLC0415 - hosted judges only
    except ImportError:
        raise SystemExit(
            "a hosted judge needs the openai client: pip install 'evaluation-harness[llm]'"
        ) from None
    r = route(params)
    return OpenAI(api_key=r["key"], base_url=r["base_url"]), r


def extra_body(params: dict[str, Any], r: dict[str, Any]) -> dict[str, Any]:
    """Provider knobs outside the OpenAI schema. `reasoning` matters: a fixed field list once
    DROPPED it, so configs said reasoning was off and the requests did not. Direct mode also
    asks OpenRouter for usage accounting, which is where billed cost comes from."""
    out: dict[str, Any] = {}
    for k in ("reasoning", "reasoning_effort"):
        if params.get(k) is not None:
            out[k] = params[k]
    if params.get("provider_routing") is not None:
        out["provider"] = params["provider_routing"]
    if r["mode"] == "direct":
        out["usage"] = {"include": True}
    return out


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


def _as_dict(obj: Any) -> Any:
    if obj is None:
        return None
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001 -- forensics must not break a paid run
                pass
    if isinstance(obj, dict):
        return obj
    try:
        return dict(vars(obj))
    except Exception:  # noqa: BLE001
        return str(obj)


def _reasoning_tokens(usage: Any) -> int | None:
    """Reasoning tokens billed, or None when the provider did not say (None is not 0)."""
    d = _as_dict(usage)
    if not isinstance(d, dict):
        return None
    details = d.get("completion_tokens_details") or d.get("output_tokens_details") or {}
    if not isinstance(details, dict):
        details = _as_dict(details) if details else {}
    if isinstance(details, dict):
        for k in ("reasoning_tokens", "reasoning", "thinking_tokens"):
            if isinstance(details.get(k), int):
                return details[k]
    return None


def _billed(usage: Any) -> float | None:
    """What the provider billed for this call; it outranks the price table, which has been
    wrong by 0.67x-3.21x per arm."""
    d = usage if isinstance(usage, dict) else (usage.model_dump() if hasattr(usage, "model_dump") else None)
    if not isinstance(d, dict):
        return None
    c = d.get("cost")
    if c is None:
        c = (d.get("cost_details") or {}).get("upstream_inference_cost")
    try:
        return round(float(c), 10) if c is not None else None
    except (TypeError, ValueError):
        return None


def _price(params: dict[str, Any], tin: int | None, tout: int | None) -> float | None:
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    if pin is None or pout is None or tin is None or tout is None:
        return None
    return round(tin / 1e6 * float(pin) + tout / 1e6 * float(pout), 8)


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
        cost_usd=_price(params, tin, tout) or 0.0,
        extra={"truncated": 0.0},
        meta={"finish_reason": "stop", "provider": FAKE, "response_model": model},
    )


def call_judge(message: str, params: dict[str, Any]) -> JudgeResult:
    """One judge reply to one message. Retrying transient failures is the caller's job."""
    if params.get("provider") == FAKE:
        return _fake_call(message, params)
    cl, r = client(params)
    eb = extra_body(params, r)
    max_tokens = int(params.get("max_tokens", 1500))
    resp = cl.chat.completions.create(
        model=r["model"],
        temperature=float(params.get("temperature", 0.0)),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": message}],
        **({"extra_body": eb} if eb else {}),
    )
    usage = getattr(resp, "usage", None)
    ti = getattr(usage, "prompt_tokens", None)
    to = getattr(usage, "completion_tokens", None)
    finish = getattr(resp.choices[0], "finish_reason", None)
    # A judgement cut off mid-JSON is a parse failure that would read as "this judge is
    # bad"; finish_reason says it was the token ceiling instead.
    truncated = finish == "length" or (to is not None and to >= max_tokens * 0.98)
    reasoning = _reasoning_tokens(usage)
    billed = _billed(usage)
    return JudgeResult(
        output=(resp.choices[0].message.content or "").strip(),
        tokens_in=ti,
        tokens_out=to,
        cost_usd=billed if billed is not None else _price(params, ti, to),
        extra={
            "truncated": 1.0 if truncated else 0.0,
            **({"reasoning_tokens": float(reasoning)} if reasoning is not None else {}),
        },
        meta={
            "usage": _as_dict(usage),
            "finish_reason": finish,
            "response_model": getattr(resp, "model", None),
            "reasoning_tokens_reported": reasoning is not None,
            "provider": (
                getattr(resp, "provider", None) or (getattr(resp, "model_extra", None) or {}).get("provider")
            ),
        },
    )
