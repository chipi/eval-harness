# A project's data in one database: how it all fits (0.8.0, design note)

Status: draft for the owner, 2026-11-06. Decided so far: a project keeps files by default and can switch to one
SQLite database for all its data (owner, 2026-11-06); **settings go in the database too (option A)**; **Python code is
always in git**; a small editing screen beside the catalog manages settings. This note is the whole picture; a UXS
for the screen, a PRD and the rewritten RFC-025 follow from it once the owner has read it.

## 1. The three kinds of thing in a project

| Kind | Who writes it | Changes how | Files mode | SQLite mode |
|---|---|---|---|---|
| **Code** | a person, in an editor | edited, reviewed | files in git | files in git (always) |
| **Settings** | a person, on purpose | edited; every edit kept | YAML in git | in the database, every edit in its history |
| **Data** | the harness (or a person through a command) | appended; frozen once written | files (git or not) | in the database |

Every folder under `data/` today, by kind:

| Folder | What it is | Kind |
|---|---|---|
| `configs/` | arm configs | settings |
| `goals/` | goals | settings |
| `fields/` | fieldsets (`fieldset-propose` drafts one, a person decides) | settings |
| `scorers/` | judge-scorer definitions (YAML) | settings |
| `rounds/` | rounds (opened, retired, closed by commands) | settings |
| `models/` | model records (onboarded once, edited by a person) | settings |
| `validate.json` | the project's validate policy | settings |
| `failure-modes/`, `tags/` | failure-mode lists (settings) and tag sets (data) | settings / data |
| `dataset_sources/`, `importers/`, adapters, scorer modules | Python the harness imports | **code** |
| `runs*/` | runs, whole (record, identity, outputs, rows) | data |
| `datasets/`, `sources/`, `materialized/`, `corpora/` | datasets and what they are made from | data |
| `references/`, `labels/`, `baselines/` | reference sets, label sets, promoted baselines | data |
| `judging-sets/`, `judge-verdicts/`, `judge-validation/` | judging | data |
| `captures/`, `profiles/` | captures from production, dataset profiles | data |
| `external/`, `.cache/` (outside data) | third-party downloads, caches | cache: stays files, never moved |

Code moves out of `data/` where it sits there today (`data/dataset_sources/`, `data/importers/`): to the project's
`code/` folder (name open), in git, in both modes. Settings and data that name code name it by path and sha256, as
runs already do (the fingerprint), so the database always says which code produced what.

## 2. What git does today, and what does it in SQLite mode

| Git today | SQLite mode |
|---|---|
| **History**: who changed a goal's margin, when, from what | Settings: every edit kept in the database (who, when, the text before and after, a note). Data: frozen once written (runs, dataset versions, label sets are never edited), so its history is its creation record |
| **Review**: a pull request diffs a config | `evh settings-export DIR` writes every setting as the YAML it is; a team that wants review keeps that export in git and diffs it. `evh settings-import DIR` takes a reviewed export back, each change an edit in the history |
| **Backup, sharing** | one file: `evh data-backup PATH` (consistent while a run writes) |
| **"What is committed"** (validate V7, V9, V16; the release's refusal of untracked text) | what the database holds is the record; those checks read it |

A setting is kept as its **text**, exactly as written, comments included (configs, goals and scorers carry long
comments that explain a decision), never as a parsed copy. The screen and the CLI edit that text and validate it
against the setting's schema before saving.

## 3. The settings screen, beside the catalog

`evh catalog-serve` today serves the catalog and the inspector, read-only, on 127.0.0.1 by default. The settings
screen is a third part of the same server:

- **Lists** configs, goals, fieldsets, scorers, rounds, models and the validate policy; each opens to its text, its
  history and what uses it (the goals an arm is in, the runs a config made, the arms a model record serves).
- **Edits** in place: the text, checked against its schema (`schemas/config.schema.json`, `goal.schema.json`, ...)
  before it is saved, with a note for the history. Shows what the edit touches before saving: "3 goals use this arm;
  12 runs were made with this config".
- **Never changes what was measured.** An edit to a config whose runs exist makes a new config version (the
  dataset rule of E3, applied to configs), so every run still points at the settings it ran with.
- **Creates** from a template or a copy; **retires** instead of deleting anything something else names.
- **Local only.** Writes are accepted from this machine (127.0.0.1 and the Host check the server already has),
  never on a `--public` server, which stays read-only.
- **Both modes.** In files mode the screen writes the YAML files (git is the history); in SQLite mode it writes the
  database. The screen does not depend on the store.
- **CLI parity**: every screen action is an `evh` command (`evh settings-ls`, `settings-show`, `settings-edit`,
  `settings-new`, `settings-retire`, `settings-history`), so an agent does what a person does.

## 4. Data in the database

- One file, `data/project.sqlite`, write-ahead logged: a crash keeps everything committed, readers never wait for the
  writer, the catalog and inspector read while a run writes.
- Every file the harness keeps today is addressed by the same path (`datasets/tickets_v1.json`,
  `runs/arm_v1_x/metrics.json`), so every record that names another (`derived.from_dir`, a label set's source, a
  manifest) is unchanged. A run is its key (`runs/<id>`, `runs-judged/<scorer>/<id>`); its outputs and rows keep the
  per-item tables already built (one committed insert per output and row).
- **One module** reads and writes it (`_store.py`), with the files store as today's filesystem; about 300 places in
  about 40 modules build paths under `data/` themselves today and move onto it, with a test that fails on a path
  built anywhere else (the RFC-024 pattern, already done for outputs and rows).
- **Seeing it** without the screen: `evh data-ls`, `evh data-cat`, `evh data-export DIR` (the files layout, for a
  diff or a hand-off), `evh data-rm RUN|PATH` (a run is no longer a directory to delete).

## 5. Moving between modes

`evh project-migrate --to sqlite`: settings and data into the database, every file read back and compared by sha256
before it is removed; code untouched. `--to files` writes everything back byte for byte, settings as their YAML text.
Their edit history has no files form (git takes over from there): open question 2 below. Refused while the project's store is not the target; a crash mid-move is finished by the next run.

## 6. Release, deploy, the catalog and agents

- **Release**: a copy of the database with a hidden dataset's text removed (outputs, item text, reference texts,
  label texts, notes; rows cut to the call), deleted pages zeroed, the file rebuilt. The deployment's catalog and MCP
  server read that copy.
- **Catalog and inspector** read everything from the store: the same pages in both modes.
- **Agents (MCP)**: the same commands; settings edits through the same `settings-*` tools, local only.

## 7. Open for the owner

1. **Where code lives**: a `code/` folder beside `data/` (scorer modules, importers, dataset sources, adapters), or
   left where each is today and only excluded from the move.
2. **Settings history on `--to files`**: exported beside the YAML (`.history/`), or dropped with a warning.
3. **Who** an edit records: the OS user and the machine, or a name the project sets (`evh settings-edit --as`).
4. **Release of settings**: published read-only (the catalog shows goals and arm configs today), or a subset.

## 8. Build order (after the UXS, PRD and RFC)

1. `_store.py` and the setting; every module onto it in files mode (nothing changes for a project); the guard test.
2. Settings as text with history: the `settings-*` commands, in both stores.
3. The SQLite store for data; `project-migrate`, `data-*` commands.
4. The settings screen in `catalog-serve`.
5. validate, release, deploy and `evh init` for both stores.
6. The full suite (`make verify`) on both stores, this repository moved into a database in a separate copy.
7. S1's bench on both stores, before S2.

## What is already built (kept, or replaced)

- Kept: outputs and rows behind one module, in either store (RFC-025's first version); tools, examples and the site
  reading through it; the tests' fixtures through the store.
- Replaced: the per-folder databases and the `.store-id` token (built 2026-11-06; not needed with one database and
  no run directories); `runs.store`/`EVAL_RUNS_STORE` (becomes the project's store setting).
- The full suite on the sqlite store, run 2: validate passes; 10 failures, 3 from the per-folder databases.
