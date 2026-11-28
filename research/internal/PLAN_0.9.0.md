# 0.9.0: the plan

**Status:** 2026-11-28. Branch `090`, from `origin/main` at `c6524b189` (0.8.3, released and deployed). **The owner's
decision (2026-11-28): no 0.8.4; 0.9.0 next, building the scope robotics-evals' case pinned here** (G1-G6, V1-V4, and
what it hit in practice), with what PLAN_0.8.4 had collected (sections P and B, housekeeping) folded in. Also named for
0.9.0 earlier and not part of this pass unless the owner says: the scenarios (RFC-035, RFC-036, RFC-037, all Draft).

## How this release is worked (carried over from 0.8.3)

- Quality, consistency and completeness come before the timeline. Every finding is fixed, the nits included.
- The docs describe what exists now, and every documented command works (`check_commands`, `check_shown_commands`,
  `guide-check`).
- A significant design gets an RFC (or an ADR for a decision) before it is built; each item below says which.
- The work goes to subagents on a lower tier (Sonnet implementers and reviewers, Haiku for mechanical work, Fable for the
  advisor). A subagent's "passes" is checked by running it again.
- Each finding gets a failing test first, then the fix; each feature its tests in both stores.
- The gates run on a committed tree, and nothing is committed while they run.
- Real calls go through the homelab LiteLLM gateway: the release-check key (`~/.config/eval-harness/release-litellm.env`,
  `eval-gpt-mini` and `eval-claude-haiku`, $1 cap) for the real-call check; the scenario uses the project key
  (`~/.config/eval-harness/scenario-litellm.env`, key `eval-harness`, $100 cap: `eval-mistral-small`, `eval-llama-scout`,
  `eval-opus-5`), copied into the scenario project's git-ignored `.env`.
- The release follows `harness/docs/RELEASING.md`. Learned on 0.8.3:
  - `make release-smoke ARGS=--release` refuses a working copy that holds fetched gold references (the release guard,
    as designed), while `make verify`'s rescore test needs them. Run the smoke on a clean checkout of the candidate (a
    detached worktree with the venv linked), not in the worktree that ran `reproduce.py`.
  - After the deploy, `deploy-verify --project evals` needs one MCP tool call first (the skill says how).
- 0.9.0 is a minor release: a change that can move a result is allowed, and each one is named in the CHANGELOG and
  UPGRADING. Each item below says whether it can.

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

**Asked of every active beta project (2026-11-27), so no item is shaped on one project's feedback** (harness-bakeoff and agent-rules-eval are paused until next week and not asked): fleet, eval
(podcast-scraper-eval-data), robotics lab (ranking its own six) and homelab (asked whether it runs the provider
bake-off). Each answers per item: no / maybe / yes, a concrete case from its own evals and what it does today, and how
it should work if that differs. Their answers go in a table here before the owner decides what 0.9.0 builds.

### The answers

The bake-off is out of the survey: homelab does not run it, has not since its last change on 2026-06-12, and knows of no
session that does (it only serves the catalog at bakeoff-evals). Its owner is the operator's to name.

| Item | robotics-evals | fleet | eval (podcast) |
| --- | --- | --- | --- |
| G1 progression | **yes, first.** r5_avoidance_v2 across R5, R5b, M2c, M2d, R7 against rules_v1 (0.575): x rounds or arms in lineage order, y primary with its CI, a series per arm family, the baseline line, a mark for significant vs the baseline, the guard metric (collisions) as a second panel; on the goal page, the Workbench and `evh chart` | **maybe.** triage_orrery has 4 closed rounds and no promoted baseline after r4, so `chart trend` draws almost nothing; each arm's triage_cost across r1-r4 is told by hand in NOTES. Works only if it draws arms never promoted; a round that moved dataset (labelled to labelled_v2) breaks the line, never joins it | **no, as the project is.** No rounds: 365 imported runs, one per system id; progression lives in prose reports. Wanted only if it moved to rounds |
| G5 tags from the scorer | **yes, second.** stand_still and pivot_fail were the whole R5 story and none is visible. Descriptive per-item metrics may be enough if (i) they can be added to a frozen run without changing its declared results and (ii) the catalog and inspector filter items by them; then G5 closes as docs | **no.** Its adapters already score each failure kind as its own 0/1 per-item metric (false_dismiss, silent_drop, no_decision, table_miss, escalated); a second channel would duplicate them | **maybe.** The naming scorer's per-voice outcome (right, wrong, unnamed) is collapsed to per-episode counts before import, and the summary gates (boilerplate_leak, speaker_label_leak, truncation) stay in its own files. Wants import-run to take them per item as a column of the scores file |
| G2 primary + guard | **yes, third.** One round over a primary dataset and guard datasets; a guard is a pass/fail limit, not a ranking; round-evidence says "beats the baseline on the primary and passes every guard". Today two goals kept in step by hand | **no.** Its guards are on the same dataset (triage v2's "false_dismiss no worse" on labelled_v2, which also carries triage_cost); the dedup guard is an `expect_identical_to` pair | **maybe, in another shape.** 14 of 19 goals have a prose `guardrails:` block, mostly on the same dataset or on cost and latency ("boilerplate_leak=0", "segment_drift p95 <= 300 ms"); nothing checks them. Wants a guard as a harness-checked limit on another measure of the same run before a two-dataset form |
| G4 lineage | **maybe.** `hypothesis.against` may do; wants it shown as a tree, and a parent on the model (training lineage) rather than the system, since R5b re-deployed the same models | **yes.** Each triage arm is a parent plus one change (a prompt rule; the stations contract; another model), kept today in ids, NOTES and `hypothesis.against` (4 systems). Wants "parent X, changed: prompt / model / stations / code" on the arm page, and pair-test taking the parent as the default `--b` | **no, as the project is.** Lineage is in ids and folder names; with one-run arms a graph would have no edges unless its importers wrote them |
| G3 selection only | **maybe.** The avoidance_val runs must never enter a comparison or leaderboard; `role: validation` covers it if every evidence view leaves validation runs out | **maybe.** bugfix_orrery and bugfix_podcast have _validation and _test splits; every run is on _validation, 0 on _test, kept by habit. Wants the marker on the dataset split ("this side is for selection"), not on each run; triage is covered by RFC-031's sealed split | **yes; the item that would change a number it reports.** 182 runs are prompt candidates on dev and smoke datasets against 8 on the benchmark; today only the dataset's name says so, and a dev candidate shows with a test result's standing. Wants the mark per dataset, not per run. Leaving a selection dataset out of leaderboards and goal pages by default would drop curated_5feeds_dev_v1's 134 runs from those views |
| G6 two deployments | **no.** Separate systems per deployment are clearer, if G4 can say "same model, other deployment" | **yes, with a case; the one item that would change a number it reports.** triage_v1_dc3315d_v1 calls the LiteLLM alias eval-fleet-triage-pro (OpenRouter, DeepSeek V4 Pro); from 11-16 to 11-21 decisions in Chinese went from 0 of 1,040 to 10 of 382, and nothing recorded separates an upstream provider change from its own reply-cap change. Wants the provider and model the gateway reports per call recorded and compared like a deployment field, so a repeat across a provider change is "not the same measurement" and splits from its arm | **no, as the project is.** Its cases were byte-identical copies (left out of the import); where one model was served two ways, the server is in the system id |

To check before deciding (questions robotics' answers raise about what 0.8.2 already does): whether an evidence view
(leaderboard, comparison-show, goal page) includes runs on a `role: validation` dataset (G3); whether a descriptive
metric can be added to a frozen run, and whether the catalog or inspector filters items by a metric (G5).

### What the three answers say together (2026-11-27)

| Item | robotics | fleet | eval | Reading |
| --- | --- | --- | --- | --- |
| G3 selection only | maybe | maybe | yes | Wanted by all three, in one shape: the mark on the dataset (or split side), never on each run. The only item two projects would see change a view |
| G1 progression | yes | maybe | no (withdrawn) | Robotics' first ask; fleet needs it to draw arms never promoted and break at a dataset change; nothing to draw for one-run arms |
| G5 failure metrics | yes | no | maybe | Robotics and eval want per-item failure flags from their own scorer in the scores file; fleet already does it as 0/1 metrics. Likely docs plus a filter, if the checks below hold |
| G2 guards | yes (second dataset) | no (same dataset) | maybe (same run, limits) | The common need is a harness-checked limit on another measure; same-dataset first, a second dataset only robotics |
| G4 lineage | maybe | yes | no (withdrawn) | Fleet's shape: "parent X, changed: prompt / model / stations / code" on the arm page, pair-test's default `--b` |
| G6 deployments | no | yes | no (withdrawn) | Fleet's case only: the provider and model a gateway reports per call, compared like a deployment field |

To check against 0.8.2 before the owner decides, read-only: whether goal `axes` limits already check a same-run guard
(G2's common case, and eval's prose `guardrails:`); whether evidence views include runs on a `role: validation`
dataset (G3); whether a descriptive per-item metric can be added to a frozen run and whether the catalog or inspector
filters items by a metric (G5).

### What robotics-evals hit in practice (2026-11-27, after its move onto rounds, models and systems)

Defects in shipped behaviour went to PLAN_0.8.3 (B1-B7). What feeds the items here:

- G1: `evh chart trend --goal r5_avoidance_v2` refuses "0 baseline version(s) and 0 of 2 closed round(s) that promoted a
  run": a round closed with nothing promoted is a result and no trend point.
- G5: an imported run cannot gain a metric. `evh rescore` finds no adapter for an imported run; a second `import-run`
  of the same system fails V8 (no `--purpose repeat`/`--of` on import-run). Asks for `import-run --of RUN` or a repeat
  that attaches descriptive metrics. Its imported runs record `metric_kinds: {}`.
- G2: `limit: baseline` needs a promoted baseline and is a paired p<0.05 test, so its pre-registered "collision count
  not above the rules arm's" cannot be said; with nothing promoted goal-leaderboard applies no limit. Asks for a limit
  that reads the round's `--baseline`, or a count-based limit against it.
- Scorer equivalence: imported runs scored by one script at different commits read as "scored by different scorers";
  asks to declare them equivalent.
- G6: one system names one deployment; rules_v1 was measured at two lab commits. Asks for a deployment per dataset, or
  per run on import-run.
- G4: lineage only in `hypothesis.against` and its statement, no view.

**Eval withdrew its G1, G4 and G6 answers (2026-11-27).** Its "every arm has one run" came from its own importers
putting the dataset and the reference into the system id (216 of 365 ids end in `__vs_<reference>`, 284 hold a dataset
name), against INTEGRATION's rule that a dataset is the run's, not the system's. A draft re-mint maps the 365 runs to
142 systems; it is not applied, because 26 groups (166 runs) would merge runs that differ only in what no stored file
records (a vLLM server setting, which model the alias `autoresearch` served). It answers again after the re-mint.

## V. Views borrowed from MLflow and TensorBoard (2026-11-27)

From the assessment (PLAN_0.8.3, A; `research/internal/MLFLOW_TENSORBOARD.md`). The owner's frame: not import or
export into either tool, but what evh can learn from how they let people see results, built on what evh records.
Put to the three beta projects.

| Item | View | robotics | fleet | eval | Reading |
| --- | --- | --- | --- | --- | --- |
| V3 | Items that flipped between a parent and a child, filterable by a per-item metric or field | yes (which items the walls model reaches that M2b did not; needs per-item metrics on imported runs) | yes (wrote its own scripts last week; needs each item's k-of-n over repeats and a way to leave out passes lost to the transport) | yes for summaries (pairs by item today), maybe for naming (per-voice outcome collapsed before import) | The one all three want |
| V2 | "What each change bought": the chain along `hypothesis.against`, each step the paired difference from its parent | yes, close second (its changes live in the training run, so label by `hypothesis.statement`, the config diff only a cross-check; flag a step with more than one change) | yes (its systems differ in one or two keys, so the diff works; also a parent named on the command line, since 4 systems carry `against`) | maybe (its cells differ only in vLLM settings no file records, so the diff is empty) | Label by the statement, fall back to the diff, flag a step with more than one change |
| V4 | A selection curve that is never evidence | maybe-yes (3 checkpoints per training; would import them only if kept out of leaderboards and paired tests) | maybe (candidates are discrete systems: a marked list, not a curve) | yes, it is G3 (182 prompt candidates; the iteration order lives in names, not a field) | The same as G3; a list unless an order is recorded |
| V1 | A progression chart that carries a verdict | yes (x = arms in lineage order; the guard panel with its limit line, arms that break it marked) | maybe (as G1: only if unpromoted arms are drawn) | maybe (one system across its dataset ladder; depends on the re-mint) | Robotics' first ask; the others need lineage or unpromoted arms |
| V5 | A judge's disagreements with people as a reading list | no (no judge) | no (gold labels and test oracles) | no (two model judges by the owner's decision, no people) | Dropped |

## M. What changed a result and nothing recorded (2026-11-27)

Two projects found the same hole from different sides: two runs look like one measurement when they are not.

- fleet (G6): `triage_v1_dc3315d_v1` calls the alias `eval-fleet-triage-pro`; the provider OpenRouter routed to is not
  recorded, so decisions in Chinese going from 0 of 1,040 to 10 of 382 cannot be put down to the provider or to its own
  reply-cap change.
- eval (V2, the re-mint): vLLM server settings (memory utilization, max sequences, max length, warmup) and which model an
  alias served are in neither the system file nor the fingerprint.

The question for 0.9.0 is what a deployment records and compares: what a gateway reports per call, and the serving
settings that can move a score. It is wider than G6 as first written. A related note from fleet (V3): its adapter writes
"triager call failed" as the decision after two failed calls, so `pair-test` counts transport failures as model
decisions; an adapter that reports the call failed instead keeps them out. That is guidance for adapter authors
(INTEGRATION), not a new feature.

## C. What a comparison calls an instrument change (the 0.8.3 newcomer run, 2026-11-27)

In an installed project, a run's `fingerprint.instrument.harness.commit` is the project's own git HEAD (`_fingerprint._harness_identity`:
`commit` and `dirty` describe the project's tree; `version` and `code_sha256` are the harness's
identity when it is a dependency). `evh run-compare` counts any instrument difference as a confound, so two rounds' runs
in a project that committed between them (every round: round 2 adds a system file) read "instrument differs:
harness.commit" and "not a controlled comparison", with `version` and `code_sha256` equal. The owner's choice (2026-11-27):
recorded for 0.9.0, not fixed in 0.8.3. To decide: whether, with the harness installed, a moved project commit with the
same `version` and `code_sha256` is shown as the project's change and left out of the confounds (display only, no hash
changes), and what of the project a run depends on (its adapters, prompts) is already identified elsewhere in the
fingerprint.

## P. Left from 0.8.3 (from PLAN_0.8.4)

| Item | What | Done when | Moves a result |
| --- | --- | --- | --- |
| P1 | `run-compare` between two rounds' runs in an installed project reads `instrument differs: harness.commit` and "not a controlled comparison" when only the project's own commit moved (`commit` is the project's tree; `version` and `code_sha256` equal). **Open:** the owner put it in 0.9.0 (PLAN_0.9.0, C); it is display only, so it could be a patch | the owner's choice; if here: a moved project commit with the same `version` and `code_sha256` is named as the project's change and left out of the confounds, tested | no (display; no hash changes) |
| P2 | `comparison-show`'s Conditions showed `deployment.model` in the 0.8.3 newcomer run, where `catalog_adapter.conditions` says the arm's model is left out (what an arm varies). Not checked which is wrong | the code and its docstring agree, with a test | no |
| P3 | The note "no goal or adapter says which way is better; read as higher-is-better" is printed for runs with no goal (a job on `briefs_v2`), on judged leaderboards and in `validate`, after the goal declared `direction: higher` | said once where it applies, or the runs it covers named | no |
| P4 | The dry run's "at most" estimate for the frontier arm was 15x what it spent (`~$0.7574` at `max_tokens 1500` against $0.0489). It is the bound it says it is; a newcomer under a $1 cap hesitates | the estimate's line makes the bound's cause plain (the `max_tokens`), or the typical figure leads when one exists | no |
| P5 | The newcomer run did not exercise, for real: a 403 from a provider, the retries on a persistent 429 or 5xx, and retiring an arm from the Workbench's Close screen (covered offline: `tests/test_providers_wire.py`, the Workbench browser suites) | each exercised once, or the reason it is not written in SCENARIO | no |

## B. The beta projects on 0.8.3 (from PLAN_0.8.4)

| Item | What | Done when | Moves a result |
| --- | --- | --- | --- |
| B1 | robotics-evals, podcast-scraper-eval-data and fleet-eval-data move their pins to `v0.8.3`; homelab's evh-serve instances (`agentic-ai-homelab` `infra/evh-serve/instances/`) move with each project's pin | each reports `evh validate` and what moved; a break is an item here | no |
| B2 | harness-bakeoff (evh 0.8.0) and agent-rules-eval (0.8.0.dev0), paused until next week, cross 0.8.1, 0.8.2 and 0.8.3 at once | each runs the check the others ran (non-ASCII ids, `validate`, a re-read of its results); what breaks is an item here | no |

## Housekeeping (from PLAN_0.8.4)

**Done 2026-11-28, the owner's go:** removed the 083, 080 (with `build/clean-wt`), 080-rfc038 and mbpp-code worktrees,
`baseline-tmp/baseline-diff-080`, the 083 branch (local and remote) and the remote `0811-fix`; the scenario folders of
0.8.0, 0.8.1 and 0.8.3 (with the scratch copy of the gateway key). The scenario key is kept once, in
`~/.config/eval-harness/scenario-litellm.env` (mode 600). Local branches 080-rfc038 and mbpp-code are kept.

- **Open:** `worktrees/044` (branch 044, no remote, last commit 2026-10-28) holds uncommitted work: 13 modified files and
  6 untracked under `site/art/` (sketches, masters, `make_sketches.py`, `experiments/`). Not removed; the owner decides.
- `/work/evh-scenario-040` and `040b` (0.4.0's scenario runs) still hold copies of the gateway key in their `.env`; not in
  the approved list.

