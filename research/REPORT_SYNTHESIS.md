# What five experiments agree on

**Five tasks · four metric shapes · 127 measured arms · $12.01 billed · one harness**

Seven findings that hold across every experiment (§1–§7), and what they imply for
**quality vs cost vs latency** in production (§8).

A cross-cutting report. Each of the four underlying reports answers *"which model is best
at this task"*; this one asks what is true in **all** of them, and it is written because
several findings only became visible once there were five corpora to compare.

| | task | metric shape | report |
|---|---|---|---|
| CNN/DailyMail | summarise a news article | continuous (ROUGE) | [REPORT_SUMMARIZATION](REPORT_SUMMARIZATION.md) |
| AG News | 4-way topic label | binary per item | [REPORT_CLASSIFICATION](REPORT_CLASSIFICATION.md) |
| DBpedia-14 | 14-way ontology label | binary, **saturated** | [REPORT_CLASSIFICATION](REPORT_CLASSIFICATION.md) |
| Few-NERD | entities + types | set vs set | [REPORT_NER](REPORT_NER.md) |
| SciFact | retrieve from 5,183 docs | ranked list | [REPORT_RETRIEVAL](REPORT_RETRIEVAL.md) |

Every number below is computed from the stored runs, not quoted from the reports.
Reproduction commands are in §8.

---

## Executive summary

**Across five tasks and 127 measured arms: the most expensive model was never the best,
four of five leaderboard tops are statistical ties, a small model trained on your task
beat every frontier LLM for $0 wherever one could run, and a 10× cost increase bought
between −0.4% and +5.9% of quality.**

**The production question — should you fine-tune a small model instead of paying an
LLM?** Yes, for a task you can define and label: every model fine-tuned on its dataset
ranked **first** (3 of 3), and every zero-shot model ranked **last** (3 of 3). The
predictor is training exposure, not model size. The counter-argument is also measured: one
hosted model covers all five tasks at the 70th percentile with a prompt change, where each
local model does exactly one. Full reasoning and four ways it could be wrong:
[§0](#0-the-production-question-should-you-fine-tune-a-small-model-instead-of-paying-an-llm).

### The seven findings

| # | finding | evidence |
|---|---|---|
| **1** | **The dearest arm is never first** | 5 of 5. It ranked 16th, 3rd, 2nd, 3rd, 2nd. But the dearest still beats the *cheapest* in 4 of 5 — price separates bad from mediocre, then stops. The best paid arm was **mid-tier** in four of five; the large tier never won anything. |
| **2** | **The top is a group, not a podium** | Every winner leads on the point estimate against **100%** of its declared family, and separates from only **31–100%**. Only Few-NERD produced a real podium (26 of 26); DBpedia's winner separates from 8 of 26. |
| **3** | **The axis is trained-on-your-task, not free-vs-paid** | Free wins outright in 3 of 5, ties in a 4th, and loses only where no *fine-tuned* free arm could run. Matched pair at price zero on both sides: `span_marker` 0.7674 vs `gliner` 0.4540 — **+0.3134 from exposure alone**. |
| **4** | **A pilot correlates beautifully and picks the wrong winner** | ρ(dev, full) = **0.72–0.90** in every experiment, and the pilot chose wrong in **3 of 5**. On SciFact it chose the **tenth-best of nineteen**. |
| **5** | **The gold is wrong, in every corpus that was checked** | 3 for 3 where anyone looked; 2 were never checked. Few-NERD: **34 of 768** gold types unanimously rejected by all 25 learned arms. DBpedia's top ten are separated by four items, three of which the whole field disputes. |
| **6** | **The instrument broke before the models got interesting** | Every time. 8 defects tabulated; **3 moved a single arm further than the gap separating most of the field** — the label parser (8.6 accuracy points), the unparsed-as-empty rule (+0.0214 f1), the reasoning flag (0.6124 → 0.6991). |
| **7** | **The metric's shape decides which diagnostics can be read** | Not which model wins — which *tools* work. On DBpedia at n=10, **19.8 of 27 arms tied** and the rank statistic was correlating arm names; 400 of 400 resampling draws are undecided at every size. |

### The economics

**A 10× cost increase buys −0.4% to +5.9% of the best arm's quality** (r = −0.07 to 0.63).
On summarisation the slope is *negative* across 24 arms and a 143× price range.

At **1,000,000 items/month**, billed:

| experiment | the expensive option | what it buys |
|---|---|---|
| summarisation | **$9,826/mo** | **−8.9%** vs free, and −0.0% vs $191/mo |
| Few-NERD | **$2,463/mo** | **−11.4%** vs a free CPU model |
| SciFact | $2,288/mo | −0.2% vs $711/mo |
| DBpedia | **$1,351/mo** | **−0.4%** vs $51/mo |
| AG News | $875/mo | −4.8% vs free |

Three more numbers that travel:

- **The cheapest arm you cannot statistically separate from the best is 8×–143× cheaper
  than the dearest**, in four of five experiments.
- **Cost does not buy speed.** log(cost) vs latency correlates at **r = −0.30 to +0.20** —
  uncorrelated, negative twice. Free local models run 44×–766× faster on classification
  and embedding, and *slower* on generation.
- **The task shape sets the bill, not the model.** 104 input tokens per item for
  classification against **3,926 for retrieval reranking** — a 38× difference that no
  model substitution recovers.

### What to do with this

1. **Check the architecture before the model.** The largest cost lever here was structural.
2. **If you can label a few thousand examples, fine-tune a small model** — $0 against up to
   $9,826/month, and far lower latency.
3. **Never buy the most expensive arm.** In three experiments it was *worse* than free.
4. **Pick the cheapest arm your test cannot separate from the leader** — which requires a
   separation test, not a leaderboard.
5. **Do not select on a pilot**; use it to catch instrument bugs, which is what it is good at.

**When paying more is right:** you cannot label data; the task is unlike anything a small
model has seen; a wrong answer is expensive; your volume is low enough that the whole
spread is rounding error (at 1,000 items/month the entire DBpedia range is $1.35); or
engineering time costs more than the API. The claim is not that expensive models are bad —
it is that **price stops predicting quality long before it stops rising.**

---

*The rest of this report unpacks each finding with its full evidence, and
[§8](#8-the-economics-what-money-actually-buys) has the complete economics. Each finding links to the experiment report it comes from; those
reports carry the per-task detail, the corrections, and what each one could not measure.*

---

## 0. The production question: should you fine-tune a small model instead of paying an LLM?

**Yes — for a task you can define and label. The evidence is 3 for 3, and it is not close
on cost or latency. But the answer depends entirely on one variable, and it is not model
size.**

### What actually predicts whether a free local model wins

Sorting all ten local arms by how much task-specific training they had produces a
**monotonic** relationship — and the boundary is sharp:

| training exposure | arms | rank among all arms | vs the best **paid** arm |
|---|---|---|---|
| **Fine-tuned on this dataset** | `span_marker`, `bert_mini`, `bart_l` | **1st, 1st, 1st** | **+0.0810, +0.0350, +0.0001** |
| Trained for the task *type* | `e5_base`, `bge_small` | 9th, 11th of 17 | −0.0246, −0.0340 — **not separated** |
| General-purpose embeddings | `mpnet`, `minilm` | 15th, 16th of 17 | −0.0794, −0.0904 |
| **Zero-shot** | `bart_mnli` ×2, `gliner` | **25th, 25th, 26th — last** | **−0.2100, −0.2324, −0.3643** |

**Every model fine-tuned on its dataset ranked first. Every zero-shot model ranked last or
second-to-last.** No exceptions in either direction, across five tasks and four metric
shapes.

The cleanest proof is a matched pair with price held at zero on both sides:
`span_marker` and `gliner` are the same model class on the same task, differing only in
whether they saw Few-NERD's training split. The difference is **+0.3134 F1** — larger than
the entire spread of the 23 hosted arms on that task.

### What that is worth in production

| | fine-tuned local | best paid alternative |
|---|---|---|
| Few-NERD | **0.7674**, $0, 0.76 s | 0.6864, **$2,324/mo**, 1.60 s |
| AG News | **0.9450**, $0, **7 ms** | 0.9100, **$351/mo**, 1.92 s |
| summarisation | **0.3461**, $0, 11.0 s | 0.3460, **$191/mo**, 1.60 s |

Better quality, zero inference cost, and **44×–766× lower latency** on the two
classification-shaped tasks. On summarisation the quality is a tie and the local model is
*slower*, because generation on a CPU is genuinely expensive — so the win there is cost
only.

### The strongest argument on the other side, also measured

**One hosted model does all five tasks with nothing but a prompt change.** Twelve of the
24 hosted arms ran every experiment unmodified; the best of them, `glm_m`, sits at the
**70th percentile across all five**. The three fine-tuned local models sit at the 100th
percentile on **one task each** and cannot perform the other four at all.

That is ten local models to cover what twelve hosted arms covered with one configuration.
If you have five tasks, a moving target, or no labelled data, the generalist is not a
compromise — it is the only thing that works.

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
   type** whose meaning exists only inside that corpus. In production, *your* conventions
   are what you want — but the measured win does not transfer to a different labelling
   standard.
3. **"Free" means zero inference cost and nothing else.** No labelling, no training
   compute, no hosting, no monitoring, no retraining when the data moves. A model that
   takes an engineer a fortnight to ship is not free at any volume. The crossover point
   against $191/month is a spreadsheet this report does not contain.
4. **All five tasks are classic NLP with mature small-model architectures** —
   summarisation, classification, NER, retrieval. Nothing open-ended, multi-step,
   reasoning-heavy, or instruction-following. Those are exactly the tasks where a
   generalist is structurally advantaged, and **none of them were tested here.**

---

## The seven findings, unpacked

### 1. The dearest arm is never first. Five times out of five.

| experiment | dearest paid arm | cost | its rank |
|---|---|---|---|
| summarisation | `anthropic_l` | $1.9652 | **16 of 25** |
| AG News | `anthropic_l` | $0.1750 | 3 of 26 |
| DBpedia | `anthropic_l` | $0.3784 | 2 of 25 |
| Few-NERD | `anthropic_l` | $0.6897 | 3 of 25 |
| SciFact | `glm_m` | $0.4576 | 2 of 17 |

**But the naive version of this claim is false, and worth killing.** "Price buys nothing"
is not supported: the dearest arm beats the *cheapest* arm in 4 of 5 experiments. Price is
weakly informative across the whole field and uninformative at the top — the money
separates bad from mediocre, then stops.

The practical form: **paying the most is never the optimum, and paying the least is
usually not either.** Among paid arms the best was a *mid*-tier model in four of five
experiments and a *small*-tier one in the fifth — the large tier never won anything here.

### 2. The top of a leaderboard is a group, not a podium

Every winner leads on the point estimate against **100%** of its declared family. How many
it actually *separates* from, under Holm step-down at α = 0.05:

| experiment | winner | ahead of | separated from | |
|---|---|---|---|---|
| Few-NERD | `span_marker` | 26 of 26 | **26 of 26** (100%) | a real podium |
| AG News | `bert_mini` | 27 of 27 | 18 of 27 (67%) | a group of 9 |
| summarisation | `bart_l` | 25 of 25 | 12 of 25 (48%) | a group of 13 |
| SciFact | `glm_s` | 18 of 18 | 6 of 18 (33%) | a group of 12 |
| DBpedia | `qwen_m` | 26 of 26 | 8 of 26 (31%) | a group of 18 |

**Four of five leaderboards have a top group the data cannot order.** Reading rank 1 as
"the best model" would have been wrong four times. The gap between "ahead of everything"
and "distinguishable from a third of it" is the single most repeated result here.

### 3. A free local model wins or ties, whenever one can run at all

*Sources:* [NER](REPORT_NER.md) · [classification](REPORT_CLASSIFICATION.md) · [summarisation](REPORT_SUMMARIZATION.md) · [retrieval](REPORT_RETRIEVAL.md)

| experiment | best free arm | rank | margin over the best **paid** arm |
|---|---|---|---|
| Few-NERD | `span_marker`, 476 MB | **1 of 25** | +0.0810 over `openai_m` |
| AG News | `bert_mini`, 44 MB | **1 of 26** | +0.0350 over `anthropic_m` |
| summarisation | `bart_l`, 1.6 GB | **1 of 25** | **+0.0001** over `deepseek_m` |
| SciFact | `e5_base`, 438 MB | 9 of 17 | −0.0246 vs `glm_s`, **not separated** |
| DBpedia | `bart_mnli` (zero-shot) | 25 of 25 | −0.3643 |

Read the third row before the first two. **`bart_l` "wins" summarisation by 0.0001** — it
is first on the leaderboard and tied with a hosted model in every sense that matters. An
earlier draft of this table reported +0.0176 there, because it compared against
`anthropic_l` rather than against the best paid arm; the corrected number turns an
apparent win into the winner's-curse case of §4.

So: two clear wins, two ties, one loss — and the loss is the one arm **not trained for its
task** (zero-shot NLI), because DBpedia's fine-tuned checkpoint could not be loaded. The
pattern is narrower and stronger than "small models win":

> **A small model fine-tuned on your task beats every frontier LLM at that task, for $0.**
> A small model *not* trained on your task loses to all of them.

Few-NERD isolates this with a matched pair — `span_marker` and `gliner` are the same model
class differing only in exposure to the training split — and the difference is **+0.3134
F1**.

**And the optimum was a mid-tier arm in four of five experiments** (`_m_` in
summarisation, AG News, DBpedia and Few-NERD; `_s_` in SciFact). Not once was it the large
tier.

**The caveat the NER report insists on:** 57% of `span_marker`'s margin comes from one
entity type whose meaning exists only inside that corpus, and 38% of its lead survives only
because it agrees with annotation the rest of the field rejects. Fine-tuned models partly
learn *your conventions*, which is exactly what you want in production and is not the same
as being right.

### 4. A pilot correlates beautifully and picks the wrong winner

*Sources:* [retrieval §3.5](REPORT_RETRIEVAL.md) · [summarisation §3.6](REPORT_SUMMARIZATION.md) · [NER §3.8](REPORT_NER.md)

Every experiment ran a small dev slice before the full one. Comparing the two:

| experiment | ρ(dev, full) | dev leader | true leader | dev leader's real rank |
|---|---|---|---|---|
| Few-NERD | 0.895 | `span_marker` | `span_marker` | 1 of 27 ✓ |
| AG News | 0.852 | `anthropic_l` | `bert_mini` | 3 of 28 |
| SciFact | 0.756 | `llama_s` | `glm_s` | **10 of 19** |
| DBpedia | 0.728 | `anthropic_l` | `qwen_m` | 2 of 27 |
| summarisation | 0.722 | `bart_l` | `bart_l` | 1 of 26 ✓ |

**ρ between 0.72 and 0.90 in every case — and the pilot picked the wrong winner in three of
five.** On SciFact it picked the tenth-best of nineteen.

This is the most transferable finding in the repo, because ρ is the number people quote to
justify a pilot and it is **the wrong number for the decision being made**. A high rank
correlation says the *ordering* is broadly preserved. Selecting one arm depends on the
ordering at the very top, which is where the noise concentrates and where the field is
tied (§2).

Related, from the summarisation study: BART's lead over the best LLM was **0.0737 at n=20**
and **0.00008 at n=200** — a 900× shrink. Same arms, same metric, more data.

### 5. The gold is wrong, in every corpus that was checked

*Sources:* [NER §3.6](REPORT_NER.md) · [classification §3.4](REPORT_CLASSIFICATION.md)

| corpus | gold errors found | method |
|---|---|---|
| Few-NERD | **34 of 768** gold types (4.4%) unanimously rejected by all 25 learned arms | consensus pass |
| DBpedia | 3 items disputed by the entire field; the top ten arms are separated by four items | consensus pass |
| AG News | systematic label noise; revised a published finding | consensus pass |
| CNN/DailyMail | **not checked** | — |
| SciFact | **not checked** (qrels incompleteness unmeasured) | — |

Three for three where anyone looked. The honest statement is not "60% of corpora have
noisy gold" — it is **every corpus we examined had it, and two were never examined.**

On a saturated benchmark this stops being a footnote and becomes the ceiling: DBpedia's top
ten arms are separated by four items, and three of those are items the whole field disputes
because the label is wrong. **The measurement was resolving annotation, not capability.**

The diagnostic is cheap and general: items nearly every *learned* arm gets wrong are items
whose gold is probably wrong. Independent models do not agree on a mistake.

### 6. The instrument was broken before the models got interesting — every time

*Sources: the Corrections section of each report, and [`NOTES.md`](NOTES.md), 56 entries*

Defects found **by** running the experiments, each of which changed published numbers or
would have:

| experiment | defect | cost if unfound |
|---|---|---|
| summarisation | scorer bug surviving two sweeps | drove `rescore.py` into existence |
| AG News | duplicate-run check flagged honest ties as copies | 4 false alarms in one sweep |
| AG News | the **label parser** is worth **8.6 accuracy points** to one arm | wider than most of the field's spread |
| Few-NERD | an unreadable answer scored **1.0** on empty-gold items | +0.0214 f1 to one arm |
| Few-NERD | `normalizer_sha256` covered the normaliser, not the scorer | a scorer change was invisible in the fingerprint |
| SciFact | the adapter never disabled reasoning, unlike the other three | one arm went **0.6124 → 0.6991** once fixed |
| all | cost computed from a price table, not what was billed | wrong per arm by 0.67×–3.21× |
| all | Spearman had no tie correction; ranks broke ties **alphabetically** | ρ measured the alphabet on saturated tasks |

Three of these — the parser, the unparsed-as-empty rule, the reasoning flag — moved a
single arm by **more than the gap separating most of the field**. So:

> **The scoring code is a model-sized lever.** Changing how you parse an answer can matter
> more than changing which model produced it.

This is why every run fingerprints `parser_sha256`, `scorer_sha256` and `normalizer_sha256`,
and why `rescore.py` exists: recomputing every score from stored outputs costs $0, so
checking a scorer is never the expensive option.

### 7. The metric's shape decides which diagnostics can be read at all

*Sources:* [classification §3.6](REPORT_CLASSIFICATION.md) · [NER §3.9](REPORT_NER.md) · [retrieval](REPORT_RETRIEVAL.md)

Not which model wins — which *tools* work.

| shape | ties? | consequence |
|---|---|---|
| continuous (ROUGE, nDCG) | ~never | rank correlation is meaningful; duplicate-detection by mean is safe |
| binary per item (accuracy) | constantly | two different models report identical means; ρ degenerates |
| set (F1 per item) | rarely | per-item F1 is legitimate, so permutation tests work directly |
| ranked list (nDCG) | rarely | but **corpus ≠ items**, which breaks fingerprinting |

Concretely: on DBpedia at n=10, **19.8 of 27 arms tied**, so the rank statistic was
correlating *arm names*. Requiring a unique winner, **400 of 400 resampling draws are
undecided at every size tested** — that corpus has no winner to agree about, and every
earlier stability figure for it was an artifact of alphabetical tie-breaking.

The same tool on Few-NERD reports `arms tied 1st = 1.0` at every size and is perfectly
readable. **The tool was never wrong in general; it was wrong for a metric shape.**

---

---

## 8. The economics: what money actually buys

The four reports each measure quality and record cost. Put together, they answer the
question a production decision actually asks — **how much quality does a dollar buy, and
where does it stop buying any.**

All figures are what the provider billed, projected to **1,000,000 items/month**. Latency
is per item, excluding one-time setup.

### What a 10× cost increase buys

A log-linear fit over the paid arms in each experiment — quality against `log10(cost)`:

| experiment | arms | quality per 10× cost | as % of the best arm | correlation |
|---|---|---|---|---|
| Few-NERD | 23 | +0.0405 | **+5.9%** | r = 0.49 |
| SciFact | 12 | +0.0212 | +2.8% | r = 0.34 |
| AG News | 24 | +0.0214 | +2.3% | r = 0.63 |
| DBpedia | 24 | +0.0094 | +0.9% | r = 0.40 |
| summarisation | 24 | −0.0013 | **−0.4%** | r = −0.07 |

**An order of magnitude more money buys between nothing and six percent.** On
summarisation the slope is *negative* and the correlation is zero — across 24 arms and a
143× price range, cost carried no information about quality at all.

Even the best case is a bad trade at scale: Few-NERD's +5.9% per 10× means going from
$27/month to $2,463/month (a 91× step) buys about 11 points of F1 — and a **free** local
model beats the top of that range by 11.4%.

### The same picture at production scale

| experiment | | arm | quality | $/month at 1M items | vs the best |
|---|---|---|---|---|---|
| **summarisation** | best | `bart_l` (local) | 0.3461 | **free** | — |
| | dearest | `anthropic_l` | 0.3155 | **$9,826** | **−8.9%** |
| | best paid | `deepseek_m` | 0.3460 | $191 | −0.0% |
| **AG News** | best | `bert_mini` (local) | 0.9450 | **free** | — |
| | dearest | `anthropic_l` | 0.9000 | $875 | −4.8% |
| | best paid | `anthropic_m` | 0.9100 | $351 | −3.7% |
| **DBpedia** | best | `qwen_m` | 0.9929 | **$51** | — |
| | dearest | `anthropic_l` | 0.9893 | **$1,351** | **−0.4%** |
| **Few-NERD** | best | `span_marker` (local) | 0.7674 | **free** | — |
| | dearest | `anthropic_l` | 0.6798 | **$2,463** | **−11.4%** |
| **SciFact** | best | `glm_s` | 0.7437 | $711 | — |
| | dearest | `glm_m` | 0.7419 | $2,288 | −0.2% |

One row per experiment, since each says something different:

- **Summarisation: $9,826/month buys −8.9%** against free, and **−0.0% against $191/month.**
  The dearest arm is beaten by a model costing 51× less.
- **AG News: $875/month buys −4.8%** against free. The gap to the best paid arm
  ($351/month) is −3.7%, so here the money is buying a *deficit* either way.
- **DBpedia: $1,351/month buys −0.4%** against $51/month — 26× the price for slightly
  worse output, and not statistically separable. **But this is also the one experiment
  where paying beats free by a mile** (+58%); see the table below for why.
- **Few-NERD: $2,463/month buys −11.4%** against a free model on a CPU. The largest
  free-vs-paid gap in the set, and the free arm separates from all 26 opponents.
- **SciFact: $2,288/month buys −0.2%** against $711/month, and the $711 arm buys **+3.4%
  over free** — the one case where paying is defensible, and even there the free arm is
  not statistically separated from it.

In no experiment did the most expensive option win. In three of five, the free option did.

### What "free" actually gets you, in all five

The free-vs-paid comparison in full, because the two cases where free *loses* are the more
instructive ones:

| experiment | best free arm | quality | rank | best paid arm | quality | $/month | verdict |
|---|---|---|---|---|---|---|---|
| Few-NERD | `span_marker` 476 MB | 0.7674 | **1** | `openai_m` | 0.6864 | $2,324 | **free wins +11.8%** |
| AG News | `bert_mini` 44 MB | 0.9450 | **1** | `anthropic_m` | 0.9100 | $351 | **free wins +3.8%** |
| summarisation | `bart_l` 1.6 GB | 0.3461 | **1** | `deepseek_m` | 0.3460 | $191 | free wins +0.0% *(a tie)* |
| SciFact | `e5_base` 438 MB | 0.7191 | 9 | `glm_s` | 0.7437 | $711 | paid wins +3.4%, **not separated** |
| DBpedia | `bart_mnli` zero-shot | 0.6286 | **25** | `qwen_m` | 0.9929 | $51 | **paid wins +58%** |

**The DBpedia row is not a counterexample — it is the control.** Its free arm is
`bart_mnli`, a *zero-shot* NLI model that has never seen the task, because the fine-tuned
DBpedia checkpoint could not be loaded on this machine (a pickle checkpoint blocked by
[CVE-2025-32434](https://github.com/advisories/GHSA-53q9-r3pm-6pq6); see
[`HANDOVER_DBPEDIA_BLOCKED_ARM.md`](HANDOVER_DBPEDIA_BLOCKED_ARM.md)). It is the only
experiment where **no fine-tuned free arm ran**, and it is the only experiment where free
loses badly.

So the axis is not free-versus-paid. It is:

> **trained on your task** → beats everything, at $0
> **not trained on your task** → loses to everything, also at $0

Few-NERD proves it directly with a matched pair: `span_marker` (fine-tuned on Few-NERD)
scores 0.7674 and `gliner` (same model class, never trained on it) scores 0.4540 — a
**+0.3134** gap from exposure alone, with price held at zero on both sides.

SciFact is the genuinely marginal case and deserves its own reading: `e5_base` is
retrieval-*trained* but not on SciFact specifically, and it lands mid-field — beaten by
0.0246 which the separation test cannot resolve. That is what "partially trained for the
task" looks like: not a win, not a rout, and cheap enough that $711/month for +3.4% is a
real decision rather than an obvious one.

**And free is not only cheaper, it is faster.** `bert_mini` answers in 7 ms against
1.92 s for the best paid arm on the same task — 192× — and `e5_base` in 0.06 s against
3.12 s. The exception is `bart_l` at 11.01 s — 23rd slowest of 25, though not last: two hosted
arms (`mistral_l` 11.04 s and `qwen_s` 25.04 s) are slower still. It is a 1.6 GB seq2seq
model generating on a CPU. Free buys latency on *classification and embedding*, and costs
it on *generation*.

### The cheapest arm you cannot tell apart from the best

Eyeballing "within 2%" is not a test. Using Holm separation — the cheapest **paid** arm
that the winner does **not** statistically separate from:

| experiment | tied with the winner | cheapest tied arm | $/1k items | vs the dearest arm |
|---|---|---|---|---|
| summarisation | 13 arms | `deepseek_s` | $0.069 | **143× cheaper** |
| DBpedia | 18 arms | `gemma_m` | $0.012 | **116× cheaper** |
| AG News | 9 arms | `gemma_s` | $0.011 | **82× cheaper** |
| SciFact | 12 arms | `deepseek_s` | $0.300 | 8× cheaper |
| Few-NERD | 0 arms | — | — | *no paid arm ties the winner* |

**In four of five experiments you can drop 8× to 143× of your inference bill and the data
cannot detect the difference.** Few-NERD is the exception and it goes the other way: no
paid arm is indistinguishable from the free one.

### Cost does not buy speed

| experiment | correlation, log(cost) vs latency | hosted latency range | fastest local arm |
|---|---|---|---|
| Few-NERD | **r = −0.30** | 0.79 – 5.94 s | `gliner` 0.17 s |
| summarisation | r = −0.18 | 1.28 – 25.04 s | `bart_l` 11.01 s |
| DBpedia | r = +0.02 | 0.44 – 12.35 s | `bart_mnli` 5.72 s |
| SciFact | r = +0.03 | 1.14 – 17.48 s | `bge_small` 0.03 s |
| AG News | r = +0.20 | 0.44 – 7.66 s | `bert_mini` **0.007 s** |

Essentially uncorrelated, and negative twice. **Price is not a proxy for latency**, and
the spread *within* the hosted field (up to 20×) dwarfs anything cost predicts.

Local models are a different regime entirely: `bert_mini` answers in **7 ms** against
0.44–7.66 s for hosted arms on the same task — 44× to 766× faster, with no network in the
path. What they cost instead is **setup**: e5-base takes 1,825 s to embed the SciFact
corpus once, BM25 takes 0.8 s for the same job. That is a real cost, it is reported as
`warmup_ms` rather than hidden, and it is paid once rather than per item.

### The task shape sets the bill, not the model

Cost per item varies more across *tasks* than across *models*:

| task | input tokens per item | why |
|---|---|---|
| classification | ~104 | one snippet in, one word out |
| NER | ~125 | one sentence in, a short JSON array out |
| summarisation | ~776 | a full news article in |
| **retrieval reranking** | **~3,926** | the prompt carries **20 full abstracts** |

A reranking prompt costs **38× more per item** than a classification prompt on the same
model at the same price (3,926 vs 104 input tokens, measured). Before shopping for a
cheaper model, check whether the *architecture* is what is expensive: on the SciFact dev
slice, halving the rerank depth from 20 to 10 cut input tokens from 3,926 to 2,027 — a
**48% bill reduction** — for 0.011 nDCG@10. Both halves of that comparison ran under the
same (pre-reasoning-fix) instrument, so the delta is internally valid but is not
comparable to the measurement table above.

No model substitution in any of these five experiments moved cost that far for that
little.

## What this means if you are choosing a model

Ordered by what they are worth, not by how obvious they are.

1. **Start with the task shape, not the model.** A reranking prompt costs 38× per item
   what a classification prompt does on the same model. The largest cost lever here was
   architectural, and no model choice could recover it.
2. **If you can label a few thousand examples, fine-tune a small model.** It won outright
   in three of five and tied in a fourth — at **$0/month against up to $9,826/month**, and
   44×–766× lower latency. This is the single biggest lever in the table.
3. **Never buy the most expensive arm.** Five for five it was not the best, and in three
   experiments it was *worse* than free while costing $875–$9,826/month.
4. **Pick the cheapest arm your test cannot separate from the leader.** That is 8×–143×
   cheaper than the dearest, in four of five. Requires a separation test, not a
   leaderboard — "ahead on the average" was true of the leader in 100% of cases and meant
   almost nothing.
5. **Do not select on a pilot.** ρ ≈ 0.8 feels like enough and picked the wrong winner
   three times in five. Use the pilot to catch instrument bugs, which is what it is
   genuinely good for.
6. **Read the items your whole field gets wrong before you read the ranking.** On a
   saturated benchmark that is where the ceiling is, and it is annotation rather than
   capability.
7. **Budget attention for the scorer, not just the model.** Three separate scoring bugs
   here moved an arm further than most model swaps did.

**When paying more IS right**, and this report should not be read as saying never: when
you cannot label data and the task is unlike anything a small model was trained on; when
the quality difference is worth more than the bill (at 1,000 items/month the entire
DBpedia spread is $1.35 and the analysis is not worth your time); when a single wrong
answer is expensive; or when engineering time to fine-tune and host costs more than the
API. The finding is not that expensive models are bad — it is that **price stops
predicting quality long before it stops rising**, so the premium has to be justified by
something other than the leaderboard.

## What this cannot say

- **Five tasks, all English, all text.** No multilingual, multimodal, long-context,
  agentic or generative-quality task. The tie-at-the-top result may be a property of
  *saturated-ish academic benchmarks* rather than of frontier models.
- **One pass per arm, temperature 0.** Every interval here is over *items*, never over
  *runs*. Run-to-run variance is real and unmeasured — two runs of an identical SciFact
  config scored 0.6691 and 0.6617, because OpenRouter routes across providers.
- **24 hosted arms, one snapshot in time, no verifiable identity.** A provider can change
  weights behind an alias; runs record `identity_declared: true`, not proof.
- **Five of the 24 arms never ran on SciFact** (the frontier tier, $31.40 against that
  sweep's $2.45), so §1 and §2 are weaker there than elsewhere. One NER arm and several
  local ML arms are also unrun — see the handovers in this directory.
- **Nothing here measures factual accuracy, safety, or instruction-following.** ROUGE is
  n-gram overlap; accuracy is label match. A confident, fluent, wrong answer scores well on
  several of these metrics, and the reports say so individually.
- **§5 is three corpora, not five.** Two were never checked for gold errors, and their
  absence from the table is a gap, not a clean bill.
- **The economics in §8 price inference and nothing else.** No engineering time to
  fine-tune or host a local model, no GPU rental, no maintenance, no serving
  infrastructure, no cost of a wrong answer. "Free" means *zero inference cost*, and a
  local model that takes a week to set up is not free in any sense a business recognises.
- **The 1M-items/month projections are linear extrapolations** from 200–280 item runs.
  They ignore volume discounts, batch pricing, caching, and rate limits — all of which a
  real deployment at that scale would negotiate or hit. Treat them as *ratios* that are
  sound, and absolute figures that are indicative.
- **Prices are one snapshot**, taken 2026-09-28/29 through one reseller. Model pricing
  moves fast and the ordering of vendors is the least durable finding here. The
  *structure* — that price stops predicting quality — is what is expected to survive.

---

## Reproduction

```bash
cd harness
# §1, §3 — cost and rank by experiment, from what the provider billed
python scripts/leaderboard.py --dataset-id few_nerd_280        # and the other four
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
```

Terms, models, datasets and tests are defined in
[`../docs/REFERENCE.md`](../docs/REFERENCE.md). The append-only journal of how each finding
arrived — including the ones that were retracted — is [`NOTES.md`](NOTES.md), 56 entries.
