# ADR-0020 — A dataset's second reference is silver, with a caveat that says what it is (0.6.0)

**Status:** Accepted (owner, 2026-10-31), built in 0.6.0. Proposed 2026-10-30 as the owner's vocabulary call.
**Date:** 2026-10-30
**Detail:** [RFC-019](../rfc/RFC-019-datasets-from-production.md) (references from outcomes),
[PRD-002](../prd/PRD-002-references.md) (references: gold, silver)

## Context

A dataset from production can carry several references at once: the one a goal decides on (a
person's verdicts), one computed from outcomes, labels carried from older fixtures. Today a
reference is `gold/<dataset>` (a person's) or `silver/<dataset>` (a model's), and the code reads
the tier from the name: `reference-manifest` requires `<gold|silver>/<name>`, `rescore` derives
the tier from the prefix, and the catalog lists only the two folders. On the goal page, every
gold reference gets its own decision; silver groups are shown beside gold and never decide.

## Decision (proposed)

- The reference a goal decides on is `gold/<dataset>`, as today.
- Every other reference on the dataset is `silver/<name>`, and its manifest's caveat says what it
  is: "OUTCOME: what production recorded afterwards, as of <date>; not a person's label", or
  "carried from fixture labels". The goal page then shows exactly one recommendation, and the others
  beside it, with no change to how goals group.

## Consequences

- No new tier, and no change to the goal page's grouping.
- "Silver" widens from "a model wrote it" to "not the reference this goal decides on"; the caveat
  carries the difference, and PRD-002 and CONCEPTS say so.
- A second person-written reference cannot also decide; a project that wants it to decide makes it
  the `gold/<dataset>` of its own dataset version.

## Alternatives considered

- **A third tier** (`outcome/`). Rejected for now: every reader of the tier (manifest, rescore, the
  catalog, the goal page) would change.
- **Two gold references.** Rejected: each gets a decision on the goal page.
