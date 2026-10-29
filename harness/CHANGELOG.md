# Changelog

Every release of the harness, newest first: what it shipped, and what a project pinning it
should know. These are the release notes. The same section is the text of the release's
GitHub Release, and the harness site shows them at
[evals.humancopilot.eu/releases.html](https://evals.humancopilot.eu/releases.html).

The version lives in `scripts/_version.py`; a release is the git tag `v<version>`, and the
release workflow refuses a tag that disagrees with that file or has no section here. A change
that can move a result is never a patch release without saying so under **Changed**.

## 0.4.5 — unreleased

### Added

- **`evh mcp`: the project's read commands as MCP tools, for an agent** (stdio, the official SDK,
  [RFC-018](https://github.com/chipi/eval-harness/blob/main/docs/rfc/RFC-018-read-only-mcp-server.md)). Thirteen
  tools: `overview`, `datasets`, `dataset-items`, `arms`, `goals`, `references`, `metrics`, `activity`,
  `search`, `inspect`, `rounds`, `runs-list`, `validate`. Each call runs the command as a child process, so a tool
  answers what the command prints; each is annotated read-only; no tool writes, spends or runs a model. For Claude
  Code, in the project: `claude mcp add evh -- evh mcp`.
- **`evh mcp --http`: the same server for a team, or for anyone.** Streamable HTTP, stateless, JSON responses:
  clients on every protocol revision since 2025-03-26 call tools without a session. The Host is checked against DNS
  rebinding (`--allowed-host` is required to bind beyond the loopback); `--public` leaves out the options that
  answer with an item's text, and the `validate` tool; `--rate`, `--concurrent` and `--timeout` bound the load; a
  missing required argument is refused before anything runs; `--hooks` takes a deployment's error reporting,
  tracing, metrics and analytics, in the inspector's shape. Each call is logged as one JSON line: the tool, its
  arguments' names (never their values), how it ended, its time.
- **`EVH_P_CACHE`: the goals' paired tests kept on disk.** Every `evh` command is a fresh process, so a view that
  shows the goals drew the same tests again each time (about 50 s on this repository's runs). With the variable
  naming a file, each estimated p is stored and read back exactly; `evh mcp` sets it to the project's ignored
  `.cache/`. `goals`, `overview` and `arms` answer in under two seconds after the first.
- **This repository's MCP server, `https://evals.humancopilot.eu/mcp`** (the deployment, not the package): the six
  worked examples for any agent, read-only, without sign-in.
- **`--json` on the catalog's view commands** (`overview`, `datasets`, `arms`, `goals`, `references`, `metrics`,
  `activity`, `search`, `inspect`): one object, `{"command", "version", "result": {"blocks": [...]}}`, each table as
  columns and rows of values, every other line as text. It is collected from the same calls that print the text, so
  the two cannot disagree. 0.5.0 gives each command its own result schema and retires this generic form: do not
  build on `blocks`.

- **What is inside a dataset, on its page and as a command.** `evh dataset-profile --dataset-id D`,
  run where the dataset is materialized, writes `data/profiles/D.json` (`schemas/profile.schema.json`,
  checked by validate V1): the number of items and their words, the shape of each gold reference
  (labels and how many of each, entries per item, a record's fields, or words per reference), and
  per item its length, its gold and, when known, where it can be read at its source. It never holds
  item text, which a dataset's licence may not let you redistribute; `--with-text` adds it only for
  items whose source files git already tracks. Commit the profile and the dataset page shows "what's
  inside" wherever the catalog is built; `evh dataset-items --dataset-id D [--item ID]` prints the
  same, and an item's text when it is materialized here.
- **An item's link to its source** comes from the dataset: an item's `source_url`, or a
  `data/sources/<dataset_id>.rows.json` that a fetch or import step writes (`{"source", "item_url",
  "rows": {item_id: {"row", "sha256"}}}`), matched by the item's bytes, so an id that recurs in
  another dataset never takes its link. This repository's Hugging Face fetchers write one, so each
  item opens at its row in the dataset viewer.
- **`inspect.html?…&item=ID`** opens that item once the comparison has loaded; a dataset page's
  **inspect** link uses it.
- Adapter: `dataset_profile(dataset)`, optional (RFC-003).

### Changed

- **Python 3.10 or later.** The official MCP SDK needs it, and every feature comes with one install, so the
  package's floor moves from 3.9 to 3.10 (CI tests 3.10, 3.11 and 3.14). On 3.9, pin `v0.4.4`.
- **A new dependency: `mcp>=2.3,<3`**, which brings `anyio`, `httpx2`, `mcp-types`, `opentelemetry-api`,
  `pydantic>=2.12`, `pyjwt[crypto]`, `python-multipart`, `sse-starlette`, `starlette`, `typing-extensions`,
  `typing-inspection` and `uvicorn`. No result moves.

## 0.4.4 — 2026-10-28

The catalog says what it is and links out: `--about` puts a deployment's own paragraph on the
overview, a goal's `links` are shown, and `--repo` turns project paths into links. The arms page
now carries the deployment's options like every other page. No result moves.

### Added

- **`evh catalog --about FILE`**: a deployment's own paragraph on the overview, under its
  description. It says which project the catalog shows and where its findings are. None by
  default.
- **A goal's `links` on its page and in `evh goals --goal G`.** The field was in the goal
  schema but shown nowhere. A web address opens; a path in the project is named as text, because
  the static pages cannot know where the project is hosted.
- **`evh catalog --repo URL`**: where the project's files can be read (e.g. a GitHub `blob/main/`
  address). A project path in a goal's links, or at the start of a guardrail's source, then links
  there. Without it, the path stays text.

### Changed

- **The overview says what the catalog is**: "pages the harness builds from this project's
  committed runs", and that the inspector tests any arms against a baseline, item by item.

### Fixed

- **`evh catalog` built the arms page without the deployment's options.** Run as a command, the
  builder is `__main__`, and the arms page was rendered by a second copy of it with the
  defaults. So `arms.html` said "eval catalog" whatever `--brand` was, and had no `--link`
  switcher, no `--head` and the default `--api`. Every page now carries them.

## 0.4.3 — 2026-10-27

A security fix to the inspector: `evh catalog-serve` no longer serves files through `/api/`.
Upgrade if you run it where anyone else can reach it. No result moves.

### Fixed

- **Nothing is read through `/api/`.** A path under `/api/` skipped the server's path checks
  and fell through to the file server, so `/api/../.env`, encoded or not, returned files from
  the project root, keys included. This happened in local and in `--public` mode. Now a `..`
  anywhere in a path is refused first, and only the API's three endpoints (`/api/health`,
  `/api/compare`, `/api/item`) answer under `/api/`. Any other `/api/` path is 404. In
  `--public` mode no path outside the API serves a file.
- **`--hooks` see one route for every unknown `/api/` path.** It is named `/api/other`, so
  someone asking for many made-up paths cannot create a metric series for each.

## 0.4.2 — 2026-10-27

A catalog that says what changed, and where: every count on the home page has a trend and opens a
page that shows the rows behind it, for the same period. An activity page and an arms and configs
page. No result moves.

### Added

- **A period on every page, counted from today.** Four chips (14 days, 30 days, this month, all
  time) and a list with the rest (7 and 90 days, this and last week, last month, this year); the
  browser works it out from the viewer's date, so a catalog built days ago still shows this week.
  A trend compares with the same days of the period before. The period travels in the link
  (`datasets.html#p30d`). On the goals, datasets, arms, references and metrics pages a row made
  in the period has a **new** badge, chips keep only the new or the active rows, and in-period
  columns give the runs and spend with their trend (▲ 12%, ▼ 31%, ▲ from 0) and a line of runs
  per day. The goals page lists what happened to each goal (baselines, rounds).
- **The activity page** (`activity.html`, `evh activity`): the home page's charts at full width,
  and the period's runs, spend and tokens by dataset, by arm and by kind of call, the busiest
  first. The measured runs, billed and tokens tiles open it.
- **The arms and configs page** (`arms.html`): every arm, saying how it was measured (measured,
  rescored against a reference, judged by a scorer, re-parsed, run again), grouped by dataset,
  config, model, provider or what it is scored against, filtered to local or hosted arms or a
  price tier, with its role in each goal's decision; tick arms on one dataset to open them in the
  inspector. Every config across the datasets it ran on, with its rank on each goal. What changed
  for arms in the period, and each goal's trade-off charts. The arms tile opens it; the configs
  tile opens it grouped by config.
- **`--period P` on every list**: `evh datasets`, `goals`, `references`, `metrics`, `arms` print
  the page's period columns. `evh arms` lists the arms page's rows (`--by`, `--where`, `--tier`)
  and `--configs` the configs. Each page's period numbers come from one builder the page and the
  command both read.
- **Adapter:** `dataset_created(dataset)`, optional: the day a dataset counts as new (else its
  first run). `spend()` events may name a measured run's `arm`, which the arms and activity pages
  bill it to; `HarnessAdapter` does.
- **Grouping on the datasets page (by goal) and the metrics page (by role: decides, weighs,
  describes)**, as the arms page groups; one script (`group.js`) groups and filters all three.
- **The arms page filters on quality and on weights:** ties the leader or below it (the arm's place
  in a goal's decision), and open weights or proprietary. `evh arms --quality ties|below` and
  `--weights open|proprietary` list the same.
- **`data/models.yaml`** (optional, `schemas/models.schema.json`, validate V1): each model's
  weights, open or proprietary, and licence, keyed by the model a run records. The adapter's
  optional `model_facts()` reads it.
- **A derived arm says how far it moved** from the config's measured arm on the same dataset
  (rescored, re-parsed, run again: "0.712 → 0.745 (+0.033) vs measured", in `evh arms` too).
- **An arm a goal leaves out for a limit it breaks is badged "over a limit"**, not "not eligible".
- **`evh catalog-serve --hooks FILE.py|MODULE`**: a deployment's error reporting, tracing or
  metrics, on a generic hook point (`start`, `request`, `error`, extra `routes` such as
  `/metrics`). The harness ships no tracker and depends on none; without `--hooks` nothing
  changes. This repository's deployment uses it (`infra/inspector/hooks.py`).

### Changed

- **The home page's tiles carry trends.** Measured runs, billed and tokens show the period's
  total, ▲/▼ % against the period before and a line per day; goals, datasets, configs, arms,
  references and metrics show the total and how many are new. The tiles are grouped and coloured
  by subject (goals; data; experiments; work and spend), with a legend; never red or green for a
  direction. The charts and the feed follow the period.
- **The menu is grouped by the same subjects:** Overview, Goals, Data (Datasets, References),
  Experiments (Arms, Configs, Metrics), Activity, Inspector; a phone's menu lists every page.
- **`evh overview --period P`** prints the tiles and trends; `--all` is gone (`--period all`).
- **The activity page and `evh activity` list what moved most first** against the period before
  (up or down), then the busiest; for all time, the busiest.
- **"What changed in the period" on the arms page folds** three or more arms of one dataset
  re-measured the same way on one day into one line ("12 arms on `<dataset>`").
- **A period select never makes a page wider than a phone**, however long its options.

### Fixed

- **`evh bootstrap-test` and this repository's report tools refuse when the gold references are
  not on the machine** (the repository commits their checksums only): they name the fetch step.
  The extraction and retrieval reports printed tables of zeros instead, as if they were results,
  and the classification report died with a traceback.

## 0.4.1 — 2026-10-27

A catalog that works on a phone and sits inside a deployment's own site, and an inspector that
no longer runs out of memory. No result moves.

### Added

- **`evh catalog --head FILE`**: HTML added to every page's `<head>`, for a deployment's own
  analytics or tags. The harness adds none of its own.
- **`evh catalog --api PATH`**: where the inspector's API answers, for a catalog served under a
  path (default `/api/`; e.g. `/catalog/api/`).
- **`evh catalog --brand NAME`**: the product's name beside the logo (default "eval catalog").

### Changed

- **`--link LABEL=URL` is a switcher between the parts of a publication**, not extra nav entries:
  the links head every page in order, the catalog marked (`LABEL=.` places it; without one it
  comes first as Catalog), and the logo opens the first. The catalog's own pages stay in its nav
  (a ☰ menu at the left of the bar on phones), and its front page is called Overview. The search
  box reads "Search ( / )", and on a phone it is a round search button in the bar that opens it below; a long
  count on the overview shows in short form on a phone (19.5M). The bar's buttons are SVG icons.
- **Tables on a phone**: a cell breaks between words, never inside a name, so a narrow screen
  scrolls a wide table sideways; running text keeps a readable width; a long item id is
  shortened in the inspector's per-item table (the whole id is its title); no catalog or
  inspector page is wider than the screen.
- **No inline styles**: the charts' legend colours are classes, so a deployment's content
  security policy can forbid `style` attributes.

### Fixed

- **The inspector no longer runs out of memory.** The paired test kept the signs it draws for
  every item count it met (~31 MB each), so `--warm` on a large catalog grew past a 256 MiB
  container limit and the server was killed every few minutes. At most two sign tables are kept
  now, stored as bytes, and at most 4096 estimates; a warmed inspector settles at ~150 MB. The
  p-values are the same, bit for bit.

## 0.4.0 — 2026-10-25

See your runs, not only tables of them. `evh catalog` builds static pages over a project's
runs, and `evh catalog-serve` runs an inspector that tests chosen arms against a baseline and
shows one item's outputs beside its reference. A project on the harness's layout needs no code;
one with its own layout writes one adapter. Goals record what an evaluation is for; items carry
the typed fields a project declares, and can live at a pinned URL. The paired test now lives in
one place, `evaluation_harness.stats`, exact at 30 items or fewer.
**Upgrading can move a result** only where `pair-test` or `family-test` ran on 30 items or fewer,
in a wins count or an order on a lower-is-better metric, or where `--exclude-dataset` named a
dataset whose items are not `.txt` files under `data/sources/<id>/` (all below), and adds no
dependency. Design:
[ADR-0002](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0002-catalog-inspector-goals.md),
[ADR-0003](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0003-item-fields-and-url-items.md);
how to upgrade: [UPGRADING](https://github.com/chipi/eval-harness/blob/main/harness/docs/UPGRADING.md).

This repository now deploys the harness on its own example experiments:
- the catalog and run inspector are public at
  [evals.humancopilot.eu/catalog](https://evals.humancopilot.eu/catalog/);
- the public site, the harness and its findings, moves from GitHub Pages to the same server;
- the docs move to [evals.humancopilot.eu/docs](https://evals.humancopilot.eu/docs/), and old
  `/docs/` links redirect there.

The deployment files are in `infra/` (runbook: `infra/README.md`). They are not part of the
package.

The example experiments keep one record per arm, the latest: the rescored and re-parsed runs
are folded into `data/runs` as derived runs, and DailyMail's `bart_s` is its fp32 run
(coverage 0.4048; the fp16 run read 0.4039). CNN's `bart_s` stays the fp16 run, the one the
judge's verdicts were made on. The reports state the current figures only; their correction
logs are gone (git keeps them). Two published statements were stale and are restated:
SciFact's `qwen_s` e5-first against the e5-first leader is +0.0178, p 0.10 (it read +0.0092,
p 0.36, from the pre-fix run), and DBpedia's 56-item dev slice, over today's 28 arms, puts
`bert_base_fy` alone at the top rather than 13 arms in a tie.

### Added
- **The rest of the inspector and catalog in the terminal.** Every page and view now has a
  command:
  - `evh search TEXT` is the catalog's search box, ranked the same way, with the command that
    shows each hit;
  - `evh inspect --items` is the per-item table (each arm's score and its Δ against the
    baseline);
  - `evh inspect --analysis [--x METRIC]` gives the analysis charts as numbers: spread per run,
    the difference from the baseline, and each arm's mean against a second metric.
- **`pair-test --round rN`** tests within a round. A defaults to the round's leader, B to the
  baseline the round started from, and the metric to the goal's measure. An arm that is not in
  play is refused.
- **On the goal page:**
  - each round has an inspect button that opens its arms against its leader (`evh inspect
    --round`);
  - every suggested command has a copy button;
  - a retired arm is greyed out.
- **Experiment rounds, optional** ([ADR-0004](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0004-experiment-rounds.md)).
  Experiments go round on round: try some arms, keep what wins, drop what lost, change something,
  compare again. `evh round-open --goal G --dataset D [--from rN]` records what a round sets out to
  learn, what changed, the arms carried in unchanged (`--keep`) and those dropped with the reason
  (`--retire ... --reason`); arms join by naming it in their config (`round: rN`, recorded on the
  run). `evh rounds --goal G` reads the evidence the way the inspector does — the round's arms
  against its leader, its best against the previous round's best and against the baseline it
  started from, its spend against `budget_usd` — and suggests the next decision, each as the
  command that makes it: `evh round-retire`, `evh rank-stability`, `evh round-close --conclusion
  ... --promote <run>` (which promotes the baseline with the conclusion as its reason). A closed
  round refuses new runs; validate (V14) checks the records; `leaderboard` and `family-test` take
  `--round`. The goal page shows the rounds, newest first, with the open round's suggestions. The
  catalog stays read-only: decisions are commands. A project that never opens a round sees none of it.
- **A goal page leads with its answer.** First the promoted baseline on each of its datasets and
  why (or "no decision yet", with the command that makes one), then what the goal is for, then on
  each dataset its references and its arms in groups by what they are scored against: gold,
  silver, a judge. Arms are ranked only within a group, and a group's leader is never an arm graded
  against its own outputs. A dataset page shows its baseline and reason, and the baseline's row is
  tagged. `evh goals --goal` and `evh datasets --dataset-id` say the same.
- **Everything the catalog and the inspector show is a command.** `evh datasets` (one dataset:
  its versions, references and arms), `evh references` (one: who wrote it, from which run, what
  is scored against it), `evh metrics`, `evh goals` (one: its arms per dataset) and
  `evh inspect --runs …` (the inspector's verdicts, conditions, `--where`/`--by` on fields,
  `--item` for one item's outputs beside the reference). Same adapter, same computation: the
  numbers are the pages'. Each is also a `make` target.
- **The catalog says what every number is measured against.** A metrics page (what each metric
  measures, which way is better, where it is recorded, which goals decide on it) and a page per
  reference (who wrote it, from which run, every arm scored against it); every metric and
  reference on the pages links there. Each arm's row says what it is scored against, and rows
  scored against silver, by a judge, or against the reference the arm wrote itself are tinted; a
  judged arm reads "judge <scorer>", no longer "gold". A goal page flags the arm that wrote the
  reference it is scored against, so it is never the leader. The inspector's charts section is
  "analysis", and its verdict rows carry the same tints. Actions are compact and tinted.
- **Long tables page.** Every catalog table and the inspector's per-item table show 10 rows, with
  "show 10 more" and "show all"; the filter and the sort work over every row, and a link to a row
  opens the table at it. The verdict tables stay whole: their Holm thresholds are read together.
- **Dataset versions keep their lineage.** `evh dataset-create --dataset-id x_v2 --from x_v1`
  records where a version came from and the item ids it adds, removes and changes
  (`derived_from` in the dataset file); `validate` V2 fails a version whose parent is gone. The
  catalog links versions both ways with what changed, and a version no arm has run on yet gets
  a page when it is linked to one that has.
- **The inspector says whether the compared runs ran under the same conditions**, from their
  fingerprints: the machine, library versions, the harness, the scorer (adapter code), the
  items and the reference's bytes. One line when all match; otherwise the fields that differ,
  arm by arm, with a warning when the scorer or the reference bytes differ (different
  measurements) or latency is compared across machines. A dataset page names each arm's machine
  when its arms ran on more than one.
- **`METRIC_DESCRIPTIONS`** in an adapter, one sentence per metric, is recorded on every run
  (`metric_descriptions` in metrics.json) and refreshed by `evh rescore`; the catalog reads the
  adapter's current descriptions over the recorded ones, so describing a metric later needs no
  new run. The harness describes its own metrics (cost, tokens, latency, judge scores).
- **A run becomes a reference: `evh reference-create --from-run <run_id>`** (`make
  reference-create RUN=<run_id>`). The usual way to get references is to run the expensive
  model as an arm, read its results, and score the cheaper arms against what it wrote. Until now
  that took a second paid pass (`--config`), whose outputs could differ from the run you read,
  and the reference did not say which run it came from. `--from-run` copies a finished run's
  outputs and calls nothing; the manifest records the run, its config, fingerprint, build and
  cost. It refuses what `run-promote` refuses (a dirty tree, an unknown build), an unfinished,
  derived or other-dataset run, and `--tier gold` (gold is what a person wrote or checked).
  With `--not-redistributed` only the manifest is committed: it records the command that rebuilds
  the texts from the run, and that command, on a checkout with the manifest alone, writes them
  again and checks them against its checksums without touching it.
- **`reference-create` refuses an empty output, and outputs that stopped at `max_tokens`**, by
  either path (`--allow-cut-off` for outputs that end at the cap by design). A frontier arm at
  `max_tokens: 80` wrote 19 of 20 summaries cut off mid-sentence and one empty reply, and they
  were frozen as the reference with no word.
- **The leaderboard marks the arm that wrote the reference it is scored against** (`arm *`, and
  a note): that row is graded against its own outputs.
- `reference-create` says when gold exists (new runs keep scoring against gold; how to rescore
  against the new silver), and to commit the reference before the next run: an uncommitted
  reference makes every later run dirty.
- **A newcomer scenario for every release**
  ([SCENARIO](https://github.com/chipi/eval-harness/blob/main/harness/docs/SCENARIO.md)): a fresh
  project, the published docs only, a summariser and a classifier with small CPU models, cheap
  hosted LLMs, a frontier reference and a judge, browsed in the catalog, under $1. RELEASING
  runs it before the merge.
- **A goal weighs cost, quality and speed, and recommends**
  ([ADR-0006](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0006-goal-axes-and-strategies.md)).
  Cost (USD per item, tokens beside it) and speed (latency p50 and p95) are built in;
  `success_criteria.axes` adds limits, another measure, `role: ignore`, or the project's own
  per-item metric in one line. A `strategy` says who is tied with the quality leader
  (`balanced`, the default: not separated by the paired test and within a margin, 2% of the
  leader unless the goal sets one; `quality_first`; `frugal`) and `tie_break` (default cost,
  then speed) picks among them. Limits come first; flagged and retired arms are never
  recommended, nor is an arm measured on fewer items than the rest of its group; identical
  scores are always tied; a missing number is "not recorded", and an axis a tied arm does not
  record cannot break the tie; speed is not compared across machines the runs recorded. Some
  groups show their leader and never recommend: a dataset marked `decides: false`, a silver
  group beside a gold one, and a group measured by unvalidated judges ("Shown, not
  recommended", with the reason). The helpers are public as `evaluation_harness.axes`.
  The goal page shows the decision with its reasons, an axis column per arm and quality
  against each axis as charts; the home page's glance a **recommended** column with cost and
  speed against the baseline; the dataset and arm pages cost and speed; the inspector's scatter
  cost and tokens. `evh goals --goal` and `evh overview` print the same. Guardrails are shown
  on the goal page and in the CLI. When the recommendation is not the promoted baseline, the
  goal page and `evh goals --goal` say by how much and whether the test separates them; with no
  eligible arm, they count the reasons. The goals page and `evh goals` count configs filed and
  show each goal's recommendation. Cost and speed metrics are their own kinds, with the goals
  that weigh them, and costs print to six places; chart names no longer overlap.

- **Reference manifests and V16.** Every reference carries a `manifest.json` with the checksum of
  each item's text (`schemas/reference.schema.json`); `evh reference-manifest` writes it for gold a
  script builds, `reference-create` for the references it makes. It is committed even when the texts
  are not redistributed: `evh validate` (V16) checks a rebuilt copy against it, and the catalog lists
  such a reference as fetched. The manifest names the dataset (`dataset_id`), so a second gold for
  one dataset can have a name of its own (`reference-manifest --dataset-id`, e.g.
  gold/ag_news_200_adj1 for ag_news_200). This repository's gold references now have one.
- **`round-retire --runs-dir`** retires one copy of a config (its runs in another runs directory,
  such as a re-timing on another machine) and leaves the arm in the project's runs directory in play.
- **`evaluation_harness.stats`**. Standard library only, and the one place the paired test
  lives:
  - `exact_p` and `sign_flip_p`;
  - `holm`, with a declared family larger than the p-values passed;
  - `exact_ci`, an interval for the mean difference that agrees with the test: none at 5
    items or fewer, where no shift can be rejected;
  - `compare`, every arm against a baseline with verdicts in words;
  - `compare_by`, the same test within each group of items, Holm-corrected over every group
    and arm together;
  - `ranks`, `pearson` and `spearman` (average ranks for ties; a constant input returns
    `constant`, NaN unless you pass another), which the judging, rank-stability and
    report-check scripts share instead of keeping their own copies.

  It has its own test suite, `scripts/test_stats.py`, run by `make test`.
- **The exact count is ~4x faster** (0.03 s at 30 items, was 0.11 s): the sign-pattern sums are
  built by doubling a list instead of enumerating each pattern. The same sums, so the same p.
  The exact interval bisects to ~1e-9 of its span, not ~1e-14: 1.4 s at 30 items, was 11 s.
  It is shown to 3 decimals.
- **`evh catalog` and `evh catalog-serve`** (`make catalog`, `make catalog-serve`).
  - **The catalog:** static pages over a project's runs, by dataset, built into
    `.build/catalog/`. Each dataset page lists every arm with its headline number, and links
    to the inspector for one arm, or for all the arms on one metric scored against one
    reference.
  - **The run inspector:** a server on 127.0.0.1 that tests any arms on one dataset against
    a baseline with `stats.py`, so it gives the same p as `pair-test` on the same pair. It
    shows the verdicts, charts of the per-item scores and differences, and, for one item,
    each arm's output beside the reference.
  - **The same rules as everywhere else:**
    - Arms on different `dataset_id`s are refused.
    - On a metric scored against a reference, an arm scored against another reference than
      the baseline's (silver against gold, say) is named and not tested against it; cost,
      latency, tokens and length compare across references.
    - The static pages carry counts and means only, never an item's text.
    - The server answers only to a 127.0.0.1 Host. It serves only the catalog and the
      data tree, and no dot-folder in either.
  - **An adapter is the only project code needed.** `catalog_adapter.Adapter` lists the
    questions both tools ask. The built-in `HarnessAdapter` reads the harness's own layout
    (`runs*/`, `runs-judged/`, `references/`): an arm is one config on one dataset, its
    repeats averaged per item. A project with another layout names its own adapter in
    `config.yaml` (`catalog: {adapter: path/to/file.py:Class}`) or passes `--adapter`.

  - **A public mode** (`evh catalog-serve --public HOST`), for a deployment behind a reverse
    proxy that serves the static pages:
    - it answers only the named host;
    - each client gets `--rate` requests a minute;
    - at most `--max-arms` arms in one comparison;
    - two computations at once, every answer cached;
    - errors never show the server's internals;
    - `--warm` computes, at start, every comparison the built catalog links to.

    `evh catalog --link LABEL=URL` adds the deployment's other sites to the nav.
  - **CSP-clean:** no inline script or style. The theme script is a file, and the legend
    colours are set from JS.

  Tests: `tests/test_catalog.py` (54 assertions), run by `make test`.
- **Goals: what an evaluation is for** (`data/goals/<goal_id>.yaml`, `schemas/goal.schema.json`).
  - **What a goal says:** who uses the output, the decision it informs, the measure that
    decides (and which direction is better), the output formats it accepts, its datasets
    and their roles, and optionally `min_items`, the fewest items a winner may rest on.
  - **Configs name their goal** (`goal:`) and may declare the `format` they ask for.
    - `experiment-run` refuses an unknown goal before it runs.
    - The run records both, outside the fingerprint: they change what a run answers, not
      what it measured.
    - `run-promote` carries both onto the baseline.
  - **`validate` V14** fails:
    - a goal that breaks its schema, or whose `goal_id` is not its file name;
    - a config, run or baseline naming a goal that does not exist, or a format the goal
      does not accept.

    A dataset smaller than a goal's `min_items` gets a note.
  - **Optional until a project opts in.** Set `required_from: YYYY-MM-DD` in
    `data/goals/policy.yaml`, and every run created from then on must name a goal. A
    project upgrading changes nothing until it sets the date.
  - **In the catalog:** a goals page, and a page per goal. On each of the goal's datasets
    it ranks the arms that record the goal's measure. An arm under `min_items` or in a format
    the goal does not accept is flagged and never the leader. Each arm links to the
    inspector, tested against the leader.
  - **This repository's six experiments have goals** (`data/goals/`), and so does the
    tutorial (`tutorial/goals/tickets_summary.yaml`). No date is set here, so nothing
    already committed is held to one.

  Tests: `tests/test_goals.py` (14 assertions), run by `make test`.
- **Item fields** (`data/fields/<fieldset_id>.yaml`, `schemas/fieldset.schema.json`, ADR-0003).
  The harness defines no field: a project declares its own in a field set, and any number of
  its datasets name it.
  - **Types:** text, number, integer, boolean, date, duration (seconds; `h:mm:ss` accepted),
    url, and choice with its values; a field can be `required` and `public`.
  - **`dataset-create --fieldset ID --fields FILE`** attaches values from a CSV or JSONL, one
    row per `item_id`, and refuses an undeclared column, a mistyped value, a value outside a
    choice, an unknown item and an empty required field. `--update-fields` corrects values on
    an existing dataset.
  - **Not the identity.** A run's fingerprint hashes item ids and bytes only, so a corrected
    field invalidates no run; the dataset records `fields_sha256` beside them.
  - **`validate` V15** fails a field set that breaks its schema, fields with no field set or an
    unknown one, an undeclared or mistyped value, a missing required value, and a
    `fields_sha256` that does not match (a hand edit).
  - **In the catalog:** each field with its coverage, and a summary of its values only when it
    is `public`. **In the inspector:** an item's fields beside its outputs; a filter on any
    field; a breakdown by a choice or yes/no field, tested per group with `stats.compare_by`.
    A public deployment answers with public fields only.
  - The adapter protocol gains an optional `item_fields(dataset)`.
- **Items fetched from a pinned URL.** `dataset-create --manifest FILE` takes one row per item:
  `item_id`, `source_url` and `source_sha256` (empty: fetched and pinned now), and field
  columns. `dataset-materialize` downloads each into `.cache/items/` and refuses bytes that
  hash to anything else, as it refuses a changed file. A transient failure is retried like a
  provider call; a host that needs a header gets it from `EVAL_FETCH_HEADERS` (that host only,
  never on a redirect elsewhere, never written into a dataset). With `--update-fields`, an
  empty cell clears a value.

  Tests: `tests/test_fields.py` (47 assertions), run by `make test`; the catalog's in
  `test_catalog.py`.
- **`evh init [DIR] [--tutorial]`** starts a project: `data/sources`, `data/configs`,
  `data/goals`, `data/fields` and a `.gitignore` for what the harness derives. `--tutorial`
  copies the GUIDE's kit (tickets, their fields, gold, arms, a goal, a judge scorer and its
  prompt, the judge panel's config) into `tutorial/`; the kit ships inside the package. It never overwrites a file.
- **`make guide-check`** (part of `make check`) runs `docs/GUIDE.md` in a fresh project, as a
  reader would, and fails when a quoted output no longer matches what the command prints.
  Lines that the unseeded `lead2_noisy` arm moves are marked in the GUIDE and not compared.
- **The tests that run `evh` install the real wheel** (`tools/_wheel.py`), built from
  `pyproject.toml`, instead of copying folders. A file the package data leaves out now fails
  them, where a copy would have included it.
- **`make browser-check`** drives the catalog and the inspector in headless Chromium: a
  tutorial project with fields, the main paths and the field controls, the phone-width layout,
  and no console error. A development extra (`requirements-browser.txt`, `make
  browser-install`), never a dependency of the package; CI runs it as its own job. The root
  `make browser-check` also drives the public site, served with production's headers.
- **`tests/test_installed_commands.py`** (in `make test`) runs every `evh` command in a
  project that pins the package; a command without a case fails it.
- **`tests/check_commands.py`** (in `make test`) checks every `make` target, `evh` command
  and flag shown in the current docs still exists: 274 of them across 27 docs today.
- **The deploy's health check** also asks the inspector the question readers send most, a
  group of arms on one metric (`infra/deploy/probe_link.sh`), and rolls back without verdict
  rows.
- **Code-quality gates**, `make quality` at the repository root and a CI job of the same name:
  ruff (lint and format), mypy, bandit, pip-audit, vulture, interrogate, codespell, shellcheck
  and actionlint, with radon's complexity report. Tools pinned in `requirements-dev.txt`
  (`make quality-install`), never a dependency of the package. What they found, and how ruff
  compares with the black, isort and flake8 that podcast_scraper runs:
  `research/internal/QUALITY_TOOLING_EXPERIMENT.md`. Every public function, class and method
  has a docstring (interrogate at 100%, the bar podcast_scraper sets). Logic kept in two or
  more copies (Spearman, Holm, the sign-flip test, module loading, the test scripts' `check()`,
  cost sums, file hashing) now lives in one place each, and every report claim re-derives
  unchanged; a test script that runs no check now fails.
- **This repository's worked examples run on patched libraries** (Linux): transformers 5.20.2,
  sentence-transformers 6.2.0, pillow 13.0.0, aiohttp 3.14.5, nltk 3.10.4, certifi 2026.10.19,
  clearing 58 published advisories in their locks; few-nerd stays on transformers 4.55.4,
  because span-marker has no transformers 5 release. `make audit-locks` audits every lock per
  platform. Every local arm was re-run against the committed record: every published finding
  holds, and all but four arms reproduce item for item (why, per arm, in the record).
  Not part of the package.

### Changed
- **A config with a key written into its params is refused** (`api_key`, `access_token`,
  `secret`, ...): it would be copied into every run record and onto the arm page. Name the
  variable with `api_key_env` instead; the catalog shows any such param as "(hidden)".
- **`success_criteria.secondary` is removed**: its entries are `axes` (UPGRADING); a goal that
  still has it fails V14.
- **Documentation never moves a fingerprint (fingerprint version 4).** Code is hashed by what it
  does: its syntax tree without docstrings, comments, formatting or `METRIC_DESCRIPTIONS`
  (assigned, or imported from a shared module). That
  holds for the adapter, the harness's measuring modules, judge_score's own hash and the examples'
  `code_digest`. A judge scorer YAML is hashed by its parsed content, and a reference manifest's
  `caveat` is outside the reference digest. Adding metric descriptions to an adapter used to make
  run-compare and the inspector call every earlier run "not the same conditions". The tree is
  serialised without empty fields, so one file hashes the same on Python 3.11, 3.12 and 3.14
  (`ast.dump` does not). v3 and v4 digests are not comparable. The committed v3 runs here were
  migrated: each recorded hash was matched to the code or reference state it came from (git
  history, unreachable objects included) and recomputed. No score changed.
- **import-run hashes the scoring code itself: `--scorer-file` replaces `--scorer-sha256`.**
  Give the file (or several, repeated in a fixed order) and the harness hashes it by the same
  rule, so a docstring in your scorer is not a new scorer. The hash is now the run's
  `instrument.adapter.sha256`, inside the fingerprint hash: before, it sat only in `imported`,
  outside the hash, so two imports scored by different versions of the code looked like the same
  conditions.
- **One install calls hosted models.** `openai` and `anthropic` are core dependencies; the
  `[llm]` extra is gone. A newcomer's first hosted arm failed on the import, and only one RUNBOOK
  section named the extra.
- **The core times every call.** `latency_ms` is recorded for any adapter that does not report
  its own (the attempt that answered, not the retries' backoff); only the bundled adapter used to
  time itself, so a project's adapter recorded no speed. **This can move a result**: a project's
  runs gain a latency column, and the leaderboard its cost/speed frontier.
- **experiment-run warns when outputs stop at `max_tokens`**, by the provider's `finish_reason`
  (the bundled OpenAI-compatible and Anthropic providers now record it) or tokens_out reaching the
  cap, naming the items: they are scored as if complete.
- **A run that stops mid-pass says what to do**: which run, after how many items, the exact
  `--resume` command, or delete it; V7's failure says the same.
- **validate V5 no longer fails two different arms that are both perfect.** On a saturated binary
  metric their per-item scores agree too; different outputs now tell two measurements from a copy.
- The inspector's item view shows the item itself (what every arm read), folded when long; the
  local inspector only. `evh inspect --item` prints it.
- Bookkeeping fields (`resumed`, the judge's `self_family_*`) stay in the record but are listed as
  metrics nowhere (leaderboard, runs-list, the spread, the inspector).
- The leaderboard's version note fires only for one arm at two versions, not for different arms at
  different versions (judge-score's too); "P(top 1)" is no longer printed beside "P(1st)" when they
  are the same; the rounding note names the scorer as what rounds.
- `evh init`'s `.gitignore` ignores `__pycache__/`; experiment-run ends "wrote N run(s) to …".
- **Exact p-values at 30 items or fewer.** `pair-test` and `family-test` now count the
  two-sided sign-flip p over all 2^n sign patterns when a pair shares 30 items or fewer, instead
  of estimating it from 20,000 seeded permutations. Above 30 items the estimate is unchanged,
  bit for bit, including `family-test`'s single stream across opponents. Near a threshold the
  estimate could land on either side of it; the count cannot. **This can move a result**:
  - **in this repository's reports:** none moved. All 200 report claims re-derive unchanged,
    because every published pair and family test is on more than 30 items;
  - **in the tutorial** (6 items): `pair-test` reads 0.0312 (was 0.0330), and the family test
    0.0938 against `lead1` and 0.3125 against `author` (`lead2_noisy`'s is unseeded and moves
    with every run). The verdicts are the same (getting started step 7, tutorial 3 step 4);
  - **in your project:** re-run `pair-test` / `family-test` on any pair with 30 or fewer
    shared items. Whether a verdict near its threshold moves depends on your data.
- `pair-test` says which it did: `(exact, all 2^n sign patterns)` or `(20000 permutations)`.
- `family-test`'s cache key includes `stats.py`, so a cached answer from 0.3.0 is recomputed.
- **`validate` V4 no longer passes what it did not check.** A materialized copy that has lost
  an item file now fails; it used to be skipped. A dataset with no materialized copy on the
  machine (materialized data is not committed, so a CI job has none) is named as not checked,
  and the ok line says how many were checked, e.g. "3 of 14 datasets materialized here". A
  project whose materialized copy is incomplete goes red where it was green.
- **The bundled adapter names its primary metric** (`PRIMARY_METRIC = "overlap_f1"`). New runs
  on it record `primary_metric: overlap_f1`. The leaderboard already ranked them by it, first
  by name; it no longer prints that the metric was "chosen by sort order", and the catalog and
  the inspector open on it. Runs made before keep what they recorded.
- **`docs/GUIDE.md` is getting started, in your own project**: install the package, `evh init
  --tutorial`, then the loop with `evh` (a dataset, arms, a reference from a run, a comparison, a
  choice). It used to run inside a checkout of this repository, with `make`, and to hold every
  step. The rest is in five tutorials (`docs/tutorials/`): a local model against a baseline, a
  hosted LLM with your own key (which variable each provider reads), a frontier model's run as
  the reference with gold and judging, experiment rounds and dataset versions, and the catalog
  and the inspector with the command behind each view. `make guide-check` runs getting started
  and the three offline tutorials, each from where getting started ends. The README and the
  RUNBOOK lead with `evh`.
- **The default metric is the one your runs recorded.** `pair-test`, `family-test`, `holdout`
  and `rank-stability` defaulted to `coverage`, the summarisation example's metric: in any
  project that does not score it they found no runs, or crashed. Without `--metric` they now
  read the primary metric the runs on the dataset recorded, and refuse, naming the recorded
  metrics, when none did.
- **`evh self-test` in a project checks the installed harness**: the paired test's own suite,
  then the tutorial end to end in a scratch folder (dataset with fields, runs, pair-test,
  rescore, validate, catalog). It used to run this repository's development suite, which
  checks this repository's reports and failed 52 checks in every project; in a checkout it
  still does.
- **A metric's direction is inferred, not remembered by a flag**, by one rule for every command
  and the inspector: a flag, else the goal the runs name, else the adapter's `METRIC_DIRECTIONS`
  (new, recorded on the run) or `import-run --asc` (a field nothing read until now), else the
  name (cost, latency and token metrics go down); V14 fails a goal that contradicts its runs.
  So lower is better without `--asc` for `pair-test`'s "A wins", `family-test`'s wins
  and "ahead", the leaderboard's order and significance block, `holdout` and `rank-stability`.
  `leaderboard --sort latency_ms` ranked the slowest arm first. p-values do not change (the
  tests are two-sided); `--asc` and `--desc` override. **This can move** a wins or "ahead"
  count, and an order, on a lower-is-better metric; no published claim is on one (200/200
  re-derive).
- **`validate` checks the project's own run directories.** V7, V8 and V9 read this
  repository's six directory names, so a project's `data/runs-adjudicated` was never checked;
  V10's scorer sources were this repository's example paths. They are project policy in
  `<data>/validate.json` (`committed`, `floors`, `scorer_sources`, `duplicate_ok`); without it
  every git-tracked `runs*` directory is checked (`validate_floors.json` is gone).
- **The package holds the harness, not this repository's tests.** The wheel shipped ~14,500
  lines of tests and report checkers; they are in `harness/tests/` and `harness/tools/` in the
  checkout. `self-test`'s own suite (`test_stats.py`) still ships. A run's `code_sha256` hashes
  the code that can move a number (the run-writing commands and what they import, read from
  the source), so editing a test no longer shows in `run-compare` as a confound; 0.4.0 runs
  record a different value from 0.3.0 runs. The deploy installs the inspector from the wheel
  too.
- **Refusals and arguments.** Every command refuses with `ERROR: …` on stderr and exit 1 (four
  printed to stdout); a command that takes no arguments refuses one with exit 2 (`validate`,
  `self-test` and five checkers ignored them). RUNBOOK: exit codes and every environment
  variable.
- **The bundled adapter refuses an unknown `provider:`** (a typo fell back to `echo` and
  recorded the echoed input as the model's output), and records what an OpenAI-compatible
  provider billed when the response carries it. One price rule for it and the judges.
- **One run record, one format; a derived run says what it was derived from.** `rescore`,
  `judge-score` and the SciFact re-parse write `derived: {kind, from, at, with}`, their own
  `created_at`, and `source_created_at`. `rescored_from`, `rescored_with`, `judged_from`,
  `judged_with`, `judge_label`, `reparsed_*` and `primary_metric_asc` are gone, and nothing
  reads them: a 0.3.0 derived run is read as a measured one. Every field the harness writes
  is declared in `metrics.schema.json`, and V1 fails a run record with any other (0.3.0's
  `import-run --asc` wrote `primary_metric_asc`, which nothing read; 0.4.0 writes
  `metric_directions`, which every command reads). `EVAL_GOALS_DIR` reads goals from outside
  the data root; `latency_s` is a speed metric, lower is better, as `latency_ms` is. A goal may name no dataset (one checked by a gate) and may set
  `direction: non_inferior`, a guard that ranks nothing (no significant drop against a baseline). `rescore` no longer records a metric it kept as
  dropped (`rescore_dropped_metrics` named whichever key a loop ended on).
- **`--resume-unverified` is gone.** `experiment-run --resume` refuses rows written before
  0.4.0 (no `_extra`); experiment-run writes `_extra` on every row, so its own rows resume.
- **The integration seam is `adapter.py` at the project root.** An arm whose config names no
  `adapter:` uses it, recorded as `adapter.py`, and the bundled adapter only when there is
  none. The docs lead with the pin and `evh init` rather than a copied `harness/`.
- **Importing the package changes nothing.** `.env` is read when a harness command starts,
  not on import, and the project's paths resolve on first use, so an adapter's tests or a
  notebook can set `EVAL_HOME` after the import. `evaluation_harness.catalog_adapter` reads
  no path at import, and its `load_adapter` is `load_catalog_adapter`.
- **Configs, judge scorers, judging sets and verdicts have schemas, and `validate` V1 checks
  them.** A config key other than `config_id`, `dataset_id`, `params`, `adapter`, `goal` and
  `format` fails (a mistyped key was read by nothing and passed).
- **A baseline carries what its number means**: `run-promote` records the run's reference
  tier, adapter and fingerprint hash, `runs-list --baselines` prints the tier and adapter, and
  V6 fails a baseline that no longer matches its run. A 0.3.0 baseline fails V6 until it is
  promoted again. Promoting replaces the baseline: the copy archived to
  `data/baselines/superseded/` and the `supersedes` field are gone, and git keeps the old one.
- **A command run from a project's subfolder finds the project**: without `EVAL_HOME`, the
  root is the nearest directory up with a `data/` folder (it was the current directory, so
  `evh validate` in a subfolder read an empty project).
- **The judge panel is a command, `evh judge`** (it sat beside the package and could not run
  from a pin); the tutorial kit ships `tutorial/judge_panel.yaml`.

### Fixed
- **V9 fails when git cannot list the committed runs.** A `git ls-files` that refused (a committed
  directory behind a link that leaves the repository) listed nothing, and V9 read that as nothing
  missing: a run with no rows passed. It now fails and quotes git's error; a project that is not a
  git repository has nothing committed, and V9 says it was not checked.
- **`silver-calibrate` no longer prints a ceiling it did not measure.** With one set of runs
  serving as both references and arms, it correlated a ranking with itself and printed "rho =
  +1.000 … from two different sets of runs". The ceiling now counts only arms whose two sides are
  different runs, and says "not measured" when fewer than three are.
- **From an external review of the core and the UI surfaces (0.4.0 candidate):**
  - **A run scored against references for only some items says so.** experiment-run took a
    reference directory as covering the dataset, so gold for 20 of 200 items gave a 20-item mean
    recorded as a 200-item gold run. It now counts coverage before any call. With no file for any
    item it refuses. With some, it warns, records `reference_coverage` on the run (schema), and
    the leaderboard names the run. **This can move a result**: a run that was refused now stops.
  - **A pair opened from a goal page's group is held to the group's family.** "test vs leader"
    passes `family=<group size − 1>`, so it is not tested as if it were the only pair. The
    inspector refuses a `family` smaller than the arms tested, and a `threshold` above alpha or
    below what the family allows, instead of obeying a URL.
  - **rescore and judge-score keep a project adapter's call-time extras** (named in the row's
    `_extra`) and `resumed`; they were dropped and reported as metrics the scorer dropped.
  - **The adapter contract:**
    - INTEGRATION gives `lower_is_better(metric, dataset)`, as the code calls it;
    - `catalog_adapter` re-exports `load_fieldset` and `fieldset_problems`, so an adapter needs
      no private `_fields`;
    - two new optional members: `arm_of(dataset, config_id)` (rounds, `inspect --round`; it
      follows `EVAL_RUNS_DIR`) and `reference_free(metric)` (from the metric's kinds, not its
      name);
    - the structured view kinds (`insights`, `nodes`, `entities`) are documented;
    - `evh rounds` reads the project's catalog adapter;
    - the inspector's default baseline is the promoted baseline's arm.
  - **A public inspector publishes text only when told.** `catalog-serve --public` served every
    arm's output and the reference text for any item, while INTEGRATION and the adapter contract
    said that text never leaves the machine. It now serves numbers, adds outputs or reference text
    only for what `--publish outputs,references` names, and never serves the item itself; the item
    view says what it withholds. **This can change a deployment**: one that relied on the old
    behaviour adds `--publish`. This repository's own publishes outputs (already public in the
    repository), not references.
  - **The catalog opens on the whole project, and every name is a link.**
    - **Home is a dashboard:** counts (goals, datasets, configs, arms, references, metrics, runs,
      USD billed, tokens), each goal's answer at a glance (its baseline, the leader of the gold
      group and the paired test between them), activity and spend side by side (spend in USD or
      in tokens, so a free local model's use is tracked too), what each dataset covers, and
      everything recorded; each for the last 14 days of activity or all time. `evh overview`
      prints the same.
    - **New pages:** Datasets (what the home page listed) and References in the menu; a page per
      arm (its metrics, runs, config without credentials, conditions, the same config scored other
      ways, its rounds; `evh arms --arm`) and per metric (what it measures and how, which way is
      better, its kind, the goals it decides, every arm recording it with a strip chart;
      `evh metrics --metric`).
    - **Links everywhere:** arms, metrics, datasets, references and goals link to their pages
      from every page and table, a reference's author to its arm, a round's configs to theirs; in
      the inspector, arm names and the metric open their pages.
    - **Metric explanations:** the harness explains its own metrics at length; a project's
      `METRIC_DESCRIPTIONS` value may be `{"summary": ..., "details": ...}` for its metric pages.
    - **The catalog adapter** gains optional `arm_runs`, `arm_config` and `spend`.
    - **From the second newcomer run:** the inspector warns when the baseline wrote the reference
      the arms are scored against; a judged arm's item shows each judge's score beside the output;
      the goal page says what "filed" means.
  - **One provider layer for the systems under test and the judges, keys by role.** The bundled
    adapter, judge-score's judges and the judge panel call hosted models through one module,
    `_providers`: `openai` (OpenAI or any compatible endpoint), `anthropic`, `openrouter` and
    `litellm`, each taking `model`, `base_url`, `api_key_env`, `temperature` and `max_tokens`.
    - **A judge goes where its `provider:` says.** Judges ignored it and went to a LiteLLM
      proxy if `LITELLM_BASE_URL` was set, else to OpenRouter with an alias looked up in
      `models.json`, while the record said the declared provider. The scorer schema now
      requires `provider` on every judge. **This can change a setup**: re-running the
      committed scorers (`provider: litellm`) needs a LiteLLM proxy.
    - **Judging can have its own keys.** A judge reads every variable as `EVAL_JUDGE_<NAME>`
      first, then `<NAME>`, so it runs on separate keys, budgets and spend logs, or shares the
      experiments' with no setting. `evh env-check` shows what each role reads.
    - **A key is not identity.** `api_key_env` is left out of a run's fingerprint and a judge's;
      no committed hash moved (all 2,800 committed verdicts keep their `judge_fp`).
    - **judge-score names each judge's route and key**, dry run included, and stops before any
      call when a key or address is missing.
    - **The judge panel's judges are declared like judge-score's** (`id`, `provider`, `model`,
      prices). It called only Anthropic, priced Sonnet in code, and ran the fake judge when
      `ANTHROPIC_API_KEY` was missing; the fake judge now runs only with `--use-fake-judge`.
    - **Anthropic takes `base_url` and `api_key_env`** like the others. **Arms pass `reasoning`,
      `reasoning_effort` and `provider_routing`** to the request as judges did, and record
      `reasoning_tokens` (descriptive, as every committed run declares it), the model and the
      host that answered.
  - **The harness imports itself as a package.** Its modules imported each other as bare
    top-level names (`import stats`) with their own directory on `sys.path`, so a project's own
    `stats.py` first on the path replaced the harness's paired test inside
    `evaluation_harness.judging`. Under `evh`, the harness's `adapter`, `stats` or `rounds` could
    also hide a project's module of that name. They now import `evaluation_harness.*`, and nothing
    of the harness goes on `sys.path`. In a checkout `harness/evaluation_harness` links to
    `scripts/`, and `python scripts/x.py` still runs. A project script that relied on the
    harness's directory being on the path writes `from evaluation_harness.adapter import Result`,
    as INTEGRATION documents.
  - **The public server trusts no client header unless told** (`--client-header NAME`); a
    spoofed `CF-Connecting-IP` no longer buys a fresh rate bucket. The deployment names
    Cloudflare's header (origin lock).
  - **The rest of the page features have commands:** `evh inspect --no-rescore` (the inspector's
    box), its "Average only" table, and the dataset page's fields block in
    `evh datasets --dataset-id`.
  - **Statistics, consistently:**
    - `family-test` marks an estimated p (~) when a family mixes exact and estimated rows;
    - pair-test separates at `p <= threshold`, as Holm and the inspector do;
    - the bootstrap ties ranks with the same tolerance as the within-item ranks;
    - runs that disagree on a direction or a primary metric are named;
    - rescore refreshes `metric_directions`;
    - the inspector and `evh inspect` show each row's 95% interval of Δ (exact up to 30 items, a
      t interval above, as its docstring now says).
  - **Accessibility:** a sortable column's header works from the keyboard and states `aria-sort`;
    every chart mark with a tooltip carries an SVG `<title>`.
  - **Messages:** rescore's missing-reference message no longer sends a project to
    `examples/`; RFC-002 tells `_extra` (adapter extras) from `_meta` (provider metadata).
- **From the second newcomer run** (`/work/evh-scenario-040`; SCENARIO, 0.4.0 candidate):
  - **A baseline promoted from one of an arm's repeats** records every repeat and their mean
    under `repeats`, and `run-promote` prints the two side by side. The catalog, the inspector
    and the tests read the mean; `scores` stays the run's own (V6).
  - **A judged run keeps its source's cost and speed kinds**, so the judged leaderboard has its
    frontier. That leaderboard also prints the judging pass's agreement and its position and
    noise checks, from `summary.json`.
  - **The arm that wrote a silver reference is left out of the ordering test and the frontier**,
    and the leaderboard says so (its row measures agreement with itself).
  - **A judge reply that is not committed** (not bare JSON, or repeating the source) keeps its
    text in a git-ignored `.withheld/` beside its record, and the log names the file. An
    unparsed reply's cause can then be read; the record keeps only the hash (V12).
  - **The dataset page and `evh datasets`** sort arms by what they are scored against (gold,
    silver, a judge, nothing) before the mean. A silver and a gold mean no longer interleave.
  - **The goal page and `evh goals --goal`** show a judge's group, read on its own score. `evh
    goals --goal` also lists the rounds and marks retired arms.
  - **One p format everywhere** (`stats.fmt_p`: four decimals, `<0.0001` below that).
    `family-test` says whether p is exact or a seeded estimate. Above 30 items it draws one
    random stream for the family, so `pair-test` and the inspector, which estimate one pair at a
    time, can differ in the third decimal. Its wins column is labelled `A wins`.
  - **Round messages:**
    - `round-open --keep` says carried arms need no change and no new run;
    - `evh rounds` does not suggest promoting the run that is already the baseline;
    - `leaderboard --round` does not warn about two versions of an arm in a round that compares
      them.
  - **`evh cost-report` sees the bundled adapter's bills.** A provider's bill (OpenRouter, or a
    LiteLLM proxy passing it through) was the run's cost but was not kept where cost-report reads
    it, so every run read as "price table only". It is now kept in the item's `_meta.usage.cost`.
  - **`evh inspect --item`** prints which run each output is from and, for a repeated arm, that it
    is the latest of N repeats beside their mean (as the page does). `evh datasets` counts configs.
  - **Smaller items:**
    - `experiment-run` prints what the command spent, and its repeat spread calls cost and speed
      what they are, not "deterministic";
    - `judge-score` says its spend is the provider's bill where one is reported, else the price
      table;
    - `silver-calibrate` explains rho and sibling lift;
    - the catalog counts the configs behind its arms;
    - "filed" reads "filed under this goal";
    - the item view says it shows the latest of N repeats beside their mean;
    - judged arms keep their version in the inspector;
    - a heading scrolled to is not hidden under the header;
    - `env-check` names the example arms only in a checkout;
    - the tutorial scorer points at tutorial 3.
- **One reference per table and per arm.** The leaderboard averaged an arm's runs whatever they
  were scored against: a silver 0.90 next to a gold 0.24, in one table labelled silver. It now
  prints one table per reference, gold first, each with its own tests. The catalog, the
  inspector and `evh rounds` read an arm against the reference of its latest run (by
  `created_at`), and they name the earlier runs they leave out. A judged run is grouped by its judge,
  not by its source run's reference. `evh rounds` reads a round against the reference most
  of its arms use and names any arm scored against another. This repository's data, the
  trial and the podcast project have no such arm.
- **`provider: openrouter` uses OpenRouter.** It read `OPENAI_API_KEY` and called OpenAI's
  address unless the arm set both `base_url` and `api_key_env`. It now reads
  `OPENROUTER_API_KEY` and calls `https://openrouter.ai/api/v1`, and an arm's own values still
  win.
- **`evh inspect --round` reads the round as `evh rounds` does:** on the goal's measure, against
  the round's leader. It defaulted to the first arm, so an arm with no score became the
  baseline and the metric fell back to `cost_usd`. Arms with no score are named and left out.
- **The bundled adapter stores `overlap_f1` as computed.** It rounded the value to 6 decimals,
  which made ties that are not there (the leaderboard warned about its own example). **This can
  move a result** only where two arms tied at the sixth decimal.
- **Hints and messages:**
  - with no reference, `experiment-run` names `reference-create --from-run` first;
  - `evh --help` describes `reference-create` as "from a run or with a config";
  - `env-check` and the `litellm` provider no longer tell a pinned project to copy a
    `.env.example` it does not have;
  - `run-promote` no longer prints `resumed` and `self_family_*` among the scores (the baseline
    file still keeps them);
  - inspector notes are no longer all labelled "Re-scoring";
  - the bundled adapter and `dataset-create --help` describe what the code does now, not its
    history.
- **A judge scorer must state its position and noise checks.** ADR-0001 makes them part of the
  pass, not optional, but a scorer that left `protocol.position_check_fraction` or
  `noise_check_fraction` out ran with them off. Both are now required. The noise check must be
  above 0, and so must the position check whenever a call sees more than one output (a pointwise
  scorer has no order to check). `judge-score` and V1 refuse a scorer that breaks this.
- **A round is read against the arm that wrote its silver reference.** `evh rounds` and the goal
  page now compare the leader with the previous round's best, the baseline and, new, the
  frontier arm whose outputs became a silver reference of the dataset. Cost per item is shown
  for each of those arms. That arm is the yardstick, so it is never suggested for retirement.
- **The inspector reads only arms and references the catalog lists.** It asked the
  adapter's `arms_of` about any path a request named; an adapter that maps a path to itself
  (the podcast repo's did) let `compare` read outside the data tree (`runs=../../.git`). A
  request may name an arm, or a path that selects arms (a run directory), but only arms the
  adapter's `arms()` reach, and a reference `references()` lists.
- A catalog nav entry may carry a CSS class as a fourth element (`hide-sm` hides it on a
  phone), and the inspector page names the command that serves it (`serve`).
- **`evh rescore` and `evh silver-calibrate` in a project that pins the package.** A run
  made with no `adapter:` uses the bundled adapter and records it as `scripts/adapter.py`, a
  path that exists only in a checkout, so both failed with "adapter not found" in every pinned
  project on the default adapter (0.2.0 and 0.3.0 alike). They now score with the package's
  own copy, the one that made the run, through one shared lookup. Found by following the GUIDE
  in a brand-new project.
- **The "next, run this" hints name a command you have.** Every one said `make …`, a target
  only a checkout of this repository has; through `evh` they now say `evh …` (the first was
  GUIDE step 1's "Next: make dataset-materialize"). Two were wrong in a checkout too: an empty
  baselines list suggested `make promote` (the target is `run-promote`), and an empty runs list
  suggested `make demo`, which a project without the bundled sample data cannot run.
- **`evh catalog-serve` on a port another program holds** says so and suggests `--port`,
  instead of a Python traceback.
- **`rescore` onto another reference no longer claims the references changed.** Moving runs
  from silver to gold (`--reference-id`) compared the gold files' hash with the silver files'
  and, as they always differ, wrote `references_changed_since_measurement: true` into every
  re-scored run and printed "the reference files have CHANGED". The move is recorded as
  before (`reference_id_at_measurement`); the flag and the warning are kept for the same
  reference's files changing. No committed run in this repository carries the false flag.
- **Commands that assumed a checkout**, each found by running every `evh` command in a
  project that pins the package:
  - `rank-stability` crashed (`set.intersection()`) instead of saying no arm had the metric;
    on a lower-is-better metric it named the worst arm the leader; with too few items for two
    halves it now says so.
  - `--exclude-dataset` (`pair-test`, `family-test`, `holdout`, `bootstrap-test`) read
    `data/sources/<id>/*.txt` instead of the dataset file: wrong for any item that is not a
    .txt, any dataset from a manifest, any project keeping sources elsewhere, and "nothing
    excluded" was then reported as true.
  - The leaderboard's metric kinds, `run-compare`'s, and the classification report's label
    parser looked for a run's adapter in the checkout only; they now find the bundled one in
    the package, as `rescore` does.
  - `bootstrap-test` on a gold set of free text (summaries) treated every summary as a class
    and would have reported a macro-F1; it now refuses, and its "too few items" refusal names
    the threshold and the opponents.
  - `catalog-serve` printed its address without flushing, so under a log file or a process
    supervisor the line did not appear; `--build-dir` outside the project was a traceback,
    now a refusal; `self-test --help` ran the whole suite instead of printing help.
- **The catalog counted a dataset's items from the harness's own path**, not the adapter's,
  so a project with its own layout got "the most items any arm scored". It now asks the
  adapter (`dataset_items`, optional).
- **The bundled adapter's `anthropic` provider failed every call** with the anthropic SDK 1.x,
  which dropped the `temperature=` keyword: a TypeError before the request was sent. The
  temperature now travels in the request body, so the request is the one every SDK version
  sends. A self-test checks the call against the installed SDK's own signature. Found by mypy.
- **A manifest URL could read a local file.** `dataset-create --manifest` fetched any scheme
  `urlopen` accepts, so a `file:///…` row was copied into the item cache and pinned, although
  a dataset's schema allows only http(s). Every fetch now refuses other schemes before reading
  anything. Found by bandit.
- **The judge panel judged placeholder text.** Every finalist, real runs included, was scored
  on "Synthetic item i for <run>". It now reads each finalist's stored outputs, finds runs
  where every command does (`EVAL_RUNS_DIR`, the project), ranks by their primary metric, and
  refuses a lower-is-better one rather than promote the worst.
- **`rescore` could record the bundled adapter's metric kinds** in a project's run: two
  registries named loaded adapters differently, and the lookup fell back to the bundled one.
  One loader (`_adapter.py`), keyed by the resolved file.
- **`import evaluation_harness.judging` failed** in an installed package (`No module named
  'stats'`), and importing `catalog_adapter` beside it loaded `_common` twice.
- **`holdout`'s significance block had no direction**, so on a lower-is-better metric it ranked
  the worst arm first.
- **Checks that could not fail, or did not run:** `self-test`'s cost-cap control turned any
  failure into a skip; `check_terminology` was failing and nothing ran it (it is in `make test`
  now); `make -C harness docs` was a no-op (eight targets were not `.PHONY`).

## 0.3.0 — 2026-10-21

Re-measure what you already have. Stored outputs can now be scored again by LLM judges, as an
optional pass that never touches a committed run: `evh judge-score`, for any text task you
declare (what an item is, what the outputs are, the dimensions, the scale). The harness refuses
a judge until the scorer names, for each judge, a committed run that measured it against human
ratings; it runs at least two judges from different vendors blind, measures their position bias
and noise, and stores every verdict so a rerun costs $0. The tutorial has an offline, $0
judging step (GUIDE step 10). Upgrading from 0.2.0 changes no committed run or score and adds
no dependency. Design: [ADR-0001](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0001-judge-scorers.md);
what it found here: the [judging page](https://evals.humancopilot.eu/experiments/judging.html).

### Added
- **`evh judge-score`** (and `make judge-score`). Re-measure an experiment's frozen outputs
  with a validated LLM judge, billed, cost-capped and resumable. It runs from the installed
  package in a project that has only its own data directory, scorer, prompt and runs: the
  prompt builder, reply parser, tau-b and Spearman, and an OpenAI-compatible judge client
  (LiteLLM proxy, OpenRouter direct, per-judge `base_url` / `api_key_env`, billed cost read
  from the response, retries) are in `evaluation_harness.judging`, with no dependency on
  `examples/`.
- **The judge scorer artifact** (`data/scorers/<id>.yaml`): two or more judges from different
  vendor families, the task, the prompt (with its sha256), the protocol, a `validation`
  block and a cost cap.
- **Any text task, declared in the scorer.** An optional `task` block names what each item is
  (`source_label`), what the arms wrote (`output_label`), the `dimensions` the judge scores
  and the `scale`; a prompt writes `{n}` where the number of outputs per call goes. Without a
  `task` block a scorer judges SummEval's news-summary task (ARTICLE, SUMMARIES, four
  dimensions, 1-5), byte for byte as before. A declared task is hashed into the judging set.
- **A judging step in the tutorial** (`docs/GUIDE.md` step 10):
  `harness/tutorial/scorers/tickets-judge-v1.yaml` re-measures the tutorial's arms with two
  fake judges, offline and $0,
  through the refusal, the dry run, the pass and the leaderboard.
- **A validation gate.** A scorer runs only if its `validation` block names a committed run
  for each judge whose metric equals the stated value (and is at least `min_metric`, when the
  scorer sets one) and whose model, temperature, reasoning, provider, max tokens, prompt file
  and prompt sha256 are the judge's. The gate checks that a validation exists and is current,
  not that it transfers to your outputs. Otherwise `--unvalidated` runs it and labels every number
  "unvalidated judge". `provider: fake` judges (offline, free, for testing a scorer) can never
  pass the gate.
- **Judging sets and stored verdicts.** One item is the article plus every arm's output, arm
  identities hidden, order shuffled by a seed; the set is hashed into its id and frozen in
  `data/judging-sets/`. Every reply is stored per call in `data/judge-verdicts/`, with its
  scores, so a rerun resumes and re-reading costs $0; a reply that is not bare JSON scores, or
  repeats 8 consecutive words of the item or an output, is kept only as its hash, since a
  judge that reasons aloud can copy the source. A different arm set is a new set, never an
  append. A block retried with `--retry-unparsed` keeps the earlier calls' cost in its record.
- **Controls.** A position check (a second shuffle that re-forms the blocks) and a noise check
  (a repeat on a subset), plus per-judge agreement and a self-family flag, in `summary.json`.
- **Adjudicated gold re-measurement** (repository tooling, `examples/_shared/adjudicate.py`,
  not in the package): a committed adjudication file overwrites only the disputed items of a
  local gold reference set to make a new reference version, and `rescore` re-scores every run
  against it for $0, the old reference kept beside it.
- **Judge validation on published human ratings** (repository tooling, not in the package):
  `validate_judge_goyal.py` (Goyal, Li & Durrett 2022) and `validate_judge_zhang.py` (Zhang et
  al. 2024, crowd ratings of 19 LLM-era summarisers) check a scorer's judges against people.
  The ratings are downloaded when the check runs, pinned by sha256, and never committed; the
  committed records hold article ids, the judges' replies and scores, and hashes; a reply that
  is not bare JSON scores, or repeats 8 consecutive words of the source, is kept only as its hash.
- **`validate` V11-V13.** V11: every judging set's stored hash is the hash of its content.
  V12: every stored verdict names a real set, item, pass and block, and its `n` is that
  block's size, and every committed judge reply (verdicts and validation records) is bare
  JSON or kept only as its hash. V13: every judge scorer loads, is structurally valid (its `task` included),
  and its prompt file resolves and renders. They read the configured data directory.
- **`judge-score` judges every arm on the dataset by default.** A scorer's `arms_match`,
  `--match` and `--arms` narrow it, and it warns when the arm set mixes config versions (`_v1`
  and `_v2` of one arm are judged as two arms).
- **A scorer's `prompt.file` resolves against the project root**, then the scorer file's own
  directory, then (in a checkout of this repository only) the repository root.
- **Judged runs carry no `reference_tier`**, since a judge reads no reference: the source
  run's tier is kept as `judged_with.source_reference_tier`, and `leaderboard` says the scores
  come from a judge, with its label.
- **A refused judge call stops the pass cleanly.** A call refused, or still failing after its
  retries (a provider's own budget guardrail answering 403, for example), stops the pass the
  way the cost cap does: every stored verdict is kept, the partial result is projected and
  labelled, and the same command resumes.
- **Scorer checks.** `task.scale` must be whole numbers, and a prompt with both `{n}` and
  SummEval's fixed count phrases is refused (the phrases would keep saying 16). V13 renders
  each prompt at 2 outputs, so a prompt that cannot be rendered fails there, not at run time.
- Experiment-level results this enables are reported in the repository's reports (the
  summarisation experiment re-measured with two pairs of SummEval-validated judges, not confirmed by people on those outputs; AG News and DBpedia
  against adjudicated gold); none of them is in the package.

### Changed
- **`leaderboard`'s precision note** no longer fires on values that are exact small-integer
  fractions (a mean of 1-5 ratings over two judges and four dimensions is in eighths); scores
  rounded on the way to disk still get it.
- Nothing that scores a run changed: committed runs and their recorded hashes are untouched,
  and the committed summarisation judging set rebuilds from its stored verdicts with the same
  id.

## 0.2.0 — 2026-10-20

The first version meant to be installed rather than copied: pin a release tag, run `evh`, and
your project's data stays in your project, never in the installed package. Runs now record
which harness produced them, other tools' scores can be imported as runs, and the paired tests
handle lower-is-better metrics.

### Added
- **Installable package.** `pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.2.0#subdirectory=harness"`
  gives the `evh` command: every Makefile target, running the same scripts.
- **`EVAL_HOME` / `EVAL_DATA_DIR`.** The project's data lives in the project, never in the
  installed package; the data root can be nested (for example `data/eval/stats`).
- **The harness identifies itself in every run.** `fingerprint.instrument.harness` gains
  `version`, `code_sha256` and `installed`.
- **`evh import-run`.** Per-item scores produced by another tool become a run the
  significance tests read, with the source, the scorer and the sha256 of the imported bytes
  on the record.
- **`--asc` for `pair-test` and `family-test`.** For lower-is-better metrics, "wins" and
  "ahead" count the lower score. The p-values were already two-sided and do not change.

### Changed
- `validate`'s V9 evidence floors are read from `<data>/validate_floors.json` (project
  policy) instead of being hardcoded for this repository's run directories.
- The `family-test` cache lives under the project root, not beside the code.

## 0.1.0 — 2026-10-19

The harness as first published with its six worked experiments, before it was packaged: a copy
you take into your project rather than install. Frozen, hash-checked datasets; one adapter
function for your system; runs that record their data, prompt, code, model and build; each
arm's own noise; paired tests with Holm correction that say separated or tied; billed cost
beside quality; re-scoring from stored outputs for $0; validation that fails CI; baselines
promoted only with a reason. Tagged afterwards, at the commit the site was deployed from on
2026-10-19 (`9454f19`), so a project that took a copy that week can name what it took. What
changed between this copy and 0.2.0, including fixes that can move results:
[UPGRADING](https://github.com/chipi/eval-harness/blob/main/harness/docs/UPGRADING.md).
