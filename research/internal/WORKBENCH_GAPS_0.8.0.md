# The Workbench against the 0.8.0 model: stale definitions and API gaps

2026-11-17. The owner's order for the Workbench step: first realign the UI definitions (PRD-017, UXS-005, the mockup
in `harness/workbench/`) with everything built since they were written, then identify the API's gaps clearly and
start from there; and before any UI work, deal with the reviews and settle.

Source: an independent review by Fable 5.1 (part 2 of the 2026-11-17 round), read against the code at 02524325b.
Every point below was checked against the code before it was written here; where the review was wrong or
unverified, the row says what is true. The API counted: `evh openapi`, 154 route-method pairs (`build/api_inventory.txt`
lists them by resource).

## Decided (owner, 2026-11-17: "accept all" the recommendations)

| # | Question | Decided |
|---|---|---|
| D1 | `validate`: PRD FR6 calls it a job; it is a read (`GET /api/v1/validate`, ~27 s, in the server's process) | keep it a read; the page says "checking…"; change PRD FR6 |
| D2 | Running a round's arms: RFC-032's promised `round-run` was never built; `sweep` takes `systems[]`, `goal`, `round` | the UI calls `sweep`; drop `round-run` from RFC-032 |
| D3 | "A retire can be undone until the round closes" (UXS-005, the mockup): no operation un-retires | drop it: a retire is a recorded decision with a reason |
| D4 | "Approve as vetted" (PRD-017, UXS-005, the mockup): vetted is computed (every deployment's onboarding passed and an arm smoke passed); no operation approves | drop the Approve step; show the rule |
| D5 | The round's question is stored as `hypothesis`; the UI and UXS say "question" | keep `hypothesis` in the model, say "question" on the page (renaming needs your yes) |
| D6 | W7 "validate the judge here": the validators are tools (`tools/validate_judge_*.py`), not operations | was cut from v1; built later in 0.8.0 as the operation `judge-validate` (RFC-038), and W7's part c validates and writes |
| D7 | `mock.js` (169,824 bytes of this repository's data) ships in the package and loads on every installed project's `/workbench/`; `mock_data.py` cannot run on format 7 (no `data/configs`, no `data/runs-linux`) | stop shipping it; keep the mockup as a frozen design reference and build the live screens from UXS-005 |
| D8 | The Workbench behind a proxy: `/api/v1` and `/workbench` answer 404 under `--public` and `--behind-proxy` | stays refused for 0.8.0 |
| D9 | config.yaml settings in W8 (e.g. exposure repos): `data-put` writes only under `data/` | out of v1 |

## The API to build first (each blocks a screen)

1. **Superseded (owner, 2026-11-17): not saved item by item.** The labelling screen fills a sheet and submits it
   when done, to the imports as they are; what is missing is the blind sheet and its key as a job (`sheet-export`
   as an operation, the key kept on the server for `sheet-import`). The original item: one label, pick or tag for
   one item (W2, step 3c). Today only a CSV upload writes them
   (`sheet-import`, `label-import`), each a job holding the dataset's lock; RFC-032 named this gap
   ("one label or one pick can only be written as a CSV"). Shape to decide: an edit
   `POST /datasets/{dataset}/label-sets/{set}/items` (under the dataset's lock, `by`), or JSON rows accepted by the
   two imports.
2. **A source preview**: describe a source and its first rows, write nothing (step 2a). No read reads a source;
   `dataset-create` has no `dry_run` (so `POST /estimate` refuses it).
3. **A reference from the dataset's own answers** (step 3c "it came with one"): `reference-promote` needs a label
   set; nothing makes one from an answer column (the Hugging Face source reads none). Either the source reads an
   answer column into a label set at create, or `reference-promote` takes the dataset's answers.
4. **`score-preview` gives a result** (W6): it only prints (`score_preview.py`, no `_jsonout`), so a job's `result`
   is empty. Also decide whether W6's "what it moves" previews a new reference (not built) or a scorer change
   (what `score-preview` does); `leaderboard?label=` covers the mockup's case today.
5. **The jobs list**: several states per query (today `state` is one exact match, so the home's
   `?state=running` misses `queued` and `running (unsupervised)`), filters by operation and goal, offset/limit.
6. **A JSON 500 always**: without `--hooks`, an unhandled error re-raises (`catalog_serve.py`, `if HOOKS is None:
   raise`) and the browser gets a broken response, not `{error}`.

Smaller, found on the way: progress (`done/total`) only for run, sweep, rescore and judge-score; dataset-create,
materialize and profile report none. No clone of a system (step 4 composes a new `set` from `system-show`); what a
minimal `set` holds for the bundled adapters is not documented. `GET /api/health` (old route) is the only read of the
catalog's rebuild state.

## Stale definitions (to realign in PRD-017, UXS-005 and the mockup)

Done for PRD-017 and UXS-005 on 2026-11-17 (both rewritten against RFC-032 and D1 to D9; RFC-032's `round-run`
passage amended for D2). The mockup stays as reviewed, a frozen design reference (D7).

- **The governing RFC**: PRD-017 names RFC-026 for the API; RFC-032 (and RFC-033) replace its model and amend it.
  UXS-005's "mock data model" table and ER diagram are superseded by RFC-032's entities (system, score, baseline
  versions, study, exposure, faithfulness are missing from the diagram).
- **Config → system**: UXS-005, `workbench.js`, `round5.js`, `mock_data.py` still say config (`run --config`,
  `arm-smoke --config`, `faithfulness --config`, `jobs-start run --arg config=`, `config_id`). Now `--system`/`--dataset`.
- **Arm**: "a model with a prompt and settings, on a dataset" (glossary, ER) is a system now; an arm is a system
  placed in a round, stored on the round with its label, runs and retirement. "Each arm's config names the round"
  is the retired mechanism.
- **Models and deployments**: deployments live apart (`data/deployments/<model>/<deployment>.yaml`) with a dated
  history of checks; the states are `vetted / onboarded / check / none`, not `pass / probed / check / none`.
- **Runs and scores**: one `data/runs/<id>/` with `purpose`, scores under `scores/<scorer>@<reference>/`, per-item
  rows in either store (RFC-033); no `runs-linux`, no `outputs.jsonl` beside `metrics.json`.
- **Rounds**: arms are stored; `carried`/`retired` lists are gone; evidence is `model/rounds.evidence`, its rows carry
  their Holm `threshold` (checked: `stats.py` `_set_verdict`).
- **Jobs**: the record is `{id, operation, inputs, by, locks, env, run_id, state, progress, spent_usd, result, files}`
  (`files` added in the build: what the job wrote for the person, by name); no `command`, `argv` or `reason`. A job's "command it runs" is built by the UI from the operation and its inputs.
- **Labels, picks, references**: `pick` is the production-record pick, not an A/B preference; `sheet-export` is not
  served (the sheet is downloaded from a job's artifact); reference promotion needs a label set.
- **Prompts**: `prompt-version` needs a `name` and a `note`.
- **Validate** is a read (D1). **Round run** is `sweep` (D2). **Undo retire** and **Approve as vetted** have no
  operation (D3, D4).
- **Store**: a project names its store at `evh init`; the Workbench cannot make a project, so its empty-project
  screen presumes `evh init --store …` ran.
- **Who acted**: every write carries `by` (and an agent `for`); every decision its reason input
  (round-retire `reason`, round-close `conclusion`, run-promote `reason`, ...). The live pages keep the name in the
  browser; UXS-005 does not say so.
- **Goal step 1**: `goal-new` must be sent `datasets: []` (checked: without it, `datasets: required`; with it, saved).
- Scope lines: PRD "80 commands" is now 154 route-method pairs; PRD decision 4 is done, decision 5 superseded.

## Per screen (✓ served, ~ partial, ✗ missing)

| Screen | Served by | Gap |
|---|---|---|
| Home | `GET /goals`, `GET /goals/{goal}/status`, `GET /jobs` | ~ jobs filter (API 5); one status call per goal |
| 1 Goal | `POST/PATCH /goals/{goal}`, `GET /metrics`, history | ✓ (send `datasets: []`) |
| 2 Dataset | `GET /datasets`, `PATCH /goals/{goal}`, fieldset-propose, fieldset-new, `POST /datasets/{dataset}`, captures | ✗ preview (API 2), ✗ answer column (API 3), no progress |
| 3 Prepare | materialize, profile, dataset-show, dataset-items, label-sheet, label-import, reference-promote | ~ items have no offset/limit; ✗ reference from answers (API 3); ✗ label one item (API 1) |
| 4 Models | `GET /models`, goal-leaderboard, prompt-version, system-new, arm-smoke, `POST /estimate` | ~ no clone of a system |
| W5 Bring in a model | model-new, deployment-new, model-onboard, model-show, deployment-history, deployment-accept | ✓; drop "Approve as vetted" (D4) |
| 5 / W1 The eval | goal-leaderboard, baselines, rounds, round evidence, round-open, sweep, estimate, rescore, judge-score, round-retire, run-promote, round-close, arm-show, comparison-item | ✓ for the chart use evidence + `leaderboard?goal=&round=`; ✗ undo retire (D3) |
| W2 Review, label, tag | sheet-show, comparison-items, failure modes, tag sets, label sets | ✗ one item's pick/label/tag (API 1); sheet-show answers blocks, not per-item rows |
| W3 Production | capture, arm-from-capture, label-from-capture, label-coverage, sheet-show, pick, dataset-extend, periods, faithfulness | ✓ (coverage's rules file must be in the project) |
| W6 Reference | references, label sets, reference-promote, rescore | ~ score-preview gives no result (API 4) |
| W7 Judge | scorers, scorer-new/set, judge-score, estimate, cost-report | ✗ validate here (D6) |
| W8 Settings | validate, migrate, data-migrate, data-put, publish | ~ validate is a 27 s read (D1); ✗ config.yaml (D9) |
| Held-out, study | dataset-split, exposure, sealed counts, unseal, pair-test, looks, study-* | ✓ |
| Jobs | jobs, job, log, files, stop, resume | ~ progress for four operations only |

Cross-cutting, checked: the token is new at every server start (a stale cookie answers 401 on any call, not only the
first); every non-GET needs `X-EVH-Data: 1`; uploads are base64 JSON, at most 50 MB a call; progress is polling only
(no events); the UI must render four refusal shapes (an edit's `{error, kind, problems}`, a job refused before it
exists `{error}`, a job that failed later (`state`, its refusal kind, the log), 503 + Retry-After during a migration).
Mobile: the mockup's tables of four or more columns stack into cards; two- and three-column tables, the live model
page's forms and the jobs list were not covered by the 390 px browser tests (every live screen is, since the build).

## Order once the reviews are settled

API 1-6 above and the unsent-changes rule (owner, 2026-11-17: UXS-005 "For every live screen"; the live goal,
model and deployment forms have no leave guard today), then the screens in this order: Home and Goal (wired) → W5 (wired) → steps 1-3 (need API 2, 3) →
step 4 → W1 the eval (every route exists) → W2 (needs API 1) → W3 → W6, W7, W8 as short lists → the held-out and
study screens last. PRD-017 and UXS-005 are rewritten against RFC-032 first, with the decisions above.
