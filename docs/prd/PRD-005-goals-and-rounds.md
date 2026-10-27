# PRD-005: Goals, and experiment rounds

- **Status**: Implemented (v0.4.0)
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (the goal page), [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the round commands)
- **Related RFC**: [RFC-004](../rfc/RFC-004-experiment-rounds.md) (rounds: files, commands, the evidence)
- **Related ADRs**: [ADR-0002](../adr/ADR-0002-catalog-inspector-goals.md) (goals first-class), [ADR-0004](../adr/ADR-0004-experiment-rounds.md) (rounds), [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md) (axes and strategies)
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md), [PRD-004](PRD-004-catalog-and-inspector.md)

## Summary

A **goal** says what an evaluation is for: who uses the output, the decision it informs, the
measure that decides and which way is better, the output formats it accepts, and the datasets
it is measured on. Configs name their goal, runs and baselines carry it, `validate` checks it,
and the catalog gives each goal a page that leads with its answer so far. On top of goals,
**rounds** are optional: a round records what it sets out to learn, what changed, which arms it
carries in, drops (with the reason) or adds, and what it concluded. `evh rounds` reads the
evidence and suggests the next decision as the command that makes it. A project that never
opens a round sees none of it.

## Background & Context

Without goals, a run is a number with no question attached: nothing says which measure decides,
so the same table can be read to support any choice. Without rounds, experiments still go round
on round (try some arms, keep what won, drop what lost, change something, compare again), but
the harness recorded none of it: runs were a flat set per dataset, and nothing said which arms
belonged together, why one was dropped, or what a round concluded. The newcomer scenario
([SCENARIO](../../harness/docs/SCENARIO.md)) made that gap concrete.

## Goals

- Every evaluation can say what it is for, and its measure decides the direction of "better"
  for every command.
- A goal's page answers first: the promoted baseline and why, or that nothing is decided yet and
  the command that decides it.
- Arms are ranked only against arms scored against the same thing.
- A sequence of experiments has a record: hypothesis, changes, retirements with reasons,
  conclusion.
- The next decision is suggested from the evidence, but made by a person, by command.

## Non-Goals

- Goals are not required until a project opts in (`required_from`).
- Rounds are not required at all.
- No rounds across goals; a round answers one goal on one dataset.
- No automatic retirement or promotion: suggestions only. (From 0.5.0, inside an optimisation
  loop, trials are kept or dropped by the loop's declared rule; promotion stays a person's, or an
  agent's after asking: [PRD-009](PRD-009-prompts-and-optimisation.md),
  [PRD-012](PRD-012-agent-ready.md).)
- The catalog never writes a round; there is no "retire" button.

## Personas

- **The engineer iterating on a prompt or model choice** over several rounds.
- **The team lead** who wants to know, per goal, what was decided and why.
- **The newcomer** who should be able to ignore goals and rounds and still use the harness.

## User Stories

- _As a team lead, I can open a goal and read the answer first: the baseline promoted for it on
  each dataset and the reason._
- _As an engineer, I can open a round with a hypothesis, carry in the arms worth keeping and drop
  the rest with a reason (`evh round-open --goal … --dataset … --keep … --retire … --reason "…"`)._
- _As an engineer, I can ask what the evidence suggests (`evh rounds --goal …`) and get each
  suggestion as the command that acts on it._
- _As an engineer, I can close a round with its conclusion and promote the run it chose in one
  step (`evh round-close … --conclusion "…" --promote <run_id>`)._
- _As a newcomer, I can ignore rounds entirely and nothing changes._

## Functional Requirements

### FR1: Goals

- **FR1.1**: A goal is `data/goals/<goal_id>.yaml`, validated by `schemas/goal.schema.json`.
  Required: `goal_id`, `title`, `statement`, `decision`, `success_criteria` (the primary measure
  and its direction: `higher`, `lower`, or `non_inferior`, a guard that ranks nothing) and
  `datasets` (each with an optional role: dev, heldout, ...; empty for a goal checked by a gate
  rather than measured on a dataset). Optional: `context` (its audience), `output_contract`,
  `references`, `measures`, `min_items` (in `success_criteria`), `links` (shown on the goal
  page and by `evh goals --goal`: a web address as a link, a project path as text), `status`.
- **FR1.2**: A config names its goal (`goal:`) and may declare its `format`; `experiment-run`
  refuses an unknown goal before it spends anything. The run records both outside the
  fingerprint; `run-promote` carries both onto the baseline.
- **FR1.3**: `evh validate` V14 fails a goal that breaks its schema or whose `goal_id` is not its
  file name, a config, run or baseline naming a goal that does not exist or a format the goal
  does not accept, and a goal whose direction contradicts its runs; a dataset smaller than
  `min_items` gets a note.
- **FR1.4**: `required_from: YYYY-MM-DD` in `data/goals/policy.yaml` makes every run created
  from that date name a goal. Without it, nothing is required.
- **FR1.5**: The goal page and `evh goals --goal …` give: the answer so far per dataset; the
  rounds, when there are any; what the goal is for; and on each dataset its references and its
  arms grouped by what they are scored against (gold, silver, a judge), ranked within a group.
  An arm with fewer items than `min_items`, a format the goal does not accept, or that wrote the
  reference it is scored against is flagged and never a group's leader.
- **FR1.6**: A goal weighs cost, quality and speed (cost and speed built in, with no
  configuration) and may add its own per-item metrics as axes, each with an optional limit. Arms
  over a limit, flagged arms and retired arms are never recommended. The goal's strategy
  (`balanced` by default, `quality_first`, `frugal`) decides who is tied with the quality leader;
  its tie-break (default cost, then speed) picks among them. Cost is shown in dollars and tokens
  per item; speed as p50 and p95. The goal page names the recommended arm per group with the
  reasons, and the home page's glance shows it with its cost and speed against the baseline;
  the CLI says the same. Guardrails (rules in words) are shown, never computed.

- **Amended in 0.5.0** ([PRD-013](PRD-013-identity-and-ties.md) FR3, FR8): `non_inferior` and the goal's
  tie-breaks use a one-sided non-inferiority test against a margin the goal declares; baselines
  become per goal and dataset.

### FR2: Rounds (optional)

- **FR2.1**: A round is `data/rounds/<goal_id>/<round_id>.yaml` (`r1`, `r2`, ...), validated by
  `schemas/round.schema.json`: goal, dataset, `from`, hypothesis, changes, the baseline it
  started from, arms carried in, arms retired with reason and date, an optional budget, status
  and conclusion.
- **FR2.2**: `evh round-open --goal G --dataset D` opens the next round; it refuses while
  another round of the goal is open. `--from rN`, `--hypothesis`, `--change` (repeatable),
  `--keep` (carried in, not run again), `--retire … --reason "…"`, `--budget-usd`.
- **FR2.3**: An arm joins a round by naming it in its config (`round: rN`, beside `goal:`);
  `experiment-run` refuses a config naming a round that does not exist, is closed, or is on
  another dataset.
- **FR2.4**: `evh rounds --goal G [--round rN]` shows each round and, for the open one, the
  arms against its leader, its leader against the previous round's best, the baseline it started
  from and the arm that wrote a silver reference of the dataset, its spend against the budget and
  the cost per item, all read against the reference most of its arms use (gold before silver on
  a tie; arms scored against another are named, not compared), and suggestions (never to retire
  the arm that wrote the silver reference): retire an arm separated as worse
  (`evh round-retire …`), more items where arms tie with the leader (`evh rank-stability …`), change course when the round's best
  is not separated from the previous round's, and close (`evh round-close …`).
- **FR2.5**: `evh round-retire --goal G --round rN --arm C --reason "…"` and
  `evh round-close --goal G --round rN --conclusion "…" [--promote RUN_ID]` record decisions;
  a reason or conclusion must be a sentence. If the promotion is refused, the round stays open.
- **FR2.6**: `evh leaderboard`, `evh family-test`, `evh pair-test` and `evh inspect` take
  `--round` to scope to a round's arms in play; `inspect --round` and `pair-test --round` default
  to the goal's measure and the round's leader (`pair-test`'s B: the baseline the round started
  from).
- **FR2.7**: `evh validate` (V14) checks round records: schema, file name, goal and dataset
  resolve, `from` exists, a closed round has a conclusion, every run naming a round names one
  that exists.

- **Amended in 0.5.0** ([PRD-013](PRD-013-identity-and-ties.md) FR3.5, FR9): round suggestions about
  arms "tied with the leader" use non-inferiority, and a round summary on a heldout dataset shows
  nominal results, labelled as not a look (only a recorded decision is one).

## Success Criteria

- `harness/tests/test_rounds.py` passes: open, run, suggest, retire, close, the next round,
  validate, the page.
- A project with no rounds produces the same pages and tables as before rounds existed, apart
  from paging and the goal page's order.

## Related Documents

- [RFC-004](../rfc/RFC-004-experiment-rounds.md), [ADR-0004](../adr/ADR-0004-experiment-rounds.md).
- [UXS-001: the goal page](../uxs/UXS-001-catalog.md#the-goal-page).
