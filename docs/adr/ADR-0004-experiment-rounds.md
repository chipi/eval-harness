# ADR-0004 — Experiment rounds, and a catalog that guides them (0.4.0)

**Status:** Accepted (2026-10-24), as built. Two parts of the proposal were not built in 0.4.0: a
round picker inside the web inspector (the goal page's per-round **inspect** button opens a round's
arms in it instead) and a progress line per round in the rounds overview;
[RFC-004](../rfc/RFC-004-experiment-rounds.md) lists what was and was not built.
**Date:** 2026-10-24
**Detail:** [PRD-005](../prd/PRD-005-goals-and-rounds.md) (what and why),
[RFC-004](../rfc/RFC-004-experiment-rounds.md) (records, commands, the evidence),
[UXS-001](../uxs/UXS-001-catalog.md#the-goal-page) (the goal page),
[UXS-003](../uxs/UXS-003-cli-and-onboarding.md#the-round-flow) (the commands)

## Context

Experiments go round on round: try arms, drop what lost, change something, compare again. The
harness recorded none of it, and the catalog compared each arm with a reference or a baseline,
never one round with another. The owner decided the shape: rounds optional, the catalog
read-only, decisions as commands run locally.

## Decision

- **Rounds are optional**: a project that never opens one sees no change.
- **A round is a file** per goal, `data/rounds/<goal_id>/<round_id>.yaml`; an arm joins by naming
  the round in its config, and its runs record it.
- **Decisions are commands**: `evh round-open`, `round-retire`, `round-close` (which can promote);
  `round-retire --runs-dir` retires one copy of a config (its runs in another runs directory, such
  as a re-timing on another machine) and leaves the arm in the project's runs directory in play;
  `evh rounds` shows the evidence and suggests the next decision, each as the command that makes
  it. The pages never write.
- **The goal page leads with the answer**, then the rounds, then the arms grouped by what they
  are scored against.
- Decided with it and built: **dataset lineage** (`dataset-create --from`) and the inspector's
  **conditions check**.

## Consequences

One more file kind, schema and set of commands; the run record gains `round`; validate V14 checks
the records. The public deployment is unaffected because the server still never writes.
