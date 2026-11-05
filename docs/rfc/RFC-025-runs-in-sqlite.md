# RFC-025: Runs in SQLite, a project's choice

- **Status**: Accepted (2026-11-06), both phases in 0.8.0 S0 (owner: "All in 0.8"). Owner, 2026-11-06: "project has file mode by default but easy to
  change to sqlite"; the go to write this RFC the same day.
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-024](RFC-024-run-outputs-in-one-file.md) (one file of outputs, one reader, the store this RFC
  swaps); [RFC-002](RFC-002-run-records-and-derived-runs.md) (the run directory); `research/internal/PLAN_0.8.0.md` S0

## Abstract

A project keeps its runs as files, as today, unless it says otherwise: one key in its `config.yaml` puts a run's
outputs, and then its per-item rows, in one SQLite database, `data/runs.sqlite`. The run directories stay, with
`metrics.json` and `run.json`; what is per item moves. `evh run-migrate --to sqlite|files` moves a project either way,
checked by the signatures RFC-024's migration checked. SQLite is in Python's standard library: no dependency.

## Problem

- **Per-item data is files.** After RFC-024 a run is a handful of files (outputs.jsonl, predictions.jsonl,
  metrics.json, run.json); 10,000 items × 50 arms is a few hundred files, not 500,000. What files still cost: every
  read of one item across arms opens and parses each arm's whole file (the sheet at 10,000 items × 50 arms reads 50
  files of 10,000 lines to show one page), and concurrent writers (a sweep in parallel, the inspector reading while
  a run writes) rely on each writer owning its own files.
- **Readers.** RFC-024 left one module that reads and writes outputs, `_outputs.py`. The rows are not there yet: 18
  modules name `predictions.jsonl` (some in messages), 7 read it through `_runs.item_rows()`, the rest open it
  themselves (run, rescore, judge-score, sheet-import, import-run, family-test, holdout, leaderboard, cost-report,
  deploy-sheet, label-from-run, the catalog adapter and views, release, validate).
- **Who wants it.** A project whose runs are not committed (production-scale data, the triage fleet's) gains a single
  file to back up and indexed reads; a project that commits its runs (this repository) keeps files, which git can
  diff and review.

## Design

### The choice

```yaml
# <project>/config.yaml
runs:
  store: sqlite        # files (the default) or sqlite
```

or `EVAL_RUNS_STORE=sqlite`, which wins over the file. Every command reads the choice the same way (`_common`);
`evh init` writes no key, so a new project is files.

### The database

`data/runs.sqlite`, opened in write-ahead mode (`PRAGMA journal_mode=WAL`, `synchronous=FULL`), so readers never block
the writer and a crash keeps every committed row:

```sql
CREATE TABLE outputs (run TEXT, item_id TEXT, text TEXT NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY (run, item_id));
CREATE TABLE rows    (run TEXT, item_id TEXT, row TEXT NOT NULL, partial INTEGER NOT NULL DEFAULT 0,
                      PRIMARY KEY (run, item_id, partial));
CREATE TABLE meta    (key TEXT PRIMARY KEY, value TEXT);   -- the schema version, the store's own
```

- `run` is the run directory under `data/` (`runs/<id>`, `runs-judged/<scorer>/<id>`), the same key
  `derived.from_dir` names; a derived run still has no outputs of its own and reads its source's.
- An output is one row inserted and committed as it is produced (what one synced line is today); `finish()` is a
  no-op, the order being the dataset's at read time.
- `rows` with `partial = 1` is the pass's checkpoint (today `rows.partial.jsonl`); finishing writes the final rows
  and deletes the partial ones in one transaction.

### Phase 1: outputs

`_outputs.py` gains a store interface with two implementations, `files` (today's) and `sqlite`; its functions keep
their signatures, so the twelve modules RFC-024 moved onto it change nothing. `run-migrate --to sqlite` copies each
run's `outputs.jsonl` into the table (each text's sha256 checked) and removes the file; `--to files` writes them back.

### Phase 2: rows

First the same step RFC-024 took for outputs: one reader for rows (`_runs.item_rows` and a writer beside it), every
module that opens `predictions.jsonl` moved onto it, and a test that fails on one built anywhere else. Then the
sqlite store under it, and `run-migrate` moves rows too. Queries across runs (one item's row in every arm of a goal)
get their own function, which the files store answers by reading each file and the sqlite store by one query.

### What stays files

`metrics.json` (the record, one per run, reviewed in git, read by every listing) and `run.json` (the run's identity,
written before the first item). A run is still a directory: listing runs, `derived.from`, the catalog's arm ids and
`--resume <run_id>` do not change.

### A release

A release copies `data/`; with the sqlite store it copies `runs.sqlite` and, for a hidden dataset's runs, deletes
their outputs and rows from the copy (what it does today by not copying `outputs.jsonl`).

## Not in scope

- A server database, or a database for anything but per-item data.
- Choosing per run: the store is the project's.
- Committing `runs.sqlite`: a project that commits its runs keeps files.

## Alternatives considered

- **Everything in SQLite, `metrics.json` too.** Every listing and the catalog would need the database; the records
  are small and reviewable as they are.
- **DuckDB or parquet.** Faster scans, but a dependency, and a single-file store with transactions is what the
  writers need.
- **A database per run.** As many files as runs again, and no query across runs.

## Testing

- The store interface's tests, run against both stores: append, a crash mid-pass, resume, a derived run reading its
  source's, signatures.
- `run-migrate --to sqlite` and back on a copy of this repository's runs: every output, row and V5 signature equal
  after the round trip.
- Two writers at once (a parallel sweep) and a reader during a run, on the sqlite store.
- S1's bench at 10,000 items × 50 arms on both stores.

## Decided

- Both phases in 0.8.0 (owner, 2026-11-06).
