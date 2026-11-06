# RFC-025: A project's data in SQLite, a project's choice

- **Status**: Accepted (2026-11-06), minimal version first (owner). The first version moved a run's outputs and rows
  only; that part is built and is part of this one. Owner, 2026-11-06: "project has file mode by default but easy to
  change to sqlite"; "one database in project for all its data"; "catalog reads from it all data and inspector as
  well"; "SQLite mode is SQLite mode"; "minimal version first".
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-024](RFC-024-run-outputs-in-one-file.md) (one reader for outputs, the pattern repeated here);
  `research/internal/PLAN_0.8.0.md` S0

## Abstract

A project keeps its data as files, as today, unless its `config.yaml` says `store: sqlite`. Then everything under
`data/` lives in one SQLite database, `data/project.sqlite`, and every command, the catalog and the inspector read and
write it there. Python code is never in the database. `evh data-migrate --to sqlite|files` moves a project either way.
SQLite is in Python's standard library: no dependency.

## Design

- **The setting**: `store: sqlite` in the project's `config.yaml`, or `EVAL_STORE=sqlite` (wins over the file).
  Default `files`.
- **One module**, `_store.py`, reads and writes everything under `data/`, addressed by its path relative to `data/`
  (`datasets/tickets_v1.json`, `runs/arm_v1_x/metrics.json`). The files store is the filesystem as today. Every module
  moves onto it, and a test fails on a path under `data/` built anywhere else.
- **The database**: `data/project.sqlite`, write-ahead logged. A table of files (path, bytes, sha256), and a run's
  outputs and rows in the per-item tables already built (one committed insert per output and row).
- **Python code** (`*.py`) under `data/` stays a file in both stores.
- **Moving**: `evh data-migrate --to sqlite|files`; every file read back and compared by sha256 before the old copy
  is removed.
- **validate** in SQLite mode skips the checks that ask git what is committed (nothing in the database is in git) and
  says so. **A release** copies the database with a hidden dataset's text removed.

## Not in scope (minimal version)

Anything else: no settings screen, no history, no export or import, no extra commands.

## Testing

- The store's tests on both stores; `data-migrate` there and back on a copy of this repository's `data/`, every file
  byte-identical.
- The full suite (`make verify`) on both stores.
- S1's bench on both stores, before S2.

## Built before this version, replaced by it

A run's outputs and rows behind `_outputs.py` in either store (kept); a database per runs folder, a `.store-id` token
per run directory, `runs.store`/`EVAL_RUNS_STORE` and `run-migrate --to` (replaced by the above).
