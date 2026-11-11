# Integrating your existing system

**The situation this is written for:** you have a working project. It has code
that does something — summarises, classifies, extracts, answers — and it has
data. What it does not have is evaluation. You change a prompt or swap a model
and you find out whether it helped by reading a few outputs and forming an
impression.

**What this costs you:** one function, and a YAML file per thing you want to
compare. No refactor. Your code does not move, does not get wrapped, does not
learn about this harness. The harness calls you.

---

## Where it goes

Pin it into your project, and start the project's folders:

```bash
cd /path/to/your-project
pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.7.2#subdirectory=harness"
evh init         # data/sources, data/configs, data/goals, data/fields, a .gitignore
```

That one install is everything: the hosted-model clients (`openai`, `anthropic`), the judges, the
catalog, the inspector and the MCP server for an agent ([below](#for-an-agent-evh-mcp)). There is
no extra to add. It needs Python 3.10 or later.

Keep `data/materialized/` out of git (derived; the `.gitignore` `evh init` writes already
does this) and decide whether to commit runs: keep each run's `metrics.json`,
`predictions.jsonl` and `outputs.jsonl` so scores can be recomputed. A project whose own layout
puts the harness's records elsewhere sets `EVAL_DATA_DIR`.

Your project **does not depend on it at runtime**, and it has no dependency on your
project: it shells out to nothing and imports nothing of yours until an arm names your
adapter. That
isolation is deliberate: an eval harness that requires a refactor does not get
adopted, and one that entangles with the system it measures stops being able to
measure it.

---

## The one function

`call_system()`, in `adapter.py` at your project's root (start from a copy of the bundled
adapter, `evaluation_harness/adapter.py`, which also has `score()`;
`python -c "import evaluation_harness, os; print(os.path.join(evaluation_harness.__path__[0], 'adapter.py'))"`
prints where it is). It receives one item's text and the
config's `params`, and returns what your system produced:

```python
from evaluation_harness.adapter import Result

def call_system(text: str, params: dict) -> Result:
    from myproject.summarise import summarise          # your existing code
    out = summarise(text, model=params["model"], temperature=params["temperature"])
    return Result(output=out.text,
                  tokens_in=out.usage.prompt_tokens,
                  tokens_out=out.usage.completion_tokens)
```

That is the integration. Everything else — freezing the dataset, hashing it,
recording which build ran, timing the call, aggregating, refusing bad
comparisons — is generic and already written. The harness times every call (`latency_ms`)
unless your `Result` reports its own; an optional `warmup(params)` in the same file runs once
before the first item (load a model, check a key), so it is not timed as the first call.

**Return what you can, omit what you cannot.** Every field beyond `output` is
optional. If your system cannot report token counts, leave them out; the
harness records what arrives and skips what does not.

### If your system is not a function call

- **A CLI** — `subprocess.run([...], capture_output=True)`, return stdout.
- **An HTTP service** — `httpx.post(...)`, return the response field.
- **A pipeline stage** — call the stage directly. You usually do not need the
  whole pipeline; you need the stage you are changing.

If calling one stage in isolation turns out to be hard, that is worth knowing
on its own. A stage you cannot invoke without booting everything is a stage you
cannot measure, and that is a design finding, not an eval problem.

### If your system is plain code

A filter, a router, a de-duplicator, a scheduler: code that decides, with no model in it. It is evaluated
like any arm; seven things are different. (The triage fleet's questions, 2026-11-05; its log is the worked case.)

- **The item holds the world the code read when it decided.** Code that reads external state (an issue
  tracker, a database, the clock) is measured on what it saw then, not what is there now. Freeze it into the
  item's body (one canonical JSON document per item, hashed like any item), and let the adapter answer the
  code's reads from it. Keys you filter or split by go in the item's fields (a field set, ADR-0003), not in
  the body.
- **One run is enough.** Deterministic code gives the same output every time, so k=1: `--repeat` adds
  nothing. (A temperature-0 model is not deterministic enough to skip repeats, but its repeats are not
  independent either: read the distinct items, not the item-runs; `run --repeat` and `pair-test` say how many
  items the repeats scored the same.)
- **Two goals, two questions.** *Is it right?* is a goal against gold (labels from outcomes, below).
  *Did it change?* is a regression guard: the same dataset scored against a silver reference made from the
  current code's own run (`evh label-from-run`, `evh reference-promote --tier silver`), and the changed items
  read with `evh inspect --runs A,B --items-out --disagree`. An arm that must give exactly what another gives
  (the same code at a newer commit) says `expect_identical_to: <config_id>` in its config, and `evh validate`
  fails it when it does not (RUNBOOK §4). [`examples/signal-fleet-dedup/`](../../examples/signal-fleet-dedup/README.md)
  is one, on the fleet's real signals.
- **The item is the unit judged.** `score()` sees one item, and a run's metric is the mean of its items'. A
  decision that depends on the ones before it (filing a signal into an issue opened by an earlier one) is
  one item whose body is the whole history, replayed in order, so the order effects are inside the item.
- **Links between items go into an outcome.** `evh label-from-capture` labels an item from its own record, so
  "A is a duplicate of B" is written into the item's outcome (B's id, or the group it joined), not as a label
  spanning two items.
- **Outcomes are joined by time and order, not by a key the outcome may not carry.** Match what production
  wrote to the decision that wrote it by the window between the cycle's previous decision and this one: a
  reopened issue need not name the fingerprint that reopened it. Measure the clock slack between the hosts
  involved before trusting a timestamp join: the fleet's host ran 1.6 s behind GitHub's for an hour.
- **The code is a record of its own.** `data/models/<id>.yaml` with `kind: code` holds its `repo` and its
  `versions`: each a `commit`, when it was `deployed` (`from`, `to`), and the `faithfulness` a replay measured
  (`agreed` of `items`, the named `exceptions`). It needs no `aliases`; an arm names it with `model_record` like
  any record, and its Models page and `evh models --model <id>` list the versions instead of an onboarding. A replay
  (`replay:` in the config, RFC-030) runs each item at the version deployed then, read from `checkout` (a local clone)
  or `repo` when it is a path; `evh faithfulness` writes each version's `faithfulness` (RUNBOOK §15c).

---

## The second function

`score()`, in the same file. It receives your system's output and the reference
for that item, and returns numbers:

```python
def score(output: str, reference: str | None) -> dict[str, float]:
    return {"rouge_l": rouge_l(output, reference),
            "has_required_section": 1.0 if "Summary:" in output else 0.0}
```

It is called with `reference=None` when no ground truth exists yet, so the same
adapter works before and after you have references. Return only what you can compute without a
reference then (an output's length, a format check), or `{}`: the run still records its outputs,
cost and latency, and `evh rescore` scores them once references exist.

When more than one answer is right for an item, its reference accepts each of them, written
`{"accept": ["escalate", "file"]}`. Read a reference with `answers(reference)` (from
`evaluation_harness.adapter`, beside `Result`): a list of one answer, or several. The bundled
`score` keeps the best overlap with any of them; yours decides what "right" means against a set.

**The shipped default is a placeholder.** Token-overlap F1 — enough to make the
loop run and rank arms crudely, not enough to defend a decision. Replace it
with what your domain actually rewards.

Beside `score()`, say what your metrics are: `PRIMARY_METRIC` (the one that decides; an adapter whose arms
measure different things, as a judge validated in several modes, may define `primary_metric(params)` instead:
given an arm's `params` it names that arm's primary, which `run` and `rescore` record, and `PRIMARY_METRIC` is
the fallback; the SummEval adapter's is `tau`, `top1` or `pair_agreement` by `params["mode"]`),
`METRIC_DIRECTIONS` (a quality metric that improves going down, `{"wer": "lower"}`),
`METRIC_KINDS` (what each metric is: `quality`, the default, ranked; `descriptive`, shown but
not ranked as quality, as a parse rate or a length; `cost` and `speed`, the leaderboard's cost and
speed columns and its frontier; `{"parse_ok": "descriptive", "cost_usd": "cost"}`) and
`METRIC_DESCRIPTIONS` (one sentence each, `{"rouge_l": "ROUGE-L F1 against the reference"}`,
or `{"summary": "one line", "details": "how it is computed and read"}`). Every run records
them; the metrics page shows the summary and each metric's own page the details. A description
is documentation: the catalog reads it from the adapter as it is today, over what a run recorded,
so describing a metric later needs no new run and moves no fingerprint (`evh rescore` refreshes
the record too, for $0). One metric name is described once across a project, so adapters that
share a name share its sentence.

An adapter that calls the system several times for one item (a probing conversation, a retry loop, a
judge after the answer) may say how many: `CALLS_PER_ITEM = 4`, or `calls_per_item(params)` returning the
number for an arm's `params`. Only `evh run --dry-run` reads it, to count the calls and multiply its
estimate; without it the dry run counts one per item, and says so. It does not make the estimate a bound
(a conversation that grows costs more than four first calls), so set a cost cap from what `evh arm-smoke`
measured. The adapter file is hashed into a run's fingerprint: adding the line is an edit like any other.

**A metric of the whole run**, which no mean of per-item scores can be (precision and recall over the pairs a
grouping makes, a calibration error, a coverage of distinct answers): define `score_run(items)` beside `score()`.
It is called once, after every item is scored, with each item's `item_id`, `output`, `reference` (or None) and
`scores` (what `score()` returned for it), and returns named numbers:

```python
def score_run(items: list[dict]) -> dict[str, float]:
    pairs = same_group_pairs(items)  # yours: which items the outputs put together, against the references
    return {"pair_precision": pairs.precision, "pair_recall": pairs.recall}
```

They go into the run's `scores` beside the means, and the record names them in `run_metrics`. A name must be its
own (not one `score()` returns), every value a finite number; a `score_run` that raises fails the run. `METRIC_KINDS`,
`METRIC_DIRECTIONS` and `METRIC_DESCRIPTIONS` describe them like any metric. The leaderboard shows them, with
their spread over an arm's runs; `evh rescore` computes them again from the stored outputs; `inspect` and the
comparison show each arm's recorded value but never test one, and `pair-test` and `family-test` refuse them by
name: with one number per run there is no item to pair. To test an arm against another on one, run each arm
several times and read the spread.

**Optional, for evaluating what production did** (RFC-023, [RUNBOOK §15b](RUNBOOK.md#15b-evaluating-what-production-did)),
in the same file:

| function | what it answers | read by |
|---|---|---|
| `decision(output)` | the decision in one output (a disposition, a label), without the reasons and traces around it | the sheet shows it per arm; with no `same`, two outputs agree when their decisions do |
| `title(item)` | a line that names an item (an alert's name, a ticket's subject) | the sheet shows it as the item's start, else the item's own first characters |
| `same(a, b)` | whether two outputs are one decision | agreement: `inspect --disagree`, the sheet's disagree and split, `label-sheet --items disagree` (default: the same decision, else the same text) |
| `recorded_output(record)` | production's own decision, from a capture's record | `arm-from-capture` (else `--field`) |
| `production_ran(record)` | what production ran for a record, under the keys a run's items report (`_meta`) | `deploy-sheet --capture` |

---

## What an "arm" is

A thing you want to compare, expressed as a config file — not a code edit:

```yaml
# data/configs/sonnet.yaml
config_id: sonnet_v1
dataset_id: my_corpus_v1
params:
  provider: anthropic
  model: claude-sonnet-4-6
  temperature: 0.0
  prompt: "Summarise the following transcript in 5 bullets:"
  usd_per_mtok_in: 3.0        # so the run records what it cost
  usd_per_mtok_out: 15.0
```

Four models to compare is four of these files, same `dataset_id`. The knobs
live in the config so an arm is reproducible and diffable; keeping them in code
means "which settings produced this number?" has no answer.

Prices live in the config too, deliberately: they change, and a run should
record the prices it was costed at. They are the fallback: when a provider's response carries
its bill (`usage.cost`), the run records the bill. Which provider does:
[RUNBOOK §4](RUNBOOK.md#4-point-the-harness-at-your-system).

A config holds `config_id`, `dataset_id`, `params`, and optionally `adapter` (a project with
several tasks names one per arm, `adapter: adapters/ner.py`), `goal` (what the evaluation is
for, `data/goals/<goal_id>.yaml`), `round` (an eval round of that goal, `rN`),
`format` (the output's shape, one of its goal's `output_contract` formats:
[RUNBOOK §4c](RUNBOOK.md#4c-the-goal-file-field-by-field)) and `hypothesis` (what the change
should do against which arm, committed before the run so a test of it counts as named in advance:
[RUNBOOK §4](RUNBOOK.md#4-point-the-harness-at-your-system); checked by V20). Any other key is
refused by `evh validate` (V1).

---

## Hosted models: you choose the provider, and bring your own key

`provider: anthropic` above is one choice. The bundled adapter, and any adapter of yours that
dispatches to its `PROVIDERS` (`from evaluation_harness.adapter import PROVIDERS, Result`), also
call OpenAI or any OpenAI-compatible endpoint (`provider: openai` with a `base_url`), OpenRouter
(`provider: openrouter`), and a LiteLLM proxy (`provider: litellm`). Each reads its key from the
environment or the project's `.env` (gitignored by `evh init`); the harness holds none.
**Which variable each provider reads, and what goes in the arm's `params`:
[tutorial 2](../../docs/tutorials/2-hosted-llm.md#1-choose-a-provider).** `evh env-check`
reports which are set. Judges use the same providers: each judge's `provider:` in the scorer
decides where its calls go. Judges read their own keys (`EVAL_JUDGE_<VAR>`) or share the arms'
credentials (`<VAR>`), so you can run judges on separate budgets or the same one
([RUNBOOK §12](RUNBOOK.md#12-re-measure-with-a-validated-judge)).

---

## Getting ground truth when you have none

Most projects do not have it. The sequence that works:

1. **Run your best model as an arm**, usually an expensive one you would not run in
   production, read its results, take its outputs as a model's labels, and promote them:
   ```bash
   evh run --config data/configs/frontier.yaml
   evh label-from-run --run <that run_id> --set frontier_v1
   evh reference-promote --dataset-id my_v1 --labels frontier_v1 --tier silver --reason "…" --by <you>
   ```
   Promoted as **silver**: a model's answers, not correct but *consistent*, which is enough to
   rank other arms against it: the cheaper arms are measured by how close they come to the
   expensive one. It calls nothing, and the labels name the run they came from.

2. **Review a few by hand.** Label the items you would sign in a sheet (`evh label-sheet
   --dataset-id <dataset_id> --items all --propose frontier_v1 --out sheet.csv`: `yes` takes the model's
   answer), import it as a person's labels (`evh label-import`) and promote them at gold. Gold
   outranks silver for every new run; `evh rescore --reference-id gold/<dataset_id>` re-scores
   the runs you have, for $0.

3. **Never let the distinction blur.** A run records which tier it scored
   against (`reference_tier` in its `metrics.json`). Silver-scored numbers are for
   ranking arms against each other; they are not a claim about correctness, and
   publishing them as one is how eval loses credibility internally.

Cost control: make the dataset small first (`evh dataset-create --limit 10`; `run` has no
`--limit`). Ten references is enough to rank four arms, and you can extend later without
re-authoring what you have.

4. **Or score without references at all**, with LLM judges that read each item and rate
   every arm's output (`evh judge-score`, optional). A judge is a model's opinion too, so
   the harness refuses one until runs show it agrees with human ratings on outputs like
   yours; until then it runs only as `--unvalidated`, labelled. The judge's task (what an
   item is, what the outputs are, which dimensions, which scale) is declared in the scorer,
   so it is not limited to summaries. [RUNBOOK §12](RUNBOOK.md#12-re-measure-with-a-validated-judge).

---

## What you get, in exchange for that one function

| you get | what it means |
| --- | --- |
| a frozen dataset | a `dataset_id` plus a sha256 per item — the thing that makes two numbers comparable |
| provenance | every run records which build produced it |
| noise floor | `--repeat 3` reports the arm's own spread, so you stop promoting jitter |
| cost and speed | per item and totalled, alongside quality |
| refusals | cross-dataset comparisons, dirty-tree promotions and unreasoned baselines are blocked, not warned about |
| integrity | `evh validate` fails CI on a tree that has drifted |
| re-measurement | stored outputs scored again for a new reference or scorer at $0, or by validated LLM judges, without re-running an arm |
| a judge panel | when the cheap metric is biased and you need an LLM to adjudicate |
| goals | what each evaluation is for, named on every config and checked by `evh validate` |
| eval rounds (optional) | round on round: what each round tried, what it kept and dropped and why, what it concluded ([tutorial 4](../../docs/tutorials/4-rounds-and-versions.md)) |
| item fields | the facts you know about each item (typed, declared once in a field set), checked by `evh validate`; items fetched from a pinned URL |
| a catalog and an inspector | pages over your runs, and a local server that tests any arms against a baseline and shows outputs beside references; every view is also an `evh` command |
| labels and references | what is right for an item and who said it (a person, a model, a rule), in sets that follow an item by its bytes; a reference set is only ever labels promoted on purpose, with a reason |
| production, evaluated | what your system did, kept as a capture; its decisions scored as an arm against labels; the rows where it was wrong picked for the next version of a dataset you govern ([tutorial 6](../../docs/tutorials/6-datasets-from-production.md)); the deploy sheet says what production must match to run what you promoted |

---

## The catalog and the inspector

`evh catalog` builds static pages over your runs: one per dataset and per goal,
one per reference (the label set it was promoted from, by whom and why, every arm scored against it),
the label sets and the captures, and a metrics page (what each metric measures, which way is better,
where it is recorded). Every arm's row says what it is scored against, and rows scored against silver,
by a judge, against a label set, or against the reference the arm wrote itself are tinted apart from
those scored against gold.
`evh catalog-serve` serves them with the run inspector on 127.0.0.1. Both only ask an
**adapter** questions: which arms exist, what each scored per item, which way is better,
which references exist, what one arm wrote for one item.

- **On the harness's layout, there is nothing to write.** The built-in `HarnessAdapter`
  reads `data/runs*/`, `data/references/`, `data/datasets/` and `data/goals/`, and its arm is
  one config on one dataset with its repeats averaged per item, exactly as `pair-test` reads
  them, so the inspector gives the same p.
- **With your own layout, write one adapter** and name it in your project's `config.yaml`:

  ```yaml
  catalog:
    adapter: tools/catalog_adapter.py:Adapter    # a file path or a module, then the class
  ```

  The class implements the `evaluation_harness.catalog_adapter.Adapter` protocol. Subclassing
  `HarnessAdapter` and overriding what differs is usually shorter than starting empty. The
  questions, grouped:

  | question | members |
  |---|---|
  | which arms, on which data | `arms()`, `arms_of(path)`, `describe(arm)`, `notes(arm)` |
  | what each scored, per item | `scores(arm, rescore=False)`, `recorded_means(arm)`, `input_hashes(arm)`, `can_rescore`. A goal's axes read their per-item values here: `cost_usd`, `tokens_in` + `tokens_out`, `latency_ms`, and any metric a goal names as its own axis ([ADR-0006](../../docs/adr/ADR-0006-goal-axes-and-strategies.md)); a project page that shows them imports `evaluation_harness.axes` (`axes_of`, `axis_title`, `decide`, `STRATEGIES`), the public module |
  | which way is better | `lower_is_better(metric, dataset)`, `is_neutral(metric, dataset)`, `preferred_metrics`, `shape_metrics` |
  | which references | `references()`, `reference_format(ref)`, `reference_archived(ref)` |
  | what was asked, what came back | `output_format(arm)` |
  | one item, side by side (the inspector only) | `item_view(arm, item)`, `reference_view(ref, item)` |
  | what it is for | `goals()`; the goal an arm names is `describe(arm)["goal"]` |
  | what each item is (optional) | `item_fields(dataset)`: `{"fieldset": <field set>, "values": {item_id: {field: value}}}` |
  | how big each dataset is (optional) | `dataset_items(dataset)`: its item count; without it the catalog shows the most items any arm scored |
  | words and places | `item_word` (e.g. `"episode"`), `data_dir` |
  | more files the pages link (optional) | `served_dirs`: further directories under the project the inspector serves read-only, beside `data_dir` (a project's reports) |
  | what each metric measures (optional) | `metric_descriptions()`: `{metric: sentence}` or `{metric: {"summary": sentence, "details": explanation}}`; without it the metrics page describes only the harness's own metrics |
  | what a row is scored against (optional keys) | `describe(arm)`: `"reference"`, `"judge"`, `"wrote_reference"`; `references()`: `"items"`, `"author"`, `"from_run"`, `"model"`, `"created_at"` |
  | what an arm was measured under (optional) | `conditions(arm)`: `{"machine.platform": …, "library.torch": …, "deployment.machine": …, "harness.version": …, "scorer.sha256": …, "data.items_sha256": …, "reference.sha256": …}` (`machine.*` and `library.*` are the runner, where `evh` ran; `deployment.*` is where the system under test ran; both come from the run's fingerprint, v5); the inspector lists what differs between the arms it compares, and warns when it is the scorer, the reference or, for latency, the machine |
  | dataset versions (optional) | `datasets()`: every dataset id, run or not; `dataset_lineage(dataset)`: `{"dataset_id", "added", "removed", "changed"}` or None; the dataset pages link versions both ways; `dataset_created(dataset)`: when it was frozen (ISO), the day the home page counts it new (else its first run) |
  | what is inside a dataset (optional) | `dataset_profile(dataset)`: the profile `evh dataset-profile` writes (`schemas/profile.schema.json`: `dataset_id`, `items_sha256`, `items`, `references`, `rows`, and `source` when known), plus `"stale": True` when the items changed since; the dataset page's "what's inside" shows it. The harness's own adapter reads `data/profiles/<dataset>.json` |
  | rounds: a config's arm id (optional) | `arm_of(dataset, config_id)`: `evh rounds` and `inspect --round` use it; `runs/<dataset>/<config_id>` when absent |
  | arm page: runs and details (optional) | `arm_runs(arm)`: `[{"run_id", "created_at", "items", "cost_usd", "derived"}]`; `arm_config(arm)`: `{"config_id", "params" (credentials removed), "adapter", "deployment" (the model-record deployment its config named, "" for none)}`; an arm page shows them when present |
  | spend in USD and tokens (optional) | `spend()`: `[{"at", "usd", "tokens", "kind": "arm"\|"judge", "dataset", "what", "arm"}]` (usd or tokens None when unknown; measured runs and judging per set and day; `arm`, optional, names a measured run's arm); the home page's spend, the activity page and the arms page's spend columns, and `evh overview` and `evh activity` use it |
  | what each model's weights are (optional) | `model_facts()`: `{model: {"weights": "open" \| "proprietary", "licence": …}}`, keyed by the model a run records (`params.model`); the arms page's open-weights and proprietary filters and `evh arms --weights` read it. The harness's own adapter reads the model records, `data/models/<model_id>.yaml` (`schemas/model.schema.json`, validate V1: `aliases` are the ids runs record, `weights`, `licence`, and `deployments`, each place the model runs with its own onboarding); a model not listed is in neither |
  | metrics that need no reference (optional) | `reference_free(metric)`: True when the metric is measured off the bill or the clock, so arms scored against different references can still be compared on it; when absent, a metric whose name contains cost, latency or tokens |
  | labels (optional, RFC-023) | `label_sets()`: every set, `{dataset, set, id, source, n_items, guideline, created_at, items}`; `label_coverage(dataset)`: the sets covering a dataset's items (by their sha256) and how often two agree; `item_labels(dataset, item)`: every label one item has, with its source; the Labels page, a dataset page's labels and the inspector's item view read them. `describe(arm)` may add `"labels_source"` (an arm scored against a label set) and `references()` `"promoted_from"`, `"reason"`, `"promoted_by"` |
  | production (optional, RFC-019, RFC-023) | `captures()`: every capture, as `evh captures` lists them (the Captures page); `dataset_meta(dataset)`: its tags and where it came from (a capture, or the version it was derived from); `describe(arm)["recorded"]`: the capture a recorded arm read production's decisions from; `same_output(arm)`: whether two outputs are one decision (the adapter's `same(a, b)`), for agreement and the sheet |
  | picks and the deploy sheet (optional, ADR-0023) | `picks_waiting(dataset)`: the picks naming a dataset as their target; `deploy_sheet(arm)`: what production must match to run a promoted arm, and what each capture says it ran |
  | the inspector's view kinds | `item_view` returns `{"kind": "text", "text"}`, `{"kind": "none", "note"}`, or a structured `insights` (`items` of `{text, grounded}`, `quotes`), `nodes` (`groups`) or `entities` (`items`); any may carry `info` |

  Every page and comparison is also a command that asks the same adapter the same questions:
  `evh datasets`, `evh references`, `evh metrics`, `evh goals`, `evh rounds`, `evh search` and
  `evh inspect --runs …` (`--analysis`, `--item`) and `evh inspect --sheet --dataset-id … --runs …` (with
  `--adapter` for a project adapter not named in `config.yaml`). The
  pages are a comfort; [tutorial 5](../../docs/tutorials/5-catalog-and-inspector.md#3-every-page-and-its-command)
  maps each page to its command.

  Item text is only ever returned by `item_view` and `reference_view`, and the static pages
  never carry it, whatever the adapter, but for what the repository already publishes (a profile
  written `evh dataset-profile --with-text`, refused unless git has committed every item's file). The local inspector shows all of it. A public deployment
  (`catalog-serve --public`) serves numbers, plus an arm's outputs or a reference's text only
  when it names them (`--publish outputs`, `--publish references`, or both), and never the item
  itself. An output can quote its input (an extractive arm returns the article's own sentences),
  and a reference can be text a project may not redistribute, so a public deployment publishes
  neither until it says so.

  A private deployment for a team behind its own proxy (a tailnet's Caddy, a VPN) is the local
  inspector, not a public one: `evh catalog-serve --behind-proxy HOST[,HOST] --bind 0.0.0.0` in a
  container serves the pages, the data tree and every item, output and reference, to requests
  whose Host is one it names (and to this machine's, for a health check), with no rate limit and
  nothing withheld. Everyone who can reach the proxy reads everything, so put it behind what
  already decides who that is. The data page's writes stay this machine's own and are not served
  through it.

  `item_fields` is optional: without it the pages show no fields. With it, the dataset page
  lists each field and its coverage, and summarises the values of a field marked `public`
  only; the local inspector shows every value, filters a comparison by a field and breaks it
  down by a `choice` or `boolean` one. A public deployment (`catalog-serve --public`) answers
  with public fields only (ADR-0003). To read a project's field set, use
  `from evaluation_harness.catalog_adapter import load_fieldset, fieldset_problems`, not the private `_fields`.

- **Observing a served inspector (optional): `--hooks`.** The harness reports to nothing and
  depends on no error tracker, tracer or metrics library. A deployment that wants them passes
  `evh catalog-serve --hooks path/to/hooks.py` (or `module`, either with `:NAME`), an object or
  module with any of:

  | part | called | with |
  |---|---|---|
  | `start(info)` | once, before serving | `{"bind", "port", "public", "version"}` |
  | `request(info)` | after each request | `{"method", "path", "route", "status", "ms"}`; `route` is the API endpoint, a hook route, or `static` |
  | `error(exc, info)` | when a request raised; it is then answered 500 | the exception, and `info` as for `request` |
  | `routes` | GET paths of the deployment's own, answered before the host check | `{path: fn(query) -> (status, content_type, body_bytes)}` |

  A hook that raises is printed to stderr and never breaks the request; without `--hooks`
  nothing changes. A hook route is answered to any Host: serve on it only what anyone who can
  reach the port may read (a `/metrics` behind a proxy that forwards only `/api/`). This
  repository's own deployment is an example: `infra/inspector/hooks.py` (Sentry, OpenTelemetry,
  `/metrics`), with its SDKs vendored by its deploy, not installed with the harness.

---

## For an agent: `evh mcp`

**An agent with a shell does not need it.** It runs `evh` as you do, reads every view, the
ranking and the paired tests with `--json`, and follows the `AGENTS.md` that `evh init` writes into the
project (the rules, the loop, what it may do: [CONCEPTS](CONCEPTS.md#an-agent-works-when-asked-a-person-owns-the-decision)).
`evh mcp` is for an agent that cannot run commands (a chat client, a hosted assistant) and for
a team sharing one project.

`evh mcp` serves the project's read commands to an agent over MCP (the official SDK): the
catalog's views (`overview`, `datasets`, `dataset-items`, `dataset-card`, `licences`, `arms`, `models`, `goals`,
`references`, `metrics`, `activity`, `search`, `captures`, `labels`, `tags`, `picks`, `label-coverage`,
`deploy-sheet`), the project's
files as the data page lists and shows them (`data-ls`, `data-show`), the inspector in the terminal (`inspect`, its
sheet included, without the options that write a file: `--csv`, `--fill` and theirs), the ranking
and the tests (`leaderboard`, `pair-test`, `family-test`, `rank-stability`, `run-compare`), `rounds`,
`runs-list` and `validate`: 28 tools. Each call runs the command as a person would, with `--json`,
so the agent sees the same numbers you do. No tool writes project data, spends or runs a model:
running arms, promoting a baseline and closing a round stay commands. (What a call does write is
computed answers in the project's ignored `.cache/`: the paired tests' p values and
`family-test`'s results.) The design is
[RFC-018](https://github.com/chipi/eval-harness/blob/main/docs/rfc/RFC-018-read-only-mcp-server.md).

**On your machine, against your project** (stdio: the agent starts it):

```bash
claude mcp add evh -- evh mcp          # Claude Code, in the project
```

Any other MCP client takes the command `evh mcp --project /absolute/path/to/project`. A desktop
client starts it from its own directory, not your project's, so give `--project`; and it starts it
with its own `PATH`, so if `evh` is in a virtualenv, give the full path to that `evh`.

**This repository's evals, from anywhere**: `https://evals.humancopilot.eu/mcp` serves the
six worked examples (Streamable HTTP, read-only, no sign-in; it answers what the site and the
catalog publish, never an item's text):

| client | how |
| --- | --- |
| Claude Code | `claude mcp add --transport http evals https://evals.humancopilot.eu/mcp` |
| Claude (claude.ai, Desktop), Pro or Max | Customize → Connectors → + Add → Add custom connector, the URL above, no authentication |
| Claude, Team or Enterprise | an owner: Organization settings → Connectors → Add → Custom → Web, the URL above; members then Connect it under Customize → Connectors |
| ChatGPT (Pro, Team, Enterprise, Edu) | Settings → Connectors → Advanced settings: turn on Developer mode; then Create, the URL above, no authentication; in a chat, + → More → Developer mode, and turn the connector on |
| OpenAI Responses API | `tools=[{"type": "mcp", "server_label": "evals", "server_url": "https://evals.humancopilot.eu/mcp", "require_approval": "never"}]` |
| Gemini CLI | `gemini mcp add --transport http evals https://evals.humancopilot.eu/mcp`, or in `~/.gemini/settings.json`: `{"mcpServers": {"evals": {"httpUrl": "https://evals.humancopilot.eu/mcp"}}}` |

The Claude, Gemini and OpenAI lines follow each vendor's own documentation (checked 2026-10-29);
the ChatGPT line follows third-party guides, as OpenAI renames that menu often. The server speaks
every protocol revision since 2025-03-26 without a session, which is what they send.

Ask it, for example: *"Which arm leads on the news_topic_ag goal, and is the lead significant?"* The
agent calls `goals` (and `arms` for the detail) and answers from the same table and paired test
the catalog shows.

**For a team**: serve a checkout of the project over HTTP behind the team's proxy:

```bash
evh mcp --http --bind 0.0.0.0 --port 8766 --allowed-host evals.team.example [--public]
```

`--allowed-host` is required beyond the loopback (the server checks the Host against DNS
rebinding); `--public` leaves out the options that answer with an item's text (an item, the sheet), and the
`validate`, `data-ls` and `data-show` tools (25 tools), and the options that set how long a test runs (`--permutations`, `--draws`); `--rate` (per
caller), `--rate-total` (everyone together), `--concurrent` and `--timeout` bound the load, and a
caller has one call running at a time; `--client-header` names the header your proxy sets for the
caller's address (trust it only if nothing else can reach the port); `--hooks FILE` adds your error reporting, tracing
and metrics. It has no accounts: put it behind what the team already uses (a VPN, an
authenticating proxy). The goals' tests are kept in the project's `.cache/` so a call that shows
them answers in seconds after the first.

---

## The first hour, concretely

```bash
cd your-project && python3 -m venv .venv && . .venv/bin/activate
pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.7.2#subdirectory=harness"
evh init                                      # folders, .gitignore, AGENTS.md for an agent
export EVAL_MAX_COST_USD=2                    # a run stops when it has spent this; with none, no cap

cp some/real/items/* data/sources/            # your data
evh dataset-create --dataset-id pilot_v1 --limit 10
evh dataset-materialize --dataset-id pilot_v1
evh dataset-profile --dataset-id pilot_v1              # what is inside, for its catalog page

$EDITOR adapter.py                            # call_system() -> your code
git add -A && git commit -m "pilot_v1, adapter, arms"   # a run from a dirty tree cannot become a reference
evh run --config data/configs/best_model.yaml
evh label-from-run --run <that run_id> --set best_v1
evh reference-promote --dataset-id pilot_v1 --labels best_v1 --tier silver --reason "…" --by <you>
git add data/labels data/references && git commit -m "pilot_v1: silver, best_model's labels"

evh run --config data/configs/arm_a.yaml --repeat 3   # + the noise floor
evh run --config data/configs/arm_b.yaml
evh run-compare --baseline <a> --candidate <b> --noise <the spread you just measured>
```

Ten items keeps the first pass cheap. Widen the dataset once the loop works —
and widen it *before* you trust any ranking, because ten items is a smoke test,
not evidence.

New to the loop? [Getting started](../../docs/GUIDE.md) walks it once, offline, and the
[tutorials](../../docs/GUIDE.md#where-to-go-next) take it to a local model, a hosted LLM, a
frontier reference and judges, rounds, and the catalog. Then read [`RUNBOOK.md`](RUNBOOK.md) for
every command and flag, and [`CONCEPTS.md`](CONCEPTS.md) for why the refusals exist.
