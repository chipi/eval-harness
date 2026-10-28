# RFC-007: Stages, stage references, structured outputs, item fields, batch mode, wrapping a runner

- **Status**: Draft (0.5.0), revision 2 (2026-10-27): OTLP import only; export is deferred
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-008](../prd/PRD-008-pipelines-and-any-language.md) (FR1, FR2, FR3, FR5, FR6)
- **Related RFCs**: RFC-008 (the process protocol carries the same result), RFC-013 (`--json`, schemas),
  [RFC-002](RFC-002-run-records-and-derived-runs.md) (run records), [RFC-006](RFC-006-item-fields-and-url-items.md)
  (item fields)
- **Code**: `harness/scripts/adapter.py` (`Result`, new `Stage`, `Item`), `experiment_run.py` (`one_pass`, `_Resumed`,
  the reference coverage check), new `_stages.py` and `_outputs.py` (one reader for an item's output, `.txt` or
  `.json`), `import_run.py` (`--otlp`), `catalog_views.py` and `inspect.js` (the stage view),
  `validate_tree.py`; every reader of `outputs/<item>.txt` or `<ref>/<item>.txt` moves to `_outputs.py`: `rescore.py`,
  `judge_score.py`, `_references.py`, `reference_create.py`, `silver_calibrate.py`, `catalog_adapter.py`,
  `validate_tree.py`, and 0.4.2's `_common.reference_texts` with its users (`_labels.py`, hence `bootstrap-test`;
  `harness/tools/extraction_report.py`, `retrieval_report.py`), keeping their refusal when a reference directory
  holds only its `manifest.json`; `catalog_arms.py` (the arms page's model column);
  `schemas/prediction.schema.json`, `harness/docs/INTEGRATION.md`, `harness/examples/wrapping/`

## Abstract

A result may carry **stages**, each shaped like an OpenTelemetry GenAI span (name, id, parent, times, output, token
and model attributes) with the harness's own cost field. Stage outputs are stored beside the end output; stage scores
become ordinary metrics named `<stage>.<metric>`, scored against a stage's own reference when the reference holds one.
Outputs may be JSON. An adapter may ask for the whole item (its fields) instead of its text, and may run a **batch**
of items at once. A recipe and an example show how to wrap an existing runner. Nothing changes for a 0.4.x adapter.

## Problem Statement

- `one_pass` (`experiment_run.py:202-403`) calls `call_system(text, params)` per item, writes the output as
  `<item_id>.txt`, reads the reference `<item_id>.txt`, scores, and writes a row; resume takes the presence of the `.txt`
  as "done" (`:259-260`) and reads it back. There is no place for intermediate outputs (they end up in `_meta`,
  unshaped), no stage reference, no JSON output, no item fields, and no way to run a pipeline that works on a whole feed.
- An item cannot fail on its own: once `call_with_retries` gives up, the exception stops the whole run
  (`experiment_run.py:280-285`, `:749-751`). A pipeline that fails on one feed loses every feed.
- Seven other modules read `outputs/<item>.txt` or `<ref>/<item>.txt` directly (listed under Code); `rescore` copies
  `*.txt` only (`rescore.py:390`). Since 0.4.2, `_common.reference_texts` lists a reference's items as
  `root.glob("*.txt")`: with stage references named `<item_id>.<stage>.txt` it would read `<item>.asr` as an item id,
  and it never finds a `.json` reference.

## Design

### Stages (`adapter.Stage`)

```python
@dataclass
class Stage:
    name: str                      # "asr", "summary", "insights": [a-z0-9_-]+, no "." (see below)
    output: str | dict | list      # text or JSON
    id: str | None = None          # span id; default f"{name}" (or name#k when repeated)
    parent: str | None = None      # parent span id: a nested pipeline recorded faithfully, never traversed
    start_ms: float | None = None
    end_ms: float | None = None
    input_tokens: int | None = None        # gen_ai.usage.input_tokens
    output_tokens: int | None = None       # gen_ai.usage.output_tokens
    request_model: str | None = None       # gen_ai.request.model
    response_model: str | None = None      # gen_ai.response.model
    provider: str | None = None            # gen_ai.provider.name
    operation: str | None = None           # gen_ai.operation.name
    cost_usd: float | None = None          # the harness's own: the conventions define no cost
    extra: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
```

`Result` gains `stages: list[Stage] = []`; its `output` stays the end result. A stage name matches `[a-z0-9_-]+`: no
`.`, so `<stage>.<metric>` splits at its first `.` without ambiguity, and the names `judge` and `harness` are reserved
(the harness's own metrics, RFC-010). `_stages.SEMCONV` names the version of the
OpenTelemetry GenAI conventions the attribute names follow (a commit of
`open-telemetry/semantic-conventions-genai`, updated deliberately), and every run records it.

### Records

- **Outputs**: the end output is `outputs/<item_id>.txt` (text) or `outputs/<item_id>.json` (JSON); the stages are
  `outputs/<item_id>.stages.json` (a list of the stage records, outputs included). Each file is written atomically, and
  in this order: the stages first, the end output last. The end output is the commit marker: resume treats an item as
  done only when its `.txt` or `.json` exists, so a crash between the two files re-runs the item instead of resuming it
  without its stages.
- **The prediction row** gains `_stages`: per stage, the record without its output (`name, id, parent, start_ms,
  end_ms, input_tokens, output_tokens, request_model, response_model, cost_usd`), and metrics `<stage>.latency_ms`,
  `<stage>.cost_usd`, `<stage>.tokens_in`, `<stage>.tokens_out` (when known) beside the stage's scores. The run's
  `cost_usd` and `latency_ms` are the sums over stages unless the result sets them.
- **Resume** reads `.txt` or `.json` and `.stages.json` back exactly; `_Resumed` carries the stages, the stage metrics
  (`<stage>.latency_ms`, cost, tokens) are recomputed from `.stages.json`, and the stages are re-scored as the end
  output is (a replayed item carries its stages' costs, as today it carries its own).
- **Rescore and judging** read and copy outputs through `_outputs.py`, so `.json` outputs and `.stages.json` survive a
  rescore and stage scores are recomputed, not dropped.
- `schemas/prediction.schema.json` describes the row, stages included.

### Item failures

An item can fail without stopping the run: when retries are exhausted, or a batch result lacks the item, or a process
adapter returns a non-transient error (RFC-008), the item gets a row `{"item_id": …, "_failed": {"reason": …,
"transient": bool, "attempts": n}}` and no output file. Failed items are left out of every mean and every paired test
(the pair needs both arms), and `metrics.json` records `n_failed` beside `n`. `experiment-run` exits 0 when at least one
item was measured (the count is printed and recorded), 7 when none was, and 75 when none was and the last failure was
transient (RFC-013's table). `--resume` retries failed items. `run-promote` refuses a run with failed items unless
`--allow-failed` and a reason; the catalog shows the count on the run.

### Scoring stages

- An adapter may define `score_stage(stage, output, reference, source) -> dict` (or `STAGE_SCORERS = {"asr": f, …}`);
  the harness calls it for each stage with that stage's reference (below) and records each key as `<stage>.<key>`.
  `score(output, reference[, source])` scores the end result as today.
- Directions and descriptions for stage metrics are declared under their full names
  (`METRIC_DIRECTIONS = {"asr.wer": "lower"}`).
- Every command that takes `--metric` takes `asr.wer`; a goal may decide on one.

### Stage references

- A reference directory holds `<item_id>.txt` (or `.json`) for the end result and `<item_id>.<stage>.txt` (or `.json`)
  for a stage; its manifest lists `stages: [asr, summary]`. The reference digest already covers every file in the
  directory (RFC-001), so stage references are part of a run's identity.
- `reference-create --from-run` copies a run's stage outputs too, when asked (`--stages asr,summary`).
- A stage without a reference can still be measured by metrics that need none (cost, time, length, a judge without a
  reference).

### Structured outputs

`Result.output` and `Stage.output` may be `dict` or `list`; scorers receive them parsed; the inspector shows them as
formatted JSON and diffs them field by field; a judge receives them serialised (`json.dumps(…, indent=2,
sort_keys=True)`).

### Item fields and batch mode

- An adapter declares how it is called: `CALL_FORM = "text"` (default, as in 0.4.x: `call_system(text, params)`) or `"item"`
  (`call_system(item: Item, params)`, `Item(id, text, fields)`, the fields RFC-006 declares).
- `BATCH = True` with `call_batch(items: list[Item], params) -> dict[str, Result]` (keyed by item id). The batch unit is
  `BATCH_KEY` (an item field, such as `feed`: one batch per distinct value, in dataset order) or `params["batch_size"]`
  items; the default is one item, so a batch adapter never risks the whole dataset by default. The harness writes each
  returned item's files as soon as the batch returns, so a crash loses at most the batch in flight. A missing item id in
  the returned mapping fails that item (an item failure, above). A transient failure of the whole batch is retried; a
  retry sends only the items still without an output.
- **Times and costs in a batch**: an item's `latency_ms` and `cost_usd` are what the adapter reports for it (PRD-008
  FR3.3, "as the adapter reports"); when it reports none, the harness records the batch's wall time and cost on the
  batch (`_batch: {id, items, latency_ms, cost_usd}` on each row) and leaves the item's own fields empty, never an even
  split it did not measure. Means of latency then use only items with their own; the catalog says how many.
- **Cost cap with batches**: the adapter may define `estimate(items, params) -> {"cost_usd": float}`; before each batch
  the estimate is that, or else the mean cost per item of the batches so far times the batch size. A batch never starts
  when the estimate would pass the cap. Under a cap, the first batch of an adapter with no `estimate` and no prices in the
  config is refused with the reason (`no-estimate`), not started blind.
- **Resume per batch**: items with outputs on disk are left out of the next batch.

### Wrapping a runner (PRD-008 FR5)

`harness/docs/INTEGRATION.md` gains "Wrapping a runner you already have", and `harness/examples/wrapping/` an adapter that runs
an existing script as a batch (a subprocess writing per-item outputs and stage files into a directory the harness
names), reads them back as `Result`s with stages, and, where the system needs it, points the system at the prompt
overlay (RFC-009). It also shows declaring the system's code ref (PRD-008 FR4.4) through the adapter's
`fingerprint(params)` hook: `{"code_ref": {"repo": …, "commit": …}}`.

### Importing traces (PRD-008 FR1.7)

- `evh import-run --otlp-traces FILE.json [--otlp-logs FILE.json] --dataset-id D --config-id C --source S` reads OTLP
  JSON. Spans with the attribute `evh.item_id` group into items; each span becomes a stage (names from `gen_ai.*` where
  present); the root span's output, when recorded, is the end output. `gen_ai.evaluation.result` is an event in the logs
  data model, parented to a span, not a span attribute, so evaluation results come from the logs file, joined to stages
  on span id (`gen_ai.evaluation.name` → the metric, `gen_ai.evaluation.score.value` → the value).
- With `--otlp-*`, `--scores` is not needed (the scores come from the logs), and `--primary-metric` and `--scorer-id` are
  required only when the logs carry scores; the scorer id defaults to `otlp:<the events' evaluator name>`. Without
  `--otlp-*`, `import-run` is unchanged.
- Exporting a run's stages and stage scores as OTLP (so a tracing tool can show them) is deferred (revision 2): the
  stage records already use the OpenTelemetry GenAI names, so an exporter can be added later without changing them.

### The stage view

The inspector's item panel shows the stages of each arm side by side (name, output, time, cost, tokens, scores), a stage
row highlighted where two arms' stage scores differ most; `evh inspect --stages --item ID [--json]` prints the same.
The stages come in `/api/item`'s answer (no new API route); a public server withholds their outputs unless
`--publish outputs`, as it does an arm's output.

### On the arms page

0.4.2's arms page reads one model per arm from `params.model` and `params.provider` (`catalog_arms.py`), and
`data/models.yaml` is keyed by that model. An arm with stages lists each stage's `request_model` in **model ·
provider**; it is hosted when any stage's provider bills per call, and its weights are open only when every stage's
model is listed open in `models.yaml`.

### Validation

`validate` notes a run whose items do not all have the same stage names, and refuses a stage metric (other than the
reserved `judge.` and `harness.` prefixes) whose stage the run
lacks; every row validates against `prediction.schema.json`.

## Migration

None: a run without stages has no new fields.

## Alternatives Considered

- **Stages as a graph the harness schedules.** Rejected (PRD-008 Non-Goals): the project runs its pipeline.
- **A flat ordered list without span shape.** Rejected after the industry review: traces from other tools would not map,
  and a nested pipeline could not be recorded faithfully.
- **Stage outputs inline in the prediction row.** Rejected: outputs can be large; rows stay small and outputs live in
  `outputs/`, as the end output does.
- **Inventing cost attribute names in the gen_ai namespace.** Rejected: the conventions define none; `cost_usd` is the
  harness's own.

## Testing

- `harness/tests/test_stages.py`: a three-stage example adapter (one stage with a reference, one calling a fake provider)
  records stages, stage metrics, sums; resume restores stages exactly; `pair-test --metric summary.rouge_l` works; a
  missing stage reference leaves reference-free stage metrics; JSON outputs round-trip; `CALL_FORM="item"` receives
  fields; a batch adapter matches the per-item adapter's results; the cap stops before a batch and refuses a first
  batch with no estimate; a crash between the stage file and the end output re-runs the item on resume; resume restores
  stage metrics; rescore keeps `.json` outputs and stages; an item that fails is recorded and the run goes on; a stage
  name with `.` is refused; OTLP traces and logs import.
- Inspector browser check: the stage panel for two arms.

## Decisions (ADR candidates)

1. Stages are span-shaped records on the result (OpenTelemetry GenAI names, a pinned conventions version, the harness's
   own cost field), stored beside outputs; stage scores are ordinary metrics named `<stage>.<metric>`.
2. A reference may hold per-stage references, inside the reference digest.
3. Adapters declare their call form (text, item) and whether they batch (by a key field, default one item); 0.4.x
   adapters are unchanged.
4. An item can fail without stopping the run; failed items are recorded, counted and left out of means and tests.
5. The end output file is written last and is the commit marker for resume.
