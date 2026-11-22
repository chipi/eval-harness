# ADR-0027 — One catalog page writes: the data page, on this machine only

**Status:** Accepted (owner, 2026-11-06); the page it governs is retired ([PRD-017](../prd/PRD-017-workbench.md)
decision 4). Its rules for a write (this machine only, the `X-EVH-Data` header, no other origin) govern
the API's calls instead ([RFC-026](../rfc/RFC-026-an-api-for-every-command.md)). Amended by
[ADR-0029](ADR-0029-one-model-two-surfaces.md): the server writes edits itself, in either store, gated by the API's token
and `X-EVH-Data`, not by `configure: true`.
**Date:** 2026-11-06
**Detail:** [PRD-016](../prd/PRD-016-managing-project-data.md), [UXS-004](../uxs/UXS-004-data-page.md),
[RFC-025](../rfc/RFC-025-runs-in-sqlite.md)

## Context

Every catalog surface is read-only ([UXS index](../uxs/index.md), rule 1): a decision a page suggests is shown as the
command that makes it. With RFC-025 a project can keep its data in one database, where a setting has no file a
person can edit; the owner asked for a small page to manage settings and data.

## Decision

*Amended: the page is retired with 0.8.0's Workbench. What carries on is its Status line's rules (this machine
only, `X-EVH-Data: 1`, no other origin) and the commands `data-ls`, `data-show`, `data-put`, `data-rm`, which
share the page's module (`_data_page`).*

- **The data page is the one page that writes.** It writes a project's settings (systems, goals, fieldsets, judge
  scorers, model records, failure-mode lists, the validate policy) and deletes runs. Everything the harness writes
  stays read-only, there as everywhere.
- **Only on this machine.** Its write calls (`PUT /api/data/form`, a setting's values; `DELETE /api/data/file`, a
  setting or a run; `POST /api/data/rebuild`, the catalog rebuilt) are served by `catalog-serve` in
  its local mode only (127.0.0.1, a Host naming this machine), and each must carry `X-EVH-Data: 1`, a header a page
  from another origin cannot send without a CORS preflight the server never grants. A public server (`--public`)
  answers no `/api/data` call at all.
- **One implementation.** The page and `evh data-ls`, `data-show`, `data-put`, `data-rm` call the same module (`_data_page`),
  which reads and writes through `_store`, so the page and the command line refuse the same things with the same
  words.
- **SQLite only, deployed on purpose** (owner). The page is the Configure menu of a SQLite project that
  sets `configure: true`; without it the catalog is built and served with no Configure part at all, and a files
  project can never turn it on (it is edited in its files).

## Consequences

- Rule 1 becomes "the catalog is read-only, but for the data page, which writes settings on this machine only".
- A setting changed on the page is checked against its schema, as `validate` would; a run made with a config keeps
  the settings it recorded (its fingerprint), so editing a config changes future runs only.
- A deployment is unchanged: its server is public and refuses the page's calls.
