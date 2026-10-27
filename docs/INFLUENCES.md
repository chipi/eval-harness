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
| **Build your own evaluation, on your own data** — the reason the harness exists, and the message of [Use it](https://evals.humancopilot.eu/use.html) | *AI Engineering* ch. 4: public benchmarks rarely identify the best model for a specific application, and are likely contaminated; choosing a model is building a **private leaderboard**; the lack of a reliable evaluation pipeline is one of the biggest blockers to adoption | A drop-in harness for that private leaderboard, and six worked examples showing what a public leaderboard would have hidden |
| **Silver is not gold** — model-written references rank, person-written ones judge | *AI Engineering* ch. 3: AI-as-a-judge evaluation is subjective, depends on the judge, is not comparable across judges, and should be supplemented with exact or human evaluation | Reference tiers recorded on every run; gold preferred automatically; [`silver-calibrate`](../harness/docs/RUNBOOK.md); `rescore --reference-id` to move runs onto gold for $0; and [SummEval](../research/REPORT_SUMMEVAL.md), which measures 24 AI judges against expert judgement directly |
| **Temperature 0 is not deterministic** — measure the noise before the difference | *AI Engineering* ch. 2: sampling makes models probabilistic, which causes inconsistency; the aim is AI engineering that is "if not deterministic, at least systematic" | Every arm can be repeated and its own spread measured (`REPEAT=3`); in an earlier 20-article sweep at temperature 0, 9.8% of hosted-model outputs (47 of 480) were byte-identical across three repeats ([REPORT_SUMMARIZATION](../research/REPORT_SUMMARIZATION.md)) |
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

## The standards 0.5.0 follows

The 0.5.0 designs ([PRD-008 to PRD-013](prd/index.md)) take their vocabulary and their methods
from these, so a reader who knows one of them recognises the flow. Each link was checked on
2026-10-26.

**Optimisation studies: inspired by Andrej Karpathy's autoresearch**

The studies in [PRD-009](prd/PRD-009-prompts-and-optimisation.md) take their shape directly from
Andrej Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) (2026): a person writes the
direction in plain words (its `program.md`), an agent tries one change at a time against an evaluation
it cannot touch (its `prepare.py`), keeps what improved and discards the rest, and logs every try (its
`results.tsv`). We say so plainly: that is the loop, and its idea that the person "programs the program"
while the agent does the trying is why the harness lets an agent drive a study, takes its directions as
written, and imports its `results.tsv`. The podcast project this harness grew up with adapted it first,
for prompts and for pipeline parameters, and its experience shaped what the harness adds.

What is different, deliberately, and why:

- **What changes.** autoresearch edits code (`train.py`); a study changes prompts, parameters, models
  and pipeline settings, never code, and the harness never writes git (a winner leaves as files).
- **What "better" means.** autoresearch keeps any improvement on its validation measure; a study
  calls that search (an *exploratory* study is exactly autoresearch's loop), and a claim that the winner
  is better needs a *confirmatory* check on heldout items the search never saw, declared beforehand and
  paid for (the statistics below).
- **When it stops.** autoresearch runs until interrupted; a study can too, always under a hard cap on
  money and time, and it asks the person before anything with consequences.

**Statistics of choosing among many candidates**

- **Searching is not proving: one counted check on held-out items** — Dwork et al.,
  [*The reusable holdout*](https://doi.org/10.1126/science.aaa9375) (Science, 2015); Blum and
  Hardt, [*The Ladder*](https://arxiv.org/abs/1502.04585) (2015); Cawley and Talbot,
  [*On over-fitting in model selection*](https://www.jmlr.org/papers/v11/cawley10a.html)
  (JMLR, 2010); Smith and Winkler, [*The optimizer's curse*](https://doi.org/10.1287/mnsc.1050.0451)
  (Management Science, 2006).
- **Monitoring as results arrive** — Johari et al.,
  [*Always valid inference*](https://arxiv.org/abs/1512.04922); Ramdas et al.,
  [*Game-theoretic statistics and safe anytime-valid inference*](https://doi.org/10.1214/23-STS894)
  (Statistical Science, 2023).
- **A tie is an equivalence claim** — Schuirmann, the two one-sided tests
  ([1987](https://doi.org/10.1007/BF01068419)); Lakens,
  [*Equivalence tests*](https://doi.org/10.1177/1948550617697177) (2017). For 0/1 measures, Tango's
  score test for the difference of paired proportions
  ([Statistics in Medicine, 1998](https://doi.org/10.1002/%28SICI%291097-0258%2819980430%2917%3A8%3C891%3A%3AAID-SIM780%3E3.0.CO%3B2-B)).
- **Each look at heldout items costs part of the level** — Tian and Ramdas,
  [*Online control of the familywise error rate*](https://arxiv.org/abs/1910.04900).
- **Intervals and power beside every verdict** — Miller,
  [*Adding error bars to evals*](https://arxiv.org/abs/2411.00640) (2024); Card et al.,
  [*With little power comes great responsibility*](https://doi.org/10.18653/v1/2020.emnlp-main.745)
  (EMNLP 2020).
- **A goal's measure and its guardrail metrics; rounds as declared intent** — Kohavi, Tang and Xu,
  [*Trustworthy Online Controlled Experiments*](https://doi.org/10.1017/9781108653985) (2020);
  Nosek et al., [*The preregistration revolution*](https://doi.org/10.1073/pnas.1708274114)
  (PNAS, 2018).
- **Judges' biases** — Zheng et al., [*Judging LLM-as-a-judge*](https://arxiv.org/abs/2306.05685)
  (2023); Panickssery et al.,
  [*LLM evaluators recognize and favor their own generations*](https://arxiv.org/abs/2404.13076)
  (2024).

**Prompt and parameter optimisation**

- **Study, trial, ask and tell** — Optuna's
  [ask-and-tell interface](https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/009_ask_and_tell.html).
- **Optimising prompts** — DSPy's [optimizers](https://dspy.ai/current/api/optimizers/); Yang et
  al., [OPRO](https://arxiv.org/abs/2309.03409); Zhou et al., [APE](https://arxiv.org/abs/2211.01910);
  Yuksekgonul et al., [TextGrad](https://arxiv.org/abs/2406.07496).

**Records, registries and provenance**

- **Versions are fixed, aliases move (`name/3`, `name@current`)** — the MLflow
  [Model Registry](https://mlflow.org/docs/latest/ml/model-registry/) and
  [Prompt Registry](https://mlflow.org/docs/latest/genai/prompt-registry/).
- **Who acted, and for whom** — W3C [PROV-O](https://www.w3.org/TR/prov-o/); runs, jobs and
  datasets as events: [OpenLineage](https://openlineage.io/docs/spec/object-model/).
- **What a published model or dataset record says** — Mitchell et al.,
  [*Model cards*](https://arxiv.org/abs/1810.03993) (2019); Gebru et al.,
  [*Datasheets for datasets*](https://arxiv.org/abs/1803.09010).

**Evaluation tools and traces**

- **Tasks, solvers, scorers, epochs, eval sets** — the UK AI Security Institute's
  [Inspect](https://inspect.aisi.org.uk/).
- **Stages as spans with standard attribute names** — OpenTelemetry's
  [GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai)
  (status: development).

**Running jobs**

- **Job states, retries, deadlines, logs** —
  [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/), Slurm's
  [job state codes](https://slurm.schedmd.com/squeue.html), the
  [Ray Jobs CLI](https://docs.ray.io/en/latest/cluster/running-applications/job-submission/cli.html).

**For agents and machines**

- **Tools, resources, long-running tasks, asking the person** — the
  [Model Context Protocol](https://modelcontextprotocol.io/specification/2026-07-28) (2026-07-28)
  and its [tasks extension](https://modelcontextprotocol.io/extensions/tasks/overview).
- **Skills** — the [Agent Skills specification](https://agentskills.io/specification).
- **Docs an agent can find** — [llms.txt](https://llmstxt.org/) (v2).
- **Commands a machine can call** — the [Command Line Interface Guidelines](https://clig.dev/);
  errors as [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html) problem details.

More, curated by Chip Huyen: [huyenchip.com/mlops](https://huyenchip.com/mlops/).
