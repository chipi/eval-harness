# PRD-004: The catalog and the run inspector

- **Status**: Implemented (0.4.0, unreleased)
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (the catalog's pages),
  [UXS-002](../uxs/UXS-002-inspector.md) (the inspector), [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the same views as commands)
- **Related RFC**: [RFC-003](../rfc/RFC-003-catalog-adapter.md) (the adapter protocol, the server, the build)
- **Related ADR**: [ADR-0002](../adr/ADR-0002-catalog-inspector-goals.md)
- **Related PRDs**: [PRD-005](PRD-005-goals-and-rounds.md) (goal pages, rounds), [PRD-006](PRD-006-datasets-versions-fields.md) (fields in a comparison)

## Summary

Tables answer the questions a user thought to ask. To look around, `evh catalog` builds static
pages over a project's runs: one per dataset, goal and reference, a metrics page, and a search
over all of them. `evh catalog-serve` serves them with the **run inspector**, which tests any
chosen arms on one dataset against a baseline with the same paired test as the command line and
shows one item's outputs beside its reference. The pages only read: every decision is a command
run locally, and everything a page shows is also a command, so the pages are a comfort, never
the only way to see something.

## Background & Context

A project that pins the harness (a private podcast evaluation repository) built a catalog, an
inspector and goals for itself. In 0.4.0 the generic part moved into the harness, with the
paired test in one module, so the inspector and the CLI cannot disagree; the project keeps one
adapter file ([ADR-0002](../adr/ADR-0002-catalog-inspector-goals.md),
[RFC-003](../rfc/RFC-003-catalog-adapter.md)). This repository publishes its own catalog at
[catalog.evals.humancopilot.eu](https://catalog.evals.humancopilot.eu/).

## Goals

- See every run of a project, by dataset, with what each arm is scored against.
- Test chosen arms against a baseline from a page, with the CLI's test and the CLI's refusals.
- Read one item's outputs side by side, with the reference and the item itself.
- Publish the static pages safely: no item text in them.
- Work on the harness's own data layout with no code, and on any other layout with one adapter.
- Every view and computation is also an `evh` command with the same numbers.

## Non-Goals

- **The pages never write.** No promote, retire or close button: decisions are commands
  ([PRD-005](PRD-005-goals-and-rounds.md)). A public deployment depends on that.
- Not a live dashboard: the server reads the runs when it starts; a new run needs a restart.
- No account system or per-user state.
- No report rendering: the catalog renders no project reports.

## Personas

- **The engineer** exploring which arm to keep, who wants to click from a mean to the items
  behind it.
- **The reviewer or reader** of a published experiment, who wants to check a claim without
  installing anything (the public catalog).
- **The terminal user** who wants the same answers without a browser.

## User Stories

- _As an engineer, I can open a dataset page and inspect every arm scored against the same
  reference in one click._
- _As an engineer, I can pick arms in the inspector, choose the baseline and metric, and read a
  verdict per arm with its p and Holm threshold._
- _As an engineer, I can click an item and see each arm's output beside the reference and the
  item itself, with what each arm adds and drops marked if I want._
- _As a reviewer, I am told when the arms I compare ran under different conditions (scorer,
  reference bytes, machine), before I read the test._
- _As a terminal user, I can get the inspector's comparison with
  `evh inspect --runs a,b`, and every page with `evh datasets`, `evh references`, `evh metrics`
  and `evh goals`._

## Functional Requirements

### FR1: The catalog (static)

- **FR1.1**: `evh catalog [--out DIR] [--adapter …] [--link LABEL=URL]` builds the pages into
  `.build/catalog/` by default.
- **FR1.2**: Pages: home (every dataset), one per dataset, goals and one per goal, one per
  reference, a metrics page, and the inspector's shell ([UXS-001](../uxs/UXS-001-catalog.md)).
- **FR1.3**: The pages carry counts and means only, never an item's text, an output or a
  reference; a field's values appear only when the project marks the field `public`.
- **FR1.4**: Every arm's row says what it is scored against; rows scored against silver, by a
  judge, or against the reference the arm wrote itself are tinted.
- **FR1.5**: Long tables show 10 rows with "show 10 more" and "show all"; the filter and the sort
  work over every row.

### FR2: The inspector (local server)

- **FR2.1**: `evh catalog-serve [--port 8765]` serves the built catalog and the inspector on
  127.0.0.1, answers only to a 127.0.0.1/localhost Host header, and serves only the catalog and
  the data tree, never a dot-folder in either.
- **FR2.2**: It refuses arms on different `dataset_id`s, and, on a metric scored against a
  reference, does not test an arm scored against another reference than the baseline's.
- **FR2.3**: It tests each arm against the baseline with `evaluation_harness.stats` (exact p up
  to 30 items, Holm across the family) and gives a verdict in words: `separated: better`,
  `separated: worse`, `not separated` (on a neutral metric, `separated: higher` or `lower`;
  `identical` or `untestable` where no test applies) ([UXS-002](../uxs/UXS-002-inspector.md)).
- **FR2.4**: It reads only arms the adapter's `arms()` reaches and references `references()`
  lists.
- **FR2.5**: It compares the arms' recorded conditions and warns when the scorer or the
  reference bytes differ, or latency is compared across machines.

### FR3: Public mode

- **FR3.1**: `evh catalog-serve --public HOST` serves the API only, behind a reverse proxy that
  serves the static pages, to the named hosts; each client gets `--rate` requests a minute and
  a comparison at most `--max-arms` arms; errors never show the server's internals; `--warm DIR`
  computes every comparison the built catalog links to.
- **FR3.2**: In public mode the item view never returns the item itself, returns outputs and
  references only when the deployment publishes them (`--publish`), and only fields marked public
  are filterable.

### FR4: Command-line parity

- **FR4.1**: Every page and comparison is also a command that asks the same adapter and computes
  with the same functions: `evh datasets`, `evh references`, `evh metrics`, `evh goals`,
  `evh search`, `evh inspect` (its comparison, `--items`, `--analysis`, `--item`)
  ([UXS-003](../uxs/UXS-003-cli-and-onboarding.md)).
- **FR4.2**: New views and actions are added to both. A decision the pages suggest is shown as
  the command that makes it.

### FR5: Any layout

- **FR5.1**: On the harness's own layout (`data/runs*/`, `data/references/`, `data/datasets/`,
  `data/goals/`) no code is needed.
- **FR5.2**: With another layout, the project writes one adapter class and names it in
  `config.yaml` (`catalog: {adapter: path/to/file.py:Class}`) or passes `--adapter`
  ([RFC-003](../rfc/RFC-003-catalog-adapter.md)).

## Success Criteria

- The inspector gives the same p as `pair-test` on the same pair (GUIDE step 12: lead2 against
  lead1 on gold, p = 0.0938).
- The catalog and the inspector pass the headless browser check (`make browser-check`) and the
  catalog tests (`harness/tests/test_catalog.py`).
- Both deployed sites pass a content security policy with no inline script or style.

## Related Documents

- [UXS-001](../uxs/UXS-001-catalog.md), [UXS-002](../uxs/UXS-002-inspector.md), [UXS-003](../uxs/UXS-003-cli-and-onboarding.md).
- [RFC-003](../rfc/RFC-003-catalog-adapter.md), [ADR-0002](../adr/ADR-0002-catalog-inspector-goals.md).
- [Integration: the catalog and the inspector](../../harness/docs/INTEGRATION.md#the-catalog-and-the-inspector).
