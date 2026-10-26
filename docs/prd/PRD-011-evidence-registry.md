# PRD-011: The evidence registry

- **Status**: Draft (0.5.0), final review round
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (the catalog, to show champions)
- **Related RFC**: RFC-012 (champion versions, the export, the check), to be written
- **Related PRDs**: [PRD-005](PRD-005-goals-and-rounds.md) (goals, baselines),
  [PRD-009](PRD-009-prompts-and-optimisation.md) (what a recipe includes),
  [PRD-013](PRD-013-identity-and-ties.md) (baselines per goal and dataset),
  [PRD-012](PRD-012-agent-ready.md)

## Summary

Every project keeps its own registry of what runs in production. What it lacks is a stable,
checkable link from those choices to the evidence that made them. The harness holds that evidence
(goals, baselines promoted with a reason, rounds and their conclusions, the references and
datasets they were judged on) across several kinds of record. This PRD gives each promotion a
**champion version** (`champion:news_summary/cnn_200/3` a fixed version,
`champion:news_summary/cnn_200@current` the moving pointer, in the one grammar of
[PRD-013](PRD-013-identity-and-ties.md) FR7, after MLflow's versions and aliases), keeps every former champion with why it was
replaced, freezes the comparison that justified each promotion when it is made, and exports the
lot in a documented file a project can read and cite. A **check** tells a project when something
it cites has been replaced, retired or never existed; a citation may name a champion, a round, a
run or a report, because a production registry also records options that were rejected.

## Background & Context

- `run-promote` makes a run a **dataset's** baseline (`<dataset_id>_baseline`,
  `promote_baseline.py:141`) with a reason; the goal is carried from the run, so two goals on one
  dataset share one baseline ([PRD-013](PRD-013-identity-and-ties.md) makes baselines per goal and
  dataset). Former baselines are kept only in git history; the comparison against the previous
  baseline is not recorded at promotion.
- The podcast project's registry is about 3,000 lines of Python in its pipeline library (modes,
  stage options, presets), recording for an option where it was promoted from and a metrics
  summary. `registry_refs.yaml` maps registry options (including demoted and rejected ones) to
  evaluation reports and rationale files, checked by its own script (`check_research_refs.py`);
  it cites reports and options, not only winners.
- The MLflow registry is the common reference: integer versions, moving aliases (`@champion`),
  and champion/challenger as the names of the two sides of a promotion. Model cards (Mitchell et
  al., 2019) are the reference for what a published model record says about intended use.

## Goals

- Per goal and dataset, a champion with a fixed version number, its recipe and its evidence, and
  a moving `@current` pointer.
- The comparison that justified a promotion is frozen when it is made, not recomputed later.
- The recipe reproduces the champion's runs: config and params, prompt versions with hashes,
  model identity, adapter and harness versions, dataset and reference with their hashes, stages.
- The export is a documented, versioned file a project's production code can read.
- A project's own registry can cite champions, rounds, runs or reports and check them, in CI or
  by hand.
- Readable by a person (catalog, command) and an agent (JSON, MCP resources).

## Non-Goals

- Not a production registry: the harness does not serve models, hold deployment state or know what
  is live.
- Not an artifact store: weights stay where they are; the recipe identifies them.
- No write-back into a project's code.

## Personas

- **The team lead** asking "what is our current best for this, and why".
- **The production engineer** who wants deployed settings to come from the evidence.
- **The reviewer** checking that a deployed choice was the winner, and that a rejected option was
  rejected for a recorded reason.

## User Stories

- _As a team lead, I run `evh champions` and get, per goal and dataset, the champion, the
  challenger it beat with the frozen result, and the round that chose it._
- _As a production engineer, I export to `registry/champions.json` and my service reads the recipe
  of `champion:news_summary/cnn_200@current`._
- _As a reviewer, CI runs `evh evidence-check registry_refs.yaml` and fails because the project
  still cites `champion:news_summary/cnn_200/2`, replaced last week by version 3._

## Functional Requirements

- **FR1**: A champion is the current baseline of a goal on a dataset. Each promotion makes a new
  fixed version `champion:<goal>/<dataset>/<n>`; `champion:<goal>/<dataset>@current` points at the
  current one; former versions stay in the tree (not only in git) with when, why and by whom they
  were replaced, stored as [PRD-013](PRD-013-identity-and-ties.md) FR7 says.
- **FR2**: At promotion, the harness freezes into the champion's record the comparison of the
  challenger with the champion it replaces, on the champion's dataset: the paired result on the
  goal's measure (effect, interval, p) and the goal's axes. A first promotion records that there
  was no champion. A study's winner also carries the study's test check
  ([PRD-009](PRD-009-prompts-and-optimisation.md) FR4) beside it; the two are different evidence
  and both are kept.
- **FR3**: `evh champions [--goal G] [--json]` lists champions with recipe, evidence (the run, the
  frozen comparison, the round and its conclusion, the study and its test check when there was one)
  and history.
- **FR4**: `evh champions-export --out FILE` writes them in a versioned schema, with the goal's
  intended use (who uses the output, the decision it informs) as a model card's intended use;
  deterministic (same records, same bytes).
- **FR5**: `evh evidence-check FILE` reads a project's citations (champion versions or pointers,
  round ids, run ids, report paths) and fails on one that does not exist, a champion version that
  is no longer current (naming the current one), or a retired arm cited as chosen.
- **FR6**: The catalog's goal page shows the champion's version and history; a champions page lists
  them all.
- **FR7**: `evh validate` checks that every champion's evidence resolves.

## Success Criteria

- The podcast project's `registry_refs.yaml` can be checked by `evidence-check` (its option-to-report
  links included), replacing its own check script (to be confirmed with that project).
- An export of the example project is byte-identical across two exports with no new promotion.

## Related Documents

- RFC-012 (to be written); [PRD-005](PRD-005-goals-and-rounds.md). References: MLflow Model
  Registry (versions, aliases, champion/challenger), model cards (Mitchell et al., 2019).
