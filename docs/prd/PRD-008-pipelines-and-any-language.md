# PRD-008: Pipelines, stages, and systems in any language

- **Status**: Draft (0.5.0), round 3
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-002](../uxs/UXS-002-inspector.md) (the inspector, to gain a stage view)
- **Related RFCs**: RFC-007 (stages and stage references), RFC-008 (the process protocol), both
  to be written
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md),
  [PRD-007](PRD-007-packaging-and-providers.md) (the adapter seam),
  [PRD-012](PRD-012-agent-ready.md) (every capability for people and agents alike)

## Summary

A system under test is often a **pipeline**: the project's own code calling third parties (a
transcription service, an LLM, a vector store) stage by stage, where what matters is the
**compound** result and where it went wrong. Today the harness sees one input string and one
output string per item. This PRD lets a result carry **stages**, shaped like the spans every
tracing tool uses (OpenTelemetry's GenAI conventions), each with its output, cost, tokens and
time; lets a stage be scored against its **own reference**; and makes every stage measure an
ordinary metric (`asr.wer`), so the tests, goals and the catalog work per stage unchanged. It
adds a **batch** mode for pipelines that process a whole dataset at once, and opens the seam to
systems **not written in Python**: a long-lived process that speaks JSON-RPC over stdio, or an
HTTP address, with the harness keeping the scoring and the statistics.

## Background & Context

- The seam is `call_system(text, params) -> Result` and `score(output, reference)`
  (`harness/scripts/adapter.py`). `Result.extra` takes numbers; `Result.meta` keeps raw metadata
  and is already written per item (`_meta`), which is where stage outputs end up today, unshaped.
  The integration guide advises calling the one stage being changed.
- A reference is one text file per item (`<item_id>.txt`, `experiment_run.py:296`), so a stage
  has no reference of its own; resume reads back `<item_id>.txt` outputs as text
  (`experiment_run.py:259`). Item fields (0.4.0) never reach the adapter: it receives the item's
  text only.
- The podcast project evaluates its pipeline (transcription, summary, insights, knowledge graph)
  with its own runners and per-stage scorers, and brings per-item scores in with `import-run`
  (242 runs). `import-run` gives an imported run a fingerprint marked `imported`, with the build
  ref and the scorer's hash; what it gives up is the outputs (the inspector shows nothing),
  resume, and the harness calling and scoring the system. Its whole-pipeline runner works per
  **feed**, not per item, and some stages (speaker naming, the knowledge-graph bridge) work
  across items: a per-item `call_system` does not fit them.
- A system in Java, Go or Node can reach the harness today through a Python adapter that runs a
  subprocess, or through `import-run`; the adapter's code hash then identifies the wrapper, not
  the system.

## Goals

- A project hands the harness its whole pipeline and gets, per item, every stage's output, cost,
  tokens and time, scored per stage (against the stage's own reference when it has one) and end
  to end.
- A stage measure is a metric like any other: `pair-test`, `family-test`, goals, axes and the
  catalog take it with no special cases.
- When the end result moves, the record shows which stage moved it.
- A pipeline that runs a whole dataset at once can be evaluated without being cut into per-item
  calls.
- A system in any language plugs in through a documented protocol, with the same records, resume
  and inspector as a Python adapter, and is identified by what it declares, never by its wrapper.
- A one-stage 0.4.0 adapter keeps working with no change to its code (its runs' fingerprints
  move once, with the harness's own code, as on every release).

## Non-Goals

- Not a pipeline orchestrator: the harness does not schedule, retry or cache stages. The
  project's code runs its pipeline.
- No graph: stages are a list. A span may name its parent, so a nested pipeline is recorded
  faithfully, but the harness does not traverse or schedule a tree.
- No harness-side scorer for a stage: the project scores; the harness records, tests and shows.
- No language SDKs beyond the protocol's specification and one example client in a second
  language.

## Personas

- **The pipeline engineer** deciding whether a change to one stage helped the whole.
- **The team outside Python** (a JVM service, a Node app) that wants the harness's statistics.
- **The agent** asked to evaluate a pipeline change ([PRD-012](PRD-012-agent-ready.md)).

## User Stories

- _As a pipeline engineer, my adapter returns the stages of one item, and the run records each
  stage's output, cost and time, so I can see that the summary got worse because transcription
  did._
- _As a pipeline engineer, I keep gold transcripts beside gold summaries and the run scores
  `asr.wer` against the first and `summary.rouge_l` against the second._
- _As a pipeline engineer whose pipeline runs a feed at a time, my adapter runs the dataset once
  and returns a result per item._
- _As a team on the JVM, I point a config at `java -jar pipeline.jar` and the harness runs the
  dataset through it, scores, fingerprints and resumes as for a Python adapter._
- _As a reviewer, I open an item in the inspector and read its stages side by side for two arms._

## Functional Requirements

### FR1: Stages

- **FR1.1**: A result may carry an ordered list of stages. Each is span-shaped: a name, an id, an
  optional parent id, start and end times, an output (text or JSON), token and model attributes
  named as in the OpenTelemetry GenAI conventions (`gen_ai.usage.input_tokens`,
  `gen_ai.usage.output_tokens`, `gen_ai.request.model`, `gen_ai.response.model`,
  `gen_ai.provider.name`, `gen_ai.operation.name`), cost under the harness's own name (the
  conventions define none), plus its own `extra` and `meta`. The record names the conventions'
  version it follows (they are in development). The end result stays the result's `output`.
- **FR1.2**: The run records each item's stages and the run's totals per stage. The run's cost and
  time are the sum of its stages unless the adapter reports them.
- **FR1.3**: Stage scores are metrics named `<stage>.<metric>`; end-result metrics keep their
  names. Directions and descriptions are declared per metric, as today.
- **FR1.4**: Every command that takes a metric takes a stage metric; a goal may decide on one.
- **FR1.5**: `evh validate` notes a run whose items do not all have the same stages, and refuses
  a stage metric whose stage the run lacks.
- **FR1.6**: A 0.4.0 adapter with no stages needs no change, and its records gain no fields.
- **FR1.7**: Stage records can also be imported as OpenTelemetry (OTLP JSON) traces, so a
  pipeline that already emits traces needs no second instrumentation; stage scores map to the
  conventions' evaluation event (`gen_ai.evaluation.result`) on import and export.
- **FR1.8**: Resume restores an item's stages, their outputs and their costs exactly as recorded.

### FR2: Stage references

- **FR2.1**: A reference may hold a reference per stage beside the end-result one; scoring passes
  each stage's scorer its stage's reference. A dataset's reference manifest says which stages it
  covers. (Design in RFC-007.)
- **FR2.2**: A stage with no reference can still be measured by reference-free metrics (cost,
  time, length, a judge without a reference).

### FR3: Structured outputs, fields, batch

- **FR3.1**: An output (end or stage) may be JSON; scorers receive it parsed; the inspector shows
  it readably and diffs it by field; resume stores and reads it back exactly.
- **FR3.2**: The adapter may receive an item's declared fields beside its text; an adapter says
  which form it takes, and a 0.4.0 adapter keeps receiving the text only (RFC-007).
- **FR3.3**: **Batch mode**: an adapter may take the whole dataset (or a batch) and return a
  result per item, for pipelines that work per feed or across items; cost and time are then
  apportioned as the adapter reports, resume works per batch, and the cost cap is checked before each
  batch (a batch never starts when the cap would be passed by its estimate).

### FR4: Systems in any language

- **FR4.1**: A config may name a **process adapter**: a command (`adapter: {command: [...]}`)
  started once and kept alive, speaking **JSON-RPC 2.0 over stdio**, newline-delimited, one request
  per item or batch, with only protocol messages on stdout and its logs on stderr (as MCP's stdio
  transport does), and trace context passed in the request; or an HTTP address
  (`adapter: {url: ...}`) speaking the same messages. Specified and versioned in RFC-008, with an
  example client in a second language.
- **FR4.2**: Scoring may stay in a Python adapter beside a process `call_system`, or be done by
  the process; either way the harness records the metrics.
- **FR4.3**: The process declares its identity (name, version, a digest of its artifact) and the
  harness records it with the protocol version; for a command, the harness also hashes the
  executable it started; for an HTTP address the identity is only what the service declares, and
  the record says so. A process that declares none is recorded as unidentified, and `run-promote`
  refuses it as it refuses an unknown build.
- **FR4.4**: Every adapter, Python or process, may declare the code ref of the system it calls
  (for example the git commit of the project's pipeline library), recorded with the system's
  identity.
- **FR4.5**: Resume, `--dry-run`, timing, cost and the refusals work as for a Python adapter.

### FR5: Wrapping what a project already has

- **FR5.1**: A documented recipe, with an example, turns an existing runner script (one that
  writes per-item outputs and scores) into an adapter, batch mode where needed, so a project moves
  from `import-run` to the harness running its system without rewriting its pipeline.

### FR6: People and agents alike

- **FR6.1**: Every stage view in the inspector has a command with the same content
  (`evh inspect --stages`), with JSON output ([PRD-012](PRD-012-agent-ready.md)).

## Success Criteria

- An example pipeline of three stages, one calling a hosted LLM and one with its own reference,
  runs through `experiment-run`; `pair-test` separates an arm on a stage metric; the inspector
  shows the stages.
- The same pipeline as a process adapter in a second language gives the same metrics to the
  stated float precision.
- A batch-mode example reproduces per-item results of the per-item version.
- The podcast project's summary → insights → knowledge-graph stages (run today by its
  `run_experiment.py` tasks; its per-feed runner turns those stages off) run through the harness via
  the wrapping recipe, with per-stage scores (to be confirmed with that project).
- Every 0.4.0 adapter runs and every 0.4.0 run validates (after the 0.5.0 migrations).

## Related Documents

- RFC-007, RFC-008 (to be written); [INTEGRATION](../../harness/docs/INTEGRATION.md);
  OpenTelemetry GenAI semantic conventions; JSON-RPC 2.0.
