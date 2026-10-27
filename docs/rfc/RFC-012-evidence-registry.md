# RFC-012: The evidence registry: baselines' evidence, `evh baselines --json`, the check

- **Status**: Draft (0.5.0), revision 3 (2026-10-27): `evh baselines --json` is the export (no separate command or
  schema); no baselines pages (the goal page shows them). Revision 2: baselines and looks per
  [RFC-017](RFC-017-record-store.md)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-011](../prd/PRD-011-evidence-registry.md)
- **Related RFCs**: RFC-014 (baseline storage and ids), RFC-015 (the verdict frozen at promotion), RFC-010 (a study's test
  check), RFC-009 (prompt versions in how to reproduce it), RFC-013 (commands, schemas)
- **Code**: `promote_baseline.py` (freezing evidence), new `view_baselines.py` (`evh baselines`), `evidence_check.py`;
  the catalog's goal page; `schemas/baseline.schema.json` (`evidence`), `schemas/baselines.schema.json` (the output of
  `evh baselines --json`)

## Abstract

At promotion, the harness freezes into the new baseline version the evidence that justified it: the RFC-015 verdict of
the promoted run against the baseline it replaces on the goal's measure, the goal's axes, the round and, for a study's
winner, its confirmation. `evh baselines` lists baselines with how to reproduce them, evidence and history; with
`--json` it is a versioned, deterministic document a production system can read, with the goal's intended use; and
`evh evidence-check FILE` checks every harness id and every file path a project's own registry cites, so a citation of a
replaced baseline, a missing round or a deleted report fails in CI.

## Problem Statement

- 0.4.0 records a baseline's reason but not the comparison that justified it; re-computing it later can drift (new runs,
  new rules).
- A production registry (the podcast project's 3,000-line `model_registry.py`) cites its evidence by hand in
  `registry_refs.yaml` (option id → report path, and rationale file names, relative to `data/eval/rationale/`,
  → the options, presets and stages they argue for), checked by the project's own script
  (`scripts/registry/check_research_refs.py`, 230 lines). That script does two kinds of thing: it resolves
  citations (every report and rationale file exists), and it joins them with the project's registry (every option
  has evidence and a claim, no entry names a removed option). Only the first is the harness's to do.

## Design

### Evidence frozen at promotion

`run-promote` (RFC-014) computes, before writing the version:

```json
"evidence": {
  "compared_to": "baseline:news_summary_cnn/cnn_dailymail_200/2",
  "measure": "rouge_l",
  "items_sha256": "…", "n": 200,
  "verdict": {"outcome": "better", "p": 0.0012, "effect": 0.021, "interval": [0.009, 0.033],
              "method": "sign-flip", "rule": "noninferiority", "level": 0.0152, "look": 1},
  "axes": {"cost_usd_per_item": {"promoted run": 0.0011, "baseline": 0.0024},
           "latency_p50_ms": {"promoted run": 1830, "baseline": 2410}},
  "round": "r3",
  "study": {"id": "study:news_summary_cnn/s2", "confirm": {"outcome": "better", "n": 180,
            "look": 1}},
  "computed_with": {"harness_version": "0.5.0", "stats_sha256": "…"}
}
```

- `compared_to` is the version current at promotion (after a rollback, not n − 1). A first promotion has
  `"compared_to": null` and no verdict.
- **When the dataset is a heldout dataset of the goal**, the comparison is a look (RFC-015): it reserves the next look,
  and when the protective limit is passed, promotion's own consent must also cover the extra look (one question
  naming both). A study's winner promoted against the baseline its confirmation compared it with reuses that look's
  verdict (the same key) and takes no new one.
- **When it is not a heldout dataset** (a dev dataset, a goal with no heldout role), the verdict is computed at
  the nominal one-sided 2.5% and recorded with `"look": null, "nominal": true`; the catalog labels it "not tested on
  held-out items".
- **When the two runs are not comparable** (a different reference digest, scorer or item set), the record has
  `"verdict": null, "not_comparable": [the fields that differ]`, and promotion says so before asking.
- The record never changes afterwards; a later re-computation is a different thing (`evh pair-test`), not the
  evidence.

### `evh baselines [--goal G] [--dataset D] [--all-versions] [--json]`

Per goal and dataset: the current version, how to reproduce it (below), its evidence, and the history (each version,
when, by whom, why, what it replaced). `--all-versions` lists every version.

### How to reproduce it (`reproduce`)

From the baseline's run: config id and `params` (credentials removed, `identity_params`), prompts (`arm.prompts`: names,
versions, hashes; RFC-009), the system's identity (`system_under_test.model`, declared code ref, accelerator), the adapter
(id and hash), the harness (version, code hash), the dataset (id, `items_sha256`), the reference (id, tier, digest), and the
stages (names, RFC-007).

### `--json` is the export

`evh baselines --json` prints `schemas/baselines.schema.json`, `"schema": "evh-baselines/1"`, and a production system
reads it, or the command's output saved to a file (`evh baselines --json > registry/baselines.json`):

```json
{"schema": "evh-baselines/1",
 "baselines": [{"id": "baseline:news_summary_cnn/cnn_dailymail_200/20261027T101500.123Z_7f3a",
                "current": "baseline:news_summary_cnn/cnn_dailymail_200@current",
                "goal": {"id": "news_summary_cnn", "title": "…", "intended_use": {"audience": "…", "decision": "…"}},
                "dataset": "cnn_dailymail_200", "reproduce": {…}, "evidence": {…}, "history": […]}]}
```

It is deterministic: baselines sorted by id, keys sorted, no timestamp of its own (each version carries its own dates)
and no harness version in the header (how to reproduce each carries the harness version of its run; the format is
`schema`), so two outputs with no new promotion are byte-identical, across harness upgrades too. The goal's `context`
and `decision` become the model card's intended use (Mitchell et al., 2019). Unlike the envelope every other `--json`
prints (RFC-013), this command's output is the document itself, so it can be saved and read as it is.

### `evh evidence-check FILE [--root DIR] [--key-paths KEY=DIR …] [--allow-replaced] [--json]`

Reads a project's citation file (YAML or JSON, any shape) and checks every string value (PRD-011 FR5):
- a harness id (RFC-014's grammar, one of its kinds): it must resolve. A fixed baseline version that is no longer
  current is an error naming the current one; `--allow-replaced` makes it a warning, for files that cite history on
  purpose. A run of a retired arm is an error ("retired in round r3: <reason>"). A run, study, trial or prompt version
  must exist.
- a string with a kind the grammar does not have (`option:…`, `preset:…`, `stage:…`: the project's own vocabulary) is
  not a harness id; it is listed as not checked, never as an error.
- a relative path with an extension (`docs/…/REPORT.md`): it must exist under `--root` (default: the project root).
- **keys** are not interpreted, except under the mappings named by `--key-paths`: `--key-paths
  rationale=data/eval/rationale` checks that every key of the top-level `rationale` mapping is a file in that
  directory (the podcast project's rationale files are named by their keys).

Joining citations to the project's production registry (every option has evidence and a claim; no entry names a
removed option) stays the project's check: the harness does not know the project's vocabulary. Exit 0 when every
citation resolves; exit 6 (a check found problems, RFC-013) with each failing citation and its key path, so a failed check is
never confused with a refusal (exit 1).

### The catalog

The goal page names each dataset's baseline with its evidence (the frozen verdict, the axes, the round or study), how to
reproduce it, and its history. There is no separate baselines page: a baseline belongs to a goal, and the goal page is
where it is read. Every view has its command.

### Validation

`validate` checks that each baseline version's `evidence.compared_to` is the version that was current when it was
promoted (the newest one before it), that its round, run and study resolve, that its look number is not also taken by
another decision on the dataset (a double-spent look, RFC-015), and that its `items_sha256` is the dataset's.

## Migration

The migration script (RFC-014 step 6) writes version 1 of each migrated baseline with `migrated_from` and no evidence
(the 0.4.0 baselines recorded none); the catalog says "promoted in 0.4.0, evidence not recorded".

## Alternatives Considered

- **Recompute the evidence on demand.** Rejected: it drifts with new runs and rules; promotion is the moment the decision
  was made.
- **Export every run.** Rejected: a production system needs the current baselines and how to reproduce them, not the history of
  every arm.
- **Interpret project option ids.** Rejected: they are the project's vocabulary; the harness checks what it owns (its ids
  and the files cited).

## Testing

- `harness/tests/test_baselines_evidence.py`: promotion on a heldout dataset freezes the verdict and takes a look; on a
  dev dataset it is nominal and takes none; a first promotion has none; a study's winner reuses its confirmation's
  look; non-comparable runs record `verdict: null` with the reason; `compared_to` after a rollback; `evh baselines
  --json` validates against its schema.
- `harness/tests/test_baselines_export.py`: two `evh baselines --json` outputs are byte-identical, and stay so when the
  harness version changes; how to reproduce it has every field above; intended use from the goal.
- `harness/tests/test_evidence_check.py`: a file shaped like the podcast project's `registry_refs.yaml` passes with present
  reports and rationale files (`--key-paths`) and fails (exit 6) on a missing one; `option:` values are listed as not
  checked; a replaced baseline version errors, and warns with `--allow-replaced`; a retired arm's run errors; a
  missing round fails.

## Decisions (ADR candidates)

1. The evidence for a promotion is frozen into the baseline version when it is made, and counts as a heldout look.
2. `evh baselines --json` is the export: a deterministic, versioned document with how to reproduce each baseline and
   the goal's intended use.
3. `evidence-check` checks the harness's ids and the cited files in any citation file (keys only where named), fails on
   replaced baselines and retired arms, and leaves project vocabulary and registry joins to the project.
4. A promotion's comparison is a look only on a heldout dataset; elsewhere it is recorded as nominal, and non-comparable
   runs record no verdict.
