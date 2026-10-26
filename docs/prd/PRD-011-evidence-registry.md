# PRD-011: The evidence registry

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (the catalog, to show champions)
- **Related RFC**: RFC-012 (the champion export and the reference check), to be written
- **Related PRDs**: [PRD-005](PRD-005-goals-and-rounds.md) (goals, baselines),
  [PRD-009](PRD-009-prompts-and-optimisation.md) (what a champion's recipe includes),
  [PRD-012](PRD-012-agent-ready.md)

## Summary

Every project keeps its own registry of what runs in production: which model, which settings,
which prompt. What a project lacks is a stable, checkable link from each of those choices to
the evidence that chose it. The harness already holds that evidence (goals, baselines with a
reason, rounds and their conclusions, the references and datasets they were judged on), spread
over several kinds of record. This PRD gathers it into an **evidence registry**: per goal, the
**champion** and its full recipe (params, prompt versions, model identity, pipeline settings),
how it became champion and what it replaced, exported as one versioned file with a stable id per
champion. A project's own registry cites those ids, and a check says when a cited champion has
been replaced or no longer exists.

## Background & Context

- `run-promote` makes a run a goal's baseline on a dataset, with a reason; rounds record
  conclusions; the catalog's goal page leads with the answer so far. There is no single record a
  production system can read, and no stable id for "the winner of goal G on dataset D".
- The podcast project's registry is about 3,000 lines of Python in its public library (modes,
  stage options, presets), recording for a winner where it was promoted from and a metrics
  summary. Its links to evidence are kept by hand in `registry_refs.yaml`, checked by its own
  script; its promote command cannot run from the evaluation repository.
- A registry kept in code drifts from the evidence the moment someone edits one side.

## Goals

- Per goal and dataset, one champion with a stable id, its recipe and its evidence.
- The recipe is enough to reproduce the champion's runs: config, params, prompt versions with
  hashes, model identity, adapter and harness versions.
- The export is a file a project's production code can read, in a documented, versioned schema.
- A project's registry can cite champion ids and check them, in CI or by hand.
- The history is kept: every former champion, when and why it was replaced.
- The same registry is readable by a person (catalog, command) and an agent (JSON, MCP).

## Non-Goals

- Not a production registry: the harness does not serve models, hold deployment state, or know
  what is live. The project decides what to deploy.
- Not a model artifact store: weights stay where they are; the recipe identifies them.
- No write-back into a project's code.

## Personas

- **The team lead** asking "what is our current best for this, and why".
- **The production engineer** who wants the deployed settings to come from the evidence, not
  from a copy.
- **The auditor or reviewer** checking that a deployed choice was actually the winner.

## User Stories

- _As a team lead, I run `evh champions` and get, per goal and dataset, the champion, its score
  against the previous one, and the round that chose it._
- _As a production engineer, I export the registry to `registry/champions.json` and my service
  reads the recipe of `summary-cnn@3` from it._
- _As a reviewer, CI runs `evh champions-check registry_refs.yaml` and fails because the
  project still cites a champion that was replaced last week._

## Functional Requirements

- **FR1**: A champion is the current baseline of a goal on a dataset (as promoted today), with a
  stable id `<goal>@<n>` that increases on each promotion; former champions keep theirs.
- **FR2**: `evh champions [--goal G] [--json]` lists champions with recipe, evidence (the run,
  the tests against the previous champion, the round and its conclusion, the loop when there was
  one) and history.
- **FR3**: `evh champions-export --out FILE` writes all of it in a versioned schema; the export is
  deterministic (same records, same bytes).
- **FR4**: The recipe includes config id and params, prompt ids, versions and hashes
  ([PRD-009](PRD-009-prompts-and-optimisation.md)), the model identity from the fingerprint, the
  adapter and harness versions, dataset and reference with their hashes, and stages when the arm
  has them ([PRD-008](PRD-008-pipelines-and-any-language.md)).
- **FR5**: `evh champions-check FILE` reads a project's list of cited champion ids and fails on
  an id that does not exist or is no longer current, naming the current one.
- **FR6**: The catalog's goal page shows the champion's id and history; a champions page lists
  them all.
- **FR7**: `evh validate` checks that every champion's evidence resolves.

## Success Criteria

- The podcast project's `registry_refs.yaml` can be replaced by champion ids and
  `champions-check` (the review with that project decides whether it is).
- An export of the example project is byte-identical across two runs with no new promotion.

## Related Documents

- RFC-012 (to be written); [PRD-005](PRD-005-goals-and-rounds.md) (baselines and promotion).
