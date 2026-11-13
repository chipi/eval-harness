# RFC-032: One data model, with the command line and the API as its surfaces

- **Status**: Accepted (owner, 2026-11-13: "Yes and yes", to accept it and start the build); drafted with the owner the same day. Every decision below was taken in that discussion and is quoted
  under **Decisions**; the first draft's six open questions are answered under **The six questions of the first draft**.
- **Authors**: Marko Dragoljevic
- **Related**: [PRD-017](../prd/PRD-017-workbench.md) (the Workbench; step 4 of "How it is decided" names this RFC),
  [UXS-005](../uxs/UXS-005-workbench.md) (its screens and the mock data model this replaces),
  [RFC-026](RFC-026-an-api-for-every-command.md) (the API and jobs, amended below),
  [RFC-027](RFC-027-who-acted-and-baselines-per-goal.md) (who acted), [RFC-025](RFC-025-runs-in-sqlite.md) (both stores),
  [ADR-0027](../adr/ADR-0027-the-data-page-writes-locally.md) (writes on this machine only)

## Abstract

The harness has no data model of its own. Each of its commands reads and writes files by path, and the API
(RFC-026) runs those commands as processes: a read is `POST /api/v1/read/<command>`, a write is a job running a
command's arguments. Building the Workbench on that showed what it costs: reads that answer text, a label written
by uploading a CSV, records no command reads, no record of where a goal stands.

This RFC gives the harness one model: its **entities**, each with one schema and one place in the store, and its
**operations**, each declared once with typed inputs and outputs. The command line, the API, the MCP server and jobs
are surfaces over that model, and none wraps another (owner: "in my mind cli and api are different surfaces around
same model"). The same model computes the views the catalog, the Workbench and `evh` print, so they cannot disagree.
It also fixes how data moves between releases, a deployed project included.

## What exists today (read 2026-11-13)

- **Entities live where commands put them.** `harness/data/` has 27 entries, among them `goals/`, `rounds/<goal>/`,
  `models/`, `configs/`, `baselines/<goal>/<dataset>/`, `labels/`, `references/{gold,silver}/`, `scorers/`,
  `judge-validation/`, `judge-verdicts/`, `judging-sets/`, `captures/`, and a dataset spread over `datasets/`,
  `materialized/`, `sources/`, `profiles/` and `fields/`. 19 JSON schemas in `harness/schemas/` cover some of them.
- **A model record holds its deployments** (`models/<id>.yaml`, `deployments:`).
- **What is compared is a config**, and a config names its dataset: `arm_bart_l_dm200.yaml` is "identical to
  arm_bart_l_n200.yaml except the dataset" (the two differ in `config_id` and `dataset_id` only). 455 config files
  are tracked in the repository.
- **"Runs" are eight folders, and four of them are not runs.** `runs` (274), `runs-linux` (10), `runs-pair` (6) and
  `runs-repeats` (18) hold passes with their outputs. `runs-silver` (29) and `runs-adjudicated` (30) hold
  `metrics.json` and `predictions.jsonl` with no outputs: existing runs scored again. `runs-rescored` holds copies
  of `runs/` and `runs-repeats/` under a hash; `runs-judged/<judge>/<run>/` holds a judge's scores. The folder name
  carries meaning: r2 of news_summary_cnn retires its arms with `runs_dir: runs-linux`, because the same config id
  has runs in two folders.
- **A round's arms are worked out, not stored:** the configs whose runs name the round (`round:` in the config),
  plus carried, less retired (`_rounds.arms_of`).
- **Views are computed inside commands.** `evh rounds` computes a round's evidence (each arm against the leader,
  Holm), `evh goals`, `evh leaderboard` and `catalog_build` (172 functions) compute theirs, each on its own.
- **The store is a file system.** `_store` reads and writes by path; in a SQLite project each key is a path and
  each value that file's bytes.
- **Migration** is `evh migrate`: four steps that each recognise old data by its shape. The project records no
  format, so nothing stops a command from reading data that has not been migrated.
- **Prod** (`infra/deploy/render.sh`, `deploy.sh`) copies `harness/data` from git into each release and mounts it
  read-only: it is migrated only because migrated data is committed, and nothing checks it.

The Workbench's gap map (2026-11-13, against the mockup's screens) found, among others: `data-ls` and `data-show`
answer text through the API; `label-coverage` cannot be called (a read that needs an upload); no command reads a
judge's validation or records a model's approval; one label or one pick can only be written as a CSV; a job has no
progress; the Workbench is not served. Not re-verified by hand: `data-put`'s file argument is a plain string, which
the API's path check does not see (`data_put.py:39`, `_api.py:189-208`); it is checked and closed in step 0.

## Design

### The layers

```
        the CLI        HTTP API      MCP (agents)      the Workbench (through the API)
              \            |             /
     operations: one registry; typed inputs and outputs (JSON Schema); kind, locks, who
     entities: one schema each, one id each, links by id
     views: computed by the model from the entities, cached, never stored as data
     stores: files | SQLite, the same keys
     jobs: an operation run detached (RFC-026's supervisor, locks, caps, ledger)
```

The model is a package of its own inside `evaluation_harness`: `model/` (entities, their schemas and layout, the
views) and `ops/` (the operations). Today's command scripts become thin CLI surfaces over it.

### Entities

| Entity | What it is | Parts |
| --- | --- | --- |
| Goal | the decision an evaluation helps make; its measure, direction and winner rule; its policy | — |
| Dataset | a frozen list of items | items, source, profile, versions, its sealed side |
| Fieldset | the facts each item carries, to slice results by; shared by datasets | — |
| Label set | answers someone (a person, a model, a rule) gave for a dataset's items | labels |
| Reference | a frozen copy promoted to gold or silver, with who, why and its tier, pointing to the label set (or the dataset's own answers) it came from | — |
| Model | a model: what it is, its weights and licence | — |
| Deployment | where and how a model runs: endpoint, settings | its checks: each probe run, smoke and approval, dated, kept |
| Prompt | a prompt | versions |
| **System** | what is evaluated: a deployment, a prompt version, settings; **no dataset** | — |
| Run | one pass of a system over a dataset's items: outputs, cost, latency, fingerprint; the machine, the purpose (pair test, repeat of another run), the round it was made in | scores |
| Score | a run's outputs scored by one scorer against one reference | rows, metrics |
| Round | one comparison on a goal and a dataset, from its question to its decision | **arms** |
| **Arm** | a system placed in a round: when added, the run(s) it is read through, retired (when, who, why) | — |
| Baseline | the run a goal stands on, per dataset | versions, with the evidence of each |
| Scorer | how outputs are scored; a judge scorer names its judges (systems), its protocol | its validation |
| Capture | what a deployed system decided | records |
| Pick, failure modes and tags, study and looks, exposure, faithfulness | as RFC-019 to RFC-031 define them | — |
| Job | an operation running detached (not project data) | log, progress, result |

Each entity has one schema (JSON Schema, in `harness/schemas/`), one id, and links to others by id. New schemas:
deployment, system, arm, run, score, label set, pick, job, study, exposure, and each view.

**What gets an id.** A thing has an id of its own when it is shared or referred to on its own; otherwise it is a
part of the entity it belongs to, read and written with it, under its lock. A dataset's profile is one dataset's
fact (a part); a fieldset is used by several datasets (an entity). A part may keep a history (a deployment's
checks) rather than be overwritten.

**Names.** "Config" is no longer the name of anything: it was the file's format. What is evaluated is a
**system**, which can be run on any dataset and placed in any round; a system in a round is an **arm**. A run is a
system run on a dataset, in a round or not; a judge is a system a judge scorer uses.

### Operations

An operation is a named function with inputs and an output described in JSON Schema, and a declaration of what it
is:

- **read**: answers at once, writes nothing;
- **edit**: changes an entity's settings; in-process, under the entity's lock; checked against the entity's schema
  and its links (every id it names exists); only changed values written, a file keeping its comments
  (`ruamel.yaml`, as the Configure page's form did);
- **decision**: promote a baseline or a reference, open, close or retire in a round, approve a deployment, unseal,
  roll back; refused without who and why; in-process when quick, a job when it runs other work;
- **work**: run, score, judge, onboard, smoke, capture, materialize, the project's full `validate`, migrate; always a
  job, with an estimate first where there is one, a cap when it spends, its locks, its progress.

Every write records who and when (RFC-027's actor). A decision also records why and what it rests on (a paired
test, a validation). An edit keeps a short history (the previous value, who, when), so a change can be seen and
undone.

**The registry is the source.** `evh`'s arguments (argparse), the API's routes and their checks, its OpenAPI
description, the MCP tools and the Workbench's forms are made from the operations' schemas; the schemas' titles and
descriptions are the help text. This is RFC-026's registry turned round: RFC-026 builds the API from the commands'
parsers.

### Surfaces

- **CLI**: arguments in, the operation, its output printed as text, or as JSON with `--json`. Every command prints
  the same data either way, so the two cannot drift.
- **API**: entities as resources, operations as actions. `GET /api/v1/goals`, `GET /api/v1/goals/{id}`,
  `PATCH /api/v1/goals/{id}`, `GET /api/v1/goals/{id}/rounds/{r}`, `POST /api/v1/goals/{id}/rounds/{r}/close`,
  `POST /api/v1/systems/{id}/runs` (answers a job). Reads call the model in the server's process (no process per
  read, as RFC-026 has it). RFC-026's token, cookie, Host and Origin checks, `X-EVH-Data`, uploads and job routes
  stay.
- **MCP**: the read operations, as today.
- **Jobs**: a job names an operation and its typed inputs, not a command line. RFC-026's supervisor, locks, caps,
  round ledger, stop and resume stay. A job reports progress (items done of how many, spend so far) as it goes.

### Views

Where a goal stands and its next step, a round's evidence (each arm against the leader, Holm: the raw p and its
threshold; what `evh rounds` would suggest; why nothing is promoted), the leaderboard, a comparison, a dataset's
label coverage: each is a read operation and a resource (`GET /api/v1/goals/{id}/status`,
`/goals/{id}/rounds/{r}/evidence`, `/goals/{id}/leaderboard`, …). They are computed from what is stored when read,
never stored as data; a cache keyed by what they were computed from is cleared by any write to it.

**The catalog renders these views.** `catalog_build` stops computing its own, so the catalog, the Workbench and the
command line give the same numbers. (The Workbench mockup showed r4's statistics with a test `evh rounds` does not
use, eight reviews in; one computation, read everywhere, is the fix.)

### Stores

Both stores stay, keyed by path as today. The model owns the layout: one table maps each entity to its keys
(`goals/<id>.yaml`, `systems/<id>.yaml`, `deployments/<id>.yaml`, `runs/<id>/run.json`, `runs/<id>/outputs.jsonl`,
`runs/<id>/scores/<scorer>@<reference>/…`, `rounds/<goal>/<r>.yaml`). Nothing outside the model builds a path or
globs a folder. Files stay files a person can read (YAML with comments, JSONL for items and outputs); SQLite keeps
the same keys. Relational tables come only if the scale step (1k to 10k items, PLAN_0.8.0 S) measures a query that
needs one, and then inside the store.

### Migrating, now and after 0.8

- **A project has a format.** `data/project.yaml` records `format: N`; each release declares the format it reads.
  Every operation refuses older data (`ERROR (old-format): your data is at format 3, this release reads 4: run evh
  migrate`, with the dry run first) and newer data (naming the release that wrote it). No record carries a version of
  its own; an export (Croissant, a Hugging Face dataset) keeps its own format's version.
- **Migrations are numbered steps**, `migrations/0005_runs_and_scores.py`, each from format N to N+1, with a dry run
  (what changes, counted per entity), the change, a check (every view gives the same numbers before and after,
  unless the step declares what it changes on purpose) and its UPGRADING line. A step works on the stored data, never
  through the current model's code, so a project of any released format reaches the current one through the steps
  in between. Steps are kept from 0.8 on.
- **Undo before the change:** a files project's undo is git (`migrate` warns about uncommitted changes); a SQLite
  project's database is copied first and the copy kept beside it.
- **No down-migrations.** A rollback after a migrated deploy restores the backup taken before the migration; what was
  written since is lost, and the deploy's log says so.
- **CI** keeps a small fixture project frozen at each released format, migrates each to the current one and checks
  the views.
- **A release that changes a stored format** ships its step, its frozen fixture and its UPGRADING section. Never a
  shim: the old layout is not read after a migration.

**A deployed project is migrated by its deploy, not left to its owner** (owner: "we also have to migrate prod as
part of deploy and not just everyone for themselves"):

- every deploy runs `evh migrate --check` on the data it ships and stops when it is not in the release's format
  (this repository's prod: in `render.sh`, whose data comes from git);
- a deployment holding data of its own (a Workbench on a server, captures from production, a SQLite project)
  migrates it as a deploy step, each a gate as `deploy.sh`'s are: preflight (the live format against the release's,
  the dry run's counts kept with the deploy), drain (jobs finish or pause; the server answers 503, as for
  `data-migrate`), backup, the change, the check, then the switch; on any failure the backup and the previous release
  are restored together;
- the harness ships the commands (`migrate --check`, `--dry-run --json`, `--backup`) and a runbook section; each
  deployment's own infra calls them.

### The first steps of the migration this RFC makes

- the four run folders with outputs become `runs/`, with the machine and the purpose as fields; the four others
  become scores of the runs they scored;
- configs become systems with their dataset taken out (`_n200` and `_dm200` pairs become one system each), and the
  arms of each round are written from today's runs, carried arms and retirements; `round:` and `runs_dir` go;
- deployments leave the model records;
- before and after each, every view (leaderboards, rounds' evidence, the catalog's numbers) is the same.

## RFC-026, ADR-0027 and the Workbench

Kept from RFC-026: the token, the cookie, the Host and Origin rules, uploads and their limit, jobs (supervisor, locks
first, state, logs, stop, resume, unsupervised and lost), caps where spend is counted, the round ledger, the estimate,
`jobs-*`, the catalog swap, `data-migrate`'s 503. Changed: the registry is made from the operations, not the parsers;
reads run in the server's process; a job runs an operation; and the server writes edits itself (RFC-026 decided on
2026-11-11 that it writes nothing itself and jobs do; owner, 2026-11-13: edits in-process, the full `validate` a job).
An ADR records this and amends ADR-0027 (writes in either store, gated by the token, not by `configure: true`).

The Workbench (PRD-017, all of W1 to W8, owner 2026-11-13) is built on this model's API, wired workflow by workflow
as the entities it needs land. The mockup (`harness/workbench`, UXS-005, eight reviews) is its design.

## Build order

Entity by entity: each command moves onto the model as its entity lands and the old path is deleted (no shims),
and the Workbench's screens that need it are wired behind it.

0. The skeleton: `model/` (the entity table, schemas, layout), `ops/` (the registry, its kinds), the surfaces made
   from it (argparse, API routes, MCP), the project format and the numbered migrations (`--check`, verify by views,
   the frozen fixtures), the format gate in `render.sh`; `data-put`'s file argument checked (above).
1. Goals and the goal's status view: proves the stack end to end (`evh goals`, `GET /goals`, the Workbench's home).
2. Models and deployments, apart (a migration step).
3. Prompts and systems (configs become systems; a migration step).
4. Runs and scores (the eight folders; a migration step).
5. Rounds with their arms and the evidence view; baselines.
6. Datasets (items, source, profile, versions, the sealed side), fieldsets, label sets, references, picks, captures,
   failure modes and tags, exposure.
7. Scorers and judges, studies, faithfulness.
8. The catalog onto the views.
9. What RFC-026 built that this replaces is removed (the reads by process, the registry from parsers); the ADR.

## Testing

- Parity: every view's JSON from the command line (`--json`) equals the API's resource, in both stores.
- Every migration step: its dry run, then the views before and after equal; every frozen fixture migrates to the
  current format.
- An operation added without a schema, a kind or a lock entry fails a test, as an unclassified command does today.
- The Workbench's browser tests run against a served project, not the mockup's data.

## Alternatives considered

- **Keep the commands as the contract and serve them** (RFC-026 as built): the gap map is its cost; the surfaces
  drift because each command prints what it chooses.
- **Operations only in the API** (`POST /ops/<name>`): simpler, not resources; the owner chose resources and actions.
- **The whole model first, then move the commands:** a long time with two ways of doing everything; entity by entity
  keeps one.
- **A version on every record:** one more thing that can disagree with the project's format; the project migrates
  whole.
- **Down-migrations:** each step written twice and tested twice, for a rollback the backup already gives.
- **Relational SQLite tables now:** nothing measured needs them yet.
- **"Arm" everywhere, the dataset inside it:** keeps one name, and keeps the duplicate files the dataset makes.

## The six questions of the first draft

Answered the same day (owner: "Love the reasoning and answers. I agree with all").

1. **How a run starts.** A run is always a system run on a dataset: `evh run --system cnn_bart_l --dataset
   cnn_dailymail_200`, optionally `--round r4`. Running a round is an operation of its own, `evh round-run --goal
   news_summary_cnn --round r4` (every arm, or `--arm`), from the round's dataset and arms. Runs happen outside rounds
   (smokes, pair re-runs, repeats, one-off runs), so the base operation does not need one; in the Workbench, "Run 4
   arms" is one action on a round. A run made in a round records it as where it came from, and the arm's
   `read_through` points to it; membership stays on the round's list.
2. **A dataset's parts.** Its items, profile, source and versions are parts of it: each dataset has one of each today
   (`materialized/<id>`, `profiles/<id>.json`, `sources/<id>.rows.json`), the profile written by a command but a fact
   about that dataset's version, never shared. A **fieldset** is an entity: `fields/triage.yaml` is used by
   `orrery_triage_smoke`, `orrery_triage_v1` and `orrery_triage_v1_labelled`. Several datasets from one remote source
   are datasets naming the same source and revision; no entity is needed for it.
3. **A reference** is its own entity, frozen at its promotion, pointing to where it came from. Today it is a copy (a
   text per item and a manifest: `items_sha256`, `tier`, `reason`, `actor`, `caveat`, `promoted_from`, which names a
   label set or, for ag_news_20, the dataset's own answers). Label sets change (RFC-031's labels that mature); scores
   point to a reference, which must not change under them. Promotion is a decision that freezes a copy.
4. **A judge is a system** (a deployment, a prompt version, settings) that a judge scorer names, with its protocol
   (the mode, how judges combine) and its validation. Today `scorers/judge-summ-v2.yaml` repeats each judge's
   provider, model, family, temperature and prices: a model record's and its deployment's facts, written twice. A
   judge needs what any system needs (onboarding, a pinned prompt, its cost counted), and its outputs on a judging set
   are a run of the judge system. The validation stays the scorer's: it validates that protocol with those judges.
5. **A deployment's checks** (each probe run, smoke and approval) are dated entries kept on the deployment, each with
   its result and the job that made it; approval is a decision (who and why); the deployment's state is read from the
   latest. Today one `onboarding: {status, at}` is overwritten at each check. "Vetted" (ADR-0021) means something only
   with when and against what: a change of endpoint shows as "checked before the change".
6. **The catalog stays static, the Workbench reads live, from the same views.** The public catalog is built from the
   views when it is built or deployed, as today: prod serves it read-only and its server refuses `/api/v1` with
   `--public`. The Workbench reads the views through the API. The inspector, which compares on request, stays served.
   Locally, a write that changes what the catalog shows starts a catalog rebuild job, so it is never stale (today the
   server says "restart it").

## Decisions (owner, 2026-11-13)

Quoted from the discussion, typing slips corrected.

- **The model, and its surfaces.** "I said I want this to be API driven originally"; "in my mind cli and api are
  different surfaces around same model". Asked where the model lives, the API's shape and how to get there:
  "Recommended is good on a/b/c": its own package (`model/`, `ops/`); resources and actions; entity by entity, no
  shims, the Workbench behind it.
- **The entities.** "Initial list looks good."
  - **Model and deployment**: "should be their own things. We might want to deepen that later".
  - **System and arm**, "config" retired: asked what to call what is compared ("Config can mean all kind of things
    … arm is maybe too specific. Maybe it's even an option to look for another name or some combination of
    names. What do you think?"), the owner accepted system plus arm ("Yes").
  - **Runs**: one collection, a score apart from its run, the folders migrated ("Yes").
  - **A round's arms**: stored by the round ("I want to keep things pretty straightforward … let's get a
    recommendation"; then "Yes").
- **Schemas and writes.** "Q3 yes, good idea, 4a and 4b also ok": JSON Schema as the source of truth; edits in the
  server's process; every write records who and when, a decision also why.
- **Views, stores, migration.** "Ok on q6 and q7 and q8. Really love how with 6 we bring benefit to catalog also."
  Then: "On q8 we should also think about data migration in general and how would that work moving forward after
  0.8", and "Don't forget that we also have to migrate prod as part of deploy and not just everyone for themselves".
  A project format number, not a version per record, and no down-migrations: "I agree with a and b".
- **The six questions of the first draft**, as above: "Love the reasoning and answers. I agree with all".
