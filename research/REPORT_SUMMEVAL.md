# Evaluation report — 24 LLM judges and seven free scorers on SummEval

**Dataset** `summeval_100` · 100 CNN/DailyMail test articles (87 DailyMail, 13 CNN) · 16 machine summaries each · expert scores on four dimensions
**Protocol** Kendall τ-b per article between a judge's scores and the expert means, averaged over coherence, consistency, fluency and relevance · Spearman ρ beside it · calibration: ROUGE-1 τ 0.1487 vs G-Eval's published 0.150 — [docs/PROTOCOL.md](../docs/PROTOCOL.md)
**Arms** 24 hosted LLM judges (8 vendors × 3 tiers, one replacement) · BARTScore · ROUGE-1/2/L · this repository's `coverage` · `length` · `random`
**Design** 1 pass per arm · one call per article, all 16 summaries in one prompt · temperature 0, reasoning off, `max_tokens` 1500 · **$7.03 billed**
**Date** 2026-10-18 · **Harness** [`../harness`](../harness) · **Example** [`../examples/summeval-judging`](../examples/summeval-judging)
**Costs** are what the provider billed (`usage.cost`), not the price in each config — see §6

> **The first experiment where the model grades instead of answers.** Every other
> experiment here asks a system to *do* a task. This one asks it to *judge* other systems'
> work, and measures the judge by how well its scores order 16 summaries the way three
> experts did. It is the LLM-as-judge question every silver reference and every automated
> eval pipeline rests on, made measurable.

> **This is the sixth experiment.** It is also the first where the free option lost: every
> hosted judge is separated from, and ahead of, the best free scorer.

---

## Executive summary

### The decision, in one table

| the choice | what the data says |
|---|---|
| **Can an LLM judge summaries like an expert?** | **Close to one expert, measurably below, and far ahead of every free scorer measured.** Against the three experts the best judges reach τ **0.5398**, BARTScore **0.2562** and ROUGE-1 **0.1487**. Measured on the same footing as a human — against the mean of two experts — the best judge reaches **0.5195**, **93%** (95% interval 89–97%) of one expert's agreement with the other two (**0.5587**); BARTScore reaches 44%. The 93% is the best of 24 judges chosen on these same articles, and each judge sees all 16 summaries at once while an expert scored them one by one (§3.7). |
| **Which judge?** | **A six-way tie at the top**: `openai_l`, `gemma_l`, `anthropic_l`, `openai_m`, `qwen37max`, `qwen_s` (§3.2). The leader is separated from the other 25 arms. |
| **Cheapest judge in the tie?** | **`gemma_l`** (Gemma 4 31B, open weights) — **$0.0278** for 100 articles, **$278 per million articles** (each one call that judges 16 summaries), against $6,350 for the leader and $20,077 for `anthropic_l`. |
| **Do I need an LLM here at all?** | **Yes, against every free scorer measured** — the first of six experiments where every free arm is separated below every LLM. Every one of the 24 judges is separated from BARTScore (§3.3). No evaluator trained to judge summaries was run; UniEval, the free one G-Eval reports, has a published τ of 0.377, which would put it above the weakest judge here (§7). |
| **Does paying more help?** | **Somewhat, unlike summarisation.** Spearman(billed cost, τ) = **+0.437** over an 80× price range, against −0.037 there. But the cheapest member of the top tie costs 1/23 of the leader. |
| **Is a small sample enough to rank judges?** | **To order them, yes; to crown one, no.** Two disjoint 20-article halves agree at ρ = **0.90** on the order of the 24 judges, but name the same unique winner only **21%** of the time (§3.5). |
| **Is ROUGE a usable judge?** | **No.** ROUGE-1/2/L agree with experts at τ 0.14–0.16; this repository's own `coverage` at **0.1011**, below ROUGE-1. |

### What this experiment specifically found

- **Every hosted judge beats every free scorer measured.** In the paired test, BARTScore is
  separated from all 24 judges, all of them ahead (`make family-test`, Holm-corrected, §3.3).
  The free scorers here are metrics and one summariser; none was trained to judge (§7).
  Against the weakest judge, `llama_s` (τ 0.3533), BARTScore wins only 33 of 100 articles.
- **The best judges come close to a single expert, and stay measurably below one.** Scored
  against the mean of two experts, as one expert is against the other two, the best judges
  reach 93% of a human's agreement (95% interval 89–97%; the gap to the expert excludes zero,
  §3.7). The experts themselves are noisy: in 37 articles two or more systems wrote the
  same summary word for word, and 41 of those 44 groups of identical texts received
  different expert scores.
- **The top is a crowd.** `openai_l` leads at τ 0.5398 and cannot be separated from five
  others; `gemma_l` sits 0.0013 behind it at 1/23 of the price. Four of the six are tied by
  a wide margin; the other two sit on a Holm boundary (§3.2).
- **The large tier beats the small one in all eight families — Qwen's by 0.0012, and with a
  substituted model — but the ladder rises steadily in only three.** Llama, Gemma and OpenAI rise with tier; DeepSeek, GLM and Mistral peak at
  the medium tier, Anthropic's medium sits below its small, and Qwen's small leads its
  medium (§3.4). Tier is a price label, not a size: OpenAI's medium now costs more than its
  large.
- **The order is stable; the winner is not.** Rankings agree across disjoint halves far
  more than on the summarisation experiment: ρ 0.90 at 20 articles per half, against 0.333
  for the same 24 models there, by the same method — but the top is close enough that the
  unique winner changes most of the time.
- **Two models could not run as planned**, and both are findings about renting models:
  `qwen_l`'s model is no longer served by the provider, and its successor refuses to run
  with reasoning off (§6).

---

## 1. What was measured

**Items.** The 100 annotated CNN/DailyMail test articles of SummEval
([Fabbri et al. 2021](https://arxiv.org/abs/2007.12626)), each with 16 summaries from
2019-era summarisation systems and expert scores (means of three annotators) on four
dimensions. 87 of the articles are DailyMail and 13 CNN. The crowd ratings, which the paper
shows disagree with the experts, are not used. Nothing is committed; `fetch.py` downloads the
data ([docs/DATA.md](../docs/DATA.md)).

**The task given to each judge.** One call per article: the article and its 16 numbered
summaries, and a request for 1–5 scores per summary on the four dimensions, as JSON
([prompt.txt](../examples/summeval-judging/prompt.txt), hashed into every run's fingerprint).
The judge never sees the human reference summaries.

**Arms.** The same 24 hosted models as the other experiments — eight vendors, three price
tiers — with one replacement (§6), plus seven free scorers that need no model call:
BARTScore (`facebook/bart-large-cnn`, local, CPU), ROUGE-1/2/L and this repository's
`coverage` against the 11 human references, the summary's length, and seeded random scores.

## 2. How a judge is scored

For each article the judge's scores on one dimension are compared with the expert means by
**Kendall τ-b** over the 16 summaries; the four dimensions are averaged into `tau`. τ-b
corrects for ties on both sides, which matters: integer 1–5 scores tie constantly, and
`tie_rate` reports how often. Because the score is per article, the harness's paired
permutation tests and Holm correction apply unchanged.

An unreadable reply scores τ = 0 on the dimensions it fails, never skipped. Two judges had
any: `gemma_m` parsed three of four dimensions on two articles, and `qwen_s` was cut off by
`max_tokens` on one article and scores 0 there (`parsed` 0.995 and 0.99).

## 3. Results

### 3.1 The leaderboard

τ against the experts, averaged over four dimensions, 100 articles; billed cost for all 100.

| rank | arm | model | τ | ρ | billed | ms / article |
|---|---|---|---|---|---|---|
| 1 | `openai_l` | GPT-6-sol | **0.5398** | 0.6018 | $0.6350 | 2,228 |
| 2 | `gemma_l` | Gemma 4 31B | **0.5384** | 0.5977 | $0.0278 | 6,670 |
| 3 | `anthropic_l` | Claude Opus 5 | 0.5283 | 0.5868 | $2.0077 | 3,427 |
| 4 | `openai_m` | GPT-5.5 | 0.5279 | 0.5870 | $1.4153 | 2,690 |
| 5 | `qwen37max` | Qwen3.7 Max | 0.5204 | 0.5812 | $0.4436 | 4,514 |
| 6 | `qwen_s` | Qwen3.8 Flash | 0.5192 | 0.5810 | $0.0385 | 3,954 |
| 7 | `glm_m` | GLM-4.6 | 0.5170 | 0.5711 | $0.1144 | 3,609 |
| 8 | `qwen_m` | Qwen3.7 Plus | 0.5075 | 0.5709 | $0.1084 | 6,770 |
| 9 | `glm_l` | GLM-5 | 0.4916 | 0.5464 | $0.2451 | 3,590 |
| 10 | `deepseek_m` | DeepSeek V4.1 Flash | 0.4861 | 0.5421 | $0.0771 | 1,120 |
| 11 | `anthropic_s` | Claude Haiku 4.5 | 0.4836 | 0.5414 | $0.3237 | 2,433 |
| 12 | `anthropic_m` | Claude Sonnet 5 | 0.4802 | 0.5394 | $0.8048 | 3,008 |
| 13 | `gemma_m` | Gemma 4 26B-A4B | 0.4770 | 0.5319 | $0.0252 | 4,308 |
| 14 | `deepseek_l` | DeepSeek V4 Pro | 0.4695 | 0.5297 | $0.0258 | 5,535 |
| 15 | `mistral_m` | Mistral Medium 3.1 | 0.4677 | 0.5309 | $0.1191 | 1,946 |
| 16 | `deepseek_s` | DeepSeek V4 Flash | 0.4590 | 0.5141 | $0.0307 | 3,985 |
| 17 | `mistral_l` | Mistral Large 2512 | 0.4554 | 0.5143 | $0.1257 | 10,885 |
| 18 | `llama_l` | Llama 4 Maverick | 0.4537 | 0.5081 | $0.0594 | 12,346 |
| 19 | `glm_s` | GLM-4.5 Air | 0.4456 | 0.5017 | $0.0481 | 5,617 |
| 20 | `mistral_s` | Mistral Small 3.2 24B | 0.4275 | 0.4762 | $0.0283 | 9,185 |
| 21 | `gemma_s` | Gemma 3 27B | 0.4196 | 0.4623 | $0.0279 | 11,572 |
| 22 | `openai_s` | GPT-5.4 mini | 0.4111 | 0.4614 | $0.2124 | 1,551 |
| 23 | `llama_m` | Llama 3.3 70B | 0.4064 | 0.4553 | $0.0517 | 4,834 |
| 24 | `llama_s` | Llama 4 Scout | 0.3533 | 0.3976 | $0.0297 | 7,141 |
| 25 | `bartscore` | BART-large-CNN, local | **0.2562** | 0.3246 | $0 | 15,662 |
| 26 | `rouge2` | ROUGE-2 F1 | 0.1578 | 0.2009 | $0 | 181 |
| 27 | `rouge1` | ROUGE-1 F1 | 0.1487 | 0.1896 | $0 | 196 |
| 28 | `rougeL` | ROUGE-L F1 | 0.1435 | 0.1842 | $0 | 274 |
| 29 | `coverage` | this repo's summarisation metric | 0.1011 | 0.1303 | $0 | 892 |
| 30 | `length` | word count | 0.0388 | 0.0476 | $0 | 0 |
| 31 | `random` | seeded random | 0.0025 | 0.0029 | $0 | 0 |

Hosted latency is mostly waiting on the provider; BARTScore's is a CPU forward pass per
summary on the machine that measured it.

**Is the ordering real?** Yes: the global permutation test on within-article ranks gives
p = 0.0002, and 289 of 465 pairs are distinguishable (`make leaderboard`).

### 3.2 A six-way tie at the top

The leader tested against every other arm on the same articles — paired sign-flip
permutation, Holm step-down over the 30 opponents (`make family-test A=se_openai_l_n100_v1
METRIC=tau`):

| tied with the leader | Δτ vs leader | articles the leader wins | p | Holm threshold |
|---|---|---|---|---|
| `gemma_l` | −0.0013 | 49 of 100 | 0.8585 | 0.0500 |
| `anthropic_l` | −0.0115 | 61 of 100 | 0.1325 | 0.0250 |
| `openai_m` | −0.0118 | 58 of 100 | 0.0790 | 0.0167 |
| `qwen_s` | −0.0205 | 61 of 100 | 0.0112 | 0.0125 |
| `qwen37max` | −0.0193 | 58 of 100 | 0.0108 | 0.0100 |

`openai_l` is separated from the other 25. Two members sit on the boundary: `qwen37max`
(p 0.0108 against a threshold of 0.0100) and `qwen_s` (0.0112 against 0.0125) — a few
articles either way would move them in or out. `glm_m` is the nearest arm outside
(p 0.0072, threshold 0.0083).

How fragile is that boundary? Not to the permutation draw: at 400,000 permutations, under
three seeds (`--permutations 400000 --seed 0/1/2`), `qwen37max` gets p = 0.0105–0.0112
against its 0.0100 and stays tied every time, and `glm_m` (0.0063–0.0066) stays separated.
The two edge members move *together*: Holm stops at the first opponent it cannot separate,
so if `qwen37max` were separated, `qwen_s` (p ≈ 0.012 against 0.0125) would be too, and
the group would shrink to the four that hold by a wide margin — `openai_l`, `gemma_l`
(p 0.86), `anthropic_l` (0.13) and `openai_m` (0.079). So the honest reading is **a core of
four, and possibly six**. What a different sample of articles would do to the edge is not
measured here; n = 100 is the whole benchmark.

The cheapest member of the tie is `gemma_l` at $0.0278, 1/23 of the leader and 1/72 of
`anthropic_l`. A tie is not proof of equality — it is a difference this sample cannot
detect — so it makes `gemma_l` the first candidate, not the answer.

### 3.3 Every judge beats every free scorer

BARTScore tested against all 30 other arms (`make family-test A=se_bartscore_n100_v1
METRIC=tau`): separated from all 30, behind every one of the 24 judges and ahead of every
other free scorer. The weakest judge, `llama_s`, leads it by 0.0971; BARTScore wins only 33
of 100 articles against it.

This is the first of the six experiments where no free arm measured is first, or not
separable from first. In the other five, a free local model was. Here no arm measured was
trained to judge summaries — none was fine-tuned on SummEval, and UniEval, a free trained
evaluator, was not run — and a model that scores only how likely the summary is given the
article (BARTScore) is far behind one asked to assess it.

The free scorers rank as the summarisation experiment's own analysis would predict:
BARTScore, which never sees a reference, beats every reference-based metric; plain ROUGE-1
beats this repository's `coverage` (0.1011, against ROUGE-1's 0.1487), most of the gap in consistency
and fluency; and the experts were not rewarding length (τ 0.0388).

### 3.4 Tier, by family: large beats small in all eight, steadily in three

τ by price tier within each vendor:

| family | small | medium | large |
|---|---|---|---|
| Llama | 0.3533 | 0.4064 | 0.4537 |
| Gemma | 0.4196 | 0.4770 | 0.5384 |
| OpenAI | 0.4111 | 0.5279 | 0.5398 |
| DeepSeek | 0.4590 | 0.4861 | 0.4695 |
| GLM | 0.4456 | 0.5170 | 0.4916 |
| Mistral | 0.4275 | 0.4677 | 0.4554 |
| Anthropic | 0.4836 | 0.4802 | 0.5283 |
| Qwen | 0.5192 | 0.5075 | 0.5204 (`qwen37max`) |

The large tier beats the small one in every family. The ladder rises steadily in three; in
the other five the middle or the smallest tier is at least as good as the next one up. Whether any single step is a real difference is a pair
test this report has not run; the pattern is the finding.

Across all 24, more expensive judges do score somewhat higher: Spearman(billed cost, τ) =
+0.437 over an 80× range. In the summarisation experiment price carried no information
about quality (Spearman −0.037 across its 24 hosted arms, by the same statistic).

### 3.5 The order is stable, the winner is not

Split-half stability among the 24 judges: two disjoint sets of *n* articles, the judges
ranked independently on each, 400 seeded draws (`harness/scripts/summeval_analysis.py`,
from the committed runs):

| articles per half | ρ (half A, half B) | 5th percentile | same unique winner |
|---|---|---|---|
| 10 | 0.821 | 0.702 | 20% |
| 20 | 0.902 | 0.837 | 21% |
| 50 | 0.960 | 0.933 | 12% |

With all 31 arms included (`make rank-stability METRIC=tau`) ρ is higher still (0.953 at 20
per half), because the free scorers sit far below the judges and are easy to agree on.

The order of the judges is far more stable than the summarisation experiment's. The same
24 hosted models, ranked there by the same split-half method at 20 articles per half, agree
at ρ **0.333**; that report's own figure, over its whole 29-arm field, is 0.443
([REPORT_SUMMARIZATION §3.6](REPORT_SUMMARIZATION.md)). Why is not tested here; the field
is also more spread out (the judges span τ 0.35–0.54, where the summarisation arms sit
within about 0.04 of each other), and a wider field is easier to order. The winner is a
different matter: the top six are close enough that the unique leader changes in most draws, which is what §3.2's tie says in
another way.

### 3.6 By dimension

| dimension | best judge | τ | worst judge | τ |
|---|---|---|---|---|
| coherence | `gemma_l` | 0.5661 | `llama_s` | 0.3135 |
| consistency | `openai_l` | 0.6345 | `llama_s` | 0.4494 |
| fluency | `glm_m` | 0.5261 | `llama_s` | 0.3108 |
| relevance | `openai_l` | 0.5099 | `llama_s` | 0.3396 |

Consistency — whether the summary's facts are supported by the article — is where judges
agree with experts most, and it is the dimension that matters most for factuality. A
judge's tie rate barely predicts its quality (Spearman +0.10 across the 24).

### 3.7 How close to an expert?

τ 0.54 says how well a judge orders summaries the way the experts do, not how close that is
to expert-level. That needs the experts' agreement with each other, and the gold here keeps
only their mean. SummEval's original release publishes each expert's own scores
([`model_annotations.aligned.jsonl`](https://storage.googleapis.com/sfr-summarization-repo-research/model_annotations.aligned.jsonl),
MIT), so `examples/summeval-judging/human_ceiling.py` computes it: for every article and
dimension, Kendall τ-b between one expert and the mean of the other two, averaged exactly as
a judge's τ is. Before using the file it checks that its three-expert means reproduce this
experiment's gold on every article, and that re-scoring every arm's committed outputs
reproduces its committed τ.

A judge scored against all three experts has an easier target than one expert scored
against two, so every arm is also scored against the same two-expert references, averaged
over which expert is left out:

| | τ against two experts | share of one expert's |
|---|---|---|
| **one expert, against the other two** | **0.5587** | — |
| `gemma_l` | 0.5195 | **93%** |
| `openai_l` | 0.5181 | 93% |
| `anthropic_l` | 0.5083 | 91% |
| `llama_s` (the weakest judge) | 0.3423 | 61% |
| `bartscore` | 0.2447 | 44% |
| `rouge1` | 0.1454 | 26% |
| `coverage` | 0.0955 | 17% |

**The best judges agree with the experts about 93% as well as an expert does** — 95%
interval 89–97% by a paired bootstrap over articles, and the gap to the expert (0.0152 to
0.0624 for `gemma_l`) excludes zero, so they are close and measurably below. Two cautions
on reading it as "an LLM is nearly an expert". The best judge is the best of 24 chosen on
these same articles, which the interval does not correct for. And a judge sees all 16
summaries in one prompt and can rank them against each other, which is what a per-article
rank correlation rewards, while an expert scored summaries one at a time. The order at
the top changes on this footing (`gemma_l` above `openai_l`), which is the tie of §3.2
showing again. The three positions in the file give 0.5213–0.5812 for "one expert against
the other two"; whether those are three people depends on the file keeping one annotator
order on every row, which its documentation does not say, so only the mean is reported as
the ceiling.

The experts are not a noiseless target either. In 37 of the 100 articles, two or more of the
16 systems produced the same summary word for word — 44 groups of identical texts — and 41
of those groups received different expert scores (different mean scores, so this does not
depend on the annotators' order in the file). Whether the gap between 93% and 100% is
the judges falling short or the experts' own noise is not something this sample can split.

## 4. Discussion

**For anyone using an LLM as a judge.** On this task a hosted judge is clearly better than
any free metric, and a cheap open-weight one cannot be told apart from the dearest
proprietary ones on this sample. The practical reading: use a judge, start with the cheapest
member of the top group, and check it against a small set of human judgements on your own
outputs — which is exactly what this experiment does at scale.

**For this repository's other experiments.** The summarisation experiment ranks its arms by
`coverage`. Here `coverage` agrees with experts at τ 0.1011, below plain ROUGE-1. That does
not invalidate the summarisation results, which test separations rather than read absolute
quality, but it says how much a `coverage` lead can be taken to mean about what a person
would prefer.

**Against the literature.** G-Eval reports GPT-4 at τ 0.418 on this data with its own
prompt and probability-weighted scoring. Most judges here exceed that with plain integer
scores, one call per article; the comparison is across different prompts and model
generations and is not a calibration.

## 5. Calibration

[G-Eval](https://arxiv.org/abs/2303.16634), Table 1, reports ROUGE-1 against these experts
at ρ 0.192, τ 0.150, averaged over four dimensions. Measured here on the same 100 articles,
ROUGE-1 F1 averaged over the 11 references: **ρ 0.1896, τ 0.1487**, and within 0.01 of the
published value on every dimension. ROUGE-2 reproduces too (τ 0.1578 against 0.161, within
0.01 on every dimension). ROUGE-L does not, quite: its average is 0.1435 against 0.128 and
its coherence 0.1530 against 0.099. The average gap (0.0155) sits inside the 95% interval
over articles (±0.0322); the coherence gap (0.054) does not (±0.0422), and passes only with
the 0.02 allowance this repository's rule adds for protocol differences (`calibrate.py`,
as for NER and SciFact). So it counts as consistent by the rule and is not a reproduction:
G-Eval scored these same 100 articles, so a gap of that size is a difference of protocol rather than of sample; the paper
does not say which ROUGE-L it ran, and this is `rouge_score`'s `rougeL` with stemming. The
three rows, with their intervals, are in
[`docs/evidence/calibration/summeval.json`](../docs/evidence/calibration/summeval.json),
written by `examples/summeval-judging/calibrate.py`.
BARTScore comes out at τ 0.2562 against G-Eval's 0.305; G-Eval does not state its variant,
and ours is plain `bart-large-cnn`, source → summary, so it is reported as measured and not
counted as a calibration row.

## 6. What changed while measuring

**`qwen_l` could not run.** Its model, `qwen/qwen3-max`, is no longer served by OpenRouter:
the model page remains, but its list of endpoints is empty (checked 2026-10-18), and it was
already missing from the model listing on 2026-10-15. Four of the other five experiments
measured it, on 2026-09-26 to 09-28; SciFact's sweep did not include it. The run failed at warm-up (404) and billed nothing. Qwen's current flagship, `qwen/qwen3.8-max-0902`, refuses reasoning
disabled ("Reasoning is mandatory for this endpoint"), which this field's protocol does not
allow. The previous flagship, `qwen/qwen3.7-max`, accepts it (tested: 0 reasoning tokens)
and runs as `qwen37max` — its own config, never read as `qwen_l`.

**Prices moved since the configs were written.** Each config carries the per-token price
the earlier experiments used (September 2026); OpenRouter's prices on the day of this run
differ, in both directions — GPT-5.5 is now $5/$30 per million tokens against $1.25/$10 in
its config, the three GLM models roughly tripled, DeepSeek V4 Pro and Claude Sonnet 5 fell.
The costs in this report are the bills, so they are right; the dry-run estimates, which use
the config prices, were not. One consequence: within OpenAI the medium tier now costs more
than the large one, so "price tier" here is a label, not a price order. Cost comparisons
between this experiment and the earlier five mix September and October prices.

## 7. NOT covered, NOT measured, NOT verified

- **No evaluator trained to judge summaries was run.** The free arms are reference metrics
  (ROUGE, `coverage`), a length and a random floor, and BARTScore, a summariser scored by
  likelihood; none was trained to judge summaries. UniEval, the free trained evaluator in
  G-Eval's table, reports τ 0.377 (ρ 0.474) there, which would put it above the weakest
  judge here (`llama_s`, 0.3533), though under G-Eval's protocol, not this one. "Every judge beats every free scorer" is about the seven measured. UniEval is
  the next arm to run.

- **n = 100 articles**, below the usual 200, and every summary is from a 2019-era system.
  Modern summaries are more fluent; a judge's skill at catching 2019 failures may not
  transfer.
- **One prompt, all 16 summaries in one call, four dimensions together.** Scoring one
  summary per call, one dimension per call, or with token probabilities (G-Eval's method)
  are different judges and are not measured.
- **Reasoning off for every judge.** A judge allowed to reason first may score differently;
  not measured.
- **No own-family test.** None of the 16 summarisers is one of the 24 judges' families, so
  this experiment cannot test whether a judge favours its own family's outputs — the bias
  the summarisation experiment found for model-written references.
- **The annotations are public** and may be in some judges' training data; memorising
  per-summary scores for 1,600 summaries is unlikely but not ruled out.
- **One pass per judge.** Run-to-run variance at temperature 0 is not measured here; in the
  summarisation experiment's three-run sweep only 9.8% of hosted outputs were byte-identical
  across the three.
- **Within-family steps are not pair-tested** (§3.4); the size pattern is descriptive.
- **Costs are October 2026 bills**; the earlier five experiments' costs are September bills.
- **The tie in §3.2 has two boundary members.** They are stable to the permutation draw
  (§3.2); what a different sample of articles would do to them is not measured.
- **The human ceiling is one expert against two.** It is computed from the original
  release's per-expert scores (§3.7) and is somewhat pessimistic, since two experts are a
  noisier reference than three. The judges' 93% has a bootstrap interval, but the best judge
  is selected on the same articles, and the judge's all-16-at-once prompt is a different
  task from an expert's one-at-a-time scoring; neither is corrected for.

## 8. Reproduction

```bash
make data EXP=summeval                     # environment, fetch, hash check
make reproduce EXP=summeval LEVEL=local    # the seven free arms, $0
make reproduce EXP=summeval LEVEL=hosted   # the 24 judges, one LiteLLM or OpenRouter key
cd harness && make leaderboard DATASET_ID=summeval_100
make family-test DATASET_ID=summeval_100 A=se_openai_l_n100_v1 AGAINST=se_ METRIC=tau
python scripts/summeval_analysis.py            # §3.4–§3.6: split-half, price, ladders, dimensions
cd .. && examples/summeval-judging/.venv/bin/python examples/summeval-judging/calibrate.py   # §5
examples/summeval-judging/.venv/bin/python examples/summeval-judging/human_ceiling.py       # §3.7
```

`make ci` checks every figure in this report against those two scripts and the committed
runs (`harness/scripts/check_report_claims.py`).
