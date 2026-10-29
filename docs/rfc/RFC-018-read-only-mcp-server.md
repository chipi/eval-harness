# RFC-018: A read-only MCP server in 0.4.5

- **Status**: In Progress (0.4.5), accepted 2026-10-29: the owner's go on "a small read-only MCP server in 0.4.5, Python 3.9
  dropped there"
- **Authors**: Marko Dragoljevic
- **Related RFCs**: 0.5.0's RFC-013 (one declaration per command, `--json`, exit codes) and RFC-016 (the MCP server,
  skills, consent), on branch `050`: this is their first, read-only step, shipped early
- **Related UX specs**: [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the commands the tools are)
- **Code**: new `harness/scripts/mcp_server.py` (`evh mcp`), `harness/scripts/_jsonout.py` (`--json` for the view
  commands), `catalog_views.py`, `cli.py`, `stats.py` (`EVH_P_CACHE`); `harness/pyproject.toml` (`requires-python`,
  the dependency), `harness/requirements.txt`, `.github/workflows/harness-package.yml`; the deployment in `infra/`
  (`compose.yml` service `mcp`, `mcp/hooks.py`, `mcp/requirements.txt`, `caddy/evals.caddy`, `deploy/render.sh`,
  `deploy/deploy.sh`, `observability/evals.alloy`); tests `harness/tests/test_mcp_server.py`, `test_mcp_http.py`,
  `test_p_cache.py`

## Abstract

`evh mcp` serves one project to an agent over MCP, on the official Python SDK: over **stdio** for an agent on the
machine that holds the project (a laptop, a workstation), or over **Streamable HTTP** (`--http`) for a shared server
(a team's, or this repository's public one at `https://evals.humancopilot.eu/mcp`). Its tools are the harness's
read commands, the same commands a person runs: the catalog's views (`overview`, `datasets`, `dataset-items`, `arms`,
`goals`, `references`, `metrics`, `activity`, `search`), the inspector in the terminal (`inspect`), `rounds`,
`runs-list` and `validate`. Each call runs the command as a child process, so a tool answers exactly what the command
prints. No tool writes project data, spends or runs a model (the one file a call writes is the goals' p cache
in the project's ignored `.cache/`, below): running arms, promoting, retiring, judging and everything with a
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
  root, with the server's environment, a timeout of 300 s and stdin closed. The timeout kills the group (exit 124).
  A request the client cancels does not stop the command: it runs to its end or its timeout, holding its slot.
- **The arguments** are built from the tool's input by the same parser actions (an option's own flag, repeated for
  a list), so a call is a command line a person could type. Refused before anything runs: a property the schema does
  not have; a missing required one; a value of the wrong kind (a list for an option that takes one value, anything
  but `true`/`false` for a flag, an object or null); and any value that starts with `-`, which the command would read
  as an option of its own (`["x", "--adapter", "mod:fn"]` would reach an option the schema leaves out).
  Positionals follow `--`. A dataset id is a name, never a path: every command refuses one with `/` or `..`
  (`_common.dataset_id_ok`).
- **The result**: stdout as the tool's text, and for a command with `--json` its JSON as `structuredContent`, both
  capped at 1 MB (beyond it the result is an error that names the command's own filters). A refusal (a non-zero exit)
  is a result with `isError: true`, the last 64 KB of the command's stderr (or its stdout when stderr is empty) as
  its text, and the exit code. A command's stderr on success is not returned.

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
The floor is the SDK's; the new tests already use 3.10 syntax (`str | None` at run time). `ruff.toml` keeps
`target-version = "py39"`: at py310 ruff raises 46 new findings (37 `zip()` without `strict=`), several in the
examples' scorers, whose source is hashed into the committed runs' fingerprints; a stricter syntax target costs
nothing.

### A shared server: `--http`

- `evh mcp --http [--bind A] [--port P] [--path /mcp]` serves the same tools over Streamable HTTP on the SDK's own
  app (Starlette, run by uvicorn), **stateless** with JSON responses: every request stands alone, so a client needs no
  session, any number of replicas can serve it, and clients on every protocol revision since 2025-03-26 call tools
  (checked with 2025-03-26, 2025-06-18, 2025-11-25 and 2026-07-28 requests). `<path>/health` answers
  `{"ok", "version", "tools", "public"}`.
- **The Host is checked** (DNS rebinding, the transport's own requirement): on the loopback only localhost names; a
  bind beyond it is refused unless `--allowed-host` names the host it answers (repeatable); `--allowed-origin` names
  the browser origins it accepts (a request without an Origin, which agents send, passes).
- **`--public`**, for a server anyone can reach: the options that answer with an item's text or an arm's output are
  left out of the schemas (`inspect --item`, `dataset-items --item`), and `validate` is not offered (a public copy of
  the data is not a whole project, so it would only report what was left out).
- **Load**: `--concurrent N` commands at once (a call waiting 30 s for a slot is refused, "busy"), `--timeout` per
  call, `--rate N` calls a minute per caller and `--rate-total N` for all callers together, and over HTTP one call
  running at a time per caller. The caller is named by `--client-header` (the proxy's, e.g. `CF-Connecting-IP`) or
  the connection, an IPv6 address by its /64. Every call counts toward the rate, a refused one too. A header is
  trusted as it comes: a caller that can reach the port past the proxy can name itself anything, which the total
  still holds.
- **Speed**: each call is a fresh process, and a view that shows the goals runs their paired tests (~500 here, ~50 s).
  `stats` keeps each estimated p on disk when `EVH_P_CACHE` names a file (the p read back exactly; a torn last line
  skipped); the server sets it to the project's ignored `.cache/evh-p.jsonl` unless the deployment names its own.
  `goals`, `overview` and `arms` went from ~52 s to ~1.6 s.
- **Observability**, the deployment's (`--hooks`, the inspector's shape: `start`, `request` after every call,
  `error`, `routes` served beside the endpoint): a call is reported as its tool, its arguments' names (never their
  values), how it ended, its time, and to the hooks only, the caller's address and user agent. One JSON line per
  call on stderr carries the same without either. A tool name the server does not have is reported as `unknown`.

### This repository's deployment (`infra/`)

- `evals-mcp`, a third container beside nginx and the inspector: the same stock Python image, user, read-only mount and
  hardening, `--http --public --allowed-host evals.humancopilot.eu --client-header CF-Connecting-IP --rate 30
  --rate-total 120 --concurrent 2 --timeout 60`. The throttling is the server's own: Cloudflare proxies the host but
  has no rate limit for it (the owner, 2026-10-29). Also a hard `mem_limit` of 384m (the box has no swap and a nightly pipeline; prod's
  sizing), 127.0.0.1:8098. Caddy sends `/mcp` and `/mcp/*` to it, nothing else (its `/metrics` stays on the loopback).
- `render.sh` vendors the SDK and its dependencies, pinned (`infra/mcp/requirements.txt`, resolved for x86_64 musl),
  as wheels beside the package, and fills the p cache during the catalog build, so the release carries it read-only.
- `deploy.sh` recreates it with the rest, checks `/mcp/health` and a real `goals` call (up to 120 s; a warning past
  30 s, which means the precomputed cache was not read), and rolls the release back when either does not answer
  (removing the container when the previous release had none). The workflow then checks `/mcp/health` through the
  public host.
- `infra/mcp/hooks.py`: errors to GlitchTip (project `evals-mcp`, `EVALS_SENTRY_DSN_MCP`), a span per call to the
  homelab's traces (service `evals-mcp`), `/metrics` (calls per tool and outcome, latency, memory, Umami events), and
  one Umami event per call (`mcp:<tool>`) on the site's own website, sent to `UMAMI_SEND_URL` on the tailnet with the
  caller's address and a browser-shaped user agent (Umami counts a visitor by address and user agent, and drops what
  looks like a bot). `evals.alloy` collects its log lines and scrapes its `/metrics`.
- No authentication: everything it answers is already public on the site and in the catalog, and every tool reads.
  Who may read and write through MCP is 0.5.0's (RFC-016, users and permissions).

### For a team

The same command serves a team: `evh mcp --http --bind 0.0.0.0 --allowed-host evals.team.example` behind the team's
proxy, on a checkout of the project (with or without `--public`, as the team's data allows). 0.4.5 has no accounts:
put it behind what the team already uses (a VPN, an authenticating proxy).

## Not in 0.4.5 (0.5.0, RFC-013 and RFC-016)

- Tools that write, spend or run: promotions, rounds, runs, judging, studies, jobs; consent; the actor on records; the
  limits file; long work as jobs.
- Per-command result schemas and `outputSchema`; `--json` on every command; the exit-code table.
- Skills, `llms.txt`, the glossary.
- Users and permissions on a shared server: who may read, who may write, through which tools, and what each did.

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
- `harness/tests/test_mcp_http.py` (the SDK's streamable HTTP client): health; another Host refused (421);
  `--public` hides the text options and `validate`; a missing required argument refused before it runs; `--rate 3`
  refuses the fourth call; the hooks see each call (tool, argument names, never values; the caller) and serve their
  route; a bind beyond the loopback without `--allowed-host` refused.
- `harness/tests/test_p_cache.py`: a stored p is the computed one, read back by a fresh process, a torn line skipped.
- `test_installed_commands.py`: `evh mcp --help` from the installed wheel.
- The package job runs the suite on 3.10, 3.11 and 3.14.
- The deployment, rehearsed before it ships: the rendered release in the pinned Alpine image on Docker, run as
  `compose.yml` runs it (user 65534, read-only root, 384m): health 200, `goals` in 5 s, 55 MB resident.
