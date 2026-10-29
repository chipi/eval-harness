# ADR-0009 — The harness versions declared prompt files (0.7.0)

**Status:** Accepted (2026-10-26), design; not yet built. Revision 3 (2026-10-27): paths are the ones the system reads (no `pkg:`), names as
written. Revision 2: content-addressed versions, no numbers, index, lock or aliases. Amends [PRD-001](../prd/PRD-001-experiments-and-comparison.md)'s
"not a prompt store" (already noted there).
**Date:** 2026-10-26
**Detail:** [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) FR1,
[RFC-009](../rfc/RFC-009-prompt-versions.md) (resolution, overlay, fingerprint, commands)

## Context

A prompt in a file reached the fingerprint only if the adapter hashed it, and then as a different
system rather than a different arm. Optimisation studies must create prompt versions, reuse them
and export a winner, but prompts live where production reads them (the podcast project's 204 Jinja
files in its pipeline library), which a trial cannot write into without making the build dirty or
touching an installed package.

## Decision

- **A config declares the prompt files its system uses**, by name, wherever they live, or a prompt
  root directory and the files in it that may vary. Prompts stay where the project keeps them; the
  owner rejected a store the project moves them into.
- **Versions are content snapshots named by their hash** in `data/prompts/<name>/`, recorded
  automatically when a run sees new bytes (no invented lineage: a parent only when someone states it).
  Two runs or two clones that see the same bytes write the same record, so no lock, number or index is
  needed; "v3" is a display number. There are no aliases: the baseline records which version production
  uses.
- **Prompts and the root's digest are part of the arm** in the fingerprint.
- **A per-run overlay directory** gives the system its prompts (a copy of the root with the varied
  files replaced), so no tracked file is written; the system takes it by its own mechanism
  (`PROMPT_DIR` for a subprocess, `set_prompt_dir` in process).
- **The harness's record directories do not make a build dirty**; validation checks their
  integrity instead.

## Consequences

Every run's prompts are in a history that can be read, diffed and exported; a study can try a
version without editing a file. The harness hashes bytes and never renders a template.
