# PRD-014: Datasets from production, and evaluating what production did

- **Status**: Built for 0.6.0 for FR1 to FR3, FR5, FR6 and the Captures page (2026-10-31, the capture window and
  sampling 2026-11-01), FR4 (labels from outcomes) FR7 (the recorded arm, agreement), FR8 (the rows view, in the terminal and the inspector), FR9 (picks) and
  FR10 (versions from picks) built
  ([RFC-023](../rfc/RFC-023-labels-and-references.md))
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (the Captures, Labels and dataset pages),
  [UXS-002](../uxs/UXS-002-inspector.md) (the rows view), [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the
  commands)
- **Related RFCs**: [RFC-019](../rfc/RFC-019-datasets-from-production.md) (captures),
  [RFC-023](../rfc/RFC-023-labels-and-references.md) (labels, the recorded arm, picks, versions)
- **Related ADRs**: [ADR-0019](../adr/ADR-0019-capture-lane.md), [ADR-0022](../adr/ADR-0022-references-are-promoted-labels.md),
  [ADR-0023](../adr/ADR-0023-picks-and-governed-versions.md); [ADR-0020](../adr/ADR-0020-second-references-are-silver.md)
  (superseded by ADR-0022)
- **Related PRDs**: [PRD-002](PRD-002-references.md) (labels and references), [PRD-005](PRD-005-goals-and-rounds.md)
  (the deploy sheet), [PRD-006](PRD-006-datasets-versions-fields.md) (datasets, versions, fields)

## Summary

A project improves a system by measuring it on what the system actually meets. The owner's flow (2026-11-01):
establish references and work in rounds on the datasets you have; deploy what you settle on; let it run; take
**datasets from production** (all of it, a sample, a selection); **evaluate on them how production works**; and,
after many such evaluations, make the **next version** of a key dataset from a few production records that would
most help, and re-establish its references. The lane reads records from a production system (an importer), keeps
them (a capture, sampled as they are read when the source is large), and freezes ordinary datasets from them;
evaluating them scores production's own decisions, the deployed config and candidates against labels, never by
making a reference; exploring the results row by row shows what to keep, kept as picks until a version is made.

## Background & Context

Records that live in a tracing system, a ledger or an issue tracker reached a dataset only through a script each
project wrote. The first live test on the triage fleet (2026-11-01) found what the lane lacked: a continued capture
took records outside the window it recorded; sampling happened after everything was captured, which cannot work
at a billion records a day; production's own decisions could not be scored, only its model re-run; and there was
no way to label new items, see what was worth keeping, or keep it. The case the lane is designed on: an agent fleet
that triages observability signals into GitHub issues, every decision in a ledger, every issue closed with a
comment that says what it was.

## Goals

- A capture records exactly what was read: the importer and its code's hash, the query, the window, the sample
  rule, each record's id, link and hash; every record inside the window it records.
- A capture can be a sample of a large source, drawn as the records are read, and drawn again identically.
- A dataset made from a capture says how its items were chosen, and grows by versions.
- Production's own decisions are scored like an arm, beside the deployed config re-run and candidates.
- Labels on new items come from a person, a model or a rule over recorded outcomes; evaluating production never
  creates a reference.
- The rows that matter (production wrong, arms disagreeing, a gap in the governed dataset's coverage) are easy to
  find, and the ones worth keeping are kept until a version is made.
- Repeating it is one command from the previous capture; nothing runs in the background.
- Nothing changes for a project that never uses it; text can be kept off every public surface.

## Non-Goals

- **Online evaluation** (A/B tests, shadow or canary deployments): the harness evaluates what production did,
  offline, after it did it.
- **Detecting drift**: comparing one production dataset with the next shows a change after the fact; nothing
  watches for one.
- A schedule, a server, or state outside the project's files.
- **Labelling or picking in the pages**: the pages never write (PRD-004); they select and give the command.
- Holding or protecting a project's data: what is committed is the project's decision.
- Reading production stores: a project's own code exports what the lane reads (for triage, the fleet's
  `build_orrery_items.py`).

## Personas

- **The engineer running a system in production** (an agent fleet, a pipeline) who wants to know whether it still
  decides well, and whether a change (a model, a prompt, a rule) would decide better on real traffic.
- **The operator** whose actions after the fact (closing an issue as fixed or as noise) are the truest verdict.
- **The dataset owner** who keeps a governed dataset and grows it from what production shows.

## User Stories

- _As an engineer, I capture the last month of my system's decisions, or one in a thousand of them
  (`evh capture … --sample-rate 0.001 --seed 7`), and see what was read and when._
- _As an engineer, I freeze a dataset from a capture and score production's own decisions on it
  (`evh arm-from-capture`), beside the deployed config and a candidate._
- _As an engineer, I check that production ran what I promoted (`evh deploy-sheet`)._
- _As an operator, my close comments become labels through a mapping I can read (`evh label-from-capture`)._
- _As an engineer, I open the rows where production was wrong on something the governed dataset does not cover
  (`evh inspect --dataset-id D --rows --wrong-against S --new-vs V1`) and pick the ones worth keeping._
- _As a dataset owner, a month later I make v2 of my dataset from v1 and seven of the picks waiting
  (`evh dataset-extend V1 --dataset-id V2 --pick …`), and promote its labels._

## Functional Requirements

### FR1: Importers

- **FR1.1**: An importer is `records(query)`; a record is `{id, body, fields, created_at, source, labels, outcome}`.
  It receives the capture's sample rule as its `sample` option and may sample at the source.
- **FR1.2**: Built in: `jsonl`, `tsv`, `github` (issues, with each close and reopen event's actor and comment),
  `langfuse` (traces). A project's own: `<data>/importers/<name>.py` or `path.py:Class`.
- **FR1.3**: `evh importer-check` passes or fails an importer: ids unique and safe as file names, records
  well-formed, times parsed, hashes stable, and the window kept (every record inside the query's `[since, until)`;
  with no `since`, a read from the middle record's time returns nothing older).

### FR2: Captures

- **FR2.1**: `evh capture` writes the records and `capture.json` (importer, code hash, query, window, per record id,
  link, hash); never overwrites without `--force`; `--since-capture` continues from an earlier one, skipping what
  it holds by id.
- **FR2.2**: Every record must fall inside the window recorded: one outside it is named and nothing is written;
  `--late` keeps records older than `since` that the earlier capture never saw, listed as `late`.
- **FR2.3**: `--sample-rate R --seed S` keeps a record when the seeded hash of its id falls below R, as the records
  arrive; the rule is recorded (rate, seed, read, kept) and a continued capture keeps it.
- **FR2.4**: `evh capture-scrub` runs the project's own scrubber and records it.
- **FR2.5**: `evh captures` and the catalog's Captures page list them; `evh validate` V17 checks every record
  against its hash. Newer outcomes of records already held are a fresh capture of the same query.

### FR3: Datasets from a capture

- **FR3.1**: `evh dataset-from-capture` selects (`--where`, `--dedup`, `--one-per`) and writes an ordinary dataset;
  only the record's body becomes the item. It does not sample: the capture does.
- **FR3.2**: The dataset records how its items were chosen (`made_from`) and optional `tags`; its origin links to
  its capture in the catalog.
- **FR3.3**: `--from` makes a new version with the existing lineage.

### FR4: Labels from outcomes (0.6.0; replaces references from outcomes)

- **FR4.1**: `evh label-from-capture` applies an ordered mapping of rules to the capture's outcome fields; the first
  match labels the item, no match leaves it unlabelled; the result is a `rule` label set (PRD-002), whoever wrote
  the outcome.
- **FR4.2**: The set records the capture, the mapping and its hash, and the counts matched, skipped and unmatched.
  It is promoted to a reference only by `reference-promote`, like any set.

### FR5: Splits

- **FR5.1**: `evh dataset-split` writes dev and heldout as ordinary datasets, by hash (stable across versions,
  optionally grouped by a field) or by time.

### FR6: Text kept off public surfaces

- **FR6.1**: `text: hidden` on a dataset keeps every text derived from it (sources, outputs, label and reference
  texts, judge reasons, text and URL field values, source links) off every public surface: the catalog, the
  inspector, MCP, and a deployment's copy. Counts and scores stay.

### FR7: Production as an arm, and agreement (0.6.0)

- **FR7.1**: `evh arm-from-capture --dataset-id D --capture C --as NAME [--like CONFIG] [--field F] [--labels SET]`
  writes the arm's config (`provider: recorded`, the capture) and runs it with `evh run`: each item's output
  is the capture's record of the same id, read by the adapter's `recorded_output(record)` (the deployed arm's
  adapter, from --like) or from the record's field `--field`; no system is called, the cost is 0, the capture's
  sha256 is in the run's settings; scored, tested and compared like any arm. Refused before anything is written
  when there is no reader, or when the capture lacks an item.
- **FR7.2**: Two outputs are one decision when the adapter's `same(a, b)` says so (default: the same text; the
  triage adapter's compares the dispositions, not the reasons). `evh inspect --runs A,B --disagree` keeps the items
  where an arm decided differently from the baseline, the same filter the inspector page offers ("only where they disagree"), and
  `evh label-sheet --items disagree` reads the same hook.

### FR8: Exploring rows (0.6.0)

- **FR8.1**: `evh inspect --dataset-id D --rows` shows one row per item: its fields, production's decision, each
  chosen arm's decision, every label with its source, and the signals: **wrong** (`--wrong-against SET`),
  **disagree**, **split** (candidates disagree among themselves), **new** (`--new-vs V`: a field value the governed
  dataset has never had), **unlabelled**; each a filter and a sort, with `--where` and `--by`.
- **FR8.2** (0.6.0): The inspector's rows view shows the same; a selection of rows gives the `evh pick` and
  `evh label-sheet` commands for them. The page writes nothing.

### FR9: Picks (0.6.0)

- **FR9.1**: `evh pick --dataset-id D --item … [--for V …] [--tag k=v …] [--note "…"] [--by WHO]` appends to the
  project's one list, `data/picks.jsonl`: the item, its sha256, the dataset and capture it came from, its targets
  (several, or none yet; each a dataset), tags, note, who and when. The list is append-only; the latest line for an
  item wins (picking again retargets or retags); `--drop` takes it off the waiting list; a refused action writes
  nothing.
- **FR9.2**: `evh picks [--for V] [--tag k=v] [--json]` lists what waits, per target and "no target yet", each with
  where it came from and its labels by source ("none yet"); an MCP read tool. The target dataset's page shows its picks waiting.

### FR10: The next version of a governed dataset (0.6.0)

- **FR10.1**: `evh dataset-extend V1 --dataset-id V2 --picks|--pick ITEM …` makes V2 of V1's items and the chosen
  picks (`--picks`: those waiting for V1; `--pick ITEM` or `DATASET:ITEM`: any), each copied as it was picked (its
  sha256 checked); V2 records `extended_from` (V1, and per added item its dataset, capture and note) and the lineage
  `dataset-create --from` records; the picks used get a `used` line and leave the waiting list. An item already in
  V1 with the same bytes is kept once; one with other bytes is refused. V2 keeps V1's field set and tags, and is
  `text: hidden` when V1 or a picked item's dataset is.
- **FR10.2**: The picked items arrive with their labels (labels follow the item); nothing is promoted by the
  extension. The dataset page gives the command for the picks you tick.

## Success Metrics

- The triage example runs end to end: capture, dataset, production as an arm, labels, the deployed config and a
  candidate scored against them, the rows view, picks, a v2, a promoted reference, live on the fleet.
- Every existing test passes, and each FR above has its own.

## Release Considerations

- `dataset-from-capture --sample/--by/--seed` and `reference-from-outcomes` are removed (no shims); captures are
  not supported on Windows (record ids may contain `:`).
