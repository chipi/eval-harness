"""ML vs LLM on AG News topic classification. The seam for this example.

An arm is a YAML file naming a system. Five backends, none imported until an arm asks:

    provider: litellm      a hosted model through the proxy.        cost > 0. Needs openai.
    provider: hf_local     a fine-tuned classifier on this machine. cost 0. Needs torch.
    provider: hf_zeroshot  an NLI model used zero-shot.             cost 0. Needs torch.
    provider: keyword      ~20 hand-written rules.                  cost 0. Needs nothing.
    provider: constant     always the same label.                   cost 0. Needs nothing.

WHAT IS DIFFERENT FROM THE SUMMARISATION EXAMPLE, AND WHY IT MATTERS

  1. THE PARSER IS PART OF THE SYSTEM UNDER TEST. A model that answers "Sports", "Sports.",
     "**Sports**" or "This article is about sports" is right or wrong depending entirely on
     who wrote `_parse_label`. In summarisation the prompt was fingerprinted because it
     shapes the output; here the parser has to be fingerprinted for the same reason, and it
     is -- `parser_sha256` sits beside `prompt_sha256` in every arm's fingerprint. Tighten
     the parser and every score in the tree changes; the fingerprint is what makes that
     visible instead of mysterious.

  2. THE PER-ITEM SCORE IS BINARY. `correct` is 1.0 or 0.0, so its mean is accuracy. That
     is fine for a mean and awkward for the statistics: on most items most arms simply
     agree (all right or all wrong), so within-item ranks are mostly ties and the paired
     tests have far less to work with than continuous ROUGE gave them. Read the
     significance block here with more suspicion than the summarisation one, not less.

  3. MACRO-F1 CANNOT BE COMPUTED PER ITEM. Accuracy can: score each item, take the mean.
     F1 needs the whole confusion matrix, which is not a property of any single item, so
     the harness's average-the-per-item-metric shape cannot express it. This is a real
     limitation and it is not worked around by inventing a per-item pseudo-F1. Instead
     every prediction is recorded in `meta.predicted`, and `scripts/classification_report.py`
     builds the confusion matrix, macro-F1 and per-class precision/recall from the stored
     predictions. Accuracy is the per-item metric; macro-F1 is a report.

  4. THE FLOOR IS EXACTLY KNOWN. fetch.py draws equal numbers per class, so a constant
     answer scores 0.25 by construction -- not approximately, exactly. An arm below 0.25 is
     worse than answering "World" to everything, which is worth seeing in the same table.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Result:
    output: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    latency_ms: Optional[float] = None
    extra: Dict[str, float] = field(default_factory=dict)
    #: Raw provider metadata, recorded verbatim and never averaged. This example also uses
    #: it to carry the PARSED label, which is what the confusion matrix is built from.
    meta: Dict[str, Any] = field(default_factory=dict)


#: The dataset's label set, in the corpus's own order. Not alphabetical, not ours to
#: reorder: these strings are what the gold reference files contain.
LABELS = ["World", "Sports", "Business", "Sci/Tech"]


# ── the prompt, in one place ─────────────────────────────────────────────────
_PROMPT_CACHE: Dict[str, str] = {}


def _prompt(params: Dict[str, Any]) -> str:
    """The instruction every hosted arm sends, read from ONE file.

    Same reasoning as the summarisation example: duplicated per-config prompts are
    identical by generation rather than by construction, and one hand-edit makes an arm
    incomparable with the rest while nothing says so. An explicit `prompt:` still wins so
    prompt research stays possible, but it is then a visible override on the run.
    """
    if params.get("prompt"):
        return str(params["prompt"])
    rel = str(params.get("prompt_file") or "prompt.txt")
    path = (Path(__file__).resolve().parent / rel).resolve()
    key = str(path)
    if key not in _PROMPT_CACHE:
        if not path.is_file():
            raise SystemExit(f"prompt file not found: {path}")
        _PROMPT_CACHE[key] = path.read_text(encoding="utf-8").strip()
    return _PROMPT_CACHE[key]


def _prompt_sha256(params: Dict[str, Any]) -> str:
    return hashlib.sha256(_prompt(params).encode()).hexdigest()


# ── the parser, which is also part of the system under test ──────────────────
#: Longest label first, so "Sci/Tech" is not shadowed by a looser match on "Tech".
_ALIASES: List[tuple] = [
    ("Sci/Tech", ("sci/tech", "sci-tech", "scitech", "science/technology", "sci tech",
                  "science and technology", "technology", "science", "tech")),
    ("Business", ("business", "finance", "financial", "economy", "economics")),
    ("Sports", ("sports", "sport")),
    ("World", ("world", "international", "world news", "politics", "general")),
]


def _parse_label(text: str) -> Optional[str]:
    """The model's answer as one of LABELS, or None when no label can be found.

    None is not "wrong", it is UNPARSEABLE, and the two are reported separately. An arm
    that returns prose 30% of the time and is right whenever it answers is a different
    engineering problem from an arm that answers crisply and is wrong, and one accuracy
    number hides that completely.

    HOW LENIENT TO BE IS A REAL DECISION, NOT A DETAIL. Exact-match-only would score
    "Sports." as wrong and measure obedience rather than classification. Matching anywhere
    in a long answer would let "this is not about sports, it is business" resolve to
    whichever alias appears first. The middle taken here:

      - strip markdown, quotes, trailing punctuation, and a leading "Category:" style label
      - accept an exact alias match on what remains
      - otherwise take the EARLIEST alias occurring as a whole word anywhere in the text,
        which is the answer-first convention the prompt asks for

    Whatever this function does is recorded as `parser_sha256`, so a later change to it is
    visible as a different system rather than as models mysteriously improving.
    """
    if not text:
        return None
    cleaned = text.strip()
    # A leading "Category:", "Label:", "Answer:" and friends, with optional markdown.
    cleaned = re.sub(r"^[\s*_#>`]*(category|label|answer|classification)\s*[:\-]\s*", "",
                     cleaned, flags=re.I)
    cleaned = cleaned.strip(" \t\n*_`\"'.,:;!?()[]{}")
    low = cleaned.lower()
    for label, aliases in _ALIASES:
        if low in aliases:
            return label
    # Nothing matched the whole answer, so look inside it. Earliest whole-word hit wins;
    # ties are impossible because a position is unique.
    best: Optional[tuple] = None
    for label, aliases in _ALIASES:
        for alias in aliases:
            m = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", low)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), label)
    return best[1] if best else None


def _parser_sha256() -> str:
    """Hash of the parser's own source, so the fingerprint changes when the rules do.

    Hashing the source rather than a version string someone has to remember to bump. The
    alias table is included because it is the parser as much as the code is.
    """
    body = inspect.getsource(_parse_label) + repr(_ALIASES)
    return hashlib.sha256(body.encode()).hexdigest()


# ── providers ────────────────────────────────────────────────────────────────
def _constant(text: str, params: Dict[str, Any]) -> Result:
    """Always the same label. The floor, and an exactly known one.

    fetch.py draws equal numbers per class, so this scores 0.25 on the nose -- not
    "about a quarter". Any arm that does not clear it is worse than a constant, and a
    ladder without that line on it cannot say whether the ranking means anything.
    """
    label = str(params.get("label", LABELS[0]))
    return Result(output=label, cost_usd=0.0, meta={"predicted": label})


#: Hand-written rules, in priority order. Written from the four label names and general
#: knowledge of news desks -- NOT by reading the slice and patching what it got wrong,
#: which would make it a model fitted on the eval set and put it on the wrong side of
#: every claim in this example.
_RULES: List[tuple] = [
    ("Sports", r"\b(game|games|season|coach|league|championship|cup|match|matches|"
               r"player|players|team|teams|score|scored|goal|goals|inning|nfl|nba|mlb|"
               r"nhl|olympic|olympics|tournament|playoff|playoffs|striker|midfield)\b"),
    ("Sci/Tech", r"\b(software|internet|computer|computers|microsoft|google|linux|"
                 r"web|online|chip|chips|semiconductor|nasa|space|scientist|scientists|"
                 r"research|researchers|technology|browser|server|servers|wireless|"
                 r"broadband|satellite|telescope|spacecraft)\b"),
    ("Business", r"\b(profit|profits|earnings|revenue|shares|stock|stocks|market|"
                 r"markets|investor|investors|merger|acquisition|quarterly|dividend|"
                 r"nasdaq|dow|economy|inflation|oil prices|bankruptcy|ceo)\b"),
]


def _keyword(text: str, params: Dict[str, Any]) -> Result:
    """~20 regex rules, first match wins, default World.

    This is the direct analogue of a rule-based classifier already running in production
    somewhere: deterministic, sub-millisecond, no model file, and nobody knows whether it
    is good enough because it was never measured against anything. Measuring it is the
    point. Its default class is World for the same reason such classifiers usually have
    one -- something has to catch the rest.
    """
    low = text.lower()
    for label, pattern in _RULES:
        if re.search(pattern, low):
            return Result(output=label, cost_usd=0.0, meta={"predicted": label})
    return Result(output="World", cost_usd=0.0, meta={"predicted": "World"})


_PIPE: Any = None
_PIPE_KEY: Optional[tuple] = None


def _local_pipeline(params: Dict[str, Any], task: str) -> Any:
    """Load once, module-level, so `warmup()` pays the cost outside the timed loop."""
    global _PIPE, _PIPE_KEY
    key = (params.get("model"), params.get("revision"), params.get("device"), task)
    if _PIPE is not None and _PIPE_KEY == key:
        return _PIPE
    from transformers import pipeline  # noqa: PLC0415 - only when an arm asks

    kwargs: Dict[str, Any] = {"model": params["model"]}
    if params.get("revision"):
        kwargs["revision"] = params["revision"]
    if params.get("device"):
        kwargs["device"] = params["device"]
    _PIPE = pipeline(task, **kwargs)
    _PIPE_KEY = key
    return _PIPE


def _hf_local(text: str, params: Dict[str, Any]) -> Result:
    """A model fine-tuned ON AG News. The in-distribution specialist.

    Its head emits the dataset's own label ids, but the checkpoint's `id2label` is often
    left at the training default ("LABEL_0"), so an arm declares `label_order` and we map
    positionally. Guessing here would silently permute the classes and report a model as
    bad when it is merely mislabelled.
    """
    pipe = _local_pipeline(params, "text-classification")
    out = pipe(text, truncation=True)[0]
    raw = str(out["label"])
    order = params.get("label_order") or LABELS
    m = re.fullmatch(r"LABEL_(\d+)", raw)
    predicted = order[int(m.group(1))] if m and int(m.group(1)) < len(order) else raw
    return Result(
        output=predicted,
        cost_usd=0.0,
        meta={"predicted": predicted, "raw_label": raw, "score": float(out.get("score", 0.0))},
        # The model's own confidence. Classification is the first task here where a
        # calibration question is even askable, and it cannot be asked later if the
        # number is not kept now.
        extra={"confidence": float(out.get("score", 0.0))},
    )


def _hf_zeroshot(text: str, params: Dict[str, Any]) -> Result:
    """An NLI model doing classification with no task fine-tune at all.

    The most interesting local arm in this example. bart-large-mnli is the SAME
    architecture family that won the summarisation study, used here with no exposure to AG
    News -- so it separates "this architecture is good" from "this checkpoint was trained
    on the test distribution", which the summarisation result could not.
    """
    pipe = _local_pipeline(params, "zero-shot-classification")
    hypothesis = str(params.get("hypothesis_template", "This news article is about {}."))
    out = pipe(text, candidate_labels=list(LABELS), hypothesis_template=hypothesis,
               truncation=True)
    predicted = str(out["labels"][0])
    confidence = float(out["scores"][0])
    return Result(
        output=predicted,
        cost_usd=0.0,
        meta={"predicted": predicted, "all_scores": dict(zip(out["labels"], out["scores"]))},
        extra={"confidence": confidence},
    )


def _litellm(text: str, params: Dict[str, Any]) -> Result:
    """A hosted model through the proxy. Lifted from the summarisation example's adapter.

    Deliberately the same code, including the two lessons that cost that study real
    findings: `reasoning` has to travel in extra_body or the request silently contradicts
    the config, and a response cut off at max_tokens scores like a bad model rather than
    like a small budget, so `truncated` is a metric and not a log line.
    """
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

    max_tokens = int(params.get("max_tokens", 200))
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
            "predicted": _parse_label(raw),
            "usage": _as_dict(usage),
            "finish_reason": finish,
            "response_model": getattr(resp, "model", None),
            "reasoning_tokens_reported": reasoning_tokens is not None,
            "provider": (
                getattr(resp, "provider", None)
                or (getattr(resp, "model_extra", None) or {}).get("provider")
            ),
        },
    )


def _as_dict(obj: Any) -> Any:
    """Best-effort plain-data view of a provider SDK object, for the run record."""
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
    """Reasoning tokens billed, or None if unreported. None and 0 are different claims."""
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
    """Cost from prices declared in the config, or None when they are not.

    None means UNPRICED. A local arm reports 0.0 instead -- a measured zero is a claim,
    a missing value is not.
    """
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    if pin is None or pout is None or tin is None or tout is None:
        return None
    return round(tin / 1e6 * float(pin) + tout / 1e6 * float(pout), 8)


PROVIDERS = {
    "constant": _constant,
    "hf_local": _hf_local,
    "hf_zeroshot": _hf_zeroshot,
    "keyword": _keyword,
    "litellm": _litellm,
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


# ── warm-up ──────────────────────────────────────────────────────────────────
def warmup(params: Dict[str, Any]) -> None:
    """Load weights / prove the endpoint answers, before anything is timed or paid for."""
    provider = params.get("provider", "litellm")
    if provider == "hf_local":
        _local_pipeline(params, "text-classification")
    elif provider == "hf_zeroshot":
        _local_pipeline(params, "zero-shot-classification")
    elif provider == "litellm":
        _litellm("Warm up.", {**params, "max_tokens": 1})
    # `keyword` and `constant` have nothing to warm: no weights, no endpoint. An `else`
    # here would send a PAID warm-up request on behalf of an arm that cannot cost anything.
    score("Sports", "Sports", "a source text")


# ── fingerprint ──────────────────────────────────────────────────────────────
_UPSTREAM_CACHE: Dict[str, Optional[str]] = {}


def _resolve_upstream(alias: Optional[str]) -> Optional[str]:
    """Ask the proxy what upstream model an alias points at, or None if it cannot say."""
    if not alias:
        return None
    if alias in _UPSTREAM_CACHE:
        return _UPSTREAM_CACHE[alias]
    resolved: Optional[str] = None
    base = (os.environ.get("LITELLM_BASE_URL") or "").rstrip("/")
    key = os.environ.get("LITELLM_API_KEY")
    if base.startswith("http") and key:
        import json as _json  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        try:
            req = urllib.request.Request(
                base + "/model/info", headers={"Authorization": "Bearer " + key}
            )
            with urllib.request.urlopen(req, timeout=15) as fh:
                for entry in (_json.load(fh).get("data") or []):
                    if entry.get("model_name") == alias:
                        resolved = (entry.get("litellm_params") or {}).get("model")
                        break
        except Exception:  # noqa: BLE001 -- provenance is best-effort, the run is not
            resolved = None
    _UPSTREAM_CACHE[alias] = resolved
    return resolved


def fingerprint(params: Dict[str, Any]) -> Dict[str, Any]:
    """What this arm's system under test IS.

    `parser_sha256` is on EVERY arm including the ones that never see the parser, because
    the question it answers is "would this number change if the parser changed?" and for a
    hosted arm the answer is yes. A local arm returns a label directly and is unaffected,
    which the identical hash across both makes checkable rather than assumed.
    """
    provider = params.get("provider", "litellm")
    common = {"parser_sha256": _parser_sha256(), "provider": provider}

    if provider in ("hf_local", "hf_zeroshot"):
        import sys  # noqa: PLC0415

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
        from hf_identity import hf_model_fingerprint  # noqa: PLC0415

        out = hf_model_fingerprint(
            params["model"],
            revision=params.get("revision"),
            device=str(params.get("device", "cpu")),
            precision=str(params.get("precision", "fp32")),
        )
        # The hypothesis template IS the prompt for a zero-shot arm -- change it and the
        # model is being asked a different question -- so it is fingerprinted like one.
        if provider == "hf_zeroshot":
            out["hypothesis_template"] = params.get("hypothesis_template")
        out.update(common)
        return out

    if provider in ("keyword", "constant"):
        # No weights and no endpoint, so the RULES are the system under test. Hashing the
        # rule table means editing one regex produces a different arm, which is exactly
        # what it is.
        return {
            "id": provider,
            "rules_sha256": hashlib.sha256(repr(_RULES).encode()).hexdigest(),
            "label": params.get("label"),
            **common,
        }

    alias = params.get("model")
    upstream = _resolve_upstream(alias)
    return {
        "id": upstream or alias,
        "alias": alias,
        "id_source": "proxy-model-info" if upstream else "alias-unresolved",
        "revision": None,
        "revision_source": "api-model-string",
        "endpoint": os.environ.get("LITELLM_BASE_URL"),
        "provider_routing": params.get("provider_routing"),
        "temperature": params.get("temperature"),
        "prompt_sha256": _prompt_sha256(params),
        "reasoning": params.get("reasoning"),
        **common,
    }


# ── the scorers ──────────────────────────────────────────────────────────────
_MARKDOWN = re.compile(r"^\s*(\*\*|__|##|#\s+|>\s+)")


def score(output: str, reference: Optional[str], source: Optional[str] = None) -> Dict[str, float]:
    """Exact label match, plus the ways an answer can fail that accuracy cannot see."""
    predicted = _parse_label(output)
    words = len(output.split())
    out: Dict[str, float] = {
        # PARSEABLE AT ALL. Separate from correct, because "returned prose" and "returned
        # the wrong label" are different engineering problems with different fixes, and
        # one accuracy column cannot tell them apart.
        "parsed": 1.0 if predicted is not None else 0.0,
        # The prompt asks for the category name and nothing else. More than two words means
        # the parser did work the model was asked to make unnecessary -- harmless for the
        # score, and the leading indicator of a prompt that is about to stop working.
        "answer_words": float(words),
        "fmt_verbose": 1.0 if words > 2 else 0.0,
        "fmt_markdown": 1.0 if _MARKDOWN.match(output) else 0.0,
    }
    if reference is None:
        return out
    gold = reference.strip()
    out["correct"] = 1.0 if predicted == gold else 0.0
    # Right only because the parser was generous: the raw answer was not the bare label.
    # If this is large, the accuracy column is partly measuring _parse_label.
    out["correct_after_repair"] = (
        1.0 if (out["correct"] and output.strip() != gold) else 0.0
    )
    return out


PRIMARY_METRIC = "correct"

METRIC_KINDS = {
    # The one that ranks. Binary per item, so its mean IS accuracy.
    "correct": "quality",
    # Quality too, and deliberately: an arm that cannot be parsed cannot be deployed,
    # whatever it knows.
    "parsed": "quality",
    # Descriptive: they describe the answer, not its correctness.
    "correct_after_repair": "descriptive",
    "answer_words": "descriptive",
    "fmt_verbose": "descriptive",
    "fmt_markdown": "descriptive",
    # The model's own confidence, where a provider reports one. Not quality -- a confident
    # wrong answer is worse than a hesitant one -- but the input to a calibration question
    # that no summarisation metric could have asked.
    "confidence": "descriptive",
    # Same meaning as in the summarisation example: an arm with truncated > 0 is reporting
    # the token ceiling rather than the model.
    "truncated": "descriptive",
    "reasoning_tokens": "descriptive",
}

#: Extra failure shapes worth retrying for THIS adapter, on top of the core's list.
TRANSIENT_MARKERS = ("model is warming up", "no instances available", "upstream")
