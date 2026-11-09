# RFC-026: An API for every command, long ones as jobs

- **Status**: Accepted (owner, 2026-11-08: "update rfc26 to approved"; revision 2 accepted 2026-11-09: "mark both as accepted"); not built yet. Owner, 2026-11-06: "next RFC is
  for this API" (S0b); the Workbench (PRD-017) is its first user. Its four open questions decided by the owner the same
  day (below: "1 waiting, 2 [the proposed file size], 3 yes, 4 enforce"). Revision 2 (2026-11-09), after an
  independent review (Fable) and aligned with [RFC-027](RFC-027-who-acted-and-baselines-per-goal.md): 82 commands,
  path arguments, the cap where spend is counted, the round ledger, who acted, locks; its fifth question decided
  by the owner the same day (local only: "I am OK with the proposed way for a team to work").
- **Authors**: Marko Dragoljevic
- **Related**: [PRD-017](../prd/PRD-017-workbench.md) (the Workbench: one server, jobs, parity),
  [UXS-005](../uxs/UXS-005-workbench.md) (its screens), [RFC-018](RFC-018-read-only-mcp-server.md) (the MCP
  server, whose way of running a command this reuses), [RFC-025](RFC-025-runs-in-sqlite.md) (both stores),
  [ADR-0027](../adr/ADR-0027-the-data-page-writes-locally.md) (writes on this machine only), the job sets of the
  0.5.0 drafts (RFC-011, not merged: its supervisor is taken here, its phases and ssh runner are not),
  `research/internal/PLAN_0.8.0.md` S0b

## Abstract

`catalog-serve` answers one HTTP API for the `evh` commands, so a person in the Workbench can do what an agent does
with the command line: 75 of the 82, all but the servers themselves, the ones that set up a project or check the
installation, and `capture-scrub`, which runs a program it is given. A command that only reads is answered at once,
run as the MCP server runs it. Every other is a **job**: a detached process running that same `evh` command, which
keeps running when the page closes, writes its log as it goes, can be stopped, and is resumed where the command can
resume. Two jobs that would write the same thing never run at once; a spending job has a cap; every call needs the
server's token. The API is made from the commands' own argument parsers, so it cannot offer what the command line
does not, or miss what it adds; every command it serves answers `--json`.

## What exists today (measured 2026-11-08)

- 82 commands (`evh --help`, 2026-11-09). 8 take `--dry-run`, 1 takes `--resume` (`run`). `--by` means who acted
  on 5 (`label-import`, `sheet-import`, `pick`, `reference-manifest`, `reference-promote`); on `dataset-split` it is
  the split rule (renamed `--split-by` by RFC-027) and on `inspect` a breakdown field. `--reason` is why on
  `run-promote`, `reference-promote`, `reference-manifest`, `round-retire` and `dataset-unseal`; on `round-open` it is
  why the `--retire` arms are dropped; `round-close` takes `--conclusion`.
- `evh mcp` serves 29 of them as read-only tools; each of the other 53 is listed with why it is not a tool
  (`mcp_server.NOT_TOOLS`: it writes, spends, or reaches outside the project). Its `parser_of(command)` reads a
  command's argparse parser without running it, and its tools' schemas are made from those parsers, leaving out the
  options a read must not have (`HIDDEN`: `--adapter`, which loads code; `TOOL_HIDDEN`: per command, the options that
  write a file or read outside the project, e.g. `inspect --csv`, `--fill`, `pair-test --runs-dir`).
  `mcp_server.run_command` runs each call in its own process group, stdin closed, with a timeout, adding `--json`
  for the tools listed in `JSON`. 27 of the 29 read commands have `--json`; `validate` and `dataset-card` answer
  text. (`JSON` lists 24: `data-ls`, `data-show` and `label-coverage` have `--json` and are added to it in step 2.)
- `catalog-serve` answers 11 routes: the inspector's 4 (`/api/health`, `/api/compare`, `/api/item`, `/api/sheet`) and
  the data page's 7 under `/api/data/` (UXS-004, ADR-0027: settings written through `_settings_form.guarded_write`,
  one at a time in the server, with `evh validate` before and after; a run removed whole). Those 7 answer only a
  SQLite project that sets `configure: true`, on 127.0.0.1, with `X-EVH-Data: 1` and no foreign `Origin`.
- Nothing runs a long command in the background. `evh run` holds its terminal until the run ends; a run becomes
  visible (`metrics.json`) only when it ends cleanly.

## Design

### One registry, made from the command line

`GET /api/v1/commands` lists every command the API serves: its name, what it does (`cli.COMMANDS`), how it is served
(`read` or `job`), whether it spends, what it locks (below), and its arguments as the parser declares them (name,
type, choices, default, required, help). The registry is built from `parser_of` at the server's start, as the MCP
tools are. A command added to `cli.COMMANDS` and not classified fails a test, as a command neither a tool nor in
`NOT_TOOLS` does today.

**What the API never takes.** The registry leaves out, for every command, the options that load or run code or reach
outside the project: `HIDDEN` and `TOOL_HIDDEN` as the MCP server leaves them out, and for jobs also `--adapter`,
`--importer` given as a `path.py:Class` rather than an importer's name, `--runs-dir`, `--source` given as a path rather than a source's name, and any other
option the registry does not list with an argument kind. `capture-scrub`, whose `--command` is a program to run, is
not served. Each argument the registry keeps has a kind: a name (checked against what exists: a dataset id, a config
id, a goal), a value (type and choices from the parser), or a file the call uploads. No argument is a free path. A
setting saved through the API is checked as `data-put` checks it, and a config whose `adapter:` names a file outside
the project's own code is refused, so `data-put` then `run` cannot run a file the project does not hold.

**Every path argument has a kind.** A command's file arguments are served as one of three, and step 2 lists every
served command's path arguments with theirs (a test fails on a `Path` argument with none):

- **a name the server maps to a file**: `run --config`, `arm-smoke --config`, `model-onboard --config`, `sweep
  --configs` take config ids (`data/configs/<id>.yaml`, or the project's configured config globs);
- **an upload**: `data-put`'s file, `label-import`'s and `sheet-import`'s sheet, `sheet-import --key`,
  `import-run --scores`, `label-coverage --map`, `dataset-create --fields`, `capture --query @file`;
- **a job artifact**: `label-sheet --out`, the one output file a served command writes outside the project's data,
  is written under `.build/jobs/<id>/` and fetched with `GET /api/v1/jobs/<id>/files/<name>` (owner, 2026-11-09: the
  sheet is offered as a download);
- not served as a path, so the command's default applies: `judge-score --out` and `rescore --out` (the project's own
  judged and re-scored runs directories), `rescore --config-dir`, `--source-dir`, `arm-from-capture --like`,
  `bootstrap-test --items` (each is left to the command line).

A call's arguments are a JSON object keyed by the argument's name, checked against the registry before anything runs
(kinds, types, choices, required, unknown names refused) and turned into the command's argv by the parser's own option
strings, so the command receives exactly what the same command typed after `evh` would. A file the command reads (`data-put`'s,
`label-import`'s and `sheet-import`'s sheet) is uploaded with the call and kept under `.build/uploads/<sha256>` for
the job; a call carries at most 50 MB (owner, 2026-11-08), and a larger one is refused before anything is written.

### Who may call

Any process on the machine can reach 127.0.0.1, another user's included, and a page from another origin can send a
simple POST to it. So every `/api/v1/` call, reads included, needs the server's token: a random value made when the
server starts, written to `.build/api-token` (mode 600, the project owner's only) and printed once with the
Workbench's address, as `http://127.0.0.1:PORT/workbench/?token=…`. The page trades it for a cookie (`HttpOnly`,
`SameSite=Strict`, this host only) on the first load; a script sends `Authorization: Bearer …`. Also: the Host must be
the server's own (DNS rebinding), a foreign `Origin` is refused, and every call that is not a read carries
`X-EVH-Data: 1`. A server started with `--public` answers none of `/api/v1/`, and (owner, 2026-11-09) nor does
one started with `--behind-proxy`, which serves the inspector to a team's
proxy (and whose `allowed()` accepts the proxy's Host names, so "the Host must be the server's own" does not hold
there); the data routes are already refused in both modes. Every job runs as the server's operating-system user, so
an API reached by a team would let each member run any command as the project's owner, and the actor (RFC-027) is a
typed claim; several people sharing one project is PRD-017's "later question".

After the page has traded the token for the cookie it removes `?token=` from its address
(`history.replaceState`), so the token does not stay in the browser's history. This is more than ADR-0027 asked of the
data page (a header and the Host): the API runs any command, so it is the new floor for the data routes too while
they live (below).

### Reads

`POST /api/v1/read/<command>` runs one of the 29 read commands as `mcp_server.run_command` runs a tool call: its own
process group, stdin closed, the same timeout, with the same options left out, and returns its envelope
(`{"command", "version", "result"}`). The 27 that have `--json` answer it; `validate` and `dataset-card` answer
their text as `{"command", "version", "text"}` until step 7 gives them `--json`.

### Jobs

`POST /api/v1/jobs` with `{"command", "args", "by", "reason"}` starts a job and answers `202` with its id and state.
`by` is RFC-027's actor (`person:NAME`, or `agent:NAME` with `for: person:NAME`); a decision (`run-promote`,
`baseline-rollback`, `round-close`, `dataset-unseal`) without it is refused here, before a job exists.
This is PLAN_0.8.0's step 4.2 (background runs), as one command a job. The same jobs from the terminal (0.8.0, planned; owner,
2026-11-08; CLI parity): `evh jobs-start <command> [args]` starts one through the same supervisor and prints its id,
`evh jobs-status [id]` lists them or shows one, `evh jobs-logs <id> [--follow]` prints its log, `evh jobs-stop <id>`
stops it, `evh jobs-resume <id>` resumes a run; each answers `--json`, and a job started in either place is seen in
both.

- **A job is one command.** The server writes `.build/jobs/<id>/job.json` (the command, its argv, who asked, when, the
  harness version) and starts `python -m evaluation_harness.jobs_supervisor <id>` detached: a new session, stdin from
  `/dev/null`, its output to the job's `supervisor.log`, every other descriptor closed. Jobs do not depend on the
  server: it can restart, or stop, and they go on; it reads `.build/jobs/` on every `GET /api/v1/jobs`, so a job
  started from the terminal (`jobs-start`, 0.8.0, planned) is seen at once.
- **Who acted.** The supervisor sets `EVH_ACTOR` (and `EVH_FOR`) from the job's `by` for every command, since a job
  has no terminal and RFC-027 would otherwise record it `unknown`; it passes `--by` only to the commands where `--by`
  means who acted, and `reason` as each command names it (`--reason`, `--conclusion` for `round-close`).
- **Locks first.** The supervisor takes the job's locks (below), waiting while another job holds one (`queued`, with
  which job holds it), then starts the command (`evh`, its name, its argv, `--json` where it has it) in its own process group with the lock files' open
  descriptors passed to it. A `flock` belongs to the open file, so the command holds the locks for as long as it
  lives, even if the supervisor dies; the operating system frees them however the command ends.
- **State** is `.build/jobs/<id>/state.json`, rewritten atomically: `queued`, `running` (with the command's process
  group id), `succeeded`, `failed` (the exit code and the refusal kind, `ERROR (<kind>)`), `cancelled`, `lost`;
  started and ended. The supervisor holds an exclusive `flock` on `supervisor.lock` for its life. The command gets
  the job's lock files' descriptors (`pass_fds`) and never `supervisor.lock`'s, or a dead supervisor's lock would
  stay held by the command and the job would never read as unsupervised. A free
  `supervisor.lock` on a `running` job means the supervisor is gone: if the process group still lives the job reads
  `running (unsupervised)`, its locks still held and `stop` still works; if not, `lost`.
- **Output**: stdout and stderr go to the job's `log`, the envelope (when the command prints one) to `result.json`.
  `GET /api/v1/jobs` (newest first; `?state=` filters), `GET /api/v1/jobs/<id>`, `GET /api/v1/jobs/<id>/log?from=<byte>`
  (the log from an offset, so a page follows it).
- **Stopping**: `POST /api/v1/jobs/<id>/stop` sends SIGTERM to the recorded process group, SIGKILL after 10 s, and
  marks the job `cancelled`.
- **Resuming**: the supervisor gives `run` its run id up front (`--run-id <config_id>_<timestamp>`), so a stopped or
  lost run job knows what to resume; `POST /api/v1/jobs/<id>/resume` starts a new job with `run --resume <run id>`.
  It is refused (`not-allowed`) for any other command, and for a run with `--repeat` above 1, which `run` itself
  refuses to resume.
- A stopped command leaves what its own write rules leave: a run is listed only once its `metrics.json` is written
  (at a clean end), so a stopped run is resumable and invisible; other commands are run again.
- Jobs are not project data: they live in `.build/` (gitignored), the same in either store.

### Never two writers of the same thing

PRD-017: "one job at a time touches the same data". Every lock is a file under `.build/locks/`, taken shared (to
read) or exclusive (to write), always in the same order (sorted by key), so two jobs never wait for each other. The
server's own writes (the data routes, its rebuild) take the same locks in the server process. The key comes from the
call's arguments, or from the file they name, read by the supervisor before it starts the command:

| command | locks (exclusive unless "shared") | the key from |
| --- | --- | --- |
| `run` | `config:<config_id>`; `dataset:<dataset_id>` shared | the config file `--config` names: its `config_id`, `dataset_id` |
| `arm-smoke`, `model-onboard` | `model:<model>` | the config `--config` names: its model (the record also has its own `flock`) |
| `sweep` | each arm's as `run` | its configs |
| the `dataset-*` commands that write (`create`, `extend`, `split`, `materialize`, `describe`, `migrate`, `from-capture`), `reference-*`, `label-*`, `sheet-import` | `dataset:<dataset_id>` (a split: the parent and each side) | `--dataset-id`, the positional dataset, `--reference-id`'s dataset, the run `--run` names (its `metrics.json`) |
| `rescore`, `judge-score` | `dataset:<dataset_id>`, and with `--round` `goal:<goal>` | `--dataset-id`, or the round's `dataset_id`; `--goal` |
| `round-open`, `round-retire`, `round-close` | `goal:<goal>` | `--goal` |
| `run-promote`, `baseline-rollback` | `baselines:<goal>/<dataset_id>` (RFC-027: one version line per goal and dataset; `_dataset` for a run with no goal) | `--goal` or the run's goal, `--no-goal`; the run's `dataset_id` |
| `dataset-unseal` | `dataset:<dataset_id>` | the positional dataset |
| `baselines-migrate` | `project` | always |
| `pick`, `dataset-extend --picks` | `picks:<dataset_id>` | `--dataset-id` |
| `capture`, `capture-restore` | `captures` | always |
| `arm-from-capture`, `dataset-from-capture` | `captures` shared; `config:<config_id>` (`arm-from-capture`); `dataset:<dataset_id>` | `--as`, `--dataset-id` |
| `catalog` | `catalog` | always (below) |
| `data-put`, `data-rm` | `settings` (one save at a time: each runs the whole project's `validate`); removing a run also `config:<its config_id>` | always; the run's `metrics.json` |
| `data-migrate`, `run-migrate`, `dataset-migrate`, `fingerprint-migrate` | `project` | always |

Every job also holds `project` shared, so a migration waits for every job and every job for it. A command not in the
table holds only `project` shared, and a test fails on a served writing command missing from it. Two promotions
from the terminal are not under these locks; RFC-027 makes a baseline version's write exclusive in itself. A read takes no lock,
so a write must not be seen half done: SQLite commits each file whole; in a files project `_store.write_text` is
`Path.write_text` today (it empties the file, then writes), so the build makes `_store`'s writes go through
`_common.write_text_atomic` (a temporary file, then `os.replace`), as `write_json` already does. The guarantee is per
file. Between the files of one command a reader can see some written and some not; what the harness lists is whole
(a run appears with its `metrics.json`, last), and the rest is named in the build (step 1).

`catalog` builds into the folder `catalog-serve` serves (`.build/catalog`, `build()` empties it first): as a job it
builds beside it and swaps it in, as the server's own **Rebuild the catalog** already does, so the pages never
disappear, and holds `catalog` so two builds never empty each other's folder.

`data-migrate` refuses while another process holds the database (`_store.held_elsewhere`), and the server does. A
`data-migrate` job therefore has the server close its connections and answer `503` with `Retry-After` to every call
until the job ends; the server then reads the project's store again (`_common.store()` is kept per process).

### Spending

`run`, `sweep`, `arm-smoke`, `judge`, `judge-score` and `model-onboard` call models. Today only `run` and
`judge-score` read `EVAL_MAX_COST_USD`, and `run` counts it per pass (`--repeat 3` can spend three caps); `judge`
stops at its config's `cost_cap_usd`; `arm-smoke`, and `model-onboard` through it, have no cap; `sweep` passes the
variable to each arm's `run`, so its cap is per arm. A round's `budget_usd` is reported, not enforced; the owner
decided it is enforced (2026-11-08). So:

- A spending job must carry `max_cost_usd`, the job's total.
- **The cap is enforced where spend is counted**: in each command's item loop, from the `cost_usd` the adapter
  reports (as `run` does today), counted per process across passes (`--repeat`), and added to `arm-smoke`. A
  project's own adapter may call its model with a client of its own, never through the provider layer, so the
  provider layer (ADR-0005) enforces the same cap only as a second net, for the bundled provider.
- A command that runs others (`sweep`, `model-onboard`) gives each the part of the job's cap still unspent, from the
  spend each child reports in its `--json` envelope: `sweep` captures each child's output (today it does not) and
  streams it to the job's log as it comes.
- `judge` keeps its config's cap as well; the lower of the two applies.
- **A round's budget is enforced**, by the spending commands themselves, so a run from the terminal and a job
  stop at the same place. A command that spends on a goal with an open round that has `budget_usd` takes, as its
  cap, the least of its own cap and what the round has left: the budget, less what the round's runs have spent (as
  `evh rounds` counts it), less what the round's running commands have reserved. It reserves that cap when it
  starts, in the round's ledger (`.build/rounds/<goal>/<round>.json`, under the `goal:<goal>` lock for the moment it
  writes), and records what it spent when it ends. A stopped or crashed run writes no `metrics.json` and so is not
  among the runs `rounds` counts, though its items were paid for: the supervisor, not the command, closes the
  reservation, reading the run's written items for what was actually spent. The budget left is the budget, less the
  round's visible runs, less the ledger's closed entries whose run is not visible, less the open reservations. Nothing left: the command is refused before it calls a model (`ERROR (over-budget)`). So
  ten arms of one round started at once cannot overrun its budget together.

`POST /api/v1/estimate` runs a command's `--dry-run` and returns what it prints, so the Workbench shows what a job
will do and cost before it starts (PRD-017's functional requirement 3, Jobs, and its goal 4). 8 commands have one: `run`,
`sweep`, `judge-score`, and five that migrate or remove (`data-migrate`, `data-rm`, `dataset-migrate`,
`fingerprint-migrate`, `run-migrate`). `arm-smoke`, `judge` and `model-onboard` have none: the Workbench shows their
cap instead of an estimate until they get one.

### Who acted

Every job records who asked for it and why (`by`, `reason`). Its actor reaches every command through `EVH_ACTOR`
/ `EVH_FOR`, set by the supervisor (Jobs, above), so every record a job writes names it as RFC-027 records the
command line's; `--by` and the reason's own option are passed only where they mean that. The MCP server stays
read-only (RFC-027): an agent acts through the command line or a job.

### Every command answers `--json`

The Workbench shows a job's result as data, not as text to scrape. 43 of the commands the API serves have no `--json`
today (the table below), 2 read commands among them. Each gets it, with the envelope the others use; a test fails
on a served command without it. Until a command has it, its job's result is its exit code and its log.

### The data page's routes and ADR-0027

PRD-017 retires the Configure page and its routes (its decision 4) and serves the Workbench in both stores (its
functional requirement 5). The API is how the Workbench writes, so, accepted, it amends ADR-0027 in two places, by an
ADR of its own: writes are no longer SQLite only and need no `configure: true` (the token and the rules above gate
them instead), and the seven `/api/data/` routes are removed when the Workbench's settings screen (W8) replaces the
page. Until then they take the API's locks and token too.

### Both stores

The API runs commands; the commands read and write through `_store`. Nothing in the API knows which store the project
has, except a migration's `503` above, so it works the same in either (RFC-025).

## Build order

1. `_store`'s whole-file writes in a files project, and a list of what each writing command writes in what order
   (what a reader sees mid-command), with a test per command that matters (a run, a rescore, a reference promotion).
2. The registry (kinds, the options never taken, the lock table), the token, and the read side, with the parity
   test (every read command's API answer equals its `--json` from the command line).
3. Jobs: the supervisor, locks passed to the command, state, logs, stop, unsupervised and lost, resume with the run
   id given up front.
4. The server's own writes on the same locks; `catalog` as a swap; `data-migrate`'s `503`.
5. The cap in the provider layer, per process; children given the rest; the round's budget and its ledger; the
   estimate.
6. (0.8.0, planned) `evh jobs-start`, `jobs-status`, `jobs-logs`, `jobs-stop`, `jobs-resume` over the same jobs.
   They are commands like the rest, classified in the registry as not served (the API has its own job routes) and
   in `NOT_TOOLS`.
7. `--json` for the 43 commands, in groups (datasets, labels and references, rounds, runs, the rest).
8. The Workbench (PRD-017) on top, and the ADR that amends ADR-0027.

## Testing

- Parity: every read command through the API and through the command line give the same JSON.
- Refusals: no token, a wrong token, another Host, a foreign Origin, a non-read without the header, an option the
  registry does not list (`--adapter`, `--runs-dir`, `--command`), a path as an argument, a config whose adapter is
  outside the project: each refused before anything runs. `--public` and `--behind-proxy` answer no `/api/v1/`
  call. A decision job without `by`; a job's records name its `by`.
  Every served `Path` argument has a kind; `label-sheet` as a job gives its sheet as a download.
- A job's life: started, followed by offset, succeeded with its result; a failing command reports its refusal kind; a
  stopped job's process group is gone; a killed supervisor shows `running (unsupervised)` and keeps its locks while
  the command lives, `lost` after; `run` resumed continues the run id it was given.
- Locks: two `run`s of one config, the second queued until the first ends; two configs at once; a `reference-promote`
  waits for a `run` on its dataset; a `rescore --round` waits for a `round-close` of its goal; two `catalog`s never
  run together and the served pages never 404 during one; a migration waits for every job and every job for it;
  a server restart in the middle changes none of it.
- Spending: a spending job without `max_cost_usd` refused; `run --repeat 3` stops at one cap in total; `arm-smoke` and
  `sweep` stop at the job's cap, with a project adapter that never calls the provider layer. A round's budget: a run that would pass it stops at it, from the terminal and as a
  job alike; two runs started at once share what is left, never both all of it; a stopped or lost run's paid items
  count against the budget; with nothing left a run is refused before its first call.
- Uploads: 50 MB taken, one byte more refused, nothing kept of it.
- The terminal's job commands: a job started with `jobs-start` is listed by the API and stopped by `jobs-stop`, and
  one the Workbench started is followed by `jobs-logs`.
- Both stores: the job and lock tests in each (`make stores-check`); `data-migrate` as a job with the server up.

## Alternatives considered

- **A hand-written endpoint per resource** (`/datasets`, `/runs`, …): 80 commands written twice, and the two drift.
  Made from the parsers, the API cannot fall behind the command line.
- **Running commands in the server's own threads**: the commands exit with `sys.exit`, keep module state and can run
  for hours; a child process isolates each, as the MCP server already does.
- **Locks in the server's memory**: lost when it restarts, while the jobs go on. Lock files held by the command itself
  outlive both the server and the supervisor, and free themselves when the command ends.
- **Only the header and the Host check, as the data page has**: enough against other web pages, not against another
  user's process on the same machine, which can reach 127.0.0.1; with every command behind the API that is code
  execution as the project's owner. Hence the token.
- **Writes through the MCP server**: MCP is the agents' protocol and stays read-only (RFC-018); a browser needs HTTP and
  jobs it can follow and stop.
- **RFC-011's job sets as they were drafted** (a set of runs with phases and an ssh runner): a job here is one command,
  which is what a Workbench step is; phases and the ssh runner were dropped (owner, 2026-11-09; PLAN_0.8.0, open
  question 3).

## Decided by the owner (2026-11-08)

1. **A job whose lock is held waits** in a queue and starts when the lock is free ("waiting"). `flock` gives no order,
   so a queued job says which job it waits for, not its place.
2. **An upload is at most 50 MB** (the proposed size).
3. **The terminal gets the same jobs** ("yes") (0.8.0, planned): `evh jobs-start`, `jobs-status`, `jobs-logs`, `jobs-stop`,
   `jobs-resume` (above).
4. **A round's budget is enforced** ("enforce"), by the spending commands, from the terminal and as jobs alike, with
   a reservation per running command so parallel runs cannot overrun it (Spending, above).

## Decided by the owner (2026-11-09)

5. **The API is not served behind a proxy** (Who may call, above): local only in 0.8.0. A team reads through
   `--behind-proxy` and each person writes as themselves, with their own account on the machine or their own clone,
   recorded as RFC-027's actor; a shared write API needs real identities and permissions, a design of its own
   (PRD-017's "later question").

## The commands, and how the API serves them

Generated from `evh --help` and `mcp_server.READ_TOOLS` / `NOT_TOOLS` on 2026-11-08, updated 2026-11-09: 29 read,
40 jobs, 6 jobs that spend, 7 not served (`capture-scrub` runs a program it is given). RFC-027 adds `baselines`
(read), `baseline-rollback` and `baselines-migrate` (jobs); the table is generated again from `cli.COMMANDS` at the
build, and its test fails on a command it does not classify.

| command | served as | `--json` | why |
| --- | --- | --- | --- |
| `activity` | read | yes | reads only (an MCP tool) |
| `arm-from-capture` | job | **no** | writes a config and a run |
| `arm-smoke` | job, spends | yes | runs a system on a few items, may spend, and writes the model record |
| `arms` | read | yes | reads only (an MCP tool) |
| `bootstrap-test` | job | **no** | a statistics command; not yet a tool |
| `capture` | job | **no** | reads a production system and writes |
| `capture-restore` | job | **no** | reads a source and writes records and item files |
| `capture-scrub` | not served | **no** | runs a project's command and writes |
| `captures` | read | yes | reads only (an MCP tool) |
| `catalog` | job | **no** | writes the pages |
| `catalog-serve` | not served | **no** | it is the server |
| `cost-report` | job | **no** | a report tool; not yet a tool |
| `data-ls` | read | yes | reads only (an MCP tool) |
| `data-migrate` | job | **no** | moves the project's data between files and its database |
| `data-put` | job | yes | writes a setting |
| `data-rm` | job | yes | deletes a setting or a run |
| `data-show` | read | yes | reads only (an MCP tool) |
| `dataset-unseal` | job | **no** | a decision: recorded with who acted (RFC-027) |
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
| `label-coverage` | read | yes | reads only (an MCP tool) |
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
| `round-close` | job | **no** | a decision: recorded with who acted (RFC-027) |
| `round-open` | job | **no** | a decision: recorded with who acted (RFC-027) |
| `round-retire` | job | **no** | a decision: recorded with who acted (RFC-027) |
| `rounds` | read | yes | reads only (an MCP tool) |
| `run` | job, spends | yes | runs a system and may spend |
| `run-compare` | read | yes | reads only (an MCP tool) |
| `run-migrate` | job | **no** | rewrites the run directories |
| `run-promote` | job | **no** | a decision: recorded with who acted (RFC-027) |
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
