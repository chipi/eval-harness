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
| [RFC-012](RFC-012-evidence-registry.md) | The evidence registry: champions' evidence, the export, the check | [PRD-011](../prd/PRD-011-evidence-registry.md) | The verdict frozen at promotion; evh champions; a deterministic evh-champions/1 export with the recipe and intended use; evidence-check over any citation file |
| [RFC-010](RFC-010-studies.md) | Studies: exploratory and confirmatory, trials, samplers, the test check | [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) | Spec and records in data/studies, an ask/tell loop over job sets, decisions against the incumbent and the start, samplers (grid, one at a time, random, LLM, command, agent), the counted test check, study-import of results.tsv |
| [RFC-011](RFC-011-job-sets-and-runners.md) | Job sets and runners: local and ssh | [PRD-010](../prd/PRD-010-runners.md) | A detached supervisor, standard job states, timeouts, retries, leases, attempts as runs; phases with check/before/after and consent; the ssh runner with a verified manifest and the local commit as the build |
| [RFC-008](RFC-008-process-protocol.md) | The process protocol: systems in any language | [PRD-008](../prd/PRD-008-pipelines-and-any-language.md) | JSON-RPC 2.0 over stdio or HTTP (evh-adapter/1), wrapped as an ordinary adapter; declared identity plus the executable's hash; a Node example; adapter-check |
| [RFC-007](RFC-007-stages-and-stage-references.md) | Stages, stage references, structured outputs, item fields, batch mode | [PRD-008](../prd/PRD-008-pipelines-and-any-language.md) | Span-shaped stages beside outputs, <stage>.<metric> scores, per-stage references, JSON outputs, call forms, batch mode with the cost cap, the wrapping recipe, OTLP import |
| [RFC-009](RFC-009-prompt-versions.md) | Prompt versions | [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) | Declared prompt files or a prompt root; versions as snapshots in data/prompts, resolved at run time; arm.prompts in the fingerprint; a per-run overlay; prompt commands and pages |
| [RFC-016](RFC-016-mcp-server-and-skills.md) | The MCP server, the skills, llms.txt and the glossary | [PRD-012](../prd/PRD-012-agent-ready.md) | evh mcp on the official SDK, tools from the manifest, resources, job ids for long work, elicitation consent, a limits file; skills in the Agent Skills format; llms.txt; a glossary |
| [RFC-013](RFC-013-machine-surface.md) | The machine surface: declarations, JSON, exit codes, refusals, the actor, the config | [PRD-012](../prd/PRD-012-agent-ready.md) | One declaration per command (help, manifest, MCP tools); --json and output schemas; exit codes; RFC 9457 refusals; actor and consent; config.yaml; Python 3.10 |
| [RFC-015](RFC-015-noninferiority-looks-power.md) | The statistics of 0.5.0: non-inferiority, verdicts, test looks, power | [PRD-013](../prd/PRD-013-identity-and-ties.md), [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) | Tests chosen by simulation (Tango for 0/1, guarded bootstrap-t for continuous), the verdict sequence, Holm across candidates, K looks per item set, attainable p and MDE |
| [RFC-014](RFC-014-identity-champions-migration.md) | Identity in 0.5.0: champions, fingerprint v5, run ids, one grammar, the migration | [PRD-013](../prd/PRD-013-identity-and-ties.md), [PRD-011](../prd/PRD-011-evidence-registry.md) | Champion versions per goal and dataset; machine outside the hash; unique run ids; kind:path/n; the one-time migration script |

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
