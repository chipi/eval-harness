# ADR-0029 — One data model; the command line, the API and MCP made from one registry

**Status:** Accepted (owner, 2026-11-13, [RFC-032](../rfc/RFC-032-one-model-two-surfaces.md)); built in 0.8.0: every
step of the build order, 0 to 9, including step 9's P1 to P4 (the views' cache, the SQLite release, every read an
operation answered in the server's process, every job an operation and its inputs, and no answer written ahead).
**Date:** 2026-11-15
**Detail:** [RFC-032](../rfc/RFC-032-one-model-two-surfaces.md) (its decision blocks, step by step),
[RFC-026](../rfc/RFC-026-an-api-for-every-command.md) (what it keeps and what it replaces),
[ADR-0027](ADR-0027-the-data-page-writes-locally.md) (amended here), `harness/docs/UPGRADING.md` (formats 1 to 7)

## Context

By 0.7.2 the project's facts lived in eight runs folders, config files that named their dataset, a model record that
held its deployments, rounds that listed retirements by folder, and 47 modules (a grep, step 6) that built these
paths themselves. Each `evh` command printed what it chose and the API (RFC-026) served the commands by running them as
processes, so the command line, the API, MCP and the catalog each computed their own numbers: a round's arms were
worked out two ways (29 against 87 on CNN r1), a round's leader by two rules, a leaderboard by a third
implementation. The owner asked for "the CLI and the API as different surfaces around the same model".

## Decision

**Three layers.** `model/` holds the entities and the views; `ops/` holds the operations; the command line, the API
(`/api/v1`) and MCP are surfaces made from the operations. Runs, rounds, goals, datasets and their views are read
through `model/`, which reads any data directory (a deployment's copy too) through its data root. The modules that still
read data folders directly are not yet moved to the model layer, among them `judge_score`, `_baselines`, `family_test`,
`dataset_split`, `_models`, `capture_restore`.

**Entities.** Each has one schema, one id and one place: goal; dataset (its items, source, profile, versions, sealed
side as parts) and fieldset; label set, tag set and reference; model and deployment (apart, with the deployment's
checks as dated history); prompt and its versions; **system** (what is evaluated: a deployment, a prompt version and
settings, with no dataset); run (one pass of a system over a dataset) and its scores under it; round and its stored
**arms** (a system read under one label in a round); baseline; scorer (a judge's validation and the people's checks as
parts); study; faithfulness record; capture. "Config" names nothing: a run records `system_id`.

**Operations.** A named function with typed inputs and an output, of one kind: *read* (answers at once, writes
nothing), *edit* (an entity's settings, checked against its schema and links, under its lock, comments kept, with a
short history), *decision* (refused without who and why), *work* (a job). A decision or a work operation runs as a job:
its inputs, its locks and whether it spends are declared, and the job names the operation and its inputs, never a command
line (a decision quick enough is answered in the server's process). The registry is the source of each surface:
each operation's command-line arguments, the API's resources and their checks, its OpenAPI description and the MCP tools.

**Views.** Where a goal stands, its decision (one leader rule for goals and rounds), a round's evidence, the
leaderboard, a comparison, label coverage: each computed from what is stored when read, never stored, read alike by
the catalog, the Workbench, the command line and the API. The catalog renders the views; a write rebuilds it.

**The project's format.** `data/project.yaml` names it; numbered migrations (`harness/evaluation_harness/migrations/mNNNN_*.py`) take a
project forward, reading what is stored, never the current model; no version on each record, no down-migration (the
backup is the rollback). A key that is part of a stored hash keeps its name: the fingerprint's `arm.config_id`,
judging sets' arms, label sets' and silver references' sources, ids recorded at a promotion.

**Amends ADR-0027.** The server writes edits itself, in either store, gated by the API's token and the
`X-EVH-Data` header, not by `configure: true`.

## Consequences

**Positive.** One computation per number: the catalog, `evh` and the API agree by construction (step 8 found the
overview's leader-against-baseline test uncorrected for the arms the leader was chosen from, and a round leader the
goal would flag possible; both fixed once). Bugs a single resolver removes: a dataset's item folder read against the
working directory, a materialized copy deleted before its rebuild, a reference promoted under another name missed.
The Workbench and agents get typed resources instead of a command's printed tables.

**Negative.** Seven format steps in one release, each with a migration the project runs (`evh migrate`). Command and
tool names change where a legacy command is replaced by an operation (step 9). Every view is computed on read: its
cost is paid per data change, which needs the cache the RFC names (measured in step 9).

**Neutral.** Files stay files a person can read; SQLite keeps the same keys; relational tables wait for a measured
query that needs one.

## Alternatives considered

- **Keep the commands as the contract and serve them** (RFC-026 as built): the surfaces drift, since each command
  prints what it chooses.
- **Operations only, as `POST /ops/<name>`:** simpler, not resources; the owner chose resources and actions.
- **The whole model first, then move the commands:** a long time with two ways of doing everything; entity by entity
  kept one.
- **A version on every record:** one more thing that can disagree with the project's format.
- **Down-migrations:** each step written and tested twice, for a rollback the backup already gives.
- **Relational SQLite tables now:** nothing measured needs them.
- **"Arm" everywhere, the dataset inside it:** one name, and the duplicate files the dataset makes.
