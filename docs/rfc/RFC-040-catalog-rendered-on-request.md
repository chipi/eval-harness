# RFC-040: The catalog rendered on request, and exported: one renderer, two drivers

- **Status**: Accepted and built (0.8.1): all six steps (owner, 2026-11-23); `research/internal/PLAN_0.8.1.md`, F3. "Built in 0.8.1" below.
- **Authors**: Marko Dragoljevic
- **Related RFCs**: [RFC-026](RFC-026-an-api-for-every-command.md) (the server's freshness: a write starts a `catalog`
  job, the pages are swapped in whole), [RFC-003](RFC-003-catalog-adapter.md) (the adapter the pages read),
  [RFC-039](RFC-039-workbench-read-only-for-visitors.md) (the public viewer; unchanged here)
- **Code**: `harness/scripts/catalog_build.py` (`collect`, `build`, `page`, the `render_*` functions),
  `harness/scripts/catalog_serve.py` (`fresh_check`, `request_rebuild`), `harness/scripts/model/view_cache.py`,
  `harness/scripts/model/goal_views.py`, `harness/scripts/axes.py`, `harness/scripts/stats.py`

Paths are relative to `harness/scripts` unless they start with `harness/`, `docs/`, `infra/` or `research/`. Read
2026-11-23 in the 0.8.1 worktree. An advisor review (Fable 5.1, 2026-11-23) checked the idea against the code before this
was written; its findings are folded in and cited by file and line.

## Abstract

The catalog is two things today. Its API, inspector and Workbench are a live web app: every request reads the store. Its
pages are a static site: `evh catalog` writes 1,906 files (43 MB for this repository), and `evh catalog-serve` serves
those files. When the data changes, the server notices within 0.25 s (`fresh_check`) and starts a background `catalog`
job that rebuilds every page and swaps the set in whole. Until the job ends (14 s here, longer on a bigger project), a
page shows the data from before the write.

This RFC makes the pages work like the rest of the server: a page is rendered when it is asked for, from the data as it
is at that moment, and kept until the data changes. The static export stays exactly as it is, for GitHub Pages and the
deployed site, because both drivers call the same renderer.

## The goal (owner, 2026-11-23)

"I want whenever I go to my catalog to be fresh with the latest data." An agent that writes through the Workbench, MCP or
the CLI on a homelab or a local server, then opens any catalog page, sees the write. And: "I do still want to retain this
option that catalog can be just a set of static pages", publishable where no server runs (GitHub Pages), where the
inspector does not work.

## Non-goals

- **The public server.** The deployed site serves its pages from nginx over a sealed, read-only store
  (`infra/compose.yml:11-13`); the public inspector never serves a page file (`catalog_serve.py:1785`, `:1598-1600`).
  Its data changes only by a deploy, so it keeps the export. Rendering on request is for a local server and
  `--behind-proxy`.
- **A new page design.** The HTML, the charts and what a page says do not change. The equality test (below) holds it.
- **Rendering in the browser.** Rendering from `/api/v1` in JavaScript would break the export and duplicate about 5,000
  lines of Python.
- **Rebuilding only the pages a write touched.** One run write changes the home page, the activity page, the dataset, the
  arm, its goals, the metrics, the arms and models tables, the scorers and four `*.js` indexes. Tracking that graph
  across five modules is a liability, and it would still rebuild the heaviest pages.

## The design

**One renderer.** A function from a page address and the project's state to that page's bytes. Its inputs are explicit:

- the model: `collect()`'s `by_ds` and the values computed from it that pages share today by call order (`arm_rows`,
  `metric_index`, `v["versions"]`, the scorer pages, the recorded arms);
- the decisions (`goal_views.decided`, `group_decision`, `glance`), memoized for that state;
- the options: the deployment's flags, which today are module globals set only in `body()` and `build()`
  (`API, HEAD, ABOUT, BRAND, REPO, MCP, CARD, SECTIONS`, `catalog_build.py:4816-4817`, `:4951-4992`);
- `built`: the time stamped in every footer, now `datetime.now()` in `page()` (`catalog_build.py:511`).

**The address table.** Computed from the model, so it is itself a value of that state: every path the export writes,
with the function and arguments that make it. It includes the redirects (`_redirect` writes only where no page is,
`catalog_build.py:650`, so a redirect is "an address not in the table"), the `~items-k.html` pages whose count depends
on a dataset's profile (`:2291-2295`), the `*-rows.js`, `home.js`, `periods.js`, `search.js`, the pick, `inspect.html`
and the assets.

**Driver 1: export (`evh catalog`).** For every address, render and write. The output is the same set of files as today,
swapped in as today (`build_beside`).

**Driver 2: serve (`evh catalog-serve`, local and `--behind-proxy`).** A request for a page address renders it and keeps
the bytes, keyed on the data's fingerprint (`data_state`, 21 ms on the files store, 0.02 ms on SQLite) and the day. The
day is in the key because `catalog_models.py:164,322` mark a model "stale" against `date.today()`, as `view_cache.py:209`
already does for its results. No `catalog` job starts on a write. One model is held per process: on a change, the old
one is dropped, never two. The page cache is bounded in bytes, like `_CACHE_BYTES` (`catalog_serve.py:379`).

**Reading during a write.** The render functions read the adapter as well as the model (`A.scores` in
`goal_views.py:417`, `A.goals()` in `render_arm`, `A.deploy_sheet` in `_sheet_fold`, `A.rounds()`). Freezing the
adapter per state is not realistic. The rule: take the fingerprint, render, take it again, and keep the bytes only if
both agree. A page rendered across a write is served once and never kept, which is what the API's reads already accept
(`catalog_serve.py:845-868`).

**What a reader sees.** Each page shows the data current when it is opened: the normal web-app property. Today a reader
sees one build until the swap. The one new case is a link to an address that is gone under the new data (an arm
removed): a 404 instead of a stale page, and a renamed arm still has its redirect.

## What it costs (measured 2026-11-23, no code change)

Measured on this repository (7 goals, 19 datasets, 673 arms), wrapping the build's functions at run time and under
cProfile:

| Part | p-values cached (as `evh` and the server run) | p-values not cached |
| --- | --- | --- |
| `collect()` | 1.7 s (0.06 s on a second call) | 2.1 s |
| Home page | 0.58 s | 12.2 s |
| A goal page | 1.4-4.0 s (heaviest: `g/news_summary_cnn.html` 4.0 s, 2.2 MB) | 2.6 s average, 18.2 s for 7 |
| An arm page | 3-9 ms | 3 ms |
| Every other page | under 0.1 s (median write 0.2 ms; 29 of 1,906 over 0.1 s) | |
| Memory held after `collect()` | +125 MiB RSS (the held scores; `by_ds` pickles to 0.6 MB) | 112 MB (tracemalloc) |

Every `evh` command and the server turn on the p-value cache (`cli.py:113`, `catalog_serve.py:1767`); a script that
imports `catalog_build` directly does not. That is why the right column exists: it is the cost on a project's first
build, or after `_P_ALGO` changes.

**Where a goal page's time goes, cached:** the decisions (`group_decision`, 96 calls across the home and goal pages,
5.4 s of a 30 s build), the rounds block (`_rounds_block` 4.3 s, of which the deploy sheet per baseline `_sheet_fold`
3.9 s), the evidence charts (2.5 s), the trade-off charts (1.9 s) and the chart label collision loop
(`catalog_charts._crossed`, 1.15 s, 44,748 calls).

So a page rendered on request is fast except the goal pages, at 1.4 to 4.0 s. The decisions memo removes about a third of
that. The rest is the rounds block and the charts.

**Safe to memoize.** `axes.decide` takes only the goal, the arms' scores, the machines, the baseline and the clusters
(`axes.py:201-250`). Its p-values are seeded: sign-flip with `SEED = 20260926` and the deltas as float.hex
(`stats.py:45`, `:133-179`); bootstrap-t with the inputs as both key and seed (`stats.py:691-735`). Neither `axes.py`
nor `goal_views.py` reads the clock. The inputs outside the store are covered by `view_cache`'s state (`models.yaml`,
`config.yaml`) or are fixed for the process (`EVAL_HOST_LABEL`). The memo's home is `model/view_cache.py`, which keys on
the same fingerprint; it has three callers today, and the decisions are not among them.

## Risks, ranked

1. **Global state read across threads.** `RECORDED` (`catalog_build.py:291`, cleared and refilled in `collect()`
   `:861-862`) and `SCORER_PAGES` (`:293`, filled in `build()`) are module globals. Under `ThreadingHTTPServer`, a page
   rendered while another thread runs `collect()` sees `RECORDED` empty and drops a "recorded" badge, depending on
   timing. They move into the model.
2. **The deployment's flags.** A page rendered by the server would carry the defaults instead of the deployment's
   `--api /catalog/api/ --brand --head --about --mcp --card` (`infra/deploy/render.sh:132-136`). The server takes the
   same options, as one options value both drivers pass.
3. **Cold p-values from a request thread.** `stats.prefetch` spawns worker processes when a p-value is not cached
   (`stats.py:280`). `stats._KEPT` and `_DISK` are plain dicts with no lock found (`stats.py:421-430`). Until that is
   shown safe, cold renders are serialized per state (as `view_cache`'s in-flight events do for its own keys).
4. **Work that is cheap in a build and surprising in a request.** `_texts_tracked` runs git per dataset page on the files
   store (`catalog_build.py:2343`). Memoized per state, it runs once, but some request pays it.
5. **Order in `build()`.** `v["versions"]` is set just before `render_dataset` (`:4839-4841`), `_versions()` adds
   datasets that have never run to `by_ds` (`:897-898`), and `arm_rows` is computed once for two tables (`:4834-4836`).
   The address table must reproduce each; the coverage test catches a miss.
6. **Scores evicted.** `build()` holds every arm's scores unbounded (`scores_once(A)`, `:4822`); the server holds them
   under `view_cache.BUDGET` (`catalog_serve.py:1770`). A goal page that reads many arms can evict and reread in serve
   mode. To measure, not assume.

## Tests, written first

1. **Coverage.** The address table computed from a model equals the set of paths a build writes today: 1,906 entries,
   with the redirects, the `~items-k` pages, the `*.js` indexes and the assets. Written against today's `build()`
   before any refactor, it pins the page set.
2. **Equality.** For every address, the served bytes equal the exported file, both made with the same `built` and the
   same options: first in process, then a sample over HTTP. Run once with the p-value cache on and once off, to show it
   does not change a byte.
3. **Fresh, without a job.** The checks that a write starts a `catalog` job and costs "2 builds in all"
   (`harness/tests/test_catalog_fresh.py:202`, `:220`) are replaced: a write through the API, then the next request for
   the affected page shows it, and no job started. On both stores.
4. **Threads.** Many concurrent requests across a fingerprint change: every page served matches the export of one state
   or the other, never a mix, and the "recorded" badges are all there.

## The order of work

1. `page()` takes `built`; the deployment's flags become one options value; `RECORDED` and `SCORER_PAGES` move into the
   model. Behaviour does not change; the existing tests and the real-catalog browser test stay green.
2. Test 1, against today's build.
3. Split each `render_*` into "make the bytes" and "write". The export loop writes. Test 2 in process.
4. The decisions memo in `view_cache`. Measure again: the heaviest goal page's render on request.
5. The serve driver, tests 2 (over HTTP), 3 and 4. The `catalog` job is no longer started on a write; `evh catalog`
   still runs it on request.
6. If a goal page is still over about 1 s after step 4, the server renders the goal pages in a background thread after
   each data change (a warm-up, not a gate: a request still renders on its own if it comes first), and the charts are
   looked at for a memo of their own.

## Decided

- **Scope (owner, 2026-11-23): all six steps ship in 0.8.1.** "We ship everything in 0.8.1 ... It's not a functional
  thing, it's a non-functional thing." The advisor had recommended steps 1-2 and the decisions memo for 0.8.1 and the
  serve driver for 0.9.0.
- **Goal pages at 1.4-4.0 s.** Step 6 is part of "everything": if a goal page is still over about 1 s after the memo, the
  server warms it in the background after a data change, and a request that comes first renders it itself.

## Built in 0.8.1

**How, and where it differs from the design above.** The render functions were not split into "make the bytes" and
"write" one by one (about thirty of them, in four modules). Every page already goes through one function,
`write(out, rel, content)` (`catalog_build.py`); inside a Site's render it keeps the page instead of writing it. So the
unit the server renders is a *group*: what one existing render call writes (a goal's page, an arm's, a dataset's page
with its item pages, the home page with `home.js`, the redirects). The export and the server run the same calls, which is
what makes a served page the exported file. `render_goals` lost its goal pages to `render_goal_page`, one group each.

- `catalog_build.Site` (`prepare(A, built=…)`): the model (`collect`, the versions links, `arm_rows`, the metric index,
  the recorded arms, the scorer pages), `owner(path)` (a group from the path alone: the top-level names in `_TOP`, the
  goal, arm and metric pages from the model, a dataset's `~items-k` pages and the redirects by their folder),
  `render(group)`, `page(path)` (rendered with its group the first time, then kept), `export(out)`, `addresses`.
  `build()` is `prepare` and `export`; its output is unchanged (below).
- What a render reads that was a module global is the Site's, per thread: the footer's time (`built`), the recorded
  arms, the scorer pages, the pages so far (`_RENDER`). The module's globals stay for a project's builder that calls
  `arm_link` outside a render. Renders take one lock per process (`_RENDER_LOCK`, risk 3): the p-values' cache takes
  none of its own.
- The decisions memo (step 4) is `goal_views.decisions_kept`, held by a Site while it renders: a group's decision made
  once per state, keyed on everything `group_decision` is given, each caller getting its own deep copy.
- The server (`catalog_serve.py`): one current Site and the change it was prepared after (`site_gen`). A request is
  answered by a model at least as new as the data was when the request came: the kept one, the one another request
  was preparing meanwhile, or one it prepares (one at a time, so a burst of requests after a change prepares one model,
  not one each). `fresh_check`, `data_changed` and a server job's end count a change (`renew`) where they started a
  `catalog` job; a new day counts as one. The home page, the goals page and each goal's page are rendered ahead in a
  thread once the data has been still for a second (step 6): a run writing for minutes does not have them rendered
  for each write. A path the Site claims (a top-level page, a page's folder) and does not render answers 404; any
  other path falls through to the folder, so a file a project's builder wrote there is still served. HEAD is answered
  as GET without the body, and the address without its last slash redirects to it. The server takes `evh catalog`'s
  page options (`--brand`, `--api`, `--about`, …) through the same `configure` the build uses. It needs no catalog
  built first; health says `catalog: {mode: "on request", state: idle|failed, built_at, prepared, failed}`.
- `stats` collected a page's tests on a module-wide stack: on a server, a page rendered on another thread could take
  a stand-in p of 1.0. The stack is per thread (`test_stats_threads.py`, failing before the fix).
- The model records (`_models.records_kept`), held by a Site while it renders like the decisions: each goal page's
  deploy sheet looked its model up by alias, which read and parsed every record (0.5 s a page here, 16 reads of one
  record in one model). Now each record is read once per state, each caller getting its own copy.
- The chart labels' collision check (`catalog_charts._crossed`, 36,180 calls over the goal pages) skips a line
  segment whose box misses the label's: the same answer for every input, cheaper. No chart is drawn twice for one
  state (counted), so the charts are not memoized: there is nothing to keep.
- A request that comes while the pages are rendered ahead waits for the render under way only: rendering ahead starts
  no page while a request waits (`catalog_serve._ASKING`). The renders' lock is not fair: under load, rendering ahead
  took it back first, up to 7 goal pages ahead of a request (`test_catalog_warm.py`, failing before the fix).

**Measured (this repository, files store, p-values cached, 2026-11-23).**

| | before | after |
| --- | --- | --- |
| `evh catalog` | 13 s | 8 s (the memos) |
| its 1,917 files | | identical, but for the footer's time (compared file by file with a build of the code before) |
| the model, on the first page after a change | (a 13 s rebuild job) | 2.3-2.6 s |
| home page | | 0.29 s |
| a goal page | | 0.25-0.84 s (0.45-1.26 s before the records memo and the collision check; 0.53-1.93 s without the decisions memo); rendered ahead after a change |
| goals page, an arm page, datasets page | | 0.02 s, under 0.01 s, 0.02 s |

**Tests.** `test_catalog_render.py` (tests 1, 2 and 4 in a tutorial project, both stores, 13 checks),
`test_catalog_render_real.py` (this repository: all 1,906 pages rendered on their own in a shuffled order equal the
export, each one's group the one its path names, each model record read once), `test_catalog_fresh.py` rewritten for test 3 (39 checks, both
stores: a write on the next page, no `catalog` job in any of it, many reads during writes each one whole page of one
state, a burst of requests after a change preparing one model, a failed render answering 500 and recovering, a page
gone under new data answering 404, HEAD, the address without its slash, `--brand` on a served page),
`test_stats_threads.py` (two threads collecting tests at once each get their own p), `test_catalog_warm.py` (under
load, no page rendered ahead starts while a request waits; every page still rendered ahead).

A review's finding that `goal_views._KEPT` could be dropped by one thread while another read it does not hold: it is
`threading.local()`, so each thread has its own, and renders take `_RENDER_LOCK`.

## Not covered

- Pages are rendered one at a time per process: a request for a page not yet rendered waits for the render under way,
  at most a goal page (0.84 s here). A page already rendered is served without the lock. Not measured under concurrent
  load beyond the fresh test's six readers.
- The day in the cache's key is the server's local date, as `date.today()` is in the models page.
- The deployment (`--public`) is unchanged: it serves the export from nginx. The homelab (`agentic-ai-homelab`,
  `infra/fleet-evals`) builds a static catalog from a read-only copy of its data and rebuilds it when the data is
  updated, so its pages are never behind its data: nothing there writes in place.
- The measurements are from one repository on one machine; the per-page times on a project with more goals or rounds
  are not known.
