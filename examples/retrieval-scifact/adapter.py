"""Retrieval over BEIR SciFact: BM25, dense bi-encoders, LLM rerankers, and two floors.

THE SHAPE THIS EXAMPLE BREAKS

  Every other adapter in this repo answers a question about the item it was handed. This
  one cannot: an item is a QUERY, and the answer lives in a 5,183-document corpus that no
  item mentions and no arm is scored on.

  Three consequences, and all three are load-bearing:

  1. `warmup()` STOPS BEING A SMOKE TEST AND BECOMES THE BUILD. It indexes the whole
     corpus, once, and caches it at module level. The harness already times it separately
     and excludes it from per-item latency, which is exactly right -- a BM25 index build
     is not a query cost -- and already records it as `warmup_ms`, which turns index cost
     into a reported column instead of a hidden one.

  2. `corpus_sha256` GOES IN THE FINGERPRINT OR THE RECORD IS A LIE. Two runs over the
     same queries against different corpora agree on dataset_id, items_sha256,
     reference_id, adapter hash and every parameter. Nothing else distinguishes them, and
     the corpus is where the answer is.

  3. THE ARM IS A PIPELINE, NOT A MODEL. A reranking arm is "BM25 top-k, then an LLM
     reorders", and its ceiling is set by the FIRST stage: an LLM cannot rank a document
     BM25 never returned. `first_stage_recall_at_k` is recorded per item for that reason.

WHAT EACH ARM IS

  bm25      lexical, no neural net, no weights. On SciFact this is not a strawman --
            BM25 famously beats weak dense models on it, which is why it is the first
            stage rather than a baseline to be beaten.
  dense     a sentence-transformers bi-encoder. Embeds the corpus once, then cosine.
  rerank    BM25 top-k handed to a hosted LLM, which returns a reordering. The remaining
            BM25 results are APPENDED BELOW the reordered head, so the pipeline's
            recall@100 is BM25's recall@100 and only the ordering of the head changes.
            Anything else would be measuring two things at once.
  random    a seeded permutation of the corpus. The floor.
  first_k   the corpus in its own order. A SECOND floor, and not a redundant one: it is
            the score you get from a broken retriever that returns a constant, which is
            a different failure from returning noise.
"""

from __future__ import annotations

import hashlib
import json
import os
import random as _random
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] / "harness"
sys.path.insert(0, str(HERE.parent / "_shared"))

from retrieval import (  # noqa: E402
    METRIC_KINDS,
    PRIMARY_METRIC,
    parse_ranking,
    score_ranking,
    scorer_sha256,
)

__all__ = ["call_system", "score", "warmup", "fingerprint", "scorer_id",
           "PRIMARY_METRIC", "METRIC_KINDS", "TRANSIENT_MARKERS"]

#: Copied from the other three adapters: substrings that mark a provider-side error as
#: worth retrying rather than fatal.
TRANSIENT_MARKERS = ("rate limit", "ratelimit", "429", "overloaded", "timeout",
                     "timed out", "502", "503", "504", "connection reset",
                     "temporarily unavailable", "upstream")

DEFAULT_TOP_K = 100          # how deep a ranking every arm returns
DEFAULT_RERANK_K = 20        # how many BM25 hits an LLM arm is shown


@dataclass
class Result:
    """The harness reads latency_ms, tokens_in, tokens_out and cost_usd off this by name,
    and times nothing itself — `call_system` below sets latency if a provider has not."""
    output: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    latency_ms: Optional[float] = None
    extra: Dict[str, float] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


# ── the corpus ───────────────────────────────────────────────────────────────
_CORPUS: Dict[str, Tuple[List[dict], str]] = {}


def _corpus(corpus_id: str) -> Tuple[List[dict], str]:
    """Documents and the corpus hash, loaded once per process.

    The hash is read from the manifest the fetcher wrote rather than recomputed here, so
    the adapter and the fetcher cannot disagree about what the corpus is -- and if the
    manifest is missing, this fails loudly instead of running against an unidentified
    corpus.
    """
    if corpus_id in _CORPUS:
        return _CORPUS[corpus_id]
    base = ROOT / "data" / "corpora" / corpus_id
    docs_f, man_f = base / "corpus.jsonl", base / "manifest.json"
    if not docs_f.is_file():
        raise SystemExit(
            f"no corpus at {docs_f} — run examples/retrieval-scifact/fetch.py first")
    if not man_f.is_file():
        raise SystemExit(
            f"{base} has documents but no manifest.json, so the corpus cannot be "
            f"identified in the fingerprint. Re-run fetch.py rather than guessing.")
    docs = [json.loads(l) for l in docs_f.read_text(encoding="utf-8").splitlines() if l.strip()]
    sha = json.loads(man_f.read_text(encoding="utf-8"))["corpus_sha256"]
    _CORPUS[corpus_id] = (docs, sha)
    return docs, sha


def _doc_text(d: dict) -> str:
    t = (d.get("title") or "").strip()
    b = (d.get("text") or "").strip()
    return f"{t}\n{b}".strip() if t else b


# ── indexes, built in warmup() and cached for the process ────────────────────
_INDEX: Dict[str, Any] = {}
_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(s: str) -> List[str]:
    """Lowercase alphanumeric runs. No stemming, no stoplist.

    Deliberately plain, and it is part of the system under test: BM25's score moves with
    its tokeniser at least as much as with its k1/b. Hashed into the fingerprint for the
    same reason the extraction normaliser is.
    """
    return _TOKEN.findall(s.lower())


def _bm25_index(corpus_id: str):
    key = f"bm25:{corpus_id}"
    if key not in _INDEX:
        from rank_bm25 import BM25Okapi  # noqa: PLC0415

        docs, _ = _corpus(corpus_id)
        ids = [d["doc_id"] for d in docs]
        _INDEX[key] = (BM25Okapi([_tokenize(_doc_text(d)) for d in docs]), ids)
    return _INDEX[key]


#: Set to 1.0 by `_dense_index` when it actually EMBEDDED rather than loaded a cache, so
#: `warmup_ms` can be read correctly: a 4-minute warmup and a 3-second one are both
#: honest, and which happened is not inferable from the number alone.
_BUILT_THIS_PROCESS: Dict[str, bool] = {}


def _dense_index(corpus_id: str, model_id: str, device: str, batch: int,
                 doc_prefix: str = ""):
    """Embed the corpus, or load the embeddings computed for this exact configuration.

    doc_prefix IS PART OF THE KEY, in memory and on disk. e5 is trained with "passage: "
    on documents and "query: " on queries; reusing an unprefixed index for a prefixed arm
    would silently score the wrong thing with no error anywhere.

    THE CACHE IS KEYED ON THE CORPUS HASH, NOT ON THE CORPUS PATH. A cache that survived
    a corpus change would be the exact failure this whole example exists to prevent --
    an arm searching a different haystack than its fingerprint claims. Re-fetch a
    different corpus and every cached index is simply missed, because its name no longer
    matches.
    """
    import numpy as np  # noqa: PLC0415

    key = f"dense:{corpus_id}:{model_id}:{device}:{doc_prefix}"
    if key in _INDEX:
        return _INDEX[key]

    from sentence_transformers import SentenceTransformer  # noqa: PLC0415

    docs, csha = _corpus(corpus_id)
    ids = [d["doc_id"] for d in docs]
    stamp = hashlib.sha256(
        f"{csha}|{model_id}|{doc_prefix}|{device}".encode()).hexdigest()[:24]
    cache = ROOT / "data" / "corpora" / corpus_id / ".index" / f"{stamp}.npy"

    model = SentenceTransformer(model_id, device=device)
    if cache.is_file():
        emb = np.load(cache)
        if emb.shape[0] == len(ids):
            _BUILT_THIS_PROCESS[key] = False
            _INDEX[key] = (model, emb, ids)
            return _INDEX[key]
        # A cache whose row count disagrees with the corpus is not a cache, it is a bug.
        # Rebuilt rather than trusted or silently truncated.
        print(f"      index cache {cache.name} has {emb.shape[0]} rows for "
              f"{len(ids)} documents — rebuilding", flush=True)

    emb = model.encode([f"{doc_prefix}{_doc_text(d)}" for d in docs], batch_size=batch,
                       convert_to_numpy=True, normalize_embeddings=True,
                       show_progress_bar=False)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, emb)
    _BUILT_THIS_PROCESS[key] = True
    _INDEX[key] = (model, emb, ids)
    return _INDEX[key]


# ── providers ────────────────────────────────────────────────────────────────
def _bm25(query: str, params: Dict[str, Any]) -> Result:
    bm, ids = _bm25_index(params.get("corpus_id", "scifact"))
    k = int(params.get("top_k", DEFAULT_TOP_K))
    scores = bm.get_scores(_tokenize(query))
    order = sorted(range(len(ids)), key=lambda i: -scores[i])[:k]
    ranked = [ids[i] for i in order]
    return Result(output=json.dumps(ranked), cost_usd=0.0,
                  meta={"ranking": ranked, "top_score": float(scores[order[0]]) if order else 0.0})


def _dense(query: str, params: Dict[str, Any]) -> Result:
    model, emb, ids = _dense_index(
        params.get("corpus_id", "scifact"), params["model"],
        str(params.get("device", "cpu")), int(params.get("encode_batch", 64)),
        str(params.get("doc_prefix", "")))
    k = int(params.get("top_k", DEFAULT_TOP_K))
    # QUERY PREFIXES ARE PART OF THE MODEL, NOT A STYLE CHOICE. e5 and bge checkpoints are
    # trained with an asymmetric instruction ("query: " / "Represent this sentence...")
    # and score materially worse without it. Declared per arm and fingerprinted; a wrong
    # or missing prefix is a silent misconfiguration, not an error.
    q = f"{params.get('query_prefix', '')}{query}"
    qv = model.encode([q], convert_to_numpy=True, normalize_embeddings=True)[0]
    sims = emb @ qv                      # both sides L2-normalised, so this IS cosine
    order = sims.argsort()[::-1][:k]
    ranked = [ids[int(i)] for i in order]
    return Result(output=json.dumps(ranked), cost_usd=0.0,
                  meta={"ranking": ranked, "top_score": float(sims[order[0]]) if len(order) else 0.0})


def _random_rank(query: str, params: Dict[str, Any]) -> Result:
    """A seeded permutation. Seeded PER QUERY so it is deterministic and reproducible.

    The floor, and also a check on the scorer: with one relevant document in 5,183 and a
    top-100 cut, expected recall@100 is 100/5183 = 0.0193. A materially different number
    means the scorer, not the arm, is wrong.
    """
    docs, _ = _corpus(params.get("corpus_id", "scifact"))
    ids = [d["doc_id"] for d in docs]
    rng = _random.Random(f"{params.get('seed', 20260928)}:{query}")
    rng.shuffle(ids)
    ranked = ids[:int(params.get("top_k", DEFAULT_TOP_K))]
    return Result(output=json.dumps(ranked), cost_usd=0.0, meta={"ranking": ranked})


def _first_k(query: str, params: Dict[str, Any]) -> Result:
    """The corpus in its own order, ignoring the query entirely."""
    docs, _ = _corpus(params.get("corpus_id", "scifact"))
    ranked = [d["doc_id"] for d in docs][:int(params.get("top_k", DEFAULT_TOP_K))]
    return Result(output=json.dumps(ranked), cost_usd=0.0, meta={"ranking": ranked})


_PROMPT_CACHE: Dict[str, str] = {}


def _prompt(params: Dict[str, Any]) -> str:
    name = params.get("prompt_file", "prompt.txt")
    if name not in _PROMPT_CACHE:
        _PROMPT_CACHE[name] = (HERE / name).read_text(encoding="utf-8")
    return _PROMPT_CACHE[name]


def _rerank(query: str, params: Dict[str, Any]) -> Result:
    """BM25 top-k, reordered by a hosted LLM, with BM25's tail appended unchanged.

    THE TAIL IS APPENDED AND NOT DISCARDED, and that is the difference between measuring a
    reranker and measuring a reranker-shaped truncation. The LLM sees k documents; the
    pipeline still returns top_k. So recall@100 is BM25's recall@100 by construction, and
    any movement in nDCG@10 is attributable to the reordering alone.
    """
    corpus_id = params.get("corpus_id", "scifact")
    docs, _ = _corpus(corpus_id)
    by_id = {d["doc_id"]: d for d in docs}
    k = int(params.get("rerank_k", DEFAULT_RERANK_K))

    # THE FIRST STAGE IS A PARAMETER, defaulting to bm25 so every arm measured before
    # this change means exactly what it meant. It is configurable because the ceiling
    # analysis produced a prediction that only a swap can test: every BM25-based
    # reranker shares one oracle ceiling (0.8163 on scifact_200) and the best has taken
    # 91% of it, while e5_base's own candidates have a ceiling of 0.8747.
    stage = params.get("first_stage", "bm25")
    if stage == "bm25":
        first = _bm25(query, {**params, "top_k": int(params.get("top_k", DEFAULT_TOP_K))})
    elif stage == "dense":
        first = _dense(query, {**params, "model": params["first_stage_model"],
                               "query_prefix": params.get("first_stage_query_prefix", ""),
                               "doc_prefix": params.get("first_stage_doc_prefix", ""),
                               "top_k": int(params.get("top_k", DEFAULT_TOP_K))})
    else:
        raise SystemExit(f"unknown first_stage {stage!r} — 'bm25' or 'dense'")
    candidates = first.meta["ranking"]
    head, tail = candidates[:k], candidates[k:]

    snippet_chars = int(params.get("snippet_chars", 900))
    listing = "\n\n".join(
        f"[{d}] {_doc_text(by_id[d])[:snippet_chars]}" for d in head)
    user = _prompt(params).replace("{{QUERY}}", query).replace("{{DOCUMENTS}}", listing)

    res = _litellm(user, params)
    order = parse_ranking(res.output)

    # WHAT THE LLM RETURNED IS NOT TRUSTED TO BE A PERMUTATION. Ids it invented, dropped
    # or duplicated are all possible. Its ordering is applied to the head where it names
    # real candidates; every head document it failed to mention keeps its BM25 order
    # BELOW them. Dropping unmentioned documents would let an arm score better by saying
    # less, which is the retrieval version of the bug the extraction scorer shipped with.
    reordered: List[str] = []
    if order:
        seen = set()
        for d in order:
            if d in head and d not in seen:
                seen.add(d)
                reordered.append(d)
        reordered += [d for d in head if d not in seen]
    else:
        reordered = list(head)

    ranked = reordered + tail
    res.meta.update({
        "ranking": ranked,
        # THE LLM'S RAW REPLY, kept because `res.output` is overwritten below with the
        # PIPELINE's ranking. Without it a reranking arm cannot be diagnosed at all:
        # qwen_s scored exactly BM25's nDCG on the dev slice and the stored outputs could
        # not say whether it had reasoned itself out of tokens, over-generated, or
        # refused -- the only recoverable fact was `finish_reason: length`. Truncated,
        # because the point is to see the shape of the failure, not to archive prose.
        "llm_raw": (res.output or "")[:2000],
        "llm_returned": order,
        "first_stage": head,
        # Did the LLM emit a usable ordering at all? Distinct from `parsed`, which is
        # about the final ranking -- this pipeline always produces one, because BM25's
        # order survives an unreadable LLM reply. Without this column an arm whose LLM
        # never answered would be indistinguishable from BM25 and look respectable.
        "llm_parsed": order is not None,
        "llm_named_unknown": sum(1 for d in (order or []) if d not in head),
    })
    res.extra["llm_parsed"] = 1.0 if order is not None else 0.0
    res.extra["llm_named_unknown"] = float(res.meta["llm_named_unknown"])
    res.output = json.dumps(ranked)
    return res


def _litellm(user: str, params: Dict[str, Any]) -> Result:
    from openai import OpenAI  # noqa: PLC0415

    base = (params.get("base_url") or os.environ.get("LITELLM_BASE_URL", "")).rstrip("/")
    if not base:
        raise SystemExit("LITELLM_BASE_URL is not set — copy .env.example to .env")
    key = os.environ.get(params.get("api_key_env", "LITELLM_API_KEY"), "")
    client = OpenAI(api_key=key, base_url=f"{base}/v1")

    # REASONING IS PASSED THROUGH, AND THE OTHER THREE EXAMPLES ALREADY DID THIS.
    # I dropped it when writing this adapter, so these arms ran at the provider's default
    # while summarisation, classification and NER all ran with `reasoning.enabled: false`.
    # That is not a tuning difference, it breaks the one claim the four examples exist to
    # support -- that only the TASK differs between them.
    #
    # It also explains a result I had already half-diagnosed: qwen_s consumed its entire
    # output budget (400, then 700 after I raised it) and returned message.content == ""
    # with finish_reason "length". The tokens went to hidden reasoning, so no budget would
    # ever have been enough. Same signature as glm_l in the NER example, different cause.
    extra_body: Dict[str, Any] = {}
    for passthrough in ("reasoning", "reasoning_effort"):
        if params.get(passthrough) is not None:
            extra_body[passthrough] = params[passthrough]
    if params.get("provider_routing") is not None:
        extra_body["provider"] = params["provider_routing"]

    kwargs: Dict[str, Any] = {
        "model": params["model"],
        "messages": [{"role": "user", "content": user}],
        "temperature": float(params.get("temperature", 0.0)),
        "max_tokens": int(params.get("max_tokens", 400)),
    }
    if extra_body:
        kwargs["extra_body"] = extra_body
    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    text = (choice.message.content or "").strip()
    usage = getattr(resp, "usage", None)
    tin = getattr(usage, "prompt_tokens", 0) or 0
    tout = getattr(usage, "completion_tokens", 0) or 0
    # WHAT THE PROVIDER BILLED, falling back to the price table only if it is silent.
    # An alias is not a price: OpenRouter routes across several upstream providers that
    # charge differently, so a per-alias `usd_per_mtok` is an estimate of a number the
    # response already carries exactly. Measured across this repo, the table was wrong by
    # 0.67x to 3.21x per arm and reordered arms by cost.
    billed = _billed(usage)
    cost = billed if billed is not None else (
        tin * float(params.get("usd_per_mtok_in", 0.0))
        + tout * float(params.get("usd_per_mtok_out", 0.0))) / 1_000_000
    extra = {"truncated": 1.0 if choice.finish_reason == "length" else 0.0}
    extra["reasoning_tokens"] = float(_reasoning_tokens(usage) or 0)
    return Result(output=text, cost_usd=cost, tokens_in=tin, tokens_out=tout,
                  meta={"finish_reason": choice.finish_reason,
                        "response_model": getattr(resp, "model", None),
                        "usage": usage.model_dump() if usage else None},
                  extra=extra)


def _billed(usage: Any) -> Optional[float]:
    """What the PROVIDER says this call cost, or None if it did not say.

    WHY THIS OUTRANKS THE PRICE TABLE. `usd_per_mtok_in/out` is one price per model
    ALIAS, and an alias is not a price: OpenRouter routes each request to one of several
    upstream providers -- a single run here recorded Novita 262 times, Parasail 9,
    DeepInfra 6, Nebius 3 -- and they charge differently. The effective price is a
    routing-dependent mixture no config can state in advance.

    Measured across the four examples in this repo, the table was wrong by 0.67x to 3.21x
    PER ARM, in both directions, and it reordered arms by cost: on few_nerd_280 `glm_s` is
    2nd-cheapest by the table and 9th by what was billed, and the cheapest-to-dearest span
    is 155x by the table against 90x billed.

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


def _reasoning_tokens(usage: Any) -> Optional[int]:
    """Reasoning tokens, however this provider spells them. Copied from the NER adapter.

    A single `getattr(details, "reasoning_tokens")` misses the pydantic/dict split and
    the two alternative spellings, and reports 0 for a model that spent its whole budget
    thinking -- which is the one case the column exists for.
    """
    d = usage if isinstance(usage, dict) else (
        usage.model_dump() if hasattr(usage, "model_dump") else {})
    details = d.get("completion_tokens_details") or d.get("output_tokens_details") or {}
    if not isinstance(details, dict):
        details = details.model_dump() if hasattr(details, "model_dump") else {}
    for k in ("reasoning_tokens", "reasoning", "thinking_tokens"):
        if isinstance(details.get(k), int):
            return details[k]
    return None


PROVIDERS = {"bm25": _bm25, "dense": _dense, "rerank": _rerank,
             "random": _random_rank, "first_k": _first_k}


def call_system(source_text: str, params: Dict[str, Any]) -> Result:
    provider = params.get("provider", "bm25")
    if provider not in PROVIDERS:
        raise SystemExit(f"unknown provider {provider!r} — one of {sorted(PROVIDERS)}")
    started = time.perf_counter()
    result = PROVIDERS[provider](source_text.strip(), params)
    # QUERY time only. The index build happened in `warmup()` and the harness records it
    # separately as `warmup_ms`; charging it here would make the first item of a dense
    # arm look sixty seconds slow and every other item look free.
    if result.latency_ms is None:
        result.latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return result


# ── scoring ──────────────────────────────────────────────────────────────────
def warmup(params: Dict[str, Any]) -> None:
    """Build the index. This is the expensive part, and the harness times it separately.

    Not a smoke test, unlike the other three adapters' warmups: for a retrieval arm this
    IS the work. Reported as `warmup_ms`, which is the honest place for an index build --
    charging it to the first query would make one item look 60 seconds slow, and hiding
    it entirely would let a dense arm claim BM25's setup cost.
    """
    provider = params.get("provider", "bm25")
    corpus_id = params.get("corpus_id", "scifact")
    _corpus(corpus_id)
    if provider == "bm25" or (provider == "rerank"
                              and params.get("first_stage", "bm25") == "bm25"):
        _bm25_index(corpus_id)
    if provider == "rerank" and params.get("first_stage") == "dense":
        _dense_index(corpus_id, params["first_stage_model"],
                     str(params.get("device", "cpu")),
                     int(params.get("encode_batch", 64)),
                     str(params.get("first_stage_doc_prefix", "")))
    if provider == "dense":
        _dense_index(corpus_id, params["model"], str(params.get("device", "cpu")),
                     int(params.get("encode_batch", 64)),
                     str(params.get("doc_prefix", "")))
    if provider == "rerank":
        _litellm("Reply with the single character: 1", {**params, "max_tokens": 8})
    if _BUILT_THIS_PROCESS:
        built = any(_BUILT_THIS_PROCESS.values())
        print(f"      dense index {'BUILT from scratch' if built else 'loaded from cache'}"
              f" — warmup_ms below means {'embedding cost' if built else 'load cost'}",
              flush=True)
    score(json.dumps(["nope"]), json.dumps([{"doc_id": "nope", "score": 1}]))


def score(output: str, reference: Optional[str]) -> Dict[str, float]:
    """nDCG@10 and friends against the qrels.

    The output is re-parsed here rather than taken from `meta`, so `make rescore` can
    recompute every number from the stored text after a scorer change -- the property
    that made the extraction scorer's bug cost nothing to fix.
    """
    try:
        judged = json.loads(reference) if reference else []
    except (TypeError, ValueError):
        judged = []
    qrels = {str(j["doc_id"]): int(j.get("score", 1)) for j in judged
             if isinstance(j, dict) and j.get("doc_id") is not None}

    ranking = parse_ranking(output)
    corpus_ids = None
    try:
        docs, _ = _corpus(os.environ.get("EVAL_CORPUS_ID", "scifact"))
        corpus_ids = {d["doc_id"] for d in docs}
    except SystemExit:
        pass  # rescoring on a machine without the corpus: unknown_ids is then unavailable
    out: Dict[str, float] = {"parsed": 0.0 if ranking is None else 1.0}
    out.update(score_ranking(ranking or [], qrels, corpus_ids,
                             parsed=ranking is not None))
    return out


def _tokenizer_sha256() -> str:
    import inspect  # noqa: PLC0415

    return hashlib.sha256(
        (inspect.getsource(_tokenize) + inspect.getsource(_doc_text)).encode()).hexdigest()


def scorer_id() -> Dict[str, str]:
    """Hashes identifying the scoring rule. No params, no network — `rescore.py` calls it."""
    return {"scorer_sha256": scorer_sha256(), "tokenizer_sha256": _tokenizer_sha256()}


def fingerprint(params: Dict[str, Any]) -> Dict[str, Any]:
    """What this arm's system under test IS — including the corpus it searched.

    `corpus_sha256` is the field this example exists to add. Without it two runs over the
    same queries against different corpora are indistinguishable in every recorded field,
    and the corpus is where the answer lives.
    """
    provider = params.get("provider", "bm25")
    docs, csha = _corpus(params.get("corpus_id", "scifact"))
    common = {
        "provider": provider,
        "corpus_id": params.get("corpus_id", "scifact"),
        "corpus_sha256": csha,
        "corpus_n_docs": len(docs),
        "top_k": int(params.get("top_k", DEFAULT_TOP_K)),
        "scorer_sha256": scorer_sha256(),
        "tokenizer_sha256": _tokenizer_sha256(),
    }
    if provider in ("bm25", "rerank"):
        # BM25's own constants. rank_bm25's defaults, not tuned, and recorded because a
        # retrieval score moves with them and a reader cannot otherwise know which BM25
        # this was.
        common["bm25"] = {"impl": "rank_bm25.BM25Okapi", "k1": 1.5, "b": 0.75,
                          "epsilon": 0.25}
    if provider == "dense":
        sys.path.insert(0, str(HERE.parent / "_shared"))
        from hf_identity import hf_model_fingerprint  # noqa: PLC0415

        out = hf_model_fingerprint(
            params["model"], revision=params.get("revision"),
            device=str(params.get("device", "cpu")),
            precision=str(params.get("precision", "fp32")))
        out.update(common)
        out["query_prefix"] = params.get("query_prefix", "")
        out["doc_prefix"] = params.get("doc_prefix", "")
        # Whether this run embedded the corpus or loaded a cached embedding. It does not
        # change the RESULT -- the cache is keyed on corpus hash, model, prefix and
        # device, so a hit is the same array a build would produce -- but it entirely
        # changes what `warmup_ms` means, and a reader comparing 260,000 ms against
        # 3,000 ms deserves to know which is which.
        out["index_built_this_run"] = any(_BUILT_THIS_PROCESS.values())
        return out
    if provider == "rerank":
        common.update({
            "rerank_k": int(params.get("rerank_k", DEFAULT_RERANK_K)),
            "snippet_chars": int(params.get("snippet_chars", 900)),
            "first_stage": params.get("first_stage", "bm25"),
            "first_stage_model": params.get("first_stage_model"),
            "first_stage_query_prefix": params.get("first_stage_query_prefix", ""),
            "first_stage_doc_prefix": params.get("first_stage_doc_prefix", ""),
            "alias": params.get("model"),
            "id": params.get("model"),
            "identity_declared": True,
            "endpoint": os.environ.get("LITELLM_BASE_URL"),
            "max_tokens": int(params.get("max_tokens", 400)),
            "temperature": float(params.get("temperature", 0.0)),
            "reasoning": params.get("reasoning"),
            "prompt_sha256": hashlib.sha256(_prompt(params).encode()).hexdigest(),
        })
    if provider == "random":
        common["seed"] = params.get("seed", 20260928)
    return common
