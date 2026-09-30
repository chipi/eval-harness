# Method — why this experiment is built the way it is

Companion to [`README.md`](README.md) and
[`REPORT_RETRIEVAL.md`](../../research/REPORT_RETRIEVAL.md). Terms in
[`docs/REFERENCE.md`](../../docs/REFERENCE.md).

---

## The task, and what it broke

Given a scientific claim, find the abstracts that support or refute it. The answer is **a
ranked list**, and it broke the harness in a way none of the first three did: **the corpus
is not the items.**

Every other adapter answers a question about the item it was handed. Here an item is a
*query*, and the answer lives in a 5,183-document corpus that no item mentions and no arm
is scored on. Three consequences:

1. **`warmup()` stopped being a smoke test and became the build.** It indexes the corpus,
   once. The harness already timed warm-up separately and excluded it from per-item
   latency — a decision made for *model loading* in the first example — and that turned out
   to be exactly right for an index build. So index cost became a reported column:
   BM25 **0.8 s**, MiniLM 194 s, e5-base **1825 s**.
2. **`corpus_sha256` or the record is a lie.** Two runs over the same queries against
   different corpora agree on `dataset_id`, `items_sha256`, `reference_id`, adapter hash
   and every parameter. *Nothing else* would distinguish them, and the corpus is where the
   answer is. It gets its own directory
   ([`data/corpora/`](../../harness/data/corpora/README.md)) because it is not `sources/`
   (no one-file-per-item), not `references/` (it is the haystack, not truth) and not
   `materialized/` (not derived from anything here).
3. **An arm became a pipeline with a ceiling it did not choose.** A reranker cannot rank a
   document its first stage never returned.

## Why SciFact

[`BeIR/scifact`](https://huggingface.co/datasets/BeIR/scifact) +
[`BeIR/scifact-qrels`](https://huggingface.co/datasets/BeIR/scifact-qrels), CC BY-SA 4.0.
[Wadden et al. 2020](https://aclanthology.org/2020.emnlp-main.609/), packaged by
[BEIR](https://arxiv.org/abs/2104.08663).

- **Small enough to index on a laptop CPU in under a minute** — which is what makes an
  honest `warmup_ms` column possible at all. MS MARCO or HotpotQA would need a vector
  database and turn this into an infrastructure exercise.
- **CC BY-SA 4.0**, and BM25's published nDCG@10 on it (0.665) gives an **external
  check**: this repo measures 0.6451, close, and lower in the direction a plainer
  tokeniser predicts (no stemming, no stopword list, no Lucene).

**The corpus is never sliced.** `--n` slices the *queries*; all 5,183 documents are
searched whatever `--n` says. Sampling the haystack would raise every arm's nDCG — most of
what it could have wrongly ranked above the answer would be gone — and would make a
40-query run and a 200-query run two different tasks wearing one name.

**Relevance is binary** here (every qrels score is 1), so nDCG's graded machinery does no
work. The gain function `2^rel − 1` is declared anyway, because a metric that silently
changes meaning between corpora is worse than one that is merely wrong.

## Why these arms

### First stages

| Arm | Trained for retrieval? | Isolates |
|---|---|---|
| `bm25` | n/a — lexical | The no-neural-net baseline. **Not a strawman**: BM25 famously beats weak dense models on SciFact. |
| [`minilm`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | No — general similarity | The "obvious dense baseline" most people reach for first |
| [`mpnet`](https://huggingface.co/sentence-transformers/all-mpnet-base-v2) | No | Same recipe as MiniLM at 4.8× the size → isolates **size** |
| [`bge_small`](https://huggingface.co/BAAI/bge-small-en-v1.5) | **Yes** | Roughly MiniLM's size, different objective → isolates **training objective** |
| [`e5_base`](https://huggingface.co/intfloat/e5-base-v2) | **Yes** | Roughly mpnet's size, different objective → the same contrast one size up |

The (minilm, bge_small) pair does for retrieval what (gliner, span_marker) did for NER:
holds size roughly fixed and varies what the model was trained to do.

> **Query prefixes are part of the model, not a style choice.** BGE and E5 are trained with
> specific instructions (`query: ` / `passage: `); omitting one costs several nDCG points
> and raises **no error**. Both are fingerprinted, and `doc_prefix` is part of the index
> cache key so a prefixed arm cannot silently reuse an unprefixed index.

### Rerankers

**The hosted LLMs cannot retrieve** — you cannot ask a model to rank 5,183 documents. The
proxy exposes no embedding models, so the LLM arms became **rerankers**, which is also what
people actually deploy.

The pipeline is built so exactly one thing varies: BM25 returns 100, the LLM reorders the
top 20, and **BM25's remaining 80 are appended below, unchanged**. So the pipeline's
recall@100 *is* BM25's by construction, and every nDCG@10 movement is the reordering
alone. Verified, not assumed: all twelve rerankers report `recall_100 = 0.8586`, identical
to BM25's, to four decimals.

**Only 12 of the 24 hosted arms ran.** The cut was *everything under $0.60/Mtok input* —
price-ordered and declared before any result was read. A reranking prompt carries 20 full
abstracts (**3,926 input tokens per query** against NER's 125), so the five frontier arms
would have cost **about $12** against this sweep's **$1.94 billed**. The consequence is stated
plainly in the report: the top tie (12–13 arms, the count on a Holm boundary) is a tie
among *cheap* models, and this example
**cannot say whether a frontier model reranks better**. See
[`HANDOVER_RETRIEVAL_FRONTIER_ARMS.md`](../../research/HANDOVER_RETRIEVAL_FRONTIER_ARMS.md).

## Why these success criteria

**Ranked by [nDCG@10](https://dl.acm.org/doi/10.1145/582415.582418)** — position-weighted,
discounted by `1/log2(rank+1)`, normalised so 1.0 is the best possible ordering. It is the
standard for ranked retrieval and it is the only one of these metrics that knows rank 1
is worth more than rank 10.

- **`recall_100` is reported beside it because a pipeline depends on it, not on nDCG.**
  With mostly one relevant document per query, nDCG@10 takes one of eleven values and is a
  disguised reciprocal rank. Recall@100 asks the different question: did the first stage
  put the answer anywhere the reranker could reach.
- **The oracle ceiling** (in [`retrieval_report.py`](../../harness/scripts/retrieval_report.py))
  sorts an arm's own candidates perfectly and scores that. It reads the gold labels, so
  nobody can deploy it — it is the only honest denominator for *"how much better could this
  get without a better retriever"*. It is what produced this repo's first **pre-registered
  quantitative prediction**.
- **`unknown_ids`** counts document ids the model invented. Those **keep their slot** in
  the ranking: dropping them would slide real documents up and make invention a scoring
  strategy.
- **Two floors that must read true first.** `random` must score ≈ k/N (measured 0.0020
  against a predicted 0.0193 — 1.8 SD low, which the report reports as a *weak* pass, not a
  clean one), and `first_k` must score ≈ 0.

**Three rewards-for-bad-behaviour were decided and asserted before any arm ran** — an
unreadable answer is not an empty ranking, a hallucinated id keeps its slot, a duplicate is
collapsed. The 31-assertion suite caught a real parser bug before the first arm: a preamble
before the JSON array made it return the literal string `["a","b"]` as a document id.

---

## Credits

**Dataset** — [SciFact](https://aclanthology.org/2020.emnlp-main.609/)
(Wadden et al., EMNLP 2020), packaged by [BEIR](https://arxiv.org/abs/2104.08663)
(Thakur et al., NeurIPS 2021) as
[`BeIR/scifact`](https://huggingface.co/datasets/BeIR/scifact) and
[`BeIR/scifact-qrels`](https://huggingface.co/datasets/BeIR/scifact-qrels). CC BY-SA 4.0.
Neither corpus nor queries are redistributed.

**Models** —
[`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) ·
[`all-mpnet-base-v2`](https://huggingface.co/sentence-transformers/all-mpnet-base-v2)
([Sentence-BERT](https://arxiv.org/abs/1908.10084), Reimers & Gurevych) ·
[`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5)
([BGE, in *C-Pack*](https://arxiv.org/abs/2309.07597)) ·
[`intfloat/e5-base-v2`](https://huggingface.co/intfloat/e5-base-v2)
([E5](https://arxiv.org/abs/2212.03533)). Hosted models in
[`docs/REFERENCE.md`](../../docs/REFERENCE.md#hosted--24-arms-8-vendors--3-price-tiers).

**Method** — [nDCG](https://dl.acm.org/doi/10.1145/582415.582418) (Järvelin & Kekäläinen,
2002); [BM25](https://en.wikipedia.org/wiki/Okapi_BM25) (Robertson & Spärck Jones);
cut-off and gain conventions follow [BEIR](https://github.com/beir-cellar/beir) /
[pytrec_eval](https://github.com/cvangysel/pytrec_eval).

**Software** — [rank_bm25](https://github.com/dorianbrown/rank_bm25) 0.2.2 ·
[sentence-transformers](https://github.com/huggingface/sentence-transformers) 3.4.1 ·
[transformers](https://github.com/huggingface/transformers) 4.55.4 ·
[torch](https://github.com/pytorch/pytorch) 2.2.2 · [numpy](https://numpy.org/) ·
[LiteLLM](https://github.com/BerriAI/litellm) · [uv](https://github.com/astral-sh/uv).
