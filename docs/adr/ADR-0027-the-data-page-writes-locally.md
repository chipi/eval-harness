# ADR-0027 — One catalog page writes: the data page, on this machine only (0.8.0)

**Status:** Proposed (owner, 2026-11-06: "build simple CRUD UI for this"); built in 0.8.0, awaiting the owner's acceptance.
**Date:** 2026-11-06
**Detail:** [PRD-016](../prd/PRD-016-managing-project-data.md), [UXS-004](../uxs/UXS-004-data-page.md),
[RFC-025](../rfc/RFC-025-runs-in-sqlite.md)

## Context

Every catalog surface is read-only ([UXS index](../uxs/index.md), rule 1): a decision a page suggests is shown as the
command that makes it. With RFC-025 a project can keep its data in one database, where a setting has no file a
person can edit; the owner asked for a small page to manage settings and data.

## Decision

- **The data page is the one page that writes.** It writes a project's settings (configs, goals, fieldsets, judge
  scorers, model records, failure-mode lists, the validate policy) and deletes runs. Everything the harness writes
  stays read-only, there as everywhere.
- **Only on this machine.** Its write calls (`PUT` and `DELETE` on `/api/data/file`) are served by `catalog-serve` in
  its local mode only (127.0.0.1, a Host naming this machine), and each must carry `X-EVH-Data: 1`, a header a page
  from another origin cannot send without a CORS preflight the server never grants. A public server (`--public`)
  answers no `/api/data` call at all.
- **One implementation.** The page and `evh data-ls`, `data-show`, `data-put`, `data-rm` call the same module (`_data_page`),
  which reads and writes through `_store`, so the page and the command line refuse the same things with the same
  words, in either store.

## Consequences

- Rule 1 becomes "the catalog is read-only, but for the data page, which writes settings on this machine only".
- A setting changed on the page is checked against its schema, as `validate` would; a run made with a config keeps
  the settings it recorded (its fingerprint), so editing a config changes future runs only.
- A deployment is unchanged: its server is public and refuses the page's calls.
