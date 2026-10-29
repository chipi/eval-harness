# UX specifications (UXS)

## Purpose

A UXS describes the **experience**: what a user sees on each page, what each control does, what
the commands print and in which order a newcomer meets them. It is the contract reviewers and
the browser tests check a change against. It complements:

- **PRDs**: what and why ([product requirements](../prd/index.md));
- **RFCs**: how it is built ([designs](../rfc/index.md));
- **ADRs**: the key decisions, in a few lines each ([decisions](../adr/index.md)).

## When to write one

Write or extend a UXS when work adds or changes a **surface**: a catalog page, the inspector,
a command's output or flags, or the onboarding path. A change that only moves internals needs an
RFC, not a UXS.

## The rules every surface keeps

These hold across all three specifications below; a change that breaks one needs a decision
(an ADR), not just a UXS edit.

1. **The catalog is read-only.** No page writes to the data tree. A decision the pages suggest
   is shown as the command that makes it, run locally.
2. **Command-line parity.** Every view and every action in the UI also exists as an `evh`
   command that asks the same adapter and computes with the same functions, so a number on a
   page is the number in the terminal. New surfaces add both. The table is in
   [UXS-003](UXS-003-cli-and-onboarding.md#the-parity-table).
3. **No item text in static pages.** Outputs, references and the items themselves reach a
   browser only through the local inspector server.
4. **Say what a number is measured against.** Every row of arms names its reference or judge,
   and the tints in [UXS-001](UXS-001-catalog.md#row-tints) mark the ones not scored against gold.
5. **Refuse, do not guess.** A comparison that cannot be made (two datasets, two references) is
   refused or set aside with the reason, never computed anyway.

## UXS vs RFC boundary

A UXS owns what is visible: pages, sections, columns, controls, words, tokens, the order of
output. The RFC owns behaviour behind it: data formats, caching, the server's limits, the
algorithms. When a rule could live in either, it goes in the RFC and the UXS links it.

## Status lifecycle

| Status | Meaning |
| --- | --- |
| **Draft** | Under review; may change before it is built |
| **Active** | Describes what is built; changes to the surface update it in the same PR |
| **Superseded** | Replaced by a newer UXS, linked from it |

## UX specifications

| UXS | Title | Status | Related PRDs / RFCs | What it covers |
| --- | ----- | ------ | ------------------- | -------------- |
| [UXS-001](UXS-001-catalog.md) | The catalog | Active; 0.7.0 changes in draft | [PRD-004](../prd/PRD-004-catalog-and-inspector.md), [PRD-005](../prd/PRD-005-goals-and-rounds.md), [PRD-006](../prd/PRD-006-datasets-versions-fields.md); [RFC-003](../rfc/RFC-003-catalog-adapter.md) | The shared shell and tokens; the period on every listing page; home, activity, datasets, dataset, arms and configs, arm, goals, goal (answer first, rounds), references, reference, metrics and metric pages; tints, paging, search |
| [UXS-002](UXS-002-inspector.md) | The run inspector | Active; 0.7.0 changes in draft | [PRD-004](../prd/PRD-004-catalog-and-inspector.md), [PRD-006](../prd/PRD-006-datasets-versions-fields.md); [RFC-003](../rfc/RFC-003-catalog-adapter.md) | Choosing arms, testing against a baseline, conditions, fields, the analysis charts, the per-item table, one item side by side |
| [UXS-003](UXS-003-cli-and-onboarding.md) | The command line and the first evaluation | Active; 0.7.0 changes in draft | [PRD-001](../prd/PRD-001-experiments-and-comparison.md), [PRD-007](../prd/PRD-007-packaging-and-providers.md) | The onboarding path, how commands speak (refusals, hints, exit codes), the parity table, the round flow |
| [UXS-004](UXS-004-studies-baselines-prompts.md) | Studies, baselines and prompts | Draft (0.7.0) | [PRD-009](../prd/PRD-009-prompts-and-optimisation.md), [PRD-011](../prd/PRD-011-evidence-registry.md), [PRD-013](../prd/PRD-013-identity-and-ties.md); [RFC-010](../rfc/RFC-010-studies.md), [RFC-012](../rfc/RFC-012-evidence-registry.md), [RFC-015](../rfc/RFC-015-noninferiority-looks-power.md) | The words and marks for verdicts, looks and actors; the baselines, studies and prompts pages; a study page that keeps search apart from evidence |
| [UXS-005](UXS-005-agents.md) | The harness for agents: tools, consent, skills, llms.txt | Draft (0.7.0) | [PRD-012](../prd/PRD-012-agent-ready.md); [RFC-013](../rfc/RFC-013-machine-surface.md), [RFC-016](../rfc/RFC-016-mcp-server-and-skills.md) | MCP tools and resources as an agent sees them, refusals and consent from both sides, long work, the skills, the agent-driven study, llms.txt and the glossary |

## Adding one

Name it `UXS-NNN-short-slug.md` (next number, three digits), with **Status**, **Authors**,
**Related PRDs**, **Related RFCs** and **Implementation paths**, then Summary, Principles,
Scope (with non-goals), and the surface itself. Add its row here.
