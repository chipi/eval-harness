# ADR-0001 — Judge scorers: re-measuring frozen outputs with a validated LLM judge

**Status:** Accepted (2026-10-21)
**Date:** 2026-10-19
**Detail:** [PRD-003](../prd/PRD-003-judging.md) (what and why), [RFC-005](../rfc/RFC-005-judge-scorers.md)
(the design, the alternatives, and what the first uses found)

## Context

A run's outputs are the frozen record and its scores can be recomputed, so a better scorer can
re-measure an experiment without rerunning its arms. In this repository the SummEval experiment
validated LLM judges that agree with human experts far better than the summarisation
experiment's own metric. A judge, though, is a model: billed, noisy, valid only under the
protocol it was validated with, and able to prefer its own vendor family.

## Decision

- A **judge scorer** is its own artifact, `data/scorers/<scorer_id>.yaml`, and judging is a
  cross-run pass, `evh judge-score`, not a code scorer inside `rescore`.
- The harness **refuses a judge** until its scorer names, for each judge, a committed run that
  validated it against human ratings; `--unvalidated` runs it with every number labelled.
- **At least two judges from different vendor families**, listwise, blind and shuffled; position
  and noise measured on subsets; every verdict stored, so re-reading costs $0.
- Judged scores are **derived runs** in `data/runs-judged/<scorer_id>/`; the originals are never
  touched, and a judged score replaces a primary metric only by a recorded decision.

## Consequences

Experiments can be re-measured as scoring improves, with every existing test unchanged. Listwise
scores depend on the arm set, so adding an arm means a new pass; the validation transfers only
partly, and a report must say how.
