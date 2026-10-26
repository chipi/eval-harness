# Product requirements (PRDs)

## Purpose

A PRD says **what** the harness does for the person using it, and **why**: the problem, who has
it, what they need to be able to do, and what is deliberately left out. It captures:

- **User needs** and the situations they come from;
- **Functional requirements**, numbered (FR1, FR1.1, ...), each one checkable;
- **Non-goals**, so a later reader does not "fix" a deliberate omission;
- **Links** to the experience (UXS), the technical design (RFC) and the decisions (ADR).

**Status vocabulary:** a PRD is **Draft** while it is being written, **Partial (vX.Y.Z)** when
some of it has shipped, and **Implemented (vX.Y.Z)** when all of it has. **Completed** and
**Accepted** are for RFCs and ADRs, not PRDs. Before a release, a PRD whose last part lands in
it says `Implemented (X.Y.Z, unreleased)` until the tag.

## How the documents fit together

New work starts with a PRD. From 0.4.0 on, the order is:

1. **PRD**: what the user needs and why ([this index](index.md)).
2. **UXS**: what the user sees and types, page by page and command by command, when the work
   has a surface ([UX specifications](../uxs/index.md)).
3. **RFC**: how it is built: data, interfaces, algorithms, alternatives
   ([proposals and designs](../rfc/index.md)).
4. **ADR**: a few lines recording a key decision and pointing at the documents above
   ([decisions](../adr/index.md)).

PRD-001 to PRD-007 were written for 0.4.0 from the code as it is, so each describes shipped
behaviour. PRD-008 to PRD-013 are the 0.5.0 drafts, held together by PRD-012: every capability
for people and agents alike. The release notes ([CHANGELOG](../../harness/CHANGELOG.md)) say what changed when.

## PRDs

| PRD | Title | Status | Related | What it covers |
| --- | ----- | ------ | ------- | -------------- |
| [PRD-001](PRD-001-experiments-and-comparison.md) | Running experiments and comparing arms | Implemented (v0.4.0) | [RFC-001](../rfc/RFC-001-fingerprint-and-code-identity.md), [RFC-002](../rfc/RFC-002-run-records-and-derived-runs.md), [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) | Frozen datasets, arms, runs with a fingerprint, the arm's own noise, paired tests with Holm, baselines with a reason |
| [PRD-002](PRD-002-references.md) | References: gold, silver, and a run as the reference | Implemented (v0.4.0) | [RFC-002](../rfc/RFC-002-run-records-and-derived-runs.md) | What outputs are scored against, who wrote it, re-scoring for $0 when it changes |
| [PRD-003](PRD-003-judging.md) | Re-measuring with a validated LLM judge | Implemented (0.3.0) | [RFC-005](../rfc/RFC-005-judge-scorers.md), [ADR-0001](../adr/ADR-0001-judge-scorers.md) | Judge scorers, the validation gate, two vendors, blind and stored verdicts |
| [PRD-004](PRD-004-catalog-and-inspector.md) | The catalog and the run inspector | Implemented (v0.4.0) | [UXS-001](../uxs/UXS-001-catalog.md), [UXS-002](../uxs/UXS-002-inspector.md), [RFC-003](../rfc/RFC-003-catalog-adapter.md), [ADR-0002](../adr/ADR-0002-catalog-inspector-goals.md) | Pages over the runs, an inspector that tests arms, read-only, every view also a command |
| [PRD-005](PRD-005-goals-and-rounds.md) | Goals, and experiment rounds | Implemented (v0.4.0) | [RFC-004](../rfc/RFC-004-experiment-rounds.md), [UXS-001](../uxs/UXS-001-catalog.md), [ADR-0004](../adr/ADR-0004-experiment-rounds.md) | What an evaluation is for and the measure that decides; optional rounds with a hypothesis, retirements and a conclusion |
| [PRD-006](PRD-006-datasets-versions-fields.md) | Datasets, versions and item fields | Implemented (v0.4.0) | [RFC-006](../rfc/RFC-006-item-fields-and-url-items.md), [ADR-0003](../adr/ADR-0003-item-fields-and-url-items.md) | Versions with lineage, typed item fields outside the identity, items at a pinned URL |
| [PRD-007](PRD-007-packaging-and-providers.md) | One install, your own keys | Implemented (v0.4.0) | [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) | The `evh` package, the project's own data, the adapter seam, hosted providers with keys you bring |
| [PRD-008](PRD-008-pipelines-and-any-language.md) | Pipelines, stages, and systems in any language | Draft (0.5.0) | RFC-007, RFC-008 (to write) | Span-shaped stages with their own references and scores; batch mode; JSON-RPC process adapter for any language |
| [PRD-009](PRD-009-prompts-and-optimisation.md) | Prompt versions, and optimisation studies | Draft (0.5.0) | RFC-009, RFC-010 (to write) | Versions of declared prompt files; exploratory and confirmatory studies (after Karpathy's autoresearch), harness- or agent-driven, built-in LLM sampler, a counted test check |
| [PRD-010](PRD-010-runners.md) | Runners: where experiments run | Draft (0.5.0) | RFC-011 (to write) | Detached job sets with standard states, retries and logs; a local runner in parallel; a simple ssh runner with phases |
| [PRD-011](PRD-011-evidence-registry.md) | The evidence registry | Draft (0.5.0) | RFC-012 (to write) | Champion versions per goal and dataset with frozen evidence, an export, and a check for a project's citations |
| [PRD-012](PRD-012-agent-ready.md) | Agent-ready: every capability for people and agents alike | Draft (0.5.0) | RFC-013 (to write) | Command manifest, --json, CLI conventions, who acted, an MCP server on the official SDK, skills; the test every 0.5.0 feature must pass |
| [PRD-013](PRD-013-identity-and-ties.md) | Baselines per goal, the host beside the hash, non-inferiority, test looks, one grammar | Draft (0.5.0) | RFC-014 (to write), [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md) | 0.4.0 corrections: baselines per goal and dataset, fingerprint v5, non-inferiority by a valid test against a declared margin, test looks as a budget, unique run ids, effects and power beside verdicts, one identifier grammar, `evh migrate` |

## Adding one

Name it `PRD-NNN-short-slug.md` (next number, three digits) with the header used here
(**Status**, **Authors**, **Related**), then the sections Summary, Background & Context, Goals,
Non-Goals, Personas, User Stories, Functional Requirements, Success Criteria and Related
Documents. Add its row to the table.
