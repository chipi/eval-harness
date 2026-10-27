# Tutorial 5 · The catalog and the inspector

Tables answer the questions you thought to ask. To look around, the harness builds a
**catalog** (static pages over your runs) and serves an **inspector** beside it (a local server
that tests any arms against a baseline, item by item, and shows one item's outputs side by side).
**Everything they show is also an `evh` command**, computed by the same code, so the numbers
match: the pages are a comfort, not the only way in.

This tutorial starts from the project [getting started](../GUIDE.md) leaves, offline, and
`make guide-check` runs it as written. It first gives the tickets some **fields**, so the
inspector has something to filter and break a comparison down by.

## 1. Fields: what you know about each item (optional)

What you know about each ticket (the part of the product it is about, the customer's plan,
whether it names a deadline) is a **field**. You declare fields yourself, in a field set; the
harness defines none. `data/fields/tickets.yaml` gives each field a type (`choice` with its
values, `boolean`, `number`, `integer`, `duration`, `date`, `url` or `text`) and says whether it
is `required` and `public`. Values come from a CSV or JSONL, one row per item:

```bash
cp tutorial/fields/tickets.yaml data/fields/
evh dataset-create --dataset-id tickets_v1 --update-fields --fieldset tickets \
    --fields tutorial/ticket_fields.csv
git add data/fields data/datasets && git commit -qm "tickets_v1: fields"
```
```text
data/datasets/tickets_v1.json  fields updated on 6 item(s); the items, and so every run measured on them, are unchanged
```

A column the field set does not declare, or a value of the wrong type, is refused. The run
fingerprint hashes the items' bytes, not their fields, so adding or correcting fields
invalidates no run. A new dataset takes them at creation (`evh dataset-create … --fieldset
tickets --fields …`); items that live at a URL come in through `--manifest`
([RUNBOOK §2](../../harness/docs/RUNBOOK.md#2-freeze-a-selection)).

## 2. Build the catalog, start the inspector

```bash
evh catalog
```
```text
catalog: .../my-evals/.build/catalog — 1 goals, 1 datasets, 4 arms, 4 configs, 1 references
inspect: evh catalog-serve, then open the address it prints
```

<!-- guide-check: background -->
```bash
evh catalog-serve
```
```text
catalog: http://127.0.0.1:8765/.build/catalog/   (Ctrl-C to stop)
  it reads the runs once: restart it to see runs made after it started
```

Open the address it prints (if another program holds port 8765, add `--port 8766`). It reads the
runs when it starts, so after a new run, stop it and start it again.

## 3. Every page, and its command

| what you look at | in the terminal |
|---|---|
| the home page: the tiles with their trends, goals at a glance, activity and spend, coverage, what was recorded | `evh overview` |
| the activity page: runs, spend and tokens by dataset, arm and kind | `evh activity` |
| the arms and configs page: every arm, grouped and filtered; every config with its rank on each goal | `evh arms --by config`, `evh arms --configs` |
| the catalog's datasets page: every dataset, its items, arms and references | `evh datasets` |
| a dataset page: its versions, references and every arm with its headline number | `evh datasets --dataset-id tickets_v1` |
| an arm page: its metrics, runs, config, conditions, rounds | `evh arms --arm tickets_lead1_v1` |
| a reference page: who wrote it, from which run, every arm scored against it | `evh references --reference-id silver/tickets_v1` |
| the metrics page: what each metric measures, which way is better, where it is recorded | `evh metrics` |
| a metric page: what it measures, its kind, the goals it decides, per-dataset strip chart | `evh metrics --metric overlap_f1` |
| the search box on every catalog page | `evh search lead2` |
| the goals page, and one goal's page: its answer (the baseline and why), its arms per dataset, its rounds | `evh goals`, `evh goals --goal tickets_summary`, `evh rounds --goal tickets_summary` |
| the period chips on any of these pages: what is new and what changed in the last 30 days, this week, … | `--period 30d` (or `week`, `month`, `all`, …) on `evh overview`, `activity`, `datasets`, `goals`, `references`, `metrics`, `arms` |
| a goal page's suggested next steps, each with a copy button | the commands `evh rounds --goal tickets_summary` prints |
| a goal page's inspect button on a round: its arms against its leader ([tutorial 4](4-rounds-and-versions.md)) | `evh inspect --round r2` |
| the inspector: arms tested against a baseline, and whether they ran under the same conditions | `evh inspect --runs tickets_lead1_v1,tickets_lead2_v1` |
| the inspector, filtered by a field, or broken down by one | `--where area:account`, `--by deadline` |
| the inspector's per-item table: every item's score per arm, and its Δ against the baseline | `--items` |
| the inspector's analysis charts, as numbers: the spread per arm, the difference from the baseline, each arm's mean against a second metric | `--analysis`, `--analysis --x latency_ms` |
| the inspector, one item: the item itself, its fields, each arm's output beside the reference | `--item t01_login` |

A goal's page, in the terminal:

```bash
evh goals --goal tickets_summary
```
```text
  decision   Which summariser to use for the queue view.
  decides    overlap_f1, higher is better

the answer so far:
  ...
tickets_v1 · dev

  scored against silver/tickets_v1
  ...
```

It leads with its answer: the promoted baseline on each dataset and why (or "no decision yet",
with the command that makes one), then what the goal is for, then the arms in groups by what
they are scored against: gold, silver, and one group per judge ("scored by judge <scorer>"). A
judged arm records its judge's score rather than the goal's measure, so its group is read on that
score, never ranked beside the others. Arms are ranked only within a group, and a group's leader
is never an arm graded against its own outputs. An arm whose config names this goal is tagged
"filed under this goal"; the others record the goal's measure on one of its datasets without
naming it. When the goal has rounds, the page shows them newest first: each with an inspect
button that opens its arms against its leader, the open round's suggestions each with a copy
button, and retired arms greyed out, "retired in rN". `evh goals --goal` prints the same groups,
marks a retired arm `[retired in rN]`, and ends with one line per round (its status, arms,
retired and conclusion); `evh rounds --goal` has the evidence in full. (This project has no
rounds yet; [tutorial 4](4-rounds-and-versions.md) makes them.) Every field a goal file can
have: [RUNBOOK §4c](../../harness/docs/RUNBOOK.md#4c-the-goal-file-field-by-field).

Each group also says what the goal recommends, and why. Beside quality, every goal weighs cost
(dollars and tokens per item) and speed (latency p50 and p95): a column each, and a chart of
quality against each. The rule ([ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md)): an
arm past a limit is out; a flagged or retired arm is never recommended; the goal's strategy
says who is tied with the quality leader (by default `balanced`: not separated by the paired
test and within 2% of it); among the tied, the cheaper wins, then the faster. The reasons
list each step, so the page says why it recommends what it does. A goal changes the rule in its
`success_criteria`:

```yaml
success_criteria:
  primary: {measure: overlap_f1, direction: higher}
  axes:
    speed: {limit: 500}                 # ms, on the p95: a slower arm is out
    quality: {margin: 0.05}             # tied if within 0.05 and not separated
  strategy: balanced                    # or quality_first, or frugal
  tie_break: [cost, speed]
  guardrails:
    - {name: no PII, rule: a summary never quotes an email address}
```

`evh goals --goal tickets_summary` prints the same columns and the recommendation with its
reasons; the home page's glance, and `evh overview`, show each goal's recommended arm with its
cost and speed against the baseline.

The search box on every page, in the terminal:

```bash
evh search lead2
```
```text
  kind     name                       about                    see it with
  arm      tickets_lead2_noisy_v1 ×3  tickets_v1 · overlap_f1  evh inspect --runs runs/tickets_v1/tickets_lead2_noisy_v1
  arm      tickets_lead2_v1 ×3        tickets_v1 · overlap_f1  evh inspect --runs runs/tickets_v1/tickets_lead2_v1
  dataset  tickets_v1                 4 arms                   evh datasets --dataset-id tickets_v1
```

It searches datasets, arms, references, metrics and goals, ranked as the catalog's search box
ranks them, and each hit comes with the command that shows it.

The inspector's comparison:

```bash
evh inspect --runs tickets_lead1_v1,tickets_lead2_v1
```
```text
overlap_f1 (higher is better) · baseline tickets_lead1_v1 ×3: mean 0.641 · Holm across 1
  ...
  tickets_lead2_v1 ×3  separated: better  6  0.900  0.259  +0.140 to +0.423  6–0          0.0312  0.0500

Same conditions: all ... recorded fields match (machine, libraries, harness, scorer, items, reference bytes).
```

The same paired test as `pair-test`, from the same code, so the same p. `family-test` agrees with
both up to 30 items, where every p is exact. Above 30 each is a seeded estimate, and
`family-test` draws one random stream for its whole family where the inspector and `pair-test`
draw one per pair, so its p can differ from theirs in the third decimal (on 32 items: 0.0297
against 0.0327); `family-test` says which kind of p it printed. Every p is printed to four
decimals, and `<0.0001` for what would print as 0.0000. `wins–losses` is each row's arm against
the baseline; `family-test`'s column is `A wins`, the items its A wins against each opponent. The
last line compares
the runs' fingerprints: the machine, library versions, the harness, the scorer, the items and
the reference's bytes. When they differ it names the fields, arm by arm, and warns when the
scorer or the reference differs (different measurements) or latency is compared across machines.

**Fields in a comparison.** Filter it to the tickets whose field matches, or break it down by a
choice or yes/no field: the paired test within each group, Holm-corrected over every group
together.

```bash
evh inspect --runs tickets_lead1_v1,tickets_lead2_v1 --by deadline
```
```text
NOTE: Broken down by deadline: 2 tests, Holm-corrected together, so a group is held to a stricter threshold than it would be alone.
  ...
by deadline (Holm across 2):
  deadline  run vs baseline      verdict        n  Δ      p
  true      tickets_lead2_v1 ×3  not separated  2  0.285  0.5000
  false     tickets_lead2_v1 ×3  not separated  4  0.246  0.1250
```

Two tickets name a deadline and four do not, and on two tickets no test can reach 0.05: a
breakdown needs items in every group, and the page says when it has too few.

**Item by item, and the charts as numbers.** `--items` is the inspector's per-item table, and
`--analysis` its charts (`--x` adds each arm's mean on a second metric, the scatter):

```bash
evh inspect --runs tickets_lead1_v1,tickets_lead2_v1 --items
evh inspect --runs tickets_lead1_v1,tickets_lead2_v1 --analysis --x latency_ms
```
<!-- guide-check: varies latency_ms -->
```text
per item (overlap_f1; Δ is each arm minus the baseline):
  item         tickets_lead1_v1 ×3  tickets_lead2_v1 ×3  Δ tickets_lead2_v1 ×3
  t01_login    0.450                0.873                +0.423
  t02_invoice  0.457                0.851                +0.394
  ...
spread per run (overlap_f1, one line per arm):
  arm                  mean   spread over the items
  tickets_lead1_v1 ×3  0.641  min 0.450  p25 0.498  median 0.687  p75 0.766  max 0.795
  tickets_lead2_v1 ×3  0.900  min 0.851  p25 0.880  median 0.906  p75 0.922  max 0.940

difference from the baseline (tickets_lead1_v1 ×3), per item:
  arm                  mean Δ  spread of Δ over the items
  tickets_lead2_v1 ×3  0.259   min 0.140  p25 0.146  median 0.227  p75 0.372  max 0.423

overlap_f1 against latency_ms, each arm's mean (the scatter's crosses):
  arm                  overlap_f1  latency_ms  items
  ...
```

Each command prints the comparison first, then its table or its charts. `--x` takes a metric the
arms record per item; here that is `latency_ms` (a length such as `output_words` is not
recorded per item, and the command names what is).

**One item**, as every arm saw it and what each wrote:

```bash
evh inspect --runs tickets_lead1_v1,tickets_lead2_v1 --item t01_login
```
```text
  Area: account
  Plan: business
  Names a deadline: True

== t01_login (the item itself)
  ...
== silver/tickets_v1 (reference)
  ...
== tickets_lead1_v1 ×3  (baseline)
(run tickets_lead1_v1_..._r3 · shown the latest of 3 repeats; the score is the mean of all 3)
Customer reports they cannot log in since this morning.
```

## 4. What the pages show, and what they refuse

- **The catalog** is static pages: a home dashboard with counts, goals at a glance, activity and
  spend charts, and everything recorded; a datasets page and one per dataset with every arm and
  its headline number; one per arm showing its metrics, runs, config and conditions; a goals
  page and one per goal; one per reference; a metrics page and one per metric. The datasets
  page counts the arms and the configs behind them: an arm is one config on one dataset scored
  one way, so a config rescored against silver or judged is an arm of its own ("N arms on M
  datasets, from K configs"; `evh datasets` has a `configs` column). Each arm's row says what it is scored
  against; rows scored against silver, by a judge, or against the reference the arm wrote itself
  are tinted. The dataset page (and `evh datasets --dataset-id`) sorts its arms by what they are
  scored against first, gold, then silver, then each judge, then none, and only then by metric
  and mean, so a silver mean and a gold one never interleave. Counts and means only, never an
  item's text, so the pages can be published. The dataset page lists its fields and how many
  tickets fill each; it summarises the values of a field marked `public` (Area, Plan) and no
  other (Names a deadline). A metric page shows what the metric measures (from the adapter's
  `METRIC_DESCRIPTIONS`, with summary and details when present), which way is better, which
  goals decide on it, and every arm's mean on each dataset in a strip chart and table.
- **The inspector** is the server behind them, on 127.0.0.1 only. Pick arms on one dataset and it
  tests each against a baseline, lists and charts the per-ticket scores, and for one ticket
  shows the ticket, its fields and each arm's output beside the reference. An arm run three
  times shows its latest repeat's output, and the page says so ("the latest of 3 repeats; the
  score is the mean of all 3"); `--item` prints the same, under each arm's heading, as
  `(run <run_id> · shown the latest of 3 repeats; …)`, and `(run <run_id>)` for an arm run once.
- **Its refusals** are the tests' refusals: no comparison across two datasets, and on a metric
  scored against a reference, no arm scored against another reference than the baseline's (a
  silver-scored run against a gold-scored one).

**No code needed here**, because this project keeps its data in the harness's layout
(`data/datasets/`, `data/runs*/`, `data/references/`, `data/goals/`). If your runs live in
another layout, write one adapter that answers the catalog's questions (which arms exist, what
each scored per item, which references exist, what one item looked like) and name it in
`config.yaml`: `catalog: {adapter: path/to/file.py:Class}`. Every command above takes the same
adapter (`evh inspect --adapter path/to/file.py:Class`).
[INTEGRATION](../../harness/docs/INTEGRATION.md#the-catalog-and-the-inspector) shows how.
