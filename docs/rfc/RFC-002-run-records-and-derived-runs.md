# RFC-002: Run records and derived runs

- **Status**: Completed (0.4.0, unreleased)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-001](../prd/PRD-001-experiments-and-comparison.md), [PRD-002](../prd/PRD-002-references.md), [PRD-003](../prd/PRD-003-judging.md)
- **Related RFCs**: [RFC-001](RFC-001-fingerprint-and-code-identity.md) (the fingerprint inside the record)
- **Code**: `harness/scripts/_record.py`, `harness/schemas/metrics.schema.json`,
  `harness/scripts/experiment_run.py`, `rescore.py`, `judge_score.py`, `import_run.py`

## Abstract

A run is a directory; its record is `metrics.json`. 0.4.0 gives the record one format with two
constructors: `run_record` for a **measured** run (`experiment-run`, `import-run`) and
`derived_record` for a **derived** run, computed from another run's stored outputs (`rescore`,
`judge-score`, and the SciFact example's re-parse). A derived run says what derived it, from
which run, when and with what, in one block, `derived`. Every field the harness writes is
declared in the schema, and `validate` V1 fails a record with any other.

## Problem Statement

Four writers built the record by hand, each with its own provenance fields (`rescored_from`,
`rescored_with`, `judged_from`, `judged_with`, `judge_label`, the example's `reparsed_*`), and a
derived run kept its source's `created_at`, so "made after a goal policy's cut-over" was read off
the wrong date. Undeclared fields such as 0.3.0's `primary_metric_asc` were written and read by
nothing.

## Design

### A run directory

| file | written | holds |
| --- | --- | --- |
| `run.json` | before the first item | run id, config, dataset, start time: a crashed run can still be identified |
| `predictions.jsonl` | one row per item, as it is measured | `item_id`, every per-item metric (score, `cost_usd`, `latency_ms`, `output_words`, ...), `_extra` (the numeric extras the adapter attached at call time, which rescore and judge-score carry) and `_meta` (provider metadata: the bill in `_meta.usage.cost`, `finish_reason`, kept verbatim) |
| `outputs/` | per item | what the arm wrote for each item |
| `metrics.json` | only on a clean exit | the run record |

`experiment-run --resume` continues a stopped run from its rows; it refuses rows written before
0.4.0 (no `_extra`). A run that stops mid-pass prints which run, after how many items, and the
exact `--resume` command.

### The record (`metrics.schema.json`)

- **Required:** `run_id`, `dataset_id`, `config_id`, `build`, `created_at`, `scores` (each
  metric's mean; totals, not means, for `total_cost_usd`, `total_tokens_in`, `total_tokens_out`),
  `n_items`.
- **Optional, written by the harness:** `params`, `adapter`, `fingerprint` ([RFC-001](RFC-001-fingerprint-and-code-identity.md)),
  `primary_metric`, `metric_kinds`, `metric_directions` (read by every command's direction rule),
  `metric_descriptions` (the adapter's `METRIC_DESCRIPTIONS`, refreshed by `rescore`),
  `reference_tier`, `goal`, `format`, `round`, `repeat_index`, `resume`, `providers_seen`,
  `warmup_ms`, `imported` (for `import-run`), and for derived runs `derived` and
  `source_created_at`.
- `validate` V1 fails a record carrying any field not declared.

### Derived runs

```json
"derived": {"kind": "rescore", "from": "<source run directory>", "at": "<when>",
            "with": {"adapter": "...", "sha256": "..."}}
```

- `kind` is `rescore`, `judge` or `reparse`; `with` names what computed it (the adapter and
  scorer hashes, the judge scorer, the parser); `source` holds the source's own `derived` block
  when the source was itself derived.
- A derived run has its own `created_at`, and keeps the source's as `source_created_at`.
- Derived runs are written to another directory than the source's: `rescore --out DIR`
  (refused when `DIR` is one it reads runs from), `judge-score` into
  `data/runs-judged/<scorer_id>/`. The originals are never touched.
- Rescoring onto another reference records the reference first measured against
  (`reference_id_at_measurement`); the "references changed" flag is kept for the same reference's
  files changing, not for a move from silver to gold.
- A 0.3.0 derived run, carrying the old fields, is read as a measured run; UPGRADING says to
  re-run `rescore` / `judge-score` on the runs a project keeps.

### Reading runs back

The tests, the leaderboard, `rescore`, `judge-score`, `validate` and the catalog read runs through
`harness/scripts/_runs.py`. The catalog's `HarnessAdapter` treats
`<runs dir>/<dataset_id>/<config_id>` as one arm: every repeat of a config on a dataset, averaged
per item, exactly as `pair-test` and `family-test` read them. `EVAL_RUNS_DIR` points any command at
another runs directory (e.g. `data/runs-judged/<scorer>`).

## Alternatives Considered

- **Keep per-writer fields, document them.** Rejected: four vocabularies for one idea, and a
  reader had to know all of them.
- **Overwrite the source run when re-scoring.** Rejected: the stored outputs and the first
  measurement are the record; a re-measurement sits beside it.
- **Compatibility readers for 0.3.0 fields.** Rejected: nothing depended on them outside this
  repository, whose committed runs were migrated.

## Testing

- `evh validate` V1 (record schema), V7 (a committed run with no `metrics.json`), V8 (two run
  directories claiming one dataset and config), V10 (a derived run naming a scorer that is not
  the code in this tree).
- `harness/tests/test_run_reports.py`: a run with a project adapter, latency, cut-off outputs, a
  crash and its resume.
