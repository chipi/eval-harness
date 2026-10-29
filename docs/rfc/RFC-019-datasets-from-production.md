# RFC-019: Datasets from production: a lane beside the method

- **Status**: Draft for review (2026-10-29, second draft), aimed at 0.6.0. Rewritten around one real case, a triage
  fleet; scheduled captures and a server are out of scope
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-006](../prd/PRD-006-datasets-versions-fields.md) (versions, item fields),
  0.7.0's PRD-012 (agents), 0.7.0's PRD-013 (dev and heldout, looks)
- **Related RFCs**: [RFC-006](RFC-006-item-fields-and-url-items.md) (field sets, URL items),
  [RFC-018](RFC-018-read-only-mcp-server.md) (the MCP server, 0.5.0) and 0.5.0's dataset profiles; on branch `070`:
  0.7.0's RFC-013 (declarations, consent), RFC-015 (dev and heldout, test looks), RFC-016 (MCP tools)

## Abstract

A project improves a system by measuring it on what the system actually meets. This RFC adds a **lane** beside the
method the harness already has: **capture** records from production systems with an **importer**, optionally scrub
them, **select** items from a capture into a new **dataset version**, take a **reference from outcomes** that
production recorded afterwards, and **split** a dataset into dev and heldout. The lane ends in the files the method
already reads (a dataset file, a reference file); from there it is the method as it is: materialize, run, compare,
goals. Every step is a command that reads files and writes files: no server, no state outside the project, no
schedule. A dataset can also be labelled so that **no text derived from it** appears on any public surface.

## Problem

- A dataset is frozen today from a directory of files (`dataset-create --source-dir`) or pinned URLs (RFC-006).
  Records that live in a tracing system, a ledger file or an issue tracker reach a dataset only through a script each
  project writes, with no record of what was read, which items were chosen and why, or a link back to the record.
- The case this is designed on: **a triage fleet**. An agent reads signals from observability (error-tracker issues,
  alerts), runs up to three probes against logs, metrics, traces and the source's state, and makes one decision per
  signal occurrence: dismiss, file an issue, escalate to a person, or clean up. Deterministic code before it (gates)
  and after it (filing and de-duplication against issues already open) shapes what reaches GitHub. Every decision is a
  row in a ledger file; since recently, a trace in a tracing system; every filed issue has a fate on GitHub.
  - It already has frozen **fixtures**: a signal, every probe answer it can ask for (the whole probe menu at default
    arguments plus what the model asked), and a hand-set label. A replay through its own `investigate(signal,
    probe_table=...)` measures the model's judgement, not drift in the stores.
  - What it lacks is what the harness has: datasets in versions with lineage, references kept apart from items,
    paired comparisons with their p, repeats, goals with limits (a false-dismiss rate of zero and an escalate rate
    under 5% is a goal with two limits), and a catalog. And what neither has: a reference taken from **what
    happened next** (the issue fixed, closed as a duplicate, closed as not planned, reopened; a dismissed signal filed
    later).
- Two datasets come from it: the **decisions** (one item per non-recurring occurrence, a model in the loop) and,
  second, **de-duplication** (deterministic, no model: signals against the open issues as they stood).

## Design

### 0. The lane and its boundary

- New commands only, under one word, **capture** (below). A project that never uses them sees no change.
- The lane writes ordinary harness files: a dataset (`data/datasets/<id>.json`, with lineage as versions have since
  0.4.0) and a reference (`data/references/...`). A run, a comparison, a goal or a page reads them as it reads any
  other.
- What existing files gain is optional and outside identity: a dataset's `labels`, `made_from` and `text`, a
  reference's `from_outcomes`. Absent, everything behaves as today. No existing command changes its arguments or its
  output for data without them.
- **Stateless**: every step reads files and writes files. "Continuous" is running a capture again: `--since last`
  reads the window the previous capture recorded. A schedule (cron calling the same commands) and a server are later
  questions, not this RFC.

### 1. Importers

- **The mechanism (core)**: an importer is a class with one method, `records(query) -> Iterator[Record]`. A
  `Record` is `{id, body | fields, created_at, source: {system, url}, labels, outcome}`: `id` is the record's own id
  in its system, `body` the item's content (text, or a JSON document such as a fixture), `outcome` what happened
  after (5). An importer is named in `config.yaml` (`importers: {fleet: {class: importers/fleet.py:Importer}}`) or
  with `--importer`. `evh importer-check NAME --query ...` is the contract test any importer passes: ids unique,
  bodies hashed stably, `created_at` parsed.
- **Built in**: `jsonl` and `tsv` (a file, one record per line or row; which columns are the id, the body, the date,
  and a filter), `github` (issues and their timelines: repo, label, state, window; the outcome is the issue's fate)
  and `langfuse` (traces and their generations: project, environment, name, window). Each built-in importer uses
  the standard library and `gh` only; they live in `evaluation_harness/importers/`, which the core never imports.
- **A project's importer** composes them. The fleet's joins three: its ledger (`tsv`), its frozen fixtures (`jsonl`
  or a folder of JSON), and GitHub (the outcome of each filed issue). The joining is the project's logic and stays in
  the project.

### 2. Captures

- `evh capture --importer fleet --query '{...}' --capture C` writes `data/captures/<C>/capture.json` (the importer,
  its code hash, the query verbatim, the window, when, how many records, each record's id, url and body sha256) and
  `data/captures/<C>/records/<id>.json`.
- What is committed is the project's choice, as for any data: the harness neither commits nor refuses. A capture is
  a candidate pool, never evidence: no run is scored on it and no page counts it.
- **Scrub, optional**: `evh capture-scrub C --command 'python scrub.py'` runs the project's own scrubber over every
  record and records the command, its hash and the count it reports. The fleet has one (secrets fail it; production
  identifiers become stable synthetic ones). The harness claims nothing about what a scrubber missed.

### 3. Select: a dataset version from a capture

- `evh dataset-from-capture C --dataset-id D [--from D_prev] [--where F:V] [--dedup exact|text] [--sample N --by F
  --seed S]` filters on fields, drops duplicates (exact body, or text with whitespace and case folded) and items
  already in `--from`, and samples N, stratified by a field when given, seeded. Each item's body is written where
  items' sources live, and the dataset records `made_from: {capture, query, filters, dedup, sample, seed}`.
- `--from D_prev` makes it a new version with 0.4.0's lineage (added, removed, changed): a dataset grows by versions,
  each earlier one frozen.
- **Labels**: `labels: {source, environment, purpose, owner}`, free text, shown and filtered on in the catalog
  (`evh datasets --label environment=prod`). Item fields (RFC-006) carry provenance per item (`occurrence_id`,
  `created_at`, `stage`, `frozen_at`).

### 4. A dataset whose text is never shown publicly

- `text: hidden` on a dataset: no text that comes from it reaches a public surface. Derived text counts: its items'
  sources, every arm's outputs on it, its references' texts and per-item gold labels, judge reasons, adjudication
  notes, its items' source URLs, and its text and URL field values. Counts, scores, ids and public-field totals stay.
- The surfaces (from a reading of the code, 2026-10-29): the catalog's dataset page and profile, the inspector's
  `/api/item` and `/api/compare`, the MCP tools (`dataset-items`, `inspect`), `evh dataset-items` and `evh inspect`
  in a public setting, and a deployment's render. One function answers "may this text be shown publicly, given the
  dataset it came from"; every surface asks it. A person's own local views show everything, as today.
- **A test that fails when a surface is missed**: a fixture project with one hidden dataset whose items, outputs and
  references carry a planted marker; it builds the catalog, serves the inspector and MCP publicly, renders a deploy
  copy, and fails if the marker appears in any answer or file.
- Two holes this closes in what exists: MCP `--public` runs `inspect` in its own process, where a `--where` or `--by`
  on a non-public field is accepted (`catalog_views.py`, the in-process `cs.compare`), so hidden field values can be
  read through counts; and a profile written `--with-text` is never checked again after it is written.

### 5. References from outcomes

- What production recorded afterwards is a reference: for a triage decision, the fate of what it did. An importer
  returns it as `outcome`; `evh reference-from-outcomes --dataset-id D --capture C --map outcomes.yaml` writes a
  reference whose per-item label comes from the mapping (outcome -> label), and records `from_outcomes: {capture,
  mapping, mapping_sha256, as_of}`. `authored_by` and every reader of it stay as they are.
- **As of a date**: outcomes change (an issue reopens). The reference is made from the outcomes read at `as_of`;
  reading them later makes a new reference, never an edited one.
- **The fleet's mapping**, to be confirmed: a filed issue closed as completed is right; closed as not planned, a
  false file; closed as a duplicate, a missed de-duplication; reopened, a case to read; a dismissal is wrong if the
  same fingerprint is filed later and right if it does not recur within N days; escalate and cleanup are judged by a
  person. An item whose outcome is not known yet (an open issue) has no reference; coverage is recorded as today
  (0.4.0 warns and records `reference_coverage`; nothing here changes that).
- A person's label outranks an outcome: the fleet's fixtures carry hand-set labels, which make a gold reference by
  the existing route (`reference-create` from a file); an outcome reference is a second reference on the same
  dataset, and the comparison between the two is itself informative.

### 6. Splits

- `evh dataset-split D --heldout 0.3 [--by hash|time] --seed S` writes two ordinary datasets, `D_dev` and
  `D_heldout`, each a version of `D` with lineage; a goal names them with the roles it has today. By hash of the
  item id and seed (default), a later version keeps every earlier item on its side and new items fall in proportion;
  by time, the newest share is heldout.

### 7. The catalog, the CLI and MCP

- The datasets page groups and filters on labels and says where a dataset came from (its capture and selection).
  A version's profile sits beside the one it came from (today the versions section lists items added, removed and
  changed only).
- `evh captures` lists captures and their counts, and the read-only MCP server gains the same tool (CLI parity).
- Write tools for agents wait for 0.7.0 (RFC-013's declarations and consent).

### 8. The triage fleet, end to end (the acceptance case)

1. **The decisions dataset, v1**: the fleet's twelve frozen fixtures for one project (July), eight of them labelled
   by hand. A project importer reads them; `dataset-from-capture` makes `triage_decisions`; the hand labels make a
   gold reference.
2. **An adapter** calls the fleet's `investigate(signal, probe_table=item["probes"])` with the arm's model and
   prompt version, and records the disposition per item. Per-item metrics from the fleet's own scorer: false-dismiss,
   silent-drop, escalate, autonomy-hit; a table miss counted as noise, not as the model's choice. Repeats (k=3) as the
   harness has them.
3. **A goal**: false-dismiss rate 0 and escalate rate at most 5% as limits, cost and latency beside quality.
4. **v2 and after**: recent decisions frozen now (their probes read at freezing time, said in each item's
   `frozen_at`), then, once the fleet keeps each decision's probe answers as it makes it, every decision exactly as
   the model saw it. Their reference from outcomes (5).
5. **The de-duplication dataset**: the fleet's frozen signals and the issues open at the time, the reference being
   which issue each signal should land on; an adapter calls the filing stage; no model, so exact and cheap.

Where the fleet's code comes from for the adapter (a pinned checkout of its repository today, its own package when
it is published) is the example's concern, not the harness's.

### What 0.6.0 ships, and what waits

- **0.6.0**: sections 0 to 7, and section 8's steps 1 to 3 and 5 as the example; step 4 as the data arrives.
- **0.7.0**: write tools and consent, runners on another machine, test looks against heldout.
- **Later**: a schedule, a server.

## Not in scope

- Scheduled captures, a server, state outside the project's files.
- A labelling interface for people.
- Holding or protecting a project's data: what is committed and where records live is the project's decision.

## Alternatives considered

- **One flow, not a lane** (the first draft): the capture steps woven into `dataset-create` and the reference
  commands, partial references compared on covered items only, `authored_by` widened. Rejected: it changes what
  exists for everyone, to serve a case only some projects have.
- **The harness keeping records private** (the first draft: records never committed, freezing refused without
  scrub rules). Rejected: what to commit is the project's decision; the harness offers a scrub step and the `text:
  hidden` label, and enforces nothing else.
- **Vendor importers only as examples.** Rejected for `github` and `langfuse`: one install should do everything
  (no extras to find); they need nothing beyond the standard library and `gh`, and the core never imports them.

## Open questions

Decided (2026-10-29): the lane beside the method, stateless, no server; the word **capture**; a generic importer
mechanism with `jsonl`, `tsv`, `github` and `langfuse`; the triage fleet as the case, its data public; decisions
first, de-duplication second; a small recent subset, older decisions accepted as lost; one `text: hidden` label
inherited by everything derived; the MCP `inspect --where/--by` hole fixed first in 0.6.0.

Open:

1. `github` and `langfuse` importers shipped in the package (proposed) or in `examples/importers/`.
2. Does a licence that forbids redistribution set `text: hidden` by itself?
3. The outcome mapping: N days without recurrence for a right dismissal; escalate and cleanup judged by a person
   only; the word for an outcome reference (gold is a person's, silver a model's; an outcome is neither).
4. Labels for the four unlabelled fixtures, set by the owner.
5. The fleet keeping each decision's probe answers (a change in the fleet's repository, the owner's go there).
6. Freezing the recent decisions now (read-only on the fleet's host), knowing their evidence is read today, not as
   the model saw it.
7. The example in this repository (`examples/triage-fleet/`, data committed after the fleet's scrubber), and its
   adapter's dependency on the fleet's code (a pinned checkout).
8. The fleet's project only, or its other projects' fixtures too.
9. The key and budget for replay runs: through the fleet's gateway alias or a key of their own.

## Testing (when built)

- `evh importer-check` on every built-in importer, against recorded responses (no network in CI).
- The lane end to end on `jsonl`: capture, scrub (a stand-in scrubber), select (dedup, a seeded sample that repeats),
  a version with lineage, a split that keeps earlier items in place, an outcome reference with its coverage and
  `as_of`.
- The hidden-text marker test across every public surface (4).
- The triage example in `examples/`: the decisions dataset, its adapter on recorded fixtures, its goal.
