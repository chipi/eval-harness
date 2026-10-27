# ADR-0014 — Fingerprint version 5, run ids, one grammar, a one-time migration (0.5.0)

**Status:** Accepted (2026-10-26), design; not yet built
**Date:** 2026-10-26
**Detail:** [PRD-013](../prd/PRD-013-identity-and-ties.md) FR1, FR2, FR4, FR8,
[RFC-014](../rfc/RFC-014-identity-baselines-migration.md), [RFC-001](../rfc/RFC-001-fingerprint-and-code-identity.md)
(version 4)

## Context

The fingerprint hashed the host's label, kernel and processor string, so the same arm on two
machines read as an uncontrolled comparison; the hash excluded only itself, and nothing recomputed
it. Two runs started in the same second shared a directory. Ids of different things were written in
different ways. 0.4.0's data changes were one-off scripts kept outside the repository.

## Decision

- **Fingerprint version 5**: platform, Python and the accelerator stack stay inside the hash; the
  machine's label, release, processor and CPU count move to `machine`, outside it. An imported
  run's host, libraries and harness describe the importer, so they are outside too. The excluded
  fields are an explicit list per version, and `validate` recomputes every hash.
- **Run ids gain milliseconds and a random suffix**; creating a run refuses an existing directory.
- **One identifier grammar**, `kind:path/n` for a fixed version and `kind:path@alias` for a moving
  pointer, with a closed list of kinds; segments admit the existing run ids.
- **Records that parallel commands write** go through one exclusive-create lock helper.
- **The migration is a one-time, re-runnable script** shipped in the package
  (`python -m evaluation_harness.migrate_0_5_0`), not an `evh` command (the owner's decision: two
  known projects, one move). It trusts only stored bodies, tags the starting point, leaves
  reference digests unchanged, and is removed in a later release.

## Consequences

The same arm on two machines compares as controlled on quality, with speed and cost flagged. Every
committed `metrics.json` here and in the podcast project is rewritten once; the version-4 hash is
kept beside the new one.
