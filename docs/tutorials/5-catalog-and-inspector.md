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
catalog: .../my-evals/.build/catalog — 1 goals, 1 datasets, 4 arms, 1 references
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
| the catalog's index: every dataset, its items, arms and references | `evh datasets` |
| a dataset page: its versions, references and every arm with its headline number | `evh datasets --dataset-id tickets_v1` |
| a reference page: who wrote it, from which run, every arm scored against it | `evh references --reference-id silver/tickets_v1` |
| the metrics page: what each metric measures, which way is better, where it is recorded | `evh metrics` |
| the goals page, and one goal's page: its answer (the baseline and why), its arms per dataset, its rounds | `evh goals`, `evh goals --goal tickets_summary`, `evh rounds --goal tickets_summary` |
| the inspector: arms tested against a baseline, and whether they ran under the same conditions | `evh inspect --runs tickets_lead1_v1,tickets_lead2_v1` |
| the inspector, filtered by a field, or broken down by one | `--where area:account`, `--by deadline` |
| the inspector, one item: the item itself, its fields, each arm's output beside the reference | `--item t01_login` |
| the inspector over a round's arms ([tutorial 4](4-rounds-and-versions.md)) | `evh inspect --round r2` |

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
they are scored against (gold, silver, a judge). Arms are ranked only within a group, and a
group's leader is never an arm graded against its own outputs.

The inspector's comparison:

```bash
evh inspect --runs tickets_lead1_v1,tickets_lead2_v1
```
```text
overlap_f1 (higher is better) · baseline tickets_lead1_v1 ×3: mean 0.641 · Holm across 1
  ...
  tickets_lead2_v1 ×3  separated: better  6  0.900  0.259  6–0          0.03125  0.0500

Same conditions: all 15 recorded fields match (machine, libraries, harness, scorer, items, reference bytes).
```

The same paired test as `pair-test`, from the same code, so the same p. The last line compares
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
  true      tickets_lead2_v1 ×3  not separated  2  0.285  0.5
  false     tickets_lead2_v1 ×3  not separated  4  0.246  0.125
```

Two tickets name a deadline and four do not, and on two tickets no test can reach 0.05: a
breakdown needs items in every group, and the page says when it has too few.

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
Customer reports they cannot log in since this morning.
```

## 4. What the pages show, and what they refuse

- **The catalog** is static pages: one per dataset with every arm and its headline number, a
  goals page and a page per goal, a page per reference, and a metrics page. Each arm's row says
  what it is scored against; rows scored against silver, by a judge, or against the reference
  the arm wrote itself are tinted. Counts and means only, never an item's text, so the pages can
  be published. The dataset page lists its fields and how many tickets fill each; it summarises
  the values of a field marked `public` (Area, Plan) and no other (Names a deadline).
- **The inspector** is the server behind them, on 127.0.0.1 only. Pick arms on one dataset and it
  tests each against a baseline, charts the per-ticket scores, and for one ticket shows the
  ticket, its fields and each arm's output beside the reference.
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
