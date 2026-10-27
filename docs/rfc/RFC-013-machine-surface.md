# RFC-013: The machine surface: one declaration per command, JSON, exit codes, refusals, the actor, the project config

- **Status**: Draft (0.5.0), revision 2 (2026-10-27): consent is a person running the command, or an elicitation the
  person's limits allow; no grant store
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-012](../prd/PRD-012-agent-ready.md) (FR1, FR2, FR3, FR7, FR10), and every 0.5.0 PRD
  through PRD-012 FR8
- **Related RFCs**: RFC-016 (the MCP server and skills, built on this), RFC-011 (long work detached as jobs),
  RFC-014 (identity)
- **Code**: `harness/scripts/cli.py` (imports commands instead of `runpy`), `_common.py`, new `_command.py`,
  `_consent.py`, `_refusals.py`, every command script (about 50), `harness/schemas/`, `harness/pyproject.toml`,
  `ruff.toml` (`target-version`), `.github/workflows/harness-package.yml`

## Abstract

Every `evh` command declares itself once, beside its `argparse` parser: name, purpose, what it touches (reads,
writes, spends), whether it runs long, its output schema and its examples. From that one declaration come the
`--help` text, `evh commands --json` (the manifest), and in RFC-016 the MCP tools. Each command separates
computing its result from printing it, so `--json` prints the result and the table is drawn from the same
data. Results go to stdout and everything else to stderr; exit codes are a documented table; refusals are RFC
9457 problem details with a stable `type`; every record a command writes says who acted and for whom. The
project's `config.yaml` becomes the one place its directories, runners and limits live. 0.5.0 requires Python
3.10 or later.

## Problem Statement

- `cli.py` maps a name to a script and a one-line help (`COMMANDS`); each script builds its parser inside
  `main()`, so nothing describes a command's arguments outside running it. 23 of 28 parsers show only their
  docstring's first line; several print `usage: promote_baseline.py`.
- No command has machine-readable output; scripts compute and print in the same loop.
- `experiment-run` has 35 `print` calls, one to stderr: progress and results share stdout.
- `die()` exits 1 for every refusal (`_common.py:465`), and 29 more sites raise `SystemExit("…")` directly (e.g.
  `_common.py:107, :356`); 1 also means "nothing measured" (`experiment_run.py:879`) and a failed `validate`; 2 means
  the cost cap (`:884`), an unknown command (`cli.py:125`) and argparse's usage error.
- `cli.py:131` runs each script through `runpy`, so a script's module state exists only while it runs; importing the
  scripts to describe them would run module-level code a second time beside it.
- Records do not say who made them; an agent's work and a person's look the same.
- The project root, data, runs and goals directories come from `EVAL_*` variables; `config.yaml` is read only
  for `catalog.adapter` (`catalog_adapter.py:800`).
- `schemas/` has no run record, fingerprint or prediction schema.
- `requires-python = ">=3.9"` and `ruff.toml:8` `target-version = "py39"`; the official MCP SDK (RFC-016) requires
  3.10.

## Design

### One declaration per command (`_command.py`)

```python
from evaluation_harness._command import Command, Effect, Consent

def _parser() -> argparse.ArgumentParser: ...   # the arguments, as today, with prog="evh run-promote"
def _run(args) -> dict: ...                     # computes; returns the result (JSON-serialisable); raises Refusal
def _render(result: dict) -> str: ...           # the table a person reads (optional; default: a generic one)

COMMANDS = [Command(
    name="run-promote",
    purpose="make a run the current baseline of its goal on its dataset",
    parser=_parser, run=_run, render=_render,
    effects={Effect.WRITES},          # READS (default), WRITES, SPENDS; SPENDS implies a cost estimate in --dry-run
    long_running=False,               # True: may run long; detached as a job (RFC-011), an MCP job in RFC-016
    serves=False,                     # True for a command that never returns (catalog-serve, mcp)
    idempotent=False,                 # running it twice with the same arguments changes nothing more
    open_world=False,                 # it calls outside the project (a provider, a runner host)
    consent=[Consent.PROMOTE, Consent.EXTRA_LOOK],   # the kinds it may ask for, at run time (below)
    override_flags=["--allow-dirty", "--allow-unknown-build", "--allow-failed"],  # each needs consent when used
    output="baseline-version",        # a schema in schemas/ (by name)
    examples=['evh run-promote --run run:runs/cnn_bart_l_v1_20261026T153757.123Z_7f3a --reason "best ROUGE-L, half the cost"'],
)]
```

- A module lists its commands in `COMMANDS`, so one module may hold several (`rounds.py` serves `round-open`,
  `round-close`, `round-retire` and `rounds`, today through four-line shim scripts, which go).
- `cli.py` imports the module (`importlib.import_module`) and calls `_command.main(command)`; `runpy` goes, so a
  module's state exists once whether the manifest is built or a command runs. A script still runs as a file
  (`python scripts/x.py`, its `if __name__ == "__main__"` calls the same `main`) and through `make`.
- `_command.main(command)` parses with `parser()`, adds the common options **unless the parser already defines them**
  (`--json`; `--dry-run` when the command writes or spends; `--actor`, `--on-behalf-of`, `--instruction`; `--confirm`
  when it declares consent kinds), calls `run`, and prints `render(result)` or the JSON. The scripts that define
  `--dry-run` today (`experiment_run.py:542`, `judge_score.py:1094`, `sweep.py:41`) drop their own and read the common
  one. **`--dry-run` is honoured by `run()`**: it computes and returns the plan, writes no record and calls no provider,
  runner or sampler; a test runs every command with `--dry-run` on the example project with a provider that fails when
  called and checks that no file under the project changed.
- `--help` is generated: `usage: evh <name> …`, the purpose, the full docstring, the examples, the effects.
- **The manifest**: `evh commands --json` lists every command: name, purpose, effects, long_running, serves,
  idempotent, open_world, consent kinds, override flags, arguments (from the parser's actions: name, type, required,
  default, choices, help, repeatable), the output schema's name and version, examples. `cli.COMMANDS` is generated from
  the declarations.
- **A test** fails when a command lacks a declaration, when its parser's arguments are not described, or when its
  `--json` output does not validate against its schema on the example project.

### Results and progress

- `run()` returns data; `render()` draws the table from it. `--json` prints the envelope `{"command": name,
  "version": schema_version, "result": …}` (`schemas/envelope.schema.json`, whose `result` is the command's output
  schema).
- **Commands without a single result**: a `serves` command (`catalog-serve`, `mcp`) never returns and takes no
  `--json`; `init` returns the files it created; `self-test` returns each check with its outcome; `jobs-run` returns
  the set id (and with `--wait`, the set's final state).
- Progress, notes and warnings go through `_common.say()` (stderr). Nothing else prints to stdout. A test runs each
  command on the example project and fails when its stdout is not exactly its rendered result.
- No command waits for input; `--no-input` is accepted everywhere and changes nothing (there is nothing to disable).

### Exit codes (`_common.EXIT`)

| code | meaning | today |
| --- | --- | --- |
| 0 | success | 0 |
| 1 | refusal (a problem details object on stderr, or as JSON with `--json`) | 1 |
| 2 | usage error (argparse) | 2, also the cost cap and an unknown command |
| 3 | a judge scorer not validated (unchanged) | 3 |
| 4 | stopped by a budget or the cost cap; partial results kept | 2 (`experiment_run.py:884`) |
| 5 | partly failed: a job set (`jobs-run --wait`) or a study in which some jobs or trials failed; results kept | — |
| 6 | a check found problems: `validate`, `evidence-check`, `adapter-check`, `skills-check` | 1 |
| 7 | the system under test failed: nothing measured | 1 (`experiment_run.py:879`) |
| 65 to 78 | operational errors, sysexits meanings (65 bad input data, 66 missing input, 69 unavailable service, 70 internal error, 73 cannot create output, 74 I/O error, 75 temporary failure, 77 permission, 78 configuration) | 1 |
| 130 | interrupted | 130 (SIGINT), with a traceback on stderr |

An unknown command becomes 2 (a usage error), which it already is. Ctrl-C keeps 130 and loses the traceback. The
release notes list each change.

**Converting the 0.4.0 exits.** Each of the 153 `die(` calls and the 29 raw `SystemExit("…")` sites is classified as
it is converted: a refusal of a request (`refuse(code, …)`, exit 1, with a registry entry), bad or missing input data
(65, 66), a configuration error (78), a service that is not there (69), or an internal error (`die`, 70). The
conversion is mechanical but each call is read once; a test fails on any `die(` or `SystemExit("…")` left outside
`_common.py`.

### Refusals (RFC 9457)

`_common.refuse(code, title, detail, fix=None, **extra)` raises `Refusal`; `die(msg)` stays for internal errors and
maps to 70. A refusal prints, without `--json`, `ERROR (<code>): <title>\n  <detail>\n  fix: <fix>` on stderr; with
`--json`, on stdout:

```json
{"type": "https://evals.humancopilot.eu/docs/refusals/#dirty-build", "title": "The run was produced by a dirty tree",
 "detail": "build.ref=1a2b3c4d does not describe what ran.", "code": "dirty-build", "exit_code": 1,
 "fix_command": "evh experiment-run --config …"}
```

`type` is the identity (a page listing every code, generated from a registry in `_refusals.py`, so a code cannot be
used without its entry); `code` is its last segment and `exit_code` the process's exit code, both extension members.
RFC 9457's `status` member means an HTTP status code, so it is not used. A refusal that needs consent carries
`consent: {kind, command, amount}` (below) and `for_the_agent`, one sentence telling an agent to ask the
person to run the fix command and not to run it itself ([UXS-005](../uxs/UXS-005-agents.md#consent-from-both-sides)).

### Who acted (PRD-012 FR3)

- `--actor` or `EVH_ACTOR`: `person:<name>` or `agent:<name>` plus `--on-behalf-of person:<name>` (or
  `EVH_ON_BEHALF_OF`). `--instruction TEXT` or `EVH_INSTRUCTION`.
- **Without either**: `person:<OS user>` when stdin is a terminal (a person typing), and `unknown:<OS user>` when it is
  not (an agent's shell tool, a script, CI). Agent shells do not run commands on a terminal, so an agent that does not
  name itself is not recorded as a person; CI sets `EVH_ACTOR=person:<name>` or `agent:ci`.
- `_record.actor()` returns `{"type": "person"|"agent"|"unknown", "name": …, "on_behalf_of": …}` (PROV's
  `actedOnBehalfOf`); every record a command writes carries `actor` (and `instruction` when given) beside its reason.
  RFC-016's server sets them itself.

### Consent (PRD-012 FR4.5, PRD-009 FR4.4)

Consent is asked for at run time, when the condition arises, not by a fixed flag: a command declares the kinds it may
ask for (`promote`, `retire`, `spend_over_budget`, `extra_look`, `override_refusal`, `data_egress`, `shared_host`) and
calls `_consent.require(kind, detail, amount)` when one applies (a promotion; a look past the protective limit; an
override flag used; a phase on a shared host; a remote sampler that sees data). Consent is **a person's, never only an
agent's**:

- a **person actor** consents by running the command: the refusal an agent gets carries the exact command
  (`fix_command`), and the person runs it in their own terminal with `--confirm`, recorded as `confirmed_by:
  <person>, via: cli`. Detached work waiting for consent (RFC-011, RFC-010) is continued the same way: `evh
  jobs-run --resume <id> --confirm` or `evh study-run --resume <id> --confirm`;
- an **MCP elicitation** answer, only for the kinds the person's limits file lists (RFC-016), recorded `via:
  elicitation (client-reported)`.

`--confirm` from an `agent:` or `unknown:` actor is refused (`consent-required`). Nothing is stored between asking and
consenting: the person's own command is the consent. What the harness cannot do: tell a person from an agent that
claims to be one (`EVH_ACTOR=person:…`). The records show what was claimed and how; the skills tell agents never to;
and `validate` lists every consent with its route so a person can audit them. Real permissions (who may promote)
come with the database provider (RFC-017).

### The project config (PRD-012 FR10)

`config.yaml` at the project root (found as today: `EVAL_HOME`, else upward from the working directory):

```yaml
data_dir: data            # EVAL_DATA_DIR wins
runs_dir: data/runs       # EVAL_RUNS_DIR wins
goals_dir: data/goals     # EVAL_GOALS_DIR wins
catalog: {adapter: tools/my_adapter.py:Adapter, publish: [prompts]}   # publish: what static pages may carry (RFC-009)
runners: {dgx: {type: ssh, host: dgx-llm-1, …}}      # RFC-011
limits: evh-limits.yaml                               # RFC-016: tracked, so git records who changed it
```

`_common` resolves every path once from it (environment, then config, then default) and records where each value came
from; `evh config --json` prints that. `schemas/config.schema.json` validates it.

### Schemas (PRD-012 FR7)

New, versioned with the harness (`$id` carries the version): `run.schema.json` (`run.json`), `metrics.schema.json`
(exists; gains the v5 fingerprint), `fingerprint.schema.json` (v5), `prediction.schema.json` (a `predictions.jsonl`
line, stages included, RFC-007), `baseline.schema.json` (RFC-014)
(RFC-015), `study.schema.json` and `trial.schema.json` (RFC-010), `job-set.schema.json` (RFC-011),
`prompt-version.schema.json` (RFC-009), `study-spec.schema.json` (RFC-010), `baselines-export.schema.json` (RFC-012),
`job-state.schema.json` (RFC-011), `process-adapter.schema.json` and `schemas/protocol/` (RFC-008),
`limits.schema.json` (RFC-016), `study-event.schema.json` (RFC-010), `config.schema.json`,
`refusal.schema.json`, `envelope.schema.json`, and one output schema per command. `validate` checks every record
against its schema.

### Python 3.10

`requires-python = ">=3.10"` and `ruff.toml` `target-version = "py310"`; the package CI matrix becomes 3.10, 3.11, 3.14
(`harness-package.yml:28`). Code may use 3.10 syntax (`match`, `X | Y` at runtime). The README, `UPGRADING.md` and the
release notes say so.

## Migration

No data migration. Scripts move to the declaration one by one; the manifest test lists the ones still missing, and the
release needs none missing. Exit-code and refusal changes are listed in the release notes; the podcast project's scripts
that read exit codes (`scripts/harness/import_*.py` calling `evh import-run`) are checked against the new table before its
pin moves.

## Alternatives Considered

- **A CLI framework (Click, Typer).** Rejected: a dependency and a rewrite of every parser, for what `argparse`
  introspection already gives.
- **Declarations in one central file.** Rejected: the arguments live in the script; a central list drifts from them,
  which is the 0.4.0 problem.
- **Parse the human output for agents.** Rejected: fragile, and it is what PRD-012 exists to remove.
- **sysexits for everything (64 for usage).** Rejected for usage: argparse uses 2 and every Python user expects it; kept
  for the operational errors.
- **Keep Python 3.9 with MCP only on 3.10+.** Rejected by the owner: one install, every feature; 3.9 is past its end of
  life.

## Testing

- `harness/tests/test_manifest.py`: every command declared; arguments described; examples parse; `evh commands --json`
  validates against its schema.
- `harness/tests/test_json_outputs.py`: each read command's `--json` on the example project validates against its
  output schema; stdout equals the rendered result without `--json`.
- `harness/tests/test_exit_codes.py`: a refusal exits 1 with a problem details body; a usage error 2; a judge not validated 3; nothing measured 7;
  the cost cap 4; a partly failed job set 5; a failed `validate` 6; Ctrl-C 130; no `die(` or `SystemExit("…")` outside
  `_common.py`.
- `harness/tests/test_dry_run.py`: every command with `--dry-run` writes nothing and calls no provider.
- `harness/tests/test_actor.py`: records carry the actor and instruction; without `EVH_ACTOR` and no terminal the actor is
  `unknown:`; a person's `--confirm` passes and an agent's is refused; the refusal carries the exact command,
  and nothing is stored between the refusal and the person's run.
- `harness/tests/test_config.py`: precedence environment > config > default; `evh config --json` names the source.

## Decisions (ADR candidates)

1. Each command declares itself once beside its `argparse` parser; help, the manifest and the MCP tools are generated.
2. Results on stdout, everything else on stderr; `--json` everywhere, with an output schema per command.
3. A documented exit-code table (0, 1 refusal, 2 usage, 3 judge not validated, 4 budget, 5 partly failed, 6 check
   failed, 7 nothing measured, 65–78, 130); splitting 1 and 2 is a breaking change, and no code changes meaning.
4. Refusals are RFC 9457 problem details with a stable `type`, a registry, and `exit_code` as an extension member.
5. Every record says who acted and for whom (PROV); an actor that does not name itself off a terminal is `unknown`.
6. One project `config.yaml` for directories, runners and limits; environment variables still win.
7. Python 3.10 or later, so the official MCP SDK can be a default dependency.
8. Consent is asked at run time by kind, and is a person's: their own command (`--confirm`), or an
   elicitation the person's limits allow; an agent's own `--confirm` is refused.
