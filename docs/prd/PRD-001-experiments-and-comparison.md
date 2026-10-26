# PRD-001: Running experiments and comparing arms

- **Status**: Implemented (v0.4.0); the core since 0.1.0
- **Authors**: Marko Dragoljevic
- **Related UX spec**: [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the command line and the first evaluation)
- **Related RFCs**: [RFC-001](../rfc/RFC-001-fingerprint-and-code-identity.md) (fingerprint and code identity),
  [RFC-002](../rfc/RFC-002-run-records-and-derived-runs.md) (run records)
- **Related PRDs**: [PRD-002](PRD-002-references.md) (references), [PRD-005](PRD-005-goals-and-rounds.md) (goals and rounds)

## Summary

The harness answers one question honestly: of the systems I tried on my task, is one really
better, or did a small sample hand me a lucky order? A user freezes a dataset, describes each
system under test as an **arm** (one config), runs every arm over the same items, and gets
per-item scores, cost and latency, recorded with a fingerprint of everything the numbers depend
on. Paired tests then say, arm by arm, **separated** or **not separated**, and a baseline is
promoted only with a written reason.

## Background & Context

Model and prompt choices are usually made from one table of averages on a few dozen examples.
Two failures follow: the order in the table is often noise, and the numbers are often not
comparable (another dataset, another reference, another scorer, an edited prompt). The harness
refuses both. A comparison is allowed only between runs on the same `dataset_id`, every run
records what it was measured under, and every claim of "better" goes through a paired test.

The rules and their reasons are in [Concepts](../../harness/docs/CONCEPTS.md); every command in
the [Runbook](../../harness/docs/RUNBOOK.md); the first evaluation, step by step, in the
[GUIDE](../GUIDE.md).

## Goals

- A number always says what it was measured on, against what, by which code, on which machine.
- A comparison either holds (same data, same reference, same scorer) or is refused with the
  reason.
- "Better" is a test result, not an order in a table: exact at 30 items or fewer, corrected for
  how many comparisons were made.
- An arm's own run-to-run noise is measured before any difference is believed.
- Cost and speed sit beside quality in every ranking.
- A baseline is a decision with a reason, not a copy.

## Non-Goals

- Not a model zoo or a prompt store: the user brings the system under test. (From 0.5.0 the
  harness versions the prompt files an arm declares, wherever they live:
  [PRD-009](PRD-009-prompts-and-optimisation.md).)
- Not a dashboard of trends over time; each comparison is between frozen runs.
- No automatic choice of a winner: the harness reports tests, a person promotes. (From 0.5.0 an
  optimisation loop keeps or drops trials by its declared rule while it searches; that is search,
  not a choice of winner, and nothing is promoted automatically:
  [PRD-009](PRD-009-prompts-and-optimisation.md).)
- No comparison across datasets, even "similar" ones; a new version is a new dataset
  ([PRD-006](PRD-006-datasets-versions-fields.md)).

## Personas

- **The engineer choosing a model or prompt** for a feature: needs to know whether the cheaper
  option is measurably worse, on their own data, before shipping it.
- **The researcher publishing a comparison**: needs every number in a report to be re-derivable
  from committed runs, and the significance claims to survive review.
- **The reviewer** of either: needs to see, without rerunning anything, what each number was
  measured under and whether two numbers may be compared.

## User Stories

- _As an engineer, I can cost a run before spending anything (`--dry-run`) so that a sweep never
  surprises me._
- _As an engineer, I can run an arm three times and see its own spread, so that a difference
  smaller than its noise is not mistaken for an improvement._
- _As a researcher, I can test one arm against a declared family of others with Holm's
  correction, so that a "winner" claim accounts for every comparison made._
- _As a reviewer, I can diff two runs fingerprint first, so that I know whether exactly one
  thing changed._
- _As any user, I can promote a run to the baseline only with a reason, so that the next person
  knows why it is the baseline._

## Functional Requirements

### FR1: Frozen inputs

- **FR1.1**: `evh dataset-create` freezes a list of items with the sha256 of each item's bytes;
  `evh dataset-materialize` builds a working copy and fails on any byte that differs.
- **FR1.2**: An arm is a config file holding only `config_id`, `dataset_id`, `params`, and
  optionally `adapter`, `goal`, `format` and `round`; `evh validate` (V1) fails any other key.
- **FR1.3**: A change to an arm is a new `config_id`; a change to a dataset is a new
  `dataset_id`.

### FR2: Runs

- **FR2.1**: `evh experiment-run --config …` runs one arm over the dataset and writes a run
  directory: per-item outputs, per-item scores, the run record (`metrics.json`) and a
  fingerprint (RFC-001).
- **FR2.2**: `--dry-run` prints the calls, tokens and estimated cost and calls nothing.
- **FR2.3**: `--repeat N` runs the arm N times so its own spread can be measured.
- **FR2.4**: The core times every call (`latency_ms`) for an adapter that does not report its
  own, and records billed cost when the provider reports it, else tokens times the config's
  prices.
- **FR2.5**: A cost ceiling (`EVAL_MAX_COST_USD`) stops a run, keeps what it has and prints the
  exact `--resume` command, so nothing is paid for twice.
- **FR2.6**: Outputs that stop at `max_tokens` are named in a warning, by item.
- **FR2.7**: `evh sweep` runs several arms and then the leaderboard; `evh import-run` turns
  per-item scores from another tool into a run the tests can read, with the scoring code hashed
  (`--scorer-file`).

### FR3: Comparison

- **FR3.1**: `evh leaderboard --dataset-id …` ranks every arm on one dataset with quality,
  cost and speed together, and runs a Friedman permutation test with Nemenyi before it lets an
  order be read.
- **FR3.2**: `evh pair-test` tests one pre-named pair; `evh family-test` tests one arm against a
  declared family with Holm's correction. Both use one paired sign-flip test
  (`evaluation_harness.stats`): exact over all 2^n sign patterns at 30 items or fewer, a seeded
  estimate above, and the output says which.
- **FR3.3**: `evh run-compare --baseline … --candidate … [--noise …]` diffs two runs fingerprint
  first, names every field that differs, and reports a delta at or below the stated noise as
  noise.
- **FR3.4**: A metric's direction is decided by one rule everywhere: a flag, else the goal the
  runs name, else the adapter's `METRIC_DIRECTIONS`, else the name (cost, latency and tokens go
  down).
- **FR3.5**: `evh rank-stability`, `evh holdout` and `evh bootstrap-test` answer how many items a
  ranking needs, what holds outside a dev slice, and intervals for corpus-level metrics.
- **FR3.6**: Every refusal (two datasets, another reference, a missing run) is an `ERROR: …`
  line on stderr with exit 1.

### FR4: Decisions

- **FR4.1**: `evh run-promote --run … --reason "…"` makes a run the dataset's baseline; it
  refuses a run from a dirty tree or an unknown build unless told otherwise
  (`--allow-dirty`, `--allow-unknown-build`).
- **FR4.2**: The baseline records the run's reference tier, adapter and fingerprint hash, and
  `evh validate` (V6) fails a baseline that no longer matches its run.
- **FR4.3**: `evh validate` checks the whole data tree (V1–V15) and exits non-zero, so CI can
  hold it.

## Success Criteria

- The GUIDE's walkthrough runs as written in a fresh project on every change (`make guide-check`).
- Every claim in this repository's reports re-derives from the committed runs
  (`harness/tools/check_report_claims.py`, run by `make test`).
- `pair-test`, `family-test` and the inspector give the same p on the same pair up to 30 items,
  where it is exact, because they call the same module. Above 30 it is a seeded estimate:
  `pair-test` and the inspector still agree, while `family-test` draws one random stream for its
  family and can differ in the third decimal, and says which kind of p it printed.

## Related Documents

- [UXS-003](../uxs/UXS-003-cli-and-onboarding.md): the command line and the onboarding path.
- [RFC-001](../rfc/RFC-001-fingerprint-and-code-identity.md), [RFC-002](../rfc/RFC-002-run-records-and-derived-runs.md).
- [Concepts](../../harness/docs/CONCEPTS.md), [Runbook](../../harness/docs/RUNBOOK.md).
