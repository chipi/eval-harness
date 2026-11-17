# UXS-005: The Workbench (sketches round 3, mockup round 5, realigned with RFC-032)

- **Status**: Draft — sketches and the clickable mockup for review (owner, 2026-11-06: "agree on the structure … see
  some sketches … then a mock-up"; 2026-11-08: "complete the mock-up really with everything we've been saying";
  2026-11-12, the owner's request: the mockups brought up to the code built since round 4, round 5); 2026-11-17:
  realigned with the model RFC-032 built and the owner's decisions D1 to D9 (PRD-017), as the spec the live screens
  are built from; 0.8.0
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-017](../prd/PRD-017-workbench.md) (the Workbench: workflows, decisions)
- **Related RFCs**: [RFC-032](../rfc/RFC-032-one-model-two-surfaces.md) (the entities and operations every screen
  calls), [RFC-033](../rfc/RFC-033-per-item-results-as-a-model.md) (per-item results)
- **Related UX specs**: [UXS-001](UXS-001-catalog.md) (the catalog: shell, tokens), [UXS-002](UXS-002-inspector.md)
  (the inspector), [UXS-003](UXS-003-cli-and-onboarding.md) (commands)

Low-fidelity sketches, in the order a person works (owner, round 1's review: "start from the beginning: you set a
goal, you have a dataset for it, you do something with the dataset, and then you go into the experiment"): an empty
project, the goal, its dataset, preparing the dataset, then models and the eval. How often a step happens
decides how much thought it gets, never its place in the order. One example runs through it: this repository's
real CNN summaries goal (`news_summary_cnn`: its title, statement, decision and measure) and its dataset from Hugging
Face (`abisee/cnn_dailymail`, the 1.0.0 test split's 11,490 rows, the first 200 the committed runs measured). Values
not read from the project are left out rather than invented; the round sketched at the end is made up to show the
screen.

## The mockup, and the live screens

The mockup is the Workbench's first, static form (owner: "the mock-up is already the workbench app you're starting,
just static"): `harness/workbench/` (`index.html`, `workbench.css`, `workbench.js` for the shell and the five steps,
`workflows.js` for the other workflows, `round5.js` for round 5's screens, `help.js` for every hint, `?` panel and
word). `live.js` turns a screen live, on the project's own API; on 2026-11-17 the home, a goal, the models (a new
model, a deployment, onboarding, an accepted flag), step 1 (a goal made or changed), step 2 (a dataset for a goal),
step 3 (preparing it), labelling a dataset's items (the sheet), step 4 (the systems) and W1 (the eval's rounds) are
live, and every other screen
says it is not yet. Until the project answers no mockup screen is drawn (one sent a reload of a live screen home).

**From 2026-11-17 (D7)** the mockup is a frozen design reference: its data (`mock.js`, this repository's) stops
shipping in the package, and `mock_data.py`, which reads the layout before RFC-032 (`data/configs`,
`data/runs-linux`), is not run again. The live screens are built from this spec, each calling the operations named in
"Every screen and what it calls" below. What the sections below say of "the mockup" describes it as it was reviewed.

- **Its data was read, never invented.** `harness/workbench/mock_data.py` wrote `mock.js` from the project: the goals,
  datasets, models and their onboarding, the CNN source, items, references and profile, the rounds, every arm's
  scores, settings and first replies, the silver reference and who wrote it, the judge and its validation, and the
  triage goal's capture and comparison, the rows where production was wrong, the label sheet, the local arms' re-runs
  and their paired tests. Several inputs are the harness's own answers, saved first because they take minutes (`evh
  models`, `evh goal-list`, `evh pair-test`, `evh sheet-show --wrong-against`, `evh label-sheet`; the list is at the
  top of the script). `harness/workbench/read_sources.py` reads every other dataset source with the example its module
  documents, through the harness's own source classes, writing nothing to the project.
- **What it pretends is labelled.** Jobs and saving are pretended; each place says so in a "mockup:" note, which a
  switch hides. In a round opened in the walk-through, a local arm shows its own real re-run (the project's Linux
  re-runs, compared with bart_l's by `evh pair-test`); a hosted arm, which the project never re-ran, shows its r1 run
  and says so; a clone has no run.
- It walks from an empty project to a closed round and through every workflow below; state is kept per browser, and
  "start over" clears it.

## The shell

```text
 evh workbench · project: harness          Home   Models   Jobs   Settings   Words   Catalog ↗   [x] hints   ◐

 GOAL                       │
 Short news summaries (CNN) │   (the screen)
  ≡ Overview                │
  ✓ Goal                    │
  ✓ Dataset                 │
  ✓ Prepare                 │
  4 Models                  │
  5 Eval                    │
 DAY TO DAY                 │
  · Review and label        │
  · Production              │
  · A judge                 │
```

- The Workbench is its own app on the catalog's server (`/workbench/`), with the catalog's look (UXS-001, its tokens,
  dark first) and a link to it. Its menu is about doing: **Home** (the goals), **Models** (bring one in), **Jobs**,
  **Settings** (W8), **Words** (the glossary). The catalog stays where results are read.
- Inside a goal a rail shows its five steps with their state, and under them the goal's day-to-day work: reviewing and
  labelling (W2), production (W3), its judge (W7).
- A `?` opens a side panel (a sheet at the bottom on a phone); "hints" hides the one-line hints for good.

## 0 An empty project: one way in

```text
 evh workbench · project: my-project       Home   Models   Jobs   Settings   Words   Catalog ↗   [x] hints   ◐

            What should this project help you decide?

            An evaluation starts with a goal: the decision you need to make, and how
            you will know which system is better for it.

                                  [ Start with a goal ]

            already have data or runs?  import a dataset · open the catalog
```

- With no goal there is one thing to do. The menu is there, its pages empty with the same single way in.
- The project exists already: its store was named at `evh init --store files|sqlite`, which the Workbench does not
  do. "import a dataset" is step 2's sources.

## 1 The goal

```text
 New goal                                                                       step 1 of 5
 ①Goal ─ ②Dataset ─ ③Prepare ─ ④Models ─ ⑤Eval

 What is it?  ?     [ Short news summaries (CNN)                                             ]
 What is it for? ?  [ Pick a model that writes a short summary of a CNN-style news article, at ]
                    [ a known cost, for a reader who wants the story's main points.            ]
 The decision ?     [ Which models can be told apart on summary quality, and what each costs   ]
                    [ per article.                                                             ]
 How you'll judge ? measure [ coverage           ▾ ]   (•) higher is better  ( ) lower is better
 How a winner is ?  (•) balanced — not worse than the best, within its margin, then the cheapest
 picked             ( ) frugal   ( ) quality first                         advanced ▸ (margins, axes)

                                                       [ Cancel ]   [ Save and add its dataset → ]
```

- Five things, on one screen; everything else in a goal (axes, tie-breaks, guardrails, output contract, links) is
  "advanced" or comes later from the steps that own it (datasets in step 2, references in step 3).
- The id is made from the title and shown small (`news_summary_cnn`), changeable before saving.
- The measure offers the metrics the project's scorers produce (`GET /metrics`); a new one can be typed.
- Saving is `goal-new` (an edit, checked against the goal's schema and links), sent with `datasets: []`: a goal has
  no dataset until step 2 adds one (`goal-set`). Its problems are shown on their fields.

After saving, the goal's page is the hub of the journey: the same five steps, each with its state and its next action.

```text
 Short news summaries (CNN)                                                  news_summary_cnn
 decides coverage (higher is better) · balanced                                        [edit]

 ①Goal ✓   ②Dataset ○   ③Prepare ○   ④Models ○   ⑤Eval ○

 ② Dataset   the items the goal is measured on                       [ Add a dataset → ]
```

## 2 The dataset

```text
 Add a dataset to news_summary_cnn                                              step 2 of 5

  Use one you have      [ choose one of the project's datasets      ▾ ]           [ Use it ]
  or make one from:
   [ a folder of files ]  [ a table: CSV, JSON lines ]  [ Hugging Face ]  [ Croissant ]
   [ Zenodo ]  [ OpenML ]  [ Kaggle ]  [ production: a capture ]
```

Making one is four short screens, one decision each:

```text
 a Where from     Hugging Face   repo [ abisee/cnn_dailymail ]  config [ 1.0.0 ]  split [ test ]
                  pinned to 690bb95 · licence apache-2.0                          [ Read it → ]

 b What's in it   11,490 rows · columns: article (text), highlights (text), id (text)
                  the item is   [ article ▾ ]   its reference is   [ highlights ▾ ]
                  ┌──────────┬───────────────────────────────────────────┬──────────────────┐
                  │ id       │ article                                   │ highlights        │
                  │ (the first rows as read, not invented here)                                │
                  └──────────┴───────────────────────────────────────────┴──────────────────┘
                  take  (•) the first [ 200 ] rows   ( ) all   ( ) a seeded sample of [ 200 ]

 c Its fields     proposed from the columns                       (a field is what you can slice by)
                  ┌───────────┬────────┬──────────────────────┬──────────┐
                  │ field     │ type   │ values               │ public   │
                  │ (fields proposed from the columns, each with its type and values)    │
                  └───────────┴────────┴──────────────────────┴──────────┘   + add a field

 d Name it        [ cnn_dailymail_200 ]   role for this goal [ test ▾ ]
                  description [ the first 200 test rows ]                 [ Create the dataset ]
```

- Each source asks only what it needs, its own query (the sources' modules document them):

  | Source | Where from asks |
  | --- | --- |
  | a folder | `path`, `glob` (which files), `recursive` |
  | a table | `path`: a .csv or .jsonl with `item_id`, `source_url` and field columns |
  | Hugging Face | `ref`, `config`, `split`, then `text`, `id`, `fields`, `limit` |
  | Croissant | `url` or `path`, `record_set`, `text`, `id` |
  | Zenodo | `record`, `file`, `text` |
  | OpenML | `dataset`, `text` |
  | Kaggle | `ref`, `version`, `file`, `text` |
  | production | which capture, which records (`FIELD:VALUE`), one per a field (`dataset-from-capture`) |

- Preview before anything is written; fields are a table, proposed (`fieldset-propose`), never typed from nothing.
- The four steps' choices are unsent until Create, kept across a reload ("For every live screen": unsent changes).
- a's "Read it" and b's first rows are `source-preview` (`POST /source-previews`, a job: the source's description and
  its first items with the start of each text and its answer; nothing written under `data/`; API 2, built).
- The expected answer's column (b) is the query's `"answer": COLUMN` (the Hugging Face, Croissant, Kaggle, OpenML and
  Zenodo sources read it): `dataset-create` writes the answers as a label set, `answers` by default (`answer_set`), of
  source `dataset` (API 3, built). The folder and manifest sources have no columns to name.
- In the mockup each source is read for real with the example its module documents: a folder (`data/sources/
  cnn_dailymail_20`), Zenodo (record 10157504, `sts_gold_tweet.csv`), Kaggle (`uciml/iris`), Hugging Face; OpenML
  answered HTTP 503 on 2026-11-08 and the screen shows that answer; Croissant shows the refusal the source gives the
  harness's own export (a text dataset's items are a FileSet, which the source does not read); the table source shows
  that the project has no manifest to read. Reading them found that the Zenodo source documented a record without the
  file it named; its example is now one that reads.
- **Create** is a job (`dataset-create`): it freezes the items and their hashes. Its role for the goal is a
  `goal-set` on the goal's `datasets`. The goal's step 2 turns ✓. Fields kept are a fieldset (`fieldset-new`), which
  other datasets may share.

## 3 Prepare the dataset

```text
 ③ Prepare  cnn_dailymail_200                                                   step 3 of 5

  a Fetch its items        ✓ materialized · 200 of 200 · hashes match        (dataset-materialize)
  b Look inside            ✓ profiled: 200 items · words per item · each field's values
                           [ open the items ↗ catalog ]
  c Its reference set      the expected answer for each item, that outputs are scored against
                           ( ) it came with one: highlights → promote as  [ gold ▾ ]  [ Promote ]
                           ( ) label it here                          [ Open the labelling screen ]
                           ( ) import labels from a sheet (CSV)       [ Choose a file ]
                           who [ you ]   why [ the dataset's own highlights, as published ]

  Ready when: fetched ✓  looked at ✓  a reference set ✓      [ Next: the models → ]
```

- One screen with the three things a dataset needs before an eval; each is a job or a small choice, done in
  order, each showing its result: a `dataset-materialize` job, a `dataset-profile` job, then the reference set.
- **"It came with one"** promotes the label set `dataset-create` wrote from the answer column (source `dataset`) with
  `reference-promote`, who and why recorded (API 3, built).
- **Labelling here** opens the labelling screen (below, W2): the person fills the sheet on the screen and submits
  it when done (`label-import`, a job that writes the label set); the CSV round trip works as today.
- A reference set's promotion (`reference-promote`, a decision) records who and why (governance).
- Once there is one, **Change the reference set** (W6, below) shows what a new one moves before anything is re-scored.

## 4 Models

```text
 Choose the models to compare                                                  step 4 of 5

 a Pick the models    (•) run on this goal before (28)   ( ) every model in the project (64)
   [ ] model                 kind  weights      state             systems  on this goal
   [x] deepseek-4.1-flash    llm   open         vetted            19       #2 of 29
   [x] eval-llama-maverick   llm   open         none              12       #3 of 29
       …                                                   [ Bring a model that isn't here ]
 b Their settings     the prompt (the same for every system) · temperature 0 · at most 1200 tokens
 c Check each on three items                                      [ Check 3 systems on 3 items ]
   deepseek-4.1-flash  system deepseek_m   3 replies · spent $0.00092 · all 200 ≈ $0.04    ▸
     item 1 · its reply · 2.0 s          │ the reference · coverage 0.47

 Ready when: at least two systems checked (3)                           [ Next: the eval → ]
```

- Models come from the project's records with their state (`GET /models`, ADR-0021): **vetted** (every deployment's
  onboarding passed and a system on it passed its smoke), **onboarded** (onboarding passed, no system smoked yet),
  **check** (a probe flagged something to read), **none** (never probed: run before onboarding existed). Vetted is
  computed, never approved by hand (D4). A model that is not there is brought in (W5).
- What is compared is a **system**: a deployment, a prompt version and settings, with no dataset (RFC-032). Picking
  a model here makes a system of it (`system-new`); a system placed in a round is an arm (step 5). One prompt and one
  set of settings for every system, so a difference in the scores is the model's; the prompt a person writes is
  saved as a prompt version (`prompt-version`, with a name and a note). ML models (BART) carry their own settings.
- The models picked and their settings are unsent until their systems are made, kept across a reload ("For every
  live screen": unsent changes).
- The three-item check (`arm-smoke`, a job: a system on a dataset) shows each system's replies beside the reference,
  what they cost and what all items would cost, before anything is compared. In the mockup the replies, cost and
  timing are the r1 run's real first three items.

## 5 The eval: its rounds

The eval is the goal measured on its dataset, in rounds: each round asks one question, compares its arms, and ends in a
decision kept with its reason. This is where people spend most of their time (W1), so it gets the most thought.

```text
 The eval                                            news_summary_cnn · cnn_dailymail_200
 THE ANSWER SO FAR · baseline bart_l
 bart_l (BART-large-CNN, MIT, $0 on a CPU) leads on coverage at 0.3461, not significantly different from
 deepseek_m (0.3460, p = 0.99), for CNN-style text; rent deepseek_m if you need speed.

 ( r1 · closed )  ( r2 · closed )  ( r3 · closed )                                   [ Open round r4 ]

 Which of 24 hosted LLMs (8 vendors × 3 price tiers) and local BART summarisers covers a CNN article's
 gold highlights best, and at what cost?
 The comparison ?                       29 arms · 200 items · scored against gold/cnn_dailymail_200
   coverage ↑  ●  bart_l      ● deepseek_m        │ What the goal's rule picks: balanced — none could be
               ●●  ●  ● ●  ●   ●     ●     ●      │ shown within the margin, so the leader stands: bart_l.
               $0      $100     $1,000   $10,000   │ Detectable: … only within about 0.0363; this goal's
                     cost per 1M articles (log)    │ margin is 0.01731: raise it, compare fewer, add items.
   #  arm          coverage      vs the leader             per 1M articles   per article
   1  bart_l  baseline recommended  0.346  leader          $0                10.7 s
   2  deepseek_m   0.346         not significant p 0.9923  $191              1.5 s
   …                                              [ Show the 13 significantly worse ]
 Its conclusion                                              promoted cnn_bart_l_n200_v1
```

- **Reading a round:** the question, the comparison as a chart (coverage against cost) and a table (the paired test
  against the leader, cost, speed), what the goal's rule picks and why, and what these items can show at all (the
  harness's own "detectable" line). Selecting an arm opens its settings, cost and its summaries beside the reference.
  The significantly worse are folded.
- **A round of one's own (W1):**

```text
 round r4 · open · from r1
 The round's question ?  [ Does a cheaper hosted model match bart_l's coverage on CNN?               ]
 1 Its arms      bart_l (baseline, carried, not re-run) · deepseek_m $0.04 · llama_l $0.04 · …
                 ▸ Clone an arm and change one thing   [ deepseek_m ▾ ] [ the prompt ▾ ] [ its new value ]
 2 Run           [ Run 4 arms · about $0.35 ]          the dry run's estimate first; jobs on the server
 3 Results       arm  coverage  vs the leader  per 1M   retire · make baseline (each with its reason)
                 The conclusion [ … ]                               [ Close the round ]
```

  The arms come from step 4; the baseline is carried, not re-run; a clone changes one thing so its difference is that
  change's. The estimate is each arm's r1 cost per item × 200 in the mockup (`POST /estimate` on the run in the live
  one). Retiring and making a baseline each record a reason; closing records the conclusion and promotes the
  baseline's run. From here: score with a judge (W7), review the outputs (W2).

  What each part calls (RFC-032; the owner's decisions of 2026-11-17):

  | Part | Operation | Note |
  | --- | --- | --- |
  | Open the round | `round-open` (`goal`, `dataset`, `from`, `keep`, `hypothesis`, `budget_usd`) | the page says "question", the model stores `hypothesis` (D5) |
  | Carry an arm in later | `round-carry` | unchanged, not run again |
  | Clone an arm | `system-show`, then `system-new` with the one change | a clone is a new system; no clone operation |
  | The estimate | `POST /estimate` with the `sweep` (its dry run) | the cap the person sets is the job's `max_cost_usd` |
  | Run | `sweep` (`systems`, `dataset`, `goal`, `round`), a job | one job for the round's arms; `round-run` is not built (D2) |
  | Results | `round-evidence`; the chart from `leaderboard` (`goal`, `round`) | each arm against the leader, Holm: the raw p and its threshold |
  | Retire | `round-retire` (`reason`) | final: a recorded decision, not undone (D3) |
  | Make baseline | `run-promote` (`reason`), or `round-close` with `promote` | the close's conclusion is the promotion's reason |
  | Close | `round-close` (`conclusion`) | |

  A round being built (its clones and changed values) is unsent until Run, kept across a reload; its question and
  conclusion are forms ("For every live screen": unsent changes).

## The other workflows

### Home

```text
 Your goals
 Running now          Nothing is running.                                         every job →
 goal                                  decides             datasets  rounds      reference sets  next
 Short news summaries (CNN)            coverage (higher)   1         4           gold/…          review the outputs →
 Triage decisions on Orrery's …  deployed  triage_cost (lower)  2   4 · last r4  2               learn from production →
```

- Every goal with where it stands and its next step, and what is running across goals (PRD-017, requirement 1). The
  mockup lists the walk-through's goal, then this repository's seven goals as they stand.
- Live: `GET /goals`, then `GET /goals/{goal}/status` per goal, and `GET /jobs?state=queued,running,running
  (unsupervised)` for "running now" (API 5, built).

### Jobs

- Every step that runs is a job: its cost first, then progress and the log, then its result. A job keeps running when
  the page closes; it can be stopped (`jobs-stop`), and a run resumed (`jobs-resume`) with what the stopped job left
  of its cap; one that spent it all is not resumed. A job that spends carries its cap (`--max-cost-usd`); one that
  waits for what another holds is "queued", naming it; one whose supervisor stopped is "running (unsupervised)" while
  its process lives, "lost" after (RFC-026). The list shows each job,
  its status, when it started and how far it is.
- A job is an operation run detached (RFC-032): its record is `{id, operation, inputs, by, locks, env, run_id, state,
  progress, spent_usd, result}`. It holds no command line: the page builds the command it shows from the operation and
  its inputs. Progress (`done` of `total`) is reported by `run`, `sweep`, `rescore` and `judge-score`; the others show
  their log. The page polls; there are no events.
- Operations: `jobs-list`, `jobs-show`, `jobs-log`, `jobs-file` (a job's artifact, such as a label sheet),
  `jobs-stop`, `jobs-resume`. The list filters by state (several at once), operation and goal, with offset, limit and
  the total found (API 5, built).

### W2 Review and label

```text
 Review the outputs                                       compare [ bart_l ▾ ] with [ deepseek_m ▾ ]  [x] hide which is which
 ‹ item 1 of 3 · row 0 ›                ▸ the article and its reference
 A                                       │ B
 The Palestinian Authority becomes …     │ The Palestinian Authority became …
 Which is better   ( ) A  ( ) B  ( ) the same  ( ) neither is good
 What went wrong   [narration] [label] [markdown] [bullets] [paragraphs] [overlong] [truncated]  + a mode
 A note            [ anything a number would miss ]                                  [ Save and next ]
```

- Two arms' outputs on the same item; the sides are shuffled and the scores hidden while arms are hidden, so the pick
  is not swayed. Which is better, tags and notes are a label set with who made them; today they come back only as a
  filled sheet (`sheet-import`, a job under the dataset's lock). The sheet is a `sheet-export` job (`POST
  /datasets/{dataset}/sheets`, `fill` pick, scores, tags or label): the page fetches the sheet from the job's files,
  never its key (403), so a blind sheet stays blind in the browser; the filled sheet goes back to `sheet-import`
  with `export_job` naming that job, which reads the key where the job kept it (API 1, built). This "which is better" is not a
  **pick**: a pick is a production record chosen for the next dataset version (W3).
- **Submitted when done, never item by item** (owner, 2026-11-17). The labelling screen is a sheet the person fills
  on the screen; nothing is written until it is submitted, and then the imports write it as they do a CSV today
  (`label-import` for labels; `sheet-import` for "which is better" and tags, with the key the server kept), one frozen
  set each. While it holds answers not yet submitted the sheet is **dirty**, and the screen says so:
  - a mark and a count beside the sheet's name ("12 answers not submitted"), from the first answer until the import
    job succeeds;
  - Submit is enabled only then, and says what it writes ("Submit 12 answers as label set owner_2026_11");
  - leaving the screen, closing the page or opening another sheet asks first;
  - a reload keeps the answers, in this browser only, and the screen says so;
  - on success the mark clears and the screen links to the new set; on a refusal the mark stays, the refused rows are
    shown on the sheet and nothing is written.
- The two arms' outputs and the item come from `comparison-items` and `comparison-item`; `sheet-show` answers a
  sheet's blocks, not one row per item.
- The failure modes are a named list, so tags are counted; the first list is proposed from the eval's own format
  checks (the CNN adapter's narration, label, markdown, bullets, paragraphs, overlong, truncated).
- **Labelling the items** (the expected answer) is the same screen's other half: the item, a box for its answer
  ("start from its highlights" when the data has one), save and next; or the sheet: download it, fill it elsewhere,
  drop it back, checked before anything is kept (`label-sheet`, `label-import`): its columns, each item id against the
  dataset's, an answer per row; unknown ids are refused and named. Labels then go to a reference set (W6). The mockup
  holds the real 200-row sheet and checks a dropped one in the page.

### W3 Production

```text
 Triage decisions on Orrery's error signals · production
 1 What it decided         233 decisions captured · 2026-07-25 to 2026-10-29 · captured 2026-11-04
 2 Against people's labels  triage_prompt_own_code_loads_v1  0.446  recommended
                            triage_baseline_pro_v2data_v1    0.872  production's model  +0.426, p 0.0014, worse
 3 Pick the rows for the next version   ( ) wrong against the labels  ( ) new since …  ( ) not labelled yet
 4 The next dataset version             [ Make the next version ]
```

- The rows checked and their reason are unsent until "Make the next version", kept across a reload ("For every
  live screen": unsent changes).
- A goal that is not deployed says so and what will show once it is. The mockup shows production on this project's
  deployed goal (triage): its capture, production's decisions scored like an arm against people's labels, the 30
  decisions where production's model disagreed with the owner's labels (what it decided, what people decided, its
  cost), the picks (checked rows, one reason) and the next dataset version made from them (`arm-from-capture`, `label-from-capture`,
  `sheet-show --wrong-against`, `pick`, `dataset-extend`).

### W5 Bring in a model

- What it is (`model-new`: weights and licence) and where it runs (`deployment-new`: a hosted gateway, a machine of
  ours, inside the harness; its address and settings); then **onboard** (`model-onboard`, a job with a cap): the
  probes run and their findings are kept as the deployment's dated checks (`deployment-history`), shown, never typed
  (answers, thinks before answering, with the chosen settings, speed, the same answer twice, valid JSON).
- A **check** is read, then either fixed and onboarded again or **accepted** as the deployment's own nature with why
  (`deployment-accept`, a decision). There is no "approve as vetted" (D4): the page shows the rule, vetted when
  every deployment's onboarding passed and a system on it passed its smoke. In the mockup the findings are
  `deepseek-4.1-flash`'s (pass) and `ministral-3-14b`'s (check: "the JSON probe's answer is not valid JSON") real
  onboarding. Live today.

### W6 Change the reference set

- Choose the new reference set, see **what it moves** (the arms ranked on it beside their rank on the current one),
  then promote it with who and why and re-score the arms ($0: stored outputs). In the mockup: the CNN silver set,
  written by the arm `anthropic_l`, puts anthropic_m first (0.491) and makes deepseek_m significantly worse (p 0.0087);
  the two arms that rise most are the author's own family, which the screen says before promoting.
- Live: the label sets (`label-set-list`), `reference-promote` (with its reason), `rescore` (a job). "What it moves"
  is the leaderboard read under the other label (`leaderboard`, `label`, such as `silver`); a scoring change's is
  `score-preview`, whose job's result gives each arm now and after, how far it moved, and the leader, the
  recommendation and the contenders now and after (API 4, built).

### W7 A judge

- Its judges (two families at least, from onboarded models), how it judges (grade each, rank a block, pick the better
  of two), its prompt, its guards and its cost cap; **does it agree with people** (its validation against the best free
  scorer, and on a CNN set where people chose the best summary); then a dry run for the cost and the scoring as a job.
  In the mockup: `judge-summ-v2` (openai_l, anthropic_l), tau 0.540 and 0.528 on SummEval against 0.372 for the best
  free scorer, best pick on Goyal 2022's CNN set 0.52 and 0.54 against 0.33 by chance, at most $15.00.
- The validation is shown as stored; running one stays a tool (`tools/validate_judge_*.py`), not in the Workbench in
  0.8.0 (D6). Live: `scorer-list`, `scorer-new`, `scorer-set`, `POST /estimate` on `judge-score` (its dry run),
  `judge-score` (a job), `cost-report`.

### W8 Settings

- Rare, so terse, one row each with its command: where the project keeps its data (`data-migrate`, a job; the
  server answers 503 with Retry-After while it moves), bringing the data to this release's format (`migrate`),
  checking the project (`validate`: a read of about 27 s, shown as "checking…", D1), committed runs and their floors,
  the goal policy, budgets (files under `data/`: `data-show`, `data-put`), publishing a dataset (`dataset-publish`).
- `config.yaml` (the exposure check's repos, for one) is not edited here in 0.8.0 (D9): `data-put` writes only under
  `data/`.

## Round 5: what 0.8.0 built after round 4

The owner asked (2026-11-12) for the mockups to follow the code built since round 4. Everything below is the harness's own answer, made by
`harness/workbench/round5_inputs.py` in throwaway projects (the tutorial's tickets and the replay example), because
this project holds no held-out side, study, prompt version, job or replay yet; each screen's "mockup:" note says so.
`round5.js` holds the new screens.

- **The held-out test** (a goal's day-to-day; RFC-029, RFC-031 H1, H2): the seal and what its counts may show; who
  has read it (each read by whom and what, a read recorded by hand, the leak check's find); counts per day by the
  fields fixed at the seal, for safety only; opening it for one candidate (one look); the confirmation, the read items
  left out and the full number beside it, marked.

```text
 The held-out test                                              sup_v1_test
 1 The seal             5 held-out items · sealed · counts by kind
 2 Who has read it      2 of 5 read · agent:homelab 1 · person:owner 1   [ what was read … ] [ Record a read ]
 3 Counts, for safety   day  items  kind=access  kind=bug  kind=question
 4 Open it              look 1: decisions on it are tested one-sided at 1.5198%
 5 The confirmation     the number that counts (2 read items left out)  3 items  +0.0676  p 0.25
                        with the read items kept (not the one that counts)  5 items  +0.0414
```

- **A study** (a goal's day-to-day; RFC-029): what it searches, its trials (kept or dropped against the best so far),
  and its confirmation on the test set as one look.
- **Production · labels from what happened later** (RFC-031 L1-L3, X1, X3): the other system joined by key, window and
  identity; how far the rules label it now (labelled, not yet mature, gone from the source or its id reused); each
  label with when it happened and when it became knowable, and whether it holds only under production's action; the
  labeller's mutants, the survivors flagged.
- **Production · replay the code that ran** (RFC-030, RFC-031 P1, P2): the code record's periods and their
  faithfulness; production's own writes hidden and the replay still agreeing on every decision; a candidate and its
  history confound; period by period, production beside the code that ran then and the candidate.
- **Jobs** (RFC-026): a real job with its cap and the locks it holds; the states a job can be in; `jobs-*`.
- **The eval**: the baseline's version, who promoted it and why, `baselines` and `baseline-rollback` (RFC-027); a
  round's close records who. **Models**: the prompt a person writes is saved as a prompt version, named by its
  content (RFC-028). **Settings**: `evh migrate` after an upgrade; the public repos the leak check searches.
- **The eval, after its critique** (owner, 2026-11-12: the decision moment first; a promotion is refused with the fix,
  not warned):
  - "The answer so far" is the standing answer (r1's, with its cost guidance); a closed round amends it under it
    ("r4 added: …") instead of replacing it, and the kicker names the baseline the latest round left (owner,
    2026-11-12).
  - The comparison names its correction (Holm across 28) and shows each arm's raw p and its Holm threshold, the two
    figures the harness reports (`stats.holm`; it never reports an adjusted p), a "<0.0001" held below an exact
    0.0001 as the true p's would be; its verdicts use r4's words ("significantly worse", not the harness's "significant:
    worse"); "coverage, best first" is a descending sort, and says so to a screen reader ("not significantly different"). On a phone, where the table's head is hidden, a sort
    menu sits above the cards.
  - An arm is opened by its name, a button, and its panel opens as the row under it. The chart's dots are for the
    mouse; the table is the keyboard and screen-reader path (a dot in the tab order would repeat every arm button).
    On a phone the chart is drawn again for the phone (a viewBox about the width it is drawn at, every other
    coverage tick, no names on the dots), so its words stay 12px and none collides or is cut. Escape closes an arm's
    panel (after the help panel, when that is open).
  - Focus goes where each action leads: an arm's name after opening or closing it; the question after opening a
    round; the results after its run; the row after a retire; the new answer, in view, after a close.
  - The rounds are a tab list with a panel and arrow keys.
  - A round's run, its job and its status count the same arms.
  - Round r4 is built from the local arms the project has re-runs of (owner, 2026-11-12, after the re-critique), so
    every result on it is real. The models picked in step 4 that have no re-run in the project are named in the
    round's arms part, in body text and its status line: they stay in r1, where they were compared.
  - Its results compare each arm's Linux re-run with bart_l's Linux re-run (the pair tests' baseline), so speed and
    coverage are from one machine; each row says which run under the arm's name, and its actions sit beside the name,
    so the table fits a desktop screen. The re-runs (2026-09-30) stand in for r4's runs, and a mockup note says so:
    in the harness a run counts in a round only when it is made in it (it records the goal and the round, and joins
    its system's arm), and `evh round-list` would read bart_l, carried in, through its r1 run. bart_l is carried into the round (`round-open --keep`), not run again; the arms part
    counts "5 arms: 4 re-run, bart_l carried", and a closed round's fold "the round's 5 arms".
  - The results open with the round's answer in one line, from the verdicts below it ("No arm was shown ahead of
    bart_l: 3 significantly worse (…), which `evh round-list` suggests retiring; 1 not significantly different (…),
    which more items may tell apart. bart_l leads the round and stays the baseline."), then the correction as a note
    above the table (a phone hides the table's head), then the table and the mockup note.
  - r4's verdicts are the ones `evh round-list` gives (`rounds.evidence`): every arm in play against the round's leader,
    the best mean, Holm across them, each row showing Δ, the raw p and its threshold, with r1's coverage bars.
    The arms in play leave the retired out (`model.rounds.in_play`), so a retire narrows the family and moves the thresholds; a retired row
    says "retired: not tested". The project's pair tests are each arm against bart_l, which leads the round on these
    re-runs. (`evh round-list` tests a leader against the baseline it started from, Bonferroni over the round's arms, only
    when the two differ, to decide whether to suggest promoting it; an earlier version of this screen applied that
    test to every arm, which `evh round-list` never does.)
  - No arm here leads bart_l, so the screen offers no "Make baseline": `evh round-list` would not suggest a promotion,
    and `round-close --promote` takes the round's conclusion as the promotion's reason, so there is no second reason to
    ask for.
  - The baseline cannot be retired. A retire is final: a recorded decision with its reason, which no operation undoes
    (D3); its confirm says so.
  - A prompt opens under its row and names the arm; Enter confirms it, Escape cancels it; a reason under three words is
    an error in the bad status, tied to its field (`round-retire` refuses one). The confirm of a close is an
    alertdialog that restates what it decides, focus on its "Yes, close r4", and Escape backs out of it. Close is
    enabled for a conclusion of three words or more (`round-close` refuses a shorter one), and the hint asks for a
    sentence until then. A clone keeps its fold open and focus on its Remove once added, and an empty value is an
    error; a clone can be removed before the run. The round's question is fixed once the round has run. The answer's
    source is a quiet line under it.
  - The commands are the ones that make the round: `round-open --keep` carries bart_l (in a files project the round
    file is committed before the runs, as `round-open` says), and the new systems run in it as one `sweep` (`--goal`
    and `--round r4`; D2), so each run joins its system's arm. r5's `round-open` keeps bart_l too.
  - Once a round has run its question is its heading (h2), as r1's is; the kicker above it is a line. The close
    confirm keeps Tab between its two buttons.
  - A cost column every arm of which is $0 gives way to one line in the arms part; a local run's button says "local,
    no API cost"; after the run the Run part is its status line. On a phone an arm's actions sit on their own line at
    its card's foot, and the column is named "actions" for a screen reader.
  - The statistics words (raw p, threshold, Holm, Δ) are glossary buttons. r1's table sorts by rank,
    arm, coverage, cost or speed. A command a person opened stays open across redraws. A job's moving count is not
    announced; its start and its end are.
  - On a phone the rail is one line naming the step ("Step 5 of 5 · Eval ▾") that opens to every step, so the screen's
    answer is in view without scrolling past eleven steps.
  - A closed round folds its arms behind one line, says its conclusion once (in the answer at the top), carries it in
    the folded command, and dates the close in local time.
  - A closed round says when it closed and by whom, shows its question as text, and offers its next steps: review the
    outputs, or open the next round. r5 opens from r4's conclusion with its question in focus and the command it
    writes; the project has no runs past r4's re-runs, so the walk-through stops at r5's question and says so.
  - A comparison's leader and a recommended arm are shown in the ok status, not in lime (a result, not an action).
  - A skip link focuses the screen without changing the route; a glossary word is a button that Enter or Space
    opens; the help panel opens with focus on its close button and gives focus back to what opened it; a reason's
    error is tied to its field; the run's progress is announced; the tabs take Home and End.
  - "Close the round" needs a conclusion of a sentence, and is confirmed with a restatement of what it decides.

## Help, for someone who is new to this

Owner, round 2's review: "assume that users don't know all these words … a first-time user who got here and never
used this can really find his way without reading the documentation … a vibe coder, a product manager … while if the
person is an engineer and knows all this stuff, let's not make it too childish". A secondary goal of every screen.

### Three layers, always the same

1. **The step says what it is for.** One sentence under each step's title, always shown: what this step does and why
   it comes now ("A dataset is the set of examples your systems will be tested on. Choose it before anything runs:
   every comparison is only as good as its examples.").
2. **Each field has a one-line hint** under it: what to put, with an example from this kind of project. Short enough
   to read without stopping.
3. **A `?` next to a field or a word opens its explanation** in a side panel (not a tooltip that vanishes): what it
   is, why it matters, a real example, what goes wrong if it is wrong, and "read more" into the docs. The panel stays
   open while the person fills the field.

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
                                                                           │ Read more: Goals ↗             │
                                                                           └────────────────────────────────┘
```

### Words

- The harness's own words are taught, not replaced: a goal, a dataset, an item, a reference set (gold, silver), an
  system, an arm, a run, a round, a baseline, significant, contenders. The first time a word appears on a screen it is
  underlined lightly; pointing at it (or tapping it) shows its one-line meaning, and its `?` the full one.
- A glossary page holds every word, the same text as the `?` panels, linked from each.

### Not childish

- Plain, exact sentences; the real terms with their meaning, never a cute substitute; no emojis, no exclamation marks,
  no "great job".
- Examples are real (this project's, or a well-known public dataset), never "foo".
- **For someone who knows:** every step shows the command it runs, folded (`evh dataset-create --source huggingface
  --query '{…}' --dataset-id cnn_dailymail_200`); hints can be hidden for good ("hide hints", remembered on this
  browser), the `?` stays; nothing blocks a person who fills the fields straight away.

### Where the help lives

- One file of help texts, keyed by step and field, written and reviewed like the docs; the screens read it.
- A check fails when a field or a step has no hint or no `?` text, so help cannot fall behind the screens. (Not
  built yet: it comes with the live screens.)

### Help texts (first draft)

| Where | Hint (always shown) | `?` panel (the explanation) |
| --- | --- | --- |
| Step 0 | — | **What this is.** An evaluation compares systems (a model, a prompt, a setting) on the same examples, and tells you which is better for a decision you have to make, with how sure it is and what each costs. You start with the decision. |
| Step 1, the goal | A goal is the decision this evaluation helps you make. | Everything later is measured against it: which data, which measure, who wins. One goal per decision; a different purpose is a new goal. |
| What is it? | A short title, as you'd say it to a colleague: "Short news summaries (CNN)". | Shown on every page about this goal. Its id is made from it. |
| What is it for? | One sentence: what you want, for whom, so that what. | It keeps the evaluation honest: a system that is better at something you don't need does not win. Example: "Pick a model that writes a short summary of a CNN-style news article, at a known cost, for a reader who wants the story's main points." |
| The decision | The choice you will make from the result. | "Which models can be told apart on summary quality, and what each costs per article." If the result cannot change this choice, the evaluation is measuring the wrong thing. |
| How you'll judge | The number that decides which system is better, and which way is better. | A measure is one number per example (coverage: how much of the reference a summary covers, cut to the reference's own length, so writing more cannot buy it). Higher or lower is better depends on the measure: quality goes up, cost and time go down. |
| How a winner is picked | Balanced suits most goals. | When systems are close, the rule decides who may still win beside the best (the contenders); among them the cheapest wins, then the fastest. **Balanced**: shown no worse than the best by more than 5% of it (a non-inferiority test). **Quality first**: the same quality only. **Frugal**: shown no worse by more than 10%. The margin, the tie-break and other measures are under "advanced". |
| Step 2, the dataset | The examples your systems will be tested on. | A dataset is a frozen list of items (an article, a question, a ticket), each with a hash, so every system sees exactly the same examples, now and later. Use one you have, or make one from a source. |
| a Where from | Where the examples are now. | A folder of files, a table (CSV, JSON lines), a dataset on Hugging Face, Croissant, Zenodo, OpenML or Kaggle, or what your system decided in production (a capture). Public sources are read at one pinned version, so the dataset can be rebuilt exactly. |
| b What's in it | Which column is the example, and which holds the expected answer if there is one. | The item is what a system receives (the article). The expected answer (the highlights) becomes the reference later, in step 3. Take a few hundred to start: enough to tell systems apart, cheap to run. |
| c Its fields | Facts about each item you may want to slice by later. | A field (the source: CNN or DailyMail) lets you see whether a system is better on one part of the data. Proposed from the columns; keep the ones you would compare on. |
| d Name it | A short id, and its role for this goal. | The role: **validation** while you choose and tune, **test** for the final answer, kept untouched until then. |
| Step 3, prepare | Three things the dataset needs before anything runs. | Each is done once per dataset. |
| a Fetch its items | Downloads every item and checks it against its hash. | So a run reads exactly the frozen items, offline, every time. |
| b Look inside | What the items are like: how many, how long, each field's values. | Read a few before running anything: most surprises (empty items, the wrong column, a skewed sample) show here. |
| c Its reference set | The expected answer for each item, that outputs are scored against. | Three ways: the data came with answers (promote them), label them here, or bring a filled sheet (CSV). **Gold** is checked by people; **silver** is a model's answers, consistent rather than correct: enough to rank systems against each other, not a claim about truth. Who and why are recorded. |
| Step 4, models | The systems you compare. Each is checked on three items before it costs anything. | A model with its prompt and settings is a system; placed in a round, it is an arm. A model that fails on three items would fail on all of them, and you would pay for every one. |
| Pick the models | Models already in this project are ready to use; a new one is onboarded once, for every goal. | Onboarding probes a model once: does it answer, how it counts tokens, what it costs, whether it thinks first. vetted, onboarded, check, none. A model with an unread check can fail mid-run, after it has cost money. |
| Their settings | What every arm is given: the prompt, the temperature, the most it may write. | The same for every model, so a difference in the scores is the model's. Change one thing at a time. |
| Check each on three items | Runs each arm on the first three items, the way the full run would, and shows the replies. | An empty, cut-off or wrongly formatted reply shows here for a few cents; the cost of three projects the cost of all. |
| Step 5, the eval | The goal measured on its dataset, in rounds. | Each round asks one question, runs its arms, compares them by the goal's measure and rule, and ends in a decision kept with its reason. |
| The round's question | What this round should find out, in one sentence. | "Does a shorter prompt keep coverage at half the cost?" A round without a question collects runs, not answers. |
| The comparison | Every arm against the best, by the paired test, with what each costs and how fast it is. | "not significant" means the difference may be noise; "significant: worse" means it holds up. Reading the order of the means alone misleads: most neighbours are not significantly different. |
| What this comparison can show | How small a difference these items can tell apart, for this many arms. | With many arms on few items only large differences can be shown; it says what to change: raise the margin, compare fewer arms, or add items. |
| Close the round | What the round showed and what it decided, and the run that becomes the baseline if one does. | The conclusion is kept with the round and shown wherever its goal is. |

### Glossary (first draft)

| Word | Meaning |
| --- | --- |
| goal | The decision an evaluation helps you make, and how a winner is picked for it. |
| dataset | A frozen list of items, each with a hash, that every system is tested on. |
| item | One example in a dataset: what a system receives. |
| reference | The expected answer for one item. |
| reference set | The promoted, governed set of references for a dataset: gold (checked by people) or silver (a model's answers, enough to rank systems, not a claim about truth). |
| label, label set | An answer a person, a model or a rule gave for an item; a label set is many of them, which can be promoted to a reference set. |
| field | A fact about each item (its source, its length) you can slice the results by. |
| measure | One number per item that says how good an output is (coverage, accuracy, cost). |
| system | What is evaluated: a model where it runs, a prompt and settings. It names no dataset: the same system runs on any. |
| arm | A system placed in a round, with the runs it is read through; retired with a reason. |
| run | One pass of a system over a dataset: its outputs, their scores, its cost. |
| round | One comparison of arms on a goal and its dataset, from its question to its decision. |
| baseline | The arm the others are measured against: the current choice, or the simplest one. |
| significant | The difference holds up beyond chance, by the paired test (better or worse); "not significant" means it may be noise. |
| contenders | The arms the goal's rule still lets win: not significantly worse than the best, within its margin. |
| eval | The goal measured on its dataset, in rounds. |
| validation, test | A dataset's role: validation while you choose and tune; test for the final answer, kept untouched until then. |
| gold, silver | A reference set checked by people; one made of a model's answers, enough to rank systems, not a claim about truth. |
| onboarding | Probing a model's deployment once, for every goal: does it answer, how it counts tokens, what it costs. Kept as the deployment's dated checks. |
| vetted | A model whose every deployment passed its onboarding and a system on it passed its smoke. Worked out, never set by hand. |
| coverage | How much of the reference a summary covers, cut to the reference's own length, 0 to 1. |
| capture | What a deployed system decided, kept as records with their hashes, to evaluate and learn from. |
| pick | A production record chosen for the next version of a dataset, with the reason it was chosen. |
| judge | A model that scores outputs the way a person would; it may decide only after agreeing with people's labels. |
| failure mode | A named way an output can be wrong (overlong, narration), so tags are counted rather than re-invented in each note. |

## The data model (RFC-032)

The mock data model of round 3 (an ER diagram and a table beside the mockup, PRD-017's decision 5) is replaced by
RFC-032's entities, built in 0.8.0. What a screen shows is an entity or a view of them; what a person changes goes
through an operation, never a path. Where each lives is the model's (`harness/scripts/model/`), the same keys in
either store:

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

✓ every operation exists, ~ partly, ✗ an operation is missing (API n: PRD-017, "The API to build first"). Checked
against the code on 2026-11-17 (`research/internal/WORKBENCH_GAPS_0.8.0.md` has the detail).

| Screen | Calls | State |
| --- | --- | --- |
| Home | `goal-list`, `goal-status` per goal, `jobs-list` | ✓ live |
| 1 Goal | `goal-new` (with `datasets: []`), `goal-set`, `goal-show`, `goal-history`, `metric-list` | ✓ live (2026-11-17): made from the home, changed from its page (only what changed is sent) |
| 2 Dataset | `dataset-list`, `goal-set`, `source-preview`, `fieldset-propose`, `fieldset-new`, `dataset-create`, `capture-list` | ✓ live (2026-11-17): one the project has, or one from a source (its query, `source-preview`, its fields proposed and kept, `dataset-create` with them and its answers, the goal's role) |
| 3 Prepare | `dataset-materialize`, `dataset-profile`, `dataset-show`, `reference-promote`; labelling: `label-sheet`, `jobs-file`, `label-import` | ✓ live (2026-11-17): fetch, look inside, promote a label set (the dataset's own answers too); "Label it here" fills the sheet on the page and submits it when done; items have no offset and limit |
| 4 Models | `model-list`, `model-show`, `system-list`, `system-show`, `system-new`, `prompt-version`, `arm-smoke` | ✓ live (2026-11-17): a system made from a model where it runs (its endpoint carried into the system), the shared prompt and settings, its prompt recorded as a prompt version beside it (owner: the easier way, the bundled adapter reads `params.prompt`; reviewed again as the build's last step); each model offered with its rank on this goal; a system cloned with one thing changed; each checked on three items with a cap (status, cost, the projection, a reply per item) |
| W5 Bring in a model | `model-new`, `deployment-new`, `model-onboard`, `model-show`, `deployment-history`, `deployment-accept` | ✓ live; no "approve" (D4) |
| 5 / W1 The eval | `round-list`, `round-show`, `round-evidence`, `round-open`, `round-carry`, `POST /estimate`, `sweep`, `round-retire`, `round-close` (`promote`), `baselines`, `baseline-rollback` | ✓ live (2026-11-17): the rounds as tabs, a round's question, arms and evidence (raw p and threshold) with its chart (each arm's mean against its cost); open one (the last one's arms carried in or not), carry an arm in later, see a run's cost, run arms as one sweep under a cap, retire with a reason (final), close with a conclusion and the leader's run promoted; the baseline's versions, rolled back with a reason |
| W2 Review, label, tag | `comparison-items`, `comparison-item`, `sheet-show`, `sheet-export`, `failure-modes-list`, `tag-set-list`, `label-set-list`, `sheet-import` | ✓ the blind sheet as a `sheet-export` job, read back with `export_job` (API 1) |
| W3 Production | `capture`, `arm-from-capture`, `label-from-capture`, `label-coverage-show`, `sheet-show`, `pick`, `dataset-extend`, `periods`, `faithfulness` | ✓ (the coverage's rules file must be in the project) |
| W6 Reference | `reference-list`, `label-set-list`, `reference-promote`, `leaderboard` (`label`), `score-preview`, `rescore` | ✓ `score-preview`'s result (API 4) |
| W7 Judge | `scorer-list`, `scorer-new`, `scorer-set`, `judge-score`, `POST /estimate`, `cost-report` | ✓; validating stays a tool (D6) |
| W8 Settings | `validate`, `migrate`, `data-migrate`, `data-show`, `data-put`, `dataset-publish` | ~ `validate` is a read of about 27 s (D1); no `config.yaml` (D9) |
| Held-out test, study | `dataset-split`, `exposure`, `exposure-add`, `sealed-counts`, `dataset-unseal`, `pair-test`, `looks`, `study-*` | ✓ |
| Jobs | `jobs-list`, `jobs-show`, `jobs-log`, `jobs-file`, `jobs-stop`, `jobs-resume` | ~ progress from four operations |

## For every live screen

- **The session.** The page opens through the Workbench link `evh catalog-serve` prints (it signs in once); the token is new at every server
  start, so a page left open answers 401 on any call after a restart, and says to open the new link.
- **Writes.** Every call that is not a GET sends `X-EVH-Data: 1`; an upload is base64 JSON, at most 50 MB a call.
- **Refusals**, shown where the action was: an edit's problems on their fields (`{error, kind, problems}`); a job
  refused before it exists (`{error}`); a job that failed later (its state, its refusal's kind, its log); 503 with
  Retry-After while the data is moved or migrated, retried after it. An unhandled server error is always a JSON 500
  (API 6, built).
- **Who acted.** The name is asked once and kept in the browser; every write sends it (`by`), every decision its
  reason.
- **Kinds.** A read answers at once; an edit or a quick decision answers with what was saved; work is a job (its
  estimate first where it spends, its cap, then its progress).
- **Phones.** Every screen at 390 px (owner, 2026-11-12): tables of four columns or more become cards; the two- and
  three-column tables, the forms and the jobs list are checked there too.
- **Behind a proxy** the Workbench and `/api/v1` answer 404 in 0.8.0 (D8).
- **Unsent changes** (owner, 2026-11-17). What a person enters is sent only by the screen's own action (Save,
  Create, Run, Submit); until then the screen holds it and says so. One rule, built once, for every screen:
  - **dirty**: a mark beside what holds unsent changes, from the first change until the action succeeds; the action is
    enabled only then and names what it will write; leaving the screen, closing the page or opening another record asks
    first; on success the mark clears; on a refusal it stays, the problems are shown where they belong, nothing is
    written;
  - **longer work** also counts what is pending ("12 answers not submitted") and keeps it across a reload, in this
    browser only (the screen says so): the labelling sheet (W2, step 3c), the rows picked for the next version (W3),
    the dataset's four steps before Create (step 2), the models and settings picked before their systems are made
    (step 4), and a round being built (its clones and changed values before Run, W1);
  - **forms** saved by one button are marked dirty and ask before leaving, with no memory across a reload: the goal
    (step 1), a model and a deployment (W5), a scorer (W7), a fieldset, a file under `data/` (W8), a round's question,
    a retire's reason and a round's conclusion.
  Built 2026-11-17 for the live forms (a new model, a deployment, a flag accepted): `live.js` marks a form
  (`data-form`), its button (`data-send`) and its mark; `workbench.js` asks before leaving and redraws nothing
  that holds unsent changes; closing the page asks too. The live goal screen has no form yet.

## The order of the build (owner, 2026-11-17)

API 1 to 6 and the unsent-changes rule ("For every live screen") are built (2026-11-17); then the screens: home and goal (live) → W5 (live) → steps 2 and 3 (need API 2 and 3) → step 4 →
W1 the eval → W2 (needs API 1) → W3 → W6, W7 and W8 as short lists → the held-out test and studies → last, a review of how
the Workbench keeps prompts (owner, 2026-11-17). The mockup's
"mockup:" notes go with the screens that replace them.
