# PRD-017: The Workbench, where an evaluation is set up and run

- **Status**: Draft (owner, 2026-11-06: "workbench is a good name"; "start with the PRD and then the RFC"); rewritten
  2026-11-17 against RFC-032 and the owner's decisions of that day (D1 to D9, below); 0.8.0
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-004](PRD-004-catalog-and-inspector.md) (the catalog and the inspector, which stay read-only),
  [PRD-016](PRD-016-managing-project-data.md) (the Configure page, retired: the Workbench replaces it),
  [PRD-005](PRD-005-goals-and-rounds.md) (goals and rounds), [PRD-014](PRD-014-datasets-from-production.md) (datasets
  from production), [PRD-015](PRD-015-models-onboarded-once.md) (models onboarded once)
- **Related RFCs**: [RFC-032](../rfc/RFC-032-one-model-two-surfaces.md) (one data model; the API the Workbench runs on:
  Accepted, built), [RFC-033](../rfc/RFC-033-per-item-results-as-a-model.md) (per-item results in either store),
  [RFC-026](../rfc/RFC-026-an-api-for-every-command.md) (the API's token, uploads and jobs, as RFC-032 amends them),
  [RFC-027](../rfc/RFC-027-who-acted-and-baselines-per-goal.md) (who acted), RFC-025 (files or one database)
- **Screens**: [UXS-005](../uxs/UXS-005-workbench.md)

## Summary

The Workbench is a second application beside the catalog, for people. Agents already do all of this well through
`evh`, the MCP server and the files (the triage fleet's agent is the proof); a person cannot do it so easily. The
catalog shows what a project has and what it decided;
the Workbench is where a person puts things in and runs them: a goal and its data, models, systems and the arms they
become in a round, labels, references, scoring, and the round that ends in a choice. It is organised around the few
things people come to do (workflows), not around the files the harness keeps, and it spends its design on what they
do every day or week. It works in either store: it calls the same operations as `evh`, which write the files of a
files project and the database of a SQLite project. Its aim is that the harness's real complexity feels the way the
site explains it: a goal, data, arms, a comparison, a choice.

## Background & Context

- Everything the Workbench does is an operation of the harness's model (RFC-032): one registry, each operation with
  typed inputs, a kind (read, edit, decision, work) and its locks. `evh`, the API (154 route-method pairs in `evh
  openapi`), the MCP server and jobs are surfaces over the same operations. Agents use them well (owner, 2026-11-06:
  "the stuff works now fine for agents … but it's hard for human users"). A person must know which operations, in
  which order, with which inputs; the site's method page explains the loop, the terminal makes you rebuild it.
- The Configure page (PRD-016) put the project's settings into forms built from their schemas. The owner's verdict
  on its forms, 2026-11-06: "massive", "nobody's gonna enter that": a goal's form is 5,023 px with 58 inputs, a model
  record's 5,489 px, the validate policy's 6,194 px. It mapped every key of every file to a field, at the same
  weight, and it only edits: it runs nothing. Two reviews (architecture and UX, 2026-11-06) found its save takes about
  52 s (two full `evh validate` runs) with no progress shown, and no lock between two saves.
- The catalog's read-only rule (UXS index, rule 1) stays: the Workbench is where writing and running happen, the
  catalog where results are read. Each links to the other.
- Today (2026-11-17) the live Workbench serves the home, a goal and the models (model-new, a deployment, onboarding);
  every other screen exists only in the static mockup, whose data is this repository's (`mock.js`).

## Goals

1. A person can do each workflow below from the Workbench without the terminal, in either store.
2. The workflows people do daily and weekly are fast and guided; the occasional ones are plain and correct; the
   one-off ones may stay terse (or stay commands).
3. Each form asks only what a person decides at that point: links to other things are pickers, what operations write
   is shown and never edited, expert settings start from named defaults.
4. Running is visible: every run is a job with what it will cost before it starts, its progress while it runs, and
   its result and catalog link when it ends; a job survives the browser closing.
5. The Workbench knows where each goal stands and offers the next step (`goal-status`).

## Non-Goals

- Replacing the catalog or the inspector: results are read there, linked from here.
- A public, multi-user service: the Workbench runs on the person's machine (ADR-0027, as RFC-032 amends it). Several
  people sharing one project is a later question. Behind a proxy (`--public`, `--behind-proxy`) the Workbench and
  `/api/v1` answer 404, and stay so in 0.8.0 (D8).
- Making a project: a project names its store at `evh init --store files|sqlite`, on the command line; the
  Workbench opens a project that exists.
- A general YAML or file editor. The raw file can be shown; it is not the way in. The project's `config.yaml` is not
  edited here in 0.8.0 (`data-put` writes only under `data/`; D9).
- New evaluation capabilities: the Workbench drives the operations that exist. Where a screen needs one that does
  not, the operation is built first, for every surface (below: "The API to build first").
- A new way for agents: they keep the commands and the MCP server.

## Personas

- **The evaluator** (daily, weekly): runs rounds on a goal: new arms, scoring, comparison, a decision.
- **The labeller** (weekly): reviews outputs, labels and tags them, helps promote references.
- **The maintainer** (occasionally): brings in models and judges, sets up goals and datasets, governs references and
  budgets.
Agents are not a persona of the Workbench: they already have the commands and the MCP server, and nothing here
changes those. The API the Workbench runs on (RFC-032) is its means, not a new interface for agents.

## Workflows, by how often they happen

Each workflow is a job to be done with tasks inside it. The Workbench presents the workflow; the tasks are its steps,
each an operation (or a few) it calls for the person. The words: a **system** is what is evaluated (a deployment, a
prompt version, settings; no dataset); a system placed in a round is an **arm**; a **run** is a system run on a
dataset, in a round or not (RFC-032, "Names").

### Daily and weekly: designed with the most care

**W1 Run a round (the core).** On a goal and its dataset: open a round with its question; choose its arms (carry
systems from the last round, clone one and change one thing — the prompt, the model, a setting — or add a system of
an onboarded model), smoke them, see the cost, run them all, score them (the goal's scorers; re-scored on the current
reference; the goal's judge when it has one), read the round's evidence (each arm against the leader, Holm), and
decide: retire an arm (with its reason; a retire is final), promote a baseline, close the round with a conclusion.
*Operations:* `round-open` (`from`, `keep`, `hypothesis`), `round-carry`, `system-show` and `system-new` (a clone is a
new system), `arm-smoke`, `POST /estimate`, `sweep` (the round's systems on its dataset, in the round; D2), `rescore`,
`judge-score`, `round-evidence`, `goal-leaderboard`, `pair-test`, `round-retire`, `run-promote`, `round-close`
(`promote`).

**W2 Review outputs, label and tag.** On a goal's dataset: the items across the arms that matter; read outputs side
by side, say which is better, give a label, tag failure modes, leave a note; bring back a sheet filled elsewhere.
*Operations:* `comparison-items`, `comparison-item`, `sheet-show`, `label-sheet`, `label-import`, `sheet-import`,
`tag-set-list`, `failure-modes-list`. The screen fills a sheet and submits it when the person is done, to the
imports as they work today (owner, 2026-11-17: not saved item by item); the blind sheet and its key as a job is to
build (API 1).

**W3 Learn from production** (once a goal is deployed): capture what the deployed system decided, evaluate it
against labels, pick the rows where it was wrong or saw something new, and make the next dataset version from them.
*Operations:* `capture`, `arm-from-capture`, `label-from-capture`, `label-coverage-show`, `sheet-show`, the
evaluation (W1's scoring), `pick`, `dataset-extend` / `dataset-from-capture`, `periods`, `faithfulness`.

### Occasionally: guided, plain, correct

**W4 Start an evaluation.** A goal (what it is for, the decision, the measure and its direction — a winner rule from a
named default), its dataset (from a source: a folder, a table, Hugging Face, Croissant, Zenodo, OpenML, Kaggle, a
capture; previewed, fields proposed, created, materialized, profiled), its reference set, and a first system run to
see it work.
*Operations:* `goal-new` (sent with `datasets: []`), `dataset-create`, `fieldset-propose`, `fieldset-new`,
`dataset-materialize`, `dataset-profile`, `reference-promote`, `system-new`, `run`, `source-preview` (API 2); the
dataset's own answers (`"answer": COLUMN` in the query) are written as a label set at create (API 3).

**W5 Bring in a model.** A model record (what it is, its weights and licence), a deployment (where it runs, its
endpoint and settings), onboarded (the probes, kept as dated checks); a flag that is the deployment's own nature
accepted with why; smoked on a system: then it is a choice in W1. A model is **vetted** when every deployment's
onboarding passed and a system on it passed its smoke: computed, never approved by hand (D4).
*Operations:* `model-new`, `deployment-new`, `model-onboard`, `model-show`, `deployment-history`,
`deployment-accept`, `arm-smoke`.

**W6 Make or change a reference.** Promote a label set to a silver or gold reference with who and why; see what the
change moves before re-scoring the arms on it.
*Operations:* `label-set-list`, `reference-list`, `reference-promote`, `leaderboard` (read under another label, such
as `silver`), `score-preview` (its result per arm, API 4), `rescore`.

**W7 Set up a judge.** Judges picked from onboarded models (two families at least), the prompt, the mode; its stored
validation against people's labels shown before it may decide. Validating a judge is a tool, not an operation, and
stays out of the Workbench in 0.8.0 (D6).
*Operations:* `scorer-list`, `scorer-new`, `scorer-set`, `POST /estimate`, `judge-score`, `cost-report`.

### One-off or rare: terse forms, or the commands

**W8 Govern and maintain.** Checking the project (`validate`, a read of about 27 s: the page says "checking…"; D1),
bringing the data to a release's format (`migrate`), moving the project between stores (`data-migrate`), publishing
a dataset (`dataset-publish`), a file under `data/` (`data-put`, `data-rm`). The validate policy, the goal policy and
budgets are files under `data/`; `config.yaml` stays a command-line edit (D9).

## Functional Requirements

1. **Home** shows the project's goals, each with where it stands (its dataset, its rounds, its reference, what is
   running) and its next step (`goal-status`); and what is running now, across goals.
2. **A workflow is one place with its steps**, not one page per operation: a step shows what it needs, what it will
   do (the command it runs, built from the operation and its inputs, for the person who wants it), and runs it.
3. **Jobs:** a step of kind *work* is a job: its cost estimate first (`POST /estimate`, the budget cap), then
   progress and the log, then its result with a link into the catalog. A job keeps running when the browser closes,
   can be watched again, stopped, and resumed with what the stopped job left of its cap (`jobs-resume`). Locks keep
   two jobs off the same data; a job waiting for one is "queued", naming what it waits for.
4. **Forms ask only what is decided at that point.** Links to other things are pickers of what exists (datasets,
   models and their deployments, systems, goals, references). What operations write (a deployment's checks, smokes,
   history; a judge's validation numbers; hashes) is shown, never an input. Expert settings start from named defaults,
   behind "advanced". A setting is never shown as its file's structure.
5. **Both stores.** The same Workbench in a files project and a SQLite project: it calls the operations, and the
   store keeps what they write (a files project's YAML keeps its comments). Nothing in the Workbench changes with the
   store.
6. **Checks without waiting.** An edit is checked by its operation against the entity's schema and links, and its
   problems are shown on their fields. The project's full check (`validate`) is a read the page waits for with
   "checking…", never part of a Save (D1).
7. **Who acted and why.** Every write carries who (`by`; for an agent, the person it acts for); the name is asked once
   and kept in the browser.
   Every decision asks for its reason, as its operation does: a reference promotion (`reason`), a retire (`reason`),
   a round's close (`conclusion`), a baseline's promotion (`reason`), a deployment's accepted flag (`why`).
8. **Parity:** every action is an operation (RFC-032), so it is also an `evh` command and an API call; the
   Workbench shows the command.
9. **Refusals are shown as the API gives them**: an edit's problems (`{error, kind, problems}`), a job refused before
   it exists (`{error}`), a job that failed later (its state, its refusal's kind, its log), and 503 with Retry-After
   while the project's data is moved or migrated.
10. **On a phone.** Every screen works at 390 px (owner, 2026-11-12).
11. **Unsent changes are shown** (owner, 2026-11-17). What a person enters is sent only by the screen's own action
    (Save, Create, Run, Submit). Until then the screen marks it dirty, names what the action will write and asks
    before the person leaves; longer work (a labelling sheet, picked rows, a dataset's steps, models picked, a round
    being built) also counts what is pending and survives a reload in that browser. Labels, preferences and tags are
    submitted as a filled sheet, never saved item by item. The rule and the screens it covers are in UXS-005.

## The API to build first (owner's order, 2026-11-17)

Each blocks a screen; each is built as an operation, for every surface. The detail and the per-screen map are in
`research/internal/WORKBENCH_GAPS_0.8.0.md`.

1. The blind sheet and its key as a job (`sheet-export` as an operation), the key kept on the server for
   `sheet-import`, so the labelling screen can submit "which is better" and tags (W2). Labels need nothing new
   (`label-sheet`, `label-import`). Owner, 2026-11-17: labels, preferences and tags are not saved item by item;
   the screen submits the filled sheet when the person is done, and the sets stay frozen as today. Built
   2026-11-17: `POST /datasets/{dataset}/sheets`, the key refused by the job's files, `sheet-import`'s `export_job`.
2. A source's preview: its description and first rows, writing nothing (W4). Built 2026-11-17 (`source-preview`).
3. A reference from the dataset's own answers (W4: "it came with one"). Built 2026-11-17 (owner: the answer column
   becomes a frozen label set of source `dataset` at create, promoted with `reference-promote`).
4. `score-preview` gives a result (W6). Built 2026-11-17.
5. The jobs list: several states per query, filters by operation and goal, offset and limit (home, jobs). Built
   2026-11-17 (`GET /jobs`, `evh jobs-status`).
6. A JSON answer for every unhandled error (every screen). Built 2026-11-17.

## Success Criteria

- W1 to W3 done start to finish in the Workbench by the owner on this repository's goals, in either store, without
  the terminal; W4 to W7 done once each.
- No form in W1 to W3 longer than one screen before "advanced"; the goal's first form has at most five inputs.
- A round of ten arms shows its cost before it starts and its progress while it runs, and survives a closed browser.
- The catalog remains read-only; every Workbench result is one link from its catalog page.

## Decisions

Owner, 2026-11-06:

1. **One server** for both apps: the catalog and the Workbench under their own paths.
2. **Labelling** in W2: an in-app labelling screen is the first surface; the CSV round trip (`label-sheet` /
   `label-import`, `sheet-import`) stays as an option.
3. **Files mode:** the Workbench changes a files project as it changes a SQLite project: through the operations,
   which change only the values that changed and keep the file's comments.
4. **The Configure page is retired** and what was built for it is thrown away (its pages, forms and routes); the
   store (RFC-025) stays. Done.
5. **The data model** was first worked out as a mock data model beside the mockup; RFC-032 replaces it.

Owner, 2026-11-13: the real Workbench, all of W1 to W8, built on RFC-032's API (RFC-032, "RFC-026, ADR-0027 and the
Workbench").

Owner, 2026-11-17 ("accept all"), after the review of the Workbench against what 0.8.0 built:

- **D1** `validate` stays a read; the page says "checking…" while it runs.
- **D2** A round's arms are run by `sweep` (its systems, the goal, the round); the `round-run` operation RFC-032
  first proposed is not built.
- **D3** A retire is a recorded decision with its reason, not undone.
- **D4** No "approve as vetted": vetted is computed, and the Workbench shows the rule.
- **D5** The round's question is stored as `hypothesis`; the page says "question".
- **D6** Validating a judge stays a tool; W7 shows the stored validation.
- **D7** `mock.js` (this repository's data) stops shipping in the package; the mockup is kept as a frozen design
  reference and the live screens are built from UXS-005.
- **D8** The Workbench stays refused behind a proxy in 0.8.0.
- **D9** `config.yaml` settings (the exposure check's repos, for one) stay out of W8 in 0.8.0.

## How it was decided, and the order from here

Owner, 2026-11-06: agree first, then build.

1. **The structure** (this PRD): what the Workbench solves, its workflows, where the UI effort goes.
2. **Sketches** of the screens (UXS-005), then **a clickable mockup** of them with this repository's real data,
   reviewed in eight rounds (`harness/workbench/`). The mockup's pages, layout and styles are the app's own (owner:
   "think about the mock-up as already a workbench app that you're starting, except it's just a static thing").
3. **RFC-032** (one model, its operations, the API) and RFC-033, built.
4. **From here** (owner's order, 2026-11-17): the API above (1 to 6) and the unsent-changes rule (requirement 11),
   built on 2026-11-17; then the screens, wired workflow by workflow:
   home and goal (wired), W5 (wired), W4's dataset and preparation (needs API 2 and 3), the models and systems, W1 the
   eval, W2 (needs API 1), W3, then W6, W7 and W8 as short lists, and the held-out test and studies last.

## Related Documents

- [RFC-025](../rfc/RFC-025-runs-in-sqlite.md), [PRD-016](PRD-016-managing-project-data.md),
  [UXS-004](../uxs/UXS-004-data-page.md), [ADR-0027](../adr/ADR-0027-the-data-page-writes-locally.md),
  [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (CLI parity).
- The site's method page (the loop before and after deploy) is the picture the Workbench follows.
