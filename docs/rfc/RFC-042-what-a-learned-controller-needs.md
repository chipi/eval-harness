# RFC-042: What a lab training a learned controller needs out of the box

- **Status**: Proposed. Scope accepted by the owner (2026-11-28: "go to 0.9 straight ... proceed with doing all scope we
  pinned in 09 coming from robotics use case"); the design below is for review before it is built.
- **Authors**: Marko Dragoljevic
- **Related RFCs**: [RFC-026](RFC-026-an-api-for-every-command.md) (rounds), [RFC-029](RFC-029-studies-and-test-set-looks.md) (studies:
  select on validation, confirm on test), [RFC-031](RFC-031-held-out-discipline-and-outcome-labels.md) (the sealed
  split), [RFC-034](RFC-034-charts-and-judge-reasons.md) (charts), [RFC-041](RFC-041-one-source-for-each-fact.md) (one
  source for each fact)
- **Code**: `harness/scripts/axes.py`, `model/goal_views.py`, `model/rounds.py`, `rounds.py`, `promote_baseline.py`,
  `charts.py`, `catalog_build.py`, `catalog_adapter.py`, `model/runs.py`, `model/compare.py`, `catalog_views.py`,
  `import_run.py`, `_hypothesis.py`, `_fingerprint.py`, `compare_runs.py`, the schemas named below
- **Plan**: `research/internal/PLAN_0.9.0.md` (G1-G6, V1-V4, M, C; the beta projects' answers)

Paths are relative to `harness/scripts` unless they start with `harness/`, `docs/` or `research/`. Read 2026-11-28 on
branch `090` (0.8.3).

## Abstract

robotics-evals trains a robot's learned controller one experiment at a time, each the child of the last with one
change, and evaluates each by picking one checkpoint on a validation set and testing it on a primary dataset
(`avoidance_v2`, success) with a safety guard on another (`avoidance_v1`: success 1.0, collisions 0), paired against a
rules baseline. It wants to drop its own experiment files, checker and progress script and use the harness as shipped.
Moving onto models, systems and rounds in 0.8.2 found seven defects (fixed in 0.8.3, B1-B7) and the gaps below. Each
gap was put to fleet and eval too (PLAN_0.9.0, "The answers"); this RFC builds each in the shape the three answers
share, robotics' case first.

Eight parts, each small and built on what the harness already records:

| Part | What | Plan items |
| --- | --- | --- |
| A | Selection-only datasets: a mark on the dataset; evidence views leave its runs out | G3, V4 |
| B | Guards: a goal's limits hold in rounds and promotion too, read against the round's baseline, on another dataset | G2 |
| C | Progression: each arm's measure across a goal's rounds, with the baseline and the guards | G1, V1 |
| D | Lineage: a system's parent and its one change, as a chain with what each step bought | G4, V2 |
| E | Descriptive per-item metrics added to a frozen run, and items filtered by them | G5 |
| F | Items that flipped between two runs | V3 |
| G | What a run was served by: the deployment per run, the served model, the build | G6, M |
| H | Scorer versions a project declares equivalent; a moved project commit is not an instrument change | robotics' practice, C |

## A. Selection-only datasets (G3, V4)

**Today.** A goal's `datasets[].role` is a free string (`goal.schema.json:80`); a split's `split.part: validation`
(`dataset.schema.json:36`) is written by `dataset_split.py:143` and read by no view. `leaderboard`, `goal-leaderboard`,
the goal page, `pair-test`, `family-test`, `comparison-show`, `round-evidence` and the catalog's arm pages take runs on
any dataset. eval's 182 prompt candidates on dev datasets show with a test result's standing; robotics would import its
checkpoint-selection runs only if they were kept out.

**Design.** One fact, one place (RFC-041): **a dataset is selection-only** when its record says `use: selection`, or
when it is the validation side of a split (`split.part: validation`). `_datasets.selection_only(dataset_id)` answers it;
every reader asks it.

- **Evidence views leave a selection dataset's runs out by default and say so in one line** ("left out: 2 dataset(s)
  for selection only, `--include-selection` shows them"): `leaderboard`, `goal-leaderboard`, the goal page and the home
  glance, the catalog's leaderboards. With `--include-selection` (and in the catalog, on the dataset's own page) they are
  shown, marked "selection".
- **Decisions refuse them:** `run-promote`, `round-close --promote` and `baseline-promote` refuse a run on a
  selection dataset (`not-allowed`, naming the dataset and the rule). `pair-test`, `family-test`, `comparison-show` and
  `round-evidence` still compute (a study and a person tuning need them) and head their output "selection only: not
  evidence".
- **Studies** are unchanged: their trials already run on the validation side and confirm on the test side.
- **V4** (a selection curve that is never evidence) is the dataset's own page: its runs in the order they were made,
  marked selection, with no verdicts.
- `dataset-create --use selection` and `dataset-set use=selection` write the mark; `validate` checks it against the
  schema (`use: evidence | selection`, default evidence).

**Moves a result:** yes, for a project with runs on a split's validation side (they leave leaderboards and goal pages).
UPGRADING names it; `--include-selection` restores the old view.

## B. Guards (G2)

**Today.** `success_criteria.axes.<name>` with `measure`, `direction` and `limit` already rules an arm out on another
measure of the same run (`axes.py:188-193, 243-248`), but only where `axes.decide` runs: the goal page,
`goal-leaderboard` and the sheet footer (`goal_views.py:520`, `_sheet.py:630`). `model/rounds.py`, `rounds.py`
(`close_body`) and `promote_baseline.py` read the primary measure only, so **a round can promote a run the goal page
shows as out.** `limit: baseline` is an uncorrected paired test against the goal's promoted baseline (`axes.py:259-277`),
never the round's `--baseline`, and with nothing promoted it does nothing. No limit can name another dataset.

**Design.**

1. **One decision.** `round-evidence`, `round-close --promote`, `run-promote` and the round's suggestions call the same
   `axes.decide` the goal page calls. An arm out on a guard is said to be out, with the guard's reason, and is not
   promoted (`not-allowed`, naming the guard) unless `--override-guard REASON`, which is recorded.
2. **Against the round's baseline.** Inside a round, `limit: baseline` reads the round's baseline arm (its `--baseline`
   run's arm); elsewhere the goal's promoted baseline, as today. The line says which.
3. **Count limits.** `limit: {baseline: at_most}` (and `at_least`) is the plain comparison of means against that
   baseline, no test: "collisions not above the rules arm's". `limit: baseline` keeps its meaning (not significantly
   worse).
4. **A guard on another dataset.** An axis may name `dataset: <id>`: the guard reads the same system's run(s) on that
   dataset (the arm `<label>/<dataset>/<system>`). An arm with no run there is "not measured on the guard" (out of a
   promotion, shown on the goal page). `round-evidence` says "beats the baseline on the primary and passes every guard"
   or names the guard that fails.

**Moves a result:** yes. A round that promoted a run over a goal's limit now refuses it; an arm out on a limit inside a
round is read against the round's baseline. UPGRADING names both.

## C. Progression (G1, V1)

**Today.** `evh chart trend` (`charts.py:874-992`) draws promoted baseline versions and closed rounds' promoted runs
only; a round closed with nothing promoted is no point, and with no point the goal page hides the chart
(`catalog_build.py:3028-3040`). The goal page's rounds section is one leader per round.

**Design.** `evh chart progression --goal G [--dataset D] [--measure M]`, drawn from the rounds' own records
(`_rounds.load_rounds`, each arm read through `round_view` as the round froze it):

- x: the goal's rounds in order; y: each arm's measure (the primary by default) with its interval, one series per
  system (a carried arm repeats its point), the round's baseline as its own marked line.
- A point is marked when it is significantly better or worse than the round's baseline (the round's own test, so the
  mark equals `round-evidence`).
- A round on another dataset breaks the series (a gap and the dataset's name), never joins it.
- Every guard (B) is its own panel below, with its limit as a line and the arms that break it marked.
- Unpromoted and retired arms are drawn (fleet's case); `--arms` narrows the series.
- The same chart on the goal page (replacing `trend` there when the goal has rounds) and in the Workbench's goal
  screen, each with its command; `--json` gives the table.

**Moves a result:** no (a view).

## D. Lineage (G4, V2)

**Today.** `hypothesis.against` (`system.schema.json`) is a claim ("better than X on M"), read by `run`, `pair-test`
and the goals table; `model.schema.json` and `system.schema.json` are closed and have no parent. fleet keeps "parent plus
one change" in ids, NOTES and `against`; robotics' changes live in the training run, and R5b re-deployed the same models.

**Design.**

- `parent: {system: <id>, change: "<one sentence>"}` on a system, and `parent: {model: <id>, change: "..."}` on a model
  (training lineage). `change` is the statement; `validate` checks the parent exists and the chain has no cycle.
- `changed` is worked out, never typed: the keys that differ between the system and its parent (params, prompts,
  model record, deployment, adapter code), shown beside the statement. A step with more than one changed key is
  flagged "more than one change".
- `hypothesis.against` defaults to the parent when a system names one and no `against`.
- **Views:** the arm page and `evh system-show` say "parent X; changed: prompt (the statement)"; `pair-test --a S`
  takes the parent as `--b` when `--b` is not given (and says so); `evh lineage --dataset D [--measure M]` prints the
  chain (a tree for siblings), each step the paired difference from its parent on D with its verdict (V2, "what each
  change bought"), labelled by the statement; a model's chain likewise through its systems.

**Moves a result:** no (records and views; `against`'s default changes only what `run` records as the claim when none
was written).

## E. Descriptive per-item metrics on a frozen run (G5)

**Today.** `import-run --scores` takes per-item metric columns and `--metric-kind name=descriptive`
(`import_run.py:153-174`), so a new import can carry them; an existing run cannot gain one: `rescore` needs the
harness's adapter, and a second `import-run` of the system fails V8. `--where` filters on dataset item fields only
(`_sheet.py:557-570`).

**Design.**

- `evh metrics-add --run RUN --scores FILE [--why TEXT]`: per-item rows `{item_id, <metric>: number}` added to the run
  as **descriptive** metrics, in their own file under the run with its hash and who added it. Refused: a name the run
  already scores, an item the run has not, a run whose dataset is hidden text. The run's declared results, its
  fingerprint and every quality metric are unchanged; the added metrics never decide a goal, a round or a promotion.
- Readers show them where descriptive metrics show (the inspector's metric list, `comparison-show --metric`, the arm
  page), marked "added".
- **Items filtered by a per-item metric:** `--where` takes `metric:NAME OP VALUE` (`metric:stand_still=1`,
  `metric:collisions>0`) beside the item fields, in `comparison-items`, `sheet-show`, the inspector's chips and the
  per-item table.
- Docs: RUNBOOK says how a scorer's failure kinds become descriptive metrics (fleet's 0/1 metrics), at import or
  afterwards.

**Moves a result:** no (descriptive metrics never decide).

## F. Items that flipped (V3)

**Today.** `comparison-items --disagree` lists items whose outputs differ; `comparison-crosstab` crosses two per-item
scores; `pair-test` counts wins and ties without naming items.

**Design.** `comparison-items --flips METRIC` (and the inspector comparison page's "only items that flipped"): the
items whose value of METRIC crossed between the two arms (for a 0/1 metric, pass to fail and fail to pass, each
counted; for another, a change past `--by D`), with each side's k-of-n over its repeats, filterable with `--where`.
Items whose row is a failed call on either side are left out and counted ("3 left out: a failed call").

**Moves a result:** no (a view).

## G. What a run was served by (G6, M)

**Today.** A system names one deployment; `same_measurement` (`model/runs.py:185-217`) and the Conditions
(`catalog_adapter.py:344-387`) leave `build.ref` out. The bundled adapter already records each call's `response_model`
and upstream `provider` in the row's `_meta` (`adapter.py:213-214`); nothing compares them.

**Design.**

- **The served set, per run.** `run` writes `served: {models: {<response_model>: n}, providers: {<provider>: n}}` into
  the run's record from the rows' `_meta` (and `import-run` from the scores file's `_response_model`, `_provider`
  columns when present). The Conditions show it; `same_measurement` names a repeat whose served set differs from its
  arm's ("served by another model or provider") and keeps it out of the arm's pooled numbers, as it does a changed
  deployment.
- **The build.** `build.ref` joins the Conditions, and `same_measurement` names a repeat whose `build.ref` differs (a
  lab commit, robotics' `rules_v1` at two commits).
- **A deployment per run on import.** `import-run --deployment ID` records the run against that deployment of the
  system's model, overriding the system's own (robotics: one system measured in two places).
- **What a deployment records** (M): RUNBOOK says how a serving setting that can move a score (vLLM's memory
  utilization, max sequences, max length) goes into the deployment's `server_settings`, which the fingerprint already
  hashes.

**Moves a result:** yes, for a repeat whose served set or build differs from its arm's (it leaves the pooled numbers).
UPGRADING names it.

## H. Scorer equivalence; a moved project commit (robotics' practice, C)

**Today.** Two imports scored by one script at different commits read "scored by different scorers"
(`model/compare.py:668-700`) and hold a promotion (`model/rounds.py:312-313, 568-569`); nothing lets a project declare
them the same. `run-compare` counts any instrument difference a confound, and in an installed project
`instrument.harness.commit` is the project's own HEAD (`_fingerprint._harness_identity`).

**Design.**

- `data/scorers/equivalent.yaml`: `[{scorer: <id>, sha256: [<a>, <b>, ...], why: "...", by: <actor>}]`. The readers that
  compare scorers (`_flat_conditions`, `same_measurement`, the promotion hold) read a listed sha as the group's first; the
  Conditions say "equivalent by declaration (why)". `validate` checks each sha is one some run records.
- `run-compare`: with the harness installed (`instrument.harness.installed`) and `version` and `code_sha256` equal, a
  moved `commit` is "the project's commit moved", not an instrument difference, and is no confound. No hash changes.

**Moves a result:** yes, where a declaration lets a held promotion through; no for `run-compare` (display).

## Order and tests

A, then B (B's promotion refusal reads A's mark), then C (it draws B's guards), D, E with F (F filters by E's metrics),
G, H. Each part: a failing test first for each "today" defect it fixes (B's round promoting a run the goal page shows
out; C's refusal with no promotion), its tests in both stores, the reader-agreement test extended to its fields, the
docs that describe it (RUNBOOK, CONCEPTS, the tutorials that touch it, the Workbench's help), and the robotics case as a
fixture shape (a rules baseline, three learned arms in a chain, a validation selection set, a primary and a guard
dataset).

## Alternatives considered

1. **Selection marked per run** (A). Asked first; all three projects answered "on the dataset", because a run's
   purpose follows from where it ran, and a per-run flag is one more thing to forget.
2. **Two goals kept in step for a primary and a guard** (B). What robotics does today, by hand; it cannot say "beats
   the baseline and passes every guard" in one place, and the two goals drift.
3. **Extending `chart trend`** (C). Its points are promotions, a different question (how the baseline moved); a
   progression of every arm is its own chart, and `trend` stays.
4. **Lineage in `hypothesis.against`** (D). It is a claim about a comparison, not where a system came from; fleet's 4
   systems use it as both, which is why the default `against` follows the parent instead.
5. **Adding descriptive metrics through `rescore`** (E). A re-score replaces the arm in goals and rounds
   (`goal_views.py:92-95`), needs the harness's adapter, and is a new measurement; an added descriptive metric is none
   of these.
6. **The provider in the deployment's hash** (G). It would make every routed call a new deployment; the served set is a
   record of what happened, compared between repeats, not an identity declared in advance.

## Not in this RFC

- A second primary measure: a goal keeps one primary; everything else is a guard or descriptive.
- Training curves: a checkpoint's training logs stay the lab's; the harness sees checkpoints as models and their
  selection runs (A).
- Eval's G1, G4 and G6 answers, withdrawn until its re-mint (PLAN_0.9.0); the scenarios (RFC-035 to RFC-037).
