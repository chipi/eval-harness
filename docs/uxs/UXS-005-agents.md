# UXS-005: The harness for agents: tools, consent, skills, llms.txt

- **Status**: Draft (0.5.0), revision 2 (2026-10-27): consent is the person's own command; no grants
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-012](../prd/PRD-012-agent-ready.md)
- **Related RFCs**: [RFC-013](../rfc/RFC-013-machine-surface.md) (declarations, JSON, exit codes, refusals,
  consent), [RFC-016](../rfc/RFC-016-mcp-server-and-skills.md) (the server, skills, llms.txt), [RFC-011](../rfc/RFC-011-job-sets-and-runners.md)
  (jobs), [RFC-010](../rfc/RFC-010-studies.md) (`study-ask`, `study-tell`)
- **Related UX specs**: [UXS-003](UXS-003-cli-and-onboarding.md) (the same commands for a person),
  [UXS-004](UXS-004-studies-baselines-prompts.md) (words and marks)
- **Implementation paths**: `harness/scripts/mcp_server.py`, `_command.py`, `_consent.py`,
  `harness/skills/`, `site/mkdocs_hooks.py`, `docs/GLOSSARY.md`

## Summary

An agent meets the harness in three ways: as **MCP tools and resources** (`evh mcp`), as **skills** it
loads when a task matches, and as **documentation** it reads through `llms.txt`. This spec says what
the agent sees in each: the names, descriptions, results, refusals, the questions put to the person,
and the order of a study driven by an agent. The test of all of it is PRD-012's: an agent in a
project, given a goal, sets up and runs a study, and the catalog looks as if a careful person did it.

## Principles

- **The same words as for a person.** Tool names are command names; results are the commands' JSON;
  verdicts, look labels and actors are UXS-004's words.
- **Every result says what to do next.** A refusal names the fix as a command; a long job names the
  tool that follows it; a suggestion names the command a person runs.
- **Decisions with consequences reach the person**, through a question the agent cannot answer for
  them, and the agent is told so in plain words.
- **Nothing is hidden from the record.** Whatever the agent does is attributed to it and to the person
  it acts for.

## Scope

**In scope:** the server's tools and resources as an agent sees them; refusals and consent from the
agent's side and the person's; long work; the skills; `llms.txt` and the glossary; the agent-driven
study.

**Non-goals:** a chat interface; the agent's own client UI (how a client renders an elicitation is the
client's); hosting the server remotely (stdio only in 0.5.0).

## Starting the server

A person adds the server to their agent's MCP configuration, once per project:

```json
{"mcpServers": {"evh": {"command": "evh", "args": ["mcp", "--agent", "claude", "--project", "."]}}}
```

On start it reads `evh-limits.yaml`. If the file is missing or has uncommitted changes, it does not
start, and says on stderr: "ERROR (limits-uncommitted): evh-limits.yaml has uncommitted changes.
Commit them, so the change has an author, then start the server again." `UPGRADING.md` and the
`evh-evaluate-a-system` skill show a starting limits file.

## Tools

- **Names** are the commands: `experiment-run`, `run-compare`, `study-ask`. **Descriptions** are the
  declaration's purpose, then its effects in one line ("reads", "writes records", "spends: calls the
  system under test and judges"), then up to three examples as command lines.
- **Arguments** are the command's, named as its long flags without dashes (`dataset_id`, `reason`),
  with types, defaults and choices; repeatable flags are arrays. `actor`, `on_behalf_of` and `confirm`
  never appear.
- **Results**: `structuredContent` is `{command, version, result}`, the same as `--json` on the command
  line; the text content is the human table, for clients that show text; the log (stderr) is attached
  as a second text block, its last 64 KB.
- **Refusals** come back with `isError: true` and the problem details:

  ```json
  {"type": "https://evals.humancopilot.eu/docs/refusals/#dirty-build", "code": "dirty-build",
   "title": "The run was produced by a dirty tree", "detail": "build.ref=1a2b3c4d does not describe what ran.",
   "fix_command": "evh experiment-run --config data/configs/cnn_bart_l.yaml", "exit_code": 1}
  ```

  The refusals page (`docs/refusals/`) lists every code with its meaning and fix; each `type` links
  there.
- **Too much output**: a result over 1 MB is replaced by a refusal, `output-too-large`, naming the
  `limit` and `offset` arguments that page it.
- **Not tools**: `catalog-serve`, `mcp`, `consent`, `skills-install`, `init` (a person runs them).
- A tool the limits disable is absent from the list.

## Resources

`evh://goals/{goal_id}`, `evh://baselines/{goal}`, `evh://baselines/{goal}/{dataset}`,
`evh://studies/{goal}/{study_id}`, `evh://runs/{+run}` (`runs/<run_id>`), `evh://prompts/{+name}`,
`evh://looks/{dataset}`, `evh://datasets/{dataset_id}`. Each returns the JSON of the matching read
command, so reading a goal costs no tool call. Listing a template's resources returns the ids the
matching command lists.

## Long work

- A tool that may run long (`experiment-run`, `sweep`, `judge`, `rescore`) returns at once:

  ```json
  {"command": "experiment-run", "version": "1", "result": {"job_set": "experiment-run_20261026T153757.123Z_7f3a",
   "status": "queued", "follow": "jobs-status", "stop": "jobs-stop"}}
  ```

- `jobs-status` returns each job's state (`queued`, `running`, `succeeded`, `failed`, `cancelled`,
  `timed_out`, `skipped`, `lost`), its attempts and run ids, the set's progress ("4 of 6 done"), and
  `next_check_s` (a suggested wait). `jobs-logs` returns the last lines; `jobs-stop` stops it and runs
  the phases' `after` commands.
- `study-run` and `jobs-run` return their own ids in the same shape.

## Consent, from both sides

**What the agent sees** when a call needs consent that an elicitation cannot give (by default:
promotion, retiring an arm, an extra look, an override, sending data out):

```json
{"type": "https://evals.humancopilot.eu/docs/refusals/#consent-required", "code": "consent-required",
 "title": "This needs the person's consent", "exit_code": 1,
 "detail": "Promoting run:runs/cnn_bart_l_v1_20261026T153757.123Z_7f3a to baseline of news_summary_cnn on cnn_dailymail_200 (replacing version 2).",
 "consent": {"kind": "promote"},
 "fix_command": "evh run-promote --run run:runs/cnn_bart_l_v1_20261026T153757.123Z_7f3a --reason '…' --confirm",
 "for_the_agent": "Ask the person to run the fix_command in their own terminal: their run is the promotion. Do not run it yourself, and do not call this tool again for it."}
```

**What the person sees** when the kind is one their limits let an elicitation answer (by default
`spend_over_budget` and `shared_host`): their client shows a form with the server's message, which is
always the exact command, host and amount, and one question:

> **evh: spend over the budget?** `experiment-run --config data/configs/cnn_qwen_m.yaml` would spend
> about $3.40; $1.20 is left of today's $10.00. Allow this one call? (Yes / No)

A study or job set asks once for the whole of it, with the count: "The study will switch dgx-llm-1 to
`code` mode and back up to 12 times. Allow?" A **No** refuses the call with `consent-declined`; nothing
runs.

**What the record shows**: "confirmed by person:marko (grant)" or "(elicitation, reported by the
client)" beside the actor, on the page and in the command's output (UXS-004).

## Skills

Installed with `evh skills-install` into the project's agent skill directory (`.claude/skills/` by
default). Each skill is a `SKILL.md` an agent loads when its description matches the task:

| skill | its description says to use it when | it walks through | it stops and asks when |
| --- | --- | --- | --- |
| `evh-evaluate-a-system` | evaluating a system for the first time | dataset, materialize, run, reference, compare, choose | promotion; spending past the budget |
| `evh-compare-and-read` | asked which arm is better, or what a result means | `goals`, `inspect`, verdicts, looks, what not to conclude | never: it reads |
| `evh-run-a-round` | trying a set of arms against a hypothesis | `round-open`, runs, `rounds`, retire, close | retiring; promotion |
| `evh-run-a-study` | optimising prompts or parameters toward a goal | the spec, `--dry-run`, `study-run` or `study-ask`/`study-tell`, `study-status`, the outcome | a remote sampler seeing data; a shared host; an extra look; promotion |
| `evh-promote-with-evidence` | asked to make an arm the baseline | the evidence, the look, the command | always: promotion is the person's |
| `evh-evaluate-a-pipeline` | the system has stages, or is not in Python | stages, stage references, batches, the process adapter, wrapping a runner | a shared host |
| `evh-bring-runs-in` | results exist from elsewhere | `import-run`, OTLP, `study-import` of a `results.tsv` | never: it writes records only |
| `evh-follow-a-job` | something runs in the background | `jobs-status`, `jobs-logs`, `jobs-stop`, consent while waiting | consent while waiting |

Every skill: says to prefer the MCP tools when the server is configured and the commands otherwise; says
in its first lines when to stop and ask, whatever the project's own instructions say; links the
documentation pages it relies on; is under 500 lines; carries `metadata: {harness-version: "0.5.0"}`.

## The agent-driven study

The order an agent follows, as the `evh-run-a-study` skill and PRD-012's first user story set it:

1. Read the goal (`evh://goals/<id>`) and its baseline; read the looks of the heldout dataset.
2. Write the spec (`data/studies/<goal>/<id>.yaml`) with `sampler: {kind: agent}`; run `study-run` with
   `dry_run: true` and show the person the plan: the trials it may take, the cost per role, the
   smallest p the heldout items can reach against the look's level. A refusal `no-possible-evidence` is
   reported to the person as it is, never worked around.
3. `study-run` opens the study. Then, in a loop: `study-ask` returns the state and an `ask_id`; the
   agent proposes one change with its hypothesis (`study-tell` with the `ask_id`); the result says kept or
   dropped and why; `trial-running` means wait and ask again.
4. When a stop rule fires the study runs its heldout check (confirmatory) and the agent reports the outcome
   in UXS-004's words, including the drop from dev to heldout.
5. If the outcome meets the rule, the agent tells the person the suggested promotion command. It does
   not run it: a promotion needs the person to run it, and the skill says so.

## llms.txt and the glossary

- `llms.txt` at the documentation root: the site's title and one-paragraph summary, then one section per
  navigation group (Getting started, Guides, Reference, Design: PRD, UXS, RFC, ADR), each page as
  `- [Title](url): its first sentence`.
- `GLOSSARY.md` (in the docs' Reference section): one row per term: **term**, **in the harness**, **in
  other tools** (Inspect, LangSmith, promptfoo, HELM, Optuna, MLflow), **difference** ("a *trial* is
  Optuna's word; here a trial is also a set of runs with its own records").

## Checklist for a change to the agent surface

- A new command has a declaration, so it is a tool, with a description an agent can act on.
- A new refusal has a registry entry, a fix command where there is one, and for consent the
  `for_the_agent` line.
- A new decision with consequences declares its consent kind.
- Every skill's commands still run in CI (`make skills-check`).
