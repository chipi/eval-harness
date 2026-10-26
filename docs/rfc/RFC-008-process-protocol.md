# RFC-008: The process protocol: systems in any language

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-008](../prd/PRD-008-pipelines-and-any-language.md) (FR4)
- **Related RFCs**: RFC-007 (the result and stages it carries), [RFC-001](RFC-001-fingerprint-and-code-identity.md)
  (identity), RFC-013 (exit codes, refusals)
- **Code**: new `harness/scripts/_process_adapter.py`, `_adapter.py` (loading a process adapter),
  `schemas/protocol/` (the messages), `harness/examples/process-adapter-node/`, `harness/docs/ADAPTER-PROTOCOL.md` (the specification)

## Abstract

A config may name a **process adapter** instead of a Python file: a command the harness starts once and talks to with
**JSON-RPC 2.0, newline-delimited, over stdio** (only protocol messages on stdout, logs on stderr, as MCP's stdio
transport), or an HTTP address that takes the same messages. The harness wraps it as an ordinary adapter
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
adapter:
  command: ["java", "-jar", "build/pipeline.jar", "--eval"]   # or: url: http://localhost:8800/rpc
  cwd: services/pipeline         # optional, relative to the project
  env: [PIPELINE_API_KEY]        # names passed through; values never recorded
  timeout_s: 120                 # per request
  score: process                 # or: a Python adapter for score() beside the process (score: adapters/score.py)
```

### Messages (protocol version `evh-adapter/1`)

| method | from → to | params | result |
| --- | --- | --- | --- |
| `initialize` | harness → system | `{protocol: "evh-adapter/1", harness_version, params}` | `{protocol, identity: {name, version, artifact_sha256?}, capabilities: {call_form: "text"\|"item", batch: bool, score: bool, stages: bool}}` |
| `call` | harness → system | `{item: {id, text, fields?}, params, _meta?: {traceparent}}` | a result: `{output, stages?, tokens_in?, tokens_out?, cost_usd?, latency_ms?, extra?, meta?}` (RFC-007's fields) |
| `call_batch` | harness → system | `{items: [...], params, _meta?}` | `{results: {item_id: result}}` |
| `score` | harness → system | `{output, reference?, source?, stage?}` | `{metrics: {name: number}}` |
| `shutdown` | harness → system | `{}` | `{}`; then the process exits |

- Errors are JSON-RPC errors; `error.data.transient: true` marks a failure the harness retries (as the Python adapter's
  transient markers do); anything else fails the item, recorded.
- One request at a time per process (the harness does not pipeline); `id`s increase.
- The messages are JSON Schemas in `schemas/protocol/`; `harness/docs/ADAPTER-PROTOCOL.md` is the specification, versioned.
- Numbers are IEEE doubles in JSON; metrics are compared across implementations within 1e-12 relative.

### Lifecycle

The harness starts the command once per run (or per job, RFC-011), sends `initialize`, refuses (code
`adapter-protocol`) a different protocol major version, calls per item or batch, and sends `shutdown` at the end. A
process that exits early fails the remaining items with its last stderr lines in the record. For `url`, `initialize` is
sent once per run and `shutdown` is not.

### Identity (PRD-008 FR4.3)

- The fingerprint's `instrument.adapter` becomes `{"id": "process:<name>", "protocol": "evh-adapter/1", "declared":
  {name, version, artifact_sha256}, "executable_sha256": …}` for a command: the harness resolves the command's first
  argument (through `PATH`) and, for a known runtime (`java`, `node`, `python`, `dotnet`), the first path argument it
  runs (`build/pipeline.jar`), and hashes that file. For `url`: only the declared identity, with `"declared_only": true`.
- With no `artifact_sha256` declared and no executable hashed, the adapter is unidentified; `run-promote` refuses it
  (code `unidentified-system`), as it refuses an unknown build.
- The adapter's own code ref (PRD-008 FR4.4) may be declared in `identity.code_ref`.

### The example and the conformance check

- `harness/examples/process-adapter-node/`: a single-file Node.js client (no dependencies) implementing `initialize`, `call`,
  `score` and `shutdown` for the example dataset, mirroring the Python example adapter.
- `evh adapter-check [--config C]`: starts the configured process adapter, runs `initialize` and one `call` and `score`
  on the dataset's first item, validates every message against the schemas, and reports (a read command, no records
  written).

## Migration

None.

## Alternatives Considered

- **One process per item (`exec`).** Rejected: start-up costs per item (a JVM) and no shared state; a long-lived process
  is what LSP and MCP use.
- **gRPC.** Rejected: a dependency and generated code in every language; JSON-RPC needs neither.
- **MCP itself as the adapter protocol.** Rejected: MCP's shape (tools for an agent) is not "call this system on an
  item"; a small purpose-built protocol is easier to implement in any language and to test.
- **HTTP only.** Rejected: a command needs no port, no server and no auth; HTTP is offered for systems already running
  as services.

## Testing

- `harness/tests/test_process_adapter.py`: the Node example (when `node` is installed; skipped with a reason otherwise)
  and a Python implementation of the protocol give the same metrics as the Python example adapter within 1e-12; a
  transient error is retried; an early exit fails the rest with stderr recorded; a protocol version mismatch is refused;
  an unidentified process is refused by `run-promote`; `adapter-check` validates the messages.

## Decisions (ADR candidates)

1. Systems in any language plug in through a long-lived process speaking JSON-RPC 2.0 over stdio (or the same messages
   over HTTP), wrapped as an ordinary adapter.
2. A process system's identity is what it declares plus the hash of the executable the harness started; an unidentified
   system cannot be promoted.
