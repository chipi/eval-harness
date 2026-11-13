# PRD-017: The Workbench, where an evaluation is set up and run

- **Status**: Draft (owner, 2026-11-06: "workbench is a good name"; "start with the PRD and then the RFC"); 0.8.0
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-004](PRD-004-catalog-and-inspector.md) (the catalog and the inspector, which stay read-only),
  [PRD-016](PRD-016-managing-project-data.md) (the Configure page, retired: the Workbench replaces it),
  [PRD-005](PRD-005-goals-and-rounds.md) (goals and rounds), [PRD-014](PRD-014-datasets-from-production.md) (datasets
  from production), [PRD-015](PRD-015-models-onboarded-once.md) (models onboarded once)
- **Related RFCs**: [RFC-026](../rfc/RFC-026-an-api-for-every-command.md) (an API for every command, with jobs: Accepted), RFC-025 (files or one database)

## Summary

The Workbench is a second application beside the catalog, for people. Agents already do all of this well through
`evh`, the MCP server and the files (the triage fleet's agent is the proof); a person cannot do it so easily. The
catalog shows what a project has and what it decided;
the Workbench is where a person puts things in and runs them: a goal and its data, models, arms, labels, references,
scoring, and the round that ends in a choice. It is organised around the few things people come to do (workflows),
not around the files the harness keeps, and it spends its design on what they do every day or week. It works in
either store: in a files project it edits the files, in a SQLite project it writes the database. Its aim is that the
harness's real complexity feels the way the site explains it: a goal, data, arms, a comparison, a choice.

## Background & Context

- Everything the Workbench does exists today as `evh` commands, 80 of them, and works for agents through them and the
  MCP server (owner, 2026-11-06: "the stuff works now fine for agents … but it's hard for human users"). A person must
  know which commands, in which order, with which options; the site's method page explains the loop, the terminal
  makes you rebuild it.
- The Configure page (PRD-016) put the project's settings into forms built from their schemas. The owner's verdict
  on its forms, 2026-11-06: "massive", "nobody's gonna enter that": a goal's form is 5,023 px with 58 inputs, a model
  record's 5,489 px, the validate policy's 6,194 px. It mapped every key of every file to a field, at the same
  weight, and it only edits: it runs nothing. Two reviews (architecture and UX, 2026-11-06) found its save takes about
  52 s (two full `evh validate` runs) with no progress shown, and no lock between two saves.
- The catalog's read-only rule (UXS index, rule 1) stays: the Workbench is where writing and running happen, the
  catalog where results are read. Each links to the other.

## Goals

1. A person can do each workflow below from the Workbench without the terminal, in either store.
2. The workflows people do daily and weekly are fast and guided; the occasional ones are plain and correct; the
   one-off ones may stay terse (or stay commands).
3. Each form asks only what a person decides at that point: links to other things are pickers, what commands write is
   shown and never edited, expert settings start from named defaults.
4. Running is visible: every run is a job with what it will cost before it starts, its progress while it runs, and
   its result and catalog link when it ends; a job survives the browser closing.
5. The Workbench knows where each goal stands and offers the next step.

## Non-Goals

- Replacing the catalog or the inspector: results are read there, linked from here.
- A public, multi-user service: the Workbench runs on the person's machine (as the Configure page does, ADR-0027).
  Several people sharing one project is a later question.
- A general YAML or file editor. The raw file can be shown; it is not the way in.
- New evaluation capabilities: the Workbench drives what the commands already do (RFC-026 exposes them).
- A new way for agents: they keep the commands and the MCP server.

## Personas

- **The evaluator** (daily, weekly): runs rounds on a goal: new arms, scoring, comparison, a decision.
- **The labeller** (weekly): reviews outputs, labels and tags them, helps promote references.
- **The maintainer** (occasionally): brings in models and judges, sets up goals and datasets, governs references and
  budgets.
Agents are not a persona of the Workbench: they already have the commands and the MCP server, and nothing here
changes those. The API the Workbench runs on (RFC-026) is its means, not a new interface for agents.

## Workflows, by how often they happen

Each workflow is a job to be done with tasks inside it. The Workbench presents the workflow; the tasks are its steps,
each a command (or a few) it runs for the person.

### Daily and weekly: designed with the most care

**W1 Run a round (the core).** On a goal and its dataset: choose the arms (keep from the last round, clone one and
change one thing — the prompt, the model, a setting — or add one from an onboarded model), smoke them, see the cost,
run them all, score them (the goal's scorers; re-scored on the current reference; the goal's judge when it has one),
see the comparison against the baseline, and decide: keep, retire, promote a baseline, close the round with a
conclusion.
*Tasks:* `round-open`, a system per arm, `arm-smoke`, `run --dry-run`, `run` (with `--repeat`), `rescore`,
`judge-score`, `leaderboard` / `pair-test` / `family-test`, `round-retire`, `run-promote`, `round-close`.

**W2 Review outputs, label and tag.** On a goal's dataset: a sheet of items across the arms that matter; read
outputs side by side, pick the better one, give a label, tag failure modes, leave a note; bring back a sheet filled
elsewhere.
*Tasks:* `inspect --sheet`, `pick`, `label-sheet` / `label-import`, `sheet-import`, `tags`.

**W3 Learn from production** (once a goal is deployed): capture what the deployed system decided, evaluate it
against labels, pick the rows where it was wrong or saw something new, and make the next dataset version from them.
*Tasks:* `capture`, `arm-from-capture`, `label-from-capture`, the evaluation (W1's scoring), `pick`,
`dataset-extend` / `dataset-from-capture`.

### Occasionally: guided, plain, correct

**W4 Start an evaluation.** A goal (what it is for, the decision, the measure and its direction — a winner rule from a
named default), its dataset (from a source: a folder, a table, Hugging Face, Croissant, Zenodo, OpenML, Kaggle, a
capture; preview, fields proposed, created, materialized), and a first arm to see it work.
*Tasks:* the goal's file, `dataset-create`, `fieldset-propose`, `dataset-materialize`, `run`.

**W5 Bring in a model.** A model record (what it is, where it runs, its endpoint and settings), onboarded (the probes),
approved as vetted, smoked on an arm: then it is a choice in W1.
*Tasks:* the model record, `model-onboard`, `arm-smoke`.

**W6 Make or change a reference.** Promote labels to a silver or gold reference with who and why; see what the change
moves (a re-score preview) before re-scoring the arms on it.
*Tasks:* `reference-promote`, `score-preview`, `rescore`.

**W7 Set up a judge.** Judges picked from onboarded models (two families at least), the prompt, the mode; validated
against people's labels before it may decide.
*Tasks:* the scorer's file, the judge validation, `judge-score`.

### One-off or rare: terse forms, or the commands

**W8 Govern and maintain.** The validate policy (committed run folders and their floors), the goal policy, budgets,
`validate`, bringing the data to a release's formats (`migrate`), moving the project between stores (`data-migrate`),
publishing a dataset (`dataset-publish`), a release.

## Functional Requirements

1. **Home** shows the project's goals, each with where it stands (its dataset, its arms and rounds, its reference,
   what is running) and its next step; and what is running now, across goals.
2. **A workflow is one place with its steps**, not one page per command: a step shows what it needs, what it will do
   (the command, for the person who wants it), and runs it.
3. **Jobs:** a step that runs is a job: its cost estimate first (the dry run, the budget cap), then progress and the
   log, then its result with a link into the catalog. A job keeps running when the browser closes, can be watched again,
   stopped, and a run resumed with what the stopped job left of its cap (`jobs-resume`). One job at a time touches
   the same data.
4. **Forms ask only what is decided at that point.** Links to other things are pickers of what exists (datasets,
   models and their deployments, goals, references). What commands write (a model's onboarding, smokes, history; a
   judge's validation numbers; hashes) is shown, never an input. Expert settings start from named defaults, behind
   "advanced". A setting is never shown as its file's structure.
5. **Both stores.** The same Workbench in a files project (it edits the files, keeping their comments) and a SQLite
   project (it writes the database). The store is a setting of the project, as today; nothing in the Workbench
   changes with it but where things are kept.
6. **Checks without waiting.** What a save must satisfy is checked as the person types where it can be (the schema,
   the id); the project's own check (`validate`) runs as a job, not inside the Save button.
7. **Governance:** a reference promotion, a model's vetting, a judge's validation, a baseline's promotion and a round's
   close record who and why, as the commands do now.
8. **Parity:** every action is an `evh` command (UXS-003) and an API call (RFC-026); the Workbench shows the command
   it runs.

## Success Criteria

- W1 to W3 done start to finish in the Workbench by the owner on this repository's goals, in either store, without
  the terminal; W4 to W7 done once each.
- No form in W1 to W3 longer than one screen before "advanced"; the goal's first form has at most five inputs.
- A run of ten arms shows its cost before it starts and its progress while it runs, and survives a closed browser.
- The catalog remains read-only; every Workbench result is one link from its catalog page.

## Decisions (owner, 2026-11-06)

1. **One server** for both apps: the catalog and the Workbench under their own paths.
2. **Labelling** in W2: an in-app labelling screen is the first surface; the CSV round trip (`label-sheet` /
   `label-import`, `sheet-import`) stays as an option.
3. **Files mode:** the Workbench edits a files project's files as it writes a SQLite project's database: the server
   saves, changing only the values that changed and keeping the file's comments (how, the RFC says).
4. **The Configure page is retired** and what was built for it is thrown away (its pages, forms and routes); the
   store (RFC-025) stays.
5. **The data model** is worked out as a mock data model alongside the mockup, and reviewed with it.

## How it is decided, before anything is built

Owner, 2026-11-06: agree first, then build.

1. **The structure** (this PRD): what the Workbench solves, its workflows, where the UI effort goes.
2. **Sketches** of the screens of W1 to W3 and the home, and the plain forms of W4 to W7 (a UXS).
3. **A clickable mockup** of those screens with this repository's real data, and beside it a mock data model (the
   entities the screens show and how they link), both reviewed with the owner in as many
   rounds as it takes. The mockup is the Workbench app's first form, static: its pages, layout and styles are the
   app's own, so once it is agreed it is wired to the API rather than rebuilt (owner: "think about the mock-up as
   already a workbench app that you're starting, except it's just a static thing").
4. Then RFC-026 (the API and jobs) and the data-model RFC, and the wiring, workflow by workflow.

## Related Documents

- [RFC-025](../rfc/RFC-025-runs-in-sqlite.md), [PRD-016](PRD-016-managing-project-data.md),
  [UXS-004](../uxs/UXS-004-data-page.md), [ADR-0027](../adr/ADR-0027-the-data-page-writes-locally.md),
  [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (CLI parity).
- The site's method page (the loop before and after deploy) is the picture the Workbench follows.
