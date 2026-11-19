# ADR-0004 — Eval rounds, and a catalog that guides them

**Status:** Accepted (2026-10-24), as built. The goal page's per-round **inspect** button opens a round's
arms in it;
[RFC-004](../rfc/RFC-004-eval-rounds.md) lists what was and was not built.
**Date:** 2026-10-24
**Detail:** [PRD-005](../prd/PRD-005-goals-and-rounds.md) (what and why),
[RFC-004](../rfc/RFC-004-eval-rounds.md) (records, commands, the evidence),
[UXS-001](../uxs/UXS-001-catalog.md#the-goal-page) (the goal page),
[UXS-003](../uxs/UXS-003-cli-and-onboarding.md#the-round-flow) (the commands)

## Context

Evals go round on round: try arms, drop what lost, change something, compare again. The
harness recorded none of it, and the catalog compared each arm with a reference or a baseline,
never one round with another. The owner decided the shape: rounds optional, the catalog
read-only, decisions as commands run locally.

## Decision

- **Rounds are optional**: a project that never opens one sees no change.
- **A round is a file** per goal, `data/rounds/<goal_id>/<round_id>.yaml`; a run joins a round with
  `evh run --goal G --round R`; its record names the round, and the round file stores its arms.
- **Decisions are commands**: `evh round-open`, `round-retire`, `round-close` (which can promote);
  `round-retire --label L` retires one reading of a system (a re-timing on another machine, say) and
  leaves the other readings in play; `evh round-evidence` shows the evidence and suggests the next
  decision, each as the command that makes it (`evh round-list` lists the rounds). The pages never write.
- **The goal page leads with the answer**, then the rounds, then the arms grouped by what they
  are scored against.
- Decided with it and built: **dataset lineage** (`dataset-create --from`) and the inspector's
  **conditions check**.

## Amended by ADR-0029 / PRD-017

The Workbench writes rounds through the local API; the catalog's static pages and a public server do not write.

## Consequences

One more file kind, schema and set of commands; the run record gains `round`; validate V14 checks
the records. The public deployment is unaffected because the server still never writes.
