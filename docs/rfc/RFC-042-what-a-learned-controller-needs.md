# RFC-042: What a lab training a learned controller needs out of the box

- **Status**: Proposed. Scope accepted by the owner (2026-11-28: "go to 0.9 straight ... proceed with doing all scope we
  pinned in 09 coming from robotics use case"); the design was reviewed by the advisor on 2026-11-28 (cuts and merges
  applied, listed under "Review").
- **Authors**: Marko Dragoljevic
- **Related RFCs**: [RFC-026](RFC-026-an-api-for-every-command.md) (rounds), [RFC-029](RFC-029-studies-and-test-set-looks.md) (studies:
  select on validation, confirm on test), [RFC-031](RFC-031-held-out-discipline-and-outcome-labels.md) (the sealed
  split), [RFC-034](RFC-034-charts-and-judge-reasons.md) (charts), [RFC-041](RFC-041-one-source-for-each-fact.md) (one
  source for each fact)
- **Code**: `harness/scripts/axes.py`, `model/goal_views.py`, `model/goals.py`, `model/rounds.py`, `rounds.py`,
  `promote_baseline.py`, `charts.py`, `catalog_build.py`, `catalog_adapter.py`, `model/runs.py`, `model/compare.py`,
  `catalog_views.py`, `_sheet.py`, `import_run.py`, `_hypothesis.py`, `_fingerprint.py`, `compare_runs.py`, the schemas
  named below
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
share, robotics' case first, on what the harness already records.

| Part | What | Plan items |
| --- | --- | --- |
| A | Selection-only datasets: a mark on the dataset; cross-dataset evidence views leave its runs out | G3, V4 |
| B | Guards: a goal's limits hold in rounds and promotion too, against the round's baseline, and on another dataset | G2 |
| C | Progression: each arm's measure across a goal's rounds, with the baseline and the guards | G1, V1 |
| D | Lineage: a system's parent and its one change, as a chain with what each step bought | G4, V2 |
| E | Descriptive per-item metrics added to a frozen run, and items filtered by them | G5 |
| F | Items that flipped between two arms, with k-of-n over repeats | V3 |
| G | What a run was served by: the served model and provider, and the build | G6, M |
| H | A moved project commit is not an instrument change; scorer versions a project declares equivalent | C, robotics' practice |

## A. Selection-only datasets (G3, V4)

**Today.** A goal's `datasets[].role` is a free string (`goal.schema.json:80`) with meaning in two places:
`model/goals.py:226` suggests no baseline on a `validation` or `test` dataset, and `_looks.py:53` makes `role: test` a
test set. A split's `split.part: validation` (`dataset.schema.json:36`) is written by `dataset_split.py:143` and read by
nothing. A goal's `datasets[].decides: false` already keeps a dataset from a recommendation and out of the home page's
glance (`goal.schema.json:83`; `model/goal_views.py:528, 591-593`). Every evidence view takes runs on any dataset; eval's
182 prompt candidates on dev datasets show with a test result's standing, and robotics would import its
checkpoint-selection runs only if they were kept out.

**Design.** One fact, one place (RFC-041): **a dataset is selection-only** when its record says `use: selection`, or
when it is the validation side of a split (`split.part: validation`). `_datasets.selection_only(dataset_id)` answers it;
every reader asks it. A goal's `role` stays a label.

- **Inside a goal, a selection dataset decides nothing**: it goes through the existing `decides` path (selection implies
  `decides: false`), so it gives no recommendation and leaves the home glance, and its group is marked "selection".
- **Cross-dataset views leave its runs out and say so in one line** ("left out: 2 dataset(s) for selection only;
  `--include-selection` shows them"): `goal-leaderboard`, the goal page, the home glance and the catalog's leaderboard
  index. Where the reader named the dataset (`leaderboard <dataset>`, the dataset's own page, `pair-test`,
  `family-test`, `comparison-show`, `round-evidence`), its runs are shown, headed "selection only: not evidence".
- **Decisions refuse them:** `run-promote`, `round-close --promote` and `baseline-promote` refuse a run on a selection
  dataset (`not-allowed`, naming the dataset and the rule). Studies are unchanged: their trials already run on the
  validation side and confirm on the test side.
- **V4** (a selection curve that is never evidence) is the dataset's own page: its runs in the order they were made,
  marked selection, with no verdicts.
- `dataset-create --use selection` and `dataset-describe --use selection|evidence` write the mark (`use: evidence |
  selection`, default evidence; `dataset-describe` changes a dataset's description and licence, never its items,
  `ops/datasets.py:43`).

**Moves a result:** yes, for a project with runs on a split's validation side: they leave the cross-dataset views and
cannot be promoted. UPGRADING names it; `--include-selection` restores the views.

## B. Guards (G2)

**Today.** `success_criteria.axes.<name>` with `measure`, `direction` and `limit` already rules an arm out on another
measure of the same run (`axes.py:188-193, 243-248`), but only where `axes.decide` runs: the goal page,
`goal-leaderboard` and the sheet footer (`model/goal_views.py:520`, `_sheet.py:630`). `model/rounds.py:341`,
`rounds.py:199` and `promote_baseline.py:113-114` read the primary measure only, so **a round can promote a run the goal
page shows as out.** `limit: baseline` is an uncorrected paired test against the goal's promoted baseline
(`axes.py:259-277`) and with nothing promoted does nothing (`axes.py:252-256`). A round's `baseline` is the dataset's
promoted baseline when it opened, or the run `round-open --baseline` named (`round.schema.json:17`). Studies already
have plain limits against their baseline (`study.schema.json:52-62`, `_study.py:403-411`). No limit can name another
dataset.

**Design.**

1. **One decision.** `round-evidence`, the round's suggestions, `round-close --promote` and `run-promote` call the same
   `axes.decide` the goal page calls. An arm out on a guard is said to be out, with the guard's reason, and is not
   promoted (`not-allowed`, naming the guard) unless `--override-guard`, recorded with the promotion's own reason, as
   `override_no_evidence` is (`ops/rounds.py:66-68`).
2. **Against the round's baseline.** Inside a round, `limit: baseline` reads the round's baseline arm; elsewhere the
   goal's promoted baseline, as today. The line says which. This changes a result only where the round's baseline is
   not the promoted one (`round-open --baseline`), which is robotics' case.
3. **A plain comparison.** `compare: mean` on an axis with `limit: baseline` compares the arm's mean with the baseline's
   on the axis's `direction`, no test, as a study's limit does: "collisions not above the rules arm's". The default stays
   the paired test.
4. **A guard on another dataset (built last).** An axis may name `dataset: <id>`: the guard reads the same system's arm on
   that dataset (the unlabelled arm, or the label the round reads). An arm with no run there is "not measured on the
   guard" and cannot be promoted. To keep a round frozen, `round-evidence` and `round-close` record the runs each guard
   read (`guards: [{axis, dataset, runs}]` in the round); a closed round reads those, never the live arm.
   `round-evidence` says "beats the baseline on the primary and passes every guard", or names the guard that fails.

**Moves a result:** yes. A round that promoted a run over a goal's limit now refuses it; inside a round, `limit:
baseline` reads the round's baseline. UPGRADING names both.

## C. Progression (G1, V1)

**Today.** `evh chart trend` (`charts.py:874-992`) draws promoted baseline versions and closed rounds' promoted runs;
a round closed with nothing promoted adds no point, and with no point the goal page hides the chart
(`catalog_build.py:3028-3040`). The goal page's rounds section is one leader per round. `_rounds.load_rounds`
(`_rounds.py:48`) and `round_view` (`model/rounds.py:62`) give each round's arms as it froze them.

**Design.** `evh chart progression --goal G [--dataset D] [--measure M] [--arms ...]`:

- x: the goal's rounds in order; y: each arm's measure (the primary by default) with its interval, one series per
  system (a carried arm repeats its point), the round's baseline as its own marked line.
- A point is marked when it is significantly better or worse than the round's baseline, read from
  `model/rounds.evidence()`, so the mark equals `round-evidence`.
- A round on another dataset breaks the series (a gap and the dataset's name), never joins it.
- Each guard (B1-B3) is its own panel below, with its limit as a line and the arms that break it marked.
- Unpromoted and retired arms are drawn (fleet's case).
- The same chart on the goal page (in place of `trend` there when the goal has rounds) and on the Workbench's goal
  screen, each with its command; `--json` gives the table. `trend` stays for how the baseline moved.

**Moves a result:** no (a view).

## D. Lineage (G4, V2)

**Today.** `hypothesis.against` (`system.schema.json`) is a claim ("better than X on M"), required whenever a
hypothesis is written (`_hypothesis.py:26`), read by `run`, `pair-test` and the goals table; `system.schema.json` is
closed and has no parent. fleet keeps "parent plus one change" in ids, NOTES and `against`; robotics' changes live in the
training run, and R5b re-deployed the same models.

**Design.**

- `parent: {system: <id>, change: "<one sentence>"}` on a system. `change` is the statement; `validate` checks the parent
  exists and the chain has no cycle. A re-deployment of the same model is a child whose change says so (robotics' R5b).
- `changed` is worked out, never typed: the parts `compare_runs` already names between two runs' fingerprints
  (`compare_runs.py:58-69`: deployment, settings by key, data, instrument), read between the system's and its parent's
  latest runs on the dataset shown. A step with more than one changed part is flagged "more than one change".
- A hypothesis may leave out `against` when the system names a parent; the parent is then the claim's `against`
  (V20 accepts it).
- **Views:** the arm page and `evh system-show` say "parent X; changed: prompt (the statement)"; `pair-test --a S`
  takes the parent as `--b` when `--b` is not given, and says so; `evh lineage --dataset D [--measure M]` prints the
  chain (a tree for siblings), each step the paired difference from its parent on D with its verdict, labelled by the
  statement (V2, "what each change bought").

**Moves a result:** no (records and views).

## E. Descriptive per-item metrics on a frozen run (G5)

**Today.** `import-run --scores` takes per-item metric columns and `--metric-kind name=descriptive`
(`import_run.py:153-176`; `_`-prefixed columns are skipped, `:154`), so a new import can carry them. An existing run
cannot gain one: `rescore` needs the harness's adapter and replaces the arm (`model/goal_views.py:92-95`), and a second
`import-run` of the system fails V8. `--where` filters on dataset item fields only, `FIELD:VALUE | FIELD:LO..HI`
(`_sheet.py:557-570`, `ops/inspect.py:26-29`).

**Design.**

- `evh metrics-add --run RUN --scores FILE --why TEXT`: per-item rows `{item_id, <metric>: number}` added to the run as
  **descriptive** metrics, in their own file under the run with its hash and who added it. Refused: a name the run
  already scores, an item the run does not have, a run on a dataset whose text is hidden. The run's declared results, its
  fingerprint and its quality metrics are unchanged; an added metric never decides a goal, a round or a promotion.
- Readers show them where descriptive metrics show (the inspector's metric list, `comparison-show --metric`, the arm
  page), marked "added".
- **Items filtered by a per-item metric**, in the existing grammar: `--where metric.collisions:1..`,
  `--where metric.stand_still:1`, in `comparison-items`, `comparison-crosstab`, `sheet-show` and the inspector's chips.
- RUNBOOK says how a scorer's failure kinds become descriptive metrics (fleet's 0/1 metrics), at import or afterwards.

**Moves a result:** no (descriptive metrics never decide).

## F. Items that flipped (V3)

**Today.** `comparison-crosstab --crosstab A,B` crosses two per-item scores per group and names the items off the
diagonal, and takes `--where` (`ops/inspect.py:43-53`, `catalog_views.py:1163-1230`); for a 0/1 metric that is the
list of items that flipped. It reads one value per item and counts a failed call's row like any other.

**Design.** `comparison-crosstab` gains what fleet and robotics lack: each side's k-of-n over its repeats per item (an
item flips when its majority does), and the rows of a failed call left out and counted ("3 left out: a failed call").
The inspector's comparison page links its "only where they disagree" view to the same crosstab for a 0/1 metric.

**Moves a result:** no (a view).

## G. What a run was served by (G6, M)

**Today.** A system names one deployment; `same_measurement` (`model/runs.py:185-213`) compares data, deployment,
settings and the scorer; the Conditions (`catalog_adapter.py:344-387`) show the declared upstream provider
(`deployment.upstream`, from `hosted.provider_id`, `:371-373`) and leave `build.ref` out (`build` is on the run record,
`run.py:1982`, not the fingerprint). `import-run` requires `--build-ref` (`ops/records_work.py:116`). The bundled
adapter records each call's `response_model` and upstream `provider` in the row's `_meta` (`adapter.py:213-214`);
nothing compares them.

**Design.**

- **The served set, per run.** At the end of a run, `run` writes `served: {models: {<response_model>: n}, providers:
  {<provider>: n}}` into the run's record from its rows' `_meta`. The Conditions show it beside the declared upstream;
  `same_measurement` names a repeat whose served set differs from its arm's ("served by another model or provider") and
  keeps it out of the arm's pooled numbers, as it does a changed deployment (fleet's case).
- **The build.** `build.ref` joins the Conditions, and `same_measurement` names a repeat whose `build.ref` differs from
  its arm's (robotics' `rules_v1` at two lab commits; import-run already records it).
- RUNBOOK says how a serving setting that can move a score (vLLM's memory utilization, max sequences, max length) goes
  into the deployment's `server_settings` (`deployment.schema.json:51`), which the fingerprint already hashes (M).

**Moves a result:** yes, for a repeat whose served set or build differs from its arm's: it leaves the pooled numbers.
UPGRADING names it.

## H. A moved project commit; scorer equivalence (C, robotics' practice)

**Today.** In an installed project `instrument.harness.commit` is the project's own HEAD
(`_fingerprint.py:270-291`), and `run-compare` counts any instrument difference a confound (`compare_runs.py:69, 119,
134`). Two imports scored by one script at different commits read "scored by different scorers"
(`model/compare.py:668-700`) and hold a promotion (`model/rounds.py:312-313, 568-569`). `--scorer-file` is hashed by
what it does, docstrings and comments not counted (`ops/records_work.py:123`), so two hashes mean the code that scores
changed; the remedy printed today is to import both again with one scorer (`model/compare.py:681`).

**Design.**

- **`run-compare`:** with the harness installed and `version` and `code_sha256` equal, a moved `commit` is "the
  project's commit moved", not an instrument difference, and no confound. No hash changes. (Built first: small.)
- **Scorer equivalence, if robotics cannot import again at one commit** (asked; its answer decides whether this is
  built): `data/instruments/scorer-equivalence.yaml`, `[{scorer: <id>, sha256: [<a>, <b>, ...], why, by}]`, kept apart
  from `data/scorers/` (judge-scorer records, whose `supersedes` says the opposite). The recorded sha is shown as it is,
  with "equivalent by declaration (why)"; `same_measurement` and the promotion hold read the listed shas as one scorer,
  so repeats across them pool. `validate` checks each sha is one some run records.

**Moves a result:** no for `run-compare` (display); yes where a declaration pools repeats or lets a held promotion
through (UPGRADING).

## Order and tests

H's `run-compare` line and G's `build.ref` in the Conditions first (small display fixes robotics hit), then A, B1-B3,
C, D, E, F, G, B4 last (the only part that touches a round's freezing; C and the fixture do not wait for it), and H's
equivalence if robotics' answer calls for it. Each part: a failing test first for each "today" defect it fixes (B's
round promoting a run the goal page shows out; C's refusal with no promotion), its tests in both stores, the
reader-agreement test extended to its fields, the docs that describe it (RUNBOOK, CONCEPTS, the tutorials that touch
it, the Workbench's help), and the robotics case as a fixture shape: a rules baseline, three learned arms in a chain, a
validation selection set, a primary and a guard dataset.

## Alternatives considered

1. **Selection marked per run** (A). Asked first; all three projects answered "on the dataset", because a run's purpose
   follows from where it ran, and a per-run flag is one more thing to forget.
2. **Two goals kept in step for a primary and a guard** (B). What robotics does today, by hand; it cannot say "beats the
   baseline and passes every guard" in one place, and the two goals drift.
3. **Extending `chart trend`** (C). Its points are promotions, a different question (how the baseline moved); a
   progression of every arm is its own chart, and `trend` stays.
4. **Lineage in `hypothesis.against`** (D). It is a claim about a comparison, not where a system came from; fleet's 4
   systems use it as both, which is why `against` may follow the parent instead.
5. **Adding descriptive metrics through `rescore`** (E). A re-score replaces the arm in goals and rounds, needs the
   harness's adapter, and is a new measurement; an added descriptive metric is none of these. **A tag set**
   (`data/tags/<dataset>/<set>`, `_tags.py:1-8`) is not the home either: tags are categorical failure modes, the ask is
   numbers with a filter.
6. **The provider in the deployment's hash** (G). It would make every routed call a new deployment; the served set is a
   record of what happened, compared between repeats, not an identity declared in advance.

## Review (advisor, 2026-11-28)

Applied: A uses `dataset-describe --use` (no new command), keeps `leaderboard <dataset>` showing what was named (headed,
not filtered), and routes a selection dataset through the existing `decides` path; B's plain comparison is one
`compare: mean` key matching a study's limits (no `at_most`/`at_least`), and B4 records the guard runs in the round and
is built last; D drops a model's `parent` (a re-deployment is a child system) and takes `changed` from `compare_runs`'
fingerprint delta; E uses the existing `--where` grammar; F extends `comparison-crosstab` instead of a new
`comparison-items --flips`, and drops a threshold for non-0/1 metrics nobody asked for; G drops `import-run
--deployment` (robotics answered G6 "no"; `--build-ref` is already required) and the import columns for a served
model (eval's case, withdrawn); H shows the recorded scorer sha with the declaration beside it, and waits on whether
robotics can import again at one commit.

## Not in this RFC

- A second primary measure: a goal keeps one primary; everything else is a guard or descriptive.
- A model's parent (training lineage): a re-deployed model is a child system; added later if a project needs the
  model's own chain.
- Training curves: a checkpoint's training logs stay the lab's; the harness sees checkpoints as models and their
  selection runs (A).
- Eval's G1, G4 and G6 answers, withdrawn until its re-mint (PLAN_0.9.0); the scenarios (RFC-035 to RFC-037).
