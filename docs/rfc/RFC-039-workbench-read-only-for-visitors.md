# RFC-039: The Workbench as a read-only viewer for visitors who are not signed in

- **Status**: Accepted as a decision (owner, 2026-11-23); not built. Built in 0.8.1 (`research/internal/PLAN_0.8.1.md`, F2).
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-017](../prd/PRD-017-workbench.md) (the Workbench; its non-goal and D8 are amended here)
- **Related RFCs**: [RFC-026](RFC-026-an-api-for-every-command.md) (the API's token and "Who may call", amended),
  [RFC-032](RFC-032-one-model-two-surfaces.md) (the operations and their kinds), [RFC-019](RFC-019-datasets-from-production.md)
  (`text: hidden`), [RFC-003](RFC-003-catalog-adapter.md) (the public inspector's limits), [RFC-038](RFC-038-call-once-artifacts-judge-validation-harbor.md)
  (an artifact is never public)
- **Related ADRs**: [ADR-0027](../adr/ADR-0027-the-data-page-writes-locally.md) (writes on this machine only; unchanged)
- **Code**: `harness/scripts/catalog_serve.py` (`allowed`, `_api`, `_model_route`), `harness/scripts/_visibility.py`,
  `harness/scripts/ops/registry.py`, `harness/workbench/`, `infra/compose.yml`, `infra/caddy/evals.caddy`
- **Screens**: [UXS-005](../uxs/UXS-005-workbench.md), section "The viewer"

Paths are relative to `harness/scripts` unless they start with `harness/`, `docs/`, `infra/` or `research/`. Read
2026-11-23 in the 0.8.1 worktree; the operation counts come from `ops.registry` on that day.

## Abstract

A visitor to the deployed site who is not signed in can open the Workbench and read everything the public rules allow:
goals, rounds, datasets, systems, models, runs, comparisons. They can write nothing, spend nothing and need no token.
Today the deployed server answers 404 for `/workbench/` and `/api/v1/` (`allowed`, `catalog_serve.py:617-623`).

## Decision (owner, 2026-11-23)

A visitor who is not signed in sees the Workbench as a viewer: everything readable, nothing written, nothing spent, no
token. This amends PRD-017's non-goal "a public, multi-user service" and its decision D8, "the Workbench is refused behind
a proxy", and RFC-026's rule that `--public` answers none of `/api/v1/`.

It is enforced at the server. The page's viewer mode is a courtesy to the reader; it is not a control.

## What a viewer can and cannot do

**Who is a viewer.** Any request to a server started with `--public`. That server makes no token (`API_TOKEN` is set
only for a local server, `catalog_serve.py:1688-1692`), so no request to it can carry one. A server started with
`--behind-proxy` (the team's private proxy) keeps its 404: this RFC does not change it.

**The rule, by operation kind.** An operation has a `kind` (RFC-032). On a public server:

| Kind | Operations | Served to a viewer |
| ---- | ---------- | ------------------ |
| `read` without `public_dropped` | 62 | yes, as listed below |
| `read` with `public_dropped` | 11 | no (refused 404, as the MCP server leaves them out) |
| `edit` | 14 (`goal-new`, `goal-set`, `system-new`, `system-set`, `model-new`, `model-set`, `scorer-new`, `scorer-set`, `fieldset-new`, `fieldset-set`, `failure-modes-new`, `failure-modes-set`, `deployment-new`, `deployment-set`) | no: they write |
| `decision`, answered in the server's process | 1 (`deployment-accept`) | no: it writes |
| every job (`op.is_job()`): `work` 49 and `decision` 12 | 61 | no: they write, spend or run a model |

`op.is_job()` is false for the 14 edits and for `deployment-accept` as well as for the reads, so "not a job" is not the
test for a read. The test is `op.kind == "read"`. An edit is a `POST` or `PATCH` on a resource's route and is answered
in the server's own process; it is refused on a public server for that reason, not because it is slow. Without a token
every one of these is refused (403 for a write, which also lacks `X-EVH-Data`), and the server never reaches the code
that would run it.

**Every job is refused without the token**, by name: `arm-from-capture`, `arm-smoke`, `baseline-rollback`,
`bootstrap-test`, `capture`, `capture-restore`, `catalog`, `cost-report`, `data-migrate`, `data-put`, `data-rm`,
`dataset-create`, `dataset-describe`, `dataset-extend`, `dataset-from-capture`, `dataset-materialize`,
`dataset-profile`, `dataset-publish`, `dataset-seal-counts`, `dataset-split`, `dataset-unseal`, `exposure-add`,
`exposure-check`, `faithfulness`, `faithfulness-name`, `fieldset-propose`, `holdout`, `import-run`, `importer-check`,
`judge-score`, `judge-validate`, `label-from-capture`, `label-from-run`, `label-import`, `label-sheet`, `migrate`,
`model-onboard`, `pick`, `prompt-export`, `prompt-version`, `reference-manifest`, `reference-promote`, `rescore`,
`round-carry`, `round-close`, `round-open`, `round-retire`, `run`, `run-promote`, `score-preview`, `sheet-export`,
`sheet-import`, `silver-calibrate`, `source-preview`, `study-ask`, `study-confirm`, `study-import`, `study-run`,
`study-stop`, `study-tell`, `sweep`. Ten of them spend (`run`, `sweep`, `judge-score`, `judge-validate`, `arm-smoke`,
`model-onboard`, `faithfulness`, `study-run`, `study-tell`, `study-confirm`). The jobs' own routes (`/api/v1/jobs`,
`/jobs/{id}`, its log, files, `stop` and `resume`) are refused as well: a deployed copy runs no job, and a job's log may
quote a project's text.

**`POST /api/v1/estimate` is refused.** It runs a job operation's dry run in a child process, and a public server starts
no process for a visitor.

**The other fixed routes.** `GET /api/v1/openapi.json` is served (it describes routes, not data). `GET /api/v1/session`
is refused: there is no token to trade for a cookie.

**The sheet and an item's input are refused publicly, as the inspector refuses them.** `sheet-show` is a `read` with a
`public_dropped`, the sheet's `/api/sheet` and its CSV are 403 on a public server (`sheet`, `sheet_csv`), and an item's
input (`source` in the item view) is served only when the server is local (`catalog_serve.py:195-199`).

### The reads

Served to a viewer: **yes**. A `-` names an input a public server does not take (`public_hidden`).

| Operation | Viewer | Why, and what it shows |
| --------- | ------ | ---------------------- |
| `activity-show`, `baselines`, `goal-history`, `goal-leaderboard`, `goal-list`, `goal-show`, `goal-status`, `leaderboard`, `looks`, `metric-list`, `metric-show`, `overview-show`, `period-compare`, `periods`, `runs-list`, `run-compare`, `round-list`, `round-show`, `round-evidence`, `study-list`, `study-show` | yes | numbers, ids and the project's own text about a goal, a round or a study |
| `arm-list`, `dataset-arm-list`, `arm-show`, `capture-list`, `capture-show`, `dataset-list`, `dataset-show`, `dataset-card`, `reference-list`, `reference-show`, `label-set-list`, `tag-set-list`, `tag-set-show`, `deploy-sheet`, `deployment-history`, `deployment-show`, `faithfulness-show`, `system-list`, `system-show`, `model-list`, `model-show`, `scorer-list`, `scorer-show`, `fieldset-list`, `fieldset-show`, `failure-modes-list`, `failure-modes-show`, `licences`, `picks`, `search` | yes | records and manifests; counts, ids, hashes |
| `dataset-items` (`-item`) | yes | an item's id and its fields; its text only where `text_shown` allows, and the item's own text input is not taken |
| `label-set-show` (`-items`) | yes | the set's record; the per-item labels are not taken |
| `comparison-show`, `comparison-crosstab` (`-group`, `-group_match`) | yes | the paired numbers; the grouping inputs, which could read a hidden field, are not taken |
| `chart` (`-svg`) | yes | a chart's data; the rendered SVG is not taken |
| `pair-test`, `family-test` (`-permutations`), `rank-stability` (`-draws`) | yes | statistics; the inputs that make a test run long are not taken |
| `prompt-list`, `prompt-show`, `prompt-diff` | yes, with a question to the owner (below) | a prompt is the project's, not a dataset's, so `text: hidden` does not cover it |
| `comparison-item` | no | an item's text and each arm's output |
| `comparison-items` | no | the recorded texts: outputs, references and labels |
| `sheet-show` | no | the sheet shows outputs and labels |
| `judge-verdicts` | no | a judge's reasons describe the outputs it judged |
| `data-ls`, `data-show` | no | the project's files and a file's text are this machine's (UXS-004) |
| `label-coverage-show`, `label-mutants` | no | they read a rules file by path and the captures |
| `exposure`, `sealed-counts` | no | a held-out side's reads and counts are the project's own safety watch |
| `validate` | no | a public copy is not a whole project: it fails by design |

That is 62 served and 11 refused, the same split the public MCP server makes (`mcp_server.read_ops(public=True)`), so
this RFC adds no operation that is not already offered to the public in a tool.

## Text under the public rules

Every read served to a viewer runs as a public call. It asks `_visibility.text_shown(dataset, public=True)`: false for a
dataset whose file says `"text": "hidden"` (RFC-019), and then nothing that comes from that dataset's text is shown,
whatever `--publish` says: its items' sources, every arm's outputs, its references' texts and labels, judge reasons, text
and URL fields. For a dataset that is not hidden, `--publish` decides: outputs and references are served only when named
(`--publish outputs`, `--publish references`), as the item view does today (`catalog_serve.py:136-190`). An artifact is
never public (RFC-038). Counts, scores and ids stay. A system's `params.prompt` (any prompt text its yaml carries) and a recorded prompt file's text (`prompt-show --text`, `prompt-diff`) are prompts: served, in the public MCP and in the catalog export only with `--publish prompts` / `catalog: {publish: [prompts]}`; a reference's promotion reason and a prompt version's note are project notes and stay public (owner, 2026-11-23).

**What the deployed copy holds** (checked 2026-11-23, `research/internal/PLAN_0.8.1.md`, F2): no item text (dataset
records carry row numbers and hashes; `data/materialized/` is gitignored); the arms' outputs (313 `outputs.jsonl`,
already published by `--publish outputs`); gold references as manifests, except 132 one-word Orrery triage labels; no
dataset is `text: hidden`. For this site a viewer therefore reads nothing that is not already public. For a project that
commits text, the public rules above still apply to every read.

**Not verified.** That each of the 62 reads applies `text_shown`. The registry has the 11 drops, the `public_hidden`
inputs and four code paths that ask `public_env()` (`model/dataset_views.py`, `model/compare.py`, `ops/datasets.py`,
`catalog_views.py`); I did not read the other reads' bodies. The first step of the build is a test that closes this: a
fixture with a `text: hidden` dataset whose every text carries a marker word, every served read called as a viewer, and
the marker found in none of the answers (the shape of `test_hidden_text.py`, RFC-019).

## Enforcement is at the server

`allowed` and `_api` change as follows, each with a test that calls the server without the page:

1. On a public server `/workbench/` and `/api/v1/` are served (today `allowed` answers 404 when `LIMITS["hosts"]` is set).
2. `_api` serves, without a token, a `GET` whose operation has `kind == "read"` and no `public_dropped`, with only the
   inputs `op.schema(public=True)` allows, in `public_call(True)`.
3. Any other method, any other operation, `/jobs*`, `/estimate` and `/session` are refused before any operation runs.
4. The Host check, the foreign-Origin check and the path checks stay.
5. The `X-EVH-Data` and `by` rules for a write need no change: a public server has no token, so no write reaches them.

## The page's viewer mode

When the page is served by a public server (`GET /api/v1/session` answers 401, or the shell is built for it) it shows:

- no control that acts: open, run, estimate, close, retire, carry in, promote, save, delete, and the screens that exist
  only to act (Jobs, Settings, bringing in a model, and the editing forms);
- a line on every screen: "This is a read-only view of a published project." with how to run your own (`pip install`,
  `evh init`, `evh catalog-serve`, linked to the install page);
- each screen's command still shown as text, as UXS-005 requires everywhere, so a reader can see what the action would be.

The page hides a control; it does not decide what is allowed. A request the page would not send is refused by the server.

## Limits

- **Rate.** Reads are under the public inspector's per-client limit, `--rate` (the deployment sets 60 a minute,
  `infra/compose.yml`; the code's default is 30), counted by `X-Real-IP`. Today only `/api/*` is counted
  (`catalog_serve.py:1481`); `/api/v1/` reads are counted the same way.
- **Memory.** The inspector's container has `mem_limit: 384m` (`infra/compose.yml`; raised from 256m after a peak of
  228 MiB under 400 distinct questions, review of 2026-10-29), and `make budget-check` guards the budget. The reads add
  an answer cache of the same bounded size and no process per request. The plan's figure of 256 MiB is out of date:
  the limit is 384 MiB, and the build is not done until `budget-check` passes at it.
- **Concurrency.** Reads compute in the server's own process; the existing cap of two concurrent comparisons applies.

## The deployment

- `infra/caddy/evals.caddy` routes `/workbench`, `/workbench/*` and `/api/v1/*` to the inspector (one named matcher,
  `@workbench`), beside `/catalog/api/*` (which it answers as `/api/`), and refuses a request body over 1 KB there.
- `infra/compose.yml` keeps `--public evals.humancopilot.eu`, `--rate 60`, `--publish outputs`, and adds
  `--catalog-at /catalog/`. No token.
- The site's home page (section 06) links to the Workbench; the Workbench's own catalog links go to `/catalog/`.

**Built in 0.8.1** (where the build says more than the design):

- **How the page knows it is a viewer:** every `/api/v1` answer of a public server carries `X-EVH-Viewer: 1`, and
  `X-EVH-Catalog`, the path `--catalog-at` names (`/` when not given), for the page's links to the catalog. No
  request of its own, no setting. The header is a courtesy: the refusals are the server's.
- **What a refusal says:** a write, a job, `POST /estimate`, `/jobs*` and `/session` answer 403 with `kind:
  not-public`; a dropped read 404; a `public_hidden` input 400. `HEAD` answers 404 on a public server.
- **The reads** run as public calls (`_visibility.public_call`), two at a time, their answers kept in the server's
  bounded cache, and count against the rate limit.
- **The page** shows the one-line notice, leaves Jobs and Settings out of its menu, and removes every acting control
  as it is drawn; a screen whose only job is to act says "not shown publicly", with its command and a link home.
- **Tested** by `tests/test_workbench_viewer.py` (every route, through HTTP, on a fixture with a `text: hidden`
  dataset whose marker word must reach no answer) and `tests/test_workbench_viewer_browser.py` (every screen in the
  menu at 1280 and 390 px: no acting control, the notice, no marker word, catalog links under `--catalog-at`).
- **Not verified before the deploy:** `caddy adapt` on the new matcher (it runs on the box, before the reload, and a
  failure keeps the old config).
- After the deploy, `deploy-verify` passes, and its checks include: `GET /workbench/` is 200; a read of `/api/v1`
  is 200; a job and `POST /estimate` are refused; the sheet is refused.

## What this amends

- [PRD-017](../prd/PRD-017-workbench.md): the non-goal "A public, multi-user service" and D8, each now pointing here and
  keeping its old text, marked "amended by RFC-039".
- [RFC-026](RFC-026-an-api-for-every-command.md), "Who may call": `--public` no longer answers none of `/api/v1/`; it
  serves the reads above without a token. `--behind-proxy` is unchanged.
- [UXS-005](../uxs/UXS-005-workbench.md): a new section, "The viewer".
- ADR-0027 and RFC-032 are not changed: writes stay this machine's own.

## Non-goals

- Any write from the deployed site.
- Any sign-in for visitors, an account, a cookie or a token for a viewer.
- Multi-user accounts, or a hosted service in which people run their own projects.
- Serving the sheet, an item's input or an artifact publicly.

## Alternatives considered

- **Serve every operation that is not a job.** Rejected: 14 edits and `deployment-accept` are not jobs and write.
- **Keep the 404 and publish the Workbench as static pages.** Rejected by the owner's decision: the Workbench reads
  through the API, and a second, static rendering would drift from it.
- **A read-only token handed to visitors.** Rejected: it is a sign-in in all but name, and a public token is not a secret.

## Open questions

1. Prompts: decided (owner, 2026-11-23). A prompt's text is served publicly only with `--publish prompts` (see "Text
   under the public rules" above); without it, `prompt-show` and `prompt-diff` answer without the text, and the viewer
   says the text is not published. The deployment does not set it.
