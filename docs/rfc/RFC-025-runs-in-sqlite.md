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
- **Either files or the database, never both** (owner, 2026-11-06): in SQLite mode nothing under `data/` is a file.
  Python code is not data and is never in the database: a project in SQLite mode keeps its code outside `data/`, in
  git, and names it by path (`path.py:Class`, as dataset sources already allow). `data-migrate --to sqlite` refuses
  while `data/` holds a `.py` file, naming each.
- **Moving**: `evh data-migrate --to sqlite|files`; every file read back and compared by sha256 before the old copy
  is removed.
- **Getting data in**: in SQLite mode `data-migrate --to sqlite` is the only way a file a person writes (a goal, a
  config) gets into the database; a way to add and change them without files comes with the API of RFC-026 (owner,
  2026-11-06). The harness's own writes (runs, datasets it creates, labels, verdicts) go to the database directly.
- **validate** in SQLite mode skips the checks that ask git what is committed (nothing in the database is in git) and
  says so. **A release** copies the database with a hidden dataset's text removed.

## Not in scope (minimal version)

Anything else: no settings screen, no history, no export or import, no extra commands.

## Testing

- The store's tests on both stores; `data-migrate` there and back on a copy of this repository's `data/`, every file
  byte-identical.
- The full suite (`make verify`) on the files store. On the sqlite store, what reads a project: this repository's
  `data/` moved into a database in a separate copy, through validate, the catalog, the site check and the report
  checks. The whole suite on the sqlite store needs a way to put its fixtures in, so it comes with RFC-026.
- S1's bench on both stores, before S2.

## Built before this version, replaced by it

A run's outputs and rows behind `_outputs.py` in either store (kept); a database per runs folder, a `.store-id` token
per run directory, `runs.store`/`EVAL_RUNS_STORE` and `run-migrate --to` (replaced by the above).

## As built (0.8.0)

- **`_store.py`** does every read, write, listing and delete of a path. A path under `data/` in the sqlite store is a
  row of `data/project.sqlite` (table `files`: path, bytes, sha256, mtime); every other path, and every path in the
  files store, is the disk, as pathlib would do it, so moving the about 950 calls in `scripts/`, `harness/tools/`,
  `site/` and `examples/` onto it changed nothing in files mode. The move was an AST-located rewrite (formatting and
  comments kept); `tests/test_store.py` fails on path I/O in any module but `_store`, `_outputs` (its files store is
  the disk by definition), `data_migrate`, `run_migrate` (the layout before 0.8.0 on disk), `_common` (finding the
  project before any store exists), `stats` (standard library only; its cache is outside `data/`) and
  `skills_install` (the harness's own files).
- **A run** is its key under `data/`; its outputs and rows are the per-item tables built in the first version.
  `_store.rmtree` of a run removes its outputs and rows with its files, so a run made again at the same path starts
  empty. A run outside `data/` (a scratch folder) is the disk's, as every path outside `data/` is.
- **Never both**: V23 names a `data/project.sqlite` beside files, and files under `data/` beside the database. V7 and
  V9 read git and say why they do not apply; their floors (each committed runs folder holds at least N runs) have no
  counterpart in SQLite mode.
- **The release** reads the store and writes the same files layout from either store, a hidden dataset's text left
  out; the deployment is unchanged. (The design above said the release copies the database: a deployment that reads
  a database needs the prod deploy changed, which is not this RFC's.)
- **`catalog-serve`** serves the data tree from the database.
- **Verified on this repository's data**: `data-migrate` there and back, 12,001 files byte-identical; on the
  database, `validate` passes, `check_report_claims` verifies 200/200 claims, the site check is green, and the
  catalog's 928 pages equal the files catalog's but for the build time (one JSON file's keys in another order, equal
  content).
- **Not covered**: the full suite on the sqlite store (its fixtures need the way in RFC-026 brings); the examples'
  `fetch.py` scripts write sources as files under `data/`, which in SQLite mode `data-migrate` then moves in.
