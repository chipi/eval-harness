# RFC-041: One source for each fact a reader works out

- **Status**: Accepted (owner, 2026-11-23: "a full-blown solution here for 081, the way it should be"); building in 0.8.1.
- **Authors**: Marko Dragoljevic
- **Related RFCs**: [RFC-032](RFC-032-one-model-two-surfaces.md) (one model, two surfaces: the same numbers and labels in
  every view), [RFC-021](RFC-021-fingerprint-v5.md) (the fingerprint's parts), [RFC-026](RFC-026-an-api-for-every-command.md)
  (the spend cap), [RFC-039](RFC-039-workbench-read-only-for-visitors.md) (the public reads)
- **Code**: `harness/scripts/_runs.py`, `_common.py`, `_spend.py`, `_visibility.py`, `model/runs.py`,
  `catalog_adapter.py`, `validate_tree.py`, and the readers named below

Paths are relative to `harness/scripts` unless they start with `harness/`, `docs/` or `research/`. Read 2026-11-23 in
the 0.8.1 worktree.

## Abstract

Three projects upgraded to v0.8.0 on 2026-11-23 and each found one bug:

- **homelab:** a cap of $0 printed as "NONE".
- **podcast eval-data:** a measure its goal says is lower-is-better printed as "higher".
- **fleet:** a pass added back to an arm with `--purpose repeat --of` counted as another arm.

Each was fixed where it showed. They have one cause: **the harness does not hold the fact in one place**. Each reader
works it out again from clues (the value's truth, whether a run names a goal, a run id's suffix), and the readers
drift apart. A search of the code for the same shape found eleven more (below).

This RFC names each fact, the one place that answers it, and what it reads: what was recorded or declared, never a
convention. Every reader asks that place. A test fails when a reader works the fact out itself, where that can be
checked from the code.

## The facts

### F1. Which way is better for a measure

**Today.** `_runs.lower_is_better_on` takes a goal's `direction` only through `goal_direction`, which counts only the
goals the runs name (`m["goal"]`). Two more derivations ignore goals entirely:

- `_common.verdict_for`, used by `evh run-compare` (`compare_runs.py:232`), reads the name table only.
- `_study.lower_is_better` reads the goal only (callers add the study's own `direction`). It knows neither the adapter
  nor the name table, so a study on `cost_usd` keeps the trial that costs more.

Whether a measure is "neutral" is answered apart from its direction (`is_neutral` and `lower_is_better` side by side in
`model/compare.py:544`, `catalog_build.py`, `model/metric_views.py`, `model/arm_views.py`), so a goal that says
`output_chars` is lower-is-better gets "lower" on its goal page and "a count, neither better" in the pair test.
Checked: a goal saying `der` is lower gives lower = False when the runs name no goal.

**The rule.** One function, `_runs.direction(metric, *, dataset=None, runs=(), goals=None, kinds=None)`, returns
`"lower"`, `"higher"` or `"neutral"`, by this precedence:

1. A goal that declares the measure: as its primary measure (`success_criteria.primary`) or as one of its axes (`axes_of`).
   For a question about one dataset, only a goal that lists that dataset, or a goal the runs name, decides. A goal on
   another dataset does not, and V14 warns when it disagrees with the answer. A question with no dataset (a measure no
   run records: `metric-list`, `metric-show`, its metric page) is decided by any goal that declares it.
   Goals that disagree on one dataset are a V14 failure, so a project never has two answers.
2. What the runs record (`metric_directions`: the adapter's `METRIC_DIRECTIONS`, `import-run --asc`), then their
   declared kinds (`metric_kinds`: descriptive is neutral).
3. The name table (`_common`: cost, speed, tokens; descriptive keys; error rates `wer`, `cer`, `der` lower).

A declared direction wins over "neutral": a project that says which way a count goes has said it is not neutral.
`lower_is_better_on`, `verdict_for`, `_study.lower_is_better`, `A.lower_is_better` and `A.is_neutral` become thin
callers of it. The "better" word on the catalog's metric pages, `metric-list`, `metric-show`, the arm page and the
comparison comes from one function, `_runs.better_word(direction)`. Today a goal page and the inspector can disagree on
the same arms.

**Validation (V14).**

- **Fails** when two goals declare opposite directions for one measure on one dataset.
- **Warns, and does not fail,** when a goal's `direction` is neither `lower` nor `higher`. The podcast project's
  `regression_detection` says `non_inferior`, which `axes_of` reads as higher; that is a decision rule, not a direction.
- **Warns** when a goal's primary measure is recorded by no run on any of its datasets, and names the measures they do
  record. The podcast project's goals name `DER` and `WER vs human transcript (ascii-v1)`; its runs record `wer`.

### F2. Which runs make up an arm

**Today.**

- **Repeat sets.** A set made by `run --repeat N` is recognised by the run-id suffix `_rN`, in four copies:
  `_runs.is_repeat_set`, `validate_tree.py:1033`, `promote_baseline.py:55` and `model/goals.py:133`. A user's
  `--run-id foo_r1` and `foo_r2` pass as a set.
- **Repeats of a run.** A `--purpose repeat --of X` run is read under the label `repeats`, a separate arm: `of` is
  written and never read. The label exists so the old `runs-repeats/` folder kept its views through the migration
  (m0004; RFC-032 "the same labels").
- **The catalog and the commands.** The catalog's arm (`catalog_adapter._index`) keeps the runs scored against the
  latest run's reference. `runs_on` (leaderboard, cost-report) keeps every run, so one arm id can average different
  runs in two views.

**The rule.** One function, `model.runs.arm_of(score_dir, rec)`, says which arm a scored run is read in, from what the
run recorded:

- **A plain run** (`purpose: run`): `<label>/<dataset>/<system>`, as today.
- **A repeat with `of`:** the arm of the run it names when `model.runs.same_measurement` says the two are the same
  measurement taken again: the same system and dataset, and equal fingerprint parts for the data, the deployment and
  the settings, and an equal adapter. Each run's own fingerprint is read (a rescored or judged score's fingerprint has
  no hash). Otherwise it stays under `repeats`, and the part that differs is named. `evh run --purpose repeat` says
  which, before its first call and in its last line.
  - **Not the whole `hash` (owner, 2026-11-23).** The hash's instrument part covers the harness's own code
    (`harness_code_sha256`), so every run made on 0.8.1 has a new hash, and a repeat of a 0.8.0 run would never join.
    And the hash is not unique to an arm: in one beta project, 13 imported systems share one hash on one dataset.
    A different harness build joins, and is named where the arm's runs are listed.
  - **`of` names a run of the same system and dataset,** or `evh run` refuses it, and validate fails it once
    committed.
  - **A repeat of a repeat** follows `of` to the root, with a cycle guard. A missing link, or a link that did not join,
    leaves it under `repeats`, with the reason.
  - **No fingerprint, or another fingerprint version,** on either side: under `repeats`, with the reason.
  - **A closed round's numbers never change.** A repeat that joins after the round closed is listed in its
    "since then". In an open round, a repeat of a retired arm's run is refused: today `add_run` brings the arm back
    without a word.
- **A repeat with no `of`:** under `repeats`, as today.
- **`retime` and `pair`:** under their own labels, as today. Another machine and another configuration really are
  other measurements.

Set membership comes from what the run records:

- `repeat_index` (written by `--repeat N`) or a joined repeat makes a run a member of its arm's set. The suffix no longer
  counts.
- `is_repeat_set`, V8, `promote_baseline._repeats` and the goal's system names call `model.runs.set_of(...)`.
- Rounds (`model/rounds.py add_run`) join the run to the arm `arm_of` names.

The runs an arm is read from come from one function, `model.runs.runs_of_arm(arm)`: the runs `arm_of` puts there, scored
against the reference of its latest run. Runs scored against another reference are named, never averaged in. The
catalog's `_index` and `runs_on` call it. Leaving git-ignored runs out stays a publishing rule of the catalog (`evh
catalog --publish`), applied on top.

**The latest run** is the one with the greatest `(created_at, run_id)`, from one function, `model.runs.latest(runs)`.
Today four readers pick it differently: by name prefix and string `max` (`judge_validate._latest_run`, which also
takes `smoke_v1_*` for system `smoke`), by run-id order (`catalog_adapter._metrics`, `_kinds`), and by `created_at`.

### F3. Unknown, none and zero

The cap was one case. The same shape elsewhere:

| Where | Today | The rule |
| --- | --- | --- |
| `_common.py:514` `build.dirty = bool(dirt)` | git failing records `false`: clean | `null` when git cannot say, as `_fingerprint` already does, recorded so it can be told apart from a run with no tree (`EVAL_BUILD_REF`, `import-run`, which also record `null`); only "git was asked and could not say" counts as not proven clean (promotion refuses it); `runs-list` shows `?` for every `null` |
| `catalog_arms.py:418`, `catalog_views.py:87,711` cost cells | `$0.00` shows `—`, as "not recorded" | `$0.00` shows `$0.00`; `—` only when not recorded, as `catalog_build.py:2931` already does |
| `workbench/live.js` trial costs | unknown shows `$0.0000` | unknown shows `—` |
| `_study.py:128` `stop.usd and stop.wall_h` | `usd: 0` refused as no stop rule | `is not None`, as `open_study` reads it |
| `run.py:1557` the identical-passes note | an unset temperature read as 0 | the provider's default, from `_providers` |

The cap is printed by `_spend.shown` only, built in 0.8.1 (`test_cap_shown.py` reads the tokens of every command).

### F4. Whether this is the public server

`model/compare.py:25` says public when the server has public hosts **or** `_visibility.public_env()`.
`catalog_serve.py` (`item()` and seven more) asks only the hosts. An in-process public MCP call is public by the first
rule and not by the second. Only a hand-kept list (`public_dropped`) keeps it from serving an item's text. And
`_visibility.hidden` shows a dataset's text when its file is missing or unreadable.

**The rule.** One function, `_visibility.public()`, which every reader calls. `hidden` fails closed: a dataset that
cannot be read is hidden on a public server.

### F5. Which day it is

`catalog_models.stale`, `ops/goals.py:109` and `model/view_cache.py:209` use the local `date.today()`. Runs are stamped
in UTC, and the period filter compares `created_at[:10]`. One function, `_common.today()`, gives the UTC date, and
every reader takes it from there.

### F6. The baseline on the datasets page

`catalog_build.py:1008,1046` show `baselines[-1]`, the latest promotion of any goal on that dataset, as "the" baseline.
The cell names the baseline per goal, as the goal pages do.

### F7. The writers record the fact, or refuse

One source per fact is half the answer: a reader can only read what a writer recorded. Today the writers accept
shapes the readers then assume away:

- `evh run --of` checks only that the run exists (`run.py:1375`).
- `--run-id foo_r1` is accepted, and was read as a set.
- `build.dirty` is written `false` when git cannot say.
- `import-run` writes `purpose: run` and `dirty: null` whatever happened (`import_run.py:182,200`).

**The rule.** Each writer records the fact explicitly or refuses what it cannot know, and validate checks the link
the readers rely on:

- `of` names a run of the same system and dataset, and its relation to that run (joined, or which part differs) is
  stated.
- A `repeat_index` set is whole and consistent.
- `dirty: null` comes with how the build was given.
- A goal's measure is recorded by some run on its datasets (a warning).
- Declared directions are `lower` or `higher` (a warning).

`evh run` and `import-run` refuse at write time what validate would fail.

## What moves

- **This repository.**
  - F1: nothing (checked, exact names: 281 (dataset, metric) pairs, none differ).
  - F2: nothing expected. The four repeats here that name `of` have a different fingerprint hash from their original
    (another build, one dirty). The twelve triage `_rN` repeats name no `of`. Checked by the export being identical
    file by file.
  - F3 to F6: display, and promotion only for a run whose build git could not read.
- **fleet-eval-data.** F2: `triage_v2_station_dc3315d_v1` on `orrery_triage_v1_labelled_v2` goes from 2 runs to 3:
  its repeat has the same hash as `_r1`. This is the fix asked for. Its pair tests and goal page on that dataset can
  change.
- **podcast-scraper-eval-data.** F1: `wer` on `curated_5feeds_dev_v1` (68 arms) and `curated_5feeds_benchmark_v1`
  (8 arms) is read as higher-is-better today, because nothing there declares it and the name table does not know it.
  With `wer` in the name table it is lower. Every ranking on `wer` there turns the right way up. The V14 warnings
  name the goals whose measures no run records.
- **A study** on a cost, speed or token measure with no `direction` in its spec or goal: its keep/discard decisions
  were made the wrong way round. No study in the four projects is on such a measure (to check in step 1).

A patch release does not move a result unless the owner decides. The owner decided on 2026-11-23: these ship in 0.8.1,
and the release notes list each move with the project it moves.

## Tests, written first

Each fact gets a failing test before its fix:

- **Its rule** on an input that shows the bug.
- **Its consistency:** every reader gives the same answer on one fixture (the goal page, the leaderboard,
  `run-compare`, the inspector, `metric-list` and the study on F1; the catalog arm, the leaderboard, `pair-test`,
  `runs-list` and the round on F2).
- **A source check, where the shape can be found in the code:** no reader tests a cap's truth (built);
  `date.today()` only in `_common.today`; `lower_is_better(` and `is_neutral(` only through `_runs.direction`; the `_rN`
  suffix read only in `model.runs`.

**The export check.** This repository's export is identical file by file before and after (the footer's time masked)
for F1, F2 and F3. Every difference is listed and explained.

## The order of work

1. F1 (direction), with its V14 checks and the podcast fixture.
2. F2 (arm membership, sets, the runs of an arm, the latest run), with a fleet-shaped fixture (a `--repeat 3` set with
   one pass lost and a repeat added with `--purpose repeat --of`).
3. F3, F4, F5 and F6.
4. Docs:
   - RUNBOOK §4 (repeats) and the would-overwrite refusal say what `--purpose repeat --of` now does.
   - PRD-001, UXS-003 and `ops/run_jobs.py` say the same.
   - UPGRADING says what moves for whom.
5. The full gates; the export check; each owner project read with the new code (read-only) and the moves listed.

## Not covered

- Facts outside the eleven found: the search read the Python in `scripts/` and part of the JavaScript. It did not
  read `catalog_assets/arms.js`, `overview.js`, `period.js`, `group.js`, `workbench/workbench.js`, `importers/`,
  `sweep.py` or `rescore.py`'s cost reconciliation.
- A goal's prose measure (`DER`) is not matched to a recorded metric (`der`) by name or alias: V14 warns, and the project
  renames it. A matching rule would guess.
- Plain runs of one system on one dataset with equal hashes are not merged into a set: V8 still refuses two plain
  measurements, as `duplicate_ok` allows on purpose.
