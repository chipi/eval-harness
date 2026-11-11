# PRD-016: Managing a project's data from the catalog

- **Status**: Built for 0.8.0 (2026-11-06); its page retired before the release ([PRD-017](PRD-017-workbench.md)
  decision 4, 2026-11-11), its commands (`data-ls`, `data-show`, `data-put`, `data-rm`) kept. Asked for by the owner, 2026-11-06: "build simple CRUD UI for this",
  "do UXS and all you need to get it right"
- **Authors**: Marko Dragoljevic
- **Related RFCs**: [RFC-025](../rfc/RFC-025-runs-in-sqlite.md) (a project's data in files or one database, read and
  written through `_store`)
- **Related ADRs**: [ADR-0027](../adr/ADR-0027-the-data-page-writes-locally.md) (the one catalog page that writes,
  on this machine only)
- **Related UX specs**: [UXS-004](../uxs/UXS-004-data-page.md) (the page and its commands)
- **Related PRDs**: [PRD-004](PRD-004-catalog-and-inspector.md) (the catalog and the inspector)

## Summary

A person can see everything a project keeps under `data/`, and create, change and delete its settings (arm
configs, goals, fieldsets, judge scorers, model records, failure-mode lists, the validate policy), from a page beside
the catalog and from `evh` commands that do the same. The page is the Configure menu of a project whose data is in
its database (RFC-025) and that deploys it (`configure: true`): there it is how the project is managed at all, with
no files to open in an editor. A files project is edited in its files; its catalog has no Configure part.

## Background & Context

RFC-025 lets a project keep its data in one SQLite database. Settings a person writes (a goal, an arm config) then
have no file to edit; the only way in was `evh data-migrate`, which moves files written elsewhere. The owner asked
for a small CRUD page next to the catalog for users to manage their settings and data.

## Goals

- Browse every folder and file the project keeps, with sizes and dates, in a SQLite project that deploys the
  Configure pages (`configure: true`); a files project is edited in its files and has none.
- Create, edit and delete a setting, each change checked against the setting's schema before it is saved.
- Delete a run (its record, outputs and rows), which in the database has no folder to remove.
- The same from the command line (`evh data-ls`, `data-show`, `data-put`, `data-rm`).

## Non-Goals

- Editing what the harness writes: a run's record, a dataset, a reference set, a label set, a judge's verdicts. They
  are what was measured; they change only through the commands that make them.
- History, undo, review, or several people editing at once.
- Any write over a public server (`catalog-serve --public`), or from another machine.
- Python code: never in the database, never edited here.

## Personas

- **The project's owner**, on their machine, changing a goal's margin or adding an arm config without opening files.
- **An agent** doing the same through the commands.

## User Stories

- As an owner whose project is in a database, I open the data page, find `goals/support_triage.yaml`, change its
  margin, see the check pass, save it, and `evh goals` uses the new margin.
- As an owner, I add an arm config from the page, and `evh run --config data/configs/<new>.yaml` runs it.
- As an owner, I delete a mistaken run from the page, and it is gone from the catalog's next build.
- As an agent, I do each of these with `evh data-ls`, `data-show`, `data-put` and `data-rm`, and read the same answers.

## Functional Requirements

1. The page lists the store, every top-level folder of `data/` with its file count, and every file of a folder with
   its size and modification time; a filter finds files by name.
2. A file opens to its size, date and sha256; a setting to its fields, anything else to its text as written.
3. A setting is entered in a form built from its kind's schema (owner, 2026-11-06: "I don't want this to be a YAML
   editor"): a field per key with the right control, the project's datasets, goals and models suggested where a field
   names them. It can be edited, created and deleted. Saving runs the same check as `evh data-put --check` (it matches
   its schema, and its id is its file name), shows each problem at its field, and saves nothing on a problem; a save
   keeps the file's comments and changes only the values that changed.
4. A run can be deleted whole, after the page shows what goes (its files, outputs and rows).
5. Everything else is read-only on the page, which says which command writes it.
6. The page writes only through a local `catalog-serve` (127.0.0.1, this machine's Host), with a header no other web
   page can send, and never on a public server.
7. Every action is an `evh` command with the same checks and the same words.

## Success Criteria

- A project in its database can be managed end to end without a file: create a config, run it, change a goal,
  delete a run.
- Every refusal (a schema error, a write over a public server, a write without the header, a path outside `data/`,
  a write to a harness-written file) has a test.

## Related Documents

[RFC-025](../rfc/RFC-025-runs-in-sqlite.md), [ADR-0027](../adr/ADR-0027-the-data-page-writes-locally.md),
[UXS-004](../uxs/UXS-004-data-page.md).
