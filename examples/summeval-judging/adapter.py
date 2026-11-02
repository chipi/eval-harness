"""SummEval: can a system judge summaries the way expert annotators do?

One item is one CNN/DailyMail article with 16 machine summaries (from 2019-era summarisers)
and 11 human reference summaries. The system under test scores each of the 16 summaries on
four dimensions -- coherence, consistency, fluency, relevance -- and is graded on how well its
scores ORDER the 16 the way the mean of three expert annotators does (Fabbri et al. 2021).

WHAT THIS EVAL BREAKS THAT THE OTHER FIVE DID NOT
  1. The answer is a vector of judgements, and the metric is a RANK CORRELATION -- not
     overlap with a reference, not 0/1, not set F1, not nDCG. Kendall tau-b per article,
     averaged over the four dimensions, is the primary metric; it is per item, so the
     harness's paired permutation tests and Holm apply unchanged.
  2. It measures the instrument. Two of the arms are METRICS the rest of this repository
     ranks by: ROUGE, and `coverage`, the summarisation eval's own primary metric. How
     well they agree with experts bounds what a lead on that eval's leaderboard means
     to a person (measured on 2019-era summaries, not the LLM-written ones it ranks).
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

MODES (litellm and random only; the default, `grade`, is everything above)
  mode: pick      the judge names the best of the 16 summaries (prompt_pick.txt); scored `top1`
                  beside `top1_chance`, what a random pick gets.
  mode: pairwise  the judge says which of two is better for `pairs_per_item` (8) seeded pairs
                  (prompt_pairwise.txt); scored `pair_agreement` over the pairs the experts
                  rank apart. The `random` arm in either mode is the floor (`min_metric`).
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
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


# ── what the system is asked: grade (above), pick the best, or compare pairs ─────────────
# A judge scorer validated in a mode (docs/rfc/RFC-005 "Judging modes") is validated as an arm
# with that `mode`: `pick` names the best of the article's 16 summaries and is scored `top1`;
# `pairwise` says which of two is better, for `pairs_per_item` seeded pairs, and is scored
# `pair_agreement`. Only the hosted judge (`litellm`) and the `random` floor have the modes.
MODES = ("grade", "pick", "pairwise")
PAIRS_PER_ITEM = 8
PAIR_SEED = 20261015
#: The last lines of the pick and pairwise messages: the same words judging.py's
#: build_pick_message / build_pairwise_message end with (tests/test_judge_score.py holds them equal).
PICK_REMINDER = (
    'Begin your reply with the JSON object, for example {"best": [3]}, naming several numbers when '
    "they are equally the best; write nothing after it."
)
PAIR_REMINDER = (
    'Begin your reply with the JSON object: {"better": 1}, {"better": 2} or {"better": "tie"}; '
    "write nothing after it."
)
TIE_EPS = 1e-9


def _mode(params: Dict[str, Any]) -> str:
    mode = params.get("mode") or "grade"
    if mode not in MODES:
        raise SystemExit(f"unknown mode {mode!r} -- expected one of {list(MODES)}")
    return mode


def _pairs_per_item(params: Dict[str, Any]) -> int:
    k = params.get("pairs_per_item", PAIRS_PER_ITEM)
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= N_SUMMARIES * (N_SUMMARIES - 1) // 2:
        raise SystemExit(f"pairs_per_item must be a whole number from 1 to 120, got {k!r}")
    return k


def _pairs(item: Dict[str, Any], params: Dict[str, Any]) -> List[tuple]:
    """The pairs of an article's 16 summaries a pairwise arm compares: `pairs_per_item` of the
    120, each as (shown first, shown second), seeded by `pair_seed` and the article alone. The
    sample is drawn blind to the experts (call_system never sees them) and is the same for every
    arm; `score` keeps the pairs the experts rank apart."""
    ident = hashlib.sha256("\x00".join([item["article"], *item["summaries"]]).encode()).hexdigest()
    rng = random.Random(f"{params.get('pair_seed', PAIR_SEED)}:{ident}")
    chosen = rng.sample(list(itertools.combinations(range(N_SUMMARIES), 2)), _pairs_per_item(params))
    return [(a, b) if rng.random() < 0.5 else (b, a) for a, b in chosen]


def _pick_message(item: Dict[str, Any], params: Dict[str, Any]) -> str:
    """Article and the 16 numbered summaries, as `_judge_message` lays them out, then the
    instruction to answer only the JSON. The prompt's `{n}` is the count."""
    summaries = "\n".join(f"{i}. {s.strip()}" for i, s in enumerate(item["summaries"], 1))
    return (f"{_prompt(params).replace('{n}', str(N_SUMMARIES))}\n\nARTICLE:\n{item['article'].strip()}"
            f"\n\nSUMMARIES:\n{summaries}\n\n{PICK_REMINDER}")


def _pair_message(item: Dict[str, Any], first: int, second: int, params: Dict[str, Any]) -> str:
    summaries = "\n".join(f"{i}. {item['summaries'][k].strip()}" for i, k in enumerate((first, second), 1))
    return (f"{_prompt(params).replace('{n}', '2')}\n\nARTICLE:\n{item['article'].strip()}"
            f"\n\nSUMMARIES:\n{summaries}\n\n{PAIR_REMINDER}")


def _reply_object(output: Optional[str]) -> Optional[Dict[str, Any]]:
    """The first JSON object in a reply (an explanation may follow it, braces and all), or None."""
    text = output or ""
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, _ = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            i = text.find("{", i + 1)
            continue
        return obj if isinstance(obj, dict) else None
    return None


def _read_pick(output: str) -> Optional[List[int]]:
    """The 1-based numbers a pick reply names: a non-empty list of distinct whole numbers in
    1..16, else None (judging.parse_pick)."""
    v = (_reply_object(output) or {}).get("best")
    if not isinstance(v, list) or not v or len(set(v)) != len(v):
        return None
    if any(isinstance(x, bool) or not isinstance(x, int) or not 1 <= x <= N_SUMMARIES for x in v):
        return None
    return list(v)


def _read_better(output: str) -> Any:
    """1, 2 or "tie", else None (judging.parse_pairwise)."""
    v = (_reply_object(output) or {}).get("better")
    if isinstance(v, bool):
        return None
    if isinstance(v, int) and v in (1, 2):
        return v
    if isinstance(v, str) and v.strip().lower() == "tie":
        return "tie"
    return None


def _pick_output(reply: str) -> str:
    """What a pick arm stores: the parsed pick, or null with the start of the reply when it did
    not parse, so `score` always knows the mode."""
    best = _read_pick(reply)
    return json.dumps({"best": best} if best else {"best": None, "reply": (reply or "")[:300]})


def _pairs_output(pairs: List[tuple], betters: List[Any]) -> str:
    return json.dumps({"pairs": [{"a": a, "b": b, "better": v} for (a, b), v in zip(pairs, betters)]})


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
    item = _item(text) if not params.get("_raw_message") else None
    if item is not None and params.get("inputs") == "published":
        item = _published_item(item)
    mode = _mode(params)
    if item is None or mode == "grade":
        return _chat(text if item is None else _judge_message(item, params), params)
    if mode == "pick":
        res = _chat(_pick_message(item, params), params)
        res.output = _pick_output(res.output)
        return res
    pairs = _pairs(item, params)
    replies = [_chat(_pair_message(item, a, b, params), params) for a, b in pairs]
    return Result(
        output=_pairs_output(pairs, [_read_better(r.output) for r in replies]),
        tokens_in=_total([r.tokens_in for r in replies]),
        tokens_out=_total([r.tokens_out for r in replies]),
        cost_usd=_total([r.cost_usd for r in replies]),
        extra={"truncated": max(r.extra.get("truncated", 0.0) for r in replies),
               **({"reasoning_tokens": _total([r.extra.get("reasoning_tokens") for r in replies])}
                  if all("reasoning_tokens" in r.extra for r in replies) else {})},
        # The harness reads meta["calls"] as a list of call records and meta["finish_reason"] as the
        # provider's string ("length" marks a reply cut at max_tokens): one record per pair's call.
        meta={"finish_reason": next((f for r in replies if (f := r.meta.get("finish_reason")) == "length"),
                                    replies[0].meta.get("finish_reason")),
              "response_model": replies[0].meta.get("response_model"),
              "provider": replies[0].meta.get("provider"),
              "calls": [{"finish_reason": r.meta.get("finish_reason"), "tokens_in": r.tokens_in,
                         "tokens_out": r.tokens_out} for r in replies]},
    )


def _total(values: List[Any]) -> Any:
    """The sum of the calls' counts, or None when any call did not report one (None is not 0)."""
    return None if any(v is None for v in values) else round(sum(values), 10)


def _chat(content: str, params: Dict[str, Any]) -> Result:
    """One call to the hosted judge with this message."""
    client, route = gateway.client(params)
    extra_body = gateway.extra_body(params, route)
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
    first-reference-only were also computed and do not reproduce it (0.198 / 0.159 rho;
    calibrate.py recomputes all three).
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


def _random_modal(text: str, params: Dict[str, Any]) -> Result:
    """The floor in pick and pairwise mode: a seeded random pick, or a random winner of each
    sampled pair (never a tie). Its top1 is the chance a random pick has, its pair_agreement
    near 0.5, which is the `min_metric` a judge must clear."""
    item = _item(text)
    rng = random.Random(f"{params.get('seed', 20261015)}:{hashlib.sha256(text.encode()).hexdigest()}")
    if _mode(params) == "pick":
        return Result(output=json.dumps({"best": [rng.randint(1, N_SUMMARIES)]}), cost_usd=0.0)
    pairs = _pairs(item, params)
    return Result(output=_pairs_output(pairs, [rng.choice([1, 2]) for _ in pairs]), cost_usd=0.0)


_BART: Any = None
_BART_KEY: Optional[tuple] = None


def _bart(params: Dict[str, Any]) -> Any:
    global _BART, _BART_KEY
    key = (params.get("model"), params.get("revision"))
    if _BART_KEY != key:
        from transformers import AutoTokenizer, BartForConditionalGeneration  # noqa: PLC0415

        kw = {"revision": params["revision"]} if params.get("revision") else {}
        tok = AutoTokenizer.from_pretrained(params["model"], **kw)  # every config that reaches this pins `revision`  # nosec B615
        model = BartForConditionalGeneration.from_pretrained(params["model"], **kw).eval()  # every config that reaches this pins `revision`  # nosec B615
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


# ── UniEval (Zhong et al. 2022): a T5 evaluator trained for these four dimensions ─────
# Re-implemented from its MIT code (maszhongming/UniEval at d33e7b6c, metric/scorer.py and
# metric/evaluator.py), not imported: each dimension is a yes/no question, the score is
# P("Yes") / (P("Yes") + P("No")) at the first decoder step, inputs truncated to 1,024
# tokens, and consistency and fluency are scored per sentence (nltk's sent_tokenize) and
# averaged. `inputs` picks the text it scores:
#   ours       this eval's items -- the text every other arm saw -- with the first of
#              the 11 references for relevance (UniEval asks for one);
#   published  UniEval's own SummEval inputs (its reproduce/ file, cased text and its one
#              reference), each summary matched to its row through the original release.
SOURCES = HERE.parents[1] / "harness" / "data" / "sources"
UNIEVAL_INPUTS_URL = ("https://raw.githubusercontent.com/maszhongming/UniEval/"
                      "d33e7b6cfebe97b2bafe435adbd818230d5a416a/reproduce/data/summarization/summeval.json")
ORIGINAL_URL = "https://storage.googleapis.com/sfr-summarization-repo-research/model_annotations.aligned.jsonl"
_UE_QUESTIONS = {
    "coherence": "question: Is this a coherent summary to the document? </s> summary: {out} </s> document: {src}",
    "consistency": "question: Is this claim consistent with the document? </s> claim: {out} </s> document: {src}",
    "fluency": "question: Is this a fluent paragraph? </s> paragraph: {out}",
    "relevance": "question: Is this summary relevant to the reference? </s> summary: {out} </s> reference: {ref}",
}
#: sha256 of every download the UniEval arms read, as the committed runs read them. Neither
#: URL is versioned (the release file is a bucket object; nltk.download fetches whatever
#: punkt_tab is current), so a mismatch means a different input, and the run stops.
UNIEVAL_INPUTS_SHA256 = "b109068754e58722f7e50f1bef70cf121eb34c9015fc3486f51bc5b8e3e3ec81"
ORIGINAL_SHA256 = "f0d4166e0cdeb439b387c4449634b067b7e9f721b9ef4c2b722f6b7550d3d6ab"
#: Over punkt_tab/english, the one model sent_tokenize loads: sorted file names and bytes.
PUNKT_ENGLISH_SHA256 = "158f5e4684a0852ae6a6e973c1e17978a4b1d780a8e353a18bc0c10a068aa07b"
#: UniEval's tokenizer as transformers 4.55 built it from the checkpoint's spiece.model, saved
#: once. transformers 5 builds a different one: it drops the "▁" token before every literal
#: `</s>` separator in UniEval's prompts, so every input reaches the model one token shorter
#: than UniEval as published (and as these runs were measured). Loading this file under 5.x
#: gives 4.55's token ids exactly.
UNIEVAL_TOKENIZER = HERE / "unieval_tokenizer" / "tokenizer.json"
UNIEVAL_TOKENIZER_SHA256 = "1a1d3011daac8f04654823d46e09b2e0e760276be5ad2731d2ad8b9a0996ddf5"  # gitleaks:allow — a file's sha256, not a credential
UNIEVAL_MODEL = "MingZhong/unieval-sum"
_UE: Any = None
_UE_KEY: Optional[tuple] = None
_UE_PUBLISHED: Any = None
_PUNKT_OK = False


def _cached(path: Path, url: str, sha256: str) -> Path:
    if not path.is_file():
        import urllib.request  # noqa: PLC0415

        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 — a pinned https URL, its bytes checked by sha256  # nosec B310
            path.write_bytes(r.read())
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    if got != sha256:
        raise RuntimeError(f"{path.name}: sha256 {got} is not the pinned {sha256}; "
                           f"{url} no longer serves the file the runs used")
    return path


def punkt_english_digest(folder: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(folder.iterdir()):
        h.update(f.name.encode() + b"\x00" + f.read_bytes() + b"\x1e")
    return h.hexdigest()


def _sentences(text: str) -> List[str]:
    global _PUNKT_OK
    import nltk  # noqa: PLC0415

    if not _PUNKT_OK:
        data = SOURCES / "summeval_nltk"
        if str(data) not in nltk.data.path:
            nltk.data.path.insert(0, str(data))
        try:
            nltk.data.find("tokenizers/punkt_tab")
        except LookupError:
            nltk.download("punkt_tab", download_dir=str(data), quiet=True)
        got = punkt_english_digest(Path(nltk.data.find("tokenizers/punkt_tab/english/")))
        if got != PUNKT_ENGLISH_SHA256:
            raise RuntimeError(f"punkt_tab/english: sha256 {got} is not the pinned "
                               f"{PUNKT_ENGLISH_SHA256}; a different sentence splitter")
        _PUNKT_OK = True
    return nltk.sent_tokenize(text) or [text]


def _unieval_model(params: Dict[str, Any]) -> Any:
    global _UE, _UE_KEY
    key = (params.get("model"), params.get("revision"))
    if _UE_KEY != key:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # noqa: PLC0415

        kw = {"revision": params["revision"]} if params.get("revision") else {}
        if params["model"] == UNIEVAL_MODEL:
            from transformers import PreTrainedTokenizerFast  # noqa: PLC0415

            if hashlib.sha256(UNIEVAL_TOKENIZER.read_bytes()).hexdigest() != UNIEVAL_TOKENIZER_SHA256:
                raise SystemExit(f"{UNIEVAL_TOKENIZER}: not the pinned sha256 {UNIEVAL_TOKENIZER_SHA256}")
            tok = PreTrainedTokenizerFast(tokenizer_file=str(UNIEVAL_TOKENIZER), eos_token="</s>",  # noqa: S106 — special tokens, not passwords
                                          unk_token="<unk>", pad_token="<pad>", model_max_length=512)  # noqa: S106 — special tokens
        else:
            tok = AutoTokenizer.from_pretrained(params["model"], **kw)  # every config that reaches this pins `revision`  # nosec B615
        model = AutoModelForSeq2SeqLM.from_pretrained(params["model"], **kw).eval()  # every config that reaches this pins `revision`  # nosec B615
        _UE, _UE_KEY =(tok, model, tok("Yes")["input_ids"][0], tok("No")["input_ids"][0]), key
    return _UE


def _unieval_score(inputs: List[str], params: Dict[str, Any]) -> List[float]:
    """UniEval's UniEvaluator.score: P(Yes) / (P(Yes) + P(No)), batched."""
    import torch  # noqa: PLC0415

    tok, model, yes, no = _unieval_model(params)
    bs, out = int(params.get("batch_size", 8)), []
    with torch.no_grad():
        for i in range(0, len(inputs), bs):
            src = tok(inputs[i:i + bs], max_length=1024, truncation=True, padding=True, return_tensors="pt")
            tgt = tok(["No"] * len(inputs[i:i + bs]), return_tensors="pt", padding=True)["input_ids"][:, :1]
            logits = model(input_ids=src["input_ids"], attention_mask=src["attention_mask"], labels=tgt).logits
            p = torch.softmax(logits.view(-1, model.config.vocab_size), dim=1)
            out += [float(a / (a + b)) for a, b in zip(p[:, yes], p[:, no])]
    return out


def _unieval_published() -> Any:
    """(our normalised summary text -> {(doc, model_id)}, (doc, system_id) -> UniEval row)."""
    global _UE_PUBLISHED
    if _UE_PUBLISHED is None:
        norm = lambda t: " ".join(t.split()).lower()  # noqa: E731
        by_text: Dict[str, set] = {}
        orig = _cached(SOURCES / "summeval_original" / "model_annotations.aligned.jsonl", ORIGINAL_URL,
                       ORIGINAL_SHA256)
        for line in orig.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                by_text.setdefault(norm(r["decoded"]), set()).add((r["id"].split("-test-")[1], r["model_id"]))
        rows = {}
        ue = _cached(SOURCES / "summeval_unieval" / "summeval.json", UNIEVAL_INPUTS_URL,
                     UNIEVAL_INPUTS_SHA256)
        for r in json.loads(ue.read_text(encoding="utf-8")):
            rows[(r["doc_id"].split("-test-")[1], r["system_id"])] = r
        _UE_PUBLISHED = (norm, by_text, rows)
    return _UE_PUBLISHED


def _published_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """The item rewritten in UniEval's published copy of SummEval: the same article and
    summaries, cased and tokenised as that file has them. For the paired judge run that asks
    whether the judges were held back by this eval's lower-cased text."""
    norm, by_text, rows = _unieval_published()
    keys = [by_text.get(norm(s), set()) for s in item["summaries"]]
    docs = set.intersection(*[{d for d, _ in k} for k in keys]) if all(keys) else set()
    if len(docs) != 1:
        raise RuntimeError(f"this item matches {len(docs)} articles in the original release")
    doc = docs.pop()
    picked = [rows[(doc, sorted(m for d, m in k if d == doc)[0])] for k in keys]
    if len({r["source"] for r in picked}) != 1:
        raise RuntimeError("UniEval's rows for one article carry different source texts")
    return {**item, "article": picked[0]["source"], "summaries": [r["system_output"] for r in picked]}


def _unieval(text: str, params: Dict[str, Any]) -> Result:
    item = _item(text)
    if params.get("inputs") == "published":
        norm, by_text, rows = _unieval_published()
        keys = [by_text.get(norm(s), set()) for s in item["summaries"]]
        docs = set.intersection(*[{d for d, _ in k} for k in keys]) if all(keys) else set()
        if len(docs) != 1:
            raise RuntimeError(f"this item matches {len(docs)} articles in the original release")
        doc = docs.pop()
        picked = [rows[(doc, sorted(m for d, m in k if d == doc)[0])] for k in keys]
        srcs = [r["source"] for r in picked]
        outs = [r["system_output"] for r in picked]
        refs = [r["reference"] for r in picked]
    else:
        srcs = [item["article"]] * N_SUMMARIES
        outs = list(item["summaries"])
        refs = [item["references"][0]] * N_SUMMARIES
    scores: Dict[str, List[float]] = {}
    for d in ("coherence", "relevance"):
        scores[d] = _unieval_score([_UE_QUESTIONS[d].format(out=o, src=s, ref=r)
                                    for o, s, r in zip(outs, srcs, refs)], params)
    for d in ("consistency", "fluency"):
        sents = [_sentences(o) for o in outs]
        flat = _unieval_score([_UE_QUESTIONS[d].format(out=x, src=s, ref="")
                               for ss, s in zip(sents, srcs) for x in ss], params)
        vals, k = [], 0
        for ss in sents:
            vals.append(sum(flat[k:k + len(ss)]) / len(ss))
            k += len(ss)
        scores[d] = vals
    return Result(output=json.dumps({d: [round(v, 10) for v in scores[d]] for d in DIMS}), cost_usd=0.0)


PROVIDERS = {"litellm": _litellm, "rouge": _rouge, "coverage": _coverage,
             "bartscore": _bartscore, "unieval": _unieval, "length": _length, "random": _random}


def call_system(text: str, params: Dict[str, Any]) -> Result:
    provider = params.get("provider", "litellm")
    fn = PROVIDERS.get(provider)
    if fn is None:
        raise SystemExit(f"unknown provider {provider!r} -- expected one of {sorted(PROVIDERS)}")
    if _mode(params) != "grade":
        if provider not in ("litellm", "random"):
            raise SystemExit(f"mode {_mode(params)!r} is for the litellm judge and the random floor, "
                             f"not provider {provider!r}")
        fn = _random_modal if provider == "random" else fn
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
    elif provider == "unieval":
        _unieval_model(params)
        _sentences("A first sentence. A second one.")
        if params.get("inputs") == "published":
            _unieval_published()
        _unieval_score([_UE_QUESTIONS["fluency"].format(out="The council approved the budget.")], params)
    elif provider == "coverage":
        _summarisation_scorer()
    elif provider == "litellm":
        _litellm("Warm up.", {**params, "max_tokens": 1, "_raw_message": True})
    gold = json.dumps({d: [float(i % 5 + 1) for i in range(N_SUMMARIES)] for d in DIMS})
    score(_broadcast([float(i) for i in range(N_SUMMARIES)]), gold)


def fingerprint(params: Dict[str, Any]) -> Dict[str, Any]:
    provider = params.get("provider", "litellm")
    code = {"rouge": _rouge, "coverage": _coverage, "length": _length, "random": _random}
    if provider == "random" and _mode(params) != "grade":
        return {"provider": provider, "id": provider, "mode": _mode(params),
                "kind": "deterministic metric, no model and no network",
                "identity_declared": False, "revision_source": "not-a-model",
                "code_sha256": code_digest(_random_modal, _pairs, _pairs_per_item, _pairs_output)}
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
    if provider == "unieval":
        import hashlib  # noqa: PLC0415

        import nltk  # noqa: PLC0415
        from hf_identity import hf_model_fingerprint  # noqa: PLC0415

        key = (params.get("model"), params.get("revision"))
        fp = hf_model_fingerprint(params["model"], revision=params.get("revision"),
                                  device="cpu", precision="fp32",
                                  loaded_model=_UE[1] if _UE is not None and _UE_KEY == key else None)
        fp["code_sha256"] = code_digest(_unieval, consts={
            "score": code_digest(_unieval_score), "questions": json.dumps(_UE_QUESTIONS, sort_keys=True)})
        fp["inputs"] = params.get("inputs", "ours")
        fp["nltk"] = nltk.__version__
        fp["weights_licence"] = "not stated on the model card (MingZhong/unieval-sum)"
        fp["punkt_english_sha256"] = PUNKT_ENGLISH_SHA256
        if fp["inputs"] == "published":
            fp["original_release_sha256"] = ORIGINAL_SHA256
            ue = SOURCES / "summeval_unieval" / "summeval.json"
            fp["unieval_inputs_url"] = UNIEVAL_INPUTS_URL
            fp["unieval_inputs_sha256"] = hashlib.sha256(ue.read_bytes()).hexdigest() if ue.is_file() else None
        return fp
    alias = params.get("model")
    upstream, id_source = gateway.resolve_upstream(alias)
    return {"id": upstream or alias, "alias": alias, "id_source": id_source,
            "revision": None, "revision_source": "api-model-string",
            "endpoint": gateway.endpoint(), "provider_routing": params.get("provider_routing"),
            "temperature": params.get("temperature"), "prompt_sha256": _prompt_sha256(params),
            "reasoning": params.get("reasoning"),
            **({} if _mode(params) == "grade" else {
                "mode": _mode(params),
                **({"pairs_per_item": _pairs_per_item(params), "pair_seed": params.get("pair_seed", PAIR_SEED)}
                   if _mode(params) == "pairwise" else {})}),
            **({"inputs": "published", "unieval_inputs_sha256": UNIEVAL_INPUTS_SHA256,
                "original_release_sha256": ORIGINAL_SHA256}
               if params.get("inputs") == "published" else {})}


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
    modal = _reply_object(output)
    if modal is not None and ("best" in modal or "pairs" in modal):
        return _score_modal(modal, reference)
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


def _expert_means(reference: str) -> List[float]:
    """The experts' mean rating of each of the 16 summaries over the four dimensions."""
    gold = json.loads(reference)
    return [sum(gold[d][i] for d in DIMS) / len(DIMS) for i in range(N_SUMMARIES)]


def _score_modal(obj: Dict[str, Any], reference: Optional[str]) -> Dict[str, float]:
    """A pick arm or a pairwise arm, against the experts.

    pick: `top1` is the share of the summaries it named that are among those the experts rate
    highest (1 for a single correct pick; a pick of several scores the chance of drawing a
    correct one from them), `top1_chance` what a random pick gets: |best set| / 16. A reply
    that is not a valid pick scores 0 and `parsed` 0.
    pairwise: `pair_agreement` is the share of the sampled pairs the experts rank apart where the
    judge preferred the expert-preferred summary, a tie counting half and an unreadable answer 0;
    an article with no such pair scores 0.5 and `n_pairs` 0.
    """
    if "best" in obj:
        pick = _read_pick(json.dumps(obj))
        out: Dict[str, float] = {"parsed": 1.0 if pick else 0.0}
        if reference is None:
            return out
        means = _expert_means(reference)
        top = max(means)
        best = {i + 1 for i, v in enumerate(means) if top - v < TIE_EPS}
        out["top1"] = round(sum(k in best for k in pick) / len(pick), 10) if pick else 0.0
        out["top1_chance"] = round(len(best) / N_SUMMARIES, 10)
        return out
    pairs = obj["pairs"]
    betters = [_read_better(json.dumps({"better": p.get("better")})) for p in pairs]
    out = {"parsed": sum(v is not None for v in betters) / len(betters) if betters else 0.0}
    if reference is None:
        return out
    means = _expert_means(reference)
    credit = []
    for p, v in zip(pairs, betters):
        a, b = p["a"], p["b"]
        if abs(means[a] - means[b]) < TIE_EPS:
            continue
        preferred = 1 if means[a] > means[b] else 2
        credit.append(0.0 if v is None else 0.5 if v == "tie" else 1.0 if v == preferred else 0.0)
    out["pair_agreement"] = round(sum(credit) / len(credit), 10) if credit else 0.5
    out["n_pairs"] = float(len(credit))
    return out


TRANSIENT_MARKERS =("model is warming up", "no instances available", "upstream")

#: tau-b, not Spearman: it is the statistic G-Eval and the SummEval paper report beside
#: rho, and it is the one that handles the judges' constant ties honestly. Spearman is kept
#: for the literature comparison.
PRIMARY_METRIC = "tau"


def primary_metric(params: Dict[str, Any]) -> str:
    """The arm's primary metric by its mode: a grading judge is ranked on tau, a picking one on top1, a pairwise
    one on pair_agreement (RFC-005 "Judging modes")."""
    return {"pick": "top1", "pairwise": "pair_agreement"}.get(str(params.get("mode") or "grade"), PRIMARY_METRIC)

METRIC_KINDS = {
    "tau": "quality", "rho": "quality",
    **{f"tau_{d}": "quality" for d in DIMS},
    **{f"rho_{d}": "quality" for d in DIMS},
    # Descriptive: how many dimensions came back readable, how often the judge tied two
    # summaries, whether it ran out of tokens, whether it billed reasoning, whether a
    # local model saw only part of the article.
    "top1": "quality", "pair_agreement": "quality",
    "top1_chance": "descriptive", "n_pairs": "descriptive",
    "parsed": "descriptive", "tie_rate": "descriptive", "truncated": "descriptive",
    "reasoning_tokens": "descriptive", "input_truncated": "descriptive",
}

#: What each metric measures, for the catalog's metric pages. Documentation, so it never
#: moves the adapter's code hash.
METRIC_DESCRIPTIONS = {
    "tau": {
        "summary": "Kendall's tau-b between the judge's scores and the experts' ratings of an "
        "article's 16 summaries, averaged over the four dimensions.",
        "details": "Per article the judge scores 16 summaries on coherence, consistency, fluency "
        "and relevance. For each dimension its scores are correlated with the expert ratings by "
        "tau-b, which corrects for ties on both sides (an LLM judge's integer scores tie often); "
        "a dimension the judge did not return, or a constant side, counts 0. tau is the mean of "
        "the four, then over articles: agreement with people on ordering summaries, not a summary's quality.",
    },
    "rho": "Spearman's rho between the judge's scores and the experts' ratings of an article's 16 "
    "summaries, averaged over the four dimensions: kept for comparison with the literature.",
    **{f"tau_{d}": f"Kendall's tau-b with the experts' {d} ratings across an article's 16 summaries "
        f"(0 when the judge returned no {d} scores)." for d in DIMS},
    **{f"rho_{d}": f"Spearman's rho with the experts' {d} ratings across an article's 16 summaries "
        f"(0 when the judge returned no {d} scores)." for d in DIMS},
    "top1": "Pick mode: how often the judge's pick of the best of an article's 16 summaries is a summary the "
    "experts rate best (highest mean over the four dimensions; ties among the experts form the best set). 1 for a "
    "correct single pick; a pick of several scores the share of them that are correct; an unreadable pick scores 0.",
    "top1_chance": "Pick mode: what a random pick scores on the article, the share of its 16 summaries the experts "
    "rate best (|best set| / 16). A judge's top1 is read against its mean.",
    "pair_agreement": "Pairwise mode: among the sampled pairs of an article's summaries that the experts rank "
    "apart, the share where the judge preferred the summary the experts prefer; a tie counts half and an "
    "unreadable answer 0. Chance is 0.5.",
    "n_pairs": "Pairwise mode: how many of the article's sampled pairs the experts ranked apart, the pairs "
    "pair_agreement is averaged over.",
    "tie_rate": "Share of the 120 summary pairs the judge scored equal, averaged over the dimensions "
    "it returned: how often it could not tell two summaries apart.",
    "parsed": "Whether the reply could be read as an answer in the task's format: 1 or 0 per item, so its mean is the share readable (for the SummEval judges, the share of the four dimensions that came back readable). An unreadable reply scores 0 on the quality metrics, never skipped.",
    "truncated": "1 when the provider cut the reply off at the token ceiling (finish_reason \"length\", and in most adapters a completion that reached 98% of max_tokens), else 0. An arm with truncated above 0 has scores that partly describe the ceiling, not the model.",
    "input_truncated": "1 when a local model saw only part of the article, because it was longer than the model's encoder window (1,024 tokens for BART) and was cut, else 0. Those items are a different task from the hosted arms' full-article ones.",
}
