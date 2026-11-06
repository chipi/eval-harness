# RFC-025: A project's data in SQLite, a project's choice

- **Status**: Proposed, revised 2026-11-06. The first version (accepted the same day: "All in 0.8") moved only a run's
  outputs and rows; that part is built and is now part of this one. Owner, 2026-11-06: "project has file mode by
  default but easy to change to sqlite"; then "one database in project for all its data", "catalog reads from it all
  data and inspector as well", "runs records also go to db", "data also goes to the same database".
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-024](RFC-024-run-outputs-in-one-file.md) (one reader for outputs, the pattern this RFC repeats for
  everything); [RFC-002](RFC-002-run-records-and-derived-runs.md) (run records, derived runs);
  `research/internal/PLAN_0.8.0.md` S0

## Abstract

A project keeps its data as files, as today, unless it says otherwise. With one key in its `config.yaml` everything
the harness keeps under `data/` (runs whole, datasets, sources and materialized copies, references, labels, judge
verdicts, captures, profiles, rounds, models) lives in one SQLite database, `data/project.sqlite`, and nothing else
under `data/`. The catalog, the inspector and every command read and write it through one module. `evh data-migrate
--to sqlite|files` moves a project either way, every file checked by its sha256. SQLite is in Python's standard
library: no dependency.

## Problem

- **Files at scale.** 10,000 items × 50 arms is hundreds of run directories, each read whole to show one item;
  concurrent writers (a parallel sweep, the inspector reading while a run writes) rely on owning separate files; a
  project's data is 12,000 files in 26 folders (this repository) that back up and move as 12,000 files.
- **One place.** A project that does not keep its data in git (production-scale data, the triage fleet's) wants one
  file to back up, copy and query, and the catalog and inspector reading it.
- **Readers.** About 300 places in about 40 modules build paths under `data/` themselves (`DATASETS / f"{id}.json"`,
  `glob("*/metrics.json")`, `DATA / "judge-verdicts"`). The first version of this RFC moved two kinds of file (outputs,
  rows) behind one module; everything else still reads the disk.

## Design

### The choice

```yaml
# <project>/config.yaml
store: sqlite        # files (the default) or sqlite
```

or `EVAL_STORE=sqlite`, which wins over the file (this replaces the first version's `runs.store` and
`EVAL_RUNS_STORE`, built today and unreleased). Every command reads the choice the same way (`_common.store()`);
`evh init` writes no key, so a new project is files.

### One module for the project's data

`_store.py`: every file under `data/` is addressed by its path relative to `data/` (`datasets/tickets_v1.json`,
`runs/arm_v1_x/metrics.json`, `judge-verdicts/s1/set/v.json`), with `read_bytes`, `read_text`, `read_json`,
`write` (atomic), `exists`, `list(prefix)`, `glob(pattern)`, `delete`, `mtime`. The files store is the filesystem as
today. Every module moves onto it, as RFC-024 moved outputs, and a test fails on a path under `data/` built anywhere
else. A run's outputs and rows keep the interface the first version built (`_outputs`), which the files store
answers from `outputs.jsonl` and `predictions.jsonl`.

### The database

`data/project.sqlite`, write-ahead logged (`journal_mode=WAL`, `synchronous=FULL`): readers never block the writer, a
crash keeps everything committed.

```sql
CREATE TABLE files   (path TEXT PRIMARY KEY, data BLOB NOT NULL, sha256 TEXT NOT NULL, mtime REAL NOT NULL);
CREATE TABLE outputs (run TEXT, item_id TEXT, text TEXT NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY (run, item_id));
CREATE TABLE rows    (run TEXT, partial INTEGER, n INTEGER, item_id TEXT, row TEXT NOT NULL,
                      PRIMARY KEY (run, partial, n));
CREATE TABLE meta    (key TEXT PRIMARY KEY, value TEXT);
```

- `files` holds every file that is not per item: a run's `metrics.json` and `run.json`, a dataset, a reference text, a
  verdict, a label. Paths are what they are today, so every record that names one (`derived.from_dir`, a label set's
  source, a manifest's files) is unchanged.
- `outputs` and `rows` are a run's per-item data as built: one committed insert per output and row, each row line's
  exact text, so `rows_text()` gives the same bytes in either store.
- A run is its key (`runs/<id>`, `runs-judged/<scorer>/<id>`): it exists while `files` holds its `run.json` or
  `metrics.json`. With no directories there is nothing to tie a run to; deleting one is `evh data-rm`, which removes
  its files, outputs and rows in one transaction.
- Listing (every run of a dataset, every verdict of a set) is a query on `path`, which is what a directory glob is
  today.

### Seeing and changing the data

With the files store a person reads `data/` with any tool. With the sqlite store the same through `evh`, both stores
(CLI parity): `evh data-ls [PREFIX]`, `evh data-cat PATH`, `evh data-put PATH FILE` (refuses a path the harness
writes itself, such as a run record), `evh data-rm PATH|RUN`, `evh data-export DIR` (the files layout, for a review
or a diff) and `evh data-import DIR`.

### Moving a project

`evh data-migrate --to sqlite` copies every file under `data/` into the database (outputs and rows into their
tables), reads each back and compares its sha256, and only then removes the files; `--to files` writes them back
byte for byte. It refuses while the project's store is not the target. A crash mid-move leaves both copies of what was
not yet removed, and the next run finishes it. `evh run-migrate --to` (built in the first version) becomes part of it.

### Git, validate and a release

- With the sqlite store the data is not in git: the database is the project's record, and backing it up is copying one
  file (SQLite's backup, consistent while a run writes: `evh data-backup PATH`). `evh init` ignores
  `data/project.sqlite*`.
- `validate`'s checks that ask git what is committed (V7, V9, V16's untracked texts, the release's refusal of an
  untracked file) apply to the files store. With the sqlite store, what would be committed is what the database holds,
  and those checks read it.
- A release copies the database, a hidden dataset's text removed from the copy (outputs deleted, rows cut to the call,
  reference texts and labels left out, with `secure_delete` and a `VACUUM`), and the deployment reads it with the
  sqlite store.

## Open for the owner

1. **The project's own settings and code.** Recommendation: they stay files in both stores, beside `data/` where they
   are: `data/configs/*.yaml`, `data/goals/*.yaml`, `data/fields/*.yaml`, `data/validate.json`, and the Python the
   harness imports (`data/scorers/`, `data/importers/`, `data/dataset_sources/`). A person writes them in an editor and
   reviews them in git, and Python can only import a file. Everything the harness writes or fetches goes in the
   database. The alternative, all of `data/` in it, means editing a config through `evh data-cat`/`data-put` and the
   harness extracting a scorer to a temporary file to import it.

## Build order

1. `_store.py` and the setting; every module onto it (files store only, nothing changes for a project), the guard
   test.
2. The sqlite store under it; `data-migrate`, `data-ls/cat/put/rm/export/import/backup`.
3. validate, the release and `evh init` for the sqlite store.
4. The whole suite on both stores: this repository's data moved into a database in a separate copy, `make verify`
   green there and here.
5. S1's bench at 10,000 items × 50 arms on both stores, before S2.

## Not in scope

- A server database, or more than one database per project.
- Choosing per folder or per run: the store is the project's.

## Alternatives considered

- **Runs only (this RFC's first version).** Built and tested; the owner wants the whole project in one database.
- **A database per runs folder.** Built for a few hours on 2026-11-06 so git could ignore throwaway runs' database
  like their folder; with the data out of git there is nothing to ignore, and it was not one database.
- **DuckDB or parquet.** Faster scans, but a dependency, and the writers need a single file with transactions.

## Testing

- The store's tests against both stores: every operation, a crash mid-write, two writers and a reader at once.
- `data-migrate --to sqlite` and back on a copy of this repository's `data/`: every file byte-identical.
- The full suite (`make verify`) on both stores.
- S1's bench on both stores.

## As built so far (0.8.0)

The first version's outputs and rows, now step 1's per-item part:

- `_outputs.py` holds both stores for a run's outputs and rows; `_runs.item_rows`, `_outputs.write_rows`, `rows_text`,
  `has_rows`, `append_partial` and `item_across` are what every module calls, and a test fails on a `predictions.jsonl`
  or `outputs/` path built anywhere else. `harness/tools/`, `examples/` and `site/figures.py` read through it too.
- Rows keep each line's exact text (`rows (run, partial, n, item_id, row)`, `n = 0` marking that rows were written),
  so a run's rows are the same bytes in either store and family-test's cache key does not move.
- `run-migrate --to sqlite|files` moves outputs and rows, each read back equal before the old copy goes; on this
  repository's 736 runs (46,800 outputs, 94,650 rows) the round trip gave back all 1,041 files byte for byte.
- A release cuts a hidden dataset's outputs and rows in the database copy (`secure_delete`, `VACUUM`).
- Two things built on the way are replaced by this revision: a database per runs folder, and a `.store-id` token in
  each run directory that tied a directory to its entries (a deleted and recreated run read the deleted run's
  outputs without it; with no run directories the case is gone).
- The full suite on the sqlite store, second run: validate passes; 10 failures, 3 of them caused by the per-folder
  databases, the rest test fixtures not yet moved and one not yet read.
