# ADR-0023 — Picks wait in one list per project; a governed dataset grows only by a version you make (0.6.0)

**Status:** Proposed (2026-11-01), agreed with the owner in RFC-023's review; accepted when RFC-023 is.
**Date:** 2026-11-01
**Detail:** [RFC-023](../rfc/RFC-023-labels-and-references.md), [PRD-014](../prd/PRD-014-datasets-from-production.md)
(FR8 to FR10), [UXS-002](../uxs/UXS-002-inspector.md) (the rows view)

## Context

After many evaluations of production data, the owner makes the next version of a key dataset from a few production
records that would most help. A good record is often noticed before its target dataset is known, across many
captures and many evaluations, and nothing kept it until the version was made.

## Decision

- A **pick** marks a production item as a candidate for one or more governed datasets, or none yet, with tags and
  a note. Picks wait in the project's one list, `data/picks.jsonl`, in git; the list is append-only, the latest line
  for an item wins, and a dropped or used pick keeps its history.
- A governed dataset grows only by a version you make on purpose: `dataset-extend V1 --dataset-id V2` with the picks
  you choose, the lineage recorded per item. Its references are then promoted as for any dataset; nothing is
  promoted by the extension.
- The pages never write (PRD-004, ADR-0004): the rows view and the dataset page select and give the `pick` and
  `dataset-extend` commands.

## Consequences

- Candidates accumulate across captures and evaluations without deciding their target early.
- A version records where every added item came from, so its origin is never lost.
- Picking in the browser means copying a command; labelling or picking by clicking is a later question.

## Alternatives considered

- **One pick list per governed dataset.** Rejected by the owner: a good item is often seen before its target.
- **Building a version, or picking, from the pages.** Rejected: the pages never write.
