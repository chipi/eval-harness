# RFC-019: Datasets from production: a lane beside the method

- **Status**: Draft (third, 2026-10-30), being built for 0.6.0: brought in line with the engineering plan after
  three independent reviews; accepted when the build lands. ADR-0020 (second references are silver) is the
  owner's call.
- **Authors**: Marko Dragoljevic
- **Related PRD**: [PRD-014](../prd/PRD-014-datasets-from-production.md); also
  [PRD-006](../prd/PRD-006-datasets-versions-fields.md) (versions, item fields),
  [PRD-002](../prd/PRD-002-references.md) (references)
- **Related ADRs**: [ADR-0019](../adr/ADR-0019-capture-lane.md), [ADR-0020](../adr/ADR-0020-second-references-are-silver.md)
- **Related RFCs**: [RFC-006](RFC-006-item-fields-and-url-items.md) (field sets),
  [RFC-018](RFC-018-read-only-mcp-server.md) (the MCP server); on branch `070`: 0.7.0's RFC-013 (declarations,
  consent), RFC-015 (dev and heldout, test looks), RFC-016 (MCP tools)

## Abstract

A project improves a system by measuring it on what the system actually meets. This RFC adds a **lane** beside
the method:

- **capture** records from production systems with an **importer**;
- optionally **scrub** them with the project's own scrubber;
- **select** items from a capture into a new **dataset version**;
- take a **reference from outcomes**, what production recorded afterwards;
- **split** a dataset into dev and heldout.

The lane ends in the files the method already reads (a dataset file, a reference file), so materialize, run,
compare and goals work as they are. Every step is a command that reads and writes files: no server, no state
outside the project, no schedule. A dataset can also be labelled so that **no text derived from it** appears on
any public surface.

## Problem

- A dataset is frozen from a directory of files or from pinned URLs (RFC-006). Records that live in a tracing
  system, a ledger file or an issue tracker reach a dataset only through a script each project writes. Nothing
  records what was read, which items were chosen and why, or links back to the record.
- **The case this is designed on: a triage fleet.** An agent reads signals from observability (error-tracker
  issues, alerts), runs up to three probes against logs, metrics, traces and the source's state, and makes one
  decision per signal occurrence: dismiss, file an issue, escalate to a person, or clean up. Deterministic code
  before it (gates) and after it (filing and de-duplication) shapes what reaches GitHub. What it leaves behind:
  - every decision is a row in a ledger;
  - every decision is now captured with the probe answers the model saw;
  - every issue is closed by a person, with a comment that says what it was: fixed, or noise.
  - It has hand-labelled frozen fixtures and a scorer of its own. What it lacks is what the harness has:
    versions, references kept apart from items, paired tests, repeats, goals, a catalog.
  - And what neither has: a reference taken from what happened next.

## Design

### 0. The lane and its boundary

- **New commands only.** A project that never uses them sees no change.
- **The lane writes ordinary files:** a dataset with lineage, and a reference. Runs, comparisons, goals and pages
  read them like any other.
- **What existing files gain is optional and outside identity:**
  - a dataset's `tags` (the dataset-level form of `items[].tags`), `made_from` and `text`;
  - a reference manifest's `from_outcomes`.
- **Stateless.** "Continuous" is running a capture again: `--since-capture` continues from an earlier one. A
  schedule and a server are later questions.

### 1. Importers

- **The interface.** An importer is a class with `records(query) -> Iterator[Record]`. A record is
  `{id, body, fields, created_at, source: {system, url}, labels, outcome}`.
  - Ids are file-name safe, at most 200 characters. They may contain `:`, so captures are not supported on
    Windows.
- **Where an importer comes from:**
  - a built-in name: `jsonl`, `tsv`, `github` or `langfuse`, in `evaluation_harness/importers/`, which the core
    never imports. They use the standard library and `gh` only;
  - `<data>/importers/<name>.py:Importer`;
  - or `path.py:Class`.
- **`github`** reads issues by GraphQL through `gh`, and records each close and reopen event with its actor
  **and the comment beside it**. A fleet that writes with its owner's token can only be told from a person by
  its text, and a person's close comment carries the verdict.
- **`langfuse`** reads traces. Its keys come from the environment only, and it records a path-only URL.
- **Reading a project's production stores is the project's own code** (the fleet's build script). The lane reads
  what that code exports.
- **`evh importer-check`** is the contract test: ids unique and well-formed, records well-formed, times parsed,
  hashes stable.

### 2. Captures

- **`evh capture --importer NAME --query JSON --capture C`** writes two things:
  - `data/captures/<C>/capture.json`: the importer, its code's sha256, the query verbatim, the window, when, and
    per record its id, link, `sha256` (the whole normalised record) and `body_sha256`;
  - `records/<id>.json`.
- It never overwrites without `--force`.
- **`evh capture-scrub C --command "... {records}"`** runs the project's own scrubber, re-hashes, and records the
  command and its files' hashes.
- **`evh captures`** lists the captures. **V17** checks every record against its hash.
- **Commit before running.** Untracked captures and sources mark runs dirty, so they are committed before any
  billed run.

### 3. A dataset version from a capture

- **The command:** `evh dataset-from-capture C --dataset-id D [--from D_prev] [--where F:V] [--dedup exact|text]
  [--one-per F] [--sample N --by F --seed S] [--fieldset FS --field F] [--tag k=v]`.
- **Only the body becomes the item**, written to `data/sources/<D>/`, so an outcome never enters an item's bytes.
- **The dataset is written through `dataset-create`'s own functions** and records `made_from`.
- **`--one-per F`** keeps one record per value of a field, which gives independent items when many records share
  one fingerprint.

### 4. A dataset whose text is never shown publicly

- **`text: hidden`.** No text that comes from such a dataset reaches a public surface: its items' sources, every
  arm's outputs on it, its references' texts and per-item labels, judge reasons, adjudication notes, source
  URLs, and its text and URL field values.
- **One function** answers "may this text be shown publicly". These surfaces ask it:
  - the catalog;
  - the inspector's API;
  - the MCP tools;
  - `evh dataset-items` and `evh inspect` under `EVH_PUBLIC`;
  - and a deployment's data copy, which moves from `render.sh` into a Python module.
- **A marker test** fails if any surface leaks.
- **It also closes two holes.** The MCP `inspect --where/--by` hole on hidden fields was closed in 0.6.0's first
  part. A profile written `--with-text` is now checked again whenever the catalog builds.

### 5. References from outcomes

- **The command:** `evh reference-from-outcomes --dataset-id D --capture C --map outcomes.yaml [--name NAME]`.
- **The mapping** is an ordered list of rules over the **flat outcome fields** the project's importer computes.
  Each rule has `when`, `unless`, `exists`, `absent`, `range` (signed), `min_age_days`, and a `label` or `skip`.
  The first match wins; no match leaves the item unlabelled. A real mapping's time arithmetic and list logic are
  the project's own semantics, computed into fields, so the language stays small.
- **The reference records** `from_outcomes: {capture, mapping, mapping_sha256, matched, skipped, unmatched}`, and
  its own caveat: "OUTCOME: what production recorded afterwards, as of <capture date>; not a person's label".
- **It never overwrites a reference.**
- **Outcomes live in the capture.** Reading them again later makes a newer capture and a newer reference, never
  an edit.
- **Which reference decides** ([ADR-0020](../adr/ADR-0020-second-references-are-silver.md), proposed): a goal
  decides on `gold/<D>`. Every other reference on the dataset is `silver/<name>`, with its caveat, and is read
  through `rescore --reference-id`. The goal page then shows exactly one recommendation, and the others beside
  it.
- **Coverage is recorded as today.** A scorer leaves the key out on an unlabelled item.

### 6. Splits

- **The command:** `evh dataset-split D --heldout 0.3 [--by hash|time] [--key F] --seed S` writes `D_dev` and
  `D_heldout`, ordinary datasets with lineage.
- **By hash** of the key (item id by default, or a field, so one fingerprint never lands on both sides): stable
  across versions.
- **By time**: the newest share is heldout.

### 7. The catalog, the CLI and MCP

- **The datasets page** groups and filters on tags, says where a dataset came from, and puts a version's profile
  beside its parent's.
- **`evh captures`**, and the read-only MCP tool of the same name.
- **The writing commands are not MCP tools** until 0.7.0's declarations and consent.

### 8. The triage fleet, end to end (the acceptance case)

The data, the references, the arms and the cost are in the application plan (`research/internal/PLAN_0.6.0_FLEET.md`).

1. **The decisions dataset.** The fleet's 236 Orrery decisions, each a signal plus the probe answers as of its
   time, labelled by how much evidence survives (33 exact; 91 with only the signal).
2. **The adapter** replays each decision through the fleet's own `investigate(signal, probe_table)`, with the arm's
   model. It disables the fleet's own tracing and tags every call as an evaluation. The fleet's code comes from a
   pinned checkout.
3. **The references:**
   - the owner's verdicts decide (`gold/`): the 42 issues, fixed or noise, as their close comments say;
   - the outcome mapping and the old fixture labels are shown as `silver/`.
4. **The goal.** `false_dismiss` is the primary measure, `false_alarm` and `escalated` are shown beside it, and
   cost and speed weigh in. No limits in v1.
5. **The de-duplication dataset**: the fleet's 100 signals through its pure dedup functions, no model, a
   regression guard.
6. **Continuous:** each month's decisions, captured exactly as the model saw them.

## Not in scope

A schedule, a server, state outside the project's files, a labelling interface, holding a project's private data,
write tools for agents (0.7.0).

## Alternatives considered

- **One flow, not a lane** (the first draft). Rejected: it changes what exists for everyone.
- **The harness keeping records private** (the first draft). Rejected: what to commit is the project's decision.
- **Vendor importers only as examples.** Rejected for `github` and `langfuse`: one install does everything.
- **GitHub's close reason as the outcome.** Rejected on the data: `COMPLETED` on 37 of 41 closes, whatever the
  close comment said.
- **A mapping language with paths, signed time windows and list quantifiers.** Rejected: the project computes
  flat fields, and the language stays small.

## Changes from the second draft

The changes, listed in the engineering plan's P10:

- importers come from `<data>/importers/` or `path:Class`, not `config.yaml`;
- `as_of` was dropped, since outcomes live in the capture;
- outcomes are read from the close comment, not the close reason;
- the mapping runs over flat fields;
- second references are `silver/`;
- `labels` became `tags`;
- the fleet's v1 is all 236 decisions, kept by evidence level, rather than 12 fixtures or "older decisions
  accepted as lost";
- the deciding reference is the owner's verdicts.

## Testing (when built)

- **`evh importer-check`** on every built-in importer, against recorded responses (no network in CI).
- **The lane end to end on `jsonl`.**
- **The reference route:** exactly one recommendation on the goal page.
- **The hidden-text marker test**, across every public surface.
- **The triage example:** offline with a stand-in model, then with real models.
