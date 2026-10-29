# PRD-007: One install, your own keys

- **Status**: Implemented (v0.4.0); installable since 0.2.0; Python 3.10 and the MCP SDK from 0.4.5 (unreleased)
- **Authors**: Marko Dragoljevic
- **Related UX spec**: [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the command line and the first evaluation)
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md)

## Summary

The harness is one Python package, `evaluation-harness`, with one command, `evh`. A project pins
a release from GitHub, runs `evh init`, and keeps all of its data in its own folder; an upgrade
changes code and never touches results. One install enables every feature, including calling
hosted models: the user brings their own keys (OpenAI, Anthropic, OpenRouter, or a LiteLLM
proxy), and an offline `echo` provider runs the whole tutorial with no key at all. The same
providers are used by experiment arms and by LLM judges, with optional separate keys for judging.
The system under test plugs in through one file, `adapter.py`, at the project root.

## Background & Context

Until 0.2.0 the harness was a copy taken into a project. Packaging it separated code from data.
In 0.4.0 the hosted-model clients moved from an optional extra into the core: a newcomer's first
hosted arm failed on the import, and only one Runbook section named the extra. The GUIDE became
a walkthrough in the user's own project, not inside a checkout of this repository.

## Goals

- One install command; no extras to discover for any documented feature.
- The project owns its data; the package holds code and schemas only.
- Any command works from any subfolder of the project.
- Hosted models are called with the user's own keys; nothing is billed through this project.
- Spend is capped on request, and a key set without a cap is pointed out.
- The integration seam is one function the user writes (`call_system`), plus `score`.

## Non-Goals

- Not on PyPI: the name `eval-harness` there belongs to an unrelated project; install only from
  GitHub.
- No hosted service and no accounts: the package runs on the user's machine.
- No bundled model weights or ML framework: a project brings its own weight, and the core only
  records what is installed.

## Personas

- **The newcomer** following the GUIDE, offline, in fifteen minutes.
- **The engineer integrating an existing system**, in any language, behind one Python function.
- **The team** pinning a release in CI.

## User Stories

- _As a newcomer, I can install the package, run `evh init --tutorial`, and follow the GUIDE
  with no API key._
- _As an engineer, I can put `adapter.py` at my project root and every arm that names no
  adapter uses it._
- _As an engineer, I can call OpenAI, Anthropic, OpenRouter or my LiteLLM proxy from the bundled
  adapter by setting a key, without installing anything else._
- _As an engineer, I can check my environment and keys without printing them (`evh env-check`)._
- _As a team, I can check that the installed harness works here (`evh self-test`) after an
  upgrade._

## Functional Requirements

### FR1: The package

- **FR1.1**: `pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.4.4#subdirectory=harness"`
  installs the package and the `evh` command; Python 3.10 or later (from 0.4.5, the MCP SDK's floor; 3.9 before).
- **FR1.2**: Its dependencies are `pyyaml`, `jsonschema`, `openai`, `anthropic` and (from 0.4.5) `mcp`; there is no
  optional extra for any user feature (the `test` extra serves the self-test's corpus checks).
- **FR1.3**: The package holds the harness's code, schemas, the catalog's assets and the
  tutorial kit, not this repository's tests or data.
- **FR1.4**: In a checkout of this repository, every command is also a `make` target running the
  same script.

### FR2: The project

- **FR2.1**: `evh init [--tutorial]` creates the data folders and a `.gitignore`; `--tutorial`
  adds the GUIDE's kit.
- **FR2.2**: The project root is `EVAL_HOME`, else the nearest directory up with a `data/`
  folder; `EVAL_DATA_DIR`, `EVAL_RUNS_DIR` and `EVAL_GOALS_DIR` move the data, the runs and the
  goals.
- **FR2.3**: `.env` is read when a command starts, not on import; importing the package changes
  nothing.
- **FR2.4**: `evh self-test` in a project checks the installed harness: the paired test's own
  suite, then the tutorial end to end in a scratch folder.

### FR3: The system under test

- **FR3.1**: `adapter.py` at the project root is the default adapter for an arm with no
  `adapter:`; a config may name another; without either, the bundled adapter runs.
- **FR3.2**: The bundled adapter's providers are `echo` (offline), `openai`, `openrouter`,
  `anthropic` and `litellm`; an unknown `provider:` is refused. Judges use the same providers
  (plus `fake` offline), with `provider:` declared on each judge in the scorer.
- **FR3.3**: Keys come from the environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `OPENROUTER_API_KEY`, `LITELLM_API_KEY` with `LITELLM_BASE_URL`); a config can name another
  variable (`api_key_env`) and endpoint (`base_url`). Judges read `EVAL_JUDGE_<VAR>` first
  (for their own keys and budgets), then fall back to `<VAR>` to share the arms' credentials.
- **FR3.4**: `evh env-check` reports which keys are set by length and shape only, never the
  key, warns when a key is set and `EVAL_MAX_COST_USD` is not, and shows which providers
  arms and judges can call.

## Success Criteria

- The package's CI job (`.github/workflows/harness-package.yml`) installs the wheel on Python
  3.10, 3.11 and 3.14 and runs `evh self-test`.
- `harness/tests/test_installed_commands.py` runs every `evh` command in a project that pins the
  package.

## Related Documents

- [GUIDE](../GUIDE.md), [Integration](../../harness/docs/INTEGRATION.md),
  [Upgrading](../../harness/docs/UPGRADING.md).
