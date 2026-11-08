# RFC-026: An API for every command, long ones as jobs

- **Status**: Proposed (2026-11-08), for the owner's review. Owner, 2026-11-06: "next RFC is for this API" (S0b); the
  Workbench (PRD-017) is its first user.
- **Authors**: Marko Dragoljevic
- **Related**: [PRD-017](../prd/PRD-017-workbench.md) (the Workbench: one server, jobs, parity),
  [UXS-005](../uxs/UXS-005-workbench.md) (its screens), [RFC-018](RFC-018-read-only-mcp-server.md) (the MCP
  server, whose way of running a command this reuses), [RFC-025](RFC-025-runs-in-sqlite.md) (both stores),
  [ADR-0027](../adr/ADR-0027-the-data-page-writes-locally.md) (writes on this machine only), the job sets of the
  0.5.0 drafts (RFC-011, not merged: its supervisor is taken here, its phases and ssh runner are not),
  `research/internal/PLAN_0.8.0.md` S0b

## Abstract

`catalog-serve` answers one HTTP API for every `evh` command, so a person in the Workbench can do what an agent does
with the command line. A command that only reads is answered at once, run as the MCP server runs it. Every other
command is a **job**: a detached process running that same `evh` command, which keeps running when the page closes,
writes its log as it goes, can be stopped, and is resumed where the command can resume. Two jobs that would write the
same thing never run at once. The API is made from the commands' own argument parsers, so it cannot offer what the
command line does not, or miss what it adds; every command it serves answers `--json`.

## What exists today (measured 2026-11-08)

- 80 commands (`evh --help`). 31 answer `--json`; 8 take `--dry-run`, 1 takes `--resume` (`run`),
  8 take `--by` (who acted).
- `evh mcp` serves 28 of them as read-only tools; each of the other 52 is listed with why it is not a tool
  (`mcp_server.NOT_TOOLS`: it writes, spends, or reaches outside the project). Its `parser_of(command)` reads a
  command's argparse parser without running it, and its tools' schemas are made from those parsers.
- `catalog-serve` answers 12 routes: the inspector's 5 reads, the data page's 7 (UXS-004; settings written by
  `evh data-put`, through `_settings_form.guarded_write`, one at a time with one `evh validate` each).
- Nothing runs a long command in the background. `evh run` holds its terminal until the run ends.

## Design

### One registry, made from the command line

`GET /api/v1/commands` lists every command the API serves: its name, what it does (`cli.COMMANDS`), how it is served
(`read` or `job`), whether it spends, and its arguments as the parser declares them (name, type, choices, default,
required, help). The registry is built from `parser_of` at the server's start, as the MCP tools are. A command added to
`cli.COMMANDS` and not classified fails a test, as a command neither a tool nor in `NOT_TOOLS` does today.

A call's arguments are a JSON object keyed by the argument's name. They are checked against the parser before anything
runs (types, choices, required, unknown names refused) and turned into the command's argv by the parser's own option
strings, so the command receives exactly what `evh <command> …` would.

A command that reads a file it is given (`data-put`'s file, `label-import`'s sheet, `sheet-import`) takes the file in
the call; the server keeps it under `.build/uploads/<sha256>` for the job and passes that path. A path argument may
name only the project's own folders and the uploads.

### Reads

`POST /api/v1/read/<command>` runs one of the 28 read commands in a child process with `--json`, as an MCP call does
(`mcp_server.run_command`: its own process group, stdin closed, the same timeout), and returns its envelope:
`{"command", "version", "result"}`.

### Jobs

`POST /api/v1/jobs` with `{"command", "args", "by", "reason"}` starts a job and answers `202` with its id and state.

- **A job is one command.** The server writes `.build/jobs/<id>/job.json` (the command, its argv, who asked, when, the
  harness version) and starts `python -m evaluation_harness.jobs_supervisor <id>` detached: a new session, stdin from
  `/dev/null`, its output to the job's `supervisor.log`, every descriptor closed. The supervisor runs
  `evh <command> <argv> --json` in its own process group, writing stdout and stderr to the job's `log`, and the
  envelope to `result.json` when the command prints one.
- **State** is `.build/jobs/<id>/state.json`, rewritten atomically: `queued`, `running`, `succeeded`, `failed` (the
  exit code and the command's refusal kind, `ERROR (<kind>)`), `cancelled`, `lost`; started, ended, the exit code.
- **One supervisor per job** holds an exclusive `flock` on the job's `supervisor.lock` for its life. The operating
  system releases it however the process ends, so a free lock on a `running` job means the supervisor is gone: the job
  reads as `lost`.
- **Reading a job**: `GET /api/v1/jobs` (each job, newest first; `?state=` to filter), `GET /api/v1/jobs/<id>` (its
  state and, when it has one, its result), `GET /api/v1/jobs/<id>/log?from=<byte>` (the log from an offset, so a page
  follows it without reading it again).
- **Stopping**: `POST /api/v1/jobs/<id>/stop` sends SIGTERM to the job's process group, SIGKILL after 10 s, and marks
  it `cancelled`.
- **Resuming**: `POST /api/v1/jobs/<id>/resume` starts a new job continuing the old one, for a command that can
  (`run --resume <run id>`); other commands are refused (`not-allowed`): they are run again instead.
- Jobs are not project data: they live in `.build/` (gitignored), the same in either store.

### Never two writers of the same thing

PRD-017: "one job at a time touches the same data". Each job command declares what it writes, as lock keys made from
its arguments:

| command | it writes | lock key |
| --- | --- | --- |
| `run`, `arm-smoke` | a run of a config (and the model's record) | `config:<config_id>`, `model:<model>` |
| the `dataset-`, `reference-` and `label-` commands that write, `sheet-import` | a dataset, its references and labels | `dataset:<dataset_id>` |
| `round-open`, `round-retire`, `round-close`, `run-promote` | a goal's rounds and baseline | `goal:<goal>` |
| `rescore`, `judge-score` | derived runs on a dataset | `dataset:<dataset_id>` |
| `data-put`, `data-rm` | a setting, or a run | `path:<path>` |
| `data-migrate`, `run-migrate`, `dataset-migrate`, `fingerprint-migrate` | the whole project | `project` (exclusive) |

Every other job holds the project's shared lock, which `project` excludes. A job whose keys are held waits as `queued`
and starts when they are free; the queue is in the order jobs were asked for. A read takes no lock, so a write must
never be seen half done. In SQLite a write is one committed transaction. In a files project `_store.write_text` is
`Path.write_text` today, which empties the file and then writes it; the build makes it write a temporary file beside
it and `os.replace` it into place, so a read sees the file before or after a write, never between.

### Spending

`run`, `sweep`, `arm-smoke`, `judge`, `judge-score` and `model-onboard` call models. A job for one of them must carry
`max_cost_usd`, which becomes `EVAL_MAX_COST_USD` for it: a job never spends without a cap. `POST /api/v1/estimate`
runs a command's `--dry-run` and returns what it prints, so the Workbench shows what a job will do and cost before
the person starts it (PRD-017, requirement 4). 8 commands have one: `run`, `sweep` and `judge-score`, and five that
migrate or remove (`data-migrate`, `data-rm`, `dataset-migrate`, `fingerprint-migrate`, `run-migrate`).

### Who acted

Every job records who asked for it and why (`by`, `reason`) and passes each to the command where the command takes
it: 8 commands take `--by`, 5 take `--reason` (`reference-manifest`, `reference-promote`, `round-open`,
`round-retire`, `run-promote`). A promotion, a reference set or a round opened or retired then records the person as
it does from the command line; the commands that act and take neither get them with step 4.1 (who acted on every
record).

### Every command answers `--json`

The Workbench shows a job's result as data, not as text to scrape. 43 of the commands the API serves have no `--json`
today (the table below). Each gets it, with the envelope the others use; a test fails on a served command without it.
Until a command has it, its job's result is its exit code and its log.

### Safety

The same rules as the data page (ADR-0027): the server listens on 127.0.0.1, a request's Host must be the server's
own, and every call that is not a read carries `X-EVH-Data: 1`, which a page from another origin cannot send without a
CORS preflight this server never grants. A server started with `--public` answers none of `/api/v1/`, as it answers no
`/api/data/` call today.

### Both stores

The API runs commands; the commands read and write through `_store`. Nothing in the API knows which store the project
has, so it works the same in either (RFC-025).

## Build order

1. `_store`'s whole-file writes in a files project (above), then the registry and the read side, with the parity test (every read command's API answer equals its `--json` from the
   command line).
2. Jobs: the supervisor, state, logs, stop, lost, resume.
3. Locks and the queue.
4. The estimate and the cost cap.
5. `--json` for the 43 commands, in groups (datasets, labels and references, rounds, runs, the rest).
6. The Workbench (PRD-017) on top.

## Testing

- Parity: every read command through the API and through the command line give the same JSON.
- A job's life: started, followed by offset, succeeded with its result; a failing command reports its refusal kind; a
  stopped job's process group is gone; a killed supervisor shows the job `lost`; `run` resumed continues its run.
- Locks: two `run`s of one config, the second queued until the first ends; two different configs at once; a migration
  waits for every job and every job for it.
- Spending: a spending job without `max_cost_usd` refused; the cap reaches the command.
- Safety: without the header refused; another Host refused; `--public` answers no `/api/v1/` call.
- Both stores: the job and lock tests in each (`make stores-check`).

## Alternatives considered

- **A hand-written endpoint per resource** (`/datasets`, `/runs`, …): 80 commands written twice, and the two drift.
  Made from the parsers, the API cannot fall behind the command line.
- **Running commands in the server's own threads**: the commands exit with `sys.exit`, keep module state and can run
  for hours; a child process isolates each, as the MCP server already does.
- **Writes through the MCP server**: MCP is the agents' protocol and stays read-only (RFC-018); a browser needs HTTP and
  jobs it can follow and stop.
- **RFC-011's job sets as they were drafted** (a set of runs with phases and an ssh runner): a job here is one command,
  which is what a Workbench step is; phases and the ssh runner wait for the owner's decision on them (PLAN_0.8.0, open
  question 3).

## Open for the owner

1. A job whose lock is held: wait in a queue (proposed), or be refused with which job holds it.
2. Uploads: the largest file a call may carry (proposed: 50 MB, a sheet or a source table).
3. Whether `evh` gets `jobs-status`, `jobs-logs`, `jobs-stop` commands over the same jobs (CLI parity says yes; the
   agents asked for background runs in the 0.5.0 drafts).

## The commands, and how the API serves them

Generated from `evh --help` and `mcp_server.READ_TOOLS` / `NOT_TOOLS` on 2026-11-08: 28 read, 40 jobs, 6 jobs that
spend, 6 not served.

| command | served as | `--json` | why |
| --- | --- | --- | --- |
| `activity` | read | yes | reads only (an MCP tool) |
| `arm-from-capture` | job | **no** | writes a config and a run |
| `arm-smoke` | job, spends | yes | runs a system on a few items, may spend, and writes the model record |
| `arms` | read | yes | reads only (an MCP tool) |
| `bootstrap-test` | job | **no** | a statistics command; not yet a tool |
| `capture` | job | **no** | reads a production system and writes |
| `capture-restore` | job | **no** | reads a source and writes records and item files |
| `capture-scrub` | job | **no** | runs a project's command and writes |
| `captures` | read | yes | reads only (an MCP tool) |
| `catalog` | job | **no** | writes the pages |
| `catalog-serve` | not served | **no** | it is the server |
| `cost-report` | job | **no** | a report tool; not yet a tool |
| `data-ls` | read | yes | reads only (an MCP tool) |
| `data-migrate` | job | **no** | moves the project's data between files and its database |
| `data-put` | job | yes | writes a setting |
| `data-rm` | job | yes | deletes a setting or a run |
| `data-show` | read | yes | reads only (an MCP tool) |
| `dataset-card` | read | **no** | reads only (an MCP tool) |
| `dataset-create` | job | **no** | writes |
| `dataset-describe` | job | **no** | writes a dataset record |
| `dataset-extend` | job | **no** | writes a dataset |
| `dataset-from-capture` | job | **no** | writes |
| `dataset-items` | read | yes | reads only (an MCP tool) |
| `dataset-materialize` | job | **no** | writes |
| `dataset-migrate` | job | **no** | writes the dataset records |
| `dataset-profile` | job | yes | writes |
| `dataset-publish` | job | **no** | writes to an outside service (a new Hub repo) |
| `dataset-split` | job | **no** | writes |
| `datasets` | read | yes | reads only (an MCP tool) |
| `deploy-sheet` | read | yes | reads only (an MCP tool) |
| `env-check` | not served | **no** | the server's own environment |
| `family-test` | read | yes | reads only (an MCP tool) |
| `fieldset-propose` | job | **no** | reads a source (it can fetch from the network) and can write a field set |
| `fingerprint-migrate` | job | **no** | rewrites the committed runs' fingerprints |
| `goals` | read | yes | reads only (an MCP tool) |
| `holdout` | job | **no** | a statistics command; not yet a tool |
| `import-run` | job | **no** | writes runs |
| `importer-check` | job | **no** | reads a production system, not the project |
| `init` | not served | **no** | makes a project; the Workbench opens one |
| `inspect` | read | yes | reads only (an MCP tool) |
| `judge` | job, spends | **no** | calls models and spends |
| `judge-score` | job, spends | **no** | calls models and spends |
| `label-from-capture` | job | **no** | writes a label set |
| `label-from-run` | job | **no** | writes a label set |
| `label-import` | job | **no** | writes a label set |
| `label-sheet` | job | **no** | writes a sheet |
| `labels` | read | yes | reads only (an MCP tool) |
| `leaderboard` | read | yes | reads only (an MCP tool) |
| `licences` | read | yes | reads only (an MCP tool) |
| `mcp` | not served | **no** | the agents' server |
| `metrics` | read | yes | reads only (an MCP tool) |
| `model-onboard` | job, spends | **no** | calls a model and writes the model record |
| `models` | read | yes | reads only (an MCP tool) |
| `overview` | read | yes | reads only (an MCP tool) |
| `pair-test` | read | yes | reads only (an MCP tool) |
| `pick` | job | **no** | writes the pick list |
| `picks` | read | yes | reads only (an MCP tool) |
| `rank-stability` | read | yes | reads only (an MCP tool) |
| `reference-manifest` | job | **no** | writes |
| `reference-promote` | job | **no** | writes a reference |
| `references` | read | yes | reads only (an MCP tool) |
| `rescore` | job | **no** | writes runs |
| `round-close` | job | **no** | a decision: a person's |
| `round-open` | job | **no** | a decision: a person's |
| `round-retire` | job | **no** | a decision: a person's |
| `rounds` | read | yes | reads only (an MCP tool) |
| `run` | job, spends | yes | runs a system and may spend |
| `run-compare` | read | yes | reads only (an MCP tool) |
| `run-migrate` | job | **no** | rewrites the run directories |
| `run-promote` | job | **no** | a decision: a person's |
| `runs-list` | read | yes | reads only (an MCP tool) |
| `score-preview` | job | **no** | runs the project's own scoring code |
| `search` | read | yes | reads only (an MCP tool) |
| `self-test` | not served | **no** | checks the installed package |
| `sheet-import` | job | **no** | writes a label set or judged runs |
| `silver-calibrate` | job | **no** | writes |
| `skills-install` | not served | **no** | writes the agents' skills into a project |
| `sweep` | job, spends | **no** | runs systems and may spend |
| `tags` | read | yes | reads only (an MCP tool) |
| `validate` | read | **no** | reads only (an MCP tool) |
