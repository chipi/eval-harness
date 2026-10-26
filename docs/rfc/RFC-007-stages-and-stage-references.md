# RFC-007: Stages, stage references, structured outputs, item fields, batch mode, wrapping a runner

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-008](../prd/PRD-008-pipelines-and-any-language.md) (FR1, FR2, FR3, FR5, FR6)
- **Related RFCs**: RFC-008 (the process protocol carries the same result), RFC-013 (`--json`, schemas),
  [RFC-002](RFC-002-run-records-and-derived-runs.md) (run records), [RFC-006](RFC-006-item-fields-and-url-items.md)
  (item fields)
- **Code**: `harness/scripts/adapter.py` (`Result`, new `Stage`, `Item`), `experiment_run.py` (`one_pass`), new
  `_stages.py`, `import_run.py` (`--otlp`), `catalog_views.py` and `inspect.js` (the stage view), `validate_tree.py`,
  `schemas/prediction.schema.json`, `harness/docs/INTEGRATION.md`, `harness/examples/wrapping/`

## Abstract

A result may carry **stages**, each shaped like an OpenTelemetry GenAI span (name, id, parent, times, output, token
and model attributes) with the harness's own cost field. Stage outputs are stored beside the end output; stage scores
become ordinary metrics named `<stage>.<metric>`, scored against a stage's own reference when the reference holds one.
Outputs may be JSON. An adapter may ask for the whole item (its fields) instead of its text, and may run a **batch**
of items at once. A recipe and an example show how to wrap an existing runner. Nothing changes for a 0.4.0 adapter.

## Problem Statement

- `one_pass` (`experiment_run.py:250-345`) calls `call_system(text, params)` per item, writes the output as
  `<item_id>.txt`, reads the reference `<item_id>.txt`, scores, and writes a row; resume reads the `.txt` back. There is
  no place for intermediate outputs (they end up in `_meta`, unshaped), no stage reference, no JSON output, no item
  fields, and no way to run a pipeline that works on a whole feed.

## Design

### Stages (`adapter.Stage`)

```python
@dataclass
class Stage:
    name: str                      # "asr", "summary", "insights" (grammar segment)
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

`Result` gains `stages: list[Stage] = []`; its `output` stays the end result. `_stages.SEMCONV` names the version of the
OpenTelemetry GenAI conventions the attribute names follow (a commit of
`open-telemetry/semantic-conventions-genai`, updated deliberately), and every run records it.

### Records

- **Outputs**: the end output is `outputs/<item_id>.txt` (text) or `outputs/<item_id>.json` (JSON); the stages are
  `outputs/<item_id>.stages.json` (a list of the stage records, outputs included), each written atomically, as today.
- **The prediction row** gains `_stages`: per stage, the record without its output (`name, id, parent, start_ms,
  end_ms, input_tokens, output_tokens, request_model, response_model, cost_usd`), and metrics `<stage>.latency_ms`,
  `<stage>.cost_usd`, `<stage>.tokens_in`, `<stage>.tokens_out` (when known) beside the stage's scores. The run's
  `cost_usd` and `latency_ms` are the sums over stages unless the result sets them.
- **Resume** reads `.txt` or `.json` and `.stages.json` back exactly (a replayed item carries its stages' costs, as
  today it carries its own).
- `schemas/prediction.schema.json` describes the row, stages included.

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

- An adapter declares how it is called: `CALL_FORM = "text"` (default, 0.4.0: `call_system(text, params)`) or `"item"`
  (`call_system(item: Item, params)`, `Item(id, text, fields)`, the fields RFC-006 declares).
- `BATCH = True` with `call_batch(items: list[Item], params) -> dict[str, Result]` (keyed by item id): the harness passes
  batches of `params.get("batch_size")` items (default: the whole dataset), in dataset order. A missing item id in the
  returned mapping fails that item (recorded, not skipped). Retries apply to the batch.
- **Cost cap with batches**: before a batch, the estimate is the mean cost per item of the batches so far times the batch
  size (none before the first batch); a batch never starts when the estimate would pass the cap; the first batch starts
  only when `--dry-run`'s estimate (from the config's prices) is under the cap, or no cap is set.
- **Resume per batch**: items with outputs on disk are left out of the next batch.

### Wrapping a runner (PRD-008 FR5)

`harness/docs/INTEGRATION.md` gains "Wrapping a runner you already have", and `harness/examples/wrapping/` an adapter that runs
an existing script as a batch (a subprocess writing per-item outputs and stage files into a directory the harness
names), reads them back as `Result`s with stages, and, where the system needs it, points the system at the prompt
overlay (RFC-009). It also shows declaring the system's code ref (PRD-008 FR4.4) through the adapter's
`fingerprint(params)` hook: `{"code_ref": {"repo": …, "commit": …}}`.

### Importing traces (PRD-008 FR1.7)

`evh import-run --otlp FILE.json …` reads OTLP JSON: spans with the attribute `evh.item_id` group into items; each span
becomes a stage (names from `gen_ai.*` where present); `gen_ai.evaluation.result` events become stage scores
(`gen_ai.evaluation.name` → the metric, `gen_ai.evaluation.score.value` → the value). The rest of `import-run` is
unchanged.

### The stage view

The inspector's item panel shows the stages of each arm side by side (name, output, time, cost, tokens, scores), a stage
row highlighted where two arms' stage scores differ most; `evh inspect --stages --item ID [--json]` prints the same.

### Validation

`validate` notes a run whose items do not all have the same stage names, and refuses a stage metric whose stage the run
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
  fields; a batch adapter matches the per-item adapter's results; the cap stops before a batch; an OTLP file imports.
- Inspector browser check: the stage panel for two arms.

## Decisions (ADR candidates)

1. Stages are span-shaped records on the result (OpenTelemetry GenAI names, a pinned conventions version, the harness's
   own cost field), stored beside outputs; stage scores are ordinary metrics named `<stage>.<metric>`.
2. A reference may hold per-stage references, inside the reference digest.
3. Adapters declare their call form (text, item) and whether they batch; 0.4.0 adapters are unchanged.
