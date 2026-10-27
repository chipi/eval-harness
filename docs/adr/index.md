# Architecture decisions (ADRs)

An ADR records **a key decision in a few lines**: the context, the decision, its consequences.
The detail lives elsewhere and each ADR links it: what the user needs and why in a
[PRD](../prd/index.md), what they see and type in a [UXS](../uxs/index.md), and the technical
design with its alternatives in an [RFC](../rfc/index.md). This list is kept small: only the
decisions that shape the architecture.

- **Once accepted, an ADR's decision is not rewritten.** A later decision that changes it is a new
  ADR, and the old one is marked superseded, with a link. (On 2026-10-24 the four ADRs below were
  shortened when the PRD/UXS/RFC process was adopted: their detail moved, unchanged in substance,
  into the linked documents.)
- **Each one names its status:** Proposed, Accepted, Superseded or Rejected.
- **The code column** says whether the code reflects it: Yes, Partial (still landing) or No.

For how the pieces fit together, read the [architecture overview](../architecture/ARCHITECTURE.md).

## Index

| ADR | Title | Status | Release | Decision | Detail | Code |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| [ADR-0001](ADR-0001-judge-scorers.md) | Judge scorers | Accepted | 0.3.0 | Re-measure frozen outputs with LLM judges, refused until validated against human ratings, at least two vendors, blind, every verdict stored | [PRD-003](../prd/PRD-003-judging.md), [RFC-005](../rfc/RFC-005-judge-scorers.md) | Yes |
| [ADR-0002](ADR-0002-catalog-inspector-goals.md) | Catalog, run inspector and goals | Accepted | 0.4.0 | One paired test for the CLI and the inspector; the catalog and inspector as a generic core with a project adapter; goals first-class; this repository deployed as a full harness deployment | [PRD-004](../prd/PRD-004-catalog-and-inspector.md), [PRD-005](../prd/PRD-005-goals-and-rounds.md), [RFC-003](../rfc/RFC-003-catalog-adapter.md), [UXS-001](../uxs/UXS-001-catalog.md), [UXS-002](../uxs/UXS-002-inspector.md) | Partial |
| [ADR-0003](ADR-0003-item-fields-and-url-items.md) | Item fields and URL items | Accepted | 0.4.0 | Items fetched from a pinned URL; typed fields declared in a reusable field set, outside the dataset identity, values public only by opt-in; filter and per-group tests in the inspector | [PRD-006](../prd/PRD-006-datasets-versions-fields.md), [RFC-006](../rfc/RFC-006-item-fields-and-url-items.md) | Yes |
| [ADR-0004](ADR-0004-experiment-rounds.md) | Experiment rounds, and a catalog that guides them | Accepted | 0.4.0 | Optional rounds per goal as files; decisions as local commands, the catalog read-only; suggestions computed from the evidence; the goal page leads with the answer; dataset lineage and the conditions check | [PRD-005](../prd/PRD-005-goals-and-rounds.md), [RFC-004](../rfc/RFC-004-experiment-rounds.md), [UXS-001](../uxs/UXS-001-catalog.md), [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) | Yes |
| [ADR-0005](ADR-0005-credentials-per-role.md) | One provider layer; credentials per role, never identity | Accepted | 0.4.0 | Arms, judges and the judge panel call hosted models through one layer; a call goes where its `provider:` says; a judge reads `EVAL_JUDGE_<NAME>` first, then `<NAME>`; `api_key_env` is not part of any fingerprint | [PRD-007](../prd/PRD-007-packaging-and-providers.md) | Yes |
| [ADR-0006](ADR-0006-goal-axes-and-strategies.md) | A goal weighs cost, quality and speed; a strategy picks | Accepted; its tie rule superseded by ADR-0015 from 0.5.0 | 0.4.0 | Goals declare axes (quality, cost, speed, and the project's own metrics); a strategy decides who ties with the quality leader (balanced: not separated and within margin; quality_first: same quality; frugal: not separated); the tie-break picks among tied arms; guardrails are prose rules shown, never computed | [PRD-005](../prd/PRD-005-goals-and-rounds.md), [UXS-001](../uxs/UXS-001-catalog.md), [UXS-002](../uxs/UXS-002-inspector.md) | Yes |
| [ADR-0007](ADR-0007-stages-and-pipelines.md) | A result carries its stages; items fail alone | Accepted | 0.5.0 | Span-shaped stages (OpenTelemetry GenAI names) stored beside outputs and scored as `<stage>.<metric>`; per-stage references in the digest; JSON outputs; item or batch call forms; an item fails without stopping the run | [PRD-008](../prd/PRD-008-pipelines-and-any-language.md), [RFC-007](../rfc/RFC-007-stages-and-stage-references.md) | No |
| [ADR-0008](ADR-0008-process-protocol.md) | Systems in any language through a JSON-RPC process | Accepted | 0.5.0 | A process adapter speaks `evh-adapter/1.0` over stdio or HTTP; the system's declared identity and hashed files are the arm; restarts must keep the identity | [PRD-008](../prd/PRD-008-pipelines-and-any-language.md), [RFC-008](../rfc/RFC-008-process-protocol.md) | No |
| [ADR-0009](ADR-0009-prompt-versions.md) | The harness versions declared prompt files | Accepted | 0.5.0 | Declared prompt files are snapshotted as versions where they live; prompts are part of the arm; a per-run overlay gives a trial its prompts without writing a tracked file | [PRD-009](../prd/PRD-009-prompts-and-optimisation.md), [RFC-009](../rfc/RFC-009-prompt-versions.md), [UXS-004](../uxs/UXS-004-studies-baselines-prompts.md) | No |
| [ADR-0010](ADR-0010-studies.md) | Studies: an ask/tell loop that searches, and one test that is evidence | Accepted | 0.5.0 | Exploratory and confirmatory studies own a round; pluggable samplers including the calling agent; guardrails against the start; one counted heldout check on unseen items; a study never promotes | [PRD-009](../prd/PRD-009-prompts-and-optimisation.md), [RFC-010](../rfc/RFC-010-studies.md), [UXS-004](../uxs/UXS-004-studies-baselines-prompts.md) | No |
| [ADR-0011](ADR-0011-job-sets-and-runners.md) | Long work runs as job sets, locally or over ssh | Accepted | 0.5.0 | Detached supervisors with locks, states, timeouts and retries; phases whose `after` survives a crash; an ssh runner that sends a verified manifest and records a verified build | [PRD-010](../prd/PRD-010-runners.md), [RFC-011](../rfc/RFC-011-job-sets-and-runners.md) | No |
| [ADR-0012](ADR-0012-baselines-and-evidence.md) | Baselines per goal, with the evidence frozen at promotion | Accepted | 0.5.0 | Versioned baselines per goal and dataset with a pointer; the justifying comparison frozen at promotion; a deterministic export; `evidence-check` fails replaced or retired citations | [PRD-011](../prd/PRD-011-evidence-registry.md), [RFC-012](../rfc/RFC-012-evidence-registry.md), [RFC-014](../rfc/RFC-014-identity-baselines-migration.md), [UXS-004](../uxs/UXS-004-studies-baselines-prompts.md) | No |
| [ADR-0013](ADR-0013-machine-surface-and-consent.md) | One declaration per command; JSON, exit codes, refusals, actors, consent | Accepted | 0.5.0 | Commands declare themselves once; results on stdout with `--json`; an exit-code table; RFC 9457 refusals; every record names its actor; consent is a person's, never only an agent's | [PRD-012](../prd/PRD-012-agent-ready.md), [RFC-013](../rfc/RFC-013-machine-surface.md), [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) | No |
| [ADR-0014](ADR-0014-identity-v5-and-migration.md) | Fingerprint version 5, run ids, one grammar, a one-time migration | Accepted | 0.5.0 | The machine outside the hash; explicit exclusions recomputed by `validate`; unique run ids; `kind:path/n` ids; a re-runnable one-time migration script | [PRD-013](../prd/PRD-013-identity-and-ties.md), [RFC-014](../rfc/RFC-014-identity-baselines-migration.md) | No |
| [ADR-0015](ADR-0015-noninferiority-and-test-looks.md) | Ties are non-inferiority; heldout datasets spend their level over looks | Accepted | 0.5.0 | Tie-breaks by a valid non-inferiority test against a declared margin (Tango, a guarded bootstrap-t); each heldout dataset spends 2.5% over front-loaded looks taken only by decisions; power stated before spending | [PRD-013](../prd/PRD-013-identity-and-ties.md), [RFC-015](../rfc/RFC-015-noninferiority-looks-power.md) | No |
| [ADR-0016](ADR-0016-mcp-server-and-skills.md) | An MCP server, skills and llms.txt for agents | Accepted | 0.5.0 | `evh mcp` on the official SDK, tools generated from the declarations, run as children; consent and actor never from the client; tracked limits; skills shipped and tested; `llms.txt` | [PRD-012](../prd/PRD-012-agent-ready.md), [RFC-016](../rfc/RFC-016-mcp-server-and-skills.md), [UXS-005](../uxs/UXS-005-agents.md) | No |
| [ADR-0018](ADR-0018-period-from-today.md) | The catalog's period is counted from today, in the browser | Accepted | 0.4.2 | Pages carry per-day facts; the browser works the period out from the viewer's date; one builder per page feeds the page and its command (`evh datasets --period P`, ...); the period travels in the link, nothing remembered | [PRD-004](../prd/PRD-004-catalog-and-inspector.md), [UXS-001](../uxs/UXS-001-catalog.md) | Yes |

ADR-0002 is Partial until the project it came from runs on the harness's copy (its layer 4) and
0.4.0 is released. ADR-0004 is Yes for the decision as recorded; the parts of its proposal left
out of 0.4.0 are listed in [RFC-004](../rfc/RFC-004-experiment-rounds.md). ADR-0007 to ADR-0016 are the 0.5.0
decisions, taken from the Decisions sections of RFC-007 to RFC-016; their code column reads No until 0.5.0 is built.

## Adding one

New work starts with a PRD ([PRD index](../prd/index.md)). Write an ADR only for a decision that
shapes the architecture: **Status**, **Date**, **Detail** (links to the PRD, UXS and RFC), then
Context, Decision and Consequences, a few lines each. Number it next (`ADR-0005-short-slug.md`)
and add its row here.
