# PRD-015: Models, onboarded once, for every eval

- **Status**: Implemented (v0.6.0)
- **Authors**: Marko Dragoljevic
- **Related RFCs**: [RFC-020](../rfc/RFC-020-onboarding-a-model.md) (records, onboarding, arm smoke, the Models
  page), [RFC-021](../rfc/RFC-021-fingerprint-v5.md) (fingerprint v5: the deployment, the settings, the runner)
- **Related ADRs**: [ADR-0021](../adr/ADR-0021-a-deployment-is-vetted.md) (a deployment, not a model, is what is
  vetted and fingerprinted)
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (the Models page, the model page, the arms badge),
  [UXS-002](../uxs/UXS-002-inspector.md) (conditions)
- **Related PRDs**: [PRD-001](PRD-001-evals-and-comparison.md) (evals and the fingerprint),
  [PRD-004](PRD-004-catalog-and-inspector.md) (the catalog and the inspector)

## Summary

A model a project tests is set up once, written down, checked, and reused by every eval: its builds on
every machine and host it runs on, what it can do, the settings chosen for it and why. Before an arm's full run,
a short smoke on its own task says whether it runs, how long the run will take and what it will cost, and
whether its settings leave it reasoning, unbounded or slow. Every run's fingerprint then records the deployment
it ran on, so a result can always be traced to the weights, server and machine behind it.

## Background & Context

Without a step that makes someone choose a model's settings, an eval runs each server's defaults, and:

- reasoning models reason at their server's default, many times the tokens a turn of the models that do not reason,
  so the results compare defaults as much as models;
- a model can reason in a loop and never answer until it is set up with reasoning off;
- one tag can name an MLX build on one machine and a GGUF build on others, or an older build on one host;
- a self-hosted model at temperature 0 can give byte-identical output twice on one machine and different decisions
  on another: repeats measure nothing, and a fingerprint that records the machine that sent the requests names the
  wrong one.

Each is found late, by reading logs. A system can set `max_tokens` and `reasoning_effort`; what is needed is the
step that makes someone choose them, the record that keeps the choice, and a fingerprint that names where a model
really ran.

## Goals

- A model is set up once per project and used by any eval, with its settings and the reason for each kept.
- Each place a model runs (a machine, a server, a hosted route) is checked on its own, because the same weights
  behave differently there.
- An arm is checked on its own task before its full run, in minutes and for cents, with a projection of what the
  full run will take.
- A run's fingerprint says which deployment produced it; a comparison says which part moved.
- One path for every kind of arm (an LLM, an ML model, a baseline), with the LLM checks on top.

## Non-Goals

- Choosing settings for a project: the harness measures and flags; a person decides and writes why.
- Pulling models, managing servers, or switching a shared machine's mode.
- Tuning prompts.
- Running `evh` on other machines; the runner is recorded.

## Personas

- **The person running the evals** adds a model to a goal and wants its arms to run as intended, the first time.
- **The reviewer** reads a result and needs to know which build, on which machine, with which settings.
- **The next person** reruns an arm months later and needs to set the model up the same way.

## User Stories

- _As the person running the evals, I onboard a model once (`evh model-onboard --model-id <id> --deployment <d>`), so that every arm of
  it inherits settings that were checked._
- _As the person running the evals, I smoke an arm before its full run (`evh arm-smoke --system <id> --dataset <id>`), so that I know it
  runs, how long it will take and what it will cost before it spends any of it._
- _As a reviewer, I see on the Models page which models are vetted, where each runs and with what, and on an
  arm's page which deployment its runs used._
- _As a reviewer, `evh run-compare` tells me whether the deployment, the settings, the data or the instrument
  moved between two runs, and the runner never counts as one of them._
- _As the next person, I read a model record's settings and their reasons, and its history of changes._

## Functional Requirements

- **FR1 Records.** `data/models/<model_id>.yaml` (schema `model.schema.json`, validate V1 and V18): kind,
  aliases, weights and licence, capabilities, settings with `settings_why`, history, and deployments, each with
  an id, where, server and settings or device and backend, the build (digest, revision or hash; quantization),
  for a hosted one its provider id and route, an endpoint, and its own onboarding.
- **FR2 Onboarding.** `evh model-onboard --model-id <id> --deployment <d>` probes an LLM through the deployment's endpoint:
  the digest its server reports against the record's, reasoning at the default and with the record's settings,
  JSON, determinism, speed (the last two written to the deployment, not the record), and a probe reply cut off.
  A build the server serves differently is flagged, and the record takes it with a history entry for the one
  replaced. An ML model or a baseline is onboarded through an arm (`--system S --dataset D`). `ONBOARD PASS` or `ONBOARD
  CHECK`; the record's settings are never changed by it.
- **FR3 Arm smoke.** `evh arm-smoke --system <id> --dataset <id>` runs any arm's first items and writes no run: runs, valid
  output for the scorer, a projection of the full run, build pinned, determinism, cost; for an LLM, each model
  call (a provider's `_meta`, or an adapter's `meta["calls"]`): reasoning, slow, long, cut off, no answer, and a
  hosted call served off its pinned route. Written into the record.
- **FR4 Arms name a record.** `model_record:` and `deployment:` in a system; the record's settings (what holds
  whatever the task: reasoning, an ML model's device and precision) under the system's params, which add the
  task's own (its reply cap, its call limit); the run records both.
- **FR5 Fingerprint v5.** `instrument`, `data`, `deployment`, `settings`, each hashed, `hash` over the four; the
  runner outside the hash; `evh run-compare` names the part that moved; the inspector's speed warning tells a
  deployment from a runner. `evh migrate` brings a project's fingerprints to v5 (its fingerprints step).
- **FR6 The catalog.** The Models page, a page per model with its deployments and their onboarding, a smoke badge
  on the arms page, a models tile; `evh model-list` the same (and over `evh mcp`). A model is *vetted* only when an
  arm that names it passed its smoke; its onboarding alone makes it *onboarded*.
- **FR7 Advice, not refusal.** `validate` notes an arm never smoked, a reasoning model with no `max_tokens`, and a
  tag that is a different build on two deployments; `--repeat` notes when a deployment's passes will be identical.

## Success Metrics

- A run of a system that names a model record and a deployment records that deployment in its fingerprint with
  `source: record`.
- `evh run-compare` names which part of the fingerprint moved between two runs.

## Limits (known, as built)

- **An ML model is onboarded through an arm**, not probed through an endpoint: `model-onboard --system S --dataset D`
  runs the arm's first items.
- **A hosted route is checked, not enforced.** `arm-smoke` flags a call served by an upstream the pinned route does
  not allow; a run does not refuse one.
- **The upstream host and quantization behind a hosted alias** are only what the gateway and provider report; a
  provider can change weights behind a name.
- **Determinism is checked on one request.** Onboarding sends the same probe twice; a task's longer prompts may
  diverge where the probe does not.
- **Reasoning is detected from what the server returns** (reasoning text or tokens); a server that reasons
  silently and reports neither reads as not reasoning.
- The settings history has no "smoke / result before and after" columns; an arm whose model has no record is not
  on the Models page.
