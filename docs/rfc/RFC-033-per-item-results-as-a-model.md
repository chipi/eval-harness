# RFC-033: Per-item results as a model, in both stores

- **Status**: Draft, revision 3 (owner, 2026-11-15: "goal is a model that can be queried, so we need to build both
  layers"; after the second review: "fix all blockers and high and other issues, we need clean work"). Revision 2
  answers every finding of the second review, revision 3 the re-review's four (ids, `json_group_object`,
  text-only callers, `_meta: {}`): ready to build.
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-024](RFC-024-run-outputs-in-one-file.md) (outputs and rows in one place),
  [RFC-025](RFC-025-runs-in-sqlite.md) (both stores; this RFC replaces its "byte-for-byte mirror" for per-item rows),
  [RFC-032](RFC-032-one-model-two-surfaces.md) (one model; step 9's SQLite release), [RFC-019](RFC-019-datasets-from-production.md)
  (§4, hidden datasets)

## Abstract

A score set's per-item results (`predictions.jsonl`, one JSON line per item) are stored verbatim in both stores: as a
file, and in SQLite as one text value per line. 56% of those bytes are repeated key names and 16% punctuation; 37% of
`_meta` is copied between the score sets of one run; the provider's whole billing object and three run settings are a
further 42 MiB. This RFC gives the results a model. **Format 7** (both stores) moves the run's settings onto the run and
keeps of the billing object what is read. The **SQLite store** keeps the results in tables (score sets, metric names,
one row per item, one value per metric, a call's facts once per run and item) instead of text, so they can be queried
and each name is stored once. Readers keep getting the same row dicts. The files store stays JSONL.

## Decisions (owner, 2026-11-15)

1. "Goal is model that can be queried, so we need to build both layers." Not compression (measured 9.6 MiB, rows
   opaque); not both.
2. The provider's billing detail is slimmed: kept `cost`, `prompt_tokens`, `completion_tokens`, `cached_tokens`,
   `cache_write_tokens` (owner: "3 ok" to keeping the last).
3. The files store stays JSONL with full rows; no new file per run.
4. Metric values in a long table (queryable).
5. What moves to the run: the three run settings `generation_config`, `generation_requested`, `encoder_window`
   (owner, "2 do it", after the review showed the generic "any constant `_meta` key" rule also moves parser output —
   `predicted`, `ranking`, `gates` — into `run.json`, which a release copies whole, so a hidden dataset's score-level
   data would leak; and moves coincidences such as a run whose rows all end `finish_reason: stop`).
6. The fleet's data repository (`chipi/fleet-eval-data`) migrates within this release, as its own PR: its whole move to
   0.8 (formats 1-7), after this repository's commit is pushed and its pin bumped.
7. The SQLite table of a call's facts is `call_facts` (not `calls`, which is already a `_meta` key: the judge adapter's
   per-pair records, 4,425 rows).
8. V9 checks a SQLite project in this release (today it skips everything there).
9. The release database uses 16 KiB pages. (Amended 2026-11-16: the tables are built in the order of the run's time, then
   the key, so a new run lands at the end of each and a deploy's rsync sends little; score-set ids are the place in that
   order, not a hash of the key: see Ids.)
10. The MCP container's memory: 512m (done, 6a91f51db).

Binding from before: one database for everything under `data/`, no Python in it, nothing invented beyond the scope
(RFC-025); no default store; no backward compatibility, committed data migrated, no shims; both stores equal and
solutions reusable for both; keep the vocabulary.

## What exists (measured 2026-11-15)

On a full SQLite copy of this repository's data (`~/.cache/evh-view-bench/sqlite/data/project.sqlite`, 246 MB; the
files layout 208 MiB by `du -sh`; a clean-HEAD SQLite release 237.8 MB after e86f3c004, files release 160.7 MB). Sizes
in MiB unless said:

| Table (dbstat) | On disk | Holds |
|---|---|---|
| `rows` + PK index + `rows_item` | 143.6 + 10.5 + 14.6 | 93,736 lines (711 of them the `n = 0` "rows exist" marker): 93,025 rows, 101.8 MiB of JSON |
| `outputs` + PK index | 43 + 4 | 46,800 output texts, 30.6 MiB |
| `files` | 28 MB | every other record: corpora 8.0, run/score JSON 3.7, verdicts 3.2, sources 3.0, materialized 2.8 (decimal MB) |

The 101.8 MiB of row JSON: key names 57.2 MiB (56%), punctuation and spacing 16.7, null/0/false 4.6, values 23.2.
`_meta` 64.9 MiB; 24.6 MiB of it (37% of `_meta`, 24% of row bytes) is a verbatim copy of the same run and item's
`_meta` in another score set (rescore and judge_score carry `_` keys over: `rescore.py:170`, `judge_score.py:1465-1468`).
`_meta.usage`: 53,720 objects, 31.8 MiB; slimmed, 5.6 MiB. The three run settings: 10.8 MiB, in 14 runs (31 score
sets), each constant over its run. Top-level fields: 102 names, 1,432,836 values, all numeric (104 of them integers:
`cost_usd`, `concision`, `coverage`, `rougeLsum`); only `item_id` is on every row; `_extra` absent on 65k rows, `{}` on 405.
All 93,025 rows are canonical (`json.dumps(sort_keys=True)`).

Code facts this design rests on (each checked):

- Rows are written through `_outputs` (`put_rows`, `write_rows`, `append_partial`/`append_row` for the crash checkpoint,
  `row_line`), and outside it by `import_run.py:264`, `sheet_import.py:371` and `tools/check_report_claims.py:268`
  (through `_outputs` too). `run.py:580` puts an adapter's `Result.meta` under `_meta`; `run.py:1487-1507` writes
  `run.json`, the first score, then the rows; `rescore.py:199` adds to `_meta`.
- Rows are read through `_runs.item_rows` (most readers), `_outputs.rows_text` (16 call sites outside `_outputs`),
  `_outputs.item_across` (one item across runs: only `catalog_views._items_out`, `evh inspect --items-out`, which is not
  served publicly), `_outputs.lines`.
- No stored hash covers prediction rows: the fingerprint (`_fingerprint.py`), judging sets (`judge_score.py:656`, over
  output texts), prompts, articles, manifests and ids. `family_test.py:124` hashes rows text for a cache key only.
- Nothing reads the three run settings from rows: they are named only in the release's filter (`_release.py:83-94`).
  Code reads only `usage.cost` from stored rows (`cost_report.py:71`, `rescore.py:215`, `tools/summeval_analysis.py:115`,
  `examples/.../reproduce.py:134`).
- `run.json` keys reach every score's record: `model/runs.py:224` (`split`) records a run key missing from the score's
  record as `unset`, except `RUN_ONLY` (`model/runs.py:40`); V1 validates the merged record against
  `schemas/metrics.schema.json` (`additionalProperties: false`).
- A migration "works on the stored data, never through the current model's code" (`migrations/__init__.py:8`).
- V9 skips a SQLite project entirely (`validate_tree.py:725-727`), its row counts and floors included.
- Resuming a run reads the prior score's rows and refuses rows without an `_extra` dict (`run.py:976`); the crash
  checkpoint may end in a torn line, which readers skip (`run.py:594-598`).
- SQLite: the local library is 3.53.4; the deploy image's is to be checked in step a.

## The model

| Concept | What it is | Files store (format 7) | SQLite store |
|---|---|---|---|
| **run settings** | `generation_config`, `generation_requested`, `encoder_window`: the run's, not an item's | `run.json` → `call` | `run.json` (in `files`) |
| **call facts** | per run and item, what the call was: `CALL_META` less the run settings (provider, response_model, usage, finish_reason, reasoning_tokens_reported, system_fingerprint, resumed_from_disk) | each row's `_meta`, as today | `call_facts`, once per run and item |
| **score-level meta** | per item and score set, what the parser made of the answer (`predicted`, `ranking`, `llm_raw`, `gates`, `calls`, ...) | each row's `_meta` | `score_rows.meta` |
| **values** | per item and score set, every numeric top-level field | top-level fields | `score_values` |

`CALL_META` and `RUN_SETTINGS` move from `_release.py` to the model (`model/results.py`, new): the one definition the
release filter, the split, the slim and the docs read.

**A row dict** (what `item_rows` yields) keeps its shape: `{"item_id", <values>, "_meta": {<call facts>, <score-level
meta>}, "_extra", <other `_` keys>}`, keys sorted. It no longer carries the run settings (nothing reads them there);
`run.json`'s `call` does. A row's own key always wins over one assembled from `call_facts`.

### Format 7 (both stores)

`migrations/m0007_results.py`. Self-contained, as the migration rule requires: it carries frozen copies of the three
run-setting keys, the slim function and the kept usage keys, and imports nothing from `model/`:

1. **Run settings.** For each run: if every row of every score set of the run holds the same value (canonical JSON) for
   a run-setting key, the key goes to `run.json` `call` and leaves the rows. Expected here: 14 runs, 31 score sets, the
   three keys (10.8 MiB). A run where the values differ keeps them in its rows (none here).
2. **Usage slimmed.** `_meta.usage` keeps `cost`, `prompt_tokens`, `completion_tokens`, and when nonzero
   `cached_tokens` (from `prompt_tokens_details.cached_tokens`) and `cache_write_tokens`; everything else goes.
   `None` and non-dict values pass through unchanged; the function is idempotent. Expected: 53,720 objects, 31.8 → 5.6
   MiB; 11 have no `cost`: slimmed like the rest, none is invented.
3. **Rows canonical** (already so here; the migration counts any it rewrites).
4. **SQLite projects**: the new tables are filled from the old `rows` table by raw SQL, in the same order `data-migrate`
   uses (below); `rows` is dropped.
5. `project.yaml` `format: 7`. `migrate --dry-run` prints each count.

`run.json` `call`: added to `schemas/metrics.schema.json` (an object) and to `RUN_ONLY` (`model/runs.py:40`), so a score
neither unsets it nor carries it into a derived record (`_record.py:178`). A test checks V1 passes with it and the first
score has no `unset: ["call"]`.

**Writes keep it so**, in both stores:

- `run.py` computes `call` from `result["predictions"]` in memory before `write_run` (`run.py:1487`), strips those keys
  from the rows, and writes the rows once. No second write, so no crash window between two.
- `_outputs` slims `usage` on every write (rows of any score set), so an adapter keeps returning what it likes and
  rescore/judge_score carry slimmed values.
- A score set added to a run later (rescore, judge_score, `sheet_import`): its rows are written as they come; a
  run-setting key equal to the run's `call` is stripped, one that differs stays in the row.

**Validation** (raw reads, not `item_rows`): a new check reports a stored row holding a run-setting key equal to its
run's `call`, or a `usage` key outside the kept set. Files: reads `predictions.jsonl` lines; SQLite: reads `call_facts`
and `score_rows.meta`.

### SQLite tables (replace `rows`)

```sql
score_sets   (id INTEGER PRIMARY KEY,               -- the order the sets were added: highest + 1 (below)
              key TEXT NOT NULL UNIQUE)             -- the score set's folder, data/-relative
metrics      (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)
call_facts   (run TEXT NOT NULL, item_id TEXT NOT NULL, meta TEXT NOT NULL,      -- JSON object
              PRIMARY KEY (run, item_id)) WITHOUT ROWID
score_rows   (id INTEGER PRIMARY KEY,               -- score_set * 2^20 + n
              score_set INTEGER NOT NULL, n INTEGER NOT NULL, item_id TEXT NOT NULL,
              facts INTEGER NOT NULL,               -- 1: its call facts are call_facts[run, item]; 0: none
              meta TEXT,                            -- JSON: score-level meta (+ any call fact that differs); NULL: no `_meta`
              extra TEXT,                           -- JSON `_extra`; NULL: absent
              rest TEXT,                            -- JSON of every field not stored above; NULL: none
              UNIQUE (score_set, n))
score_values (row INTEGER NOT NULL, metric INTEGER NOT NULL, value NOT NULL,     -- no type affinity
              PRIMARY KEY (row, metric)) WITHOUT ROWID
rows_partial (run TEXT NOT NULL, n INTEGER NOT NULL, line TEXT NOT NULL, PRIMARY KEY (run, n))  -- the crash checkpoint, verbatim
CREATE INDEX score_rows_item ON score_rows (item_id)
```

**Ids.** `score_sets.id` = the highest id plus one (the first is 1): the order the sets are added. `data-migrate --to sqlite`
(the release's, a project's) adds them, and writes the outputs, in the order of the run's time then the key: `started_at`
of run.json, else its `created_at`, as an instant (a zone counts; a time with none is UTC); a run with neither as an ISO
time comes first, by its key. A score set is its run's (`runs/<run>/scores/<key>`). So a release's ids are positions
in that order, one data gives one database (the files' creation order and the project's place do not matter), and a run
newer than every other lands at the end of `score_sets`, `score_rows`, `score_values` and `outputs`. Metric ids are the
order their names are first met in that order, a set's new names sorted. A project that writes a score set later
appends it the same way (highest + 1); a score set added to an old run sits with that run when the release is built
again, and the ids after it move up (a release is always built from the files; ids are not content, every comparison
of the two stores is on canonical text). A database whose highest id has no room for a set's 2^20 row numbers (a project
built when ids were key hashes, 43 bits) gives the lowest free id. `score_rows.id` = `score_set * 2^20 + n`: under
2^63; a set over 2^20 rows is refused. Ids that follow the order also shrink the database (a row id of 5 bytes, not 7 in
`score_values`' key): 128.5 MB against 136.3 MB at 16 KiB pages. How much a release delta shrinks was measured (step
e): a new run costs 1.1 MB (named last) to 4.3 MB (named first) of rsync, against 10 to 87 MB with hashed ids; a rescore
of an old run lands where the run is and moves the pages after it (27 MB for a run in the middle of the time order, 61 MB
for the oldest). The release is sealed with `page_size = 16384`. The `files` table is built in the same order (what is not under a run first, in path order,
then each run's files by its time): in path order a new run's files cost 4.8 MB when the name sorts first.

**What goes where** (one rule, tested case by case):

- `score_values`: every top-level field whose value is an `int` or `float`, not `bool`, finite, and within int64.
  An integer stays an integer, a float a float (no affinity; `-0.0` and `1.0` round-trip).
- `rest`: every other top-level field except `item_id`, `_meta` and `_extra`: `bool`, `None`, NaN, ±inf (as their JSON
  text, which Python's `json` reads back), integers beyond int64, strings, lists, dicts, and other `_` keys (`_commit`).
- `_meta`: absent → `meta` NULL, `facts` 0. Present → its call-fact keys compared with `call_facts[run, item]`: inserted
  if the pair has none; if the row's call facts equal the stored ones, `facts` = 1 and they leave `meta`; otherwise
  `facts` = 0 and the row's whole `_meta` stays in `meta`. `{}` stays `{}`, and a row whose `_meta` held only call
  facts (or only run settings, now on the run) keeps `_meta: {}`: `meta` = `'{}'` in SQLite, `"_meta": {}` in its file.
- `_extra`: absent → NULL, `{}` → `'{}'`.

The pair's `run` is the score set's run (`runs/<run>/scores/<key>` → `runs/<run>`). A score set whose folder is not
under a run (tests, scratch) gets no `call_facts`: its rows keep their `_meta` whole (`facts` 0).

**Writing** a score set: one transaction (the set's rows and values deleted, then inserted), metric names added sorted.
**A line that is not a JSON object with an `item_id` is refused** (`invalid-file`) for a score set, in both stores, so the
stores stay equal; the strict reader already raises on it. The crash checkpoint is exempt (verbatim, a torn last line
allowed). The files store's reader stays tolerant of a hand-edited file (as today, `_runs.py:80`), and validate reports it.

**Reading** a score set: its `score_rows` by id range, its `score_values` by `row BETWEEN`, its run's `call_facts`, each
dict assembled with keys sorted. `rows_text` is derived (`row_line` of each dict); the kept-rows cache keeps the parsed
dicts and the text together (the same text object, so `item_across` on the files path keeps its index), and is sized by
what it holds now, dicts being 2-3 times their text: budget-check in step c sets the bound. The callers that only want
text pay for the derivation and are measured in step c: `family_test.py:124` (a cache key), `_data_page.py:367` (line
counts), `validate_tree.py:408` and `:788` (V5, V9).

**Deleting** (`rmtree`, `forget_under`, `_store._per_item_tables` / `_per_item_under`, `_store.py:689-715`): a score
set's rows go through `score_sets.key` (a subselect); a run's `call_facts` with its last score set; metric names stay.
`SqliteStore._ready` (`_outputs.py:335`) checks the new tables; `ensure_tables` stops creating `rows`; `runs()` and
`row_runs()` read `score_sets`.

**`data-migrate`** files ⇄ sqlite compares every score set as canonical row text (`row_line` of the assembled dicts),
not raw bytes; to files it writes canonical lines. The sentences that promise "byte for byte" (`data_migrate.py:6`,
`RUNBOOK.md` §files-or-sqlite, `_outputs.py:19`) are rewritten.

### Performance

A prototype on this data (second review): reading every row from today's table and parsing it, 0.65 s; assembling the
same rows from the new tables, 0.97 s (+49%), before key sorting. The gate is `tools/view_bench.py` cold and warm within
±10% of step a on both stores. Planned in the build, measured in order until the gate holds: (1) assemble per score set
in one query (`score_values` grouped by row, `json_group_object` in SQL) instead of per row in Python; (2) keep
assembled dicts in the view cache (P1) so a warm view reads none; (3) skip `rest`/`meta` decoding for views that read
values only. A step does not land above the gate. Step (1)'s limits, tested by the review on SQLite 3.53.4: `1` stays
`1`, `1.0` stays `1.0`, 17-digit doubles and int64 are exact, but `-0.0` comes out `0.0` and keys follow metric-id
order. So if (1) is used, a `-0.0` value is stored in `rest` (as `bool`/NaN are), the dict is sorted after assembly, and
a round-trip test runs against the deploy image's SQLite version (step a records it), since `json_group_object`'s
number formatting is version-dependent.

### Validation: V9 in SQLite

V9's file listing stays a git check for the files store. In SQLite it now checks what the database is the record of:
every score set with a `metrics.json` has rows; its row count equals `n_items`; every committed arm meets its floor
(`FLOORS`). Tests plant each failure in a SQLite project.

### The release and hidden datasets

`_release.copy_data` stays a files copy followed by `data-migrate` (P1b), sealed with `VACUUM INTO` at 16 KiB pages. A
hidden dataset's rows keep the call facts and never score-level meta, `_extra` or `rest`'s non-numeric fields; its runs'
`run.json` `call` holds settings only (checked in `plan_problems`). `test_hidden_text.py` and `test_release_store.py`
check both stores; two renders of one commit give one sha256 (as now). Whether `CALL_META` should also name call-level
keys some adapters put in `_meta` (`model`, `prompt_sha`, triage-fleet's `gates`) is a leak-policy question for
RFC-019 §4, out of this RFC: today's list is kept.

### Not changed

`files` and `outputs` tables; output texts and their hashes; the fingerprint; judging sets; `metrics.json` means;
adapters (`Result.meta` stays free-form); the row dicts readers see, except the three run settings (now on the run); the
files store's layout.

### Not done (decided)

Compression; JSONB (text JSON stays readable; small gain); a schema for adapter `_meta`; integer item ids; SQL
aggregation in views (the files store could not share it); modelling `outputs` or `files`; history or export.

## Build order, each step with its proof

| Step | What | Proof |
|---|---|---|
| a | Baseline | `view_bench` both stores; dbstat per table; files `runs/` size; `cost-report` totals; `check_report_claims` 200/200; the deploy image's `sqlite3` version |
| b | `model/results.py`; format 7 in both stores (`m0007`, frozen); `run.json` `call` (schema, `RUN_ONLY`); writes (run.py in memory, `_outputs` slim, later score sets) | `migrate --dry-run`: 14 runs / 31 score sets / 3 keys hoisted, 53,720 usage objects slimmed; every score set's rows equal before/after except those keys; `cost-report` identical; V1 passes with `call`; no `unset: ["call"]`; V5 and outputs signatures unchanged; the new check passes; files `runs/` about 42 MiB smaller |
| c | `_outputs` API: dicts as the primitive, `rows_text` derived, malformed lines refused (checkpoint exempt), the cache keeping dicts and text; the 15 test files (16 `put_rows_text` calls) moved to rows, the few that write malformed lines to raw-file tests | `make check`; `make stores-check`; budget-check |
| d | SQLite tables, ids, the type rule, `facts`, deletes, `data-migrate`, `m0007`'s SQLite part; V9 in SQLite | data-migrate there and back: every score set's canonical text equal; dbstat per table (expected per-item results ~73 MiB with the wide ids, database ~150 MiB at 4 KiB pages: the review's prototype); `view_bench` within ±10%; each type case (bool, None, NaN, ±inf, int64 bounds, -0.0, 1 vs 1.0, `_meta` absent / `{}`, `_extra` absent / `{}`) round-trips; V9 failures planted |
| e | Release: 16 KiB pages | P1b's proof (catalog, 2,905 comparisons, 38 MCP calls, same bytes from both stores); two renders, one sha256; rsync bytes for no change and one new run first / middle / last, against today's 219 B / 228 / 122 / 20 MB |
| f | Fleet data repository, own PR | on a scratch copy first: `evh migrate --dry-run` with its own counts (formats 1-7 at once: it is unstamped, format 0, old layout), then the migrate; its gate is `evh validate` and `make catalog` (it has no CI); pin bumped to the pushed harness commit (pushing there needs the owner's approval) |
| g | Docs | RFC-025 "As built" amended; ADR-0030 (the results model); UPGRADING (format 7); RUNBOOK (tables, the read path, data-migrate's equality); `docs/DATA.md`; `harness/docs/INTEGRATION.md` (`Result.meta`: usage slimmed at write); `harness/skills/evh-compare-and-read/SKILL.md:75` (`_meta.gates`); CHANGELOG |

Test fixtures: a format-6 fixture project for `m0007` (beside `tests/fixtures/formats/0`), holding each case above.

Every step: all gates (`make quality`; `make check`, `stores-check`, `budget-check`, `browser-check`,
`browser-real-check`, `commands-check`, `guard-check`, `site-check`; `mkdocs build --strict`), mutation checks on its new
guards, commit, push, `ci-watch` green.

## Risks

- **Git diff**: format 7 rewrites every committed `predictions.jsonl` that holds `usage` or the run settings (about 42
  MiB less): a large diff in `harness/data`; gitleaks and GitHub's diff limits are checked on it before push.
- **Lossy slim**: dropped billing detail only comes back from the provider.
- **Assembly speed**: +49% before tuning (above); the gate decides.
- **Release delta**: B-trees order by id, so what is added in the middle moves the pages after it. The tables are built
  in the order of the run's time so a new run is added last; a rescore of an old run, a new run's name in `outputs`'
  index and its item ids in `score_rows_item` still move some pages; measured in step e.
- **Fleet repo**: its rows are unread here (NaN, strings, `_commit`?); its scratch migrate in step f reports them.
