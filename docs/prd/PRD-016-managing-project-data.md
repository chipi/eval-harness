# PRD-016: Managing a project's data

- **Status**: Implemented (0.8.0)
- **Authors**: Marko Dragoljevic
- **Related RFCs**: [RFC-025](../rfc/RFC-025-runs-in-sqlite.md) (a project's data in files or one database, read and
  written through `_store`)
- **Related ADRs**: [ADR-0027](../adr/ADR-0027-the-data-page-writes-locally.md) (a write through the local server only,
  on this machine)
- **Related UX specs**: [UXS-004](../uxs/UXS-004-data-page.md) (the commands)
- **Related PRDs**: [PRD-004](PRD-004-catalog-and-inspector.md) (the catalog and the inspector),
  [PRD-017](PRD-017-workbench.md) (the Workbench, whose Settings screen is the page for this)

## Summary

A person or an agent can see everything a project keeps under `data/` and create, change and delete its settings
(systems, goals, fieldsets, judge scorers, model records, failure-mode lists, the validate policy) with four `evh`
commands, `data-ls`, `data-show`, `data-put` and `data-rm`, in either store. The Workbench's Settings screen
([PRD-017](PRD-017-workbench.md), W8) is the page beside them: it shows and saves the two policy files through the
same checks.

## Background & Context

RFC-025 lets a project keep its data in one SQLite database. Settings a person writes (a goal, a system) then have no
file to edit; `evh data-migrate` only moves files written elsewhere. These commands are the way in that works in
either store, with the same checks and the same words.

## Goals

- See what a project keeps under `data/`, in either store.
- Create, change and delete a setting from the command line, checked before it is saved.
- Delete a mistaken run whole, after seeing what goes.

## Non-Goals

- Editing what the harness writes: a run's record, a dataset, a reference set, a label set, a judge's verdicts. They
  are what was measured; they change only through the commands that make them.
- History, undo, review, or several people editing at once.
- Any write over a public server (`catalog-serve --public`), or from another machine.
- Python code: never in the database, never edited here.

## Personas

- **The project's owner**, on their machine, changing a goal's margin or adding a system without opening files.
- **An agent** doing the same through the commands.

## User Stories

- As an owner whose project is in a database, I change a goal's margin with
  `evh data-put --path goals/<goal>.yaml --set …`, see the check pass, and `evh goal-list` uses the new margin.
- As an owner, I add a system with `evh data-put --path systems/<id>.yaml --file … --new`, and
  `evh run --system <id> --dataset <id>` runs it.
- As an owner, I see what deleting a mistaken run removes (`evh data-rm --path runs/<run_id> --dry-run`), then delete
  it, and it is gone from the catalog's next build.
- As an agent, I do each of these with the four commands and read the same answers.

## Functional Requirements

1. `evh data-ls [PATH] [--find TEXT] [--offset N]` lists what the project keeps under `data/`, in either store: the
   overview (the store, every top-level folder with its file count), one folder (each entry with its size and modification
   time, 500 entries a page, `--offset` for the next), or the files whose path holds TEXT.
2. `evh data-show PATH [--text] [--fields]` shows one file's size, date and sha256 and its text; `--fields` a setting's
   fields, one `KEY: value` a line; `--text` its text only.
3. `evh data-put --path PATH [--by WHO]` creates or changes a setting (a system, a goal, a fieldset, a judge scorer, a
   model record, a failure-mode list or the validate policy), checked first: with `--file FILE` (`-` reads standard
   input) the whole text, or `--set KEY=VALUE` and `--unset KEY` for single fields (a dotted key, the value read as
   YAML), which keep the file's comments and the rest of its values. The check is that it parses, matches its schema
   and its id is its file name; nothing is saved on a problem. `--check` only checks; `--new` refuses a name already
   taken.
4. `evh data-rm --path PATH [--dry-run] [--by WHO]` deletes a setting, or a whole run (`runs/<run_id>`: its record,
   outputs, scores and rows); `--dry-run` says what would go. A delete cannot be undone.
5. Anything else under `data/` is written by the harness's own commands and is refused by `data-put` and `data-rm`.
6. The Workbench's Settings screen shows and saves the policy files through the same operations
   ([PRD-017](PRD-017-workbench.md), W8).

## Success Criteria

- A project in its database can be managed end to end without a file: create a system, run it, change a goal,
  delete a run.
- Every refusal (a schema error, a name already taken with `--new`, a path outside `data/`, a write to a
  harness-written file) has a test (`harness/tests/test_data_page.py`).

## Related Documents

[RFC-025](../rfc/RFC-025-runs-in-sqlite.md), [ADR-0027](../adr/ADR-0027-the-data-page-writes-locally.md),
[UXS-004](../uxs/UXS-004-data-page.md), [PRD-017](PRD-017-workbench.md).
