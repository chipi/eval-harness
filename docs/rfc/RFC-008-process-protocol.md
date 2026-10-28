# RFC-008: The process protocol: systems in any language

- **Status**: Draft (0.5.0), revision 3 (2026-10-27): the metric declarations live in the adapter file, not in
  `initialize`, so nothing is cached. Revision 2: stdio only; the HTTP transport is deferred
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-008](../prd/PRD-008-pipelines-and-any-language.md) (FR4)
- **Related RFCs**: RFC-007 (the result and stages it carries), [RFC-001](RFC-001-fingerprint-and-code-identity.md)
  (identity), RFC-013 (exit codes, refusals)
- **Code**: new `harness/scripts/_process_adapter.py`, `_adapter.py` (`_find_adapter`, `load_adapter`,
  `load_recorded_adapter` and the declaration readers `metric_kinds` … `primary_metric` accept a process adapter),
  `_retry.py` (`TransientError`), `_fingerprint.py` (`arm.system`), `compare_runs.py`,
  `schemas/protocol/` (the messages), `harness/examples/process-adapter-node/`, `harness/docs/ADAPTER-PROTOCOL.md` (the specification)

## Abstract

A config may name a **process adapter** instead of a Python file: a command the harness starts once and talks to with
**JSON-RPC 2.0, newline-delimited, over stdio** (only protocol messages on stdout, logs on stderr, as MCP's stdio
transport). The harness wraps it as an ordinary adapter
(`_process_adapter.ProcessAdapter` provides `call_system`, `call_batch`, `score`, `fingerprint`), so resume, retries,
the cost cap, timing and refusals are the existing code. The process declares its identity and capabilities when it
starts; for a command, the harness also hashes the executable. An example client in Node.js and a conformance check ship
with it.

## Problem Statement

- The seam is Python (`adapter.py`); a system in another language reaches the harness through a Python wrapper that
  runs a subprocess (its code hash then identifies the wrapper) or through `import-run` (no outputs, no resume, the
  harness neither calls nor scores the system).

## Design

### Configuration

```yaml
adapter: adapters/pipeline.process.yaml     # a string, as today; a file ending .process.yaml is a process adapter
```

```yaml
# adapters/pipeline.process.yaml
name: pipeline                                # the id is process:pipeline
command: ["java", "-cp", "build/libs/*", "eval.Main"]
cwd: services/pipeline         # optional, relative to the project
env: [PIPELINE_API_KEY]        # names passed through; values never recorded
timeout_s: 120                 # per request
identity_files: ["services/pipeline/build/libs/*.jar"]  # what the harness hashes as the system (below)
score: process                 # or: a Python file whose score() is used (score: adapters/score.py)
metrics:                       # what a Python adapter declares as module attributes
  wer: {kind: quality, direction: lower, description: "word error rate against the reference"}
  latency_ms: {kind: speed}
primary_metric: wer
transient_markers: ["503", "rate limit"]
```

`adapter:` stays a string, so every place that resolves it (`_find_adapter`, `load_recorded_adapter` for `rescore`,
`silver-calibrate` and the catalog) keeps working: the recorded id of a process adapter is the path of its
`.process.yaml`, portable as a Python adapter's is. `schemas/process-adapter.schema.json` validates the file. The
declarations a Python adapter makes as module attributes (`METRIC_KINDS`, `METRIC_DIRECTIONS`, `METRIC_DESCRIPTIONS`,
`PRIMARY_METRIC`, `TRANSIENT_MARKERS`) are written in the file by the person, so every command that reads them without
running the system (`rescore`, the catalog) reads the file, and nothing is cached.

### Messages (protocol version `evh-adapter/1`)

| method | from → to | params | result |
| --- | --- | --- | --- |
| `initialize` | harness → system | `{protocol: "evh-adapter/1.0", harness_version, params}` | `{protocol, identity: {name, version, artifact_sha256?, code_ref?, scorer?: {version, sha256?}}, capabilities: {call_form: "text"\|"item", batch: bool, batch_key?: str, score: bool, stages: bool, estimate: bool}}` |
| `call` | harness → system | `{item: {id, text, fields?}, params, _meta?: {traceparent}}` | a result: `{output, stages?, tokens_in?, tokens_out?, cost_usd?, latency_ms?, extra?, meta?}` (RFC-007's fields) |
| `call_batch` | harness → system | `{items: [...], params, _meta?}` | `{results: {item_id: result}}` |
| `score` | harness → system | `{output, reference?, source?, stage?}` | `{metrics: {name: number}}` |
| `estimate` | harness → system | `{items: [...], params}` | `{cost_usd}` (RFC-007's cost cap) |
| `shutdown` | harness → system | `{}` | `{}`; then the process exits |

- Errors are JSON-RPC errors. `error.data.transient: true` raises `_retry.TransientError`, which `is_transient` treats
  as transient by type, not by message; anything else is an item failure (RFC-007), recorded with the error's message.
- One request at a time per process (the harness does not pipeline); `id`s increase.
- The messages are JSON Schemas in `schemas/protocol/`; `harness/docs/ADAPTER-PROTOCOL.md` is the specification, versioned.
- Numbers are IEEE doubles in JSON; metrics are compared across implementations with
  `abs(a - b) <= 1e-12 * max(1, abs(a), abs(b))`, so a metric of 0 compares too.
- **Versions**: the protocol is `evh-adapter/<major>.<minor>`. A different major is refused; a newer minor from either
  side is accepted, and fields a side does not know are ignored (never an error). Optional features are announced in
  `capabilities`, never inferred from the minor.

### Lifecycle

- The harness starts the command once per pass (each `--repeat` is a pass with its own process, so repeats are
  independent), in its own process group, sends `initialize`, refuses (code `adapter-protocol`) a different protocol
  major version, calls per item or batch, and sends `shutdown` at the end, then waits 10 s and kills the group.
- A request past `timeout_s` kills the process group; the item fails as transient, and the next item starts a new
  process.
- A process that exits or is killed is restarted for the next item (a retry included): the harness sends `initialize`
  again and compares the identity with the first one. A different identity stops the pass (code `identity-changed`):
  the run would otherwise measure two systems. After 3 restarts in a pass, the remaining items fail with the last
  stderr lines recorded.
- `--resume` starts a process, and refuses (code `identity-changed`) when its identity differs from the one the resumed
  run recorded.

### Identity (PRD-008 FR4.3)

- **The system is the arm.** A process system's identity is what is being compared (jar v1 against jar v2), so it goes
  under `arm.system`, inside the hash: `{"process": "process:<name>", "protocol": "evh-adapter/1.0", "declared": {name,
  version, artifact_sha256, code_ref}, "files_sha256": …}`. `run-compare` reads every `arm.*` difference as the
  variable, so two versions of the system compare as a controlled comparison. A Python adapter that declares a system
  through `fingerprint(params)` (`{"system": {...}}`) records it in the same place.
- **What is hashed**: `files_sha256` is the digest (sorted relative paths and their sha256) of the files matched by
  `identity_files`. Hashing the command's first argument identifies the launcher (`java`, `node`, `uv`, `./gradlew`, a
  shell wrapper), not the program, and a jar's hash misses its dependency jars, so the harness does not guess; with no
  `identity_files` it records the resolved command's sha256 as `launcher_sha256`, labelled as the launcher.
- **Identified** means a declared `artifact_sha256` or a `files_sha256`. Otherwise the system is unidentified;
  `run-promote` refuses it (code `unidentified-system`), as it refuses an unknown build.
- **The scorer is the instrument.** `instrument.adapter` stays the scorer: with `score: adapters/score.py`, that file's
  id and hash as today; with `score: process`, `{"id": "process:<name>", "scorer": identity.scorer}` when the process
  declares its scorer's version, and otherwise the system's `files_sha256`. In that last case a new system version also
  moves the instrument; `run-compare` names it ("the scorer is part of the system and changed with it"), and the
  wrapping recipe recommends `score:` in a separate file.
- The system's code ref (PRD-008 FR4.4) is `identity.code_ref`.
- **On the arms page.** 0.4.2's arms page names an arm's model from `params.model` (`catalog_arms.py`), which a process
  config has none of. A process arm shows `process:<name>` and its declared version as its model; it counts as local,
  since the harness bills no provider for it (its own spend is what its results report), and `data/models.yaml` does
  not apply to it.

### The example and the conformance check

- `harness/examples/process-adapter-node/`: a single-file Node.js client (no dependencies) implementing `initialize`, `call`,
  `score` and `shutdown` for the example dataset, mirroring the Python example adapter.
- `evh adapter-check [--config C] [--json]`: starts the configured process adapter, runs `initialize` and one `call`
  and `score` on the dataset's first item, validates every message against the schemas, checks that the metrics it
  scores are the ones the file declares, and reports. It writes no records. It exits 0 when every message conforms, and 6 (a check found problems, RFC-013)
  when one does not, with each failure listed.

## Migration

None.

## Alternatives Considered

- **One process per item (`exec`).** Rejected: start-up costs per item (a JVM) and no shared state; a long-lived process
  is what LSP and MCP use.
- **gRPC.** Rejected: a dependency and generated code in every language; JSON-RPC needs neither.
- **MCP itself as the adapter protocol.** Rejected: MCP's shape (tools for an agent) is not "call this system on an
  item"; a small purpose-built protocol is easier to implement in any language and to test.
- **HTTP only.** Rejected: a command needs no port, no server and no auth.
- **The same messages over HTTP, for systems already running as services.** Deferred (revision 2): a service can be
  reached by a small command that forwards the messages; an HTTP transport can be added later without changing them.

## Testing

- `harness/tests/test_process_adapter.py`: the Node example (when `node` is installed; skipped with a reason otherwise)
  and a Python implementation of the protocol give the same metrics as the Python example adapter within 1e-12; a
  transient error is retried; a killed process restarts and a changed identity stops the pass; `--resume` with a
  changed identity is refused; a timeout kills the process group; a protocol major mismatch is refused and an unknown
  field from a newer minor is ignored; an unidentified process is refused by `run-promote`; two jar versions compare
  with only `arm.system` moved; `rescore` of a process run reads the declarations from the file; `adapter-check` validates the
  messages.

## Decisions (ADR candidates)

1. Systems in any language plug in through a long-lived process speaking JSON-RPC 2.0 over stdio, wrapped as an
   ordinary adapter.
2. A process system's identity is what it declares plus the hash of the files it names, recorded as part of the arm
   (`arm.system`); the scorer stays the instrument. An unidentified system cannot be promoted.
3. A process restarts after a crash and must declare the same identity; repeats each get their own process.
