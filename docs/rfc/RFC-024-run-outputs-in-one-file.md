# RFC-024: A run's outputs in one file, read through one function

- **Status**: Proposed (2026-11-05), for 0.8.0 S (scale to 1,000–10,000 items). Owner's go to write it: 2026-11-05.
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-002](RFC-002-run-records-and-derived-runs.md) (the run directory, derived runs);
  [RFC-019](RFC-019-datasets-from-production.md) §4 (hidden text, which a release strips);
  `research/internal/PLAN_0.8.0.md` S1–S3

## Abstract

A run writes what the arm answered as one file per item, `outputs/<item_id>.txt`, and every derived run (a
re-score, a judging, a sheet import) copies all of them. At 10,000 items and 50 arms that is 500,000 files for the
measured runs alone; the committed tree already holds 94,795 output files, 70% of them byte copies of another run's.
This RFC puts a run's outputs in one file, `outputs.jsonl`, has a derived run read its source's instead of copying
them, and gives every reader one function to read an output through. The committed runs are migrated, byte for byte.

## Problem

Measured on 2026-11-05:

- **Files.** A run of 1,000 items is 1,004 files: 1,000 `outputs/<item>.txt` and four records. The 0.8.0 S1 bench
  (10,000 items, 50 arms) wrote 350,534 files before it filled the last inodes of the workstation's `/tmp`, a tmpfs
  capped at 1,048,576, and broke file creation there for every process on the machine until they were deleted.
- **Copies.** The committed tree has 736 run directories with outputs: 273 measured, 463 derived (283 re-scored, 89
  judged, 30 adjudicated, 29 silver, 17 repeats, 9 linux, 6 pair). Of their 94,795 output files only 28,055 are
  distinct (item, bytes) pairs: 66,740 (70%) are copies made by `rescore`, `judge-score` and `sheet-import`, which
  copy every `outputs/*.txt` of the source (rescore.py, judge_score.py, sheet_import.py). They are 89% of the 106,492
  files under `harness/data/`.
- **The checkpoint stays.** `outputs/_rows.jsonl`, appended during a pass so `--resume` can continue, is a second copy
  of `predictions.jsonl` and is kept after the run ends.
- **No one place reads an output.** Twelve modules build an `outputs/` path themselves: run, rescore, judge-score,
  judge-panel, label-from-run, label-sheet (whose `output()` the sheet and the inspector use), `_labels`,
  sheet-import, silver-calibrate, the catalog adapter, `_release` and validate (V5's output signature). A change of
  layout has twelve places to make, and a reader that misses one reads nothing.
- **Time is not why.** The S1 bench (PLAN_0.8.0 S, 10,000 items × 50 arms) spends its minutes in the statistics, not
  in files: reading outputs one file at a time cost 0.115 s for the 5,000 reads of a 5-arm sheet at 1,000 items
  (about 23 µs a file). The case for this RFC is the number of files, the copies and the twelve readers.

## Design

### One file per run

`outputs.jsonl` in the run directory, one line per item:

```json
{"item_id": "t00042", "text": "…the output, exactly…", "sha256": "<sha256 of the text's UTF-8 bytes>"}
```

- **Written as items are measured**: appended, one line per item, so a stopped run keeps every finished output and
  `--resume` reads them back (the live `outputs/<item>.txt` writes and `outputs/_rows.jsonl` go away).
- **Rewritten in dataset order when the run completes**, so the same run writes the same bytes (git diffs stay
  readable), and `_rows.jsonl` is deleted: `predictions.jsonl` is the rows.
- **`sha256` per line**: what judging sets already record (`outputs_sha256` over the texts), now written once; a
  reader can check a line without re-hashing the text.
- **Text exactly**: every committed output is valid UTF-8 (94,795 of 94,795), so JSON holds each byte for byte. An
  output that is not UTF-8 is refused at write time, naming the item.

### One reader

`_outputs.py`: `output(run_dir, item_id) -> str | None`, `outputs(run_dir) -> {item_id: text}`, `writer(run_dir)`
(append, then `finish()`), and `signature(run_dir)` (V5's digest, computed as now: the same value for the same bytes).
A run's file is parsed once a process and kept by its path and mtime, so the inspector's per-item reads do not
re-parse it. Every one of the twelve modules reads through it; a test fails on any `"outputs" / ` path elsewhere.

### A derived run reads its source's outputs

A derived run records `derived.from` already (RFC-002). It writes no outputs of its own: `output()` follows
`derived.from` to the run that measured them. What changes for each writer:

| writer | today | after |
| --- | --- | --- |
| `rescore` | copies `outputs/*.txt` | writes `predictions.jsonl` and `metrics.json` only |
| `judge-score` | copies `outputs/*.txt` | the same |
| `sheet-import` (judged runs) | copies `outputs/*.txt` | the same |
| `label-from-run` | reads `outputs/` | reads through `output()` |

`validate` refuses a derived run whose source is not in the tree (V7 already refuses a committed run with no record;
the new check names the missing source). A release copies the source of every derived run it copies.

### Migration

`evh run-migrate` (idempotent, `--dry-run`): for each run directory, `outputs/*.txt` into `outputs.jsonl` in dataset
order, each line's sha256 checked against the file it came from; a derived run whose outputs are byte copies of its
source's loses them (refused, naming the items, when any differs: then the derived run keeps its own file); the
checkpoint `outputs/_rows.jsonl` deleted when `predictions.jsonl` has the same rows. Before and after, for every run:
V5's signature, each judging set's `outputs_sha256`, and the catalog's per-item outputs are the same, checked by the
migration itself and by a test. No shim reads the old layout afterwards (no backward compatibility): a project upgrading
to 0.8.0 runs `evh run-migrate` once, as UPGRADING will say.

### A store behind the reader: a future opportunity (owner, 2026-11-05: no release planned)

Because every module reads and writes outputs through `_outputs.py`, the layout under it can be swapped without
touching them: files (`outputs.jsonl`, the default, diffable and committed) or, later, a SQLite database per project
(`sqlite3` is in Python's standard library: no dependency). A store would be chosen per project (a key in its config),
and `evh run-migrate --to sqlite|files` would move runs between the two, checked by the same signatures. What SQLite
would add: one file for a whole project's runs (no inode count at all), indexed reads by item across runs (the sheet
and the inspector at 10,000 items × 50 arms), and transactions for concurrent writers. What it costs: the committed
runs stop being reviewable as text in git, so it fits a project whose runs are not committed (production-scale data,
the fleet's), not this repository's. Not planned for any release; the reader's interface only keeps it possible.

## Not in scope

- Where runs live (`data/runs*/`), their names, `metrics.json` and `predictions.jsonl`: unchanged.
- Compression, sharding a single run's file, a database: 10,000 items × 15 KB at most is 150 MB in one file; the
  committed runs average 1 KB per output.
- The fingerprint: outputs are not in it, so no fingerprint moves.

## Alternatives considered

- **Keep per-item files, stop copying them in derived runs.** Removes 70% of the files today, but a measured run
  of 10,000 items is still 10,000 files, and the fourteen readers stay.
- **Hard links instead of copies.** Saves bytes, not inodes, and git stores them as separate files.
- **Outputs inside `predictions.jsonl`.** One file fewer, but every metric reader would parse every output text, and
  a re-score's `predictions.jsonl` would carry them again.
- **SQLite as the only layout.** Not diffable in git, and a committed tree of binary files is not reviewable in a
  PR. As an alternative store behind the same reader it stays open: see "A store behind the reader".

## Testing

- The migration on a copy of the committed tree: every V5 signature, every judging set's `outputs_sha256` and every
  output text read through `output()` equal before and after; file counts before and after.
- `run`, `--resume` after a stop mid-pass, `rescore`, `judge-score`, `sheet-import`, `label-from-run`, the catalog,
  the inspector and a release, each on the new layout.
- A test that fails when a module outside `_outputs.py` builds an `outputs/` path.
- S1's bench again at 1,000 and 10,000 items × 50 arms: files, and the timings above.

## Open for the owner

1. Migrate the triage fleet's data repository (chipi/fleet-eval-data) by the same command, in its own PR, when it moves
   to 0.8.0; or ask its session to.
