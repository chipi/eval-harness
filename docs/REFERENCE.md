# Reference — every metric, model and dataset in this repo, and where each one comes from

A single index for the five worked examples. Nothing here is a summary of results; it is
the **glossary**, so that reading an example does not require already knowing what
`rougeLsum` recall or nDCG@10 is, or which weights `gemma_m` actually loads.

Every row links to the primary source: the HuggingFace repo for a model or dataset, the
paper or specification for a metric.

- [Metrics](#metrics) — what each number means, how it is computed here, and what it cannot see
- [Success criteria per experiment](#success-criteria-per-experiment) — what "good" meant, and why
- [Models](#models) — every arm, with the exact weights or upstream model id
- [Datasets](#datasets) — every corpus, its licence, and its download recipe
- [Statistical tests](#statistical-tests) — how separation is decided
- [Terminology](#terminology) — the canonical name for every experiment, arm and term
- [`papers/`](papers/README.md) — every cited work with the redistribution licence **read from the publisher's page**, and a fetcher for the twelve that permit it

---

## Metrics

Each example declares `PRIMARY_METRIC` (the one thing arms are ranked by) and
`METRIC_KINDS`, which splits everything else into **quality** (a claim about how good the
output is) and **descriptive** (a diagnostic that must never be ranked). The split is
enforced in code, not convention: `harness/scripts/leaderboard.py` will not rank a
descriptive metric.

### Summarisation — continuous overlap

| metric | kind | what it is |
|---|---|---|
| **`coverage`** ← primary | quality | [ROUGE-Lsum](https://aclanthology.org/W04-1013/) **recall** against the human reference, after clipping the output to a word budget. "How much of what a human thought mattered did it get?" |
| `concision` | quality | ROUGE-Lsum **precision** over the whole output. "What share of what it wrote earned its place." Padding is punished here exactly as much as raw recall rewards it. |
| `rouge1` | quality | Unigram overlap — [ROUGE](https://aclanthology.org/W04-1013/) in its simplest form. Reported because it is what most papers quote. |
| `rougeLsum` | quality | Longest-common-subsequence overlap, computed per sentence and unioned. Rewards preserving order, unlike `rouge1`. |
| `grounding` | quality | **Ours, ~20 lines, not comparable to anyone else's number.** Share of the summary's bigrams that also appear in the *article*. High = extractive and safe; low = abstractive, which is either a good paraphrase or a fabrication. It cannot tell those apart — but it *can* tell you the model left the source behind, which ROUGE cannot. |
| `compression`, `length_vs_reference` | descriptive | Output length relative to article and to the human reference. ROUGE rises with length, so this is **how a verbose winner gets caught**. |
| `fmt_bullets`, `fmt_markdown`, `fmt_narration`, `fmt_label`, `fmt_paragraphs`, `fmt_overlong` | descriptive | Format compliance. A model that answers with a markdown heading is not wrong about the content, and this keeps that out of the quality number. |

> **What ROUGE cannot see:** it is n-gram overlap. A factually wrong summary that reuses
> the article's wording scores well; a correct paraphrase scores badly. Read `grounding`
> beside it, never instead of it. ROUGE is the standard because it is cheap and
> reproducible, not because it is right — see
> [Kryscinski et al., *Neural Text Summarisation: A Critical Evaluation*](https://aclanthology.org/D19-1051/).

Implementation: [`google-research/rouge`](https://github.com/google-research/google-research/tree/master/rouge) via the `rouge-score` package.

### Classification — binary per item

| metric | kind | what it is |
|---|---|---|
| **`correct`** ← primary | quality | 1 if the predicted label equals the gold label, else 0. Its mean **is** accuracy. |
| `parsed` | quality | Whether the output could be read as a label at all. Quality, not descriptive: an arm that cannot be parsed cannot be deployed, whatever it knows. |
| `correct_after_repair` | descriptive | Whether a lenient re-parse would have rescued it. The gap between this and `correct` is **what the parser is worth** — 8.6 accuracy points to one arm. |
| `confidence` | descriptive | The model's own probability for its answer. Only the local ML arms supply it; no hosted arm does, because logprobs were never requested. |
| `answer_words`, `fmt_verbose`, `fmt_markdown` | descriptive | Did it answer with one word, or a paragraph containing one. |

**Macro-F1 is not here, and that is deliberate.** Macro-F1 needs a confusion matrix over
the whole run — there is no per-item number whose mean is macro-F1. It lives in
`harness/scripts/classification_report.py` instead. See
[scikit-learn's explanation of micro vs macro averaging](https://scikit-learn.org/stable/modules/model_evaluation.html#precision-recall-f-measure-metrics).

### Extraction (NER) — a set vs a set

| metric | kind | what it is |
|---|---|---|
| **`f1`** ← primary | quality | Harmonic mean of precision and recall over the entity set for **one item**, matched one-to-one after normalisation. Type must match. |
| `precision`, `recall` | quality | Of what it found, how much was right; of what was there, how much it found. |
| `untyped_f1` | quality | The same, ignoring the type label. **The pair is the point:** `f1` asks "did it label it right", `untyped_f1` asks "did it find it at all". |
| `type_penalty` | descriptive | `untyped_f1 − f1`. Credit lost purely to mislabelling something it did find. A type-confusion problem is fixed differently from a detection problem, and this says which you have. |
| `tp`/`fp`/`fn` (+ untyped) | descriptive | Raw counts, so a report script can pool them into a **corpus micro-F1** — a different number from the mean of per-item F1s, answering a different question. |
| `parsed` | quality | Could the output be read as a set. An unreadable answer scores **0**, not "found nothing" — those are different, and conflating them once paid a non-answer 1.0. |

Background: [CoNLL-2003 shared task](https://aclanthology.org/W03-0419/) defines the
standard exact-match entity F1 this follows.

### Retrieval — a ranked list vs a set

| metric | kind | what it is |
|---|---|---|
| **`ndcg_10`** ← primary | quality | [Normalised Discounted Cumulative Gain](https://dl.acm.org/doi/10.1145/582415.582418) at rank 10. Position-weighted: a relevant document at rank 1 is worth more than at rank 10, discounted by `1/log2(rank+1)`. Normalised by the best possible ordering, so 1.0 is perfect. |
| `recall_10`, `recall_100` | quality | Share of relevant documents appearing in the top 10 / top 100. **`recall_100` is what a two-stage pipeline depends on** — a reranker cannot retrieve what the first stage never returned. |
| `mrr_10` | quality | [Mean Reciprocal Rank](https://en.wikipedia.org/wiki/Mean_reciprocal_rank) — `1/rank` of the first relevant document, 0 if outside the top 10. |
| `unknown_ids` | descriptive | Document ids the model named that are not in the corpus. **Hallucinated ids keep their slot in the ranking** — dropping them would slide real documents up and make invention a scoring strategy. |
| `duplicate_ids` | descriptive | Ids repeated in one answer. Collapsed, not counted, or one document could fill the whole top-10. |
| `rank_of_first`, `found_any`, `n_returned`, `n_relevant` | descriptive | `rank_of_first` is **never** ranked: 0 means "never found", which would sort as the best possible position. |

Gain function is `2^rel − 1`, matching
[`pytrec_eval`](https://github.com/cvangysel/pytrec_eval) and [BEIR](https://github.com/beir-cellar/beir).
On SciFact every judgment is binary, so this is indistinguishable from linear gain — it is
declared anyway, because a metric that silently changes meaning between corpora is worse
than one that is merely wrong.

### Shared across all examples

| metric | kind | what it is |
|---|---|---|
| `cost_usd` | descriptive | **What the provider billed** (`usage.cost`), not a price table. See [REPORT_RETRIEVAL §7](../research/REPORT_RETRIEVAL.md) for why that distinction cost four reports a correction. |
| `latency_ms` | descriptive | Per item, **excluding** warm-up. Index builds and model loads are reported separately as `warmup_ms`. |
| `truncated` | descriptive | The provider stopped at `max_tokens`. Distinguishes "the model is bad" from "the budget was too small". |
| `reasoning_tokens` | descriptive | Tokens spent on hidden reasoning. All examples run `reasoning: {enabled: false}`; this verifies it took. |

---

## Success criteria per experiment

"Which arm is best" is decided by exactly one metric per example, fixed before any arm
ran. Everything else is read **after** the ranking, to understand it rather than to change
it.

| Experiment | Ranked by | Floor that must read true first | Secondary criteria, read after |
|---|---|---|---|
| Summarisation · CNN/DM | `coverage` | `lead3` — the first three sentences. A model below it has not earned its inference cost. | `grounding` (did it leave the source?), `length_vs_reference` (did it win by padding?), `concision` |
| Classification · AG News | `correct` | `constant` (always one class, ≈0.25) and `keyword` (~20 regex rules) | `parsed` and `correct_after_repair` — the parser is part of the system; macro-F1 for concentrated blind spots; `confidence` calibration |
| Classification · DBpedia | `correct` | same two | same, plus the **label-noise pass** — on a saturated task the field's consensus errors are the ceiling |
| Extraction · Few-NERD | `f1` | `nothing` (predicts the empty set; must score exactly the empty-gold rate) and `capitalized` (every capitalised run) | `untyped_f1` and `type_penalty` — detection vs labelling; per-type breakdown; consensus type disagreements |
| Retrieval · SciFact | `ndcg_10` | `random` (must score ≈ k/N) and `first_k` (corpus order) | `recall_100` — the pipeline ceiling; the oracle reordering; `unknown_ids` for invention |

**Why each example has floors that are not models.** `nothing`, `random`, `constant` and
`first_k` have predictable scores. They are **calibration checks on the scorer** before
they are baselines on the task: if `nothing` does not score exactly the empty-gold rate,
no other row in the table can be trusted. On Few-NERD this caught a gold entity that the
normaliser deleted (the currency symbol `£`), which moved the floor by 1/280.

---

## Models

### Hosted — 24 arms, 8 vendors × 3 price tiers

Every example runs the same 24, at temperature 0 with reasoning disabled, so a difference
between examples is the **task** and not the configuration. Reached through a
[LiteLLM](https://docs.litellm.ai/) proxy, which routes to [OpenRouter](https://openrouter.ai/).

| arm | alias | upstream model | weights |
|---|---|---|---|
| `anthropic_l` | `eval-opus-5` | [anthropic/claude-opus-5](https://openrouter.ai/anthropic/claude-opus-5) | proprietary |
| `anthropic_m` | `eval-claude-sonnet` | [anthropic/claude-sonnet-5](https://openrouter.ai/anthropic/claude-sonnet-5) | proprietary |
| `anthropic_s` | `eval-claude-haiku` | [anthropic/claude-haiku-4.5](https://openrouter.ai/anthropic/claude-haiku-4.5) | proprietary |
| `openai_l` | `eval-gpt-6sol` | [openai/gpt-6-sol](https://openrouter.ai/openai/gpt-6-sol) | proprietary |
| `openai_m` | `eval-gpt-55` | [openai/gpt-5.5](https://openrouter.ai/openai/gpt-5.5) | proprietary |
| `openai_s` | `eval-gpt-mini` | [openai/gpt-5.4-mini](https://openrouter.ai/openai/gpt-5.4-mini) | proprietary |
| `deepseek_l` | `eval-deepseek-pro` | [deepseek/deepseek-v4-pro](https://openrouter.ai/deepseek/deepseek-v4-pro) | **open** · MIT |
| `deepseek_m` | `eval-deepseek-41flash` | [deepseek/deepseek-v4.1-flash](https://openrouter.ai/deepseek/deepseek-v4.1-flash) | **open** · MIT |
| `deepseek_s` | `eval-deepseek-flash` | [deepseek/deepseek-v4-flash](https://openrouter.ai/deepseek/deepseek-v4-flash) | **open** · MIT |
| `gemma_l` | `eval-gemma-31b` | [google/gemma-4-31b-it](https://openrouter.ai/google/gemma-4-31b-it) | **open** · Apache-2.0 |
| `gemma_m` | `eval-gemma-26b` | [google/gemma-4-26b-a4b-it](https://openrouter.ai/google/gemma-4-26b-a4b-it) | **open** · Apache-2.0 |
| `gemma_s` | `eval-gemma-3-27b` | [google/gemma-3-27b-it](https://openrouter.ai/google/gemma-3-27b-it) | **open** · Gemma, gated |
| `llama_l` | `eval-llama-maverick` | [meta-llama/llama-4-maverick](https://openrouter.ai/meta-llama/llama-4-maverick) | **open** · Llama, gated |
| `llama_m` | `eval-llama-70b` | [meta-llama/llama-3.3-70b-instruct](https://openrouter.ai/meta-llama/llama-3.3-70b-instruct) | **open** · Llama 3.3, gated |
| `llama_s` | `eval-llama-scout` | [meta-llama/llama-4-scout](https://openrouter.ai/meta-llama/llama-4-scout) | **open** · Llama, gated |
| `mistral_l` | `eval-mistral-large` | [mistralai/mistral-large-2512](https://openrouter.ai/mistralai/mistral-large-2512) | **open** · Apache-2.0 |
| `mistral_m` | `eval-mistral-medium` | [mistralai/mistral-medium-3.1](https://openrouter.ai/mistralai/mistral-medium-3.1) | proprietary |
| `mistral_s` | `eval-mistral-small` | [mistralai/mistral-small-3.2-24b-instruct](https://openrouter.ai/mistralai/mistral-small-3.2-24b-instruct) | **open** · Apache-2.0 |
| `qwen_l` | `eval-qwen-3max` | [qwen/qwen3-max](https://openrouter.ai/qwen/qwen3-max) | proprietary |
| `qwen_m` | `eval-qwen-37plus` | [qwen/qwen3.7-plus](https://openrouter.ai/qwen/qwen3.7-plus) | proprietary |
| `qwen_s` | `eval-qwen-flash` | [qwen/qwen3.8-flash](https://openrouter.ai/qwen/qwen3.8-flash) | proprietary |
| `glm_l` | `eval-glm-5` | [z-ai/glm-5](https://openrouter.ai/z-ai/glm-5) | **open** · MIT |
| `glm_m` | `eval-glm-46` | [z-ai/glm-4.6](https://openrouter.ai/z-ai/glm-4.6) | **open** · MIT |
| `glm_s` | `eval-glm-45-air` | [z-ai/glm-4.5-air](https://openrouter.ai/z-ai/glm-4.5-air) | **open** · MIT |

> **14 of these 24 have downloadable weights and could be self-hosted.** Verified on
> 2026-09-29 against the HuggingFace API. Ten are unrestricted (MIT / Apache-2.0); four
> are gated behind licence acceptance and carry use conditions. An earlier version said
> 13 and inferred openness from OpenRouter's endpoint count — *one provider implies
> closed* — which is **not a valid test**: `mistral_l` is served only by Mistral and its
> weights are on HuggingFace under Apache-2.0. What that is worth is measured in
> [`REPORT_SYNTHESIS.md` §0](../research/REPORT_SYNTHESIS.md) — **no proprietary model
> separated from the best open-weight model in any of the five experiments.**

> **A hosted model has no verifiable identity.** The fingerprint records
> `identity_declared: true` and `revision_source: unavailable` — we record the alias we
> asked for, not proof of what answered. A provider can change weights behind a name
> without notice. This is the single largest unverifiable assumption in the repo, and it
> is why the local arms record a `revision` and a weight-file size and the hosted ones
> cannot.

### Local — downloaded weights, pinned by revision

Every one is loaded from [HuggingFace](https://huggingface.co/) and its commit SHA and
`model.safetensors` byte size are recorded in the run fingerprint, so a silent upstream
change is detectable.

| arm | model | size | revision | what it is |
|---|---|---|---|---|
| `bart_l` | [`facebook/bart-large-cnn`](https://huggingface.co/facebook/bart-large-cnn) | 1.6 GB | `37f520fa929c` | BART fine-tuned on CNN/DailyMail — the in-distribution summariser |
| `bart_mnli` | [`facebook/bart-large-mnli`](https://huggingface.co/facebook/bart-large-mnli) | 1.6 GB | `d7645e127eaf` | Zero-shot classification by [NLI entailment](https://arxiv.org/abs/1909.00161) — no training on the task |
| `bert_mini` | [`mrm8488/bert-mini-finetuned-age_news-classification`](https://huggingface.co/mrm8488/bert-mini-finetuned-age_news-classification) | 44 MB | `e94b474cce6f` | Fine-tuned on AG News. The 44 MB model that beat 24 LLMs |
| `span_marker` | [`guishe/span-marker-generic-ner-v1-fewnerd-fine-super`](https://huggingface.co/guishe/span-marker-generic-ner-v1-fewnerd-fine-super) | 476 MB | `f836dfa9b6b0` | [SpanMarker](https://github.com/tomaarsen/SpanMarkerNER) fine-tuned **on Few-NERD**, predicting the 66 fine types mapped down to 8 |
| `gliner` | [`urchade/gliner_medium-v2.1`](https://huggingface.co/urchade/gliner_medium-v2.1) | 745 MB | `40ec419335d0` | [GLiNER](https://arxiv.org/abs/2311.08526) — zero-shot NER where the **caller supplies the label set**. The matched control for `span_marker` |
| `minilm` | [`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | 91 MB | `1110a243fdf4` | General [sentence-similarity](https://www.sbert.net/) encoder, symmetric, no prefix |
| `mpnet` | [`sentence-transformers/all-mpnet-base-v2`](https://huggingface.co/sentence-transformers/all-mpnet-base-v2) | 438 MB | `e8c3b32edf54` | The larger general encoder. Same recipe as MiniLM, so the pair isolates **size** |
| `bge_small` | [`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5) | 133 MB | `5c38ec7c405e` | Trained **for retrieval**, with an asymmetric query instruction. Pairs with MiniLM to isolate **training objective** |
| `e5_base` | [`intfloat/e5-base-v2`](https://huggingface.co/intfloat/e5-base-v2) | 438 MB | `f52bf8ec8c71` | Retrieval-trained, asymmetric on **both** sides (`query: ` / `passage: `) |

**Blocked — checkpoints this machine cannot load.** Below torch 2.6 `transformers` refuses
to `torch.load` a pickle ([CVE-2025-32434](https://github.com/advisories/GHSA-53q9-r3pm-6pq6)),
and there is no Intel-Mac torch wheel above 2.2.2. These ship no `safetensors`:
[`sshleifer/distilbart-cnn-12-6`](https://huggingface.co/sshleifer/distilbart-cnn-12-6),
[`sshleifer/distilbart-cnn-6-6`](https://huggingface.co/sshleifer/distilbart-cnn-6-6),
[`facebook/bart-large-xsum`](https://huggingface.co/facebook/bart-large-xsum),
[`textattack/bert-base-uncased-ag-news`](https://huggingface.co/textattack/bert-base-uncased-ag-news),
[`fabriceyhc/bert-base-uncased-ag_news`](https://huggingface.co/fabriceyhc/bert-base-uncased-ag_news),
[`fabriceyhc/bert-base-uncased-dbpedia_14`](https://huggingface.co/fabriceyhc/bert-base-uncased-dbpedia_14).

### Non-model arms

Not baselines to be beaten — **calibration checks on the scorer**, with predictable scores.

| arm | what it does | what it must score |
|---|---|---|
| `lead3` | first three sentences of the article | the extractive floor for summarisation |
| `constant` | always the same class | ≈ 1/num_classes |
| `keyword` | ~20 hand-written regex rules | whatever rules alone are worth |
| `nothing` | predicts the empty set | **exactly** the empty-gold rate |
| `capitalized` | every capitalised run, minus a stoplist | high untyped recall, near-random types |
| `random` | a seeded permutation of the corpus | ≈ k/N for recall@k |
| `first_k` | the corpus in id order | ≈ 0 |
| `bm25` | [Okapi BM25](https://en.wikipedia.org/wiki/Okapi_BM25) via [`rank_bm25`](https://github.com/dorianbrown/rank_bm25) | not a strawman — it beats weak dense models on SciFact |

---

## Datasets

**None is committed.** Each example ships a `fetch.py` download recipe; the slice lands on
your machine and is gitignored. Dataset identity travels as `items_sha256` (and
`corpus_sha256` for retrieval), not as bytes in the repo.

| Dataset | Source | Licence | Used for |
|---|---|---|---|
| CNN/DailyMail | [`abisee/cnn_dailymail`](https://huggingface.co/datasets/abisee/cnn_dailymail) | Apache-2.0 | 200 news articles + human highlights. Corpus from [Hermann et al. 2015](https://arxiv.org/abs/1506.03340); adapted for summarisation by [Nallapati et al. 2016](https://arxiv.org/abs/1602.06023) |
| AG News | [`fancyzhx/ag_news`](https://huggingface.co/datasets/fancyzhx/ag_news) | **`unknown`** on the card; the corpus description says non-commercial research use | 200 snippets, 4 topics ([paper](https://arxiv.org/abs/1509.01626)) |
| DBpedia-14 | [`fancyzhx/dbpedia_14`](https://huggingface.co/datasets/fancyzhx/dbpedia_14) | CC-BY-SA 3.0 + GFDL, inherited from Wikipedia | 280 abstracts, 14 ontology classes |
| Few-NERD | [`DFKI-SLT/few-nerd`](https://huggingface.co/datasets/DFKI-SLT/few-nerd) | **CC BY-SA 4.0** — the cleanest of the five | 280 sentences, 8 coarse entity types ([paper](https://aclanthology.org/2021.acl-long.248/)) |
| BEIR SciFact | [`BeIR/scifact`](https://huggingface.co/datasets/BeIR/scifact) + [`BeIR/scifact-qrels`](https://huggingface.co/datasets/BeIR/scifact-qrels) | CC BY-SA 4.0 | 200 claims over a 5,183-abstract corpus ([BEIR](https://arxiv.org/abs/2104.08663), [SciFact](https://aclanthology.org/2020.emnlp-main.609/)) |

> **Licence is a selection criterion here, not a footnote.** Few-NERD was chosen over
> WNUT-2017 — which is closer to noisy podcast speech, the actual application — purely
> because WNUT is licensed `other`. That is relevance given up for a clean grant, and the
> NER report says so.

---

## Statistical tests

Ranking arms by a mean is not a result until you know which gaps survive noise.

| Tool | What it answers | Method |
|---|---|---|
| `family_test.py` | Is arm A better than each of a **pre-declared** family? | [Sign-flip permutation](https://en.wikipedia.org/wiki/Resampling_(statistics)#Permutation_tests) on paired per-item scores, then [Holm step-down](https://en.wikipedia.org/wiki/Holm%E2%80%93Bonferroni_method) over the whole family. The family is declared *before* p-values are read — otherwise you are choosing the comparison after seeing the answer. |
| `holdout_significance.py` | Does the ordering hold on items a smaller slice never contained? | [Friedman-style](https://en.wikipedia.org/wiki/Friedman_test) permutation on within-item ranks, plus a [Nemenyi](https://en.wikipedia.org/wiki/Nemenyi_test) critical difference. |
| `rank_stability.py` | How many items before the leaderboard stops moving? | Two **disjoint** halves, ranked independently, correlated by [Spearman's ρ](https://en.wikipedia.org/wiki/Spearman%27s_rank_correlation_coefficient) with **midranks for ties**. Neither half is treated as truth. |
| `bootstrap_test.py` | Confidence interval for macro-F1, which has no per-item value | Paired percentile [bootstrap](https://en.wikipedia.org/wiki/Bootstrapping_(statistics)). **Documented as anti-conservative** — 11 separations against the exact test's 8. |
| `rescore.py` | What would this look like under a different scorer? | Recomputes from stored outputs. **No API calls, no money.** This is why a scorer bug costs nothing to fix. |

**Why Holm and not Bonferroni:** Holm is uniformly more powerful and controls the same
family-wise error rate. **Why permutation and not a t-test:** these per-item scores are not
normal — `correct` is Bernoulli, `ndcg_10` on a single-relevant query takes one of eleven
values — and permutation assumes only exchangeability under the null.

---

## Further reading

- [BEIR](https://arxiv.org/abs/2104.08663) — the benchmark design this repo's retrieval example borrows from
- [HELM](https://crfm.stanford.edu/helm/) — multi-metric, multi-scenario LLM evaluation at scale
- [*A Careful Examination of Large Language Model Performance on Grade School Arithmetic*](https://arxiv.org/abs/2405.00332) — builds a fresh GSM8k-equivalent to measure how much of a benchmark score is overfitting to the benchmark. The reason this repo freezes slices and records `items_sha256`
- [`../research/NOTES.md`](../research/NOTES.md) — this repo's own append-only journal, including every retraction

---

## Terminology

Fixed names, used the same way in every document here. Where a table's first column is
"experiment", every cell in it reads **`Task · Dataset`** — mixing a task name in one row
with a dataset name in the next is what this convention exists to stop.

| canonical label | task | dataset | report |
|---|---|---|---|
| **Summarisation · CNN/DM** | summarisation | [CNN/DailyMail](https://huggingface.co/datasets/abisee/cnn_dailymail) | [REPORT_SUMMARIZATION](../research/REPORT_SUMMARIZATION.md) |
| **Classification · AG News** | classification | [AG News](https://huggingface.co/datasets/fancyzhx/ag_news) | [REPORT_CLASSIFICATION](../research/REPORT_CLASSIFICATION.md) |
| **Classification · DBpedia** | classification | [DBpedia-14](https://huggingface.co/datasets/fancyzhx/dbpedia_14) | [REPORT_CLASSIFICATION](../research/REPORT_CLASSIFICATION.md) |
| **Extraction · Few-NERD** | extraction (NER) | [Few-NERD](https://huggingface.co/datasets/DFKI-SLT/few-nerd) | [REPORT_NER](../research/REPORT_NER.md) |
| **Retrieval · SciFact** | retrieval | [BEIR SciFact](https://huggingface.co/datasets/BeIR/scifact) | [REPORT_RETRIEVAL](../research/REPORT_RETRIEVAL.md) |

Two experiments share the *classification* task and differ only in dataset, which is why
the dataset is never optional in these labels.

### Other fixed terms

| term | means | not |
|---|---|---|
| **arm** | one configuration under test — a model *plus* its prompt, parameters and parsing | "model", which is only part of an arm |
| **experiment** | one task on one dataset, with its own report section | "dataset" or "task" alone |
| **dev slice / measurement slice** | the small tuning set / the frozen set results are reported on | "train/test", which implies we trained something |
| **floor** | an arm whose score is predictable in advance (`nothing`, `random`, `constant`) | "baseline" — these are scorer calibration checks first |
| **separated** | the difference survives Holm step-down at α = 0.05 | "better", which only needs a point estimate |
| **billed** | what the provider charged (`usage.cost`) | "cost", which used to mean a price-table estimate |
| **local ML** / **open-weight** / **proprietary** | the three tiers in [REPORT_SYNTHESIS §0](../research/REPORT_SYNTHESIS.md) | "free vs paid", which conflates tiers 1 and 2 |

### Spelling

**Prose uses British `-isation`** (summarisation, normalisation, normaliser) — the
majority form across this repo. **Identifiers keep whatever they were named**, because
renaming them breaks paths and hashes: `REPORT_SUMMARIZATION.md`,
`examples/summarization-cnn-dailymail/`, `normalizer_sha256`, `normalize()`. The two
spellings coexisting in one sentence is expected when one of them is code.

---

## Credits

Everything below is somebody else's work. Versions are the ones actually recorded in the
run fingerprints, not the ones a lockfile would prefer.

### Datasets

| Dataset | Authors | Licence |
|---|---|---|
| [CNN/DailyMail](https://huggingface.co/datasets/abisee/cnn_dailymail) | [Hermann et al. (2015)](https://arxiv.org/abs/1506.03340); summarisation framing by [Nallapati et al. (2016)](https://arxiv.org/abs/1602.06023); split by [See et al. (2017)](https://arxiv.org/abs/1704.04368) | Apache-2.0 |
| [AG News](https://huggingface.co/datasets/fancyzhx/ag_news) | [Zhang, Zhao & LeCun (2015)](https://arxiv.org/abs/1509.01626); corpus by ComeToMyHead | card says `unknown`; corpus states non-commercial research use |
| [DBpedia-14](https://huggingface.co/datasets/fancyzhx/dbpedia_14) | [Lehmann et al., DBpedia](https://www.semantic-web-journal.net/content/dbpedia-large-scale-multilingual-knowledge-base-extracted-wikipedia); split by Zhang et al. (2015) | CC-BY-SA 3.0 + GFDL |
| [Few-NERD](https://huggingface.co/datasets/DFKI-SLT/few-nerd) | [Ding et al. (2021)](https://aclanthology.org/2021.acl-long.248/) | CC BY-SA 4.0 |
| [BEIR SciFact](https://huggingface.co/datasets/BeIR/scifact) | [Wadden et al. (2020)](https://aclanthology.org/2020.emnlp-main.609/); BEIR by [Thakur et al. (2021)](https://arxiv.org/abs/2104.08663) | CC BY-SA 4.0 |

### Models

Licences below were read from the HuggingFace API on 2026-09-29, not assumed. **Two state
no licence at all**, which is a reuse blocker rather than a permission — follow each link
and check before reusing any of them commercially.

| model | licence |
|---|---|
| [`facebook/bart-large-cnn`](https://huggingface.co/facebook/bart-large-cnn) | MIT |
| [`facebook/bart-large-mnli`](https://huggingface.co/facebook/bart-large-mnli) | MIT |
| [`facebook/bart-large-xsum`](https://huggingface.co/facebook/bart-large-xsum) | MIT |
| [`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5) | MIT |
| [`intfloat/e5-base-v2`](https://huggingface.co/intfloat/e5-base-v2) | MIT |
| [`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | Apache-2.0 |
| [`sentence-transformers/all-mpnet-base-v2`](https://huggingface.co/sentence-transformers/all-mpnet-base-v2) | Apache-2.0 |
| [`urchade/gliner_medium-v2.1`](https://huggingface.co/urchade/gliner_medium-v2.1) | Apache-2.0 |
| [`sshleifer/distilbart-cnn-12-6`](https://huggingface.co/sshleifer/distilbart-cnn-12-6) | Apache-2.0 |
| [`sshleifer/distilbart-cnn-6-6`](https://huggingface.co/sshleifer/distilbart-cnn-6-6) | Apache-2.0 |
| [`fabriceyhc/bert-base-uncased-ag_news`](https://huggingface.co/fabriceyhc/bert-base-uncased-ag_news) | Apache-2.0 |
| [`fabriceyhc/bert-base-uncased-dbpedia_14`](https://huggingface.co/fabriceyhc/bert-base-uncased-dbpedia_14) | Apache-2.0 |
| [`guishe/span-marker-generic-ner-v1-fewnerd-fine-super`](https://huggingface.co/guishe/span-marker-generic-ner-v1-fewnerd-fine-super) | **CC-BY-SA-4.0** |
| [`mrm8488/bert-mini-finetuned-age_news-classification`](https://huggingface.co/mrm8488/bert-mini-finetuned-age_news-classification) | **none stated** |
| [`textattack/bert-base-uncased-ag-news`](https://huggingface.co/textattack/bert-base-uncased-ag-news) | **none stated** |

An earlier version of this line claimed the set was "variously MIT, Apache-2.0 and
CC-BY-NC-4.0". No model here is CC-BY-NC-4.0; one is CC-BY-SA-4.0 and two state nothing.
That was asserted rather than checked, and it is the same error the paper citations had.

[`facebook/bart-large-cnn`](https://huggingface.co/facebook/bart-large-cnn) ·
[`facebook/bart-large-mnli`](https://huggingface.co/facebook/bart-large-mnli) ·
[`mrm8488/bert-mini-finetuned-age_news-classification`](https://huggingface.co/mrm8488/bert-mini-finetuned-age_news-classification) ·
[`guishe/span-marker-generic-ner-v1-fewnerd-fine-super`](https://huggingface.co/guishe/span-marker-generic-ner-v1-fewnerd-fine-super) ·
[`urchade/gliner_medium-v2.1`](https://huggingface.co/urchade/gliner_medium-v2.1) ·
[`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) ·
[`sentence-transformers/all-mpnet-base-v2`](https://huggingface.co/sentence-transformers/all-mpnet-base-v2) ·
[`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5) ·
[`intfloat/e5-base-v2`](https://huggingface.co/intfloat/e5-base-v2)

Underlying architectures: [BART](https://arxiv.org/abs/1910.13461),
[BERT](https://arxiv.org/abs/1810.04805), [MPNet](https://arxiv.org/abs/2004.09297),
[DeBERTa-v3](https://arxiv.org/abs/2111.09543) (GLiNER's encoder),
[Sentence-BERT](https://arxiv.org/abs/1908.10084),
[E5](https://arxiv.org/abs/2212.03533), [BGE, in *C-Pack*](https://arxiv.org/abs/2309.07597),
[GLiNER](https://arxiv.org/abs/2311.08526), [SpanMarker](https://github.com/tomaarsen/SpanMarkerNER).

### Software

| Package | Version used | Licence |
|---|---|---|
| [transformers](https://github.com/huggingface/transformers) | 4.55.4 | Apache-2.0 |
| [torch](https://github.com/pytorch/pytorch) | 2.2.2 | BSD-3-Clause |
| [sentence-transformers](https://github.com/huggingface/sentence-transformers) | 3.4.1 | Apache-2.0 |
| [datasets](https://github.com/huggingface/datasets) | 5.0.1 | Apache-2.0 |
| [rouge-score](https://github.com/google-research/google-research/tree/master/rouge) | 0.1.2 | Apache-2.0 |
| [rank_bm25](https://github.com/dorianbrown/rank_bm25) | 0.2.2 | Apache-2.0 |
| [gliner](https://github.com/urchade/GLiNER) | ≥0.2.13 | Apache-2.0 |
| [span-marker](https://github.com/tomaarsen/SpanMarkerNER) | ≥1.5 | Apache-2.0 |
| [scikit-learn](https://scikit-learn.org/) | 1.9.1 | BSD-3-Clause |
| [numpy](https://numpy.org/) | 1.26.4 | BSD-3-Clause |
| [openai](https://github.com/openai/openai-python) (client only) | 2.48.0 / 3.19.2 | Apache-2.0 |
| [LiteLLM](https://github.com/BerriAI/litellm) | proxy | MIT |
| [uv](https://github.com/astral-sh/uv) | env management | Apache-2.0 / MIT |

### Infrastructure

Hosted inference is routed through [OpenRouter](https://openrouter.ai/), which resells
capacity from Anthropic, OpenAI, Google, Meta, Mistral, DeepSeek, Alibaba (Qwen), Z.ai and
their serving partners (Novita, DeepInfra, Nebius, Parasail and others). Dataset slices are
fetched through the [HuggingFace datasets-server](https://huggingface.co/docs/datasets-server).

### Method

The statistical approach follows standard practice rather than inventing any: Holm
step-down (Holm 1979 (*A Simple Sequentially Rejective Multiple Test Procedure*, Scandinavian Journal of Statistics 6(2):65–70)), Friedman and Nemenyi for
multiple classifiers over multiple datasets
([Demšar 2006](https://www.jmlr.org/papers/v7/demsar06a.html)), and permutation tests as
described in [Dror et al., *The Hitchhiker's Guide to Testing Statistical Significance in
NLP*](https://aclanthology.org/P18-1128/).

**No corpus, no model weight, no paper and no provider output is redistributed by this
repository.** Every example ships a download recipe instead, and
[`papers/README.md`](papers/README.md) records the licence of each cited work — twelve of
the twenty-four may be mirrored, twelve may not, and the split follows publisher policy
rather than importance.

**Every citation above was verified on 2026-09-29** by fetching it and comparing the real
title to the claim made about it. That check found four errors in the first draft: a
fabricated paper title, a GitHub advisory ID pointing at an unrelated NuGet CVE, a dataset
credited to the wrong authors, and a moved repository. One citation — Holm (1979) — could
**not** be verified programmatically and is therefore given as a full text reference rather
than a link.
