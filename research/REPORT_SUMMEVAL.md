# Evaluation report — 24 LLM judges and nine free scorers on SummEval

**Dataset** `summeval_100` · 100 CNN/DailyMail test articles (87 DailyMail, 13 CNN) · 16 machine summaries each · expert scores on four dimensions
**Protocol** Kendall τ-b per article between a judge's scores and the expert means, averaged over coherence, consistency, fluency and relevance · Spearman ρ beside it · calibration: ROUGE-1 τ 0.1487 vs G-Eval's published 0.150 (ROUGE-L only within the rule's allowance), UniEval 0.3717 vs 0.377 — [docs/PROTOCOL.md](../docs/PROTOCOL.md)
**Arms** 24 hosted LLM judges (8 vendors × 3 tiers, one replacement) · UniEval, a trained evaluator, on two sets of inputs · BARTScore · ROUGE-1/2/L · this repository's `coverage` · `length` · `random`
**Design** 1 pass per arm · one call per article, all 16 summaries in one prompt · temperature 0, reasoning off, `max_tokens` 1500 · **$7.03 billed**
**Date** free arms 2026-10-15, judges and UniEval 2026-10-18, paired side runs 2026-10-19 · **Harness** [`../harness`](../harness) · **Example** [`../examples/summeval-judging`](../examples/summeval-judging)
**Costs** are what the provider billed (`usage.cost`), not the price in each config — see §6

> **The first experiment where the model grades instead of answers.** Every other
> experiment here asks a system to *do* a task. This one asks it to *judge* other systems'
> work, and measures the judge by how well its scores order 16 summaries the way three
> experts did. It is the LLM-as-judge question every silver reference and every automated
> eval pipeline rests on, made measurable.

> **This is the sixth experiment.** It is also the first where no free scorer (no model call)
> is first or tied with first: the best, UniEval — an evaluator trained for these four
> dimensions — is separated below 23 of the 24 judges; only the weakest is not separated
> from it. The cheapest judge in the top group, `gemma_l`, is open weights at $0.028 per 100
> articles hosted; running it locally was not tested.

---

## Executive summary

**Use an LLM judge, and start with `gemma_l`** (Gemma 4 31B, open weights, hosted: **$0.0278**
for 100 articles), the cheapest of the judges the leader `openai_l` cannot be separated from
(§3.2). The best judges reach **0.5195**, **93%** (95% interval 89–97%) of one expert's agreement with the other two (**0.5587**): close to an expert,
measurably below. Every free scorer is far behind: UniEval reaches 64% (60% on this experiment's inputs), BARTScore 44%, ROUGE-1 26%. Before relying on any judge, check it against a small set of
human judgements on your own outputs (§4).

How sure this is: it covers 2019-era summaries, 100 articles, all 16 summaries ranked in one
call, reasoning off, one pass per judge (§7). The 93% is the best of 24 chosen on these
articles (92% when the judge is chosen on half the articles and scored on the other half). A
no-model lookup of which system wrote each summary already reaches 63% of an expert, so how
much of a judge's score is reading the summary rather than recognising its system is not
measured (§3.7). And no provider was pinned: `gemma_l` scored 0.0113 apart and billed 3.7×
apart on two providers, one run each (§3.3).

### Supporting facts

| the choice | what the data says |
|---|---|
| **Can an LLM judge summaries like an expert?** | **Close to one expert, measurably below, and far ahead of every free scorer measured.** Against the three experts the best judges reach τ **0.5398**; UniEval, the best free scorer, **0.3717** on its own inputs (0.3476 on this experiment's), BARTScore **0.2562**, ROUGE-1 **0.1487**. A no-model system-identity lookup: τ 0.3518 against two experts, 63% (§3.7). |
| **Which judge?** | **A core of four, possibly six**: the leader `openai_l` and the arms it cannot be separated from — `gemma_l`, `anthropic_l` and `openai_m` by a wide margin, `qwen37max` and `qwen_s` on a Holm boundary (§3.2). From `gemma_l` the set also takes in `glm_m`. |
| **Cheapest judge in the tie?** | **`gemma_l`** (open weights, hosted; running it locally was not tested) — **$0.0278** for 100 articles, **$278 per million articles** (each one call that judges 16 summaries), against $6,350 for the leader (1/23) and $20,077 for `anthropic_l`. Provider not pinned: the price and score can move (§3.3). |
| **Do I need an LLM here at all?** | **Yes, against the free scorers measured (UniEval is the only one trained to judge); a pointwise LLM judge was not run.** UniEval is separated below 23 of the 24 judges on mean τ and cannot be told apart from the weakest, `llama_s` (§3.3). The judges rank 16 at once and UniEval scores one at a time, so the gap is a design difference as well as a model one. On coherence alone `unievalpub` is above seven judges. |
| **Does paying more help?** | **Somewhat, and not adjusted for vendor family.** Spearman(billed cost, τ) = **+0.437** over an 80× price range; summarisation's −0.037 cannot exclude a moderate effect either way (October bills here, September there). The cheapest member of the top tie costs 1/23 of the leader. |
| **Is a small sample enough to rank judges?** | **To order them, yes; to crown one, no.** Two disjoint 20-article halves agree at ρ = **0.90** on the order of the 24 judges, helped by the wide spread of the field (judges τ 0.35–0.54, §3.5), but name the same unique winner only **21%** of the time: within the top group the order is not reliable. |
| **Is ROUGE a usable judge?** | **No.** ROUGE-1/2/L agree with experts at τ 0.14–0.16; this repository's own `coverage` at **0.1011**, below ROUGE-1. |

- **On mean τ, 23 of the 24 judges score above every free scorer, including one trained for the task.**
  UniEval ([Zhong et al. 2022](https://arxiv.org/abs/2210.07197)), a T5 evaluator trained
  for these four dimensions, is the best free scorer: τ 0.3717 on its own published inputs,
  0.3476 on this experiment's. On either, the paired test separates it below 23 judges and
  cannot separate it from the weakest, `llama_s` (τ 0.3533; raw p 0.18 and 0.70, the last
  step of the Holm order, §3.3). Every judge is separated from, and ahead of, BARTScore and
  every reference metric. The separations are on the four-dimension mean: on Spearman ρ
  `unievalpub` is above four judges, and on coherence alone above seven. How the input text
  and the provider move the scores is in §3.3.
- **The best judges come close to a single expert, and stay measurably below one.** Scored
  against the mean of two experts, as one expert is against the other two, the best judges
  reach 93% of a human's agreement (95% interval 89–97%; the gap to the expert excludes zero,
  §3.7). The experts themselves are noisy: in 37 articles two or more systems wrote the
  same summary word for word, and 41 of those 44 groups of identical texts received
  different expert scores.
- **A lookup of which system wrote each summary reaches 63% of an expert**, scoring each
  summary by the mean expert score its position got on the other 99 articles (every position
  is the same system on every article). UniEval's 64% (60%) sits at it; the best judges are
  about 30 points above. The split between reading the summary and recognising the system is
  not measured (§3.7).
- **The top is a crowd.** `openai_l` leads at τ 0.5398 and cannot be separated from five
  others (a set that depends on which arm is tested: from `gemma_l` it differs); `gemma_l`
  sits 0.0013 behind it at 1/23 of the price. Four of the six hold by a wide margin;
  `qwen37max` and `qwen_s` sit on a Holm boundary (§3.2).
- **Large is separated above small in six of the eight families; the medium steps were not
  tested.** DeepSeek and Qwen are not separated, and Qwen's large is a substituted model
  (§3.4). Tier is a price label, not a size: at this run's prices OpenAI's medium costs more than its large.
- **The order is stable; the winner is not.** Rankings agree across disjoint halves far
  more than on the summarisation experiment: ρ 0.90 at 20 articles per half, against 0.333
  for the same 24 models there, by the same method — though the judges are also far more
  spread out, and a wider field is easier to order (§3.5). The top is close enough that the
  unique winner changes most of the time.

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
tiers — with one replacement (§6), plus nine free scorers that need no model call:
UniEval (`MingZhong/unieval-sum`, local, CPU), run twice — on this experiment's text and on
UniEval's own published SummEval inputs (§3.3) — BARTScore (`facebook/bart-large-cnn`, local,
CPU), ROUGE-1/2/L and this repository's `coverage` against the 11 human references, the
summary's length, and seeded random scores.

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
| 24 | `unievalpub` | UniEval, its own published inputs, local | **0.3717** | 0.4671 | $0 | 44,694 |
| 25 | `llama_s` | Llama 4 Scout | 0.3533 | 0.3976 | $0.0297 | 7,141 |
| 26 | `unieval` | UniEval, this experiment's inputs, local | 0.3476 | 0.4387 | $0 | 41,676 |
| 27 | `bartscore` | BART-large-CNN, local | 0.2562 | 0.3246 | $0 | 15,662 |
| 28 | `rouge2` | ROUGE-2 F1 | 0.1578 | 0.2009 | $0 | 181 |
| 29 | `rouge1` | ROUGE-1 F1 | 0.1487 | 0.1896 | $0 | 196 |
| 30 | `rougeL` | ROUGE-L F1 | 0.1435 | 0.1842 | $0 | 274 |
| 31 | `coverage` | this repo's summarisation metric | 0.1011 | 0.1303 | $0 | 892 |
| 32 | `length` | word count | 0.0388 | 0.0476 | $0 | 0 |
| 33 | `random` | seeded random | 0.0025 | 0.0029 | $0 | 0 |

Hosted latency is mostly waiting on the provider; BARTScore's and UniEval's are CPU forward
passes on the machine that measured each — UniEval asks one question per summary for
coherence and relevance and one per sentence for consistency and fluency.

**Is the ordering real?** Yes: the global permutation test on within-article ranks gives
p = 0.0002, and 334 of 528 pairs are distinguishable (`make leaderboard DATASET_ID=summeval_100`).

**A reference row that is not an arm.** Each of the 16 positions is the same system on every
article (§7), so a prior that scores each summary by the mean expert score its position got
on the other 99 articles needs no model at all. It reaches τ 0.3637 (`calibrate.py`): it
would rank 25th here, between `unievalpub` and `llama_s`. The separations in this report are
on that pooled τ, which includes telling good systems from bad ones as well as reading each
summary; this report does not split the two.

### 3.2 The leader and five arms it cannot be separated from

The leader tested against every other arm on the same articles — paired sign-flip
permutation, Holm step-down over the 32 opponents (`make family-test DATASET_ID=summeval_100
A=se_openai_l_n100_v1 AGAINST=se_ METRIC=tau`):

| tied with the leader | Δτ vs leader | articles the leader wins | p | Holm threshold |
|---|---|---|---|---|
| `gemma_l` | −0.0013 | 49 of 100 | 0.8585 | 0.0500 |
| `anthropic_l` | −0.0115 | 61 of 100 | 0.1325 | 0.0250 |
| `openai_m` | −0.0118 | 58 of 100 | 0.0790 | 0.0167 |
| `qwen_s` | −0.0205 | 61 of 100 | 0.0112 | 0.0125 |
| `qwen37max` | −0.0193 | 58 of 100 | 0.0108 | 0.0100 |

`openai_l` is separated from the other 27. "Tie" here means the leader cannot be separated
from an arm, not that the six cannot be separated from each other: tested from `gemma_l`
instead (`make family-test DATASET_ID=summeval_100 A=se_gemma_l_n100_v1 AGAINST=se_ METRIC=tau`), the arms it cannot be
separated from are `openai_l`, `anthropic_l`, `openai_m`, `qwen37max`, `qwen_s` and also
`glm_m` (p 0.0107 against 0.0083). Two members sit on the boundary: `qwen37max`
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

### 3.3 The best free scorer, a trained evaluator, ties only the weakest judge

UniEval ([Zhong et al. 2022](https://arxiv.org/abs/2210.07197)) is a T5-large evaluator
trained to answer one yes/no question per dimension, for exactly these four dimensions. It
is trained in two stages: first on existing datasets for related tasks — inference,
paraphrase, sentence acceptability, yes/no questions — and an opening-sentence task on
CNN/DailyMail; then on each dimension, with CNN/DailyMail reference summaries as the
positive examples and rule-based corruptions of them as the negative ones. Its paper uses
SummEval to evaluate it and does not use these expert scores for training; the checkpoint's
training data is not checked here beyond the paper. It is the free trained evaluator in
G-Eval's table, and it runs here twice: on the text every other arm saw (`unieval`), and on
UniEval's own published SummEval inputs (`unievalpub`), the protocol its published figures
come from (§5).

Each was tested against the other 32 arms (`make family-test DATASET_ID=summeval_100
A=se_unieval_n100_v1 AGAINST=se_ METRIC=tau`, and the same for `unievalpub`):

| arm | τ | Δτ vs `llama_s`, the weakest judge | articles UniEval wins | p | separated from |
|---|---|---|---|---|---|
| `unievalpub` | 0.3717 | +0.0184 | 56 of 100 | 0.1848 | 31 of 32, all but `llama_s` |
| `unieval` | 0.3476 | −0.0057 | 51 of 100 | 0.7048 | 31 of 32, all but `llama_s` |

So 23 of the 24 judges are separated from, and ahead of, the best free scorer, and the
weakest judge cannot be told apart from it under either set of inputs. Every judge,
`llama_s` included, is separated from BARTScore, the best free scorer not trained to judge
(`make family-test DATASET_ID=summeval_100 A=se_bartscore_n100_v1 AGAINST=se_ METRIC=tau`: separated from all 32). `llama_s`
leads BARTScore by 0.0971, and BARTScore wins only 33 of 100 articles against it. Both
UniEval arms are separated above BARTScore (by 0.0914 and 0.1155) and every reference metric.

This is the first of the six experiments where no free arm measured is first, or not
separable from first. In the other five, a free local model was. Here the best free arm was
trained for these very dimensions, and it sits 0.168 below the leader: 64% of one expert's
agreement against the best judges' 93% (§3.7).

Two qualifications travel with that. The judges see all 16 summaries in one call and rank
them against each other; UniEval scores one summary at a time, and a pointwise LLM judge was
not run, so the gap is a design difference as well as a model one. And the system-identity
prior of §3.1 (τ 0.3637) sits between the two UniEval arms: the free trained evaluator is at
the level of a lookup that knows only which system wrote the summary.

These separations are on the mean over the four dimensions, which every test here uses. One
dimension or one statistic at a time the free scorers come closer: on Spearman ρ `unievalpub`
(0.4671) is above four judges, on coherence τ (0.4423) above seven, and BARTScore's coherence
(0.3799) is above four. The comparison is also not on equal footing in UniEval's favour:
it is given one human reference for relevance, which no judge sees.

**The inputs move UniEval.** The two UniEval arms score the same articles, summaries and
reference, written differently. 1,528 of the 1,600 summaries match character for character
once case, spacing and punctuation are ignored, and the other 72 differ only in how brackets
are written (`-lrb-` and `-rrb-` in this experiment's text); `calibrate.py` counts this, and
finds the same article and the same reference on every row. UniEval's file has a tokenised article and
sentence-cased summaries. This experiment's has the article as published and the summaries
lower-cased, as SummEval releases them. That difference is worth 0.0241 τ, separated (p 0.0002; `unievalpub`
wins 66 of 100 articles). Which part of it does the work is not tested.

**The text does not measurably move the one judge tested.** The judges were given this
experiment's text as well, lower-cased summaries and bracket tokens included. `gemma_l` was
re-run twice on UniEval's text as paired side runs (`harness/data/runs-pair/`, not on the
leaderboard). Pinned to CoreWeave, which served 99 of the original run's 100 calls (the
other went to DeepInfra), it scores 0.5397 against its 0.5384 here: +0.0013, not separated
(p 0.7689; it wins 49 of 100 articles). So the text that is worth 0.0241 to UniEval is
worth nothing measurable to this judge, and its lead over UniEval is 0.1908 on this
experiment's text and 0.1680 on UniEval's.

The first re-run, routed by OpenRouter to SambaNova, scored 0.5510; on the same
text the two providers differ by 0.0113 (p 0.0133, uncorrected, and a pair chosen after the
first result was seen), and SambaNova billed 3.7× what CoreWeave did for the same calls. That
is consistent with a provider effect, but it is one judge and one run per provider, and
hosted runs at temperature 0 also vary from run to run, so the two are not separated here.
Most judges were served by one provider throughout (11 of 24 on every call, 18 of 24 on at
least 98 of 100, as each call's record shows), so the leaderboard is not a blend of
providers; what another provider would score for them is not measured.

Among the free scorers not trained to judge, BARTScore, which never sees a reference,
beats every reference-based metric, and plain ROUGE-1 beats this repository's `coverage`
(0.1011, against ROUGE-1's 0.1487), most of the gap in consistency and fluency. The experts
were not rewarding length on average (τ 0.0388), though a little on relevance (0.0997).

### 3.4 Tier, by family: large is separated above small in six of eight

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

Large against small, paired over the 100 articles, Holm over the eight families
(`summeval_analysis.py`): separated in six — OpenAI +0.1286, Gemma +0.1188, Llama +0.1004,
GLM +0.0460, Anthropic +0.0446, Mistral +0.0279 — and not in two: DeepSeek +0.0105
(p 0.1078) and Qwen +0.0012 (p 0.8952), where the large tier is a substituted model. By point
estimate the ladder rises at every step in three families; in the other five the middle or
the smallest tier is at least as good as the next one up. The medium steps were not
pair-tested, so those patterns are descriptive. Several of these
arms were served by two or more providers in roughly even shares (`gemma_s`, `llama_l`,
`mistral_s`), which these tests do not separate from the model.

Across all 24, more expensive judges do score somewhat higher: Spearman(billed cost, τ) =
+0.437 over an 80× range. In the summarisation experiment the same statistic is −0.037
across its 24 hosted arms, which cannot exclude a moderate effect either way; the two use
September and October prices respectively.

### 3.5 The order is stable, the winner is not

Split-half stability among the 24 judges: two disjoint sets of *n* articles, the judges
ranked independently on each, 400 seeded draws (`harness/tools/summeval_analysis.py`,
from the committed runs):

| articles per half | ρ (half A, half B) | 5th percentile | same unique winner |
|---|---|---|---|
| 10 | 0.821 | 0.702 | 20% |
| 20 | 0.902 | 0.837 | 21% |
| 50 | 0.960 | 0.933 | 12% |

With all 33 arms included (`make rank-stability DATASET_ID=summeval_100 METRIC=tau`) ρ is higher still (0.960 at 20
per half), because most free scorers sit far below the judges and are easy to agree on.

The order of the judges is far more stable than the summarisation experiment's. The same
24 hosted models, ranked there by the same split-half method at 20 articles per half, agree
at ρ **0.333**; that report's own figure, over its whole 29-arm field, is 0.443
([REPORT_SUMMARIZATION §3.6](REPORT_SUMMARIZATION.md)). Why is not tested here; the field
is also more spread out (the judges span τ 0.35–0.54, where the summarisation arms sit
within about 0.04 of each other), and a wider field is easier to order. The winner is a
different matter: the top six are close enough that the unique leader changes in most draws, which is what §3.2's tie says in
another way. Agreement on the winner is no higher at 50 per half (12%) than at 10 or 20: at
50 the two halves split all 100 articles between them, so their noise runs in opposite
directions, and with four to six near-tied leaders a figure in this range is about what
chance gives.

### 3.6 By dimension

| dimension | best judge | τ | worst judge | τ |
|---|---|---|---|---|
| coherence | `gemma_l` | 0.5661 | `llama_s` | 0.3135 |
| consistency | `openai_l` | 0.6345 | `llama_s` | 0.4494 |
| fluency | `glm_m` | 0.5261 | `llama_s` | 0.3108 |
| relevance | `openai_l` | 0.5099 | `llama_s` | 0.3396 |

Consistency — whether the summary's facts are supported by the article — is where judges
agree with experts most, and it is the dimension that matters most for factuality. It is
also where the experts agree with each other most (one expert against the other two:
consistency 0.6811, coherence 0.5896, fluency 0.551, relevance 0.4129), so part of that is
an easier target, not a better judge. A
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
| `unievalpub` (UniEval, its own inputs) | 0.3589 | 64% |
| position prior (no model: other 99 articles' mean per position) | 0.3518 | 63% |
| `llama_s` (the weakest judge) | 0.3423 | 61% |
| `unieval` (UniEval, this experiment's inputs) | 0.3352 | 60% |
| `bartscore` | 0.2447 | 44% |
| `rouge1` | 0.1454 | 26% |
| `coverage` | 0.0955 | 17% |

The position-prior row is the lookup of §3.1 and §7 on this footing: each summary scored by
the mean expert score its position got on the other 99 articles only (`human_ceiling.py`),
against the same two-expert references. It reaches 63% of one expert, close to UniEval's 60–64%
and about 30 points below the best judges. How much of a judge's score is reading the summary
and how much is recognising the system is not measured.

**The best judges agree with the experts about 93% as well as an expert does** — 95%
interval 89–97% by a paired bootstrap over articles, and the gap to the expert (0.0152 to
0.0624 for `gemma_l`) excludes zero, so they are close and measurably below. Two cautions
on reading it as "an LLM is nearly an expert". The best judge is the best of 24 chosen on
these same articles. Picking the best judge on a random half of the articles and scoring it
on the other half, 2,000 times, gives 92% held out against 93% in sample
(`human_ceiling.py`), so the selection is worth about a point. And a judge sees all 16
summaries in one prompt and can rank them against each other, which is what a per-article
rank correlation rewards; how the experts were shown the summaries is not recorded here. The order at
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

**For anyone using an LLM as a judge.** On this task almost any hosted judge, ranking all 16
summaries in one call, is clearly better on mean τ than any free scorer, a pointwise trained
evaluator included, and a cheap open-weight one cannot be told apart from the dearest
proprietary ones on this sample. The practical reading: use a judge, start with the cheapest
member of the top group, and check it against a small set of human judgements on your own
outputs — which is exactly what this experiment does at scale.

**For this repository's other experiments.** The summarisation experiment ranks its arms by
`coverage`. Here `coverage` agrees with experts at τ 0.1011, below plain ROUGE-1. That
bounds how much a `coverage` lead can be taken to mean about what a person would prefer. It
was measured on 2019-era summaries, not on the LLM-written ones that experiment ranks, so
how far it transfers there is not measured.

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
does not say which ROUGE-L it ran, and this is `rouge_score`'s `rougeL` with stemming.

UniEval reproduces on its own inputs: **τ 0.3717 against G-Eval's 0.377** (ρ 0.4671 against
0.474), inside the interval (±0.0221) on the average and on every dimension, the largest gap
consistency's 0.0145. On this experiment's inputs it scores 0.3476, outside that interval,
which is why the calibration row is the published-input arm and the gap is reported as a
finding about the inputs (§3.3), not as an error. The
four rows, with their intervals, are in
[`docs/evidence/calibration/summeval.json`](../docs/evidence/calibration/summeval.json),
written by `examples/summeval-judging/calibrate.py`.
BARTScore comes out at τ 0.2562 against G-Eval's 0.305; G-Eval does not state its variant,
and ours is plain `bart-large-cnn`, source → summary, so it is reported as measured and not
counted as a calibration row.

## 6. Conditions of this run

**`qwen_l` could not run.** Its model, `qwen/qwen3-max`, is not served by OpenRouter:
the model page remains, but its list of endpoints is empty (checked 2026-10-18), and it was
already missing from the model listing on 2026-10-15. Four of the other five experiments
measured it, on 2026-09-26 to 09-28; SciFact's sweep did not include it. The run failed at warm-up (404) and billed nothing. Qwen's current flagship, `qwen/qwen3.8-max-0902`, refuses reasoning
disabled ("Reasoning is mandatory for this endpoint"), which this field's protocol does not
allow. The previous flagship, `qwen/qwen3.7-max`, accepts it (tested: 0 reasoning tokens)
and runs as `qwen37max` — its own config, never read as `qwen_l`.

**Prices moved since the configs were written.** Each config carries the per-token price
the earlier experiments used (September 2026); OpenRouter's prices on the day of this run
differ, in both directions — GPT-5.5 costs $5/$30 per million tokens against $1.25/$10 in
its config, the three GLM models rose about 2.5×, DeepSeek V4 Pro and Claude Sonnet 5 fell.
The costs in this report are the bills, so they are right; the dry-run estimates, which use
the config prices, were not. One consequence: within OpenAI the medium tier costs more
than the large one at those prices, so "price tier" here is a label, not a price order. Cost comparisons
between this experiment and the earlier five mix September and October prices.

## 7. NOT covered, NOT measured, NOT verified

- **One trained evaluator.** UniEval is the only free arm trained to judge summaries.
  "Free scorers measured" means these nine; an evaluator fine-tuned on SummEval's own
  scores would need articles held out from its training to be measured fairly here, and
  none was run.
- **UniEval may have seen these articles.** Part of its training data is built from
  CNN/DailyMail, and its paper does not say from which split; SummEval's articles are from
  the CNN/DailyMail test split. Its paper does not use the expert scores for training.
  SummEval is also the benchmark its authors reported on.
- **UniEval's weights state no licence.** The model card of `MingZhong/unieval-sum` gives
  none; its code is MIT. It is run here by pinned revision, and nothing of it is
  redistributed.

- **n = 100 articles**, below the usual 200, and every summary is from a 2019-era system.
  Modern summaries are more fluent; a judge's skill at catching 2019 failures may not
  transfer.
- **The 16 summaries are always shown in the same order**, the dataset's own, and each
  position is the same system on every one of the 100 articles. So position stands for which
  system wrote the summary, and systems differ in quality: scoring each summary by the mean
  expert score its position got on the other 99 articles reaches τ 0.3637 (`calibrate.py`),
  above the weakest judge (0.3533) and UniEval on this experiment's text (0.3476), below
  every other judge. Part of any arm's τ can be a system-level prior rather than a reading of
  the summary; how much, for the judges, and their own position bias, are not measured.
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
- **No leaderboard run pinned a provider.** OpenRouter chose the provider for every judge;
  most were served by one throughout. For `gemma_l` two providers scored 0.0113 apart on the
  same text in one run each (§3.3), a gap the size of several in the tie table; for the
  other 23 judges it is not measured.
- **One pass per judge.** Run-to-run variance at temperature 0 is not measured here; in the
  summarisation experiment's three-run sweep only 9.8% of hosted outputs were byte-identical
  across the three.
- **Within-family steps are not pair-tested** (§3.4); the size pattern is descriptive.
- **Costs are October 2026 bills**; the earlier five experiments' costs are September bills.
- **The tie in §3.2 has two boundary members.** They are stable to the permutation draw
  (§3.2); what a different sample of articles would do to them is not measured.
- **The human ceiling is one expert against two.** It is computed from the original
  release's per-expert scores (§3.7). Two experts are a noisier reference than three, which
  lowers the ceiling's absolute value; the judges are scored against the same two-expert
  references, so it does not make the 93% ratio conservative. The best judge is selected
  on the same articles (held out, 92%), and the judge sees all 16 summaries at once, which a
  per-article rank correlation rewards — not corrected for; how the experts were shown the
  summaries is not recorded here.

## 8. Reproduction

```bash
make data EXP=summeval                     # environment, fetch, hash check
make reproduce EXP=summeval LEVEL=local    # the nine free arms, $0
make reproduce EXP=summeval LEVEL=hosted   # the 24 judges, one LiteLLM or OpenRouter key
cd harness && make leaderboard DATASET_ID=summeval_100
make family-test DATASET_ID=summeval_100 A=se_openai_l_n100_v1 AGAINST=se_ METRIC=tau
python tools/summeval_analysis.py            # §3.4–§3.6: split-half, price, ladders, dimensions
cd .. && examples/summeval-judging/.venv/bin/python examples/summeval-judging/calibrate.py   # §5
examples/summeval-judging/.venv/bin/python examples/summeval-judging/human_ceiling.py       # §3.7
```

`make ci` checks every figure in this report against those two scripts and the committed
runs (`harness/tools/check_report_claims.py`).
