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
pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.4.0#subdirectory=harness"
evh init         # data/sources, data/configs, data/goals, data/fields, a .gitignore
```

That one install is everything: the hosted-model clients (`openai`, `anthropic`), the judges, the
catalog and the inspector. There is no extra to add.

Keep `data/materialized/` out of git (derived; the `.gitignore` `evh init` writes already
does this) and decide whether to commit runs: keep each run's `metrics.json`,
`predictions.jsonl` and `outputs/` so scores can be recomputed. A project whose own layout
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
adapter works before and after you have references.

**The shipped default is a placeholder.** Token-overlap F1 — enough to make the
loop run and rank arms crudely, not enough to defend a decision. Replace it
with what your domain actually rewards.

Beside `score()`, say what your metrics are: `PRIMARY_METRIC` (the one that decides),
`METRIC_DIRECTIONS` (a quality metric that improves going down, `{"wer": "lower"}`) and
`METRIC_DESCRIPTIONS` (one sentence each, `{"rouge_l": "ROUGE-L F1 against the reference"}`).
Every run records them; the catalog's metrics page shows the descriptions. Added later, they
reach existing runs through `evh rescore`, for $0.

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
for, `data/goals/<goal_id>.yaml`), `round` (an experiment round of that goal, `rN`) and
`format` (the output's shape, one of its goal's `output_contract` formats:
[RUNBOOK §4c](RUNBOOK.md#4c-the-goal-file-field-by-field)). Any other key is refused by
`evh validate` (V1).

---

## Hosted models: you choose the provider, and bring your own key

`provider: anthropic` above is one choice. The bundled adapter, and any adapter of yours that
dispatches to its `PROVIDERS` (`from evaluation_harness.adapter import PROVIDERS, Result`), also
call OpenAI or any OpenAI-compatible endpoint (`provider: openai` with a `base_url`), OpenRouter
(`provider: openrouter`), and a LiteLLM proxy (`provider: litellm`). Each reads its key from the
environment or the project's `.env` (gitignored by `evh init`); the harness holds none.
**Which variable each provider reads, and what goes in the arm's `params`:
[tutorial 2](../../docs/tutorials/2-hosted-llm.md#1-choose-a-provider).** `evh env-check`
reports which are set. LLM judges route the same way: through a LiteLLM proxy, or straight to
OpenRouter with `OPENROUTER_API_KEY` ([RUNBOOK §12](RUNBOOK.md#12-re-measure-with-a-validated-judge)).

---

## Getting ground truth when you have none

Most projects do not have it. The sequence that works:

1. **Run your best model as an arm**, usually an expensive one you would not run in
   production, read its results, and make its outputs the reference:
   ```bash
   evh experiment-run --config data/configs/frontier.yaml
   evh reference-create --dataset-id my_v1 --from-run <that run_id>
   ```
   That writes **silver** — model-generated. It is not correct, it is
   *consistent*, which is enough to rank other arms against it: the cheaper arms are measured
   by how close they come to the expensive one. It calls nothing, and the reference names the
   run it came from. (`--config data/configs/frontier.yaml` instead of `--from-run` authors it
   in a pass of its own.)

2. **Review a few by hand.** Where you agree with the output, you now have gold: copy the
   items you would sign into `data/references/gold/<dataset_id>/<item_id>.txt`. Gold outranks
   silver for every new run; `evh rescore --reference-id gold/<dataset_id>` re-scores the runs
   you have, for $0.

3. **Never let the distinction blur.** A run records which tier it scored
   against (`reference_tier` in its `metrics.json`). Silver-scored numbers are for
   ranking arms against each other; they are not a claim about correctness, and
   publishing them as one is how eval loses credibility internally.

Cost control: `--limit 10`. Ten references is enough to rank four arms, and you
can extend later without re-authoring what you have.

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
| experiment rounds (optional) | round on round: what each round tried, what it kept and dropped and why, what it concluded ([tutorial 4](../../docs/tutorials/4-rounds-and-versions.md)) |
| item fields | the facts you know about each item (typed, declared once in a field set), checked by `evh validate`; items fetched from a pinned URL |
| a catalog and an inspector | pages over your runs, and a local server that tests any arms against a baseline and shows outputs beside references; every view is also an `evh` command |

---

## The catalog and the inspector

`evh catalog` builds static pages over your runs: one per dataset and per goal,
one per reference (who wrote it, from which run, every arm scored against it), and a metrics page
(what each metric measures, which way is better, where it is recorded). Every arm's row says what
it is scored against, and rows scored against silver, scored by a judge, or scored against the
reference the arm wrote itself are tinted apart from those scored against gold.
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
  | what each scored, per item | `scores(arm, rescore=False)`, `recorded_means(arm)`, `input_hashes(arm)`, `can_rescore` |
  | which way is better | `lower_is_better(metric, dataset)`, `is_neutral(metric)`, `preferred_metrics`, `shape_metrics` |
  | which references | `references()`, `reference_format(ref)`, `reference_archived(ref)` |
  | what was asked, what came back | `output_format(arm)` |
  | one item, side by side (the inspector only) | `item_view(arm, item)`, `reference_view(ref, item)` |
  | what it is for | `goals()`; the goal an arm names is `describe(arm)["goal"]` |
  | what each item is (optional) | `item_fields(dataset)`: `{"fieldset": <field set>, "values": {item_id: {field: value}}}` |
  | how big each dataset is (optional) | `dataset_items(dataset)`: its item count; without it the catalog shows the most items any arm scored |
  | words and places | `item_word` (e.g. `"episode"`), `data_dir` |
  | more files the pages link (optional) | `served_dirs`: further directories under the project the inspector serves read-only, beside `data_dir` (a project's reports) |
  | what each metric measures (optional) | `metric_descriptions()`: `{metric: sentence}`; without it the metrics page describes only the harness's own metrics |
  | what a row is scored against (optional keys) | `describe(arm)`: `"reference"`, `"judge"`, `"wrote_reference"`; `references()`: `"items"`, `"author"`, `"from_run"`, `"model"`, `"created_at"` |
  | what an arm was measured under (optional) | `conditions(arm)`: `{"machine.platform": …, "library.torch": …, "harness.version": …, "scorer.sha256": …, "data.items_sha256": …, "reference.sha256": …}`; the inspector lists what differs between the arms it compares, and warns when it is the scorer, the reference or, for latency, the machine |
  | dataset versions (optional) | `datasets()`: every dataset id, run or not; `dataset_lineage(dataset)`: `{"dataset_id", "added", "removed", "changed"}` or None; the dataset pages link versions both ways |
  | rounds: a config's arm id (optional) | `arm_of(dataset, config_id)`: `evh rounds` and `inspect --round` use it; `runs/<dataset>/<config_id>` when absent |
  | metrics that need no reference (optional) | `reference_free(metric)`: True when the metric is measured off the bill or the clock, so arms scored against different references can still be compared on it; when absent, a metric whose name contains cost, latency or tokens |
  | the inspector's view kinds | `item_view` returns `{"kind": "text", "text"}`, `{"kind": "none", "note"}`, or a structured `insights` (`items` of `{text, grounded}`, `quotes`), `nodes` (`groups`) or `entities` (`items`); any may carry `info` |

  Every page and comparison is also a command that asks the same adapter the same questions:
  `evh datasets`, `evh references`, `evh metrics`, `evh goals`, `evh rounds`, `evh search` and
  `evh inspect --runs …` (`--items`, `--analysis`, `--item`; with `--adapter` for a project
  adapter not named in `config.yaml`). The
  pages are a comfort; [tutorial 5](../../docs/tutorials/5-catalog-and-inspector.md#3-every-page-and-its-command)
  maps each page to its command.

  Item text is only ever returned by `item_view` and `reference_view`, and the static pages
  never carry it, whatever the adapter. The local inspector shows all of it. A public deployment
  (`catalog-serve --public`) serves numbers, plus an arm's outputs or a reference's text only
  when it names them (`--publish outputs`, `--publish references`, or both), and never the item
  itself. An output can quote its input (an extractive arm returns the article's own sentences),
  and a reference can be text a project may not redistribute, so a public deployment publishes
  neither until it says so.

  `item_fields` is optional: without it the pages show no fields. With it, the dataset page
  lists each field and its coverage, and summarises the values of a field marked `public`
  only; the local inspector shows every value, filters a comparison by a field and breaks it
  down by a `choice` or `boolean` one. A public deployment (`catalog-serve --public`) answers
  with public fields only (ADR-0003). To read a project's field set, use
  `from evaluation_harness.catalog_adapter import load_fieldset, fieldset_problems`, not the private `_fields`.

---

## The first hour, concretely

```bash
cd your-project && pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.4.0#subdirectory=harness"
evh init

cp some/real/items/* data/sources/            # your data
evh dataset-create --dataset-id pilot_v1 --limit 10
evh dataset-materialize --dataset-id pilot_v1

$EDITOR adapter.py                            # call_system() -> your code
git add -A && git commit -m "pilot_v1, adapter, arms"   # a run from a dirty tree cannot become a reference
evh experiment-run --config data/configs/best_model.yaml
evh reference-create --dataset-id pilot_v1 --from-run <that run_id>
git add data/references && git commit -m "pilot_v1: silver from best_model"

evh experiment-run --config data/configs/arm_a.yaml --repeat 3   # + the noise floor
evh experiment-run --config data/configs/arm_b.yaml
evh run-compare --baseline <a> --candidate <b> --noise <the spread you just measured>
```

Ten items keeps the first pass cheap. Widen the dataset once the loop works —
and widen it *before* you trust any ranking, because ten items is a smoke test,
not evidence.

New to the loop? [Getting started](../../docs/GUIDE.md) walks it once, offline, and the
[tutorials](../../docs/GUIDE.md#where-to-go-next) take it to a local model, a hosted LLM, a
frontier reference and judges, rounds, and the catalog. Then read [`RUNBOOK.md`](RUNBOOK.md) for
every command and flag, and [`CONCEPTS.md`](CONCEPTS.md) for why the refusals exist.
