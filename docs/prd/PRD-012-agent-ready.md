# PRD-012: Agent-ready: every capability for people and agents alike

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the commands), a new UXS
  for the tools and skills, to be written
- **Related RFC**: RFC-013 (the MCP server and the skills), to be written
- **Related PRDs**: every 0.5.0 PRD ([PRD-008](PRD-008-pipelines-and-any-language.md) to
  [PRD-011](PRD-011-evidence-registry.md)) is held to this one

## Summary

More and more evaluation work is done by an agent on someone's behalf: "run an optimisation loop
on this prompt", "is the new transcription stage better end to end". The harness must be as
usable by that agent as by a person, and what the agent did must look, in the records and the
catalog, exactly as if a careful person had done it. This PRD sets that as the test for every
0.5.0 feature and adds three things: **structured output** on every command (`--json`), an **MCP
server** that exposes the harness's commands as tools to agents, run where the project is, and a
set of **skills** a project imports into its own agent setup, teaching the workflows (start an
evaluation, run a loop, read a goal, promote with evidence) rather than listing commands.

## Background & Context

- Since 0.4.0 every catalog and inspector view has a command (CLI parity). The commands print
  tables for people; none has machine-readable output, so an agent parses text.
- The harness refuses unsafe actions with a reason (an unfrozen dataset, an unknown goal, a run
  that would overwrite another). Those refusals are exactly what an agent needs, if it can read
  them.
- The podcast project's optimisation loops were run by an agent following hand-written
  `program_*.md` instructions, editing files and committing; nothing in the harness guided it,
  and its results were TSV files outside the harness's records.
- MCP (Model Context Protocol) is how agents in Claude Code, opencode and others are given tools;
  skills are how they are given procedures.

## Goals

- Everything a person can do with the CLI or see in the catalog, an agent can do and read through
  tools, with structured input and output.
- An agent given a goal ("optimise this prompt for this goal, $10 budget") finds the tools,
  sets up the experiment and runs it, without guessing at command syntax.
- The records do not depend on who acted: the same run, round, loop and promotion records, with
  the actor (person, agent and which) recorded beside them, never instead of the reason.
- Decisions with consequences (promotion, retiring arms, spending over a budget) stay explicit:
  an agent can make them only when the person running it allowed that, and the record says who
  decided.
- Skills are versioned with the harness and work in any agent harness that reads skills.

## Non-Goals

- No hosted service: the MCP server runs where the project is, with that project's files and
  keys, and serves only its own user.
- No agent inside the harness: the harness exposes tools and procedures; the agent is the
  user's.
- No new capability that exists only for agents: a tool is a command, and a skill describes
  commands a person could run.

## Personas

- **The project's agent** (Claude Code, opencode, or another) asked to run an evaluation.
- **The person** who set the goal and reads the result in the catalog later.
- **The maintainer** who adds a command and should get its tool for free.

## User Stories

- _As a person, I tell my agent "run an optimisation loop on the summary prompt for goal
  news_summary_cnn, $10 budget"; it reads the goal, writes the loop spec, dry-runs it, runs it,
  and reports the confirmed winner with the evidence, asking me before it promotes._
- _As a person, I open the catalog afterwards and the goal page shows the loop's round, each step
  with its reason, the held-out check and the cost, as if I had run it by hand; the round says an
  agent ran it, on my instruction._
- _As an agent, every tool returns JSON with the same fields the command's table shows, and a
  refusal returns its reason and the command that would fix it._
- _As a maintainer, I add a command and its MCP tool appears without writing a second
  implementation._

## Functional Requirements

### FR1: Structured output

- **FR1.1**: Every read command takes `--json` and prints the same content as its table, in a
  documented shape; the shapes are versioned.
- **FR1.2**: Every refusal has a stable code, a message, and when there is one, the command that
  resolves it; with `--json` it is printed as JSON on a non-zero exit.

### FR2: The MCP server

- **FR2.1**: `evh mcp` starts an MCP server (stdio) in the project; its tools are the commands,
  generated from one declaration so a new command gains its tool.
- **FR2.2**: Read tools are always available; tools that spend money or write records
  (`experiment-run`, `loop-run`, `plan-run`, `round-*`, `run-promote`) are listed separately and
  can be disabled, limited by a budget, or required to dry-run first, in the project's config.
- **FR2.3**: Long work (a run, a plan, a loop) returns an id at once; status tools follow it
  ([PRD-010](PRD-010-runners.md)).
- **FR2.4**: Each record the server writes names the actor (`agent:<name>` from the client) and
  the session, beside the reason the agent gave.

### FR3: Skills

- **FR3.1**: The harness ships skills (Markdown with front matter, the common skill format):
  start evaluating a system, compare arms and read the result, run a round, run an optimisation
  loop, promote with evidence, evaluate a pipeline, bring in runs from elsewhere.
- **FR3.2**: `evh skills-install [--target DIR]` copies them into a project or an agent's skill
  directory; they are versioned with the harness and name the version they describe.
- **FR3.3**: Each skill is tested: its commands are run against the example project in CI.

### FR4: The gaps found in 0.4.0

An audit of the 0.4.0 commands (2026-10-26) found these, besides the missing `--json`; each is
fixed in 0.5.0, and new gaps found later are added here.

- **FR4.1**: **Dry run everywhere it matters.** Only `experiment-run`, `judge-score` and `sweep`
  take `--dry-run`. Every command that writes a record or spends money gains it (`run-promote`,
  `round-open`, `round-retire`, `round-close`, `dataset-create`, `reference-create`,
  `import-run`, `rescore`, `judge`, `silver-calibrate`, and the 0.5.0 commands), printing what it
  would write or spend.
- **FR4.2**: **Results on stdout, progress on stderr.** `experiment-run` has 35 `print` calls, one
  of them to stderr: progress and result share stdout, and a caller cannot separate the result from the
  narration. Progress goes to stderr; stdout carries only the result (its JSON with `--json`).
- **FR4.3**: **Exit codes that mean something.** Every refusal exits 1, like a crash would.
  Exit codes become documented: success, refusal (with its code, FR1.2), failure of the system
  under test, interrupted, and an internal error.
- **FR4.4**: **Help an agent can trust.** `--help` names the script (`usage: promote_baseline.py`)
  rather than the command (`evh run-promote`), and one script in 67 shows an example. Every
  command's help gives its `evh` name, a one-line purpose and at least one example.
- **FR4.5**: **A machine-readable command list.** `evh commands --json` lists every command, its
  arguments (types, required, defaults), whether it writes or spends, and its output shape; the
  MCP tools (FR2.1) are generated from it.
- **FR4.6**: **Schemas for every record.** `schemas/` covers configs, datasets, goals, rounds and
  others, but not the run record (`run.json`), the fingerprint or a prediction line. Every record
  a command writes or an agent reads has a schema, versioned with the harness.
- **FR4.7**: **Docs an agent can find.** The documentation site publishes an `llms.txt` (an index
  of the pages for agents), and each skill links the reference pages it relies on.
- **FR4.8**: **Long work detaches.** `experiment-run` and `sweep` hold the terminal until done; an
  agent's tool call times out first. Long work gets an id and a status command
  ([PRD-010](PRD-010-runners.md) FR1.3).

### FR5: The test for every feature

- **FR5.1**: A 0.5.0 feature is done when a person can do it (CLI, catalog) and an agent can do
  it (MCP tool, a skill that covers it), and the catalog shows the same thing either way.
- **FR5.2**: A scenario test runs the PRD's first user story with an agent end to end on the
  example project ($ capped), and checks the catalog afterwards.

## Success Criteria

- An agent in the podcast project, given a goal and a budget, sets up and runs an optimisation
  loop through the MCP tools and skills alone, and the goal page reads as a complete, careful
  record (the review with that project checks this).
- Every 0.4.0 read command has `--json`; every tool has a test.

## Related Documents

- RFC-013 (to be written); [PRD-004](PRD-004-catalog-and-inspector.md) (CLI parity, the
  precedent).
