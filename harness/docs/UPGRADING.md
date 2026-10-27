# Upgrading

Two cases. **If you pin a release**, read the section for each release you cross, below:
change the pin, then check what it says can move. **If you copied `harness/` into your
repository** before October 2026, read the rest of this page first: your copy has
correctness bugs, not just missing features.

## From 0.4.1 to 0.4.2

Change the pin to `@v0.4.2`. No record, hash or p-value moves. One command line changes:
**`evh overview` no longer takes `--all`**: `evh overview --period all` says the same (`--period P` on every list now,
counted from today). Everything else is added and optional: an adapter may answer
`dataset_created(dataset)` and `model_facts()` (each model's weights, open or proprietary; the
harness's own adapter reads an optional `data/models.yaml`), `spend()` events may name an `arm`,
and `catalog-serve --hooks` takes a deployment's error reporting, tracing or metrics. `evh
bootstrap-test` now refuses when the gold references are not on the machine, where it read none.

## From 0.4.0 to 0.4.1

Change the pin to `@v0.4.1`. Nothing moves: the same records, hashes and p-values. The inspector
fits in a 256 MiB container again after `--warm` on a large catalog, and `evh catalog` gains `--head`,
`--api` and `--brand`.

## From 0.3.0 to 0.4.0

Change the pin to `@v0.4.0`. **One install is everything:** `openai` and `anthropic`, the
clients of the hosted providers and the judges, are core dependencies now, and the `[llm]` extra
is gone. If your pin names it (`evaluation-harness[llm] @ git+…`), drop `[llm]`; pip warns about
an extra that no longer exists. Nothing else is added. 0.4.0 reads only its own record format,
so check these before you trust a `validate`:

- **Fingerprints are version 4: documentation never moves a hash.** Code is hashed by what it
  does, its syntax tree without docstrings, comments, formatting or `METRIC_DESCRIPTIONS`: your
  adapter, the harness's measuring modules and a judge scorer's own hash. A judge scorer YAML is
  hashed by its parsed content, and a reference manifest's `caveat` is outside the reference
  digest. Before, adding metric descriptions to an adapter made `run-compare` and the inspector
  call every earlier run "not the same conditions". **v3 and v4 digests are not comparable**:
  a run made on 0.3.0 and one made on 0.4.0 differ in their adapter, scorer and reference hashes
  even where nothing changed, and 0.4.0 ships no command that rewrites old runs' hashes (this
  repository's own were migrated once, by matching each recorded hash to the code it came from).
  Compare runs made under the same version, or re-run the arms you compare. No score changes.
- **`import-run` hashes the scoring code itself: `--scorer-file` replaces `--scorer-sha256`.**
  Pass the file (or several, repeated in a fixed order); the harness hashes it by the same rule,
  so a docstring in your scorer is not a new scorer, and the hash is the run's
  `instrument.adapter.sha256`, inside the fingerprint hash. Before, it sat in `imported`, outside
  the hash, so two imports scored by different versions of the code looked like the same
  conditions. A script that passed `--scorer-sha256` is refused (exit 2): pass the file.

- **Derived runs** (rescore, judge-score) record `derived: {kind, from, at, with}`; the
  0.3.0 fields (`rescored_*`, `judged_*`, `judge_label`, `primary_metric_asc`) are read by
  nothing. Re-run `rescore` / `judge-score` on the runs you keep.
- **Baselines** carry the run's reference tier, adapter and fingerprint hash, and V6 fails
  one that does not: promote each again (`evh run-promote`). `data/baselines/superseded/` is
  no longer written; git keeps a replaced baseline.
- **Configs** may hold only `config_id`, `dataset_id`, `params`, `adapter`, `goal`, `round`
  and `format` (V1); anything else was read by nothing.
- **Run records** may hold only the fields the harness writes (V1). A run imported with
  0.3.0's `import-run --asc` carries `primary_metric_asc`, which no version read: the metric
  was ranked higher-is-better unless every command passed `--asc`. Replace it with
  `metric_directions: {<metric>: lower}` (or re-import with 0.4.0, which writes that), and
  `--asc` becomes unnecessary.
- **Judge verdicts** need `output_sha256` and `output_withheld` (V1): the hash of the stored
  reply, and false.
- **Judge scorers state both controls.** A scorer's `protocol` must set
  `position_check_fraction` and `noise_check_fraction` (ADR-0001 §4): the noise check above 0,
  and the position check above 0 when `outputs_per_call` is above 1. A scorer without them is
  refused. Before, a scorer that left one out ran the pass with that check off. Add both (0.5
  each is what the tutorial's scorer uses).
- **`--resume`** takes a run made by 0.4.0 (rows with `_extra`); `--resume-unverified` is
  gone.
- **`evh judge`** is the judge panel (it sat beside the package and could not run from a pin);
  the tutorial kit ships `tutorial/judge_panel.yaml`.
- **Your adapter**: put it at the project root as `adapter.py` and an arm with no `adapter:`
  uses it. Code that imported `catalog_adapter.load_adapter` imports `load_catalog_adapter`;
  a script that relied on importing the package to read `.env` loads it itself
  (`evaluation_harness._common.load_dotenv()`).

**What can move a number:**
- **`pair-test` and `family-test` on 30 items or fewer** now count the exact p over all 2^n
  sign patterns instead of estimating it from 20,000 permutations. Re-run them on any pair
  with 30 or fewer shared items: a verdict that sat near its threshold can move. Above 30
  items nothing changes, bit for bit. `pair-test` prints which it did.
- **`family-test`'s cache** recomputes once: its key includes the new `stats.py`.
- **`validate` V4** now fails a materialized copy that has lost an item file, and names each
  dataset it could not check. A project whose copy is incomplete goes red where it was green.
- **The direction of a metric is decided once, for every command and the inspector:** a flag,
  else the goal your runs name, else the adapter's new `METRIC_DIRECTIONS` (or `import-run
  --asc`), else the name (costs, latencies and token counts go down). Before, `pair-test`'s
  "A wins", `family-test`'s wins and "ahead", the leaderboard's order and its significance
  block, `holdout` and `rank-stability` counted the higher score unless you passed `--asc`
  (`holdout` and `rank-stability` had no flag), and a goal's direction was read by the goal
  page alone. p-values do not change: the tests are two-sided. `--asc` and `--desc` override.
  `validate` (V14) now fails a goal whose direction contradicts what its runs record.
- **`validate` checks every committed `runs*` directory** (V7, V8, V9), read from git: it
  checked only this repository's six directory names, so a project's own `data/runs-adjudicated`
  was never validated. Declare the list, floors, scorer sources and duplicate exceptions in
  `<data>/validate.json` (RUNBOOK §9), which replaces `validate_floors.json`: move its
  `floors` there.
- **The core times every call.** `latency_ms` is recorded for any adapter that does not report
  its own (the attempt that answered, not the retries' backoff). A project's runs gain a latency
  column, and the leaderboard its cost/speed frontier.
- **`validate` V5 no longer fails two different arms that are both perfect** on a binary metric:
  their outputs tell two measurements from a copy. A tree that failed only on that goes green.
- **`provider: openrouter` calls OpenRouter by default**, with `OPENROUTER_API_KEY`. Before, an
  arm that named it without `base_url` and `api_key_env` read `OPENAI_API_KEY` and called
  OpenAI's address. An arm that sets either keeps its own; one that set neither now calls a
  different endpoint, so treat its next run as a new measurement.
- **A judge goes where its `provider:` says, and every judge must declare one.** Judges used
  to ignore it: a LiteLLM proxy when `LITELLM_BASE_URL` was set, else OpenRouter with the
  model looked up in `$EVAL_MODELS_FILE` or `<project>/models.json`. Now the judge is called
  through the same providers as an arm, with the model as written, and the harness reads no
  models table. A scorer whose judges went to OpenRouter that way names `provider: openrouter`
  and the OpenRouter id (`vendor/model`) the alias stood for; that is a new judge identity, so
  its validation must be measured again. The committed scorers declare `provider: litellm`:
  re-running them needs a LiteLLM proxy (`examples/litellm.config.yaml` serves their aliases).
- **Judging can have its own keys.** A judge reads every variable as `EVAL_JUDGE_<NAME>` first,
  then `<NAME>`; with no `EVAL_JUDGE_` variable set it shares the arms' keys, as before.
- **The judge panel's judges are declared** (`id`, `provider`, `model`, `usd_per_mtok_in`,
  `usd_per_mtok_out`) where its config named a model string, and the fake judge runs only with
  `--use-fake-judge`: a missing `ANTHROPIC_API_KEY` used to swap it in silently.
- **`leaderboard` prints one table per way of scoring.** When a dataset's runs were scored more
  than one way (silver and gold, a judge, or runs made before any reference existed), each gets
  its own table and tests, gold first, under `=== scored against <ref> ===` (judged runs:
  `=== scored by judge <scorer_id> ===`), and nothing is averaged across them. Before, they were averaged into one row and one ranking. The
  catalog and the inspector read an arm against the reference of its latest run and say which
  earlier runs they leave out; `evh rounds` reads a round against the reference most of its arms
  use and names the arms it does not compare. With one reference the output is unchanged.
- **The bundled adapter stores `overlap_f1` unrounded** (it rounded to 6 decimals); a new run's
  mean can differ from an older one's in the sixth decimal, and the leaderboard's rounding note
  no longer fires for it.
- **`--exclude-dataset`** (`pair-test`, `family-test`, `holdout`, `bootstrap-test`) reads the
  excluded dataset's own item list. It read `data/sources/<id>/*.txt`, so a dataset whose items
  are not `.txt` files there was excluded wrongly, or not at all.

**New, all optional:**
- **The catalog and the run inspector** (`evh catalog`, `evh catalog-serve`). On the
  harness's own data layout they need no code; with another layout, write one adapter
  ([tutorial 5](https://evals.humancopilot.eu/docs/tutorials/5-catalog-and-inspector/)). Every
  view is also a command: `evh overview`, `evh datasets`, `evh arms`, `evh references`,
  `evh metrics`, `evh goals`, `evh search`, `evh inspect` (with `--items` for the per-item table
  and `--analysis` for the charts as numbers). **The home page** is now a dashboard (index.html
  moved, the datasets table is datasets.html). **Metric links** now go to m/<metric>.html pages
  (metrics.html#m-<metric> anchors still exist for compatibility). A project's own catalog
  builder that reuses `render_inspect` gets the arm and metric links only when the built pages
  exist (`pages=True` parameter).
- **Goals** (`data/goals/<goal_id>.yaml`, `goal:` on configs, validate V14). Nothing is
  required of an upgrading project until it sets `required_from` in `data/goals/policy.yaml`.
- **Experiment rounds** (`evh round-open`, `evh round-retire`, `evh round-close`, `evh rounds`;
  `round: rN` on configs; validate V14). `--round rN` on `leaderboard`, `family-test`,
  `pair-test` and `inspect`: `inspect --round` and `pair-test --round` default to the goal's
  measure and the round's leader (`pair-test`'s B: the baseline the round started from). A
  project that never opens a round sees none of it
  ([tutorial 4](https://evals.humancopilot.eu/docs/tutorials/4-rounds-and-versions/)).
- **A run becomes a reference:** `evh reference-create --from-run <run_id>` copies a finished
  run's outputs and calls nothing; the reference records the run. `reference-create` now refuses
  an empty output and outputs that stopped at `max_tokens`, by either path (`--allow-cut-off`).
- **Dataset versions keep their lineage:** `evh dataset-create --dataset-id x_v2 --from x_v1`
  (`derived_from` in the dataset file; validate V2).
- **Item fields and URL items** (`data/fields/<fieldset_id>.yaml`, `dataset-create --fieldset
  --fields`, `--manifest`, validate V15). The dataset schema only gains optional keys, so
  every 0.3.0 dataset is still valid; a dataset that uses them needs 0.4.0 to validate. If
  you keep a second registry of facts about your items beside your datasets, this replaces
  it: declare the facts as fields and attach them with `--update-fields`, which changes no
  run's fingerprint.
- **`success_criteria.secondary` is removed; goals weigh axes** (ADR-0006). A goal that
  still has `secondary:` fails `evh validate` (V14). Move each entry to `axes:`, keyed by its
  measure:

  ```yaml
  # before
  secondary:
    - {measure: rouge1, direction: higher}
    - {measure: usd_per_min, direction: lower}
  # after
  axes:
    rouge1: {direction: higher}
    cost: {measure: usd_per_min, unit: USD per audio minute}   # a built-in, another measure
  ```

  A `threshold` becomes a `note` (shown), or a `limit` if an arm past it should be out of the
  recommendation. An entry with no number to compare (a human review) belongs in
  `guardrails` (`{name, rule, source}`), which are shown and never computed, as before. Cost
  and speed need no entry. Without a `strategy` a goal is `balanced`.

**Also changed:** `pair-test`, `family-test`, `holdout` and `rank-stability` read the
primary metric your runs recorded when no `--metric` is given. They used to default to
`coverage`, the summarisation example's metric, and said "no runs" or crashed in any project
that does not score it. Pass `--metric` as before to choose another.

Also:
- A run's `instrument.harness.code_sha256` hashes only the code that can move a number (the
  run-writing commands and what they import), not the package's tests and read-only
  commands. Runs made on 0.4.0 record a different value from 0.3.0 runs, as any upgrade
  does; `run-compare` names it.
- The bundled adapter refuses an unknown `provider:` (it fell back to `echo`, so a typo
  recorded the echoed input as the model's output) and records what an OpenAI-compatible
  provider billed when the response says so.
- Every command refuses with `ERROR: …` on stderr and exit 1, and refuses an argument it
  does not take with exit 2 (`validate`, `self-test` ignored them). Exit codes: RUNBOOK.
- `import evaluation_harness.judging` works, and the package's modules load once each.
- The wheel holds the package's code only: this repository's tests and report checkers
  moved to `harness/tests/` and `harness/tools/` in the checkout.

**After upgrading:** `evh self-test` (in a project it checks that the installed harness
works here: its paired test, and the tutorial end to end in a scratch folder), `evh
validate`, and re-run the small paired tests.

---

## Upgrading a copy of the harness taken before October 2026

If you copied `harness/` into your own repository before the review rounds of late
September and October 2026, your copy has **correctness bugs that can change results**, not
just missing features. This page lists what changed since the harness was extracted (the
first commit of this repository, `fb7366a0`, 2026-09-26), in the order you should care
about it, and how to upgrade.

### 1. Fixes that may have changed numbers you already have

Check each against how your copy was used. A "yes" means re-run or re-score the affected
runs after upgrading. Re-scoring from stored outputs costs nothing.

| if you… | the bug | fixed in |
|---|---|---|
| used `pair_test --family N` and called it Holm | it was **Bonferroni labelled as Holm** (more conservative, so some real separations were reported as ties). `family_test.py` now does the genuine step-down; `pair_test` says what it does | `a57d778b` |
| had a run crash or stop mid-sweep | **every paid item before the crash was lost**: outputs reached disk only after the pass. Now each output is written as it arrives | `c6e8365f` |
| resumed a run (`--resume`) | a fully resumed run **wrote empty scores and reported success**; replayed items lost their cost, tokens and diagnostics (a resumed run under-reported spend: $0.03 for $0.05 real); `--resume` **accepted another arm's outputs** without complaint | `c6e8365f`, `897c0bbc`, `3f16a79b` |
| ran out of disk, or killed a run | writes were not atomic, so a **half-written output was replayed as the model's answer** and scored | `8e98a885` |
| re-scored against a gold set that had changed | the rescored run **asserted the old reference hash** while scoring against the new files | `ebd54b60` |
| used a cost cap (`EVAL_MAX_COST_USD`) in scripts or CI | a cap that stopped the run before any item **exited 0**, leaving an empty run that looked complete. Exit codes are now 0 complete, 2 stopped early, 1 nothing measured | `2b6a129a` |
| ran `silver_calibrate` on exactly 3 arms | it crashed; the minimum is now stated as 4, with the reason | `ebd54b60` |
| read `dirty: true` on your runs | every run after the first on a machine was marked dirty, because earlier run directories are untracked files. Untracked paths under `data/runs*/` no longer count | `9ec2513a` |
| relied on parser hashes | the scoring-code hash covered the function but not the module-level regexes it reads, so a parser change could leave the hash identical. Copy `examples/_shared/codehash.py` and hash with `code_digest(fn, consts=…)` | `3f16a79b`, `c6e8365f` |

### 2. Changes that break an old adapter or an old run

- **Remove any retry loop from your adapters.** The original `adapter.py` template had its
  own `_with_retries`. The core now retries every `call_system`, so an adapter that kept
  its loop retries a failing item 8 × 8 = 64 times, each billed. To make extra error
  messages count as transient, declare `TRANSIENT_MARKERS = (...)` in the adapter; the core
  honours it.
- **The adapter contract grew** (all optional, all recommended):
  - `warmup(params)`: load models and prove the endpoint answers before the first item,
    so warm-up is excluded from latency and a bad key fails before any spend;
  - `fingerprint(params)`: what the arm really ran (the model behind an alias, the
    weights' revision, prompt hash, scoring-code hash);
  - `PRIMARY_METRIC`: the metric the leaderboard ranks by;
  - `METRIC_KINDS`: `quality` vs `descriptive`, so diagnostics such as parse rate and
    truncation are not ranked as if they were quality;
  - `METRIC_DIRECTIONS` (0.4.0): `{"wer": "lower"}` for a quality metric that improves going
    down, which a name cannot tell the harness.
- **The run directory gained files written during the pass:** `run.json` (written before
  the first item) and `outputs/_rows.jsonl` (appended and fsynced per item). Old runs
  without them still read, but cannot be resumed safely.
- **Read cost from the provider's bill, not a price table.** The example adapters take
  OpenRouter's `usage.cost` when it is returned (`examples/_shared/gateway.py` asks for it)
  and fall back to the config's per-token prices. The price table was off by 0.67×–3.21× per
  arm when checked. This lives in the adapters, not the core, so an old adapter keeps
  estimating from prices until you copy the pattern.

### 3. New tools worth adopting

| command | what it gives you |
|---|---|
| `make family-test DATASET_ID=… A=… AGAINST=…` | one arm against a declared family, genuine Holm, with a result cache |
| `make leaderboard` | Friedman permutation test and Nemenyi critical difference before it prints an order |
| `make rank-stability` | how many items a ranking needs, measured by splitting into disjoint halves |
| `make holdout` | tune on a dev slice, confirm on the held-out rest |
| `make bootstrap-test` | intervals for corpus-level metrics (with the caveat that it is anti-conservative) |
| `make cost-report` | billed cost and projections per arm |
| `make validate` / `make check` | schema and tree validation that exits non-zero, for CI |
| `pair_test` / `family_test --items FILE` | test on a declared item subset (a stratum), the same ids everywhere |
| `make judge-score` / `evh judge-score` (0.3.0) | optional: re-measure stored outputs with LLM judges, refused until validated against human ratings; any text task, declared in the scorer (RUNBOOK §12) |

### 4. What not to copy

These exist for this repository's public showcase and assume its six experiments, its
reports and its site: `check_report_claims.py`, `check_model_facts.py`,
`check_terminology.py`, `check_links.py`, `summeval_analysis.py`, the per-task
`*_report.py` scripts, and the `site`/`docs` Makefile targets. Copy a report script only if
you run the same task; it is an example, not part of the core.

### 5. How to upgrade, and stay upgraded

Copying the directory once is what caused this page. Since version 0.2.0 the harness is
an installable package, so a project can **pin** it the way it pins any other dependency:

```bash
pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@<commit>#subdirectory=harness"
evh --help          # the Makefile's targets, as commands
```

1. **Pin a commit, not a branch.** An upgrade is then a one-line change to the pin, and
   every run records the harness `version` and a `code_sha256` of its code in
   `fingerprint.instrument.harness`. A run's `commit` is the commit of YOUR project, so
   those two fields are what say which harness produced a number.
2. **Keep the data in your project.** The package holds code and schemas only. Run the
   commands from your project root, or set `EVAL_HOME` to it; `EVAL_DATA_DIR` moves the
   data root if your layout is not `<project>/data` (for example
   `EVAL_DATA_DIR=data/eval/stats`).
3. **Bring existing results in without re-running them.** If your project already has
   outputs scored by its own code, `evh import-run` writes those per-item scores
   as a run the significance tests read (`pair-test`, `family-test`, `leaderboard`,
   `rank-stability`). Lower-is-better metrics take `--asc`.
4. **Delete the copy.** Remove the copied `harness/scripts` and call `evh`
   instead. Your adapters, configs and report scripts stay where they are, outside the
   package, so an upgrade never conflicts with your work.
5. **After every upgrade,** run `evh self-test` and `evh validate`, then
   re-score your committed runs (`evh rescore`) and compare. A number that moves
   is either a fixed bug from §1 or a change you need to understand before trusting new
   runs.
