# RFC-018: A read-only MCP server in 0.4.5

- **Status**: Accepted (0.4.5), 2026-10-29: the owner's go on "a small read-only MCP server in 0.4.5, Python 3.9
  dropped there"
- **Authors**: Marko Dragoljevic
- **Related RFCs**: 0.5.0's RFC-013 (one declaration per command, `--json`, exit codes) and RFC-016 (the MCP server,
  skills, consent), on branch `050`: this is their first, read-only step, shipped early
- **Related UX specs**: [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the commands the tools are)
- **Code**: new `harness/scripts/mcp_server.py` (`evh mcp`), `harness/scripts/_jsonout.py` (`--json` for the view
  commands), `catalog_views.py`, `cli.py`; `harness/pyproject.toml` (`requires-python`, the dependency),
  `harness/requirements.txt`, `.github/workflows/harness-package.yml`; tests `harness/tests/test_mcp_server.py`

## Abstract

`evh mcp` serves one project to an agent over MCP (stdio), on the official Python SDK. Its tools are the harness's
read commands, the same commands a person runs: the catalog's views (`overview`, `datasets`, `dataset-items`, `arms`,
`goals`, `references`, `metrics`, `activity`, `search`), the inspector in the terminal (`inspect`), `rounds`,
`runs-list` and `validate`. Each call runs the command as a child process, so a tool answers exactly what the command
prints. No tool writes, spends or runs a model: running arms, promoting, retiring, judging and everything with a
consequence stay commands a person runs, until 0.5.0 brings the declarations, the actor and consent they need.

## Problem Statement

- An agent can use the harness only through a shell: run the `evh` commands, read their tables. The owner asked for the MCP server
  that 0.5.0 designs (RFC-016) to come forward, read-only first.
- The official SDK (`mcp` 2.3.0, PyPI 2026-10-29) requires Python 3.10; the package declares `>=3.9`
  (`harness/pyproject.toml:22`) and CI tests 3.9 (`harness-package.yml:28`). The owner's rule is one install with
  every feature (no extras), so the SDK becomes a dependency and 3.9 goes, in 0.4.5 instead of 0.5.0. The two projects
  that use the harness run 3.11 or later (this repository's environments; the podcast project declares `>=3.10` and
  runs 3.11.8).
- What the SDK brings (its 2.3.0 metadata): `anyio`, `httpx2`, `jsonschema` (already a dependency), `mcp-types`,
  `opentelemetry-api`, `pydantic>=2.12`, `pyjwt[crypto]`, `python-multipart`, `sse-starlette`, `starlette`,
  `typing-extensions`, `typing-inspection`, `uvicorn`. This is the footprint RFC-016 recorded and the owner accepted.
- No command prints JSON today; the view commands compute and print in the same loop (`catalog_views.py`), which is
  the refactor 0.5.0's RFC-013 does command by command, with a schema each.

## Design

### The server

- `evh mcp [--project DIR]` (default: the project the working directory is in, as every command finds it) starts a
  stdio server on the SDK's low-level `Server` (`on_list_tools`, `on_call_tool`; `mcp.server.stdio.stdio_server`).
  Server name `evaluation-harness`, its version the harness's.
- **The tools** are a fixed list in `mcp_server.READ_TOOLS`: the thirteen commands above. Not tools: anything that
  writes, spends or never returns (`experiment-run`, `sweep`, `judge`, `rescore`, `run-promote`, the round commands,
  `dataset-create`, `dataset-materialize`, `dataset-profile`, `reference-create`, `catalog`, `catalog-serve`, `init`,
  `mcp`). A test fails when a command is in neither list, so a new command is decided, not forgotten.
- **Each tool's description** is the command's one line in `cli.COMMANDS`, then its parser's description. **Its input
  schema** is generated from its `argparse` parser: each option becomes a property (its type, `choices` as an `enum`, a
  flag as a boolean, `nargs` as an array, the help as the description, required when the parser requires it). The
  parser is read without running the command: the command's module is run with `argparse.ArgumentParser.parse_args`
  replaced by one that hands the parser back. `--adapter` and `--json` are left out of every schema: the server uses
  the project's own adapter (an agent must not load an arbitrary Python file), and sets `--json` itself.
- **Annotations**: every tool `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`,
  `openWorldHint: false` (no read command calls a provider).
- **A call** runs the command as a child process (`evh`, the command, the tool's arguments as options, `--json` where it has one) in its own process group, in the project
  root, with the server's environment, a timeout of 300 s and stdin closed. Cancelling the request or the timeout kills
  the group. The arguments are built from the tool's input by the same parser actions (an option's own flag, repeated
  for a list), so a call is a command line a person could type; a property the schema does not have is refused before
  anything runs.
- **The result**: stdout as the tool's text, and for a command with `--json` its JSON as `structuredContent`, both
  capped at 1 MB (beyond it the result is an error that names the command's own filters). A refusal (a non-zero exit)
  is a result with `isError: true`, the command's stderr as its text and the exit code. The last 64 KB of stderr is
  kept otherwise as the result's log.

### `--json` for the view commands (`_jsonout.py`)

- The catalog's view commands (`catalog_views.py`) take `--json`. Under it, the same code runs and what it would print
  is collected: every table as `{"columns": [...], "rows": [{column: value}]}` with the values before they are turned
  into text, every other line as a string, in order; at the end one object is printed:
  `{"command": "datasets", "version": "0.4.5", "result": {"blocks": [{"lines": [...]}, {"columns": …, "rows": …}]}}`.
  It is the envelope RFC-013 names (`command`, `version`, `result`), and because it is the printing path, the JSON
  and the text cannot disagree.
- `dataset-items --json` keeps the profile it already prints (inside the envelope). `rounds`, `runs-list` and
  `validate` print text only in 0.4.5; their tools return the text.
- **What 0.5.0 changes**: RFC-013 gives each command its own result and schema, computed before it is printed; the
  generic `blocks` form goes then. 0.4.5's release notes say so, so nothing builds on its shape.

### Python 3.10

`requires-python = ">=3.10"`, the package job's matrix `3.10`, `3.11`, `3.14`, the README's badge and PRD-007's floor.
Nothing in the code needs 3.10 syntax for this change; the floor is the SDK's. `ruff.toml` keeps
`target-version = "py39"`: at py310 ruff raises 46 new findings (37 `zip()` without `strict=`), several in the
examples' scorers, whose source is hashed into the committed runs' fingerprints; a stricter syntax target costs
nothing.

## Not in 0.4.5 (0.5.0, RFC-013 and RFC-016)

- Tools that write, spend or run: promotions, rounds, runs, judging, studies, jobs; consent; the actor on records; the
  limits file; long work as jobs.
- Per-command result schemas and `outputSchema`; `--json` on every command; the exit-code table.
- Skills, `llms.txt`, the glossary.

## Alternatives considered

- **A tool per command with its output parsed from the text tables.** Rejected: a parser of our own tables would be a
  second rendering that drifts from the first.
- **`mcp` as an extra (`pip install …[mcp]`).** Rejected by the owner's rule: everything works from one install.
- **The SDK's `MCPServer` (decorators per tool).** Rejected: the tools are generated from the parsers, a list known at
  start; the low-level `Server`'s two handlers take that list directly.
- **Writing tools now, guarded by a confirm flag.** Rejected: consent is a person's (RFC-013), and 0.4.5 has no actor or
  consent model; a read-only server needs neither.

## Testing

- `harness/tests/test_mcp_server.py` (offline, the tutorial project): the server starts through the SDK's own stdio
  client; `tools/list` holds exactly `READ_TOOLS`, each read-only, each schema without `--adapter` or `--json`;
  `datasets` returns the same text as `evh datasets` and a `structuredContent` whose tables hold its rows; a call with
  an unknown property is refused before it runs; a refusal (`goals` with an unknown goal) comes back as `isError` with
  the command's message; every command is in `READ_TOOLS` or in the list of commands that are not tools.
- `test_installed_commands.py`: `evh mcp --help` from the installed wheel.
- The package job runs the suite on 3.10, 3.11 and 3.14.
