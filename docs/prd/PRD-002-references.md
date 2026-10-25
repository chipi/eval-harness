# PRD-002: References: gold, silver, and a run as the reference

- **Status**: Implemented (v0.4.0); gold and silver since 0.1.0, a run as the reference in 0.4.0
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (reference pages, row tints),
  [UXS-002](../uxs/UXS-002-inspector.md) (what the inspector refuses to compare)
- **Related RFC**: [RFC-002](../rfc/RFC-002-run-records-and-derived-runs.md) (derived runs: rescore onto another reference)
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md), [PRD-003](PRD-003-judging.md)

## Summary

Most quality metrics score an output against a **reference**: the answer each item should get.
The harness keeps two tiers apart. **Gold** is written or checked by a person; **silver** is
written by a model. Silver is consistent, not correct: good for ranking arms against each other,
never a claim that any of them is right. A user can make silver in a pass of its own, or, from
0.4.0, by taking the outputs of a run they have already read and freezing them as the
reference. When the reference changes, every arm is re-scored from its stored outputs for $0.

## Background & Context

Gold is expensive and often missing at the start. The common practice is to run the strongest
model available, read its outputs, and score the cheaper arms against what it wrote. Until
0.4.0 that took a second paid pass, whose outputs could differ from the run that was read, and
the reference did not say which run it came from. And an arm scored against the reference it
wrote itself is graded against its own outputs: it should never be the leader of that table.

The reasoning is in [Concepts: Gold is not silver](../../harness/docs/CONCEPTS.md#gold-is-not-silver);
the commands in §4b of the [Runbook](../../harness/docs/RUNBOOK.md).

## Goals

- Every scored number says which reference it was scored against, and that reference's tier.
- Silver and gold numbers are never ranked together or tested against each other.
- A finished run can become the reference without a second paid pass, and the reference says
  which run, config, fingerprint, build and cost it came from.
- A reference never silently freezes broken outputs (empty, or cut off at `max_tokens`).
- Changing the reference costs nothing: stored outputs are re-scored, never regenerated.
- How far silver drifts from gold can be measured once gold exists.

## Non-Goals

- No reference authoring interface: gold is files a person writes or checks.
- No automatic promotion of silver to gold (`--tier gold` is refused for a run's outputs).
- No redistribution of a dataset's gold where its licence does not allow it; the examples here
  fetch it ([Data & licences](../DATA.md)).

## Personas

- **The engineer with no gold yet**: needs a usable yardstick today, labelled for what it is.
- **The annotator or domain expert**: writes or checks gold for a subset, later.
- **The reviewer**: needs to see at a glance which numbers rest on a person's answers.

## User Stories

- _As an engineer, I can run a frontier model as an arm, read its results, and make that run's
  outputs the silver reference (`evh reference-create --dataset-id … --from-run <run_id>`), so
  the reference is exactly what I read._
- _As an engineer, I am refused when the run I chose stopped at `max_tokens` or wrote an empty
  output, so a broken reference is never frozen without a word._
- _As a researcher, when gold arrives after the runs, I can re-score every run against it
  (`evh rescore --reference-id gold/…`) for $0, into a separate directory._
- _As a reviewer, I can see which arm wrote the reference a table is scored against, so I do not
  read its row as a result._
- _As a researcher, I can measure how far silver drifts from gold (`evh silver-calibrate`)._

## Functional Requirements

### FR1: Two tiers

- **FR1.1**: Gold lives in `data/references/gold/<dataset_id>/<item_id>.txt`; silver in
  `data/references/silver/<dataset_id>/`, with a `manifest.json` recording who wrote it.
- **FR1.2**: A run records the reference it was scored against (`reference_id`, tier) and a hash
  of the reference's bytes, inside its fingerprint (RFC-001), so an edited reference file shows
  as a different measurement.

### FR2: Making silver

- **FR2.1**: `evh reference-create --dataset-id … --config …` writes silver in a pass of its own
  with that arm (`--limit N` for a cheap first pass).
- **FR2.2**: `evh reference-create --dataset-id … --from-run <run_id>` copies a finished run's
  outputs and calls nothing. The manifest records the run, its config, fingerprint, build and
  cost.
- **FR2.3**: `--from-run` refuses what `run-promote` refuses (a dirty tree, an unknown build),
  an unfinished, derived or other-dataset run, and `--tier gold`.
- **FR2.4**: Both paths refuse an empty output and outputs that stopped at `max_tokens`
  (`--allow-cut-off` for outputs that end at the cap by design).
- **FR2.5**: `reference-create` says when gold exists (new runs keep scoring against gold), and
  that the reference must be committed before the next run, or every later run is dirty.

### FR3: The arm that wrote the reference

- **FR3.1**: The leaderboard marks it (`arm *`, with a note).
- **FR3.2**: The catalog tints its row and a goal page flags it, so it is never a group's leader
  ([UXS-001](../uxs/UXS-001-catalog.md)).

### FR4: Changing the reference

- **FR4.1**: `evh rescore --dataset-id … --reference-id gold/… --out data/runs-gold` re-scores
  every run's stored outputs against another reference, $0, into a separate directory; the
  originals are never touched (RFC-002).
- **FR4.2**: A re-scored run records the reference it was first measured against
  (`reference_id_at_measurement`).
- **FR4.3**: `evh silver-calibrate --dataset-id …` reports how far silver references drift from
  gold.
- **FR4.4**: The inspector, on a metric scored against a reference, does not test an arm scored
  against another reference than the baseline's; it names it and says why
  ([UXS-002](../uxs/UXS-002-inspector.md)).

## Success Criteria

- A reference made from a run records where it came from, and the refusals above hold
  (`harness/tests/test_reference_from_run.py`: provenance, refusals, the author's row).
- No table on the pages or in the terminal ranks a silver-scored arm with a gold-scored one.

## Related Documents

- [RFC-002](../rfc/RFC-002-run-records-and-derived-runs.md): derived runs.
- [Runbook §11, adjudicating disputed gold](../../harness/docs/RUNBOOK.md#11-adjudicate-disputed-gold).
