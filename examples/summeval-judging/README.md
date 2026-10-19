# SummEval judging: can a model grade summaries the way experts do?

Experiment 6. Every other experiment in this repository asks a system to *do* a task; this
one asks it to *grade* one. Each item is a CNN/DailyMail article with 16 machine summaries.
The system scores every summary on four dimensions (coherence, consistency, fluency,
relevance), and it is measured by how well its scores **order** the 16 the way three expert
annotators did ([Fabbri et al. 2021](https://arxiv.org/abs/2007.12626)).

Two questions this repository already asks, made measurable:

- **Can an LLM judge be trusted?** Every silver reference, every "LLM-as-judge" pipeline,
  rests on it.
- **How good are the metrics we rank by?** ROUGE and this repository's own `coverage` (the
  summarisation experiment's primary metric) are arms here. How well they agree with experts
  bounds how much that leaderboard's lead means to a person — measured on 2019-era
  summaries, not the LLM-written ones it ranks.

## What it breaks that the other five did not

| | |
|---|---|
| the answer | a vector of 64 judgements (16 summaries × 4 dimensions), returned as JSON |
| the metric | a **rank correlation**: Kendall τ-b per article against the expert means, averaged over the four dimensions (`tau`); Spearman (`rho`) beside it for the literature |
| ties | LLM judges give integer 1–5 scores, so they tie constantly; τ-b corrects for ties on both sides, and `tie_rate` reports how often the judge tied two summaries |
| the referee | expert human judgement, continuous (means of three annotators), not a label or a reference text |

τ is computed **per article**, so the harness's paired permutation tests and Holm correction
apply unchanged.

## Data

`mteb/summeval` (MIT; the original [Yale-LILY/SummEval](https://github.com/Yale-LILY/SummEval)
is MIT): the 100 annotated CNN/DailyMail test articles, 16 summaries each from 2019-era
summarisers, 11 human reference summaries each, and expert scores on four dimensions. The
expert means are the gold; the crowd ratings, which the paper shows disagree with the
experts, are not used. Nothing is committed: `fetch.py` downloads it (see
[docs/DATA.md](../../docs/DATA.md)).

```bash
python examples/summeval-judging/fetch.py      # or, from the root: make data EXP=summeval
```

## Arms

| arm | what it is |
|---|---|
| 24 hosted LLM judges | the same 24 models as the other experiments, with `qwen37max` in place of `qwen_l`, whose model is no longer served; one call per article; shown the article and the 16 summaries, **never the human references** ([prompt.txt](prompt.txt)) |
| `unieval`, `unievalpub` | [UniEval](https://arxiv.org/abs/2210.07197) (Zhong et al. 2022), a T5-large evaluator trained to answer one yes/no question per dimension, for exactly these four; `MingZhong/unieval-sum`, pinned, licence not stated on its model card; local, CPU. `unieval` scores the text every other arm saw, plus one human reference for relevance; `unievalpub` scores UniEval's own published SummEval inputs (the same articles, summaries and reference, cased and tokenised differently), the protocol behind its published figures |
| `rouge1`, `rouge2`, `rougeL` | ROUGE F1 of each summary against each of the 11 human references, averaged |
| `coverage` | this repository's summarisation metric, imported from that example's own scorer, averaged over the references |
| `bartscore` | log-likelihood of the summary given the article under `facebook/bart-large-cnn` ([Yuan et al. 2021](https://arxiv.org/abs/2106.11520)), pinned to the revision the summarisation experiment measured; local, CPU |
| `length` | the summary's word count: a confound to rule out, not a judge |
| `random` | seeded random scores: the floor, near τ = 0 |

A reference-based metric gives one number per summary; it stands for all four dimensions.

## Calibration

[G-Eval](https://arxiv.org/abs/2303.16634), Table 1, reports ROUGE-1 against these experts at
**ρ 0.192, τ 0.150** (averaged over the four dimensions). Measured here, on the same 100
articles, with ROUGE-1 F1 averaged over the references: **ρ 0.190, τ 0.149**, and per
dimension within 0.01 of every published value. (Max over references gives ρ 0.198 and the
first reference alone 0.159; neither reproduces the published row, so averaging is the
setup.) UniEval reproduces as well, on its own inputs: τ 0.372 against G-Eval's 0.377, inside the
interval on every dimension (on this experiment's text it scores 0.348; see the report,
§3.3). The instrument reproduces the literature before anything new is read off it.
[`calibrate.py`](calibrate.py) recomputes all of this from the committed runs and writes
[`docs/evidence/calibration/summeval.json`](../../docs/evidence/calibration/summeval.json),
which `make ci` checks this page against.

## Results: the free arms

τ against the experts, per article, averaged over the four dimensions (100 articles):

| arm | τ | ρ | τ, relevance | τ, consistency |
|---|---|---|---|---|
| `unievalpub` | 0.372 | 0.467 | 0.324 | 0.356 |
| `unieval` | 0.348 | 0.439 | 0.321 | 0.338 |
| `bartscore` | 0.256 | 0.325 | 0.246 | 0.198 |
| `rouge2` | 0.158 | 0.201 | 0.220 | 0.148 |
| `rouge1` | 0.149 | 0.190 | 0.253 | 0.122 |
| `rougeL` | 0.143 | 0.184 | 0.210 | 0.109 |
| `coverage` | 0.101 | 0.130 | 0.214 | 0.056 |
| `length` | 0.039 | 0.048 | 0.100 | 0.071 |
| `random` | 0.003 | 0.003 | 0.007 | −0.007 |

Four things already worth saying:

- **UniEval, the one free arm trained to judge, is the best free arm** — and how the text is
  written moves it: the same articles and summaries, cased and tokenised as UniEval's own
  file has them, score 0.024 higher, a separated difference.

- **BARTScore, a model that never sees a reference, beats every reference-based metric**
  (τ 0.256 against ROUGE-2's 0.158). G-Eval publishes BARTScore at τ 0.305 / ρ 0.385; ours is
  lower on consistency, fluency and relevance and *higher* on coherence (τ 0.380 against
  0.342). G-Eval does not say which BARTScore variant it ran; this is plain
  `bart-large-cnn`, source → summary. So it is reported as measured, not counted as a
  calibration row. (ROUGE-2 reproduces too:
  τ 0.158 against 0.161 published. ROUGE-L does not quite: 0.143 against 0.128 on average,
  and 0.153 against 0.099 on coherence. The average is inside the 95% interval over
  articles; the coherence gap (0.054) is outside its interval (±0.042) and passes only with
  the 0.02 allowance the repository's calibration rule adds for protocol differences. G-Eval
  scored these same articles, so the gap is one of protocol, not sample; the paper does not
  say which ROUGE-L it ran.)

- **This repository's own `coverage` agrees with the experts less than plain ROUGE-1**
  (τ 0.101 against 0.149), most of the gap in consistency and fluency. Coverage was built to
  stop rewarding length, and it does that; what it gives up is visible here.
- **The experts were not rewarding length** on average (τ 0.039; 0.100 on relevance), so
  agreement here is mostly not a length effect in disguise.

## Results: the hosted judges

All 24 hosted judges are measured ($7.03 billed). 23 of them are separated from, and ahead
of, UniEval on either set of inputs; the weakest, `llama_s`, cannot be told apart from it.
Every one is ahead of BARTScore. The leader cannot be separated from five others, led by `openai_l` (τ 0.540), with `gemma_l` (τ 0.538) the
cheapest member at $0.03 for all 100 articles. Scored against the mean of two experts, as one
expert is against the other two, the best judges reach 93% of a human's agreement (95% interval 89–97%; the best of 24, chosen on these
articles), UniEval 64% ([`human_ceiling.py`](human_ceiling.py)). The full results, the significance tests and
what changed while measuring (a retired model, a model that forces reasoning, moved prices)
are in [research/REPORT_SUMMEVAL.md](../../research/REPORT_SUMMEVAL.md).

## Running the hosted judges

With `OPENROUTER_API_KEY` in `harness/.env`, from `harness/` (about $7 for all 24):

```bash
for a in anthropic_s anthropic_m anthropic_l openai_s openai_m openai_l \
         deepseek_s deepseek_m deepseek_l gemma_s gemma_m gemma_l glm_s glm_m glm_l \
         llama_s llama_m llama_l mistral_s mistral_m mistral_l qwen_s qwen_m qwen37max; do
  ../examples/summeval-judging/.venv/bin/python scripts/experiment_run.py \
    --config ../examples/summeval-judging/configs/arm_${a}_n100.yaml; done
make leaderboard DATASET_ID=summeval_100
```

## What this cannot say

- **No leaderboard run pinned a provider.** OpenRouter chose who served every judge, though
  most were served by one throughout. For `gemma_l`, two providers scored 0.0113 apart on
  the same text in one run each, and billed 3.7× apart; for the other 23 judges this is not
  measured. Renting a judge through default routing may give a different score and bill.
- **Each position is the same system on every article.** A prior that only knows which
  system wrote a summary reaches τ 0.364 against the experts, above UniEval on this text and
  the weakest judge; read the free arms, and the bottom of the field, against it.
- **Judges and UniEval are not scored the same way.** A judge sees all 16 summaries in one
  call and can rank them against each other, which a per-article rank correlation rewards;
  UniEval scores one summary at a time and is given one human reference for relevance,
  which no judge sees.
- **One trained evaluator.** UniEval is the only free arm trained to judge. Part of its
  training data is built from CNN/DailyMail, and its paper does not say from which split, so
  it may have seen these articles' text; its paper does not train on their expert scores.
- **How the prompt was developed is not recorded.** There is no dev slice, so nothing here
  is reported on articles the prompt and parser were not written against.

- **n = 100 articles**, and every summary is from a 2019-era system; modern summaries are
  more fluent, so a judge's skill at catching 2019 failures may not transfer.
- **The annotations are public** and may be in some models' training data, though memorising
  per-summary scores for 1,600 summaries is unlikely.
- **One prompt, four dimensions in one call.** Scoring one summary per call, or asking for
  token probabilities (G-Eval's probability-weighted score), are different judges; they are
  not measured here.
- **The articles are mostly DailyMail** (87 of 100; 13 CNN), unlike the summarisation
  experiment's sample, which is all CNN.
