# ADR-0003 — Item fields and items fetched from a URL (0.4.0)

**Status:** Accepted (2026-10-22). The owner approved A, B and C below and the three decisions as
recommended; everything here is 0.4.0 scope.
**Date:** 2026-10-22

## Context

A dataset item is a file on disk and its sha256, plus optional `tags`. The item schema is closed.
Two needs from a project that pins the harness do not fit:

1. **Items that live at a URL.** Some inputs are published files (audio, PDFs, a benchmark's
   hosted copy) that a project cannot or should not commit. Today they cannot be frozen.
2. **Facts about an item.** A title, a source, a duration, a customer, a language: a project
   that needs them keeps a second registry beside the frozen dataset, which drifts from it.

Neither need is specific to the project that raised it. The harness must stay generic: it
provides the mechanism, and a project brings its own fields.

## Decision

**A. Items fetched from a pinned URL.** An item gives `source_url` and `source_sha256` (instead of
a file under `source_dir`). `dataset-materialize` downloads it into a gitignored cache, checks the
hash, and fails on a mismatch, exactly as it fails on a changed file. The item's identity is
still its id and its bytes' hash; the URL is where to get them.

**B. Item fields, declared in a field set.**
- A **field set** is a project file, `data/fields/<fieldset_id>.yaml`, validated by the
  harness's `schemas/fieldset.schema.json`. It lists fields: a name, a type (`text`, `number`,
  `integer`, `boolean`, `date`, `duration`, `url`, `choice` with its `values`), a label, a
  description, optionally a `unit`, `required` and `public`.
- A dataset names one field set (`fieldset`), and each item carries `fields`: values for the
  declared names. Many datasets can share one field set.
- `dataset-create --fieldset ID --fields FILE` attaches the values from a CSV or JSONL keyed by
  `item_id`; `--manifest FILE` creates URL items, its extra columns becoming fields;
  `--update-fields` replaces the values of a dataset whose items are unchanged.
- The harness defines no field. `tags` stays as it is.

**C. In the catalog and the inspector.**
- The catalog's dataset page lists the declared fields and how many items fill each.
- The inspector shows an item's fields beside the outputs, filters a comparison to the items
  whose field matches, and breaks a comparison down by a `choice` or `boolean` field: the paired
  test per group, Holm-corrected over every group and opponent tested.
- The adapter protocol gains an optional `item_fields(dataset_id)`; the harness's own adapter
  reads the dataset file.

**The three decisions:**
1. **Fields are not the dataset's identity.** The run fingerprint hashes item ids and bytes only
   (`items_sha256`), so correcting a title invalidates no run. The dataset records
   `fields_sha256`, a hash of every item's fields, beside it.
2. **Declared only.** `validate` (V15) fails a value of an undeclared field, a value of the wrong
   type or outside a `choice`, a missing `required` field, a dataset naming a field set that
   does not exist, and a `fields_sha256` that does not match.
3. **Values stay off the static pages unless `public: true`.** The catalog shows a field's name,
   type and coverage; for a public field it adds a summary of its values. The local inspector
   shows every value. A public deployment of the inspector (`catalog-serve --public`) answers
   with public fields only, and refuses a filter or breakdown on any other: a filter's counts
   would otherwise reveal a hidden field's values.

## Consequences

- A project's metadata lives in the frozen dataset, typed and checked, instead of in a second
  registry.
- A comparison can be read per group ("better on long items, not on short ones") with the same
  test and a correction that grows with the number of groups.
- Datasets without fields are unchanged; the schema change is additive.
- Materializing a URL dataset needs the network once per item; the cache makes it once.

## Alternatives considered

- **Free-form metadata, no declaration.** Simpler, but a typo becomes a new field silently, and
  the inspector cannot know which fields to filter or group by.
- **Fields inside the identity hash.** Every correction of a label would invalidate every run.
- **A separate metadata file per dataset.** It is the second registry this replaces.
- **Fields specific to the project that asked.** The harness would stop being generic.
