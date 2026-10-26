# Architecture

How the harness is built, layer by layer, and why each layer refuses what it refuses. The
rules themselves are in [Concepts](../../harness/docs/CONCEPTS.md); the commands in the
[Runbook](../../harness/docs/RUNBOOK.md). What each capability is for is in the
[product requirements (PRDs)](../prd/index.md), what a user sees and types in the
[UX specifications (UXS)](../uxs/index.md), the technical designs in the [RFCs](../rfc/index.md),
and the key decisions, a few lines each, in the [ADRs](../adr/index.md).

## What it is

The harness is a Python package, `evaluation-harness`, with one command, `evh` (in a checkout,
the same scripts run through `make`). It holds **code and schemas only**. A project's data, its
datasets, configs, runs, references and goals, lives in the project and is found through
`EVAL_HOME` and `EVAL_DATA_DIR`, so an upgrade changes code and never touches results.

This repository is the package plus six worked experiments run with it, the public site that
explains the harness and its findings, and these docs.

## The layers

Each layer freezes what it produces, so the next one can be redone without redoing it.

| layer | what it records | commands | what it refuses |
|---|---|---|---|
| **1. Data** | a dataset: every item and the sha256 of its bytes, from a file or a pinned URL, and the typed fields a project declares for it | `dataset-create`, `dataset-materialize` | a working copy whose bytes differ from the frozen hashes; a field nobody declared |
| **2. Arms and runs** | a config per arm; per run its outputs, scores, cost, latency and a fingerprint of the system, the instrument and the data | `experiment-run`, `sweep`, `import-run` | a run missing any of the three inputs; an unknown goal |
| **3. Scoring** | scores are arithmetic over stored outputs, so they can be redone | `rescore` ($0), `judge-score` (billed, optional) | an `--out` that is a directory it reads runs from; a judge that is not validated |
| **4. Decisions** | paired tests, rankings, baselines with a reason | `pair-test`, `family-test`, `leaderboard`, `run-promote` | comparing runs on two different `dataset_id`s |
| **5. Goals** | what an evaluation is for and the measure that decides | `goal:` on configs, validate V14 | a config or run naming a goal that does not exist |
| **6. Looking** | the catalog (static pages) and the run inspector (a local server) | `catalog`, `catalog-serve` | item text in the static pages; mixed datasets in one comparison |

Under all of them, `validate` (V1–V15) checks the tree in CI and exits non-zero, and
`self-test` checks the harness itself. The tests that run `evh` install the package from its
real wheel, the GUIDE is run in a fresh project on every change (`guide-check`), and the
catalog and the inspector are driven in headless Chromium (`browser-check`).

### One paired test

Every significance answer comes from one module, `evaluation_harness.stats`: `pair-test`,
`family-test` and the run inspector all call it, so they cannot disagree. A two-sided sign-flip
test, exact over all 2^n sign patterns at 30 items or fewer and a seeded estimate above that,
with Holm's correction over a declared family. The leaderboard's Friedman and Nemenyi test
answers a different question (is there any order at all) and stays separate.

## Re-measuring with an LLM judge

*The short version of [RFC-005](../rfc/RFC-005-judge-scorers.md) ([ADR-0001](../adr/ADR-0001-judge-scorers.md)).*

A run's outputs are the expensive, frozen record; its scores can always be computed again.
That makes three kinds of re-measurement possible on the same outputs:

| kind | what changes | cost |
|---|---|---|
| a new reference | what an output is scored against, e.g. adjudicated gold | $0, `rescore` |
| a new code scorer | the metric, written as code | $0, `rescore` |
| a judge scorer | the metric, delivered by an LLM | billed, `judge-score` |

A judge is a model, so it is treated like an arm: fingerprinted, noisy, able to prefer its own
family. The harness therefore:
- refuses a judge until its scorer names, for each judge, a committed run that measured it
  against human ratings (the validation gate). The gate checks that the validation exists
  and is current, not that it transfers to your outputs;
- runs at least two judges from different vendor families, blind and shuffled;
- measures each judge's position bias and its own noise;
- stores every verdict, so a rerun costs $0, and writes judged runs beside the originals, never
  over them.

A judged score never replaces an experiment's primary metric by itself: that is a recorded
decision.

## Catalog, inspector and goals

*The short version of [RFC-003](../rfc/RFC-003-catalog-adapter.md) ([ADR-0002](../adr/ADR-0002-catalog-inspector-goals.md)); the pages are specified in [UXS-001](../uxs/UXS-001-catalog.md) and [UXS-002](../uxs/UXS-002-inspector.md).*

These came from a project that pins the harness and built them for itself. In 0.4.0 the
generic part moved into the harness; the project keeps one adapter.

- **The catalog** builds static pages over a project's runs, by dataset: every arm with its
  headline number. Counts and means only, never an item's text.
- **The run inspector** is a server, on 127.0.0.1 by default, that tests chosen arms on one
  dataset against a baseline with the same paired test as the CLI, and shows one item's outputs
  beside its reference. It checks the Host header and serves only the catalog and the data
  tree. A public mode adds a host allowlist, a per-client rate, an arm cap and a cache.
- **The adapter** is the only project code either needs. `catalog_adapter.Adapter` lists the
  questions they ask: which arms exist, what each scored per item, which way is better, which
  references exist, what one item looked like. `HarnessAdapter` answers them for the harness's
  own layout, so a project on that layout needs no code at all.
- **Goals** say what an evaluation is for: who uses the output, the decision it informs, the
  measure that decides, the formats it accepts, its datasets. Configs name their goal, runs and
  baselines carry it, validate checks it, and the catalog ranks each goal's arms. A goal is
  optional until a project sets a date from which every new run must name one.

## Item fields and items at a URL

*The short version of [RFC-006](../rfc/RFC-006-item-fields-and-url-items.md) ([ADR-0003](../adr/ADR-0003-item-fields-and-url-items.md)).*

The harness defines no field. A project declares its own in a field set (a name and a type
each), any number of its datasets name it, and each item carries values for those names.
Fields describe an item and are not its identity: a run's fingerprint hashes item ids and
bytes only, so correcting a field invalidates no run, and the dataset's `fields_sha256`
records that it changed. `validate` (V15) refuses an undeclared field and a value of the
wrong type. The catalog summarises a field's values only when it is marked public; the
inspector filters a comparison by a field, and breaks it down by a choice or yes/no field
with one Holm correction over every group, since each group is another chance of a false
"separated".

An item can also live at a URL: it is frozen by its sha256 like any other, fetched once into a
cache, and refused when the bytes there are not the pinned ones.

## This repository's deployment

| address | what | where |
|---|---|---|
| `evals.humancopilot.eu` | the public site: the harness and its findings | prod VPS, nginx |
| `evals.humancopilot.eu/catalog` | the harness deployed on these experiments: catalog, goal pages, run inspector | prod VPS, nginx and the inspector |
| `evals.humancopilot.eu/docs` | these docs | GitHub Pages |

Both sites on the VPS sit behind the box's shared Caddy edge, each container read-only with
every capability dropped, under a content security policy with no inline script or style. A
release is deployed from `main` through a protected environment, health-checked on the box and
rolled back on failure. The runbook is
[`infra/README.md`](https://github.com/chipi/eval-harness/blob/main/infra/README.md).

## Requirements, experience, designs and decisions

New work starts with a PRD, then a UXS when it has a surface, then an RFC; an ADR records the key
decision in a few lines.

- [Product requirements (PRDs)](../prd/index.md): what each capability does for a user, and why.
- [UX specifications (UXS)](../uxs/index.md): the catalog, the inspector, and the command line.
- [Designs (RFCs)](../rfc/index.md): fingerprints, run records, the adapter, rounds, judging, fields.
- [Architecture decisions (ADRs)](../adr/index.md): the key decisions, never edited once
  accepted except to mark them superseded.
