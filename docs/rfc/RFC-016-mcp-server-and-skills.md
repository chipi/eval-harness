# RFC-016: The MCP server, the skills, llms.txt and the glossary

- **Status**: Draft (0.5.0), revision 3 (2026-10-27): tools only (no resources); consent only by the person running
  the command (no elicitation); three skills. Revision 2: no grant store and no spend ledger; a budget is checked
  against the spend the runs record
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-012](../prd/PRD-012-agent-ready.md) (FR4, FR5, FR6, FR8)
- **Related RFCs**: RFC-013 (the command declarations this is generated from), RFC-011 (jobs), RFC-010 (studies:
  `study-ask`, `study-tell`)
- **Code**: new `harness/scripts/mcp_server.py` (`evh mcp`), `harness/skills/` (package data
  `evaluation_harness.skills`), `skills_install.py` (`evh skills-install`), `site/mkdocs_hooks.py` (llms.txt),
  `docs/GLOSSARY.md`; `pyproject.toml` (the dependency, package data for `skills/**`); dependency `mcp>=2.3,<3`

## Abstract

`evh mcp` is an MCP server over stdio for one project (0.4.5 shipped its read-only start, with `--http` for a team
or the public: RFC-018 on `main`, the last section here), built on the official Python SDK (`mcp` 2.3, protocol
revision 2026-07-28). Its tools are the commands RFC-013 declares, generated from the manifest, each run as a child
`evh <command> --json` so a tool behaves exactly as the command does. Long work returns a job id that the agent
follows with `jobs-status`, because the SDK does not yet implement the tasks extension. A decision with consequences
is refused to the agent with the exact command the person runs; the person's run is the consent. What the server may
do is set by a limits file the server never writes, and who acted is fixed when the server starts, never taken from the
client. The harness also ships three skills in the Agent Skills format, installed with `evh skills-install`, an
`llms.txt` for the documentation, and a glossary that maps its terms to other tools'.

## Problem Statement

- An agent can use the harness today only by running commands and reading tables (PRD-012 Background).
- MCP 2026-07-28 is stateless; a client's self-reported name is not to be trusted for security
  (specification, base protocol); tasks are an opt-in extension.
- The official SDK `mcp` 2.3.0 supports the 2026-07-28 revision, tool annotations and structured output; it has a hook
  for extensions but no handler for the tasks extension. It requires Python 3.10 (RFC-013 moves the harness there).
- **What it brings with it** (its PyPI metadata for 2.3.0, read 2026-10-26): `anyio`, `httpx2`, `jsonschema` (already
  a harness dependency), `mcp-types`, `opentelemetry-api`, `pydantic>=2.12`, `pyjwt[crypto]`, `python-multipart`,
  `sse-starlette`, `starlette`, `typing-extensions`, `typing-inspection`, `uvicorn` (and `pywin32` on Windows). The
  podcast project's environment already has `pydantic` 2.14.1 and `opentelemetry-api` 1.45.1, inside those bounds;
  `httpx2` is a separate distribution from the `httpx` it has. This is the footprint the owner accepted with "the
  official SDK in 0.5.0"; the release notes list it.

## Design

### The server (`evh mcp`)

- `evh mcp [--agent NAME] [--project DIR]` starts a stdio server for the project (`config.yaml`, RFC-013). `--agent`
  names the agent for the records (default `agent:mcp-client`); the person comes from the limits file.
- **Tools** are generated from `evh commands --json` (RFC-013): name = the command (`run-promote`), description =
  purpose + effects + examples, `inputSchema` from its arguments, `outputSchema` = the envelope schema with the
  command's result schema inside (`{command, version, result}`, what stdout carries). Reading a record is a read tool
  (`goals`, `baselines`, `study-status`, `arms`, …); there are no separate resources.
- **Not tools**: commands that never return (`catalog-serve`, `mcp`), and the ones only a person runs:
  `skills-install` (it writes the instructions agents follow) and `init`. The server's own `limits` tool is read-only.
- **What the input schema leaves out**: `--actor`, `--on-behalf-of` and `--confirm`. The server sets the actor itself;
  consent comes from the person (below), never from an argument. `--instruction` stays, recorded as the agent reported
  it. Override flags (`--allow-dirty`, …) stay, and using one needs consent of kind `override_refusal`.
- **Paths**: an argument the parser types as a path is resolved before the call; one that lands in `.evh/`, on the
  limits file, or outside the project root is refused (`path-not-allowed`), so no tool (`prompt-export --to`, a
  `--out`) can overwrite what governs the server.
- **A call** runs `evh <command> <args> --json --actor agent:<name> --on-behalf-of <person>` as a child process in its
  own process group, with the server's environment and a timeout (the command's declared `timeout_s`, default 600 s
  for a command that is not long-running). Cancelling the request, or the timeout, kills the process group. stdout (the
  JSON result) becomes `structuredContent`, capped at 1 MB (beyond it the tool returns an error naming the command's
  `--limit`/`--offset` paging, which list commands declare); stderr is kept as the tool's log text, its last 64 KB; a
  refusal (exit 1) becomes a result with `isError: true` and the problem details body.
- **Parallel calls** write records through the record store, as the commands do (RFC-017): every record is written once
  with an id two calls cannot share, so two tools promoting or recording a prompt version at once cannot collide.
- **Annotations** from the declaration: `readOnlyHint` when the command only reads; `destructiveHint` when it writes;
  `idempotentHint` and `openWorldHint` from the declaration's `idempotent` and `open_world`. They are hints for the
  client; the server's own checks (below) do not rest on them.

### Long work

- A command declared `long_running` (`experiment-run`, `sweep`, `judge`, `rescore`) is started as a one-job set (RFC-011):
  the tool returns at once with `{"job_set": id, "status": "queued", "follow": "jobs-status", "stop": "jobs-stop"}`, and
  the agent follows it with the `jobs-status`, `jobs-logs` and `jobs-stop` tools (the protocol's pattern for stateful
  tools). Commands that detach by themselves (`jobs-run`, `study-run`) are called directly: they return an id at once
  and are never wrapped in a second set. A `rescore` of one run is declared long-running like any rescore: one rule per
  command, no guessing from arguments.
- **Consent during long work.** A detached set or study that needs consent part-way (a budget crossed, a look past the
  limit) stops that step and enters `waiting_consent` with the question in its state. `jobs-status` and `study-status`
  return the question and the command the person runs to continue (`… --resume <id> --confirm`). Until the person runs
  it, the step stays waiting, and nothing is spent.
- When the SDK implements the tasks extension and the client asks for a task, the same call returns a task instead;
  the job set's states map to task states as RFC-011 lists.

### Consent and limits

- **Limits file** (path in `config.yaml`, default `evh-limits.yaml` at the project root, `schemas/limits.schema.json`),
  written by the person, never by the server:
  ```yaml
  acting_for: person:marko
  tools: {disabled: [run-promote], read_only: false}
  budgets: {usd_per_day: 10, gpu_hours_per_day: 2, usd_per_study: 5}
  ```
- **Who changed it** (PRD-012 FR4.6): the file is tracked, and the server reads it from the committed tree. It reads the
  path from `config.yaml` once, at start; if the file has uncommitted changes, the server refuses to start (and, when
  they appear later, refuses calls) naming them, so every change in force is a commit with its author. Every record the
  server writes carries the commit of the limits in force. No tool writes it, and path arguments cannot reach it
  (above).
- **Consent** (RFC-013's model: a person's, never only an agent's). When a command asks for consent at run time (a
  promotion, retiring an arm, an extra look, an override, a shared host) or a call would cross a budget, the tool is
  refused (`consent-required`) with the exact command the person runs in their own terminal, with `--confirm`. The
  person's run is the action and the consent, so the agent does not retry it. One path, and nothing stored in between.
- **Budgets**: nothing is stored apart from the records (RFC-017). The spend of a day is what the catalog adapter's
  `spend()` counts for it (the runs' cost, `metrics.json`, and the judges' verdicts under `data/judge-verdicts/`:
  the number 0.4.2's activity page shows for that day), plus `outputs/_rows.jsonl` for a run in progress and the
  `--dry-run` estimates of the jobs still queued or running. A call whose estimate would cross a limit needs consent. The child gets
  `EVAL_MAX_COST_USD` set to the budget left, so `experiment-run`'s own cost cap stops it at the limit even when the
  estimate was low; the job and study supervisors pass the same cap to every job they start. Two calls started at the
  same moment can both pass the check; the cost caps still stop each at what was left when it started. A shared
  budget for a team is the database provider's.
- What the server cannot stop: an agent with a shell can run `evh` directly or edit files. The records say who acted;
  the skills tell agents to use the server.

### Skills

- Shipped as package data under `evaluation_harness/skills/<name>/SKILL.md` (with `references/` where needed), in the
  Agent Skills format: front matter `name` (lowercase, matching its directory), `description` (what it does and when to
  use it), `metadata: {harness-version: "0.5.0"}`; under 500 lines; it links the documentation pages it relies on.
- The set, three:
  - `evh-evaluate-and-compare`: a first evaluation (dataset, materialize, run, reference, compare, choose), reading a
    comparison (verdicts, looks, what not to conclude), rounds, pipelines and other languages (stages, batch mode, the
    process adapter, the wrapping recipe), and bringing runs in (`import-run`, OTLP, `study-import`);
  - `evh-run-a-study`: the spec, `--dry-run`, `study-run` or `study-ask`/`study-tell` as the sampler, `study-status`,
    `study-confirm`, and promotion with its evidence;
  - `evh-follow-a-job`: `jobs-status`, `jobs-logs`, `jobs-stop`, and a job waiting for consent.
- Each says when to stop and ask (promotion, retiring, an extra look, an override, spending over the budget, a shared
  host), whatever a project's own instructions say, and to prefer the MCP tools when they are available.
- `evh skills-install [--target DIR] [--force]` copies them into the project (`.claude/skills/` by default, or any agent's
  skill directory); it refuses to overwrite a changed copy without `--force`.
- **Tested**: every fenced block tagged `evh` in a skill runs against the example project in CI, in order, with its
  expected exit code; a skill whose commands fail fails the build.
- **Covered** (PRD-012 FR8.1): `evh skills-check` (exit 6 on a gap) fails when a command in the manifest is named by no
  skill and is not listed, with a reason, in `skills/NOT_IN_A_SKILL.md` (internal commands such as `self-test`).
- **Packaged**: `pyproject.toml` maps `evaluation_harness.skills` to `harness/skills` and includes `**/*.md` under it as
  package data, nested directories included; the package test installs the wheel and lists them.

### llms.txt and the glossary

- `site/mkdocs_hooks.py` writes `llms.txt` at the documentation root on build (`/docs/llms.txt`: the docs are served
  under `https://evals.humancopilot.eu/docs/`, `mkdocs.yml` `site_url`): the site's title and summary, then each page
  with its title, URL and first sentence, grouped by the navigation's sections (llms.txt v2).
- `site/build.py` writes `/llms.txt` at the site root, where agents look for it: the site's own pages first, then a
  link to `/docs/llms.txt`; its `--check` checks it as it checks `robots.txt` and `sitemap.xml`.
- `docs/GLOSSARY.md`: each harness term (arm, run, adapter, reference, gold, silver, goal, round, study, trial, sampler,
  baseline, look, separated, non-inferior, inconclusive) with its meaning and the word other tools use (Inspect,
  LangSmith, promptfoo, HELM, Optuna, MLflow), and where the meaning differs, how.

### The scenario test (PRD-012 FR8.2)

`harness/tools/agent_scenario.py` (a release check, not a command) runs an agent CLI headless (Claude Code's `claude
-p` with the project's MCP configuration; another agent CLI may be named) on the example project with the instruction of
PRD-012's first user story and a hard dollar cap, then checks the records: a study round with trials, reasons and an
actor; a refused promotion without consent; the goal page built. It needs the person's API key and is run before each
release, recorded in `RELEASING.md`, not in CI.

### Users on a shared server (to design; the owner's note, 2026-10-29)

0.4.5 ships `evh mcp` early, read-only (RFC-018 on `main`): stdio, and `--http` for a team or the public, with no
accounts, deployed at `evals.humancopilot.eu/mcp` without sign-in. A server many people reach needs users before it
can offer anything but reads. To design here, before 0.5.0's writing tools go on a shared server:

- **Who can read and who can write, through which tools**: an identity per caller (OAuth 2.1, which the protocol and
  the SDK define for HTTP), roles per project (reader, runner, decider), and the consent model above applied per user,
  so "the person running the command" is a known person on a shared server too.
- Most probably more, as the owner expects: per-user budgets and rate limits, an audit of what each user did through
  which tool (the actor on every record, RFC-013), which projects or datasets a user may see (private data beside
  public), and how a team's server is run (one per project, or one for several).

## Migration

None. The server and skills are new; `UPGRADING.md` says how to add `evh mcp` to an agent's MCP configuration and run
`evh skills-install`. 0.4.5's read-only server (RFC-018) is the start: its tools keep their names and answers; 0.5.0
adds the declarations, the writing tools, consent and, once designed, users.

## Alternatives Considered

- **Run tools in-process.** Rejected: commands keep module-level state (the catalog's `API`, `HEAD`, `BRAND`,
  `ABOUT`, `REPO`, set by its `main()`), and a
  child process gives a tool exactly the command's behaviour, refusals and exit codes.
- **A hand-written MCP server.** Rejected by the owner earlier: the SDK tracks the protocol.
- **Trust the client's name for the actor.** Rejected: the specification says not to.
- **Only MCP tasks for long work.** Rejected for now: the SDK does not implement the extension; the job id works
  everywhere and stays as the fallback.
- **Consent by elicitation** for some kinds of decision (revisions 1 and 2). Rejected in revision 3 (owner): an agent
  client may answer an elicitation itself, and two consent paths are harder to explain and audit than one.
- **Records as MCP resources** beside the tools (revisions 1 and 2). Deferred in revision 3 (owner): every resource
  duplicated a read tool.
- **Eight narrow skills** (revisions 1 and 2). Rejected in revision 3: three cover the same ground with less to keep
  tested.
- **Serve skills over MCP only.** Deferred until MCP's skills extension settles; files work with every agent harness
  today.

## Testing

- `harness/tests/test_mcp_server.py` (an in-memory client from the SDK): the tool list equals the manifest; a read tool's
  `structuredContent` validates against the envelope schema; a refusal is `isError` with a problem details body; a
  long-running tool returns a job set id; a promotion is refused with the exact command a person runs; `--actor` and
  `--confirm` are not in any input schema; a path argument into `.evh/` or the limits file is refused; uncommitted
  limits refuse; a call over the budget the runs record needs consent; a cancelled call kills its child; output over
  1 MB is refused with paging named; a set waiting for consent returns the command to continue it; `catalog-serve`,
  `mcp`, `skills-install` and `init` are not tools; a disabled tool is absent; the actor recorded is the server's
  `--agent` acting for the limits file's person.
- `harness/tests/test_skills.py`: front matter valid and matching directories; under 500 lines; every `evh` block runs on
  the example project; `skills-check` finds no command uncovered.
- `site/test_browser.py` or a docs check: `llms.txt` lists every page in the navigation.

## Decisions (ADR candidates)

1. `evh mcp` on the official SDK; tools generated from the manifest, each run as a child `evh … --json`; no resources.
2. Long work returns a job id followed with `jobs-status`; MCP tasks when the SDK supports them.
3. Consent is a person's: the agent gets the exact command and the person runs it with `--confirm`; limits in a tracked
   file the server never writes and reads only when committed; the actor fixed at start, never from the client; actor
   and consent flags are never tool arguments.
4. Three skills ship with the package in the Agent Skills format, installed by a command, their commands tested, every
   command covered.
5. `llms.txt` generated with the documentation; a glossary maps terms to other tools'.
6. Tools run as child processes with a timeout, killed on cancel, with capped output; a budget is checked against the
   spend the runs record, and every job runs under a cost cap of what is left.
