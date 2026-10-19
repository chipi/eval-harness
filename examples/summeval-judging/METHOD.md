# Method — why this experiment is built the way it is

Companion to [`README.md`](README.md) (how to run it) and
[`REPORT_SUMMEVAL.md`](../../research/REPORT_SUMMEVAL.md) (what it found). This file is the
**reasoning**: why this dataset, why these arms, why this metric, and what each choice gives
up. Terms are defined in [`docs/REFERENCE.md`](../../docs/REFERENCE.md).

---

## The task, and why it is sixth

Score 16 machine summaries of a news article on four dimensions, and be graded on how well
those scores **order** the summaries the way three experts did. Every earlier experiment
asks a system to *do* a task and grades the output against a reference. This one asks a
system to *grade*, and grades the grading.

It came after the other five because it measures the instrument they rely on. Every silver
reference in this repository, and every automated eval that uses a model as the judge,
assumes that a model's judgement of text tracks a person's. Here that assumption is a number
with an interval. And two of the arms are metrics this repository ranks by, so the same run
says how far the summarisation leaderboard can be believed.

## Why SummEval

[`mteb/summeval`](https://huggingface.co/datasets/mteb/summeval), MIT;
[Fabbri et al. 2021](https://arxiv.org/abs/2007.12626).

- **Expert gold, on the dimensions that matter.** Each of the 1,600 summaries carries the
  1–5 scores of three expert annotators on coherence, consistency, fluency and relevance.
  The mean of the three is the reference. The crowd ratings, which the paper shows disagree
  with the experts, are not used.
- **A published protocol to check against.** G-Eval (Liu et al. 2023) reports
  summary-level correlations on these 100 articles for ROUGE, BARTScore and GPT-4 judges,
  so a number here can be checked against a published one directly — which
  `calibrate.py` does for ROUGE-1/2/L and UniEval.
- **No sample.** The 100 annotated articles are the whole benchmark, so there is no slice
  to bias, and nothing is seeded.

**What it gives up.**

- **n = 100**, against 200–280 items elsewhere. Per-article τ carries a lot of signal (each
  averages 16 summaries and four dimensions), and the split-half figures in the report show
  the judges' order is stable; the top of the field is not.
- **2019-era summaries.** The 16 systems are from before current LLMs. Modern summaries
  are more fluent, and a judge's skill at catching 2019 failures may not transfer.
- **The annotations are public** and could be in a judge's training data. Memorising
  per-summary scores for 1,600 summaries is unlikely; it is not ruled out.
- **Mostly DailyMail** (87 of 100 articles, 13 CNN), where the summarisation experiment's
  sample is all CNN.

## Why these arms

| Arm | Why it is here |
|---|---|
| 24 hosted LLMs | The same 8 vendors × 3 price tiers as every other experiment, so a model's judging can be set beside its doing. One call per article: the article and the 16 numbered summaries, and a request for JSON scores ([`prompt.txt`](prompt.txt)). The judge never sees the human references. |
| `qwen37max` | Replaces `qwen_l`, whose model is no longer served. A different model under its own arm name, never read as `qwen_l` ([report §6](../../research/REPORT_SUMMEVAL.md#6-what-changed-while-measuring)). |
| `bartscore` | [BARTScore](https://arxiv.org/abs/2106.11520), the log-likelihood of the summary given the article under `facebook/bart-large-cnn`, pinned to the revision the summarisation experiment measured. In G-Eval's Table 1 it is the strongest of the metrics G-Eval does not group with those that learn from human ratings (τ 0.305; UniEval, a trained evaluator, reaches 0.377 there). It is also a model fine-tuned on this very corpus — to write summaries, not to grade them. |
| `unieval`, `unievalpub` | [UniEval](https://arxiv.org/abs/2210.07197), the free evaluator in G-Eval's table that was trained for these four dimensions, re-implemented from its MIT code (`adapter.py` says how). The bar a judge must clear to earn its bill. Run twice, because its published figures come from its own copy of SummEval, cased and tokenised differently from the text the other arms see: `unievalpub` is the calibration row, `unieval` the comparison on this experiment's text (still with one human reference for relevance, which no judge is shown). |
| `rouge1`, `rouge2`, `rougeL` | The reference-based metrics the field still ranks summarisers by, against each of the 11 references and averaged. They are also the calibration rows. |
| `coverage` | **This repository's own** summarisation metric, imported from that example's scorer. How well it agrees with experts is how much a `coverage` lead means. |
| `length` | The summary's word count. A confound to rule out: if it agreed with the experts, anything that rewards length would too. |
| `random` | Seeded random scores, the floor near τ = 0. |

A reference-based metric gives one number per summary, so it stands for all four
dimensions at once; a judge scores each dimension separately.

## Why this success criterion

**Ranked by `tau`**: Kendall τ-b per article between the arm's scores and the expert means
over the 16 summaries, computed per dimension and averaged over the four. Spearman `rho` is
reported beside it because the literature reports both.

- **A rank correlation, because the question is ordering.** A judge that scores everything
  one point too high but in the right order is a good judge; a calibrated scale is a
  separate property, and not one this experiment asks about.
- **τ-b, not τ-a, because judges tie.** Integer 1–5 scores give 16 summaries at most five
  distinct values, so a judge ties constantly. τ-b corrects for ties on both sides; τ-a
  would punish every tie. `tie_rate` reports how often each judge ties, and it barely
  predicts its quality (report §3.6).
- **Per article, then averaged.** That is G-Eval's summary-level protocol, and it makes the
  score per item, so the harness's paired permutation tests and Holm correction apply as
  they do everywhere else.
- **An unreadable reply scores 0** on the dimensions it fails, never skipped: skipping
  would score a judge only on the articles it managed.

### What this scoring cannot see

Agreement with three experts is agreement with three people, and they disagree with each
other: one expert agrees with the other two at τ 0.5587, so a τ of 0.54 is not "54% of the
way to perfect". [`human_ceiling.py`](human_ceiling.py) measures that ceiling from the
original release's per-expert scores and sets every arm against it (report §3.7). And the protocol is one prompt, one call per article, scores as
integers: scoring one summary per call, one dimension per call, or with token probabilities
(G-Eval's method) are different judges, and none of them is measured.

---

## Credits

**Dataset** — [SummEval](https://huggingface.co/datasets/mteb/summeval) (MIT;
[original repository](https://github.com/Yale-LILY/SummEval), MIT),
[Fabbri et al. (2021)](https://arxiv.org/abs/2007.12626). Its articles and references are
from [CNN/DailyMail](https://huggingface.co/datasets/abisee/cnn_dailymail), Apache-2.0.
Not redistributed; [`fetch.py`](fetch.py) downloads it.

**Calibration** — [G-Eval](https://arxiv.org/abs/2303.16634) (Liu et al. 2023), Table 1.

**Models** — [`facebook/bart-large-cnn`](https://huggingface.co/facebook/bart-large-cnn)
([BART](https://arxiv.org/abs/1910.13461), Lewis et al. 2019) as
[BARTScore](https://arxiv.org/abs/2106.11520) (Yuan et al. 2021);
[`MingZhong/unieval-sum`](https://huggingface.co/MingZhong/unieval-sum) as
[UniEval](https://arxiv.org/abs/2210.07197) (Zhong et al. 2022), its code
[maszhongming/UniEval](https://github.com/maszhongming/UniEval) MIT, its weights' licence not
stated. Hosted models are credited
in [`docs/REFERENCE.md`](../../docs/REFERENCE.md#hosted--24-arms-8-vendors--3-price-tiers).

**Metric** — [ROUGE](https://aclanthology.org/W04-1013/) (Lin, 2004), via
[`rouge-score`](https://github.com/google-research/google-research/tree/master/rouge) 0.1.2,
Apache-2.0; Kendall τ-b and Spearman ρ implemented in [`adapter.py`](adapter.py).

**Software** — as recorded in the runs' fingerprints:
[transformers](https://github.com/huggingface/transformers) 4.55.4 ·
[torch](https://github.com/pytorch/pytorch) 2.14.1 · Python 3.11 ·
[openai](https://github.com/openai/openai-python) client ·
[LiteLLM](https://github.com/BerriAI/litellm) proxy · [uv](https://github.com/astral-sh/uv).
