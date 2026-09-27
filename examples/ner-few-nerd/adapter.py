"""ML vs LLM named-entity recognition on Few-NERD. The seam for this example.

Set-valued scoring lives in `examples/_shared/extraction.py`. What is HERE is the task:
eight entity types, the providers that can produce a set of them, and the JSON contract
the hosted arms are held to.

    provider: litellm       a hosted model asked for a JSON array.    cost > 0
    provider: gliner        zero-shot NER, CALLER supplies the labels. cost 0. Needs gliner.
    provider: span_marker   fine-tuned ON Few-NERD.                    cost 0. Needs torch.
    provider: capitalized   maximal runs of capitalised tokens.        cost 0. Needs nothing.
    provider: nothing       predicts no entities at all.               cost 0. Needs nothing.

WHAT THIS TASK BREAKS THAT CLASSIFICATION DID NOT

  1. THE OUTPUT IS STRUCTURED, so the parser can fail at the level of the ITEM rather than
     the label. A classification arm that answers badly still answers one thing; an arm
     here can emit a JSON array that does not parse, and then it has no answer at all.
     `parsed` is a quality metric for that reason, and `_parse_entities` is deliberately
     forgiving about the wrappers models put round JSON -- fenced code blocks, a leading
     "Here are the entities:", a trailing comma -- because none of those are the task.

  2. THE FLOOR IS NOT 1/k. 15% of Few-NERD sentences contain no entities, so an arm that
     predicts NOTHING scores exactly the empty-gold rate. That is the `nothing` arm, and
     like `constant` before it, it is a calibration check on the scorer before it is a
     baseline on the task.

  3. TWO QUALITY METRICS THAT DISAGREE BY CONSTRUCTION. `f1` requires the right span AND
     the right type; `untyped_f1` requires only the span. Their difference is
     `type_penalty`, and it separates a detection problem from a labelling one -- two
     failures with the same score and completely different fixes.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))

from extraction import (  # noqa: E402
    METRIC_KINDS,
    PRIMARY_METRIC,
    normalizer_sha256,
    score_sets,
)

__all__ = ["call_system", "score", "warmup", "fingerprint",
           "PRIMARY_METRIC", "METRIC_KINDS", "TRANSIENT_MARKERS"]

TRANSIENT_MARKERS = ("model is warming up", "no instances available", "upstream")

#: Few-NERD's eight coarse types, in the dataset's own order. These strings are what the
#: gold reference files contain and what the prompt offers the model.
LABELS = ["art", "building", "event", "location", "organization", "other", "person",
          "product"]

#: The most frequent type in the corpus, used by the `capitalized` baseline as its guess.
#: Measured on the dev slice (location 40 of 149), not chosen to flatter it.
MAJORITY_TYPE = "location"


@dataclass
class Result:
    output: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    latency_ms: Optional[float] = None
    extra: Dict[str, float] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


# ── the prompt ───────────────────────────────────────────────────────────────
_PROMPT_CACHE: Dict[str, str] = {}


def _prompt(params: Dict[str, Any]) -> str:
    if params.get("prompt"):
        return str(params["prompt"])
    rel = str(params.get("prompt_file") or "prompt.txt")
    path = (HERE / rel).resolve()
    if str(path) not in _PROMPT_CACHE:
        if not path.is_file():
            raise SystemExit(f"prompt file not found: {path}")
        _PROMPT_CACHE[str(path)] = path.read_text(encoding="utf-8").strip()
    return _PROMPT_CACHE[str(path)]


def _prompt_sha256(params: Dict[str, Any]) -> str:
    import hashlib  # noqa: PLC0415

    return hashlib.sha256(_prompt(params).encode()).hexdigest()


# ── parsing a model's answer into a set ──────────────────────────────────────
_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)
_ARRAY = re.compile(r"\[.*\]", re.S)
_TRAILING_COMMA = re.compile(r",\s*([\]}])")


def _parse_entities(text: str) -> Optional[List[dict]]:
    """A model's answer as a list of {text, type}, or None if it cannot be read.

    None is not "found nothing" -- an empty list is that, and on this corpus finding
    nothing is often CORRECT. None means the output was not a set at all, which is a
    different failure and is counted separately as `parsed`.

    Forgiving about wrappers and strict about content. A fenced code block, a preamble, a
    trailing comma -- none of those are the task, and refusing them would measure JSON
    etiquette instead of entity recognition. But an object that is not {text, type} is
    dropped rather than guessed at.
    """
    if not text or not text.strip():
        return None
    body = text.strip()
    fenced = _FENCE.search(body)
    if fenced:
        body = fenced.group(1).strip()
    if not body.lstrip().startswith("["):
        found = _ARRAY.search(body)
        if not found:
            return None
        body = found.group(0)
    for candidate in (body, _TRAILING_COMMA.sub(r"\1", body)):
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if not isinstance(parsed, list):
            return None
        out = []
        for item in parsed:
            if isinstance(item, dict):
                txt = item.get("text") or item.get("entity") or item.get("name")
                kind = item.get("type") or item.get("label") or item.get("category")
                if txt:
                    out.append({"text": str(txt), "type": str(kind or "")})
            elif isinstance(item, str) and item.strip():
                # A bare string is a span with no type. Kept, and it will simply fail the
                # typed match -- which is the honest outcome, not an error.
                out.append({"text": item, "type": ""})
        return out
    return None


def _parser_sha256() -> str:
    import hashlib  # noqa: PLC0415
    import inspect  # noqa: PLC0415

    return hashlib.sha256(inspect.getsource(_parse_entities).encode()).hexdigest()


# ── providers ────────────────────────────────────────────────────────────────
def _nothing(text: str, params: Dict[str, Any]) -> Result:
    """Predicts no entities, ever.

    Scores exactly the share of sentences whose gold is also empty -- 0.1429 on the dev
    slice. Any other value means the scorer's empty-set conventions are wrong, and no
    other row in the table can be trusted until this one reads right.
    """
    return Result(output="[]", cost_usd=0.0, meta={"predicted": []})


_CAP_RUN = re.compile(r"\b([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*)*)")
#: Sentence-initial and other capitalised non-entities that the heuristic would otherwise
#: emit constantly. Written from English orthography, NOT from reading the slice.
_CAP_STOP = frozenset({"the", "a", "an", "in", "on", "at", "of", "and", "he", "she",
                       "it", "they", "this", "that", "his", "her", "their", "i"})


def _capitalized(text: str, params: Dict[str, Any]) -> Result:
    """Maximal runs of capitalised tokens, all guessed as the majority type.

    The NER analogue of LEAD-3: a rule anybody would write in ten minutes, included so the
    ladder has a floor that is not zero. It will have decent recall on `person` and
    `location`, terrible precision on sentence-initial words, and type accuracy no better
    than the corpus's majority class -- which is exactly the shape of result worth seeing
    next to a model that costs money.
    """
    kind = str(params.get("label", MAJORITY_TYPE))
    found = []
    for m in _CAP_RUN.finditer(text):
        span = m.group(1).strip()
        if span.casefold() in _CAP_STOP or len(span) < 2:
            continue
        found.append({"text": span, "type": kind})
    return Result(output=json.dumps(found), cost_usd=0.0, meta={"predicted": found})


_MODEL: Any = None
_MODEL_KEY: Optional[tuple] = None


def _gliner(text: str, params: Dict[str, Any]) -> Result:
    """Zero-shot NER where the CALLER supplies the label set.

    The reason this example can ask the ML-vs-LLM question that DBpedia could not. Most
    off-the-shelf NER models predict their own training taxonomy -- CoNLL's four types,
    OntoNotes' eighteen -- and comparing them here would need a lossy mapping onto
    Few-NERD's eight. GLiNER is handed the eight directly, so the comparison is clean and
    the model has still never seen this dataset.
    """
    global _MODEL, _MODEL_KEY
    key = ("gliner", params.get("model"))
    if _MODEL is None or _MODEL_KEY != key:
        from gliner import GLiNER  # noqa: PLC0415

        _MODEL = GLiNER.from_pretrained(params["model"])
        _MODEL_KEY = key
    threshold = float(params.get("threshold", 0.5))
    found = [{"text": e["text"], "type": e["label"]}
             for e in _MODEL.predict_entities(text, list(LABELS), threshold=threshold)]
    return Result(output=json.dumps(found), cost_usd=0.0, meta={"predicted": found})


def _span_marker(text: str, params: Dict[str, Any]) -> Result:
    """A model fine-tuned ON Few-NERD. The in-distribution specialist.

    Predicts the FINE taxonomy (66 types), which maps down to the coarse eight
    deterministically -- `person-actor` -> `person` -- because the fine labels are
    literally `coarse-detail`. That mapping is declared here rather than assumed, and it
    is in the fingerprint: getting it wrong would silently retype every prediction.
    """
    global _MODEL, _MODEL_KEY
    key = ("span_marker", params.get("model"))
    if _MODEL is None or _MODEL_KEY != key:
        from span_marker import SpanMarkerModel  # noqa: PLC0415

        _MODEL = SpanMarkerModel.from_pretrained(params["model"])
        _MODEL_KEY = key
    found = []
    for e in _MODEL.predict(text):
        label = str(e.get("label", ""))
        coarse = label.split("-", 1)[0] if params.get("coarsen", True) else label
        found.append({"text": e.get("span", ""), "type": coarse})
    return Result(output=json.dumps(found), cost_usd=0.0, meta={"predicted": found})


def _litellm(text: str, params: Dict[str, Any]) -> Result:
    from openai import OpenAI  # noqa: PLC0415

    base = (params.get("base_url") or os.environ.get("LITELLM_BASE_URL", "")).rstrip("/")
    if not base.startswith("http"):
        raise SystemExit("LITELLM_BASE_URL is not set — copy .env.example to .env")
    key_env = params.get("api_key_env", "LITELLM_API_KEY")
    key = os.environ.get(key_env)
    if not key:
        raise SystemExit(f"{key_env} is not set")
    client = OpenAI(api_key=key, base_url=f"{base}/v1")

    extra_body: Dict[str, Any] = {}
    for passthrough in ("reasoning", "reasoning_effort"):
        if params.get(passthrough) is not None:
            extra_body[passthrough] = params[passthrough]
    if params.get("provider_routing") is not None:
        extra_body["provider"] = params["provider_routing"]

    max_tokens = int(params.get("max_tokens", 600))
    resp = client.chat.completions.create(
        model=params["model"],
        temperature=float(params.get("temperature", 0.0)),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": _prompt(params) + "\n\n" + text}],
        **({"extra_body": extra_body} if extra_body else {}),
    )
    usage = getattr(resp, "usage", None)
    ti = getattr(usage, "prompt_tokens", None)
    to = getattr(usage, "completion_tokens", None)
    finish = getattr(resp.choices[0], "finish_reason", None)
    truncated = finish == "length" or (to is not None and to >= max_tokens * 0.98)
    reasoning_tokens = _reasoning_tokens(usage)
    raw = (resp.choices[0].message.content or "").strip()

    return Result(
        output=raw,
        tokens_in=ti,
        tokens_out=to,
        cost_usd=_price(params, ti, to),
        extra={
            "truncated": 1.0 if truncated else 0.0,
            **({"reasoning_tokens": float(reasoning_tokens)}
               if reasoning_tokens is not None else {}),
        },
        meta={
            "predicted": _parse_entities(raw),
            "usage": _as_dict(usage),
            "finish_reason": finish,
            "response_model": getattr(resp, "model", None),
            "provider": (getattr(resp, "provider", None)
                         or (getattr(resp, "model_extra", None) or {}).get("provider")),
        },
    )


def _as_dict(obj: Any) -> Any:
    if obj is None:
        return None
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001
                pass
    if isinstance(obj, dict):
        return obj
    try:
        return dict(vars(obj))
    except Exception:  # noqa: BLE001
        return str(obj)


def _reasoning_tokens(usage: Any) -> Optional[int]:
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


def _price(params: Dict[str, Any], tin: Optional[int], tout: Optional[int]) -> Optional[float]:
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    if pin is None or pout is None or tin is None or tout is None:
        return None
    return round(tin / 1e6 * float(pin) + tout / 1e6 * float(pout), 8)


PROVIDERS = {
    "capitalized": _capitalized,
    "gliner": _gliner,
    "litellm": _litellm,
    "nothing": _nothing,
    "span_marker": _span_marker,
}


def call_system(text: str, params: Dict[str, Any]) -> Result:
    provider = params.get("provider", "litellm")
    fn = PROVIDERS.get(provider)
    if fn is None:
        raise SystemExit(f"unknown provider {provider!r} — expected one of {sorted(PROVIDERS)}")
    started = time.perf_counter()
    result = fn(text, params)
    if result.latency_ms is None:
        result.latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return result


def warmup(params: Dict[str, Any]) -> None:
    """Load weights / prove the endpoint answers, before anything is timed or paid for."""
    provider = params.get("provider", "litellm")
    if provider in ("gliner", "span_marker"):
        PROVIDERS[provider]("Warm up in New York.", params)
    elif provider == "litellm":
        _litellm("Warm up.", {**params, "max_tokens": 16})
    # `capitalized` and `nothing` have nothing to warm. An `else` here would send a PAID
    # request on behalf of an arm that cannot cost anything.
    score("[]", "[]", "a source text")


def score(output: str, reference: Optional[str], source: Optional[str] = None) -> Dict[str, float]:
    """Set F1 against the gold entities, typed and untyped.

    The output is re-parsed here rather than taken from `meta`, so `make rescore` can
    recompute every number from the stored text after a scorer change -- the same
    property the summarisation example relies on.
    """
    predicted = _parse_entities(output)
    out: Dict[str, float] = {"parsed": 0.0 if predicted is None else 1.0}
    out.update(score_sets(predicted or [], reference))
    return out


def fingerprint(params: Dict[str, Any]) -> Dict[str, Any]:
    """What this arm's system under test IS.

    `normalizer_sha256` and `parser_sha256` are on EVERY arm, including local ones that
    never touch the JSON parser. A set-matcher has strictly more room to move a score than
    a label parser did, and the label parser turned out to be worth 8.6 accuracy points in
    the classification example -- so both are recorded from the start rather than after
    the surprise.
    """
    provider = params.get("provider", "litellm")
    common = {
        "provider": provider,
        "labels": list(LABELS),
        "normalizer_sha256": normalizer_sha256(),
        "parser_sha256": _parser_sha256(),
    }

    if provider in ("gliner", "span_marker"):
        sys.path.insert(0, str(HERE.parent / "_shared"))
        from hf_identity import hf_model_fingerprint  # noqa: PLC0415

        out = hf_model_fingerprint(
            params["model"],
            revision=params.get("revision"),
            device=str(params.get("device", "cpu")),
            precision=str(params.get("precision", "fp32")),
        )
        if provider == "gliner":
            # The threshold IS this arm's decision boundary: move it and precision and
            # recall trade against each other. As much part of the system as a prompt.
            out["threshold"] = params.get("threshold", 0.5)
        else:
            out["coarsen"] = params.get("coarsen", True)
        out.update(common)
        return out

    if provider in ("capitalized", "nothing"):
        import hashlib  # noqa: PLC0415
        import inspect  # noqa: PLC0415

        rules = inspect.getsource(_capitalized) + repr(sorted(_CAP_STOP)) + _CAP_RUN.pattern
        return {"id": provider,
                "rules_sha256": hashlib.sha256(rules.encode()).hexdigest()
                if provider == "capitalized" else None,
                "label": params.get("label"), **common}

    alias = params.get("model")
    return {
        "id": alias,
        "alias": alias,
        "id_source": "alias-unresolved",
        "endpoint": os.environ.get("LITELLM_BASE_URL"),
        "temperature": params.get("temperature"),
        "prompt_sha256": _prompt_sha256(params),
        "reasoning": params.get("reasoning"),
        "max_tokens": params.get("max_tokens"),
        **common,
    }
