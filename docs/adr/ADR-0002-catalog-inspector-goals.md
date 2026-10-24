# ADR-0002 — Catalog, run inspector and goals in the harness (0.4.0)

**Status:** Accepted (2026-10-21). Built: the paired-test module, the catalog and inspector, goals,
and this repository's deployment. Open: the podcast repository running on the harness's copy (its
layer 4) and the 0.4.0 release.
**Date:** 2026-10-21
**Detail:** [PRD-004](../prd/PRD-004-catalog-and-inspector.md) (catalog and inspector),
[PRD-005](../prd/PRD-005-goals-and-rounds.md) (goals), [UXS-001](../uxs/UXS-001-catalog.md),
[UXS-002](../uxs/UXS-002-inspector.md), [RFC-003](../rfc/RFC-003-catalog-adapter.md) (the design,
the podcast code it came from, and where the build differs from this note)

## Context

A project that pins the harness built a catalog, a run inspector and a goal registry for itself,
with its own exact paired test, while the harness's paired test was written twice as a Monte
Carlo estimate. The owner decided these become the main content of 0.4.0.

## Decision

1. **One paired test**, `evaluation_harness.stats`, exact at 30 items or fewer: `pair-test`,
   `family-test` and the inspector all call it.
2. **A generic core with a project adapter**: the catalog and the inspector only ask an
   `Adapter` protocol; the built-in `HarnessAdapter` reads the harness's layout, so a project on
   it writes no code.
3. **Goals are first-class**: a schema, `goal:` on configs, carried by runs and baselines,
   checked by `validate`, optional until a project sets a date.
4. **The static pages never carry item text**; the inspector binds 127.0.0.1 and checks the Host.
5. **This repository is deployed as a full harness deployment** (catalog and public inspector
   beside the site); the owner's four answers: exact p in the CLI, a cut-over date the project
   sets, the catalog published, no intermediate releases.

## Consequences

The inspector and the CLI cannot disagree. Any project gets a catalog and inspector with one
adapter file, or none. Small-sample p-values became exact; no published claim here moved.
