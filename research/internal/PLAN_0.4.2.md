# Harness 0.4.2 plan

0.4.1 (2026-10-27, 0de7b423) shipped the inspector OOM fix. Everything else found on the
deployed 0.4.0 goes here, in the owner's order.

## 1. Catalog home: KPI tiles with trends, and more time filters

Decided 2026-10-27:

- **Periods are measured from today, in the browser.** The page embeds the per-day numbers;
  the browser works out each period from the viewer's date, so "current week" is this week
  even when the catalog was built days ago. Tiles, trends, charts and the feed follow the
  period switch.
- **Periods**: last 7 days, last 14 days, current week, last week, current month, last month,
  last 90 days, current year, all time. A trend compares a period with the one before it of
  the same kind (this week against last week, the last 14 days against the 14 before).
- **Flow tiles** (measured runs, billed, tokens): the period's total, ▲/▼ % against the
  previous period, a sparkline.
- **Stock tiles** (datasets, configs, arms, references, metrics, goals): the total and "+N new"
  in the period. A dataset with no `created_at` is new on the date of its first run.
- "new: nothing in the previous period" instead of ∞%.
- `evh overview --period P` prints the same numbers (CLI parity).
- Screenshots to the owner before it ships.
- Owner's review of round 1 (2026-10-27): colour in the tiles, never red/green (up and down are
  neither good nor bad); chips instead of the dropdown; one short line for what the trends
  compare with, the dates in its title. Round 2 gave each tile its own colour: "a circus".
  Round 3 (kept): four colours, one per subject, the tiles in that order with a legend: goals;
  data (datasets, references); experiments (configs, arms, metrics); work and spend (measured
  runs, billed, tokens).

### 1b. The pages a tile opens carry the period too (owner agreed 2026-10-27)

A tile is a door. Today none of the pages it opens knows the period, and the configs and arms
tiles open the datasets page, which lists datasets only. One system, not one dashboard:

- **Everywhere a tile leads:** the same period chips; the period travels with the click
  (`datasets.html#p30d`, a bare anchor token); a **new** badge in the group's colour on rows made
  in the period; table chips **all / new in period / active in period**.
- **Datasets:** runs in the period with ▲▼ against the period before, spend in the period, a
  line of runs per day per row, grouping by goal. It keeps a table of each dataset's arms, and
  links to the full arms page.
- **Arms and configs: a first-class page** (owner: "super useful for 0.5.0 later"). The arms
  tile opens it ungrouped, the configs tile grouped by config. Beyond the big table of every
  arm, what else it holds is still to be designed (below).
- **Goals:** runs and spend in the period per goal with ▲▼, and what happened in it (a baseline
  promoted, a round opened or closed), from the events the feed reads.
- **References:** the new badge, arms scored in the period.
- **Metrics:** the new badge (from the first run recording it), arms recording it in the period,
  grouping by decides / weighs / describes.
- **Activity: a page of its own** (owner agreed). The two charts full width; tables by dataset,
  by arm and by kind for the period against the one before, what moved most first. The home
  section stays a summary that links to it. Measured runs, billed and tokens open it.
- **`evh` parity:** `--period` on `evh datasets`, `goals`, `references`, `metrics`; `evh arms`
  lists every arm; `evh activity`.
- **No personalisation for now** (owner): the period is not remembered between visits; only the
  link carries it.
- **Order (owner, 2026-10-27):** the shared parts first (chips on any page, the period in the
  link, the new badge, the row chips), then goals, datasets, references, metrics and activity,
  with screenshots for review as each lands; the arms page (1c) last. UXS-001 follows each.

### 1c. The arms page (owner: all six, 2026-10-27)

The arms page is one of the six pages a tile opens (goals, datasets, references, metrics, arms
and configs, activity), so it carries everything in 1b like the others: the period chips, the
period in the link, the **new** badge, the **all / new / active in period** chips, runs and spend
in the period with ▲▼. On top of that, all from data the catalog already reads:

1. **The table of every arm**, grouped by dataset, config, model, provider or what it is scored
   against (gold / silver / judge). Per row: role badges (baseline, recommended, leader, retired
   in a round, over a goal's limit), the goal's deciding metric and value, repeats, cost per
   item, latency, first and last run, runs in the period with ▲▼.
2. **Configs view:** one row per config across every dataset it ran on: model, provider, its
   arms, total spend, its rank on each goal. Where 0.5.0's prompt versions and studies land.
3. **Derived arms under their source:** a rescored or judged arm nested under the arm it came
   from, with how its number moved.
4. **Facets** as filter chips on the table: local / hosted, open / proprietary, cost and quality.
5. **What changed in the period:** new arms, retirements, baselines promoted, rescores (the
   feed's events, filtered to arms).
6. **Comparison actions:** tick arms and open them in the inspector; pick a goal and see its arms
   on a cost × quality scatter.

`evh arms` lists every arm with the same grouping (`--by dataset|config|model|provider|scored`)
and `--period`; `evh arms --configs` the configs view.

## 2. Observability of the prod inspector (homelab session's request, 2026-10-27)

**The harness stays generic (owner, 2026-10-27).** Someone running the harness locally uses none
of this, so the package gets only hooks, and the deployment fills them:

- Harness: `evh catalog-serve --hooks FILE.py|module:object`, a small documented interface
  (start, around each request with route/status/duration, an unhandled error, an extra route).
  No hooks given: behaves as today, no new dependency, nothing about any deployment.
- Deploy only (`infra/`): `inspector_hooks.py` implements them with sentry-sdk and
  OpenTelemetry and serves `/metrics`; render.sh vendors the SDKs next to the deployed package.

What the deploy's hooks do:

- Error reporting: Sentry SDK to a new GlitchTip project (backend, separate from evals-web's CSP
  project), environment=prod, release=sha-<7>.
- Traces: OpenTelemetry, service.name evals-inspector, deployment.environment prod,
  service.version sha-<7>.
- `/metrics` on the inspector (requests, latency, cache sizes, RSS); homelab adds the scrape.
- Grafana dashboard evals-humancopilot-eu: panels for evals-nginx and inspector logs
  (`{app="evals"}`).

## 3. Anything else found on the way

- **Why the long runs are slow** (owner, 2026-10-27): local `make ci` takes ~25 min and CI's `verify` ~30 min. Find where the time goes and what can be cut. No long runs until the 0.4.2 scope is locked.

Decided with the owner when it comes up.

## 4. Tests

- **Memory budget**: start the inspector with `--warm` on a built catalog; fail if peak RSS
  passes 200 MB (prod limit 256 MiB; prod peaked at 235 MB on 0.4.1's warm-up, locally 147 MB:
  find out why). Runs in CI on every PR. Also checks the SDKs' cost from 2.
- **Response-time budget** for the heaviest inspector answers, cold and cached, with limits
  generous enough for a slow runner. Measure the CI cost first.
- **The test pyramid, written down**: unit (stats, adapters, scorers), integration (build a
  catalog, query the inspector over HTTP), end to end (`test_inspector_browser.py` in Chromium),
  and the resource tier above. Measure line coverage once to see the real gaps.

## Decisions

- The deployment layer stays in `infra/` of this repo (owner, 2026-10-27): outside the package (the wheel ships only `harness/`), no secrets in it (DSNs and endpoints from the box's env); the harness gets generic hooks only.
- (Decided 2026-10-27: the official SDKs, sentry-sdk and opentelemetry-sdk with the OTLP/HTTP exporter, as dependencies of the deployed inspector only, not of the evh package; their memory measured against the 256 MiB limit.)

## Status (2026-10-27)

- Done on 042: 1 (home, the five pages, the arms page, the grouped menu), `--period` on every
  list, `evh arms --by/--configs`, `evh activity`, the docs (UXS-001/003, PRD-004, RFC-003,
  INTEGRATION, ADR-0018, CHANGELOG), 2's code (`--hooks` in the harness; `infra/inspector/`,
  render.sh, compose, evals.alloy) proven locally against stand-ins, and the dashboard's rows
  (chipi/humancopilot.eu, worktree `evals-dashboard-obs`, commit cc297aa, not pushed).
- Then: 4 (tests), then 3 (the long runs).

## At the 0.4.2 deploy (owner, 2026-10-27: wait until then)

In this order, each its own approval:

1. Create the GlitchTip project `evals-inspector` (platform python) on the mini, separate from
   evals-web's CSP project; read its DSN; tell the homelab session the slug (projects.json).
2. The prod session writes `/srv/evals/observability.env` (mode 644): `SENTRY_DSN=<dsn via the
   tailnet TLS node>`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://vtraces.<tailnet>/insert/opentelemetry/v1/traces`.
3. Merge 042, deploy; check the start line (`hooks: sha-…; GlitchTip on, traces on`), the
   inspector's memory under 256 MiB after `--warm`, `up{job="evals-inspector"}` = 1, a span in
   VictoriaTraces, and prove GlitchTip with one test event (telemetry-probe), then delete it.
4. Push chipi/humancopilot.eu `evals-dashboard-obs`, PR, then import the dashboards on the mini
   (`import.sh`).
