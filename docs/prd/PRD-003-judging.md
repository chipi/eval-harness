# PRD-003: Re-measuring with a validated LLM judge

- **Status**: Implemented (0.3.0)
- **Authors**: Marko Dragoljevic
- **Related RFC**: [RFC-005](../rfc/RFC-005-judge-scorers.md) (the judging pass, technically)
- **Related ADR**: [ADR-0001](../adr/ADR-0001-judge-scorers.md)
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md), [PRD-002](PRD-002-references.md)

## Summary

A run's outputs are the expensive, frozen record; its scores are arithmetic over them. When a
better instrument appears, the same outputs can be measured again without paying for the arms
again. Three kinds of re-measurement exist: a new reference and a new code scorer (both $0,
`evh rescore`), and an **LLM judge** (billed, `evh judge-score`). Because a judge is itself a
model, noisy and able to prefer its own family, the harness treats it like an arm: it refuses a
judge until a committed run shows it agrees with human ratings, runs at least two judges from
different vendors blind, measures their position bias and noise, and stores every verdict so a
rerun costs $0.

## Background & Context

In this repository, the summarisation experiment ranked 29 arms by its own overlap metric, and
the SummEval experiment then showed that metric agrees with human experts far less than the
best LLM judges do. One experiment had validated a better instrument for another. The full
reasoning, and what the first uses found, are in [RFC-005](../rfc/RFC-005-judge-scorers.md);
how to run it is in [Runbook §12](../../harness/docs/RUNBOOK.md#12-re-measure-with-a-validated-judge)
and step 10 of the [GUIDE](../GUIDE.md).

## Goals

- Re-measure frozen outputs with a better scorer, without regenerating them.
- Never present an unvalidated judge's number as a measurement.
- Make a judge's verdicts as reproducible as a run: frozen, fingerprinted, re-readable for $0.
- Keep every existing test (leaderboard, pair-test, family-test) working unchanged on judged
  scores.
- Keep the spend bounded.

## Non-Goals

- A judged score never replaces an experiment's primary metric by itself: that is a recorded
  decision ([Concepts](../../harness/docs/CONCEPTS.md#re-measuring-a-frozen-experiment)).
- The gate checks that a validation exists and is current, not that it transfers to the
  user's outputs.
- Not the older judge **panel** (`evh judge`), which narrows finalists on a cheap metric and
  judges them pointwise; it stays a triage tool.
- No human-rating collection tool.

## Personas

- **The researcher** whose primary metric is known to track people poorly.
- **The engineer** with outputs that no code scorer captures (tone, faithfulness).
- **The reviewer** who must know which numbers came from a model.

## User Stories

- _As a researcher, I can price a judging pass first (`--dry-run`) and cap its cost._
- _As a researcher, I am refused when my scorer names no validation run for a judge, and can
  run it anyway only with every number labelled "unvalidated judge" (`--unvalidated`)._
- _As a reviewer, I can see each judge's score, their agreement, and whether an arm shares a
  judge's vendor family._
- _As an engineer, I can read judged runs with the usual commands
  (`EVAL_RUNS_DIR=data/runs-judged/<scorer> evh leaderboard --dataset-id …`)._

## Functional Requirements

### FR1: The scorer

- **FR1.1**: A judge scorer is a file, `data/scorers/<scorer_id>.yaml`, with `kind: judge`, the
  judges (model specs), the task (what an item is, what the outputs are, the dimensions and the
  scale), the prompt, the protocol, a `validation` block and a cost cap.
- **FR1.2**: It needs at least two judges from different vendor families.

### FR2: The gate

- **FR2.1**: A scorer runs only if its `validation` block names, for each judge, a committed run
  whose metric equals the stated value and whose model, settings and prompt are the judge's.
- **FR2.2**: `--unvalidated` overrides the gate and every number then carries the label
  "unvalidated judge". `provider: fake` judges (offline, for testing a scorer) never pass it.

### FR3: The pass

- **FR3.1**: `evh judge-score --dataset-id … --scorer …` builds a frozen judging set (one item:
  the source and every arm's output for it), hides arm identities and shuffles their order per
  item with a recorded seed.
- **FR3.2**: Every reply is stored; a rerun skips what is stored and `--no-calls` re-reads stored
  verdicts for $0. A cost cap stops it mid-run with what was bought kept.
- **FR3.3**: A second shuffle on a subset measures position bias; a repeat on a subset measures
  the judge's own noise.
- **FR3.4**: Verdicts are projected to one score per arm per item and written as runs in
  `data/runs-judged/<scorer_id>/`; the originals are never touched.

### FR4: Where it shows

- **FR4.1**: A judged arm's row on the catalog reads "judge <scorer>" and is tinted; judged and
  reference-scored numbers are never ranked together
  ([UXS-001](../uxs/UXS-001-catalog.md)).

## Success Criteria

- GUIDE step 10 runs offline and free with fake judges, through the refusal, the dry run, the
  pass and the leaderboard (`make guide-check`).
- Re-reading stored verdicts reproduces the judged runs without a call.

## Related Documents

- [RFC-005](../rfc/RFC-005-judge-scorers.md), [ADR-0001](../adr/ADR-0001-judge-scorers.md).
- The [judging page](https://evals.humancopilot.eu/experiments/judging.html): what judging found
  in this repository.
