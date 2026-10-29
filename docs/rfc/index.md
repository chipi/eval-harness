# Designs (RFCs)

## Purpose

An RFC holds the **how**: the technical design behind a requirement. It captures:

- the **problem** the design solves, with the evidence;
- the **design**: data formats, interfaces, algorithms, what each command reads and writes;
- the **alternatives** considered and why they were set aside;
- **what changes for a project** pinning the harness, and how it is **tested**.

An RFC implements a [PRD](../prd/index.md) and is referenced by the
[UX specification](../uxs/index.md) of any surface it drives. The key decision it settles is
recorded in a few lines as an [ADR](../adr/index.md), which links back here for the detail.

## How RFCs work

1. **Reference the PRD**: what the user needs comes first ([PRD index](../prd/index.md)).
2. **Design**: the RFC is argued while it is **Draft** and may change freely.
3. **Build**: **In Progress** while the code lands.
4. **Completed (vX.Y.Z)**: the design is built; a later change to it is a new RFC, or a dated
   note in this one that says what changed and when.

Other statuses: **Rejected** and **Withdrawn**, each with the reason kept.

## Open RFCs

| RFC | Title | Related PRD | Status | Description |
| --- | ----- | ----------- | ------ | ----------- |
| [RFC-019](RFC-019-datasets-from-production.md) | Datasets from production: a lane beside the method (draft for review) | [PRD-006](../prd/PRD-006-datasets-versions-fields.md) | Draft (aim 0.6.0) | A capture lane of new commands ending in ordinary datasets and references; importers (jsonl, tsv, github, langfuse built in); optional scrub; versions; references from outcomes as of a date; dev/heldout splits as two datasets; a `text: hidden` label on every public surface; stateless, no server; designed on a triage fleet |

## Completed RFCs

| RFC | Title | Related PRD | Version | Description |
| --- | ----- | ----------- | ------- | ----------- |
| [RFC-001](RFC-001-fingerprint-and-code-identity.md) | The run fingerprint and code identity (v4) | [PRD-001](../prd/PRD-001-experiments-and-comparison.md) | 0.4.0 | What a run records it was measured under; code hashed by its syntax tree, so documentation never moves a fingerprint |
| [RFC-002](RFC-002-run-records-and-derived-runs.md) | Run records and derived runs | [PRD-001](../prd/PRD-001-experiments-and-comparison.md), [PRD-002](../prd/PRD-002-references.md) | 0.4.0 | One record format; `derived: {kind, from, at, with}` for rescored, judged and re-parsed runs |
| [RFC-003](RFC-003-catalog-adapter.md) | The catalog, the inspector server and the adapter protocol | [PRD-004](../prd/PRD-004-catalog-and-inspector.md) | 0.4.0 | One paired test; the questions an adapter answers; the build; the server's local and public modes |
| [RFC-004](RFC-004-experiment-rounds.md) | Experiment rounds | [PRD-005](../prd/PRD-005-goals-and-rounds.md) | 0.4.0 | Round records, membership by `round:`, the four commands, the evidence and its suggestions |
| [RFC-005](RFC-005-judge-scorers.md) | Judge scorers and the judging pass | [PRD-003](../prd/PRD-003-judging.md) | 0.3.0 | The scorer artifact, the validation gate, the listwise blind pass, its controls, judged runs |
| [RFC-006](RFC-006-item-fields-and-url-items.md) | Item fields and items at a URL | [PRD-006](../prd/PRD-006-datasets-versions-fields.md) | 0.4.0 | Field sets and types, `fields_sha256` outside the identity, V15, filters and breakdowns, pinned downloads |
| [RFC-018](RFC-018-read-only-mcp-server.md) | A read-only MCP server | [0.7.0's PRD-012](https://github.com/chipi/eval-harness/blob/070/docs/prd/PRD-012-agent-ready.md) (branch `070`) | 0.5.0 | `evh mcp` on the official SDK, stdio and Streamable HTTP; thirteen read commands as tools, each a child process; `--public`, rate, Host check; `--json` for the views; the goals' tests on disk; this repository's server at /mcp; Python 3.10 |

## Adding one

Name it `RFC-NNN-short-slug.md` (next number, three digits) with **Status**, **Authors**,
**Related PRDs**, **Related RFCs** and **Code**, then Abstract, Problem Statement, Design,
Alternatives Considered and Testing (and Open questions while it is a draft). Add its row under
Open RFCs.
