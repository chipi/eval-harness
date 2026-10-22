# Architecture decisions (ADRs)

An ADR records **what was decided and why**: the context, the decision, its consequences and
the alternatives set aside. It is the short, lasting record of a choice. The full design and
its working-out, when there is one, is a [proposal (RFC)](../rfc/index.md).

- **Once accepted, an ADR is not rewritten.** A later decision that changes it is a new ADR,
  and the old one is marked superseded, with a link.
- **Each one names its status:** Proposed, Accepted, Superseded or Rejected.
- **The code column** says whether the code reflects it: Yes, Partial (still landing) or No.

For how the pieces fit together, read the [architecture overview](../architecture/ARCHITECTURE.md).

## Index

| ADR | Title | Status | Release | Decision | Code |
| :--- | :--- | :--- | :--- | :--- | :--- |
| [ADR-0001](ADR-0001-judge-scorers.md) | Judge scorers | Accepted | 0.3.0 | Re-measure frozen outputs with LLM judges, refused until validated against human ratings, at least two vendors, blind, every verdict stored | Yes |
| [ADR-0002](ADR-0002-catalog-inspector-goals.md) | Catalog, run inspector and goals | Accepted | 0.4.0 | One paired test for the CLI and the inspector; the catalog and inspector as a generic core with a project adapter; goals first-class; this repository deployed as a full harness deployment | Partial |
| [ADR-0003](ADR-0003-item-fields-and-url-items.md) | Item fields and URL items | Accepted | 0.4.0 | Items fetched from a pinned URL; typed fields declared in a reusable field set, outside the dataset identity, values public only by opt-in; filter and per-group tests in the inspector | Yes |

ADR-0002 is Partial until the project it came from runs on the harness's copy (its layer 4) and
0.4.0 is released.

## Adding one

Copy the frame of an existing ADR: **Status**, **Date**, then Context, Decision,
Consequences, Alternatives. Number it next (`ADR-0004-short-slug.md`) and add its row here.
