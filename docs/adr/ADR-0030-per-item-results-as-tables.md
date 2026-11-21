# ADR-0030 — Per-item results as tables in the SQLite store; the files store stays JSONL

**Status:** Accepted (owner, 2026-11-15, [RFC-033](../rfc/RFC-033-per-item-results-as-a-model.md)); built in 0.8.0.
**Date:** 2026-11-16
**Detail:** [RFC-033](../rfc/RFC-033-per-item-results-as-a-model.md) (the design, its "As built" section for where the
build differs), [RFC-025](../rfc/RFC-025-runs-in-sqlite.md) (the SQLite store; its byte-for-byte mirror of a score's
rows is replaced here), `harness/docs/UPGRADING.md` (format 7)

## Context

A score set's per-item results (`predictions.jsonl`, one JSON line per item) were stored verbatim in both stores: as a
file, and in SQLite as one text value per line (table `rows`). On this repository's data the 101.8 MiB of row JSON was
56% key names and 16% punctuation; 37% of `_meta` was copied between the score sets of one run; the provider's whole
billing object and three run settings were a further 42 MiB (RFC-033). The owner's goal was "a
model that can be queried" in both layers, not only a smaller file.

## Decision

**Format 7, both stores.** A run's three settings (`generation_config`, `generation_requested`, `encoder_window`) that
every row of every score set of the run holds with one value are kept once, in `run.json`'s `call`, and leave the rows.
`_meta.usage` keeps `cost`, `prompt_tokens`, `completion_tokens` and, when nonzero, `cached_tokens` and
`cache_write_tokens`. `model/results.py` is the one definition; the migration (`m0007_results`) carries frozen copies,
as a migration must.

**The SQLite store keeps per-item results in tables**, replacing `rows`: `score_sets`, `metrics` (each name once),
`score_rows` (the item, its score-level `_meta`, `_extra`, and the fields that are not numbers), `score_values` (one row
per numeric field), `call_facts` (what a run's call to one item was, once per run and item) and `rows_partial` (the crash
checkpoint, verbatim). A row read back is the row written: the same dict, keys sorted, an integer still an integer.
Readers keep getting row dicts.

**The files store stays JSONL**, full rows, canonical lines, no new file per run. The two stores are compared on
canonical text (`row_line` of each row), not on bytes.

**The tables are built in the order of the run's time**, then the key (`started_at`, else `created_at`), and a score
set's id is its place in that order, so a run added since lands after every older one and a deploy's rsync of the
database stays small. The release database is sealed at 16 KiB pages.

## Consequences

**Positive.** Per-item results are queryable and each name is stored once: 82.0 MiB with indexes against 168.7 MiB for
`rows`, and the project's database 159.2 MiB against 246 MiB (34ce211fb). The release database is 128,581,632 bytes
(a7c49749a). `data/runs` of this repository went from 153,465,935 to 112,483,047 bytes (d853c6550). A new 5-item run
costs a deploy's rsync 4.3 MB when its name sorts first, 2.2 MB in the middle and 1.1 MB last (a7c49749a), against 228,
122 and 20 MB on the old `rows` table (18923f31c).

**Negative.** The slimmed billing detail only comes back from the provider. Format 7 rewrites every committed
`predictions.jsonl` that held `usage` or the settings (295 files on this repository): a large diff, committed with the
migration. Assembling a score set's rows from tables costs more than parsing its lines, which `meta=False` reads and the
kept-rows cache offset (view_bench medians of 3 interleaved runs, 0.86-0.96 of the baseline taken before format 7, 34ce211fb). A score set added to an
old run lands where that run is and moves the pages after it (26.6 MB for a run in the middle of the time order, 61.2 MB
for the oldest). Score-set ids are positions, not content: a release is always built from the files, and the two stores
are compared on canonical text.

**Neutral.** Adapters' `Result.meta` stays free-form; output texts, hashes, the fingerprint and the judging sets do not
change. `evh migrate` takes a project to format 7 (a SQLite project's tables are filled in one transaction, then the
database is vacuumed); there is no step back down, the backup is the rollback (ADR-0029).

## Alternatives considered

- **Compression of each score set** (measured 9.6 MiB): the smallest, and the rows stay opaque: nothing can be queried.
  Not chosen, and not both (owner).
- **The byte-for-byte mirror** (RFC-025: a text value per line, the files store's bytes in a table): simple to prove, and
  it keeps the repeated key names and the copied `_meta`. Replaced for per-item rows; `files` and `outputs` stay as
  they were.
- **Any constant `_meta` key moves to the run** (the first draft's rule): it would also move parser output
  (`predicted`, `ranking`, `gates`) into `run.json`, which a release copies whole, so a hidden dataset's score-level data
  would leak, and it moves coincidences such as a run whose rows all end `finish_reason: stop`. Only the three named
  settings move (owner).
- **Hashed score-set ids** (built first, 34ce211fb): a new run's rows landed anywhere in the tables, 10.1 to 86.9 MB of
  rsync. Replaced by the order of time (owner).
- **`json_group_object` to assemble a row's values in SQL:** measured, 0.407 s against 0.380 s for the Python assembly it
  would replace (0.360 s with each set's rows scanned once); no gain, not adopted (RFC-033 "As built").
- **JSONB, integer item ids, SQL aggregation in the views, modelling `outputs` or `files`:** decided out of this
  change (RFC-033, "Not done").
