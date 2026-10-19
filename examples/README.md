# The experiments

The harness, pointed at 24 LLMs, small fine-tuned models and baselines. On the site:
[the experiments](https://evals.humancopilot.eu/experiments.html).

Six experiments, five metric shapes, one harness. Each exists because it **breaks
something the previous one did not** — the harness grew by meeting a task it could not
already express, and every example's most interesting output is the defect it exposed.

None of them ships a corpus. Each ships a `fetch.py` download recipe, and the data is
gitignored.

> ### Start here
>
> **To rerun any of these:** `make list`, then `make plan EXP=<experiment>` from the
> repository root — the walkthrough is [`../docs/REPRODUCE.md`](../docs/REPRODUCE.md).
>
> **[`../docs/REFERENCE.md`](../docs/REFERENCE.md)** — the encyclopedia. Every metric
> explained with a link to its paper, every model with a link to its weights, every
> dataset with its licence, and every statistical test with the reason it was chosen.
> Read it once and the six examples stop needing footnotes.
>
> Each example then has **three** documents:
>
> | file | answers |
> |---|---|
> | `README.md` | **how** — commands, arms, what the data licence permits |
> | `METHOD.md` | **why** — why this dataset, why these arms, why these criteria, and what each choice gives up |
> | the report in [`../research/`](../research) | **what happened** — results, statistics, corrections, and what was *not* covered |

| Example | Task | Shape of the answer | What it broke in the harness | Method (why) | Report |
|---|---|---|---|---|---|
| [`summarization-cnn-dailymail`](summarization-cnn-dailymail) | summarise a news article | one text vs one text, **continuous** | nothing — it *is* the baseline the others are measured against | [METHOD](summarization-cnn-dailymail/METHOD.md) | [report](../research/REPORT_SUMMARIZATION.md) |
| [`classification-ag-news`](classification-ag-news) | 4-way topic label | one label vs one label, **0 or 1** | a discrete metric ties, and the duplicate-run check flagged honest ties as copies | [METHOD](classification-ag-news/METHOD.md) | [report](../research/REPORT_CLASSIFICATION.md) |
| [`classification-dbpedia-14`](classification-dbpedia-14) | 14-way ontology label | same, but **saturated** | rank-stability measured the alphabet when most arms tie | [METHOD](classification-dbpedia-14/METHOD.md) | [report](../research/REPORT_CLASSIFICATION.md) |
| [`ner-few-nerd`](ner-few-nerd) | named entities + types | **a set** vs a set, order irrelevant | an unreadable answer scored 1.0, and no fingerprint covered the scorer | [METHOD](ner-few-nerd/METHOD.md) | [report](../research/REPORT_NER.md) |
| [`retrieval-scifact`](retrieval-scifact) | find the abstract supporting a claim | **a ranked list** over a 5,183-doc corpus | the corpus is not the items, so nothing in the fingerprint identified it | [METHOD](retrieval-scifact/METHOD.md) | [report](../research/REPORT_RETRIEVAL.md) |
| [`summeval-judging`](summeval-judging) | grade 16 summaries of an article like an expert would | **a vector of judgements**, scored by **rank correlation** with experts | the first experiment whose answer is a judgement of other systems' outputs, and whose arms include this repository's own metrics | [METHOD](summeval-judging/METHOD.md) | [report](../research/REPORT_SUMMEVAL.md) |

Shared scoring code lives in [`_shared/`](_shared): `classification.py`, `extraction.py`,
`retrieval.py`, plus `hf_identity.py` for pinning local model weights.

---

## What all six agree on

**[`../research/REPORT_SYNTHESIS.md`](../research/REPORT_SYNTHESIS.md)** — the
cross-cutting report. Seven findings, each tested in every experiment that could test it
and computed from the stored runs rather than quoted: the dearest arm is never first (6/6),
five of six leaderboard tops are statistical ties (not separable at 100–280 items, which
is not the same as equal), a pilot with ρ ≈ 0.8 picked the wrong
winner three times in the five experiments that ran one, and the scoring code moved single
arms further than most model swaps did.

It also answers the deployment question directly. **Every experiment has a $0 answer**:
the best model fine-tuned on each dataset ranked first in 3 of 4 and third-equal (not
separable from the leader) on saturated DBpedia, a
proprietary model never separated from the best open-weight one in any of the six, and
**on four of the six tasks the best model that fits a 64 GB machine scores the same as the
unlimited-hardware answer** (two at int8 or int4, unmeasured; provider-served scores). Every task-specific winner is under 2 GB and needs no GPU. On SummEval, even
a free evaluator trained for the task sits far below the judges — the best judges reach 93% of a
human expert's agreement (the best of 24, on the same articles), UniEval 64% — so the LLM earns its bill, and the $0 answer is an open-weight LLM judge.

## What each one actually found

### Summarisation — price and quality were uncorrelated here
24 hosted models over 200 news articles — **all of them CNN's** (the first 200 test rows; the
benchmark is 91% DailyMail). The dearest arm, at **143× the price** of the
cheapest, ranks **18th of 29** (15th of the 24 hosted). Two *independent* 100-article evals of the same models
agree at only **ρ = 0.79**, and at 20 articles at **ρ = 0.44** (29 arms). Price and
quality were uncorrelated across the 24 hosted arms (r −0.07, 95% interval −0.46 to +0.34),
which does not exclude a moderate effect.

Later, ML arms were added and BART took the lead — by **0.00008** over the best LLM across
200 articles. Its lead at n=20 had been 0.0737. That illustrates the winner's curse, and it turns up twice: in the leaderboard, and in
`P(both halves crown the same arm)` collapsing to 0.01.

Then the control: the same BART fine-tuned on **XSum** instead of CNN/DailyMail finishes
**last of 29** on `coverage` — below LEAD-3. BART's level with the best paid arm is
consistent with this corpus's house style, learned; the XSum control also decodes shorter,
so it does not isolate style. Its distillations keep most of it at 1.5–1.8× the speed on the same machine (`bart_m`
0.3367 at 4.1 s against `bart_l`'s 6.3 s, not separated from `bart_l`).

On 200 DailyMail articles drawn at random, the five local arms keep every verdict they
had on CNN — the fine-tune still beats LEAD-3 by +0.07, the XSum control is still last.
The hosted arms were not re-run there, so the price findings are about CNN's articles
([REPORT_SUMMARIZATION §3.7](../research/REPORT_SUMMARIZATION.md#37-does-it-hold-outside-cnn-the-dailymail-slice)).

### AG News — small models lead, on a task with headroom — largely on its labels
Three fine-tuned classifiers lead on the point estimate: `bert_base_ta` **0.9600**,
`bert_base_fy` 0.9500, the 44 MB `bert_mini` 0.9450, against a hosted field of
0.835–0.910, LLMs as run here (zero-shot, one prompt, no label definitions). The leader
separates from 26 of 29, not from `anthropic_m` (0.0500 behind); `bert_mini` is not
separated from 11 hosted arms. The lead is concentrated in **17 items the hosted field
mostly gets wrong** — the fine-tunes agree with the gold on 12–14 of them, `anthropic_l` on
none — and on the other 183 there is no difference. Read by one person, about half follow a
learnable AG News convention and half are mislabels: what fine-tuning bought here is
reproducing the corpus's labelling. (The 17 are selected by the LLMs' own errors — see the
report's §3.4.)

The example also found that **the scoring code is a bigger lever than the model choice for
some arms**: the label parser is worth 8.6 accuracy points to `glm_l` on DBpedia, wider than the gap
separating most of the field.

### DBpedia-14 — the same experiment, the opposite regime
Deliberately paired with AG News, and **they should not be read one at a time.** Here the
task is saturated: the leader separated from only **8 of 27**, and the top eleven arms are
one group across a **115× price range**. The fine-tuned classifier — blocked for three days
by a pickle checkpoint, run on 2026-09-30 — lands *inside* that group at 0.9857, $0:
where there is no headroom, training buys a tie, not a win.

Both corpora carry systematic label noise, and on DBpedia it is the size of the signal —
the top eleven are separated by four items, three of which 24–25 of the 26 learned arms
dispute because the gold label is wrong.

### Few-NERD — task-specific training, against a zero-shot control
A 499 MB span tagger fine-tuned on the corpus beat all 24 hosted LLMs as run here
(zero-shot, bare type names) and separated from **all 27 other arms** — the one
separated win in the repo. But **57% of its margin over `openai_m` is one entity
type**, `other` (30–57% across the 24 hosted arms), which the prompt never defined. On
`person`, three of the 24 hosted arms edge it, by at most 0.0067 (untested).

A zero-shot control (`gliner`, a different architecture, never trained on Few-NERD) scores
**0.0000** on `other`, having predicted the label 3 times. And 34 of 768 gold types are
rejected by at least 80% of the 26 learned arms; resolving them moves every hosted arm
~+0.03 and the fine-tuned model +0.006, so **up to 38% of its lead over `openai_m` is
agreement with the annotation** — an upper bound, since the arms being scored cast the vote.

### SciFact — pipelines have a ceiling they did not choose
The leading LLM reranker cannot be separated from eleven or twelve other arms (a Holm boundary): ten rerankers **and two
free local encoders**, among the twelve cheapest hosted LLMs as run here. `e5_base`
(0.7191, $0, CPU) is not separated from any of the twelve, and trails the best by 0.0246.

A reranker cannot rank a document its first stage never returned, so the ceiling analysis
produced a **prediction registered before the arm existed**: swapping only the first stage
should move the pipeline from 0.74 to 0.786–0.797. Measured: **0.7891** for `glm_s`, inside
the range; `qwen_s` landed outside it (0.7713 under the corrected parser). One of two.

### SummEval — LLM judges beat a free evaluator trained for the task
The 24 hosted models as **judges**, scoring 16 summaries per article on four dimensions,
graded by how well they order the summaries the way three experts did (Kendall τ-b). The
best free scorer is UniEval, a T5 evaluator trained for these four dimensions: τ **0.3717**
on its own published inputs, against `openai_l`'s **0.5398**. 23 of the 24 judges are
separated from, and ahead of, it; the weakest, `llama_s`, cannot be told apart from it.
BARTScore, a model fine-tuned on this corpus to write summaries, reaches **0.2562**, below
every judge. The leader cannot be separated from five other judges, and `gemma_l` — open weights, $0.0278 for all 100
articles — sits 0.0013 behind the leader. Scored against the mean of two experts, as one
expert is against the other two, the best judges reach 93% of a human's agreement
(interval 89–97%, the best of 24 chosen on the same articles), UniEval 64%, BARTScore 44%.

It also measures the instrument: ROUGE agrees with the experts at τ 0.14–0.16, and this
repository's own `coverage` at **0.1011**, below ROUGE-1. One model could not run as
planned: `qwen_l`'s is no longer served, so `qwen37max` stands in
([REPORT_SUMMEVAL](../research/REPORT_SUMMEVAL.md)).

---

## The pattern across all six

**At the top of a field, the dearest model did not win, and the leader could not be told
apart from a group of others, most of them cheaper.** In five of the six examples the leader cannot be statistically separated
(Holm step-down, α = 0.05) from a group of other arms — and that group spans a large price
range. Few-NERD is the exception: it has a clear winner, and the same tie appears one rank
down.

| experiment | leader | arms not separated from the leader | price ratio: dearest arm ÷ cheapest paid arm not separated from the leader |
|---|---|---|---|
| Summarisation · CNN/DM | `bart_l` ($0) | 15 of 28 — 13 paid, plus both distilled BARTs ($0) | 143× |
| Classification · AG News | `bert_base_ta` ($0) | 3 of 29 — two other fine-tunes ($0) and `anthropic_m` | 2.5× |
| Classification · DBpedia | `qwen_m` | 19 of 27 — one of them the $0 fine-tune | 115× |
| Extraction · Few-NERD | `span_marker` ($0) | **none** — separated from all 27 | no tie at the top; the 8 hosted arms tied for 2nd span 78× |
| Retrieval · SciFact | `glm_s` | 11–12 of 18 (the count sits on a Holm boundary) — **2 of them free** encoders | 7.6× (billed) |
| Judging · SummEval | `openai_l` | 5 of 32 — all hosted judges; every free scorer is separated below them | 72× |

Counts and ratios are from each experiment's report; "dearest" is the most expensive arm in
the whole experiment, which is not always inside the group.

And every example before SummEval found something wrong with the instrument before it found
anything about the models. The append-only journal, [`../research/internal/NOTES.md`](../research/internal/NOTES.md), is the
record of that — including the retractions.

---

## Running one

```bash
cd examples/<name>
uv sync --extra local      # --extra local pulls the local ML arms; plain `uv sync` does not
uv run fetch.py --n <N>
cd ../../harness
make dataset-create DATASET_ID=<id> ARGS='--source-dir data/sources/<id>'
make dataset-materialize DATASET_ID=<id>
for f in ../examples/<name>/configs/arm_*_n200.yaml; do
  ../examples/<name>/.venv/bin/python scripts/experiment_run.py --config "$f"
done
```

Each example's own README has the exact commands, its arms, and what its data licence
permits. Costs are what the provider billed (`usage.cost`), not a price table — see
[`REPORT_RETRIEVAL.md`](../research/REPORT_RETRIEVAL.md) §7 for why that distinction
cost this repo four reports' worth of corrections.

## Unfinished work

Every example has a handover for what was not run and why, in
[`../research/`](../research). What remains is five frontier rerankers on SciFact, about
$12 against the retrieval sweep's $1.94 billed, and the four hosted summarisation arms on
the DailyMail slice. The rate-limited NER arm ran on 2026-10-01, and the six local ML arms
that needed a machine able to load pickle checkpoints ran on 2026-09-30. SummEval's free
trained evaluator, UniEval, ran on 2026-10-18.

---

## Credits

Every dataset, model, paper and library used across the six examples is credited with its
licence in **[`../docs/REFERENCE.md#credits`](../docs/REFERENCE.md#credits)**, and again
per-experiment at the bottom of each `METHOD.md`.

Every cited paper's redistribution licence is recorded in
[`../docs/papers/README.md`](../docs/papers/README.md), with a fetcher for the thirteen
mirrored there. All citations but one were verified by fetching them and comparing titles; Holm (1979) could not be fetched and is given as a full reference.

**No corpus, model weights or papers are redistributed here.** Each example ships a
download recipe, and dataset identity travels as a content hash (`items_sha256`,
`corpus_sha256`) recorded inside every run. **The models' outputs are committed** — every
run's `predictions.jsonl` and `outputs/` — because they are the evidence every score is
recomputed from (`make rescore`). For summarisation that means model-written summaries of
the CNN/DailyMail articles, which quote and paraphrase them; the corpus is Apache-2.0 per
its dataset card.
