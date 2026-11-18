# RFC-035: Scenarios: evaluating what takes several steps

- **Status**: Draft, revision 4 (0.9.0): the fleet and flotilla sessions' feedback folded in (2026-11-18). Owner, 2026-11-18: "write RFC for 4 for 0.9" (multi-turn evaluation, after
  the comparison with EvalBench); then, on revision 1: no EvalBench importer, ever; the simulated user is any model,
  local or online, as a judge is; "how do we keep it small?"; agreed: the approach below, the names **scenario** and
  **transcript**, running a scenario outside the harness behind an interface.
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-034](RFC-034-charts-and-judge-reasons.md) (charts and judge reasons, which scenarios reuse),
  [RFC-032](RFC-032-one-model-two-surfaces.md) (one model, two surfaces), [RFC-019](RFC-019-datasets-from-production.md)
  (datasets from production), [RFC-029](RFC-029-studies-and-test-set-looks.md) (studies and test-set looks),
  [RFC-031](RFC-031-held-out-discipline-and-outcome-labels.md) (held-out discipline)

## Abstract

Today an item is one input, a system answers it in one call, and the answer is scored. Much of what people need to
evaluate does not work in one call: a chatbot that asks back, a checkout on a website, an agent that lists the tables,
writes SQL, changes a database and then answers. A failure can hide in any step, and only the whole sequence shows it.

This RFC adds one idea to the harness: an item can be a **scenario** (a goal, what success means, and the steps or a
plan for whoever plays the user), and what a run records for it is a **transcript** (every turn, every action with its
result, the final state, the cost and the time). Everything after the run is the harness as it is: references, scorers,
judges with their reasons, repeated runs and paired tests, rounds, studies, the held-out test, production, charts.

The harness owns the measuring instrument: the scenario, the user's side of the conversation, the transcript, the
scoring and the decision. It does not run the systems under test. A **runner**, outside the harness, does: it starts the
system, gives it each user turn, and reports what the system did, through one small interface.

## Decisions (owner, 2026-11-18)

1. The approach below: one new item shape and one new output shape in the core; the harness never learns how to drive a
   browser, a CLI or an API.
2. The names: **scenario** (the item) and **transcript** (what a run records for it). No new word for the whole: it is
   still an eval, of scenarios.
3. The simulated user is any model, local or online, named the way a judge is (a model record or a system, its provider,
   its settings), and part of the run's fingerprint.
4. Running a scenario is outside the harness, behind an interface; where the systems run is the runner's business.
5. No EvalBench importer.
6. **The first users are Flotilla's agents** (owner, 2026-11-18): every Flotilla agent is evaluated with scenarios as
   part of its acceptance. Triage and the others first; the bugfix chain last. The first runner is the one for them,
   beside fleet-eval-data. The fleet session's count: three of Flotilla's routines call a model, triage (`triage/cycle`),
   the bugfix chain (`bugfix/fix`) and `fix-podcast`; the rest call none. So the order is triage, then bugfix, then
   fix-podcast; each takes one input and works alone, so each of their scenarios is one step.
7. Keep it small: the boundary of [§2](#2-what-the-harness-owns-and-what-it-does-not) and the surfaces of
   [§12](#12-what-it-adds-to-the-surfaces) hold.
8. **One shape in two layers** (owner, 2026-11-18, on the flotilla session's proposal): the station **episode** is
   Flotilla's (a versioned JSON schema in its `runtime/`, produced by every harness adapter); the **transcript** is the
   harness's envelope around it and embeds episodes verbatim. Names: *station* (one agent), *episode* (one station's
   run), *turn* (one model call), *action* (one tool call). See [§5](#5-a-transcript).
9. **The offline path** (owner, 2026-11-18): scenarios of Flotilla's agents run outside flotillad, on the version's
   stations and its own command. See [Where systems run](#where-systems-run). The owner asked Flotilla to make the
   episode schema, the offline entry point, the frozen input format and a scenario result in acceptance first-class
   parts of its v2 build.

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

What we take: the scenario's shape, a simulated user that never sees the success criteria, grading the path, the outcome
and the answer, and the cost of the whole sequence rather than of a call. What it does not have is what the harness is.

## 1. Two questions, not one

What "evaluating a flow" means depends on two questions that do not depend on each other.

**Who plays the user?**

| driver | what it is | cost |
| --- | --- | --- |
| **script** | the user's turns are fixed in the scenario: a chat's messages, a website's clicks, an API's calls in order | $0, the same every run |
| **person** | someone runs the scenario by hand and records what happened | a person's time |
| **simulated user** | a model follows the scenario's plan and writes each next turn from what the system just did | a model's calls |

**What is being tested?**

| system | example |
| --- | --- |
| a model, one call | everything the harness evaluates today |
| a system of several steps | a chatbot, a website's checkout, a sequence of API calls |
| an agent | something that chooses its own next steps and tools: a coding CLI with an MCP server, the triage fleet |

EvalBench is one cell (a simulated user, an agent); end-to-end web testing is another (a script, a website). Every cell
is the same thing to the harness: a scenario, a run that produces a transcript, and scores on the transcript.

## 2. What the harness owns, and what it does not

The grid is endless if the harness drives the systems: browsers, CLIs, APIs, MCP, voice, each with its own way to start,
isolate and reset. That is a test framework's job, and others do it well. The harness's part is what happens around the
system: the measuring and the deciding.

| the harness owns | the runner owns |
| --- | --- |
| the scenario and its versions (a dataset) | starting the system under test, where it runs |
| the user's side: the script's next step, or the simulated user's next turn | giving the system each user turn, and its tools |
| the loop: when to stop (the user says it is done, `max_turns`, a timeout) | isolating each run (its own home, its own session) |
| the transcript, as recorded | what the system did: its reply, its actions and their results, its tokens and time |
| scoring, judges, repeats, tests, rounds, decisions | the final state, and resetting it before the next run |

The simulated user stays in the harness because it is part of the instrument: two systems are comparable only under the
same user, so its model and its prompt are the harness's to fix and to fingerprint, as a judge's are.

## 3. The runner interface

A runner has one of two shapes. Most systems an evaluation meets take one input and work alone (every Flotilla agent
does); they need no loop, so the first shape is a batch:

```
run(scenario, system) -> transcript                # a command: one scenario (or a file of them) in, a transcript
                                                   # file out; a fresh, isolated run each time
```

That is the shape fleet-eval-data's bugfix driver already has (`driver_fix.py`): a command, no service to keep up. A
system that converses (a chatbot, the bugfix chain when it asks its reporter a question) needs the user's next turn to
depend on its last reply, so the second shape is a session, and the harness keeps the loop:

```
start(scenario_env, system)  -> session            # a fresh, isolated run of the system under test
step(session, user_turn)     -> system_turn        # what the system did with that turn: its reply, its actions
                                                   # (name, arguments, result, time), tokens, cost, done?
end(session)                 -> final_state        # what the outcome check reads, then the session is gone
```

A batch run is a session with one `step`, so the two shapes record the same transcript. A runner is named like a deployment
(RFC-032's model records): where it is, how it is reached, which systems it can run, and a check that it answers. The
harness ships one runner of its own, `local`: an in-process stub that replays fixed system turns, for its own tests and
the tutorial, $0 and offline. Every real runner lives outside: a project's own service, a container, or a platform that
already runs agents (see [Where systems run](#where-systems-run)).

Why the loop stays in the harness: the user's turn depends on the system's last reply, the stop rule is part of the
measurement, and the transcript is recorded as it happens by the side that scores it. A runner that only executes is
thin, replaceable, and cannot change what is measured.

## 4. A scenario

A dataset whose items are scenarios. Each item:

```yaml
item_id: top-customers-eu
start: Show my top customers
plan: |                         # for a simulated user; or `turns:` for a script (the user's turns, in order)
  You want your top customers in the EU for last quarter. Say "EU" and "last quarter" only when asked.
  If you get a list, ask for just the top 5.
success:                        # never shown to the simulated user
  - The answer lists five customers, all in the EU, ranked by last quarter's revenue.
expected_path: [list_tables, get_schema, execute_sql]
path_order: loose               # loose | strict | none
outcome_check: checks/top5.py   # optional: reads the final state the runner reports
max_turns: 6
env: {DATABASE: orders_eval}    # passed to the runner's start
```

Items are hashed and versioned as any dataset's. Splits, sealed test sides, exposure and looks apply unchanged: a held-out
set of scenarios is opened once for one candidate. `success`, `expected_path` and `outcome_check` are the scenario's
reference: a reference set of scenarios holds them, so a second reference (another person's success criteria) is a
second reference set, as it is today.

## 5. A transcript

What a scenario's run records, in the run's rows (RFC-033's model), one row per scenario and trial:

- the turns: who (user or system), the text, the time;
- the actions: name (`server__tool` for MCP), arguments, result (or its hash when it carries the source's text, as V12
  treats a judge's reply), duration, success;
- tokens, cost, latency, turns, steps; how it ended (the user said done, `max_turns`, a timeout, an error);
- the final state the runner reported, and the outcome check's verdict on it;
- **stations**: a run can be several agents in sequence, each on its own model and harness (the bugfix chain is five:
  verdict, reproducer, fix, review, advisor, with kick-backs between them; Flotilla calls them stations). Every turn and
  action names its station, and each station has its own model, harness, tokens, cost and time;
- the prompt each call received, rendered (Flotilla's texts are templates, recorded per call), and the system's version
  and spec hash;
- the cost and its source: a provider's bill or a gateway key's spend before and after (an agent's own count can
  under-report: the fleet measured pi at about half), never a figure without saying which.

One shape, not a mapping, in two layers with one owner each:

- **The episode** (one station's run) is Flotilla's: a versioned JSON schema in its `runtime/`, which every harness
  adapter produces and both repositories test against. It carries the station's name and sequence, the version and spec
  hash, its turns (one model call each: model, text, tokens including cache and reasoning, time, latency, the rendered
  prompt or its hash and a pointer), its actions (one tool call each: name, arguments and result whole or hashed,
  duration, success), its answer, `exit_reason`, `session_id`, `notes` (prompt changes a harness forced, part of what
  was measured), the cost with `cost_source`, and `raw_path` (the native stream, for audit).
- **The transcript** is the harness's envelope: the scenario, the trial, the user's turns, `stations: [episode, …]` in
  run order (kick-backs included), the final state, the outcome check's verdict, and how it ended (mapped from the
  episodes' `exit_reason`). Episodes are embedded verbatim, never converted.

Arguments and results are kept whole only after Flotilla's redaction (credentials masked), and above a size cap (set in
the schema) as a hash and a length, so a record cannot balloon or carry raw source text. The schema comes with v2's
build step 4 (the harness layer in `runtime/`), validated against every adapter in the same commit.

A transcript is a new kind of output beside the ones the views already draw (`text`, `insights`, `nodes`, `entities`):
the inspector, the sheet and the Workbench gain one renderer, turn by turn, two side by side.

## 6. The drivers, in order

0. **None**: a one-step scenario, an agent given its input and left to work, needs no driver. All of Flotilla's agents
   are this, so their scenarios need neither of the two below; neither gates them.
1. **Script** first: the scenario's `turns:` are sent in order. Deterministic, $0 on the harness's side, and it proves
   the whole shape (scenario datasets, the runner interface, transcripts, scorers, repeats, tests, views) before any model
   plays a user.
2. **Simulated user** second: a model named as a judge is (any provider, local or online), given the plan and the
   transcript so far, never the success criteria, writes the next turn or says it is done. Its model, settings and prompt
   are part of the run's fingerprint; a run under another simulated user is another measurement.

## 7. The person, and the path between manual and automated

A person fits in two places, both through the sheet the harness already has:

- **A person as the driver**: the scenarios exported as a sheet; someone runs each by hand against the system and fills
  in what happened and whether it worked; the sheet comes back as a run (`sheet-import`).
- **A person as the grader**: transcripts exported as a sheet and labelled; that is how a judge of transcripts is
  validated against people (RFC-034's reasons included).

The path from manual to automated reuses one scenario at every step: a person runs it (a manual run); a person's session
is recorded once and becomes the scenario's `turns:` (a script); the script runs every time (the scripted driver); a
simulated user varies it (the plan).

## 8. Scoring the whole run

| what | question | scorer |
| --- | --- | --- |
| path | did the system take a valid path? | `path_match`: the expected actions against the actions taken, as a set (loose) or in order (strict); a forbidden action (a write before any read) fails it |
| outcome | did the world change as it should? | `outcome_check`: the project's check over the final state the runner reported; pass or fail with its reason |
| answer | does the final answer do the job? | a judge (RFC-034, with its reason) given the success criteria and, when asked, the actions |
| goal | how much of the job got done? | a judge splitting `success` into parts, the share met |
| behaviour | invented facts, needless questions | a judge, counted per scenario |
| cost | what the whole run cost | tokens, dollars, latency, turns, steps per scenario |

Each row can be scored per station as well as for the whole: did the reproducer's test fail on the base, did the review
approve a wrong fix. For a chain, a station's score often says more than the whole run's. Every judge here is a judge
scorer as today: validated against people's labels on transcripts before its numbers count.

## 9. Trials and statistics

A scenario's run is noisy: the system and the simulated user both sample. Each arm runs every scenario `k` times (default
3, as arms repeat now). The unit of the paired tests is the scenario, its mean over trials (`k` trials of `n` scenarios
are not `k·n` independent items). Reported per arm: the pass rate with its interval, **pass^k** (all `k` trials passed:
the consistency a user feels), cost and latency per scenario; between arms the paired test on scenarios, Holm across
arms, contenders by non-inferiority (ADR-0026). The charts of RFC-034 apply unchanged: `gain-cost` on a study that
changes one skill or prompt is EvalBench's skill ablation, with a significance test.

## 10. State

A system that changes things needs a known start, and only the runner can give it one. A scenario dataset may say its
scenarios change state (`stateful: true`); a runner states whether it resets (`start` gives a fresh state) and the
harness refuses to repeat a stateful scenario on a runner that does not, or runs it once and says so. Two runs of
stateful scenarios on one runner do not run at once (the job lock of RFC-026).

## 11. How it fits the harness's model

| today | with scenarios |
| --- | --- |
| dataset of items | dataset of scenarios: versioned, hashed, split, sealed for the held-out test, unchanged |
| reference set | per scenario: success, the expected path, the outcome check |
| system / arm | the system under test and its settings, the runner it runs on, the driver, the simulated user's model (all in the fingerprint) |
| deployment | a runner: where scenarios run, how it is reached, its check |
| run (outputs) | run of transcripts; repeats are the trials |
| scorers | path, outcome, cost (deterministic); answer, goal, behaviour (judges with reasons, validated on labelled transcripts) |
| comparison, goal, rounds, studies, held-out test | unchanged |
| production capture | real conversations become scenarios; a production failure becomes a scenario that must pass from then on |
| inspector, sheet, Workbench | a transcript renderer: turn by turn, two side by side |

## 12. What it adds to the surfaces

Most of the harness never sees the difference: everything after a run reads per-item scores, and a scenario's run gives
per-scenario scores like any run.

| unchanged | goals, rounds, decisions, the tests, studies, the held-out test, jobs, settings, prompts, models, the catalog's lists, every chart |
| --- | --- |
| extended | a dataset's preview (a scenario's fields); a system (its runner, its driver, its simulated user); the item views (the transcript renderer); the judge's task (over transcripts); the sheet (a transcript column, a pass/fail column) |
| new | the transcript view; a runner record (as a deployment: make, show, check); scenario authoring (a file per scenario at first, a form later) |

Commands: `runner-new`, `runner-show`, `runner-check`, `transcript-show`; scenario datasets come through
`dataset-create` from a folder of scenario files. The rule that keeps it from doubling: a scenario is an item shape and
a transcript is an output kind, so no screen asks "is this a scenario?" except where it draws one.

## 13. Scenarios from production

A capture of real conversations (RFC-019) becomes scenarios: the first message as `start`, a plan written by a person
(or proposed by a model, accepted by a person) from what the user went on to say, `success` from the outcome production
recorded. A production failure becomes a scenario that must pass from then on.

For Flotilla this needs no new machinery: its v2 design freezes exactly what a live run was handed (the case, the
commit, the ledger's mark) and exports live and shadow results as pairs keyed by that frozen input. A frozen input is a
scenario's `start`; a pair's sides are transcripts.

## 14. The build, in order

1. Scenario datasets and the transcript output (with stations); the batch runner contract and the `local` runner.
2. The deterministic scorers (path, outcome, cost), whole and per station, and the transcript renderer in the inspector
   and the Workbench.
3. Repeats and the statistics on scenarios (pass rate, pass^k, the paired test on scenarios).
4. Triage: its scenarios and its batch runner beside fleet-eval-data, the first acceptance.
5. The bugfix chain, then fix-podcast, on the batch runner fleet-eval-data's driver already is.
6. The session runner, the script and the simulated user, when a system that converses needs them (the first: the
   bugfix chain's question to its reporter).
7. Judges on transcripts and their validation on labelled transcripts; scenarios from production.

## Where systems run

Asked (owner, 2026-11-18): can Flotilla, the owner's platform for running agentic workflows, be where scenarios run?
Read 2026-11-18 at flotilla `main` 0ed0d28: not as it is, and not by its own rule.

- **Its rule**: "Evaluation in any form lives outside flotilla" (flotilla `docs/rfc/RFC-0002-job-runtime.md` item 9, the
  boundary agreed with this project); interactive chat is out of its scope (`docs/wip/positioning.md`).
- **What it lacks for a runner**: a run takes no input (`POST /v1/routines/{fleet}/{routine}/run` starts a declared
  routine, `internal/api/api.go`); no turns from outside a run; isolation is per worker role and a scratch directory, not
  per scenario, with no reset; its run records keep tool calls' arguments cut short and not their results, and the
  specified export (`flotilla records export`) is not built.
- **What it already has that fits**: its bugfix chain drives a coding agent through a harness adapter that normalizes
  each session into an episode of turns, tools, usage and answer (flotilla `bugfix/HARNESS_SEAMS.md`, ADR-0020): close to
  a transcript. And the pattern that already exists for evaluating its code runs outside both projects: fleet-eval-data's
  bugfix driver runs a routine's entry point in a container built from Flotilla's worker image, with Flotilla mounted read
  only (fleet-eval-data `projects/bugfix-eval/PLAN.md`).

So the synergy runs the other way: Flotilla's agents are systems under test, and a runner for them lives beside the
evaluation data (fleet-eval-data), as that driver does; Flotilla contributes what its own plans already hold. Neither
the harness nor Flotilla takes on running scenarios.

**Flotilla's v2 design changes the "not as it is"** (flotilla `docs/wip/v2-design.md`, the operator's decision of
2026-11-18; designed, not built). Every routine gets versions; a new version runs in shadow beside the live one with no
effect, over the same frozen input; live and shadow results are exported as pairs. "Evals have the same guarantees": an
eval runs through flotillad as a shadow run on a given input, or offline with `flotillad -stations` and the shadow
worker's read-only environment; either way no write credential is reachable.

Scenarios take the **offline path** (the flotilla session's recommendation, the owner's decision): the runner beside
fleet-eval-data takes the version's stations from `flotillad -stations <version> -models <config>`, runs the version's
own `run:` command in a fresh container from the worker image with the read-only environment, the scenario's input as
the run's input and a fresh state folder per scenario, and wraps the episodes the run writes in a transcript. That
gives isolation and reset per scenario, many trials, no load on the live platform, and exactly the version that would go
live. Through flotillad does not fit: v2's shadows start from live inputs and are paired with them, and feeding them
scenarios would put evaluation inside Flotilla.

**What v2 builds for it** (the flotilla session, 2026-11-18, on the owner's request that these be first-class; build
steps are v2's):

| piece | v2 step | what it is |
| --- | --- | --- |
| episode schema | 4 | `runtime/episode.schema.json`, every adapter validated against it |
| offline entry point | 3, its test in 5 | a tested contract (`flotillad -run-offline`, flags settled at build): a version folder, models, an input envelope, a fresh state folder, an output folder; the version's own `run:` in the worker image, read-only; episodes, the calls file and decision records in the output folder; the e2e asserts nothing outside it changed. The harness's runner starts it; Flotilla provides and tests it |
| frozen input | 2 | `runtime/input.schema.json`: the handed input, the ledger mark, the case keys, the commit, the routine and version. A captured input exports as the envelope, the ledger slice as of the mark, and a state snapshot together, so a scenario sees what the live run saw |
| acceptance | 1 | promote gains evidence: an eval-harness run id and its verdict line beside the pairs and the replay gates; a routine declares `acceptance: [pairs, replay, scenario_eval]` and promote refuses without it unless the operator gives a reason. Flotilla stores the verdict; it does not judge the eval |

A captured live input carries production data: making it a scenario is a copy and a scrub, and it lands in the
installation's private data (fleet-eval-data), never a public repository.

**Where scenarios sit in Flotilla's acceptance** (the installation's bars, flotilla-fleets
`docs/fleets-v2-requirements.md`, draft; the fleet session's summary): a new version is accepted by the operator after
replay gates, a model replay (triage: k>=3, false dismissals and silent drops no worse than live; bugfix: approved plans
that fail the oracle = 0 and approved plans and oracle passes at least live's, cost from the gateway key) and a shadow
comparison of at least seven days. Scenarios are the eval part of those bars; the shadow pairs stay Flotilla's.

## Open questions

1. Decided (owner, 2026-11-18): the first runner is the one for Flotilla's agents, beside fleet-eval-data; the first
   scenario sets are theirs, triage first, bugfix last.
2. Answered by the fleet session (2026-11-18), folded in above: three model-calling agents, one step each; triage's
   scenario is a signal with its six probes' frozen results and a ledger fixture, one step, its decision as the final
   state (success: the reference decision; forbidden: cleanup or dismiss without the evidence probe), much of which
   exists already as items with frozen tool results, so what scenarios add is path scoring and the outcome check on
   what it would file; the batch runner; stations, rendered prompts and the cost's source in the transcript; no
   simulated user or person driver needed for Flotilla now.
3. Answered by the flotilla session (2026-11-18) and decided by the owner: one shape in two layers, the offline path.
   Asked of it next (owner, 2026-11-18): the episode schema, the offline entry point as a tested contract, the frozen
   input format usable as a scenario's start, and a scenario result in a version's acceptance, as parts of v2's build;
   the schema's commit to reference here. Answered: all four fit v2 (the table above); the commits follow as v2's
   steps land.

## Not in this RFC

- Driving any particular system (a browser, a CLI, an API): a runner's work, outside the harness.
- Agents that run for hours (a scenario has a timeout; long work is a runner's).
- Voice and screen agents.
- Importing EvalBench's results (owner, 2026-11-18: never).
