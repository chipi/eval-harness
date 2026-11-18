# RFC-035: Agent journeys: multi-turn evaluation with a simulated user

- **Status**: Draft (0.9.0). Owner, 2026-11-18: "write RFC for 4 for 0.9", item 4 of the comparison with EvalBench
  (multi-turn journeys, a simulated user, scoring the path and the outcome).
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-034](RFC-034-charts-and-judge-reasons.md) (charts and judge reasons, which journeys reuse),
  [RFC-032](RFC-032-one-model-two-surfaces.md) (one model, two surfaces), [RFC-019](RFC-019-datasets-from-production.md)
  (datasets from production), [RFC-029](RFC-029-studies-and-test-set-looks.md) (studies and test-set looks),
  [RFC-031](RFC-031-held-out-discipline-and-outcome-labels.md) (held-out discipline)

## Abstract

Today a run sends one input per item and scores one output. An agent is not used that way: a person brings a goal,
the agent asks, calls tools, changes things, and answers over several turns. What matters is whether the person's
job got done, how, and at what cost; a regression can hide in a tool, a skill, a prompt or the model, and only a
whole journey shows it.

This RFC adds **journeys**: a dataset kind whose items are scenarios (a goal, a plan for a simulated user, what
success means), a runner that drives an agent through them, a recorded **trajectory** per item, and scorers for the
path, the outcome and the answer. Everything after the run is the harness as it is: repeated runs, paired tests,
rounds, studies, the held-out test, judges with reasons, the charts.

## What we learned from EvalBench

EvalBench (GoogleCloudPlatform/evalbench, Apache-2.0) does this for coding CLIs and data agents. From its docs (read
2026-11-18; `docs/agentic-evals.md`, `docs/configs/agentic-dataset-config.md`, `docs/scorers.md`):

- A scenario has `starting_prompt`, `conversation_plan` (for the simulated user), `expected_trajectory` (ordered
  tool names), `max_turns`, and optionally `success_criteria` (which "the simulated user does not see"),
  `binary_rubric`, `expected_skills`, `env`, `work_dir`, `num_trials`.
- The simulated user is an LLM following the plan; the conversation ends at `max_turns` or when it says
  `TERMINATE`.
- Agents run with `HOME` pointed at an isolated directory; MCP servers, plugins and skills are installed there by
  each CLI's own mechanism; a fake MCP server returns fixed replies for offline tests.
- Scorers: `trajectory_matcher` (Jaccard of tool names, or Levenshtein with order), turns, steps, latency, tokens
  (fresh, processed, price-weighted), and LLM-judged goal completion, behaviour (hallucinations, unnecessary
  clarifications), parameter feedback and binary rubrics; judges can be given the tool-call record.
- Trials of a scenario run in the same sandbox, reset between trials; "Cloud resources are not reset".
- Its docs describe no significance test, no confidence interval and no calibration of judges against people.

What we take: the scenario's shape, the simulated user that never sees the success criteria, the three things
graded (path, outcome, answer), the sandbox, the fake tool server, and the cost of a journey rather than a call.
What we add is what the harness already is: paired tests over trials, judges validated against people and showing
their reasons, decisions kept with their evidence, a held-out set of journeys, and journeys from production.

## 1. A journey dataset

A dataset with `kind: journey`. Each item is a scenario:

```yaml
item_id: top-customers-eu
starting_prompt: Show my top customers
plan: |
  You want your top customers in the EU for last quarter. Say "EU" and "last quarter" only when asked.
  If you get a list, ask for just the top 5.
success:                       # never shown to the simulated user
  - The answer lists five customers, all in the EU, ranked by last quarter's revenue.
expected_path: [list_tables, get_schema, execute_sql]
path_order: loose              # loose | strict | none
outcome_check: checks/top5.py  # optional: reads the real state after the journey
max_turns: 6
env: {DATABASE: orders_eval}
```

Items are hashed and versioned as any dataset's. Splits, sealed test sides, exposure and looks apply unchanged: a
held-out set of journeys is opened once for one candidate.

## 2. The simulated user

An LLM, named by the scorer-like record `data/users/<id>.yaml` (provider, model, params, prompt file), so it has a
fingerprint like a judge. It sees the plan and the conversation, never `success`. It answers in the person's words,
gives facts only when asked, and ends with `END` when the plan is done or cannot be. It is part of every journey
run's fingerprint: two arms are compared only under the same user.

A user can also be **scripted** (a list of replies keyed by turn), for tests and for journeys whose words must not
vary.

## 3. The agent under test

A journey system is an arm whose adapter drives an agent instead of answering once. Three runners:

- **cli**: an agent CLI (Claude Code, Codex, Gemini CLI, …) started with `HOME` and a working directory of its own
  per item and trial, its MCP servers, skills and plugins installed there from the arm's settings. The runner reads
  the CLI's own transcript for turns, tool calls, arguments, results, tokens and latency.
- **http**: an agent behind an endpoint the project names (a chat API), one conversation per item.
- **python**: an adapter function `step(conversation) -> reply` for an agent in the project's own code.

A **fake tool server** (an MCP stdio server with fixed replies, failures included) lets a project test its
journeys, scorers and runner offline and for $0.

## 4. The trajectory

Each item of a journey run records, in the run's rows (RFC-033's model):

- the turns: who spoke, the text, the time;
- the tool calls: name (normalised to `server__tool`), arguments, result (or its hash when it carries the source's
  text, as V12 treats a judge's reply), duration, success;
- tokens (fresh, cached, output), cost, latency, turns, steps;
- how it ended: `END` from the user, `max_turns`, a timeout, an error.

## 5. Scoring the whole run

| what | question | scorer |
| --- | --- | --- |
| path | did the agent take a valid path? | `path_match`: expected tools against the calls, Jaccard (loose), edit distance (strict), with forbidden calls (a write before discovery) as a hard fail |
| outcome | did the world change as it should? | `outcome_check`: the project's check script reads the real state after the journey; pass or fail with its reason |
| answer | does the final answer do the job? | a judge (RFC-034, with its reason) given the success criteria and, when asked, the tool calls |
| goal | how much of the job got done? | a judge splitting `success` into parts, the share met |
| behaviour | invented facts, needless questions | a judge, counted per journey |
| cost | what the journey cost | tokens, dollars, latency, turns, steps per journey |

Every judge here is a judge scorer as today: validated against people's labels on journeys before its numbers count,
and showing its reason.

## 6. Trials and statistics

A journey is noisy: the user and the agent both sample. Each arm runs every journey `k` times (default 3, as arms do
now). The unit of the paired tests is the journey: its mean over trials, so `k` trials of `n` journeys are not
`k·n` independent items. Reported per arm: the pass rate with its interval, **pass^k** (all `k` trials passed: the
consistency a user feels), cost and latency per journey; between arms, the paired test on journeys, Holm across
arms, and contenders by non-inferiority (ADR-0026). The charts of RFC-034 apply as they are (`gain-cost` is
EvalBench's skill ablation with a significance test).

## 7. State

A journey that changes things needs a known start. A journey dataset may name `setup` and `reset` commands (a
database restore, a container) run before every trial; a run refuses to start when `reset` is named and fails, and
two journey runs that share a `state` key do not run at once (the job lock of RFC-026). Without a `reset`, a journey
that writes runs one trial and says so.

## 8. The Workbench and the catalog

- A journey's page: the conversation turn by turn (user, agent, each tool call with its arguments and result), the
  scores beside it with the judges' reasons, and the expected path drawn against the actual one.
- The round and study screens unchanged: arms, evidence, charts, decisions.

## 9. Journeys from production

A capture of real conversations (RFC-019) becomes scenarios: the first message as `starting_prompt`, a plan written
by a person (or proposed by a model, accepted by a person) from what the user went on to say, and `success` from
the outcome production recorded. A production failure becomes a journey that must pass from then on.

## Open questions for the owner

1. Which runner first: **cli** (Claude Code first, as the agent we use), **http**, or **python**?
2. Is there a first real journey set to prove it on (the triage fleet's agents, the podcast product's MCP server)?
3. ~~The simulated user's default model~~ Decided (owner, 2026-11-18): any model, local or online, named the way a
   judge's is (a model record or a system, its provider, its settings), and part of the run's fingerprint.
4. Before 1 and 2 (owner, 2026-11-18): what this is in the harness's model, what it is called, how small it can stay,
   and whether scripted and person-driven flows are the same thing with another driver.

## Not in this RFC

- Agents that run for hours (the harness's jobs cover long runs; a journey has a timeout).
- Voice and screen agents.
- Importing EvalBench's results (owner, 2026-11-18: never).
