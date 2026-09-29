# Method — why this experiment is built the way it is

Companion to [`README.md`](README.md) and
[`REPORT_CLASSIFICATION.md`](../../research/REPORT_CLASSIFICATION.md). Terms in
[`docs/REFERENCE.md`](../../docs/REFERENCE.md).

**This experiment exists to disagree with [`classification-ag-news`](../classification-ag-news/METHOD.md).**
Same harness, same 24 arms, same statistics, same metric — a different corpus, chosen
before any result was seen, to sit in the opposite regime. Read together or not at all.

---

## Why a second classification task

AG News produced a clean story: a 44 MB fine-tuned model beat 24 frontier LLMs. That story
is only trustworthy if you know what the *other* regime looks like, because a single
corpus supports whatever conclusion it happens to produce.

So DBpedia-14 was picked for the properties AG News lacks:

| | AG News | DBpedia-14 |
|---|---|---|
| classes | 4 | **14** |
| headroom | field spans 0.835–0.910 | **saturated** — top arms above 0.98 |
| what a ranking can resolve | real differences | **almost nothing** |

## Why DBpedia-14

[`fancyzhx/dbpedia_14`](https://huggingface.co/datasets/fancyzhx/dbpedia_14), CC-BY-SA 3.0
+ GFDL inherited from Wikipedia — **a cleaner licence than AG News**, which is part of why
it was chosen.

Wikipedia abstracts labelled with one of 14 DBpedia ontology classes
([Lehmann et al.](https://www.semantic-web-journal.net/content/dbpedia-large-scale-multilingual-knowledge-base-extracted-wikipedia)).
The classes are ontological rather than topical — `NaturalPlace` vs `Building` vs
`MeanOfTransportation` — which matters: **an ontology's boundaries are conventions**, and
that turns out to be where the ceiling comes from.

**The fetcher draws a seeded-random prefix, not first-k-per-class.** AG News's dev slice
used first-k and was nested but *not representative* — `keyword` scored 0.35 on dev and
0.67 on the measurement slice, roughly 3 SD apart. Fixed here.

## Why these arms

The same 24 hosted arms plus `keyword` and `constant`, for comparability.

**The ML arm could not run**, and that is a reported gap rather than a footnote:
[`fabriceyhc/bert-base-uncased-dbpedia_14`](https://huggingface.co/fabriceyhc/bert-base-uncased-dbpedia_14)
ships a pickle checkpoint, which `transformers` refuses below torch 2.6
([CVE-2025-32434](https://github.com/advisories/GHSA-53q9-r3pm-6pq6)). So **this example
cannot answer the ML-vs-LLM question its twin answers** — see
[`HANDOVER_DBPEDIA_BLOCKED_ARM.md`](../../research/HANDOVER_DBPEDIA_BLOCKED_ARM.md). That
absence is precisely why the NER example was built with a *matched pair* of local arms.

`bart_mnli` did run, and its calibration is the interesting result: confidence 0.317
against accuracy 0.629, an ECE of 0.311 — badly underconfident, because zero-shot NLI
normalises entailment across candidate labels and with 14 candidates the mass spreads thin
regardless of certainty. **The raw score is a good ranking signal and not a probability.**

## Why these success criteria

Identical to AG News, deliberately — changing the metric between the two would confound
regime with measurement.

What differs is **what the criteria can do**:

- **Accuracy stops discriminating.** The leader separated from only 8 of 26 opponents; the
  top ten are one group across a 115× price range.
- **So the label-noise pass becomes the main instrument, not a diagnostic.** On a saturated
  task the field's consensus errors *are* the ceiling. Fourteen arms reported byte-identical
  accuracy, macro-F1 **and** worst class — traced to one item: *"Dukart's Canal"*, gold
  `NaturalPlace`, which 20 of 24 arms called `MeanOfTransportation`. It is a man-made
  waterway built to move coal. The models are right and the ontology's label is the odd one
  out.
- **And rank-stability stops being readable.** With 19.8 of 27 arms tied at n=10, Spearman's
  ρ was correlating *arm names*. That is what drove the `arms tied 1st` column into the
  tool, and later the tie-correct ρ. Requiring a unique winner, **400 of 400 draws are
  undecided at every n tested** — the corpus has no winner to agree about.

**The transferable lesson:** on a saturated benchmark, the headline metric is the least
informative number on the page, and a ranking computed from it is mostly an artifact of
tie-breaking.

---

## Credits

**Dataset** — [DBpedia-14](https://huggingface.co/datasets/fancyzhx/dbpedia_14),
CC-BY-SA 3.0 + GFDL. Ontology and abstracts from
[DBpedia](https://www.dbpedia.org/) / Wikipedia; the 14-class split from
[Zhang, Zhao & LeCun (2015)](https://arxiv.org/abs/1509.01626). Not redistributed.

**Models** — [`facebook/bart-large-mnli`](https://huggingface.co/facebook/bart-large-mnli)
([zero-shot NLI](https://arxiv.org/abs/1909.00161)). Blocked:
[`fabriceyhc/bert-base-uncased-dbpedia_14`](https://huggingface.co/fabriceyhc/bert-base-uncased-dbpedia_14).
Hosted models in [`docs/REFERENCE.md`](../../docs/REFERENCE.md#hosted--24-arms-8-vendors--3-price-tiers).

**Method** — Holm (1979), *A Simple Sequentially Rejective Multiple Test Procedure*, Scand. J. Statist. 6(2):65–70;
[Demšar (2006)](https://www.jmlr.org/papers/v7/demsar06a.html) for Friedman/Nemenyi;
[Guo et al. (2017)](https://arxiv.org/abs/1706.04599) for calibration.

**Software** — [transformers](https://github.com/huggingface/transformers) 4.55.4 ·
[torch](https://github.com/pytorch/pytorch) 2.2.2 ·
[scikit-learn](https://scikit-learn.org/) 1.9.1 ·
[LiteLLM](https://github.com/BerriAI/litellm) · [uv](https://github.com/astral-sh/uv).
