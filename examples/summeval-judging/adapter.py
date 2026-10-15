"""SummEval: can a system judge summaries the way expert annotators do?

One item is one CNN/DailyMail article with 16 machine summaries (from 2019-era summarisers)
and 11 human reference summaries. The system under test scores each of the 16 summaries on
four dimensions -- coherence, consistency, fluency, relevance -- and is graded on how well its
scores ORDER the 16 the way the mean of three expert annotators does (Fabbri et al. 2021).

WHAT THIS EXPERIMENT BREAKS THAT THE OTHER FIVE DID NOT
  1. The answer is a vector of judgements, and the metric is a RANK CORRELATION -- not
     overlap with a reference, not 0/1, not set F1, not nDCG. Kendall tau-b per article,
     averaged over the four dimensions, is the primary metric; it is per item, so the
     harness's paired permutation tests and Holm apply unchanged.
  2. It measures the instrument. Two of the arms are METRICS the rest of this repository
     ranks by: ROUGE, and `coverage`, the summarisation experiment's own primary metric. How
     well they agree with experts is how far that experiment's leaderboard can be believed.
  3. It is the LLM-as-judge question in measurable form: when a model grades text, does it
     grade like a person? That is the question behind every silver reference.

THE ARMS
  litellm    a hosted LLM judge: reads the article and the 16 summaries, returns JSON scores
             (prompt.txt). It is never shown the human references.
  rouge      ROUGE-1/2/L F1 of each summary against each human reference, averaged over the
             references. Reference-based: the same score stands for all four dimensions.
  coverage   this repository's summarisation metric (ROUGE-Lsum recall, the summary clipped
             to the reference's length), imported from that example's own scorer and
             averaged over the references.
  bartscore  log-likelihood of the summary given the article under facebook/bart-large-cnn
             (Yuan et al. 2021, the source->hypothesis direction). Local, CPU.
  length     the summary's word count. A confound, not a judge: if it correlates with the
             experts, so does anything that rewards length.
  random     seeded random scores: the floor every judge must clear, near tau = 0.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
import gateway  # noqa: E402
from codehash import code_digest  # noqa: E402

DIMS = ("coherence", "consistency", "fluency", "relevance")
N_SUMMARIES = 16


@dataclass
class Result:
    output: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    latency_ms: Optional[float] = None
    extra: Dict[str, float] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


def _item(text: str) -> Dict[str, Any]:
    """The item, as fetch.py wrote it: article, 16 summaries, the human references."""
    d = json.loads(text)
    if len(d.get("summaries") or []) != N_SUMMARIES:
        raise ValueError(f"item has {len(d.get('summaries') or [])} summaries, expected {N_SUMMARIES}")
    return d


def _broadcast(values: List[float]) -> str:
    """A single score per summary, stood in for all four dimensions (metric arms)."""
    return json.dumps({d: [round(float(v), 10) for v in values] for d in DIMS})


# ── the prompt, in one file ──────────────────────────────────────────────────
_PROMPT_CACHE: Dict[str, str] = {}


def _prompt(params: Dict[str, Any]) -> str:
    if params.get("prompt"):
        return str(params["prompt"])
    path = (HERE / str(params.get("prompt_file") or "prompt.txt")).resolve()
    if str(path) not in _PROMPT_CACHE:
        if not path.is_file():
            raise SystemExit(f"prompt file not found: {path}")
        _PROMPT_CACHE[str(path)] = path.read_text(encoding="utf-8").strip()
    return _PROMPT_CACHE[str(path)]


def _prompt_sha256(params: Dict[str, Any]) -> str:
    return hashlib.sha256(_prompt(params).encode()).hexdigest()


def _judge_message(item: Dict[str, Any], params: Dict[str, Any]) -> str:
    """Article and numbered summaries. The human references are deliberately left out:
    a judge shown them would be doing ROUGE's job, and that is a different arm."""
    summaries = "\n".join(f"{i}. {s.strip()}" for i, s in enumerate(item["summaries"], 1))
    return f"{_prompt(params)}\n\nARTICLE:\n{item['article'].strip()}\n\nSUMMARIES:\n{summaries}"


# ── the hosted judge ─────────────────────────────────────────────────────────
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
    """What the provider billed for this call; it outranks the price table (see the
    summarisation adapter for why: the table was wrong by 0.67x-3.21x per arm)."""
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


def _litellm(text: str, params: Dict[str, Any]) -> Result:
    client, route = gateway.client(params)
    extra_body = gateway.extra_body(params, route)
    content = text if params.get("_raw_message") else _judge_message(_item(text), params)
    max_tokens = int(params.get("max_tokens", 1500))
    resp = client.chat.completions.create(
        model=route["model"],
        temperature=float(params.get("temperature", 0.0)),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
        **({"extra_body": extra_body} if extra_body else {}),
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
    return Result(
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


# ── the metric arms ──────────────────────────────────────────────────────────
def _rouge(text: str, params: Dict[str, Any]) -> Result:
    """ROUGE F1 against each human reference, averaged over the references.

    Averaged, not max: this is the setup that reproduces G-Eval's published ROUGE-1 row
    (Liu et al. 2023, Table 1: rho 0.192, tau 0.150 averaged over the four dimensions;
    measured here on the same 100 articles: 0.190 and 0.149). Max over references and
    first-reference-only were also computed and do not reproduce it (0.198 / 0.158 rho).
    """
    from rouge_score import rouge_scorer  # noqa: PLC0415

    kind = str(params.get("metric", "rouge1"))
    scorer = rouge_scorer.RougeScorer([kind], use_stemmer=True)
    item = _item(text)
    vals = [sum(scorer.score(r, s)[kind].fmeasure for r in item["references"]) / len(item["references"])
            for s in item["summaries"]]
    return Result(output=_broadcast(vals), cost_usd=0.0)


_SUMM: Any = None


def _summarisation_scorer() -> Any:
    """The summarisation example's own score(): `coverage` is defined there, once."""
    global _SUMM
    if _SUMM is None:
        path = HERE.parent / "summarization-cnn-dailymail" / "adapter.py"
        spec = importlib.util.spec_from_file_location("_summ_adapter", path)
        mod = importlib.util.module_from_spec(spec)
        # Registered before it runs: its @dataclass looks itself up in sys.modules, and a
        # module loaded by path is not there unless put there.
        sys.modules["_summ_adapter"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _SUMM = mod
    return _SUMM


def _coverage(text: str, params: Dict[str, Any]) -> Result:
    score = _summarisation_scorer().score
    item = _item(text)
    vals = [sum(score(s, r)["coverage"] for r in item["references"]) / len(item["references"])
            for s in item["summaries"]]
    return Result(output=_broadcast(vals), cost_usd=0.0)


def _length(text: str, params: Dict[str, Any]) -> Result:
    return Result(output=_broadcast([len(s.split()) for s in _item(text)["summaries"]]), cost_usd=0.0)


def _random(text: str, params: Dict[str, Any]) -> Result:
    # Seeded by the config seed AND the item, so a rerun is identical and two items do not
    # share a draw.
    seed = f"{params.get('seed', 20261015)}:{hashlib.sha256(text.encode()).hexdigest()}"
    rng = random.Random(seed)
    return Result(output=json.dumps({d: [rng.randint(1, 5) for _ in range(N_SUMMARIES)] for d in DIMS}),
                  cost_usd=0.0)


_BART: Any = None
_BART_KEY: Optional[tuple] = None


def _bart(params: Dict[str, Any]) -> Any:
    global _BART, _BART_KEY
    key = (params.get("model"), params.get("revision"))
    if _BART_KEY != key:
        from transformers import AutoTokenizer, BartForConditionalGeneration  # noqa: PLC0415

        kw = {"revision": params["revision"]} if params.get("revision") else {}
        tok = AutoTokenizer.from_pretrained(params["model"], **kw)
        model = BartForConditionalGeneration.from_pretrained(params["model"], **kw).eval()
        _BART, _BART_KEY = (tok, model), key
    return _BART


def _bartscore(text: str, params: Dict[str, Any]) -> Result:
    """Mean log-probability of each summary's tokens given the article (source->hypothesis).

    The article is cut to BART's 1,024-token encoder window, exactly as the summarisation
    example's local arms see it; `input_truncated` records when that happened.
    """
    import torch  # noqa: PLC0415

    tok, model = _bart(params)
    item = _item(text)
    enc = tok(item["article"], truncation=True, max_length=1024, return_tensors="pt")
    full = len(tok(item["article"])["input_ids"])
    vals = []
    with torch.no_grad():
        for s in item["summaries"]:
            tgt = tok(s, truncation=True, max_length=256, return_tensors="pt")["input_ids"]
            out = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"], labels=tgt)
            vals.append(-float(out.loss))  # mean token NLL -> mean log-probability
    return Result(output=_broadcast(vals), cost_usd=0.0,
                  extra={"input_truncated": 1.0 if full > 1024 else 0.0})


PROVIDERS = {"litellm": _litellm, "rouge": _rouge, "coverage": _coverage,
             "bartscore": _bartscore, "length": _length, "random": _random}


def call_system(text: str, params: Dict[str, Any]) -> Result:
    provider = params.get("provider", "litellm")
    fn = PROVIDERS.get(provider)
    if fn is None:
        raise SystemExit(f"unknown provider {provider!r} -- expected one of {sorted(PROVIDERS)}")
    started = time.perf_counter()
    result = fn(text, params)
    if result.latency_ms is None:
        result.latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return result


# ── warm-up and fingerprint ──────────────────────────────────────────────────
_SAMPLE = json.dumps({"article": "The council met on Tuesday. It approved the budget.",
                      "summaries": [f"The council approved budget {i}." for i in range(N_SUMMARIES)],
                      "references": ["The council approved the budget."]})


def warmup(params: Dict[str, Any]) -> None:
    """Load what must be loaded, prove the endpoint answers, prove the scorer runs."""
    provider = params.get("provider", "litellm")
    if provider == "bartscore":
        _bartscore(_SAMPLE, params)
    elif provider == "coverage":
        _summarisation_scorer()
    elif provider == "litellm":
        _litellm("Warm up.", {**params, "max_tokens": 1, "_raw_message": True})
    gold = json.dumps({d: [float(i % 5 + 1) for i in range(N_SUMMARIES)] for d in DIMS})
    score(_broadcast([float(i) for i in range(N_SUMMARIES)]), gold)


def fingerprint(params: Dict[str, Any]) -> Dict[str, Any]:
    provider = params.get("provider", "litellm")
    code = {"rouge": _rouge, "coverage": _coverage, "length": _length, "random": _random}
    if provider in code:
        consts: Dict[str, Any] = {}
        if provider == "coverage":
            consts["summarisation_score"] = code_digest(_summarisation_scorer().score)
        return {"provider": provider, "id": provider if provider != "rouge" else str(params.get("metric")),
                "kind": "deterministic metric, no model and no network",
                "identity_declared": False, "revision_source": "not-a-model",
                "code_sha256": code_digest(code[provider], consts=consts)}
    if provider == "bartscore":
        from hf_identity import hf_model_fingerprint  # noqa: PLC0415

        key = (params.get("model"), params.get("revision"))
        fp = hf_model_fingerprint(params["model"], revision=params.get("revision"),
                                  device="cpu", precision="fp32",
                                  loaded_model=_BART[1] if _BART is not None and _BART_KEY == key else None)
        fp["code_sha256"] = code_digest(_bartscore)
        return fp
    alias = params.get("model")
    upstream, id_source = gateway.resolve_upstream(alias)
    return {"id": upstream or alias, "alias": alias, "id_source": id_source,
            "revision": None, "revision_source": "api-model-string",
            "endpoint": gateway.endpoint(), "provider_routing": params.get("provider_routing"),
            "temperature": params.get("temperature"), "prompt_sha256": _prompt_sha256(params),
            "reasoning": params.get("reasoning")}


# ── the scorer ───────────────────────────────────────────────────────────────
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

    Ties matter here more than anywhere else in this repository: an LLM judge gives integer
    scores 1-5 to 16 summaries, so it ties constantly, and tau-a would punish it for every
    tie as if it were a wrong ordering.
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


_JSON = re.compile(r"\{.*\}", re.S)


def parse_scores(output: str) -> Dict[str, Optional[List[float]]]:
    """{dimension: 16 numbers, or None}. Lenient about wrapping (markdown fences, a sentence
    before the JSON), strict about content: a dimension counts only with exactly 16 numbers."""
    m = _JSON.search(output or "")
    got: Dict[str, Optional[List[float]]] = {d: None for d in DIMS}
    if not m:
        return got
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return got
    if not isinstance(obj, dict):
        return got
    for d in DIMS:
        v = obj.get(d)
        if isinstance(v, list) and len(v) == N_SUMMARIES:
            try:
                got[d] = [float(x) for x in v]
            except (TypeError, ValueError):
                pass
    return got


def score(output: str, reference: Optional[str], source: Optional[str] = None) -> Dict[str, float]:
    """Per-article agreement with the experts: tau-b and Spearman per dimension, and means.

    A dimension the system did not return scores 0 on every correlation -- the same as a
    judge whose ordering is unrelated to the experts' -- and `parsed` says how many of the
    four dimensions arrived, so an unreadable reply is visible rather than averaged away.
    """
    got = parse_scores(output)
    out: Dict[str, float] = {"parsed": sum(v is not None for v in got.values()) / len(DIMS)}
    if reference is None:
        return out
    gold = json.loads(reference)
    taus, rhos, ties = [], [], []
    for d in DIMS:
        sys_scores = got[d]
        if sys_scores is None:
            t = r = 0.0
        else:
            t, r = kendall_tau_b(sys_scores, gold[d]), spearman(sys_scores, gold[d])
            pairs = N_SUMMARIES * (N_SUMMARIES - 1) / 2
            ties.append(sum(sys_scores[i] == sys_scores[j] for i in range(N_SUMMARIES)
                            for j in range(i + 1, N_SUMMARIES)) / pairs)
        out[f"tau_{d}"], out[f"rho_{d}"] = round(t, 10), round(r, 10)
        taus.append(t)
        rhos.append(r)
    out["tau"] = round(sum(taus) / len(DIMS), 10)
    out["rho"] = round(sum(rhos) / len(DIMS), 10)
    if ties:
        out["tie_rate"] = round(sum(ties) / len(ties), 10)
    return out


TRANSIENT_MARKERS = ("model is warming up", "no instances available", "upstream")

#: tau-b, not Spearman: it is the statistic G-Eval and the SummEval paper report beside
#: rho, and it is the one that handles the judges' constant ties honestly. Spearman is kept
#: for the literature comparison.
PRIMARY_METRIC = "tau"

METRIC_KINDS = {
    "tau": "quality", "rho": "quality",
    **{f"tau_{d}": "quality" for d in DIMS},
    **{f"rho_{d}": "quality" for d in DIMS},
    # Descriptive: how many dimensions came back readable, how often the judge tied two
    # summaries, whether it ran out of tokens, whether it billed reasoning, whether a
    # local model saw only part of the article.
    "parsed": "descriptive", "tie_rate": "descriptive", "truncated": "descriptive",
    "reasoning_tokens": "descriptive", "input_truncated": "descriptive",
}
