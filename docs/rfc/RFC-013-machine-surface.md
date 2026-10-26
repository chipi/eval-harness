# RFC-013: The machine surface: one declaration per command, JSON, exit codes, refusals, the actor, the project config

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-012](../prd/PRD-012-agent-ready.md) (FR1, FR2, FR3, FR7, FR10), and every 0.5.0 PRD
  through PRD-012 FR8
- **Related RFCs**: RFC-016 (the MCP server and skills, built on this), RFC-011 (long work detached as jobs),
  RFC-014 (identity)
- **Code**: `harness/scripts/cli.py`, `_common.py`, a new `_command.py`, every command script (about 50),
  `harness/schemas/`, `harness/pyproject.toml`, `.github/workflows/harness-package.yml`

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
- `die()` exits 1 for every refusal (`_common.py:465`); 1 also means "nothing measured"
  (`experiment_run.py:878`); 2 means the cost cap (`:884`), an unknown command (`cli.py:125`) and argparse's usage
  error.
- Records do not say who made them; an agent's work and a person's look the same.
- The project root, data, runs and goals directories come from `EVAL_*` variables; `config.yaml` is read only
  for `catalog.adapter` (`catalog_adapter.py:800`).
- `schemas/` has no run record, fingerprint or prediction schema.
- `requires-python = ">=3.9"`; the official MCP SDK (RFC-016) requires 3.10.

## Design

### One declaration per command (`_command.py`)

```python
from evaluation_harness._command import Command, Effect

COMMAND = Command(
    name="run-promote",
    purpose="make a run the current champion of its goal on its dataset",
    effects={Effect.WRITES},          # READS (default), WRITES, SPENDS; SPENDS implies a cost estimate in --dry-run
    long_running=False,               # True: runs as a job (RFC-011) when detached, an MCP job in RFC-016
    needs_consent=True,               # PRD-012 FR4.5: promotion, retiring, spending over budget, overrides
    output="champion-version",        # a schema in schemas/ (by name)
    examples=['evh run-promote --run runs/cnn_bart_l_v1_20261026T153757.123Z_7f3a --reason "best ROUGE-L, half the cost"'],
)

def parser() -> argparse.ArgumentParser: ...   # the arguments, as today, with prog="evh run-promote"
def run(args) -> dict: ...                     # computes; returns the result (JSON-serialisable); raises Refusal
def render(result: dict) -> str: ...           # the table a person reads (optional; default: a generic one)
```

- `_command.main(module)` is every script's `main()`: it parses with `parser()`, adds the common options (`--json`,
  `--dry-run` when the command writes or spends, `--actor`, `--instruction`, `--confirm` when it needs consent), calls
  `run`, and prints `render(result)` or the JSON. The scripts keep running as files (`python scripts/x.py`) and through
  `make`, as today.
- `--help` is generated: `usage: evh <name> …`, the purpose, the full docstring, the examples, the effects.
- **The manifest**: `evh commands --json` lists every command: name, purpose, effects, long_running, needs_consent,
  arguments (from the parser's actions: name, type, required, default, choices, help, repeatable), the output schema's
  name and version, examples. `cli.COMMANDS` is generated from the declarations (the script file is the module).
- **A test** fails when a command lacks a declaration, when its parser's arguments are not described, or when its
  `--json` output does not validate against its schema on the example project.

### Results and progress

- `run()` returns data; `render()` draws the table from it. `--json` prints `{"command": name, "version":
  schema_version, "result": …}`.
- Progress, notes and warnings go through `_common.say()` (stderr). Nothing else prints to stdout. A test runs each
  command on the example project and fails when its stdout is not exactly its rendered result.
- No command waits for input; `--no-input` is accepted everywhere and changes nothing (there is nothing to disable).

### Exit codes (`_common.EXIT`)

| code | meaning | today |
| --- | --- | --- |
| 0 | success | 0 |
| 1 | refusal (a problem details object on stderr, or as JSON with `--json`) | 1 |
| 2 | usage error (argparse) | 2, also the cost cap and an unknown command |
| 3 | the system under test failed: nothing measured | 1 (`experiment_run.py:878`) |
| 4 | stopped by a budget or the cost cap; partial results kept | 2 (`experiment_run.py:884`) |
| 65 to 78 | operational errors, sysexits meanings (65 bad input data, 66 missing input, 69 unavailable service, 73 cannot create output, 74 I/O error, 75 temporary failure, 77 permission, 78 configuration) | 1 |
| 130 | interrupted | Python's traceback |

An unknown command becomes 2 (a usage error), which it already is. The release notes list each change.

### Refusals (RFC 9457)

`_common.refuse(code, title, detail, fix=None, **extra)` raises `Refusal`; `die(msg)` stays for internal errors and
maps to 70. A refusal prints, without `--json`, `REFUSED (<code>): <title>\n  <detail>\n  fix: <fix>` on stderr; with
`--json`, on stdout:

```json
{"type": "https://evals.humancopilot.eu/docs/refusals/#dirty-build", "title": "The run was produced by a dirty tree",
 "status": 1, "detail": "build.ref=1a2b3c4d does not describe what ran.", "code": "dirty-build",
 "fix_command": "evh experiment-run --config …"}
```

`type` is the identity (a page listing every code, generated from a registry in `_refusals.py`, so a code cannot be
used without its entry); `code` is its last segment, an extension member for readers that prefer a short key;
`status` is the exit code. The 0.4.0 refusals (153 `die(` occurrences across the scripts, the definition included)
are converted by kind.

### Who acted (PRD-012 FR3)

- `--actor` or `EVH_ACTOR`: `person:<name>` or `agent:<name>` plus `--on-behalf-of person:<name>` (or
  `EVH_ON_BEHALF_OF`); without either, `person:` and the OS user name. `--instruction TEXT` or `EVH_INSTRUCTION`.
- `_record.actor()` returns `{"type": "person"|"agent", "name": …, "on_behalf_of": …}` (PROV's `actedOnBehalfOf`);
  every record a command writes carries `actor` (and `instruction` when given) beside its reason. RFC-016's server sets
  them from the limits file and the person's answers.
- `--confirm` (and `EVH_CONFIRM_BY=person:<name>`): a command that needs consent refuses without it (code
  `consent-required`), and records who confirmed. An agent with a shell can pass it; PRD-012 says so, and the record
  shows that an agent confirmed.

### The project config (PRD-012 FR10)

`config.yaml` at the project root (found as today: `EVAL_HOME`, else upward from the working directory):

```yaml
data_dir: data            # EVAL_DATA_DIR wins
runs_dir: data/runs       # EVAL_RUNS_DIR wins
goals_dir: data/goals     # EVAL_GOALS_DIR wins
catalog: {adapter: tools/my_adapter.py:Adapter}
runners: {dgx: {type: ssh, host: dgx-llm-1, …}}      # RFC-011
limits: .evh/limits.yaml                              # RFC-016
```

`_common` resolves every path once from it (environment, then config, then default) and records where each value came
from; `evh config --json` prints that. `schemas/config.schema.json` validates it.

### Schemas (PRD-012 FR7)

New, versioned with the harness (`$id` carries the version): `run.schema.json` (`run.json`), `metrics.schema.json`
(exists; gains the v5 fingerprint), `fingerprint.schema.json` (v5), `prediction.schema.json` (a `predictions.jsonl`
line, stages included, RFC-007), `champion.schema.json` and `champion-index.schema.json` (RFC-014), `look.schema.json`
(RFC-015), `study.schema.json` and `trial.schema.json` (RFC-010), `job-set.schema.json` (RFC-011),
`prompt-version.schema.json` (RFC-009), `config.schema.json`, `refusal.schema.json`, and one output schema per command.
`validate` checks every record against its schema.

### Python 3.10

`requires-python = ">=3.10"`; the package CI matrix becomes 3.10, 3.11, 3.14 (`harness-package.yml:28`). Code may use
3.10 syntax (`match`, `X | Y` at runtime). The README, `UPGRADING.md` and the release notes say so.

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
- `harness/tests/test_exit_codes.py`: a refusal exits 1 with a problem details body; a usage error 2; nothing measured 3;
  the cost cap 4; Ctrl-C 130.
- `harness/tests/test_actor.py`: records carry the actor and instruction; `--confirm` required where declared.
- `harness/tests/test_config.py`: precedence environment > config > default; `evh config --json` names the source.

## Decisions (ADR candidates)

1. Each command declares itself once beside its `argparse` parser; help, the manifest and the MCP tools are generated.
2. Results on stdout, everything else on stderr; `--json` everywhere, with an output schema per command.
3. A documented exit-code table (0, 1 refusal, 2 usage, 3 system failed, 4 budget, 65–78, 130), a breaking change.
4. Refusals are RFC 9457 problem details with a stable `type` and a registry.
5. Every record says who acted and for whom (PROV), and consent is recorded.
6. One project `config.yaml` for directories, runners and limits; environment variables still win.
7. Python 3.10 or later, so the official MCP SDK can be a default dependency.
