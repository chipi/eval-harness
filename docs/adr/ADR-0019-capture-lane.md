# ADR-0019 — Datasets from production: a capture lane beside the method (0.6.0)

**Status:** Accepted (2026-10-30), built in 0.6.0.
**Date:** 2026-10-30
**Detail:** [PRD-014](../prd/PRD-014-datasets-from-production.md) (requirements),
[RFC-019](../rfc/RFC-019-datasets-from-production.md) (design),
[UXS-001](../uxs/UXS-001-catalog.md) (the datasets page)

## Context

A project that wants to evaluate on what its system meets in production has its records in a
tracing system, a ledger file or an issue tracker. Today they reach a dataset only through a
script each project writes, with no record of what was read, which items were chosen, or a link
back to the record, and no reference taken from what happened afterwards. The first case is an
agent fleet that triages observability signals into GitHub issues, whose decisions and their
fates are all recorded.

## Decision

- **A lane, not a rewrite.** New commands (`capture`, `capture-scrub`, `captures`,
  `dataset-from-capture`, `reference-from-outcomes`, `dataset-split`, `importer-check`) end in the
  files the method already reads: a dataset with lineage, a reference. No existing command changes
  its arguments or its output for data without the new optional fields (a dataset's `tags`,
  `made_from`, `text`; a reference's `from_outcomes`).
- **Stateless.** Every step reads and writes the project's files. "Continuous" is running a
  capture again from the previous one (`--since-capture`). No server, no schedule.
- **Importers.** One interface, `records(query)`. Four built in (`jsonl`, `tsv`, `github`,
  `langfuse`), standard library and `gh` only, in a folder the core never imports; a project's
  own in `<data>/importers/` or by path. Reading a project's production stores is the project's
  code; the lane reads what that code exports.
- **Outcomes are references.** A mapping of ordered rules over flat fields the project computes
  turns what happened afterwards into a reference, recorded with its mapping's hash and the
  capture it read, and its own caveat. It never overwrites a reference.
- **Text can be kept off every public surface** by one dataset field, `text: hidden`, inherited by
  everything derived from the dataset, and proved by one test across every surface.

## Consequences

- A project measures on its production records without changing how it runs, compares or
  decides.
- The harness offers scrubbing (the project's own scrubber, recorded) and the `text: hidden`
  label; what to commit stays the project's decision.
- A capture's records are files; a project that commits them makes its datasets reproducible
  from them, one that does not keeps their hashes.
- Two more words in the vocabulary: capture and outcome (importer and record are code terms).

## Alternatives considered

- **Weaving capture into `dataset-create` and the reference commands.** Rejected: it changes what
  exists for every project to serve a case only some have.
- **The harness keeping records private** (refusing to freeze without scrub rules). Rejected: the
  project decides what it commits.
- **Vendor importers only as examples.** Rejected for `github` and `langfuse`: one install should
  do everything, and they need no new dependency.
- **A scheduler and a server.** Deferred: the commands are what a schedule would call.
