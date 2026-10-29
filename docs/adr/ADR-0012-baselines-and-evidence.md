# ADR-0012 — Baselines per goal, with the evidence frozen at promotion (0.7.0)

**Status:** Accepted (2026-10-26), design; not yet built. Revision 3 (2026-10-27): `evh baselines --json` is the export; no baselines pages. Revision 2: write-once versions, the newest current; no index, pointer or lock.
**Date:** 2026-10-26
**Detail:** [PRD-011](../prd/PRD-011-evidence-registry.md), [PRD-013](../prd/PRD-013-identity-and-ties.md)
FR7, [RFC-014](../rfc/RFC-014-identity-baselines-migration.md) (storage, commands),
[RFC-012](../rfc/RFC-012-evidence-registry.md) (evidence, `evh baselines --json`, the check)

## Context

A baseline was per dataset (`<dataset>_baseline`), so two goals on one dataset shared it; former
baselines lived only in git; and a baseline recorded its reason, not the comparison that justified
it. A production registry (the podcast project's) cites its evidence by hand, and nothing tells it
when a cited result has been replaced.

## Decision

- **A baseline belongs to a goal on a dataset**, stored as write-once versions with collision-free
  ids; the current one is the newest; a rollback is a new version that re-promotes an earlier run. No
  index, pointer or lock file ([ADR-0017](ADR-0017-record-store.md)).
- **The comparison that justified a promotion is frozen into the version** when it is made (the
  verdict against the baseline it replaces, the axes, the round or study). It is a heldout look only
  on a heldout dataset; elsewhere it is recorded as nominal; runs that cannot be compared record no
  verdict and why.
- **`evh baselines --json` is the export**: a deterministic, versioned document with how to reproduce each
  baseline and the goal's intended use, for a production system to read. No separate export command, and no
  separate baselines page: the goal page shows each baseline.
- **`evidence-check`** fails a citation file that names a missing id or file, a replaced baseline
  or a retired arm. It checks the harness's ids and the files cited; the project's own vocabulary
  and the joins with its registry stay the project's.

## Consequences

Every goal shows its baseline's history and the evidence for each change; a replaced baseline
cited in CI fails there. The 0.4.0 baselines migrate as version 1 with no evidence ("evidence not
recorded"), since they recorded none.
