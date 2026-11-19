# UXS-004: Data management commands

- **Status**: Active
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-016](../prd/PRD-016-managing-project-data.md) (managing a project's data)
- **Related RFCs**: [RFC-025](../rfc/RFC-025-runs-in-sqlite.md) (files or one database, `_store`)
- **Related UX specs**: [UXS-003](UXS-003-cli-and-onboarding.md) (how commands speak),
  [UXS-005](UXS-005-workbench.md) (the Workbench)
- **Implementation paths**: `harness/scripts/ops/records.py` (`evh data-ls`, `data-show`),
  `harness/scripts/ops/project_jobs.py` (the operations `data-put` and `data-rm`),
  `harness/scripts/data_put.py`, `data_rm.py` (`evh data-put`, `data-rm`),
  `harness/scripts/_data_page.py` (what is a setting, what is harness-written, the refusals),
  `harness/workbench/live.js` (`screenSettings`)

## Summary

Four commands browse and manage the project's data files under `data/`, in either store (files
or one SQLite database), and the Workbench's Settings screen offers the setting-editing part as a
form. There is no catalog page for the data: the catalog is read-only.

- `evh data-ls [path]`: what the project keeps under `data/` (the overview, one folder, or the files a name matches)
- `evh data-show <path>`: a file's text, size, date and sha256, or a setting's fields
- `evh data-put --path <path> [--set KEY=VALUE …] [--file FILE]`: create or change a setting, checked first
- `evh data-rm --path <path>`: delete a setting, or a whole run

## Principles

- **Settings are edited here; everything else is written by the harness's own commands.** A setting is a system, a goal, a fieldset, a judge scorer, a model record, a failure-mode list, `validate.json` or `goals/policy.yaml`. Any other path is shown, never edited or deleted, and the refusal names the command that writes it.
- **Checked before saved.** `data-put` parses the file, matches it to its schema and checks that its id is its file name; on a problem nothing is saved.
- **A delete names what goes.** `data-rm --dry-run` says what would be deleted and deletes nothing; a delete cannot be undone.
- **Parity with the Workbench's Settings screen**, whose "Its policies" row does `data-show`, `data-put --check` and `data-put` through a form (`live.js`, `screenSettings`).

## Scope

**In scope:** the four commands and their options (`--find`, `--offset`, `--text`, `--fields`, `--set`, `--unset`, `--file`, `--new`, `--check`, `--dry-run`, `--by`, `--json`), and the Settings screen.

**Non-goals:** editing harness-written data (datasets, references, labels, a run's files, `config.yaml`), or a page in the catalog.

## Commands

### data-ls

```text
evh data-ls [--find TEXT] [--offset OFFSET] [--json] [path]
```

Lists what the project keeps under `data/`: the overview (the store, then the settings folders and the harness-written folders, each with its file count), one folder, or the files a name matches.

- **path** (optional): a folder under `data/` (default: the overview). A folder listing shows each entry's size and modification time and pages 500 entries at a time.
- **--find TEXT**: the first 200 files whose path holds TEXT, then `... and N more`.
- **--offset OFFSET**: the first entry of a long folder to list (for paging, 500 entries a page).
- **--json**: the answer as one JSON object.

### data-show

```text
evh data-show [--text] [--fields] [--json] <path>
```

Shows a file: its text, then its path, size, date and sha256 (first 12 characters), and whether it is a setting or written by a command. On a system it appends `· N run(s) were made with this system`: such runs keep the settings they recorded, and a change applies to the next run.

- **path**: the file, relative to `data/`.
- **--text**: its text only, nothing else.
- **--fields**: a setting's fields, one `KEY: value` a line.
- **--json**: the answer as one JSON object.

### data-put

```text
evh data-put --path <path> [--set KEY=VALUE …] [--unset KEY …] [--file FILE] [--new] [--check] [--by WHO]
```

Creates or changes a setting. KEY is a dotted path (`datasets.0.role`); VALUE is read as YAML (`3`, `true`, `null`, text). Give a whole file (`--file`) or fields (`--set`, `--unset`), not both; a field edit keeps the file's comments. It prints `saved <path> · N bytes · sha256 <12>`, `<path>: nothing changed` when the text is the same, or `<path>: N problem(s); nothing saved` when the check fails.

- **--path PATH**: the setting, relative to `data/`.
- **--set KEY=VALUE**: set a field (repeatable).
- **--unset KEY**: remove a field (repeatable).
- **--file FILE**: the file holding the whole new text (`-` is standard input).
- **--new**: refuse a setting that exists already.
- **--check**: only check it; save nothing.
- **--by WHO**: who acted (see [How a command speaks](UXS-003-cli-and-onboarding.md#how-a-command-speaks)).

### data-rm

```text
evh data-rm --path <path> [--dry-run] [--by WHO]
```

Deletes a setting (`goals/x.yaml`) or a whole run (`runs/<run id>`: its record, outputs, scores and rows).

- **--path PATH**: the setting or run folder, relative to `data/`.
- **--dry-run**: say what would go; delete nothing.

## The Settings screen

The Workbench's Settings screen (`#settings`, "Govern and maintain") has six rows, each one form with the command that does the same:

| row | what it does | command |
| --- | --- | --- |
| 1 Where the project keeps its data | reads the `data-ls` overview (the store, the database file and its size); counts what would move into the store `config.yaml` names, then moves it: "Move it" is offered only once the dry run counted something to move, and moving to the other store needs `store: <other>` set in `config.yaml` first | `evh data-migrate --to <store> --dry-run`, `evh data-migrate --to <store>` |
| 2 Bring the data to this release's formats | compare the formats, what it would change, migrate | `evh migrate --check`, `evh migrate --dry-run`, `evh migrate` |
| 3 Check the project | every integrity check: the failed ones listed, every check below | `evh validate` |
| 4 Its policies | `validate.json` or `goals/policy.yaml`: its text in a box, **Check it**, **Save** | `evh data-show <path>`, `evh data-put --path <path> --file - --check`, `evh data-put --path <path> --file -` |
| 5 Budgets | says a round's cap is set when the round opens | `evh round-open … --budget-usd N` |
| 6 Publish a dataset | a dataset and an `owner/name` repo | `evh dataset-publish --dataset-id <id> --to huggingface --query '{"repo": "owner/name"}'` |

A job started from the screen names who asked: the "Who you are" field at the top (kept in the browser). `config.yaml` is not edited on the screen.

## Refusals

| When | The command says |
| --- | --- |
| path outside `data/` (`..`, an absolute path) | That path is outside the project's data. |
| `data-put --new` on an existing setting | `<path>` exists: open it to edit it. |
| `data-put` or `data-rm` on harness-written data | `<path>` is written by `<the command that writes it>`; it is not edited here. |
| `data-put` or `data-rm` on Python under `data/` | `<path>` is code: code is never edited here. |
| `data-put` or `data-rm` on a judge scorer that has made judged scores | `<path>` is not changed: `<why>` (`<path>` is not deleted: `<why>` for `data-rm`). |
| `data-put` while the settings lock is held, or a second new setting of one name | `<lock>` is held by `<holder>`; of two new settings of one name, the second is refused. |
| `data-rm` on a file of a run | `<path>` is part of a run: delete the run instead. |
| `data-rm` on a path that is not there | No file `<path>` in the project's data. |
| `data-put` with both a file and fields | give a FILE, or fields with --set / --unset (not both) |
