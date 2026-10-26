# RFC-012: The evidence registry: champions' evidence, the export, the check

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-011](../prd/PRD-011-evidence-registry.md)
- **Related RFCs**: RFC-014 (champion storage and ids), RFC-015 (the verdict frozen at promotion), RFC-010 (a study's test
  check), RFC-009 (prompt versions in the recipe), RFC-013 (commands, schemas)
- **Code**: `promote_baseline.py` (freezing evidence), new `view_champions.py` (`evh champions`), `champions_export.py`,
  `evidence_check.py`; catalog champion pages; `schemas/champion.schema.json` (`evidence`), `champions-export.schema.json`

## Abstract

At promotion, the harness freezes into the new champion version the evidence that justified it: the RFC-015 verdict of
the challenger against the champion it replaces on the goal's measure, the goal's axes, the round and, for a study's
winner, its test check. `evh champions` lists champions with their recipe, evidence and history; `evh champions-export`
writes them in a versioned, deterministic file a production system can read, with the goal's intended use; and
`evh evidence-check FILE` checks every harness id and every file path a project's own registry cites, so a citation of a
replaced champion, a missing round or a deleted report fails in CI.

## Problem Statement

- 0.4.0 records a baseline's reason but not the comparison that justified it; re-computing it later can drift (new runs,
  new rules).
- A production registry (the podcast project's 3,000-line `model_registry.py`) cites its evidence by hand in
  `registry_refs.yaml` (option id → report path, plus rationale files), checked by the project's own script.

## Design

### Evidence frozen at promotion

`run-promote` (RFC-014) computes, before writing the version:

```json
"evidence": {
  "compared_to": "champion:news_summary_cnn/cnn_dailymail_200/2",
  "measure": "rouge_l",
  "items_sha256": "…", "n": 200,
  "verdict": {"outcome": "superior", "p": 0.0012, "effect": 0.021, "interval": [0.009, 0.033],
              "method": "sign-flip", "level": 0.005, "look": 4},
  "axes": {"cost_usd_per_item": {"challenger": 0.0011, "champion": 0.0024},
           "latency_p50_ms": {"challenger": 1830, "champion": 2410}},
  "round": "round:news_summary_cnn/r3",
  "study": {"id": "study:news_summary_cnn/s2", "test_check": {"outcome": "superior", "n": 180, "look": 4}},
  "computed_with": {"harness_version": "0.5.0", "stats_sha256": "…"}
}
```

A first promotion has `"compared_to": null` and no verdict. The comparison is a look on the test item set (RFC-015) and is
counted. The record never changes afterwards; a later re-computation is a different thing (`evh pair-test`), not the
evidence.

### `evh champions [--goal G] [--dataset D] [--all-versions] [--json]`

Per goal and dataset: the current version, its recipe (below), its evidence, and the history (each version, when, by whom,
why, what it replaced). `--all-versions` lists every version.

### The recipe

From the champion's run: config id and `params` (credentials removed, `identity_params`), prompts (`arm.prompts`: names,
versions, hashes; RFC-009), the system's identity (`system_under_test.model`, declared code ref, accelerator), the adapter
(id and hash), the harness (version, code hash), the dataset (id, `items_sha256`), the reference (id, tier, digest), and the
stages (names, RFC-007).

### `evh champions-export --out FILE`

`schemas/champions-export.schema.json`, `"schema": "evh-champions/1"`:

```json
{"schema": "evh-champions/1", "harness_version": "0.5.0",
 "champions": [{"id": "champion:news_summary_cnn/cnn_dailymail_200/3",
                "pointer": "champion:news_summary_cnn/cnn_dailymail_200@current",
                "goal": {"id": "news_summary_cnn", "title": "…", "intended_use": {"audience": "…", "decision": "…"}},
                "dataset": "cnn_dailymail_200", "recipe": {…}, "evidence": {…}, "history": […]}]}
```

Deterministic: champions sorted by id, keys sorted, no export timestamp (each version carries its own dates), so two
exports with no new promotion are byte-identical. The goal's `context` and `decision` become the model card's intended
use (Mitchell et al., 2019).

### `evh evidence-check FILE [--root DIR] [--require-current] [--json]`

Reads a project's citation file (YAML or JSON, any shape) and checks every string value:
- a harness id (RFC-014's grammar): it must resolve; a fixed champion version that is no longer current is reported with
  the current one (an error with `--require-current`, a warning otherwise); a round, run, study or prompt version must
  exist; a retired arm's run is reported as retired;
- a relative path with an extension (`docs/…/REPORT.md`): it must exist under `--root` (default: the project root).

Keys (a project's own option ids, such as the podcast registry's) are not interpreted: joining them to the project's
production registry stays the project's check. Exit 1 on any error, with each failing citation and its key path.

### The catalog

The goal page names each dataset's champion by id with its evidence (the frozen verdict, the axes, the round or study), and
links its history; a champions page lists every goal's champions with their recipes' key fields. Every view has its
command.

### Validation

`validate` checks that each champion version's `evidence.compared_to` is the previous version, its round, run and study
resolve, and its `items_sha256` is the dataset's.

## Migration

The migration script (RFC-014 step 6) writes version 1 of each migrated champion with `migrated_from` and no evidence
(the 0.4.0 baselines recorded none); the catalog says "promoted in 0.4.0, evidence not recorded".

## Alternatives Considered

- **Recompute the evidence on demand.** Rejected: it drifts with new runs and rules; promotion is the moment the decision
  was made.
- **Export every run.** Rejected: a production system needs the current champions and their recipes, not the history of
  every arm.
- **Interpret project option ids.** Rejected: they are the project's vocabulary; the harness checks what it owns (its ids
  and the files cited).

## Testing

- `harness/tests/test_champions_evidence.py`: promotion freezes the verdict and counts a look; a first promotion has none;
  a study's winner carries its test check; `evh champions --json` validates against its schema.
- `harness/tests/test_champions_export.py`: two exports are byte-identical; the recipe has every field above; intended use
  from the goal.
- `harness/tests/test_evidence_check.py`: a file shaped like the podcast project's `registry_refs.yaml` passes with present
  reports and fails on a missing one; a replaced champion version warns, and errors with `--require-current`; a missing
  round fails.

## Decisions (ADR candidates)

1. The evidence for a promotion is frozen into the champion version when it is made, and counts as a test look.
2. Champions export as a deterministic, versioned file with the recipe and the goal's intended use.
3. `evidence-check` checks the harness's ids and the cited files in any citation file, and leaves project vocabulary to
   the project.
