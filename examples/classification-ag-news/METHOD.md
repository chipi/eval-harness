# Method — why this experiment is built the way it is

Companion to [`README.md`](README.md) and
[`REPORT_CLASSIFICATION.md`](../../research/REPORT_CLASSIFICATION.md). Terms are defined in
[`docs/REFERENCE.md`](../../docs/REFERENCE.md).

**Read this with its twin, [`classification-dbpedia-14`](../classification-dbpedia-14/METHOD.md).**
The two were chosen to sit in opposite statistical regimes, and either alone would support
whichever conclusion it happened to produce.

---

## The task, and what it broke

Put a news snippet in one of four topics. The answer is **one label**, scored 0 or 1 — and
that discreteness broke three things the continuous summarisation metric never touched:

1. **A discrete metric ties.** Two genuinely different models both getting 172 of 200 right
   report byte-identical 0.86. The harness's duplicate-run check (`V5`) read that as a
   copy-paste error and flagged it four times in one sweep. It now compares **per-item**
   results, not means.
2. **Accuracy cannot express macro-F1.** Precision for a class needs every prediction of
   that class across the whole run — a property of the *set*, not of any item. So there is
   no per-item number whose mean is macro-F1, and it lives in a report script instead of
   pretending to be a metric.
3. **Parsing became load-bearing.** "Which topic?" invites a sentence, not a word. The
   label parser turned out to be worth **8.6 accuracy points** to one arm — wider than the
   gap separating most of the field.

## Why AG News

[`fancyzhx/ag_news`](https://huggingface.co/datasets/fancyzhx/ag_news),
[Zhang, Zhao & LeCun 2015](https://arxiv.org/abs/1509.01626).

- **It has headroom.** The field spans 0.835–0.910, so differences are resolvable. Its twin
  was chosen for the opposite reason.
- **Four balanced classes**, so accuracy and macro-F1 track closely and the *gap* between
  them is informative rather than structural.
- **Good fine-tuned checkpoints exist**, which is what makes the ML-vs-LLM comparison
  possible at all.

> **Licence caveat, stated because it constrains reuse.** The dataset card says `unknown`
> and the corpus's own description states non-commercial research use. Nothing is
> redistributed here — [`fetch.py`](fetch.py) downloads a slice to whoever runs it — but
> anyone reusing this example commercially needs to resolve that themselves.

**The fetcher stratifies by class**, unlike the summarisation one, because here an item
*has* a class and an unstratified draw would put class imbalance into the measurement.

## Why these arms

| Arm | Why it is here |
|---|---|
| 24 hosted LLMs | The same 24 as every other example, so a difference between examples is the **task**. |
| [`bert_mini`](https://huggingface.co/mrm8488/bert-mini-finetuned-age_news-classification) | **44 MB**, fine-tuned on AG News. The in-distribution specialist — and the arm that beat all 24. |
| [`bert_base_ta`](https://huggingface.co/textattack/bert-base-uncased-ag-news), [`bert_base_fy`](https://huggingface.co/fabriceyhc/bert-base-uncased-ag_news) | **438 MB** each, two independent BERT-base fine-tunes on AG News. They ask whether 44 MB was a floor or a ceiling (it was close to the ceiling: 0.9450 vs 0.9600, not separated), and check each other (192 of 200 labels agree). Needed torch ≥ 2.6; ran 2026-09-30. Together with `bert_mini` they made the label-convention effect measurable — see the report's §3.4. |
| [`bart_mnli`](https://huggingface.co/facebook/bart-large-mnli) | Zero-shot via [NLI entailment](https://arxiv.org/abs/1909.00161). The **matched control**: same "small model" class, but never trained on this task. Without it, `bert_mini` winning would confound *small* with *trained on this*. |
| `keyword` | ~20 hand-written regex rules. Establishes what rules alone are worth before any model is credited. |
| `constant` | Always one class. Must score ≈0.25 — a **calibration check on the scorer**, not a baseline. |

## Why these success criteria

**Ranked by `correct`** — exact match against the gold label. Its mean is accuracy. Simple
on purpose: on a balanced four-class task, accuracy is the number a practitioner would act
on.

Everything else is read *after* the ranking:

- **`parsed` is a quality metric, not descriptive.** An arm whose output cannot be read as
  a label cannot be deployed, whatever it knows.
- **`correct_after_repair` minus `correct` is what the parser is worth.** Recording both is
  how the 8.6-point finding was possible at all; a single number would have hidden it
  inside "model quality".
- **Macro-F1** ([scikit-learn's definition](https://scikit-learn.org/stable/modules/model_evaluation.html#precision-recall-f-measure-metrics))
  weights every class equally, so it disagrees with accuracy exactly when an arm has a
  *concentrated blind spot* rather than a uniform error rate. The gap is the signal.
- **`confidence` and calibration.** Only the local arms supply a probability. `bert_mini`'s
  [expected calibration error](https://arxiv.org/abs/1706.04599) is 0.025 — a reliable
  "I am not sure" you can route on, which is what makes a cheap classifier *deployable*
  rather than merely accurate. No hosted arm has this: logprobs were never requested.
- **The label-noise pass.** Items nearly the whole field gets "wrong" are usually items
  whose gold label is wrong. This was added *after* the AG News report was first published
  and revised it — the ranking survived, the interpretation did not.

---

## Credits

**Dataset** — [AG News](https://huggingface.co/datasets/fancyzhx/ag_news).
[Zhang, Zhao & LeCun (2015)](https://arxiv.org/abs/1509.01626); original corpus by
ComeToMyHead. Card licence `unknown`, non-commercial research use stated. Not
redistributed.

**Models** —
[`mrm8488/bert-mini-finetuned-age_news-classification`](https://huggingface.co/mrm8488/bert-mini-finetuned-age_news-classification)
([BERT](https://arxiv.org/abs/1810.04805)) ·
[`facebook/bart-large-mnli`](https://huggingface.co/facebook/bart-large-mnli)
([BART](https://arxiv.org/abs/1910.13461);
[zero-shot via NLI](https://arxiv.org/abs/1909.00161)) ·
[`textattack/bert-base-uncased-ag-news`](https://huggingface.co/textattack/bert-base-uncased-ag-news),
[`fabriceyhc/bert-base-uncased-ag_news`](https://huggingface.co/fabriceyhc/bert-base-uncased-ag_news)
(pickle checkpoints; need torch ≥ 2.6).
Hosted models in [`docs/REFERENCE.md`](../../docs/REFERENCE.md#hosted--24-arms-8-vendors--3-price-tiers).

**Method** — calibration/ECE from [Guo et al. (2017)](https://arxiv.org/abs/1706.04599).

**Software** — [transformers](https://github.com/huggingface/transformers) 4.55.4 ·
[torch](https://github.com/pytorch/pytorch) 2.2.2 on x86_64 macOS, 2.14.0 elsewhere (the bert-base arms ran on 2.14.0) ·
[scikit-learn](https://scikit-learn.org/) 1.9.1 ·
[LiteLLM](https://github.com/BerriAI/litellm) · [uv](https://github.com/astral-sh/uv).
