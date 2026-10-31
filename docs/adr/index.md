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
| [ADR-0006](ADR-0006-goal-axes-and-strategies.md) | A goal weighs cost, quality and speed; a strategy picks | Accepted | 0.4.0 | Goals declare axes (quality, cost, speed, and the project's own metrics); a strategy decides who ties with the quality leader (balanced: not separated and within margin; quality_first: same quality; frugal: not separated); the tie-break picks among tied arms; guardrails are prose rules shown, never computed | [PRD-005](../prd/PRD-005-goals-and-rounds.md), [UXS-001](../uxs/UXS-001-catalog.md), [UXS-002](../uxs/UXS-002-inspector.md) | Yes |
| [ADR-0018](ADR-0018-period-from-today.md) | The catalog's period is counted from today, in the browser | Accepted | 0.4.2 | Pages carry per-day facts; the browser works the period out from the viewer's date; one builder per page feeds the page and its command (`evh datasets --period P`, ...); the period travels in the link, nothing remembered | [PRD-004](../prd/PRD-004-catalog-and-inspector.md), [UXS-001](../uxs/UXS-001-catalog.md) | Yes |
| [ADR-0019](ADR-0019-capture-lane.md) | Datasets from production: a capture lane beside the method | Accepted | 0.6.0 | New commands (capture, dataset-from-capture, reference-from-outcomes, dataset-split, importer-check) end in ordinary datasets and references; stateless; four built-in importers the core never imports; outcomes become references through a recorded mapping; `text: hidden` on every public surface | [PRD-014](../prd/PRD-014-datasets-from-production.md), [RFC-019](../rfc/RFC-019-datasets-from-production.md) | No |
| [ADR-0020](ADR-0020-second-references-are-silver.md) | A dataset's second reference is silver, with a caveat | Accepted | 0.6.0 | The reference a goal decides on is `gold/<dataset>`; every other one is `silver/<name>` with a caveat saying what it is, so the goal page shows one recommendation | [RFC-019](../rfc/RFC-019-datasets-from-production.md), [PRD-002](../prd/PRD-002-references.md) | No |
| [ADR-0021](ADR-0021-a-deployment-is-vetted.md) | A deployment, not a model, is what is vetted and fingerprinted | Accepted | 0.6.0 | Onboarding, smoke and the fingerprint's deployment part are per deployment; determinism and the build are a deployment's facts; the runner is outside the hash; in process only when the arm calls nothing elsewhere |

ADR-0002 is Partial until the project it came from runs on the harness's copy (its layer 4) and
0.4.0 is released. ADR-0004 is Yes for the decision as recorded; the parts of its proposal left
out of 0.4.0 are listed in [RFC-004](../rfc/RFC-004-experiment-rounds.md).

## Adding one

New work starts with a PRD ([PRD index](../prd/index.md)). Write an ADR only for a decision that
shapes the architecture: **Status**, **Date**, **Detail** (links to the PRD, UXS and RFC), then
Context, Decision and Consequences, a few lines each. Number it next (`ADR-0005-short-slug.md`)
and add its row here.
