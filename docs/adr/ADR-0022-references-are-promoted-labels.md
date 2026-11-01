# ADR-0022 — A reference is labels you promote; the tier is chosen then (0.6.0)

**Status:** Accepted (owner, 2026-11-01), with RFC-023; built for 0.6.0. Supersedes
[ADR-0020](ADR-0020-second-references-are-silver.md) and ADR-0019's references from outcomes.
**Date:** 2026-11-01
**Detail:** [RFC-023](../rfc/RFC-023-labels-and-references.md), [PRD-002](../prd/PRD-002-references.md),
[PRD-014](../prd/PRD-014-datasets-from-production.md), [UXS-001](../uxs/UXS-001-catalog.md)

## Context

`reference-create` made a reference by asking a model what it would do (`--from-run`, `--config`), so a model doing
the task and someone saying what is right were one command. Labelling lived outside the harness; the tier was
taken on the user's word; ADR-0020 stretched "silver" to cover labels from outcomes. Evaluating what production did
needs someone, a person, a model or a rule over recorded outcomes, to say what was right on new items, without
making a reference each time.

## Decision

- A **label** says what is right for one item and who said it: its **source**, `person`, `model` or `rule`,
  recorded with when and the guideline followed. Labels come in **sets**, never edited, and follow an item by its
  sha256 into any dataset holding the same item.
- A **reference** is made only by **promoting** labels: chosen on purpose, with a reason, at the tier you decide.
  No rule ties the tier to the source; the promotion records the source beside the tier.
- Arms can be scored against a label set without promoting it; every view names what a number was scored against,
  a reference with its tier or a label set with its source.
- `reference-create` and `reference-from-outcomes` are removed; every existing reference is migrated to a label
  set and a promotion record, every run's score unchanged.

## Consequences

- Evaluating production data never creates a reference; references stay governed.
- One way to make a reference, and a record of where every reference came from.
- A person's poor labels, or a model's, are simply never promoted.
- Two more things to read on every page (a tier pill, a source chip), kept visually apart so neither is mistaken
  for the other.

## Alternatives considered

- **Keep `reference-create` beside labelling.** Rejected: two ways to make a reference, one asking a model what it
  would do.
- **Tier from the source** (a person's labels are gold). Rejected by the owner: a person's labelling can be poor.
- **Enforce gold only from a person's labels.** Rejected by the owner: the promotion decides.
