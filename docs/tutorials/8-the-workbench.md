# Tutorial 8 · The Workbench

The catalog is where results are read. The **Workbench** is where the work is done: a goal set, a dataset made and
prepared, systems made and checked, rounds run and decided, outputs reviewed, production learned from, a held-out
test opened once. It is the same loop the command line runs: **every screen calls the operations the `evh` commands
are**, and every action shows "the command this runs" beneath it, so anything done on a screen can be done, scripted
or reviewed in a terminal, and the other way round.

This tutorial starts from the project [getting started](../GUIDE.md) leaves. It opens the Workbench and walks its
screens in the order a goal goes through them.

## 1. Open it

The server that serves the Workbench also serves the catalog's pages, so it starts once they are built:

```bash
evh catalog
```
```text
catalog: .../my-evals/.build/catalog — 1 goals, 1 datasets, 4 arms, 4 systems, 1 references
inspect: evh catalog-serve, then open the address it prints
```

<!-- guide-check: background -->
```bash
evh catalog-serve
```
<!-- guide-check: varies 127.0.0.1 -->
```text
catalog: http://127.0.0.1:18xxx/.build/catalog/   (Ctrl-C to stop)
  the project .../my-evals, on a port of its own
  each page is rendered when it is asked for, from the data as it is then: a write shows on the next read
```

Its startup also prints a **Workbench** line: a link that signs in once (it carries the server's token, which becomes a
cookie) and opens `/workbench/`. The token is new at every start, so a page left open from before a restart asks you
to open the new link. The token is printed to a terminal only: when the server's output goes to a file (a background
job's log), the line names the token's file instead, `.build/api-token`, and the link takes the token read from it.
A terminal recorder (`script`, asciinema) runs in a terminal and does record the link. The Workbench that writes answers
on this machine only: a server behind a proxy does not serve it, and a server started with `--public` serves it
read-only, to anyone, with nothing that writes, spends or runs a model (RFC-039).

The first time a screen writes something it asks who you are; that name is kept in your browser and recorded with
every change and every job (`person:<name>`).

## 2. A goal's steps

| screen | what you do there | the commands it calls |
| --- | --- | --- |
| **Home** | every goal with where it stands and its next step; what is running | `goal-list`, `goal-status`, `jobs-status` |
| **Set the goal** / **The goal** | the decision, how you will judge, which way is better | `goal-new`, `goal-set` |
| **Add a dataset** | one the project has, or one from a source: its query, a preview, its fields kept, its expected answers | `source-preview`, `fieldset-propose`, `dataset-create` |
| **Prepare the dataset** | fetch the items, look inside, make the reference set; or label the items on a sheet and submit it | `dataset-materialize`, `dataset-profile`, `label-sheet`, `label-import`, `reference-promote` |
| **Choose the systems** | a system from a model where it runs, its prompt and settings; a clone with one thing changed; each checked on three items under a cap | `system-new`, `prompt-version`, `arm-smoke` |
| **Its rounds** | rounds: a question, its arms run as one sweep under a cap, the evidence, an arm retired with why, the round closed and its leader promoted | `round-open`, `sweep`, `round-carry`, `round-retire`, `round-close`, `baseline-rollback` |
| **Review the outputs** | two arms side by side: which is better (blind), or what went wrong (tags from a failure-mode list) | `sheet-export`, `sheet-import`, `failure-modes-new` |
| **Learn from production** | records captured and made a dataset, production's decisions scored as an arm, the rows where it was wrong picked for the next version, labels from what happened later, a replay of the code that ran | `capture`, `dataset-from-capture`, `arm-from-capture`, `sheet-show`, `pick`, `dataset-extend`, `label-from-capture`, `faithfulness` |
| **Change the reference set** | what another label set moves before anything is promoted; promoted with why; a scoring change previewed | `rescore`, `reference-promote`, `score-preview` |
| **A judge for this goal** | its judges and their validation as stored, its cost first, then the arms judged under a cap | `scorer-new`, `scorer-set`, `judge-score`, `cost-report` |
| **The held-out test** | a dataset split and its test side sealed (the screen seals by default; `evh dataset-split` leaves the side open unless given `--seal`, and a goal's `role: test` dataset is a test set either way, shown as "not sealed"); its reads recorded and the leak check; counts for safety only; opened for one candidate (one look); the confirmation with the read items left out | `dataset-split`, `exposure-add`, `exposure-check`, `sealed-counts`, `dataset-unseal`, `pair-test` |
| **Studies** | a search over one thing at a time on the validation items (`study-run` opens a round of the goal on that dataset, recorded with the study, and closes it when the study ends; it does not count against the one-open-round rule), its trials and best, an agent's proposals asked and told, confirmed once on a test set | `study-run`, `study-ask`, `study-tell`, `study-stop`, `study-confirm`, `study-import` |

On a goal's screens a **rail** on the left lists the goal's five steps, each marked done, current, open or locked from
what the project holds, and what a step not done lacks ("not fetched", "no reference set", "1 of 2 systems with runs");
a locked step leads back to the goal's page, and on a narrow screen the rail folds to "Step N of 5". A **?** beside a
field or heading opens a side panel (what it is, why it matters, an example, what goes wrong, a link to the docs), and a
harness word is underlined the first time it appears: point at it for its meaning, click for the panel. The **Words**
page lists them all.

The models (bring one in, add where it runs, run its probes, accept a flag with why), the **Jobs**, the **Prompts** and
the **Settings** are on the home page's bar.

The evidence is drawn where it is read (RFC-034), each chart with its numbers folded under it and the `evh chart`
command that answers the same: on **The eval**, the round's arms against where it started, the difference in quality
against the difference in cost, a quadrant named only for a difference the tests support, then every arm against the
leader with its interval, where they differ item by item and their latency; on a **study**, its trials and the best so
far; on **A judge**, what each judge said and why, the lowest scores first, and its judges' controls; on the **goal**,
its baseline over time; on **Prepare it**, how many items the order needs and whether the label sets agree.

## 3. What it keeps for you

- **Nothing you type is lost and nothing is half-sent.** A form you changed is marked "not saved yet", its button says
  what it will write, and leaving the screen asks first. Longer work (a dataset being described, a sheet being filled,
  a system being made, a study's spec) is kept in your browser until it is sent; a label sheet is submitted whole,
  never item by item.
- **Whatever runs is a job**, with what it may spend first where it spends. A job keeps running if you close the page:
  the **Jobs** page lists every job, filtered by state, operation and goal, and shows one job's progress, result, the
  files it wrote and its log; a running job is stopped there, and a stopped run resumed with what it left of its cap.
- **A refusal says why, where you acted**: an edit's problems on their fields, a job's reason under its button.

## 4. Prompts: a manual eval and a study

A system's prompt is kept as **versions**. In step 4 the prompt you type is recorded as a version of the goal's prompt
(`<goal>/prompt`) and the system points at it; a clone with a changed prompt records a new version made from the one
before. Every run records the version it sent. A study changes prompts the same way: its agent proposes a new text,
and each trial's text is a new version. The **Prompts** page shows every prompt's versions with their text, who made
each, what it was made from and the runs that sent it, and compares two versions; `evh prompt-show --name
<goal>/prompt --text` and `evh prompt-diff` say the same in a terminal.

## Where to go next

The API the Workbench reads is in [RUNBOOK §14](../../harness/docs/RUNBOOK.md#14-browse-the-catalog-and-the-inspector):
`evh openapi` lists every operation it serves, with its inputs. The design behind the Workbench is
[PRD-017](../prd/PRD-017-workbench.md) and [UXS-005](../uxs/UXS-005-workbench.md).
