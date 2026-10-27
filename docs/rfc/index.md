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

None.

## Draft RFCs (0.5.0)

| RFC | Title | Related PRD | Description |
| --- | ----- | ----------- | ----------- |
| [RFC-007](RFC-007-stages-and-stage-references.md) | Stages, stage references, structured outputs, item fields, batch mode | [PRD-008](../prd/PRD-008-pipelines-and-any-language.md) | Span-shaped stages beside outputs, <stage>.<metric> scores, per-stage references, JSON outputs, call forms, batch mode with the cost cap, item failures, the wrapping recipe, OTLP import |
| [RFC-008](RFC-008-process-protocol.md) | The process protocol: systems in any language | [PRD-008](../prd/PRD-008-pipelines-and-any-language.md) | JSON-RPC 2.0 over stdio (evh-adapter/1.0), wrapped as an ordinary adapter; the system's identity is the arm; a Node example; adapter-check |
| [RFC-009](RFC-009-prompt-versions.md) | Prompt versions | [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) | Declared prompt files or a prompt root; content-addressed versions in data/prompts, resolved at run time; arm.prompts in the fingerprint; a per-run overlay; prompt commands and pages |
| [RFC-010](RFC-010-studies.md) | Studies: exploratory and confirmatory, trials, samplers, the heldout check | [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) | A spec and one event log per study; an ask/tell loop on the dev dataset, decisions against the best so far and the baseline; grid, command and agent samplers; the counted heldout check; Karpathy's results.tsv import |
| [RFC-011](RFC-011-job-sets-and-runners.md) | Job sets and runners: local and ssh | [PRD-010](../prd/PRD-010-runners.md) | A detached supervisor, standard job states, timeouts, retries, attempts as runs; phases with check/before/after and consent; the ssh runner as a git checkout of the pushed commit, ignored data by rsync |
| [RFC-012](RFC-012-evidence-registry.md) | The evidence registry: baselines' evidence, the export, the check | [PRD-011](../prd/PRD-011-evidence-registry.md) | The verdict frozen at promotion; evh baselines; a deterministic evh-baselines/1 export with how to reproduce each baseline and its intended use; evidence-check over any citation file |
| [RFC-013](RFC-013-machine-surface.md) | The machine surface: declarations, JSON, exit codes, refusals, the actor, the config | [PRD-012](../prd/PRD-012-agent-ready.md) | One declaration per command (help, manifest, MCP tools); --json and output schemas; exit codes; RFC 9457 refusals; the actor; consent as the person's own command; config.yaml; Python 3.10 |
| [RFC-014](RFC-014-identity-baselines-migration.md) | Identity in 0.5.0: baselines, fingerprint v5, run ids, one grammar, the migration | [PRD-013](../prd/PRD-013-identity-and-ties.md), [PRD-011](../prd/PRD-011-evidence-registry.md) | Write-once baseline versions per goal and dataset, the newest current; machine outside the hash; unique run ids; kind:path/<version>; the one-time migration script |
| [RFC-015](RFC-015-noninferiority-looks-power.md) | The statistics of 0.5.0: non-inferiority, verdicts, heldout looks, power | [PRD-013](../prd/PRD-013-identity-and-ties.md), [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) | Tests chosen by simulation (Tango for 0/1; bootstrap-t at half the level from 100 items for continuous), the verdict sequence, Holm across candidates, front-loaded looks counted from decisions, attainable p and MDE |
| [RFC-016](RFC-016-mcp-server-and-skills.md) | The MCP server, the skills, llms.txt and the glossary | [PRD-012](../prd/PRD-012-agent-ready.md) | evh mcp on the official SDK, tools from the manifest, resources, job ids for long work, consent through the person or an allowed elicitation, a tracked limits file, budgets from recorded spend; skills; llms.txt; a glossary |
| [RFC-017](RFC-017-record-store.md) | The record store: records, ids and one store contract | [PRD-011](../prd/PRD-011-evidence-registry.md), [PRD-012](../prd/PRD-012-agent-ready.md), [PRD-013](../prd/PRD-013-identity-and-ties.md) | Write-once records with collision-free ids; nothing derivable stored; one store contract (create-if-absent, get, list, append) for files in git now and a database later; what validate reports after a merge |

## Completed RFCs

| RFC | Title | Related PRD | Version | Description |
| --- | ----- | ----------- | ------- | ----------- |
| [RFC-001](RFC-001-fingerprint-and-code-identity.md) | The run fingerprint and code identity (v4) | [PRD-001](../prd/PRD-001-experiments-and-comparison.md) | 0.4.0 | What a run records it was measured under; code hashed by its syntax tree, so documentation never moves a fingerprint |
| [RFC-002](RFC-002-run-records-and-derived-runs.md) | Run records and derived runs | [PRD-001](../prd/PRD-001-experiments-and-comparison.md), [PRD-002](../prd/PRD-002-references.md) | 0.4.0 | One record format; `derived: {kind, from, at, with}` for rescored, judged and re-parsed runs |
| [RFC-003](RFC-003-catalog-adapter.md) | The catalog, the inspector server and the adapter protocol | [PRD-004](../prd/PRD-004-catalog-and-inspector.md) | 0.4.0 | One paired test; the questions an adapter answers; the build; the server's local and public modes |
| [RFC-004](RFC-004-experiment-rounds.md) | Experiment rounds | [PRD-005](../prd/PRD-005-goals-and-rounds.md) | 0.4.0 | Round records, membership by `round:`, the four commands, the evidence and its suggestions |
| [RFC-005](RFC-005-judge-scorers.md) | Judge scorers and the judging pass | [PRD-003](../prd/PRD-003-judging.md) | 0.3.0 | The scorer artifact, the validation gate, the listwise blind pass, its controls, judged runs |
| [RFC-006](RFC-006-item-fields-and-url-items.md) | Item fields and items at a URL | [PRD-006](../prd/PRD-006-datasets-versions-fields.md) | 0.4.0 | Field sets and types, `fields_sha256` outside the identity, V15, filters and breakdowns, pinned downloads |

0.4.0 is not yet released: its RFCs describe the code as built, which ships with the release.

## Adding one

Name it `RFC-NNN-short-slug.md` (next number, three digits) with **Status**, **Authors**,
**Related PRDs**, **Related RFCs** and **Code**, then Abstract, Problem Statement, Design,
Alternatives Considered and Testing (and Open questions while it is a draft). Add its row under
Open RFCs.
