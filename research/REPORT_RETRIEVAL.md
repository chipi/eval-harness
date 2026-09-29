# Evaluation report — BM25, four dense retrievers and twelve LLM rerankers on SciFact

**Dataset** `scifact_200` · 200 scientific claims · a **5,183-document corpus** · 234 relevance judgments
**Arms** BM25 · 4 sentence-transformer bi-encoders · 12 hosted LLMs reranking BM25's top-20 · 2 floors
**Design** 1 pass per arm · temperature 0, reasoning off, `max_tokens` 700 · rerank depth 20 · **$1.94 billed**
**Date** 2026-09-29 · **Harness** [`../harness`](../harness) · **Journal** [`NOTES.md`](NOTES.md)
**Costs** are what the provider billed (`usage.cost`), not this repo's price table — see §7

> **The fourth metric shape, and the first where POSITION carries meaning.** Summarisation
> compares one text to one text. Classification compares one label to one label.
> Extraction compares a set to a set, and order is irrelevant. Retrieval compares a
> **list** to a set: an arm that finds the right document at rank 50 instead of rank 1 is
> not correct, and no set-valued metric can say so.


> **This is one of five experiments.** What all five agree on — and the four
> places they disagree with the conventional reading of a leaderboard — is in
> [`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).

---

## Executive summary

### The decision, in one table

| the choice | what the data says |
|---|---|
| **Deploy — on your own hardware** | **Both halves are open-weight, so the best configuration here is free.** `e5_base` alone (438 MB, MIT): **0.7191**, 0.06 s/item, not separable from any paid arm. Add **`glm_s`** (GLM-4.5-Air, **MIT**) reranking it: **0.7891** — the highest score measured in this experiment. |
| **Deploy — rented API** | The same two models through a provider: **$732/month per 1M items** for the reranked pipeline. You are renting convenience, not access — **no proprietary model is needed at any point.** |
| **What should I not deploy?** | A reranker on a weak first stage. Every BM25-based pipeline is capped at **0.8163** no matter which model reorders, and 11 of 12 are within 4 points of that cap. |
| **Does paying more help?** | Slightly: **+2.8%** per 10× cost. The dearest arm ranks **2nd of 17** at $2,288/month for **−0.2%**. |
| **Arms tied at the top?** | **12 of 18** — and two of them (`e5_base`, `bge_small`) are **free and local**. |
| **Biggest single lever?** | **Replacing the retriever, not adding a reranker.** BM25 → e5_base is +0.0740; worst → best reranker is +0.0420. |
| **Is a pilot enough?** | **Emphatically no.** ρ = 0.756 and the dev slice's leader finished **10th of 19**. |
| **Fine-tune or pay?** | **The one genuinely marginal case.** No arm here was fine-tuned *on SciFact*; `e5_base` is retrieval-trained but not on this corpus, and lands mid-field — beaten by 0.0246 that the test cannot resolve. Partially-trained looks like a tie, not a win. |

**A prediction registered before the arm existed** — that swapping only the first stage
would move the pipeline from 0.74 to 0.786–0.797 — came back at **0.7891**, and the
mechanism transferred too (headroom-used 90.9% → 90.2%).

*Cross-cutting context for all five experiments:
[`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).*

### What this experiment specifically found


**Two free local models are statistically indistinguishable from every paid LLM reranker.
And a prediction registered before the arm existed — that swapping only the first stage
would move the pipeline from 0.74 to 0.786–0.797 — came back at 0.7891.**

1. **A twelve-way tie at the top.** The best arm, `glm_s` at **0.7437**, separates from
   only **6 of 18** opponents under Holm. The twelve it cannot separate from include
   `e5_base` (**0.7191**) and `bge_small` (**0.7097**) — both **$0**, local, CPU.

2. **Reranking beats retrieval, and which reranker barely matters.** All twelve
   rerankers land in **0.7017–0.7437**, every one above BM25's 0.6451. The spread among
   them is 0.042 across a 3.6× price range; the gap from BM25 to the worst of them is
   0.057. The *act* of reranking is worth more than the *choice* of reranker.

3. **The ceiling is the finding.** A reranker cannot rank a document its first stage never
   returned. Every BM25-based arm shares one oracle ceiling — **0.8163** — and the best
   has already taken **91.1%** of it. `e5_base`'s own candidates have a ceiling of
   **0.8747** and, standing alone, it exploits only 82.2%.

4. **So the prediction, registered before `first_stage` was even configurable:** a
   reranker on e5_base's candidates should reach ~0.786–0.797. Measured: `glm_s`
   **0.7891**, `qwen_s` **0.7799**. The mechanism transferred too — headroom-used went
   90.9% → 90.2% and 88.5% → 89.2%.

5. **The dev slice picked the wrong winner.** Its leader, `llama_s`, finished **10th of
   19** on the measurement slice, nine places down. ρ(dev, measurement) = 0.756.

6. **One arm looked broken and was misconfigured by me.** `qwen_s` scored *exactly* BM25's
   nDCG because it never answered. The cause was a `reasoning` passthrough this adapter
   never had and the other three examples all do. Fixed, and it then scored 0.7338. See §6.

---

## 1. What was measured

| | |
|---|---|
| Corpus | BEIR SciFact, **5,183 abstracts**, CC BY-SA 4.0, `corpus_sha256` `297643e2d005` |
| Queries | 200 test claims, seeded random, `items_sha256` frozen |
| Dev slice | 40 claims, a strict **prefix** of the same permutation — nested |
| Judgments | 234 over 200 queries: 184 queries have 1 relevant doc, 9 have 2, 4 have 3, 2 have 4, 1 has 5 |
| Relevance | **binary** — every qrels score is 1 |
| Reachability | every judged document is in the corpus, so recall@all = 1.0 is attainable |

**The corpus is never sliced.** `--n` slices the queries; all 5,183 documents are searched
whatever `--n` says. Sampling the haystack would raise every arm's nDCG — most of what it
could have wrongly ranked above the answer would be gone — and would make a 40-query run
and a 200-query run two different tasks wearing one name.

### The corpus is a third kind of artifact

It is not `sources/` (no one-file-per-item correspondence: 200 queries search 5,183
documents), not `references/` (it is the haystack, not ground truth), and not
`materialized/` (not derived from anything in this repo). It lives in `data/corpora/` with
its own README.

**`corpus_sha256` is in every arm's fingerprint or the record is a lie.** Two runs over the
same queries against different corpora agree on `dataset_id`, `items_sha256`,
`reference_id`, adapter hash and every parameter. Nothing else would distinguish them, and
the corpus is where the answer lives.

---

## 2. How a ranked list is scored

`nDCG@10` is the ranking metric; `recall@10`, `recall@100` and `MRR@10` ride along.
All are per-item — a query has its own gold set — so their means are honest and
`family_test.py`'s sign-flip permutation works directly, as in the extraction example.

### Three things that look like leniency and are rewards for bad behaviour

Each is a place where the tidy implementation quietly pays an arm for something it should
be punished for. The extraction scorer in this repo shipped with exactly this class of bug,
so these were decided — and asserted — **before any arm ran**.

| | |
|---|---|
| **An unreadable answer is not an empty ranking** | scores zero on every quality metric |
| **A hallucinated document id keeps its slot** | dropping it would slide real documents *up* and improve the score, making invention a strategy |
| **A duplicate is collapsed, not counted** | otherwise one relevant document repeated ten times fills the top-10 |

The suite earned itself immediately: it caught a real parser bug before any arm ran. A
preamble before the JSON array sent the parser down its line-splitting path, which returned
the literal string `["a","b"]` as a single document id.

### The pipeline is constructed so only one thing varies

A reranking arm is BM25 top-100 → the LLM reorders the top-20 → **BM25's remaining 80 are
appended below, unchanged**. So the pipeline's recall@100 *is* BM25's recall@100 by
construction, and every nDCG@10 movement is attributable to the reordering alone.

Verified, not assumed: all twelve rerankers report `recall_100 = 0.8586`, identical to
BM25's, to four decimals.

---

## 3. Results

### 3.1 The leaderboard

| arm | nDCG@10 | recall@10 | recall@100 | MRR@10 | index build | cost |
|---|---|---|---|---|---|---|
| glm_s ⟳ | **0.7437** | 0.8067 | 0.8586 | 0.7364 | 0.8 s | $0.0548 |
| glm_m ⟳ | 0.7419 | 0.8067 | 0.8586 | 0.7325 | 0.8 s | $0.1374 |
| deepseek_m ⟳ | 0.7399 | 0.7893 | 0.8586 | 0.7373 | 0.8 s | $0.1233 |
| deepseek_s ⟳ | 0.7378 | 0.8017 | 0.8586 | 0.7303 | 0.8 s | $0.0838 |
| gemma_m ⟳ | 0.7363 | 0.7967 | 0.8586 | 0.7287 | 0.8 s | $0.0620 |
| gemma_l ⟳ | 0.7359 | 0.7917 | 0.8586 | 0.7287 | 0.8 s | $0.0884 |
| qwen_s ⟳ | 0.7338 | 0.7997 | 0.8586 | 0.7270 | 0.8 s | $0.0547 |
| llama_l ⟳ | 0.7281 | 0.7955 | 0.8586 | 0.7234 | 0.8 s | $0.1540 |
| **e5_base** | **0.7191** | **0.8305** | **0.9540** | 0.6889 | 1825 s | **$0** |
| llama_s ⟳ | 0.7172 | 0.7855 | 0.8586 | 0.7065 | 0.8 s | $0.0715 |
| **bge_small** | **0.7097** | 0.8298 | 0.9325 | 0.6812 | 874 s | **$0** |
| llama_m ⟳ | 0.7088 | 0.7792 | 0.8586 | 0.6996 | 0.8 s | $0.1022 |
| mistral_s ⟳ | 0.7071 | 0.7668 | 0.8586 | 0.6990 | 0.8 s | $0.0467 |
| gemma_s ⟳ | 0.7017 | 0.7760 | 0.8586 | 0.6938 | 0.8 s | $0.0607 |
| mpnet | 0.6643 | 0.7707 | 0.9350 | 0.6355 | 1825 s | $0 |
| minilm | 0.6533 | 0.7705 | 0.9125 | 0.6212 | 194 s | $0 |
| bm25 | 0.6451 | 0.7635 | 0.8586 | 0.6152 | **0.8 s** | $0 |
| random | 0.0005 | 0.0010 | 0.0020 | 0.0006 | — | $0 |
| first_k | 0.0000 | 0.0000 | 0.0350 | 0.0000 | — | $0 |

⟳ = BM25 + that LLM reranking the top 20. Costs are this repo's price table — see §7, they
understate the bill by roughly 2.4×.

### 3.2 A twelve-way tie, and two of the twelve are free

`glm_s` vs a family of 18 declared before any p-value was read, Holm step-down at α = 0.05:

```
separated from 6 of 18; ahead on the point estimate against 18 of 18

  SEPARATED:      bm25 (+0.0986)  first_k  random  minilm (+0.0904)
                  mpnet (+0.0794)  llama_m (+0.0349)

  NOT separated:  gemma_s  mistral_s  llama_s  bge_small  llama_l  e5_base
                  qwen_s  gemma_m  gemma_l  deepseek_s  deepseek_m  glm_m
```

**`e5_base` and `bge_small` are in that group, and they cost nothing.** A 110M-parameter
encoder running on a laptop CPU is not distinguishable from twelve hosted LLM rerankers.

The tie also explains the stability numbers: ρ between two disjoint halves rises
monotonically 0.408 → 0.742, so the *ordering* is real, while **P(same winner) is 0.01–0.07**
— with twelve indistinguishable arms, which one crowns a random half is close to a coin
toss. Both statements are true at once, and reading either alone would mislead.

### 3.3 Reranking is worth more than the retriever, and the retriever is worth more than the reranker choice

- BM25 → worst reranker (`gemma_s`): **+0.0566**
- worst reranker → best reranker (`glm_s`): **+0.0420**, across a 3.6× price range
- BM25 → `e5_base`, no LLM at all: **+0.0740**

The largest single move available on this corpus is **replacing the retriever**, not adding
a model on top of it.

### 3.4 The ceiling, and a prediction registered before the arm existed

A reranker cannot rank a document its first stage never returned. `retrieval_report.py`
computes the oracle: sort the arm's own top-20 candidates so every relevant document
precedes every irrelevant one, and score that.

```
arm             nDCG@10  ceiling     gap    used
glm_s            0.7437   0.8163  0.0726  91.1%
qwen_s           0.7338   0.8163  0.0826  89.9%
e5_base          0.7191   0.8747  0.1556  82.2%
bm25             0.6451   0.8163  0.1712  79.0%
```

Every BM25-based arm shares one ceiling because they share one first stage, and the best
has taken 91% of it. `e5_base` has a **higher** ceiling and exploits less of it.

**The prediction, written down before `first_stage` was made configurable and before any
e5-based arm existed:** if the headroom share transfers, a reranker on e5_base's candidates
reaches 0.899 × 0.8747 = 0.786 to 0.911 × 0.8747 = 0.797.

**Measured:**

| reranker | over BM25 | over e5_base | Δ | headroom used |
|---|---|---|---|---|
| glm_s | 0.7422 | **0.7891** | +0.0469 | 90.9% → 90.2% |
| qwen_s | 0.7224 | **0.7799** | +0.0575 | 88.5% → 89.2% |

`glm_s` lands inside the registered range. `qwen_s` lands 0.006 below its own. And the
**mechanism** transferred, not just the number: the share of available headroom each
reranker takes moved by under one percentage point when the candidates changed entirely.

Both halves of each pair ran under the same adapter, so the comparison is internally valid;
that adapter differs from the 19-arm main table's, which is why these four are reported
separately and are not in §3.1.

### 3.5 The dev slice picked the wrong winner

ρ(dev-40, measurement-200) over 19 arms = **0.756**. But:

- dev leader `llama_s` → **10th of 19** on measurement, down nine places
- measurement leader `glm_s` → was **9th** on dev
- `mistral_s` moved six places

Choosing an arm on 40 queries would have shipped the tenth-best. This is the same machinery
that found a winner's curse in the summarisation study and found none in NER; here it finds
one.

On the 160 queries the dev slice never contained, the global permutation test gives
p = 0.0002 — an arm effect exists — with **34 of 171 pairs distinguishable** and a Nemenyi
critical difference of 2.21 rank positions against an observed span of 8.41.

### 3.6 Index cost is a first-class number, because `warmup_ms` made it one

| | build | nDCG@10 | recall@100 |
|---|---|---|---|
| bm25 | **0.8 s** | 0.6451 | 0.8586 |
| minilm | 194 s | 0.6533 | 0.9125 |
| bge_small | 874 s | 0.7097 | 0.9325 |
| mpnet | 1825 s | 0.6643 | 0.9350 |
| e5_base | 1825 s | **0.7191** | **0.9540** |

BM25's index builds **2,280× faster** than e5_base's and scores 0.074 lower. The harness
already timed warmup separately and excluded it from per-item latency — a decision made for
model loading in the first example — and that turned out to be exactly the right shape for
an index build.

`mpnet` is the cautionary row: 1825 seconds to build, and it scores *below* `bge_small`
which builds in less than half the time. Size is not the variable; training objective is.
`minilm` and `mpnet` are general sentence-similarity models, `bge_small` and `e5_base` are
trained for retrieval.

---

## 4. Discussion

**For the product case, the answer is: use a retrieval-trained bi-encoder, and add a
reranker only if you need the last four points.** `e5_base` alone reaches 0.7191 for
nothing, on a CPU, and is not statistically distinguishable from any paid reranker. Adding
the cheapest LLM on top of it reaches 0.7891 — a real +0.070 — for $0.055 per 200 queries.

**What you should not do is add a reranker to a weak first stage.** Every BM25-based
pipeline here is capped at 0.8163 no matter which model does the reordering, and eleven of
twelve are within 4 points of that cap. Money spent on a better reranker there buys almost
nothing; money spent on the retriever raises the cap itself.

**The tie is the recurring result across all four examples in this repo.** Summarisation:
the dearest arm ranked 15th of 24. AG News: a leader tied with five. DBpedia: a group of
ten across a 115× price range. NER: eight hosted arms across 78×. Here: twelve, two of
which are free. Four unrelated tasks, the same shape — at the top of a field, price stops
predicting quality well before quality stops varying.

---

## 5. Calibration checks that had to read true first

`random` and `first_k` are not arms worth ranking; they are the checks that the instrument
reads true before any of it is believed.

- `random` recall@100 = **0.0020** against a predicted 100/5183 = 0.0193. That is 1.8 SD
  below expectation for 200 Bernoulli draws — a low draw, not a fault, and the honest
  reading is that this check passes weakly rather than cleanly.
- `first_k` nDCG@10 = **0.0000** exactly, recall@100 = 0.0350. It ignores the query
  entirely; the non-zero recall is the accident of which documents sort first by id.
- BM25 nDCG@10 = **0.6451** against BEIR's published **0.665** for BM25 on SciFact. Close,
  and the gap is the right direction for a plainer tokeniser: no stemming, no stopword
  list, no Lucene.

---

## 6. Corrections

### This adapter never disabled reasoning, and the other three always did

`sf_qwen_s` scored **exactly** BM25's nDCG@10 on the dev slice. `llm_parsed` said why:
0.000 — it hit the output ceiling on 40 of 40 queries, produced nothing parseable, and the
pipeline fell back to BM25's ordering every time.

I read that as a budget problem and raised `max_tokens` 400 → 700. It failed identically.
`_meta.llm_raw`, added for exactly this, then gave the answer: **the empty string**, with
700 completion tokens spent. Not a model running out of room — a model reasoning silently.

The cause was mine. The other three examples all pass `reasoning: {enabled: false}` through
`extra_body`; I dropped that passthrough when writing this adapter and set it in none of the
48 configs. That is not a tuning difference — it breaks the one property the four examples
exist to support, that only the *task* differs between them. Fixed, fingerprinted, and
`qwen_s` then scored 0.7338.

Every reranking run made before the fix is in `data/runs-superseded/` with the reason
written down — including `gemma_m`, which was fine. A uniform instrument means re-running
the arms that worked too.

### I misread my own adapter's stored output, twice

A reranking arm overwrites `res.output` with the *pipeline's* 100-document ranking, which
is the right thing to score and the wrong thing to debug. I twice read those stored outputs
as the model's reply and drew conclusions from them before noticing.

### The tree went dirty mid-sweep

I wrote `retrieval_report.py` while the sweep was running, so `sf_llama_s_n200_v1` records
`harness.dirty: true`. All 19 main arms share one `adapter.sha256` (`cedb9f962a`), which is
what determines the instrument; 12 were committed at `0e20aae`, 6 at `a903fb3`, and
`llama_s` carries the flag. Second time this session.

---

## 7. NOT covered, NOT measured, NOT verified

- **Five of the 24 standard arms were never run.** `anthropic_s`, `openai_m`, `openai_l`,
  `anthropic_m`, `anthropic_l` — the frontier tier. They cost **$31.40 of the $39.81** a
  full 24-arm sweep would have cost, against this sweep's $2.45. The cut was
  "everything under $0.60/Mtok input", price-ordered and declared before any result was
  read. **So this report says nothing about whether a frontier model is a better
  reranker**, and the 12-way tie is a tie among cheap models plus two free ones. See
  [`HANDOVER_RETRIEVAL_FRONTIER_ARMS.md`](HANDOVER_RETRIEVAL_FRONTIER_ARMS.md).
- **The cost column is what the provider BILLED, not this repo's price table.** Those
  differ, because an alias is not a price: OpenRouter routes across upstream providers
  that charge differently. Measured across all four examples the table was wrong **per arm
  by 0.67× to 3.21×**, in both directions, and it reordered arms by cost. All four reports
  are now corrected and all four adapters record `usage.cost`. An earlier draft of this
  report quoted **2.41×** from a single before/after spend delta on a **$0.0055** run —
  far too small for fixed overhead and concurrent traffic not to dominate. That number
  was wrong and stated with more confidence than one measurement earned.
- **One first-stage swap, two rerankers, one corpus.** §3.4 is a pair, not a study. It does
  not show that e5_base is the best possible first stage, or that the headroom share
  transfers for any other reranker or corpus.
- **Rerank depth 20 and snippet 900 chars were tuned on the dev slice** and then fixed.
  `k=50` was tested and failed for a budget reason (`llm_parsed` 0.700); `k=10` scored
  0.6799 against `k=20`'s 0.6908. Nothing between 20 and 50 was tested.
- **`gliner`-style threshold tuning has no analogue here, but BM25's k1/b do.** They are
  `rank_bm25`'s defaults (1.5 / 0.75), recorded in the fingerprint, and **untuned**. A
  tuned BM25 might close some of the 0.074 gap to e5_base; nothing here bounds how much.
- **No confidence, no calibration.** Logprobs were never requested from any hosted model,
  in this example or any other.
- **The stability figures here were recomputed after a scorer fix on 2026-09-29.**
  `spearman()` had no tie correction and `ranks_on()` broke ties alphabetically. On this
  corpus the correction is small (≤0.007 at any n, because nDCG@10 rarely ties) but it is
  not zero, and the numbers above are the corrected ones. `P(same winner)` now excludes
  draws where either half had no unique best arm rather than crediting them as agreement.
- **One pass per arm, temperature 0** — and temperature 0 is *not* reproducible here.
  Two runs of an identical config scored 0.6691 and 0.6617, because OpenRouter routes
  across providers. Every interval in this report is over *queries*, not over *runs*, and
  the run-to-run variance is real and unmeasured.
- **Binary relevance only.** nDCG's graded machinery is declared (`gain = 2^rel − 1`) but
  does no work on this corpus, where every judgment is 1.
- **English scientific abstracts.** The relevance to podcast transcripts is by analogy.

---

## 8. Reproduction

```bash
python examples/retrieval-scifact/fetch.py --n 200
python examples/retrieval-scifact/fetch.py --n 40 --skip-corpus
cd harness
make dataset-create DATASET_ID=scifact_200 ARGS='--source-dir data/sources/scifact_200'
make dataset-materialize DATASET_ID=scifact_200

for f in ../examples/retrieval-scifact/configs/arm_*_n200.yaml; do
  python scripts/experiment_run.py --config "$f"
done

python scripts/retrieval_report.py --dataset-id scifact_200 --match sf_
python scripts/family_test.py --dataset-id scifact_200 --a sf_glm_s_n200_v1 \
    --against _n200_v1 --metric ndcg_10
python scripts/holdout_significance.py --dataset-id scifact_200 \
    --exclude-dataset scifact_40 --metric ndcg_10 --match sf_
python scripts/rank_stability.py --dataset-id scifact_200 --metric ndcg_10 --match sf_
```

Neither the corpus nor the queries are committed: `fetch.py` downloads both and both are
gitignored. Corpus identity travels as `corpus_sha256` inside every run, not as bytes.
