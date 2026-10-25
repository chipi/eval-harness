# ADR-0003 — Item fields and items fetched from a URL (0.4.0)

**Status:** Accepted (2026-10-22)
**Date:** 2026-10-22
**Detail:** [PRD-006](../prd/PRD-006-datasets-versions-fields.md) (what and why),
[RFC-006](../rfc/RFC-006-item-fields-and-url-items.md) (types, checks, filters, fetching),
[UXS-001](../uxs/UXS-001-catalog.md#the-dataset-page), [UXS-002](../uxs/UXS-002-inspector.md)

## Context

A dataset item was a file and its sha256. Projects needed items they cannot commit (published at
a URL) and facts about items (title, source, duration), which they kept in a second registry that
drifted from the frozen dataset. The harness must stay generic.

## Decision

- **Items at a pinned URL**: `source_url` plus `source_sha256`, fetched into a gitignored cache
  and refused on a mismatch, exactly as a changed file is.
- **Item fields, declared in a field set** a project writes (`data/fields/<id>.yaml`); the
  harness defines no field.
- **Fields are not the identity**: the run fingerprint hashes item ids and bytes only; the
  dataset records `fields_sha256`.
- **Declared only**: `validate` V15 fails an undeclared or mistyped value.
- **Values stay off the static pages unless `public: true`**; a public inspector answers with
  public fields only.

## Consequences

A project's metadata lives in the frozen dataset, typed and checked, and a comparison can be read
per group with one Holm correction. This repository's own experiments carry no fields: the
truthful candidates are gold classes, which are not redistributed here.
