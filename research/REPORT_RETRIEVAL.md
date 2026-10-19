# Evaluation report — BM25, four dense retrievers and twelve LLM rerankers on SciFact

**Dataset** `scifact_200` · 200 scientific claims · a **5,183-document corpus** · 227 relevance judgments
**Protocol** 200 of 300 test queries, seeded, full corpus · nDCG@10, the BEIR standard · calibration: BM25 on all 300 queries, 0.6523 vs BEIR's 0.665 — [docs/PROTOCOL.md](../docs/PROTOCOL.md#retrieval--scifact)
**Arms** BM25 · 4 sentence-transformer bi-encoders · the 12 cheapest of 24 hosted LLMs reranking BM25's top-20 · 2 floors
**Design** 1 pass per arm · zero-shot, one prompt · temperature 0, reasoning off, `max_tokens` 700, no provider pinned (`providers_seen` is empty in every run) · rerank depth 20 · **$1.94 billed** for the 19 main arms (the four pair runs and three repeats billed $1.03 more)
**Date** main sweep and pair runs 2026-09-28, repeats 2026-09-29, index builds re-measured 2026-10-15 · **Harness** [`../harness`](../harness) · **Journal** [`NOTES.md`](internal/NOTES.md)
**Costs** are what the provider billed (`usage.cost`), not this repo's price table — see §7

> **The fourth metric shape, and the first where POSITION carries meaning.** Summarisation
> compares one text to one text. Classification compares one label to one label.
> Extraction compares a set to a set, and order is irrelevant. Retrieval compares a
> **list** to a set: an arm that finds the right document at rank 50 instead of rank 1 is
> not correct, and no set-valued metric can say so.


> **This is one of six experiments.** What all six agree on — and where they disagree
> with the conventional reading of a leaderboard — is in
> [`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).

## Executive summary

**Build `e5_base` retrieval first; add an LLM reranker on its top 20 only if about +0.07
nDCG@10 is worth about $732 per 1M queries.** `e5_base` (e5-base-v2, MIT, 438 MB, CPU, $0
per query) scores **0.7191**, +0.0740 over BM25, and is not separated from any of the twelve
BM25-then-rerank pipelines (§3.2). `glm_s` reranking `e5_base`'s candidates scores
**0.7891**, +0.0700 over `e5_base` alone (p 0.0001, separated), billed $0.1464 per 200
queries: one run, under a different adapter from the main table (§3.4). A reranker and a
better retriever are comparable moves; **do both** and they stack to +0.1441 over BM25 (§3.3).

**As run here:** the 12 cheapest of 24 hosted LLMs (no Anthropic or OpenAI arm), zero-shot,
one prompt, one run per arm, 200 SciFact claims. Frontier models, fine-tuning on SciFact and
other rerank depths were not tested (§7). Corrections and their dates: §6.

### Supporting facts

| the choice | what the data says |
|---|---|
| **Retriever** | **`e5_base`**: 0.7191, +0.0740 over BM25 (p 0.001), $0, CPU. Not separated from any of the twelve rerankers (p 0.27–0.97); `bge_small` (0.7097, free) likewise (p 0.12–0.97). n = 200 cannot resolve gaps of 0.02–0.03. |
| **Add a reranker** | **`glm_s`** on `e5_base`'s top 20: 0.7891, +0.0700 over `e5_base` (separated), $0.1464 per 200 queries = $732/month per 1M. Highest point estimate; one run, not separated from 6 of 22 arms (§3.4). |
| **Reranker on BM25 alone** | All 12 score above BM25 by 0.0566–0.0986. Worst to best is +0.0420 (p 0.004), and `llama_m` is Holm-separated from the leader `glm_s` (+0.0349). The top 12–13 are not resolved at n = 200; the bottom of the twelve is worse than the leader. |
| **Reranker vs. retriever** | The best reranker over BM25 (+0.0986) minus the retriever swap (+0.0740) is `glm_s` − `e5_base`, 0.0246, p 0.27: not separated. The worst reranker (+0.0566) is below the swap. |
| **Open-weight LLM, ≤128 GB** | GLM-4.5-Air (`glm_s`, MIT, 110B, ~221 GB native): ~110 GB at int8 is 86% of a 128 GB box, tight once KV cache counts; ~55 GB at int4 is comfortable. Every score was served by a hosted provider; quantised quality was not measured. |
| **Open-weight LLM, ≤64 GB** | `gemma_m` (Gemma-4-26B-A4B, 52 GB native, leaving ~12 GB of 64: tight): 0.7363 as served by a hosted provider. The 0.0074 gap to `glm_s` is inside run-to-run noise (two-run difference SD ≈ 0.0064). |
| **Rented API** | The same pair through a provider is $732/month per 1M queries. One proprietary arm (`qwen_s`) ran; whether a frontier model reranks better was not tested (§7). |
| **Does paying more help?** | Not shown: +0.0200 nDCG@10 per 10× billed cost (r = 0.32, n = 12, p ≈ 0.3), over a 7.6× range in the cheap hosted tier only. The dearest of the twelve ranks 2nd of 19 at $2,288/month for −0.2%. |
| **Is a 40-query pilot enough?** | Its leader, `llama_s`, finished 10th of 19 on 200 queries, 0.0265 behind `glm_s` (p 0.045 uncorrected, not separated under Holm): a rank inside a tie, not a wrong pick shown at this n. The dev runs are uncommitted, so the pilot's ρ 0.756 (which includes two floors) cannot be recomputed (§3.5). |
| **Fine-tune?** | Not tested: no arm was fine-tuned on SciFact. |

1. **A top group of 12–13 arms.** `glm_s` (0.7437) separates from only **6–7 of 18**
   opponents under Holm: 6 at the default 20,000 permutations, 7 at 400,000, because
   `gemma_s` and `mistral_s` sit on their thresholds. The group is `glm_s` plus 11–12
   opponents, spans 0.7437–0.7017 by point estimate, and "not separated" is not
   transitive. Two members, `e5_base` and `bge_small`, are free and local (0.0246 and
   0.0340 behind `glm_s`).

2. **The ceiling is a property of the first stage at rerank depth 20.** A reranker cannot
   rank a document its first stage never returned. The oracle sorts the top 20; BM25's
   recall@100 is 0.8586 and depths between 20 and 50 were not tested. Every BM25-based arm
   shares one ceiling, **0.8163**, and the best has taken **91.1%** of it.
   `e5_base`'s candidates have a ceiling of **0.8747**, and alone it exploits 82.2%.

3. **The registered prediction, 1 of 2** (commit `a903fb37`, 2026-09-28, before the pair
   runs): 0.786–0.797, built from `qwen_s`'s pre-fix headroom share (0.899) and `glm_s`'s
   (0.911). `glm_s` **0.7891**, inside. `qwen_s` **0.7799** as printed, outside by 0.006,
   and **0.7713** under the corrected parser, outside by 0.0147. Headroom-used went 90.9% →
   90.2% (`glm_s`) and, corrected, 87.4% → 88.2% (`qwen_s`): a mechanism seen in two
   rerankers on one corpus, not established. (The pair runs' BM25 half scored 0.7422
   rather than §3.1's 0.7437, hence 90.9% here against 91.1% above.)

---

## 1. What was measured

| property | value |
|---|---|
| Corpus | BEIR SciFact, **5,183 abstracts**, CC BY-SA 4.0, `corpus_sha256` `297643e2d005` |
| Queries | 200 test claims, seeded random, `items_sha256` frozen |
| Dev slice | 40 claims, a strict **prefix** of the same permutation — nested |
| Judgments | 227 over 200 queries: 184 queries have 1 relevant doc, 9 have 2, 4 have 3, 2 have 4, 1 has 5 |
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

| rule | why |
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

*How to read this table.* Sorted by **nDCG@10**, descending. ⟳ = BM25 retrieves, then
that LLM reorders BM25's top 20 (§2); these rows inherit BM25's recall@100 and its 1.2 s
index build, because the first stage *is* BM25. **first-stage index build** = one-off
time to index the 5,183-document corpus on CPU; — = no index (floors). **cost** = what the
provider billed for all 200 queries. **Bold** marks the best value in each column, plus
the two free, local arms in the top tie group (`e5_base`, `bge_small`: name, nDCG@10 and
cost). **Tie group:** every row from `glm_s` down to `gemma_s` except `llama_m` — 13 arms:
`glm_s` and the 12 opponents it is not separated from. `gemma_s` and `mistral_s` sit on their Holm
thresholds, which is why the group is quoted as 12–13 (§3.2).

| arm | nDCG@10 | recall@10 | recall@100 | MRR@10 | first-stage index build | cost (billed, 200 queries) |
|---|---|---|---|---|---|---|
| glm_s ⟳ | **0.7437** | 0.8067 | 0.8586 | 0.7364 | 1.2 s | $0.1421 |
| glm_m ⟳ | 0.7419 | 0.8067 | 0.8586 | 0.7325 | 1.2 s | $0.4576 |
| deepseek_m ⟳ | 0.7399 | 0.7893 | 0.8586 | 0.7373 | 1.2 s | $0.2381 |
| deepseek_s ⟳ | 0.7378 | 0.8017 | 0.8586 | 0.7303 | 1.2 s | $0.0600 |
| gemma_m ⟳ | 0.7363 | 0.7967 | 0.8586 | 0.7287 | 1.2 s | $0.0721 |
| gemma_l ⟳ | 0.7359 | 0.7917 | 0.8586 | 0.7287 | 1.2 s | $0.1701 |
| llama_l ⟳ | 0.7281 | 0.7955 | 0.8586 | 0.7234 | 1.2 s | $0.1731 |
| **e5_base** | **0.7191** | **0.8305** | **0.9540** | 0.6889 | 1386 s | **$0** |
| qwen_s ⟳ | 0.7183 | 0.7947 | 0.8586 | 0.7062 | 1.2 s | $0.1559 |
| llama_s ⟳ | 0.7172 | 0.7855 | 0.8586 | 0.7065 | 1.2 s | $0.1458 |
| **bge_small** | **0.7097** | 0.8298 | 0.9325 | 0.6812 | 480 s | **$0** |
| llama_m ⟳ | 0.7088 | 0.7792 | 0.8586 | 0.6996 | 1.2 s | $0.1434 |
| mistral_s ⟳ | 0.7071 | 0.7668 | 0.8586 | 0.6990 | 1.2 s | $0.0852 |
| gemma_s ⟳ | 0.7017 | 0.7760 | 0.8586 | 0.6938 | 1.2 s | $0.0962 |
| mpnet | 0.6643 | 0.7707 | 0.9350 | 0.6355 | 1659 s | $0 |
| minilm | 0.6533 | 0.7705 | 0.9125 | 0.6212 | 143 s | $0 |
| bm25 | 0.6451 | 0.7635 | 0.8586 | 0.6152 | **1.2 s** | $0 |
| random | 0.0005 | 0.0010 | 0.0020 | 0.0006 | — | $0 |
| first_k | 0.0000 | 0.0000 | 0.0350 | 0.0000 | — | $0 |

**Costs are what the provider billed** (`_meta.usage.cost`), not this repo's price table.
**Index build times** are one-off, uncached builds re-measured on 2026-10-15 on one machine
(4-vCPU Xeon, Linux), each arm alone, through the adapter's own `warmup()` with the
revisions the runs used: [`docs/evidence/index_build_times.json`](../docs/evidence/index_build_times.json).
The committed runs loaded a cached index, so their `warmup_ms` (6–9 s) is a load time, not a
build time. *The figures these replace (bm25 0.8 s, minilm 194 s, bge_small 874 s, mpnet
1825 s, e5_base 1825 s) came from another machine, and only three had a recorded source;
mpnet's was a copy of e5_base's.*

*This footnote said the opposite until 2026-09-30 — "costs are this repo's price table,
they understate the bill by roughly 2.4×" — while the cells above it had already been
converted to the bill, and while §1 and the retraction in §7 both said the bill was
being used. Three statements, two of them right. The 2.4× was also a multiplier this
repo retracted. Found by external review.*

### 3.2 A tie of twelve or thirteen arms, and two of them are free

`glm_s` vs a family of 18 declared before any p-value was read, Holm step-down at α = 0.05:

```
separated from 6 of 18; ahead on the point estimate against 18 of 18

  SEPARATED:      bm25 (+0.0986)  first_k  random  minilm (+0.0904)
                  mpnet (+0.0794)  llama_m (+0.0349)

  ON THE BOUNDARY: gemma_s  p = 0.0045  vs threshold 0.0042
                   mistral_s p = 0.0055 vs threshold 0.0045

  NOT separated:  gemma_s  mistral_s  llama_s  bge_small  llama_l  e5_base
                  qwen_s  gemma_m  gemma_l  deepseek_s  deepseek_m  glm_m
```

**`e5_base` and `bge_small` are in that group, and they cost nothing.** A 110M-parameter
encoder running on a laptop CPU is not shown different from any of the twelve hosted LLM
rerankers: with `e5_base` as arm A, the sign-flip p against the twelve is 0.27–0.97 (it
trails `glm_s` by 0.0246, p 0.27); with `bge_small`, 0.12–0.97 (0.0340 behind `glm_s`, p
0.13) — `family_test.py --a sf_e5_base_n200_v1 --runs-dir data/runs-reparsed`, uncorrected
per pair. That is not "equal": n = 200 cannot resolve gaps of 0.02–0.03. The twelve or
thirteen span 0.7437–0.7017 by point estimate, and "not separated" is not transitive.

The tie also explains the stability numbers: ρ between two disjoint halves rises
monotonically 0.409 → 0.748, so the *ordering* is real, while **P(same winner) is 0.01–0.07**
— with twelve or thirteen arms that cannot be told apart at this n, which one crowns a random half is
close to a coin toss. Both statements are true at once, and reading either alone would
mislead. (`rank_stability.py` reads `EVAL_RUNS_DIR`; the figures above are under
`data/runs-reparsed`, the record. Under `data/runs`, with the pre-fix `qwen_s`, they read
0.408 → 0.742.)

### 3.3 Adding a reranker and swapping the retriever are comparable; together they stack

Each line is a paired sign-flip on 200 queries, uncorrected (20,000 permutations):

- worst reranker → best reranker (`gemma_s` → `glm_s`): **+0.0420**, p 0.004, across a
  **7.6× billed** price range — the *choice* of reranker
- BM25 → worst reranker (`gemma_s`): **+0.0566**, p 0.005 — the cheapest *addition* of a reranker
- BM25 → `e5_base`, no LLM at all: **+0.0740**, p 0.001 — the *retriever swap*
- BM25 → best reranker (`glm_s`): **+0.0986**, p < 0.0001 — adding the best reranker

The best reranker over BM25 minus the retriever swap is exactly `glm_s` − `e5_base`,
0.0246, p 0.27 (§3.2): not separated. The worst reranker (+0.0566) is below the swap, and
the best is the best of twelve, picked after the fact. So adding a reranker and swapping
the retriever are comparable and not distinguishable here; the choice among rerankers is
numerically smaller than either. They stack: `glm_s` on `e5_base`'s candidates (§3.4,
pair run) is **+0.1441** over the main-table BM25 (p < 0.0001).

*Corrections to this section's ranking of the levers: §6.*

### 3.4 The ceiling, and a prediction registered before the arm existed

A reranker cannot rank a document its first stage never returned. `retrieval_report.py`
computes the oracle: sort the arm's own top-20 candidates so every relevant document
precedes every irrelevant one, and score that.

```
arm             nDCG@10  ceiling     gap    used
glm_s            0.7437   0.8163  0.0726  91.1%
qwen_s           0.7183   0.8163  0.0980  88.0%
e5_base          0.7191   0.8747  0.1556  82.2%
bm25             0.6451   0.8163  0.1712  79.0%
```

Every BM25-based arm shares one ceiling because they share one first stage, and the best
has taken 91% of it. `e5_base` has a **higher** ceiling and exploits less of it.

**The prediction, written down before `first_stage` was made configurable and before any
e5-based arm existed** (commit `a903fb37`, 2026-09-28 22:13; the pair runs are later and
record `dirty: false`)**:** if the headroom share transfers, a reranker on e5_base's
candidates reaches 0.899 × 0.8747 = 0.786 to 0.911 × 0.8747 = 0.797. The range's ends are
the two rerankers' own shares at the time — `qwen_s` 0.899 (its pre-fix 0.7338; 0.880
corrected) and `glm_s` 0.911 — so it was built from the very two arms later tested.

**Measured:**

*Evidence: `harness/data/runs-pair/`, committed since 2026-09-29. These four runs sat
in an ignored directory until an external review pointed out that the most-advertised
number in this repo was the one number with no committed run behind it.
`check_report_claims.py` now verifies 0.7891 against the registered **range**, 0.786–0.797,
rather than against itself.*

*The `glm_s` row is unaffected by the round-2 retrieval parser fix — **0 of 200 items
reorder** under the corrected parser. The `qwen_s` row IS affected: under the corrected
parser its stored replies give 0.7138 over BM25 and 0.7713 over e5_base. Those two runs
have not been re-measured, so the row below is the pre-fix figure with the corrected
one stated here.*

Both halves of each pair ran under the same adapter, so the comparison is internally valid;
that adapter differs from the 19-arm main table's, which is why these four are reported
separately and are not in §3.1 — and why `glm_s` over BM25 reads 0.7422 here against
0.7437 in §3.1 (90.9% of the ceiling here, 91.1% in the block above).

| reranker | nDCG@10, BM25 candidates | nDCG@10, e5_base candidates | gain from e5_base | share of ceiling reached (BM25 → e5_base) |
|---|---|---|---|---|
| glm_s | 0.7422 | **0.7891** | +0.0469 | 90.9% → 90.2% |
| qwen_s, as stored | 0.7224 | 0.7799 | +0.0575 | 88.5% → 89.2% |
| qwen_s, corrected parser | 0.7138 | 0.7713 | +0.0575 | 87.4% → 88.2% |

Each reranker reorders the top 20 candidates of the named first stage. **Share of ceiling
reached** = nDCG@10 ÷ that first stage's oracle ceiling (0.8163 for BM25, 0.8747 for
`e5_base`). The corrected `qwen_s` row is `reparse.py` run over the two stored pair runs
(`qwen_s` BM25-first 12 items reordered, e5-first 10); it is not a committed run.

**Outcome: one of two inside the registered range.** `glm_s`, at 0.7891, is inside.
`qwen_s` is outside: 0.006 below 0.786 as printed, **0.0147 below** under the corrected
parser. The share of available headroom each reranker takes moved by under one percentage
point when the candidates changed entirely (−0.7 for `glm_s`, +0.7 for `qwen_s`,
corrected) — consistent with the mechanism, from two rerankers on one corpus.

**What the four pair runs show** (sign-flip on 200 queries, uncorrected; each prediction
was made once before and tested once, and none of these was repeated):

- `glm_s`, e5-first vs BM25-first: +0.0469, p 0.015. `qwen_s`: +0.0575, p 0.002.
- `glm_s`, e5-first vs `e5_base` alone: +0.0700, p 0.0001 — the LLM adds on top of the
  encoder.

**What they do not show.** Run-to-run variance (each cell is one run; "Between-run
variance" below puts a two-run difference at SD ≈ 0.0064). Whether 0.7891 is the best
arm in a separated sense: with `glm_s` e5-first as arm A over a 22-arm family (the 19
main arms and the other three pair runs, the `qwen_s` ones as stored), Holm separates it from 16 and does **not**
separate it from `glm_m` (+0.0473, p 0.013), `deepseek_m` (+0.0492, p 0.014),
`deepseek_s` (+0.0513, p 0.009), `glm_s` BM25-first (+0.0469, p 0.015), `glm_s` in the
main table (+0.0454, p 0.017) or `qwen_s` e5-first (+0.0092, p 0.36). 0.7891 is the highest
**point estimate** here. And the pair adapter is not the main adapter, so 0.7891 against
the main table's 0.7437 mixes the first-stage swap with the adapter and the run.

### 3.5 The dev slice's leader was 10th of 19 on the measurement slice

**The dev-slice runs (`scifact_40`) are not committed**, so the dev figures below are the
original session's and cannot be recomputed from this repo: ρ(dev-40, measurement-200)
over 19 arms = **0.756** (the 19 include the `random` and `first_k` floors, which anchor
the bottom of both rankings), the dev leader being `llama_s`, `glm_s` having been **9th**
on dev, and `mistral_s` having moved six places. What the repo does give:

- dev leader `llama_s` → **10th of 19** on measurement by point estimate (§3.1), down nine places
- `llama_s` is **0.0265** behind `glm_s`, p 0.045 uncorrected, not separated under Holm
  (§3.2) — so "10th" is a rank inside a tie, not a wrong pick shown at this n

Choosing an arm on 40 queries put the 10th-by-point-estimate arm first; it is not shown
worse than the leader. This is the same machinery that found a winner's curse in the
summarisation study and found none in NER.

On the 160 queries the dev slice never contained (only the 40 dev item ids are needed,
from `fetch.py --n 40`; the dev runs are not), the global permutation test gives p = 0.0002 — an arm effect exists — with **34 of 171 pairs distinguishable**
and a Nemenyi critical difference of 2.21 rank positions against an observed span of
8.4. This part is recomputable: `EVAL_RUNS_DIR=data/runs-reparsed holdout_significance.py`
(§8).

### 3.6 Index cost is a first-class number, because `warmup_ms` made it one

| arm | index build time | nDCG@10 | recall@100 |
|---|---|---|---|
| bm25 | **1.2 s** | 0.6451 | 0.8586 |
| minilm | 143 s | 0.6533 | 0.9125 |
| bge_small | 480 s | 0.7097 | 0.9325 |
| e5_base | 1386 s | **0.7191** | **0.9540** |
| mpnet | 1659 s | 0.6643 | 0.9350 |

First-stage arms only, sorted by index build time (one-off, CPU, uncached — see the note
under §3.1).

BM25's index builds about **1,150× faster** than e5_base's (1.2 s against 1,386 s) and scores 0.074 lower. The harness
already timed warmup separately and excluded it from per-item latency — a decision made for
model loading in the first example — and that turned out to be exactly the right shape for
an index build.

`mpnet` is the cautionary row: the slowest build, 1,659 seconds, and it scores *below*
`bge_small`, which builds in under a third of the time (480 s). Size is not the variable
here; training objective is consistent with it, from four first-stage arms.
`minilm` and `mpnet` are general sentence-similarity models, `bge_small` and `e5_base` are
trained for retrieval.

---

### The parser fix, what it actually moved, and a correction to this section

**One arm changes: `qwen_s`, 0.7338 → 0.7183.** 16 of its 200 replies were prose the
parser had been reading as a one-document ranking.

**This section previously said three arms changed, and two of those were my own bug.**
The round-2 fix added a comma path to the line parser so that `4983, 13734012` would
parse. `llama_l` opens with a real array and then corrects itself in prose —
`…, 4459491 is removed and [30813140, …` — so `json.loads` fails, the line path split
that line on commas, and tokens like `[8925851` and `21884449]` passed the
"no spaces" test and were accepted as document ids. 25 of 200 items on one run.

Those bracket tokens are never real ids, so they counted as hallucinations *and* the
harvested partial ranking scored **below the BM25 fallback the pipeline uses when a
reply is unreadable** — 0.6386 against 0.7155 on the same bytes. The arm was punished
for the parser's guess.

| arm | nDCG@10 as first measured | after round-2 parser change (reverted) | after current parser |
|---|---|---|---|
| `llama_l` | 0.7281 | 0.6864 | **0.7281** |
| `llama_s` | 0.7172 | 0.7129 | **0.7172** |
| `qwen_s` | 0.7338 | 0.7183 | **0.7183** |

Under the current parser `llama_l` and `llama_s` are back to their first-measured scores —
the round-2 drop was the parser's artifact — while `qwen_s`'s drop is real and stays.

The parser now refuses a leading array that will not parse, rather than harvesting
fragments from it, and a line-path token must look like an id (`[\w.-]+`). Found by
external review.

### Between-run variance — smaller than this report claimed, and still unmeasured

Three arms were re-run on 2026-09-29 (`data/runs-repeats/`). Once the parser artifact
is removed, the like-for-like deltas are:

`bm25first` is the BM25-candidate half of the §3.4 pair (`sf_glm_s_bm25first_n200_v1`,
`sf_qwen_s_bm25first_n200_v1`): the same reranker settings run again later, under the
pair adapter — which is not the main table's adapter, so these two pairs mix run-to-run
difference with an adapter difference. Δ = nDCG@10 of the second (later) run − the
first, both read under the current parser; a negative Δ means the later run scored lower.

| arm | first run | second run | Δ nDCG@10 (second − first) |
|---|---|---|---|
| `llama_l` | 0.7281 | 0.7155 | **−0.0126** |
| `llama_s` | 0.7172 | 0.7125 | −0.0047 |
| `qwen_s` | 0.7183 | 0.7187 | +0.0004 |
| `glm_s` bm25first vs `glm_s` | 0.7437 | 0.7423 | −0.0015 |
| `qwen_s` bm25first vs `qwen_s` | 0.7183 | 0.7138 | −0.0045 |

**These deltas are derived, not stored.** The committed `data/runs-repeats/` and
`data/runs-pair/` hold the uncorrected figures (`llama_l` 0.6386, `llama_s` 0.7132,
`qwen_s` 0.7187; `qwen_s` BM25-first 0.7224), and the repeat runs are `dirty: true`. The
table reads them through `reparse.py` (`--runs <dir> --out <scratch>`, which needs the
qrels from `fetch.py`); the reparsed copies are not committed. `llama_s` previously read
−0.0003 and `qwen_s` −0.0004 here: the first compared the repeat with the round-2
parser's figure for the original, the second had its sign reversed.

**An earlier version of this section reported that swing as 0.0895 and called it twelve
times the noise floor.** Most of it was the parser artifact above. Pooled over the five
pairs, σ_run is **0.0045 per arm** (0.0089 for `llama_l` alone) and the SD of a
two-run difference is **0.0064**: a gap below about **0.013** (two such SDs) between two
single runs is inside run-to-run noise. The 0.0074 gap between `gemma_m` and `glm_s`
is 1.2 of those SDs. This report's earlier noise figure, also 0.0074 (0.6691 against
0.6617), came from two runs that, as round 3 pointed out, **appear in no committed run
and cannot be re-derived.** The five pairs above replace them. Five pairs, four
rerankers, one corpus.

What does not go away: temperature 0 is not reproducible on any hosted provider here —
between 13 and 78 of 200 replies are byte-identical across two runs of the same config
— and every separation test in this report is over items *within* one run, so none of
them can see σ_run at all. Adding 2σ_run² to the standard error takes the separated set
from 6 to 5 of 18. **No arm outside SciFact has a repeat run at all.**

---

## 4. Discussion

**For the product case, as run here: start with a retrieval-trained bi-encoder, and add
a reranker if +0.0700 nDCG@10 is worth the bill.** `e5_base` alone reaches 0.7191 for
nothing, on a CPU. It trails the best BM25-first reranker by 0.0246 and is not separated
from any of the twelve at n = 200 (p 0.27–0.97) — not shown equal. Adding `glm_s` on top
of it reaches 0.7891, +0.0700 over `e5_base` alone (p 0.0001, uncorrected; one run, one
reranker) for **$0.1464 billed** per 200
queries (the §3.4 pair run; `glm_s` over BM25 in §3.1 billed $0.1421). (`glm_s` is not the cheapest reranker; `deepseek_s` is, at $0.0600. The
$0.055 previously quoted here was the price table, and the "cheapest" was wrong under
either cost.)

**A BM25-first reranker is capped, and a stronger first stage raises the cap.** Every
BM25-based pipeline here is capped at 0.8163 at rerank depth 20 no matter which model does
the reordering (the oracle sorts the top 20; depths between 20 and 50 were not tested).
All twelve beat BM25 by 0.0566–0.0986, and the worst-to-best spread is +0.0420
(p 0.004), so the choice among rerankers is not nothing; `e5_base`'s candidates have a
cap of 0.8747.

**The tie is the recurring result across the four examples that existed when this was
written** (five of the six experiments now; see the synthesis). Summarisation:
the dearest arm ranked 18th of 29 (15th of the 24 hosted). AG News: a leader tied with three others. DBpedia: a leader
tied with nineteen, across a 115× price range (both per
[`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md), after the 2026-09-30 fine-tune runs). NER:
eight hosted arms across 78×. Here: twelve or thirteen, two of which are free. Five unrelated tasks, the same shape — at the top of a field, the leader cannot be
separated from a group spanning a wide price range (not shown different, which is not the
same as equal).

---

## 5. Calibration checks that had to read true first

`random` and `first_k` are not arms worth ranking; they are the checks that the instrument
reads true before any of it is believed.

- `random` recall@100 = **0.0020** against a predicted 100/5183 = 0.0193. That is 1.8 SD
  below expectation for 200 Bernoulli draws — a low draw, not a fault, and the honest
  reading is that this check passes weakly rather than cleanly.
- `first_k` nDCG@10 = **0.0000** exactly, recall@100 = 0.0350. It ignores the query
  entirely; the non-zero recall is the accident of which documents sort first by id.
- BM25 on all 300 test queries = **0.6523 ± 0.0453** (95% interval, n = 300;
  [`docs/evidence/calibration/scifact.json`](../docs/evidence/calibration/scifact.json))
  against BEIR's published **0.665** for BM25 on SciFact: 0.0127 apart, inside its own
  interval. The 200-query slice reads 0.6451 (the arms are scored on it). No cause for the
  gap is established; this BM25 has no stemming, no stopword list and no Lucene.

---

## 6. Corrections

### The lever ranking in §3.3 was corrected twice

Until 2026-10-19 §3.3 said the largest single move available was replacing the retriever,
not adding a model on top of it. That compared the retriever swap (+0.0740) with the choice
among rerankers (+0.0420), not with adding a reranker (+0.0986). The executive summary,
which said "reranking beats retrieval", and the heading disagreed with each other. The
correction then ranked adding the best reranker (+0.0986) over the swap (+0.0740), which
the same section's own test does not support: their difference, `glm_s` − `e5_base`, is
0.0246 at p 0.27, and the best reranker is the best of twelve picked after the fact. The
section now says the two are comparable and not distinguishable here.

### The executive summary's "weak first stage" and "no proprietary model" lines

The summary said not to deploy a reranker on a weak first stage and that a better reranker
there "buys almost nothing"; every BM25 pipeline beat BM25 by 0.0566–0.0986 and the
worst-to-best spread is +0.0420 (p 0.004), so it now states the cap instead. It also said
no proprietary model was needed among the arms run; one proprietary arm (`qwen_s`) ran and
none of the five frontier models did, so it now says that.

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
`qwen_s` then scored 0.7338 — **0.7183 under the corrected parser**, which is the
figure §3.1 and the rest of this report use. The 0.7338 is what that fix produced
at the time and is kept because the sentence is about that fix.

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

- **Twelve of the 24 hosted arms were never run on SciFact** — only the 12 below the price
  cut were. The five that matter most are the frontier tier, `anthropic_s`, `openai_m`,
  `openai_l`, `anthropic_m`, `anthropic_l`: they would cost **about $12**,
  against this sweep's **$1.94 as billed** — not the $31.40 stated here until
  2026-09-29, which rested on a multiplier that does not survive checking. The cut was
  "everything under $0.60/Mtok input", price-ordered and declared before any result was
  read. **So this report says nothing about whether a frontier model is a better
  reranker**, and the top tie (12–13 arms) is a tie among cheap models plus two free ones. See
  [`HANDOVER_RETRIEVAL_FRONTIER_ARMS.md`](internal/HANDOVER_RETRIEVAL_FRONTIER_ARMS.md).
- **The cost column is what the provider BILLED, not this repo's price table.** Those
  differ, because an alias is not a price: OpenRouter routes across upstream providers
  that charge differently. Measured across all four examples the table was wrong **per arm
  by 0.67× to 3.76×**, in both directions, and it reordered arms by cost. All four reports
  are now corrected and all four adapters record `usage.cost`. An earlier draft of this
  report quoted **2.41×** from a single before/after spend delta on a **$0.0055** run —
  far too small for fixed overhead and concurrent traffic not to dominate. That number
  was wrong and stated with more confidence than one measurement earned.
- **One first-stage swap, two rerankers, one corpus.** §3.4 is a pair, not a study. It does
  not show that e5_base is the best possible first stage, or that the headroom share
  transfers for any other reranker or corpus. The prediction was registered once and
  tested once, and one of its two rerankers (`qwen_s`) fell outside the range. The four
  pair runs are single runs under an adapter that differs from the main table's.
- **Contamination was not measured.** SciFact is a public benchmark (BEIR); whether any
  hosted model saw its claims or abstracts in training is unknown, and no arm was scored
  on held-back data. The relevance judgments are also incomplete — 227 for 200 queries,
  mostly one relevant document each — so a relevant but unjudged abstract that an arm
  ranks first counts against it, for every arm alike.
- **No arm ran on self-hosted hardware.** Every open-weight score here was served by a
  hosted provider (no provider pinned; `providers_seen` is empty in every run). The memory
  figures in the executive summary are model sizes, not measured deployments, and
  quantised quality was not measured.
- **Zero-shot, one prompt.** No hosted model was shown examples or run with a second
  prompt wording; a different prompt could reorder the twelve.
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
- **One pass per arm, temperature 0** — and temperature 0 is *not* reproducible here:
  between 13 and 78 of 200 replies are byte-identical across two runs of the same config,
  and the five pairs in "Between-run variance" above differ by up to 0.0126
  (`llama_l`), SD of a two-run difference ≈ 0.0064. Which upstream provider served a reply
  is not recorded, so the cause is not established here. Every interval in this report is
  over *queries*, not over *runs*; five pairs on four rerankers do not measure the
  run-to-run variance of the other eight.
- **Binary relevance only.** nDCG's graded machinery is declared (`gain = 2^rel − 1`) but
  does no work on this corpus, where every judgment is 1.
- **English scientific abstracts.** The relevance to podcast transcripts is by analogy.

---

## 8. Reproduction

```bash
python examples/retrieval-scifact/fetch.py --n 200
python examples/retrieval-scifact/fetch.py --n 40 --skip-corpus
cd harness
# The dataset file is committed and frozen; materialize checks the fetched bytes against it.
make dataset-materialize DATASET_ID=scifact_200

for f in ../examples/retrieval-scifact/configs/arm_*_n200.yaml; do
  python scripts/experiment_run.py --config "$f"
done

# The record for every SciFact figure is data/runs-reparsed (corrected parser). Every script
# reads it through EVAL_RUNS_DIR; data/runs holds the pre-fix qwen_s (0.7338).
export EVAL_RUNS_DIR=data/runs-reparsed
python scripts/retrieval_report.py --dataset-id scifact_200 --match sf_
python scripts/family_test.py --dataset-id scifact_200 --a sf_glm_s_n200_v1 \
    --against _n200_v1 --metric ndcg_10 --runs-dir data/runs-reparsed
python scripts/holdout_significance.py --dataset-id scifact_200 \
    --exclude-dataset scifact_40 --metric ndcg_10 --match sf_
python scripts/rank_stability.py --dataset-id scifact_200 --metric ndcg_10 --match sf_

# The §3.4 pair runs live in data/runs-pair, so testing them against the main arms needs
# one directory holding both (copy the runs; the config_ids differ, so nothing collides):
mkdir -p /tmp/sf_all && cp -r data/runs-reparsed/* data/runs-pair/sf_* /tmp/sf_all/
python scripts/family_test.py --dataset-id scifact_200 --a sf_glm_s_e5first_n200_v1 \
    --against _n200_v1 --metric ndcg_10 --runs-dir /tmp/sf_all
python scripts/pair_test.py --dataset-id scifact_200 --a sf_glm_s_e5first_n200_v1 \
    --b sf_glm_s_bm25first_n200_v1 --metric ndcg_10 --runs-dir /tmp/sf_all
```

The between-run table is `examples/retrieval-scifact/reparse.py --runs <dir> --out
<scratch>` over `data/runs-repeats` and `data/runs-pair`; the pair runs are stored
uncorrected.

Neither the corpus nor the queries are committed: `fetch.py` downloads both and both are
gitignored. Corpus identity travels as `corpus_sha256` inside every run, not as bytes.
