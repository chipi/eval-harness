# MLflow and TensorBoard, side by side with evh

**Status:** 2026-11-27, a first draft for the owner. PLAN_0.8.3 item A. Written from documentation only: nothing was
installed or run. Every idea is a candidate for the owner, not a decision.

## How this was read, and its limits

- MLflow: `mlflow.org/docs/latest/...`. PyPI lists **MLflow 3.18.0, 2026-11-03** as the latest release
  (https://pypi.org/project/mlflow/). The docs pages are "latest" and do not print their own version; only the Tracking
  page says it describes "MLflow 3" (https://mlflow.org/docs/latest/ml/tracking/). I take "latest" as 3.18.x; unverified.
- TensorBoard: PyPI lists **2.21.0, 2026-06-29** (https://pypi.org/project/tensorboard/). The tensorflow.org tutorials are
  undated Colab notebooks of the TF 2.x era (the profiler page prints TF 2.2). The hparams page says its API and UI are
  "in a preview stage".
- The fetch tool summarises pages through a small model, so a quoted phrase may be a paraphrase. Where a claim comes from
  a web-search excerpt and not from a page I opened, the row says "(search excerpt)".
- Several mlflow.org pages returned HTTP 403 (tracking UI, backend stores, running-evaluation); claims that would need them
  are marked "not read".
- evh: read in `/work/eval-harness/worktrees/083` at 0.8.2 (`bf8d2eeb4` plus branch 083). Cited as file:heading.
- "No" for MLflow or TensorBoard means "not found in the pages I read", never "the product cannot".

## 1. What each records

| Thing | MLflow | TensorBoard | evh |
| --- | --- | --- | --- |
| Run | yes: a run holds "run ID, timing, parameters, metrics" and artifacts ([Tracking](https://mlflow.org/docs/latest/ml/tracking/)) | yes, a "run" is a subdirectory of the logdir that holds tfevents data ([README](https://raw.githubusercontent.com/tensorflow/tensorboard/master/README.md)) | yes: a run is a system on a dataset, with per-item results (CONCEPTS.md:"Three inputs, or the number means nothing") |
| Params | yes: `mlflow.log_param(s)` ([Tracking API](https://mlflow.org/docs/latest/ml/tracking/tracking-api/)) | partly: HParams records "the values used in this trial" per run ([hparams](https://www.tensorflow.org/tensorboard/hyperparameter_tuning_with_hparams)) | yes: the system record, hashed into the fingerprint (CONCEPTS.md:"A fingerprint says what was measured...") |
| Metrics | yes: `log_metric(s)` "with optional step/timestamp" ([Tracking API](https://mlflow.org/docs/latest/ml/tracking/tracking-api/)) | yes: scalars by step, `tf.summary.scalar` ([get started](https://www.tensorflow.org/tensorboard/get_started)) | yes: per-item scores, aggregates, cost and latency per item (CONCEPTS.md:"Cost and speed are part of quality") |
| Artifacts | yes: `log_artifact`, "model weights, images, Parquet files" ([Tracking](https://mlflow.org/docs/latest/ml/tracking/)) | partly: images, audio, text, embedding checkpoints and profiles live in the logdir ([README](https://github.com/tensorflow/tensorboard)) | partly: per-item artifact link (`meta["artifact"]`, RUNBOOK.md:"14. Browse the catalog and the inspector") |
| Datasets | yes: `mlflow.log_input` with name, digest, source, schema, profile and a context label ([Dataset](https://mlflow.org/docs/latest/ml/dataset/)) | no | yes: frozen, a sha256 per item, versions, licence, card (CONCEPTS.md:"`dataset_id` is a contract, not a label") |
| Tags / system context | yes: tags; auto tags `mlflow.source.git.commit`, `mlflow.user` ([Tracking API](https://mlflow.org/docs/latest/ml/tracking/tracking-api/)) | no | yes: `build.ref`, actor on every record (CONCEPTS.md:"An agent works when asked...") |
| Model registry | yes: registered models, versions, aliases (`@champion`), tags, link of each version to its run ([Model Registry](https://mlflow.org/docs/latest/ml/model-registry/)) | no | partly: a model record with deployments and settings, not weights (CONCEPTS.md:"A model is set up once, where it runs"); baselines are versioned and rolled back (CONCEPTS.md:"A baseline is a decision") |
| Prompt registry | yes: immutable versions, aliases, lineage to evaluations and traces ([Prompt Registry](https://mlflow.org/docs/latest/genai/prompt-registry/)) | no | yes: prompt versions, checked against bytes (RFC-028, Accepted; RUNBOOK.md:"Datasets" table, V24) |
| LLM / GenAI evaluation | yes: evaluation datasets (inputs, expectations, tags), scorers, LLM judges, human feedback on traces ([GenAI eval](https://mlflow.org/docs/latest/genai/eval-monitor/), [datasets](https://mlflow.org/docs/latest/genai/datasets/)) | no | yes: the product (PRODUCT.md:"Product Purpose") |
| Scorer kinds | yes: built-in LLM judges, guideline judges, custom judges, code scorers ([Scorers](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/)) | no | yes: code scorers, judge scorers in grade, pick, pairwise modes (RUNBOOK.md:"Judging modes: grade, pick, pairwise") |
| Tracing | yes: inputs, outputs, metadata per step, latency, tokens, cost, feedback; OpenTelemetry-compatible ([Tracing](https://mlflow.org/docs/latest/genai/tracing/)) | no (Profile is a performance trace of TF ops, not LLM calls: [profiler](https://www.tensorflow.org/tensorboard/tensorboard_profiling_keras)) | partly: timing, tokens and cost per call, not span trees; replay of production code (RUNBOOK.md:"15c. Replaying the code that ran"); OpenTelemetry only in the deployment's hooks (INTEGRATION.md:"The catalog and the inspector") |
| Histograms / distributions | no | yes: "distribution of a Tensor over time"; `histogram_freq` is off by default ([get started](https://www.tensorflow.org/tensorboard/get_started)) | no |
| Embeddings | no | yes: Embedding Projector reads a checkpoint plus `metadata.tsv` ([projector](https://www.tensorflow.org/tensorboard/tensorboard_projector_plugin)) | no |
| Other | AI Gateway: usage, model, cost, traces per call; prompt optimization ([gateway](https://mlflow.org/docs/latest/genai/governance/ai-gateway/), [README](https://github.com/mlflow/mlflow)) | model graph, images, audio, text, HParams, profile ([README](https://github.com/tensorflow/tensorboard)) | labels, references, captures from production, studies, goals, rounds (CONCEPTS.md, RUNBOOK.md) |

## 2. How each stores and serves it, and the day-to-day

| | MLflow | TensorBoard | evh |
| --- | --- | --- | --- |
| Metadata store | "backend store": file system or SQL (PostgreSQL, MySQL, SQLite, MSSQL via SQLAlchemy) ([architecture](https://mlflow.org/docs/latest/self-hosting/architecture/overview/)) | none: event files in the logdir | files under `data/`, or one SQLite database (PRODUCT.md:"Operating Context"; ADR-0030, Accepted) |
| Large files | "artifact store": local dir or object storage such as S3 ([architecture](https://mlflow.org/docs/latest/self-hosting/architecture/overview/)) | same logdir | files in the project; items and outputs per run (RFC-024, Accepted and built) |
| Server | optional FastAPI "tracking server" with REST and UI; default is a local `mlruns` directory; remote server for teams ([architecture](https://mlflow.org/docs/latest/self-hosting/architecture/overview/)) | `tensorboard --logdir path`, UI on localhost:6006 ([get started](https://www.tensorflow.org/tensorboard/get_started)); "runs entirely offline" ([README](https://github.com/tensorflow/tensorboard)) | `evh catalog-serve` on 127.0.0.1; `--public` read-only; `evh mcp` (RUNBOOK.md:"14. Browse the catalog and the inspector") |
| Format | database rows plus artifact files; the on-disk layout was not read | tfevents: "append-only record dump" with "tfevents" in the filename ([README](https://raw.githubusercontent.com/tensorflow/tensorboard/master/README.md)) | JSON, YAML, JSONL; SQLite tables (ADR-0030; RUNBOOK.md:"The data's format, and migrating it") |
| Multi-user | workspaces separate teams on shared infrastructure; access controls need the server ([architecture](https://mlflow.org/docs/latest/self-hosting/architecture/overview/)) | README states offline operation; "no mention of authentication" in the page read | the local server answers anyone who can reach it; `--public` holds back item text (CONCEPTS.md:"An agent works when asked...") |
| Limits seen | evaluation datasets "require ... a SQL backend", not the file store ([datasets](https://mlflow.org/docs/latest/genai/datasets/)) | "one event file written at a time" per directory; reservoir sampling; no GCS logdirs in the reduced no-TensorFlow mode ([README](https://github.com/tensorflow/tensorboard)) | one machine per project; no multi-writer server documented |
| Hosted service | Databricks offers an enhanced registry ([registry](https://mlflow.org/docs/latest/ml/model-registry/)) | TensorBoard.dev was shut down by 2023-12-31 (search excerpt; primary page not fetched) | evals.humancopilot.eu is a read-only catalog (PRODUCT.md:"Platform") |
| Day to day | add `mlflow.log_*` or `mlflow.autolog()` to training or app code ([Tracking API](https://mlflow.org/docs/latest/ml/tracking/tracking-api/)); look at runs in the UI; register a model version, move an alias; for GenAI, trace the app, score traces with judges, collect human feedback | write summaries during training, point `tensorboard` at the logdir, watch curves as training goes, compare runs as overlaid lines ([get started](https://www.tensorflow.org/tensorboard/get_started)); HParams table, parallel coordinates and scatter views over trials ([hparams](https://www.tensorflow.org/tensorboard/hyperparameter_tuning_with_hparams)) | freeze data, run arms, read the refusals, name a goal, open a round, promote a baseline with a reason (CONCEPTS.md; RUNBOOK.md:"The loop") |

## 3. Overlap with evh, row by row

Each cell: yes (how) / partly (what) / no.

| Row | MLflow | TensorBoard | evh |
| --- | --- | --- | --- |
| Fingerprints and code identity | **partly.** Git commit and user are auto-tagged ([Tracking API](https://mlflow.org/docs/latest/ml/tracking/tracking-api/)); a dataset has a content digest ([Dataset](https://mlflow.org/docs/latest/ml/dataset/)). No single hash of code, data, deployment and settings, and no refusal to compare on a mismatch, in pages read | **no.** Nothing on code or data identity in pages read | **yes.** Four hashed parts (instrument, data, deployment, settings) with the runner outside; `run-compare` names the part that moved (CONCEPTS.md:"A fingerprint says what was measured..."; RFC-001 Completed, RFC-021 Built for 0.6.0) |
| References and their tiers | **partly.** Evaluation datasets hold "expectations (ground truth)" and a per-record source type ([datasets](https://mlflow.org/docs/latest/genai/datasets/)). No gold/silver tier, no promotion of a label set, in pages read | **no** | **yes.** Labels by person, model or rule; a reference is promoted at gold or silver with a reason; every run records `reference_tier` (CONCEPTS.md:"Gold is not silver, and a label is not a reference"; RFC-023 Accepted, ADR-0020, ADR-0022) |
| Judges measured against people | **yes (how).** `judge.align()` learns from traces that carry both a judge assessment and human feedback of the same name; at least 10 traces; optimizers MemAlign (default), SIMBA, GEPA; the docs show a `test_alignment_improvement()` function that compares aligned and original judges with human labels ([alignment](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/alignment/)). MemAlign is called experimental (search excerpt, Databricks mirror: https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/align-judges). Its goal is to change the judge; it is not a gate on use | **no** | **yes.** A judge is validated as an arm on human-rated items (tau, top1, pair_agreement) against a random floor and `min_metric`; the gate refuses an unvalidated judge unless `--unvalidated`; people against people is `human_tau` (RUNBOOK.md:"Validating a judge: what the gate needs"; ADR-0001 Accepted; RFC-038 Accepted) |
| Rounds and goals | **partly.** Experiments group runs (`set_experiment`); registry aliases name the current version ([registry](https://mlflow.org/docs/latest/ml/model-registry/)). No goal (decision, measure, datasets) and no round with arms dropped and a conclusion, in pages read | **no.** HParams "session groups" are trials of one setup ([hparams](https://www.tensorflow.org/tensorboard/hyperparameter_tuning_with_hparams)) | **yes.** A goal names the use, decision and measure; a round records what changed, arms carried and dropped with reasons, and the conclusion (CONCEPTS.md:"A goal says what the evaluation is for", "A round records a decision, not just a result"; ADR-0004, RFC-004 Completed) |
| Held-out discipline (sealed splits, looks) | **partly.** A context label on `log_input` such as 'training', 'validation', 'evaluation' ([Dataset](https://mlflow.org/docs/latest/ml/dataset/)). Docs describe it as a label; no enforcement, no count of looks, in pages read. The eval-dataset page positions datasets as test suites, "distinct from held-out training data splitting" ([datasets](https://mlflow.org/docs/latest/genai/datasets/)) | **no** | **yes.** `dataset-split --seal`, unseal per system with a recorded look, look k decided at a stricter level, exposure register (RUNBOOK.md:"Datasets" table and "Test sets and their looks"; RFC-029 Accepted; RFC-031 Accepted and built) |
| The catalog and the Workbench | **partly.** A UI over experiments, runs, models, traces, datasets; run comparison and artifact download ([Tracking](https://mlflow.org/docs/latest/ml/tracking/)); human feedback can be entered in the UI ([alignment](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/alignment/)). One UI that reads and writes; no read-only public view found | **partly.** Read-only dashboards over the logdir ([get started](https://www.tensorflow.org/tensorboard/get_started)); no run launching | **yes.** A read-only static catalog, an inspector, a Workbench that writes on this machine, every action also an `evh` command (PRODUCT.md:"Capabilities and Constraints"; RFC-039, RFC-040; ADR-0027) |
| Statistics: paired tests, Holm, bootstrap, intervals | **no** in pages read: the scorers page says aggregation is not discussed ([Scorers](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/)); the evaluate page returned 403 (not read). A search for bootstrap or confidence intervals in `mlflow.evaluate` found no doc page | **no** in pages read | **yes.** Paired sign-flip test, exact up to 30 items, then 20,000 permutations, normal limit from 10,000 (ADR-0028); Holm in `family-test`; Bonferroni for a chosen leader; non-inferiority (Tango, bootstrap-t); `bootstrap-test` percentile interval; Bradley-Terry with a 95% interval (RUNBOOK.md:"7b. The analysis tools"; ADR-0026 Accepted) |

Where the products are closest: MLflow's GenAI side (datasets, judges, human feedback, traces, a prompt registry) and
evh's capture lane and judge validation. Where they are furthest: TensorBoard is a training-time viewer of curves;
evh is a decision record over frozen evaluations.

## 4. What evh could learn or borrow

All rows are candidates for the owner.

### Ideas

| Idea | From | What it would mean in evh | Moves a result |
| --- | --- | --- | --- |
| Per-call model and provider on the record | MLflow tracing: model name on a span, cost computed from it ([token-usage](https://mlflow.org/docs/latest/genai/tracing/token-usage-cost/)); a provider attribute exists (search excerpt of [attribute mapping](https://www.mlflow.org/docs/latest/genai/tracing/opentelemetry/attribute-mapping/), page not opened) | G6 below | yes |
| Aliases over immutable versions | MLflow registry and prompt registry ([registry](https://mlflow.org/docs/latest/ml/model-registry/), [prompts](https://mlflow.org/docs/latest/genai/prompt-registry/)) | evh already has versioned baselines and rollback; nothing to add beyond naming | no |
| Judge improvement loop | MLflow `align()` ([alignment](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/alignment/)) | evh validates and gates a judge but never edits one; a "suggest a rubric change from the judge's disagreements with people, then validate it as a new scorer" step would fit `supersedes:`. Needs an owner view on whether a model should write a scorer | no |
| Dataset from traces | MLflow evaluation datasets from filtered production traces ([datasets](https://mlflow.org/docs/latest/genai/datasets/)) | same idea as the capture lane (RFC-019 Built); no gap found | no |
| Curves over steps with several runs overlaid | TensorBoard scalars ([get started](https://www.tensorflow.org/tensorboard/get_started)) | G1 below | no |
| Parallel-coordinates view over trials | TensorBoard HParams ([hparams](https://www.tensorflow.org/tensorboard/hyperparameter_tuning_with_hparams)) | for a study's trials; `chart study-progress` exists (RUNBOOK.md:"Reading results"); not clearly a gap | no |
| OpenTelemetry for call traces | MLflow Tracing ([Tracing](https://mlflow.org/docs/latest/genai/tracing/)) | evh uses OpenTelemetry only in the deployment's hooks; per-item call spans are not an evh feature | no |

### Not import or export (the owner, 2026-11-27)

The owner ruled out importing from or exporting to either tool: the point is what evh can learn from how they let people
see results. The views below come from that, built on what evh already records (paired per-item results, baselines,
rounds). Each went to the three beta projects; their answers are in PLAN_0.9.0, section V.

| View | Borrowed from | In evh |
| --- | --- | --- |
| V1. A progression chart that carries a verdict | TensorBoard: several runs' scalars overlaid on one step axis | x = rounds or arms in lineage order, y = the primary with its interval, the baseline as a band, each point marked significant or not against it, a break where a round moved dataset, a guard panel with its limit line |
| V2. What each change bought | MLflow: comparing two runs' parameters side by side | the chain along `hypothesis.against`, each step the paired difference from its parent; labelled by `hypothesis.statement`, the config diff as a cross-check that flags a step with more than one change |
| V3. Items that flipped between a parent and a child | TensorBoard: distributions over time (where values moved, not only the mean) | the paired per-item results, as better / worse / same, filterable by a per-item metric or field |
| V4. A selection curve that is never evidence | both: a metric against a step within training | candidates on a dataset marked for selection, against checkpoint step or iteration, the chosen one marked, kept out of leaderboards (G3) |
| V5. A judge's disagreements with people | MLflow `align()`, without its automatic rewriting | a reading list on judge validation, a fixed rubric then a new scorer (`supersedes:`) validated again. Dropped: no beta project has a judge measured against people |
| (G6) The provider a gateway used, per call | MLflow tracing and AI Gateway: model and cost per call | recorded and compared like a deployment field (PLAN_0.9.0, M) |

Not borrowed: TensorBoard's embedding projector and smoothing (no beta case); MLflow's aliases (evh's versioned
baselines do this) and autolog (evh's adapters).

## 5. The 0.9.0 beta-survey items (PLAN_0.9.0.md, G)

Does MLflow or TensorBoard already have an equivalent? "Equivalent" means for the need as the survey states it.

| Item | MLflow | TensorBoard | Reading |
| --- | --- | --- | --- |
| G1 progression across rounds, with the baseline's line | **partly.** Metrics are logged "with optional step/timestamp" and the UI offers "metric visualization" ([Tracking API](https://mlflow.org/docs/latest/ml/tracking/tracking-api/), [Tracking](https://mlflow.org/docs/latest/ml/tracking/)); chart types (line, bar, scatter, parallel coordinates, contour) are described on Databricks' mirror, not on a page I could open from mlflow.org ([search excerpt](https://docs.databricks.com/aws/en/mlflow/visualize-runs)). No round axis, no baseline line, no interval or significance mark found | **partly.** Scalars by step, runs overlaid ([get started](https://www.tensorflow.org/tensorboard/get_started)). Step is the x axis, so a round would be a step. No baseline line, no interval, no significance mark in pages read | A curve over steps exists in both. The survey's need (arms in lineage order, a baseline line, a mark for significance, a second panel for the guard) is not documented in either |
| G3 selection-only datasets (a mark on the dataset, kept out of evidence views) | **partly.** `log_input` takes a context label such as 'validation' or 'evaluation' ([Dataset](https://mlflow.org/docs/latest/ml/dataset/)). It is set when the dataset is logged to a run, not on the dataset; no rule that leaves it out of a comparison is documented | **no** | Neither has the mark on the dataset or an exclusion rule. MLflow's label is nearest, and it is per logging call, the shape the fleet and eval projects said they do not want |
| G4 lineage (parent and the one change) | **partly.** A registered model version links to the experiment and run that made it, and carries tags ([registry](https://mlflow.org/docs/latest/ml/model-registry/)); prompt versions have lineage to evaluations ([prompts](https://mlflow.org/docs/latest/genai/prompt-registry/)); MLflow 3 adds logged models ([Tracking API](https://mlflow.org/docs/latest/ml/tracking/tracking-api/)). A parent model and a "changed: prompt / model / code" field: not found. Nested or parent runs: not read | **no** | Provenance (this version came from that run) exists in MLflow; parent-plus-one-change does not appear in pages read. A tag could carry it by convention |
| G6 provider and model a gateway reports per call, compared like a deployment field | **partly.** Spans record the model name and cost is computed from it ([token-usage](https://mlflow.org/docs/latest/genai/tracing/token-usage-cost/)); a provider attribute exists (search excerpt); the AI Gateway logs usage, model, cost and routing per call ([gateway](https://mlflow.org/docs/latest/genai/governance/ai-gateway/)). Whether it records the upstream provider a gateway chose behind an alias: not stated. Nothing compares it to decide "not the same measurement" | **no** | Recording per call is documented in MLflow; treating a change of provider as a different measurement is evh's own need and is in neither |

## Not covered

- MLflow pages that returned 403 and were not read: tracking UI, backend and artifact store reference, running-evaluation,
  `mlflow.evaluate` API docs. Chart types and comparison in the OSS UI therefore rest on a Databricks mirror in a search
  excerpt.
- MLflow: Projects, Model Serving and deployment, the AI Gateway's configuration, workspaces beyond one line, nested
  runs, human-feedback labeling sessions, the REST API, the on-disk file layout, any import or export tooling
  (including third-party `mlflow-export-import`), the Python API reference, release notes between MLflow 3.0 and 3.18.
- MLflow's statistics: I found no page that documents a paired test or interval. A page I did not open may.
- TensorBoard: text, audio, graph, custom-scalar and what-if plugins (named in the README, not opened except images,
  embeddings, hparams, profile); the plugin API; how to write tfevents without TensorFlow; `--logdir_spec` beyond one
  quotation; remote and cloud-hosted TensorBoard (Vertex, SageMaker) beyond search titles; TensorBoard.dev's
  shutdown has only a search excerpt behind it.
- Both: licence terms, performance at scale, security hardening, measured behaviour. Nothing was installed or run, so
  every "yes" is "documented", not "works".
- evh: only the files named in the request, plus the plan files. I did not read RFC bodies beyond status lines and the
  first sections of RFC-029 and RFC-031, the PRDs, UXS, tutorials, `docs/architecture`, `research/internal/FIELD_ALIGNMENT_0.8.0.md`
  (it mentions MLflow evaluate once, line 230, as "not looked at"), or any code. Statistics claims rest on RUNBOOK
  prose, not on the code.
- RFC statuses seen: RFC-001 Completed (v0.4.0); RFC-004 Completed (v0.4.0); RFC-019 Built for 0.6.0; RFC-021 Built for
  0.6.0; RFC-023 Accepted (owner, 2026-11-01), built; RFC-024 Accepted and built for 0.8.0; RFC-028 Accepted, built;
  RFC-029 Accepted, built 2026-11-11; RFC-031 Accepted and built (0.8.0); RFC-035 Draft; RFC-036 Draft; RFC-037 Draft;
  RFC-038 Accepted (0.8.0); RFC-039 Accepted, built in 0.8.1; RFC-040 Accepted and built (0.8.1).
