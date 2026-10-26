# ADR-0007 — A result carries its stages; items fail alone (0.5.0)

**Status:** Accepted (2026-10-26), design; not yet built
**Date:** 2026-10-26
**Detail:** [PRD-008](../prd/PRD-008-pipelines-and-any-language.md) (what and why),
[RFC-007](../rfc/RFC-007-stages-and-stage-references.md) (records, resume, batches, traces)

## Context

A project's system is often a pipeline (transcribe, summarise, extract) with third-party calls in
between. The harness saw only the end output: intermediate results went into `_meta` unshaped, no
stage could be scored against its own reference, outputs were text only, an adapter could not see
an item's fields or run a whole feed at once, and one item that failed after its retries stopped
the whole run.

## Decision

- **Stages are span-shaped records on the result**: name, id, parent, times, output, tokens and
  model under the OpenTelemetry GenAI attribute names (a pinned conventions version), and the
  harness's own `cost_usd`. They are stored beside the outputs; their scores are ordinary metrics
  named `<stage>.<metric>` (stage names have no `.`; `judge` and `harness` are reserved).
- **A reference may hold per-stage references**, inside the reference digest.
- **Outputs may be JSON**; scorers get them parsed, judges serialised.
- **An adapter declares how it is called**: with the text (0.4.0) or the whole item, one at a time
  or in batches by a key field (default one item). 0.4.0 adapters are unchanged.
- **An item can fail without stopping the run**: recorded, counted, left out of means and paired
  tests; a run with failures cannot be promoted without a reason.
- **The end output is written last** and is resume's marker, so a crash never resumes an item
  without its stages.
- Traces come in and go out as OTLP (spans and evaluation-result log records).

## Consequences

A pipeline is measured stage by stage with the same tests as any metric, and its traces can come
from or go to a tracing tool. Every module that read `outputs/<item>.txt` moves to one reader. The
harness still never schedules a pipeline: the project runs it (PRD-008 Non-Goals).
