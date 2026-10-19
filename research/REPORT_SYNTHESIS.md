# What six experiments agree on

**Six tasks · five metric shapes · 167 measured arms · $19.07 billed · one harness**

*$19.07 is the 167 arms under `harness/data/runs/`. Including the six paired runs (four
behind the registered prediction, $0.60; two on SummEval's text, $0.13) and the three hosted
repeat runs ($0.43), the repo has spent $20.23. How the count grew, and every figure this
report has corrected, is in [Corrections](#corrections).*

---

## Executive summary

**Choose by task: if you have labels for a fixed taxonomy, fine-tune a small model; if you
rent, take the cheapest arm the leader cannot be separated from, not the dearest; to grade
text, use an LLM judge checked against your own human judgements.**

For entity extraction use `span_marker` (0.7674 against 0.6864 for the best of 24 hosted
LLMs; rented, `gemma_m` at about $32 per 1M items). For AG News use `bert_mini` (44 MB,
0.9450, above every hosted arm on the point estimate; rented, `gemma_m` at $8 per 1M items).
For DBpedia take the cheapest arm at 0.9857: `gemma_m` (about $12 per 1M items), `qwen_s` or
`bert_base_fy`. For summarisation use `bart_l` on a CPU if your text looks like CNN news
(0.3461, 11.0 s an article) or `deepseek_m` for speed ($191 per 1M articles, 0.3460). For
retrieval build `e5_base` first, and add a reranker only if about +0.07 nDCG@10 is worth
about $732 per 1M queries. For judging summaries use `gemma_l` ($278 per 1M articles, within
0.0013 of the leader that costs $6,350). Never `anthropic_l`: the dearest arm in five of the
six experiments, it was never first and was separated below the leader in three.

These picks hold as run here: hosted LLMs zero-shot with one prompt, temperature 0 and
reasoning off, one run per arm, on public benchmarks whose contamination was not measured.
At 100–280 items, "not separated" does not mean equal. Labelling and training cost, and how
a fine-tune does with fewer labels, were not measured.

### Supporting facts

Every figure is as run here and computed from the stored runs; reproduction commands are at
the end. The seven findings, each tested in every experiment that could test it, unpacked in
§1–§7:

| # | finding | evidence |
|---|---|---|
| **1** | **The dearest arm is never first** | `anthropic_l`, the dearest in five of six experiments, ranked 18th of 29 (summarisation), 5th of 30 (AG News), 2nd of 28 (DBpedia), 3rd of 28 (Few-NERD) and 3rd of 33 (SummEval), and was separated below the leader in three (summarisation, AG News, Few-NERD). SciFact had no frontier tier: its dearest, `glm_m`, is the dearest of twelve cheap models (2nd of 19). The dearest beat the cheapest in 5 of 6. |
| **2** | **The top is a group, not a podium** | The leader is separated from 100% (Few-NERD, 27 of 27), 90% (AG News), 84% (SummEval), 46% (summarisation), 33% (SciFact) and 30% (DBpedia) of its opponents. |
| **3** | **Training exposure predicts who wins, not price — with one exception** | The best fine-tune ranked first in three of four experiments that had one and third-equal on DBpedia, two items behind; zero-shot models ranked last among learned arms; a BART trained on XSum finished 29th of 29 on CNN. Exception: on SummEval, UniEval, trained to judge, is separated below 23 of the 24 LLM judges (cause untested). |
| **4** | **A pilot picks the wrong winner** | Pilot ρ was 0.68–0.90 where it can be recomputed, and the pilot's leader was not the full-run leader in 3 of the 5 experiments that ran one. |
| **5** | **Some gold labels are disputed or noisy** | Where anyone checked: Few-NERD 34 of 768 gold types rejected by ≥80% of 26 learned arms; AG News 17 items most hosted arms miss, about half convention and half mislabels on one rater's reading; DBpedia's top eleven are separated by four items, three of them disputed (unadjudicated); SummEval's experts scored 41 of 44 groups of identical summaries differently. Candidates, not proven errors; two corpora were not checked. |
| **6** | **The scorer is a model-sized lever** | Three of eight defects moved one arm further than the gap separating most of the field: DBpedia's label parser (8.6 accuracy points), Few-NERD's unparsed-as-empty rule (+0.0214 f1), SciFact's reasoning flag (0.6124 → 0.6991). |
| **7** | **Metric shape decides which diagnostics can be read** | On DBpedia at n = 10, 19.9 of 28 arms tied, so rank correlation measured arm names; the same tool is readable on Few-NERD. |

The cross-cutting numbers behind the picks:

| question | answer |
|---|---|
| **What does 10× the money buy?** | −0.4% to +7.4% of the best paid arm's score: a log-linear fit of quality on log10(cost) over the paid arms, slope ÷ best paid score, across vendors rather than an experiment (§8). Steepest on SummEval (+7.4%, r = 0.49); negative on summarisation (−0.4%, r = −0.07). |
| **How much cheaper is the cheapest arm the leader cannot be separated from?** | 143× (summarisation), 115× (DBpedia), 72× (SummEval: `gemma_l`, $278 per 1M articles), 7.6× (SciFact) and 2.5× against the AG News fine-tune's group; no paid arm ties Few-NERD's leader. Renting on AG News, start with `gemma_m` ($8 per 1M items): the paid leader `anthropic_m` ($351) is separated from only 3 of the 23 other hosted arms (§8). |
| **Rent or own?** | 14 of the 24 hosted arms have downloadable weights. The best proprietary arm was never separated from the best open-weight arm in any of the six experiments (`anthropic_l` and `anthropic_m` are separated below `deepseek_m` on summarisation). Every arm's bill at 1M items, summed: $24,187 for the open-weight tier rented, $0 self-hosted; $100,894 for the 10 proprietary arms and `qwen37max` on SummEval, which cannot be self-hosted. |
| **Is there a $0 answer?** | In every experiment: the self-hostable option is the winner in four of six and trails by 0.0071 (DBpedia) and 0.0013 (SummEval), neither resolvable. |
| **What does a 64 GB machine hold?** | At native precision the best model that fits still equals the unlimited-hardware answer on two of six tasks (DBpedia, Few-NERD) and trails by 0.0074 (SciFact) and 0.0200 (AG News), both not separated, and by 0.0205 (summarisation) and 0.0614 (SummEval), both separated. The unlimited-hardware model would fit AG News and SummEval only at int4 or int8, which was not run. At 128 GB five of six answers equal the unlimited one (two only as an unrun int8 or int4 build). Nothing was run on a 64 or 128 GB machine; scores are as the providers served them (§0). |
| **Can one model do everything?** | `glm_m`, the best of the twelve hosted arms that ran all six experiments, sits at the 67th percentile among hosted arms (the share it scores above, ties counted half, averaged over the six; 72nd if ties are counted fully in its favour), where each local model does one task (§0). |
| **How good is an LLM judge?** | The best LLM judges reached 93% of a human expert's agreement (95% interval 89–97%) and the best free scorer, UniEval, 64%. The 93% is the best of 24 chosen on the same articles (92% when chosen on half and scored on the other half). A no-model lookup of which system wrote each summary reaches 63%, so how much of a judge's score is reading rather than recognising the system is not measured. The summaries are 2019-era, reasoning was off, and the judges ranked all 16 summaries in one call where UniEval scores one at a time (REPORT_SUMMEVAL §3.7). |

What the dearest arm in each experiment buys, at **1,000,000 items/month** as billed,
sorted by its bill (highest first). An item is one call: on SummEval that is a whole
article with its 16 summaries, which is why its bills lead the table. The last column is its
score relative to the cheaper option named, so −8.9% means 8.9% below it:

| experiment | dearest arm, $/month at 1M items | its quality vs the cheaper option (relative; − = worse) |
|---|---|---|
| Judging · SummEval | `anthropic_l`, $20,077 | −2.1% vs `openai_l` at $6,350/mo (and `gemma_l`, tied with the leader at $278/mo, is −0.3% vs it) |
| Summarisation · CNN/DM | `anthropic_l`, $9,826 | −8.9% vs free `bart_l` (and the best paid arm, `deepseek_m` at $191/mo, is −0.0% vs free) |
| Extraction · Few-NERD | `anthropic_l`, $2,463 | −11.4% vs free `span_marker`, on a CPU |
| Retrieval · SciFact | `glm_m`, $2,288 | −0.2% vs `glm_s` at $711/mo |
| Classification · DBpedia | `anthropic_l`, $1,351 | −0.4% vs `qwen_m` at $51/mo |
| Classification · AG News | `anthropic_l`, $875 | −6.3% vs free `bert_base_ta` |

Two more facts about cost:

- **Cost rarely buys speed.** log(cost) vs latency correlates at **r = −0.19 to +0.20** in
  five experiments; on SummEval it is **−0.47** (the dearer judges answered faster, unexplained).
  `bert_mini` (7 ms) runs 61× to 1,078× faster than the hosted field, timed on the same Mac;
  the bert-base fine-tunes (76–90 ms) roughly 5×–140× faster, timed on a different machine, so
  good to about a factor of two. Generators run *slower*.
- **The task shape sets the bill, not the model.** 104 input tokens per item for
  classification against **3,926 for retrieval reranking** (38×); judging one article with its
  16 summaries takes ~2,095.

#### What to do with this

1. **Check the architecture before the model.** The largest cost lever here was structural.
2. **If you have labels for a fixed taxonomy, fine-tune a small model** — $0 against up to
   $9,826/month where one exists, and far lower latency on classification. Every task-specific
   winner here is **under 2 GB and needs no GPU**. Fine-tune on *your* data: the same BART
   trained on another corpus's summaries finished last (one arm, on `coverage`; its decode
   settings differ too). How few labels still work was not measured: the public fine-tunes
   here were trained on their corpora's own training splits.
3. **If you cannot, self-host an open-weight LLM before renting one.** The best proprietary
   arm never separated from the best open-weight arm in any experiment. A 128 GB machine
   matched the unlimited-hardware answer on five of six tasks; a 64 GB one, at native precision,
   on two (see above).
4. **Do not default to the most expensive arm.** `anthropic_l` was never first, and in three
   experiments it was *worse* than free. SciFact had no frontier tier, so its dearest arm says
   nothing about frontier models. Price still separates bad from mediocre: the dearest beat the
   cheapest in 5 of 6.
5. **Pick the cheapest arm your test cannot separate from the leader** — which requires a
   separation test, not a leaderboard — and read "cannot separate" as "not shown to differ
   at this n", not "equal": on AG News a paid arm five points behind the leader is still
   not separated at n = 200. Check the gap is one you can live with.
6. **Do not select on a pilot**; use it to catch instrument bugs, which is what it is good at.

**When paying more is right:** you cannot label data; the task is unlike anything a small
model has seen — on SummEval the one free evaluator trained for it, scoring one summary at a
time, lost to 23 of the 24 judges ranking all 16 at once; a wrong answer is expensive; your
volume is low enough that the whole spread is rounding error (at 1,000 items/month the entire
DBpedia range is $1.35); or engineering time costs more than the API. The claim is not that
expensive models are bad — it is that **the dearest model tested was never the best, and near
the top a large price range sat inside differences this much data could not resolve.**

### About this report

A cross-cutting report. Each of the five underlying reports answers *"which model is best
at this task"*; this one asks what is true in **all** of them, and it is written because
several findings only became visible once there were several corpora to compare. Seven
findings (§1–§7) and what they imply for **quality vs cost vs latency** in production (§8).
Every number below is computed from the stored runs, not quoted from the reports.

| dataset | task | primary metric (shape) | report |
|---|---|---|---|
| CNN/DailyMail | summarise a news article (**all 200 from CNN**; the test split is 91% DailyMail, so the summarisation price verdicts are CNN-only) | `coverage` (continuous) | [REPORT_SUMMARIZATION](REPORT_SUMMARIZATION.md) |
| AG News | 4-way topic label | `correct` (binary per item) | [REPORT_CLASSIFICATION](REPORT_CLASSIFICATION.md) |
| DBpedia-14 | 14-way ontology label | `correct` (binary per item, **saturated**) | [REPORT_CLASSIFICATION](REPORT_CLASSIFICATION.md) |
| Few-NERD | entities + types | `f1` (set vs set) | [REPORT_NER](REPORT_NER.md) |
| SciFact | retrieve from 5,183 docs | `ndcg_10` (ranked list) | [REPORT_RETRIEVAL](REPORT_RETRIEVAL.md) |
| SummEval | grade 16 summaries of an article as three experts did (**all 100 annotated articles**) | `tau` (rank correlation per article) | [REPORT_SUMMEVAL](REPORT_SUMMEVAL.md) |

*Each experiment is ranked by one primary metric, and every bare score below is in that
metric's units: summarisation by `coverage` (ROUGE-Lsum recall against the human
summary, output clipped to a word budget), AG News and DBpedia by `correct` (share of
items labelled right, i.e. accuracy), Few-NERD by `f1` (typed-entity F1 per sentence,
averaged), SciFact by `ndcg_10` (nDCG@10 of the ranked documents), SummEval by `tau`
(Kendall τ-b per article between a judge's scores and the expert means, averaged over four
dimensions). The first five run 0 to 1 and τ runs −1 to 1; all six are higher-is-better, so
a gap such as "0.0071" is in the units of the row's own metric.
"Arm" means one model-plus-configuration measured on one experiment.*

*The rest of this report unpacks each finding with its full evidence, and
[§8](#8-the-economics-what-money-actually-buys) has the complete economics. Each finding links
to the experiment report it comes from; those reports carry the per-task detail, the
corrections, and what each one could not measure. What this report cannot say is
[listed at the end](#what-this-cannot-say).*

---

## 0. The production question: should you fine-tune a small model instead of paying an LLM?

**Yes — for a task you can define and label. The best fine-tuned model is first, or not
separable from first, in 4 of 4, and it is not close on cost. But the answer depends entirely on one
variable, it is not model size, and on a saturated task it buys a tie rather than a win.
On SummEval the best local model, UniEval, was trained to judge, and it is separated below
23 of the 24 LLMs.**

### What actually predicts whether a free local model wins

Sorting all nineteen local arms by how much training on *this* data they had produces a
relationship that is **ordered, with exceptions** — one at each end of the middle: SciFact's
retrieval-trained encoders tie the paid arms without SciFact's labels, and SummEval's UniEval,
trained for its task, loses. One row per arm, grouped from most to least exposure. "Learned arms", here and below, means every arm that is a trained model:
all arms except the rule-based baselines (`constant`, `keyword`, `nothing`, `capitalized`,
`lead3`, `bm25`, `random`, `first_k`, and on SummEval ROUGE, `coverage` and `length`). The
last column is the arm's score minus the best **paid** arm's score in that experiment, in that experiment's metric, and the verdict of the
arm's own Holm family test against that paid arm: its p-value against the Holm threshold it
had to beat. "Not separated" means the test cannot tell the two apart. Every row was
re-run from the committed runs on 2026-10-15, the SummEval rows on 2026-10-19
(`scripts/family_test.py`, the arm against the whole field).

| training exposure | experiment | arm | rank (of N arms) | quality minus best paid arm (that task's metric) |
|---|---|---|---|---|
| **Fine-tuned on this dataset** | Extraction · Few-NERD | `span_marker` | **1st of 28** | **+0.0810**, separated (p = 0.0001 vs 0.05) |
| | Classification · AG News | `bert_base_ta` | **1st of 30** by point estimate | +0.0500, not separated (p = 0.022 vs 0.0167) |
| | Classification · AG News | `bert_base_fy` | 2nd of 30 | +0.0400, not separated (p = 0.077 vs 0.0167) |
| | Classification · AG News | `bert_mini` | 3rd of 30 | +0.0350, not separated (p = 0.116 vs 0.0167) |
| | Summarisation · CNN/DM | `bart_l` | **1st of 29** | +0.0001, not separated (p = 0.99 vs 0.05) |
| | Summarisation · CNN/DM | `bart_m` | 5th of 29 | −0.0094, not separated (p = 0.30 vs 0.0071) |
| | Summarisation · CNN/DM | `bart_s` | 10th of 29 | −0.0185, not separated (p = 0.054 vs 0.0023) |
| | Classification · DBpedia | `bert_base_fy` | 3rd= of 28 (five-way tie) | −0.0071, not separated (p = 0.62 vs 0.0050) |
| Fine-tuned on the task, **another corpus** | Summarisation · CNN/DM | `bart_l_xsum` (XSum → CNN/DM) | **29th of 29 — last** | **−0.1390**, separated (p < 0.0001 vs 0.0024), and from all 28 opponents |
| Trained for the task, **no human judgements of it** | Judging · SummEval | `unievalpub` (UniEval, on its own inputs) | 24th of 33 | **−0.1680**, separated (p < 0.0001 vs 0.0036), and below 23 of 24 judges |
| | Judging · SummEval | `unieval` (UniEval, on this experiment's inputs) | 26th of 33 | **−0.1922**, separated (p < 0.0001 vs 0.0042), and below 23 of 24 judges |
| Fine-tuned on this corpus, **another task** | Judging · SummEval | `bartscore` (a CNN/DM summariser, used as a judge) | 27th of 33 — **last learned arm** | **−0.2836**, separated (p < 0.0001 vs 0.0042), and below all 24 judges |
| Trained for the task *type* | Retrieval · SciFact | `e5_base` | 8th of 19 | −0.0246, not separated (p = 0.27 vs 0.0038) |
| | Retrieval · SciFact | `bge_small` | 11th of 19 | −0.0340, not separated (p = 0.13 vs 0.0042) |
| General-purpose embeddings | Retrieval · SciFact | `mpnet` | 15th of 19 | −0.0794, separated (p = 0.0011 vs 0.0031) |
| | Retrieval · SciFact | `minilm` | 16th of 19 | −0.0904, separated (p = 0.0002 vs 0.0042) |
| **Zero-shot** | Classification · AG News | `bart_mnli` | 28th of 30 — **last learned arm** | **−0.2100**, separated (p < 0.0001 vs 0.0018) |
| | Extraction · Few-NERD | `gliner` | 26th of 28 — **last learned arm** | **−0.2324**, separated (p < 0.0001 vs 0.0071) |
| | Classification · DBpedia | `bart_mnli` | 27th of 28 — **last learned arm** | **−0.3643**, separated (p < 0.0001 vs 0.0167) |

**The best model fine-tuned on each dataset ranked first in three experiments and
third-equal in the saturated fourth. Every zero-shot model ranked last among the learned
arms, and so did the one model trained on the corpus for a different task** — BARTScore,
fine-tuned to summarise CNN/DailyMail and asked here to judge summaries of it. That is
true of the best fine-tune per experiment in three of four and not of every one:
distillation costs `bart_m` and `bart_s` a few places without a separable loss, and on
DBpedia the fine-tune lands in a five-way tie for third, two items behind the leader —
inside the 19-arm group the leader cannot separate from, which is a weak kind of tie.

**The cleanest proof is a matched pair with price held at zero on both sides**, and a
control beside it. `gliner`, a zero-shot model that never saw Few-NERD, is the control: **+0.3134 F1** for `span_marker`. It is not a matched pair — the two differ in architecture and encoder (a span classifier on a RoBERTa encoder against a label-prompted matcher on DeBERTa-v3) as well as in exposure — so the gap is exposure plus architecture, not exposure alone. The gap is larger than the spread of the 24 hosted arms on that
task. And the matched pair: `bart_l` against `bart_l_xsum`, the same BART-large,
fine-tuned for summarisation both times, one on CNN/DailyMail and one on XSum — **1st and
29th of 29** on `coverage`. It is not a single-variable pair either: the XSum model also
decodes shorter (62/11 against 142/56 tokens, other beam and length settings). The XSum
model scores below LEAD-3. "Trained for the task" is not the
variable; "trained on text like yours" is — with one exception this report cannot explain.
UniEval was trained for the task, partly on CNN/DailyMail text, and still loses to 23 of
24 judges. UniEval trains in two stages: first on existing datasets for related tasks (inference, paraphrase, sentence acceptability, yes/no questions) and an opening-sentence task on CNN/DailyMail, then on each dimension with reference summaries as positives and rule-based corruptions of them as negatives. Its paper names no human judgements of summaries in either stage. Whether that, its size, or something else is why it loses is not tested.

### What that is worth in production

The best fine-tuned local arm against the best paid arm, in the four experiments that have
a fine-tuned arm (no arm was fine-tuned on SciFact). Every local arm costs $0 per item.
Bold marks the better quality in each row; latency is mean time per item. A second local
arm in parentheses is a smaller alternative, with its own figures in parentheses.

| experiment | fine-tuned local arm | local quality | local latency per item | best paid arm | paid quality | paid $/month at 1M items | paid latency per item |
|---|---|---|---|---|---|---|---|
| Extraction · Few-NERD | `span_marker` | **0.7674** | 0.76 s | `openai_m` | 0.6864 | $2,324 | 1.60 s |
| Classification · AG News | `bert_base_ta` (`bert_mini`) | **0.9600** (0.9450) | 76 ms‡ (7 ms) | `anthropic_m` | 0.9100 | $351 | 1.92 s |
| Summarisation · CNN/DM | `bart_l` (`bart_m`) | **0.3461** (0.3367) | 11.0 s (`bart_m` 1.5× faster than `bart_l` on one machine) | `deepseek_m` | 0.3460 | $191 | 1.60 s |
| Classification · DBpedia | `bert_base_fy` | 0.9857 | 87 ms‡ | `qwen_m` | **0.9929** | $51 | 0.85 s |

*‡ Timed on a 4-core Linux container. Every other figure in this table was timed on a
12-core Intel Mac, and the Linux machine ran `bart_l` 1.7× faster than the Mac did
(`harness/data/runs-linux/README.md`).*

Better or equal quality, zero inference cost, and **10–270× lower latency** on the
classification-shaped tasks: 270× for `bert_mini`, timed on the same Mac as the paid arm;
10–25× for the bert-base fine-tunes, a Linux-against-Mac ratio that is good to about a
factor of two. On DBpedia the paid arm leads by two items in 280, not separated. On
summarisation the two are not separated (gap 0.0001) and the local model is
*slower*, because generation on a CPU is genuinely expensive. Distillation takes a third
(`bart_m`) to nearly half (`bart_s`) off `bart_l`'s time on the same machine, and the win
there is still cost only.


### Three tiers, not two: the "paid" arms split in half

Calling the 24 hosted arms "paid" conflates two very different things. **14 of them have
downloadable weights** and could run on hardware you own; paying OpenRouter for them was a
convenience, not a requirement. The other 10 have no such option.

Verified against the HuggingFace API on 2026-09-29.

| tier | arms | what you can do with it |
|---|---|---|
| **1 · Local ML** | 19 local arms: 16 task-specific, and on SummEval BARTScore and UniEval on two sets of inputs | download, fine-tune, self-host. $0 at the margin |
| **2 · Open-weight LLM** | **14 of the 24** — DeepSeek ×3 (MIT), GLM ×3 (MIT), Gemma ×3, Llama ×3, `mistral_s` and **`mistral_l`** (Apache-2.0) | download and self-host, **or** rent. We rented |
| **3 · Proprietary** | **10 of the 24** — Anthropic ×3, OpenAI ×3, Qwen ×3, `mistral_m` (and `qwen37max`, which replaced `qwen_l` on SummEval) | rent only. No floor below the API price |

Licence nuance inside tier 2: **ten are unrestricted** (MIT or Apache-2.0 — all DeepSeek,
all GLM, `gemma_l`, `gemma_m`, `mistral_s`, `mistral_l`); **four are gated** behind
acceptance and carry use conditions (`gemma_s` under the Gemma licence, all three Llama arms). Gated still means
self-hostable; it does not mean unconditionally reusable.

### Best open-weight vs best proprietary, head to head

| experiment | best open-weight | best proprietary | delta (open − proprietary) | separated (Holm)? |
|---|---|---|---|---|
| Summarisation · CNN/DM | `deepseek_m` 0.3460 | `openai_m` 0.3268 | **+0.0192** | no |
| Retrieval · SciFact | `glm_s` 0.7437 | `qwen_s` 0.7183 | **+0.0254** | no |
| Classification · DBpedia | `glm_m` 0.9857 | `qwen_m` 0.9929 | −0.0071 | no |
| Extraction · Few-NERD | `gemma_m` 0.6733 | `openai_m` 0.6864 | −0.0131 | no |
| Classification · AG News | `llama_m` 0.8800 | `anthropic_m` 0.9100 | −0.0300 | no |
| Judging · SummEval | `gemma_l` 0.5384 | `openai_l` 0.5398 | −0.0013 | no (p = 0.8554 vs 0.0500, `gemma_l`'s own family test; 0.8585 in the leader's) |

**The best proprietary arm was never separated from the best open-weight arm. Not once in
six — and neither was the best open-weight arm separated from the best proprietary one.**
Individual proprietary arms can be separated, though: `anthropic_l` and `anthropic_m` sit
below `deepseek_m` on summarisation (p < 0.0001 and p = 0.0003 in `deepseek_m`'s family test).

Open weights led without separation on summarisation (by 0.0192; p = 0.0069 against a Holm
threshold of 0.0050, in `deepseek_m`'s family) and on SciFact (by 0.0254; p = 0.0283 against
0.0050), and trailed by 0.0013–0.0300 without separation on the other four.

"Not separated at n=200" is not "equal" — AG News's 0.0300 gap would likely resolve with
more items, and the honest reading is that **proprietary may hold a small real edge on
some tasks that this much data cannot demonstrate.** What the data does rule out is a
large one.



### If you are self-hosting anyway: small ML or an open-weight LLM?

Both run on your hardware at $0 marginal cost, so the choice is quality against the
machine it demands. They are not close in size.

| experiment | small ML model | small ML size | small ML score | best open-weight LLM | LLM size | LLM score | verdict |
|---|---|---|---|---|---|---|---|
| Classification · AG News | `bert_base_ta` (or `bert_mini`) | **438 MB** (44 MB) | **0.9600** (0.9450) | Llama-3.3-70B | ~141 GB | 0.8800 | **ML wins by 0.0800 at 1/322 the size, separated** (as run here); the 44 MB one leads by 0.0650 at 1/3,205 but is not separated (p = 0.0149 vs 0.0063) |
| Extraction · Few-NERD | `span_marker` | **499 MB** | **0.7674** | Gemma-4-26B-A4B | ~52 GB | 0.6733 | **ML wins by 0.0941, at 1/103** |
| Summarisation · CNN/DM | `bart_l` | **1.6 GB** | **0.3461** | DeepSeek-V4.1-Flash | 552B backbone, 510 GB checkpoint | 0.3460 | **not separated** (gap 0.0001) |
| Retrieval · SciFact | `e5_base` | **438 MB** | 0.7191 | GLM-4.5-Air | ~221 GB | **0.7437** | LLM wins by 0.0246, **not separated** |
| Classification · DBpedia | `bert_base_fy` | **438 MB** | **0.9857** | GLM-4.6 (or Gemma-4-26B, 52 GB) | ~714 GB | **0.9857** | **same score** (not separated), at 1/1,630 the size (1/119 of Gemma) |
| Judging · SummEval | `unievalpub` (UniEval, trained to judge; its own inputs) | **3.1 GB** | 0.3717 | Gemma-4-31B | ~63 GB | **0.5384** | **LLM wins by 0.1667, separated**, at 20× the size |

*Sizes are on-disk checkpoint sizes. A model in parentheses is an alternative with its own
size and score in parentheses beside the main ones: a smaller fine-tune (`bert_mini`) or an
equally scoring, smaller LLM (Gemma-4-26B). "At 1/322 the size" is the small model's size
divided by the LLM's. "Separated" is the Holm test against the LLM.*

**Four wins or ties for a model between 44 MB and 1.6 GB, against LLMs 103× (by download size) to 3,205×
larger**, LLMs as run here — two of them *separated* wins (Few-NERD, and AG News through
the bert-base fine-tune `bert_base_ta`; the 44 MB one is not separated), two not separated
at gaps of 0.0001 (summarisation) and 0.0000 (DBpedia). The DBpedia ML arm loads on any
machine with torch ≥ 2.6. The LLM earns its size in two places. On SciFact the
margin is not statistically separated, and the *best* configuration uses **both**:
`e5_base` retrieving, `glm_s` reranking, for 0.7891 — the highest point estimate, not
separated from six other configurations (REPORT_RETRIEVAL §3.4); the range registered for it held for `glm_s` and
not for `qwen_s`. On SummEval it is: a 63 GB open-weight
judge beats UniEval, a 3.1 GB evaluator trained for the task, by 0.1667, scored on UniEval's
own inputs, and the 1.6 GB BARTScore by 0.2822.

Two practical consequences a DGX owner should weigh:

- **Several of these "self-hostable" LLMs are cluster-scale, and the published
  parameter counts understate them.**
  DeepSeek-V4.1-Flash is advertised as 552B backbone parameters; its checkpoint is
  **510 GB**, because a 196B Engram memory ships with it and the headline count excludes
  it. GLM-4.6 is 714 GB. Whether either fits a given node depends on what must stay
  GPU-resident — a question about serving strategy that a parameter count cannot answer
  and **this report does not attempt to.** The small ML models fit in RAM on a laptop,
  which needs no such caveat.

- **Concurrency is where the size gap really lands.** A 44 MB classifier at 7 ms/item
  saturates a CPU core and scales by forking; a 70B model occupies most of a GPU and
  scales by buying more of them. The scores above are per-item quality, and they say
  nothing about how many items per second each arrangement sustains — **this report
  measures no throughput at all.**

**So the ordering for a hardware owner is: fine-tuned small ML first, open-weight LLM
where no fine-tuned model exists or the task is generative or a judgement, and a rented
API only when neither can run.** DBpedia fits the ordering: a 438 MB classifier matches the
best open-weight LLM exactly.


### What you would actually install on a 128 GB machine

"Open-weight" and "runnable" are not the same thing. Of the 14 open-weight arms here,
**five exceed 700 GB** at native precision and the largest is **1.5 TB** (GLM-5) — those are cluster models,
not something you put on a workstation. So the practical question is: *what is the best
open-weight model that fits the box I have?*

Sizes are native on-disk (dtype-aware, read from each HuggingFace safetensors index), and
the budget is **128 GB of unified or GPU memory** — an Apple M-series box, a dual-GPU
workstation, or a single node with room for weights plus KV cache.

A model needs room for KV cache and activations as well as weights, so an arm qualifies
here only if its weights fit in **85% of nominal memory**.

Read each row left to right: the best open-weight LLM with no memory limit, then the best one
that fits 128 GB, then the best that fits 64 GB. **"same"** means the same model as in the
previous model column, at the precision and size stated. "Fits" applies the 85% rule above:
weights at most 108.8 GB for the 128 GB budget and 54.4 GB for the 64 GB one. Every score
is the full-precision model as served by a provider — none of the int8/int4 variants was
measured (see the caveat below). The ≤128 GB column names an int8 or int4 build where the
unlimited-hardware model fits only that way, marked "not run", as the reports do. The ≤64 GB
column names the best model that fits at native precision: a score as served is no evidence
about the model's int4 or int8 build, and where the unlimited-hardware model would fit only
quantised, the cell says so. These are open-weight LLMs only; the experiment's overall
winner may be a small ML model or a proprietary one.

| experiment | best open-weight LLM, unlimited hardware | its size | its score | best that fits ≤128 GB (precision, size) | ≤128 GB score | best that fits ≤64 GB (precision, size) | ≤64 GB score |
|---|---|---|---|---|---|---|---|
| Classification · AG News | Llama-3.3-70B | 141 GB | 0.8800 | **same**, ~70 GB at int8 (not run) | **0.8800** as served | Mistral-Small-3.2-24B (`mistral_s`), native 48 GB; Llama at int4 (~35 GB) not run | 0.8600 (0.0200 below, not separated) |
| Classification · DBpedia | GLM-4.6 | 714 GB | 0.9857 | **Gemma-4-26B**, native 52 GB | **0.9857** | **same**, native 52 GB | **0.9857** |
| Extraction · Few-NERD | Gemma-4-26B | 52 GB | 0.6733 | **same**, native (weights only; not run at that size) | **0.6733** as served | **same**, native (not run) | **0.6733** as served |
| Retrieval · SciFact | GLM-4.5-Air | 221 GB | 0.7437 | **same**, ~55 GB at int4 (not run) | **0.7437** as served | Gemma-4-26B, native 52 GB | 0.7363 (0.0074 below, not separated) |
| Summarisation · CNN/DM | DeepSeek-V4.1-Flash | 510 GB | 0.3460 | Llama-3.3-70B, ~70 GB at int8 (not run) | 0.3382 as served | Mistral-Small-3.2-24B (`mistral_s`), native 48 GB; Llama at int4 not run | 0.3255 (0.0205 below, separated) |
| Judging · SummEval | Gemma-4-31B | 63 GB | 0.5384 | **same**, native 63 GB | **0.5384** | Gemma-4-26B-A4B (`gemma_m`), native 52 GB; Gemma-4-31B at int8 (~31 GB) not run | 0.4770 (0.0614 below, separated) |

**Hardware buys almost nothing from unlimited down to 128 GB, and something below that.**
Five of six 128 GB answers equal the unlimited-hardware answer (two of them, AG News and
SciFact, only as an int8 or int4 build that was not run). Capping at 128 GB costs **0.0078**
on summarisation (a 510 GB model replaced by a 70 GB one at int8; not separated, p = 0.27),
about **18%** of the spread between the best and worst hosted arm on that task (0.0431).
Halving the budget to 64 GB leaves two of the six answers unchanged (DBpedia and Few-NERD,
both Gemma-4-26B at 52 GB) and costs the rest, against the unlimited-hardware answer:
SciFact **0.0074** (`glm_s` 0.7437 → `gemma_m` 0.7363, a gap its own test cannot resolve and
inside run-to-run noise), AG News **0.0200** (not separated, p = 0.39), summarisation
**0.0205** (separated: p = 0.0026 against a Holm threshold of 0.0042) and SummEval
**0.0614** (separated: p < 0.0001).

So at native precision a **64 GB machine matched the unlimited-hardware answer on two of the
six tasks** and trailed on the other four, by 0.0074 to 0.0614. On AG News and SummEval an
int4 or int8 build of the unlimited-hardware model would fit 64 GB; whether it would close
the gap was not measured.

**The 64 GB column cannot lean on quantised builds, and that is where the caveat below
bites hardest:** int8 is usually close to lossless, int4 frequently is not. If your box is
64 GB, the native-precision options (Gemma-4-26B-A4B at 52 GB, Mistral-Small-3.2-24B at 48 GB)
are the ones whose numbers here you can trust without re-measuring.

> **The caveat, and it is a real one: quantised quality was never measured here.** Every
> score in this table comes from the full-precision model as served by a provider. int8 is
> usually close to lossless and int4 usually is not, but "usually" is not a measurement —
> and this repo's whole argument is that the difference matters. **Before deploying a
> quantised arm, re-run it locally through this harness and compare.** `rescore.py` makes
> the comparison cost nothing once the outputs exist.

**Practical shortlist for a 128 GB machine, by task:**

| if your task is | install |
|---|---|
| classification | **a BERT fine-tune** (44–438 MB) if you can label — it led AG News on the point estimate and was not separated from DBpedia's best, LLMs as run here; else **Gemma-4-26B** (52 GB) |
| entity extraction | **SpanMarker fine-tune** (499 MB). No open-weight LLM here came close |
| summarisation | **BART-large-CNN** (1.6 GB), or its distillation (`bart_m`, 1.2 GB, 1.5× faster on the same CPU, not separated from it), if your summaries look like CNN/DailyMail's; else **Llama-3.3-70B** (~70 GB at int8; scored as served, not run at int8) — a BART trained on someone else's summaries finished last |
| retrieval | **e5-base** (438 MB) alone, and add **GLM-4.5-Air int4** (55 GB) only if you need the last 0.07 |
| judging summaries | **Gemma-4-31B** (63 GB native, or int8 at about half that, unmeasured). The best small model measured, UniEval (3.1 GB, trained for the task), is separated below every open-weight judge but `llama_s` |

The first choice in every row but the last is under 2 GB and needs no GPU at all; the LLM
fallbacks (52–70 GB), and the judge, do.

### Every experiment has a $0 answer, if you own hardware

Combining the tiers with the separation tests: in **all six** experiments there is a
configuration requiring no proprietary model and no per-item bill.

"Tied with N" counts the opponents the leader's Holm test cannot separate from it (§2).

| experiment | the $0 answer | tier | quality | quality given up vs the leader |
|---|---|---|---|---|
| Summarisation · CNN/DM | `bart_l` | local ML | **0.3461** | none — first on the point estimate, not separated from 15 others (13 paid) at gaps of 0.0001–0.0257 |
| Classification · AG News | `bert_base_ta` (or `bert_mini`) | local ML | **0.9600** (0.9450) | none — first on the point estimate, not separated from 3 others (two fine-tunes and `anthropic_m`) at gaps of 0.0100–0.0500 |
| Extraction · Few-NERD | `span_marker` | local ML | **0.7674** | none — it ranks first, separated from all 27 opponents |
| Retrieval · SciFact | `glm_s` reranking BM25's top 20 | **open-weight, MIT** | **0.7437** | none — **the leader itself is self-hostable**. With `e5_base` retrieving instead of BM25 the same reranker scores 0.7891, a separate pipeline run |
| Classification · DBpedia | `bert_base_fy` (or `gemma_m` / `glm_m`) | **local ML** (or open-weight) | 0.9857 | **−0.0071, not separated** |
| Judging · SummEval | `gemma_l` | **open-weight, Apache-2.0** | 0.5384 | **−0.0013, not separated** (p = 0.8585 vs 0.0500, the leader's family test) |

Four of six cost nothing at all. DBpedia costs 0.0071 accuracy — two items in 280, a
difference the data cannot resolve — to avoid a winner with **no self-host option at any
price** (`qwen_m`, one vendor, no published weights; SummEval's `openai_l` is the other). That $0
answer is a 438 MB classifier on a CPU (or a 52 GB open-weight LLM) at the same score. SummEval costs 0.0013 τ against `openai_l`, also unresolvable, and
it is the one experiment whose $0 answer has no CPU-sized alternative: SciFact's is an
LLM too, but `e5_base` on a CPU is tied with it, while on SummEval the best small model,
UniEval, is separated below 23 of the 24 judges.

**This is the finding a hardware owner should read first.** Not "free models are
competitive" but: *across six unrelated tasks, the best configuration you can run
entirely on your own machines either ranks first or is not separated from the leader at
this many items.*

The bill you avoid is **$24,187/month** at 1M items for the open-weight tier (every arm's
bill summed, as below), and the proprietary tier's combined **$100,894/month** becomes
irrelevant rather than merely expensive.

### What that means if you own the hardware

Each arm's billed cost per item, scaled to 1M items/month in every experiment the arm ran,
then summed over every arm in the tier — a combined bill for running the whole tier, not
the price of any one model:

| tier | sum of every arm's bill at 1M items/month, rented | the same, self-hosted |
|---|---|---|
| tier 2 (14 open-weight arms) | $24,187/month | **$0** |
| tier 3 (10 proprietary arms, and `qwen37max` on SummEval) | $100,894/month | **not possible** |

*SummEval adds $9,169 to the first and $61,085 to the second. An item there is a whole
article with 16 summaries, the prompts are long (§8), and its bills are October's, after
prices had moved in both directions
([REPORT_SUMMEVAL §6](REPORT_SUMMEVAL.md#6-what-changed-while-measuring)). Without it the
two tiers were $15,018 and $39,809.*

For someone with a DGX, tier 2 collapses into tier 1 economically: **the marginal cost of
an open-weight LLM becomes electricity, and the quality question stops being a cost
question at all.** The only arms whose price is unavoidable are the eleven proprietary
ones, and none of them was separated from the best open-weight arm here.

What self-hosting costs instead — and this report measures none of it — is the hardware,
the serving stack, the ops burden, throughput engineering, and the fact that a 70B model
on your own GPUs is slower per request than a provider's optimised fleet unless you invest
in batching. **The trade is capex and engineering time against a rental bill**, and the
crossover depends entirely on volume.

### The strongest argument on the other side, also measured

**One hosted model does all six tasks with nothing but a prompt change.** Twelve of the
24 hosted arms ran every experiment unmodified; the best of them, `glm_m`, sits at the
**67th percentile across all six** (the share of each experiment's hosted arms that it
scores above, ties counted half, averaged; 72nd if ties are counted fully in its favour.
Recomputed from the committed runs, with no check behind it). The best fine-tuned local
model sits at or tied with
the top on **one task each** and cannot perform the others at all — and, the XSum
control shows, cannot even perform its *own* task on someone else's data. On the sixth,
judging, the best local model — UniEval, trained to judge — finished below 23 of the 24
hosted judges, and a summariser used as a judge below all of them.

That is sixteen task-specific local arms to cover five of the six tasks, against what twelve hosted
arms covered with one configuration. If you have many tasks, a moving target, or no
labelled data, the generalist is not a compromise — it is the only thing that works.

### So the honest rule

> **If the task is stable, you own labels in a fixed taxonomy, and the volume is high enough
> that a rental bill matters — fine-tune a small model.** Where one existed it ranked first
> or was not separated from the leader at $0 per item in all four experiments, separated
> from the paid field on Few-NERD only. It was 10×–270× faster on classification, slower on
> summarisation (11.0 s against 1.6 s for `deepseek_m`, quality not separated) and two items
> behind on DBpedia. How few labels still work was not measured.
>
> **If the task is fluid, unlabelled, or one of many — pay for the LLM.** Then use §8 to
> avoid overpaying for it: `anthropic_l`, the dearest arm in five experiments, was never the
> best one.

### What this conclusion does NOT rest on, and the four ways it could be wrong

1. **Every fine-tuned arm was tested on the same distribution it was trained on.** That is
   precisely what "you govern the dataset" means, and it is also the best case. Nothing
   here measures **distribution drift**, which is the main way a fine-tuned model decays
   in production and the main reason teams reach for a generalist.
2. **Part of the lead is learning the annotator's conventions, not the task.** Few-NERD
   bounds it: **up to 38% of `span_marker`'s lead** over `openai_m` is agreement with
   annotation the rest of the field rejects (7–53% across thresholds and arms; an upper
   bound, voted on by the arms being scored), and **57% of its margin over `openai_m` is one
   entity type**, `other` (30–57% across the 24 hosted arms, for a prompt that defines no
   type). AG News is starker: three
   fine-tunes agree with the gold on 12–14 of 17 items that ≥80% of the hosted field
   disputes, the best hosted arms on 0–3, and that is almost the whole lead — 8 of the 17 a
   learnable convention (tech-company business news filed as `Sci/Tech`), 7 plain
   mislabels, 2 ambiguous. And summarisation shows the other face of it: BART trained on another
   corpus's summaries finishes last. In production, *your* conventions are what you want
   — but the measured win does not transfer to a different labelling standard.
3. **"Free" means zero inference cost and nothing else.** No labelling, no training
   compute, no hosting, no monitoring, no retraining when the data moves. A model that
   takes an engineer a fortnight to ship is not free at any volume. The crossover point
   against $191/month is a spreadsheet this report does not contain.
4. **Five of the six tasks are classic NLP with mature small-model architectures** —
   summarisation, classification, NER, retrieval. Nothing multi-step, reasoning-heavy, or
   instruction-following. Those are exactly the tasks where a generalist is structurally
   advantaged, and **none of them were tested here.** The sixth, judging summaries, is
   the one task where the free arm trained for the job lost, and there 23 of the 24
   generalists are separated above it. It is one task and one trained evaluator, so it
   shows the direction of the exception, not its size.

---

## The seven findings, unpacked

### 1. The dearest arm is never first — but SciFact's "dearest" is a cheap model

Five of the six are one model, `anthropic_l`; SciFact's is `glm_m`, because only the twelve
cheapest models ran there. So this is mostly a finding about one dear model, and it says
nothing about the next few down: the best hosted arm was the 3rd-dearest of 24 on AG News,
the 2nd on Few-NERD and the 4th on SummEval. SciFact had no frontier tier, so there the
claim is about the dearest of twelve cheap models; for the frontier tier it rests on the
five experiments where it ran.

| experiment | dearest paid arm | billed cost, whole run (N items) | its rank among all arms |
|---|---|---|---|
| Summarisation · CNN/DM | `anthropic_l` | $1.9652 (200) | **18 of 29** (16 of 25 before the distilled BARTs) |
| Classification · AG News | `anthropic_l` | $0.1750 (200) | 5 of 30 (3 of 28 before the bert-base arms) |
| Classification · DBpedia | `anthropic_l` | $0.3784 (280) | 2 of 28 |
| Extraction · Few-NERD | `anthropic_l` | $0.6897 (280) | 3 of 28 |
| Retrieval · SciFact | `glm_m` | $0.4576 (200) | 2 of 19 |
| Judging · SummEval | `anthropic_l` | $2.0077 (100) | 3 of 33 |

*SciFact's dearest arm is `glm_m` because only the 12 hosted arms under $0.60/Mtok input
were run there: no Anthropic or OpenAI arm, and none of the other expensive ones.*

**But the naive version of this claim is false, and worth killing.** "Price buys nothing"
is not supported: the dearest arm beats the *cheapest* arm in 5 of 6 experiments. Price is
weakly informative across the whole field, and near the top the price ranges sit inside
differences the data cannot resolve — though SummEval has the steepest price slope as a
share of the best score.

The practical form: **paying the most was never the optimum here (SciFact's "most" being
a cheap model), and paying the least is usually not either.** Among paid arms the best was a *mid*-tier model in four of six
experiments, a *small*-tier one in SciFact, and a *large*-tier one once: `openai_l` on
SummEval, where it cannot be separated from five other judges, one of them costing 1/23 as much.

### 2. The top of a leaderboard is a group, not a podium

Every winner leads on the point estimate against **100%** of its declared family. How many
it actually *separates* from, under Holm step-down at α = 0.05:

Sorted by the share separated, highest first. "Ahead of" and "separated from" count the
winner's opponents, every other arm in the experiment. In the last column, "a group of N"
is the N opponents the winner cannot separate from; the winner is not counted, so the tied
group including it is N + 1 arms.

| experiment | winner | ahead of | separated from | reading |
|---|---|---|---|---|
| Extraction · Few-NERD | `span_marker` | 27 of 27 | **27 of 27** (100%) | a real podium |
| Classification · AG News | `bert_base_ta` | 29 of 29 | 26 of 29 (90%) | a group of 3 |
| Judging · SummEval | `openai_l` | 32 of 32 | 27 of 32 (84%) | a group of 5 |
| Summarisation · CNN/DM | `bart_l` | 28 of 28 | 13 of 28 (46%) | a group of 15 |
| Retrieval · SciFact | `glm_s` | 18 of 18 | 6 of 18 (33%)† | a group of 12 |
| Classification · DBpedia | `qwen_m` | 27 of 27 | 8 of 27 (30%) | a group of 19 |

*† At the default 20,000 permutations. Two opponents sit on their Holm thresholds, and at
400,000 permutations it is 7 of 18 and a group of 11 — so 11–12 opponents, or 12–13 arms
counting `glm_s` itself ([retrieval §3.2](REPORT_RETRIEVAL.md)). The default-setting figure
is the one §8's tie table uses.*

*AG News's group is two other fine-tunes and `anthropic_m`, the last at p = 0.022 against
a 0.0167 threshold — close to a podium, and a podium of three fine-tuned models of one kind.*

**Five of six leaderboards have a top group the data cannot order.** Reading rank 1 as
"the best model" would have been wrong five times. The gap between "ahead of everything"
and "distinguishable from a third of it" is the single most repeated result here.

### 3. A free local model wins or ties, whenever one trained for the task can run — except on SummEval

*Sources:* [NER](REPORT_NER.md) · [classification](REPORT_CLASSIFICATION.md) · [summarisation](REPORT_SUMMARIZATION.md) · [retrieval](REPORT_RETRIEVAL.md) · [SummEval](REPORT_SUMMEVAL.md)

"3=" means tied on score for third place (on DBpedia, five arms score 0.9857). The last
column is the free arm's score minus the best paid arm's, in that experiment's metric.

| experiment | best free arm (size) | rank (= tied) | free − best paid arm (task metric) |
|---|---|---|---|
| Extraction · Few-NERD | `span_marker`, 499 MB | **1 of 28** | +0.0810 over `openai_m`, separated |
| Classification · AG News | `bert_base_ta`, 438 MB | **1 of 30** | +0.0500 over `anthropic_m`, not separated from it (p = 0.022 vs 0.0167) |
| Summarisation · CNN/DM | `bart_l`, 1.6 GB | **1 of 29** | **+0.0001** over `deepseek_m` |
| Retrieval · SciFact | `e5_base`, 438 MB | 8 of 19 | −0.0246 vs `glm_s`, **not separated** |
| Classification · DBpedia | `bert_base_fy`, 438 MB | 3= of 28 | −0.0071 vs `qwen_m`, **not separated** (p = 0.62) |
| Judging · SummEval | `unievalpub`, 3.1 GB (UniEval, trained for the task, on its own inputs) | 24 of 33 | −0.1680 vs `openai_l`, **separated**, and from 23 of 24 judges |

Read the third row before the first two. **`bart_l` "wins" summarisation by 0.0001** — it
is first on the leaderboard and tied with a hosted model in every sense that matters. An
earlier draft of this table reported +0.0176 there, because it compared against
`anthropic_l` rather than against the best paid arm; the corrected number turns an
apparent win into the winner's-curse case of §4.

So: **one separated win (Few-NERD), four statistical ties — two led by the free arm (AG
News, summarisation) and two trailed by it (SciFact, DBpedia) — and one loss, SummEval,
where the free arm was trained for the task and still lost.** The pattern is
narrower and stronger than "small models win":

> **A small model fine-tuned on your data wins or ties against every hosted LLM as run here
> (one prompt, zero-shot), for $0** — a separated win on Few-NERD, a statistical tie everywhere else.
> A small model trained for a different task, on a different corpus, or not at all loses
> to the best LLMs on Few-NERD, AG News, DBpedia and SummEval — one trained for the same task
> on a different corpus, one trained on the same corpus for a different task (BARTScore on
> SummEval, below all 24 judges), and the zero-shot models. **Two exceptions:** on SciFact
> two encoders trained for retrieval but not on SciFact tie the paid arms, and UniEval,
> trained for SummEval's task, partly on its corpus, loses to 23 of the 24 judges; why is
> not tested here.

Few-NERD shows the size of it against a zero-shot control — `span_marker` +0.3134 F1 over
`gliner`, which differs in architecture as well as exposure. Summarisation has the closest
to a matched pair: the same BART-large fine-tuned for summarisation
on CNN/DailyMail and on XSum, **1st and 29th of 29** on `coverage`, though the two also
decode at different lengths.

**And the optimum was a mid-tier arm in four of six experiments** (`_m_` in
summarisation, AG News, DBpedia and Few-NERD; `_s_` in SciFact; `_l_` in SummEval). The
large tier was the optimum once, and there it cannot be separated from five others.

**The caveat the NER report insists on:** 57% of `span_marker`'s margin over `openai_m`
comes from one entity type the prompt never defined (30–57% across the hosted arms), and up
to 38% of its lead is agreement with annotation the rest of the field rejects (an upper
bound). AG News now shows the same
thing at larger scale: three fine-tunes agree with the gold on 12–14 of the 17 items that
≥80% of the hosted field rejects, and that is nearly their whole lead
([classification §3.4](REPORT_CLASSIFICATION.md)). Fine-tuned models partly learn *your
conventions*, which is exactly what you want in production and is not the same as being
right.

### 4. A pilot correlates beautifully and picks the wrong winner

*Sources:* [retrieval §3.5](REPORT_RETRIEVAL.md) · [summarisation §3.6](REPORT_SUMMARIZATION.md) · [NER §3.8](REPORT_NER.md)

Five of the six experiments ran a small dev slice before the full one; SummEval, whose
items are the whole benchmark, ran none. Comparing the two, sorted by ρ
— the Spearman rank correlation between the arms' order on the dev slice and their order on
the full run (1 = identical order). ✓ marks a pilot that picked the true leader:

| experiment | ρ, dev-slice vs full ranking (Spearman) | dev slice (items) | dev leader | true leader | dev leader's rank on the full run |
|---|---|---|---|---|---|
| Extraction · Few-NERD | 0.895 over the 27 arms measured then (0.903 with all 28) | 56 | `span_marker` | `span_marker` | 1 of 28 ✓ |
| Classification · AG News | 0.677 committed (0.852 uncommitted) | 20 | `anthropic_l` | `bert_base_ta` | **5 of 30** (3 of 28 before the bert-base arms) |
| Retrieval · SciFact | 0.756 (dev runs not committed) | 40 | `llama_s` | `glm_s` | **10 of 19**, 0.0265 behind, not separated |
| Classification · DBpedia | 0.757 committed (0.728 uncommitted) | 56 | `anthropic_l` | `qwen_m` | 2 of 28 |
| Summarisation · CNN/DM | 0.722 (hosted dev runs not committed) | 20 | `bart_l` | `bart_l` | 1 of 29 ✓, not separated from `deepseek_m` (0.0001) |

*The ρ column is from dev-slice runs made before the six local arms existed, and those dev
runs were never committed — so ρ cannot be extended to the new arms, and the AG News and
DBpedia values cannot be re-derived from this repository. Recomputing the dev ranking from
the dev items inside the committed full runs gives 0.677 and 0.757 on the field as it stood
then (28 and 27 arms; 0.701 and 0.768 with today's), with a 10- to 13-way tie at the top of
the dev slice; see
[`KNOWN_ISSUES.md`](internal/KNOWN_ISSUES.md). The last two columns are from committed runs.*

**ρ between 0.68 and 0.90 where it can be recomputed — and the pilot picked a different
leader from the full run in three of the five experiments that ran one.** On SciFact it
picked the tenth by point estimate, 0.0265 behind the leader and not separated from it: a
wrong winner inside a tie, which is the point.

This is the most transferable finding in the repo, because ρ is the number people quote to
justify a pilot and it is **the wrong number for the decision being made**. A high rank
correlation says the *ordering* is broadly preserved. Selecting one arm depends on the
ordering at the very top, which is where the noise concentrates and where the field is
tied (§2).

Related, from the summarisation study: BART's lead over the best LLM was **0.0737 at n=20**
and **0.00008 at n=200** — a 900× shrink. Same arms, same metric, more data.

### 5. Some gold labels are disputed or noisy, in every corpus that was checked

*Sources:* [NER §3.6](REPORT_NER.md) · [classification §3.4](REPORT_CLASSIFICATION.md)

A **consensus pass** takes every learned arm's answers and lists the gold labels that
nearly all of them contradict in the same way; independent models rarely agree on the same
mistake, so those labels are suspect. It flags candidates, it does not prove an error.

| corpus | suspect gold labels (count, unit) | flagged when | method |
|---|---|---|---|
| Few-NERD | **34 of 768** gold entities (4.4%) | the span is found but ≥80% of the 26 learned arms give it another type | consensus pass |
| DBpedia | 3 items | 24–25 of the 26 learned arms dispute the label; the top eleven arms are separated by four items. Whether the label or the field is right is one rater's reading, unadjudicated | consensus pass |
| AG News | 17 items | ≥80% of the hosted field disputes the label (19 at 75%, 20 at 70%) — the fine-tuned lead is concentrated in them; revised a published finding twice | consensus pass, hosted arms only |
| CNN/DailyMail | **not checked** | — | — |
| SciFact | **not checked** (qrels incompleteness unmeasured) | — | — |
| SummEval | 41 of 44 groups of word-for-word identical summaries | the copies received different expert mean scores (REPORT_SUMMEVAL §3.7) | identical-text check, not a consensus pass |

Four for four where anyone looked. The honest statement is not "most corpora have noisy
gold" — it is **every corpus we examined had disputed or noisy gold labels, and two were
never examined.** A consensus pass flags candidates; which of them are wrong is a judgement,
made here by one rater. SummEval's
is a different kind of check: identical inputs that received different scores show the
gold is noisy, not that any one score is wrong.

On a saturated benchmark this stops being a footnote and becomes the ceiling: DBpedia's top
eleven arms are separated by four items, and three of those are items 24–25 of 26 learned arms dispute
because, on one rater's reading, the field's answer is defensible and the label
unadjudicated; DBpedia's leader is ahead of the second arm by exactly one of them. **On that
reading the measurement was resolving annotation, not capability.**

The diagnostic is cheap and general: items nearly every *learned* arm gets wrong are items
that are candidates for wrong gold. Independent models do not agree on a mistake.

**With one refinement the fine-tuned arms forced:** leave out the arms trained on the gold.
They are not independent of it. On DBpedia the one arm that "gets" the canal filed under
`NaturalPlace` is the one trained on DBpedia; on AG News the arms that agree with the gold
on the 17 disputed items are the three trained on AG News. A consensus that includes them
under-counts label errors — and a leaderboard that includes them over-counts their skill.

### 6. The instrument was broken before the models got interesting — in five of six

*Sources: the Corrections section of each report, and [`NOTES.md`](internal/NOTES.md), 70 entries*

Defects found **by** running the experiments, each of which changed published numbers or
would have:

| experiment | defect | impact if not found |
|---|---|---|
| Summarisation · CNN/DM | scorer bug surviving two sweeps | drove `rescore.py` into existence |
| Classification · AG News | duplicate-run check flagged honest ties as copies | 4 false alarms in one sweep |
| Classification · DBpedia | the **label parser** is worth **8.6 accuracy points** to one arm | wider than most of the field's spread |
| Extraction · Few-NERD | an unreadable answer scored **1.0** on empty-gold items | +0.0214 f1 to one arm |
| Extraction · Few-NERD | `normalizer_sha256` covered the normaliser, not the scorer | a scorer change was invisible in the fingerprint |
| Retrieval · SciFact | the adapter never disabled reasoning, unlike the other three | one arm went **0.6124 → 0.6991** once fixed |
| all | cost computed from a price table, not what was billed | wrong per arm by 0.67×–3.76× |
| all | Spearman had no tie correction; ranks broke ties **alphabetically** | ρ measured the alphabet on saturated tasks |

Three of these — the parser, the unparsed-as-empty rule, the reasoning flag — moved a
single arm by **more than the gap separating most of the field**. SummEval adds none:
none of its committed runs was rescored or re-run because of a scorer defect. What it did
find were facts about renting models — a model withdrawn by its provider, a successor that
refuses reasoning off, and prices that had moved since September
([REPORT_SUMMEVAL §6](REPORT_SUMMEVAL.md)). So:

> **The scoring code is a model-sized lever.** Changing how you parse an answer can matter
> more than changing which model produced it.

This is why every run fingerprints `parser_sha256`, `scorer_sha256` and `normalizer_sha256`,
and why `rescore.py` exists: recomputing every score from stored outputs costs $0, so
checking a scorer is never the expensive option.

### 7. The metric's shape decides which diagnostics can be read at all

*Sources:* [classification §3.6](REPORT_CLASSIFICATION.md) · [NER §3.9](REPORT_NER.md) · [retrieval](REPORT_RETRIEVAL.md) · [SummEval §3.5](REPORT_SUMMEVAL.md)

Not which model wins — which *tools* work.

| shape | how often two arms tie on the mean | consequence |
|---|---|---|
| continuous (ROUGE) | ~never | rank correlation is meaningful; duplicate-detection by mean is safe |
| binary per item (accuracy) | constantly | two different models report identical means; ρ degenerates |
| set (F1 per item) | rarely | per-item F1 is legitimate, so permutation tests work directly |
| ranked list (nDCG) | rarely | but **corpus ≠ items**, which breaks fingerprinting |
| rank correlation per item (Kendall τ-b) | never here (no two of the 33 SummEval arms share a mean τ to four decimals) | the *judge's* scores tie constantly (integer 1–5), so the τ-b tie correction is part of the instrument; per-item τ makes the paired tests apply directly, and split-half rankings are readable (ρ 0.90 at 20 articles per half) |

Concretely: on DBpedia at n=10, **19.9 of 28 arms tied** (19.8 of 27 before the fine-tuned arm), so the rank statistic was
correlating *arm names*. Requiring a unique winner, **354–399 of 400 resampling draws are
undecided at every size tested, and in every decided draw the two halves crown different
arms** — that corpus has no winner to agree about, and every earlier stability figure for
it was an artifact of alphabetical tie-breaking. (At k=27 it was 400 of 400 undecided; the
fine-tuned arm breaks a few ties without producing agreement.)

The same tool on Few-NERD reports `arms tied 1st = 1.0` at every size and is perfectly
readable. **The tool was never wrong in general; it was wrong for a metric shape.**

---

## 8. The economics: what money actually buys

The five reports each measure quality and record cost. Put together, they answer the
question a production decision actually asks — **how much quality does a dollar buy, and
where does it stop buying any.**

All figures are what the provider billed, projected to **1,000,000 items/month**. Latency
is per item, excluding one-time setup.

### What a 10× cost increase buys

A log-linear fit over the paid arms in each experiment — quality against `log10(cost)`,
sorted by the slope as a percentage, highest first. The slope is in each experiment's own
metric; the percentage divides it by the best paid arm's score:

| experiment | paid arms in fit | slope: quality change per 10× cost (task metric) | slope as % of best paid arm's score | Pearson r |
|---|---|---|---|---|
| Judging · SummEval | 24 | +0.0399 | **+7.4%** | r = 0.49 |
| Extraction · Few-NERD | 24 | +0.0407 | **+5.9%** | r = 0.50 |
| Retrieval · SciFact | 12 | +0.0200 | +2.7% | r = 0.32 (p ≈ 0.3) |
| Classification · AG News | 24 | +0.0214 | +2.3% | r = 0.63 |
| Classification · DBpedia | 24 | +0.0094 | +0.9% | r = 0.40 |
| Summarisation · CNN/DM | 24 | −0.0013 | **−0.4%** | r = −0.07 |

*Every fit uses the rescored Few-NERD runs and the corrected-parser SciFact runs. Only
summarisation's fit is checked by `check_report_claims.py`; the others were recomputed from
the committed runs and the billed costs (SummEval: slope 0.03989 ÷ best paid score 0.5398 =
7.39%).*

**An order of magnitude more money buys between nothing and seven percent.** On
summarisation the slope is *negative* and the correlation near zero — r = −0.07 across 24
arms and a 143× price range (95% interval −0.46 to +0.34, so a moderate effect is not
excluded), with price confounded with vendor. SummEval has the
largest slope as a share of its best score, though not the largest correlation (AG News's
r = 0.63 and Few-NERD's 0.50 exceed its 0.49), and no slope here has an interval. Even there
the cheapest judge inside the leader's tie costs 1/72 of the dearest.

Even a steep case is a bad trade at scale: Few-NERD's +5.9% per 10× predicts that
going from $27/month to $2,463/month (a 90× step) buys about **8 points** of F1. The
two arms at those ends — `mistral_s` at $0.0076 and `anthropic_l` at $0.6897 — actually
differ by **15.6 points**, so the regression understates this particular pair by half;
it is a fit across 24 arms, not a prediction about two. Either way a **free** local
model beats the top of that range by 11.4%.

### The same picture at production scale

"Role" is the arm's place in that experiment: the best arm overall, the dearest, and the
best paid or best free arm. The last column is the arm's score relative to that
experiment's best arm (the "best" row), so −8.9% means 8.9% below it.

| experiment | role | arm | quality | $/month at 1M items | quality vs best arm (relative) |
|---|---|---|---|---|---|
| **Summarisation · CNN/DM** | best | `bart_l` (local) | 0.3461 | **free** | — |
| | dearest | `anthropic_l` | 0.3155 | **$9,826** | **−8.9%** |
| | best paid | `deepseek_m` | 0.3460 | $191 | −0.0% |
| **Classification · AG News** | best | `bert_base_ta` (local) | 0.9600 | **free** | — |
| | dearest | `anthropic_l` | 0.9000 | $875 | −6.3% |
| | best paid | `anthropic_m` | 0.9100 | $351 | −5.2% |
| **Classification · DBpedia** | best | `qwen_m` | 0.9929 | **$51** | — |
| | dearest | `anthropic_l` | 0.9893 | **$1,351** | **−0.4%** |
| | best free | `bert_base_fy` (local) | 0.9857 | **free** | −0.7%, not separated |
| **Extraction · Few-NERD** | best | `span_marker` (local) | 0.7674 | **free** | — |
| | dearest | `anthropic_l` | 0.6798 | **$2,463** | **−11.4%** |
| **Retrieval · SciFact** | best | `glm_s` | 0.7437 | $711 | — |
| | dearest | `glm_m` | 0.7419 | $2,288 | −0.2% |
| **Judging · SummEval** | best | `openai_l` | 0.5398 | $6,350 | — |
| | dearest | `anthropic_l` | 0.5283 | **$20,077** | −2.1% |
| | best free | `unievalpub` (local) | 0.3717 | **free** | **−31.1%**, separated |

One row per experiment, since each says something different:

- **Summarisation: $9,826/month buys −8.9%** against free, while the best paid arm, at
  **$191/month, gets within −0.0% of free.** The dearest arm is beaten by a model costing
  51× less.
- **AG News: $875/month buys −6.3%** against free. The gap to the best paid arm
  ($351/month) is −5.2%, so here the money is buying a *deficit* either way — with the
  caveat that the free arms' lead is largely agreement with disputed gold labels.
- **DBpedia: $1,351/month buys −0.4%** against $51/month — 26× the price for slightly
  worse output, and not statistically separable. **And $51/month buys +0.7% over free**,
  also not separable.
- **Few-NERD: $2,463/month buys −11.4%** against a free model on a CPU. The largest
  free-vs-paid gap in the set, and the free arm separates from all 27 opponents.
- **SciFact: $2,288/month buys −0.2%** against $711/month, and the $711 arm buys **+3.4%
  over free** — a case where paying is defensible, and even there the free arm is not
  statistically separated from it.
- **SummEval: $20,077/month buys −2.1%** against $6,350/month, and the best free scorer,
  UniEval, is **−31.1%** — the one experiment where no free arm comes close. Even
  there the answer need not be rented: `gemma_l`, tied with the leader, has open weights and
  bills $278/month rented.

In no experiment did the most expensive option win (SciFact's was the dearest of twelve
cheap models). In three of six the free option
ranked first, and on Few-NERD it is separated from everything.

### What "free" actually gets you, in all six

The free-vs-paid comparison in full. Free loses once: on SummEval, where even the free arm
trained for the task lost, and there by a margin no test was needed to see.

The verdict's percentage is the winner's lead **relative to the lower of the two scores**
(+11.8% = 0.7674 ÷ 0.6864 − 1), whereas the table above measures everything relative to the
best arm — which is why Few-NERD reads −11.4% there and +11.8% here. "Separated" is the
Holm test between the two arms.

| experiment | best free arm (size) | free quality | free rank | best paid arm | paid quality | paid $/month at 1M items | verdict (lead relative to the lower score) |
|---|---|---|---|---|---|---|---|
| Extraction · Few-NERD | `span_marker` 499 MB | 0.7674 | **1** | `openai_m` | 0.6864 | $2,324 | **free wins +11.8%**, separated |
| Classification · AG News | `bert_base_ta` 438 MB | 0.9600 | **1** | `anthropic_m` | 0.9100 | $351 | free leads +5.5%, **not separated** (p = 0.022 vs 0.0167) |
| Summarisation · CNN/DM | `bart_l` 1.6 GB | 0.3461 | **1** | `deepseek_m` | 0.3460 | $191 | free leads +0.0%, **not separated** (p = 0.99) |
| Retrieval · SciFact | `e5_base` 438 MB | 0.7191 | 8 | `glm_s` | 0.7437 | $711 | paid wins +3.4%, **not separated** |
| Classification · DBpedia | `bert_base_fy` 438 MB | 0.9857 | 3= | `qwen_m` | 0.9929 | $51 | paid wins +0.7%, **not separated** |
| Judging · SummEval | `unievalpub` 3.1 GB | 0.3717 | 24 | `openai_l` | 0.5398 | $6,350 | **paid wins +45.2%**, separated |

*The SciFact rank is 8th against the corrected-parser runs in `data/runs-reparsed/`, which
are the retrieval report's record (`qwen_s` 0.7183). A plain `leaderboard.py` over
`data/runs/` reads the original-parser `qwen_s` (0.7338) and puts `e5_base` 9th.*

**DBpedia has a zero-shot control at the same price:** `bart_mnli` scores **0.6286** and
the fine-tuned `bert_base_fy` **0.9857** — **+0.357 from training exposure**, on a task where
the difference between the best and the fifteenth paid arm is under 0.02.

So the axis is not free-versus-paid. It is:

> **trained on your task's data** → beats or ties everything, at $0 — in four of four
> experiments that had one
> **trained for another task, another corpus, or nothing** → loses, also at $0 — except
> SciFact's retrieval-trained encoders, which tie

SummEval is the case neither line covers: a free model trained for the task, partly on
examples built from its own corpus, that still loses. BARTScore was fine-tuned on
this very corpus, to *write* summaries, and asked to *judge* them it finishes below every
one of the 24 hosted judges. UniEval was trained *to judge* these four dimensions, and it
finishes below 23 of the 24 (`unievalpub` 0.3717 on its own inputs; the SummEval row above
uses it). UniEval trains in two stages: first on existing datasets for related tasks (inference, paraphrase, sentence acceptability, yes/no questions) and an opening-sentence task on CNN/DailyMail, then on each dimension with reference summaries as positives and rule-based corruptions of them as negatives. Its paper names no human judgements of summaries in either stage. Why it loses is not tested, and one case is not enough to draw a
new rule from.

Few-NERD shows its size against a control: `span_marker` (fine-tuned on Few-NERD) scores
0.7674 and `gliner` (zero-shot, never trained on it) scores 0.4540 — **+0.3134**, with
price held at zero on both sides. The two also differ in architecture and encoder, so that
is exposure plus architecture; summarisation's BART pair is the matched one.

SciFact is the genuinely marginal case and deserves its own reading: `e5_base` is
retrieval-*trained* but not on SciFact specifically, and it lands mid-field — beaten by
0.0246 which the separation test cannot resolve. That is what "partially trained for the
task" looks like: not a win, not a rout, and cheap enough that $711/month for +3.4% is a
real decision rather than an obvious one.

**And free is not only cheaper, it is faster.** `bert_mini` answers in 7 ms against
1.92 s for the best paid arm on the same task — **270×**, both timed on the same Mac — the
bert-base fine-tunes in 76–90 ms on a Linux machine (about 10–25×, a cross-machine ratio),
and `e5_base` in 0.06 s against 3.12 s. The exception is `bart_l` at 11.01 s on the Mac —
third-slowest of 29, behind two hosted arms (`mistral_l` 11.04 s and `qwen_s` 25.04 s). It
is a 1.6 GB seq2seq model generating on a CPU. Re-timed with its distillations on one
Linux machine, `bart_l` takes 6.3 s, `bart_m` 4.1 s and `bart_s` 3.4 s
(`harness/data/runs-linux/`); even the fastest is slower than 17 of the 24 hosted arms (their
Mac timings, so again a cross-machine comparison). Free buys latency on *classification and embedding*, and costs it on
*generation*.

### The cheapest arm you cannot tell apart from the best

Eyeballing "within 2%" is not a test. Using Holm separation — the cheapest **paid** arm
that the winner does **not** statistically separate from. The second column counts the
winner's opponents only (the winner itself is not included), the same count as §2's
"group of N"; the last compares that arm's bill with the dearest paid arm's in the same
experiment:

| experiment | arms the winner cannot separate from | cheapest paid arm among them | its billed $ per 1,000 items | how much cheaper than the dearest paid arm |
|---|---|---|---|---|
| Summarisation · CNN/DM | 15 arms (13 paid) | `deepseek_s` | $0.069 | **143× cheaper** |
| Classification · DBpedia | 19 arms (18 paid) | `gemma_m` | $0.012 | **115× cheaper** |
| Classification · AG News | 3 arms (1 paid) | `anthropic_m` | $0.351 | **2.5× cheaper** |
| Retrieval · SciFact | 12 arms (10 paid) | `deepseek_s` | $0.300 | 7.6× cheaper |
| Judging · SummEval | 5 arms (5 paid) | `gemma_l` | $0.278 | **72× cheaper** |
| Extraction · Few-NERD | 0 arms | — | — | *no paid arm ties the winner* |

**In four of six experiments you can drop 7.6× to 143× of your inference bill and the data
cannot detect the difference.** On AG News the row reads the fine-tuned leader's group,
whose only paid member is `anthropic_m`, the second-dearest, so the saving there is 2.5× —
and the real answer on AG News is the free arm, as on Few-NERD, where no paid arm is
indistinguishable from it. If you rent rather than fine-tune on AG News, read the paid
leader's group instead: `anthropic_m` ($351 per 1M items, 0.9100) is separated from only 3
of the 23 other hosted arms, and the cheapest it is not separated from is `gemma_m` ($8,
0.8550; 0.0550 behind, p = 0.0081 against 0.0025), with `qwen_m` ($35, 0.8850) between. Start
with `gemma_m`.

### Cost rarely buys speed

Sorted by r. Latencies are mean seconds per item from the stored runs, except the
re-timed Linux figures for the BARTs, which are medians from `harness/data/runs-linux/`.

| experiment | Pearson r, log(cost) vs latency (hosted) | hosted latency per item, min–max | fastest local arm, latency per item |
|---|---|---|---|
| Judging · SummEval | **r = −0.47** | 1.12 – 12.35 s | `length` and `random`, ~0 s (the rule-based ROUGE and `coverage` 0.18–0.89 s; the learned local arms, BARTScore 15.66 s on the cloud runner and UniEval 41.68–44.69 s on the EVO-X3, different machines) |
| Extraction · Few-NERD | **r = −0.19** | 0.79 – 10.25 s | `gliner` 0.17 s |
| Summarisation · CNN/DM | r = −0.18 | 1.28 – 25.04 s | `bart_s` 3.39 s (`bart_l` 6.26 s), one Linux machine; `bart_l` 11.01 s on the Mac |
| Classification · DBpedia | r = +0.02 | 0.44 – 12.35 s | `bert_base_fy` **0.087 s** |
| Retrieval · SciFact | r = +0.03 | 1.14 – 17.48 s | `bge_small` 0.03 s |
| Classification · AG News | r = +0.20 | 0.44 – 7.66 s | `bert_mini` **0.007 s** |

Essentially uncorrelated in five experiments, and negative twice. **Price is not a proxy
for latency**, and the spread *within* the hosted field (up to 28×, on DBpedia) dwarfs
anything cost predicts. The exception is SummEval, where the dearer judges were faster
(r = −0.47); this report does not measure why, and its judges were called from a different
machine and gateway than the other five experiments' hosted arms, so its latencies are not on
the same footing as theirs.

Local models are a different regime entirely: `bert_mini` answers in **7 ms** against
0.44–7.66 s for hosted arms on the same task — 61× to 1,078× faster, with no network in the
path. The bert-base fine-tunes, ten times larger, take 76–90 ms, timed on a different (Linux)
machine: roughly 5× to 140× faster than any hosted arm on their tasks, a cross-machine
ratio good to about a factor of two. On one machine `bert_mini` is 11–13× faster than
them (`harness/data/runs-linux/`). What they cost instead is **setup**: e5-base takes 1,386 s to embed the SciFact
corpus once on a 4-vCPU machine, BM25 takes 1.2 s for the same job. That is a real cost, it is reported as
`warmup_ms` rather than hidden, and it is paid once rather than per item.

### The task shape sets the bill, not the model

Cost per item varies more across *tasks* than across *models*:

| task | input tokens per item | why |
|---|---|---|
| classification | ~104 | one snippet in, one word out |
| NER | ~125 | one sentence in, a short JSON array out |
| summarisation | ~776 | a full news article in |
| LLM judging (SummEval) | ~2,095 | an article and its 16 summaries in, 64 scores out as JSON |
| **retrieval reranking** | **~3,926** | the prompt carries **20 full abstracts** |

A reranking prompt costs **38× more per item** than a classification prompt on the same
model at the same price (3,926 vs 104 input tokens, measured). Before shopping for a
cheaper model, check whether the *architecture* is what is expensive: on the SciFact dev
slice, halving the rerank depth from 20 to 10 cut input tokens from 3,926 to 2,027 — a
**48% bill reduction** — for 0.011 nDCG@10. Both halves of that comparison ran under the
same (pre-reasoning-fix) instrument, so the delta is internally valid but is not
comparable to the measurement table above.

No model substitution in any of these six experiments moved cost that far for that
little.

## What this means if you are choosing a model

Ordered by what they are worth, not by how obvious they are.

1. **Start with the task shape, not the model.** A reranking prompt costs 38× per item
   what a classification prompt does on the same model. The largest cost lever here was
   architectural, and no model choice could recover it.
2. **If you have labels for a fixed taxonomy, fine-tune a small model — on your own
   data.** The best fine-tune ranked first in three of six and third-equal, not separable
   from the leader, in a fourth (DBpedia); SciFact and SummEval had none fine-tuned for the
   task. How few labels still work was not measured: the public fine-tunes here were
   trained on their corpora's own training splits. It costs
   **$0/month against up to $9,826/month**, with lower latency on classification —
   61×–1,078× for `bert_mini` against the hosted field on the same Mac, roughly 5×–140× for
   the bert-base fine-tunes timed elsewhere. On someone else's data of the same task it
   finished last. This is the single biggest lever in the table.
3. **Do not default to the most expensive arm.** `anthropic_l`, the dearest in five
   experiments, was never first, and in three it was *worse* than free while costing
   $875–$9,826/month. SciFact had no frontier tier, so its dearest arm says nothing about
   frontier models; the dearest still beat the cheapest in 5 of 6.
4. **Pick the cheapest arm your test cannot separate from the leader.** That is 7.6×–143×
   cheaper than the dearest in four of six, 2.5× on AG News against the fine-tune's group
   (renting there, start with `gemma_m`, $8 per 1M items), and on Few-NERD no paid arm is
   indistinguishable from the free leader. Requires a separation test, not a
   leaderboard — "ahead on the average" was true of the leader in 100% of cases and meant
   almost nothing.
5. **Do not select on a pilot.** ρ ≈ 0.8 feels like enough and picked the wrong winner
   three times in the five experiments that ran one. Use the pilot to catch instrument
   bugs, which is what it is genuinely good for.
6. **Read the items your whole field gets wrong before you read the ranking.** On a
   saturated benchmark that is where the ceiling is, and on one rater's reading of DBpedia
   it is annotation rather than capability.
7. **Budget attention for the scorer, not just the model.** Three separate scoring bugs
   here moved an arm further than most model swaps did.

**When paying more IS right**, and this report should not be read as saying never: when
you cannot label data and the task is unlike anything a small model was trained on
(on SummEval the one free evaluator trained for it, scoring one summary at a time, lost to 23 of the 24 LLM judges ranking all 16 at once); when the
quality
difference is worth more than the bill (at 1,000 items/month the entire
DBpedia spread is $1.35 and the analysis is not worth your time); when a single wrong
answer is expensive; or when engineering time to fine-tune and host costs more than the
API. The finding is not that expensive models are bad — it is that **the dearest model
tested was never the best, and near the top a large price range sat inside differences this
much data could not resolve**, so the premium has to be justified by
something other than the leaderboard.

## What this cannot say

- **The hosted LLMs ran as configured, not at their best.** One prompt per task, no
  examples in the prompt, temperature 0, reasoning off, no retrieval. A fine-tune "beats
  every LLM" means it beats them as they were run; an LLM given your labelled examples in
  the prompt, or allowed to reason, is the obvious rival to a fine-tune and was not
  measured. On SummEval the judges also scored all 16 summaries in one listwise call, while
  UniEval scores one summary at a time — a design difference as well as a model one.
- **All six benchmarks are public and some are years old**, so their text, and in places
  their labels or scores, may be in the hosted models' training data. Contamination is not
  measured anywhere here.
- **"Not separated" is not "equal".** Every tie in this report is a difference that 100–280
  items cannot resolve. No equivalence margin is set or tested; on AG News a five-point gap
  is still a tie.
- **The summarisation sample is CNN, not CNN/DailyMail.** All 200 of its articles are
  CNN's; the test split is 91% DailyMail. The DailyMail slice
  ([REPORT_SUMMARIZATION §3.7](REPORT_SUMMARIZATION.md#37-does-it-hold-outside-cnn-the-dailymail-slice))
  re-ran the five local arms, and every one of their comparisons held; the hosted arms
  could not be re-run from the environment that found it, so whether the *paid*
  comparisons travel is measured for none of them.
- **SummEval's 93% and 64% carry caveats.** The 93% is the best of 24 judges, chosen on the
  same articles (92% when chosen on half the articles and scored on the other half). A
  no-model lookup of which system wrote each summary reaches 63% of an expert, so how much of
  a judge's score is reading the summary rather than recognising its system is not measured.
  The summaries are 2019-era systems', reasoning was off, and the judges scored all 16
  summaries in one listwise call where UniEval scores one at a time (REPORT_SUMMEVAL §3.7).
- **Six tasks, all English, all text.** No multilingual, multimodal, long-context or
  agentic task. Summarisation is the only one whose output is free text; judging is the
  only one that grades other systems' output. The
  tie-at-the-top result may be a property of *saturated-ish academic benchmarks* rather
  than of frontier models.
- **One pass per arm, temperature 0.** Every interval here is over *items*, never over
  *runs*. Run-to-run variance is real and, for hosted arms, unmeasured — two runs of an
  repeated SciFact configs differ by σ ≈ 0.0045 per run (REPORT_RETRIEVAL, "Between-run variance"), and on
  SummEval `gemma_l` scored 0.0113 apart on the same text from two providers in one run
  each (REPORT_SUMMEVAL §3.3). No leaderboard run pinned a provider; which upstream served a
  call varies by arm — single-provider for the proprietary arms, up to 14 providers in one
  run for some open-weight ones. For the local arms of summarisation and classification it is measured and zero: all
  nine re-ran byte-identically, six on the same machine and `bart_l`, `lead3` and
  `bert_mini` on a different one (`bert_mini`'s confidences moved by ≤ 2 × 10⁻⁶, its
  labels not at all). The NER and retrieval local arms were not re-run.
- **24 hosted arms, one snapshot in time, no verifiable identity.** A provider can change
  weights behind an alias; runs record `identity_declared: true`, not proof. A provider can
  also withdraw a model: `qwen_l`'s was no longer served by the SummEval run, so there the
  Qwen large tier is `qwen37max`, a different model under a different arm name.
- **Twelve of the 24 hosted arms never ran on SciFact.** The sweep took only models under
  $0.60/Mtok input, which left out the whole frontier tier (its five arms alone would
  have cost ≈$12 against that sweep's $1.94 billed), so §1 and §2 are weaker there than
  elsewhere.
- **Each fine-tuned arm is one checkpoint.** DBpedia's tie and AG News's win are each a
  statement about one or three public fine-tunes, not about fine-tuning in general, and
  every one of them was tested on the distribution it was trained on.
- **The summarisation experiment's own metric agrees with experts less than ROUGE-1.**
  Measured on SummEval, `coverage` reaches τ 0.1011 against the experts, below ROUGE-1's
  0.1487 (REPORT_SUMMEVAL §3.3). The summarisation findings are separations under that
  metric; how far a `coverage` lead tracks what a person would prefer is that much weaker.
- **Nothing here measures factual accuracy, safety, or instruction-following.** ROUGE is
  n-gram overlap; accuracy is label match. A confident, fluent, wrong answer scores well on
  several of these metrics, and the reports say so individually.
- **§5 is four corpora, not six.** Two were never checked for gold errors, and their
  absence from the table is a gap, not a clean bill.
- **The economics in §8 price inference and nothing else.** No engineering time to
  fine-tune or host a local model, no GPU rental, no maintenance, no serving
  infrastructure, no cost of a wrong answer. "Free" means *zero inference cost*, and a
  local model that takes a week to set up is not free in any sense a business recognises.
- **The 1M-items/month projections are linear extrapolations** from 100–280 item runs.
  They ignore volume discounts, batch pricing, caching, and rate limits — all of which a
  real deployment at that scale would negotiate or hit. Treat them as *ratios* that are
  sound, and absolute figures that are indicative.
- **Prices are two snapshots**, taken 2026-09-28/29 for the first five experiments and
  2026-10-18 for SummEval, through one reseller, and several had moved in between. Model
  pricing moves fast and the ordering of vendors is the least durable finding here. The
  *structure* — that the dearest model tested is not the best, and that near the top the price
  range sits inside differences this much data cannot resolve — is what is expected to
  survive.

## Corrections

Every figure this report stated wrongly, or stated and later changed, kept here with its
date so the sections above can describe only the present state. The append-only journal of
how each finding arrived — including the ones that were retracted — is
[`NOTES.md`](internal/NOTES.md).

### 2026-09-29

- **The open-weight split was 13/11 and is 14/10.** The first version of the tier section
  inferred openness from OpenRouter's endpoint list — *many independent providers implies
  distributable weights; one provider implies closed*. The first half holds; **the second
  does not.** `mistral_l` is served only by Mistral and was filed as proprietary, but
  `mistralai/Mistral-Large-3` is on HuggingFace under **Apache-2.0**. A vendor can publish
  weights and still be the only one serving them. Found by review; every figure in that
  section was recomputed.
- **DeepSeek-V4.1-Flash's checkpoint is 510 GB; the ~765 GB first stated was derived, never measured.**
  *This report said ~765 GB until 2026-09-29, and that number was never measured.* It
  came from multiplying HuggingFace's per-dtype **element** counts by one byte for the
  763B elements tagged `I8`. Those tensors are packed at roughly four bits: 763.2B
  parameters occupy 510.3 GB across 48 safetensors shards, which is **0.67 bytes per
  parameter**. The same mistake inflated DeepSeek-V4-Pro (1,602 → 865 GB) and
  DeepSeek-V4-Flash (292 → 160 GB); the other 20 models in the capture are unaffected,
  their derived and measured sizes agreeing to within 3%. The conclusion did not move —
  510 GB is still far beyond one 128 GB box — but the figure was wrong by half again,
  and it was wrong because it was computed rather than read. Found by external review;
  the evidence capture now records measured bytes and `check_model_facts.py` reads the
  claim out of this file rather than out of its own source.

### 2026-09-30 — the six local arms that could not run on the original machine

They need torch ≥ 2.6 and ran at $0. They changed two headline claims and several rows;
no conclusion about price reversed.

- **"Every model fine-tuned on its dataset ranked first" was 3 of 3.** With eight such arms
  it is true of the best one per experiment in three of four and not of every one:
  distillation costs `bart_m` and `bart_s` a few places without a separable loss, and
  DBpedia's fine-tune is not separated from the top group and does not beat it. On AG News
  the fine-tuned lead is now measured as concentrated in 17 items the hosted field mostly
  gets wrong.
- **The free-vs-paid summary read "two clear wins, two ties, one loss",** and the loss was
  DBpedia — where the only free arm that had run was `bart_mnli`, a zero-shot NLI model,
  because the fine-tuned checkpoint would not load. Run on a machine with torch ≥ 2.6, the
  fine-tune is not separated from the top group.
- **DBpedia's free row was `bart_mnli`, zero-shot, 25th, "paid wins +58%".** The fine-tuned
  checkpoint is a pickle that `transformers` refuses below torch 2.6
  ([CVE-2025-32434](https://github.com/advisories/GHSA-53q9-r3pm-6pq6)) and the original
  machine had no newer torch. The §8 bullet likewise said "the one experiment where paying
  beats free by a mile (+58%)"; that was against a zero-shot arm, because the fine-tuned one
  had not run.
- **DBpedia's row in the self-hosting table read "blocked — LLM by default".** The ML arm
  loads on any machine with torch ≥ 2.6, and ties. DBpedia's $0 answer used to need a 52 GB
  open-weight LLM; a 438 MB classifier on a CPU reaches the same score.
- **The best open-weight vs best proprietary table had two errors, both found by external
  review.** The summarisation row read **"yes — open wins"**. That rested on an UNCORRECTED
  pair test of a pair nobody registered in advance — the winner's curse the rest of this
  repo is built to avoid. Under Holm over `deepseek_m`'s declared family it is not
  separated (the note then said p = 0.0070 against 0.0063; `family_test.py` gives
  p = 0.0069 against 0.0050 on 2026-10-19, and neither separates). The point estimate
  still favours the open-weight model by 0.0192. The SciFact row named `glm_m` as "best
  proprietary"; **GLM is open-weight** — MIT. The genuine best proprietary reranker is
  `qwen_s` at 0.7183, a gap of 0.0254 that its own test also cannot resolve (p = 0.0283
  against a 0.0050 threshold). A line under the table then said "won outright on
  summarisation" after the correction had retracted exactly that.
- **AG News's cheapest-tied row read "9 arms, `gemma_s`, 82× cheaper",** around `bert_mini`.
  The new leader, a bert-base fine-tune, is separated from every paid arm but `anthropic_m`,
  the second-dearest, so the saving there is 2.5×. The separation table likewise read
  `bert_mini`, 18 of 27, a group of 9; the new leader's group is two other fine-tunes and
  `anthropic_m`, the last at p = 0.022 against a 0.0167 threshold.
- **The `bert_mini` latency ratio read 44×–766×,** computed from 10 ms rather than the
  measured 7.11 ms; it is 61×–1,078×.
- **The SciFact rank in the free-vs-paid table read 9th,** from a plain `leaderboard.py` over
  `data/runs/`, which reads the original-parser `qwen_s` (0.7338). It was changed to 8th,
  against the corrected-parser runs, without a note.
- **Local arms: 16 task-specific, 10 until 2026-09-30.**

### 2026-10-01

`fn_mistral_l`, the NER arm that had been rate-limited, finally got past its upstream rate
limit for $0.0419.

### Arm counts and the bill

The report said 127 arms until 2026-09-30, when six local arms that need torch ≥ 2.6 were
run at $0; 133 until 2026-10-01, when `fn_mistral_l` ran; 134 until SummEval's 31 arms were
run for $7.03 (its free arms on 2026-10-15, its judges on 2026-10-18); and 165 until
2026-10-19, when its two UniEval arms, run on 2026-10-18, were added at $0. That is 167.

### 2026-10-14 — scope of the summarisation experiment

The summarisation experiment's 200 articles are the first 200 rows of the CNN/DailyMail test
split, and the split puts CNN's articles first: they are **all CNN articles**, while the
split is 91% DailyMail. Every summarisation figure here is therefore about CNN-style news.
Found by the first calibration against the literature (LEAD-3 on the full test set: ROUGE-1
39.94 here, 40.34 published; 30.20 on the slice). A seeded DailyMail slice tested whether the
conclusions travel
([REPORT_SUMMARIZATION §3.7](REPORT_SUMMARIZATION.md#37-does-it-hold-outside-cnn-the-dailymail-slice)):
among the five local arms **every comparison transfers**, including the house-style control
(BART on XSum still last). The hosted arms were not re-run, so **the summarisation price
verdicts are CNN-only**. Every other experiment was calibrated the same way and needed no
correction: all seven calibration figures then, and all eleven with SummEval's four, agree
with the published values on their averages within the protocol's allowance, and ten of the
eleven inside their own interval; LEAD-3 is the exception, outside its interval and inside
the allowance ([`docs/PROTOCOL.md`](../docs/PROTOCOL.md)), and SummEval's ROUGE-L agrees only
within the allowance on one dimension (REPORT_SUMMEVAL §5).

### 2026-10-15

The SciFact leader's separation count read 7 of 18 and a group of 11; the default-setting
figure, 6 of 18 and a group of 12, is the one §8's tie table uses.

### 2026-10-18 — SummEval added as the sixth experiment

Two figures stated with it were wrong and were corrected on 2026-10-19:

- **A 64 GB machine matched the unlimited-hardware answer on "four of five" tasks.** That
  was the 128 GB count; at 64 GB both summarisation and SciFact lose, so it was three of five.
- **Few-NERD's cost slope read +0.0405 and r = 0.49.** It had been fitted to the un-rescored
  runs in `data/runs/`, while every other Few-NERD figure here is the rescored one. Fitted to
  the rescored runs it is +0.0407 and 0.50, and the percentage does not move.

### 2026-10-19 — UniEval, and a review of this report against the five reports

- **Finding 3 as worded — "a free arm trained for the task never loses" — was broken** by the
  UniEval arms, run on 2026-10-18 and written in on 2026-10-19: on SummEval, UniEval is
  separated below 23 of the 24 judges and ties only the weakest. The finding, the
  free-vs-paid summary clause ("where no free arm measured was trained for the task") and
  the table of the best free arm per experiment now say so (§3).
- **The 64 GB column was rebuilt.** It had listed Llama at int4 for AG News and
  summarisation and Gemma-4-31B at int8 for SummEval, each with its as-served score, which is
  no evidence about the quantised build (REPORT_SUMMARIZATION says so for Llama at 4 bits;
  REPORT_CLASSIFICATION marks AG News's 64 GB answer "Not measured"). It now lists the best
  model that fits 54.4 GB at native precision. The headline "on four of the six tasks the
  best model that fits a 64 GB machine scored the same as the unlimited-hardware answer"
  became two of six, plus two where only an unrun int4 or int8 build would match; "five of
  six ≤64 GB answers equal the ≤128 GB one" became two of six; and the cost of capping the
  budget, "0.0078 and 0.0074", became 0.0205 on summarisation (separated; p = 0.0026 against
  0.0042) and 0.0614 on SummEval (separated) as well as 0.0074 on SciFact and 0.0200 on AG
  News (neither separated).
- **"A proprietary model never separated from the best open-weight model" was false read
  literally:** `anthropic_l` and `anthropic_m` are separated below `deepseek_m` on
  summarisation. What the table shows, and what is now stated, is that the best proprietary
  arm was never separated from the best open-weight arm.
- **"The dearest arm is never first, six times out of six" and "never buy the most expensive
  arm" are scoped.** SciFact's field had no frontier tier, so its dearest arm is the dearest
  of twelve cheap models; the claim is about `anthropic_l` in the five experiments where it
  ran, and the dearest beat the cheapest in 5 of 6.
- **"If you can label a few thousand examples" and "It will be better, free, and faster" were
  removed.** No report supports a label count (the public fine-tunes were trained on their
  corpora's full training splits; fewer-label behaviour was not measured), and the fine-tune
  was slower on summarisation (11.0 s against 1.6 s) and two items behind on DBpedia.
- **The "71st percentile" (and "70th across the first five") could not be reproduced.** It
  had no computation behind it. Recomputed from the committed runs it is the 67th percentile
  with ties counted half and the 72nd with ties counted fully in `glm_m`'s favour.
- **Finding 5 was titled "The gold is wrong or noisy".** The DBpedia disputes are one rater's
  reading and unadjudicated; the finding now says disputed or noisy, candidates and not
  proven errors.
- **AG News's rented-API choice was framed around the fine-tune leader's tie group,** whose
  only paid member is `anthropic_m`. The report's advice is the paid leader's group:
  `anthropic_m` is separated from only 3 of the 23 other hosted arms, and the cheapest it is
  not separated from is `gemma_m` ($8 per 1M items).
- **SummEval's 93% and 64% were stated without their caveats:** the 93% is the best of 24
  chosen on the same articles (92% held out), a no-model system-identity lookup reaches 63%,
  the summaries are 2019-era, reasoning was off, and the judges ranked listwise where UniEval
  scores pointwise.
- **The executive summary was rewritten** as a decision and per-task picks; the dated update
  banners that preceded it are the entries above.

---

## Reproduction

```bash
cd harness
# §1, §3 — cost and rank by experiment, from what the provider billed
python scripts/leaderboard.py --dataset-id few_nerd_280        # and the other five
# §2 — separation
python scripts/family_test.py --dataset-id few_nerd_280 \
    --a fn_span_marker_n200_v1 --against _n200_v1 --metric f1
# §4 — pilot vs full, and holdout
python scripts/holdout_significance.py --dataset-id few_nerd_280 \
    --exclude-dataset few_nerd_56 --metric f1 --match fn_
# §5 — gold errors
python scripts/extraction_report.py --dataset-id few_nerd_280 --match fn_
python scripts/classification_report.py --dataset-id dbpedia_280
# §7 — tie behaviour by metric shape
python scripts/rank_stability.py --dataset-id dbpedia_280 --metric correct --match db_
# SummEval's derived figures (split-half, price vs quality, ladders, dimensions)
python scripts/summeval_analysis.py
```

Terms, models, datasets and tests are defined in
[`../docs/REFERENCE.md`](../docs/REFERENCE.md). The append-only journal of how each finding
arrived — including the ones that were retracted — is [`NOTES.md`](internal/NOTES.md), 70 entries.
