"""The parts of a classification adapter that are not about any particular corpus.

OPTIONAL AND OUT OF THE CORE, like `hf_identity`. `scripts/` defines a vocabulary --
call_system, score, fingerprint -- and never learns what a label is. This module knows
what a label is; the core still cannot reach it.

It exists because the SECOND classification example was about to be a copy of the first.
Two copies of a label parser drift, and when they drift the two examples stop being
comparable for a reason nobody can see. Written on the second use, not the first: the
seam is only visible once two corpora disagree about what a label looks like.

WHAT IS SHARED AND WHAT IS NOT

    shared    parsing an answer into a label, and hashing the parser
              scoring: correct / parsed / the format flags
              the provider bodies: constant, keyword, hf_local, hf_zeroshot, litellm
              the fingerprint's shape, including which fields are per-provider
    NOT       the labels, their aliases, the rule table, the prompt

  The second list is the task. An example declares it, gets the first list, and adds
  nothing else. `LABELS` is not a default here on purpose -- a classification adapter with
  a plausible-looking default label set is a way to run the wrong experiment quietly.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


@dataclass
class Result:
    output: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    latency_ms: Optional[float] = None
    extra: Dict[str, float] = field(default_factory=dict)
    #: Raw provider metadata, recorded verbatim and never averaged. Classification also
    #: uses it to carry the PARSED label, which the confusion matrix is built from.
    meta: Dict[str, Any] = field(default_factory=dict)


_MARKDOWN = re.compile(r"^\s*(\*\*|__|##|#\s+|>\s+)")
_LEADIN = re.compile(r"^[\s*_#>`]*(category|label|answer|class|classification)\s*[:\-]\s*", re.I)


class ClassificationTask:
    """One corpus's label set, and every behaviour that follows from it.

    `aliases` maps a canonical label to the spellings a model might answer with. Order
    matters: the table is searched longest-canonical-first so a broad alias cannot shadow
    a narrower label ("Tech" must not swallow "Sci/Tech").

    `rules` is the keyword baseline's table, ordered, first match wins. `default_label` is
    its catch-all. Both are the example's to supply, because a rule set is a claim about a
    corpus, not about classification.
    """

    def __init__(
        self,
        labels: Sequence[str],
        aliases: Optional[Dict[str, Sequence[str]]] = None,
        rules: Optional[Sequence[Tuple[str, str]]] = None,
        default_label: Optional[str] = None,
        prompt_dir: Optional[Path] = None,
    ) -> None:
        if not labels:
            raise ValueError("a classification task needs labels; there is no default")
        self.labels: List[str] = list(labels)
        # Every label is its own alias, lowercased, before anything the example adds.
        table: Dict[str, List[str]] = {lab: [lab.lower()] for lab in self.labels}
        for lab, extra in (aliases or {}).items():
            if lab not in table:
                raise ValueError(f"alias for unknown label {lab!r}")
            table[lab].extend(a.lower() for a in extra)
        # Longest canonical label first: "Sci/Tech" must be tried before "Tech" would be,
        # and "EducationalInstitution" before "Institution".
        self._aliases: List[Tuple[str, Tuple[str, ...]]] = [
            (lab, tuple(dict.fromkeys(table[lab])))
            for lab in sorted(self.labels, key=len, reverse=True)
        ]
        self.rules: List[Tuple[str, str]] = list(rules or [])
        self.default_label = default_label or self.labels[0]
        self.prompt_dir = prompt_dir
        self._prompt_cache: Dict[str, str] = {}
        self._pipe: Any = None
        self._pipe_key: Optional[tuple] = None
        self._upstream_cache: Dict[str, Optional[str]] = {}

    # ── the prompt ───────────────────────────────────────────────────────────
    def prompt(self, params: Dict[str, Any]) -> str:
        """The instruction every hosted arm sends, read from ONE file.

        Duplicated per-config prompts are identical by generation rather than by
        construction; one hand-edit makes an arm incomparable and nothing says so. An
        explicit `prompt:` still wins, so prompt research stays possible -- but it is then
        a visible override recorded on the run.
        """
        if params.get("prompt"):
            return str(params["prompt"])
        rel = str(params.get("prompt_file") or "prompt.txt")
        base = self.prompt_dir or Path.cwd()
        path = (base / rel).resolve()
        key = str(path)
        if key not in self._prompt_cache:
            if not path.is_file():
                raise SystemExit(f"prompt file not found: {path}")
            self._prompt_cache[key] = path.read_text(encoding="utf-8").strip()
        return self._prompt_cache[key]

    def prompt_sha256(self, params: Dict[str, Any]) -> str:
        return hashlib.sha256(self.prompt(params).encode()).hexdigest()

    # ── the parser, which is also part of the system under test ──────────────
    def parse_label(self, text: str) -> Optional[str]:
        """The model's answer as one of `labels`, or None when no label can be found.

        None is not "wrong", it is UNPARSEABLE, and the two are reported separately. An
        arm returning prose a third of the time and correct whenever it answers is a
        different engineering problem from one that answers crisply and is wrong; a single
        accuracy number hides that completely.

        HOW LENIENT TO BE IS A REAL DECISION. Exact-match-only scores "Sports." as wrong
        and measures obedience rather than classification. Matching anywhere in a long
        answer lets "this is not about sports, it is business" resolve to whichever alias
        appears first. The middle taken here: strip markdown, quotes, trailing punctuation
        and a leading "Category:"; accept an exact alias match on the remainder; otherwise
        take the EARLIEST alias occurring as a whole word, which is the answer-first
        convention the prompt asks for.

        Whatever this does is hashed into `parser_sha256`, so a later change to it shows
        up as a different system rather than as models mysteriously improving. It is not
        hypothetical: on AG News the leniency here was worth 7.5 accuracy points to one
        arm, wider than the gap separating most of the field.
        """
        if not text:
            return None
        cleaned = _LEADIN.sub("", text.strip())
        cleaned = cleaned.strip(" \t\n*_`\"'.,:;!?()[]{}")
        low = cleaned.lower()
        for label, aliases in self._aliases:
            if low in aliases:
                return label
        best: Optional[Tuple[int, str]] = None
        for label, aliases in self._aliases:
            for alias in aliases:
                m = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", low)
                if m and (best is None or m.start() < best[0]):
                    best = (m.start(), label)
        return best[1] if best else None

    def parser_sha256(self) -> str:
        """Hash of the parser's source AND the alias table it is driven by.

        Hashing the source rather than a version string someone must remember to bump.
        The table is included because it is the parser as much as the code is -- adding
        one alias changes what every hosted arm scores.
        """
        from codehash import code_digest  # noqa: PLC0415

        # `_MARKDOWN` and `_LEADIN` decide whether "**Category:** Sports" parses as a
        # label at all. `getsource` covers only the def block, so editing either moved
        # every score under an identical hash until a review caught it.
        return code_digest(ClassificationTask.parse_label,
                           consts={"aliases": self._aliases,
                                   "_MARKDOWN": _MARKDOWN, "_LEADIN": _LEADIN})

    def labels_sha256(self) -> str:
        """The label set is the task. Change it and every arm answers a new question."""
        return hashlib.sha256(repr(self.labels).encode()).hexdigest()

    def rules_sha256(self) -> str:
        return hashlib.sha256(repr(self.rules).encode()).hexdigest()

    # ── providers ────────────────────────────────────────────────────────────
    def constant(self, text: str, params: Dict[str, Any]) -> Result:
        """Always the same label. The floor, and on a balanced slice an exact one.

        With k classes drawn evenly this scores 1/k on the nose -- not "about" 1/k. That
        makes it a calibration check on the harness as much as a baseline on the task: any
        other value means the slice is unbalanced or the scorer is wrong, and no other row
        can be trusted until it reads right.
        """
        label = str(params.get("label", self.labels[0]))
        return Result(output=label, cost_usd=0.0, meta={"predicted": label})

    def keyword(self, text: str, params: Dict[str, Any]) -> Result:
        """Ordered regex rules, first match wins, then the catch-all default.

        The shape of a rule-based classifier that is already in production somewhere and
        has never been measured. Its failure mode is worth knowing: on AG News the rules
        under-triggered so badly that the default fired on 15 of 20 dev items, which
        accuracy alone did not reveal and the confusion matrix did immediately.
        """
        low = text.lower()
        for label, pattern in self.rules:
            if re.search(pattern, low):
                return Result(output=label, cost_usd=0.0, meta={"predicted": label})
        return Result(output=self.default_label, cost_usd=0.0,
                      meta={"predicted": self.default_label})

    def _local_pipeline(self, params: Dict[str, Any], task: str) -> Any:
        """Load once, module-level, so `warmup()` pays the cost outside the timed loop."""
        key = (params.get("model"), params.get("revision"), params.get("device"), task)
        if self._pipe is not None and self._pipe_key == key:
            return self._pipe
        from transformers import pipeline  # noqa: PLC0415 - only when an arm asks

        kwargs: Dict[str, Any] = {"model": params["model"]}
        if params.get("revision"):
            kwargs["revision"] = params["revision"]
        if params.get("device"):
            kwargs["device"] = params["device"]
        self._pipe = pipeline(task, **kwargs)
        self._pipe_key = key
        return self._pipe

    def encoder_window(self) -> Optional[int]:
        """The loaded model's input ceiling, from the MODEL config, not the tokenizer.

        The summarisation example lost an afternoon to `tokenizer.model_max_length` being
        HuggingFace's ~1e30 sentinel on a checkpoint whose tokenizer_config never set it,
        which silently made both the truncation check and `truncation=True` no-ops.
        Returns None rather than loading weights as a side effect of being asked.
        """
        cfg = getattr(getattr(self._pipe, "model", None), "config", None)
        for attr in ("max_position_embeddings", "n_positions", "max_source_positions"):
            value = getattr(cfg, attr, None)
            if isinstance(value, int) and 0 < value < 1_000_000:
                return value
        return None

    def hf_local(self, text: str, params: Dict[str, Any]) -> Result:
        """A model fine-tuned ON this task. The in-distribution specialist.

        `label_order` maps head positions to labels. Many checkpoints leave `id2label` at
        "LABEL_0", so without it the classes permute silently -- every prediction is still
        a valid label, nothing errors, and the model takes the blame for the config.
        """
        pipe = self._local_pipeline(params, "text-classification")
        out = pipe(text, truncation=True)[0]
        raw = str(out["label"])
        order = params.get("label_order") or self.labels
        m = re.fullmatch(r"LABEL_(\d+)", raw)
        predicted = order[int(m.group(1))] if m and int(m.group(1)) < len(order) else raw
        confidence = float(out.get("score", 0.0))
        return Result(
            output=predicted,
            cost_usd=0.0,
            meta={"predicted": predicted, "raw_label": raw, "score": confidence},
            extra={"confidence": confidence},
        )

    def hf_zeroshot(self, text: str, params: Dict[str, Any]) -> Result:
        """An NLI model classifying with no task fine-tune at all.

        The control that separates "this architecture is good" from "this checkpoint saw
        the test distribution" -- the two explanations the summarisation study left
        tangled together.
        """
        pipe = self._local_pipeline(params, "zero-shot-classification")
        hypothesis = str(params.get("hypothesis_template", "This text is about {}."))
        out = pipe(text, candidate_labels=list(self.labels),
                   hypothesis_template=hypothesis, truncation=True)
        predicted = str(out["labels"][0])
        return Result(
            output=predicted,
            cost_usd=0.0,
            meta={"predicted": predicted,
                  "all_scores": dict(zip(out["labels"], out["scores"]))},
            extra={"confidence": float(out["scores"][0])},
        )

    def litellm(self, text: str, params: Dict[str, Any]) -> Result:
        """A hosted model through the proxy.

        Carries two lessons that cost the summarisation study real findings: `reasoning`
        must travel in extra_body or the request silently contradicts the config, and a
        response cut off at max_tokens scores like a bad model rather than a small budget,
        so `truncated` is a metric and not a log line.
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
            messages=[{"role": "user", "content": self.prompt(params) + "\n\n" + text}],
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
            cost_usd=_billed(usage) if _billed(usage) is not None else _price(params, ti, to),
            extra={
                "truncated": 1.0 if truncated else 0.0,
                **({"reasoning_tokens": float(reasoning_tokens)}
                   if reasoning_tokens is not None else {}),
            },
            meta={
                "predicted": self.parse_label(raw),
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

    def providers(self) -> Dict[str, Callable[[str, Dict[str, Any]], Result]]:
        return {
            "constant": self.constant,
            "hf_local": self.hf_local,
            "hf_zeroshot": self.hf_zeroshot,
            "keyword": self.keyword,
            "litellm": self.litellm,
        }

    def call_system(self, text: str, params: Dict[str, Any]) -> Result:
        provider = params.get("provider", "litellm")
        fn = self.providers().get(provider)
        if fn is None:
            raise SystemExit(
                f"unknown provider {provider!r} — expected one of {sorted(self.providers())}"
            )
        started = time.perf_counter()
        result = fn(text, params)
        if result.latency_ms is None:
            result.latency_ms = round((time.perf_counter() - started) * 1000, 3)
        return result

    def warmup(self, params: Dict[str, Any]) -> None:
        """Load weights / prove the endpoint answers, before anything is timed or paid."""
        provider = params.get("provider", "litellm")
        if provider == "hf_local":
            self._local_pipeline(params, "text-classification")
        elif provider == "hf_zeroshot":
            self._local_pipeline(params, "zero-shot-classification")
        elif provider == "litellm":
            self.litellm("Warm up.", {**params, "max_tokens": 1})
        # `keyword` and `constant` have nothing to warm: no weights, no endpoint. An
        # `else` here would send a PAID warm-up on behalf of an arm that cannot cost
        # anything -- which is what the first version of this did.
        self.score(self.labels[0], self.labels[0], "a source text")

    # ── fingerprint ──────────────────────────────────────────────────────────
    def _resolve_upstream(self, alias: Optional[str]) -> Optional[str]:
        """What upstream model an alias points at, or None if the proxy cannot say."""
        if not alias:
            return None
        if alias in self._upstream_cache:
            return self._upstream_cache[alias]
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
        self._upstream_cache[alias] = resolved
        return resolved

    def fingerprint(self, params: Dict[str, Any], hf_fingerprint: Any = None) -> Dict[str, Any]:
        """What this arm's system under test IS.

        `parser_sha256` and `labels_sha256` go on EVERY arm, including local ones that
        never touch the parser. The question they answer is "would this number change if
        the parser / label set changed?", and for a hosted arm the answer is yes. An
        identical hash across both kinds is what makes "no" checkable rather than assumed.
        """
        provider = params.get("provider", "litellm")
        common = {
            "parser_sha256": self.parser_sha256(),
            "provider": provider,
            "labels_sha256": self.labels_sha256(),
            "labels": list(self.labels),
        }

        if provider in ("hf_local", "hf_zeroshot"):
            out = dict(hf_fingerprint or {})
            if provider == "hf_zeroshot":
                # The hypothesis template IS the prompt for a zero-shot arm.
                out["hypothesis_template"] = params.get("hypothesis_template")
            if provider == "hf_local":
                out["label_order"] = list(params.get("label_order") or self.labels)
                out["encoder_window"] = self.encoder_window()
            out.update(common)
            return out

        if provider == "keyword":
            return {"id": "keyword", "rules_sha256": self.rules_sha256(),
                    "default_label": self.default_label, **common}

        if provider == "constant":
            # Deliberately NOT carrying rules_sha256: this arm runs no rules, and hashing
            # something it does not use implies an edit to those rules could change it.
            return {"id": f"constant:{params.get('label')}",
                    "label": params.get("label"), **common}

        alias = params.get("model")
        upstream = self._resolve_upstream(alias)
        return {
            "id": upstream or alias,
            "alias": alias,
            "id_source": "proxy-model-info" if upstream else "alias-unresolved",
            "revision": None,
            "revision_source": "api-model-string",
            "endpoint": os.environ.get("LITELLM_BASE_URL"),
            "provider_routing": params.get("provider_routing"),
            "temperature": params.get("temperature"),
            "prompt_sha256": self.prompt_sha256(params),
            "reasoning": params.get("reasoning"),
            **common,
        }

    # ── the scorers ──────────────────────────────────────────────────────────
    def score(self, output: str, reference: Optional[str],
              source: Optional[str] = None) -> Dict[str, float]:
        """Exact label match, plus the ways an answer fails that accuracy cannot see."""
        predicted = self.parse_label(output)
        words = len(output.split())
        out: Dict[str, float] = {
            "parsed": 1.0 if predicted is not None else 0.0,
            "answer_words": float(words),
            "fmt_verbose": 1.0 if words > 2 else 0.0,
            "fmt_markdown": 1.0 if _MARKDOWN.match(output) else 0.0,
        }
        if reference is None:
            return out
        gold = reference.strip()
        out["correct"] = 1.0 if predicted == gold else 0.0
        # Right only because the parser was generous. If this is large, the accuracy
        # column is partly measuring parse_label rather than the model.
        out["correct_after_repair"] = (
            1.0 if (out["correct"] and output.strip() != gold) else 0.0
        )
        return out


PRIMARY_METRIC = "correct"

METRIC_KINDS = {
    # The one that ranks. Binary per item, so its mean IS accuracy.
    "correct": "quality",
    # Quality too, deliberately: an arm that cannot be parsed cannot be deployed,
    # whatever it knows.
    "parsed": "quality",
    "correct_after_repair": "descriptive",
    "answer_words": "descriptive",
    "fmt_verbose": "descriptive",
    "fmt_markdown": "descriptive",
    # Not quality -- a confident wrong answer is worse than a hesitant one -- but the
    # input to a calibration question no summarisation metric could ask.
    "confidence": "descriptive",
    "truncated": "descriptive",
    "reasoning_tokens": "descriptive",
}

#: Extra failure shapes worth retrying, on top of the core's list.
TRANSIENT_MARKERS = ("model is warming up", "no instances available", "upstream")


# ── provider-agnostic helpers ────────────────────────────────────────────────
def _as_dict(obj: Any) -> Any:
    """Best-effort plain-data view of a provider SDK object, for the run record.

    Degrades to a string rather than raising: a failure here must never lose a paid run.
    """
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


def _billed(usage: Any) -> Optional[float]:
    """What the PROVIDER says this call cost, or None if it did not say.

    WHY THIS OUTRANKS THE PRICE TABLE. `usd_per_mtok_in/out` is one price per model
    ALIAS, and an alias is not a price: OpenRouter routes each request to one of several
    upstream providers -- a single NER run recorded Novita 262 times, Parasail 9, DeepInfra
    6, Nebius 3 -- and they charge differently. The effective price is a routing-dependent
    mixture that no config can state in advance.

    Measured across the four examples in this repo, the price table was wrong by 0.67x to
    3.21x PER ARM, in both directions, and it reordered arms by cost: on few_nerd_280
    `glm_s` is the 2nd-cheapest arm by the table and the 9th by what was actually billed,
    and the cheapest-to-dearest span is 155x by the table against 90x billed. Every cost
    figure computed from the table is therefore an estimate of a number the provider
    already told us exactly.

    So: bill what was billed, and fall back to the table only when the provider is silent.
    """
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
    """Cost from prices declared in the config, or None when they are not.

    None means UNPRICED. A local arm reports 0.0 instead -- a measured zero is a claim,
    a missing value is not.
    """
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    if pin is None or pout is None or tin is None or tout is None:
        return None
    return round(tin / 1e6 * float(pin) + tout / 1e6 * float(pout), 8)
