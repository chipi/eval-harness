# UXS-004: The data page

- **Status**: Active (built in 0.8.0, 2026-11-06)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-016](../prd/PRD-016-managing-project-data.md) (managing a project's data)
- **Related ADR**: [ADR-0027](../adr/ADR-0027-the-data-page-writes-locally.md) (the one page that writes, locally)
- **Related RFC**: [RFC-025](../rfc/RFC-025-runs-in-sqlite.md) (files or one database, `_store`)
- **Related UX specs**: [UXS-001](UXS-001-catalog.md) (shell, tokens), [UXS-002](UXS-002-inspector.md) (a live page
  served by `catalog-serve`), [UXS-003](UXS-003-cli-and-onboarding.md) (how commands speak)
- **Implementation paths**: `harness/catalog_assets/data.js` (the page), `harness/scripts/catalog_build.py`
  (`render_data`: the shell), `harness/scripts/catalog_serve.py` (`/api/data/*`), `harness/scripts/_data_page.py`
  (listing, checking, writing, deleting), `harness/scripts/data_ls.py`, `data_show.py`, `data_put.py`, `data_rm.py` (`evh data-ls/data-show/data-put/data-rm`);
  tests `harness/tests/test_data_page.py` (server and commands) and `test_data_page_browser.py` (the page)

## Summary

`data.html` is the catalog's page for what a project keeps under `data/`: every folder and file, in either store,
and the project's **settings**, which a person can create, edit and delete there. It is a live page like the
inspector: the catalog build writes its shell, `evh catalog-serve` fills it, and it writes only through that
server on this machine. Its state is in the URL, so a file or a folder can be linked to.

## Principles

- **Settings are edited; data is shown.** A setting is what a person decides (an arm config, a goal). Data is what
  the harness wrote (a run, a dataset, a reference set): the page shows it and names the command that writes it.
  Runs are the one kind of data the page deletes, whole.
- **Check before save.** A setting is saved only when it parses and matches its schema, and, for every kind but an
  arm config, its id is its file name: the same check `evh data-put --check` prints. An arm config is exempt because
  its `config_id` is versioned (`data/configs/tickets_lead1.yaml` holds `tickets_lead1_v1`); the other kinds are found
  by their id (validate checks goals, scorers, models and failure-mode lists; a fieldset is read as `<id>.yaml`).
  `validate.json` has no schema: it must be a JSON object.
- **The same in both stores.** The page does not change with the store; a badge says which one the project uses.
- **Parity.** Every view and every action is an `evh data-*` command (below).

## Scope

**In scope:** the overview, a folder, a file, editing and creating a setting, deleting a setting or a run.

**Non-goals:** editing harness-written data; history or undo; renaming or moving; uploads of binary files; any
write on a public server; Python code.

## Where it is

In the header's **Data** group, after Reference sets: **Manage**. The link is shown only when the page is served by a
local `catalog-serve` that answers `/api/data/store`; on a public deployment or a page opened from disk it stays
hidden.

## State in the URL

`data.html` (the overview), `data.html?path=<folder>` (a folder), `data.html?path=<file>` (a file),
`&edit=1` (the file's editor), `data.html?path=<folder>&new=1` (a new setting in that folder). `path` is relative to
`data/`; one that leaves `data/` (`..`, an absolute path) is refused with **That path is outside the project's
data.**

## 01 The overview

```text
 DATA
 Project data
 What this project keeps under data/: its settings, which you can create, change and delete here, and the data
 the harness wrote, shown read-only.
 store: SQLite · data/project.sqlite · 60.0 KB

 [ find a file by name…                ]

 Settings  you can edit these
 ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
 │ 4             │ │ 1             │ │ 1             │ │ 0             │ ...
 │ configs       │ │ goals         │ │ fields        │ │ scorers       │
 │ ARM CONFIG    │ │ GOAL          │ │ FIELDSET      │ │ JUDGE SCORER  │
 └───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘

 Data  written by evh commands; read-only here
 datasets 1 file     materialized 7 files · materialized items     runs 4 files
```

- The **store line** under the lede: `store: files`, or `store: SQLite · data/project.sqlite · <size>`.
- **Settings** are tiles, one per settings folder: the number of files, the folder, what one is. A folder the
  project does not have yet is shown at 0 and opens empty, with **+ New <kind>** (its first file makes it).
  `validate.json` is a tile of its own (**validate policy**); at 0 it opens a new policy.
- **Data** lists the other folders with their file counts, and what they are when the name does not say it; each
  is a link.
- **Find** lists every file whose path contains the text (up to 200, then **and N more**).

## 02 A folder

```text
 data / configs                                                          [ + New arm config → ]
 ┌──────────────────────────────┬──────────┬──────────────────────┐
 │ name                         │ what     │ modified             │
 ├──────────────────────────────┼──────────┼──────────────────────┤
 │ tickets_lead1.yaml           │ 259 B    │ 2026-11-06 10:55 UTC │
```

- A breadcrumb (`data / configs`), then a table of the folder's entries: sub-folders first (with their file count),
  then files, by name.
- In a settings folder, **+ New <kind>** opens a new setting there.
- In a runs folder (`runs`, `runs-*`), a run is a row with its dataset, items and when it was made (its record's
  time; **not finished** when it has no `metrics.json`), and **delete**.
- A folder of more than 500 entries pages them, 500 at a time (**next**, **previous**).

## 03 A file

- The breadcrumb, then the file's size, date and sha256 (the first 12 characters, the whole on hover), and its kind.
- Its text, as written, in a monospace block that scrolls; a file that is not text says **binary, N bytes** instead.
- A setting has **Edit** and **Delete**. Anything else says what writes it: **Written by `evh run`** (a run's
  files), **Written by `evh dataset-create`** (a dataset), and so on, and for a run's file links **inspect this run**.

## 04 Editing a setting

```text
 data / goals / support_triage.yaml   editing
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ goal_id: support_triage                                                  │
 │ ...                                                                      │
 └──────────────────────────────────────────────────────────────────────────┘
 [ Check ]  [ Save ]  [ Cancel ]
 ✓ It passes the check: it parses, matches goal.schema.json, and its goal_id is its file name.
```

- A monospace text area with the file's text. **Check** runs the check and lists what it found, each problem on its
  own line with where it is (`datasets[0].dataset_id: 'x' is not of type 'object'`). **Save** is enabled once the
  text in the box has passed a check; editing again disables it until the next check. **Cancel** leaves without
  saving (if the text changed, it asks first, on the page: **Discard your changes? [Discard] [Keep editing]**).
- After a save the file view opens with **Saved. sha256 <first 12>**.
- An arm config whose runs exist: the editor says **N runs were made with this config; they keep the settings they
  recorded. A change applies to the next run.** (the file view says the first sentence).

## 05 A new setting

- In a settings folder, a name field (the file name without its suffix, the setting's id) and the text area,
  started from the kind's template with the id filled in. **Create** is enabled once the text has passed a
  check, like Save; a name already taken is refused: **configs/x.yaml exists: open it to edit it.** After it, the
  file view opens with **Created.**

## 06 Deleting

- **Delete** opens a panel on the page, never a browser dialog: **Delete goals/x.yaml? This cannot be undone.
  [Delete] [Cancel]**. For a run: **Delete the run runs/x? Its record and 2 files, 200 outputs and 200 rows go.
  This cannot be undone.**
- After a delete, the folder opens with **Deleted goals/x.yaml.** (for a run, **Deleted the run runs/x.**)

## Refusals and states

| When | The page says |
| --- | --- |
| Opened from disk, or the server is not local | **Managing data needs `evh catalog-serve` on this machine.** |
| A public server | the link is hidden; a direct visit says the above |
| A check fails | the problems, Save stays disabled |
| A write to a harness-written file | **`<path>` is written by `evh <command>`; it is not edited here.** |
| A path outside data/ | **That path is outside the project's data.** |
| Python under data/ | shown read-only: **Code is never edited here.** |

## Parity with the terminal

| The page | The command |
| --- | --- |
| the overview, a folder | `evh data-ls [PATH]` |
| a file | `evh data-show PATH` |
| Check | `evh data-put PATH FILE --check` |
| Save, Create | `evh data-put PATH FILE` (`--new` refuses a name already taken) |
| Delete | `evh data-rm PATH` (a setting, or a whole run) |

## Checklist for a change to the data page

- Each view rendered by the browser test, with a setting edited, created and deleted, and a run deleted, on both
  stores.
- Every refusal above has a test, on the page and on the command.
- The public server answers no `/api/data` call.
