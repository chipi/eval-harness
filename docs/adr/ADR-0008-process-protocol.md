# ADR-0008 — Systems in any language through a JSON-RPC process (0.5.0)

**Status:** Accepted (2026-10-26), design; not yet built
**Date:** 2026-10-26
**Detail:** [PRD-008](../prd/PRD-008-pipelines-and-any-language.md) FR4,
[RFC-008](../rfc/RFC-008-process-protocol.md) (messages, lifecycle, identity)

## Context

The adapter seam is Python. A system in another language reached the harness through a Python
wrapper around a subprocess, whose code hash then identified the wrapper, not the system, or through
`import-run`, where the harness neither calls nor scores it.

## Decision

- **A process adapter** is a command the harness starts and talks to with JSON-RPC 2.0,
  newline-delimited over stdio (or the same messages over HTTP): `initialize`, `call`,
  `call_batch`, `score`, `estimate`, `shutdown`. It is wrapped as an ordinary adapter, so resume,
  retries, the cost cap and refusals are the existing code. `adapter:` stays a path (a
  `.process.yaml` file).
- **The protocol is `evh-adapter/<major>.<minor>`**: a different major is refused; unknown fields
  are ignored; optional features are announced as capabilities.
- **The system's identity is the arm**: what it declares, plus the hash of the files it names
  (`identity_files`), recorded under `arm.system`, so two versions of a system compare as a
  controlled comparison. The scorer stays the instrument. An unidentified system cannot be
  promoted.
- **A process restarts after a crash and must declare the same identity**; each repeat gets its
  own process.

## Consequences

A Java, Node or Go system plugs in with a small client and a conformance check
(`evh adapter-check`). The harness does not guess what to hash from a command line (a launcher is
not the program); a project that names no files is labelled with the launcher's hash only.
