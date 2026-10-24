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
def call_system(text: str, params: Dict[str, Any]) -> Result:
    from myproject.summarise import summarise          # your existing code
    out = summarise(text, model=params["model"], temperature=params["temperature"])
    return Result(output=out.text,
                  tokens_in=out.usage.prompt_tokens,
                  tokens_out=out.usage.completion_tokens)
```

That is the integration. Everything else — freezing the dataset, hashing it,
recording which build ran, timing the call, aggregating, refusing bad
comparisons — is generic and already written.

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
def score(output: str, reference: Optional[str]) -> Dict[str, float]:
    return {"rouge_l": rouge_l(output, reference),
            "has_required_section": 1.0 if "Summary:" in output else 0.0}
```

It is called with `reference=None` when no ground truth exists yet, so the same
adapter works before and after you have references.

**The shipped default is a placeholder.** Token-overlap F1 — enough to make the
loop run and rank arms crudely, not enough to defend a decision. Replace it
with what your domain actually rewards.

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
record the prices it was costed at.

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
| integrity | `make validate` fails CI on a tree that has drifted |
| re-measurement | stored outputs scored again for a new reference or scorer at $0, or by validated LLM judges, without re-running an arm |
| a judge panel | when the cheap metric is biased and you need an LLM to adjudicate |
| goals | what each evaluation is for, named on every config and checked by `make validate` |
| item fields | the facts you know about each item (typed, declared once in a field set), checked by `make validate`; items fetched from a pinned URL |
| a catalog and an inspector | pages over your runs, and a local server that tests any arms against a baseline and shows outputs beside references |

---

## The catalog and the inspector

`make catalog` (`evh catalog`) builds static pages over your runs; `make catalog-serve`
(`evh catalog-serve`) serves them with the run inspector on 127.0.0.1. Both only ask an
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
  | which way is better | `lower_is_better(metric)`, `is_neutral(metric)`, `preferred_metrics`, `shape_metrics` |
  | which references | `references()`, `reference_format(ref)`, `reference_archived(ref)` |
  | what was asked, what came back | `output_format(arm)` |
  | one item, side by side (the inspector only) | `item_view(arm, item)`, `reference_view(ref, item)` |
  | what it is for | `goals()`; the goal an arm names is `describe(arm)["goal"]` |
  | what each item is (optional) | `item_fields(dataset)`: `{"fieldset": <field set>, "values": {item_id: {field: value}}}` |
  | how big each dataset is (optional) | `dataset_items(dataset)`: its item count; without it the catalog shows the most items any arm scored |
  | words and places | `item_word` (e.g. `"episode"`), `data_dir` |
  | more files the pages link (optional) | `served_dirs`: further directories under the project the inspector serves read-only, beside `data_dir` (a project's reports) |

  Item text is only ever returned by `item_view` and `reference_view`, which only the local
  inspector calls: the static pages never carry it, whatever the adapter.

  `item_fields` is optional: without it the pages show no fields. With it, the dataset page
  lists each field and its coverage, and summarises the values of a field marked `public`
  only; the local inspector shows every value, filters a comparison by a field and breaks it
  down by a `choice` or `boolean` one. A public deployment (`catalog-serve --public`) answers
  with public fields only (ADR-0003).

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

Then read [`RUNBOOK.md`](RUNBOOK.md) for the day-to-day, and
[`CONCEPTS.md`](CONCEPTS.md) for why the refusals exist.
