# RFC-016: The MCP server, the skills, llms.txt and the glossary

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-012](../prd/PRD-012-agent-ready.md) (FR4, FR5, FR6, FR8)
- **Related RFCs**: RFC-013 (the command declarations this is generated from), RFC-011 (jobs), RFC-010 (studies:
  `study-ask`, `study-tell`)
- **Code**: new `harness/scripts/mcp_server.py` (`evh mcp`), `harness/skills/` (package data
  `evaluation_harness.skills`), `skills_install.py` (`evh skills-install`), `site/mkdocs_hooks.py` (llms.txt),
  `docs/GLOSSARY.md`; `pyproject.toml` (the dependency, package data for `skills/**`); dependency `mcp>=2.3,<3`

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
- The official SDK `mcp` 2.3.0 supports the 2026-07-28 revision, tool annotations, structured output, resources and
  elicitation (form and URL); it has a hook for extensions but no handler for the tasks extension. It requires Python
  3.10 (RFC-013 moves the harness there).
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
  command's result schema inside (`{command, version, result}`, what stdout carries).
- **Not tools**: commands that never return (`catalog-serve`, `mcp`), and the ones only a person runs: `consent`
  (grants), `skills-install` (it writes the instructions agents follow) and `init`. The server's own `limits` tool
  is read-only.
- **What the input schema leaves out**: `--actor`, `--on-behalf-of` and `--confirm`. The server sets the actor itself;
  consent comes from the person (below), never from an argument. `--instruction` stays, recorded as the agent reported
  it. Override flags (`--allow-dirty`, …) stay, and using one triggers consent of kind `override_refusal`.
- **Paths**: an argument the parser types as a path is resolved before the call; one that lands in `.evh/`, on the
  limits file, or outside the project root is refused (`path-not-allowed`), so no tool (`prompt-export --to`, a
  `--out`) can overwrite what governs the server.
- **A call** runs `evh <command> <args> --json --actor agent:<name> --on-behalf-of <person>` as a child process in its
  own process group, with the server's environment and a timeout (the command's declared `timeout_s`, default 600 s
  for a command that is not long-running). Cancelling the request, or the timeout, kills the process group. stdout (the
  JSON result) becomes `structuredContent`, capped at 1 MB (beyond it the tool returns an error naming the command's
  `--limit`/`--offset` paging, which list commands declare); stderr is kept as the tool's log text, its last 64 KB; a
  refusal (exit 1) becomes a result with `isError: true` and the problem details body.
- **Parallel calls** write records through the same lock helper as the commands do (RFC-014 `_lock.py`), so two tools
  promoting, recording a look or a prompt version at once cannot collide.
- **Annotations** from the declaration: `readOnlyHint` when the command only reads; `destructiveHint` when it writes;
  `idempotentHint` and `openWorldHint` from the declaration's `idempotent` and `open_world`. They are hints for the
  client; the server's own checks (below) do not rest on them.
- **Resources** (templates, RFC 6570 with `{+var}` where a value holds `/`): `evh://runs/{+run}` (`runs/<run_id>`, the
  runs directory and id as in RFC-014's `run:` ids), `evh://goals/{goal_id}`, `evh://baselines/{goal}` (every dataset's
  baseline of the goal) and `evh://baselines/{goal}/{dataset}`, `evh://studies/{goal}/{study_id}`,
  `evh://prompts/{+name}`, `evh://looks/{dataset}`, `evh://datasets/{dataset_id}`. These include PRD-012 FR4.3's three
  (`evh://runs/{run_id}` there; a run id alone is ambiguous across runs directories, so the template takes the
  directory too, and a bare id resolves as `run-promote --run` does). Each returns the JSON a command would (`evh goals
  --goal … --json`), so an agent can read without a tool call.

### Long work

- A command declared `long_running` (`experiment-run`, `sweep`, `judge`, `rescore`) is started as a one-job set (RFC-011):
  the tool returns at once with `{"job_set": id, "status": "queued", "follow": "jobs-status", "stop": "jobs-stop"}`, and
  the agent follows it with the `jobs-status`,
  `jobs-logs` and `jobs-stop` tools (the protocol's pattern for stateful tools). Commands that detach by themselves
  (`jobs-run`, `study-run`) are called directly: they return an id at once and are never wrapped in a second set. A
  `rescore` of one run is declared long-running like any rescore: one rule per command, no guessing from arguments.
- **Consent during long work.** The tasks extension's input-required state is not available, so a detached set or
  study that needs consent part-way (a budget crossed, a look past the limit) stops that step and enters
  `waiting_consent` with the question in `state.json`. The next `jobs-status` or `study-status` tool call on it returns
  the elicitation (the same question and amount); the answer becomes a grant bound to that set or study, and the
  supervisor continues. Without an answer the step stays waiting, and nothing is spent.
- When the SDK implements the tasks extension and the client asks for a task, the same call returns a task instead;
  the job set's states map to task states as RFC-011 lists, and `waiting_consent` to `input_required`.

### Consent and limits

- **Limits file** (path in `config.yaml`, default `evh-limits.yaml` at the project root, `schemas/limits.schema.json`),
  written by the person, never by the server:
  ```yaml
  acting_for: person:marko
  tools: {disabled: [run-promote], read_only: false}
  budgets: {usd_per_day: 10, gpu_hours_per_day: 2, usd_per_study: 5}
  consent: [promote, retire, spend_over_budget, extra_look, override_refusal, data_egress, shared_host]
  elicitation_counts_as_consent: [spend_over_budget, shared_host]   # the kinds an elicitation answer may grant
  ```
- **Who changed it** (PRD-012 FR4.6): the file is tracked, and the server reads it from the committed tree. It reads the
  path from `config.yaml` once, at start; if the file has uncommitted changes, the server refuses to start (and, when
  they appear later, refuses calls) naming them, so every change in force is a commit with its author. Every record the
  server writes carries the commit of the limits in force. No tool writes it, and path arguments cannot reach it
  (above).
- **Consent** (RFC-013's model: a person's, never only an agent's). When a call would need consent (the command asks at
  run time for one of the limits' `consent` kinds; or the call would cross a budget), the server:
  - for a kind listed in `elicitation_counts_as_consent`, returns an input-required result with a form elicitation
    (the exact command, host and amount; one answer may cover a whole study or job set, with a count). The SDK's own
    documentation notes that an agent client may answer an elicitation itself, so an answer is recorded as `via:
    elicitation (client-reported)`, and only the kinds the person listed accept it;
  - for every other kind (by default promotion, retiring, an extra look, an override, data egress), refuses
    (`consent-required`) with the exact `evh consent grant …` command a person runs in their own terminal; the agent
    retries the call after, and the grant is consumed.
  The person's answer or grant is turned into a grant bound to the call's `args_sha256` before the child runs; the
  child consumes it. The server never passes `--confirm`.
- **Budgets**: the server keeps a ledger (`.evh/spend.jsonl`, `schemas/spend-ledger.schema.json`). Under a lock, a call
  reserves its `--dry-run` estimate before it runs (refused without consent if the reservation would cross a limit) and
  the reservation is replaced by the recorded spend after; so two concurrent calls cannot both pass a limit one of them
  would cross. The child gets `EVAL_MAX_COST_USD` set to the budget left, so `experiment-run`'s own cost cap stops it
  at the limit even when the estimate was low. Detached work spends after the tool returns, so the job and study
  supervisors write their spend into the same ledger as it happens, and stop at the limit. A sampler or judge with no
  estimate counts against the study's per-role cap (RFC-010), which a study under a server budget must declare.
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
- **Covered** (PRD-012 FR8.1): `evh skills-check` (exit 6 on a gap) fails when a command in the manifest is named by no
  skill and is not listed, with a reason, in `skills/NOT_IN_A_SKILL.md` (internal commands such as `self-test`).
- **Packaged**: `pyproject.toml` maps `evaluation_harness.skills` to `harness/skills` and includes `**/*.md` under it as
  package data, nested directories included; the package test installs the wheel and lists them.

### llms.txt and the glossary

- `site/mkdocs_hooks.py` writes `llms.txt` at the documentation root on build: the site's title and summary, then each
  page with its title, URL and first sentence, grouped by the navigation's sections (llms.txt v2). The site root links
  it.
- `docs/GLOSSARY.md`: each harness term (arm, run, adapter, reference, gold, silver, goal, round, study, trial, sampler,
  baseline, look, separated, non-inferior, inconclusive) with its meaning and the word other tools use (Inspect,
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
  `structuredContent` validates against the envelope schema; a refusal is `isError` with a problem details body; a
  long-running tool returns a job set id; a promotion is refused with a grant command and passes after the grant, and
  an elicitation does not grant it unless the limits list the kind; a kind the limits list is granted by elicitation;
  `--actor` and `--confirm` are not in any input schema; a path argument into `.evh/` or the limits file is refused;
  uncommitted limits refuse; two concurrent calls cannot both pass a budget; a cancelled call kills its child; output
  over 1 MB is refused with paging named; a set waiting for consent returns an elicitation from `jobs-status`;
  `catalog-serve`, `mcp`, `consent`, `skills-install` and `init` are not tools; a disabled tool is absent; the actor
  recorded is the server's `--agent` acting for the limits file's person.
- `harness/tests/test_skills.py`: front matter valid and matching directories; under 500 lines; every `evh` block runs on
  the example project.
- `site/test_browser.py` or a docs check: `llms.txt` lists every page in the navigation.

## Decisions (ADR candidates)

1. `evh mcp` on the official SDK; tools generated from the manifest, each run as a child `evh … --json`.
2. Long work returns a job id followed with `jobs-status`; MCP tasks when the SDK supports them.
3. Consent is a person's: a grant from their terminal, or an elicitation answer only for the kinds their limits allow;
   limits in a tracked file the server never writes and reads only when committed; the actor fixed at start, never
   from the client; actor and consent flags are never tool arguments.
4. Skills ship with the package in the Agent Skills format, installed by a command, and their commands are tested.
5. `llms.txt` generated with the documentation; a glossary maps terms to other tools'.
6. Tools run as child processes with a timeout, killed on cancel, with capped output; spending is reserved in a ledger
   under a lock, and detached work writes its spend as it happens.
