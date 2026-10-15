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
  is how far that leaderboard can be believed.

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
| 24 hosted LLM judges | the same 24 models as every other experiment; one call per article; shown the article and the 16 summaries, **never the human references** ([prompt.txt](prompt.txt)) |
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
first reference alone 0.158; neither reproduces the published row, so averaging is the
setup.) The instrument reproduces the literature before anything new is read off it.

## Results so far: the free arms

τ against the experts, per article, averaged over the four dimensions (100 articles):

| arm | τ | ρ | τ, relevance | τ, consistency |
|---|---|---|---|---|
| `rouge2` | 0.158 | 0.201 | 0.220 | 0.148 |
| `rouge1` | 0.149 | 0.190 | 0.253 | 0.122 |
| `rougeL` | 0.143 | 0.184 | 0.210 | 0.109 |
| `coverage` | 0.101 | 0.130 | 0.214 | 0.056 |
| `length` | 0.039 | 0.048 | 0.100 | 0.071 |
| `random` | 0.003 | 0.003 | 0.007 | −0.007 |

Two things already worth saying:

- **This repository's own `coverage` agrees with the experts less than plain ROUGE-1**
  (τ 0.101 against 0.149), most of the gap in consistency and fluency. Coverage was built to
  stop rewarding length, and it does that; what it gives up is visible here.
- **The experts were not rewarding length** (τ 0.039), so agreement here is not a length
  effect in disguise.

The hosted judges are the open question: does any LLM order summaries like an expert better
than ROUGE's 0.15?

## Running the hosted judges

With `OPENROUTER_API_KEY` in `harness/.env`, from `harness/` (about $7 for all 24):

```bash
for a in anthropic_s anthropic_m anthropic_l openai_s openai_m openai_l \
         deepseek_s deepseek_m deepseek_l gemma_s gemma_m gemma_l glm_s glm_m glm_l \
         llama_s llama_m llama_l mistral_s mistral_m mistral_l qwen_s qwen_m qwen_l; do
  ../examples/summeval-judging/.venv/bin/python scripts/experiment_run.py \
    --config ../examples/summeval-judging/configs/arm_${a}_n100.yaml; done
make leaderboard DATASET_ID=summeval_100
```

## What this cannot say

- **n = 100 articles**, and every summary is from a 2019-era system; modern summaries are
  more fluent, so a judge's skill at catching 2019 failures may not transfer.
- **The annotations are public** and may be in some models' training data, though memorising
  per-summary scores for 1,600 summaries is unlikely.
- **One prompt, four dimensions in one call.** Scoring one summary per call, or asking for
  token probabilities (G-Eval's probability-weighted score), are different judges; they are
  not measured here.
- **The articles are CNN's**, like the summarisation experiment's sample.
