# RFC-006: Item fields and items at a URL

- **Status**: Completed (0.4.0, unreleased)
- **Authors**: Marko Dragoljevic
- **Related PRD**: [PRD-006](../prd/PRD-006-datasets-versions-fields.md)
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md#the-dataset-page) (the fields table),
  [UXS-002](../uxs/UXS-002-inspector.md#controls) (filter and breakdown)
- **Related ADR**: [ADR-0003](../adr/ADR-0003-item-fields-and-url-items.md)
- **Code**: `harness/scripts/_fields.py` (types, parsing, checks, digest, the pages' summary),
  `harness/scripts/_fetch.py` (pinned downloads), `harness/scripts/dataset_create.py`,
  `harness/scripts/materialize.py`, `harness/schemas/fieldset.schema.json`,
  `dataset.schema.json`; tests `harness/tests/test_fields.py`

## Abstract

A project declares the facts it keeps about its items in a **field set**; a dataset names one
field set and each item carries typed values for it. Values are checked when they are attached
and by `validate`, hashed into the dataset's `fields_sha256`, and kept out of the run fingerprint.
Separately, an item may be fetched from a URL and frozen by its sha256 like any file.

## Design

### Field sets

`data/fields/<fieldset_id>.yaml` (`fieldset.schema.json`): a list of fields, each with `name`,
`type`, `label`, `description`, and optionally `unit`, `required`, `public`, and `values` for a
`choice`. Parsing (`_fields.parse`), by type:

| type | accepted | stored as |
| --- | --- | --- |
| `text` | anything | string |
| `number` | a number (not a boolean) | int when whole, else float |
| `integer` | a whole number | int |
| `boolean` | true/false, yes/no, 1/0 | bool |
| `date` | `YYYY-MM-DD` | string |
| `duration` | seconds, or `h:mm:ss` | seconds, non-negative |
| `url` | an `http(s)://` URL | string |
| `choice` | one of its `values` | string |

### Attaching values

- `dataset-create --fieldset ID --fields FILE` reads a CSV or JSONL, one row per `item_id`, and
  refuses an undeclared column, a value that does not parse, a value outside a choice, an unknown
  item, and an empty required field.
- `--manifest FILE` creates items from rows of `item_id`, `source_url`, an optional
  `source_sha256` (or a `source_path` under `--source-dir`); other columns are field values.
- `--update-fields` replaces the values of an existing dataset whose items are unchanged.

### Identity

- The run fingerprint's `items_sha256` hashes each item's `item_id` and `source_sha256` only
  ([RFC-001](RFC-001-fingerprint-and-code-identity.md)): correcting a field invalidates no run.
- The dataset records `fields_sha256`: one hash over every item's id and its fields as sorted
  compact JSON, in item order. `fields_sha256` requires `fieldset` (`dependentRequired`).

### Validation (V15)

A field set that breaks its schema; a dataset naming a field set that does not exist, or carrying
fields without one; a value of an undeclared field, one that is not stored as its type or not in
its choices; a required field with no value; a `fields_sha256` that is not the hash of the fields.

### In the pages and the inspector

- `_fields.summary`: per field its coverage and, for a `public` field only, counts per value
  (choice, boolean), min, median and max (number, integer, duration), min and max (date), or the
  number of distinct values (text, url).
- The inspector's `/api/compare` takes `where=field:value` (repeatable) and `by=field`. A filter
  matches a choice, boolean, text, URL or date exactly, and takes `lo..hi` (either end open) or
  one number for a number, integer or duration. A breakdown groups by a `choice` (in declared
  order) or a `boolean` (yes, then no), counts items with no value apart, and tests with
  `stats.compare_by`: one Holm correction over every group and arm together.
- The adapter answers `item_fields(dataset)` → `{"fieldset": …, "values": {item_id: {…}}}`; an
  adapter without it shows no fields.
- In public mode the server sees only `public` fields, so a filter's counts cannot reveal a hidden
  field's values.

### Items at a URL (`_fetch`)

- An item with `source_url` is frozen by `source_sha256`; the URL is where to get the bytes.
  Without a hash in the manifest, `dataset-create` fetches the bytes once and pins their hash.
- `dataset-materialize` fetches into `.cache/items/<sha256>` (gitignored): a cached copy with the
  right hash is reused, bytes that hash to anything else are refused and deleted, never cached.
- Only `http` and `https` are fetched; any other scheme (a `file:///` row) is refused before
  anything is read. Transient failures are retried.

## Alternatives Considered

- **Free-form metadata, no declaration.** A typo becomes a new field silently, and the inspector
  cannot know what to filter or group by.
- **Fields inside the identity hash.** Every correction of a label would invalidate every run.
- **A separate metadata file per dataset.** The second registry this replaces.
- **Fields specific to the project that asked.** The harness would stop being generic.

## Testing

`harness/tests/test_fields.py`; the tutorial dataset carries three fields (two public);
`harness/tests/test_inspector_browser.py` drives a filter and a breakdown in Chromium.
