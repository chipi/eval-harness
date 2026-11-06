# UXS-005: The Workbench (sketches, round 2)

- **Status**: Draft — sketches for review (owner, 2026-11-06: "agree on the structure … see some sketches … then a
  mock-up"); 0.8.0
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-017](../prd/PRD-017-workbench.md) (the Workbench: workflows, decisions)
- **Related UX specs**: [UXS-001](UXS-001-catalog.md) (the catalog: shell, tokens), [UXS-002](UXS-002-inspector.md)
  (the inspector), [UXS-003](UXS-003-cli-and-onboarding.md) (commands)

Low-fidelity sketches, in the order a person works (owner, round 1's review: "start from the beginning: you set a
goal, you have a dataset for it, you do something with the dataset, and then you go into the experiment"): an empty
project, the goal, its dataset, preparing the dataset, then models and the experiment. How often a step happens
decides how much thought it gets, never its place in the order. One example runs through it: this repository's
real CNN summaries goal (`news_summary_cnn`: its title, statement, decision and measure) and its dataset from Hugging
Face (`abisee/cnn_dailymail`, the 3.0.0 test split's 11,490 rows, the first 200 the committed runs measured). Values
not read from the project are left out rather than invented; the round sketched at the end is made up to show the
screen.

## The shell

```text
 [eval] Workbench · harness                       Goals   Running (1)   Models   Data   ·  Catalog ↗   ◐
```

- The Workbench is its own app on the catalog's server (`/workbench/`), with the catalog's look (UXS-001) and a
  link to it. Its menu is about doing: **Goals** (home), **Running** (jobs), **Models**, **Data** (datasets, labels,
  references). The catalog stays where results are read.

## 0 An empty project: one way in

```text
 Workbench · my-project                                     Goals   Running   Models   Data   Catalog ↗

            What should this project help you decide?

            An evaluation starts with a goal: the decision you need to make, and how
            you will know which system is better for it.

                                  [ Start with a goal ]

            already have data or runs?  import a dataset · open the catalog
```

- With no goal there is one thing to do. The menu is there, its pages empty with the same single way in.

## 1 The goal

```text
 New goal                                                                       step 1 of 5
 ①Goal ─ ②Dataset ─ ③Prepare ─ ④Models ─ ⑤Experiment

 What is it?        [ Short news summaries (CNN)                                             ]
 What is it for?    [ Pick a model that writes a short summary of a CNN-style news article, at ]
                    [ a known cost, for a reader who wants the story's main points.            ]
 The decision       [ Which models can be told apart on summary quality, and what each costs   ]
                    [ per article.                                                             ]
 How you'll judge   measure [ coverage           ▾ ]   (•) higher is better  ( ) lower is better
 How a winner is    (•) balanced — not worse than the best, within its margin, then the cheapest
 picked             ( ) frugal   ( ) quality first                         advanced ▸ (margins, axes)

                                                       [ Cancel ]   [ Save and add its dataset → ]
```

- Five things, on one screen; everything else in a goal (axes, tie-breaks, guardrails, output contract, links) is
  "advanced" or comes later from the steps that own it (datasets in step 2, references in step 3).
- The id is made from the title and shown small (`news_summary_cnn`), changeable before saving.
- The measure offers the metrics the project's scorers produce; a new one can be typed.

After saving, the goal's page is the hub of the journey: the same five steps, each with its state and its next action.

```text
 Short news summaries (CNN)                                                  news_summary_cnn
 decides coverage (higher is better) · balanced                                        [edit]

 ①Goal ✓   ②Dataset ○   ③Prepare ○   ④Models ○   ⑤Experiment ○

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
 a Where from     Hugging Face   repo [ abisee/cnn_dailymail ]  config [ 3.0.0 ]  split [ test ]
                  pinned to the commit it reads (shown once read) · licence apache-2.0   [ Read it → ]

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

- Each source asks only what it needs (a folder: its path and which files; a table: its file and columns; a
  capture: which one). Preview before anything is written; fields are a table, proposed, never typed from nothing.
- **Create** is a job (`dataset-create`): it freezes the items and their hashes. The goal's step 2 turns ✓.

## 3 Prepare the dataset

```text
 ③ Prepare  cnn_dailymail_200                                                   step 3 of 5

  a Fetch its items        ✓ materialized · 200 of 200 · hashes match        (dataset-materialize)
  b Look inside            ✓ profiled: 200 items · words per item · each field's values
                           [ open the items ↗ catalog ]
  c Its reference          what an output is scored against
                           ( ) it came with one: highlights → promote as  [ gold ▾ ]  [ Promote ]
                           ( ) label it here                          [ Open the labelling screen ]
                           ( ) import labels from a sheet (CSV)       [ Choose a file ]
                           who [ you ]   why [ the dataset's own highlights, as published ]

  Ready when: fetched ✓  looked at ✓  a reference ✓          [ Next: the models → ]
```

- One screen with the three things a dataset needs before an experiment; each is a job or a small choice, done in
  order, each showing its result.
- **Labelling here** opens the in-app labelling screen (W2, to sketch); a CSV round trip stays the other way in.
- A reference's promotion records who and why (governance).

## 4 Models (to sketch next)

Bring in a model the experiment will use: what it is, where it runs, onboarded (the probes), approved. A project with
models already onboarded picks from them and skips this step.

## 5 The experiment: a round

The experiment is a round on the goal and its dataset: its arms, their runs and scores, and the decision. This is
where people spend most of their time, so it gets the most thought; round 1's sketch of its board stays as the
starting point:

```text
 news_summary_cnn / round r2 · open (an example)                       budget $5.00 · spent $0.00
 Question  Does a shorter prompt keep coverage at half the cost?                         [edit]

 1  ARMS      rows: clone and change one thing · carry from r1 · new from a model      [ + Add arm ▾ ]
 2  RUN       one button, the estimate first, then progress per job                     [ Run 2 arms ]
 3  RESULTS   the goal's comparison as arms finish; retire · promote baseline · close the round
```

## The mock data model (round 2: unchanged)

What the screens above show and how it links; the files and the database keep it as they keep it today until the
data-model RFC decides. Reviewed with the mockup (PRD-017, decision 5).

```mermaid
erDiagram
    GOAL ||--o{ ROUND : "is decided in"
    GOAL }o--o{ DATASET : "is measured on (role: validation, test, pilot)"
    GOAL ||--o{ SCORER : "is scored by"
    DATASET ||--o{ DATASET : "v2 from v1"
    DATASET }o--|| SOURCE : "is made from"
    DATASET ||--o{ ITEM : has
    DATASET }o--o| FIELDSET : "its items carry"
    DATASET ||--o{ LABELSET : "is labelled in"
    LABELSET ||--o{ REFERENCE : "is promoted to (silver, gold)"
    MODEL ||--o{ DEPLOYMENT : "runs on"
    DEPLOYMENT ||--o{ ONBOARDING : "is checked by"
    ARM }o--|| DEPLOYMENT : runs
    ARM }o--|| PROMPT : uses
    ARM }o--|| DATASET : "runs on"
    ARM ||--o{ RUN : "is run as (repeats)"
    ROUND }o--o{ ARM : "compares (kept, retired, carried)"
    RUN ||--o{ SCORE : "is scored (by scorer, on reference)"
    SCORER ||--o{ JUDGE : "has (a judge scorer)"
    JUDGE }o--|| DEPLOYMENT : "calls"
    JOB }o--o| RUN : "makes"
```

| Entity | What a person sets | What commands write | Today it lives in |
| --- | --- | --- | --- |
| Goal | title, what it is for, the decision, the measure and direction, the winner rule (a named default) | — | `goals/<id>.yaml` |
| Round | its question, budget, which arms; the decision and conclusion | when opened and closed | `rounds/<goal>/<r>.yaml` |
| Dataset | its source, name, fields | items, hashes, version lineage, profile | `datasets/`, `materialized/`, `sources/`, `profiles/` |
| Model / Deployment | what it is, where it runs, endpoint, settings | onboarding, capabilities, smokes, history | `models/<id>.yaml` |
| Arm | dataset, deployment, prompt, the settings it varies | its config id, version | `configs/<id>.yaml` |
| Prompt | its text | its hash | a file named by the config |
| Run | — (it is made by running an arm) | outputs, rows, metrics, cost, fingerprint | `runs*/…` |
| Label set / Reference | labels (in the labelling screen), who and why for a promotion | hashes, counts | `labels/`, `references/` |
| Scorer / Judge | which judges, prompt, mode | validation numbers, verdicts | `scorers/`, `judge-*/` |
| Job | which step to run | status, progress, log, cost | — (new: RFC-026) |

## To review in this round

1. The order: an empty project, the goal (step 1), its dataset (2), preparing it (3), models (4), the experiment (5),
   with the goal's page as the hub that shows the five steps and their state.
2. The goal in five inputs, the rest advanced or owned by later steps.
3. The dataset in four short screens (where from, what's in it, its fields, its name), preview before writing.
4. Preparing as one screen of three things (fetch, look, reference), with the three ways to a reference.
5. The data model (unchanged from round 1).

Not sketched yet: step 4 (models), the experiment in detail, the labelling screen, production (W3).
