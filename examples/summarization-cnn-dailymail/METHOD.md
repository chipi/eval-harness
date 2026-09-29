# Method — why this experiment is built the way it is

Companion to [`README.md`](README.md) (how to run it) and
[`REPORT_SUMMARIZATION.md`](../../research/REPORT_SUMMARIZATION.md) (what it found). This
file is the **reasoning**: why this dataset, why these arms, why these metrics, and what
each choice gives up. Terms are defined in [`docs/REFERENCE.md`](../../docs/REFERENCE.md).

---

## The task, and why it is first

Summarise a news article; compare to a human-written summary. It is the **easiest shape a
metric can have** — one text against one text, scored continuously — and that is exactly
why it came first. Everything the harness needed for the later examples (frozen datasets,
fingerprints, retries, cost accounting) could be built against a task whose scoring was
not itself in question.

## Why CNN/DailyMail

[`abisee/cnn_dailymail`](https://huggingface.co/datasets/abisee/cnn_dailymail), Apache-2.0,
[See et al. 2017](https://arxiv.org/abs/1704.04368).

- **Human-written references.** The "highlights" are journalists' own bullets, not model
  output. That makes the reference *gold*, not silver, and it is the reason this example
  can make claims the others qualify.
- **Apache-2.0.** The cleanest licence of the five corpora here.
- **It is the standard.** Nearly every summarisation paper reports on it, so an absolute
  number here is checkable against the literature.

**What it gives up:** CNN/DailyMail is famously *extractive-biased* — the highlights often
reuse article sentences nearly verbatim. A model that copies scores well. That is why
`lead3` is an arm and not a joke, and why `grounding` exists.

## Why these arms

| Arm | Why it is here |
|---|---|
| 24 hosted LLMs | 8 vendors × 3 price tiers. The price tiers are the point: the experiment is as much about **what money buys** as about which model wins. |
| [`bart_l`](https://huggingface.co/facebook/bart-large-cnn) | Fine-tuned **on this exact dataset**. The in-distribution ceiling — what a small model does when it has seen the training split. |
| `lead3` | The first three sentences. **Not a joke baseline.** On CNN/DailyMail it is famously hard to beat, and an LLM that does not clear it has not earned its inference cost. |

**Blocked, and why it matters:** `distilbart-cnn-12-6`, `distilbart-cnn-6-6` and
`bart-large-xsum` ship pickle checkpoints, which `transformers` refuses to `torch.load`
below torch 2.6 ([CVE-2025-32434](https://github.com/advisories/GHSA-53q9-r3pm-6pq6)), and
there is no Intel-Mac torch wheel above 2.2.2. Their absence removes the *distilled* size
tier and the *out-of-distribution* (XSum-trained) comparison — see
[`HANDOVER_ML_ARMS.md`](../../research/HANDOVER_ML_ARMS.md).

## Why these success criteria

**Ranked by `coverage`** — [ROUGE-Lsum](https://aclanthology.org/W04-1013/) recall against
the human reference, after clipping the output to a word budget.

Why recall and not F1: the question is *"did it capture what a human thought mattered"*.
Precision against a 3-bullet reference punishes a model for adding a true fact the
journalist omitted. But recall alone rewards writing more, so:

- **`concision`** is ROUGE-Lsum *precision* over the whole output — what share of what it
  wrote earned its place. Padding is punished here exactly as much as recall rewards it.
- **`length_vs_reference`** is how a verbose winner is caught. ROUGE rises with length;
  this makes that visible rather than letting it hide inside the primary metric.
- **The clip is part of the metric, not a convenience.** Without a word budget, `coverage`
  is a length contest.

**`grounding` is ours and is not comparable to anyone's published number.** ~20 lines:
what share of the summary's bigrams also appear in the *article*. It cannot distinguish a
good paraphrase from a fabrication. What it *can* do is say the model left the source
behind, which ROUGE structurally cannot — ROUGE only ever looks at the reference.

### What this scoring cannot see

ROUGE is n-gram overlap. **A factually wrong summary that reuses the article's wording
scores well; a correct paraphrase scores badly.** This is a known and much-criticised
property — [Kryscinski et al. 2019](https://aclanthology.org/D19-1051/) is the standard
reference — and it is why every claim in the report is about *overlap with a human
reference*, never about *quality* unqualified.

No judge model is used. That is deliberate: an LLM judge would introduce a second model's
preferences into the measurement, and this repo's whole design is that the instrument must
be cheaper to audit than the thing it measures.

---

## Credits

**Dataset** — [CNN/DailyMail](https://huggingface.co/datasets/abisee/cnn_dailymail),
Apache-2.0. [Hermann et al. (2015)](https://arxiv.org/abs/1506.03340) built the corpus; [Nallapati et al. (2016)](https://arxiv.org/abs/1602.06023) adapted it for summarisation; [See, Liu & Manning (2017)](https://arxiv.org/abs/1704.04368) defined the split used here.
Not redistributed; [`fetch.py`](fetch.py) downloads it.

**Models** — [`facebook/bart-large-cnn`](https://huggingface.co/facebook/bart-large-cnn)
([BART](https://arxiv.org/abs/1910.13461), Lewis et al. 2019). Hosted models are credited
in [`docs/REFERENCE.md`](../../docs/REFERENCE.md#hosted--24-arms-8-vendors--3-price-tiers).

**Metric** — [ROUGE](https://aclanthology.org/W04-1013/) (Lin, 2004), via
[`rouge-score`](https://github.com/google-research/google-research/tree/master/rouge)
0.1.2, Apache-2.0.

**Software** — [transformers](https://github.com/huggingface/transformers) 4.55.4 ·
[torch](https://github.com/pytorch/pytorch) 2.2.2 ·
[openai](https://github.com/openai/openai-python) client ·
[LiteLLM](https://github.com/BerriAI/litellm) proxy · [uv](https://github.com/astral-sh/uv).
