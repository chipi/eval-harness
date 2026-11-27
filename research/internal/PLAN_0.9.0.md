# 0.9.0: the plan

**Status:** 2026-11-27, a first draft. Nothing in it is built. The owner decides scope and order. Already named for
0.9.0 elsewhere: the scenarios (RFC-035, RFC-036, RFC-037, all Draft) and whatever the MLflow and TensorBoard assessment
(PLAN_0.8.3, A) leads to.

## G. What robotics-evals needs out of the box (2026-11-27)

The robotics lab wants to use the harness as shipped (catalog, Workbench, goals, models, rounds) and retire its own
`experiments/<id>.yaml`, its checker and `progress.py`. Its case: a robot's learned controller trained one experiment
at a time (rules, M2a, M2b from M2a, M2c, M2d), each a child of the last with one change. Each training run has 3-15
ONNX checkpoints. Each evaluation picks one checkpoint on a validation set (selection only), then tests it on
avoidance_v2 (primary: success) and avoidance_v1 (safety: success 1.0, collisions 0), paired against rules, Holm
across the learned arms, pre-registered.

The mapping to 0.8.2 that works today was sent to the lab (a checkpoint is an `ml` model with a deployment's
`file_hash`, one system per checkpoint; the change is the system's `hypothesis:`; an evaluation is a round;
`comparison-show --baseline rules` is the Holm table; failure behaviours are descriptive per-item metrics). What does
not exist:

| Item | Gap | Found in 0.8.2 |
| --- | --- | --- |
| G1 | No progression view: each arm's primary metric across rounds, with the baseline's line. The lab's first ask | `evh chart trend` draws only promoted baseline versions and each closed round's promoted run (`charts.py:874-993`); the goal page's rounds section is a text table |
| G2 | A round is one dataset, and a goal has one primary measure: a primary dataset plus a safety guard on another dataset needs two goals or two rounds | `round.schema.json` requires `dataset_id`; `success_criteria.primary` is one measure; `axes` apply to every dataset of the goal |
| G3 | A run cannot be marked "selection only, never evidence"; a study selects on validation and confirms on test, but against its own baseline on one test set, not against an outside arm across two | no such marker in `run` or `import-run`; RFC-029 "The confirmation" |
| G4 | No lineage on models or systems ("the parent and the one change") beyond a system's `hypothesis.against` and a round's `from` | `model.schema.json` and `system.schema.json` are closed (`additionalProperties: false`) |
| G5 | Failure tags only from a hand-filled sheet; no adapter, scorer or `import-run` writes a tag set | `write_tags` has one caller, `sheet_import.py:198` |
| G6 | Two deployments of one system on one dataset are told apart only by separate system ids or rounds; `EVAL_BUILD_REF` is recorded, not compared | `_flat_conditions` (`catalog_adapter.py:337-392`) and `same_measurement` (`model/runs.py:186-230`) leave `build.ref` out |

Not verified: whether `_`-keyed columns of an imported score show anywhere, and what the goal page picks when one system
has two plain runs on one dataset. Neither was run.

For 0.8.3 the mapping found no defect: every gap above is a missing feature, not a bug in something shipped.

**Asked of every beta project (2026-11-27), so no item is shaped on one project's feedback:** fleet, eval
(podcast-scraper-eval-data), robotics lab (ranking its own six) and homelab (asked whether it runs the provider
bake-off). Each answers per item: no / maybe / yes, a concrete case from its own evals and what it does today, and how
it should work if that differs. Their answers go in a table here before the owner decides what 0.9.0 builds.

### The answers

The bake-off is out of the survey: homelab does not run it, has not since its last change on 2026-06-12, and knows of no
session that does (it only serves the catalog at bakeoff-evals). Its owner is the operator's to name.

| Item | robotics-evals | fleet | eval (podcast) |
| --- | --- | --- | --- |
| G1 progression | **yes, first.** r5_avoidance_v2 across R5, R5b, M2c, M2d, R7 against rules_v1 (0.575): x rounds or arms in lineage order, y primary with its CI, a series per arm family, the baseline line, a mark for significant vs the baseline, the guard metric (collisions) as a second panel; on the goal page, the Workbench and `evh chart` | **maybe.** triage_orrery has 4 closed rounds and no promoted baseline after r4, so `chart trend` draws almost nothing; each arm's triage_cost across r1-r4 is told by hand in NOTES. Works only if it draws arms never promoted; a round that moved dataset (labelled to labelled_v2) breaks the line, never joins it | waiting |
| G5 tags from the scorer | **yes, second.** stand_still and pivot_fail were the whole R5 story and none is visible. Descriptive per-item metrics may be enough if (i) they can be added to a frozen run without changing its declared results and (ii) the catalog and inspector filter items by them; then G5 closes as docs | **no.** Its adapters already score each failure kind as its own 0/1 per-item metric (false_dismiss, silent_drop, no_decision, table_miss, escalated); a second channel would duplicate them | waiting |
| G2 primary + guard | **yes, third.** One round over a primary dataset and guard datasets; a guard is a pass/fail limit, not a ranking; round-evidence says "beats the baseline on the primary and passes every guard". Today two goals kept in step by hand | **no.** Its guards are on the same dataset (triage v2's "false_dismiss no worse" on labelled_v2, which also carries triage_cost); the dedup guard is an `expect_identical_to` pair | waiting |
| G4 lineage | **maybe.** `hypothesis.against` may do; wants it shown as a tree, and a parent on the model (training lineage) rather than the system, since R5b re-deployed the same models | **yes.** Each triage arm is a parent plus one change (a prompt rule; the stations contract; another model), kept today in ids, NOTES and `hypothesis.against` (4 systems). Wants "parent X, changed: prompt / model / stations / code" on the arm page, and pair-test taking the parent as the default `--b` | waiting |
| G3 selection only | **maybe.** The avoidance_val runs must never enter a comparison or leaderboard; `role: validation` covers it if every evidence view leaves validation runs out | **maybe.** bugfix_orrery and bugfix_podcast have _validation and _test splits; every run is on _validation, 0 on _test, kept by habit. Wants the marker on the dataset split ("this side is for selection"), not on each run; triage is covered by RFC-031's sealed split | waiting |
| G6 two deployments | **no.** Separate systems per deployment are clearer, if G4 can say "same model, other deployment" | **yes, with a case; the one item that would change a number it reports.** triage_v1_dc3315d_v1 calls the LiteLLM alias eval-fleet-triage-pro (OpenRouter, DeepSeek V4 Pro); from 11-16 to 11-21 decisions in Chinese went from 0 of 1,040 to 10 of 382, and nothing recorded separates an upstream provider change from its own reply-cap change. Wants the provider and model the gateway reports per call recorded and compared like a deployment field, so a repeat across a provider change is "not the same measurement" and splits from its arm | waiting |

To check before deciding (questions robotics' answers raise about what 0.8.2 already does): whether an evidence view
(leaderboard, comparison-show, goal page) includes runs on a `role: validation` dataset (G3); whether a descriptive
metric can be added to a frozen run, and whether the catalog or inspector filters items by a metric (G5).
