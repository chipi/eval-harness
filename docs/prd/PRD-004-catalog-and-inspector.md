# PRD-004: The catalog and the run inspector

- **Status**: Implemented (v0.4.0); FR6, the same views for an agent: Implemented (v0.5.0)
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
[evals.humancopilot.eu/catalog](https://evals.humancopilot.eu/catalog/).

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
- **The agent** (Claude, ChatGPT, Gemini, any MCP client) that a person asks about the experiments,
  and that needs the same numbers, refusals included, as data it can call for.

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
  `evh inspect --runs a,b`, and every page with `evh datasets`, `evh references`, `evh metrics`,
  `evh goals`, `evh arms` and `evh activity`._
- _As a person working with an agent, I can ask it which arm a goal recommends and why, and it
  answers from the same table and paired test the catalog shows, without being able to change
  anything._
- _As a maintainer of an evaluation, I can see what is new and what moved this week or this
  month on every page, and follow a count on the home page to the rows behind it._

## Functional Requirements

### FR1: The catalog (static)

- **FR1.1**: `evh catalog [--out DIR] [--adapter …] [--link LABEL=URL] [--api PATH] [--head FILE] [--about FILE] [--repo URL]`
  builds the pages into `.build/catalog/` by default. `--link` names the parts of the publication
  the catalog belongs to (a switcher on every page, `LABEL=.` for the catalog itself); `--api` is
  where the inspector's API answers when the catalog is served under a path; `--head` adds a
  deployment's own HTML (analytics) to every page; `--about` puts a deployment's own paragraph
  on the overview (which project it shows, where its findings are); `--repo` says where the
  project's files can be read, so a project path in a goal's links or guardrail sources links there.
- **FR1.2**: Pages: home (the dashboard, FR1.8), datasets and one per dataset, goals and one per
  goal, references and one per reference, one per arm, metrics and one per metric, and the
  inspector's shell ([UXS-001](../uxs/UXS-001-catalog.md)).
- **FR1.3**: The pages carry counts and means only, never an output or a reference, and never an
  item's text unless the repository already publishes it (a profile written `--with-text`, refused unless git has committed every item's file); a field's values appear only when the project marks the field `public`.
- **FR1.4**: Every arm's row says what it is scored against; rows scored against silver, by a
  judge, or against the reference the arm wrote itself are tinted.
- **FR1.5**: Long tables show 10 rows with "show 10 more" and "show all"; the filter and the sort
  work over every row.
- **FR1.6**: Every arm name, metric name, dataset, reference and goal link to their pages from
  every page. A round's configs link to their arm pages.
- **FR1.7**: An arm's page shows its metrics, runs, config without credentials, conditions, the
  same config scored other ways, and rounds it joined. A metric's page shows what it measures
  (summary and details from `METRIC_DESCRIPTIONS`), which way is better, its kind, the goals it
  decides, and per-dataset a strip chart and table of arms.
- **FR1.8**: The home page shows tiles for the counts (goals, datasets, configs, arms,
  references, metrics, measured runs, USD billed, tokens); each goal's baseline and gold-group
  leader with their paired test (threshold 0.05); activity (measured runs per day by dataset)
  beside spend (cumulative, systems under test and judges, in USD or tokens); coverage per
  dataset; and everything recorded, newest first; each for a period counted from today (the last
  14, 7, 30 or 90 days, this or last week or month, this year, all time), the counts with their
  trends against the period before. The tiles are grouped and coloured by subject (goals; data;
  experiments; work and spend), never red or green for a direction.
- **FR1.9** (0.4.2): A tile is a door: the page it opens shows what it counts, for the same
  period, carried in the link. The goals, datasets, arms, references and metrics pages mark the
  rows new in the period, keep only the new or the active ones on request, and show the period's
  runs and spend against the period before; the goals page lists what happened to each goal.
- **FR1.10** (0.4.2): An activity page shows the period's runs, spend and tokens by dataset, by
  arm and by kind of call, against the period before, what moved most first.
- **FR1.11** (0.4.2): An arms and configs page lists every arm, each saying how it was measured
  (measured, rescored, judged, re-parsed, run again), grouped by dataset, config, model, provider
  or what it is scored against, filtered to local or hosted arms or a price tier, with its role
  in each goal's decision; picks arms on one dataset to open in the inspector; lists every config
  across the datasets it ran on with its rank on each goal; and shows each goal's trade-off
  charts.
- **FR1.12** (0.4.2): The menu groups the pages by the same subjects as the tiles, so it fits a
  desktop bar; a phone's menu lists every page.

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
  with the same functions: `evh overview` (the home dashboard), `evh activity`, `evh datasets`,
  `evh arms` (`--by`, `--where`, `--tier`, `--configs`), `evh references`, `evh metrics`,
  `evh goals`, `evh search`, `evh inspect` (its comparison, `--items`, `--analysis`, `--item`)
  ([UXS-003](../uxs/UXS-003-cli-and-onboarding.md)); every list takes `--period P` and prints the
  page's period columns, from the same builder the page reads.
- **FR4.2**: New views and actions are added to both. A decision the pages suggest is shown as
  the command that makes it.

### FR5: Any layout

- **FR5.1**: On the harness's own layout (`data/runs*/`, `data/references/`, `data/datasets/`,
  `data/goals/`) no code is needed.
- **FR5.2**: With another layout, the project writes one adapter class and names it in
  `config.yaml` (`catalog: {adapter: path/to/file.py:Class}`) or passes `--adapter`
  ([RFC-003](../rfc/RFC-003-catalog-adapter.md)).

### FR6: The same views for an agent (v0.5.0)

- **FR6.1**: `evh mcp` serves the read commands of FR4 (and `rounds`, `runs-list`, `validate`,
  `dataset-items`) as MCP tools, each call the command itself, so FR4's parity holds for an agent
  too ([RFC-018](../rfc/RFC-018-read-only-mcp-server.md)).
- **FR6.2**: No tool writes project data, spends or runs a model: the non-goal "the pages never
  write" holds for the tools. A command that writes is never a tool, and a test lists every
  command as one or the other.
- **FR6.3**: `--http --public` serves them to anyone, as FR3 serves the API: no item text, Host
  checked, the load bounded per caller and in total. This repository's catalog answers at
  `https://evals.humancopilot.eu/mcp`.

## Success Criteria

- The inspector gives the same p as `pair-test` on the same pair (GUIDE step 12: lead2 against
  lead1 on gold, p = 0.0938).
- The catalog and the inspector pass the headless browser check (`make browser-check`) and the
  catalog tests (`harness/tests/test_catalog.py`).
- Both deployed sites pass a content security policy with no inline script or style.
- An MCP client gets the same JSON from `datasets` as `evh datasets --json` prints, and every tool is
  annotated read-only (`harness/tests/test_mcp_server.py`, `test_mcp_http.py`).

## Related Documents

- [UXS-001](../uxs/UXS-001-catalog.md), [UXS-002](../uxs/UXS-002-inspector.md), [UXS-003](../uxs/UXS-003-cli-and-onboarding.md).
- [RFC-003](../rfc/RFC-003-catalog-adapter.md), [ADR-0002](../adr/ADR-0002-catalog-inspector-goals.md),
  [RFC-018](../rfc/RFC-018-read-only-mcp-server.md) (the MCP server).
- [Integration: the catalog and the inspector](../../harness/docs/INTEGRATION.md#the-catalog-and-the-inspector).
