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
  the pages are rebuilt when the data changes: a write through the API at once, any other on the next read
```

Its startup also prints a **Workbench** line: a link that signs in once (it carries the server's token, which becomes a
cookie) and opens `/workbench/`. The token is new at every start, so a page left open from before a restart asks you
to open the new link. The Workbench answers on this machine only: a server started with `--public` or behind a proxy
does not serve it.

The first time a screen writes something it asks who you are; that name is kept in your browser and recorded with
every change and every job (`person:<name>`).

## 2. A goal's steps

| screen | what you do there | the commands it calls |
| --- | --- | --- |
| **Home** | every goal with where it stands and its next step; what is running | `goal-list`, `goal-status`, `jobs-status` |
| **1 · The goal** | the decision, how you will judge, which way is better | `goal-new`, `goal-set` |
| **2 · A dataset** | one the project has, or one from a source: its query, a preview, its fields kept, its expected answers | `source-preview`, `fieldset-propose`, `dataset-create` |
| **3 · Prepare it** | fetch the items, look inside, make the reference set; or label the items on a sheet and submit it | `dataset-materialize`, `dataset-profile`, `label-sheet`, `label-import`, `reference-promote` |
| **4 · The systems** | a system from a model where it runs, its prompt and settings; a clone with one thing changed; each checked on three items under a cap | `system-new`, `prompt-version`, `arm-smoke` |
| **5 · The eval** | rounds: a question, its arms run as one sweep under a cap, the evidence, an arm retired with why, the round closed and its leader promoted | `round-open`, `sweep`, `round-carry`, `round-retire`, `round-close`, `baseline-rollback` |
| **Review the outputs** | two arms side by side: which is better (blind), or what went wrong (tags from a failure-mode list) | `sheet-export`, `sheet-import`, `failure-modes-new` |
| **Production** | records captured and made a dataset, production's decisions scored as an arm, the rows where it was wrong picked for the next version, labels from what happened later, a replay of the code that ran | `capture`, `dataset-from-capture`, `arm-from-capture`, `sheet-show`, `pick`, `dataset-extend`, `label-from-capture`, `faithfulness` |
| **Change the reference set** | what another label set moves before anything is promoted; promoted with why; a scoring change previewed | `rescore`, `reference-promote`, `score-preview` |
| **A judge** | its judges and their validation as stored, its cost first, then the arms judged under a cap | `scorer-new`, `scorer-set`, `judge-score`, `cost-report` |
| **The held-out test** | a dataset split and its test side sealed; its reads recorded and the leak check; counts for safety only; opened for one candidate (one look); the confirmation with the read items left out | `dataset-split`, `exposure-add`, `exposure-check`, `sealed-counts`, `dataset-unseal`, `pair-test` |
| **Studies** | a search over one thing at a time on the validation items, its trials and best, an agent's proposals asked and told, confirmed once on a test set | `study-run`, `study-ask`, `study-tell`, `study-stop`, `study-confirm`, `study-import` |

The models (bring one in, add where it runs, run its probes, accept a flag with why), the **Jobs**, the **Prompts** and
the **Settings** are on the home page's bar.

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
