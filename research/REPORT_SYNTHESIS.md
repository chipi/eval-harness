# What six experiments agree on

**Six tasks · five metric shapes · 167 measured arms · $19.07 billed · one harness**

*$19.07 is the 167 arms under `harness/data/runs/` — 127 until 2026-09-30, when six local
arms that need torch ≥ 2.6 were run at $0; 133 until 2026-10-01, when `fn_mistral_l`
finally got past its upstream rate limit for $0.0419; 134 until 2026-10-18, when
SummEval's 31 arms were run for $7.03; and 165 until 2026-10-19, when SummEval's two UniEval
arms were added at $0. Including the four paired runs behind the registered
prediction and the three hosted repeat runs, the repo has spent $20.10.*

> **Updated 2026-10-18 with a sixth experiment, SummEval** ([REPORT_SUMMEVAL](REPORT_SUMMEVAL.md)):
> 24 LLMs judging summaries against expert scores. It confirms the price findings and adds
> the first experiment where the free option loses: the best free scorer, UniEval — an
> evaluator trained for the task — is separated below 23 of the 24 judges and ties only the
> weakest. Run on 2026-10-19, after the rest, UniEval also changed finding 3: a free arm
> trained for the task can lose, and the line is now drawn at training on the task's own
> labels (§3). Two figures stated here before it were wrong, and are
> corrected below: a 64 GB machine matched the unlimited-hardware answer on **three** of the
> five tasks, not four (the 128 GB budget is the one that matched on four), and Few-NERD's
> cost slope was computed on the un-rescored runs (+0.0405, r = 0.49) while every other
> Few-NERD figure here is rescored (+0.0407, r = 0.50; the +5.9% does not move).

> **Updated 2026-09-30 with the six local arms that could not run on the original machine.**
> They changed two headline claims. "Every model fine-tuned on its dataset ranked first"
> was 3 of 3; with eight such arms it is *the best one in each experiment ranked first, or
> not separable from first* — DBpedia's fine-tune ties the top group, it does not beat it. And on AG
> News the fine-tuned lead is now measured as mostly agreement with disputed gold labels.
> No conclusion about price reversed.

> **Scope correction, 2026-10-14.** The summarisation experiment's 200 articles are the
> first 200 rows of the CNN/DailyMail test split, and the split puts CNN's articles first: they
> are **all CNN articles**, while the split is 91% DailyMail. Every summarisation figure
> below is therefore about CNN-style news. Found by the first calibration against the
> literature (LEAD-3 on the full test set: ROUGE-1 39.94 here, 40.34 published; 30.20 on
> the slice). A seeded DailyMail slice tested whether the conclusions travel
> ([REPORT_SUMMARIZATION §3.7](REPORT_SUMMARIZATION.md#37-does-it-hold-outside-cnn-the-dailymail-slice)):
> among the five local arms **every comparison transfers**, including the house-style
> control (BART on XSum still last). The hosted arms were not re-run, so **the
> summarisation price verdicts below are CNN-only**. Every other experiment was
> calibrated the same way and needed no correction: all seven calibration figures then,
> and all ten with SummEval's three, agree with the published values on their averages
> ([`docs/PROTOCOL.md`](../docs/PROTOCOL.md)); SummEval's ROUGE-L does so only within the
> protocol allowance on one dimension (REPORT_SUMMEVAL §5).

Seven findings, each tested in every experiment that could test it (§1–§7), and what they
imply for **quality vs cost vs latency** in production (§8).

A cross-cutting report. Each of the five underlying reports answers *"which model is best
at this task"*; this one asks what is true in **all** of them, and it is written because
several findings only became visible once there were several corpora to compare.

| dataset | task | primary metric (shape) | report |
|---|---|---|---|
| CNN/DailyMail | summarise a news article (**all 200 from CNN**) | `coverage` (continuous) | [REPORT_SUMMARIZATION](REPORT_SUMMARIZATION.md) |
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

Every number below is computed from the stored runs, not quoted from the reports.
Reproduction commands are at the end.

---

## Executive summary

**Across six tasks and 167 measured arms: the most expensive model was never the best,
five of six leaderboard tops are statistical ties, a small model fine-tuned on your data
ranked first in three experiments and third-equal — not separable from the leader — in a
fourth, always at $0, a 10× cost increase bought
between −0.4% and +7.4% of quality — and a 64 GB machine reached the same answer as
unlimited hardware on four of the six tasks** (two of the four at int8 or int4, which was
not measured). On the one task where the free arm trained for the job lost — judging
summaries — the best LLM judges reached 93% of a human expert's agreement (95% interval
89–97%; the best of 24, chosen on the same articles), and the best free scorer, UniEval,
64%.

**The production question — should you fine-tune a small model instead of paying an
LLM?** Yes, for a task you can define and label: in all four experiments with a model
fine-tuned on that dataset, the best one **ranked first in three** (Few-NERD, AG News and
— by 0.0001 — summarisation) and **third-equal on DBpedia**, two items behind the leader
and not separable from it. "Not separable" is weaker than it sounds on DBpedia: the leader
cannot separate from 19 of its 27 opponents, so the fine-tune sits in a large group, not
beside the winner. Every zero-shot model ranked **last** among the learned arms
(3 of 3), and so did BARTScore, a model fine-tuned to write CNN/DailyMail summaries and
used here to judge them; the one model fine-tuned on a *different* corpus of the same task ranked
**last of 29**. The predictor is training exposure to *your* data, not model size — and on
AG News what that exposure buys is largely the corpus's own labelling (§0).

**And "paying" splits in two.** 14 of the 24 hosted arms have **downloadable weights** and
could run on hardware you own — renting them was a convenience. Head to head, **a
proprietary model never separated from the best open-weight model in any of the six
experiments**, and open weights did not separate from proprietary either, in any. Summing every arm's bill at 1M items/month
across the experiments it ran, that tier costs **$24,187** rented and **$0 self-hosted**;
the 10 genuinely proprietary arms, and `qwen37max` in `qwen_l`'s place on SummEval, have no
self-host option, and their combined bill on the same basis is **$100,894**.

**Combining the two: every experiment has a $0 answer.** In four of six the
self-hostable option *is* the winner; in the other two it trails by 0.0071 (DBpedia) and
0.0013 (SummEval), neither of which the data can resolve. Across six unrelated tasks, the
best configuration runnable entirely on your own machines is either first or in the group
the leader cannot separate from — on SummEval only as an open-weight LLM, never as a small
model.

**And hardware buys almost nothing.** Of the 14 open-weight arms, several are cluster-scale
models, not workstation ones. But capping the budget costs almost no quality:
**five of six ≤128 GB answers equal the unlimited-hardware answer, and five of six
≤64 GB answers equal the ≤128 GB one**. Capping at 128 GB costs **0.0078** on one task
(summarisation, a 510 GB model replaced by a 70 GB one) and nothing on the other five;
halving it again to 64 GB also costs SciFact **0.0074** (`glm_s` 0.7437 → `gemma_m` 0.7363,
a gap its own test cannot resolve). So a 64 GB machine matched the unlimited-hardware
answer on four of the six tasks, two of them at int8 or int4, which was not measured.

The counter-argument is measured too: one hosted model covers all six tasks at the 71st
percentile with a prompt change, where each local model does exactly one. Full reasoning,
the three-tier breakdown, the memory budgets, and four ways it could be wrong:
[§0](#0-the-production-question-should-you-fine-tune-a-small-model-instead-of-paying-an-llm).

### The seven findings

| # | finding | evidence |
|---|---|---|
| **1** | **The dearest arm is never first** | 6 of 6. It ranked 18th of 29 (summarisation), 5th of 30 (AG News), 2nd of 28 (DBpedia), 3rd of 28 (Few-NERD), 2nd of 19 (SciFact) and 3rd of 33 (SummEval). But the dearest still beats the *cheapest* in 5 of 6 — price separates bad from mediocre, then stops. The best paid arm was **mid-tier** in four of six; the large tier won once, on SummEval, inside a six-way tie. |
| **2** | **The top is a group, not a podium** | Every winner leads on the point estimate against **100%** of its declared family, and separates from only **30–100%**. Few-NERD produced a real podium (separated from 27 of 27) and AG News nearly one (26 of 29); DBpedia's winner separates from 8 of 27. |
| **3** | **The axis is trained-on-your-task's-labels, not free-vs-paid** | A free arm ranks first in 3 of 6 (one by 0.0001) and is statistically tied with first in 2 more, every one trained on real labels for its task. On SummEval the one free arm trained for the task, UniEval, learned from synthetic labels and loses: separated below 23 of the 24 judges, tied only with the weakest. Until 2026-10-19 this row said a free arm never loses once one trained for the task can run; UniEval had not run, and the narrower line is drawn after its result (§3). Two matched pairs at price zero on both sides: `span_marker` 0.7674 vs `gliner` 0.4540 — **+0.3134 from exposure alone** — and BART fine-tuned on CNN/DailyMail vs on XSum, **1st vs 29th of 29**. |
| **4** | **A pilot correlates beautifully and picks the wrong winner** | ρ(dev, full) = **0.72–0.90** in every experiment that ran a pilot, and the pilot chose wrong in **3 of 5** (SummEval ran none). On SciFact it chose the **tenth-best of nineteen**; on AG News, now, the fifth of thirty. |
| **5** | **The gold is wrong, in every corpus that was checked** | 4 for 4 where anyone looked; 2 were never checked. SummEval's experts gave different scores to 41 of 44 groups of identical summaries. Few-NERD: **34 of 768** gold entity types rejected by ≥80% of the 26 learned arms. DBpedia's top eleven are separated by four items, three of which the field disputes. On AG News the fine-tuned lead sits almost entirely in **17 items** the hosted field disputes — fine-tunes agree with the gold on 12–14, `anthropic_l` on 0 (a set selected by the hosted arms' own errors; classification §3.4 says what it does and does not show). |
| **6** | **The instrument broke before the models got interesting** | In five of six. 8 defects tabulated; **3 moved a single arm further than the gap separating most of the field** — the label parser (8.6 accuracy points), the unparsed-as-empty rule (+0.0214 f1), the reasoning flag (0.6124 → 0.6991). |
| **7** | **The metric's shape decides which diagnostics can be read** | Not which model wins — which *tools* work. On DBpedia at n=10, **19.9 of 28 arms tied** and the rank statistic was correlating arm names; 354–399 of 400 resampling draws are undecided at every size, and in every decided one the two halves crown different arms. |

### The economics

**A 10× cost increase buys −0.4% to +7.4% of the best paid arm's quality** (r = −0.07 to 0.63).
On summarisation the slope is *negative* across 24 arms and a 143× price range; on SummEval
it is +7.4%, the largest as a share of the best score.

What the dearest arm in each experiment buys, at **1,000,000 items/month** as billed,
sorted by its bill (highest first). An item is one call: on SummEval that is a whole
article with its 16 summaries, which is why its bills lead the table. The last column is its score relative to the cheaper
option named, so −8.9% means 8.9% below it:

| experiment | dearest arm, $/month at 1M items | its quality vs the cheaper option (relative; − = worse) |
|---|---|---|
| Judging · SummEval | `anthropic_l`, $20,077 | −2.1% vs `openai_l` at $6,350/mo (and `gemma_l`, tied with the leader at $278/mo, is −0.3% vs it) |
| Summarisation · CNN/DM | `anthropic_l`, $9,826 | −8.9% vs free `bart_l` (and the best paid arm, `deepseek_m` at $191/mo, is −0.0% vs free) |
| Extraction · Few-NERD | `anthropic_l`, $2,463 | −11.4% vs free `span_marker`, on a CPU |
| Retrieval · SciFact | `glm_m`, $2,288 | −0.2% vs `glm_s` at $711/mo |
| Classification · DBpedia | `anthropic_l`, $1,351 | −0.4% vs `qwen_m` at $51/mo |
| Classification · AG News | `anthropic_l`, $875 | −6.3% vs free `bert_base_ta` |

Four more findings that travel:

- **The cheapest paid arm you cannot statistically separate from the best is 7.6×–143×
  cheaper than the dearest** in four experiments (72× on SummEval) — and on AG News, where
  the fine-tuned leader now ties with only one paid arm, 2.5×. Few-NERD has none.
- **Cost rarely buys speed.** log(cost) vs latency correlates at **r = −0.19 to +0.20** in
  five experiments — uncorrelated, negative twice. On SummEval it is **−0.47**: the dearer
  judges answered faster there, which this report does not explain. `bert_mini`
  (7 ms) runs 61× to 1,078× faster than the hosted field, timed on the same Mac. The bert-base fine-tunes (76–90 ms) come out roughly
  5×–140× faster, but they were timed on a different machine, so that ratio is good to
  about a factor of two. Generators run *slower*.
- **The task shape sets the bill, not the model.** 104 input tokens per item for
  classification against **3,926 for retrieval reranking** — a 38× difference that no
  model substitution recovers. Judging one article with its 16 summaries takes ~2,095.
- **Every experiment has a $0 answer.** In four of six the self-hostable option *is* the
  winner; in the other two it trails by 0.0071 and 0.0013, which the data cannot resolve.

### What to do with this

1. **Check the architecture before the model.** The largest cost lever here was structural.
2. **If you can label a few thousand examples, fine-tune a small model** — $0 against up to
   $9,826/month where one exists, and far lower latency on classification. Every task-specific winner here
   is **under 2 GB and needs no GPU**. Fine-tune on *your* data: the same BART trained on
   another corpus's summaries finished last.
3. **If you cannot, self-host an open-weight LLM before renting one.** A proprietary model
   never separated from the best open-weight arm in any experiment, and **a 64 GB machine
   matched the unlimited-hardware answer on four of the six tasks** (128 GB on five; two of
   the four at int8 or int4, unmeasured).
4. **Never buy the most expensive arm.** In three experiments it was *worse* than free, and
   on SummEval a judge tied with the leader cost 1/72 of it.
5. **Pick the cheapest arm your test cannot separate from the leader** — which requires a
   separation test, not a leaderboard.
6. **Do not select on a pilot**; use it to catch instrument bugs, which is what it is good at.

**When paying more is right:** you cannot label data; the task is unlike anything a small
model has seen — on SummEval even a free evaluator trained for it lost to 23 of the 24 judges; a wrong answer is
expensive; your volume
is low enough that the whole spread is rounding error (at 1,000 items/month the entire DBpedia range is $1.35); or
engineering time costs more than the API. The claim is not that expensive models are bad —
it is that **price stops predicting quality long before it stops rising.**

---

*The rest of this report unpacks each finding with its full evidence, and
[§8](#8-the-economics-what-money-actually-buys) has the complete economics. Each finding links to the experiment report it comes from; those
reports carry the per-task detail, the corrections, and what each one could not measure.*

---

## 0. The production question: should you fine-tune a small model instead of paying an LLM?

**Yes — for a task you can define and label. The best fine-tuned model is first, or not
separable from first, in 4 of 4, and it is not close on cost. But the answer depends entirely on one
variable, it is not model size, and on a saturated task it buys a tie rather than a win.
On SummEval no model trained to judge was measured, and the only local model there — a
summariser used as a judge — is separated below every LLM.**

### What actually predicts whether a free local model wins

Sorting all seventeen local arms by how much training on *this* data they had produces a
**monotonic** relationship — and the boundary is sharp. One row per arm, grouped from most
to least exposure. "Learned arms", here and below, means every arm that is a trained model:
all arms except the rule-based baselines (`constant`, `keyword`, `nothing`, `capitalized`,
`lead3`, `bm25`, `random`, `first_k`, and on SummEval ROUGE, `coverage` and `length`). The
last column is the arm's score minus the best **paid** arm's score in that experiment, in that experiment's metric, and the verdict of the
arm's own Holm family test against that paid arm: its p-value against the Holm threshold it
had to beat. "Not separated" means the test cannot tell the two apart. Every row was
re-run from the committed runs on 2026-10-15 (`scripts/family_test.py`, the arm against the
whole field).

| training exposure | experiment | arm | rank (of N arms) | quality minus best paid arm (that task's metric) |
|---|---|---|---|---|
| **Fine-tuned on this dataset** | Extraction · Few-NERD | `span_marker` | **1st of 28** | **+0.0810**, separated (p = 0.0001 vs 0.05) |
| | Classification · AG News | `bert_base_ta` | **1st of 30** | +0.0500, not separated (p = 0.022 vs 0.0167) |
| | Classification · AG News | `bert_base_fy` | 2nd of 30 | +0.0400, not separated (p = 0.077 vs 0.0167) |
| | Classification · AG News | `bert_mini` | 3rd of 30 | +0.0350, not separated (p = 0.116 vs 0.0167) |
| | Summarisation · CNN/DM | `bart_l` | **1st of 29** | +0.0001, not separated (p = 0.99 vs 0.05) |
| | Summarisation · CNN/DM | `bart_m` | 5th of 29 | −0.0094, not separated (p = 0.30 vs 0.0071) |
| | Summarisation · CNN/DM | `bart_s` | 10th of 29 | −0.0185, not separated (p = 0.054 vs 0.0023) |
| | Classification · DBpedia | `bert_base_fy` | 3rd= of 28 (five-way tie) | −0.0071, not separated (p = 0.62 vs 0.0050) |
| Fine-tuned on the task, **another corpus** | Summarisation · CNN/DM | `bart_l_xsum` (XSum → CNN/DM) | **29th of 29 — last** | **−0.1390**, separated (p < 0.0001 vs 0.0024), and from all 28 opponents |
| Trained for the task, on this corpus, from **synthetic labels** | Judging · SummEval | `unievalpub` (UniEval, on its own inputs) | 24th of 33 | **−0.1680**, separated (p < 0.0001 vs 0.0063), and below 23 of 24 judges |
| | Judging · SummEval | `unieval` (UniEval, on this experiment's inputs) | 26th of 33 | **−0.1922**, separated (p < 0.0001 vs 0.0056), and below 23 of 24 judges |
| Fine-tuned on this corpus, **another task** | Judging · SummEval | `bartscore` (a CNN/DM summariser, used as a judge) | 27th of 33 — **last learned arm** | **−0.2836**, separated (p < 0.0001 vs 0.0017), and below all 24 judges |
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
fine-tuned to summarise CNN/DailyMail and asked here to judge summaries of it. Until
2026-09-30 the first sentence read "every model fine-tuned on its dataset ranked first",
3 of 3. With eight such arms it is true of the best one per experiment in
three of four and not of every one: distillation costs `bart_m` and `bart_s` a few places
without a separable loss, and on DBpedia the fine-tune lands in a five-way tie for third,
two items behind the leader — inside the 19-arm group the leader cannot separate from,
which is a weak kind of tie.

**The cleanest proofs are matched pairs with price held at zero on both sides.**
`span_marker` and `gliner` are the same model class on the same task, differing only in
whether they saw Few-NERD's training split: **+0.3134 F1**, larger than the spread of the
24 hosted arms on that task. And `bart_l` against `bart_l_xsum`: the same BART-large,
fine-tuned for summarisation both times, one on CNN/DailyMail and one on XSum — **1st and
29th of 29**. The XSum model scores below LEAD-3. "Trained for the task" is not the
variable; "trained on text like yours" is — and SummEval narrows it further. UniEval was
trained for the task, on CNN/DailyMail text, and still loses to 23 of 24 judges; its labels
were rule-based corruptions of reference summaries, not anyone's judgements. What every
winning free arm had is labels made for its task on text like yours.

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
factor of two. On DBpedia the quality is a statistical tie that the paid arm
leads by two items in 280. On summarisation the quality is a tie and the local model is
*slower*, because generation on a CPU is genuinely expensive. Distillation takes a third
(`bart_m`) to nearly half (`bart_s`) off `bart_l`'s time on the same machine, and the win
there is still cost only.


### Three tiers, not two: the "paid" arms split in half

Calling the 24 hosted arms "paid" conflates two very different things. **14 of them have
downloadable weights** and could run on hardware you own; paying OpenRouter for them was a
convenience, not a requirement. The other 10 have no such option.

Verified against the HuggingFace API on 2026-09-29.

> **A correction, because the first version of this section used a broken test.** It
> inferred openness from OpenRouter's endpoint list — *many independent providers implies
> distributable weights; one provider implies closed*. The first half holds; **the second
> does not.** `mistral_l` is served only by Mistral and was filed as proprietary, but
> `mistralai/Mistral-Large-3` is on HuggingFace under **Apache-2.0**. A vendor can publish
> weights and still be the only one serving them. Found by review; the split is 14/10, not
> 13/11, and every figure in this section is recomputed.

| tier | arms | what you can do with it |
|---|---|---|
| **1 · Local ML** | 18 local models: 16 task-specific (10 until 2026-09-30), and BARTScore and UniEval on SummEval | download, fine-tune, self-host. $0 at the margin |
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
| Judging · SummEval | `gemma_l` 0.5384 | `openai_l` 0.5398 | −0.0013 | no (p = 0.8554 vs 0.0500, `gemma_l`'s own family test) |

**A proprietary model never separated from the best open-weight model. Not once in six —
and now neither did open-weight, in the one row where it appeared to.**

*Two corrections to this table, 2026-09-30, both found by external review.*

*The summarisation row read **"yes — open wins"**. That rested on an UNCORRECTED pair
test of a pair nobody registered in advance — the winner's curse the rest of this repo
is built to avoid. Under Holm over `deepseek_m`'s declared family it is **p = 0.0070
against a 0.0063 threshold: not separated.** The point estimate still favours the
open-weight model by 0.0192; it is simply not a separation, and calling it one was
picking the comparison after seeing the leaderboard.*

*The SciFact row named `glm_m` as "best proprietary". **GLM is open-weight** — MIT, and
this document's own tier table two sections above says so. The genuine best proprietary
reranker is `qwen_s` at 0.7183, a gap of 0.0254 that its own test also cannot resolve
(p = 0.0283 against a 0.0050 threshold).*
Open weights led without separation on summarisation and SciFact, and trailed by
0.0013–0.0300 without separation on the other four. (This line said "won outright on
summarisation" after the correction above had retracted exactly that.)

"Not separated at n=200" is not "equal" — AG News's 0.0300 gap would likely resolve with
more items, and the honest reading is that **proprietary may hold a small real edge on
some tasks that this much data cannot demonstrate.** What the data does rule out is a
large one.



### If you are self-hosting anyway: small ML or an open-weight LLM?

Both run on your hardware at $0 marginal cost, so the choice is quality against the
machine it demands. They are not close in size.

| experiment | small ML model | small ML size | small ML score | best open-weight LLM | LLM size | LLM score | verdict |
|---|---|---|---|---|---|---|---|
| Classification · AG News | `bert_base_ta` (or `bert_mini`) | **438 MB** (44 MB) | **0.9600** (0.9450) | Llama-3.3-70B | ~141 GB | 0.8800 | **ML wins by 0.0800 at 1/322 the size, separated**; the 44 MB one leads by 0.0650 at 1/3,205 but is not separated (p = 0.0149 vs 0.0063) |
| Extraction · Few-NERD | `span_marker` | **499 MB** | **0.7674** | Gemma-4-26B-A4B | ~52 GB | 0.6733 | **ML wins by 0.0941, at 1/109** |
| Summarisation · CNN/DM | `bart_l` | **1.6 GB** | **0.3461** | DeepSeek-V4.1-Flash | 552B backbone, 510 GB checkpoint | 0.3460 | **tie** |
| Retrieval · SciFact | `e5_base` | **438 MB** | 0.7191 | GLM-4.5-Air | ~221 GB | **0.7437** | LLM wins by 0.0246, **not separated** |
| Classification · DBpedia | `bert_base_fy` | **438 MB** | **0.9857** | GLM-4.6 (or Gemma-4-26B, 52 GB) | ~714 GB | **0.9857** | **exact tie**, at 1/1,630 the size (1/119 of Gemma) |
| Judging · SummEval | `unievalpub` (UniEval, trained to judge; its own inputs) | **3.1 GB** | 0.3717 | Gemma-4-31B | ~63 GB | **0.5384** | **LLM wins by 0.1667, separated**, at 20× the size |

*Sizes are on-disk checkpoint sizes. A model in parentheses is an alternative with its own
size and score in parentheses beside the main ones: a smaller fine-tune (`bert_mini`) or an
equally scoring, smaller LLM (Gemma-4-26B). "At 1/322 the size" is the small model's size
divided by the LLM's. "Separated" is the Holm test against the LLM.*

**Four wins or ties for a model between 44 MB and 1.6 GB, against LLMs 109× to 3,205×
larger** — two of them *separated* wins (Few-NERD, and AG News through the bert-base
fine-tune), two exact or near-exact ties (summarisation's 0.0001, DBpedia's 0.0000). Until
2026-09-30 the DBpedia row read "blocked — LLM by default"; the ML arm loads on any
machine with torch ≥ 2.6, and ties. The LLM earns its size in two places. On SciFact the
margin is not statistically separated, and the *best* configuration uses **both**:
`e5_base` retrieving, `glm_s` reranking, for 0.7891. On SummEval it is: a 63 GB open-weight
judge beats UniEval, a 3.1 GB evaluator trained for the task, by 0.1667, scored on UniEval's
own inputs, and the 1.6 GB BARTScore by 0.2822.

Two practical consequences a DGX owner should weigh:

- **Several of these "self-hostable" LLMs are cluster-scale, and the published
  parameter counts understate them — but not as badly as this report first said.**
  DeepSeek-V4.1-Flash is advertised as 552B backbone parameters; its checkpoint is
  **510 GB**, because a 196B Engram memory ships with it and the headline count excludes
  it. GLM-4.6 is 714 GB. Whether either fits a given node depends on what must stay
  GPU-resident — a question about serving strategy that a parameter count cannot answer
  and **this report does not attempt to.** The small ML models fit in RAM on a laptop,
  which needs no such caveat.

  *This report said ~765 GB until 2026-09-29, and that number was never measured.* It
  came from multiplying HuggingFace's per-dtype **element** counts by one byte for the
  763B elements tagged `I8`. Those tensors are packed at roughly four bits: 763.2B
  parameters occupy 510.3 GB across 48 safetensors shards, which is **0.67 bytes per
  parameter**. The same mistake inflated DeepSeek-V4-Pro (1,602 → 865 GB) and
  DeepSeek-V4-Flash (292 → 160 GB); the other 20 models in the capture are unaffected,
  their derived and measured sizes agreeing to within 3%. The conclusion does not move —
  510 GB is still far beyond one 128 GB box — but the figure was wrong by half again,
  and it was wrong because it was computed rather than read. Found by external review;
  the evidence capture now records measured bytes and `check_model_facts.py` reads the
  claim out of this file rather than out of its own source.
- **Concurrency is where the size gap really lands.** A 44 MB classifier at 7 ms/item
  saturates a CPU core and scales by forking; a 70B model occupies most of a GPU and
  scales by buying more of them. The scores above are per-item quality, and they say
  nothing about how many items per second each arrangement sustains — **this report
  measures no throughput at all.**

**So the ordering for a hardware owner is: fine-tuned small ML first, open-weight LLM
where no fine-tuned model exists or the task is generative or a judgement, and a rented
API only when neither can run.** DBpedia used to be the exception, because its ML arm was
blocked; run, it fits the ordering — a 438 MB classifier matches the best open-weight LLM exactly.


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
measured (see the caveat below). These are open-weight LLMs only; the experiment's overall
winner may be a small ML model or a proprietary one.

| experiment | best open-weight LLM, unlimited hardware | its size | its score | best that fits ≤128 GB (precision, size) | ≤128 GB score | best that fits ≤64 GB (precision, size) | ≤64 GB score |
|---|---|---|---|---|---|---|---|
| Classification · AG News | Llama-3.3-70B | 141 GB | 0.8800 | **same**, int8 70 GB | **0.8800** | **same**, int4 35 GB | **0.8800** |
| Classification · DBpedia | GLM-4.6 | 714 GB | 0.9857 | **Gemma-4-26B**, native 52 GB | **0.9857** | **same**, native 52 GB | **0.9857** |
| Extraction · Few-NERD | Gemma-4-26B | 52 GB | 0.6733 | **same**, native | **0.6733** | **same**, native | **0.6733** |
| Retrieval · SciFact | GLM-4.5-Air | 221 GB | 0.7437 | **same**, int4 55 GB | **0.7437** | Gemma-4-26B, native 52 GB | 0.7363 |
| Summarisation · CNN/DM | DeepSeek-V4.1-Flash | 510 GB | 0.3460 | Llama-3.3-70B, int8 70 GB | 0.3382 | **same**, int4 35 GB | 0.3382 |
| Judging · SummEval | Gemma-4-31B | 63 GB | 0.5384 | **same**, native 63 GB | **0.5384** | **same**, int8 31 GB | **0.5384** |

**Hardware buys almost nothing here.** Five of six 128 GB answers equal the
unlimited-hardware answer, and **five of six 64 GB answers equal the 128 GB one.** Only
SciFact loses anything by halving the budget — 0.0074, which its own separation test
cannot resolve. Only summarisation loses anything by capping the budget at all — 0.0078,
about **18%** of the spread between the best and worst hosted arm on that task (0.0431).

So a **64 GB machine matched the unlimited-hardware answer on four of the six tasks**;
the two it missed, it missed by 0.0078 and 0.0074. This read "four of five" until
2026-10-18, which was the 128 GB count: at 64 GB both summarisation and SciFact lose, so it
was three of five.

**But the 64 GB column leans on int4 twice and int8 once** (SummEval), and that is where the
caveat below bites hardest: int8 is usually close to lossless, int4 frequently is not. If
your box is 64 GB, the native-precision options (Gemma-4-26B at 52 GB, Mistral-Small-24B at 48 GB) are the
ones whose numbers here you can trust without re-measuring.

> **The caveat, and it is a real one: quantised quality was never measured here.** Every
> score in this table comes from the full-precision model as served by a provider. int8 is
> usually close to lossless and int4 usually is not, but "usually" is not a measurement —
> and this repo's whole argument is that the difference matters. **Before deploying a
> quantised arm, re-run it locally through this harness and compare.** `rescore.py` makes
> the comparison cost nothing once the outputs exist.

**Practical shortlist for a 128 GB machine, by task:**

| if your task is | install |
|---|---|
| classification | **a BERT fine-tune** (44–438 MB) if you can label — it won AG News and tied DBpedia's best; else **Gemma-4-26B** (52 GB) |
| entity extraction | **SpanMarker fine-tune** (499 MB). No open-weight LLM here came close |
| summarisation | **BART-large-CNN** (1.6 GB), or its distillation (1.2 GB, 1.5× faster on the same CPU, no separable loss), if your summaries look like CNN/DailyMail's; else **Llama-3.3-70B int8** (70 GB) — a BART trained on someone else's summaries finished last |
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
| Summarisation · CNN/DM | `bart_l` | local ML | **0.3461** | none — it ranks first, tied with 15 others (13 paid) |
| Classification · AG News | `bert_base_ta` (or `bert_mini`) | local ML | **0.9600** (0.9450) | none — it ranks first, tied with 3 others (two fine-tunes and `anthropic_m`) |
| Extraction · Few-NERD | `span_marker` | local ML | **0.7674** | none — it ranks first, separated from all 27 opponents |
| Retrieval · SciFact | `glm_s` reranking BM25's top 20 | **open-weight, MIT** | **0.7437** | none — **the leader itself is self-hostable**. With `e5_base` retrieving instead of BM25 the same reranker scores 0.7891, a separate pipeline run |
| Classification · DBpedia | `bert_base_fy` (or `gemma_m` / `glm_m`) | **local ML** (or open-weight) | 0.9857 | **−0.0071, not separated** |
| Judging · SummEval | `gemma_l` | **open-weight, Apache-2.0** | 0.5384 | **−0.0013, not separated** (p = 0.8585 vs 0.0500, the leader's family test) |

Four of six cost nothing at all. DBpedia costs 0.0071 accuracy — two items in 280, a
difference the data cannot resolve — to avoid a winner with **no self-host option at any
price** (`qwen_m`, one vendor, no published weights; SummEval's `openai_l` is the other). That $0
answer used to need a 52 GB open-weight LLM; since 2026-09-30 a 438 MB classifier on a CPU
reaches the same score. SummEval costs 0.0013 τ against `openai_l`, also unresolvable, and
it is the one experiment whose $0 answer has no CPU-sized alternative: SciFact's is an
LLM too, but `e5_base` on a CPU is tied with it, while on SummEval the only small model is
separated below every judge.

**This is the finding a hardware owner should read first.** Not "free models are
competitive" but: *across six unrelated tasks, the best configuration you can run
entirely on your own machines either ranks first or is statistically tied with the leader.*

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
ones, and none of them statistically beat an open-weight alternative here.

What self-hosting costs instead — and this report measures none of it — is the hardware,
the serving stack, the ops burden, throughput engineering, and the fact that a 70B model
on your own GPUs is slower per request than a provider's optimised fleet unless you invest
in batching. **The trade is capex and engineering time against a rental bill**, and the
crossover depends entirely on volume.

### The strongest argument on the other side, also measured

**One hosted model does all six tasks with nothing but a prompt change.** Twelve of the
24 hosted arms ran every experiment unmodified; the best of them, `glm_m`, sits at the
**71st percentile across all six** (its rank among the hosted arms of each experiment,
averaged; 70th across the first five). The best fine-tuned local model sits at or tied with
the top on **one task each** and cannot perform the others at all — and, the XSum
control shows, cannot even perform its *own* task on someone else's data. On the sixth,
judging, the one local model measured — a summariser used as a judge — finished below every
hosted judge; no small model trained to judge was run.

That is seventeen local models to cover five of the six tasks, against what twelve hosted
arms covered with one configuration. If you have many tasks, a moving target, or no
labelled data, the generalist is not a compromise — it is the only thing that works.

### So the honest rule

> **If the task is stable, you own the labels, and you will run it more than a few
> thousand times a month — fine-tune a small model. It will be better, free, and faster.**
>
> **If the task is fluid, unlabelled, or one of many — pay for the LLM.** Then use §8 to
> avoid overpaying for it, because the dearest arm was never the best one.

### What this conclusion does NOT rest on, and the four ways it could be wrong

1. **Every fine-tuned arm was tested on the same distribution it was trained on.** That is
   precisely what "you govern the dataset" means, and it is also the best case. Nothing
   here measures **distribution drift**, which is the main way a fine-tuned model decays
   in production and the main reason teams reach for a generalist.
2. **Part of the win is learning the annotator's conventions, not the task.** Few-NERD
   quantifies it: **38% of `span_marker`'s lead** survives only because it agrees with
   annotation that the rest of the field rejects, and **57% of its margin is one entity
   type** whose meaning exists only inside that corpus. AG News is starker: three
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

### 1. The dearest arm is never first. Six times out of six.

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
weakly informative across the whole field and uninformative at the top — the money
separates bad from mediocre, then stops.

The practical form: **paying the most is never the optimum, and paying the least is
usually not either.** Among paid arms the best was a *mid*-tier model in four of six
experiments, a *small*-tier one in SciFact, and a *large*-tier one once: `openai_l` on
SummEval, which it leads inside a six-way tie that includes a judge costing 1/23 as much.

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
counting `glm_s` itself ([retrieval §3.2](REPORT_RETRIEVAL.md)). This row read 7 / 11 until 2026-10-15; the
default-setting figure is the one §8's tie table uses.*

*AG News read `bert_mini`, 18 of 27, a group of 9 until 2026-09-30. The new leader's group
is two other fine-tunes and `anthropic_m`, the last at p = 0.022 against a 0.0167
threshold — close to a podium, and a podium of three fine-tuned models of one kind.*

**Five of six leaderboards have a top group the data cannot order.** Reading rank 1 as
"the best model" would have been wrong five times. The gap between "ahead of everything"
and "distinguishable from a third of it" is the single most repeated result here.

### 3. A free local model wins or ties, whenever one trained on the task's own labels can run

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
| Judging · SummEval | `unievalpub`, 3.1 GB (UniEval, trained for the task on synthetic labels, on its own inputs) | 24 of 33 | −0.1680 vs `openai_l`, **separated**, and from 23 of 24 judges |

Read the third row before the first two. **`bart_l` "wins" summarisation by 0.0001** — it
is first on the leaderboard and tied with a hosted model in every sense that matters. An
earlier draft of this table reported +0.0176 there, because it compared against
`anthropic_l` rather than against the best paid arm; the corrected number turns an
apparent win into the winner's-curse case of §4.

So: **one separated win (Few-NERD), four statistical ties — two led by the free arm (AG
News, summarisation) and two trailed by it (SciFact, DBpedia) — and one loss, SummEval,
where the one free arm trained for the task learned from synthetic labels.** Until
2026-10-19 that clause read "where no free arm measured was trained for the task"; UniEval,
run since, is trained for it. Until 2026-09-30 this line read "two clear
wins, two ties, one loss", and the loss was DBpedia — where the only free arm that had run
was `bart_mnli`, a zero-shot NLI model, because the fine-tuned checkpoint would not load.
Run on a machine with torch ≥ 2.6, the fine-tune ties the top group. The pattern is
narrower and stronger than "small models win":

> **A small model fine-tuned on your data — your inputs, labelled for your task — wins or
> ties against every frontier LLM at that task, for $0** — a separated win on Few-NERD, a
> statistical tie everywhere else. A small model *not* trained that way loses — one
> trained for the same task on a different corpus (to all of them), one trained on the
> same corpus for a different task (BARTScore on SummEval, below all 24 judges), and one
> trained for the same task on the same corpus from synthetic labels (UniEval, below 23 of
> the 24).

Few-NERD isolates this with a matched pair — `span_marker` and `gliner` are the same model
class differing only in exposure to the training split — and the difference is **+0.3134
F1**. Summarisation adds the sharper one: the same BART-large fine-tuned for summarisation
on CNN/DailyMail and on XSum, **1st and 29th of 29**.

**And the optimum was a mid-tier arm in four of six experiments** (`_m_` in
summarisation, AG News, DBpedia and Few-NERD; `_s_` in SciFact; `_l_` in SummEval). The
large tier was the optimum once, and there it cannot be separated from five others.

**The caveat the NER report insists on:** 57% of `span_marker`'s margin comes from one
entity type whose meaning exists only inside that corpus, and 38% of its lead survives only
because it agrees with annotation the rest of the field rejects. AG News now shows the same
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
| Classification · AG News | 0.852 | 20 | `anthropic_l` | `bert_base_ta` | **5 of 30** (3 of 28 before the bert-base arms) |
| Retrieval · SciFact | 0.756 | 40 | `llama_s` | `glm_s` | **10 of 19** |
| Classification · DBpedia | 0.728 | 56 | `anthropic_l` | `qwen_m` | 2 of 28 |
| Summarisation · CNN/DM | 0.722 | 20 | `bart_l` | `bart_l` | 1 of 29 ✓ |

*The ρ column is from dev-slice runs made before the six local arms existed, and those dev
runs were never committed — so ρ cannot be extended to the new arms, and the AG News and
DBpedia values cannot be re-derived from this repository. Recomputing the dev ranking from
the dev items inside the committed full runs gives 0.677 and 0.757 instead, with a 10- to
13-way tie at the top of the dev slice; see
[`KNOWN_ISSUES.md`](internal/KNOWN_ISSUES.md). The last two columns are from committed runs.*

**ρ between 0.72 and 0.90 in every case — and the pilot picked the wrong winner in three of
the five experiments that ran one.** On SciFact it picked the tenth-best of nineteen.

This is the most transferable finding in the repo, because ρ is the number people quote to
justify a pilot and it is **the wrong number for the decision being made**. A high rank
correlation says the *ordering* is broadly preserved. Selecting one arm depends on the
ordering at the very top, which is where the noise concentrates and where the field is
tied (§2).

Related, from the summarisation study: BART's lead over the best LLM was **0.0737 at n=20**
and **0.00008 at n=200** — a 900× shrink. Same arms, same metric, more data.

### 5. The gold is wrong or noisy, in every corpus that was checked

*Sources:* [NER §3.6](REPORT_NER.md) · [classification §3.4](REPORT_CLASSIFICATION.md)

A **consensus pass** takes every learned arm's answers and lists the gold labels that
nearly all of them contradict in the same way; independent models rarely agree on the same
mistake, so those labels are suspect. It flags candidates, it does not prove an error.

| corpus | suspect gold labels (count, unit) | flagged when | method |
|---|---|---|---|
| Few-NERD | **34 of 768** gold entities (4.4%) | the span is found but ≥80% of the 26 learned arms give it another type | consensus pass |
| DBpedia | 3 items | 24–25 of the 26 learned arms dispute the label; the top eleven arms are separated by four items | consensus pass |
| AG News | 17 items | ≥80% of the hosted field disputes the label — the fine-tuned lead lives in them; revised a published finding twice | consensus pass, hosted arms only |
| CNN/DailyMail | **not checked** | — | — |
| SciFact | **not checked** (qrels incompleteness unmeasured) | — | — |
| SummEval | 41 of 44 groups of word-for-word identical summaries | the copies received different expert mean scores (REPORT_SUMMEVAL §3.7) | identical-text check, not a consensus pass |

Four for four where anyone looked. The honest statement is not "most corpora have noisy
gold" — it is **every corpus we examined had it, and two were never examined.** SummEval's
is a different kind of check: identical inputs that received different scores show the
gold is noisy, not that any one score is wrong.

On a saturated benchmark this stops being a footnote and becomes the ceiling: DBpedia's top
eleven arms are separated by four items, and three of those are items 24–25 of 26 learned arms dispute
because the label is wrong. **The measurement was resolving annotation, not capability.**

The diagnostic is cheap and general: items nearly every *learned* arm gets wrong are items
whose gold is probably wrong. Independent models do not agree on a mistake.

**With one refinement the fine-tuned arms forced:** leave out the arms trained on the gold.
They are not independent of it. On DBpedia the one arm that "gets" the canal filed under
`NaturalPlace` is the one trained on DBpedia; on AG News the arms that agree with the gold
on the 17 disputed items are the three trained on AG News. A consensus that includes them
under-counts label errors — and a leaderboard that includes them over-counts their skill.

### 6. The instrument was broken before the models got interesting — in five of six

*Sources: the Corrections section of each report, and [`NOTES.md`](internal/NOTES.md), 66 entries*

Defects found **by** running the experiments, each of which changed published numbers or
would have:

| experiment | defect | impact if not found |
|---|---|---|
| Summarisation · CNN/DM | scorer bug surviving two sweeps | drove `rescore.py` into existence |
| Classification · AG News | duplicate-run check flagged honest ties as copies | 4 false alarms in one sweep |
| Classification · AG News | the **label parser** is worth **8.6 accuracy points** to one arm | wider than most of the field's spread |
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
| rank correlation per item (Kendall τ-b) | never here (no two of the 31 SummEval arms share a mean τ to four decimals) | the *judge's* scores tie constantly (integer 1–5), so the τ-b tie correction is part of the instrument; per-item τ makes the paired tests apply directly, and split-half rankings are readable (ρ 0.90 at 20 articles per half) |

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
| Retrieval · SciFact | 12 | +0.0200 | +2.7% | r = 0.32 |
| Classification · AG News | 24 | +0.0214 | +2.3% | r = 0.63 |
| Classification · DBpedia | 24 | +0.0094 | +0.9% | r = 0.40 |
| Summarisation · CNN/DM | 24 | −0.0013 | **−0.4%** | r = −0.07 |

*Few-NERD's row read +0.0405 and r = 0.49 until 2026-10-18: it had been fitted to the
un-rescored runs in `data/runs/`, while every other Few-NERD figure in this report is the
rescored one. Fitted to the rescored runs it is +0.0407 and 0.50, and the percentage does
not move.*

**An order of magnitude more money buys between nothing and seven percent.** On
summarisation the slope is *negative* and the correlation is zero — across 24 arms and a
143× price range, cost carried no information about quality at all. SummEval has the
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
  also not separable. Until 2026-09-30 this bullet said "the one experiment where paying
  beats free by a mile (+58%)"; that was against a zero-shot arm, because the fine-tuned
  one had not run.
- **Few-NERD: $2,463/month buys −11.4%** against a free model on a CPU. The largest
  free-vs-paid gap in the set, and the free arm separates from all 27 opponents.
- **SciFact: $2,288/month buys −0.2%** against $711/month, and the $711 arm buys **+3.4%
  over free** — a case where paying is defensible, and even there the free arm is not
  statistically separated from it.
- **SummEval: $20,077/month buys −2.1%** against $6,350/month, and the best free scorer,
  UniEval, is **−31.1%** — the one experiment where no free arm comes close. Even
  there the answer need not be rented: `gemma_l`, tied with the leader, has open weights and
  bills $278/month rented.

In no experiment did the most expensive option win. In three of six the free option
ranked first, and on Few-NERD it is separated from everything.

### What "free" actually gets you, in all six

The free-vs-paid comparison in full. Free loses once: on SummEval, where the one free arm
trained for the task learned from synthetic labels, and there by a margin no test was
needed to see.

The verdict's percentage is the winner's lead **relative to the lower of the two scores**
(+11.8% = 0.7674 ÷ 0.6864 − 1), whereas the table above measures everything relative to the
best arm — which is why Few-NERD reads −11.4% there and +11.8% here. "Separated" is the
Holm test between the two arms.

| experiment | best free arm (size) | free quality | free rank | best paid arm | paid quality | paid $/month at 1M items | verdict (lead relative to the lower score) |
|---|---|---|---|---|---|---|---|
| Extraction · Few-NERD | `span_marker` 499 MB | 0.7674 | **1** | `openai_m` | 0.6864 | $2,324 | **free wins +11.8%**, separated |
| Classification · AG News | `bert_base_ta` 438 MB | 0.9600 | **1** | `anthropic_m` | 0.9100 | $351 | free leads +5.5%, **not separated** (p = 0.022 vs 0.0167) |
| Summarisation · CNN/DM | `bart_l` 1.6 GB | 0.3461 | **1** | `deepseek_m` | 0.3460 | $191 | free leads +0.0% *(a tie)* |
| Retrieval · SciFact | `e5_base` 438 MB | 0.7191 | 8 | `glm_s` | 0.7437 | $711 | paid wins +3.4%, **not separated** |
| Classification · DBpedia | `bert_base_fy` 438 MB | 0.9857 | 3= | `qwen_m` | 0.9929 | $51 | paid wins +0.7%, **not separated** |
| Judging · SummEval | `unievalpub` 3.1 GB | 0.3717 | 24 | `openai_l` | 0.5398 | $6,350 | **paid wins +45.2%**, separated |

*The SciFact rank is 8th against the corrected-parser runs in `data/runs-reparsed/`, which
are the retrieval report's record (`qwen_s` 0.7183). A plain `leaderboard.py` over
`data/runs/` reads the original-parser `qwen_s` (0.7338) and puts `e5_base` 9th — which is
what this row said until 2026-09-30, when it was changed without this note.*

**The DBpedia row used to be `bart_mnli`, zero-shot, 25th, "paid wins +58%"** — the only
free arm that had run, because the fine-tuned checkpoint is a pickle that `transformers`
refuses below torch 2.6 ([CVE-2025-32434](https://github.com/advisories/GHSA-53q9-r3pm-6pq6))
and the original machine had no newer torch. It was presented here as the control, and it
still is one: at the same price of zero, the zero-shot model scores **0.6286** and the
fine-tuned one **0.9857** — **+0.357 from training exposure**, on a task where the
difference between the best and the fifteenth paid arm is under 0.02.

So the axis is not free-versus-paid. It is:

> **trained on your task's own labels** → beats or ties everything, at $0
> **not trained that way** → loses, also at $0

SummEval tests the line from two sides. BARTScore was fine-tuned on this very corpus, to
*write* summaries, and asked to *judge* them it finishes below every one of the 24 hosted
judges. UniEval was trained *to judge* these four dimensions on this corpus's text, but from
rule-based corruptions of reference summaries rather than anyone's judgements, and it
finishes below 23 of the 24 (`unievalpub` 0.3717 on its own inputs; the SummEval row above
uses it). Until 2026-10-19 the first line read "trained on your task"; UniEval is trained
for the task and loses, and "own labels" is drawn after that result, from one case, so read
it as the best current description rather than a tested finding.

Few-NERD proves it directly with a matched pair: `span_marker` (fine-tuned on Few-NERD)
scores 0.7674 and `gliner` (same model class, never trained on it) scores 0.4540 — a
**+0.3134** gap from exposure alone, with price held at zero on both sides.

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
cannot detect the difference.** AG News read "9 arms, `gemma_s`, 82× cheaper" until
2026-09-30; its new leader, a bert-base fine-tune, is separated from every paid arm but
`anthropic_m`, the second-dearest, so the saving there is 2.5× — and the real answer on
AG News is the free arm, as on Few-NERD, where no paid arm is indistinguishable from it.

### Cost rarely buys speed

Sorted by r. Latencies are mean seconds per item from the stored runs, except the
re-timed Linux figures for the BARTs, which are medians from `harness/data/runs-linux/`.

| experiment | Pearson r, log(cost) vs latency (hosted) | hosted latency per item, min–max | fastest local arm, latency per item |
|---|---|---|---|
| Judging · SummEval | **r = −0.47** | 1.12 – 12.35 s | `length` and `random`, ~0 s (the rule-based ROUGE and `coverage` 0.18–0.89 s; the learned local arms, BARTScore 15.66 s and UniEval 41.68–44.69 s) |
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
path (this read 44×–766× until 2026-09-30, computed from 10 ms rather than the measured
7.11 ms). The bert-base fine-tunes, ten times larger, take 76–90 ms, timed on a different (Linux)
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
2. **If you can label a few thousand examples, fine-tune a small model — on your own
   data.** The best fine-tune ranked first in three of six and third-equal, not separable
   from the leader, in a fourth (DBpedia); SciFact and SummEval had none fine-tuned for the
   task. It costs
   **$0/month against up to $9,826/month**, with lower latency on classification —
   61×–1,078× for `bert_mini` against the hosted field on the same Mac, roughly 5×–140× for
   the bert-base fine-tunes timed elsewhere. On someone else's data of the same task it
   finished last. This is the single biggest lever in the table.
3. **Never buy the most expensive arm.** Six for six it was not the best, and in three
   experiments it was *worse* than free while costing $875–$9,826/month.
4. **Pick the cheapest arm your test cannot separate from the leader.** That is 7.6×–143×
   cheaper than the dearest in four of six, 2.5× on AG News, and on Few-NERD and AG
   News the cheapest indistinguishable arm is the free one. Requires a separation test, not a
   leaderboard — "ahead on the average" was true of the leader in 100% of cases and meant
   almost nothing.
5. **Do not select on a pilot.** ρ ≈ 0.8 feels like enough and picked the wrong winner
   three times in the five experiments that ran one. Use the pilot to catch instrument
   bugs, which is what it is genuinely good for.
6. **Read the items your whole field gets wrong before you read the ranking.** On a
   saturated benchmark that is where the ceiling is, and it is annotation rather than
   capability.
7. **Budget attention for the scorer, not just the model.** Three separate scoring bugs
   here moved an arm further than most model swaps did.

**When paying more IS right**, and this report should not be read as saying never: when
you cannot label data and the task is unlike anything a small model was trained on
(on SummEval, even a free evaluator trained for it lost to 23 of the 24 LLM judges); when the
quality
difference is worth more than the bill (at 1,000 items/month the entire
DBpedia spread is $1.35 and the analysis is not worth your time); when a single wrong
answer is expensive; or when engineering time to fine-tune and host costs more than the
API. The finding is not that expensive models are bad — it is that **price stops
predicting quality long before it stops rising**, so the premium has to be justified by
something other than the leaderboard.

## What this cannot say

- **The summarisation sample is CNN, not CNN/DailyMail.** All 200 of its articles are
  CNN's; the test split is 91% DailyMail. The DailyMail slice
  ([REPORT_SUMMARIZATION §3.7](REPORT_SUMMARIZATION.md#37-does-it-hold-outside-cnn-the-dailymail-slice))
  re-ran the five local arms, and every one of their comparisons held; the hosted arms
  could not be re-run from the environment that found it, so whether the *paid*
  comparisons travel is measured for none of them.
- **Six tasks, all English, all text.** No multilingual, multimodal, long-context or
  agentic task, and one judging task (SummEval) as the only open-ended one. The
  tie-at-the-top result may be a property of *saturated-ish academic benchmarks* rather
  than of frontier models.
- **One pass per arm, temperature 0.** Every interval here is over *items*, never over
  *runs*. Run-to-run variance is real and, for hosted arms, unmeasured — two runs of an
  identical SciFact config scored 0.6691 and 0.6617, because OpenRouter routes across
  providers. For the local arms of summarisation and classification it is measured and zero: all
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
  elsewhere. The NER arm that was
  rate-limited (`fn_mistral_l`) ran on 2026-10-01, and the six local ML arms that were
  unrun until 2026-09-30 have all run.
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
  *structure* — that price stops predicting quality — is what is expected to survive.

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
arrived — including the ones that were retracted — is [`NOTES.md`](internal/NOTES.md), 66 entries.
