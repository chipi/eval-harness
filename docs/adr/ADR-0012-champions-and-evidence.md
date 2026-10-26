# ADR-0012 — Champions per goal, with the evidence frozen at promotion (0.5.0)

**Status:** Accepted (2026-10-26), design; not yet built
**Date:** 2026-10-26
**Detail:** [PRD-011](../prd/PRD-011-evidence-registry.md), [PRD-013](../prd/PRD-013-identity-and-ties.md)
FR7, [RFC-014](../rfc/RFC-014-identity-champions-migration.md) (storage, commands),
[RFC-012](../rfc/RFC-012-evidence-registry.md) (evidence, export, the check)

## Context

A baseline was per dataset (`<dataset>_baseline`), so two goals on one dataset shared it; former
baselines lived only in git; and a baseline recorded its reason, not the comparison that justified
it. A production registry (the podcast project's) cites its evidence by hand, and nothing tells it
when a cited result has been replaced.

## Decision

- **A baseline becomes the current champion of a goal on a dataset**, stored as numbered versions
  with a pointer (no symlinks), written under a lock; a rollback is a recorded history entry.
- **The comparison that justified a promotion is frozen into the version** when it is made (the
  verdict against the champion it replaces, the axes, the round or study). It is a test look only
  on a test dataset; elsewhere it is recorded as nominal; runs that cannot be compared record no
  verdict and why.
- **Champions export** as a deterministic, versioned file with each recipe and the goal's intended
  use, for a production system to read.
- **`evidence-check`** fails a citation file that names a missing id or file, a replaced champion
  or a retired arm. It checks the harness's ids and the files cited; the project's own vocabulary
  and the joins with its registry stay the project's.

## Consequences

Every goal shows its champion's history and the evidence for each change; a replaced champion
cited in CI fails there. The 0.4.0 baselines migrate as version 1 with no evidence ("evidence not
recorded"), since they recorded none.
