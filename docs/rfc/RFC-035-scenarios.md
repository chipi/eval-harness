# RFC-035: Scenarios: evaluating what takes several steps

- **Status**: Draft, revision 5 (0.9.0, with [RFC-036](RFC-036-agentic-scenarios.md)). Owner, 2026-11-18: "write RFC
  for 4 for 0.9" (multi-turn evaluation, after the comparison with EvalBench); then: no EvalBench importer, ever; "how do
  we keep it small?"; agreed: the names **scenario** and **transcript**, running a scenario outside the harness behind
  an interface; then split in three: this RFC is the base, [RFC-036](RFC-036-agentic-scenarios.md) adds agents (tools,
  stations, the path), [RFC-037](RFC-037-conversational-scenarios.md) adds a user who talks back. Any agent and any
  system can be tested: only a runner knows a particular one.
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-036](RFC-036-agentic-scenarios.md), [RFC-037](RFC-037-conversational-scenarios.md),
  [RFC-034](RFC-034-charts-and-judge-reasons.md) (charts and judge reasons, which scenarios reuse),
  [RFC-032](RFC-032-one-model-two-surfaces.md) (one model, two surfaces), [RFC-019](RFC-019-datasets-from-production.md)
  (datasets from production), [RFC-029](RFC-029-studies-and-test-set-looks.md) (studies and test-set looks),
  [RFC-031](RFC-031-held-out-discipline-and-outcome-labels.md) (held-out discipline)

## Abstract

Today an item is one input, a system answers it in one call, and the answer is scored. Much of what people need to
evaluate does not work in one call: an agent that reads, decides and acts; a chatbot that asks back; a checkout on a
website. A failure can hide in any step, and only the whole sequence shows it.

This RFC adds one idea to the harness: an item can be a **scenario** (an input or a goal, and what success means), and
what a run records for it is a **transcript** (what the system did, the final state, how it ended, the cost and the
time). Everything after the run is the harness as it is: references, scorers, judges with their reasons, repeated runs
and paired tests, rounds, studies, the held-out test, production, charts.

The harness owns the measuring instrument: the scenario, the transcript, the scoring and the decision. It does not run
the systems under test. A **runner**, outside the harness, does, through one small contract: a scenario in, a transcript
out.

## The three RFCs

| RFC | adds | first user |
| --- | --- | --- |
| **035, scenarios** (this one) | the scenario item and the transcript; the runner contract and the `local` stub; the outcome check; trials and the statistics; the transcript view, the sheet; state | any system judged by what it ends with |
| [036, agentic scenarios](RFC-036-agentic-scenarios.md) | actions (tool calls and results), stations and episodes, the path and forbidden paths, per-station scores, recorded tool results, Flotilla's offline path and acceptance | Flotilla: triage, then bugfix, then fix-podcast |
| [037, conversational scenarios](RFC-037-conversational-scenarios.md) | the session runner, the scripted and the simulated user, a person as the user, judges of conversations, real conversations as scenarios | the bugfix chain asking its reporter |

035 and 036 are built together for 0.9.0: Flotilla's first acceptance needs both. 037 waits for its first case. 036 and
037 each sit on this RFC, not on each other.

## Decisions (owner, 2026-11-18)

1. One new item shape and one new output shape in the core; the harness never learns how to drive a browser, a CLI, an
   API or an agent.
2. The names: **scenario** (the item) and **transcript** (what a run records for it). No new word for the whole: it is
   still an eval, of scenarios.
3. Running a scenario is outside the harness, behind a contract; where the systems run is the runner's business. Any
   agent or system can be tested: a runner for it is all it takes.
4. No EvalBench importer.
5. Keep it small: the boundary of [§1](#1-what-the-harness-owns-and-what-it-does-not) and the surfaces of
   [§9](#9-what-it-adds-to-the-surfaces) hold.
6. Split in three (the table above).

## What we learned from EvalBench

EvalBench (GoogleCloudPlatform/evalbench, Apache-2.0) evaluates coding CLIs and data agents this way. From its docs
(read 2026-11-18; `docs/agentic-evals.md`, `docs/configs/agentic-dataset-config.md`, `docs/scorers.md`):

- A scenario has `starting_prompt`, `conversation_plan` (for the simulated user), `expected_trajectory` (ordered tool
  names), `max_turns`, and optionally `success_criteria` (which "the simulated user does not see").
- The simulated user is an LLM following the plan; the conversation ends at `max_turns` or when it says `TERMINATE`.
- Agents run with `HOME` pointed at an isolated directory; trials are reset between runs; "Cloud resources are not
  reset".
- It scores the path (Jaccard of tool names, or edit distance in order), turns, steps, latency, tokens, and LLM-judged
  goal completion and behaviour.
- Its docs describe no significance test, no confidence interval and no calibration of judges against people.

What we take: the scenario's shape (here and in 036, 037), grading the outcome (here), the path (036) and a simulated
user that never sees the success criteria (037), and the cost of the whole sequence rather than of a call. What it does
not have is what the harness is.

## 1. What the harness owns, and what it does not

The space is endless if the harness drives the systems: browsers, CLIs, APIs, agents, MCP, voice, each with its own way
to start, isolate and reset. That is a test framework's or a platform's job. The harness's part is what happens around
the system: the measuring and the deciding.

| the harness owns | the runner owns |
| --- | --- |
| the scenario and its versions (a dataset) | starting the system under test, where it runs |
| the transcript, as recorded | giving the system its input, and its tools |
| scoring, judges, repeats, tests, rounds, decisions | isolating each run (its own home, its own state) |
| the stop rule's limits (`max_turns`, a timeout) | what the system did, the final state, resetting it before the next run |

## 2. The runner contract

```
run(scenario, system) -> transcript                # a command: one scenario (or a file of them) in, a transcript
                                                   # file out; a fresh, isolated run each time
```

That is the shape fleet-eval-data's bugfix driver already has (`driver_fix.py`): a command, no service to keep up. A
system that converses needs a second shape, a session the harness drives turn by turn; that is
[RFC-037](RFC-037-conversational-scenarios.md), and it records the same transcript.

A runner is named like a deployment (RFC-032's deployments, kept apart from the model records): where it is, how it is reached, which systems it can run,
and a check that it answers. The harness ships one runner of its own, `local`: an in-process stub that replays fixed
transcripts, for its own tests and the tutorial, $0 and offline. Every real runner lives outside: a project's own
service, a container, or a platform that already runs agents. The first is the one for Flotilla's agents
([RFC-036](RFC-036-agentic-scenarios.md#5-the-first-runner-flotilla)); a runner for any other agent (a coding CLI, an
MCP server, a model with a tool loop, a project's own service) implements the same contract.

A runner that only executes is thin, replaceable, and cannot change what is measured: the transcript's schema, the
scoring and the decision stay in the harness.

## 3. A scenario

A dataset whose items are scenarios. The base fields:

```yaml
item_id: refund-over-limit
input: {ticket: "Customer asks for a refund of 640 EUR on order 1182"}   # what the runner hands the system
success:
  - The refund is escalated, not issued: 640 EUR is over the 500 EUR limit.
outcome_check: checks/refund_escalated.py   # optional: reads the final state the runner reports
max_turns: 12                               # a limit on the system's model calls (exit_reason turn_cap); a timeout too
env: {LEDGER: refunds_eval}                 # passed to the runner
```

036 adds the expected path and recorded tool results; 037 adds the user's turns or plan. Items are hashed and versioned
as any dataset's. Splits, sealed test sides, exposure and looks apply unchanged: a held-out set of scenarios is opened
once for one candidate. `success` and `outcome_check` are the scenario's reference: a reference set of scenarios holds
them, so a second reference (another person's success criteria) is a second reference set, as it is today.

## 4. A transcript

What a scenario's run records, in the run's rows (RFC-033's model), one row per scenario and trial:

- the scenario, the trial, the system and its version;
- the turns: who (user or system), the text, the time;
- the answer, if the system gives one;
- tokens, cost, latency, turns; how it ended, its `exit_reason` (RFC-036's open set: `completed`, `turn_cap` at
  `max_turns`, `timeout`, `error`; RFC-037 adds `user_done`);
- the final state the runner reported, and the outcome check's verdict on it;
- the cost and its source: a provider's bill or a gateway key's spend before and after (an agent's own count can
  under-report: the fleet measured pi at about half), never a figure without saying which.

036 adds the actions and the stations. The transcript's schema is the harness's (`transcript.schema.json`, versioned);
a runner writes it, and `evh validate` checks it.

A transcript is a new kind of output beside the ones the views already draw (`text`, `insights`, `nodes`, `entities`):
the inspector, the sheet and the Workbench gain one renderer, step by step, two side by side.

## 5. Scoring

| what | question | scorer |
| --- | --- | --- |
| outcome | did the world change as it should? | `outcome_check`: the project's check over the final state the runner reported; pass or fail with its reason |
| answer | does the final answer do the job? | a judge (RFC-034, with its reason) given the success criteria |
| goal | how much of the job got done? | a judge splitting `success` into parts, the share met |
| cost | what the whole run cost | tokens, dollars, latency, turns per scenario |

036 adds the path and per-station scores; 037 adds judges of conversations. Every judge here is a judge scorer as today:
validated against people's labels on transcripts before its numbers count. A person grades transcripts through the sheet
the harness already has: transcripts exported, labelled, imported.

## 6. Trials and statistics

A scenario's run is noisy: the system samples. Each arm runs every scenario `k` times (`--repeat k`; the harness's default is 1, and pass^k needs
`k` of at least 2: 3 is the start this RFC proposes).
The unit of the paired tests is the scenario, its mean over trials (`k` trials of `n` scenarios are not `k·n`
independent items). Reported per arm: the pass rate with its interval, **pass^k** (all `k` trials passed: the
consistency a user feels), cost and latency per scenario; between arms the paired test on scenarios, Holm across arms,
contenders by non-inferiority (ADR-0026). The charts of RFC-034 apply unchanged: `gain-cost` on a study that changes
one skill or prompt is EvalBench's skill ablation, with a significance test.

## 7. State

A system that changes things needs a known start, and only the runner can give it one. A scenario dataset may say its
scenarios change state (`stateful: true`); a runner states whether it resets (each run starts from a fresh state) and
the harness refuses to repeat a stateful scenario on a runner that does not, or runs it once and says so. Two runs of
stateful scenarios on one runner do not run at once (the job lock of RFC-026).

## 8. How it fits the harness's model

| today | with scenarios |
| --- | --- |
| dataset of items | dataset of scenarios: versioned, hashed, split, sealed for the held-out test, unchanged |
| reference set | per scenario: success, the outcome check |
| system / arm | the system under test and its settings, the runner it runs on (in the fingerprint) |
| deployment | a runner: where scenarios run, how it is reached, its check |
| run (outputs) | run of transcripts; repeats are the trials |
| scorers | outcome, cost (deterministic); answer, goal (judges with reasons, validated on labelled transcripts) |
| comparison, goal, rounds, studies, held-out test | unchanged |
| production capture | a production failure becomes a scenario that must pass from then on |
| inspector, sheet, Workbench | a transcript renderer |

## 9. What it adds to the surfaces

Most of the harness never sees the difference: everything after a run reads per-item scores, and a scenario's run gives
per-scenario scores like any run.

| unchanged | goals, rounds, decisions, the tests, studies, the held-out test, jobs, settings, prompts, models, the catalog's lists, every chart |
| --- | --- |
| extended | a dataset's preview (a scenario's fields); a system (its runner); the item views (the transcript renderer); the judge's task (over transcripts); the sheet (a transcript column, a pass/fail column) |
| new | the transcript view; a runner record (as a deployment: make, show, check); scenario authoring (a file per scenario at first, a form later) |

Commands: `runner-new`, `runner-show`, `runner-check`, `transcript-show`; scenario datasets come through
`dataset-create` from a folder of scenario files. The rule that keeps it from doubling: a scenario is an item shape and
a transcript is an output kind, so no screen asks "is this a scenario?" except where it draws one. 036 and 037 extend
the transcript view (actions, stations; the user's turns); they add no screen of their own.

## 10. The build, in order

1. Scenario datasets, the transcript output and its schema; the runner contract and the `local` runner.
2. The outcome check and the cost scorer; the transcript renderer in the inspector and the Workbench.
3. Repeats and the statistics on scenarios (pass rate, pass^k, the paired test on scenarios).
4. Judges over transcripts and their validation on labelled transcripts.

Steps 1 to 3 are built with [RFC-036](RFC-036-agentic-scenarios.md#7-the-build-in-order)'s, in 0.9.0.

## Open questions

1. **Two kinds of turn.** RFC-036 takes Flotilla's names, where a *turn* is one model call inside an episode; RFC-035's
   transcript and RFC-037 also say turn for one step of a conversation (the user's turn, the system's turn), and
   `max_turns` for both a cap on model calls (`turn_cap`) and the length of a conversation. One word cannot mean both.
   Proposed: *turn* stays a model call (as agreed with Flotilla), a conversation's step is a *message* (the user's
   message, the system's reply), and RFC-037's limit is `max_messages`. New names: the owner's decision, not taken
   here; until then each RFC says which it means.

## Not in this RFC

- Driving any particular system (a browser, a CLI, an API, an agent): a runner's work, outside the harness.
- Tools, stations, the path: [RFC-036](RFC-036-agentic-scenarios.md).
- A user who talks back: [RFC-037](RFC-037-conversational-scenarios.md).
- Agents that run for hours (a scenario has a timeout; long work is a runner's).
- Voice and screen agents.
- Importing EvalBench's results (owner, 2026-11-18: never).
