# PRD-014: Datasets from production

- **Status**: Built for 0.6.0 (2026-10-31); drafted 2026-10-30
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (the datasets page: tags, origin, versions side by side)
- **Related RFC**: [RFC-019](../rfc/RFC-019-datasets-from-production.md)
- **Related ADRs**: [ADR-0019](../adr/ADR-0019-capture-lane.md), [ADR-0020](../adr/ADR-0020-second-references-are-silver.md)
- **Related PRDs**: [PRD-002](PRD-002-references.md) (references), [PRD-006](PRD-006-datasets-versions-fields.md)
  (datasets, versions, fields)

## Summary

A project improves a system by measuring it on what the system actually meets. 0.6.0 adds a lane beside the
method: read records from a production system (an importer), keep them (a capture), choose items from them
into a new dataset version, take a reference from what happened afterwards (an outcome), and split dev from
heldout. The lane ends in an ordinary dataset and reference, so the method runs and compares as it does today.

## Background & Context

Records that live in a tracing system, a ledger or an issue tracker reached a dataset only through a script
each project wrote: no record of what was read, which items were chosen and why, or a link back. And what
happened after a decision (an issue fixed, closed as noise, reopened) never became a reference, though it is
often the best one there is. The case the lane is designed on: an agent fleet that triages observability
signals into GitHub issues, every decision in a ledger and a trace, every issue closed with a comment that says
what it was.

## Goals

- A capture records exactly what was read: the importer and its code's hash, the query, the window, each
  record's id, link and hash.
- A dataset made from a capture says how its items were chosen, and grows by versions.
- An outcome becomes a reference through a recorded mapping, never by hand-editing, and says what it is.
- Repeating it is one command from the previous capture; nothing runs in the background.
- Nothing changes for a project that never uses it.
- Text from a dataset can be kept off every public surface with one field.

## Non-Goals

- A schedule, a server, or state outside the project's files.
- A labelling interface (a project's labels arrive as files).
- Holding or protecting a project's data: what is committed is the project's decision.
- Write tools for agents (0.7.0).

## Personas

- **The engineer running a system in production** (an agent fleet, a pipeline) who wants to know whether a change
  (a model, a prompt, a rule) is better on real traffic.
- **The operator** whose actions after the fact (closing an issue as fixed or as noise) are the truest verdict.

## User Stories

- _As an engineer, I can capture the last month of my system's decisions (`evh capture --importer … --query …`)
  and see what was read and when._
- _As an engineer, I can make the next version of my dataset from a new capture
  (`evh dataset-from-capture … --from D_prev`) and see what it added._
- _As an operator, my close comments become the reference, through a mapping I can read and change, with the
  mapping's hash recorded._
- _As an engineer, I can keep a dataset's text off my public catalog (`text: hidden`)._

## Functional Requirements

### FR1: Importers

- **FR1.1**: An importer is `records(query)`; a record is `{id, body, fields, created_at, source, labels,
  outcome}`.
- **FR1.2**: Built in: `jsonl`, `tsv`, `github` (issues, with each close and reopen event's actor and comment),
  `langfuse` (traces). A project's own: `<data>/importers/<name>.py` or `path.py:Class`.
- **FR1.3**: `evh importer-check` passes or fails an importer: ids unique and safe as file names, records
  well-formed, times parsed, hashes stable.

### FR2: Captures

- **FR2.1**: `evh capture` writes the records and `capture.json` (importer, code hash, query, window, per record
  id, link, hash); never overwrites without `--force`; `--since-capture` continues from an earlier one.
- **FR2.2**: `evh capture-scrub` runs the project's own scrubber and records it.
- **FR2.3**: `evh captures` lists them; `evh validate` V17 checks every record against its hash.

### FR3: Datasets from a capture

- **FR3.1**: `evh dataset-from-capture` filters, removes duplicates, keeps one item per value of a field if
  asked, samples with a seed, and writes an ordinary dataset; only the record's body becomes the item.
- **FR3.2**: The dataset records how its items were chosen (`made_from`) and optional `tags`.
- **FR3.3**: `--from` makes a new version with the existing lineage.

### FR4: References from outcomes

- **FR4.1**: `evh reference-from-outcomes` applies an ordered mapping of rules to the capture's outcome fields;
  the first match labels the item, no match leaves it unlabelled.
- **FR4.2**: The reference records the capture, the mapping and its hash, and the counts matched, skipped and
  unmatched, and carries its own caveat. It never overwrites a reference.
- **FR4.3**: The reference a goal decides on is the dataset's gold; others are shown beside it and never decide
  ([ADR-0020](../adr/ADR-0020-second-references-are-silver.md)).

### FR5: Splits

- **FR5.1**: `evh dataset-split` writes dev and heldout as ordinary datasets, by hash (stable across versions,
  optionally grouped by a field) or by time.

### FR6: Text kept off public surfaces

- **FR6.1**: `text: hidden` on a dataset keeps every text derived from it (sources, outputs, reference texts,
  judge reasons, text and URL field values, source links) off every public surface: the catalog, the
  inspector, MCP, and a deployment's copy. Counts and scores stay.

### FR7: Views

- **FR7.1**: The datasets page and `evh datasets` show tags and a dataset's origin; a version's profile sits
  beside its parent's. `evh captures` has an MCP read tool.

## Success Metrics

- The triage example runs end to end from a capture to a goal decision, offline with a stand-in model, and
  with real models on the owner's verdicts.
- Every existing test passes unchanged.

## Release Considerations

- New optional fields only: no migration. Captures are not supported on Windows (record ids may contain `:`).
