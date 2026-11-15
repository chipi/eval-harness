# RFC-033: Per-item results as a model, in both stores

- **Status**: Draft for review (owner, 2026-11-15: "goal is a model that can be queried, so we need to build both
  layers"; plan first, then a second review before the build)
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-024](RFC-024-run-outputs-in-one-file.md) (outputs and rows in one place),
  [RFC-025](RFC-025-runs-in-sqlite.md) (both stores; this RFC replaces its "byte-for-byte mirror" for per-item rows),
  [RFC-032](RFC-032-one-model-two-surfaces.md) (one model; step 9's SQLite release), [RFC-019](RFC-019-datasets-from-production.md)
  (§4, hidden datasets)

## Abstract

A score set's per-item results (`predictions.jsonl`, one JSON line per item) are stored verbatim in both stores: as a
file, and in SQLite as one text value per line. 73% of those bytes are repeated key names and punctuation, a quarter
of `_meta` is copied between the score sets of one run, and two `_meta` fields (the provider's whole billing object,
and generation settings that are the run's) are 41% of the rest. This RFC gives the results a model: **format 7**
(both stores) moves what belongs to the run onto the run and keeps of the billing object what is read; the **SQLite
store** stores the results in tables (score sets, metric names, one row per item, one value per metric, a call's facts
once per item) instead of text, so they can be queried and each name is stored once. Readers keep getting the same
row dicts. The files store stays JSONL.

## Decisions (owner, 2026-11-15)

1. "Goal is model that can be queried, so we need to build both layers." Not compression (measured 9.6 MB, but rows
   opaque); not both.
2. The provider's billing detail is slimmed ("slim it"): lossy, accepted.
3. The files store stays JSONL with full rows ("stays jsonl"); no calls file per run.
4. Metric values in a long table (queryable), not a per-row array.
5. What moves to the run: any `_meta` field constant over the run (a generic rule), not a named list.
6. The fleet's data repository migrates in this release, in the same step. (Read from "yes on suggestion"; the owner
   confirms in the review.)
7. Plan first, then a second review, then build.

Binding from before: one database for everything under `data/`, no Python in it, nothing invented beyond the scope
(RFC-025, 2026-11-06); no default store (2026-11-15); no backward compatibility, committed data migrated, no shims; both
stores equal and solutions reusable for both; keep the vocabulary.

## What exists (measured 2026-11-15)

Measured on a full SQLite copy of this repository's data (`~/.cache/evh-view-bench/sqlite/data/project.sqlite`, 246
MB; the files layout of the same data 208 MB; a clean-HEAD SQLite release 241.5 MB against 7,695 files of 176 MB):

| Table (dbstat) | On disk | Holds |
|---|---|---|
| `rows` + its PK index + `rows_item` | 143 + 10 + 14 MB | 93,736 lines (711 of them the `n = 0` "rows exist" marker), 101.8 MB of JSON |
| `outputs` + PK index | 43 + 4 MB | 46,800 output texts, 32 MB (2.5 MB of it duplicated across runs) |
| `files` | 28 MB | every other record: corpora 8.0, run/score JSON 3.7, verdicts 3.2, sources 3.0, materialized 2.8 |

The 101.8 MB of row JSON: key names 57.2 MB (56%), punctuation and spacing 16.7 MB, null/0/false 4.6 MB, values 23.2
MB. By field: `_meta` 65.7 MB, of which `usage` 32.3 MB (the provider's whole object; code reads only `usage.cost`:
`cost_report.py:71`, `rescore.py:215`, `arm_smoke.py:57`, `tools/summeval_analysis.py:115`, `examples/.../reproduce.py:134`)
and `generation_config` 9.9 MB (31 score sets, 6,000 items, 31 distinct values: one per set). 24.6 MB of `_meta`
(minified) is a verbatim copy of the same run and item's `_meta` in another score set (rescore and judge_score carry
`_` keys over). Top-level fields: 102 names, 1,045,954 values, all numeric; only `item_id` is on every row.

How the rows are written and read today:

- Written through `_outputs` only: `put_rows(run_dir, text)` (whole set), `append_row`/`append_partial` (the crash
  checkpoint `rows.partial.jsonl`), `write_rows(run_dir, rows)`, `row_line(row)` (canonical: `json.dumps(sort_keys=True)`).
  `run.py:580` puts an adapter's `Result.meta` under `_meta`; `rescore.py:199` and `judge_score.py:1368` add to it.
- Read through `_outputs.rows_text` (20 call sites) and `_runs.item_rows` (the parsing reader most code uses),
  `_outputs.item_across` (one item across runs, the `rows_item` index), `_outputs.lines`.
- No stored hash covers prediction rows: the fingerprint hashes instrument, data, deployment and settings
  (`_fingerprint.py`), judging sets hash output texts (`judge_score.py:656`), every other `_sha` in `judge_score.py`
  hashes prompts, articles, manifests and ids. V5's per-item signature is computed at validate time from parsed rows
  minus `_meta`.
- `validate`'s V9 file listing comes from `git ls-files` (`validate_tree.py:762`), which does not apply in SQLite mode.
- A hidden dataset's rows keep only `CALL_META` of `_meta` in a release (`_release.py:83-94`: provider,
  response_model, usage, finish_reason, reasoning_tokens_reported, system_fingerprint, generation_config,
  generation_requested, encoder_window, resumed_from_disk).
- The deploy image's SQLite is 3.53.4 (P1b, `python:3.12.14-alpine3.23`).

## The model

Four things the rows mix today, each given its place:

| Concept | What it is | Files store (format 7) | SQLite store |
|---|---|---|---|
| **run-level call settings** | `_meta` fields constant over the run (here `generation_config`, `generation_requested`, `encoder_window`) | `run.json` → `call` | the run's `run.json` in `files` |
| **call facts** | per item, what the call was: the `CALL_META` keys (provider, model, usage, finish, ...) | in each row's `_meta`, as today | `calls(run, item)`, once per run and item |
| **score-level meta** | per item and score set, what the parser made of the answer (`predicted`, `ranking`, `llm_raw`, `gates`, ...) | in each row's `_meta` | `score_rows.meta` |
| **values** | per item and score set, every numeric top-level field (the metrics, latency, cost, tokens, flags) | top-level fields of the row | `score_values(row, metric, value)` |

`CALL_META` moves from `_release.py` to the model (`model/results.py`, new) and is the one definition of "call facts":
the release filter, the SQLite split and the docs read it there.

A **row dict** (what `item_rows` yields) is unchanged in shape: `{"item_id": …, <values>, "_meta": {<call settings>,
<call facts>, <score-level meta>}, "_extra": …}`. Every reader gets the same dict it gets today, from either store.

### Format 7 (both stores)

`migrations/m0007_results.py`, applied by `evh migrate` as m0001-m0006 are:

1. **Run-level call settings.** For each run with at least two rows over its score sets: every `_meta` key whose value
   (canonical JSON) is identical on every row of every score set of the run, and that is a `CALL_META` key, goes into
   `run.json` as `call: {<key>: <value>}` and leaves the rows. (Restricted to `CALL_META` so a parser field that happens
   to be constant, e.g. a `model` name the parser echoes, is not hoisted; the generic rule decided by the owner
   applies within the call facts. The review checks this narrowing.) Expected here: 31 runs, three keys.
2. **Usage slimmed.** `_meta.usage` keeps `cost`, `prompt_tokens`, `completion_tokens`, and when present
   `reasoning_tokens` and `cached_tokens` (lifted from `completion_tokens_details` / `prompt_tokens_details`); every
   other key goes. Applied at write too (below), so an adapter keeps returning what it likes. Expected: 53,720 objects.
3. **Rows canonical.** Every stored line is `row_line(row)` (sorted keys, `json.dumps` defaults). Committed rows
   already are (checked on a sample; the migration counts any it rewrites).
4. `project.yaml` `format: 7`; `migrate --dry-run` prints the counts per change.

The write path keeps it so, in `_outputs` (both stores), generically: a row written for a score set under
`runs/<id>/scores/<key>/` loses the `_meta` keys equal to its run's `call`, and its `usage` is slimmed; `run.py` computes
`call` when the run finishes (the same rule as the migration) and rewrites the run's rows once. The read path adds
`call` back under `_meta`. So rescore and judge_score, which copy a row's `_` keys into a new score set, write what
format 7 stores.

**Validation**: a new check (V-number at build) reports a row holding a `call` key with the run's value, or a `usage`
key outside the kept set.

### SQLite tables (replace `rows`)

```sql
score_sets   (id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE)          -- runs/<run>/scores/<key>
metrics      (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)         -- every numeric top-level field name
calls        (run TEXT NOT NULL, item_id TEXT NOT NULL, meta TEXT NOT NULL, -- call facts, JSON, once per run and item
              PRIMARY KEY (run, item_id)) WITHOUT ROWID
score_rows   (id INTEGER PRIMARY KEY, score_set INTEGER NOT NULL, n INTEGER NOT NULL, item_id TEXT NOT NULL,
              meta TEXT,          -- score-level meta and any call fact that differs from calls.meta, JSON
              extra TEXT,         -- `_extra`, JSON
              rest TEXT,          -- any other `_` key or non-numeric top-level field, JSON; usually NULL
              UNIQUE (score_set, n))
score_values (row INTEGER NOT NULL, metric INTEGER NOT NULL, value NOT NULL,  -- no affinity: 1 stays 1, 1.0 stays 1.0
              PRIMARY KEY (row, metric)) WITHOUT ROWID
rows_partial (run TEXT NOT NULL, n INTEGER NOT NULL, row TEXT NOT NULL, PRIMARY KEY (run, n))  -- the crash checkpoint, verbatim
CREATE INDEX score_rows_item ON score_rows (item_id)
```

- **A score set with no rows** keeps its `score_sets` entry (today's `n = 0` marker).
- **Writing a score set** (`put_rows`, `write_rows`): one transaction: the set's rows deleted, then per row its values,
  its call facts compared with `calls[run, item]` (inserted if absent; a differing key stays in the row's `meta`), its
  score-level meta, `_extra` and the rest. Metric ids for new names inserted. A line that is not a JSON object with an
  `item_id` is refused (`invalid-file`): today the strict reader already raises on it.
- **Reading a score set**: `score_rows WHERE score_set = ? ORDER BY n`, its values by `row BETWEEN min AND max` (a set's
  rows are inserted together), `calls` for the run; each dict assembled, `call` from `run.json` added under `_meta`.
  `item_across`: `score_rows WHERE item_id = ?`.
- **Deterministic ids** (the release's bytes, RFC-032 step 9): a migration and `data-migrate` insert score sets sorted
  by key, metric names sorted, items in stored order; the release's `seal` already rebuilds with `VACUUM INTO`.
- **`rows_text`** becomes derived: the canonical lines of the assembled dicts. Its callers that compare text
  (`rescore.py:559`, `judge_score.py:1534`, `examples/retrieval-scifact/reparse.py:189`) compare canonical text on both
  sides, as they do now.
- **Kept rows** (`_Kept`, 8 MB by text length) re-keyed by row count or serialized size.
- **Deleting** a run or score set (`rmtree` cascade, `forget_under`, `_store._per_item_tables`) learns the new tables;
  `calls` rows go with their run.
- **`data-migrate`** files ⇄ sqlite compares every score set as rows (canonical text of the assembled dicts), not raw
  bytes; going to files writes canonical lines.

Estimated sizes (arithmetic on the measured parts, not a built prototype; step d measures them): `score_values` ~16 MB
(15 B × 1.05 M), `score_rows` ~6 MB + score-level meta ~14 MB + `_extra` 1.4 MB, `calls` ~20 MB (call facts once per run
and item, usage slimmed), indexes ~10 MB: per-item results ~65-70 MB against 167 MB today; the database ~135-145 MB
against 246; the files layout ~165 MB against 208 (format 7 alone).

### The release and hidden datasets

`_release.copy_data` stays a files copy followed by `data-migrate` to SQLite (P1b), so the release follows. A hidden
dataset's rows keep the call facts and the run's `call`, never score-level meta (`predicted`, `llm_raw`, `ranking`, ...)
nor `_extra`: the same rule as `_call_only` today, now read from `CALL_META` in the model. `test_hidden_text.py` and
`test_release_store.py` check it on both stores. Two renders of one commit give one `project.sqlite` sha256.

### Not changed

`files` and `outputs` tables; output texts and their hashes; the fingerprint; judging sets; `metrics.json` means;
adapters (`Result.meta` stays free-form); the row dict readers see; the files store's layout (no new file).

### Not done (decided)

Compression; JSONB (SQLite 3.53 has it; text JSON stays readable and the gain is small); a schema for adapter `_meta`;
integer item ids; SQL aggregation in views (the files store could not share it); modelling `outputs` or `files`;
history or export mechanisms.

## Build order, each step with its proof

| Step | What | Proof (each a command and its output, before/after) |
|---|---|---|
| a | Baseline | `tools/view_bench.py` both stores; dbstat per table; files `runs/` size; `cost-report` totals; `check_report_claims` |
| b | `model/results.py` (`CALL_META`, the split, slim, hoist rule) + format 7 migration + write/read path in `_outputs` for both stores | `migrate --dry-run` counts (expect 31 runs hoisted, 53,720 usage objects slimmed); every score set's assembled rows equal before/after except the slimmed keys; `cost-report` totals identical; V5 and outputs signatures unchanged; files `runs/` size |
| c | `_outputs` API: rows as the primitive, `rows_text` derived, malformed lines refused, `_Kept` re-keyed; the ~30 tests writing raw row text moved to rows (or to the files store where the test is about a malformed file) | `make check`, `make stores-check` |
| d | SQLite tables, `put_rows`/`rows`/`item_across`, `ensure_tables`, cascade, `data-migrate` by rows, m0007 rebuilding the tables in a SQLite project | `data-migrate` there and back on this repository: every score set equal; dbstat per table against the estimates; `view_bench` cold/warm within ±10% of a; one `item_across` over 30 arms timed |
| e | Release | P1b's proof again: catalog, 2,905 comparisons and 38 MCP calls the same bytes from both stores; two renders, one sha256; inspector RSS under the limit |
| f | Fleet data repository (`chipi/fleet-eval-data`) | `evh migrate` there with the same counts reported; its CI green |
| g | Docs | RFC-025 "As built" amended; ADR-0030 (the results model); UPGRADING (format 7); RUNBOOK (the tables, the read path); CHANGELOG |

Every step: all gates (`make quality`; `make check`, `stores-check`, `budget-check`, `browser-check`,
`browser-real-check`, `commands-check`, `guard-check`, `site-check`; `mkdocs build --strict`), mutation checks on its
new guards, commit, push, `ci-watch` green.

This is not a speed fix: step 9 measured a fresh view's 2 s as store-layer work (0.15 s of SQL). Assembling 1 M values
may cost what parsing 102 MB of JSON costs now; `view_bench` within ±10% is the gate, and a regression is fixed
before the step lands.

## Risks

- **Git diff**: format 7 rewrites every committed `predictions.jsonl`: a diff of about 100 MB in `harness/data`.
- **Lossy slim**: the dropped billing detail can only come back from the provider.
- **Type fidelity**: `score_values.value` has no type affinity so an integer stays an integer; a test checks a row's
  canonical text round-trips.
- **Tests writing raw text**: 30 test files call `put_rows`/`put_rows_text`; how many write non-JSON lines is counted
  in step c.
- **Call facts that differ between score sets** of one run and item: kept in the row's `meta`, so nothing is lost;
  step d counts them (expected 0).

## Questions for the review

1. The run.json field's name (`call` proposed) and its place.
2. Hoisting restricted to `CALL_META` keys (proposed) or any `_meta` key constant over the run.
3. The kept `usage` keys.
4. Refusing a malformed row at write (proposed) against storing it.
5. The fleet data repository in the same step (decision 6, as read).
