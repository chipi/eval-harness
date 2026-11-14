# UXS-004: The data page

- **Status**: Retired (2026-11-11, before 0.8.0's release): [PRD-017](../prd/PRD-017-workbench.md) decision 4 retires
  the page and throws away its pages, forms and routes; the terminal's `data-ls`, `data-show`, `data-put`, `data-rm`
  stay. Kept as the record of what was built and why (built 2026-11-06).
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-016](../prd/PRD-016-managing-project-data.md) (managing a project's data)
- **Related ADR**: [ADR-0027](../adr/ADR-0027-the-data-page-writes-locally.md) (the one page that writes, locally)
- **Related RFC**: [RFC-025](../rfc/RFC-025-runs-in-sqlite.md) (files or one database, `_store`)
- **Related UX specs**: [UXS-001](UXS-001-catalog.md) (shell, tokens), [UXS-002](UXS-002-inspector.md) (a live page
  served by `catalog-serve`), [UXS-003](UXS-003-cli-and-onboarding.md) (how commands speak)
- **Implementation paths**: `harness/catalog_assets/data.js` (the page), `harness/catalog_assets/data_form.js` (the
  form and a setting's fields), `harness/scripts/_settings_form.py` (schema, values, suggestions, the save that keeps
  comments), `harness/scripts/catalog_build.py`
  (`render_data`: the shell), `harness/scripts/catalog_serve.py` (`/api/data/*`), `harness/scripts/_data_page.py`
  (listing, checking, writing, deleting), `harness/scripts/data_ls.py`, `data_show.py`, `data_put.py`, `data_rm.py` (`evh data-ls`, `data-show`, `data-put`, `data-rm`);
  tests `harness/tests/test_data_page.py` (server and commands), `test_settings_form.py` (every setting of this
  repository through the form's save) and `test_data_page_browser.py` (the page)

## Summary

`data.html` is the **Configure** page of a project that keeps its data in SQLite and deploys it (`configure: true`):
every folder and file the project keeps under `data/`, and its **settings**, which a person can create, edit and delete
there. It is a live page like the
inspector: the catalog build writes its shell, `evh catalog-serve` fills it, and it writes only through that
server on this machine. Its state is in the URL, so a file or a folder can be linked to.

## Principles

- **Settings are edited; data is shown.** A setting is what a person decides (a system, a goal). Data is what
  the harness wrote (a run, a dataset, a reference set): the page shows it and names the command that writes it.
  Runs are the one kind of data the page deletes, whole.
- **A form, not a text editor.** A setting is entered in a form built from its kind's schema: one labelled field
  per key, the right control for its type, the schema's description as its help. Nobody types YAML on this page.
- **Check before save.** A setting is saved only when it matches its schema, and, for every kind but a system,
  its id is its file name: the same check `evh data-put --check` prints. Then the project's own check runs:
  `evh validate` before the write and after it, and anything it says after that it did not say before (a scorer
  with judges of one family, a system naming a goal that does not exist) puts the file back as it was and comes
  back as the save's problems. A setting the page saves is one `validate` passes. A system is exempt because
  its `system_id` is versioned (`data/systems/tickets_lead1.yaml` holds `tickets_lead1_v1`); the other kinds are found
  by their id (validate checks goals, scorers, models and failure-mode lists; a fieldset is read as `<id>.yaml`).
  `validate.json` is checked against `schemas/validate.schema.json`, written from what `validate` reads, and the goal
  policy (`goals/policy.yaml`, not a goal) against `schemas/goal-policy.schema.json`; the goals folder offers
  **+ New goal policy** when the project has none.
- **The catalog follows.** The catalog's other pages are built ahead of time; a line under the store badge says when,
  and **Rebuild the catalog** runs `evh catalog` in a child process into a folder beside the served one, then swaps
  it in, so the pages are served throughout. The line follows the rebuild (**Rebuilding…**, **Rebuilt in N s**, or
  the end of its output when it fails).
- **The file stays the person's.** Saving from the form changes only the values that changed: the file's comments
  and the order of its keys are kept (ruamel.yaml, owner yes 2026-11-06).
- **SQLite only, and deployed on purpose** (owner, 2026-11-06). A files project is edited in its files, so it never
  has the page: `configure: true` (or `EVAL_CONFIGURE=1`) with `store: files` is refused by `evh catalog` and
  `catalog-serve` and named by `validate` V23. A SQLite project chooses: the catalog only (the default), or the
  catalog and Configure.
- **Parity.** Every view and every action is a command: `evh data-ls`, `data-show`, `data-put` or `data-rm` (below).

## Scope

**In scope:** the overview, a folder, a file, editing and creating a setting, deleting a setting or a run.

**Non-goals:** editing harness-written data, or the fields of a setting a command writes (a model record's
onboarding and smokes); a text editor for YAML; history or undo; renaming or moving; uploads of binary files; any
write on a public server; Python code.

## Where it is

**Configure**, a menu item of its own at the end of the header, after Inspector; the catalog's menus (Data, Arms)
are what they are without it. Two deployments:

| | built | served |
| --- | --- | --- |
| **catalog only** (the default; every files project) | no Configure item, no `data.html`, no `data.js` / `data_form.js` | no `/api/data` route (404) |
| **catalog and Configure** (`configure: true`, SQLite) | the item, the page and its scripts | `/api/data` by a local `catalog-serve` only |

Even when built, the item is shown only when a local `catalog-serve` answers `/api/data/store` (with the data, or
asking for its token): on a public deployment or a page opened from disk it stays hidden, and a public server answers
no `/api/data` call. Since RFC-026 the routes need the server's token: the page is opened from the **Configure** link
`catalog-serve` prints, which sets it as a cookie.

To try it (while it existed): make serve with STORE=sqlite and CONFIGURE=1 served this repository's data from a SQLite copy
(`.build/serve-sqlite/`, made once; `FRESH=1` makes it again), so the tracked files are never touched; without
`CONFIGURE` the same copy is served as the catalog only; `make serve` alone is the files catalog.

## State in the URL

`data.html` (the overview), `data.html?path=<folder>` (a folder), `data.html?path=<file>` (a file),
`&edit=1` (the file's form), `data.html?path=<folder>&new=1` (a new setting in that folder). `path` is relative to
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
 │ systems       │ │ goals         │ │ fields        │ │ scorers       │
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
 data / systems                                                          [ + New system → ]
 ┌──────────────────────────────┬──────────┬──────────────────────┐
 │ name                         │ what     │ modified             │
 ├──────────────────────────────┼──────────┼──────────────────────┤
 │ tickets_lead1.yaml           │ 259 B    │ 2026-11-06 10:55 UTC │
```

- A breadcrumb (`data / systems`), then a table of the folder's entries: sub-folders first (with their file count),
  then files, by name.
- In a settings folder, **+ New <kind>** opens a new setting there.
- In a runs folder (`runs`, `runs-*`), a run is a row with its dataset, items and when it was made (its record's
  time; **not finished** when it has no `metrics.json`), and **delete**.
- A folder of more than 500 entries pages them, 500 at a time (**next**, **previous**).

## 03 A file

- The breadcrumb, then the file's size, date and sha256 (the first 12 characters, the whole on hover), and its kind.
- **A setting** is shown as its fields, the way the form lays them out, read-only: each key's label and value, a
  group's fields under its heading, a list's items one per row. A key the file does not set is not shown. **Edit**
  opens the form, **Delete** the delete panel. Below the fields, **the file as stored** (closed) shows its text.
- **Anything else** is its text, as written, in a monospace block that scrolls (a file that is not text says
  **binary, N bytes**), and what writes it: **Written by `evh run`** (a run's files), **Written by
  `evh dataset-create`** (a dataset), and so on; a run's file links **inspect this run**.

## 04 Editing a setting: the form

```text
 data / systems / tickets_lead1.yaml   editing
 config_id *        [ tickets_lead1_v1            ]  The arm's identity; runs are named after it.
 dataset_id *       [ tickets_v1               ▾ ]  (the project's datasets)
 goal               [ tickets_summary          ▾ ]  The goal_id this arm is measured for.
 params *           provider   text    [ echo   ]  ×
                    sentences  number  [ 1      ]  ×
                    [ + add a parameter ]
 hypothesis         [ + add hypothesis ]
 [ Save ]  [ Cancel ]
```

- **Fields come from the schema.** Each key of the kind's schema is a row: its name as the label (`*` when
  required), the control, and the schema's description as help. Required keys come first in the schema's order,
  then the optional ones a file sets, then **more fields** (closed) with the optional ones it does not, at every
  level (a deployment's card has its own).
- **Controls by type.** A string is one line; a long-text key (`statement`, `decision`, `description`, `notes`,
  `why`, `rule`, `usage`, `what`, `differs_from_this_use`) is a box of a few lines. A number or integer is a number
  field. A boolean is a choice of **not set / yes / no**. An `enum` is a menu; a `const` is shown, fixed. A key that
  takes one of several types (a number or `baseline`, a backend name or any text, a string or `null`) is a line with
  its allowed words as suggestions; what is typed is read as a number when a number is allowed, `null` when null is.
- **Groups and lists.** An object with named keys is a group of fields under its key; an optional group the file
  does not set is a **+ add <key>** button. A list of strings or numbers is one field per item, each with **×**,
  and **+ add**. A list of objects is one card per item, each with **×**, and **+ add <item>** (a goal's datasets:
  **+ add a dataset**).
- **Free keys.** An object whose keys are the person's (an arm's `params`, a deployment's `server_settings`, a
  model's `settings_why`, validate's `floors`) is a table of rows: the key, the value's type (**text**, **number**,
  **yes/no**, **list**, **group**) and the value; a list or group value opens the same controls nested. **+ add**
  adds a row. An existing value keeps its type.
- **Suggestions from the project.** A field that names other data offers what exists: a `dataset_id` the project's
  datasets; `goal`, `superseded_by` its goals; `model_record` its model records; `deployment` the deployments of the
  chosen model record; `hypothesis.against` its systems' `system_id`; `supersedes` its scorers; a
  `reference_id` its reference sets; validate's `committed` its runs folders. A suggestion is not a limit: any value
  may be typed, and the check says if it is wrong.
- **Written by a command.** A field a command writes is shown read-only with **written by `evh model-onboard`**
  (a model record's `capabilities`, a deployment's `onboarding` and `checked_at`) or **written by `evh arm-smoke`**
  (`smokes`), a group of them folded behind that line; saving keeps it as it is.
- **The id.** For every kind but a system the id is the file name, so an existing setting's id is shown, fixed
  (renaming is not supported). A system's `system_id` is a field like the others.
- **Save** checks first. A problem is shown at its field, in red, and all of them are listed above the buttons, each
  a link to its field (**datasets › 1 › dataset id: required**); nothing is written until the check passes. Editing
  any field clears the list (it was the last save's). After a save the file view opens with **Saved. sha256 <first
  12>**, or **Nothing changed.** when the values are the file's.
- **Saving keeps the file.** Only changed values are written; comments, blank lines and key order stay. A long list
  written inline over several lines may come back on one line when its item changes. `validate.json` is JSON: it
  is written with two-space indents.
- **Cancel** leaves without saving; if anything changed it asks first, on the page: **Discard your changes?
  [Discard] [Keep editing]**.
- A system whose runs exist: the form says **N runs were made with this system; they keep the settings they
  recorded. A change applies to the next run.** (the file view says the first sentence).

## 05 A new setting

- **+ New <kind>** in a settings folder opens the same form, filled from the kind's template. The id field names the
  file (`goals/<goal_id>.yaml`); a system has a **file name** field of its own above `system_id`. **Create**
  checks and saves like Save; a name already taken is refused: **systems/x.yaml exists: open it to edit it.** After
  it, the file view opens with **Created.**

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
| Opened without the server's token (RFC-026) | **this page needs the server's token: open the Configure link `evh catalog-serve` printed when it started** |
| A job writes the same settings (RFC-026) | **not now: `<lock>` is held by `<job id>`; try again when it ends** (nothing is written) |
| A check fails | each problem at its field and in the list above the buttons; nothing is written |
| A write to a harness-written file | **`<path>` is written by `<the command that writes it>`; it is not edited here.** (for a dataset, `the dataset-* commands`) |
| A path outside data/ | **That path is outside the project's data.** |
| Python under data/ | shown read-only: **Code is never edited here.** |

## Parity with the terminal

| The page | The command |
| --- | --- |
| the overview, a folder | `evh data-ls [PATH]` |
| a file; a setting's fields | `evh data-show PATH [--fields]` |
| the form's Save, a field at a time | `evh data-put PATH --set KEY=VALUE … [--unset KEY …] [--check]` (KEY a dotted path, `datasets.0.role`; VALUE read as YAML: `3`, `true`, `null`, text) |
| Create, a whole file | `evh data-put PATH FILE [--new] [--check]` (`-` reads stdin) |
| Delete | `evh data-rm PATH` (a setting, or a whole run) |

## Checklist for a change to the data page

- Each view rendered by the browser test, with a setting edited in its form, created and deleted, and a run
  deleted, in a SQLite project that deploys Configure; a files project's catalog has no Configure item, page or route.
- Every settings file in the repository and the examples opens in its form, and saving it unchanged writes nothing.
- A save from the form keeps the file's comments: a test edits one value of a commented file and compares the rest.
- Every refusal above has a test, on the page and on the command.
- Every kind of setting created, changed and deleted through the page alone, `evh validate` passing on what it
  made, and in SQLite nothing on disk but the database.
- In the dark theme (the catalog's default) every page and the form paint dark; every label, help line, error and
  control's text at a contrast of at least 3.5 against its ground.
- The public server answers no `/api/data` call.
