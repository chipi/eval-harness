# UXS-005: The Workbench

- **Status**: Active
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-017](../prd/PRD-017-workbench.md) (the Workbench: workflows, decisions)
- **Related RFCs**: [RFC-032](../rfc/RFC-032-one-model-two-surfaces.md) (the entities and operations every screen
  calls), [RFC-033](../rfc/RFC-033-per-item-results-as-a-model.md) (per-item results)
- **Related UX specs**: [UXS-001](UXS-001-catalog.md) (the catalog: shell, tokens), [UXS-002](UXS-002-inspector.md)
  (the inspector), [UXS-003](UXS-003-cli-and-onboarding.md) (commands), [UXS-004](UXS-004-data-page.md) (the Settings screen)
- **Implementation paths**: `harness/workbench/` (below)

The Workbench is a web UI for the harness, in the order a person works: set a goal, choose a dataset, prepare the dataset, choose models and systems, then run the eval. The screens show the same data the CLI commands show, through the project's own API, and every screen shows the command that does what it does.

## Implementation

The live Workbench is `harness/workbench/index.html` (the shell), `workbench.js` (the routes, the help panel, the Words screen, the unsent-changes guard), `live.js` (every screen, read and written through the project's API under `/api/v1`), `help.js` (the help texts and the glossary) and `workbench.css`. `evh catalog-serve` serves it under `/workbench/` and prints the link that signs a browser in.

`harness/workbench/mockup/` is a frozen design reference: `mockup.html` with `mock.js`, `workflows.js` and `round5.js`, and the scripts that make their data (`mock_data.py`, `read_sources.py`, `round5_inputs.py`). It loads none of `live.js`, saves nothing, and is not part of the package. It shows the walk-through of one goal with this repository's data, every screen read from it, and `round5.js` adds the screens for the held-out test, a study, labels from what happened later, replaying the code that ran, and jobs. The mockup's rail is drawn from its own browser state; the live Workbench draws its rail from the project's API (see The shell).

## The shell

```text
 evh workbench                    Home   Models   Jobs   Prompts   Settings   Words   Catalog ↗   [x] hints   ◐

 (the screen)
```

- The Workbench is its own app on the catalog's server (`/workbench/`), with the catalog's look (UXS-001, its tokens,
  dark first) and a link to it. Its menu is about doing: **Home** (the goals), **Models** (bring one in), **Jobs**,
  **Prompts**, **Settings**, **Words** (the glossary) and **Catalog ↗**. The catalog stays where results are read.
- A goal's page leads to each step by its buttons; every screen's kicker names where it is ("Step 2 · <goal>", "The eval · <goal>").
- A `?` opens a side panel (a sheet at the bottom on a phone); "hints" hides the one-line hints for good.
- **The step rail** is on a goal's screens: the goal's overview, its five steps (`#goal-edit`, `#dataset`, `#prepare`, `#label`,
  `#reference`, `#systems`, `#eval`) and its day-to-day screens (review, production, a judge, the held-out test, studies). It is
  not on the home, the models, the jobs, the prompts, the settings or the Words. From the top it holds:

  ```text
   Goal
   Short news summaries (CNN)
   states for dataset cnn_dailymail_200
   ≡ Overview
   ✓ The goal
   ✓ Add a dataset
   3 Prepare the dataset      not looked at yet, no reference set
   4 Choose the systems       0 of 2 systems with runs
   5 Its rounds               no round closed
   Day to day
   · Review the outputs   · Production   · A judge for this goal   · The held-out test   · Studies
  ```

  - The goal's title, then "states for dataset `<id>`": the dataset the screen is on for the prepare, label and reference
    screens, else the first dataset that decides the goal (else the first it names). A dataset's screen is placed under the
    goal the person last had open when that goal names it, else the first goal that does.
  - **Overview** is the goal's page. The five steps are **The goal**, **Add a dataset**, **Prepare the dataset**, **Choose the
    systems** and **Its rounds**; each is `done` (a check mark), `current` (the screen it is on), `open` or `locked`. Done is read
    from live data: the goal exists; it names a dataset; that dataset is fetched, has a profile ("looked at") and has a
    reference set; two or more systems have runs on it; a round is closed. Adding a dataset is open from the start; Prepare is
    open once a dataset is named; Choose the systems and Its rounds are open once the dataset is prepared. A locked step links
    to the goal's page.
  - A step not done says what it lacks, under its name and as its tooltip: "no dataset named"; for Prepare "not fetched", "not
    looked at yet", "no reference set" (those that apply, comma-separated; "no dataset to prepare" with no dataset); for the
    systems "N of 2 systems with runs"; for the rounds "no round closed".
  - The day-to-day group links to **Review the outputs**, **Production**, **A judge for this goal**, **The held-out test** and
    **Studies**; the screen the person is on is marked.
  - At 900 px and narrower (checked at 390 px) the rail folds to one line, "Step N of 5 · Name ▾" (the day-to-day screen's name
    on a day-to-day screen), and the reasons are in the opened list.
- Opened without the server's link, the page says how to open it (`evh catalog-serve` prints the link); with a server that
  has restarted, it says to open the new link.

## 0 An empty project: one way in

```text
 Your goals
 Running now          Nothing is running.                                         Every job

 What should this project help you decide?
 An evaluation starts with a goal: the decision you need to make, and how you will know which
 system is better for it.

 [ Start with a goal ]   [ Models ]   [ Prompts ]   [ Settings ]   [ The catalog ↗ ]
```

- With no goal there is one thing to do. The menu is there, its pages empty.
- The project exists already: its store was named at `evh init --store files|sqlite`, which the Workbench does not
  do.

## 1 The goal

```text
 Step 1                                                                         Set the goal
 A goal is the decision this evaluation helps you make. Everything later is measured against it.

 What is it?  ?     [ Short news summaries (CNN)                                             ]  id [ short_news_summaries_cnn ]
 What is it for? ?  [ Pick a model that writes a short summary of a news article, at a known  ]
                    [ cost.                                                                    ]
 The decision ?     [ Which models can be told apart on summary quality, and what each costs.  ]
 How you'll judge ? [ coverage ▾ ]   (•) higher is better  ( ) lower is better
 How a winner is ?  (•) balanced — not worse than the best by more than its margin, then the cheapest
 picked             ( ) quality first   ( ) frugal — a wider margin, then the cheapest
                    advanced ▸ margin, then pick by [ cost ▾ ] [ speed ▾ ]
 Who you are        [ your name ]

                                                       [ Make the goal ]   [ Cancel ]
```

- Five things, on one screen; everything else in a goal (axes, guardrails, output contract, links) is edited
  with `goal-set` or comes from the screens that own it (datasets in step 2).
- The id is made from the title, changeable before saving, fixed once the goal exists.
- The measure is a text box offering the metrics the project's scorers produce (`GET /metrics`); a new one can be typed, and
  picking one with a known direction sets the direction.
- Saving is `goal-new` (an edit, checked against the goal's schema and links), sent with `datasets: []`: a goal has
  no dataset until step 2 adds one (`goal-set`). Its problems are shown on their fields. Editing an existing goal
  (**Edit the goal**) is the same form with "Save the goal", sending only what changed.
- The form is a unit of unsent changes ("For every live screen").

After saving, the goal's page is the hub of the journey: where it stands, and the next step.

```text
 Goal · news_summary_cnn
 Short news summaries (CNN)
 Decides on coverage (higher is better).
 next step   <what to do next>
             <the command that does it>

 dataset            role         items         reference   runs         baseline
 cnn_dailymail_200  test         made, fetched gold/…       2 run(s) · 3 arm(s)   v1

 Rounds            r1 closed: <its question>
 Running now       <operation> · running
 [ the goal over time: a chart of its baseline's versions and closed rounds' promoted runs ]

 [ Add a dataset ] [ Choose the systems ] [ The eval ] [ Review the outputs ] [ Production ]
 [ The held-out test ] [ Studies ] [ Edit the goal ] [ Back to your goals ]
```

- The next-step box and the table come from `goal-status`; a dataset reads "made, fetched", "made, not fetched" or
  "not made", and "does not decide" beside a role it does not decide on. Running jobs and rounds show only when there are some.
- The trend chart is `evh chart trend --goal <id>`, its numbers folded under it; it is left out until there is something to draw. With fewer than two points it is one line ("One point so far: <line> (v<n>), <measure> <value>. A trend needs two."). The goal screen shows its commands (`goal-status` and `chart trend`) in one folded block, once.

## 2 The dataset

```text
 Step 2 · news_summary_cnn                                                       Add a dataset

  Use one you have      [ choose one of the project's datasets      ▾ ]           [ Use it ]
  Its role for this goal   (•) validation  ( ) test

  Or make one from a source
  Where from   [ Hugging Face ▾ ]
  ref [ abisee/cnn_dailymail ]  config [ 3.0.0 ]  split [ test ]
  text [ article ]  answer [ highlights ]  id [ id ]  limit [ 200 ]
  [ Read it ]   a job: the source's description and its first rows; nothing is saved
  ┌──────────┬───────────────────────────────────────────┬──────────────────┐
  │ item     │ text                                      │ answer           │
  │ (the first rows as read, not invented here)                              │
  └──────────┴───────────────────────────────────────────┴──────────────────┘
  Its fields   [ Propose its fields ]      keep │ field │ type │ values
  Its id [ cnn_dailymail_200 ]   Who you are [ … ]                [ Make the dataset ]
```

- A dataset is made on one screen, from a source; each source asks only what it needs, its own query:

  | Source | Where from asks |
  | --- | --- |
  | a folder of files | `path`, `glob` (which files) |
  | a table: CSV, JSON lines | `path`: a .csv or .jsonl with `item_id`, `source_url` and field columns |
  | Hugging Face | `ref`, `config`, `split`, then `text`, `answer`, `id`, `limit` |
  | Croissant | `url` or `path`, `record_set`, then `text`, `answer`, `id`, `limit` |
  | Zenodo | `record`, `file`, then `text`, `answer`, `id`, `limit` |
  | OpenML | `dataset`, then `text`, `answer`, `id`, `limit` |
  | Kaggle | `ref`, `version`, `file`, then `text`, `answer`, `id`, `limit` |

  The columns `text` (the item a system receives), `answer` (the expected answer, which becomes a reference set in
  step 3), `id` (default: the row number) and `limit` (default: all) are asked for every source that has columns; a
  folder and a table have none to name. A dataset made from a capture is made in Production (W3).
- "Use one you have" offers the project's datasets the goal does not use yet; the role is `validation` (while you
  choose and tune) or `test` (the final answer, kept untouched until then).
- Preview before anything is written; fields are a table, proposed (`fieldset-propose`, a job) from the source's columns,
  never typed from nothing, each kept or not.
- The choices are unsent until **Make the dataset**, and kept across a reload in this browser ("For every live
  screen": unsent changes).
- **Read it** is `source-preview` (`POST /source-previews`, a job: the source's description and its first rows with the
  start of each text and its answer; nothing written under `data/`).
- The expected answer's column is the query's `"answer": COLUMN` (the Hugging Face, Croissant, Kaggle, OpenML and
  Zenodo sources read it): `dataset-create` writes the answers as a label set, `answers` by default, of source `dataset`.
- **Make the dataset** writes the kept fields as a fieldset (`fieldset-new`, which other datasets may share), then
  `dataset-create` as a job: it freezes the items and their hashes. Its role for the goal is a `goal-set` on the goal's
  `datasets`; the goal's page then lists it.

## 3 Prepare the dataset

```text
 Step 3 · cnn_dailymail_200                                                     Prepare the dataset

  a Fetch its items        ✓ done                                             (dataset-materialize)
  b Look inside            ✓ done   Open its page in the catalog ↗             (dataset-profile)
  c Its reference set      the expected answer for each item, that outputs are scored against
                           Change the reference set     see what another one moves first
                           Promote a label set
                           answers · dataset: the answers the data came with
                           [ gold ▾ ] [ why: a sentence ]                              [ Promote ]
                           Or label it                [ Label it here ]
                           Who you are [ … ]
  [ rank stability chart ]  [ agreement chart ]
```

- One screen with the three things a dataset needs before an eval; each is a job or a small choice, done in
  order, each showing its result: a `dataset-materialize` job (**Fetch them**), a `dataset-profile` job (**Profile it**, after
  the fetch), then the reference set.
- **Promote a label set** lists the dataset's label sets, the one `dataset-create` wrote from the answer column (source
  `dataset`) among them, each with a tier choice (gold or silver) and a reason: `reference-promote`, a decision, which records who and why.
- **Label it here** opens the labelling screen (below, W2). Importing a filled CSV is `label-import` on the command line.
- Once there is a reference set, **Change the reference set** (W6, below) shows what a new one moves before anything is re-scored.
- The rank-stability and agreement charts show when there is something to draw.

## 4 Models and systems

```text
 Step 4 · news_summary_cnn                                                      Choose the systems

 Check each on three items       on [ cnn_dailymail_200 ▾ ]   spend at most (USD) [ 0.05 ]
   system        model       where it runs   its prompt   its check
   deepseek_m    deepseek    openrouter      p_3f9a…      [ Check it on three items ] [ Clone it, change one thing ]
                                                          pass · 3 call(s) · spent $0.00092 · all 200 items ≈ $0.04
                                                          ▸ item 1 · its reply
 Make a system from a model
   The model [ deepseek-4.1-flash · vetted · #2 of 29 on this goal ▾ ]   Where it runs [ openrouter ▾ ]
   The prompt [ … ]   Temperature [ 0 ]   At most this many tokens [ ]   Its id [ … ]   Who you are [ … ]
                                                                           [ Make the system ]
```

- Models come from the project's records with their state (`GET /models`, ADR-0021): **vetted** (every deployment's
  onboarding passed and a system on it passed its smoke), **onboarded** (onboarding passed, no system smoked yet),
  **check** (a probe flagged something to read), **none** (never probed). Vetted is computed, never approved by hand. A model
  that is not there is brought in (W5); the screen offers only models that have somewhere to run, each with its rank on this goal.
- What is compared is a **system**: a deployment, a prompt version and settings, with no dataset (RFC-032). Making one
  here is `system-new`; a system placed in a round is an arm (step 5). One prompt and one set of settings for every
  system, so a difference in the scores is the model's. The goal's prompt is one name, `<goal>/prompt`, kept as
  versions (RFC-028): the text typed is recorded as a prompt version (`prompt-version`; the same text is the same version)
  and the system points at it, so every run records the version it sent. Each system's version is shown and links to
  the Prompts screen.
- **Clone it, change one thing** makes a new system from an existing one with one change (its prompt, temperature, most
  tokens or the model it sends), so its difference in the scores is that change's. A changed prompt is a new version
  made from the source's. A clone is a new system; there is no clone operation (`system-show`, then `system-new`).
- The three-item check (`arm-smoke`, a job under the cap given: a system on a dataset) shows each system's status, calls,
  what they cost, what all items would cost and the reply to each item, before anything is compared.
- The new system's choices are unsent until it is made, kept across a reload ("For every live screen": unsent changes).

## 5 The eval: its rounds

The eval is the goal measured on its dataset, in rounds: each round asks one question, compares its arms, and ends in a
decision kept with its reason. This is where people spend most of their time (W1).

```text
 The eval · news_summary_cnn                                                              Its rounds
 ( r1 · closed )  ( r2 · closed )  ( r3 · open )                           (tabs; the open round, else the last)

 Does a cheaper hosted model match bart_l's coverage on CNN?                (the round's question)
 Who you are [ … ]
 r3 · open · on cnn_dailymail_200 · from r2 · budget $5 · spent $0.0412
 its conclusion                    (once closed)

 The evidence                                       coverage · each arm against the leader, Holm
   [ gain-cost chart: each arm's gain against its cost ]            its numbers folded under it
   The leader: bart_l. A verdict holds when the raw p is under its threshold.
   arm          mean     Δ        raw p    threshold   verdict
   deepseek_m   0.3460   -0.0001  0.9923   0.0500      not significant
   (notes: the spend against the budget; "<system>: n run(s) since then not read here (…); the round reads the k it recorded")

 Where the arms stand        every arm of the goal on the dataset, this round's and before
   [ intervals ]  [ items ]  [ latency ]

 Its arms
   bart_l · 1 run(s) · carried                                            
   deepseek_m · 1 run(s) · run                                            [ Retire ]
   Carry in [ llama_l ▾ ] [ Carry it in ]  an arm of an earlier round, or a system already measured on the dataset

 The baseline on cnn_dailymail_200
   v2 current · <run> · who · reason
   v1 · <run> · who · reason            [ why go back, a sentence ] [ Roll back to v1 ]

 Run arms in it
   [ ] llama_l  [ ] gemma_s          spend at most (USD) [ 1 ]   [ See the cost first ]  [ Run them ]

 Close the round
   Its conclusion [ … ]
   [ ] promote the leader's run (<run id>) to the goal's baseline, the conclusion as its reason
                                                                            [ Close the round ]
```

- **The tabs** are the goal's rounds (`#eval/<goal>/<round>`); the open round is selected, else the last. A closed round
  shows its conclusion; an open one the parts below.
- **Evidence:** the gain-cost chart of the round (`GET /charts/gain-cost`, drawn by the server as the catalog and
  `evh chart` draw it, its numbers folded under it), the leader, and a table of **arm**, **mean**, **Δ**, **raw p**,
  **threshold** and **verdict**: each arm against the leader, Holm across them, the harness's own verdict words. The
  notes are `round-evidence`'s: the spend against the budget, and runs of an arm made after the round recorded its own,
  which the round does not read.
- **Where the arms stand:** the goal's arms on the round's dataset as the catalog draws them (intervals, items where
  they differ, latency), each with its numbers folded.
- **Its arms:** each arm of the round with its runs and how it entered ("carried" or run in it); in an open round a
  **Retire** button asks for a reason of a sentence and says the retire is final, a recorded decision no operation undoes;
  **Carry in** offers the arms of the round before and the systems already measured on the dataset (`round-carry`):
  unchanged, not run again.
- **The baseline** on the round's dataset: its versions with the run, who promoted each and why, the current one marked;
  an earlier version has a reason box and **Roll back** (`baseline-rollback`, a new version with its own evidence).
- **Run arms in it:** the systems that are not in the round and not yet measured on its dataset (a second measurement
  of a measured system is refused by `evh run`); ticked, with a cap, **See the cost first** is the dry run of the sweep
  (`POST /estimate`) and **Run them** is one `sweep` job for the round's arms under that cap, with its progress. A
  system already measured is carried in, never run again. An arm never smoked has no measured cost to cap from: the dry run
  says so ("no arm-smoke of it is recorded"), and the screen links **Choose the systems**, where **Check it on three
  items** (`arm-smoke`, with its command printed) runs the smoke.
- **Close the round:** the conclusion, and a checkbox to promote the leader's run to the goal's baseline with the conclusion
  as its reason; the browser asks to confirm. This checkbox is the only way to make a baseline on this screen. A conclusion
  shorter than three words is refused by `round-close`, a reason by `round-retire`.
- **Open the next round** (on the last round's tab, and only when no round is open; the first round on a goal with none):
  the round's question (stored as `hypothesis`), the dataset, **Carry in from rN** with each arm in play of the last
  round that has plain runs on the chosen dataset ticked (all ticked) and the hint "carried arms are not run again; on another dataset each is read through its
  runs there", what it may spend (USD) and who you are. The list follows the "On" dataset: an arm of the last round with no plain run on it is not
  offered, and the screen says "not offered: no run on <dataset>" beside its name. A round a study opened (`study:` on the round, RFC-029)
  says "opened by study <id>" on its tab.
- The screen ends with the commands `evh round-list <goal>` and `evh round-evidence <goal> rN`, and a link to **A judge for this goal**.

  What each part calls (RFC-032):

  | Part | Operation | Note |
  | --- | --- | --- |
  | Open the round | `round-open` (`dataset`, `from`, `keep`, `hypothesis`, `budget_usd`) | the page says "question", the model stores `hypothesis` |
  | Carry an arm in later | `round-carry` | unchanged, not run again |
  | Clone an arm | `system-show`, then `system-new` with the one change | in Choose the systems: a clone is a new system |
  | The estimate | `POST /estimate` with the `sweep` (its dry run) | the cap the person sets is the job's `max_cost_usd` |
  | Run | `sweep` (`systems`, `dataset`, `goal`, `round`), a job | one job for the round's arms |
  | Evidence | `round-evidence`; the charts from `GET /charts/<kind>` | each arm against the leader, Holm: the raw p and its threshold |
  | Retire | `round-retire` (`arm`, `reason`) | final: a recorded decision, not undone |
  | Make baseline | `round-close` with `promote` (the checkbox), or `baseline-rollback` | the close's conclusion is the promotion's reason |
  | Close | `round-close` (`conclusion`) | |

  The screen's forms (the round's question, a retire's reason, a round's conclusion, a roll back's reason) are units of unsent changes
  ("For every live screen").

## The other workflows

### Home

```text
 Your goals
 Running now          Nothing is running.                                         Every job →
 goal                       decides                datasets            rounds   next
 <title>   <goal id>        <measure> (<direction>) <its datasets>        <n>      <the next step>
 [ New goal ]  [ Models ]  [ Prompts ]  [ Settings ]  [ The catalog ↗ ]
```

- Every goal with where it stands and its next step, and what is running across goals (PRD-017, requirement 1).
- Live: `GET /goals`, then `GET /goals/{goal}/status` per goal, and `GET /jobs?state=queued,running,running
  (unsupervised)` for "running now". The command shown is `evh goal-list`, `evh goal-status <goal>` and `evh jobs-status`.

### Jobs

- Every step that runs is a job: its cost first, then progress and the log, then its result. A job keeps running when
  the page closes; it can be stopped (`jobs-stop`), and a run resumed (`jobs-resume`) with what the stopped job left
  of its cap; one that spent it all is not resumed. A job that spends carries its cap (`jobs-start --max-cost-usd`); one that
  waits for what another holds is "queued", naming it; one whose supervisor stopped is "running (unsupervised)" while
  its process lives, "lost" after (RFC-026).
- A job is an operation run detached (RFC-032): its record is `{id, operation, inputs, by, locks, env, run_id, state,
  progress, spent_usd, result}`. It holds no command line: the page builds the command it shows from the operation and
  its inputs. Progress (`done` of `total`) is reported by `run`, `sweep`, `rescore` and `judge-score`; the others show
  their log. The page polls; there are no events.
- Commands: `jobs-start`, `jobs-status` (the jobs, or one), `jobs-logs` (from a byte on, or followed until it ends),
  `jobs-stop`, `jobs-resume`. A job's files (such as a label sheet) are read from `GET /api/v1/jobs/{id}/files/{name}`.
- **Jobs** lists every job a page at a time (**Newer**, **Older**), filtered by state (several at once), operation and goal,
  with the total found: **job**, **operation**, **state** (and what it waits for), **who**, **made**, **progress**,
  **spent**. A job's page shows its operation, state, who asked, when it was made and ended, progress, spent against its cap,
  the locks it holds, its run, its inputs, **Stop it** while it runs, **Resume the run** for a stopped run job, its result, its
  files as downloads and its log, followed while it runs.

### W2 Review and label

```text
 Review · news_summary_cnn                                                       Review the outputs
 On [ cnn_dailymail_200 ▾ ]    Compare [ bart_l ▾ ] with [ deepseek_m ▾ ]
 What you will say   (•) which is better   the arms hidden and shuffled per item, so the pick is not swayed
                     ( ) what went wrong   each output tagged with the failure modes it shows
 Failure modes       [ summaries ▾ | a new list… ]   (for "what went wrong")
                                                                                   [ Make the sheet ]

 item   the item         A                          B                          which is better
 t01    The Palestinian  The Palestinian Authority  The Palestinian Authority  ( ) A  ( ) B  ( ) the same
 …
 The judgements' name [ … ]   Who you are [ … ]       [ Submit ]  12 answer(s) not submitted   [ Throw the sheet away ]
```

- Two arms' outputs on the same item, on a sheet; for "which is better" the sides are shuffled and the arms hidden, so the pick
  is not swayed; for "what went wrong" each output has a box per failure mode, and "ok". The sheet is a `sheet-export` job
  (`POST /datasets/{dataset}/sheets`, `fill` pick or tags): the page fetches the sheet from the job's files, never its key
  (403), so a blind sheet stays blind in the browser; the filled sheet goes back to `sheet-import` (`POST
  /datasets/{dataset}/sheets/import`) with `export_job` naming that job, which reads the key where the job kept it. "Which is
  better" is written as judged scores (read as `judged/<name>`) and "what went wrong" as a tag set; neither is a **pick**: a pick is a
  production record chosen for the next dataset version (W3).
- **Submitted when done, never item by item.** The sheet is filled on the screen; nothing is written until it is submitted, and
  then `sheet-import` writes it as it does a CSV, one frozen set. While it holds answers not yet submitted the sheet is **dirty**,
  and the screen says so:
  - a mark and a count beside the sheet's name ("12 answer(s) not submitted"), from the first answer until the import
    job succeeds;
  - Submit is enabled only then;
  - leaving the screen, closing the page or opening another sheet asks first;
  - a reload keeps the answers, in this browser only, and the screen says so;
  - on success the mark clears and the screen says what was written; on a refusal the mark stays and nothing is written.
- The failure modes are a named list (`failure-modes-list`, `failure-modes-show`), so tags are counted; a new list is made on the screen
  (`failure-modes-new`).
- **Labelling the items** (the expected answer) is the labelling screen (`#label/<dataset>`, "Label the items"): choose the
  items (not labelled yet, or all), **Make the sheet** (`label-sheet`, a job), then a row per item with its text, a proposal,
  a box for its answer (offering the allowed answers when the sheet names them) and a note; a label set's name and who you are;
  **Submit** writes the label set (`label-import`, a job), **Throw the sheet away** drops it. The sheet is kept in this browser
  until it is submitted. A label set is never edited; a second pass is a new set, promoted to a reference set (step 3, W6).
  Filling a CSV elsewhere and importing it is `label-sheet` and `label-import` on the command line.

### W3 Production

```text
 Production · <goal>                                                             Learn from production
 Who you are [ … ]
 1 What it decided          <capture> · n record(s) · <importer> · captured <time> · made into <dataset>
                            Capture records   [ jsonl ▾ ] [ the capture's id ]   {"path": "records.jsonl"}     [ Capture them ]
                            Make a dataset of a capture   [ capture ▾ ] [ its dataset's id ]               [ Make the dataset ]
 2 Against people's labels  [ capture ▾ ] [ dataset ▾ ] [ the arm's system id ] [ the decision's field ]       [ Score its decisions ]
 3 Pick the rows for the next version
                            [ dataset ▾ ] [ production's arm ▾ ] [ against a label set ]   [ Show where it was wrong ]
                            keep │ item │ production decided │ the labels
                            [ the dataset they may join ] [ why they are worth keeping ]                   [ Pick them ]
 4 The next dataset version [ dataset ▾ ] [ the new version's id ]                                         [ Make the next version ]
 5 Labels from what happened later   [ label set's name ]  [ rules over each record's outcome ]            [ Label from the outcomes ]
 6 Replay the code that ran [ code record ▾ ] [ Show its periods and faithfulness ]
                            Replay a system   [ system ▾ ] [ dataset ▾ ] [ production's run id ] …        [ See the plan first ] [ Replay it ]
```

- Each part is one small form with its command: a capture (`capture`, with an importer and its query) and a dataset made from it
  (`dataset-from-capture`, then `dataset-materialize`); production's recorded decisions as an arm, scored like any (`arm-from-capture`,
  no call); the rows where that arm's decision is not a label set's (`sheet-show --wrong-against`), checked and picked with a reason
  (`pick`); the next version made from the picks (`dataset-extend`); labels from what happened afterwards, rules tried in order, the first
  that matches deciding (`label-from-capture`, with its coverage from `label-coverage-show`); a code record's periods and
  faithfulness (`periods`, `faithfulness-show`), and a replay's plan first, then the replay as a job (`faithfulness`).
- The rows checked and their reason are unsent until **Pick them** ("For every live screen": unsent changes).

### W5 Bring in a model

```text
 Models · bring one in                                                           Bring in a model
 Its id [ … ]   Its name [ … ]   What it is (•) a language model ( ) an ML model ( ) a baseline
 The ids runs record [ … ]   Its weights ( ) open ( ) proprietary   Licence [ … ]   Who you are [ … ]   [ Make it ]
```

- **Models** lists every model with its kind, weights, deployments and state, and **Bring in a model**. What it is is `model-new`
  (weights, licence, the ids runs record); the model's page then shows its kind, weights, licence, aliases and settings and, per
  deployment, where it runs, its backend and tag, whether it passed onboarding, its flags, its arm smokes and what it accepts. **Add a
  deployment** is `deployment-new` (its id, where, its tag and address).
- **Onboard** is `model-onboard`, a job with a cap (**Run the probes**): the probes run and their findings are kept as the
  deployment's dated checks (stored in the deployment's history), shown, never typed (answers, thinks before answering, with the chosen
  settings, speed, the same answer twice, valid JSON). A model of ours costs nothing; a hosted one is charged for each probe call.
- A **check** is read, then either fixed and onboarded again or **accepted** as the deployment's own nature with why
  (`deployment-accept`, a decision: the flag's kind, a sentence). There is no "approve as vetted": the page shows the rule, vetted when
  every deployment's onboarding passed and a system on it passed its smoke.

### Prompts

- `#prompts` lists every prompt with its versions and runs; a prompt's page (`#prompts/<name>`) has `1 Its versions` (each with who made
  it, what it was made from, its note, its text and the runs that sent it, with their scores), `2 What changed between two` (a diff of
  two versions, `prompt-diff`), `3 A new version` (made from the latest, its note required: `prompt-version`) and `4 Write one out`
  (a version as a file to commit: `prompt-export`).
- A system points at a version; a study's trials make new ones.

### W6 Change the reference set

```text
 Prepare · <dataset> · its reference set                                    Change the reference set
 a Its reference sets now       the reference sets, the label sets (who, how many, when), how often two sets agree
 b What it moves                [ a label set ▾ ] compared with [ a reference ▾ ]   [ Score the arms against it ($0) ]
 c Promote it                   [ gold ▾ ] [ its name ]  [ why these answers are the yardstick: a sentence ]   [ Promote ]
 d When the scoring changes     [ a goal ▾ ]   [ Preview the change ]   Apply it to a round [ rN ▾ ] [ why ]   [ Re-score the round ]
```

- Choose the new reference set, see **what it moves**: "What it moves" scores the stored outputs against a label set under its own label
  (`rescore` with `labels`, a job, $0; never where a goal reads) and reads the leaderboard, one table per reference: the arms ranked on
  the label set beside their rank on a reference chosen to compare with, each side's ordering test, an arm that wrote the reference marked.
- Promoting is `reference-promote` with who and why, then `rescore` with `reference_id` (a table of its own beside the one scored
  against the old reference): the arms are re-scored against it from stored outputs, no calls.
- A scoring change is `score-preview` (a job writing nothing): each arm now and after, how far it moved, the leader, the recommendation
  and the contenders now and after; applied to a round by `rescore` with the goal, the round and why.

### W7 A judge

- `#judge/<goal>`, "A judge for this goal": `a Its judge scorers` (`scorer-list`: each with its judges, families, whether validated and the
  judged scores it made; a form to make one with systems as its judges, `scorer-new`), `b How it judges` (`scorer-show`: its prompt file,
  guards and cap, its judges; changed while it has judged nothing, `scorer-set`, only what changed sent, else a new version started from it,
  `scorer-new` with `supersedes`), `c Does it agree with people?` (its validation as stored, with the reasons it is not validated and the
  people's checks of its judges), `d Score the arms with it` (the cost first, a dry run, `POST /estimate` on `judge-score`; then the judging
  as a job under a cap, an unvalidated judge only when asked and labelled so; what it judged), `e What it said, and why` (`judge-verdicts`,
  the lowest scores first, a page at a time) and `f What it cost` (`cost-report`, a job).
- Its judges are two families at least, from onboarded models, so one vendor's taste does not decide. The prompt is a file the scorer names
  (`prompt.file`), typed as its path, relative to `data/scorers`: its validation was measured on those bytes.
- The validation is shown as stored; this screen does not run one. The screen says what an installed project does: a validation is an
  ordinary eval whose arms are the judges (`evh run` on items people have rated), and the scorer's `validation` block names those runs
  (RUNBOOK, "Validating a judge"). The repository's `tools/validate_judge_*.py` are not installed and are not named on the screen.
- The judging job speaks as `judge-score` does: a grade scorer whose prompt does not name every dimension of its task is refused before any
  call, naming the dimensions it leaves out; a reply that is JSON of the wrong shape is reported as unparsed with the keys it had and the
  dimensions the prompt must ask for; and a note appears when a judge's bill differs from what its declared prices give for the same tokens by
  more than 1.2 times either way ("NOTE: judge J was billed $X, N.NNx what its declared prices give"), since the dry run estimates at the declared prices.

### W8 Settings

- Rare, so terse: six rows, each one form with the command that does the same: where the project keeps its data (`data-migrate`, a job;
  the server answers 503 with Retry-After while it moves, and the page waits it out; "Move it" is offered only once the dry run counted
  something to move, and moving to the other store needs `store: <other>` set in `config.yaml` first), bringing the data to this release's formats
  (`migrate`), checking the project (`validate`, a read, shown as "checking…", its failures listed as `evh validate` prints them), the
  two policies under `data/` (`validate.json`, `goals/policy.yaml`: `data-show`, `data-put`; a file that did not exist when read is saved with `new: true`, so one made elsewhere since is not overwritten), budgets (set when a round opens) and
  publishing a dataset (`dataset-publish`, a job). The screen's detail is [UXS-004](UXS-004-data-page.md#the-settings-screen).
- `config.yaml` (the exposure check's repos, for one) is not edited here: `data-put` writes only under `data/`.
- A project whose data the release does not read (another format, a store just switched) opens live, and the settings are where it is put right.

### The held-out test

```text
 Day to day · <goal>                                                             The held-out test
 Who you are [ … ]                                  the held-out side [ <dataset>_test ▾ ]
 1 The seal             n held-out items · sealed <date> · counts by <fields>
 2 Who has read it      n read    who read │ reads       [ what was read … ]  [ Record a read ]   The leak check [ Check for leaks ]
 3 Counts, for safety   day │ items │ kind=…         [ allow one more field ] [ why ]  [ Allow it ]
 4 Open it              the candidate's hypothesis committed first; one look     [ candidate ▾ ] [ why ]  [ Open it for this candidate ]
 5 Run the candidate and what it is against                                            [ Run <candidate> and <against> ]
   the number that counts (n read items left out)   items │ Δ │ p │ verdict
   with the read items kept (not the one that counts)   items │ Δ
```

- A goal's day-to-day screen (RFC-029, RFC-031): a test set is a goal dataset with `role: test` or a sealed side of a split, as `evh looks` and the
  studies read it, and both are listed, each with its seal state: for a sealed side the seal and what its counts may show; for one that is
  not sealed "not sealed: role test", its looks so far and the next one's level, and **Seal it** (the split again by its recorded rule, the same
  items, with `--seal`, its command printed; a side no split made has no rule to seal by, and says so); who has read it (each read by whom and
  what, a read recorded by hand with who read it, and the leak check's finds, which can be recorded as reads); counts per day by the fields fixed
  at the seal, for safety only, never to judge an effect, with a field allowed by a decision with a reason (`dataset-seal-counts`); opening it for one
  candidate (`dataset-unseal`: its hypothesis committed first, one look, each later look tested at a stricter level); both arms run on it; and
  the confirmation, the read items left out and the full number beside it, marked.
- **Hold some items out** (**Hold another dataset out** once one is) is a form on the same screen: a dataset, by time (the time field and a boundary) or by hash (the test share),
  and the fields its counts may show, with a box, ticked, to seal the test side. A split makes `<id>_validation` and `<id>_test`, and both sides join the goal
  (validation to tune on, test to decide on). Each side
  gets the parent's references, promoted from the same label sets at the same tiers; a parent with references is split only by someone named (the
  split form's "Who you are": a promotion records who made it, and the split is refused before anything is written otherwise).
- Commands: `exposure`, `exposure-add`, `exposure-check`, `sealed-counts`, `dataset-seal-counts`, `dataset-unseal`, `looks`, `pair-test`, `dataset-split`.

### A study

- A goal's day-to-day screen (RFC-029): `#study/<goal>` lists the goal's studies and offers **A new study** (an id and a spec as YAML, **Write the spec
  from these**, **Check it (nothing runs)**, **Run it**: `study-run`) and **Import a past loop** (a `results.tsv` kept as a closed study, shown, never
  confirmed: `study-import`). A study's page has `1 What it searches`, `2 Its trials` (kept or dropped against the best so far, with the cost), for
  an agent-sampled study `3 Propose the next trial` (ask its state, then tell a proposal that runs as the next trial: `study-ask`, `study-tell`), and
  `Confirm it on a test set: one look` (the rule given before any test item is read; what it would read first; `study-confirm`). **Stop it**
  (`study-stop`) and **Continue it** under a cap end or resume it.
- A study is research on validation items and never promotes; only its confirmation on a test set is evidence.

## Help, for someone who is new to this

Help assumes a first-time reader does not know the harness's words and can find the way without reading the documentation, and never talks down to
one who does. It is a secondary goal of every screen.

### Three layers, always the same

1. **The step says what it is for.** One sentence under each step's title, always shown: what this step does and why
   it comes now ("The examples your systems will be tested on: a frozen list of items, each with its hash, so every system sees exactly the
   same ones, now and later.").
2. **Each field has a one-line hint** under it: what to put, with an example from this kind of project. Short enough
   to read without stopping.
3. **A `?` next to a field or a heading opens its explanation** in a side panel (not a tooltip that vanishes): what it
   is, why it matters, a real example, what goes wrong if it is wrong, and "read more", a link to the page of the published
   docs that holds the topic (`DOCS_BASE` plus the page `HELP_DOCS` names for the label). The panel stays open while the
   person fills the field. A screen's lead sentence carries the `?` of its step.

```text
 How you'll judge ?  measure [ coverage ▾ ]  (•) higher is better          ┌─ How you'll judge ─────────────┐
   the number that decides which system is better                          │ A measure is one number per    │
                                                                           │ example: how good one output   │
                                                                           │ is. coverage: how much of the  │
                                                                           │ reference a summary covers when│
                                                                           │ cut to the reference's length, │
                                                                           │ 0 to 1.                        │
                                                                           │ Why it matters: the goal ranks │
                                                                           │ systems by it; pick the one    │
                                                                           │ your decision depends on.      │
                                                                           │ If it is wrong: the "best"     │
                                                                           │ system wins at the wrong thing.│
                                                                           │ Read more: Metrics ↗           │
                                                                           └────────────────────────────────┘
```

### Words

- The harness's own words are taught, not replaced. The first time a word appears on a screen it is underlined lightly, in running text only; pointing at it shows its one-line meaning and a click (or Enter, or Space) opens the full
  panel. A word carries no `?` of its own. The **Words** screen lists the glossary.

### Not childish

- Plain, exact sentences; the real terms with their meaning, never a cute substitute; no emojis, no exclamation marks,
  no "great job".
- Examples are real (a well-known public dataset), never "foo".
- **For someone who knows:** every screen shows the command that does what it does, folded; hints can be hidden for good ("hints",
  remembered on this browser), the `?` stays; nothing blocks a person who fills the fields straight away.

### Where the help lives

- `help.js`: `HELP`, the texts keyed by step and field (a title, the hint always shown, and the `?` panel's what, why, example, what goes
  wrong and where to read more), and `GLOSSARY`, the words the Words screen lists. The screens read it; the texts are written and reviewed like the docs.

## The data model (RFC-032)

What a screen shows is an entity or a view of them; what a person changes goes through an operation, never a path. Where each lives is the
model's (`harness/scripts/model/`), the same keys in either store:

| Entity | What a person sets | What operations write | Kept at |
| --- | --- | --- | --- |
| Goal | title, what it is for, the decision, the measure and direction, the winner rule (a named default) | its history of saves | `goals/<id>.yaml` |
| Dataset | its source, name, fields | items, hashes, versions, profile, its sealed side | `datasets/`, `materialized/`, `sources/`, `profiles/` |
| Fieldset | the fields kept | — | `fields/<id>.yaml` |
| Label set | labels (a filled sheet, submitted when done) | who, when | `labels/<dataset>/<set>/` |
| Reference | who and why for a promotion | hashes, counts, its tier | `references/{gold,silver}/` |
| Model | what it is, weights, licence | — | `models/<id>.yaml` |
| Deployment | where it runs, its endpoint and settings; a flag accepted with why | its dated checks (onboarding, smokes, acceptances) | `deployments/<model>/<deployment>.yaml` |
| Prompt | its text, a name, a note | its hash, its parent | `prompts/<name>/` |
| System | a deployment, a prompt version, settings (no dataset) | — | `systems/<id>.yaml` |
| Run | — (a system run on a dataset, in a round or not) | outputs, cost, latency, fingerprint, purpose | `runs/<id>/run.json`, `outputs.jsonl` |
| Score | which scorer, which reference | per-item rows (RFC-033), metrics | `runs/<id>/scores/<scorer>@<reference>/` |
| Round, arm | its question (`hypothesis`), budget, which arms; a retire's reason; the conclusion | when opened and closed, by whom; each arm's runs | `rounds/<goal>/<r>.yaml` |
| Baseline | a promotion's reason; a rollback | its versions, the evidence | `baselines/<goal>/<dataset>/<n>.json` |
| Scorer, judge | which judges, prompt, mode | its validation (by the tools), verdicts | `scorers/`, `judge-validation/`, `judge-verdicts/` |
| Capture | which deployment, since when | its records and their hashes | `captures/<id>/` |
| Pick | which production record, for which dataset, why | when, by whom | the picks (`GET /picks`) |
| Failure modes, tag | the list of modes; a tag on an output | counts per arm | `failure-modes/<id>.yaml`, a label set |
| Study, look; exposure; faithfulness | the spec; a read by hand; a code record's versions | trials, looks, reads, faithfulness records | as RFC-029 to RFC-031 define them |
| Job | which operation, its inputs, its cap | state, progress, log, spent, result | the project's `.build/jobs/` (not project data) |

Views (where a goal stands, a round's evidence, the leaderboard, a comparison, label coverage) are read operations,
computed from what is stored when read and cached until a write changes what they read: the Workbench, the catalog
and `evh` give the same numbers.

## Every screen and what it calls

| Screen | Calls | What it does |
| --- | --- | --- |
| Home | `goal-list`, `goal-status` per goal, `jobs-status` | every goal with its next step; what is running |
| Goal | `goal-status`, `chart trend` | where it stands, the next step, its datasets and rounds, the buttons to each step |
| 1 Goal form | `goal-new` (with `datasets: []`), `goal-set`, `goal-show`, `metric-list` | made from the home, changed from its page (only what changed is sent) |
| 2 Dataset | `dataset-list`, `goal-set`, `source-preview`, `fieldset-propose`, `fieldset-new`, `dataset-create` | one the project has, or one from a source (its query, `source-preview`, its fields proposed and kept, `dataset-create` with them and its answers, the goal's role) |
| 3 Prepare | `dataset-materialize`, `dataset-profile`, `dataset-show`, `reference-promote`, `chart` (rank-stability, agreement) | fetch, look inside, promote a label set (the dataset's own answers too); "Label it here" |
| Label | `label-sheet`, `jobs-status` (its files), `label-import` | the sheet filled on the page and submitted when done |
| 4 Models and systems | `model-list`, `model-show`, `system-list`, `system-show`, `system-new`, `prompt-show`, `prompt-version`, `arm-smoke` | a system made from a model where it runs, the shared prompt and settings (kept as versions of `<goal>/prompt`); a clone; each checked on three items with a cap |
| Prompts | `prompt-list`, `prompt-show` (`text`), `prompt-diff`, `prompt-version`, `prompt-export` | every prompt with its versions and runs; two versions' diff; a new version made from the latest; a version written out as a file |
| W5 Bring in a model | `model-new`, `deployment-new`, `model-onboard`, `model-show`, `deployment-accept` | a model, its deployments, the probes, an accepted flag; no "approve" |
| 5 / W1 The eval | `round-list`, `round-show`, `round-evidence`, `round-open`, `round-carry`, `POST /estimate`, `sweep`, `round-retire`, `round-close` (`promote`), `baselines`, `baseline-rollback`, `chart` (gain-cost, intervals, items, latency) | the rounds as tabs, a round's question, arms, evidence and baseline versions; open one, carry an arm in, see a run's cost, run arms as one sweep under a cap, retire with a reason, close with a conclusion |
| W2 Review, label, tag | `dataset-arm-list`, `failure-modes-list`, `failure-modes-show`, `failure-modes-new`, `sheet-export`, `sheet-import` (`export_job`) | two arms compared on a sheet made as a job, "which is better" blind, or "what went wrong" with a failure-mode list; answers kept in this browser until submitted |
| W3 Production | `capture-list`, `capture`, `dataset-from-capture`, `dataset-materialize`, `arm-from-capture`, `sheet-show` (`wrong_against`), `pick`, `dataset-extend`, `label-from-capture`, `label-coverage-show`, `periods`, `faithfulness-show`, `faithfulness` | records captured and made a dataset; production's decisions scored as an arm; the rows where it was wrong picked; the next version made from the picks; labels from what happened later; a code record's periods and faithfulness, a replay |
| W6 Reference | `reference-list`, `label-set-list`, `reference-promote`, `leaderboard`, `score-preview`, `rescore` | what a label set moves, a promotion with why and the arms re-scored against it, a scoring change previewed and applied to a round with why |
| W7 Judge | `scorer-list`, `scorer-show`, `scorer-new`, `scorer-set`, `judge-score`, `judge-verdicts`, `POST /estimate`, `cost-report` | the goal's judge scorers and one shown; changed until it judges, then a new version from it; the cost first, then judging as a job under a cap; its verdicts and what it cost |
| W8 Settings | `data-ls`, `validate`, `migrate`, `data-migrate`, `data-show`, `data-put`, `dataset-publish` | the store and moving the data into it, formats, the check, the two policies, publishing ([UXS-004](UXS-004-data-page.md)) |
| Held-out test | `dataset-split`, `exposure`, `exposure-add`, `exposure-check`, `sealed-counts`, `dataset-seal-counts`, `dataset-unseal`, `looks`, `pair-test` | a dataset split and sealed; reads and the leak check; the counts for safety; the side opened for one candidate; the confirmation |
| Studies | `study-list`, `study-show`, `study-run`, `study-ask`, `study-tell`, `study-stop`, `study-confirm`, `study-import` | a study written as YAML, checked (the dry run) and run; its trials and best; the agent sampler; stopped; confirmed on a test set (one look); a past loop imported |
| Jobs | `jobs-status` (`GET /jobs`, `GET /jobs/{id}` with its `files`), `jobs-logs`, `GET /jobs/{id}/files/{name}`, `jobs-stop`, `jobs-resume` | every job a page at a time, filtered by state, operation and goal; one job's record, cap and spend, result, files and log; stopped; a stopped run resumed (refused when it wrote nothing) |

## For every live screen

- **The session.** The page opens through the Workbench link `evh catalog-serve` prints (it signs in once); the token is new at every server
  start, so a page left open answers 401 on any call after a restart, and the page puts up one notice, over whatever screen it shows and whichever read answered (an optional chart too), that the server was restarted and to open the Workbench link it printed (it carries the new token);
  reloading the page shows "Sign in" and says to open the Workbench link the server printed.
- **Writes.** Every call that is not a GET sends `X-EVH-Data: 1`; an upload is base64 JSON, at most 50 MB a call.
- **Reads.** An API read that may have nothing to show takes `optional=1`: the server then answers 200 with why instead of an error, and the
  screen reads it as a refusal ("No chart yet: …", a chart left out).
- **Refusals**, shown where the action was: an edit's problems on their fields (`{error, kind, problems}`); a job
  refused before it exists (`{error}`); a job that failed later (its state, its refusal's kind, its log); 503 with
  Retry-After: 5 while a migration holds the project: job polling waits it out ("the project is being moved, waiting…"), other calls show the error. An unhandled server error is always a JSON 500.
- **Who acted.** The name is asked once ("Who you are", kept in the browser) and sent as `person:<name>` with every write (`by`); every
  decision sends its reason.
- **Kinds.** A read answers at once; an edit or a quick decision answers with what was saved; work is a job (its
  estimate first where it spends, its cap, then its progress).
- **Phones.** Every screen is checked at 390 px: tables of four columns or more become cards; the two- and
  three-column tables, the forms and the jobs list are checked there too.
- **Behind a proxy** the Workbench and `/api/v1` answer 404.
- **Unsent changes.** What a person enters is sent only by the screen's own action (Save, Make, Run, Submit); until then the screen holds it
  and says so. One rule, built once, for every screen: a form is an element marked `data-form`, its button `data-send`, its mark
  `data-unsent-mark` (`live.js`); `workbench.js` asks before leaving and redraws nothing that holds unsent changes; closing the page asks too.
  - **dirty**: a mark beside what holds unsent changes ("not saved yet"), from the first change until the action succeeds; the action is
    enabled only then and names what it will write; leaving the screen, closing the page or opening another record asks first; on success the
    mark clears; on a refusal it stays, the problems are shown where they belong, nothing is written;
  - **longer work** also counts what is pending ("12 answer(s) not submitted") and keeps it across a reload, in this browser only (the screen
    says so): the labelling sheet and the review sheet (W2), the new dataset's choices (step 2) and the new system's choices (step 4);
  - every other **form** saved by one button is marked dirty and asks before leaving, with no memory across a reload: the goal form, a model and a
    deployment (W5), a scorer (W7), a file under `data/` (W8), a round's question, a retire's reason, a round's conclusion, a roll back's reason, the
    rows picked for the next version (W3).
