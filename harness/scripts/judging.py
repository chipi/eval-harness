"""What a judging pass needs from a judge, with no dependency outside this package.

`judge_score.py` used to borrow these from examples/summeval-judging/adapter.py and
examples/_shared/gateway.py, which an installed package does not have. They live here now:

  prompt       `render_prompt` and `build_message`. At 16 summaries the message is byte-identical
               to the one SummEval's adapter builds (self-tested against it), so the validation
               a judge earned there still describes what is sent.
  parsing      `parse_block`: the four dimensions, exactly n numbers each, each in 1..5.
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DIMS = ("coherence", "consistency", "fluency", "relevance")
OPENROUTER = "https://openrouter.ai/api/v1"
FAKE = "fake"


# ── the prompt, generalised only in its count ────────────────────────────────
def render_prompt(base: str, n: int) -> str:
    """SummEval's prompt for `n` summaries. Byte-identical to it when n == 16."""
    if n == 16:
        return base
    a, b = "16 numbered summaries", "a list of 16 integers"
    if a not in base or b not in base:
        raise SystemExit("the prompt no longer contains the two count phrases this pass rewrites "
                         f"({a!r}, {b!r}); it cannot be rendered for {n} summaries")
    if n == 1:
        # Singular grammar, and an example showing one value per key: the 16-wide example
        # ("[3, 4, ...]") would invite a list that parse_block then rejects.
        ex = ('{"coherence": [3, 4, ...], "consistency": [5, 2, ...], '
              '"fluency": [4, 4, ...], "relevance": [2, 3, ...]}')
        if ex not in base:
            raise SystemExit("the prompt no longer contains the example line this pass rewrites "
                             "for one summary")
        return (base.replace(a, "1 numbered summary").replace(b, "a list of 1 integer")
                .replace(ex, '{"coherence": [3], "consistency": [5], "fluency": [4], "relevance": [2]}')
                .replace("Rate every summary", "Rate the summary")
                .replace("the summaries may share mistakes", "the summary may contain mistakes")
                .replace("a list of 1 integer in summary order", "a list of 1 integer"))
    return base.replace(a, f"{n} numbered summaries").replace(b, f"a list of {n} integers")


def build_message(base: str, article: str, summaries: Sequence[str]) -> str:
    """The judge's input: the prompt for this many summaries, the article, the numbered
    summaries. Same layout as SummEval's `_judge_message`; the human references are left out
    on purpose (a judge shown them would be doing ROUGE's job)."""
    numbered = "\n".join(f"{i}. {s.strip()}" for i, s in enumerate(summaries, 1))
    return (f"{render_prompt(base, len(summaries))}\n\nARTICLE:\n{article.strip()}"
            f"\n\nSUMMARIES:\n{numbered}")


_JSON = re.compile(r"\{.*\}", re.S)


def parse_block(output: str, n: int) -> Optional[List[float]]:
    """Per-summary mean of the four dimensions, or None.

    Lenient about wrapping (a fence, a sentence before the JSON), strict about content: a
    dimension counts only with exactly `n` numbers, and a block counts only with all four,
    each in 1..5.
    """
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
    for d in DIMS:
        v = obj.get(d)
        if not isinstance(v, list) or len(v) != n:
            return None
        try:
            f = [float(x) for x in v]
        except (TypeError, ValueError):
            return None
        if any(not (1.0 <= x <= 5.0) for x in f):
            return None
        cols.append(f)
    return [statistics.fmean(c[i] for c in cols) for i in range(n)]


# ── rank statistics ──────────────────────────────────────────────────────────
def _ranks(x: List[float]) -> List[float]:
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


def _pearson(a: List[float], b: List[float]) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) ** 0.5


def spearman(a: List[float], b: List[float]) -> float:
    """Spearman's rho with average ranks for ties; 0 when either side is constant."""
    return _pearson(_ranks(a), _ranks(b))


def kendall_tau_b(a: List[float], b: List[float]) -> float:
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


# ── routing ──────────────────────────────────────────────────────────────────
def _models_table() -> Dict[str, str]:
    """alias -> upstream id, from the first models file that exists; {} when none does."""
    from _common import ROOT  # noqa: PLC0415

    cands = [os.environ.get("EVAL_MODELS_FILE", "").strip(), ROOT / "models.json",
             ROOT.parent / "examples" / "models.json"]
    for c in cands:
        if c and Path(c).is_file():
            return json.loads(Path(c).read_text(encoding="utf-8")).get("aliases", {})
    return {}


def _upstream_for(alias: Optional[str]) -> Optional[str]:
    """An alias from the table, or -- to name a model of your own -- an OpenRouter id as-is."""
    if not alias:
        return None
    table = _models_table()
    if alias in table:
        return table[alias]
    return f"openrouter/{alias}" if "/" in alias else None


def route(params: Dict[str, Any]) -> Dict[str, Any]:
    """{mode, base_url, key, model, endpoint} for this judge, or SystemExit saying how to fix it."""
    alias = params.get("model")
    base = (params.get("base_url") or os.environ.get("LITELLM_BASE_URL", "")).rstrip("/")
    if base.startswith("http"):
        key_env = params.get("api_key_env", "LITELLM_API_KEY")
        key = os.environ.get(key_env)
        if not key:
            raise SystemExit(f"{key_env} is not set (a proxy base_url is, so the proxy route "
                             "was chosen)")
        return {"mode": "proxy", "base_url": f"{base}/v1", "key": key, "model": alias,
                "endpoint": base}
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        upstream = _upstream_for(alias)
        if not upstream:
            raise SystemExit(f"{alias!r} is neither an alias in a models table nor an "
                             "OpenRouter id (vendor/model), so it cannot be sent to "
                             "OpenRouter directly")
        return {"mode": "direct", "base_url": OPENROUTER, "key": key,
                "model": upstream.removeprefix("openrouter/"), "endpoint": OPENROUTER}
    raise SystemExit(
        f"No route to hosted model {alias!r}. Set ONE of:\n"
        "  OPENROUTER_API_KEY=sk-or-...           one key, no proxy\n"
        "  LITELLM_BASE_URL + LITELLM_API_KEY     your own LiteLLM proxy\n"
        "in the project's .env or the environment (a judge may also carry base_url / "
        "api_key_env).")


def client(params: Dict[str, Any]) -> Tuple[Any, Dict[str, Any]]:
    """An OpenAI-compatible client for this judge, and the route it was built for."""
    try:
        from openai import OpenAI  # noqa: PLC0415 - hosted judges only
    except ImportError:
        raise SystemExit("a hosted judge needs the openai client: pip install "
                         "'evaluation-harness[llm]'") from None
    r = route(params)
    return OpenAI(api_key=r["key"], base_url=r["base_url"]), r


def extra_body(params: Dict[str, Any], r: Dict[str, Any]) -> Dict[str, Any]:
    """Provider knobs outside the OpenAI schema. `reasoning` matters: a fixed field list once
    DROPPED it, so configs said reasoning was off and the requests did not. Direct mode also
    asks OpenRouter for usage accounting, which is where billed cost comes from."""
    out: Dict[str, Any] = {}
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
    output: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    latency_ms: Optional[float] = None
    extra: Dict[str, float] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


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


def _reasoning_tokens(usage: Any) -> Optional[int]:
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


def _billed(usage: Any) -> Optional[float]:
    """What the provider billed for this call; it outranks the price table, which has been
    wrong by 0.67x-3.21x per arm."""
    d = usage if isinstance(usage, dict) else (
        usage.model_dump() if hasattr(usage, "model_dump") else None)
    if not isinstance(d, dict):
        return None
    c = d.get("cost")
    if c is None:
        c = (d.get("cost_details") or {}).get("upstream_inference_cost")
    try:
        return round(float(c), 10) if c is not None else None
    except (TypeError, ValueError):
        return None


def _price(params: Dict[str, Any], tin: Optional[int], tout: Optional[int]) -> Optional[float]:
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    if pin is None or pout is None or tin is None or tout is None:
        return None
    return round(tin / 1e6 * float(pin) + tout / 1e6 * float(pout), 8)


def _fake_call(message: str, params: Dict[str, Any]) -> JudgeResult:
    """Scores each numbered summary 1-5 from a hash of its text and the judge's model, so
    two fake judges disagree a little and a rerun reproduces itself."""
    body = message.split("SUMMARIES:\n", 1)[1] if "SUMMARIES:\n" in message else ""
    sums = re.findall(r"^\d+\. (.*)$", body, re.M)
    model = str(params.get("model", ""))
    s = [1 + int(hashlib.sha256(f"{model}|{x}".encode()).hexdigest()[:8], 16) % 5 for x in sums]
    out = json.dumps({d: s for d in DIMS})
    tin, tout = max(1, len(message) // 4), max(1, len(out) // 4)
    return JudgeResult(output=out, tokens_in=tin, tokens_out=tout,
                       cost_usd=_price(params, tin, tout) or 0.0, extra={"truncated": 0.0},
                       meta={"finish_reason": "stop", "provider": FAKE, "response_model": model})


def call_judge(message: str, params: Dict[str, Any]) -> JudgeResult:
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
        extra={"truncated": 1.0 if truncated else 0.0,
               **({"reasoning_tokens": float(reasoning)} if reasoning is not None else {})},
        meta={"usage": _as_dict(usage), "finish_reason": finish,
              "response_model": getattr(resp, "model", None),
              "reasoning_tokens_reported": reasoning is not None,
              "provider": (getattr(resp, "provider", None)
                           or (getattr(resp, "model_extra", None) or {}).get("provider"))},
    )
