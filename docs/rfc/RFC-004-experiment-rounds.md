# RFC-004: Experiment rounds

- **Status**: Completed (0.4.0, unreleased)
- **Authors**: Marko Dragoljevic
- **Related PRD**: [PRD-005](../prd/PRD-005-goals-and-rounds.md)
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md#the-goal-page) (the rounds block),
  [UXS-003](../uxs/UXS-003-cli-and-onboarding.md#the-round-flow) (the commands)
- **Related ADR**: [ADR-0004](../adr/ADR-0004-experiment-rounds.md)
- **Code**: `harness/scripts/_rounds.py` (records, membership, checks), `rounds.py` (the
  commands and the evidence), `round_open.py`, `round_retire.py`, `round_close.py`,
  `round_status.py` (entry points), `harness/schemas/round.schema.json`; test
  `harness/tests/test_rounds.py`

## Abstract

A round is a small YAML record beside a goal: what it set out to learn, what changed, which arms
it carries in or drops and why, the baseline it started from, and what it concluded. Arms are not
listed in it: an arm is in a round when its config names the round, and its runs record it. Four
commands write and read the records; the evidence for the open round is computed with the same
comparison the inspector runs, and each suggestion is printed as the command that acts on it.
Nothing in the catalog writes.

## Problem Statement

The newcomer trial ([SCENARIO](../../harness/docs/SCENARIO.md)) ran two experiments in one round
each; the natural next step, a second round dropping the CPU arms and tuning the cheap hosted
model against the frontier's silver, had nowhere to be recorded. Runs were a flat set per
dataset; config versions and `--match` only scoped a table; a baseline was one run per dataset.
The owner asked for "a little experiment workflow that guides us, where we make decisions and see
how things are going", comparing round against round, not only against the reference.

## Design

### The record

`data/rounds/<goal_id>/<round_id>.yaml`, written only by the commands, keys in a stable order so a
diff shows what a command changed:

| field | holds |
| --- | --- |
| `round_id` | `r1`, `r2`, ... (the file name); the next id is one more than the goal's highest |
| `goal`, `dataset_id` | the goal it answers (the folder) and the dataset its arms run on |
| `from` | the round it continues |
| `hypothesis`, `changes` | what it sets out to learn; what changed, one line each |
| `baseline` | the run the dataset's promoted baseline came from when the round opened, or null |
| `carried` | config ids from earlier rounds kept unchanged, compared without being run again |
| `retired` | `{config_id, reason, at}` each |
| `budget_usd` | optional; the round's billed cost is shown against it |
| `status`, `opened_at`, `closed_at` | `open` or `closed` |
| `conclusion` | `{text, promoted_run}` |

### Membership

`arms_of(round)` = the configs whose runs on the round's dataset record `round: rN` and the
round's goal, plus `carried`, minus `retired`. A config's `round:` needs `goal:` beside it.
`experiment-run` checks it before spending anything (`config_round`): the round must exist, be
open and be on the config's dataset.

### Commands

- `evh round-open --goal G --dataset D [--from rN] [--hypothesis …] [--change …]… [--keep a,b]
  [--retire c --reason "…"] [--budget-usd N]`: refuses an unknown goal or dataset, a second open
  round of the goal, a `--from` that does not exist, and `--retire` without a reason of three
  words or more.
- `evh round-retire --goal G --round rN --arm C --reason "…"`: refuses a closed round, a reason
  under three words, an arm not in play.
- `evh round-close --goal G --round rN --conclusion "…" [--promote RUN_ID]`: refuses a closed
  round and a conclusion under three words; `--promote` runs `run-promote` with the conclusion
  as the reason, and a refused promotion leaves the round open.
- `evh rounds --goal G [--round rN]`: every round, then one (the open one, else the last) in
  full with its evidence and suggestions.
- `--round` (with `--goal` when several goals have that round) on `evh leaderboard`,
  `evh family-test` (opponents in play), `evh pair-test` and `evh inspect` scopes to the arms in
  play. `evh inspect --round` reads the goal's measure against the round's leader (`--metric`,
  `--baseline` override) and names the arms with no score on it, leaving them out.
  `evh pair-test --round` defaults A to the round's leader, B to the baseline it started from and
  the metric to the goal's measure, and refuses an arm not in play.

### The evidence (`rounds.evidence`)

For the open round, reading the goal's primary measure and direction, against one reference: the
one most of its arms are scored against (gold before silver on a tie). Arms scored against
another are named and not compared ("NOTE: read against <ref>; not compared: <arm> (scored against
<ref>) — run them again to score them against it"), and `compare`'s own warnings are carried into
the notes.

1. **The leader**: the best mean among the arms in play.
2. **The arms against the leader**: `catalog_serve.compare` with the leader as baseline, the
   same call the inspector makes; its conditions warnings are carried into the notes.
3. **Against the previous round**: its best against `from`'s best, on the same dataset.
4. **Against the baseline it started from**, when there was one.
5. **Against the arm that wrote a silver reference** of the dataset ("against the arm that wrote
   silver/<id> (<arm>)"), scored on the same references as the round: how close the leader
   comes to the arm whose outputs became the reference. That arm is a yardstick, not a contender:
   no suggestion retires it.
6. **The spend** against `budget_usd` ("spent $x of $y", "over budget"), and the **cost per
   item** of the leader and of each arm it is compared against, where they record a cost.

Suggestions, each a sentence and a command:

| when | suggestion | command |
| --- | --- | --- |
| an arm is `separated: worse` than the leader after Holm, and did not write a silver reference | retire it, with the test as the reason | `evh round-retire … --reason "separated worse than <leader> on <measure> after Holm (p …)"` |
| arms are `not separated` from the leader | more items would separate them | `evh rank-stability --dataset-id D` |
| the round's best is not separated better than the previous round's | change course, or close | (none) |
| always | close the round with what it showed | `evh round-close … --conclusion "..." --promote <leader's run>` |

### Pages

The goal page shows the rounds newest first, and, for the open round, the suggestions with their
commands, each with a copy button ([UXS-001](../uxs/UXS-001-catalog.md#the-goal-page)).
Suggestions are computed only when the catalog is built with `HarnessAdapter` over the project's
data. Each round with a leader and two or more arms has an **inspect** button that opens the
inspector on its arms against its leader, on the goal's measure (`evh inspect --round`). Arms
retired in a round carry a "retired in rN" label in the goal's tables, and their rows are greyed
out.

### Validation

`evh validate` V14 reports rounds: a record that does not parse or breaks the schema, a
`round_id` or goal that is not its file name and folder, a goal or dataset that does not exist, a
`from` that does not exist, a closed round with no conclusion, and a run naming a round that does
not exist.

## Proposed in ADR-0004, not built in 0.4.0

The proposal (2026-10-24) went further than the first build; most of it is now in 0.4.0:
`pair-test --round`, the leader against the arm that wrote the silver reference, the cost per
item, retired arms greyed out on the goal page, a copy button on each suggested command, and a
way into the inspector for a round. Not in 0.4.0:

- a round picker inside the web inspector (`round=`). The way in is the goal page's **inspect**
  button on each round, which opens the inspector on that round's arms; the terminal has
  `evh inspect --round`;
- a progress line per round in the rounds overview (the cost per item is printed only with the
  open round's evidence, by `evh rounds` and on the goal page).

## Alternatives Considered

- **The local inspector writes decisions** (a retire button). Set aside: it ends "the server
  never writes", which the public deployment depends on.
- **Rounds required.** Simpler, but it taxes a quick experiment; the owner chose optional.
- **Rounds as a naming convention** (`_r2` in config ids) or git tags: no place for a hypothesis,
  a reason or a conclusion, and nothing to validate.
- **Rounds per dataset rather than per goal.** A round's conclusion answers a goal's decision;
  the dataset is a field of the round.
- **Listing arms in the record.** Rejected: membership is what the runs record, so a record cannot
  claim an arm that never ran in the round.

## Testing

`harness/tests/test_rounds.py`, in a throwaway project built from the tutorial ($0, offline): a
round opened carrying two arms, a third running in it, the suggestion to retire the arm the test
separates as worse, the retirement and the close with promotion, a closed round refusing new runs,
the next round continuing it, validate checking the records, the leaderboard scoped to a round,
and the goal page showing the rounds.
