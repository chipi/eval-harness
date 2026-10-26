# PRD-008: Pipelines, stages, and systems in any language

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-002](../uxs/UXS-002-inspector.md) (the inspector, to gain a stage view)
- **Related RFCs**: RFC-007 (stages in the result and the run record), RFC-008 (the process
  protocol), both to be written
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md),
  [PRD-007](PRD-007-packaging-and-providers.md) (the adapter seam),
  [PRD-012](PRD-012-agent-ready.md) (every capability for people and agents alike)

## Summary

A system under test is often not one model call but a **pipeline**: the project's own code,
calling third parties (a transcription service, an LLM, a vector store) stage by stage, and what
matters is the **compound** result and where it went wrong. Today the harness sees one input
string and one output string per item. This PRD makes a result able to carry **stages** (each
with its output, cost, tokens and time), lets the project score each stage as well as the end
result, and makes every stage measure an ordinary metric, so the paired tests, goals and the
catalog work per stage without anything new to learn. It also opens the seam to systems **not
written in Python**: an adapter can be a command or an HTTP address that speaks a small JSON
protocol, and the harness keeps the scoring and the statistics.

## Background & Context

- The adapter seam is `call_system(text, params) -> Result` and `score(output, reference)`
  (`harness/scripts/adapter.py`). `Result.extra` takes numbers, `Result.meta` keeps raw
  metadata; there is no place for intermediate outputs, and the integration guide advises
  calling one stage.
- The podcast project evaluates its pipeline (transcription, summary, insights, knowledge
  graph) with its own runners (`run_experiment.py`, `run_dataset_through_pipeline.py`,
  `pipeline_validate.py`) and per-stage scorers, then brings per-item scores into the harness
  with `import-run` (242 runs). It never used `call_system`; the harness did not run or score
  any of those runs, and the inspector cannot show a stage.
- A system in Java, Go or Node can reach the harness only through `import-run` today, which
  gives up the fingerprint of the system, resume, the inspector's outputs and timing.

## Goals

- A project can hand the harness its whole pipeline and get, per item, every stage's output,
  cost, tokens and time, scored per stage and end to end.
- A stage measure is a metric like any other: `pair-test`, `family-test`, goals, axes and the
  catalog take it without special cases (`summary.rouge_l`, `asr.wer`, `end.judge_score`).
- When the end result moves, the record shows which stage moved it.
- A system in any language plugs in by speaking a documented protocol, with the same records,
  resume and inspector as a Python adapter.
- A one-stage adapter written for 0.4.0 keeps working unchanged.

## Non-Goals

- The harness is not a pipeline orchestrator: it does not schedule stages, retry a stage, or
  cache stage outputs across runs. The project's code runs its pipeline; the harness asks it
  for an item's result.
- No graph of stages: stages are an ordered list with names. Branching pipelines report their
  stages as a list.
- No harness-side scorer for a stage it cannot read: the project scores; the harness records,
  tests and shows.
- No language SDKs in 0.5.0 beyond the protocol's specification and one example client.

## Personas

- **The pipeline engineer** whose product is several stages and third-party calls, deciding
  whether a change to one stage helped the whole.
- **The team outside Python** (a Java service, a Node app) that wants the harness's statistics
  on its own system.
- **The agent** asked to evaluate a pipeline change on a project's behalf
  ([PRD-012](PRD-012-agent-ready.md)).

## User Stories

- _As a pipeline engineer, my adapter returns the stages of one item, and the run records each
  stage's output, cost and time, so I can see that the summary got worse because transcription
  did._
- _As a pipeline engineer, I score each stage and the end result, and test an arm against the
  baseline on any of those measures with the commands I already use._
- _As a team on the JVM, I point a config at `java -jar pipeline.jar` and the harness runs the
  dataset through it, scores, fingerprints and resumes as it would a Python adapter._
- _As a reviewer, I open an item in the inspector and read its stages side by side for two
  arms._

## Functional Requirements

### FR1: Stages

- **FR1.1**: A result may carry an ordered list of stages; each has a name, an output (text or
  JSON), and optionally tokens, cost, latency, and its own `extra` and `meta`. The end result
  stays the result's `output`.
- **FR1.2**: The run records each stage per item (predictions) and the run's totals per stage
  (cost, tokens, time). The run's cost and time are the sum of its stages unless the adapter
  says otherwise.
- **FR1.3**: The adapter may score stages: a stage's scores become metrics named
  `<stage>.<metric>`; the end result's keep their names. Directions and descriptions are
  declared per metric, as today.
- **FR1.4**: Every command that takes a metric takes a stage metric; a goal may decide on one.
- **FR1.5**: `evh validate` checks that every item of a run has the same stages, and refuses a
  stage metric whose stage the run does not have.
- **FR1.6**: An adapter with no stages behaves exactly as in 0.4.0; no fingerprint moves for it.

### FR2: Structured outputs

- **FR2.1**: An output (end or stage) may be JSON, not only text; scorers receive it parsed.
- **FR2.2**: The inspector shows JSON outputs readably and diffs them by field.

### FR3: Systems in any language

- **FR3.1**: A config may name a **process adapter**: a command (`adapter: {command: [...]}`) or
  an HTTP address (`adapter: {url: ...}`), instead of a Python file.
- **FR3.2**: The protocol is JSON: the harness sends an item (its text or fields) and the
  config's params, and reads back the result fields of FR1, stages included. It is versioned and
  specified in RFC-008, with an example client in a second language.
- **FR3.3**: Scoring may stay in a Python adapter beside a process `call_system`, or be done by
  the process (`score` in the protocol); either way the harness records the metrics.
- **FR3.4**: The fingerprint identifies a process system by what it declares (a version, a
  digest of its artifact) and by the protocol version; a system that declares nothing is
  recorded as unidentified, never as identified.
- **FR3.5**: Resume, `--dry-run`, timing, cost and the refusals work the same as for a Python
  adapter.

### FR4: People and agents alike

- **FR4.1**: Every stage view in the inspector has a command with the same content
  (`evh inspect --stages`), with JSON output.

## Success Criteria

- An example pipeline of three stages, one calling a hosted LLM, runs through `experiment-run`;
  `pair-test` separates an arm on a stage metric; the inspector shows the stages.
- The same pipeline wrapped as a process adapter in a second language gives byte-identical
  metrics to the Python version.
- The podcast project can run its summary → insights → knowledge-graph chain through the
  harness instead of its own runner, with per-stage scores (the review with that project decides
  whether it does).
- Every 0.4.0 adapter and run validates unchanged.

## Related Documents

- RFC-007 and RFC-008 (to be written).
- [INTEGRATION](../../harness/docs/INTEGRATION.md) (the adapter seam today).
