# PRD-006: Datasets, versions and item fields

- **Status**: Implemented (v0.4.0); frozen datasets since 0.1.0; FR4, what is inside a dataset: Implemented (0.4.5, unreleased)
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (dataset pages: versions, fields),
  [UXS-002](../uxs/UXS-002-inspector.md) (filter and break down by a field)
- **Related RFC**: [RFC-006](../rfc/RFC-006-item-fields-and-url-items.md)
- **Related ADR**: [ADR-0003](../adr/ADR-0003-item-fields-and-url-items.md)
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md)

## Summary

A dataset is a frozen list of items, each with the sha256 of its bytes: the comparison
contract. 0.4.0 adds three things around it. A new **version** records the version it was made
from and which items it adds, removes and changes. Items can carry **fields**, typed facts a
project declares (a title, a source, a duration, a language), kept in the frozen dataset but
outside its identity. And an item can live at a **pinned URL** instead of a committed file.

## Background & Context

A project that needs facts about its items used to keep a second registry beside the frozen
dataset, which drifted from it. Inputs a project cannot commit (audio, PDFs, a benchmark's
hosted copy) could not be frozen at all. And when a dataset grew, nothing linked the new
version to the old, so its history lived in commit messages. The harness stays generic: it
defines no field, a project declares its own
([Concepts: fields](../../harness/docs/CONCEPTS.md#fields-describe-an-item-they-do-not-identify-it)).

## Goals

- A dataset's identity is its items' ids and bytes, nothing else.
- A version says where it came from and what changed, and the catalog links the chain.
- A project's facts about its items live in the dataset, typed and checked.
- Correcting a fact invalidates no run.
- A comparison can be read per group of items ("better on long items, not on short ones") with
  the correction that grows with the number of groups.
- Field values stay off public pages unless the project says otherwise.
- Items that cannot be committed can still be frozen.

## Non-Goals

- The harness defines no field; `tags` stays as it is.
- Runs on different versions are never tested against each other.
- This repository's own experiments carry no fields: the truthful candidates are each item's
  gold class, and gold is not redistributed here ([ADR-0003](../adr/ADR-0003-item-fields-and-url-items.md)).

## Personas

- **The engineer with item metadata** (customer, language, length) who wants results per group.
- **The engineer with unshareable inputs** published at a stable URL.
- **The maintainer of a growing dataset** who adds items and wants the history kept.

## User Stories

- _As a maintainer, I can make `x_v2` from `x_v1` (`evh dataset-create --dataset-id x_v2 --from x_v1 …`)
  and see on both pages what was added, removed and changed._
- _As an engineer, I can declare my item fields once and attach their values from a CSV
  (`--fieldset ID --fields FILE`), and be refused on an undeclared column or a mistyped value._
- _As an engineer, I can correct a field later (`--update-fields`) without changing any run's
  fingerprint._
- _As an engineer, I can filter a comparison to the items whose field matches, or break it down
  by a choice or yes/no field, in the inspector or with `evh inspect --where … --by …`._
- _As an engineer, I can freeze items from URLs (`--manifest FILE`) and be refused when the
  bytes there are not the pinned ones._

## Functional Requirements

### FR1: Datasets and versions

- **FR1.1**: `evh dataset-create --dataset-id … --source-dir …` freezes items with their sha256;
  `evh dataset-materialize` builds a hash-checked copy.
- **FR1.2**: `--from DATASET_ID` records `derived_from`: the parent and the item ids added,
  removed and changed. `evh validate` V2 fails a version whose parent is gone.
- **FR1.3**: The catalog links versions both ways with what changed, and a version no arm has run
  on yet gets a page when it is linked to one that has. `evh datasets --dataset-id …` says the
  same.

### FR2: Item fields

- **FR2.1**: A field set is `data/fields/<fieldset_id>.yaml` (`schemas/fieldset.schema.json`): each
  field has a name, a type (`text`, `number`, `integer`, `boolean`, `date`, `duration`, `url`,
  `choice` with its values), a label, a description, and optionally `unit`, `required` and
  `public`.
- **FR2.2**: A dataset names one field set and each item carries values for its declared names;
  many datasets can share one field set.
- **FR2.3**: `dataset-create --fieldset ID --fields FILE` (CSV or JSONL keyed by `item_id`)
  refuses an undeclared column, a mistyped value, a value outside a choice, an unknown item and
  an empty required field; `--update-fields` replaces the values of a dataset whose items are
  unchanged.
- **FR2.4**: Fields are not the identity: a run's fingerprint hashes item ids and bytes only, and
  the dataset records `fields_sha256` beside them.
- **FR2.5**: `evh validate` V15 fails a field set that breaks its schema, fields with no field
  set or an unknown one, an undeclared or mistyped value, a missing required value, and a
  `fields_sha256` that does not match.
- **FR2.6**: The catalog's dataset page lists each field with its coverage, and summarises its
  values only when it is `public`. The local inspector shows every value, filters by any field
  and breaks a comparison down by a `choice` or `boolean` field, Holm-corrected over every group
  and arm together. A public deployment answers with public fields only.

### FR3: Items at a URL

- **FR3.1**: `dataset-create --manifest FILE` reads rows of `item_id`, `source_url`, an optional
  `source_sha256`, and field columns. With a hash the item is pinned as given; without one the
  bytes are fetched once and their hash becomes the item's identity.
- **FR3.2**: `dataset-materialize` downloads into a gitignored cache (`.cache/items/<sha256>`),
  checks the hash, and fails on a mismatch exactly as it fails on a changed file.
- **FR3.3**: Only http(s) URLs are fetched; any other scheme is refused before anything is read.

### FR4: What is inside a dataset (0.4.5)

- **FR4.1**: A reader sees what a dataset holds without the dataset being republished: its item
  count and lengths, each gold reference's shape (labels and their counts, entries per item, a
  record's fields, words per reference), and per item its length, its gold when the gold is a
  label, and a link to read it at its source. `evh dataset-profile` writes it where the dataset is
  materialized (`data/profiles/<id>.json`); committed, every catalog built anywhere shows it.
- **FR4.2**: No item text unless the repository already publishes it: `--with-text` is refused
  unless git has committed every item's file. A gold that is not labels is summarised, never listed.
- **FR4.3**: A link comes from the dataset, never a guess: an item's `source_url`, or a rows map a
  fetch step writes, matched by the item's sha256 (an id alone may recur in another dataset). Only
  http(s) links.
- **FR4.4**: The same in the terminal (`evh dataset-items`) and for an agent (the MCP tool).

## Success Criteria

- The tutorial's dataset carries fields (GUIDE steps 1 and 12), two of them public and one not.
- `harness/tests/test_fields.py` passes, and the browser check drives a filter and a breakdown
  (`make browser-check`).
- `harness/tests/test_dataset_profile.py` passes: shapes, links matched by sha256, the git guard on
  `--with-text`, the page section, and every page's footer command.

## Related Documents

- [RFC-006](../rfc/RFC-006-item-fields-and-url-items.md), [ADR-0003](../adr/ADR-0003-item-fields-and-url-items.md).
- [Runbook §2, freezing a selection](../../harness/docs/RUNBOOK.md#2-freeze-a-selection).
