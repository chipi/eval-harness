# RFC-016: The MCP server, the skills, llms.txt and the glossary

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-012](../prd/PRD-012-agent-ready.md) (FR4, FR5, FR6, FR8)
- **Related RFCs**: RFC-013 (the command declarations this is generated from), RFC-011 (jobs), RFC-010 (studies:
  `study-ask`, `study-tell`)
- **Code**: new `harness/scripts/mcp_server.py` (`evh mcp`), `harness/skills/` (package data
  `evaluation_harness.skills`), `skills_install.py` (`evh skills-install`), `site/mkdocs_hooks.py` (llms.txt),
  `docs/GLOSSARY.md`; dependency `mcp>=2.3,<3`

## Abstract

`evh mcp` is an MCP server over stdio for one project, built on the official Python SDK (`mcp` 2.3, protocol
revision 2026-07-28). Its tools are the commands RFC-013 declares, generated from the manifest, each run as a child
`evh <command> --json` so a tool behaves exactly as the command does. Records are also resources. Long work returns a
job id that the agent follows with `jobs-status`, because the SDK does not yet implement the tasks extension.
Decisions with consequences ask the person through elicitation when the client supports it and are refused otherwise.
What the server may do is set by a limits file the server never writes, and who acted is fixed when the server starts,
never taken from the client. The harness also ships skills in the Agent Skills format, installed with
`evh skills-install`, an `llms.txt` for the documentation, and a glossary that maps its terms to other tools'.

## Problem Statement

- An agent can use the harness today only by running commands and reading tables (PRD-012 Background).
- MCP 2026-07-28 is stateless; a client's self-reported name is not to be trusted for security
  (specification, base protocol); tasks are an opt-in extension; consent has two standard paths (an input-required
  result with an elicitation for a short call, the task's input-required state for long work).
- The official SDK `mcp` 2.3.0 supports the 2026-07-28 revision, tool annotations, structured output and resources;
  its 2.0.0 release notes say the tasks extension is not part of it, and 2.3.0's do not add it. It requires Python
  3.10 (RFC-013 moves the harness there).

## Design

### The server (`evh mcp`)

- `evh mcp [--agent NAME] [--project DIR]` starts a stdio server for the project (`config.yaml`, RFC-013). `--agent`
  names the agent for the records (default `agent:mcp-client`); the person comes from the limits file.
- **Tools** are generated from `evh commands --json` (RFC-013): name = the command (`run-promote`), description =
  purpose + effects + examples, `inputSchema` from its arguments, `outputSchema` = the command's output schema. A call
  runs `evh <command> <args> --json --actor agent:<name> --on-behalf-of <person>` as a child process with the server's
  environment; stdout (the JSON result) becomes `structuredContent`; stderr is kept as the tool's log text; a refusal
  (exit 1) becomes a result with `isError: true` and the problem details body.
- **Annotations** from the declaration: `readOnlyHint` when the command only reads; `destructiveHint` when it writes;
  `idempotentHint` as declared; `openWorldHint` when it calls outside the project (a provider, a runner host). They are
  hints for the client; the server's own checks (below) do not rest on them.
- **Resources** (templates): `evh://runs/{runs_dir}/{run_id}`, `evh://goals/{goal_id}`, `evh://champions/{goal}/{dataset}`,
  `evh://studies/{goal}/{study_id}`, `evh://prompts/{name}`, `evh://looks/{item_set}`, `evh://datasets/{dataset_id}`;
  each returns the JSON a command would (`evh goals --goal … --json`), so an agent can read without a tool call.

### Long work

A command declared `long_running` (`experiment-run`, `sweep`, `jobs-run`, `study-run`, `judge`, `rescore` at scale) is
started as a job set (RFC-011): the tool returns at once with `{"job_set": id, "status": "queued"}`, and the agent follows
it with the `jobs-status`, `jobs-logs` and `jobs-stop` tools (the protocol's pattern for stateful tools). When the SDK
implements the tasks extension and the client asks for a task, the same call returns a task instead; the job set's
states map to task states as RFC-011 lists.

### Consent and limits

- **Limits file** (path in `config.yaml`, default `.evh/limits.yaml`), written by the person, never by the server:
  ```yaml
  acting_for: person:marko
  tools: {disabled: [run-promote], read_only: false}
  budgets: {usd_per_day: 10, gpu_hours_per_day: 2, usd_per_study: 5}
  consent: [promote, retire, spend_over_budget, override_refusal, data_egress, shared_host]
  ```
  The server reads it at every call; its hash is recorded with every record the server writes, so a change to it shows.
  No tool reads or writes it except a read-only `limits` tool.
- **Consent**: a call to a command declared `needs_consent`, or one that would cross a budget, first asks the person:
  the server returns an input-required result with an elicitation request (the exact command, host and amount; one
  answer may cover a whole study or job set with a count); on the answer, it runs the command with
  `--confirm --confirmed-by <answer's person>` and records the answer. If the client does not support elicitation, the
  tool is refused (`consent-required`) with the command a person runs to confirm (`evh consent grant …`, which writes a
  one-use consent the next call can consume).
- **Budgets**: the server keeps a ledger (`.evh/spend.jsonl`) of what its calls spent (from the commands' records) and
  refuses a call whose `--dry-run` estimate would cross a limit without consent.
- What the server cannot stop: an agent with a shell can run `evh` directly or edit files. The records say who acted;
  the skills tell agents to use the server.

### Skills

- Shipped as package data under `evaluation_harness/skills/<name>/SKILL.md` (with `references/` where needed), in the
  Agent Skills format: front matter `name` (lowercase, matching its directory), `description` (what it does and when to
  use it), `metadata: {harness-version: "0.5.0"}`; under 500 lines; it links the documentation pages it relies on.
- The set: `evh-evaluate-a-system` (dataset, materialize, run, compare, choose), `evh-compare-and-read`,
  `evh-run-a-round`, `evh-run-a-study` (harness- or agent-driven, as the sampler with `study-ask`/`study-tell`),
  `evh-promote-with-evidence`, `evh-evaluate-a-pipeline` (stages, batch mode, the wrapping recipe), `evh-bring-runs-in`
  (`import-run`, `study-import`), `evh-follow-a-job`.
- Each says when to stop and ask (promotion, spending over the budget, a shared host, sending data out), whatever a
  project's own instructions say, and to prefer the MCP tools when they are available.
- `evh skills-install [--target DIR] [--force]` copies them into the project (`.claude/skills/` by default, or any agent's
  skill directory); it refuses to overwrite a changed copy without `--force`.
- **Tested**: every fenced block tagged `evh` in a skill runs against the example project in CI, in order, with its
  expected exit code; a skill whose commands fail fails the build.

### llms.txt and the glossary

- `site/mkdocs_hooks.py` writes `llms.txt` at the documentation root on build: the site's title and summary, then each
  page with its title, URL and first sentence, grouped by the navigation's sections (llms.txt v2). The site root links
  it.
- `docs/GLOSSARY.md`: each harness term (arm, run, adapter, reference, gold, silver, goal, round, study, trial, sampler,
  champion, look, separated, non-inferior, inconclusive) with its meaning and the word other tools use (Inspect,
  LangSmith, promptfoo, HELM, Optuna, MLflow), and where the meaning differs, how.

### The scenario test (PRD-012 FR8.2)

`harness/tools/agent_scenario.py` (a release check, not a command) runs an agent CLI headless (Claude Code's `claude
-p` with the project's MCP configuration; another agent CLI may be named) on the example project with the instruction of
PRD-012's first user story and a hard dollar cap, then checks the records: a study round with trials, reasons and an
actor; a refused promotion without consent; the goal page built. It needs the person's API key and is run before each
release, recorded in `RELEASING.md`, not in CI.

## Migration

None. The server and skills are new; `UPGRADING.md` says how to add `evh mcp` to an agent's MCP configuration and run
`evh skills-install`.

## Alternatives Considered

- **Run tools in-process.** Rejected: commands keep module-level state (the catalog's `API`, `HEAD`, `BRAND`), and a
  child process gives a tool exactly the command's behaviour, refusals and exit codes.
- **A hand-written MCP server.** Rejected by the owner earlier: the SDK tracks the protocol.
- **Trust the client's name for the actor.** Rejected: the specification says not to.
- **Only MCP tasks for long work.** Rejected for now: the SDK does not implement the extension; the job id works
  everywhere and stays as the fallback.
- **Serve skills over MCP only.** Deferred until MCP's skills extension settles; files work with every agent harness
  today.

## Testing

- `harness/tests/test_mcp_server.py` (an in-memory client from the SDK): the tool list equals the manifest; a read tool's
  `structuredContent` validates against its output schema; a refusal is `isError` with a problem details body; a
  long-running tool returns a job set id; a consent tool asks (elicitation) and refuses without it; a disabled tool is
  absent; the actor recorded is the server's `--agent` acting for the limits file's person.
- `harness/tests/test_skills.py`: front matter valid and matching directories; under 500 lines; every `evh` block runs on
  the example project.
- `site/test_browser.py` or a docs check: `llms.txt` lists every page in the navigation.

## Decisions (ADR candidates)

1. `evh mcp` on the official SDK; tools generated from the manifest, each run as a child `evh … --json`.
2. Long work returns a job id followed with `jobs-status`; MCP tasks when the SDK supports them.
3. Consent through elicitation, refused when the client cannot ask; limits in a file the server never writes; the actor
   fixed at start, never from the client.
4. Skills ship with the package in the Agent Skills format, installed by a command, and their commands are tested.
5. `llms.txt` generated with the documentation; a glossary maps terms to other tools'.
