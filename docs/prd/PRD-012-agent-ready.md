# PRD-012: Agent-ready: every capability for people and agents alike

- **Status**: Draft (0.5.0), final review round
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the commands), a new UXS
  for the tools and skills, to be written
- **Related RFCs**: [RFC-013](../rfc/RFC-013-machine-surface.md) (declarations, JSON, exit codes, refusals, the actor,
  the config), [RFC-016](../rfc/RFC-016-mcp-server-and-skills.md) (the MCP server, the skills, llms.txt, the glossary)
- **Related PRDs**: every 0.5.0 PRD ([PRD-008](PRD-008-pipelines-and-any-language.md) to
  [PRD-013](PRD-013-identity-and-ties.md)) is held to this one

## Summary

More and more evaluation work is done by an agent on someone's behalf: "run an optimisation loop
on this prompt", "is the new transcription stage better end to end". The harness must be as usable
by that agent as by a person, and what the agent did must read, in the records and the catalog,
as the work of a careful person, with who acted recorded. This PRD makes that the test for every
0.5.0 feature and adds: a **command manifest** and **structured output** on every command, the
CLI conventions machines rely on (results on stdout, messages on stderr, meaningful exit codes,
refusals in a standard shape); an **MCP server** built on the official SDK and the protocol's own
features (tools with annotations, resources, long-running tasks, asking the person); and
**skills** a project imports into its agent setup, teaching workflows rather than listing
commands.

## Background & Context

- Since 0.4.0 every catalog and inspector view has a command. The commands print tables; none has
  machine-readable output.
- The harness refuses unsafe actions with a reason. Refusals go to stderr as `ERROR: …` with exit
  1 (`_common.die`); exit 2 already means "stopped by the cost cap" (`experiment_run.py:884`) and
  "unknown command" (`cli.py:125`), and argparse uses 2 for usage errors.
- The commands are declared as a script name and a one-line description (`cli.py`); each script
  builds its own arguments, so there is no single description of what a command takes.
- The podcast project's loops were run by an agent following hand-written `program_*.md`
  instructions, which tell it never to pause and ask; results lived in TSV files.
- Standards to build on: MCP (tools with `readOnlyHint`/`destructiveHint` annotations, resources,
  the tasks extension for long work, asking the person mid-call, `structuredContent` with a JSON
  Schema); Agent Skills (`SKILL.md` with name and description, progressive disclosure);
  `llms.txt`; clig.dev's CLI guidelines; RFC 9457 problem details for errors; W3C PROV's
  `actedOnBehalfOf` for an agent acting for a person.

## Goals

- Everything a person can do with the CLI or see in the catalog, an agent can do and read through
  tools and resources, with structured input and output.
- An agent given a goal and a budget finds the tools, sets up the work and runs it, without
  guessing at syntax.
- The records do not depend on who acted, and always say who: the person, or the agent and the
  person it acted for.
- Decisions with consequences (promotion, retiring arms, spending over a budget, touching a shared
  host) stay explicit: an agent makes them only after asking, and the record says who decided.
- Limits an agent works within are set by a person; through the MCP server an agent cannot widen
  its own. An agent with a shell can edit files and run commands; the harness cannot stop that, says
  so, records who acted, and its skills steer agents to the MCP server.
- Skills are versioned with the harness and work in any agent harness that reads skills.

## Non-Goals

- No hosted service: the MCP server runs where the project is, with that project's files and keys.
- No agent inside the harness: the harness exposes tools and procedures; the agent is the user's.
- No capability that exists only for agents: a tool is a command, a skill describes commands a
  person could run.

## Personas

- **The project's agent** (Claude Code, opencode, or another) asked to run an evaluation.
- **The person** who set the goal and reads the result in the catalog later.
- **The maintainer** who adds a command and gets its tool from the same declaration.

## User Stories

- _As a person, I tell my agent "run an optimisation loop on the summary prompt for goal
  news_summary_cnn, $10 and two GPU hours"; it reads the goal, writes the study spec, dry-runs it,
  tells me the smallest effect it can detect, runs it, and reports the result of the test check,
  asking me before it promotes._
- _As a person, I open the catalog afterwards and the goal page shows the study's round, each trial
  with its hypothesis, change, test against the incumbent and reason, the test check and the cost,
  and that the agent ran it on my instruction._
- _As an agent, every tool returns JSON matching its declared schema, and a refusal returns its
  code, its explanation and the command that resolves it._
- _As a maintainer, I declare a command once and its CLI help, `--json` shape, manifest entry and
  MCP tool all come from that declaration._

## Functional Requirements

### FR1: The command manifest and structured output

- **FR1.1**: Each command is declared once: name, purpose, arguments (types, required, defaults),
  whether it reads, writes or spends, whether it is long-running, its output schema and examples.
  The CLI's argument parsing, `--help`, the manifest and the MCP tools are generated from it.
- **FR1.2**: `evh commands --json` prints the manifest.
- **FR1.3**: Every command takes `--json` and prints its result in its declared shape; shapes are
  versioned JSON Schemas.

### FR2: CLI conventions machines rely on

- **FR2.1**: Results on stdout, everything else (progress, notes, warnings) on stderr.
  (`experiment-run` has 35 `print` calls, one of them to stderr.)
- **FR2.2**: Exit codes are documented and stable: 0 success; 1 refusal; 2 usage error (argparse's
  convention, kept rather than sysexits' 64); 3 the system under test failed (today `experiment-run`
  returns 1 when nothing was measured); 4 stopped by a budget or cost cap (today 2); 130
  interrupted; 65 to 78 (sysexits) for the remaining operational errors. This is a breaking change,
  listed in the release notes with each old code and its new one.
- **FR2.3**: A refusal is an RFC 9457 problem details object: a stable `type` URI (its identity),
  `title`, `detail`, and the extension member `fix_command` when a command resolves it; with
  `--json` it is printed as JSON.
- **FR2.4**: Every command that writes a record or spends money takes `--dry-run`, which writes and
  calls nothing (no system, judge or sampler call) and prints what it would do and cost. Today only
  `experiment-run`, `judge-score` and `sweep` have it.
- **FR2.5**: No command ever waits for a person on a terminal. A command that needs consent (FR4.5)
  refuses without it, with the command a person runs to give it (`--confirm`, or a consent recorded
  beforehand); the record names who confirmed.
- **FR2.6**: Every command's help names it as `evh <command>` (some scripts print their file name,
  e.g. `usage: promote_baseline.py`), gives its purpose, and shows at least one example. Today 23
  of the 28 commands that build their own parser show only the first line of their docstring, so
  the examples written there never reach `--help`.

### FR3: Who acted

- **FR3.1**: Every record a command writes (run, round, trial, study, promotion, prompt version)
  records the actor: a person, or an agent and the person it acted for (PROV's
  `actedOnBehalfOf`), beside the reason, never instead of it; and, for work an agent was asked to do,
  the instruction verbatim (`--instruction`). The CLI takes them from `--actor` or `EVH_ACTOR`; the
  MCP server from the project's limits file and the person's answers, never from the client's
  self-reported name, which the protocol says not to trust.

### FR4: The MCP server

- **FR4.1**: `evh mcp` starts an MCP server (stdio) for the project, built on the official MCP
  Python SDK, installed by default. It reads the project's `config.yaml` (FR10) as the CLI does.
- **FR4.2**: Its tools are the manifest's commands. Each carries annotations from the manifest:
  read-only, destructive, idempotent, open-world (reaches outside the project, such as a provider);
  spending is the manifest's own flag, and annotations are hints, never what consent rests on. Results are
  `structuredContent` with the command's output schema; a refusal is a tool result marked as an
  error with the RFC 9457 body.
- **FR4.3**: Records are also **resources** with URI templates (`evh://runs/{run_id}`,
  `evh://goals/{goal_id}`, `evh://champions/{goal}`), so an agent can read without calling a
  command.
- **FR4.4**: Long work (a run, a job set, a study) is an MCP **task** when the client asks for one
  (the tasks extension is opt-in per request); otherwise the call returns a job id at once and the
  agent follows it with the `jobs-status` tool, the protocol's own pattern for stateful tools.
- **FR4.5**: **Consent**: promotion, retiring arms, spending beyond the budget the person gave,
  overriding a protective refusal ([PRD-009](PRD-009-prompts-and-optimisation.md) FR4.4, FR4.5),
  sending private data out ([PRD-009](PRD-009-prompts-and-optimisation.md) FR3.5) and phase commands
  that touch a shared host ([PRD-010](PRD-010-runners.md) FR1.7) ask the person before acting: for a
  short call through the protocol's input-required result with an elicitation, for long work through
  the task's input-required state. The question shows the exact command, host and amount. One
  answer may cover a whole study or job set, with a count. The record names who answered.
- **FR4.6**: **Limits**: which tools are enabled, spending and time budgets, and what needs consent
  are set by the person in a file the server will not write and an agent's tools cannot change; a
  change to it is recorded with who made it.

### FR5: Skills

- **FR5.1**: The harness ships skills in the Agent Skills format (a lowercase name matching its
  directory, a description saying when to use it, under 500 lines, the harness version in its
  metadata): evaluate a system for the first time, compare arms and read the result, run a round,
  run an optimisation study (including as its sampler, through `study-ask` and `study-tell`),
  promote with evidence, evaluate a pipeline, bring in runs from elsewhere, and follow a long job.
- **FR5.2**: Skills say when to stop and ask (promotion, spending, shared hosts), whatever a
  project's own instructions say.
- **FR5.3**: `evh skills-install [--target DIR]` copies them into a project or an agent's skill
  directory; they name the harness version they describe. When MCP's skills extension settles, the
  server also offers them.
- **FR5.4**: Each skill's commands are run against the example project in CI.

### FR6: Docs an agent can find

- **FR6.1**: The documentation site publishes an `llms.txt`, and each skill links the reference
  pages it relies on.
- **FR6.2**: A glossary maps the harness's terms to the common ones (Inspect, LangSmith, promptfoo,
  HELM, Optuna, MLflow), so a reader from any of them finds their word.

### FR7: Schemas for every record

- **FR7.1**: `schemas/` covers configs, datasets, goals, rounds, metrics and others, but not the
  run record (`run.json`), the fingerprint or a prediction line. Every record a command writes or
  an agent reads has a versioned schema.

### FR8: The test for every feature

- **FR8.1**: A 0.5.0 feature is done when a person can do it (CLI, catalog), an agent can do it
  (MCP tool or resource, a skill that covers it), and the catalog shows the same thing either way.
- **FR8.2**: A scenario test runs the first user story with an agent end to end on the example
  project, with a dollar cap, before each release (not on every push), and checks the catalog
  afterwards.

### FR9: Gaps found later

New agent-readiness gaps found anywhere in the harness are added to this PRD, each as a numbered
requirement with what was found, and fixed in the release that finds them.

### FR10: One project configuration

- **FR10.1**: The project's `config.yaml` (today read only for `catalog.adapter`) holds the data,
  runs and goals directories, the runners ([PRD-010](PRD-010-runners.md)), the path of the limits
  file (FR4.6) and the catalog's adapter. The CLI and the MCP server both read it; an environment
  variable still wins over it, as `EVAL_DATA_DIR` and its siblings do today.
- **FR10.2**: `evh config --json` prints the configuration in effect and where each value came from.

## Success Criteria

- An agent in the podcast project, given a goal and a budget, sets up and runs an optimisation loop
  through the MCP tools and skills alone, asks before promoting, and the goal page reads as a
  complete, careful record (to be confirmed with that project).
- Every command has `--json`, a declared schema, help with an example and a test of its tool.

## Related Documents

- RFC-013 (to be written); [PRD-004](PRD-004-catalog-and-inspector.md) (CLI parity, the
  precedent). References: the MCP specification (2026-07-28), Agent Skills, llms.txt, clig.dev,
  RFC 9457, W3C PROV-O.
