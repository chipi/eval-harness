# ADR-0010 — Studies: research by an ask/tell loop, and one test that is evidence (0.7.0)

**Status:** Accepted (2026-10-26), design; not yet built. Revision 3 (2026-10-27): one kind of study; evidence
only from a confirmation. Revision 2: one dev dataset per study; grid, command and agent samplers; a spec and an event log. Several datasets per study, a built-in LLM sampler, contested-judgement policies and column-map imports are deferred.
**Date:** 2026-10-26
**Detail:** [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) FR2 to FR5,
[RFC-010](../rfc/RFC-010-studies.md) (files, the loop, samplers, the confirmation, imports),
[INFLUENCES](../INFLUENCES.md) (Karpathy's autoresearch)

## Context

Projects already optimise prompts and parameters with loops outside the harness (the podcast
project's agent programs and parameter sweep, after Karpathy's autoresearch). Their results sit in
TSV files the catalog cannot show, a change is kept on a fixed 1% gain on the tuning items, and
nothing protects the items used to claim the winner is better.

## Decision

- **A study is research**, never evidence by itself. It owns a round, which does not block other rounds.
- **The loop is ask/tell**: a sampler proposes a trial (parameters or prompt versions, with a
  hypothesis); the harness runs it on the study's dev dataset, compares it with the best so far and the baseline,
  and keeps or drops it by the declared rule. Code is never among the changes.
- **Samplers are pluggable**: a grid over the space, an external command (Optuna, or any optimiser,
  through ask/tell), or the calling agent through `study-ask` and `study-tell`, which is how
  autoresearch's loop runs here.
- **A study is a spec and one append-only event log**, the typed form of autoresearch's `results.tsv`;
  its state and its trials' configs are read from the log, never stored apart.
- **Limits and tie-break acceptance are judged against the baseline**, so concessions
  cannot accumulate.
- **Keeping a trial is research; a confirmation is the only evidence**: `study-confirm`, with its rule
  given before the heldout items are looked at, tests the best trial against the baseline on heldout items
  the study never saw (the dev items and every item shown to a sampler are excluded), counted as one look.
- **A study never promotes**: it suggests; a person promotes, or an agent with the person's
  consent.

## Consequences

Past loops can be imported (Karpathy's `results.tsv`; other formats are converted to it) and shown as
closed, untestable studies. A study on small dev sets mostly ends "inconclusive"; that is
the honest outcome, not a defect.
