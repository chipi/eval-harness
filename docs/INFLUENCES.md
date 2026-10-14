# Influences

**The approach in this repository builds on Chip Huyen's books** —
[*AI Engineering: Building Applications with Foundation Models*](https://www.oreilly.com/library/view/ai-engineering/9781098166298/)
(O'Reilly, 2025) and
[*Designing Machine Learning Systems*](https://www.oreilly.com/library/view/designing-machine-learning/9781098107956/)
(O'Reilly, 2022). Their framing — that evaluation is engineering work on *your* data, that
a model is chosen on a private leaderboard rather than a public one, that the dataset is a
design decision, and that every experiment must be tracked and versioned — is the
foundation this harness was built on. If the method here is useful to you, read them.

Below, each idea this project relies on, where her books set it out, and what this
repository added. The book references are to her own published chapter summaries
([*AI Engineering*](https://github.com/chiphuyen/aie-book/blob/main/chapter-summaries.md),
[*Designing ML Systems*](https://github.com/chiphuyen/dmls-book/blob/main/summary.md)),
so each line can be checked.

| Idea in this project | In her books | What this repository adds |
|---|---|---|
| **Build your own evaluation, on your own data** — the reason the harness exists, and the message of [Use it](https://chipi.github.io/eval-harness/use.html) | *AI Engineering* ch. 4: public benchmarks rarely identify the best model for a specific application, and are likely contaminated; choosing a model is building a **private leaderboard**; the lack of a reliable evaluation pipeline is one of the biggest blockers to adoption | A drop-in harness for that private leaderboard, and five worked examples showing what a public leaderboard would have hidden |
| **Silver is not gold** — model-written references rank, person-written ones judge | *AI Engineering* ch. 3: AI-as-a-judge evaluation is subjective, depends on the judge, is not comparable across judges, and should be supplemented with exact or human evaluation | Reference tiers recorded on every run; gold preferred automatically; [`silver-calibrate`](../harness/docs/RUNBOOK.md); `rescore --reference-id` to move runs onto gold for $0 |
| **No single score** — combine methods | *AI Engineering* ch. 4: no perfect evaluation method exists; combining methods mitigates their limits | Quality, billed cost and latency side by side in every comparison; standard metrics reported beside this repo's own |
| **The dataset is a design decision** — small, high-quality gold; size measured, not assumed | *AI Engineering* ch. 8: quality, coverage and quantity; a small amount of high-quality data can beat a large amount of noisy data; annotation guidelines are hard; performance-gain curves across dataset sizes | Datasets frozen by content hash and re-checked on every use; `rank-stability` to measure how many items a ranking needs |
| **Sampling, and the population a sample claims to represent** | *Designing ML Systems* ch. 4 (sampling methods) and ch. 8 (data distribution shifts) | The calibration rows that caught this repository's own all-CNN sample, and the DailyMail slice that tested whether findings travel |
| **Labels are expensive** — start without perfect ones | *Designing ML Systems* ch. 4: hand labels are expensive and slow; alternatives to them | Silver references by default, gold where a person has checked, and the tier stated wherever a number is published |
| **Baselines** | *Designing ML Systems* ch. 6: evaluation metrics don't mean much without a baseline to compare them to | Floor arms in every experiment (lead-3, keyword rules, a constant, random rankings); promoted baselines recorded with their reason |
| **Track and version every experiment** | *Designing ML Systems* ch. 6: intensive tracking and versioning of experiments, automated by tooling | A fingerprint per run — data, prompt, scorer, upstream model, libraries, commit — and refusals when it cannot be trusted (dirty tree, unknown build, two runs of one config) |

## Other foundations

- **Testing separations, not reading rank order** — the statistics are older than any of
  this: Holm (1979) for multiple comparisons, Demšar (2006) for comparing systems over
  many items, Dror et al. (2018) for significance testing in NLP. Full references in
  [REFERENCE](REFERENCE.md) and [papers](papers/README.md).
- **Calibrating an instrument against published results** — standard reproduction
  practice; each benchmark's original paper is the published value
  ([PROTOCOL](PROTOCOL.md)).
- **Production rules** — Martin Zinkevich, *Rules of Machine Learning* (Google): design and
  implement your metrics first. Breck et al., *The ML Test Score* (2017): tests for data,
  models and infrastructure.
- **Offline gains are not real gains** — Bernardi et al., *150 Successful Machine Learning
  Models* (KDD 2019, Booking.com).

More, curated by Chip Huyen: [huyenchip.com/mlops](https://huyenchip.com/mlops/).
