# Changelog

Every release of the harness, newest first: what it shipped, and what a project pinning it
should know. These are the release notes. The same section is the text of the release's
GitHub Release, and the harness site shows them at
[evals.humancopilot.eu/releases.html](https://evals.humancopilot.eu/releases.html).

The version lives in `scripts/_version.py`; a release is the git tag `v<version>`, and the
release workflow refuses a tag that disagrees with that file or has no section here. A change
that can move a result is never a patch release without saying so under **Changed**.

## 0.8.0 — unreleased

### Added

- **`evh init` writes an example judge prompt** (`prompts/judge_prompt_example.txt`, without `--tutorial` too): a worked
  prompt to copy for a first judge scorer, with the dimensions named, `{n}` and one JSON list per dimension. A newcomer
  whose prompt did not name its scorer's dimensions got 80 unparsed replies; `judge-score` now refuses such a prompt, and
  the example shows one that passes. An existing file is kept.
- **Evidence charts, one operation for every surface** (RFC-034): `evh chart KIND` (and `GET /api/v1/charts/{kind}`, an
  MCP tool) answers what a chart draws as a table, its caption, and the drawing as SVG (`--svg FILE` writes it).
  `gain-cost`: a round's arms or a study's trials against their baseline, the difference in quality (with its interval)
  against the difference in cost per item, a quadrant named only for a difference the tests support; `intervals`: each
  arm against the leader with its 95% interval and the contender margin; `study-progress`: a study's trials, kept or
  dropped, and the best so far; `rank-stability`; `latency`: every item's latency with its p50 and p95; `agreement`: a
  dataset's label sets as confusion heat maps, or a judge scorer's controls; `items`: arms by items, the most disputed
  first; `trend`: a goal's baseline across its versions and its closed rounds, or a code record's faithfulness per
  deployed period. The Workbench draws them on the eval, study, judge, goal and dataset screens; the catalog on a goal's
  page (its datasets and studies) and a dataset's (its label sets); the inspector adds each interval to "Difference from
  the baseline" and a latency's p50 and p95 to "Spread per run".
- **Judges that say why** (RFC-034 §5): a scorer with `explain: true` asks each judge for a short reason inside its
  verdict, one per graded output or one for a pick or a pair, in the same call. The verdict stores it (`why`), withheld
  like a reply when it repeats the source, marked missing when absent, never costing the scores. `evh judge-verdicts
  SCORER` lists the verdicts with their reasons, the lowest scores first, a page at a time (also
  `GET /scorers/{scorer}/verdicts`); the Workbench's judge screen and the inspector's item view show them. The validation
  gate compares `explain` (a judge asked for its reason is validated with it), and the SummEval validation adapter asks
  in the same words; the dry run counts the reasons' tokens.

- **Tutorial 8, the Workbench** (`docs/tutorials/8-the-workbench.md`, run by `make guide-check`): opening it from
  `evh catalog-serve`, every screen in the order a goal goes through them with the commands it calls, what it keeps for
  you (unsent changes, jobs, refusals), and prompts as versions in a manual eval and a study. PRD-017 and UXS-005 are
  marked built.
- **The Workbench's step rail and help layer** (UXS-005): on a goal's step and day-to-day screens, a rail with the goal's
  title, "states for dataset `<id>`" (the dataset the screen is on, else the first that decides), Overview, the five
  steps (The goal, Add a dataset, Prepare the dataset, Choose the systems, Its rounds) as done, current, open or locked
  from live data, and under a step not done what it lacks ("no dataset named", "not fetched", "not looked at yet", "no
  reference set", "N of 2 systems with runs", "no round closed"); a locked step links to the goal's page, then Review the
  outputs, Production, A judge for this goal, The held-out test and Studies. At 390 px it folds to "Step N of 5 · Name
  ▾", the reasons in the opened list. A `?` beside a field or heading opens a side panel (what it is, why it matters,
  an example, if it is wrong, read more: the published docs page); a glossary word is underlined the first time it
  appears in running text, its one-line meaning on pointing and the full panel on a click; the Words screen lists the
  glossary.
- **The package ships the live Workbench only** (D7): `index.html`, `workbench.js`, `help.js`, `live.js` and
  `workbench.css`, the only files `/workbench/` serves. The mockup (its page, this repository's data in `mock.js`, its
  screens and the scripts that read its data, 170 KB of it loaded by every installed project's Workbench) is a frozen
  design reference in `harness/workbench/mockup/`, outside the package; opened without its project's API, the
  Workbench says to open the link `evh catalog-serve` prints.
- **Prompts kept as versions in the Workbench, in a manual eval and in a study** (UXS-005; RFC-028; the owner's
  prompt review): "Prompts" on the home lists every prompt with its versions and runs, shows a prompt's versions with
  their text, who made each, what it was made from and the runs that sent it, compares two versions (`prompt-diff`),
  records a new version from the latest and writes one out as a file (`prompt-export`). Step 4's systems point at a
  version of the goal's prompt; an agent study offers the baseline's prompt to change, its proposal starting from the
  best so far's text, each trial's text a new version.
- **The bundled adapter sends a system's declared prompt**: `params.prompt` when the system has one, else the one
  prompt it declares by version or file (RFC-028), in the run, its dry run's estimate and the arm-smoke (which now gives
  the adapter its declared prompts, as a run does). It sent "Summarise:" for a system that declared its prompt; one
  declaring two is refused before anything is called.
- **`evh prompt-show --text`** (and `GET /prompts/versions?text=true`): each version's text with its record.
- **The Workbench's held-out test and studies, live** (UXS-005): from a goal, "The held-out test" splits a dataset
  and seals its test side (both sides joining the goal), shows the seal, records reads and runs the leak check (its finds
  recorded as reads), shows the counts for safety and allows a field with why, opens the side for one candidate (one
  look), runs both arms on it and shows the confirmation with the read items left out beside the number with them kept.
  "Studies" writes a study's spec on the page and checks it before it runs, shows its trials and best, asks and tells
  the agent sampler from the page, stops it, confirms its best on a test set (one look) and imports a past loop's
  results.tsv. Every screen of the Workbench is live: a route only the mockup has opens the live screen it stands for.
- **The Workbench's jobs, live** (UXS-005): "Every job" on the home lists the jobs a page at a time, filtered by
  state, operation and goal, counted as `evh jobs-status` counts them; a job's page shows its record, cap and spend,
  progress, result, the files it wrote (each a link) and its log, followed while it runs; a running job is stopped
  there, and a stopped run resumed as a new job with what it left of its cap. The home's running jobs open their pages.
- **A job's read names the files it wrote** (`files`: a sheet, an export; never the job's own bookkeeping or a blind
  sheet's key), in `GET /jobs/{id}` and `evh jobs-status JOB`: what `GET /jobs/{id}/files/{name}` gives had no list.
- **The Workbench's settings (W8), live** (UXS-005): "Settings" on the home, one row each with its command: the
  store config.yaml names, and the data moved into it (`data-migrate`, its dry run first; Move it only once the dry run
  counted something; the page waits out the server's 503 while it moves); this release's formats (`migrate`); the
  project checked (`validate`, its failures listed); the policies (`validate.json`, `goals/policy.yaml`) read, checked
  and saved with `data-put`, a file made elsewhere since it was read not overwritten; publishing a dataset
  (`dataset-publish`). config.yaml is not edited here (D9).
- **`data-migrate --json` gives its counts as values** (`to`, `dry_run`, `files`, `bytes`, `runs`, `outputs`, `rows`):
  they were printed only.
- **The Workbench's judge (W7), live** (UXS-005): "A judge for this goal" on the eval lists the goal's judge scorers
  and shows one: how it judges, its prompt file, guards and cap, its judges and families, its validation as stored
  (with the reasons it is not validated), the people's checks and what it judged. It is changed on the page while it
  has judged nothing (`scorer-set`, only what changed), else a new version is started from it (`scorer-new` with
  `supersedes`, its judges kept); a scorer is made with systems as its judges. The cost comes first (`POST /estimate`
  on `judge-score`), then the arms are judged as a job under a cap, an unvalidated judge only when asked; what it cost
  is `cost-report`. Validating a judge stays a tool (D6).
- **The Workbench's reference set (W6), live** (UXS-005): "Change the reference set" on a dataset's prepare screen lists
  its reference sets and label sets (how often two agree); shows what a label set moves before anything is promoted
  (the stored outputs re-scored against it under its own label, `rescore --labels`, $0, and the arms ranked on it beside
  their rank on a current reference, each side's ordering test, an arm that wrote the reference marked); promotes it
  with why (`reference-promote`) and re-scores the arms against it (`rescore --reference-id`); previews a scoring change
  on a goal (`score-preview`: each arm now and after, the leader and the contenders) and applies it to a round with why
  (`rescore --goal --round --why`).
- **The Workbench's production (W3), live** (UXS-005): "Production" on a goal captures a deployed system's records
  through an importer (`capture`) and makes a dataset of them, fetched (`dataset-from-capture`, `dataset-materialize`);
  scores production's recorded decisions as an arm (`arm-from-capture`); shows the rows where production was wrong
  against a label set and picks the checked ones for a dataset with a reason (`pick`); makes the next version of a
  dataset from the picks waiting for it (`dataset-extend`); labels a dataset from what happened later with rules typed
  on the page (`label-from-capture`) and shows how far they reach (`label-coverage-show`); and replays the code that
  ran: a code record's periods and newest faithfulness record, a replay's plan first (the dry run), then the replay as
  a job under a cap (`faithfulness`).
- **`sheet-show` gives its rows as values** (`--json`, the API's answer): each row's item, text, fields, the runs'
  decisions, the labels, its signals and whether it is picked, and the counts; it answered printed blocks only.
- **What an action said stays on the screen**: a refusal or a job's end shown under an action is kept through a redraw
  of the same screen (a read coming back redrew it and wiped the message, so nothing seemed to happen).
- **The Workbench's review (W2), live** (UXS-005): "Review the outputs" on a goal compares two arms of a dataset on a
  sheet made as a `sheet-export` job: "which is better", blind (outputs A and B shuffled per item; the page reads the
  sheet, never its key), or "what went wrong", each output tagged with a failure-mode list (a new one made here with
  `failure-modes-new`). The answers are kept in this browser until submitted to `sheet-import` with `export_job`, as
  judged scores (read as judged/<name>) or a tag set; "Make another sheet" starts the next one. Every live screen is
  checked at a phone's width.
- **The Workbench's eval (W1), live** (UXS-005 step 5): a goal's rounds as tabs; a round shows its question, its arms
  (a retired one with its reason) and the evidence (each arm against the leader, Holm: the raw p and its threshold, the
  verdict, the notes). With no round open, "Open the round" asks its question, the dataset, whether to carry the last
  round's arms in and its budget (`round-open`). In an open round: the systems to run, "See the cost first" (the
  sweep's dry run, `POST /estimate`), "Run them" as one `sweep` job under a cap, its progress shown (D2); "Retire" with a
  reason, said to be final (D3); "Close the round" with its conclusion, optionally promoting the leader's run; "Carry it
  in" brings an arm of the round before into the open one (`round-carry`); the evidence has its chart (each arm's mean
  against its cost); the baseline on the round's dataset lists its versions, each with who and why, and rolls back to
  one with a reason (`baseline-rollback`). One "who you are" serves the round.
- **The Workbench's step 4, live** (UXS-005): "Choose the systems" on a goal lists the project's systems, each checked on
  three items of a goal's dataset (`arm-smoke` as a job, under a cap): its status and flags, what it spent, what the
  whole dataset would cost and take, a reply per item. "Make a system from a model" picks a model and where it runs,
  the shared prompt, temperature and most tokens, and makes the system (`system-new`) naming the model record and the
  deployment, with the deployment's endpoint carried into its params (a run reads it from there). The prompt typed is
  recorded as a version of the goal's prompt (`<goal>/prompt`) and the system points at it, so every run records the
  version it sent. Each model is offered with its rank on this goal; "Clone it, change one thing" makes a new system
  with one change (the prompt, as a new version made from the source's; the temperature, the most tokens, the model
  it sends). The form is kept in this browser until the system is made.
- **The Workbench never loses what is being typed to a redraw, and reads afresh on each screen**: a redraw (a job's
  poll, a read that came back) carries what the person typed in a form with unsent changes, instead of being held back
  (held back, a screen waiting for its data stayed on "loading"); moving to another screen drops the page's reads, so
  what a job wrote elsewhere (a sweep's runs, a model's rank) shows there.
- **The Workbench's step 3 and labelling, live** (UXS-005): a goal's dataset opens its preparation: fetch it
  (`dataset-materialize`) and look inside (`dataset-profile`) as jobs, then its reference set, by promoting a label set
  (the dataset's own answers too) with its tier and why. "Label it here" makes the sheet (`label-sheet`, a job), fills it
  on the page and submits it when done to `label-import` (owner, 2026-11-17: never item by item); its answers are kept in
  this browser until then, counted, and a sheet with no answer holds nothing to lose.
- **The Workbench's step 1, live** (UXS-005): "New goal" on the home (or "Start with a goal" in an empty project)
  makes a goal from five things (what it is, what it is for, the decision, the measure and its direction, the winner
  rule; the margin and tie-break under "advanced"), its id made from the title; "Edit the goal" on its page changes it,
  sending only what changed. A refusal is shown on the page; the form keeps the unsent-changes rule.
- **The Workbench's step 2, live** (UXS-005): from a goal, "Add a dataset" uses one the project has or makes one from a
  source: the source's own query (its columns, the answer column), "Read it" previews it as a job, "Make the dataset"
  runs `dataset-create` as a job and adds it to the goal with its role (validation or test). "Propose its fields"
  runs `fieldset-propose` as a job; the fields kept become the dataset's field set (`fieldset-new`, named as the
  dataset) and are read with its items. The choices are kept in this browser until the dataset is made. A reload of a
  live screen no longer lands on the home (a mockup screen drew first and sent it there).
- **`fieldset-propose` gives its proposal as a value** (`--json`, a job's result), and leaves the query's answer column
  out as it does the text and the id: the answer is the dataset's reference, not a field to slice by. It closes a source
  it read only in part, as `source-preview` does.
- **The Workbench shows unsent changes** (owner, 2026-11-17; UXS-005 "For every live screen"): a live form with
  changes not yet sent (a new model, a deployment, a flag accepted) is marked "not saved yet", its button is enabled
  only then and names what it will write ("Make model gemma4-12b"), leaving the screen or closing the page asks first,
  and the screen is not redrawn under it (a job's poll used to redraw the model's page every 2 s and wipe what was
  being typed in its forms).
- **A source previewed** (the Workbench's dataset step): `evh source-preview --source NAME --query '{…}' [--rows N]`
  and `POST /api/v1/source-previews` (a job): the source's description and its first items, the start of each text
  and its answer, nothing written under data/.
- **The dataset's own answers as a label set** (owner, 2026-11-17: the Workbench's "it came with one"): a source query
  may name the expected answer's column, `"answer": COLUMN` (huggingface, croissant, kaggle, openml, zenodo). `dataset-create`
  writes those answers as a frozen label set, `answers` by default (`--answer-set`), of a new source kind, `dataset`
  (the provider, the column, the pinned revision; the label set and reference schemas name it, the catalog shows its
  chip); `reference-promote` makes it a reference. Refused, before anything is written, when the set exists (a
  dataset made again with `--force`). An answer of 0 or false is kept.
- **`score-preview` gives its numbers as a result** (the Workbench's W6): with `--json`, and as its job's result, per
  dataset each arm's deciding mean now and after, how far it moved and whether it is within the goal's limits, and the
  leader, the recommendation and the contenders now and after; a dataset with nothing to re-score says how many
  re-scores the goal reads instead.
- **The jobs list filtered** (the Workbench's home and jobs pages): `GET /api/v1/jobs` takes several states at once
  (`state=queued,running` or `state` repeated; 400 for a state a job is never in), `operation`, `goal` (the jobs whose
  inputs name it), `offset` and `limit`, and answers the `total` found; `evh jobs-status` takes `--state` (repeatable
  or comma-separated), `--operation` and `--goal`. The Workbench's "running now" asked for `running` alone and missed
  queued jobs and those whose supervisor had gone; it asks for all three.
- **A sheet to fill as a job** (owner, 2026-11-17: the Workbench submits a filled sheet, never item by item):
  `sheet-export` is an operation, `POST /api/v1/datasets/{dataset}/sheets`, run as a job under the dataset's lock.
  The job writes the sheet and, for a blind fill, its key in its own folder; `GET /api/v1/jobs/{id}/files/<sheet>`
  serves the sheet and answers 403 for the key, so a page that fills a blind sheet never holds which arm is which.
  `sheet-import --export-job JOB` (`export_job`) reads the key where that job kept it; it is refused for a job that is
  not a succeeded sheet-export of the same dataset, and with `--key`.
- **The goal through the model** (RFC-032 step 1): `evh goal-list`, `goal-show`, `goal-status` (where a goal stands and
  its next step), `goal-history`, `goal-new` and `goal-set`, and the same operations as the API's resources
  (`/api/v1/goals`, `PATCH /api/v1/goals/{goal}`, …), giving the same JSON. A save is checked against the schema and the
  datasets and references the goal names, keeps the file's comments, records who and the goal as it was, and is refused
  while a job writes the goal. The commands, the API routes and the MCP tools are made from one registry of the
  model's operations (`evaluation_harness/ops`); the model reads only data in this release's format.
- **Systems** (RFC-032 step 3): what is evaluated is a **system**, `data/systems/<system_id>.yaml` (or a folder
  validate.json's `systems` names): an adapter, its settings and the model it runs, with **no dataset, goal or
  round**. A run puts it on a dataset: `evh run --system ID --dataset ID [--goal G] [--round R]`; `sweep`,
  `arm-smoke`, `faithfulness`, `period-compare`, `periods`, `model-onboard`, `deploy-sheet`, `dataset-unseal` and
  `arm-from-capture` take systems the same way, as do the API's jobs (`{"system", "dataset", ...}`, locks
  `system:<id>`) and `make run SYSTEM=… DATASET_ID=…`. `evh system-list`, `system-show`, `system-new`, `system-set`,
  and `/api/v1/systems`; the prompt versions (RFC-028) as `evh prompt-list`, `prompt-show` and `/api/v1/prompts`. "Config" is no longer the name of anything. Format 3 (`m0003_systems`) turns configs into
  systems: the 146 groups of this repository's examples that differed only in their dataset became one system each
  (155 ids renamed, `data/renames.json`), every live reference renamed with them, and judging sets, their verdicts
  and reference manifests kept as they were judged (owner, 2026-11-13: frozen evidence keeps its ids; `judge-score`
  finds a stored set by the runs it judged, so no verdict is lost or paid for again, and a reference's author is read
  through the renames). Each view before and after was compared: the leaderboards, rounds, models and every catalog
  page read the same with the ids renamed, but for the counts of distinct systems (`systems filed` 36 to 29 on the CNN
  goal; the arms page's 271 to 264), a merged system's rollup row on the arms page, and chart labels that a shorter id
  lets fit; the old arm pages redirect. A study's trial is `<study>-t<k>.yaml`, its spec names `baseline: {system:
  …}`, and a confirmation runs the two systems on the test set as they are.
  The words follow: `evh arm-list --configs` is `--systems` and `evh import-run --config-id` is `--system-id` (no
  aliases), the catalog says systems everywhere (the arms page's `#systems` and `?group=system`, the home tile, "systems
  filed" on the goals page and `evh goal-list`), the commands' hints print `evh run --system … --dataset …`, and
  `rescore --config-dir`, which was parsed and never read, is gone.
- **Runs and scores** (RFC-032 step 4): every pass of a system over a dataset is one run in `data/runs/<run_id>/`
  (`run.json`, its outputs), and every score of it sits under it, `scores/<scorer>@<reference>/`. What the
  `runs-linux`, `runs-pair`, `runs-repeats`, `runs-silver`, `runs-adjudicated`, `runs-rescored`, `runs-judged` and
  `runs-labels-*` folders meant is a field now: a run's `purpose` (`run`, `repeat`, `retime`, `pair`, with `machine`
  and `of`) and a score's label ("silver", "rescored cd35dc1f", "judged/<scorer>"). Format 4 (`m0004_runs`) moves the
  data: every record reads back exactly as its metrics.json did (checked on all 736 of this repository's), a judging
  pass's summary goes to `data/judge-summaries/`, a retirement names its runs, validate.json names arms by label. A
  re-score by the scorer a run already had, with the same rows, is the same measurement: the 25 triage copies a round's
  scoring made are kept once (owner, 2026-11-13), and `rescore` writes no copy from now on. The folder flags are gone,
  no aliases: `EVAL_RUNS_DIR` (a throwaway pass is `evh run --scratch`, a re-run `evh run --purpose repeat|retime|pair
  [--of RUN_ID]`), `--runs-dir` and the comparison's `--from` (now `--label`, as on `comparison-show`, `leaderboard`, `runs-list` and
  `family-test`), `round-retire --runs-dir` (now `--label`), `rescore --out` and `judge-score --out` (they write under
  the runs they score; `rescore --label` names what its scores are read as). Every view was compared before and after:
  the same numbers, the arm ids renamed (`silver/…`, `rescored-cd35dc1f/…`; the plain arms keep `runs/…`, and the old
  pages redirect), but for the 25 copies kept once (690 arms are 665), the arms' order where it follows their ids
  (a round's inspect link, capped, now opens its plain arms where it opened their silver ones), and the re-scores of
  the runs triage round r3 retired, now marked retired with them. `evh validate` fails on a `data/runs-*` folder left
  unmigrated.
  A run records the prompts it sent (step 4b): an adapter's optional `prompts(params)` gives each prompt's text by
  name, and a run whose fingerprint declares that text's `prompt_sha256` records it as a prompt version
  (`run.json` `prompt_versions`; `evh prompt-show` lists the runs that sent it), outside the fingerprint's hash, so
  no run's fingerprint moves; a scratch pass records none. The examples' adapters have the hook.
- **Rounds store their arms** (RFC-032 step 5): each arm in a round's record is a system read under one label, the
  runs it is read through, how and when it entered (ran in the round, or carried from an earlier one) and its
  retirement; a run made with `--round` joins its arm (a run the round would read under a re-score is told to
  re-score the round), and the round's file is not dirt in a run's fingerprint. One evidence computation
  (`model/rounds.evidence`) is read by `evh round-evidence`, the goal page for every round, `comparison-show --round`, pair-test's
  and family-test's `--round` and the API (`evh round-list`, `round-show`, `round-evidence`; `/api/v1/goals/{goal}/
  rounds…`), its leader read as a goal decides (gold first, no judged arm, no arm that wrote its reference). New:
  `evh round-carry`; `round-retire` retires an arm whole, or the one `--label` names (no `--runs`). A baseline
  version names the round and arm that promoted it. Format 5 (`m0005_rounds`) writes every round's arms from what it
  read before: all 17 rounds of this repository give the same evidence (arms, leader, every test) before and after.
  Views that move, by the decision that an arm is a system read under one label: the catalog's count of a round's
  arms (CNN r1 87 to 29, AG r1 60 to 30, triage r3 80 to 53), AG r1's best on the goal page (an adjudicated copy
  scored against another reference before; the round's own arm now), triage r4's "vs r3's best" (another dataset:
  no comparison), and which arm pages list a round (the arms the round stores, under their label).
- **Datasets and what belongs to them in the model** (RFC-032 step 6): datasets, fieldsets, failure-mode lists, label
  sets, tag sets, references and captures are entities of `model/datasets`, with one table of where each part of a
  dataset is (nothing moved). New: `evh dataset-list`/`dataset-show` (its parts, lineage, label sets, references),
  `fieldset-*` and `failure-modes-*` (list, show, new, set: checked, comments kept), `label-set-list`/`-show`,
  `tag-set-list`/`-show`, `reference-list`/`-show`, `capture-list`/`-show`, and their resources under `/api/v1`.
  Fixed: `dataset-materialize` read a dataset's items against the directory it ran in (from a subfolder every item
  was missing) and cleared the old copy before reading, so a failed run deleted it or left an empty copy the next
  run took as done: it now builds the copy and then replaces the old one. `dataset-create --source-dir` outside the
  project recorded the folder's bare name, which nothing could read: it copies the items into `data/sources/<id>/`.
  A goal's status missed a reference promoted under another name (`gold/ag_news_200_adj1`). The deployment's copy
  of the data left out the exposure registers, so a deployed catalog scored items a sealed side's readers saw.
  Validate checks label sets, tag sets, picks and exposure rows against new schemas, and a dataset's capture link.
  `orrery_triage_v1_labelled_v2` records its parent, `orrery_triage_v1_labelled` (version 2.0). A dataset's page says
  where it came from: the capture its items were taken from and the version it was made from (a capture-made
  dataset's page named neither); the datasets list and `evh datasets --dataset-id` give both. The catalog reads any
  data directory (the deployment's copy too) through the model's layout.
- **Models and deployments, apart** (RFC-032 step 2): a model's deployments are records of their own,
  `data/deployments/<model>/<deployment>.yaml`, each with its checks as dated history: every onboarding, every arm
  smoke and every acceptance is kept, with who made it; the views read the latest of each, so `evh model-list`, the
  Models page and a model's page say what they said. `evh model-list`, `model-show`, `model-new`, `model-set`,
  `deployment-show`, `deployment-history`, `deployment-new`, `deployment-set` and `deployment-accept` (with why, a
  sentence), and the same as the API's resources under `/api/v1/models`. A deployment's checks are refused as an edit:
  onboard it, smoke an arm, or accept a flag. An arm smoke is recorded on the deployment the arm names, or the model's
  only one; with several and none named it says it is not recorded. `validate` checks each deployment against
  `deployment.schema.json` and names one under no model or not named by its folder and file.
- **The Workbench on its server** (PRD-017, RFC-032 step 1): `evh catalog-serve` serves it under `/workbench/` on
  this machine (never `--public` or `--behind-proxy`) and prints the link that signs in. Its home and a goal's screen
  read the model's API. Its models (step 2, W5): the project's models and their state, a model's page with each deployment's checks,
  "Run the probes" (`model-onboard` as a job, with the most it may spend, followed on the page), accepting a flag with
  why, adding a deployment, and bringing a model in; every change names who made it, asked once and kept in the browser.
  A deployment's record names no actor of its own: each of its checks names who made it (`by`), so a deployment
  `model-onboard` wrote is saved again through the model. `model-onboard` and `arm-smoke` exit 6 on a CHECK, as their
  help now says (it said 1).
- **The data's format** (RFC-032): `data/project.yaml` records the format of a project's data, `evh init` writes it,
  and `evh migrate --check` compares it with the release's (format 7 in 0.8.0; `ERROR (old-format)`, a new refusal kind, for older data;
  `ERROR (mismatch)` for data a later release wrote). `evh migrate` runs numbered steps (`migrations/`), records the
  format after each, and copies a SQLite project's database first. This repository's deploy stops on data not in the
  release's format (`render.sh`), `make check` runs the same check first (CI's reproduce), and CI migrates a project 0.7.2's own code made (`tests/fixtures/formats/0/`) and
  checks its leaderboard against 0.7.2's. `evh init dir` run inside another SQLite project wrote into that one's
  database; it writes the project it makes.
- **Replay the code that ran, and prove the replay faithful** (RFC-030): a config with `replay:` names a `kind: code`
  model record (the fleet's feedback 27: its versions, when each was deployed; `checkout` for a local clone) and runs
  the system's own code over a dataset in order, each item at the version deployed when it happened (unpacked once
  with `git archive` under `.build/code/`), each call made once, `--resume`/`--items`/`--repeat` refused; a candidate
  (`replay.commit`) runs every item at one commit. `evh faithfulness` replays the recorded versions and compares each
  item with production's recorded arm by the adapter's `same()`, recording the disagreements and the coverage (the
  functions no item reached), and writes each version's summary into the code record. A replay is scored against a
  reference (`run`, `rescore`, `run-promote`) only when the newest record made with its adapter and support modules
  agrees, its disagreements named by a person (`faithfulness-name`), or a person's `--unfaithful`, said everywhere.
  `faithfulness-show`, V26, overlapping deployed periods refused (V18), and a `datetime` field type. `examples/replay-filing/`: a filing system with three commits, its frozen history, the stand-in world, the
  write join that makes production's arm, and mutants (three killed, one survivor explained by coverage).
- **Studies** (RFC-029): a study is research on a validation set, a spec and an append-only log under
  `data/studies/<goal>/`. `evh study-run` opens its round and runs ask/tell over trials: a grid over the spec's space,
  a program speaking JSON lines (`sampler: {command: ...}`, Optuna's ask/tell plugs in), or the calling agent
  (`study-ask`, `study-tell`, also MCP tools: the only tools that write). Each trial's config is written once and found
  like any config; it is kept or dropped by the spec's rule against the best so far, its limits against the baseline,
  every p labelled nominal. Stop rules: trials, dollars, wall time, patience, a changed spec. `evh study-confirm` is
  the one step to evidence: the trial and the baseline on a test set's items no study saw (`run --items`), one look
  at the set's next level, the rule given first. `study-stop`, `study-list`, `study-show`, and `study-import` for
  Karpathy's `results.tsv`. A sampler is shown the best's weakest validation items (recorded; a confirmation leaves
  them out); a trial may change a prompt root's varied files; a changed scorer stops a study; `study-run --resume`
  after a crash; each goal's page shows its studies' trials.
- **Test-set looks** (RFC-029, its first part): a goal's `role: test` dataset or a sealed split side is a test set,
  and each decision written on it (a `dataset-unseal`, a `run-promote` compared on it) is a look, keyed by its question
  (the configs, the measure, the rule) so asking again reuses it. Look k decides one-sided at 2.5%·6/(π²k²) (1.52%,
  0.38%, ...); past the limit (10, or a goal's `test_looks`) only the person's `--confirm-extra-look` allows another,
  never an agent's. A promotion whose items could never reach its look's level is refused unless the person passes
  `--override-no-evidence` (recorded inconclusive). `pair-test --look-level`; `pair-test` on a test set says
  "nominal, not a look"; `evh looks`; V25 reports a look number two questions took. A goal's page and `evh goal-leaderboard`
  say each test set's looks and the next one's level; `round-close --promote` passes `--confirm-extra-look` and
  `--override-no-evidence` to the promotion.
- **Prompt versions, and the code a system runs** (RFC-028): a config declares `prompts:` (files, wherever they live)
  or a `prompt_root:`; each run records the version it used in `data/prompts/` and its hash in the fingerprint's
  settings, and gives the adapter the text and a per-run copy of the root. `code:` records the system's checkout
  (remote, commit, changed files) as `deployment.code`; a hook's `code_ref` lands there too. `evh prompt-list`, `prompt-show`,
  `prompt-diff`, `prompt-version`, `prompt-export`; a Prompts page (the text only when published); V24.
- **Every command the API serves answers `--json`** (RFC-026 step 7): the 43 job commands that wrote or reported only in text
  (`dataset-create`, `catalog`, the label, reference, round and migration commands, `bootstrap-test`, `holdout`,
  `cost-report`, ...) and `validate` and `dataset-card`; text to stderr as it goes, the envelope on stdout. A job's
  result is its envelope.
- **The jobs from the terminal** (RFC-026 step 6): `evh jobs-start`, `jobs-status`, `jobs-logs [--follow]`,
  `jobs-stop`, `jobs-resume`, over the same jobs as the API, with no server. A resumed run job is given what the
  stopped one left of its cap, not the cap again; one that spent it all is not resumed.
- **What a command may spend, and a round's budget enforced** (RFC-026 step 5): `EVAL_MAX_COST_USD` caps the
  whole command (`run --repeat 3` stops at one cap, not three); `arm-smoke` stops at it; the bundled provider layer
  counts the calls too, a second net under an adapter that reports less; `sweep` and `model-onboard` give each child
  what is left; `judge` takes the lower of its config's cap and this one. A run or smoke of a round with
  `budget_usd` reserves its share in the round's ledger before its first call and is refused (`over-budget`, a new
  refusal kind) when nothing is left; a stopped or killed run's paid items count; `evh round-evidence` shows what is left.
  `POST /api/v1/estimate` answers a job operation's dry run.
- **A migration holds the server too** (RFC-026 step 4): while a migration holds the project the server answers
  `503` with `Retry-After` and lets go of the database, so `data-migrate` runs as a job with the server up, and the
  server reads the new store after.
- **Jobs** (RFC-026 step 3): `POST /api/v1/jobs` runs a decision or work operation as a detached job with a supervisor,
  its state, log and envelope in `.build/jobs/<id>/`; listed, read, followed from a byte offset, stopped (its process group,
  `cancelled`) and, for a run, resumed. A job's locks, one per thing it writes (`.build/locks/`, taken in key order, held by the
  job's command itself): a second job writing the same thing waits `queued`, naming the job it waits for; a migration
  takes the whole project. A command run in the terminal takes no job lock; `evh migrate` and `evh data-migrate` refuse
  a SQLite project another process has open. A spending job needs `max_cost_usd`, and every job `by` (who asked). Uploads (50 MB a
  call) and artifacts (files a job writes, fetched from it). A job outlives the server; one whose supervisor died
  reads `running (unsupervised)`, then `lost`.
- **The API, its read side** (RFC-026 step 2): a local `catalog-serve` answers `/api/v1/` behind a token written to
  `.build/api-token` (bearer, or a cookie from `/api/v1/session`), this machine's Host and no foreign Origin. `GET
  /api/v1/commands` is the registry, made from the commands' own parsers: each served as a read or a job, its
  arguments with a kind, the ones that load code or name a server path never taken (a test fails on a path argument
  given no kind). `POST /api/v1/read/<command>` answers what the command's `--json` answers. Not served under
  `--public` or `--behind-proxy`.
- **Baselines per goal, in versions, with their evidence** (RFC-027 D2-D4): a baseline is a goal's on a dataset
  (`data/baselines/<goal>/<dataset>/<n>.json`), or a dataset's own for a run with no goal (`_dataset/`). Promoting
  writes the next version, never over the last (exclusively: two at once both land), with the paired test against
  the version it replaces frozen in, as `pair-test` answers it (`pair-test --json` now also gives `items_sha256`,
  `reduce` and the run ids it pooled). `evh baseline-rollback` restores an earlier version as a new one. `evh
  baselines` lists each line with who promoted it, why, the evidence, how to reproduce it (the deploy sheet's block)
  and the history; `--json` is the export, the same bytes until a promotion. `evh migrate` brings 0.7
  records over; this repository's are migrated. V6 holds each line's chain.
- **Who acted, on every record** (RFC-027 D1): runs, references, label sets, rounds, picks, dataset and model records
  and baselines carry `actor`: a person, or an agent and the person it acted for (`EVH_ACTOR`, `EVH_FOR`), from
  `--by` (on every command that writes a record), the environment or the terminal's login, with where it came from. A
  decision (`run-promote`, `round-close`, `dataset-unseal`) refuses an `unknown` actor; everything else records it.
  A label set keeps who labelled (`source.by`) beside it. Agents: the project's AGENTS.md says to name themselves.
- **"If your system is plain code"** (INTEGRATION, the fleet's feedback 19 and 26): what an item holds for code that
  reads external state (its world at decision time), why one run is enough, a correctness goal beside a regression
  guard, the item as the unit judged, links between items folded into an outcome, and outcomes joined by time and
  order rather than by a key the outcome may not carry.
- **Code under test as a record of its own** (the fleet's feedback 27): a model record with `kind: code` holds its
  repository and its versions (commit, deployed windows, the faithfulness a replay measured), with no aliases. Its
  Models page row shows its latest commit and how many versions were checked, never "not onboarded"; its page and
  `evh model-show <model>` list the versions. Validate V18 names a version listed twice.
- **A private inspector behind a proxy** (homelab, 2026-11-05): `evh catalog-serve --behind-proxy HOST[,HOST]`
  serves the whole local inspector (pages, items, outputs, references) to the named Hosts as well as this machine,
  with `--bind 0.0.0.0` in a container behind a team's own proxy; no rate limit and nothing withheld, unlike
  `--public`.
- **A sealed held-out side** (the fleet's feedback 29): `evh dataset-split D --split-by time --key F --at T --seal` splits
  at a time boundary and seals the test side: runs, labels, label sheets, references, rescores and judging onto it
  are refused until `evh dataset-unseal D_test --config C --reason "..."` names a candidate whose hypothesis is
  committed; it opens to that config and the one it is against, and records the look. `validate` (V22) fails when
  the open side changed after the seal or a run on the sealed side has no unseal. The look budget comes with the
  test-set looks (plan 4.4).
- **A metric of the whole run** (the fleet's feedback 20): an adapter's optional `score_run(items)`, called once
  with every item's output, reference and scores, returns named numbers (pairwise precision and recall of a grouping,
  say) that no mean of items can be. They are recorded in `scores` and named in `run_metrics`; the leaderboard shows
  them, `rescore` recomputes them, the comparison shows each arm's value untested, and `pair-test`/`family-test`
  refuse them by name.
- **How far outcome rules label a dataset** (the fleet's feedback 31): `evh label-coverage --dataset-id D --capture
  C --map rules.yaml` applies `label-from-capture`'s rules without writing: labelled now, skipped by design, not yet
  mature (with each item's maturing date), matched by no rule (with the outcome fields they lack), not in the
  capture; per rule, the items it takes now and when mature. A read tool on the local MCP server.
- **Items, not item-runs** (the fleet's feedback 33): `run --repeat` ends with how many items every repeat scored the
  same on the primary metric, named near-copies when nearly all are, and the items to read against the item-runs;
  `pair-test` names each arm's runs and their per-item agreement (`repeats`, in JSON too) and says each item counts
  once.
- **A dataset already cited gains its lineage** (the fleet's feedback 16): `evh dataset-create --dataset-id D
  --from P --lineage-only` records the dataset D was made from and what changed, recomputing its version, with its
  items and the rest of its record untouched; a second parent, a split side and a loop are refused.
- **A round records its harness code** (the fleet's feedback 17): `round-open` records the harness version, commit
  and measuring-code hash it opened on and says so; `evh round-evidence` shows it and names each run of the round that ran on
  other harness code, with how to run it on the round's (a worktree at its commit, or its version pinned).
- **A round's baseline can be named** (the fleet's feedback 22): `evh round-open … --baseline <config_id or run id>`
  records the run the round starts from when the dataset has no promoted baseline (arms carried in with `--keep`), so
  `pair-test --round` and `evh round-evidence` read its arms against it instead of refusing ("records no other baseline
  run"). `round-open` says which run the round starts from.
- **A regression guard** (the fleet's feedback 28): `expect_identical_to: <config_id>` in an arm's config says its
  runs must reproduce that config's, item for item and output for output (the same code at another commit).
  `evh validate` V5 reads such a pair as the agreement asked for, not as an inert knob, and fails the guard when they
  differ. Recorded on the run, outside the fingerprint.
- **A project's data in SQLite, a project's choice** (RFC-025). Files stay the default; `store: sqlite` in
  `config.yaml`, or `EVAL_STORE=sqlite`, keeps everything under `data/` in one database, `data/project.sqlite`
  (write-ahead logged; a run's outputs and rows committed as they are produced), and nothing under `data/` on disk
  but it. Every command, the catalog and the inspector read and write through one module (`_store`); a test fails on
  path I/O anywhere else. `evh data-migrate --to sqlite|files` moves a project either way, every file read back by
  its sha256; on this repository's data the round trip gives back every file byte for byte. `validate` V23 names a
  project in both. Python code is never in the database.
- **A project's data from the terminal** (PRD-016): `evh data-ls`, `data-show [--fields]`, `data-put [--set
  KEY=VALUE] [--unset KEY] [--new] [--check]`, `data-rm [--dry-run]`, in either store. A setting is saved only after
  it passes the check (its schema; its id is its file name, but for an arm config), keeping the file's comments and
  every line it does not change (every setting in this repository written back unchanged is the same file, and
  5,159 one-value edits kept every comment), and only when `evh validate` passes with it; harness-written data is
  refused, and a run is deleted whole. In SQLite mode it is how a person's settings get into the database without
  `data-migrate`. New dependency: `ruamel.yaml` (owner yes, 2026-11-06), which writes a setting back with its
  comments. A catalog page for the same (the Configure page) was built during 0.8.0 and retired before the
  release (PRD-017 decision 4): the Workbench takes its place.
- **`schemas/validate.schema.json`** and **`schemas/goal-policy.schema.json`**: the validate policy's keys and the goal
  policy's `required_from`, written from what `validate` and `goal_policy` read; `data-put` checks a setting against
  them. A judge's `params.family`, which `judge_score` requires two of, is in the scorer schema.
- **Tests that know when items are related.** `--cluster FIELD` on `pair-test`, `family-test` and
  `bootstrap-test`, and `cluster: FIELD` on a goal's dataset (used by the goal page, `evh goal-leaderboard`, the inspector,
  rounds and `--round`): items that share a value of the field (one thread's comments, one incident's decisions)
  count as one. The sign-flip test flips one sign per cluster, the interval is cluster-robust above 30 clusters,
  the bootstrap draws whole clusters. Tested items one by one, related items made p too small: in a simulation
  of 12 clusters of 5 with no real difference, the item test called 45% of them significant, the cluster test
  4%. `validate` (V14) refuses a goal whose cluster field no item carries.
- **The contender test is shown.** `evh goal-leaderboard` has a column "contender test (within the margin)" (p, its Holm
  threshold, shown or not, or "too few"), `--json` carries it per arm (`noninferior`), the goal page's cell says it,
  and `evh pair-test --margin M` runs it for any one pair.
- **What a goal can detect.** Its decision says the smallest margin a contender could be shown within, with its
  number of candidates and items or clusters (80% power): on ag_news, 29 candidates on 200 items need about 0.10,
  so its 5% (0.048) admits nobody. `axes.quality.reference: baseline` tests contenders against the promoted
  baseline ("no worse than what runs now") instead of the leader.
- **How repeats combine, named.** `success_criteria.primary.reduce` on a goal, and `--reduce` on `pair-test` and
  `family-test`: `mean` (the default, as before), `majority` or `at_least_K` for 0/1 scores (`at_least_1` is
  pass@k's question). The catalog keeps each item's repeats beside their mean.
- **Agreement over every label set, and where people disagree with the reference.** `evh label-set-list D`
  gives Krippendorff's alpha over all the sets together (three or more), with a 95% bootstrap interval (it is
  Krippendorff's 0.743 on his 2011 example); `--contested` lists, per item, how many people's sets agree with the
  gold reference. The pairwise alpha now counts labels in one pass (it compared every pair of labels, 4 × 10^8 at
  10,000 items).
- **Judges: length bias, a 0/1 start, and why a rubric changed.** A judging's `summary.json` gives each judge's
  `length_bias`, Spearman's rho of its score with the output's length in words (the committed judge-summ-v1: 0.23
  and 0.29; judge-summ-v2: 0.02 and 0.21; both summaries re-summarised from their verdicts, $0, nothing else
  changed). The RUNBOOK recommends `scale: [0, 1]` to start a project's own judge. A scorer that replaces another
  says so: `supersedes:` and `why:`, checked by `validate` (V13) and printed by `judge-score`.
- **How an arm fails: failure modes and tags.** A project names its failure modes once
  (`data/failure-modes/<id>.yaml`); `evh sheet-export … --fill tags --modes <id>` writes a sheet with a
  `failure_modes:` cell beside each arm's output, `evh sheet-import … --tags <name> --modes <id>` reads it back as a
  tag set (checked against its key, never edited); `evh tags` and the goal page count each arm's modes, and the
  sheet shows each item's in an `<arm>: failure modes` column. `ok`
  marks an output read and found fine; a blank cell was not read. `validate` V21 checks the lists and the sets.

- **A dataset can name its licence.** Optional: `dataset-create --licence ID`, or `evh dataset-describe
  --dataset-id D --licence ID` later (a licence or description change is no new version). `evh licences` lists the
  SPDX ids a line each (`--search`, `--json`, an MCP tool); `unknown` and `LicenseRef-<name>` are allowed;
  `validate` V22 refuses others. The committed Hub datasets carry the licence their Hub page states (2026-11-05):
  ag_news unknown, cnn_dailymail Apache-2.0, dbpedia_14 CC-BY-SA-3.0, few-nerd and scifact CC-BY-SA-4.0, summeval MIT.

- **Where the items came from, the same for every source.** A dataset record has a `source` block: `provider`, `ref`,
  `url`, `revision` (the source's own version), `config`, `split`, `gated`, `description_sha256` and `item_url` (one
  item's page, with `{row}` or `{item_id}`); each item its `source_row`. `dataset-create` reads it from a fetcher's
  `data/sources/<id>.rows.json`; the profile and the catalog link items from the record, no longer from that file.
  `validate` V22 checks it. The committed Hub datasets and their profiles were migrated by `evh migrate`
  from what their profiles recorded; `revision` and `gated` were never recorded for them and are null.

- **A dataset card.** The datasheet questions, answered in a `card` block under Croissant RAI 1.0's property names
  (`dataUseCases`, `dataCollection`, `dataAnnotationProtocol`, `dataBiases`, `dataLimitations`, …, twenty in all):
  `evh dataset-describe --card-template` prints them with their questions, `--card FILE` records the answers. No new
  version; `validate` V22 checks the keys.

- **Dataset sources: one interface for every place items come from.** `evh dataset-create --source NAME --query
  JSON` reads a source: a class with `describe(query)` (source block, licence, description, card, features) and
  `items(query)`, found as importers are (built-in `folder` and `manifest`, a project's `data/dataset_sources/NAME.py`,
  or `path.py:Class`). Its items are written to `data/sources/<id>/`, never over files already there.

- **A dataset as Croissant 1.1.** `evh dataset-card --dataset-id D --format croissant` writes the record as
  Croissant JSON-LD (licence, version, source url, parent, the card as `rai:` properties, its files with their
  sha256, the items as a record set with typed fields); without `--format` it prints the card as text (also an MCP
  tool). A required property the record cannot give is named, never invented. Not run through `mlcroissant`.
  `--format hf-readme` writes the card as a Hugging Face dataset README.

- **A dataset from a Croissant description.** `--source croissant` reads any Croissant file or URL whose record set is
  columns of one parquet, CSV, JSON or JSON-lines file (its sha256 checked), with the description's licence, version
  (as `source.revision`) and `rai:` card. A FileSet is refused, naming its format: Hugging Face's descriptions keep
  their parquet in one, whose files only the Hub can list.
- **pyarrow is a dependency** (owner, 2026-11-05), to read parquet: `pyarrow>=15`, installed with the harness.

- **A field set proposed from a source.** `evh fieldset-propose --source NAME --query JSON --fieldset-id ID` turns
  the features a source describes into a field set (types mapped, few-valued text proposed as a choice from a
  sample), printed for a person to read; `--write` writes it, never over one that exists.

- **A dataset from the Hugging Face Hub, pinned.** `--source huggingface --query '{"ref", "split", "text", …}'` reads
  the Hub's parquet conversion of a split at one commit (`source.revision`), each file checked against the Hub's
  sha256, with the card's licence and metadata, and each row's viewer page as its link.

- **Publishing a dataset to the Hugging Face Hub.** `evh dataset-publish --to huggingface --query '{"repo": …}'`
  writes a new repo, private by default (items as parquet, the record, the card as README), reads it back by sha256,
  and records where it went on the dataset. Hidden datasets are never published. `huggingface_hub>=0.26` is a new
  dependency (owner, 2026-11-05). Checked live: a private repo published, read back and deleted.

- **Datasets from Zenodo and OpenML.** `--source zenodo` reads a record's table file (md5 checked, the record id as
  revision); `--source openml` reads a dataset's parquet copy with its version and typed features.

- **Datasets from Kaggle, without kagglehub.** `--source kaggle` reads a table file of a dataset's zip at a version
  through Kaggle's own API (public datasets need no credentials), with its licence mapped from Kaggle's name.

- **The examples fetch through the huggingface source.** Their shared reader (`examples/_shared/hf_rows.py`) reads
  each split's parquet conversion at a commit pinned once a fetch, each file sha256-checked, instead of the
  datasets-server's `/rows` (whose 2026-11-02 outage held back a release); the retry ladder, the parquet fallback
  and the fetchers' `--delay` are gone. The rows were checked equal to `/rows` at 21 places across the 8 splits the
  fetchers read, and the 12 committed Hub datasets fetched fresh match every frozen hash and gold checksum. The
  examples cap pyarrow below 26, which refuses the NumPy 1.x they pin on Intel macOS (18.1 to 25.0 checked).

- **A held-out side's reads, recorded, and its counts for safety only** (RFC-031 H1, H2; the triage fleet's 78 of
  91 held-out items read before anyone noticed): `evh exposure-add` records a read (by hand or a TSV), the harness
  records its own when it shows a held-out item's text, an output or a label, and every score on the side leaves the
  read items out and says how many (`pair-test --include-exposed` shows the full number beside it, marked);
  `evh exposure` counts the reads; `evh exposure-check` searches the project's public repos for held-out ids named
  after their time and exits 6 on one the register lacks. `dataset-split --seal --count-by` fixes what a held-out
  side's counts may be grouped by, `evh sealed-counts` counts by those fields per day (a capture's newer records too),
  and `evh dataset-seal-counts` lets a person add one.

- **Labels from what happened later, in other systems** (RFC-031 L1-L3, X3): `label-from-capture` and
  `label-coverage` join an outcome from another capture (`--outcomes C --join F=F --within -1m,+15m`, `--outcomes-as`
  one name across later captures), with an identity check and a "gone from the source, or its id reused" class that is
  never labelled; each label keeps when its outcome happened and when it became knowable, and the set its `as_of`; a
  relabel (`--from-set`) keeps the earlier labels, adds what matured and marks what changed after maturing, and never
  drops a label silently; a rule's `under: action` keeps production's action, and a run or rescore against the set
  leaves out an item where the variant acted otherwise ("not scorable under this variant", recorded). Several outside
  systems in one label run: `--outcomes` again, each with its own options, read under its own name; the set records
  each (`source.outcomes`, a list) and `label-mutants` mutates each join (the fleet's beta).

- **Replays with production's own writes hidden, and the history confound** (RFC-031 P1): `replay.hide: {kinds:
  [...]}` hands the adapter what to hide (production's own writes of those kinds inside the replayed window), as part
  of its identity, so only a faithfulness record made with it lets the replay be scored; an adapter marks the items
  where a variant met a person's reaction to an action it did not take, and the run and every score on it say how
  many (`history_confound`, the ids in `confound.jsonl`, never a held-out side's). The replay example shows both.

- **A past period at its own code, beside a candidate** (RFC-031 P2): `evh periods ID` (the model's ID) numbers a code
  record's deployed periods (with how each was dated, `dated_by: pull | commit`) and counts a replay's items in each;
  `evh period-compare SYSTEM --dataset D --candidate C` reads a period's production, its code as it ran and a candidate, refuses to count when the
  replay disagrees with production there, and gives the paired test on that period's items only.

- **The labeller mutation-tested, and labels kept only where production is reproduced** (RFC-031 X1, X2): `evh
  label-mutants` labels again with each named change to the rules or the join (built in, and a project's own) and
  exits 6 on a mutant that moves no label; `label-from-capture --reproduced-by REPLAY_RUN --production RUN` keeps a
  label only where the replay at the recorded versions reproduces production's decision, and counts one at a version
  dated by commit time (`dated_by: commit` on a code record's deployment) as approximate. A replay run records each
  item's commit on its row (`_commit`).
- **Dev observability, for this repository's deployment** (`infra/`, not the package; the homelab's contract,
  `docs/recipes/o11y-dev.md`): `make serve-dev` and `make mcp-dev` run the servers with the deployment's hooks in dev
  mode (`EVALS_ENV=dev`, `infra/inspector/hooks_env.py`). Errors go to GlitchTip `evals-dev` tagged with the service
  and the worktree (the git branch), release `dev-<7>`; spans carry `deployment.environment=dev` and the worktree; one
  log line per request, tool call and error goes to VictoriaLogs with the same labels. Settings come from
  `~/.config/evals/observability-dev.env`, never the repository. A dev run with a prod GlitchTip project, or a prod run
  with the dev one, sends nothing there; Umami counts prod's callers only. The repository gains an `AGENTS.md` for
  coding agents: run the `o11y-dev` skill before a PR; a dev error never becomes a GitHub issue.
- **`llms.txt`, the agent-facing index of this repository's docs** (llmstxt.org; issue #35): the agent rules by
  section, the ADR, RFC, PRD and UXS sets with their counts by status, the decisions every change must respect, the
  guides, the docs to read for each area of the code, and for each service its GlitchTip project and logs. Made by
  `tools/llms_txt.py` from `tools/llms.in.txt` and the documents' own titles and status lines (`make llms`);
  `make llms-check`, part of `make quality`, fails when it is stale, a link, an anchor or a path in it does not
  resolve, or an index misses one of its documents, and the guard proves each of those failures.

- **`evh sweep --scratch`**: each arm a throwaway pass (`evh run --scratch`, under `.build/scratch/runs`, which nothing
  that reads runs sees), and no leaderboard after it, which would rank the real arms. A smoke of several arms no longer
  adds a second measurement to a real sweep's (`make sweep … ARGS=--scratch`).
- **A price that disagrees with the bill is named.** `evh run` and `judge-score` print a NOTE after their spend when the
  provider billed far from the prices the system's or the scorer's file declares (more than 1.2× either way), so the
  next dry run's estimate is not trusted blindly.
- **`evh env-check` says where each variable came from**: the shell, or the project's `.env`.
- **A long run's progress line says how long it has left** at its pace so far, when that is 30 s or more.

### Changed

- **`EVAL_MAX_COST_USD=0` means spend nothing**: a run, smoke, sweep arm or judging pass of a system known to be free
  (provider echo, a recorded arm, a judge of provider fake, or both `usd_per_mtok_in` and `usd_per_mtok_out`
  declared 0) is no longer stopped by it, and anything else is stopped before its first call (exit 7), with the message
  saying how to declare it free.
- **The Workbench's goal screen shows its command once**, and a goal's trend with fewer than two points is one line
  ("One point so far: …") rather than a chart; a page left open after the server restarted says, on any 401, that the
  server restarted and to open the Workbench link it printed.
- **Every command a surface shows is checked**: `tests/check_shown_commands.py` extracts each `evh` command from the
  Workbench's and the catalog's scripts and the package's Python and checks its name, flags and argument count (the
  self-test runs it). 13 wrong ones are fixed, among them the Workbench's `prompt-diff`, `round-open`, `arm-smoke` and
  `dataset-items`.
- **`schemas/config.schema.json` is removed**: nothing read it.
- **`evh scorer-new` writes `explain: true`**: a new judge scorer's judges give their reasons. A scorer without the
  field gives none, so every scorer made before keeps its judging sets and its messages byte for byte.
- **`goal-leaderboard`'s test against the leader carries its 95% interval** (`vs_leader.ci`, before Holm's correction;
  the verdict is after it).
- **The Workbench's eval screen draws the round's arms against its baseline** (`gain-cost`) where it drew each arm's
  mean against its cost.
- **A project names its store: `evh init --store files|sqlite` is required, and there is no default** (owner decision,
  2026-11-15). The two are equal choices: `files` keeps every run, label and score as a file under `data/`, in git
  (review in a pull request, history in git log); `sqlite` keeps the project's data in one database file,
  `data/project.sqlite`, which `.gitignore` leaves out of git (one file to copy and deploy). `evh init` without
  `--store` is `ERROR (bad-argument)` and changes nothing; with it, it writes `store: <choice>` into the project's
  `config.yaml`. A project whose `config.yaml` names no store is refused by every command that reads or writes its data
  (`ERROR (not-configured)`, with the same two-line explanation); it was read as `files`. `EVAL_STORE` still overrides
  the file, and a command that touches no project data (`--version`, `--help`, `init`, `env-check`, `skills-install`) runs
  as before. A project made before this release: add `store: files` (or `store: sqlite`, which it already names) to its
  `config.yaml`. `evh data-migrate` switches a project's store later. A release made by `_release.py copy-data` names its
  store too (`--store` is now required there, and a `files` release gets `store: files`).
- **A deployment's data is one SQLite file, opened read-only** (RFC-032 step 9, "the next deploy goes on SQLite"): a SQLite
  release served from the box's read-only mount failed on its first request (`/api/health` 200, every comparison 500:
  `OSError: [Errno 30] Read-only file system: .../project.sqlite-setup-lock`), because every open wrote: a lock file,
  `PRAGMA journal_mode=WAL`, `CREATE TABLE`. A project's database whose folder is not writable, or with
  `EVAL_STORE_READONLY=1`, is now opened as SQLite's `mode=ro&immutable=1`: no lock file, no journal, nothing created;
  every read works, a file that is not a project's database is `ERROR (invalid-file)`, and every write, through the store
  or the outputs, is `ERROR (not-allowed)`, never a sqlite error (`_store.readonly`, `require_writable`). The release
  build makes the SQLite release (`_release.py copy-data --store sqlite`: the filtered copy, every refusal and hidden-text
  rule unchanged, moved by `data-migrate` into `data/project.sqlite`, checkpointed and out of write-ahead logging so
  `data/` holds that file alone, and a `config.yaml` saying `store: sqlite`); `render.sh` makes it by default and
  `EVALS_STORE=files` makes the files release as before. Both services read the store the release's own config.yaml
  names, so a rollback may cross from one store to the other. Every check of render.sh reads the release through its
  own store (`_release.py check`: no reference text git does not track, no materialized item, the MCP answers cover every
  goal, the goals' tests kept, the one sealed database; and `evh migrate --check`), each failing on a leak planted in
  either store (`tests/test_release_store.py`, `tests/test_store_readonly.py`); the build after the copy runs read-only
  and fails if it changes the database. The inspector keeps the goals' tests in the release's `cache/evh-p.jsonl`, as the
  MCP server does (its default is a folder the mount cannot write). Measured on a render of a clean checkout of HEAD (the
  gold reference texts git does not track are not in it), the two stores side by side: the release 4,481 files against
  12,174 (its data one 241.5 MB file against 7,695 files of 176 MB; 160 s to render against 126 s); the catalog's 1,904
  files and the site's 2,083 equal but for the build-time footer; each of the 2,905 comparisons the catalog links to
  (2,888 with arms) and 38 MCP tool calls answered by the same bytes from both, with the inspector and the MCP server in
  compose.yml's container limits (384 MB, half a CPU, read-only root and mount) on python:3.12.14-alpine; the inspector's
  peak resident memory after every view 208.6 MB on SQLite (206.7 MB files), `docker stats` 191.1 MiB, 49.8% of the limit
  deploy.sh holds to 80% (files 49.5%); the container's cache of the database file brings its cgroup peak to the limit
  (reclaimed, no kill, no restart).
- **The same data makes the same SQLite release, byte for byte** (RFC-032 step 9): two releases built from two checkouts
  of one commit were different databases (2,624 of 58,965 pages, and the file change counter 3 or 5), because the
  `files` table kept each file's checkout time and the database's header kept how many transactions and checkpoints the
  move had made. Every file of a release now goes into the database with one modification time (2000-01-01 UTC,
  `RELEASE_MTIME_NS`: nothing reads it from a release), and the seal writes the database again whole (`VACUUM INTO`,
  which also takes 3.7 MB off: 237.8 MB), so the bytes depend on the data alone. The project's own database is
  unchanged. Measured with `rsync --checksum --delete --link-dest` (what deploy-prod.yml runs; delta transfer on, as
  over ssh) of `inspector/`: no data change 215 bytes sent (was 12.5 MB, 241.6 MB with a whole-file copy), where the files release sends 476 KB (its
  7,696-file list); one new run 20 MB, 122 MB or 228 MB sent by where its id sorts (last, in the middle, first),
  against 486 KB for the files release. `tests/test_release_store.py` builds the same data twice, a checkout apart.
- **A deployment shows the people's checks of a judge scorer**: the release copies `data/judge-validation` (each
  source's report, each record without the judge's reply, its hash kept), so a judge scorer's page and `scorer-show`
  on the deployed site list the same checks as the project's (this repository: two sources per scorer, 1,200 records,
  4.8 MB). Before, the copy left them out and every judge read as never checked by people.
- **A view is kept, not read again** (RFC-032 step 9, "the next deploy goes on SQLite; the solutions reusable for both"):
  a process that answers more than one view (catalog-serve's API, and the MCP server once it runs views in its own
  process) read every arm's scores, and indexed every run, for each question: 2 s of a 2 s view, in either store. The
  model (`model/view_cache`) now keeps them, once per process: the adapter and each arm's scores (`scores_once(...,
  held=True)`, bounded by `EVH_VIEW_CACHE_VALUES`, 2 million per-item scores by default, ~100 MB of this repository's
  1.4 million), and the answers of `overview-show`, `arm-list`, `dataset-arm-list`, `goal-leaderboard`, `metric-list`,
  `activity-show`, `dataset-list` and `dataset-show` (kept pickled, so a caller never changes what is kept). What is
  kept is valid for the data root, the store, the code's version, `_store.generation()` (every write through the
  store, either store, bumps it: a write in this process clears it at once) and the data's fingerprint (another
  process's write, looked at when an operation or a view starts; the project's config.yaml and .gitignore too). Same
  answers with and without it, on both stores (`tests/test_view_cache_views.py`): on this repository's data a second
  call in the same process is 2.0 s (files) and 2.5 s (SQLite) before, 0.00 s for the kept answers and 0.3 s for
  `goals`. `catalog-serve` keeps the goals' tests (`EVH_P_CACHE`) as `evh` does, which it did not, and decides a
  dataset's arms on that dataset alone (`dataset-arm-list` with an empty p cache: 11 to 4 s). The SQLite store
  resolves its database's path once per project instead of once per call and builds a path's key from strings, not
  pathlib: a view 2.4 s to 2.1 s (files 2.0 s). `tools/view_bench.py` measures any of it, in both stores.
- **A run's `config_id` is its `system_id`** (RFC-032 step 8): a run names its system, so the stored key is
  `system_id` and "config" is no longer the name of anything. Format 6 (`m0006_system_id`) renames it in every stored
  record whose key is not hashed: `run.json` (all 305 of this repository's), a score's `metrics.json` and the `unset`
  list of its `score.json`, faithfulness records, a study log's trial lines and a sealed dataset's unseals, each file
  written as it was with only the key changed. Kept, because the key is inside a hash (renaming it would move every
  stored hash): the fingerprint's `arm.config_id` (305 run records, 406 score records here), a judging set's
  `arms[].config_id` (60 arms in 3 sets), a label set's `source.config_id` (a set is hashed whole into the fingerprint
  of every run scored against it; 2 here) and a reference manifest's `from_run.config_id` and
  `promoted_from.source.config_id` (`from_run` is hashed with the reference; 2 and 3 here). A record with both keys,
  or a `config_id` that is not the id of a system of the project, is refused before anything is written. Writers write
  `system_id` and readers read it only; the schemas (`metrics`, `faithfulness`, `dataset`) say it. The JSON answers
  that named it change their key: `evh leaderboard --json` (its rows and its column list), `runs-list --json`, `run
  --json` (the dry run and the run written), `baselines`, `prompt-show`, the key file `sheet-export` writes, an
  arm's `config` block and the compare answer of `catalog-serve`; the text headers follow (`system_id`), and `evh
  arm-show` says `system` where it said `config`. Before and after, every view and every catalog page read the same
  but for those keys.
- **A run's settings are stored once, and the provider's billing object is kept to what is read** (RFC-033, format 7,
  `m0007_results`; both stores). `generation_config`, `generation_requested` and `encoder_window` were copied into
  every row's `_meta`; a setting that every row of every score of a run holds with one value now sits once in
  `run.json`'s `call` (the schema and `RUN_ONLY` name it, so a score neither unsets it nor carries it into a derived
  record) and leaves the rows; a run whose rows differ keeps it in them. `_meta.usage` keeps `cost`, `prompt_tokens`,
  `completion_tokens` and, when nonzero, `cached_tokens` and `cache_write_tokens` (from `prompt_tokens_details`); the
  rest of the provider's object (`total_tokens`, `cost_details`, `is_byok`, the token details) is dropped, and a `usage`
  that is `null` or not an object is left as it is. Rows are canonical text. On this repository's data: 14 runs, 31
  score sets and 3 settings hoisted (6,000 rows each), 53,720 usage objects slimmed (11 had no `cost`: none is
  invented), 295 `predictions.jsonl` rewritten, `data/runs` 153,465,935 to 112,483,047 bytes; every other number
  (the cost report, the 200 report claims, V5's signatures) reads the same. Writes keep it so: `evh run` works out
  `call` in memory and writes the rows once without it, every write of a score's rows slims the usage (the crash
  checkpoint too), and a score added to a run later (`rescore`, `judge-score`, `sheet-import`) drops a setting equal to
  its run's `call` and keeps one that differs. `model/results.py` is the one definition (`CALL_META`, `RUN_SETTINGS`,
  the slim) that the release's hidden-dataset filter reads too. `evh validate` V28 reports a stored row holding its
  run's setting or a `usage` key outside the kept set. `Result.meta` stays free-form: a usage object an adapter returns
  is slimmed when it is written.
- **A score's rows are written and read as rows** (RFC-033 step c; both stores). The store takes a score's rows as
  dicts (`put_rows`), keeps their canonical lines, and gives them back parsed (`_outputs.rows`; `item_rows` reads them),
  with the text derived (`rows_text`). A line that is not a JSON object with an `item_id` string is **refused at write**
  (`ERROR (invalid-file)`, naming the file and the row), by `evh run`, `rescore`, `judge-score`, `sheet-import`,
  `import-run`, `evh data-migrate` and `evh migrate`; the crash checkpoint (`rows.partial.jsonl`) is exempt: kept
  verbatim, a torn last line allowed. A hand-edited `predictions.jsonl` in the files store is still read (a strict reader
  raises on a line that is not JSON, naming the line; a page skips it) and `evh validate` V28 names each line that is no
  row. `data-migrate` writes a score's rows as canonical lines in either direction, so a row that was not in key order
  is canonical on the other side; a project whose file holds a line that is no row is refused until it is corrected.
  `evh migrate` to format 7 refuses such a score set too, writing nothing. The rows the cache keeps are shared dicts:
  code that reads them and changes one copies it first.
- **A score's per-item results are tables in the SQLite store** (RFC-033 step d, format 7, `m0007_results`).
  Table `rows` (one text value per line, 168.7 MiB on this repository's data) is replaced by `score_sets`,
  `score_rows` (the item, its `_meta` and `_extra`, and the fields that are not numbers), `score_values` (every field
  that is a number, one row each, its metric named in `metrics`), `call_facts` (what a run's call to one item was,
  held once for every score set of the run) and `rows_partial` (the crash checkpoint, verbatim): 82.0 MiB, indexes
  included, and the project's database 190.6 MiB (the lines of format 7) to 159.2 MiB. A row comes back as it was
  written: an integer stays an integer and a float a float (`1` and `1.0`, `-0.0`, int64's bounds), a bool, `null`,
  NaN, the infinities and an integer past int64 come back as they were, keys sorted; `_meta` absent, `{}`, its call
  facts equal to the run's or different, and `_extra` absent or `{}` each round-trip. A score set's id is the
  next after the highest (see the order the tables are built in, below), its rows are one id range, written in one transaction and deleted
  through the key: dropping a score set, or `rmtree` of it or of a run, takes its rows, and a run's call facts go with
  its last score set. `evh migrate`
  moves a SQLite project of format 6 into the tables in one transaction (14 runs, 31 score sets, 3 settings hoisted,
  53,720 usage objects slimmed, 93,025 rows in 711 score sets, 5 s on this repository's data) and drops `rows`; a SQLite
  project that is at format 7 already with the old table (an early build of format 7) is finished by `evh migrate`
  too, and `evh migrate --check` and every command refuse it until then (`ERROR (old-format)`). It then vacuums the
  database, giving back the pages `rows` held (a format-6 database of 241.8 MB stood at 327.7 MB after the move
  until vacuumed); a VACUUM that cannot run, short of free disk about the database's size, only says so. `evh data-migrate` moves a project either way with every score set's
  canonical text compared (on this repository's data: 711 score sets equal, files to SQLite to files byte for byte,
  13,022 files), and `evh validate` V9 reads a SQLite project's database: every score set with a record has rows, as
  many as its `n_items`, and each committed arm meets its floor. Reading a score set's rows costs more than parsing
  its lines did; a reader of the numbers (`item_rows(meta=False)`: the leaderboards, the arms and goals pages, the
  paired tests) is not given `_meta` and `_extra` and does not decode them, which leaves the one-pass views 10-19%
  faster than with the lines (`tools/view_bench.py`, medians of three interleaved runs). The suite runs with
  `EVH_FREEZE_ROWS=1`: the rows the cache shares are frozen, and a view or command that changes one fails at the line
  that does.
- **A SQLite release is sealed at 16 KiB pages** (RFC-033 step e). `_release_store.seal` asks for `page_size = 16384`
  before its `VACUUM INTO` (SQLite takes the copy's page size from the connection, not from the file, and only outside
  write-ahead logging), `PRAGMA page_size` on the release says 16384, and render.sh's release check (`_release.py check`)
  refuses a release at another size. On this repository's data the release database went from 142,020,608 bytes at
  4 KiB to 136,265,728 (two renders from two checkouts a few minutes apart: one sha256); what a deploy's rsync sends of
  it is in the next entry. Release
  and serving, in compose.yml's limits (inspector 384m, MCP server 512m): the catalog's 2,905 comparisons and the MCP's 38
  calls give the same bytes from a files release and a SQLite release. A hidden dataset's run.json `call` holding anything
  but the three run settings is refused with the rest of the release (`_release.plan_problems`): run.json is copied whole.
- **The SQLite tables are built in the order of time** (RFC-033 step e, owner 2026-11-16). `evh data-migrate --to
  sqlite` (a release's database is made by it, and `evh migrate` moves a format-6 SQLite project the same way) writes
  the outputs, the score sets, their rows and values, and the files under `runs/<id>/` (run.json, score.json,
  metrics.json, ...) in the order of the run's time, then the key (the other files of `data/`, in path order, come before
  every run): run.json's
  `started_at`, else its `created_at`, as an instant (a zone counts, a time with none is UTC); a run with neither as an
  ISO time comes first, by its key (304 of this repository's 305 runs hold `created_at` and one `started_at`). A score
  set's id is its place in that order, from 1, in place of the hash of its key; the metrics' ids are the order their
  names are first met in it. One data gives one database, whatever order its files were made in. A project that writes a
  score set later gives it the next id after the highest; a database built with hashed ids (an early build) gives the
  lowest free id when the highest has no room. What a deploy's rsync sends of `inspector/data/` (the flags of
  `deploy-prod.yml`, delta transfer on, this repository's data, the stand-in remote shell of step e): nothing when the data
  did not change (103 B), and for one new run of 5 items 4.3 MB when its name sorts first, 2.2 MB in the middle and 1.1 MB
  last, against 86.9, 61.5 and 10.1 MB (the same code as before measured again: 32.6 MB for a run named last, where the hash
  put its rows; 9.4, 4.7 and 1.1 MB with the `files` table in path order). What is left in the first two is `outputs`'
  index by run name (4.2 MB when the name sorts first) and the item index of `score_rows` (1.2 MB). A new score set on an
  old run lands where that run is, and the pages after it move: 26.6 MB for a run in the middle of the time order, 61.2 MB
  for the oldest (36.8 and 20.6 MB before: where the hash put it).
  The database is 128,581,632 bytes (136,265,728 before: a row id is 5 bytes where it was 7); two renders of one commit
  give one sha256. The views' speed in both stores, three interleaved runs against the code before, is within 8% of it
  and of step a (no row over 1.10; the first three runs, taken while the machine was used for tests, had three rows at
  1.11 to 1.20 of the code before).
- **The API's description, made from the operations** (RFC-032 step 9): `GET /api/v1/openapi.json` (OpenAPI 3.1,
  with the token) and `evh openapi` give every operation's route, inputs, body, refusals and the job routes. Gone:
  `POST /api/v1/read/<command>` (a read run as a process) and `GET /api/v1/commands`; the operations' resources
  answer the reads. ADR-0029 records the model.
- **The catalog never goes stale** (RFC-032 step 8): `evh catalog-serve` rebuilds the pages as a `catalog` job when
  the data changes, at once for a write through the API or an edit, on the next read for any other (another terminal,
  a pull); the pages stay served while it builds and after a failed build, `/api/health` says which, and it no longer
  says to restart it. A scorers page (each judge scorer, its judges, validation and people's checks), linked from the
  arms it judged. The catalog's views as API resources: `overview-show`, `arm-list`, `dataset-arm-list`,
  `arm-show`, `metric-list`, `metric-show`, `activity-show`, `comparison-show` and `label-coverage-show`
  (`GET /api/v1/overview`, `/arms`, `/metrics`, `/activity`, `/compare`, `/datasets/{dataset}/label-coverage`), each
  the command's text and JSON; an API read's query inputs are typed by the operation's schema. Exposure registers,
  seals, looks and prompts read any data directory, so a copy's sealed side uses the copy's register.
- **A goal's decision is made once** (RFC-032 step 8): the answers, groups, leader, contenders and axes a goal page,
  `evh goal-leaderboard` (`GET /api/v1/goals/{goal}/leaderboard`), the overview and `evh leaderboard` show come from one view in the model; a round's leader follows the goal's rule (never an arm
  with too few items, the wrong format, or one that wrote its reference). The overview's test of the leader against
  the baseline is corrected for the arms the leader was chosen from, as a round's is (it was not); the goal page's
  note on the recommended arm says it is one comparison. `evh leaderboard` shows the goal's arms and groups, every
  label by default (`--label ""` the plain runs), and `--round` the arms the round compared under their labels (it
  showed the in-play systems' plain runs). The model's runs, rounds and goal status read any data directory, so the
  catalog shows a round's evidence from a copy too; one listing per entity (captures, references, label coverage,
  picks, tags, judge spend, rounds, runs). Fixed: a round's hold reason crashed on a test with no p.
- **Judging spend is counted** (RFC-032 step 7): `evh cost-report` ends with what judging cost, per scorer, judging set
  and judge, read from the verdicts' own `cost_usd` (`billed` where the provider reported it, `estimated` where the
  scorer's price table priced it; this repository's 3,280 verdicts: $13.50), the dataset filter applied through each
  judging set's dataset. Judging keeps its own budget and keys, never a round's budget: a pass is capped by the
  smallest of its scorer's `cost_cap_usd`, the new `EVAL_JUDGE_MAX_COST_USD` and `EVAL_MAX_COST_USD` (a job's
  max_cost_usd), and its calls read the `EVAL_JUDGE_<NAME>` keys first, as since 0.4.0 (ADR-0005).
- **`evh judge` (the older judge panel, its own config format, no stored verdicts) is removed:** judge with a judge scorer (`evh judge-score`).
- **One `evh migrate` brings a project to 0.8.0's formats**, in seven numbered steps (m0001-m0007),
  idempotent, `--dry-run` first. `fingerprint-migrate` (0.6.0 to 0.7.2) is its fingerprints step; the per-format
  commands built during 0.8.0 were folded into it before the release. `data-migrate` (files and SQLite) stays its
  own command.
- **`runs-list --baselines` is now `evh baselines`** (RFC-027); `run-promote --baseline-id` is gone (a baseline is
  named by goal, dataset and version); `round-close --promote` promotes into the round's goal, read as the round
  reads its arms. A goal page reads only its own baselines, no longer a dataset baseline with no goal.
- **`dataset-split --by hash|time` is now `--split-by`** (and a split side records `split.split_by`), so `--by` means
  who acted on every command that writes (RFC-027).
- **The paired tests take their normal limit from 10,000 units** (ADR-0028). From 10,000 items (or clusters) the
  sign-flip p is erfc(|z|/sqrt 2) with z = sum d / sqrt(sum d^2), and the contender test's bootstrap-t p is
  1 - Phi(T), instead of 20,000 permutations and 9,999 resamples; a simulation over seven kinds of data
  (`tools/large_sample_check.py`) found them within the resampling's own Monte Carlo error there, and not at 1,000
  to 5,000 for heavy-tailed or sparse data, so below 10,000 nothing changes and no committed result moves.
  `pair-test` and `family-test` say which (`method`: `exact`, `sampled`, `normal limit`, in the text and `--json`;
  `family-test` a `p_method` per row). A p from the limit can be 0.0 (it prints `<0.0001`). A family that mixes
  sizes keeps its other opponents' p's: the one random stream moves past a large opponent as if it were drawn.
- **Every `evh` command keeps the p's it draws** in `<project>/.cache/evh-p.jsonl` (`EVH_P_CACHE`; an empty value
  turns it off), as `evh mcp` did: `goals` right after `catalog` reads them instead of drawing them again (142 s to
  0.4 s on a 1,000-item, 50-arm project).
- **Resampled tests are drawn at once in child processes**: a catalog's, a goal's and a comparison's bootstrap-t's
  and sign-flips are found first, drawn in parallel, and read back, the same p's bit for bit (each is seeded by its
  data or its seed). The 1,000-item, 50-arm project's catalog took 16.3 s instead of 150.4 s, `goals --goal --json`
  12.5 s instead of 147.7 s, with the same JSON and the same pages. Small projects are drawn as before, and so is
  everything in a container under one whole CPU (the quota is read, as `cpus: 0.5` hides it from the core count);
  `EVH_WORKERS` sets the number, `1` turns it off.
- **A dataset page lists 200 items a page**, the rest on pages beside it (`d/<dataset>~items-2.html`, ...): the
  10,000-item page was 13.8 MB, now 0.32 MB. The page's filter reads its own page; `evh dataset-items` lists all.
- **The agent skills put a setting in with `evh data-put` and read one with `evh data-show --text`**, in a
  temporary folder, so they work in either store and never touch a folder of the project's own.
- **A run's outputs are one file** (RFC-024). `outputs.jsonl`, a line per item (`item_id`, `text`, `sha256`),
  appended as each output is produced and rewritten in dataset order when the run completes, replaces the `outputs/`
  folder of one file per item. Re-scores, judgings and sheet imports no longer copy their source's outputs: they read
  them through `derived.from`. Every module reads outputs through one function. `evh migrate` moves a project's
  runs (`--dry-run` first); in this repository it turned 94,796 files into 305 (`harness/data/` from 106,492 files
  to 12,001), every output and V5 signature checked equal before and after. A derived run records its source's
  directory (`derived.from_dir`) and reads only that run; `validate` V23 names a run left in the old layout or a
  derived run whose source is gone. A resume from a run that kept no row checkpoint no longer crashes (`_Resumed`
  read `_extra` from an empty row).

- **A dataset's version means something.** `version` is MAJOR.MINOR, two integers (1.10 follows 1.9), computed from
  the lineage when the dataset is made: 1.0 for a first dataset and for each side of a split (which names its
  parent's version, `split.from_version`); from a parent (`--from`, `dataset-extend`), MINOR + 1 when items were only
  added, MAJOR + 1 and MINOR 0 when any was removed or changed. A licence or description change is no new version.
  `validate` (V22) recomputes it; `evh migrate` writes it for records made before (every committed dataset
  is 1.0 by the rule, as it was). Neither key is in a run's fingerprint: no run moves.

- **One failed item no longer stops a run** (owner, 2026-11-05). An item whose call fails (not transiently) is
  scored as an empty answer (0 on most measures, or the adapter's `score_failure(reference)`), marked `failed` on its
  row, listed in metrics.json's `failed_items`, and called again by `--resume`; the run goes on. A 429 or a timeout
  that outlasts the retries now stops the run with `75` like an unreachable server (it used to end in a traceback),
  and more than 5 failures that are also over 20% of the items called stop it with `ERROR (failed)`.
- **A contender is shown no worse than the leader** ([ADR-0026](../docs/adr/ADR-0026-contenders-by-non-inferiority.md)).
  It had to be "not significantly different", which more arms are the fewer items there are, and `frugal` then
  recommended the cheapest. Now a one-sided non-inferiority test against the leader decides, Holm across the
  candidates: Tango's score test for 0/1 scores at any size, the bootstrap-t from 100 items or clusters for other
  scores, "too few items to call a tie" below. A strategy is a default margin: `balanced` 5% of the leader (was 2%,
  with the old test), `frugal` 10% (had none), `quality_first` the same quality; a goal's `axes.quality.margin`
  wins, and `validate` notes each goal on a default. **Recommendations move** on goals whose contenders the old
  rule over- or under-counted: on this repository's 7 goals, scifact recommends deepseek_s (was the free e5_base, not
  shown within 10% once 18 arms are corrected for), ag_news bert_base_ta and triage its leader (both were undecided).
- **Each exit code has one meaning** ([RUNBOOK, Exit codes](docs/RUNBOOK.md#exit-codes)). The cost cap that stops
  `evh run` or `judge-score` early exits `4` (was `2`, which is also a usage error); a run that measured nothing
  exits `7` (was `1`, which is also a refusal); a server that could not be reached exits `75` (was `1`); a check
  that ran and found problems exits `6` (was `1`): `validate`, `self-test`, `env-check`, `importer-check`,
  `arm-smoke`, `model-onboard`, `deploy-sheet --capture`; a `sweep` in which some runs failed exits `5` (was `1`).
  `evh` exits `70` for an error nothing caught (a traceback) and `130` on Ctrl-C, without a traceback.
- **Every refusal names its kind:** `ERROR (<kind>): <why>`, the kind one of fourteen
  ([RUNBOOK, Refusals](docs/RUNBOOK.md#refusals)): `not-found`, `bad-argument`, `would-overwrite`, `mismatch`,
  `invalid-file`, `not-materialized`, `not-enough`, `not-public`, `not-allowed`, `not-configured`, `failed`,
  `missing-dependency`, `over-budget`, `old-format`. A script or an agent reads the kind, which stays when a message is reworded. The
  project's `AGENTS.md` (`evh init`) says what to do for each exit code and the common kinds.

- **Every legacy read is an operation or gone, and MCP answers in the server's own process** (RFC-032 step 9, owner
  2026-11-14/16: "this is a new project and I don't want many legacy commands or tools, we just move forwards"; no alias,
  no shim, no old name kept). The 16 commands that read a view through a script of their own are removed, each replaced
  by the operation (and its API resource) that answers it, which now also gives what the old command gave and the
  operation lacked: `overview` is `overview-show`; `activity` is `activity-show`; `arms` is `arm-list` (`--systems 1` a
  row per system) and `arm-show LABEL DATASET SYSTEM`; `datasets` is `dataset-list [--tag K=V] [--period P]` and
  `dataset-show D` (its arms: `dataset-arm-list D`); `references` is `reference-list` and `reference-show TIER NAME`;
  `metrics` is `metric-list` and `metric-show M`; `goals` is `goal-list [--period P]` and `goal-leaderboard G [--arms
  PATTERN] [--top N]`; `rounds` is `round-list G`, `round-show G R` and `round-evidence G R`; `inspect` is
  `comparison-show` (the verdicts; `--analysis`, `--round`, `--goal`, `--rescore 0`), `comparison-item` (`--item`),
  `comparison-crosstab` (`--crosstab`), `comparison-items` (`--items-out`) and `sheet-show D` (`--sheet`), with
  `sheet-export` the one that writes a file (`--csv`, `--fill`, which no tool and no API resource offers);
  `labels` is `label-set-list D` (each pair's confusion matrix is always in the answer: no `--confusion`) and
  `label-set-show D SET`; `tags` is `tag-set-list D`; `captures` is `capture-list` and `capture-show C`; `models` is
  `model-list [--kind K] [--where W] [--status S]` and `model-show M`; `prompts` is `prompt-list` and `prompt-show --name
  N`; `studies` is `study-list G` and `study-show G S`; `label-coverage` is `label-coverage-show D`. The reads that were
  commands of their own are operations now and name the thing they read as their argument: `leaderboard`, `pair-test`,
  `family-test`, `rank-stability`, `sealed-counts`, `label-mutants`, `dataset-items` and `dataset-card` take the
  dataset (`evh leaderboard D`, not `--dataset-id D`), `deploy-sheet` and `period-compare` the system, `periods` and
  `faithfulness-show` the model, and `exposure --dataset-id` is `--dataset`; `dataset-card --out` is gone (it prints:
  redirect it) and `search --adapter` with it. Several outside systems for `label-coverage-show` and `label-mutants` are
  `--outcomes` repeated, as `label-from-capture` takes them. A conflict between two options of a read is `ERROR
  (bad-argument)` (exit 1), naming the inputs (`b_dataset and round cannot be combined`), where the old parser said
  exit 2; `inspect`'s choice of what to show by which option was given is the choice of command. Dropped, with no
  replacement: `arms --by system|model|provider|scored|none` and `arms --all` (`arm-list` groups as the arms page does,
  by dataset, three arms a group, `dataset-arm-list D` opening one; `--systems 1` lists a row per system instead), `arms --arm
  ID` (`arm-show`), the `labels` and `tags` listings of every set of every dataset (`dataset-list` says each dataset's label
  sets, `dataset-show D` its tag sets), the studies listing across goals (`goal-list` names each goal's studies that
  ran), and `--adapter` of the view
  commands (every operation reads the project's adapter). What a command prints is what it printed (the tables, the notes, the columns);
  what `--json` gives is the operation's result: structured, no longer the printed blocks, so `result.values.groups`
  of `goals --goal G --json` is `result.datasets[].groups[]` of `goal-leaderboard G --json`, `runs-list --json` is
  `result.runs`, `looks --json` is `result.sets`, `baselines --json` is the export itself (`result.schema`,
  `result.baselines`), `dataset-list --json` and the other listings are `result.datasets`, and so on; `pair-test`,
  `family-test`, `leaderboard`, `rank-stability`, `run-compare`, `validate`, `sealed-counts`, `periods`,
  `period-compare`, `faithfulness-show`, `label-mutants`, `comparison-item`, `comparison-items`, `comparison-crosstab` and `sheet-show` keep `result.blocks` and `result.values`. Every script of a
  removed command, and the process path the MCP server and the API ran a read by, are gone.
- **MCP tools are the registry's reads, named as the operation, answered in the server's process** (RFC-032 step 9;
  no outside caller, so no old name kept): 75 tools on a local server (among them `study-ask` and `study-tell`, the
  only tools that write) and 62 on a public one, where there were 40 command tools beside 43 operation tools. A call is the
  operation's own call, in the process the server runs in: no process per call, the view cache and the p cache shared
  by every call, the answer the operation's structured result (as `structuredContent` and as JSON text, in the envelope
  `{"command", "version", "result"}`). A tool name from before that differs from its operation (`goals`, `datasets`,
  `arms`, `models`, `inspect`, `labels`, `rounds`, `references`, `metrics`, `overview`, `activity`, `captures`, `tags`,
  `prompts`, `studies`, `label-coverage`) is gone; an input is the operation's own, typed (`dataset`, not `dataset-id`;
  a list is an array; a flag a boolean) and checked against the tool's JSON Schema before anything runs. `--public` is
  the flag of each call (what `--public` hides stays hidden: a hidden dataset's text and labels; the tools that would
  answer with an item's text, an output or a label are not offered, nor `group` and `group_match` of
  `comparison-crosstab`, nor `items` of `label-set-show`, and a public server's `label-set-show` answers with no
  labels). What a call computes is its own while others run beside it: its printing, its notes (the held-out items
  left out, the items not scorable, the history confounds) and `include_exposed`; the scores the server keeps are kept
  before the held-out items are left out and are filtered on every call, so a kept answer still says what it left out. The first `goal-list` call after a start, which was 33 s at the box's
  cpus 0.5, is 7 to 8 s at those limits; the next views take 0.3 to 2.5 s where each took 12 to 16 s as a process of its
  own, and the view cache keeps one computation in flight per key, so two callers asking for the same view at once pay
  for one. So no answer is written ahead any more (owner, 2026-11-17): `evh mcp`'s `--write-answers` and `--answers` are
  gone, with render.sh's step that wrote `mcp-answers.jsonl` and its check of it, and compose.yml's `--answers`. A call that runs past `--timeout`, or is cancelled, stops being waited
  for but is not stopped: a computation answered in the server's process runs to its end, and keeps its slot (and its
  caller's one call at a time) until it does, so no more runs at once than `--concurrent` allows. The old server refused the
  tools that take more than one path argument (`arm-show`, `reference-show`): it sorted a call's arguments by name
  before putting them on the command line.
- **A job is an operation and its inputs** (RFC-032 step 9; owner 2026-11-16: a route for each): every command that ran
  as a job is a work or decision operation (58), with its locks, whether it spends and a decision's reason declared,
  and starts at its own resource as well as at `POST /api/v1/jobs` (`POST /api/v1/goals/{goal}/rounds/{round}/close`,
  `POST /api/v1/systems/{system}/runs`, `POST /api/v1/data/file`, ...), answering 202 with the job. A job is
  `{"operation", "inputs", "by", "for", "max_cost_usd"}`, where it was `{"command", "args", "by", "reason"}` (refused
  now); an estimate is `{"operation", "inputs"}` and answers the dry run's text and its result; a job's record names its
  `operation` and `inputs` (no `command`, `argv` or `reason`) and reports `progress` and `spent_usd`; a goal's status
  names a running job's `operation`. An input is named as the operation names it, with underscores (`dataset_id`). On
  the command line a route's parts are named options, never positionals: `evh data-put --path P (--file F | --set
  K=V ...)`, `evh data-rm --path P`, `evh round-close --goal G --round R --conclusion ...`; `evh jobs-start` names an
  operation and has no `--reason` (a decision's reason is one of its `--arg` inputs). A local MCP server's `study-ask`
  and `study-tell` run as the operation's own process. `migrate.py` run as a file is only the dry run's own child and
  refuses anywhere else.

- **`evh run` refuses a repeat set beside a plain run of the same system** (`--repeat N` when the dataset already has a
  measured run of it), before any call: the two were two measurements of one system, which `evh validate` refuses
  (V8) once committed. Measure a hosted arm once, as its repeat set; to repeat a run afterwards, `--purpose repeat --of
  <run_id>`. A resumed, scratch or label-set run is not refused.
- **A closed round keeps the numbers it closed on.** Every view of a round (`round-evidence`, the goal page, the
  inspector's `--round`, the Workbench) reads the runs the round recorded; a run of its systems made after it closed is
  named "since then", never mixed into its means and tests.
- **`dataset-split` gives each side the parent's references** on its own items, promoted from the same label sets and
  recorded with who split it: with references on the parent it needs an actor (`--by`, or `EVH_ACTOR`).
- **A round carries an arm from the round before only when that round ran on the same dataset**; any other system
  is carried through its own runs on the round's dataset, never run again, and refused (`not-found`) when it has none
  there (the Workbench carried a 13-item validation run into a 20-item round, and its evidence compared the two). The
  Workbench's form carries arms one by one.
- **`judge-score` refuses a grade prompt that does not name the task's dimensions**, before any call (a prompt that
  does not, made both judges invent their own keys and every reply came back unparsed); `--no-calls` is not checked.
  An unparsed grade names the keys it expected.
- **`family-test` prints wins, losses and ties** (`A wins-losses (ties)`, was `A wins`, which read 8/32 beside a
  positive delta when 23 items tied); `--json` adds `losses` and `ties`.
- **`rank-stability` measures halves of 5 and of half the dataset** besides 10, 20, 50 and 100, so 20 items give a
  line rather than one point, and reads "saturated" from halves of 10 up.
- **A read asked with `optional=1`** answers a `not-enough` or `not-found` refusal with 200 and `{"result": null,
  "empty", "kind"}`: the Workbench asks its charts and optional files that way, so "nothing yet" is no browser console
  error.
- **The leaderboard says why the goal recommends what it does**, under the goal's line; `round-open`, the round budget
  refusal and the catalog's text view name `round-evidence` for a round's evidence and spend.
- **A goal page's "test every arm against its leader" leaves the silver reference's author out** of the test on its
  own silver. `catalog-serve --port 0` prints the port it bound.

### Fixed

- **`evh validate` failed on every record the Workbench or the API wrote** (`'api' is not one of ['flag', 'environment',
  'terminal', 'migration']`): `from: api`, which a job started from an API call records, is in the actor's `from`
  list of every schema that has one (rounds, scores' metrics, references, datasets, baselines, models). A new test
  (`test_validate_after_api.py`) starts jobs through the API as the Workbench does and runs `evh validate` after, and
  checks every such schema lists every origin a job may carry.
- **"See the cost first" asked for a check the system could not keep.** A smoke is kept on a model's deployment, so a
  system that names no model record never had one recorded, and the screen and the dry run said "check it first" after the
  check had run. They now say the system names no model record, so its check is not kept, and to set the cap from the
  check's own "all N items" line; the check says "not kept" under its result.
- **The held-out test screen asked for the exposure register of a side that is not sealed** and the API refused it
  (409, a console error). The screen asks only for a sealed side's register.
- **The Workbench did not say to commit what it wrote before a paid run.** The eval screen's "Run arms in it" now says the
  screen wrote files into the project and that a run on uncommitted files is recorded dirty.
- **The Jobs list and `evh jobs-status` showed a check that flagged something as "failed".** A job that ends with exit 6
  (arm-smoke, model-onboard, exposure-check: the checks ran and flagged) reads "checked, flagged" in the Workbench, in
  `evh jobs-status` and in `evh jobs-logs --follow`, from one definition (`state_label` on the job record, which the API
  carries); its stored state stays `failed` (the `--state` filter), its exit code is shown.
- **The held-out screen asked for the paired test before the candidate had runs on the side**, and the API refused it
  (400, "only 0 shared item(s)", a console error). The confirmation now says which of the two has no run there and asks
  once both have.
- **A chart wider than a phone looked cut off** at its right edge (it scrolls in its own box, which only an edge shadow
  said). A line under it says to slide it sideways, shown only while it is wider than the screen.
- **"Choose the systems" and "Run arms in it" listed the systems of every goal.** A system measured only for another goal
  is left out; a system never run is offered on every goal.
- **The data page named `tools/validate_judge_*.py`** as what writes `judge-validation`, a script a `pip install` does not
  ship; it names the judges' validation as an `evh run`.
- **`pair-test --round` read the runs the round recorded and the arm's later ones**; it reads only the recorded ones,
  as every other view of a round does.
- **`make demo` overwrote the committed `smoke_v1` dataset** (it re-created it with `--force`, sweeping the real datasets' row
  files into it) and added its runs to the committed `data/runs`: it now leaves an existing dataset alone and runs a scratch
  pass (nothing added to committed data, any number of times).
- **`evh jobs-status` and the API's job reads stopped on a job record from before jobs were operations** (a KeyError,
  a 500): the record reads with the operation `unknown`, its state as recorded, and resuming it is refused.
- **No log file holds the Workbench's token.** `evh catalog-serve` printed the sign-in link with its token, and its
  access log wrote the session route's request line, token and all: a background job's log or CI's kept a working
  token. The full link is printed only when the output is a terminal; to a file or a pipe it names the token's file
  (`.build/api-token`) instead, and the access log masks the token. A terminal recorder (`script`, asciinema, tmux's
  `pipe-pane`) runs in a terminal and still records the link. Found by the fleet trying 0.8.0 (2026-11-18), as were the
  four below; a review of the release (2026-11-19) found the six after them.
- **`evh run` and `evh arm-smoke` say where a spend without a bill came from.** They called any such figure "the
  system's price table" even for a system with no prices, whose adapter reported the cost itself (a gateway key's
  spend). Now: the adapter's own figure, with its source, when its meta names a `cost_source` (whatever prices the
  system declares for the dry run's estimate); else the price table when the system declares `usd_per_mtok_in` and
  `_out`; else the adapter's own figure. INTEGRATION.md says how an adapter names its source.
- **`evh comparison-show` with no metric named compares on the arms' own primary metric, among the metrics every
  compared arm scores**, not the project's most common one (bugfix arms were compared on triage's `actionable`); a
  primary only some arms score never wins over a metric they all share, and a metric scored against a reference
  (`oracle_pass vs gold`) is that metric. When the primary has no score per item as the arms are read, it says so
  instead of moving to another in silence: which arms lack it, the `--label` of another reading of the same runs that
  scores it, and the arms scored for it nowhere (bugfix arms read as plain runs carry `oracle_pass` only under
  `silver`).
- **`evh chart trend` draws what each point was at the time, on one time line.** It said a goal had no closed rounds
  with its measure when the measure was added after the runs (triage's `triage_cost`): a run measured before its
  measure existed is now read from its latest re-score, and its row says so; any other run from the score it made
  when it ran, a baseline version from its record. Every baseline version and closed round is one point in the order
  they happened, named by itself (`v2`, `r1`): a round's point no longer sits under a version's name, nor a second
  dataset's names over the first's. With nothing to draw it says how many versions and rounds it found.
- **A record `evh migrate` filled in names nobody**, wherever an actor is shown: "promoted 2026-10-31 by nobody
  recorded (before 0.8.0)", not "by before 0.8.0" (baselines, label sets, looks, prompt versions, faithfulness, in the
  CLI, the catalog and the Workbench); `label-set-show` printed the raw record.
- **`evh chart gain-cost` no longer fails on an arm that shares no item with the baseline**: it is a row "not
  compared: no shared item", left off the drawing and named in the caption, not a crash of the command, the API and the
  Workbench's chart. A study is drawn on its own measure in that measure's direction (on a measure other than the
  goal's primary, a trial better on it was drawn down and called worse); the axis says when lower is better and the
  mark is flipped; with no cost recorded the cost axis is tokens per item; a trial its rule dropped carries its reason;
  a significant difference at no cost difference is "better at the same cost", not "better and cheaper".
- **A Workbench screen that asks for a read already on its way is drawn when it lands.** Since a read only redraws the
  screen that asked for it, a screen opened while the screen before was still reading the same thing stayed on
  "Reading…" for good.
- **`evh chart intervals` draws the margin from the arm contenders are tested against**: the promoted baseline when
  the goal says `axes.quality.reference: baseline`, not always the leader; and only a significant difference is a
  filled dot (the leader, the zero, was filled too).
- **`evh chart agreement` draws a judge pair with no τ as an empty cell**, not as 0 (two judges that disagree).
- **The inspector's p50 and p95 of a time are the leaderboard's** (linear between the closest ranks), as `evh chart
  latency`'s now are: four times gave p50 30 in the inspector and 25 in the chart.
- **`evh validate`'s V12 checks a committed reason's shape**: `why` a sentence, or one per graded output, never beside
  `why_missing` or `why_withheld`; it read the reply only, so a hand-edited reason passed. Whether a reason repeats the
  source stays checked when it is written, where the source is at hand.
- **In a SQLite project, `evh data-ls` and `evh data-show` show a run's outputs and a score's rows.** The database keeps
  them as table rows, so `outputs.jsonl`, `predictions.jsonl` and a checkpoint's `rows.partial.jsonl` were missing from
  a run's folder, `data-show` refused them, and the overview counted 1,728 files under `runs/` where the same project on
  files has 2,744. Each is now listed, counted and shown as the file `data-migrate --to files` writes from it, its
  sha256 the file's; its time is that of the file written beside it (the database keeps none for rows). Found comparing
  every read command of this repository's data on both stores (2026-11-19).
- **A Workbench read answered after its screen was left no longer redraws the screen opened since.** A slow read (a
  chart) landing on Settings redrew its text box while a person typed, and the rest of the typing went into the new box
  in front of the old text: the file saved held both.
- **A study whose baseline has no run on its dataset is refused**, its dry run too, saying to run it first: every
  trial was run, paid for and dropped as "not compared: only 0 shared item(s)".
- **A failed job says what it printed last** in the Workbench when it printed no `ERROR` line (a check's findings, a
  traceback), not "see the job's log"; the leak check's exit 6 (its finds) is read as finds, not as a failure.
- **A run that stopped before it wrote anything is not resumed**: `jobs-resume` (and the API's resume) started a job
  that then failed with "cannot resume: no outputs"; it refuses before starting anything, and says to start the run
  again.
- **A read the API serves that refuses is answered with the refusal**: a read whose body refused as a command does
  (`ERROR (old-format): …`, a project whose config.yaml just named a store still empty, say) ended the server's request
  with no answer at all. It is answered at its kind's status with `{error, kind}`.
- **The Workbench opens live on a project that refuses a read**: it fell back to the mockup on any answer but OK or 401,
  so a project whose data needs migrating showed the mockup's data. The home shows the refusal with the way to
  Settings, and Settings no longer needs the dataset list to open.
- **`judge-score` runs as a job and with `--json`**: its body asked `sys.stdout.isatty()` to line-buffer, and the
  envelope's stand-in for stdout had no `isatty`, so the API's judge-score job and `evh judge-score --json` stopped
  (exit 70) before judging anything. The stand-in says it is not a terminal.
- **A list item past the end is refused when a record is made**, as it is when one is changed: `--set judges.2.id=x`
  on a new scorer (or model, deployment, system, field set, failure-mode list, goal) stopped with an error nothing
  caught (exit 70; the API's 500) instead of `ERROR (bad-argument)` naming the key.
- **An unhandled error in `evh catalog-serve` is answered as JSON** without `--hooks` too (API 6 of the Workbench's
  list): a route that raised closed the connection with no answer, so a Workbench page read a broken response, not
  `{error}`. It is now a 500 with `{"error": …}` either way; without hooks the traceback is printed on the server's
  stderr, with them the hooks are told as before.
- **A run's output, an exposure, a pick or a record's history holding U+2028, U+2029 or U+0085 is read whole**
  (RFC-033; unreleased 0.8 code, an independent review): JSON-lines files keep those characters raw, and their readers
  split lines with `str.splitlines`, which splits there too. `evh data-migrate --to sqlite` dropped such an output
  without a word (its read-back check read the file the same way), `--to files` could never finish, an exposure's
  `what` made the register unreadable (every score of that held-out dataset failed), and the next save split a
  history's line in two for good. Every JSON-lines reader splits on newlines only (`_common.jsonl_lines`).
- **`evh migrate`'s copy of a SQLite database is kept out of the project's data** (RFC-032; unreleased 0.8 code, an
  independent review): named `project.sqlite.before-format-…`, validate called it a stray file and its advice
  (`data-migrate --to sqlite`) would have moved the copy into the database. It is
  `project.sqlite-before-format-<the data's format>-<when>`, beside the database as its -wal is.
- **`evh migrate` refuses a SQLite project another process has open** (RFC-032; unreleased 0.8 code, an independent
  review): its last step drops a table and rewrites the database, under a running catalog-serve or run. As a job it
  waits for the server to let go, as `data-migrate` does.
- **An `/api/v1` request is logged and measured under its route** (RFC-032; unreleased 0.8 code): `--hooks` saw every
  `/api/v1/…` request as the one route `/api/other`, so a deployment's metrics and traces could not tell a goal's
  status from a job's log. Each is named by its route's template (`/api/v1/goals/{goal}/rounds/{round}/close`,
  `/api/v1/jobs/{id}/log`), never its ids; a path no route fits is `/api/v1/other`.
- **`evh mcp` with relative paths** (RFC-032; unreleased 0.8 code, found rendering a release as the deploy does,
  `render.sh _release <sha>`): the server moves into the project before it works, and read `--project` and a `--hooks`
  file from there, so a relative one named a place inside the project. They are taken where the caller stands.

- **`evh migrate` step 2 finds the configs step 3 does** (RFC-032; unreleased 0.8 code, found migrating the fleet's data): step 2 (deployments) looked for configs in data/configs, the studies and validate.json's globs but not in the folders config.yaml's `configs:` lists, so a smoke whose config named its `deployment:` there was refused (`its config names none, and the model has 4`). It reads those folders too.
- **`evh migrate` step 3 keeps config.yaml's config folders findable** (RFC-032; unreleased 0.8 code, found migrating the fleet's data): a project with no data/validate.json had config.yaml's `configs:` removed and no `systems` glob written, so the systems the step wrote were in no folder the project read and step 6 refused every run (`config_id … is not the id of a system of this project`). Step 3 now writes data/validate.json with the `systems` globs of the folders it moved (UPGRADING always said they are added to them); an existing validate.json keeps its other keys.
- **`evh migrate --dry-run` runs the real steps on a copy** (RFC-032; unreleased 0.8 code, found migrating the fleet's data): each step reads what an earlier one writes, so on a project several formats behind the dry run refused at a later step (step 6: `config_id … is not the id of a system of this project`) or counted differently from the migration (step 5: 157 arms where the migration made 186). It now runs the steps for real on a scratch copy of the data (and of config.yaml and the config folders it names) in the project's ignored `.build/`, reports each step's counts from that and deletes the copy; the project is untouched. The copy is as large as the data while the dry run lasts.
- **A crashed run names its build**: the run.json a run writes before its first item now holds `build`, so a run that
  was killed (and is kept to resume) no longer fails V3 "every run identifies its build".
- **Scores entered through a sheet pass V13**: `sheet-import`'s judged scores are a person's judgements
  (`derived.with.source: sheet`), not a judge scorer's, and V13 no longer asks for a scorer file under `data/scorers`
  for them.
- **"Warm-up: nothing to load" under load**: a warm-up that did nothing was reported as "warmed up in 6ms" when the
  machine was busy (the window is wall time and counts a descheduled process's wait). The threshold is 25 ms, from the
  measured distribution (a no-op window reached 11 ms with the machine at twice its cores); a model load or a hosted
  call takes longer, a call to a model already loaded on the same machine may now read as nothing to load.
- **The API took a file or code path where the command line does** (RFC-026 says it never does): `capture --importer`,
  `importer-check`'s importer and `dataset-create --source` given as `path.py:Class` loaded that file's code, `--query
  @file` of `capture` and `importer-check` read a file of the server's, and `data-put`'s file was read from the server.
  The API now takes a name for the first three, the query's JSON (not `@file`), and `data-put`'s file as an upload;
  each needed the server's token. A served argument whose help offers `path.py:Class` or `@file` without a rule fails
  a test.
- **The catalog's arms page** (its design critique, 2026-11-12):
  - Sorting a grouped table threw on a group's heading row and did nothing; it sorts inside each group now.
  - A column sorted its cells' text: a cost as "$0.0009", a blank first, every measure in one ranking. It sorts each
    cell's value now, blanks last, a measure among its own.
  - No row said what it was measured against. Each is tinted by its kind, under the row key, and "measured" names
    its reference and tier.
  - A free arm's cost read "—". It reads "$0".
  - The picked arms' bar hid under the header.
  - Sections are headings, and a column head keeps its meaning around its sort button.
  - "leader" did not say whether the lead was real. It says how many eligible arms it is not significantly
    ahead of, or that it is significantly ahead.
  - The role badges looked alike: a result is set solid, an arm left out drawn as an outline.
  - The trade-off charts did not name their reference; they do. Speed's ticks read "57.5 s", not "57500.0".
    The frontier is no longer drawn in the accent.
  - A grouping or a facet picked was lost on reload; both are in the address now.
  - Every catalog page has a skip link to its content.
  - The page opened on 690 arms in alphabetical order, no leader in sight. It opens grouped by dataset, the arms a
    goal decided on first, three a group with "show N more" (owner, 2026-11-12); a group's count follows the
    filter.
  - A filter that matched nothing left bare column heads. It says so, with a button that clears it.
  - A judged row was tinted in a model kind's colour and a silver row in a grey like a label set's: a judge's is the
    model source's colour, silver's the silver tier's, a label set's rule is thin. A baseline badge is plain.
  - `evh arm-list` opens as the page does: grouped by dataset, the arms a goal decided on first, three a group with the
    command that shows the rest; `--all` shows every row, `--by none` none grouped, `--dataset-id` one dataset in full.
  - A dataset's group mixed references and measures (gold and adjudicated gold; coverage and a judge's score) and read
    as one ranking. A group is now one dataset scored one way on one measure, its direction named; the page and `evh
    arms` say "dataset ag_news_200 · against gold/ag_news_200 · correct ↑". The deciding measure's first sort is best
    first. The table fits 1280. Each trade-off chart lists its points as a table, and its words are readable on a
    phone. The light theme's series colours are 3:1 or more on every light surface (amber was 1.9:1).
  - An arm scored against the reference it wrote led its group (coverage 1.000), told by colour alone: it says so in
    words, on the page and in `evh arm-list`, and is read last. Columns no longer overlap at 1280; a folded group opens ten
    at a time; the footer's command is the view's; a config's rank sorts by its number.
  - The rest of the arms page's review: heads that stay in view; a key to the role badges and the only chips labelled
    by kind; a group no goal decides says so; on a phone the controls and keys fold (the first arm from 1,135px down to
    769px); the period in the address (`?period=`, `#p` links still read); config ids linked; chart axes in Muted
    (they were 1.6:1).
  - The sixth review: "no goal decides here" showed under groups a goal decides, and a configs chip showed at an equal
    count (a display rule beat [hidden]; the catalog keeps hidden hidden now, which also showed the home page's
    period chips were found by a duplicate id: period.js finds them by place). Every grouping ranks like with like.
    Keyboard focus clears the sticky heads. The footer's command follows the period's "more…". Picks and the sort
    are in the address. A jump to the page's sections; cells name their group. Role pills padded; a sans note 12px;
    chart words 11px or more. `evh arm-list` says "1 arm", shows cost and latency, keys its roles.
- **`dataset-from-capture` deleted what sat in its items' folder**: `data/sources/<dataset>/` was emptied before the
  items were written, and a capture's own export kept there was deleted without a word (the fleet's beta). A file
  there that the dataset's record does not name is now refused (`would-overwrite`), and stays.
- **`pair-test --round` gave one reason for three**: a round whose only arm is its baseline, or whose leader is its
  baseline, was said to "record no other baseline run". Each is now named; `--a` naming the baseline itself is said
  as that, whatever else the round holds (the fleet's beta and retest).
- **`label-mutants` reported a join mutant it could not apply as SURVIVED**: a project's join mutant with a key the
  join does not read (`item_field`) ran the unchanged join. It is refused now, the key named (the fleet's beta).
- **A regression guard could not cover runs made before it was declared**: V5 read `expect_identical_to` only from a
  run's `metrics.json`, which a frozen run never gains. It now also reads the config's own declaration, so a guard
  pair from before 0.8.0 is checked as the guard, not flagged as a copied result. A config kept outside
  `data/configs/` is read from the folders `config.yaml` names under `configs:` (the fleet's beta and retest).
- **A history confound had two denominators**: the run's note counted every item (5 of 287), while its score's mean
  counted only the items the adapter marked (5 of 34, 0.147). An unmarked item now counts as 0, so both read 5 of
  287. A command reading part of a run (`period-compare`'s period) counts the confound over the items it reads
  (the fleet's beta).
- **`period-compare --production` took only a config id**, where `faithfulness --production` takes a run id; the run
  id was refused with "no run of". `--production` and `--candidate` now take either (the fleet's beta).
- **A code record's misplaced key was ignored**: `dated_by` on a version, instead of on its deployment, dated
  nothing and said nothing. A replay's code record is now held to its schema when it is read, and the refusal says
  where `dated_by` goes (the fleet's beta).
- **`validate` V24 failed every replay run**: it required a run's `deployment.code` to be one checkout (repo, commit,
  dirty, path), and a replay's (RFC-030) is its code record, the record's versions' hash and the commits it ran. The
  replay test read only V26's line of `validate`; it now holds V24 too.
- **`budget-check`'s cached answer timed recomputes**: the warm-up stops at 3/4 of the cache's 32 MB (151 of this
  repository's 2,931 catalog links), so most sampled links were computed on the request, and the median followed the
  runner's speed (26 to 53 ms against 50). Each link is now asked once and then timed (0.5 ms); the check prints how
  many links the warm-up cached, and an answer the cache does not hold stays the cold budget's. The inspector also reads
  each arm's `metrics.json` once instead of on every answer (an uncached answer 25.7 → 21.8 ms here; `--warm`'s peak
  116 → 128 MB).
- **An agent could not act through the API, and the server's own actor reached every job** (RFC-026, RFC-027; an
  independent review): a job had no `for`, so an agent's job failed when its command first recorded who acted (a run:
  after its last item, its cap spent), and every job inherited the server's `EVH_ACTOR` / `EVH_FOR`. A job call now
  carries `for: person:NAME`, refused before a job exists for an agent without it; a job's actor is its own alone.
- **Stopping a queued job left its supervisor holding the locks it had taken**, behind a job that read `cancelled`:
  the supervisor is now ended with it.
- **A command waiting for a lock a job held waited in silence** (`run-promote` on a test set, a run in a budgeted
  round, a study's log, `faithfulness-name`): it now says which lock and who holds it.
- **The pick list could lose lines, and a new SQLite project's database could fail to open, under writers at once**:
  the list is one per project, but `pick` locked per dataset and `dataset-extend` not at all, and in the SQLite store
  an append is a read and a rewrite (eight writers kept 21 of 200 lines); and setting a new database's journal mode
  while another process did raised "database is locked". The list now has one project-wide lock, and a database is
  set up by one process at a time.
- **The contender test raised on whole-number scores passed to `stats` directly** (an int has no `.hex()`); `evh`
  reads every score as a float, so no command met it. Its look-ahead dropped them too.
- **Test files left their temporary projects in /tmp** (6,762 of them, filling its inodes on a shared machine): the
  self-test and the store matrix give each test file a temporary folder of its own, removed when it ends.
- **A client could read the previous server's API token** (RFC-026): `catalog-serve` listened before it wrote
  `.build/api-token`, so a script that waited for the port and read the file at once got the old token and a 401
  (the store matrix met it under load), and the file was truncated and then written, so it could read it empty. The
  port is now bound, the token written (beside and renamed into place), then listened on; a port that cannot be bound
  leaves a running server's token alone.
- **`family-test`'s first run below 10,000 units took 37.6 s at 1,000 items** (49 opponents): its opponents share
  one random stream, so they were summed one after another. They are now summed in child processes, each from the
  stream state its opponent starts at, and each sum is exact on integers: 6.7 s on the same project, every p bit for
  bit what it was (the S2 bench, PLAN_0.8.0). Under one CPU it is drawn in order as before, still faster.
- **Items with the same text got each other's labels**: labels follow an item by its text's hash, so on one dataset
  every item with the same text (the same alert twice) took the label of the last of them, and a reference promoted
  from the set held that label for all. Found by RFC-030's example, where 13 of 20 decisions share their text with
  another: its faithful replay scored 0.6 against gold instead of 0.95. A label made on the item's own dataset now
  follows its id; on another dataset a text its set labels two ways carries neither. The catalog's label views read
  the same way.
- **`fieldset-propose` proposed `date` for a timestamp**, whose values `dataset-create` then refused; a date or
  datetime type is proposed only when every sampled value reads as it, else text.
- **A round opened with `round-open` lost its actor**: `_rounds.save` writes a fixed list of fields and `actor`
  (RFC-027) was not among them. Found building studies; `test_actor` now checks a round.
- **`evh catalog` emptied the served folder before building** (RFC-026 step 4): a server showed missing pages for the
  whole build, and a failed build left none. It now builds beside the folder and swaps it in.
- **A job just started read `lost`** until its supervisor took its lock (found building step 4): it reads `queued`
  while the supervisor process it started is alive.
- **A file could be read cut short while it was written over** (RFC-026 step 1): `_store` wrote a file on disk by
  truncating it and writing again, so a second reader (another terminal, the catalog server) could see half of it.
  Every write is now a new file renamed into place. And `reference-promote` wrote its texts before its manifest:
  it now builds the reference in a hidden folder and moves it in whole, as label sets already were. The RUNBOOK's
  "What another reader sees while a command writes" lists each command's order.
- **The comparison swapped an asked metric in silence**: `comparison-show --metric M` (and the inspector's `metric=`) on
  runs with no per-item score of `M` compared another metric and did not say so. It now says `M` cannot be tested,
  gives each arm's recorded value, and names the metric compared instead.
- **`dataset-create --update-fields` kept only part of the record**: it rewrote the dataset with its items,
  description, source, licence and lineage, and dropped its card, tags, split block, hidden-text flag,
  `extended_from` and `made_from`. Every key it does not set is now kept.
- **A judge that runs out of `max_tokens` is stopped after 3 calls, not after the whole pass.** A reasoning judge
  that spends its tokens thinking replies with nothing, every time; judge-score said so only at the end, after every
  call was paid for (the 0.7.1 newcomer run: tutorial 3's judge at 400 tokens). Now a judge whose first 3 replies all
  come back empty at the token limit stops the pass (`STOPPED EARLY`), keeps what it stored, and prints the hint.
- **The newcomer scenario and tutorial 3 commit what judging writes** (`data/runs` with label `silver`, `data/judging-sets`,
  `data/judge-verdicts`), which they left untracked.
- **The inspector opens on large comparisons.** At 10,000 items and 40 arms it never showed its verdicts: its charts
  took the least and greatest of 400,000 values with `Math.min(...values)`, which overflows the call stack. Past
  500 items a run its charts now draw shaded bins instead of a dot each (they were 1.2 million dots), and its
  per-item table draws only the rows it shows (10, then more on request; "show all" up to 1,000 items), where it
  drew all of them and hid the rest (3.2 million elements). Found measuring S3 in a browser.
- **The catalog's pages are the same whatever the process's hash seed.** The arms page's per-config rows came out in
  another order every build, and on the models page a model's best rank, when two of its configs tied, could come
  from either: both iterated a set. Found comparing two builds of one project; a test now builds under six seeds.
- **A goal's dataset notes with a comma were cut short.** `notes: first 200 test rows, all CNN; ...` inside a
  `{...}` entry is YAML for `notes: first 200 test rows` and a stray key; seven goals (the tutorial's among them)
  showed half a note on their pages. The notes are quoted, and the goal schema now refuses a key a dataset entry
  does not have (`validate` V14 names it). Found by the data page's round trip.
- **A release cuts a hidden dataset's judged and re-scored runs too.** A run scored under the label `judged/<scorer>`
  or `rescored <id>` on a hidden dataset was copied whole, its rows' `_meta` (which a judging carries over from the
  source row) included. Each run is decided by its own dataset. This repository has no hidden dataset, so its
  published catalog never carried any.
- **`evh <command> --help` names the command.** 43 of the 67 commands printed the script behind them
  (`evh run-promote --help` said `usage: promote_baseline.py`).
- **`evh validate` survives a file that does not parse.** A dataset, run, baseline or capture that is not valid
  JSON is named by V1, and every later check runs; before, the first check to read it ended `validate` in a
  traceback. A reference manifest, capture record or label set that does not parse is named by its own check.
- **A cancelled MCP call stops its command.** The server waited for the command to finish, so a call a client
  gave up on kept running to its timeout and held one of the server's slots.

- **SQLite: `data-ls` and `data-show` list a run's `outputs.jsonl`, `predictions.jsonl` and a pass's
  `rows.partial.jsonl`**, kept as tables, as the files store lists them.
- **A study's records no longer make the tree dirty**: `data/studies/` is exempt like the rounds, so a study's trial
  runs are not marked dirty by the study writing its own state.
- **The Workbench at 390 px and on an empty project**: the eval screen's charts no longer scroll the page sideways;
  a chart or file with nothing yet logs no console error; Home shows its commands; the open-round form is on the last
  round's tab only.
- **p and scores print the same way everywhere**: `round-evidence`, `evh baselines` and the records views print p to
  four decimals and scores rounded, as every other command.
- **`jobs-start` says a spending job's cap must be above 0**, rather than calling `--max-cost-usd 0` missing.
- **The docs name no removed variable or folder of runs**: `EVAL_RUNS_DIR` and the `data/runs-*` folders format 4
  removed (their meaning is a run's label now: `silver`, `judged/<scorer>`) were still in the README, the RUNBOOK,
  CONCEPTS, REFERENCE, tutorials 3, 4 and 6, the summarisation example and the Makefile's help;
  `tests/check_commands.py` now refuses both. `make rescore` no longer passes `--out`, which `evh rescore` does not
  have.
- **The test suite leaves no temporary folders**: 16 test files left 1,485 under the machine's shared `/tmp`.
- **An empty reply at `max_tokens` says why, and `label-from-run` says what to do about it**: `evh run`'s and `evh
  rescore`'s warnings name the empty items ("the token budget was spent before any answer, on reasoning, say"), one
  sentence shared by `run`, `rescore` and `label-from-run`, whose refusal of an empty output ends, as the warnings do,
  with "Raise max_tokens in the system (a new system id) and run it again".
  The inspector's item view marks a reply the run recorded as stopped at `max_tokens` ("output cut off at max_tokens,
  empty reply") instead of showing `0.000` and nothing.
- **One fact, one format, in `spent` and `run-promote`**: the long `spent $X ($Y the provider's bill, $0.000000 the
  system's price table ...)` form printed when the run's recorded total (rounded to 8 places) differed from the summed
  bills by rounding; it prints only when the second figure shows at the printed precision. `run-promote`'s note on a
  run with repeats prints scores as `evh baselines` does (`0.000019 (mean of 3: 0.000019)`, not `1.9e-05 (mean of 3:
  1.86667e-05)`), and `study-confirm`'s validation delta is rounded like its test delta.
- **A judged leaderboard fits both judges in 100 columns**: when the `_unvalidated` ending keeps columns out, it drops to a
  second header line; the table says its `runs` is the latest run of an arm (judging does not average repeats).
- **`dataset-show` no longer ends "made from version of briefs_v1"**: it says "made from briefs_v1" (as does the
  catalog page's "From briefs_v1."). The version number was right (a removed item makes a new major, 2.0; an added-only
  version is 1.1, as tutorial 4 shows).
- **`evh looks` prints one row for one look**: `study-confirm` writes two records of its look (named before the runs, the
  verdict after); the row says "(2 records of this look ...)" instead of two rows numbered 1 under a header of 1 look.
- **The Workbench's "Open the next round" offers only arms it can carry**: the list follows the "On" dataset and names
  each arm left out ("not offered: no run on <dataset>"), where it offered every arm in play of the last round whatever
  the dataset and failed on opening ("no run of it on briefs_v1 to carry in"). A round a study opened says "opened by
  study <id>" on its tab.
- **"The held-out test" lists a `role: test` dataset that is not sealed**, as `evh looks` and the Studies screen do: its
  seal state ("not sealed: role test"), its looks, and **Seal it** (the split again by its recorded rule, with `--seal`).
  It said "None of this goal's datasets is held out yet" after a split made without `--seal` and a confirmation.
- **"See the cost first" links the smoke**: an arm with no arm-smoke gets a link to "Check it on three items" on "Choose
  the systems" beside the dry run's "no arm-smoke of it is recorded".
- **A job started through the API records `from: api`** on the records it writes (the name typed in a call), not
  `from: environment`, which said the name came from the server's environment. A job started by `evh jobs-start` records
  what that command resolved (`flag`, `environment` or `terminal`), never `api`.
- **`evh dataset-split --force` refuses a side a run cites**, as its help says ("if nothing cites them yet"); it
  overwrote them whatever ran on them (`would-overwrite`, naming the side and its runs).
- **The held-out screen shows one row per look**: a look `study-confirm` wrote two records of is one row, "(2 records of
  this look, the last <time>)", as `evh looks` says it.
- **Home and `evh goal-status` no longer ask for a baseline on a `validation` or `test` dataset**: a study's validation
  side can never get one (a study never promotes).
- **Charts name the arms they leave out, and keep what tells two apart**: `chart intervals` (the command and the
  Workbench) says "Left out: <arm> (retired in rN)" instead of dropping a retired arm silently; a long row label is
  shortened in the middle (`briefs_…al_small_v1 ×3`, not `efs_mistral_small_…`), so v1 and v2 can be told apart.
- **The Workbench at 390 px**: "The evidence" no longer runs under the chart's title, and a chart wider than the screen
  shows an edge shadow where it scrolls in its own box (the item heat map was read as cut off).
- **"A judge for this goal" no longer names a tool the install lacks**: it says a validation is an ordinary eval whose
  arms are the judges (`evh run`), named in the scorer's `validation` block, instead of `tools/validate_judge_*.py`.
- **A judged leaderboard's `runs` says `1/3` for an arm with repeats**, not a bare 1: judging scores the latest run of an
  arm (its repeats are not averaged), and the column now reads the judged run out of the arm's runs on the dataset. The
  note under the table says so. (The two judges' columns did fit 100 columns on the newcomer's own project, 6d3f90984's
  fix; the bare `1` was what it kept reading as wrong.)
- **`round-open` says what `code` is**: "(code 5be806915132, a hash of the harness code that can change a measurement,
  not your project's commit)", and tutorial 4 says it where the command is first run.
- **A dataset's version number is explained where tutorial 4 shows it**: adding items only is `v1.1`, removing or
  changing any is `v2.0` (RUNBOOK §2, `_dataset_version.py`); `dataset-show` was right, the tutorial showed one case.
- **`evh chart trend` with one point says why**: how many baseline versions there are and how many closed rounds promoted a
  run (a round that kept the baseline adds no point).
- **`dataset-split --test` says its share is approximate** (tutorial 6, RUNBOOK's command table, the command's docstring): each
  item's hash picks its side on its own, so `--test 0.4` on 20 items can give 10 and 10.
- **The inspector's `item=ITEM_ID` parameter is in RUNBOOK §14** (it was in tutorial 5 only), and SCENARIO step 15 names it.
- **`evh env-check` prints the retry count the harness uses**: `EVAL_MAX_RETRIES` showed a default of 3 where the retry
  core makes 8 attempts. Both read one constant (`_retry.DEFAULT_MAX_RETRIES`, `DEFAULT_RETRY_MAX_DELAY`).
- **INTEGRATION says what a project adapter's cost is**: the harness never prices a custom adapter's tokens (the price
  table is applied by the bundled providers and the dry run's estimate), so an adapter that returns tokens and no
  `cost_usd` records no cost and counts nothing against `EVAL_MAX_COST_USD`. The page said the table applied.
- **`spent` says "the system's price table" only where the table was applied**: `evh run` and `evh arm-smoke` called a
  project adapter's own `cost_usd` the price table's whenever the system declared prices (it declares them for the dry
  run's estimate). The bundled adapter now marks a call it priced from the table (`meta.cost_basis`), and the label
  follows the mark; any other figure is "the adapter's own figure".
- **A judged leaderboard keeps every judge's column on a narrow terminal**: below about 70 columns it kept the ranking
  metric alone and dropped the judges; it now drops cost, speed and tokens first (the judges are the ranking's evidence).
- **SCENARIO step 9 gives the round-2 prompt's full text**, which asks for plain text (no quotes, no heading or label, no
  markdown): the replies came back wrapped in quotes or starting with "**Summary:**", which lowers the ROUGE-style score.
- **`evh dataset-create` without `--source-dir` reads `data/sources/<dataset id>`**, as its `--help`, the API's schema and
  RUNBOOK §2 say; it read `data/sources` itself and failed "no items matched" for a project that keeps one folder per
  dataset. A `--manifest` keeps `data/sources` as the base of its `source_path`s.

## 0.7.2 — 2026-11-04

The public MCP server's answers written ahead were empty. From 0.6.2 to 0.7.1 its `goals`, `datasets`, `arms`,
`models`, `references` and `runs-list` answered as if the project held nothing, and 0.7.1's leaderboards written
ahead were never written. A project's own server (`evh mcp` without `--answers`) and every command were not
affected. No result moves.

### Fixed

- **Answers written ahead are answered from the project's data.** `evh mcp --write-answers` runs each command
  inside the project; the deployment passed `EVAL_HOME` as a relative path (`_release/inspector`), which each
  command read from inside the project, where there is no such folder. A relative `EVAL_HOME` or `EVH_P_CACHE` is
  now made absolute from where the caller stands before the command runs.
- **A broken write is no longer silent.** `--write-answers` names what it could not write (a dataset with no runs,
  an answer too large, or a call that failed with its error) and exits non-zero when a call failed; the
  deployment's render also refuses answers whose `goals` do not list the release's goals, or that hold no
  leaderboard.

## 0.7.1 — 2026-11-04

Fixes from the fifth newcomer scenario (the first on a release, 0.7.0) and from releasing 0.7.0. A judge that
returns empty replies no longer leaves a tree that fails `evh validate`; the commands say more about what they
did and what they spent; the public MCP server answers a leaderboard at once. No committed run's scores move;
three figures read differently (**Changed**).

### Changed

- **`family-test --round` tests the round's leader against every other arm in play**, without `--a` and
  `--against` (as `pair-test --round` picks its pair), and reads a re-score in place of the run it re-read, as the
  round does. A family test of a round can give a different p than 0.7.0's runs-only read.
- **The billed figure counts arm smokes.** `evh overview`'s billed tile and the catalog's include what
  `evh arm-smoke` spent (recorded in the model records), and the spend lists name it as "arm smokes".
- **`runs-list --baselines` shows the baseline's mean over its repeats**, as every other view does; `--json`
  `scores` is that mean and a `repeats` column says over how many.
- **`--json` fields:** the leaderboard's frontier gains `dominated_by`; `evh goals --goal`'s last column is named
  `decision` (it was `""`); the dry run gains `input_tokens_counts`; `arm-smoke` has `--json`.

### Fixed

- **An empty judge reply is withheld like any other unparsed reply.** A reasoning judge that spent its whole
  `max_tokens` thinking returned nothing; `judge-score` stored it as text and `evh validate`'s V12 then failed on
  the harness's own record. Now it is withheld (its hash kept), V12 names the command that rewrites one stored
  before 0.7.1 (`evh judge-score … --retry-unparsed`), each unparsed reply says why (empty, cut off at the token
  limit, not JSON, not the expected shape), a pass whose replies were cut off ends with a `HINT` (raise
  `max_tokens`, or `reasoning: {enabled: false}`), and its progress lines arrive as they happen through a pipe.
- **`evh arm-smoke`** prints each reply (its first 300 characters; `--replies` for all) and what it spent, and
  times a call that the adapter did not time.
- **`evh run`** says whether "spent" is the provider's bill or the config's price table, prints no "warmed up in
  0ms" for an arm with nothing to load, and counts the config's prompt in the dry run's input estimate.
- **`rescore`** ends with a whole sentence that says when a re-score stands in for a run, and warns about outputs
  cut off at `max_tokens`. **`score-preview`** says when a goal holds no measured run to re-score.
- **`silver-calibrate`** says what `--ref-match` and `--arm-match` take, with an example from your runs.
- **Leaderboards fit the terminal** (the ranking metric first, the rest named; `--wide` for every column), and
  "dominated" says what it means (as good on all three, better on at least one) and by which arm.
- **`inspect`** shows a model name whole in its conditions, and `--round` names the round's leader as such;
  **`evh goals --goal`**'s headers line up; **`cost-report`** names each repeat; **`evh rounds`** prints a round's
  conclusion whole.
- **The catalog and the inspector:** the inspector names the silver reference's author and marks its row; an
  item's cards show each arm's score; a goal page's "test every arm against its leader" leaves out retired arms;
  a judged group below the goal's `min_items` says so; a recommended dataset id may break, so the goals table
  fits; home tiles keep their number on one line at 1400 px.
- **The public MCP server answers `leaderboard` for each dataset at once:** `evh mcp --write-answers` writes it
  ahead per dataset, and the leaderboard's permutation test is kept in the p cache (`EVH_P_CACHE`) with the
  generator state the rank intervals draw on, so every number is the same. A first call took 47-60 s.
- **The website's on-this-page line** names each section in a word or two and leaves out "Who built this".
- **Deploys and CI:** the release renders while CI runs, and the site's build check runs beside `verify`.
- **Docs:** tutorial 3 shows the whole judge scorer and what to do when a reasoning judge returns nothing;
  tutorial 5 lists the inspector's URL parameters; the RUNBOOK has a complete goal file; the newcomer scenario
  smokes each arm first, says what each step writes (all committed), and seeds pip in a `uv venv`.

## 0.7.0 — 2026-11-04

Agents as users. `evh init` writes an `AGENTS.md`, three skills teach the loop, and the ranking and the tests answer
in `--json`, so an agent with a shell needs neither the catalog nor MCP. The features and fixes the first beta
agents asked for are in, among them crosstabs of per-item scores, a hypothesis recorded before a run, `pair-test`
across two versions of a dataset, and `capture-restore`. Upgrading can change a verdict: a leader the tool picked
is now corrected for the pick, and a round no longer promotes on a tie (**Changed**). No committed run's scores or
fingerprint move.

### Changed

- **A leader the tool picked is corrected for the pick.** `pair-test --round` takes A from the table, so its p is
  Bonferroni-corrected for the comparisons A could have been (every arm in play but B); a round's promotion gate
  corrects the same way (p × K over the round's arms). A verdict that was significant uncorrected can read
  not significant. A pair you name yourself is unchanged, and still uncorrected.
- **A round promotes nothing when its leader is tied, or its arms were scored differently.** Before, it promoted
  the first of the tied arms. The hold names the arms and says how to break the tie (the goal's tie-break picks
  among them; `evh goals --goal` names the arm it recommends). A closed round suggests nothing.
- **A round's baseline is read re-scored.** It was read as first scored, so the rule "a leader must beat the
  baseline" did not run on re-scored rounds; it does now, and can hold a promotion it let through.
- **The leaderboard's JSON lists no distinguishable pairs without an arm effect.** Pairs are read only after the
  global (Friedman) test finds one: without it, `pairwise_valid` is false and `distinguishable_pairs` is empty.
- **`dataset-from-capture --from` replaces an item with the capture's record of the same id**, counted as changed
  in the lineage. Before, the earlier version's body was kept and the lineage read "0 changed". **`--fieldset`
  alone keeps every field it declares**; before, it kept none without `--field`.
- **A run is never written into another run's directory.** A run id is the config and the start time to the
  second, so two runs of one config started in the same second shared a directory and the second wrote over the
  first, a committed run included. The second now takes the next second's id; `--run-id` naming an existing run
  is refused.
- **`evh run --dry-run` no longer calls its estimate an upper bound.** It counts one call per item, or an adapter's
  `CALLS_PER_ITEM`, and says more calls or a growing conversation cost more. Where the model record has an
  arm-smoke of the config, it shows the measured cost per item projected over the run. `--json` adds
  `estimate_is_upper_bound: false`, `calls_per_item` and `measured_usd_per_item`.

### Added

- **`AGENTS.md` (and `CLAUDE.md` importing it) in every new project** from `evh init`: the rules an agent must not
  break, the loop from nothing to a decision, the `--json` command for each question, and what an agent may do
  (run arms, label and promote when its operator asked, under `EVAL_MAX_COST_USD`; closing a round stays the
  operator's).
- **Three skills, and `evh skills-install`**: `evh-evaluate-a-system`, `evh-compare-and-read` and
  `evh-promote-with-evidence`, shipped with the package and copied into `.claude/skills/` (or `--target`). Every
  `evh` block in them runs as written in the tests.
- **`--json` on `leaderboard`, `pair-test`, `family-test`, `run-compare`, `rank-stability`, `runs-list` and
  `rounds`**: one envelope, `{"command", "version", "result": {"blocks", "values"}}`, with raw numbers. The text
  output is unchanged. `evh run` prints each run id it wrote (`values.runs` under `--json`), and its progress as
  one `[n/N] item outcome seconds` line per item while it runs (on stderr under `--json`).
- **Five more MCP tools**: `leaderboard`, `pair-test`, `family-test`, `rank-stability` and `run-compare` (23 tools,
  22 with `--public`).
- **A hypothesis recorded before the run** ([ADR-0025](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0025-a-hypothesis-lives-in-the-arm-config.md)):
  a `hypothesis:` block in an arm config (which way, against which arm, on which measure) is recorded in each run
  with whether it was committed before the run. `pair-test` and `evh goals --goal` show it; an arm with runs made
  before it reads "not named in advance". `evh validate` V20 checks it. Not in the fingerprint.
- **`evh inspect --runs … --crosstab A,B [--group FIELD [--group-match RE]]`**: two per-item scores crossed, per
  value of a field of the run's prediction rows, the items off the diagonal named. **`--items-out`**: each run's
  whole output and scores beside the reference and labels (`--disagree`: only the items the runs decided
  differently).
- **`evh goals --goal G --arms PATTERNS --top N`**: the rows shown filtered; the decision is still made over every
  arm, and the baseline, the leader and the recommended arm are always shown. Each row has its paired test
  against the leader.
- **`pair-test --b-dataset D2`**: one arm on two versions of a dataset, paired by item id. Refused unless the
  reference is the same text for each shared item; it says it is cross-version, what that establishes and what
  not, and names the runs of each side (`run_ids_a`, `run_ids_b`).
- **`evh capture-restore --capture C [--query KEY=VALUE]`**: a capture's records, and the item files of every
  dataset made from it, read again from the recorded importer and query (a key replaced, e.g. the same files in a
  download folder), a recorded scrubber run again; every record and item must match its recorded sha256, or
  nothing is written.

- **The triage example's v2** (`orrery_triage_v1_labelled_v2`): the same 65 owner-labelled decisions with the
  rebuild's hindsight taken out (probe answers that stated an outcome, release and last-seen times after the
  decision), as revision `v2` of the dataset on Hugging Face; `examples/triage-fleet/fetch.py --revision v2`
  restores it. Round r4 of `triage_orrery` runs on it.

### Fixed

- **An importer path in a capture works from the project root** as well as from the directory it was given in.
- **The triage example's fetch restores its capture again**: the importer's newer fields come only when the query
  asks (`prompt_fields`, `v2_fields`), so a past capture's records hash as recorded.
- **`evh inspect --items` is no longer read as `--items-out`**, and `--crosstab` refuses a name that is not a
  per-item score, pointing at `--group`.
- **A label set is written whole or not at all**: to a temporary folder renamed into place.
- **`pair-test --b-dataset`** refuses a measure stored only in re-scored runs as a missing metric (naming
  `evh rescore`), not as "no shared items".
- `family-test --against` takes a list; `--family` below 1 is refused; a mixed family's `n` is its range; a goal's
  `--goal` cannot name a file outside `data/rounds`; `round-open --keep`'s help says it accepts any arm already run.

## 0.6.2 — 2026-11-03

Faster answers from `evh` and its MCP server. No result moves.

### Added

- **`evh mcp --write-answers FILE` and `evh mcp --public --answers FILE`: a release's answers written ahead.** Each
  call to the MCP server runs a fresh `evh` process, several seconds of CPU; a deployment that limits the server's CPU
  pays it in tens of seconds (the evals server's first `goals` after each start, and after each hour, took 33 s at
  half a core). `--write-answers` writes the answer of every tool that takes no argument and does not depend on the
  date (not `overview` or `activity`); a public server started with `--answers` serves them without running the
  command, for as long as it runs. A line another harness version wrote is not read.

### Fixed

- **A view and a catalog build read each arm's scores once.** `evh goals` read 1,054 arms' scores for 686 arms; that
  reading was 79% of its CPU. The answers are byte for byte the same; `goals`, `arms` and `models` take about a
  quarter to a third less CPU.

## 0.6.1 — 2026-11-03

Fixes to 0.6.0, from two reviews of what it shows. Six can move a number or a verdict a project sees (Changed): the
sheet's win rates and verdicts, a goal's recommendation and the places in its field, and the catalog's run and
spend figures. One keeps a hidden dataset's labels and notes off public surfaces (Security). The rest restore what
0.6.0 documented or make the catalog say what a number means beside it (Fixed).

### Changed

- **A goal recommends from the group it decides on, once per dataset.** A judged group (a grade, a pick, a pairwise
  pass) or another measure of a scorer is shown with its leader, never recommended: 0.6.0's CNN goal page printed
  four "Recommended:" verdicts, three of them from judging passes the goal does not decide on.
- **A goal's field places one arm per config, without the arms a round retired** (a re-timing, a second run, a
  paired side run). A config run twice took two places: AG News `anthropic_l` read "#8 of 33" in the catalog where
  the site reads 5th of 30, and the Models page put Gemma 4 31B first on SummEval through its paired side run.
- **Runs re-scored or re-parsed in place count in every period figure**, dated when they were measured: 0.6.0 left
  Few-NERD's and SciFact's 54 runs and $5.58 out of the activity, the datasets page and the home tiles. A copied
  re-score (judged, re-scored, silver, adjudicated) keeps its run's id too and is still never counted.
- **The sheet's verdict compares only the arms scored on the metric**: an arm with no score on it reads "no <metric>
  in this run", where 0.6.0 named the other arm the leader and recommended.

- **The sheet's win rate on a pick or pairwise verdict is each arm's share of what the judge gave** over the rows it
  judged (its `judge_won`), so with every arm shown it is the judging pass's own win rate. 0.6.0 gave a shown arm a
  whole row when it held the largest share among the arms shown, however small: on the CNN pick pass `anthropic_l`
  read 0.646 in the sheet against the pass's 0.402.
- **The sheet's win rate on a metric is over the rows each arm was scored on**, "—" for an arm scored on none. 0.6.0
  divided by every row with a winner, so an arm with no value on a row counted as beaten there, and one never scored
  read 0.000.

### Security

- **A hidden dataset's labels and notes stay off public surfaces** (RFC-019 §4: per-item labels, adjudication notes).
  0.6.0 showed its label sets' confusion matrices, whose rows and columns are the label values, on the catalog's
  dataset page and in a public server's `labels`; listed a person's sheet notes on its items in a public server's
  `labels`; and copied those notes into a deployment's data. The counts, Cohen's kappa and Krippendorff's alpha stay.

### Fixed

- **The installed `evh` reads the project's `.env`.** 0.6.0's `evh`, as pip installs it, loaded none (`env-check`:
  "loaded 0 var(s)"), so a key or a cost cap put there was not in force; `python -m evaluation_harness` and a
  checkout were unaffected. Found by the newcomer scenario.
- **`reference-promote` adopting a hand-made folder keeps its files' bytes.** It added a newline to each, so the
  reference digest every run scored against the folder had recorded no longer matched (`rescore` warned the
  reference had changed), where UPGRADING said no run's reference moves.
- **Fetching the examples' public data falls back to the Hub's parquet files** when the Hugging Face
  datasets-server's `/rows` keeps failing (its outage of 2026-11-02 answered HTTP 503 for every dataset): the same
  rows and row numbers, read with `pyarrow`, now in each example's environment; every item is still checked against
  the frozen dataset. The installed harness does not depend on it.
- **`inspect --sheet --wrong-against NAME` refuses a name two datasets' sets share** on this dataset's items (labels
  follow an item into every dataset holding it), naming each as DATASET/SET; it read whichever it found first.
- **A round's best is read as its goal decides**: on the deciding reference, never the arm that wrote it (CNN round
  r1's best read `anthropic_l` 1.000, the silver's author scored against itself, beside a conclusion naming `bart_l`).
- **Gold reference sets are dated by when their labels came to be**: the dataset's freeze, or the adjudication. The
  0.4.0 migration had stamped every one with its own time, so the references page listed sets a month old as new.
  No run's reference digest moves (the digest leaves the date out).
- **`evh deploy-sheet` and the goal page say a key production never recorded "cannot be checked"**, where they read
  "prompt_sha 0 match; not recorded: 233".
- **The catalog says each thing once, and what a number means beside it.** A goal page names a re-score's scorer
  once, counts a long list of contenders, folds a conclusion its answer already shows, and explains its groups and
  strategy once. Dataset pages open on the deciding measure, give one inspect button per judging pass, name the
  machine in one form ("served on", "run on"), say how much of a period's spend was judging, and show a rise past
  doubling as a multiple. The answer column no longer scrolls off at 1280 px; chart names never overlap; a cost every
  arm shares draws no axis; a metric's strip leaves out the arm scored against what it wrote; ids break between
  words at phone width; the sheet's rows stay short and name arms by what sets them apart; probes read yes or no.
  The triage datasets and `fleet_dedup_v1` have their profiles (`evh dataset-profile`).
- Site: SciFact leads with the compared field (the best reranker +0.025, not significant) and names the extra
  +0.07 run with its caveats; the method page describes fingerprint v5 with 0.6.0's own `run-compare` output; the
  use page counts its steps; the XSum control's caveat and the judging spend's passes are carried where they are
  quoted.
- Docs: tutorial 5 and the RUNBOOK named the old fixed ports (8765, 8766) where 0.6.0 gives each project its own;
  the home page's MCP section names what 0.6.0 added and that the public server never answers with an item's text.

## 0.6.0 — 2026-11-02

What you get: datasets made from what production did (capture, scrub, split, `dataset-from-capture`); labels that say
who decided what is right, and reference sets promoted from them; production's own decisions scored as an arm;
models onboarded before they are run; scoring that evolves without re-running an arm; judges that grade, pick the
best or compare two; and one sheet of every item and arm, filled in Excel or another tool and read back. Upgrading
moves no committed score. Two formats (fingerprint v5, model records) and the old references are migrated by a
command, and a few names change to the field's words with no alias (`evh run`, `significant`, `contenders`):
[UPGRADING](https://github.com/chipi/eval-harness/blob/main/harness/docs/UPGRADING.md) has the steps.

### Added

- **Labels, and the reference sets promoted from them** (RFC-023, PRD-002, ADR-0022). A **label** says what is right
  for one item and who said it: a `person`, a `model` or a `rule`. Labels come in **sets**, never edited, under
  `data/labels/<dataset>/<set>/`, and follow an item by its sha256 into any dataset holding the same bytes.
  - **`evh label-from-run`**: a finished run's outputs as a model's labels, no calls, the refusals a reference's
    provenance needs (a dirty or unknown build, an unfinished or derived run, an empty output, one cut off at
    `max_tokens` unless `--allow-cut-off`). **`--not-redistributed`** keeps the texts out of git (a `.gitignore` beside
    them) and records the command that rebuilds them, checked against the set's checksums.
  - **`evh label-sheet`** writes a sheet of the items to label (unlabelled, all, where runs disagree, or chosen),
    each run's decision and a proposal beside an empty label; **`evh label-import`** reads it back, or a folder of
    `<item_id>.txt`, as a person's set (`yes` takes the proposal; notes kept). The sheet is CSV that Excel opens
    and saves (UTF-8 with its mark, `,` or `;`); **`--choices`** puts the allowed answers in the label column's
    header and the import refuses any other; the local inspector downloads it. **`evh label-from-capture`** turns a
    capture's recorded outcomes into a `rule` set by the rules `reference-from-outcomes` read. **`evh labels`** lists
    the sets, what each covers and how two agree: the same answers, sharing one, Cohen's kappa, Krippendorff's
    alpha and (`--confusion`) the confusion matrix; free-text labels are not compared as text (an MCP tool).
    **V19** checks every set.
  - **A label can accept more than one answer**, when several are right for an item: `{"accept": ["escalate",
    "file"]}`, sorted and without repeats, made by the sheet's `also right` column, a rule's `label: [file,
    escalate]` or a folder's text, shown "escalate or file". A decision is wrong against a label when it is none of
    them; two labels agree only when they accept the same answers. An adapter's `score` reads a reference with
    **`answers(reference)`** (`evaluation_harness.adapter`); the bundled one keeps the best overlap. The triage gold's
    23 `file-or-escalate` labels (and their reference) are written so now, by `labels_from_verdicts.py` byte for byte:
    every one of the 18,460 item scores of the 284 runs against it is the same replayed old and new. The outcome
    rules give the same two answers, so gold and the rules accept the same answers on 34 of the 34 items both label
    (kappa 1.00).
  - **`evh reference-promote`** makes a reference set of a label set, at the tier you choose, with a reason and who promoted
    it; the manifest records where it came from (for a model's set, the run and model that wrote it). No rule ties
    the tier to the source. Every existing reference set records how it was promoted (20 here; 6 copied byte for byte
    into label sets, 209 labels), every run's fingerprint unchanged.
  - **Scoring against a label set without promoting it**: `evh rescore --labels SET`, `evh run --labels
    SET`. The run records `reference_id: labels/<dataset>/<set>` and lands in `data/runs-labels-<dataset>-<set>/`, an
    arm of its own; a goal groups such arms under the set, the arm that made a model's labels flagged.
  - The catalog: a tier is a **pill** in its own colour, a label set a **source chip**, wherever either is named; a
    **Labels** page; a dataset's label sets and how often two agree; where each reference set was promoted from.
- **Evaluating what production did** (RFC-023, PRD-014, ADR-0023). A capture's decisions are evaluated against
  labels; the governed datasets grow only by a version you make:
  - **`evh arm-from-capture`** makes production's recorded decisions an arm (`provider: recorded`): each output the
    capture's record of the same id, read by the adapter's **`recorded_output(record)`** (else `--field`), scored,
    tested and compared like any arm, cost 0. The catalog badges it `recorded`, its cost and speed "recorded, no
    call".
  - **Agreement**: the adapter's **`same(a, b)`** says when two outputs are one decision (default: the same text;
    the triage adapter compares dispositions). **`evh inspect --disagree`** and the inspector's "only where they
    disagree" keep the items where the arms decided differently; `label-sheet --items disagree` reads the same hook.
  - **The sheet**, `evh inspect --sheet --dataset-id D --runs A,B,…` and the inspector's **05 sheet** (the dataset
    page's "Open its sheet"): the items down, a column per arm across with what it wrote and every score it has
    (its run's metrics, and a judging pass's where one covered the run; `--metric M` or `SCORER/M` chooses the one it
    is read on; `--scores-only` leaves the outputs out), every label set and reference set, the winner per item (on
    that metric, and per pick or pairwise judge), the signals **wrong** (`--wrong-against SET`), **disagree**,
    **split**, **new** (`--new-vs D`: a field value it never had), **unlabelled**, each a filter beside `--where` and
    `--by`, and a footer per arm: its mean, its win rate and its verdict (the goal's decision, else the paired test
    against the leader). On a pick or pairwise verdict only an arm the judge preferred wins a row; a row it gave to
    an arm not shown is nobody's win. The item column stays in place as the arms scroll; the rows you tick give the `evh pick`
    and `evh label-sheet` commands. `--csv FILE` writes it (UTF-8 with the mark Excel needs), and the inspector
    downloads the same (`/api/sheet`, `&format=csv`). Local only: a public server refuses it.
  - **A sheet to fill, and `evh sheet-import`** (`make sheet-import`): `--csv FILE --fill label` adds `label`, `also
    right` and `note` (`--choices`); `--fill pick` or `scores` writes the outputs as blind columns A, B, C… shuffled
    per row (`--seed`), a `pick` or a `score: X` column per output (`--scale LO..HI`), the rubric as the first row
    (`#rubric`; `--rubric FILE`) and its key beside the sheet (`sheet.key.json`). `evh sheet-import FILE --dataset-id
    D --by WHO` reads back what was filled: labels as a label set (`--set`, `--kind person|model`), picks or scores
    as judged runs under `data/runs-judged/<scorer>/` (`--scorer`), `judge_won_unvalidated` or
    `judge_score_unvalidated` per arm per item, through the key. A row or text the key does not have, a letter not on
    its row, a score off the scale and a name already used are refused, with nothing written.
  - **Picks**: `evh pick` marks a production item for the next version of one or more governed datasets (targets,
    tags, a note) in `data/picks.jsonl`, append-only; **`evh picks`** lists what waits (an MCP tool), and the target
    dataset's page shows them with a box per row. **`evh dataset-extend V1 --dataset-id V2 --picks`** (or `--pick`)
    makes V2 of V1's items and the picks chosen, each checked against the bytes picked, `extended_from` recorded;
    labels follow the items; nothing is promoted.
  - **`evh deploy-sheet --config ARM [--capture C]`**: what production must match to run what you promoted (the
    model, its record and deployment, every setting sent and a record's setting that was not, what each item
    reported, the adapter), and with a capture, whether each record says production ran it (the adapter's
    **`production_ran(record)`**); exit 1 unless every record matches. On the promoted arm's page, and folded beside a
    goal's baseline. The triage importer keeps the ledger's `prompt_ver` and `prompt_sha`.
- **Several projects on one machine** (ADR-0024): `catalog-serve` and `mcp --http` take a port of the project's own
  (18000–18999, 19000–19999), the same every time, the next free one if taken; a local catalog names its project;
  every command notes a stray `EVAL_HOME`; a model record's lock is keyed by the record.
- **Datasets from production: the capture lane** (RFC-019, PRD-014, ADR-0019). A project keeps what a
  production system did as a **capture**, then makes datasets and labels from it:
  - **`evh capture`** reads records through an **importer** (`--importer jsonl|tsv|github|langfuse`, or a
    project's own `path.py:Class`) into `data/captures/<id>/`: each record's id, body, fields, time, source
    and outcome, hashed one by one (`capture.json`); `--since-capture` continues from an earlier capture.
    **`evh importer-check`** tests an importer against the contract, including that it keeps to `since` and
    `until`; **`evh captures`** lists them, and the catalog's **Captures** page shows them with the datasets made
    from each. A capture keeps the window it records: a record outside it is named and nothing is written
    (`--late` keeps the ones older than `since` that the earlier capture never saw). Newer outcomes of the same
    records are a fresh capture, labelled with `label-from-capture --capture` (tutorial 6 §5).
  - **`evh capture-scrub`** runs a project's own scrubber over a capture's records and re-hashes the ones
    it changed, keeping their earlier hashes.
  - **`evh capture --sample-rate R --seed S`** keeps a share of the records, by a hash of each id, as they are
    read: the same rule draws the same records again, an importer may sample at the source, and a continued
    capture keeps the rule.
  - **`evh dataset-from-capture`** freezes a selection (`--where`, `--dedup`, `--one-per`),
    typed fields from a field set, and `--tag K=V` labels; only the body becomes the item.
  - What happened afterwards becomes labels by a small rule set (`when`, `unless`, `exists`, `absent`, `range`,
    `min_age_days`): `evh label-from-capture`, above.
  - **`evh dataset-split`** makes `<D>_validation` and `<D>_test` by hash (stable across versions, a group
    kept whole with `--key`) or by time.
  - **V17** checks every capture's records against their hashes; a capture whose records a project keeps
    out of git (fetched from where it publishes them) is named as not fetched, not failed.
- **`text: hidden` on a dataset**: none of its text, nor anything derived from it, on any public surface:
  the catalog's pages, the inspector and `evh mcp` in public mode, and a deployment's copy of the data
  (`_release.py copy-data`, which also refuses a release carrying reference texts or run outputs git does
  not track). `dataset-from-capture --hide-text` sets it.
- **Dataset tags on the views**: the catalog's datasets page groups by each tag key and shows where a
  dataset came from (a capture and its selection); **`evh datasets --tag K=V`** filters the same way.
- **Two examples from a production fleet**: `examples/triage-fleet/` (an agent's real triage decisions,
  replayed through its own code; the operator's verdicts as gold; the model's own decision scored beside
  the fleet's, before and after its gates) and `examples/signal-fleet-dedup/` (a regression guard for the
  fleet's de-duplication functions; no model). Their data is published on Hugging Face and fetched by a
  pinned revision.
- **A share card on every catalog page**: its title and its opening line as `description`, `og:*` and
  `twitter:card`, and with **`evh catalog --card URL`** the image a shared link shows. The pages stay
  `noindex`.
- **Onboarding models, once, for every eval** (RFC-020). A project keeps a **model record** per model,
  `data/models/<model_id>.yaml`: its aliases, weights and licence, what it can do, the settings that hold
  whatever the task (`reasoning_effort`; device, precision, batch size for an ML model) with why, its history,
  and its **deployments** (each place and build it runs: machine or host, server and version, digest, revision
  or hash, the route for a hosted one), each onboarded on its own.
  - **`evh model-onboard <id> --deployment <d>`** probes an LLM through the deployment's endpoint: the digest the
    server reports, whether it reasons at the default and with the record's settings, JSON, determinism and
    speed (the deployment's, not the record's); a different build than the record's is flagged and kept in its
    history. An ML model or a baseline through an arm (`--config`). `ONBOARD PASS` or `ONBOARD CHECK`.
  - **`evh arm-smoke --config <arm>`** runs any arm on a few items before its full run and writes no run: runs,
    valid output for the scorer, a projection of the full run's time and cost, build pinned, determinism; for an
    LLM every model call (reasoning, slow, long, cut off, no answer, from a provider's `_meta` or an adapter's
    `meta["calls"]`; a reply is long past half the arm's reply cap, or with no cap against the arm's own median,
    so neither a summarising arm nor an agent's short probe calls beside its answers make a long reply).
    `SMOKE PASS` or `SMOKE CHECK`, written into the record.
  - An arm names a record and a deployment (**`model_record:`**, **`deployment:`**): the record's settings go under
    its params, which add the task's own (its reply cap, its call limit: a record refuses them, since they would
    reach every other eval's arms); the run records both. **V18** checks the records, and the arm configs in `data/configs` and those validate.json's `configs` globs name; `validate` notes an arm never smoked, a
    reasoning model with no `max_tokens`, a tag that is a different build on two deployments.
  - The catalog's **Models** page and a page per model, a smoke badge on the arms page, a models tile; **`evh
    models`** for the same (and over `evh mcp`). A model is *vetted* when an arm that names it passed its smoke;
    its onboarding alone makes it *onboarded*.
- **Scoring that evolves** (RFC-022). A round records the scorer it is judged by, and a scoring change is a
  step of its own:
  - **`evh score-preview --goal G [--round rN]`** re-scores the goal's arms (or the round's) with the scorer in
    the working tree, in a temporary directory, and prints each arm before and after and the decision before
    and after; it writes nothing and spends nothing.
  - **`evh rescore --goal G --round rN --why "…"`** re-scores a round's arms; the round records the change
    (`scoring`: when, the scorer, why, where).
  - **`evh round-open --from rN --keep all --scoring "…"`** opens the next round judged by the current scorer:
    every carried arm another scorer judged is re-scored first ($0), each one's measure printed before and after.
  - Re-scores land in **one place the tool designates**, `data/runs-rescored/<scorer>/<source>/`, read by the
    catalog, the goals, the rounds and `validate`; `--out` still names any other. Rounds read an arm from its
    re-score as the goals do, and `evh rounds` and the goal page show a round's scorer and scoring changes.
  - **`evh round-open --adopt`** records a goal's first round from the arms already run for it.
  - A goal axis's **`limit: baseline`**: an arm is out when the paired test finds it worse than the group's
    baseline arm on that measure.
  - `validate` notes a round whose arms one adapter scored in more than one version.
  - `evh init`'s `.gitignore` ignores the throwaway `data/runs-smoke*/` and `data/runs-tune*/`.
- **`call_timeout_s`, an arm's call limit, for the built-in providers**: the SDK client's timeout (its own
  default is 10 minutes). The RUNBOOK told arms to set a call limit only the triage adapter honoured.
- **The triage example's adapter takes `reasoning_effort` and `max_tokens` per arm**, reports every model call
  for `arm-smoke`, and records a call that fails the same way twice at temperature 0 as the fleet's own "no
  terminal decision" (`no_decision`, `deferred`). With `reply_in_tool_call: <name>` it reads an answer a server
  returns as a tool call to that name, with no text: Ollama 0.40 does that to every gpt-oss answer, and the fleet,
  which reads only the text, got nothing.
- **No key for a local server**: the `openai` provider asks for no `OPENAI_API_KEY` when its address is on this
  machine (localhost, 127.x, ::1) or on Ollama's port, 11434; Ollama takes any key. Any other address still
  needs one, and a key that is set is used.
- **Tutorial 7, set up a model before you test it**: a model record, onboarding it where it runs, an arm that
  names it, a smoke before the full run; on your own machine with Ollama.
- **Judging modes** (RFC-005, PRD-003 FR5): a scorer's **`mode`** says what a judge is asked: `grade` (the default,
  as before), `pick` (the best of an item's outputs, in one call: `outputs_per_call` must hold every arm) or
  `pairwise` (the better of two, every pair of arms; `outputs_per_call` 2). Pick and pairwise project `won` per arm
  per item (judged runs' primary `judge_won`) and report each arm's win rate and Bradley-Terry strength with a 95%
  interval from resampling the items, and the position and noise checks as the share of verdicts that held. A judge
  is validated in its mode (`validation.mode` must be `mode`). The SummEval example validates `gemma_l` and
  `qwen_s` in both (`mode: pick`, scored `top1` beside `top1_chance`; `mode: pairwise`, scored `pair_agreement`
  with `n_pairs`; a `random` floor each): picks 0.364 and 0.263 against a random 0.070, pairwise 0.825 and 0.813
  against 0.473; the prompts ask for the JSON first and nothing after it. `judge-summ-pick-v1` and
  `judge-summ-pairwise-v1` are the summarisation eval's judges in those modes; the pick pass is run (29 arms in
  one pick: the order moved about half the picks, see the SummEval README), the pairwise one not yet.
- **An adapter's optional `primary_metric(params)`**: it names an arm's primary metric from the arm's params,
  beside `PRIMARY_METRIC` (its fallback); `run` and `rescore` record it. The SummEval adapter's is `tau`, `top1` or
  `pair_agreement` by mode.

### Changed

- **`evh experiment-run` is `evh run`, and an *experiment* is an *eval***: industry words (OpenAI evals,
  inspect_ai, Weave, Langfuse); what Braintrust and LangSmith call an experiment is a run here. The site's
  Experiments page is Evals (`evals.html`); the old address redirects.
- **Dataset roles are *validation* and *test*** (were dev and heldout): `evh dataset-split --test SHARE` (was
  `--heldout`) writes `<D>_validation` and `<D>_test`, and a split dataset records `split.test` and `part`
  validation or test. A goal's `role:` says validation, test or pilot. The reports' dev slice is the *pilot slice*,
  a small slice inside the test slice (not a validation split), and their measurement slice the *test slice*.
  `evh holdout` keeps its name.
- **The paired test's verdict is *significant*** (was separated): `significant: better`, `significant: worse`,
  `not significant`, everywhere they are printed or shown (`evh` output, the catalog, the inspector, the site,
  the reports); `family_test` and `bootstrap_test` print `SIGNIFICANT`, `pair-test` `SIGNIFICANT` or
  `NOT-SIGNIFICANT`. A project reading the old verdict strings reads the new ones.
- **A goal's arms that may win the tie-break are its *contenders*** (were tied): the decision's key is
  `contenders` (was `tied`), `evh arms --quality contender|below` (was `ties|below`), the arms page's facet
  "a contender", and the why-lines say "Contenders beside it" and "Still undecided after the tie-break". A tie
  is still what it was in a paired test: an item where two arms score the same.
- **A promoted reference is a *reference set*** (the governed collection under `data/references/<tier>/<name>/`);
  a *reference* is the expected answer for one item. The catalog's References page is Reference sets. Commands,
  paths and keys (`reference-promote`, `reference_id`, `reference_tier`) keep their names. REFERENCE.md maps
  every term to what inspect_ai, lm-evaluation-harness, HELM, OpenAI evals, Braintrust, LangSmith, Langfuse and
  Hugging Face call it.
- **`reference-create` and `reference-from-outcomes` are removed** (ADR-0022): a reference set is made only by
  promoting labels. A run's outputs are `label-from-run`'s (with the same refusals and `--not-redistributed`),
  outcomes `label-from-capture`'s (the same rules). A reference set made from outcomes has no rule of its own any more:
  promoted, it is a silver like any (with gold beside it, gold still decides; ADR-0020 is superseded). The one
  reference set here that named `reference-create` as its rebuild says where its texts come from instead.
- **`validate` fails a reference set with no manifest (V16)**, where it noted one: texts copied into
  `data/references/` by hand are a reference set nobody promoted. Import them as labels where they are and promote
  them: `reference-promote` adopts the folder when its texts are the labels' (writing its manifest; a folder whose
  texts differ is still never overwritten). Tutorial 1, the newcomer scenario, `evh self-test` and the tests make
  gold that way.
- **`evh reference-manifest` is a promotion**: it takes `--labelled-by`, `--reason` and `--by` (and `--kind`), and
  records them as `promoted_from` and the reason, so every reference set says where it came from; the reference schema
  requires both. This repository's reference sets are aligned: the caveats name where their labels came from (no
  "human-authored" or "model-generated" tier wording), the two that named a removed command as their rebuild name
  the 0.6.0 ones, and `from_outcomes` and `cost_usd`, which only the removed commands wrote, are gone. No run's
  fingerprint moves (none of these is hashed).
- **The sheet shows each arm's decision, the signals first**: an adapter's optional `decision(output)` (the
  triage example's: its disposition) is what an arm's column shows, the output itself otherwise; with no
  `same(a, b)`, two outputs agree when their decisions do. The browser's columns follow the terminal's (UXS-002).
  An adapter's optional `title(item)` names each item (the triage example's: the signal's alert name, not the
  probes that open it).
- **`evh inspect --items` is gone, and so is `--rows`; the sheet replaces both** (no aliases): `evh inspect --sheet
  --dataset-id D --runs …` shows every item's scores per arm and the rows view's signals in one table. The
  inspector's endpoints `/api/rows` and `/api/label-sheet` are gone; `/api/sheet` serves the sheet, and its
  `&format=csv` the download. The MCP tool `inspect` offers the sheet's options but not the ones that write a file
  (`--csv`, `--fill` and theirs).
- **The triage example's `write_gold.py` is `labels_from_verdicts.py`**: a source's labels from `verdicts.jsonl`,
  one file per item, for `evh label-import`; the tier is the promotion's. Its owner labels rebuild the committed
  gold set byte for byte.
- **`catalog-serve` serves on the project's own port**, not 8765 (`--port` overrides; `--public` keeps 8765), and
  `mcp --http` on another; a bookmark of `127.0.0.1:8765` moves.
- **The release leaves the pick list out**: picks are working notes that name production items, so a published
  catalog shows none waiting.
- **The tutorial kit's desk export records where the desk's router sent each ticket** (`routed`): tutorial 6 scores
  that decision against what happened, and picks the misrouted tickets for a dataset it governs.
- **The goal page explains, then answers, then shows how it got there**: what it is for first; then the answer
  so far, led by the latest round's conclusion when one closed after the baseline was promoted (the promotion's
  reason folded under it); then its rounds, one folded section each, headed by its row (round and status, the
  conclusion, what it set out to learn, arms and best), and inside it a heading per part (what changed, arms
  with retirements grouped by reason and the carried ones folded, scoring, evidence, suggested next, notes). The
  rounds table is gone.
- **The Models page has one line per cell**: the first build and "+k", the deployments' ids, "N goals" with the
  first named, the single best placing with "+k more"; vetted records first. **A model's page** has one folded
  section per deployment, holding its build and its own onboarding with the flags it accepts and why; its arms
  table names each arm's deployment and reads a re-scored arm as the goals do.
- **The datasets table shows each tag as a chip.**

- **Fingerprint v5** (RFC-021): what each part identifies. `instrument` (the harness and the adapter's code),
  `data`, `deployment` (the system under test as it executed: from the arm's model record and deployment, the
  adapter's hook, or the params; the weights, the server, where it ran; in process only when the arm calls
  nothing elsewhere) and `settings` (how it was asked: the params that change behaviour, and what a hook declares
  about its prompt), each hashed, and `hash` over the four. The machine `evh` ran on is `runner`, recorded outside
  the hash: the same deployment run from two machines is the same measurement. `evh run-compare` names the part
  that moved; the inspector's speed warning tells a deployment that differs from a runner that does. Every
  committed run is migrated by **`evh fingerprint-migrate`** (idempotent, `--dry-run`); v4 fingerprints are not kept.
- **`data/models.yaml` is replaced by the model records** (`data/models/`): its 41 entries are migrated one record
  each, and the arms page's open / proprietary filter reads the records.

- **CI runs once per merge, not twice**: a squash onto main whose tree is its pull request's head,
  tested green and up to date with main, skips the workflows that already passed on it; the deploy
  no longer waits ~13 minutes for a second run of the same files. Anything else runs them again.
- **An item id may contain `:`, `@`, `+` and `=`** (a production record's id, e.g. a fingerprint and its
  time), on the inspector's item view too; still never a path.
- **A deployment copies its data through `_release.py copy-data`**, not a list in `render.sh`: the same
  directories, plus each capture's `capture.json` (never its records), with the `text: hidden` rules
  applied and the untracked-text refusal checked before anything is written.

### Fixed

- **Every `evh` command is a `make` target again**, as the READMEs and the RUNBOOK say: the 22 added in 0.5.0 and
  0.6.0 had none (`make labels`, `make reference-promote ARGS="…"`, …).
- **The home page's "recorded" feed shows the period's events.** Its period filter read the date from the table
  cell, not the span inside it, so it hid every event and said "Nothing recorded in this period" (since 0.4.2).
- **Coverage counts an arm scored against a label set as `labels`**, on the home page and in `evh overview`; it
  counted as `none`.
- **The home page's glance reads a goal's baseline from its re-score** (RFC-022), as the goal page does: a baseline
  promoted before a re-score showed no value and no test.
- **A frontier chart's names stay inside the chart**: a long name on a dot in the middle ran past the right edge;
  it goes to the side it fits, shortened when neither does, never over the y axis.
- **The label-set and agreement tables keep their promoted and agreement columns on screen** on a desktop: long set
  ids may break there (a phone still scrolls the table sideways).
- **`evh deploy-sheet` says "against no reference"** for a run scored against none, not `None (None)`.
- **The leaderboard's silver note no longer says "model-generated"**: a silver reference set can be a person's or a
  rule's labels.
- **A retired arm read through its re-score is out of the goal's contenders.** A round's retirements name the arm's
  config, and an arm read from `runs-rescored/<scorer>/` kept the prefix, so it was never matched as retired and
  stayed among the contenders (the triage goal's: 76 arms, 51 once read right).
- **Sorting a page's later table sorts it by the column clicked.** Its header's index was counted over every sortable
  header on the page, so a second table sorted by a column it does not have and threw.
- **`evh mcp --public` sees only public fields in `inspect`.** The tool runs the command in its own
  process, where the inspector's public rules were never set, so a `--where` or `--by` on a field not
  marked public was accepted and its values could be read through the counts (0.5.0). A public
  server now runs its commands as public (`EVH_PUBLIC`), and such a filter is refused by name. This
  repository's own deployment declares no field sets, so it exposed nothing.
- **A command's own refusal through `evh mcp`** (exit 1, its `ERROR:` line, no traceback, such as a
  dataset id that is a path) is told to `--hooks` as `refused: "command"`, not as an error: a
  deployment's metrics count it as refused and its analytics send no event for it.
- **The site's links to its home page** point at `/`, never `index.html` (analytics counted the two
  apart, search engines saw two addresses for one page), and each of its pages names its own address
  as `<link rel="canonical">` and `og:url`, checked by `site/build.py --check`.
- **`validate` checks every git-tracked runs directory**, those `committed` in validate.json with their floors
  and every other one: a directory re-allowed in `.gitignore` but not added to the list was never checked
  (a set of 65 re-scored triage runs, before RFC-022 gave re-scores one place).
- **The local catalog reads what is committed.** It read every `data/runs*` directory on disk, so a smoke
  pass in an ignored `runs-smoke*` showed as a result locally and was gone from a clone and the published
  catalog. Directories git ignores are no longer read (outside a git checkout everything is). A measured arm
  the goals read from its re-score says so on its page, on the arms page and in `evh arms`.
- **Runs written where git does not keep them are named.** `EVAL_RUNS_DIR` pointed at any
  `data/runs-*` directory that `.gitignore` does not re-allow wrote runs that were never committed
  and that no catalog showed, without a word: 35 self-hosted triage runs sat in `data/runs-local`
  that way. `run` and `rescore` now print a `WARNING` when they write to such a directory
  (throwaway `runs-smoke*` and `runs-tune*` stay silent), or outside the project's data, where nothing
  reads them, and `evh validate` notes one that holds
  finished runs. The RUNBOOK's scratch example is `data/runs-smoke`, the throwaway name git already
  ignores.
- **One row per arm when a scorer changed.** A goal listed an arm twice when its runs had been
  re-scored (`evh rescore`) into a derived set, once per directory, and dropped the measured runs
  whose older score lacked the goal's measure: 37 triage arms were listed twice, 15 only from
  the re-score. A re-score against the same reference now stands in for the run it re-read on the
  goal pages, in `evh goals` and in the recommendation, which says how many arms it read that way.
  `evh goals --goal` also prints a dataset's notes, as its page did.
- **A deployment the adapter's hook declares keeps the server it was called on.** Its `server` was
  always null, so a self-hosted run whose adapter has a `fingerprint()` hook lost its Ollama or vLLM
  URL. The 130 triage runs are backfilled with the fleet they replayed (`tools/backfill_triage_fleet.py`:
  the fleet's code hash and commit `f07efa9`, the prompt's hash, each checked against what the runs'
  own items recorded) and re-sealed.
- **Onboarding a model on several machines at once keeps every result.** `model-onboard` and `arm-smoke` read the
  record when they started and wrote all of it back when they finished, so the slower erased the other machine's
  result. They re-read it under a lock and write only their own deployment or smoke.
- **A LiteLLM address given with `/v1` is not given a second one** (`http://host:4000/v1` became `/v1/v1`, a 404),
  and a reasoning setting sent through LiteLLM is named in `allowed_openai_params`: most hosted model groups refused
  `reasoning_effort` without it (`UnsupportedParamsError`).
- **A record can accept a flag as the model's nature** (`accepted: {reasoning: "<why>"}`): onboarding and arm smokes
  report it as accepted and pass (gpt-oss reasons whatever it is asked). A deployment accepts kinds of its own
  beside the record's: a hosted gateway's build cannot be pinned, and its repeats at temperature 0 vary.
- **A round with more than 40 arms is compared.** Its evidence asked the inspector for one comparison of every
  arm, which refuses past 40, and the refusal left the rows empty without a word (the triage round, 52 arms). Past
  the inspector's limit the round runs the same paired test on the scores directly; a refusal becomes a note.
- **A project module edited within the second is what runs.** Adapters and hooks were imported through
  Python's bytecode cache, which trusts a `.pyc` while the source's modification time (whole seconds) and size
  match: a scorer edited to a value of the same length (`BONUS = 0.0` to `0.5`) and re-scored at once ran the
  old code while the re-score recorded the new code's hash. They are compiled from the source every time.
- **A system that ran in the harness's own process, with no hook, is in process.** A deployment taken
  from the params was always `in_process: false`, so a local baseline (Lead-3, a keyword rule) kept its
  libraries on the runner instead of the deployment. `evh fingerprint-migrate` brings existing v5
  fingerprints to the rule when it has the run's params (11 runs here, one baseline's hash).
- **A run stops when its server cannot be reached.** An adapter that turns a failed model call into an
  answer (the triage replay records it as the fleet's "no terminal decision") wrote a complete-looking run
  when a tunnel dropped: 54 and 65 refused items scored as the model's own failures. When every call an
  item reports (`meta["calls"]`) failed reaching its server (connection refused, no route, a name that does
  not resolve), `run` stops there with `STOPPED`, that item unwritten, and `--resume` calls it
  again. A model's own failure is still a measurement.
- **`evh pair-test --round` reads each arm as the round does**: from its latest re-score when one stands in for
  its runs. It read `data/runs` alone, so a measure an arm's re-score added (production's triage run on
  `triage_cost`) found "only 0 shared item(s)" while the round's own evidence tested it. "(its leader)" is said
  only when the test chose the leader.

## 0.5.0 — 2026-10-29

Two things to know before upgrading: the package now needs **Python 3.10 or later**, and it depends on the
official **MCP SDK** (`mcp>=2.3,<3`). On 3.9, stay on `v0.4.4`. What you get: `evh mcp`, the project's read
commands as tools for any agent (stdio on your machine, or `--http` for a team or the public), and a dataset page
that shows what is inside a dataset without republishing its text. [UPGRADING](docs/UPGRADING.md) has the steps.

### Added

- **`evh mcp`: the project's read commands as MCP tools, for an agent** (stdio, the official SDK,
  [RFC-018](https://github.com/chipi/eval-harness/blob/main/docs/rfc/RFC-018-read-only-mcp-server.md)). Thirteen
  tools: `overview`, `datasets`, `dataset-items`, `arms`, `goals`, `references`, `metrics`, `activity`,
  `search`, `inspect`, `rounds`, `runs-list`, `validate`. Each call runs the command as a child process, so a tool
  answers what the command prints; each is annotated read-only; no tool writes project data, spends or runs a
  model (the one file a call writes is the p cache in the project's ignored `.cache/`, below). For Claude
  Code, in the project: `claude mcp add evh -- evh mcp`.
- **`evh mcp --http`: the same server for a team, or for anyone.** Streamable HTTP, stateless, JSON responses:
  clients on every protocol revision since 2025-03-26 call tools without a session. The Host is checked against DNS
  rebinding (`--allowed-host` is required to bind beyond the loopback); `--public` leaves out the options that
  answer with an item's text, and the `validate` tool; `--rate`, `--concurrent` and `--timeout` bound the load; a
  missing required argument is refused before anything runs; `--hooks` takes a deployment's error reporting,
  tracing, metrics and analytics, in the inspector's shape. Each call is logged as one JSON line: the tool, its
  arguments' names (never their values), how it ended, its time; never the caller's address or user agent.
  `--rate` counts calls a minute per caller (an IPv6 caller by its /64), `--rate-total` for all callers together;
  over HTTP a caller has one call running at a time.
- **`EVH_P_CACHE`: the goals' paired tests kept on disk.** Every `evh` command is a fresh process, so a view that
  shows the goals drew the same tests again each time (about 50 s on this repository's runs). With the variable
  naming a file, each estimated p is stored and read back exactly; `evh mcp` sets it to the project's ignored
  `.cache/`. `goals`, `overview` and `arms` answer in under two seconds after the first.
- **This repository's MCP server, `https://evals.humancopilot.eu/mcp`** (the deployment, not the package): the six
  worked examples for any agent, read-only, without sign-in.
- **`--json` on the catalog's view commands** (`overview`, `datasets`, `arms`, `goals`, `references`, `metrics`,
  `activity`, `search`, `inspect`): one object, `{"command", "version", "result": {"blocks": [...]}}`, each table as
  columns and rows of values, every other line as text. It is collected from the same calls that print the text, so
  the two cannot disagree. 0.7.0 gives each command its own result schema and retires this generic form: do not
  build on `blocks`.

- **What is inside a dataset, on its page and as a command.** `evh dataset-profile --dataset-id D`,
  run where the dataset is materialized, writes `data/profiles/D.json` (`schemas/profile.schema.json`,
  checked by validate V1): the number of items and their words, the shape of each gold reference
  (labels and how many of each, entries per item, a record's fields, or words per reference), and
  per item its length, its gold and, when known, where it can be read at its source. A gold of labels
  (a few short values that repeat) is listed per item; any other gold is summarised, never listed. It
  holds no item text, which a dataset's licence may not let you redistribute, unless written with
  `--with-text`, which is refused unless git has committed every item's file (a project's own synthetic data). Commit the profile and the dataset page shows "what's
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
- **Every catalog page names its command**, in its footer (`evh goals --goal G`, the inspector's from the arms
  picked). **`evh catalog --mcp URL`** names the same as an MCP tool call, with the server and how to connect
  (`--mcp-howto`); this repository's catalog passes its `/mcp`, and its header links to the site's MCP section.
- **`evh dataset-profile --json` and `evh dataset-items --json`** print the profile inside the same envelope as
  the views, `{"command", "version", "result": <the profile>}`; the Makefile targets `dataset-profile` and
  `dataset-items`.

### Changed

- **Python 3.10 or later.** The official MCP SDK needs it, and every feature comes with one install, so the
  package's floor moves from 3.9 to 3.10 (CI tests 3.10, 3.11 and 3.14). On 3.9, pin `v0.4.4`.
- **A new dependency: `mcp>=2.3,<3`**, which brings `anyio`, `httpx2`, `mcp-types`, `opentelemetry-api`,
  `pydantic>=2.12`, `pyjwt[crypto]`, `python-multipart`, `sse-starlette`, `starlette`, `typing-extensions`,
  `typing-inspection` and `uvicorn`. No result moves.
- **A dataset id is a name, never a path.** Every command that reads or writes `data/…/<id>.json` refuses an id
  that is not letters, digits, `.`, `_` and `-` (or that holds `..`); before, `../x` read or wrote outside `data/`.
- **A param shown on a catalog page or by `evh arms --arm`** hides a URL's user and password and a nested key
  named like a credential (`headers: {Authorization: …}`), as it already hid a top-level `api_key`.

### Security

From two independent reviews before this release, each reproduced before it was fixed:

- **The inspector served any `.txt` under its data tree** through `/api/item?item=../../…` (an item id was never
  checked; on `main` since 0.4.0). An item id is now a file's name, refused otherwise, in the server and the adapter.
- **The inspector's answers were cached by count, not size**: a hundred distinct 40-arm questions took a 256 MiB
  container past its limit, and `--warm` alone did on this repository's data. The cache is bounded by the bytes it
  keeps (32 MB), keeps no refusals, takes no question over 4 KB, and `--warm` stops when it is three quarters full;
  the deployment's inspector has 384 MB (it peaked at 228 of 256 under load). Its rate key is an address, never a header's
  text.
- **`evh mcp --http`**: a few parallel 4 MiB bodies killed the server; held GETs and ping floods cost memory no rate
  saw. Now `--max-body`, `--max-connections`, 8 open requests per caller, a 10 s deadline on a request's body
  (eight callers holding slow bodies took every connection), `--request-rate`, GET is 405, refusals do not count toward
  `--rate-total`, and `--public` answers are kept and their errors carry no paths. Values with NUL bytes or over 512
  characters are refused.
- **The deployment**: Caddy refuses a body over 64 KB on `/mcp` (and its `handle` line now adapts); nginx limits
  each visitor (20 requests a second, a burst of 200, 32 connections); the deploy checks the inspector is up and
  under 80% of its memory once `--warm` is done, and rolls back otherwise; the MCP hooks no longer export the
  SDK's own spans; the containers'
  `/tmp` caps files as well as bytes; `render.sh`'s check for reference texts in a release could pass with 1,657 of
  them (a pipe's SIGPIPE) and refused the five tracked ones: it now compares against what git tracks; a deploy keeps
  two releases (the live one and the rollback), prunes at its start as well as its end, and refuses to start short of
  2 GB or 300,000 inodes; the upload hard-links unchanged files again (no file ever linked: each release took ~69k new
  inodes).

### Fixed

- **The deployment's release ships `data/models.yaml`** (`render.sh`, and the item fields and profiles with it):
  from 0.4.2 it was never copied, so the deployed arms page called every model's weights unknown.
  `tests/test_render_data.py` fails when a part of `data/` the adapter reads is not copied.
- **The CNN/DailyMail and SummEval fetchers deleted the committed gold `manifest.json`** on every refetch; they
  now clear only the item files.
- **`--hooks` files with a module-level `@dataclass`** failed to load (the module was not registered before it
  ran); they load as any other module now.
- **A page links only to `http(s)` URLs**: a `source_url` or rows map that held `javascript:…` was written into
  an `href`.
- **The p cache** reads an unreadable or non-UTF-8 file as no cache instead of failing the command, starts a new
  line after a torn one, and keys each p by how it was computed.
- **`evh dataset-profile --with-text`** counts a file as tracked only once it is committed, not when it is
  merely staged.

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
- **Experiment rounds, optional** ([ADR-0004](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0004-eval-rounds.md)).
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
