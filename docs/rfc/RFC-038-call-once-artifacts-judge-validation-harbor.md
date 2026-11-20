# RFC-038: Call once, artifact links, judge validation and a Harbor example

- **Status**: Accepted (0.8.0, 2026-11-20): the owner took all nine recommendations of section 10. Owner, 2026-11-20: four items pulled into 0.8.0 as last-minute scope: a no-retry switch for adapters with side effects; an artifact link per item; an installed command that validates a judge (it was "for 0.8.1" in `research/internal/IDEAS_0.8.1.md:13`, which asked for this RFC first); a Harbor example under `examples/harbor/`. House rules that bind this RFC: every inspector or Workbench view and action has an `evh` command and the screen prints it; the core stays generic (Harbor lives under `examples/`, the core gets only generic hooks); no backward-compatibility shims (committed data migrates); docs reflect what exists.
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-030](RFC-030-replay-and-faithfulness.md) (replay: the only caller that calls once today), [RFC-033](RFC-033-per-item-results-as-a-model.md) (per-item results, `Result.meta` stays free-form), [RFC-005](RFC-005-judge-scorers.md) (judge scorers, the validation gate), [RFC-019](RFC-019-datasets-from-production.md) (captures and importers; hidden datasets), [RFC-023](RFC-023-labels-and-references.md) (recorded arms), [RFC-032](RFC-032-one-model-two-surfaces.md) (one model, two surfaces), [RFC-034](RFC-034-charts-and-judge-reasons.md) (`explain`), [RFC-035](RFC-035-scenarios.md) (what runs outside the harness)

Paths are relative to `harness/scripts` unless they start with `harness/`, `docs/`, `examples/` or `research/`; `harness/evaluation_harness` is a symlink to `harness/scripts`. Read 2026-11-20 in the 0.8.0 worktree (it has uncommitted edits in `docs/tutorials` and `UXS-005`). A claim I could not verify says so, and the list is collected under "Not verified".

## Abstract

Four things, one release, each small, each a generic hook or a command, none of them Harbor-specific in the core.

1. **Call once.** An adapter declares `CALL_ONCE = True` (or `call_once(params)`), and `evh run` calls each item once: no retry, a failure recorded, and `--resume` never calls an item again that may already have had its effect unless a person says so.
2. **An artifact link per item.** An adapter puts `artifact` (a path inside the project) in `Result.meta`. The inspector, `evh comparison-item` and the Workbench show it, served read-only by the machinery that already serves `served_dirs`, hardened.
3. **`evh judge-validate`.** The command takes a human-rated dataset and a scorer, runs every judge of the scorer as an arm over the rated items with the exact message `judge-score` sends, runs a floor arm, and prints (or with `--fill` writes) the scorer's `validation` block. It is the installed route that `harness/tools/validate_judge_goyal.py` and `validate_judge_zhang.py` were for one download each; those two stay in the repository as the research report's evidence (owner, 2026-11-20, section 3.6). What is specific to their two downloads moves to two example sources.
4. **`examples/harbor/`.** A dataset source for Harbor tasks, an importer for existing Harbor job directories (capture, dataset, recorded arm), and an adapter that runs one `harbor run` trial per item with call once, the trial directory as the artifact, `reward` as an extra metric and a cost with its `cost_source`. CI tests it with recorded job directories and a fake `harbor`; locally it runs with Harbor's `oracle` agent, which needs no model.

## Decisions (owner, 2026-11-20)

1. The four items are in 0.8.0.
2. The house rules in Status apply to all four.

**Decisions taken in the draft, confirmed on 2026-11-20 with the nine of section 10**: the flag name `--recall-failed`; a Harbor trial that ran and failed is a score of 0, not a failed item; `artifacts/` is served by default; the two judge-validation tools are kept as research, outside the package, and their committed records are also read as runs (owner, 2026-11-20, section 3.6).

## What exists today (read 2026-11-20)

**Retries.**
- `call_with_retries` retries a failure that `is_transient` calls transient, up to `EVAL_MAX_RETRIES` attempts, default 8 (`_retry.py:37`, `106-146`). `FATAL` substrings are checked first (`_retry.py:69-96`).
- `one_pass` has a `once` parameter (`run.py:434`). With it set, the item is called through `_timed(call_system)` and nothing else (`run.py:539-548`); a transient failure is then recorded as a failed item and does not stop the run with exit 75 (`run.py:557-562`).
- `evh run` passes `once=plan is not None` (`run.py:1469`), so only a system with a `replay:` block calls once. `evh faithfulness` passes `once=True` (`faithfulness.py:146`, from the research report).
- A replay run also refuses `--resume`, `--items` and `--repeat` above 1 (`_replay.py:245-257`, RUNBOOK `harness/docs/RUNBOOK.md:1912-1914`).
- The warm-up is retried for every system, replay included (`run.py:1309`).
- `evh arm-smoke` calls the system directly, with no retry (`arm_smoke.py:305`), and calls item 1 a second time to test determinism (`arm_smoke.py:334-340`).
- `evh sweep` starts one `evh run` per arm as a subprocess (`sweep.py:35-90`, from the research report).
- Adapters declare facts as module names that the core reads lazily: `TRANSIENT_MARKERS` (`_adapter.py:157-166`), `CALLS_PER_ITEM` / `calls_per_item(params)` (`_adapter.py:169-175`; `harness/docs/INTEGRATION.md:187-192`), `primary_metric(params)` with a `PRIMARY_METRIC` fallback (`_adapter.py:218-235`). The adapter file is hashed into the fingerprint, so adding a line is an edit like any other (`harness/docs/INTEGRATION.md:192`).
- A system file has no room for a new top-level key: `additionalProperties: false`, and its `params` are "interpreted by the adapter" (`harness/schemas/system.schema.json:4,10`). Any new key inside `params` enters the fingerprint's `settings` (`_fingerprint.py:378-385`, from the research report).
- The user who needs this today words an error with a fatal marker: `/work/harness-bakeoff/adapter.py:137-141` raises `RuntimeError("trial not found: ... no retry")` on a Harbor timeout, because the core would retry "timed out". Harbor's own `--max-retries` defaults to 0 (`harbor run --help`).

**Failed items and resume.**
- A failed item gets `Result(output="")`, its row has `failed: 1`, its output is not written, and so `--resume` calls it again (`run.py:556-588`; RUNBOOK `harness/docs/RUNBOOK.md:852-858`). Its `Result.meta` is lost, because the empty `Result` replaces it (`run.py:572-574`).
- Resume skips an item whose id is in the earlier run's outputs (`run.py:511`) and reads the earlier rows, failed ones included, from the row checkpoint (`run.py:1076-1108`).
- More than 5 failures that are also over 20% of the items called stop the run (`run.py:567-571`).

**Meta and the inspector.**
- `Result.meta` is free-form (`harness/scripts/adapter.py:49-56`; `harness/docs/INTEGRATION.md:71-82`). `run.py:649-650` stores it as the row's `_meta`. Format 7 changes only `usage` and three run settings (`model/results.py:60-97`; RFC-033 "Not changed", "Not done": "a schema for adapter `_meta`"). Any other key passes through, in both stores (`_outputs.py:416-475`, from the research report).
- `item_view` builds `info` as a flat dict of strings (`catalog_adapter.py:987-1018`). `inspect.js:634-645` joins and escapes it as one line of text. `evh comparison-item` prints it as `(k v · k v)` (`catalog_views.py:946-974`). `evh comparison-items` already prints each arm's `_meta` (`catalog_views.py:1286-1306`).
- `served_dirs` is an optional tuple on the catalog adapter: directories under the project served read-only (`catalog_adapter.py:252-253`; `harness/docs/INTEGRATION.md:382`; `catalog_serve.py:462-478`, `1640`). A directory outside the project root is refused (`catalog_serve.py:462-478`). `allowed()` refuses a `..` segment and a dot-segment after the prefix (`catalog_serve.py:579-607`). The `nosniff` and `sandbox` headers go only to the data prefix, not to `served_dirs` (`catalog_serve.py:1515-1523`). Whether a symlink under a served prefix is followed is not verified (see below). A public deployment serves no directory (`catalog_serve.py:1626`).
- A hidden dataset's rows keep only `CALL_META` of `_meta` (`_release.py:277-283`, `model/results.py:23-34`); other datasets' rows are copied whole.
- The Workbench does not read `/api/item`; it reads `/api/v1` operations, and `comparison-item` is one (`ops/inspect.py:34-35`, `98-103`). Which Workbench screens render it is not verified.
- The Workbench prints the command of every screen (`harness/workbench/workbench.js:22`, `WB.cmd`; UXS-005 line 12).

**Judge validation.**
- The gate is `validation_problems` (`judge_score.py:420-498`). It reads each named run in `data/runs`: the dataset id, the metric equal to `value` within 1e-6, at least `min_metric`, `explain`, `mode`, `OUTPUT_PARAMS` (provider, model, temperature, reasoning, max_tokens), the prompt file's name, and `fingerprint.settings.declared.prompt_sha256` equal to the scorer's `prompt.sha256_at_16` (`judge_score.py:415-417`, `478-497`). A `provider: fake` judge is refused whatever the block says (`judge_score.py:425-427`). A validation's `mode` must equal the scorer's (`judge_score.py:334-358`).
- RUNBOOK says a validation "is an ordinary eval whose arms are the judges" (`harness/docs/RUNBOOK.md:1299-1328`). The only worked adapter is `examples/summeval-judging/adapter.py`, which builds its own judge message (`:237-242`, `:155-166`) and keeps its pick and pairwise reminders equal to the core's by tests (`:101-111`).
- **The two tools write no runs and fill no block.** They call the judge directly with `js.real_call` (`validate_judge_goyal.py:463`, `validate_judge_zhang.py:512`) and write `data/judge-validation/<scorer>/<source>/report.json` plus per-call records (`validate_judge_goyal.py:558`). The gate never reads them; the Workbench shows them as "People's checks" (`model/scorers.py:189-228`, `checks_of`). `IDEAS_0.8.1.md:9` says the scripts "write such runs"; that is wrong, and this RFC corrects it. No code writes the `validation` block: it is hand-written YAML (`harness/schemas/scorer.schema.json`, `validation` object; the Workbench's scorer forms offer no such field, `harness/workbench/live.js:1629-1650`).
- Editing a scorer changes its content hash, which every judged score records; a scorer that has made judged scores is not edited, a new version is a new id with `supersedes` (`harness/schemas/scorer.schema.json:4`; `ops/scorers.py:28,105`).
- The Workbench's "A judge for this goal" shows the stored validation and says "this screen does not measure a judge" (UXS-005 lines 494-512; `live.js:1652-1664`). `research/internal/WORKBENCH_GAPS_0.8.0.md:21`, D6, cut it from v1.

**Importers, sources, examples.**
- An importer is a class with `records(query)`; a record is `{id, body, fields, created_at, source, labels, outcome}` with `id` matching `[A-Za-z0-9][A-Za-z0-9._:@+=-]{0,199}` (`_importers.py:1-14`, `30-34`); a project's importer is named `path/to/file.py:Class` (`_importers.py:44-76`).
- A source is a class `Source(options)` with `describe(query)` and `items(query)`, named the same way (`_sources.py:1-19`, `39-72`).
- `evh capture`, `dataset-from-capture`, `dataset-materialize`, `arm-from-capture` (`capture.py:1-28`, `arm_from_capture.py:1-13`): a recorded arm reads each item's output with the adapter's `recorded_output(record)`, else a record field named by `--field`; it is run like any system, at cost 0 (`arm_from_capture.py:8-12`).
- Examples are tested by standalone scripts listed in `harness/tests/self_test.py` (`:1282`, `:1286`, from the research report), each using `evaluation_harness._check`.
- `cost_source` in `meta` is read by `run.py:390-396`; `harness/docs/INTEGRATION.md:84-88` documents it.

**Harbor 0.26.0** (read from `harbor --help`, `harbor run --help` and its installed source under `~/.local/share/uv/tools/harbor/lib/python3.12/site-packages/harbor`; no trial was run):
- `harbor run` is `harbor job start`. It takes `-p` (a local task or dataset directory), `-d name@version`, `-i` (task name glob), `-a`, `-m`, `-o/--jobs-dir`, `--job-name`, `-n`, `-k`, `-r/--max-retries` (default 0), `--delete/--no-delete`, `-q`, `-y`, `-c` (a job config).
- A timeout in seconds exists only in a job config (`override_timeout_sec`, `max_timeout_sec`); the flags are multipliers.
- A job directory is plain JSON and text: `config.json`, `result.json`, and per trial `<task>__<id>/{config.json, result.json, trial.log, agent/, verifier/{reward.txt, ctrf.json, test-stdout.txt}, artifacts/}`.
- The trial `result.json` carries `task_name`, `trial_name`, `agent_info`, `agent_result` (`n_input_tokens`, `n_cache_tokens`, `n_output_tokens`, `cost_usd`), `verifier_result.rewards`, `exception_info` (`exception_type`, `exception_message`, `exception_traceback`, `occurred_at`; `models/trial/result.py:28`) and `started_at`/`finished_at`.
- `oracle` is an agent that uploads the task's `solution/` and runs `solve.sh` inside the task's environment with no model call and no API key (`agents/oracle.py:60-77`, `~105`); `nop` does nothing, so the verifier should give reward 0 (`agents/nop.py`). Both need an environment (Docker, the default) and the first run pulls the task's image over the network. Whether `harbor run -a oracle` wants any credential was not run.
- `harbor job resume` re-runs trials without a `result.json` (`job.py:~323-325`).
- The one finished job on disk is 1.5 MB, 1.4 MB of it `agent/`; without `agent/` it is about 32 KB. Its trial `result.json` holds `trial_uri` (an absolute `file:///` path), and five files hold `base_url` and `model_api_key_name`. No failed trial is on disk, so the filled `exception_info` shape comes from the source, not from data.
- A real user's adapter exists, `/work/harness-bakeoff/adapter.py`, one `harbor run -n 1` per item with a subprocess timeout (`:114-164`). It is the shape the example generalises; its gateway spend delta (`:85-111`) is not.

## 1. Call once

### 1.1 How an adapter says it

An adapter file declares

```python
CALL_ONCE = True                       # every item, every system
def call_once(params): ...             # or: per system, from its params (wins over the constant)
```

read by a new `_adapter.call_once(adapter_path, params) -> bool`, written the way `calls_per_item` is (`_adapter.py:169-175`) and documented beside `CALLS_PER_ITEM` (`harness/docs/INTEGRATION.md:187-192`). `evh run` sets `once = plan is not None or call_once(adapter_path, params)` (`run.py:1469`).

**Not a system field.** The system schema reads nothing but `params` for the adapter (`system.schema.json:4,10`), a field there would need a schema change and a fingerprint change, and the person who writes a system should not be able to turn off a guard the adapter's author put there because the system has side effects. **Not an environment variable**: it is a property of the code, not of the machine. A system whose adapter does not declare it cannot be made call-once; the adapter changes (one line, hashed into the fingerprint with the adapter, `harness/docs/INTEGRATION.md:192`).

### 1.2 What it does

| where | what changes |
|---|---|
| `evh run` | each item is called once; no `call_with_retries`; a failure, a transient one included, is a failed item and not exit 75 (the branch exists, `run.py:557`); the run prints "calls each item once" with its first line and the dry run says so |
| the adapter | must not retry inside `call_system`: the core no longer does and a retry loop of its own repeats a side effect (the rule `adapter.py:97-102` already gives for the 8 x 8 case); for Harbor that is `-r 0`, passed explicitly |
| warm-up | still retried (`run.py:1309`): it checks a key or loads a model and makes no item's effect; an adapter whose warm-up has side effects is not described by this RFC |
| `evh arm-smoke` | calls each of its items once, which it already does, and skips the determinism second call (`arm_smoke.py:334-340`), saying "call once: item 1 not called twice, determinism not checked"; the smoke is real calls and its summary says N real calls |
| `evh sweep`, jobs | inherit: both start `evh run` (`sweep.py:35-90`); how `jobs-resume` passes `--resume` is not verified |
| `--repeat N` | allowed: items are independent, unlike a replay's; each repeat is N more real calls and the dry run counts them |
| the run record | `run.json` identity gains `call_once: true` when set (`run.py:1442-1450`), shown on the arm page ("called once each"). Whether `run.json`'s schema accepts it is not verified; the schema changes with it |
| judges, fetches | unchanged (`judge_score.py:914`, `_fetch.py:77`) |

A failed item keeps what the adapter knew. An exception may carry `meta` (and `cost_usd`) as attributes; `run.py:572-574` then builds `Result(output="", meta=getattr(exc, "meta", {}), cost_usd=getattr(exc, "cost_usd", None))` instead of an empty `Result` (built as `_failed_result`, for every failed item, call-once or not; under call once the core adds `meta["call_error"]`, the error text a resume lists). Without this the trial directory of the trial that timed out is the one artifact (section 2) a person wants and the row has lost it.

### 1.3 Resume

`--resume` on a call-once arm keeps what it does today for an item with a stored output, and changes what it does for the other two kinds:

| the earlier run has for the item | resume |
|---|---|
| an output | not called; its output and row are read and scored again (`run.py:511`, `525`) |
| no row at all, no start mark | called: it was never attempted |
| a row with `failed: 1` | not called. It was called once and the call raised: its effect may have happened |
| a start mark and no row | not called. The process died during the call ("in doubt") |

Both of the last two are listed by item id with their error, and the run says "N items were called once already and not again: `--recall-failed` calls them again, and repeats their side effects". `evh run --resume RUN --recall-failed` calls exactly those items again, once each; the run record lists them (`recalled: [item ids]`). The flag is refused on a run that is not call-once.

The start mark is one synced line per item, written before the call and read by resume (`_outputs.py` already appends a row line per item, `run.py:669-670`). It must not be a row: `run.py:1092-1102` refuses a row without `_extra` and keeps the first row it sees for an item. **As built:** the line is `{"_started": "<item id>"}`, appended to the run's checkpoint (`rows.partial.jsonl`; the `rows_partial` table in SQLite) by `_outputs.mark_started`, and read by `_outputs.started`. The checkpoint is already verbatim text in both stores, so no table, column or format changed; the line has no `item_id`, so nothing that reads rows (`_resume_source`, `_spend`, a release's copy) takes it for one. `finish` drops it with the checkpoint, which is why a call-once item stopped by the provider's own cost cap (`CostCapExceeded` inside its call, which `one_pass` treated as "stopped before the call" for every other adapter) is recorded as a failed item and the run stops after it: the cap run finishes, and the mark would be gone.

What a resumed run does with an item it does not call: it is a failed item of the new run (`failed: 1`, its error in `failed_items` and in the row's `_meta.call_error`, carried from the earlier row, or "in doubt: its call started and the run stopped before it ended"), its earlier cost, tokens and `_meta` kept as a replayed item keeps them, and its row is appended to the new checkpoint, so a resume that is itself stopped keeps the rule. A carried item does not count toward the rule that more than 5 failures over 20% of the items called stop the run (`run.py:567-571`): only calls made in this pass do.

A replay still refuses `--resume`, `--items` and `--repeat` above 1 (`_replay.py:245-257`): its state spans items, which a call-once adapter's does not. A call-once adapter whose items do depend on each other must refuse those flags itself, as the replay does; the core does not know.

### 1.4 Refusals

- `--recall-failed` on a run that is not call-once, or without `--resume`: `ERROR (bad-argument)`.
- `--resume` of a call-once run with failed or in-doubt items and no `--recall-failed`: the items are not called and the run says so; it does not fail (the remaining items are still run).
- A system whose adapter declares call once and sets `EVAL_MAX_RETRIES`: ignored for that adapter; `evh env-check` says so on the line that prints the retry count (`env_check.py:161-163`: "not used by an arm whose adapter declares CALL_ONCE"; it knows no system, so it cannot name one). `jobs-resume` (a job resumed as a new job) drops `recall_failed` from the inputs it copies, so a recall is never repeated by resuming the job that made it (`_api.py`).

## 2. An artifact link per item

### 2.1 The field

One reserved key of `Result.meta`: `artifact`, a string, a path to a directory or a file inside the project. Not a new `Result` field: adapters that define their own `Result` dataclass (the SummEval adapter does, `examples/summeval-judging/adapter.py:69-77`) would not carry it, and the core reads `res.meta` already (`run.py:649-650`). It is stored with the rest of `_meta`, in both stores, with no migration (format 7 only touches `usage` and three run settings, `model/results.py:60-97`). RFC-033 said `Result.meta` stays free-form and a schema for it was not done (RFC-033 "Not changed", "Not done"); this adds one reserved key, not a schema.

### 2.2 Path rules

At write, in `run.py` after the call returns, the core normalises `meta["artifact"]`:

- absolute or relative; made absolute against the project root, `.resolve()`d (symlinks followed), and kept only when the result `is_relative_to` the project root (the check `ops/views.py:550-561` already makes for a file the project reads). Stored as a POSIX path relative to the project root, with no `..` and no leading `/`.
- a value that fails is dropped from the row, the item is not failed (its answer is good), and `meta["artifact_refused"]` holds the reason; the run prints it once ("artifact dropped: outside the project"). It is not stored as given: a stored path is something a server reads later.

At read, the server checks again and trusts nothing stored (a run copied from elsewhere, a hand-edited row). The link is built only when the path lies under a served prefix: the data directory or one of `served_dirs` (`catalog_serve.py:462-478`, `579-607`). **`artifacts/` under the project root is a served prefix by default** (built as always served, whether or not the directory exists yet: a server started before the first trial would otherwise 404 every link until restarted), so an adapter that writes there needs no catalog configuration (the house rule "everything works by default"). Another place, such as `/work/harness-bakeoff/benchmarks/jobs`, is declared by the catalog adapter's `served_dirs` (`harness/docs/INTEGRATION.md:382`). A path under no served prefix is shown as text with "not served by this inspector".

An artifact does not belong under `data/` in a SQLite project: that store holds `data/` in one database (project-store decisions), and a trial directory of 1.5 MB per item does not belong in it. `artifacts/` is outside `data/`.

### 2.3 Serving, read-only, hardened

No new route: the link is a URL under a served prefix, answered by the static handler that already serves `served_dirs` (`catalog_serve.py:1464`). A directory gives the standard listing. Two hardenings, generic, for every served prefix and not for artifacts alone:

1. `nosniff` and `Content-Security-Policy: sandbox` go to every served prefix, not only the data prefix (`catalog_serve.py:1515-1523`): an agent's trial directory holds HTML, and an HTML file served from this origin could call the write API. **Every prefix but the first, the catalog's own pages** (`Handler.prefixes[0]`): `sandbox` without `allow-scripts` blocks scripts and gives the page an opaque origin, which would break the catalog and the inspector themselves. The cost is on `served_dirs`: a project's HTML report with scripts of its own is now shown without them (INTEGRATION and the CHANGELOG say so).
2. A request whose path resolves, through a symlink, outside the served prefix's real directory is a 404 (`allowed`, `catalog_serve.py:579-607`, did not resolve: the stdlib file server followed the link and served the target, shown by removing the check). A trial directory written by an agent may contain a link to `/etc`. A link that stays inside the prefix is still served.

A public deployment serves no directory (`catalog_serve.py:1626`) and `/api/item` is refused unless it publishes outputs (`catalog_serve.py:147-158`): an artifact is never public. `catalog-serve --behind-proxy` serves it with the rest.

### 2.4 What each surface shows

| surface | shows |
|---|---|
| `item_view` (`catalog_adapter.py:987-1018`) | a new top-level key `artifact: {"path", "url", "kind"}` (`kind`: `dir`, `file`, `missing`, or `refused` for a stored value that is not a path inside the project: no url, whatever was stored; `url` absent when the path is under no served prefix), and `info["artifact"]` = the path as text, which is what the CLI line prints. **A failed item has no output, and its trial directory is the one a person wants**: its view is `{"kind": "none", "note": "This item's call failed, so no output was stored."}` with the same `artifact`. `harness/docs/INTEGRATION.md:396` (the view kinds) gains the key |
| the inspector (`inspect.js:634-645`) | the link beside the output, drawn only from a `url` that starts with a single `/`, text escaped, `rel="noopener"`; the `artifact` entry is left out of the `info` line when the link is drawn. `missing` says "artifact not found on this machine" |
| the CLI | `evh comparison-item --runs … --item …` prints `(run R · artifact artifacts/h1/trial_ab12)` under the arm (`catalog_views.py:969-973`), and `--json` carries `artifact` per arm. `evh comparison-items` already prints `_meta` (`catalog_views.py:1286-1306`). No new command: the printed path is the parity, read with an ordinary file browser. A command to list a directory would only reimplement `ls` |
| the Workbench | **No Workbench screen reads `comparison-item`** (listed at step 2: `live.js` and `workbench.js` name it nowhere; the item lists it has are the label sheet and the production screen's `sheet-show` rows, which show no run's artifact). Decided from UXS-005 W2, which describes the screen as sheet-export and sheet-import with the arms hidden and shuffled: a link to an arm's artifact would unblind it, so PRD-017 W2's list of `comparison-item(s)` and `sheet-show` as its operations was corrected to what the screen calls, and the finished run's item with its link stays in the inspector and `evh comparison-item`. The op's result gains `artifacts: [{arm, path, url, kind}]` (built), for a screen that will; the one Workbench screen that shows one item's output of a system is "Check it on three items" (`arm-smoke`), and it draws the link under each reply and prints the command (UXS-005 line 12). `arm-smoke`'s items carry `artifact` for it (and the CLI prints `artifact PATH` on the item's line) |
| a release | a hidden dataset's rows drop `artifact` (it is not in `CALL_META`, `_release.py:277-283`; it must stay out: a trial directory quotes the items). A non-hidden release copies the row; `artifacts/` is not under `data/`, so it is not copied and the link reads as `missing`, "not found on this machine" (built after the first review: `copy_data` writes `release.json` into its copy, and an item view of data that has it says "not in this deployment" for a missing artifact). `plan_problems` (`_release.py:135-164`) refuses a hidden dataset's run whose artifact lies under `data/runs/` (it would be copied: `_release.py:320-329`) |

## 3. `evh judge-validate`

### 3.1 What it is

```
evh judge-validate --scorer ID --dataset RATED [--judges a,b] [--floor random | --floor-run RUN]
                   [--dry-run] [--resume] [--fill [--replace] --reason "…" --by NAME] [--what …] [--differs …]
```

The cap is the scorer's `cost_cap_usd`, or the environment's (`EVAL_MAX_COST_USD`; a job's `max_cost_usd` arrives as it): there is no `--max-cost-usd` flag, as `evh run` has none.

It runs the route RUNBOOK §12 describes, with every step done by the harness:

1. **Read** the scorer (`js.load_scorer`, `judge_score.py:264`) and the rated dataset; refuse before any call what the next section lists.
2. **One system per judge**, `data/systems/<scorer>__<judge>__validation.yaml`, its `params` the judge's (`OUTPUT_PARAMS`, prices, the family) plus `prompt_file`, `mode`, `explain` (the fields the gate compares, `judge_score.py:467-488`), its adapter the core's `scripts/judge_validation.py`. A system's `adapter:` could not name a core module (`_find_adapter` and `resolve_adapter_path` looked under the system and the project, and knew only the bundled `scripts/adapter.py`): `_common.CORE_ADAPTER_IDS` now names both, as the id a run records, resolved in the package for a project that pins it (the installed-commands test runs it there). A system that exists with other params is not overwritten (the rule `arm_from_capture.py:34-39` has).
3. **A floor arm** per mode: a seeded random scorer at cost 0 (`provider: random`), as the SummEval example's `random` arm is (`examples/summeval-judging/adapter.py:425-443`).
4. **Run each as an ordinary run**, on the rated dataset, through `run`'s own body (`run.body`, in this process, one after another, as `arm-from-capture` runs its arm): the cap, the fingerprint, the progress lines are the run's, and the runs share the command's one cap (`_spend` counts across them). `--dry-run` is the command's own, since `run`'s estimate counts one call per item: it builds every message and prints the calls, tokens and cost per judge and the cap, and writes nothing. `--resume` is a flag: a finished run of a system on the dataset is used as it is, one that stopped is continued. With no cap in the scorer or the environment the command refuses, as the tools did (`validate_judge_goyal.py:423`), unless every judge costs nothing (a fake judge, the floor).
5. **Print** per judge: the metric, n, the floor, the run id, and the block that would be written. The value in the block is the run's `metrics.json` figure, which is what the gate compares to 1e-6 (`judge_score.py:457-461`).
6. **`--fill`** writes the `validation:` block (`dataset_id`, `mode`, `metric`, `what`, `differs_from_this_use` from `--what` / `--differs`, `runs[]` with `{judge, run, value, min_metric}`) and `prompt.sha256_at_16`, through the scorer's model operation (the one `scorer-set` uses), as a decision with `--by` and `--reason`: the block gains `why` (the scorer schema had no place for a decision's reason), the scorer's history records `--by`. The command then calls the gate's own `validation_problems` and prints its answer: the check that proves the write is the gate, not a copy of it. The exit code is 0 when the gate answers nothing and 3 (`EXIT_UNVALIDATED`) when it still names a problem (a judge below the floor): the block is written either way, since it is the measurement.

### 3.2 The adapter

`harness/scripts/judge_validation.py`, a core module, because the point is that the judge sees the message `judge-score` sends. It builds the message with `judging.build_message`, `build_pick_message` and `build_pairwise_message` (imported by `judge_score.py:88-111`), so the example adapter's copy of the message and the tests that hold it equal (`examples/summeval-judging/adapter.py:101-110`) are not needed for a project's own judge. It declares `primary_metric(params)`, `METRIC_KINDS`, and `prompts(params)` (the prompt file's text, which is what the fingerprint's `declared.prompt_sha256` and the gate's `sha256_at_16` hash, `_adapter.py:250-255`, `judge_score.py:489-497`). It declares no `CALL_ONCE`: a judge call is a retryable read.

**The rated dataset** is a dataset whose items are one JSON document each, `{"source": str, "outputs": [str, …]}`, and whose reference per item is one JSON document, `{"ratings": {dimension: [one number per output]}}` (the mean of the raters, any scale: only order is used), optionally `"raters": [{dimension: […]}, …]`. Everything else derives from the ratings: a pick's best is the argmax set (credit 1/k for k tied, the rule `RUNBOOK:1265` and the Goyal tool use); a pairwise item's pairs are sampled seeded, as the SummEval adapter does (`PAIRS_PER_ITEM = 8`, capped at the pairs an item has, `PAIR_SEED = 20261015`, `adapter.py:99-100`, so the committed `pair_agreement` values reproduce), and kept where the raters rank the two apart. The dimension names in `ratings` must be the scorer's `task.dimensions`; mapping a human dimension to a judge's (Zhang's faithfulness to the judge's consistency, `validate_judge_zhang.py:85`) is the source's work, not a flag. **That was not enough for Zhang's file (found building the sources, 2026-11-20): its raters did not rate fluency.** The owner decided (2026-11-20): validate on the dimensions the ratings carry. The ratings may carry some of the scorer's dimensions (the same in every item; one the scorer does not judge, or none of them, is refused); the block records them (`validation.dimensions`, in the scorer schema; absent means every dimension of the task); the gate names each dimension of the task the block does not carry (`dimension fluency: not validated on <dataset> (its ratings carry …)`), and `scorer-show` and the Workbench's part c say the same for each validation run; nothing is averaged in. Goyal's file has one overall preference, which its source copies to every dimension.

| mode | metric the adapter scores | per item |
|---|---|---|
| `grade` | `tau`: Kendall tau-b (`judging.kendall_tau_b`, `judging.py:338`) of the judge's scores with the ratings, averaged over the dimensions; `rho` beside it | one call per block of at most `outputs_per_call` (`js.block_sizes`, `judge_score.py:510`) |
| `pick` | `top1` with `top1_chance` | one call |
| `pairwise` | `pair_agreement` with `n_pairs` | one call per sampled pair |

With `raters`, `human_tau` (or `human_top1`) is scored beside the judge: one rater against the mean of the others, rotating, which is the human baseline both tools computed (`validate_judge_goyal.py:194-242`, `validate_judge_zhang.py:175-200`).

**What a run stores as `output`** is the parsed verdict (`{"scores": …}`, `{"best": […]}`, `{"pairs": […]}`), and for a reply that does not parse only its sha256, its finish reason and its length. The SummEval adapter stores the first 300 characters of an unparsed reply (`:207-211`); a reply can quote the rated item, and the two tools withheld such replies from commits (`validate_judge_goyal.py:475`; `harness/docs/RUNBOOK.md:1223-1226`). A validation run's `outputs.jsonl` is committed with the run.

**`summeval_100` is not a rated dataset** (found building rec 5's check, 2026-11-20): its items are the example's own `{article, summaries, references}` and its gold `{dimension: [16 numbers]}`, which the core adapter does not read. `examples/summeval-judging/rated_source.py` builds a rated copy of the same 100 articles and expert scores (items `{source, outputs}`, reference `{"ratings": ...}`), read through the Hub's conversion as `fetch.py` reads it; open question 5's paid run is on that copy.

### 3.3 How much of the two scripts generalises

Everything that runs or judges generalises, because it becomes the run's own machinery. What is specific stays with its download.

| in the scripts | where it goes |
|---|---|
| download, pinned sha256, zip handling (`validate_judge_goyal.py:60-104`; `validate_judge_zhang.py:78-120`) | a `Source` each, under `examples/judge-validation-goyal/` and `examples/judge-validation-zhang/`, writing the rated shape; `fetch` is `_fetch.fetch` as now |
| reading best/worst votes into ranks `{best 2, unranked 1, worst 0}` (`:146-148`); Likert columns, the `cnndm` filter, the `reference` system, the NaN summaries (`validate_judge_zhang.py:92-116`) | the same two sources, as `ratings` and `raters` |
| the seeded order of the outputs (`goyal-0:`, `zhang-0:`) | the adapter's seeded order, one seed for all |
| judge calls, retries, cost cap, `--dry-run`, resume, `--no-calls`, stored-record integrity (`judge_fp`, `prompt_sha`, order), withheld text | the run's: `evh run` caps, resumes, records the fingerprint, and the gate compares the fingerprint |
| best-pick credit, majority best, leave-one-annotator-out | `top1` (1/k credit) and `human_top1` |
| per-article tau against two-rater means, held out in turn | `tau` and `human_tau` |
| Wilson intervals, `rate()` (`validate_judge_goyal.py:177-191`) | not carried: the leaderboard and `pair-test` give a run's interval and a paired test (`stats.py`: `exact_ci`, `sign_flip_p`) |
| "GPT-3 versus BRIO" per article, the three-system chance 1/3 (`validate_judge_goyal.py:66-67`, `287-295`) | not generic: pairwise over every pair the raters separate; the pair view is an example's own question |
| `rouge1` and `coverage` free metrics, the 18-versus-19 split, system means and the system ranking (`validate_judge_zhang.py:314-327`, `266-311`) | not core. Free metrics are arms on the same dataset in `examples/summeval-judging/` already, and a `--floor-run` names the best one as `min_metric` (RUNBOOK:1319) |
| `report.json` and the record files under `data/judge-validation/` | kept, as the research report's evidence (owner, 2026-11-20): the two tools, their report and record schemas, V12, `checks_of` and the "People's checks" stay; the command's runs are what `scorer-show` and the Workbench's part c list first |

I count no percentage: the functions are listed so a reviewer can check the mapping line by line.

### 3.4 What the Workbench offers

"A judge for this goal", part c "Does it agree with people?" (UXS-005 lines 499-507), changes from "shown as stored" to doing it. It keeps the stored validation, the reasons it is not validated and the runs, and gains:

- **Validate it**: a rated dataset to choose (`scorer-show`'s `rated_datasets`: the datasets whose first item and reference have the rated shape for the scorer's dimensions), the floor, the estimate before anything is called (`POST /estimate` on `judge-validate`, as for `judge-score`), the cap, and a job. The result is the table of section 3.1 step 5.
- **Write it into the scorer**: with who and why, offered only when the scorer has judged nothing; otherwise "Make a new version with it" (`scorer-new` with `supersedes`), as part b does.
- the command beneath, folded (UXS-005 line 12), and the W7 row of the screens table gains `judge-validate` (UXS-005 line 663).

### 3.5 Refusals

- A dataset that is not rated (an item without `source` and `outputs`; a reference without `ratings`; ratings that carry none of the scorer's dimensions, one it does not judge, or different dimensions in different items (a subset of the scorer's dimensions is allowed and said, section 3.2); a ratings list whose length is not the item's output count).
- A scorer whose `mode` is `pairwise` and a dataset whose items have fewer than 2 outputs; a `pick` scorer whose `outputs_per_call` is below the outputs (`harness/docs/RUNBOOK.md:1259-1261`).
- A `provider: fake` judge: the run is allowed (it is how the plumbing is tested for $0), `--fill` is refused, since the gate refuses a fake judge whatever the block says (`judge_score.py:425-427`).
- A grade scorer whose prompt does not name every dimension (`judge_score.py:185-192`): the command refuses before any call, as `judge-score` does.
- No cost cap (`cost_cap_usd` and the environment): refused, with what the dry run estimated.
- `--fill` on a scorer that has judged scores: refused, naming `scorer-new --supersedes` (the scorer's hash is recorded on every judged score).
- `--fill` over an existing, different `validation` block without `--replace`.

### 3.6 Migrating what exists

`harness/data/judge-validation/{judge-summ-v1,judge-summ-v2}/{goyal2022-cnn,zhang2023-cnndm}/` is committed evidence made by the scripts. The draft was to migrate them to the form the command writes and delete the scripts; the owner kept them (below).

**Re-projection at $0 works (verified 2026-11-20, in a scratch project, for all eight scorer, judge and source combinations).** The committed records hold each reply (Goyal: the reply, per dimension, in `output`; Zhang: `dims`, per block) with the order it was shown in. A throwaway importer reads them into a capture of verdicts in the adapter's output form, in the dataset's item order; the example source builds the rated dataset (the same 100 articles: the Goyal source's ids are the archive's keys, the Zhang source's the first 16 hex digits of the article's sha256, as the records' ids are); `evh run` scores a recorded system over it (the machinery of section 4.3, with `recorded_output(record)` in the adapter). 1,197 of the 1,200 records hold a verdict; three Zhang records do not parse and stay unparsed, as the reports counted them. The runs, at cost 0: tau against the ratings, with the people's own beside it (`human_tau` 0.300 on Goyal, 0.380 on Zhang):

| scorer, judge | Goyal tau | Zhang tau |
|---|---|---|
| judge-summ-v1, gemma_l | 0.205 | 0.491 |
| judge-summ-v1, qwen_s | 0.336 | 0.475 |
| judge-summ-v2, openai_l | 0.232 | 0.469 |
| judge-summ-v2, anthropic_l | 0.265 | 0.487 |

These are new definitions, not the old reports' figures (best-pick agreement with Wilson intervals, GPT-3 against BRIO, leave-one-annotator-out, the system rankings): the command does not compute them (section 3.3). Re-running the judges instead would cost the reports' `billed_usd`, $5.71 in all.

**Decision (owner, 2026-11-20): the tools and their reports stay, as research.** `validate_judge_goyal.py`, `validate_judge_zhang.py`, `data/judge-validation/` and its schemas and V12 stay where they are, outside the package, as the evidence the research report and the site rest on; `judge_figures.py`, `check_report_claims.py`, `site/figures.py`, `site/remeasured.py` and `REPORT_SUMMARIZATION.md` are not touched. The reason: the published figures (best-pick agreement with Wilson intervals, GPT-3 against BRIO, leave-one-annotator-out, the system rankings, the paired tests) are defined differently from what the command computes (tau against the ratings, the people's agreement beside it), so the new runs cannot replace them without changing what the report says. RUNBOOK §12 and the Workbench point an installed user to `evh judge-validate`; the two tools are not installed and not named on the screen.

**What was done.** The two sources build the rated datasets (`goyal2022_cnn_v1`, `zhang2023_cnndm_v1`, gold from the ratings; their items, ratings and labels are git-ignored, as SummEval's are, their checksums and the runs committed). The core adapter gained `recorded_output(record)`, and `tools/reproject_judge_validation.py` reads each judge's records as a capture of verdicts and runs the eight recorded systems (`<scorer>__<judge>__validation_<source>`) at $0; `evh scorer-show judge-summ-v1` lists them, with `fluency: not validated on zhang2023_cnndm_v1`. `--fill` was not applied to these scorers: each has judged (its hash is on 29 judged scores), and a block names one dataset, which for both is SummEval's. A scorer that has not judged takes its block from `--fill`; a new version of one that has, from `scorer-new --set supersedes=…`.

## 4. `examples/harbor/`

### 4.1 Layout and the core's share

```
examples/harbor/README.md
examples/harbor/source.py          class Source: Harbor tasks as items
examples/harbor/importer.py        class Importer: Harbor job directories as records
examples/harbor/adapter.py         call_system, score, recorded_output, CALL_ONCE
examples/harbor/systems/           harbor_oracle_v1.yaml, harbor_nop_v1.yaml, harbor_agent_template.yaml (not run)
examples/harbor/tasks/             three tiny local tasks (task.toml, instruction.md, environment/, solution/, tests/)
examples/harbor/fields.yaml        the field set the source's fields need (dataset-create refuses fields without one)
examples/harbor/_toml.py           the few task.toml keys the source and the adapter read, parsed by hand (Python 3.10: no tomllib)
examples/harbor/fixtures/jobs/     recorded, trimmed job directories: oracle and nop per task, one agent timeout, one synthetic
examples/harbor/fake_harbor.py     a `harbor` stand-in for CI
examples/harbor/record_fixtures.py records and scrubs the fixtures (local, needs Docker)
examples/harbor/test_harbor.py     the test, run by harness/tests/self_test.py
```

The core's share is the three hooks above (call once, the artifact key, the served-prefix hardening) and nothing else. A test (`test_core_stays_generic`) fails when the string `harbor` appears under `harness/scripts` (which is `harness/evaluation_harness`), `harness/workbench` or `harness/catalog_assets` outside a comment that cites this RFC. `harbor` is a program the user installs; the package gains no dependency.

### 4.2 The source

`evh dataset-create --source examples/harbor/source.py:Source --query '{"path": "examples/harbor/tasks"}'` (a local task directory, offline), or `--query '{"dataset": "NovitaAI/tb21-file-recovery"}'` (the registry; the harness's own first guess, `terminal-bench@2.0`, is no name in the registry `harbor dataset list` shows, whose names are `owner/name`; `--fieldset harbor_tasks` is needed for the fields, `examples/harbor/fields.yaml`: the source runs `harbor dataset download` into the project's `.build/harbor/`, which needs the network and is never run in CI). `items(query)` yields one item per task directory: `item_id` the task name, `text` a JSON document `{"task", "path" or "dataset", "instruction"}` (the instruction is what the inspector shows as the item), and `fields` from `task.toml`: `difficulty`, `category`, `agent_timeout_sec`. It never copies `author_email` or `author_name`. `describe(query)` gives `source: {provider: "harbor", …}`, the task count and the description. The source reads `task.toml` by hand (`_toml.py`): the package's minimum Python is 3.10 (`pyproject.toml`, `requires-python`), which has no `tomllib` (open question 7, decided). It was run against a real downloaded dataset, whose `task.toml` has `[[task.authors]]`, multi-line arrays and `[verifier.env]` tables.

### 4.3 The importer

`records(query)` over `{"jobs_dir": …, "job": optional}` yields one record per trial directory that holds a `result.json`: `id` the trial name (`fix-git__AUdzLMG` matches `_importers.py:34`), `body` the same item JSON the source writes, `fields` `{task, agent, model, difficulty, category}`, `created_at` the trial's `started_at`, `source` `{system: "harbor", url: "<job>/<trial>"}`, `outcome` `{reward, rewards, exception_type}`. A job directory is plain files, so the importer needs neither Docker nor Harbor. Then, with no further code:

```
evh capture --importer examples/harbor/importer.py:Importer --query '{"jobs_dir": "…"}' --capture harbor_2026_11
evh dataset-from-capture --capture harbor_2026_11 --dataset-id harbor_hist_v1 && evh dataset-materialize --dataset-id harbor_hist_v1
evh arm-from-capture --dataset-id harbor_hist_v1 --capture harbor_2026_11 --as harbor_recorded_v1 --like harbor_oracle_v1
```

`recorded_output(record)` in the adapter returns the same JSON the live call produces, so one `score` measures a live arm and a recorded one. A task that appears in several trials is several items (the capture's ids are trial names); choosing one trial per task is the person's `--query` (`{"pick": "first" | "last"}`), not the importer's silence.

### 4.4 The adapter

`CALL_ONCE = True`. `call_system(text, params)`:

- **Command**: `harbor run (-p <task path> | -d <dataset> -i <task>) -a <params.agent> [-m <params.model>] -o <params.jobs_dir> --job-name <task>-<utc>-<pid>-<random> -n 1 -r 0 -q -y`, `--env-file` and `--ae` from `params` when named. The jobs directory is `params.jobs_dir` (the system file says `artifacts/<system_id>`; the adapter is not given the system's id), default `artifacts/harbor`, a served prefix (section 2.2).
- **Its own timeout per item**: `subprocess.run(..., timeout=params.timeout_s)`, default the task's `agent.timeout_sec` plus its `verifier.timeout_sec` plus `environment.build_timeout_sec` plus a slack (`params.timeout_slack_s`, default 120); Harbor has no flag in seconds (section on Harbor above). On expiry the adapter sends SIGTERM to the process group (`start_new_session=True`), waits a grace period, then SIGKILL, and raises `HarborTimeout` carrying `meta = {"artifact": <trial dir if any>}`. Measured (Harbor 0.26.0, Docker, a task whose solution sleeps): SIGTERM to Harbor's process group ends the trial (its `result.json` records a `CancelledError`) and Harbor removes the container, 10 to 15 s after the signal, so the grace default is 20 s; a SIGKILLed Harbor **leaves its container running** (it had to be removed by hand), so SIGKILL is only the last resort.
- **Result**: `output` is the JSON `{task, reward, pass, answered, tests, exception, trial}` (`pass` is reward >= 1.0, `tests` from `verifier/ctrf.json`); `extra = {"reward": reward}`; `tokens_in` and `tokens_out` from `agent_result`; `cost_usd`: 0.0 for `oracle` and `nop` with `meta["cost_source"] = "no-model-agent"`, else `agent_result.cost_usd` with `meta["cost_source"] = "harbor-agent-estimate"` (read by `run.py:390-396`); `meta["artifact"]` the trial directory; `meta` also `wall_s`, `harbor_job`, `agent`, `exception_type`. The bakeoff's gateway spend delta (`/work/harness-bakeoff/adapter.py:85-111`) is a user's own hook and is not in the example (it is right only while one call uses the key).
- **`score(output, reference)`** returns `pass`, `answered`, `reward` and, with a `ctrf.json`, `tests_passed_frac`. `reward` is in both `score` and `extra`, as in the bakeoff (`:160`, `:228`): a recorded arm has no `Result.extra`, so `score` must carry it.
- **What a failure is.** A trial that ran and ended badly (Harbor wrote a trial `result.json` with `exception_info`, or `reward` 0) is a scored 0 with `exception` filled: the agent failed the task. A trial whose agent times out is both: Harbor records the `AgentTimeoutError`, still runs the verifier (reward 0, `reward_valid` true) and exits 0 (measured), so `answered` is 1 for it; `answered` is 0 only for a trial with no reward at all (it never reached its verifier). A call that produced no trial result (Harbor crashed, our timeout, no `result.json`) raises: a failed item, called once, listed by `--resume` (section 1.3). Open question 2 states the choice.

### 4.5 How it is tested

**CI, no Docker, no model, no network** (`examples/harbor/test_harbor.py`, added to `harness/tests/self_test.py` beside `:1282-1286`):

- `fake_harbor.py` is put first on `PATH` as `harbor`. It parses the flags the adapter passes, copies a fixture job directory into `-o` under `--job-name`, and exits 0; modes by an environment variable: pass, fail (reward 0), timeout (the recorded `AgentTimeoutError` job), exception (the synthetic job: `exception_info`, no reward), crash (exit 1, no directory), hang (makes the trial's directory, starts a child, sleeps past the timeout), stubborn (a hang that ignores SIGTERM) and "connection reset by peer" on stderr with exit 1 (a message the retry code reads as transient); `FAKE_HARBOR_ONLY` limits a mode to named tasks, `FAKE_HARBOR_LOG` counts the invocations, and it stands in for `harbor dataset download` too.
- The fixtures under `fixtures/jobs/` are recorded Harbor job directories without `agent/`: `config.json`, `result.json`, the trial's `config.json`, `result.json`, `verifier/{reward.txt, ctrf.json, test-stdout.txt}`, about 12 KB each. The recorder scrubs `trial_uri` (an absolute path), `base_url`, `model_api_key_name` and the home folder in a traceback, refuses to write a fixture that still holds one, and the test fails on any `/home/`, `/work/`, `http` or `_KEY` string in a fixture. The tasks are ours, so there is no third-party licence to carry.
- Proofs: the importer yields the expected records from the fixtures; capture, dataset and arm-from-capture give a recorded arm whose scores equal the live adapter's on the same fixture (two routes, one `score`); the source lists the local tasks with their fields and no author fields; a run with `fake_harbor` in crash and "connection reset" modes calls it once (the fake counts invocations) and records a failed item with its trial dir as the artifact; `--resume` does not call it again; `--resume --recall-failed` calls it once more; a hang ends at the timeout and leaves no process (the fake's process group is checked); the item view carries a link to the trial directory and the served URL answers a directory listing, with `nosniff`/`sandbox`; `test_core_stays_generic`.

**Locally, with the oracle agent, $0** (`examples/harbor/README.md`; needs Docker 29.7.2, which runs here, and the network once, for each task's image): `evh dataset-create --source … --query '{"path": "examples/harbor/tasks"}'`, then `evh run --system harbor_oracle_v1 …`, expecting `pass` 1.0 on every task at cost 0, and `evh run --system harbor_nop_v1 …`, expecting `pass` 0.0 (the verifier fails an untouched environment: the proof that a pass is not free). `record_fixtures.py` makes the fixtures from those two runs, so the pass and fail fixtures are real data, and from a third: a real failed trial, the `oracle` agent on a copy of `write-greeting` whose solution outlasts its 3 s agent timeout (Harbor ends it with an `AgentTimeoutError`). Only the `exception_info` fixture of a trial that never reached its verifier is edited, from `models/trial/result.py:28`, not recorded, and is labelled so in the README. **Run 2026-11-20:** `oracle` passes the three tasks and `nop` fails them (`pass` 1.0 and 0.0, cost 0) through `evh run`, with `env -i` (no key in the environment) for the oracle probe; 17 s a trial, 51 s a run.

## 5. What each surface shows

| item | CLI | API | catalog and inspector | Workbench |
|---|---|---|---|---|
| call once | `evh run` (dry run and first line say "calls each item once"), `evh run --resume RUN [--recall-failed]`, `evh arm-smoke`; `evh env-check` | the `run` operation (a job, spends) takes `recall_failed`; `jobs-resume` follows the same refusal | the arm page: "called once each", the run's `recalled` list | the Jobs screen, on a finished run job of a call-once arm that left held items: the items with their errors, **See the cost first** (`POST /estimate` of `run` with `resume` and `recall_failed`: its dry run prices only what the resume would call) and **Call them again** (a job under a cap, by a named person), and the commands beneath (built). "Resume the run" on a stopped job is unchanged and does not call them |
| artifact | `evh comparison-item` prints the path; `--json` carries it; `comparison-items` prints `_meta` | `comparison-item` result gains `artifacts` | `item_view` `artifact`, drawn as a link | the item views that read `comparison-item` draw the link and print the command (screens to be listed in step 2) |
| judge validation | `evh judge-validate`; `evh scorer-show` lists the validation runs instead of "People's checks" | `judge-validate` operation (a job, spends; not an MCP tool, as `judge-score` is not) | the judge's page lists the validation runs | W7 part c: validate, estimate, write, command |
| Harbor | `evh dataset-create --source …`, `evh capture --importer …`, `evh arm-from-capture` | none of its own | its runs and arms like any; the trial link | the same screens as any system |

## 6. Non-goals

- Retrying a call-once item automatically under any condition. `--recall-failed` is a person naming items.
- Serving an artifact publicly, writing one through any server, or listing a directory through an operation.
- More than one artifact per item, a label for it, a typed schema for `meta` beyond the one reserved key.
- Running Harbor inside the harness, a Harbor dependency, a Harbor-aware core, a Harbor runner for [RFC-035](RFC-035-scenarios.md)'s scenarios (that is a runner, 0.9.0).
- Reading Harbor's trajectory (`agent/trajectory.json`) into the harness; the link is how a person reads it.
- A gateway-spend cost hook in the example.
- Judge validation of a judge no human rated; validating a judge in a mode other than the scorer's; the GPT-3-versus-BRIO view; a free-metric comparison inside the command.
- Extending `validate_judge_goyal.py` and `validate_judge_zhang.py`, or reaching them from the package: they stay as research, outside it, and an installed user is pointed to `evh judge-validate`.
- A Harbor dataset (the Terminal-Bench tasks) committed to this repository.

## 7. Alternatives considered

- **A system field `once: true`.** The schema is closed (`system.schema.json:10`), a person could switch the guard off for an adapter that has effects, and a new field needs a fingerprint rule. An adapter constant is what the other adapter facts use.
- **`params.call_once` in the system.** It enters the fingerprint's settings (`_fingerprint.py:378-385`) and the adapter would have to read it; the same objection about who decides.
- **An environment variable (`EVAL_MAX_RETRIES=1`).** It is the machine's, not the code's; the first run on another machine retries.
- **Words in the error message to avoid retry** (what the bakeoff adapter does, `adapter.py:137-141`). It couples the adapter to the wording of the retry table and changes the failure's meaning; that is the problem this fixes.
- **Refusing `--resume` for call-once runs, as a replay does.** Items are independent, and a crash at item 40 of 50 should not cost 40 paid trials. The rule here refuses only to repeat what may have happened.
- **A new `Result.artifact` field.** Adapters with their own `Result` class would not carry it (`examples/summeval-judging/adapter.py:69`), the SQLite and files stores would take a new column or format, and RFC-033 made `meta` the place for what an adapter wants kept.
- **A new artifact route in the server.** The static handler and its prefix check exist; the work is hardening them for all prefixes.
- **Serving artifacts from `data/`.** In a SQLite project `data/` is one database.
- **Extending the two tools into `evh` commands as they are.** They call judges outside the run model, so the gate cannot read their output, and they would stay two commands each specific to a download.
- **A judge-validation mode inside `judge-score`.** `judge-score` is a pass over arms with a blind shuffled judging set; validation is a run of one judge over rated items. Different inputs, different outputs.
- **Writing the `validation` block by hand, as today.** It is what `IDEAS_0.8.1.md` set out to remove; the gate then checks a block no command ever produced.
- **A Harbor importer in the core's built-in importers.** `evaluation_harness/importers/` is for formats every project has (`jsonl`, `github`, …); Harbor's is a project's own, named by path (`_importers.py:44-76`).

## 8. Build order, each step with its proof

Steps 1 and 2 come before 4; 3 is independent. Every step: `make quality`, `make check`, `stores-check`, `commands-check`, `guard-check`, `site-check`, `mkdocs build --strict`, mutation checks on its new guards (remove the guard, the test fails), commit, ci-watch green.

| Step | What | Proof |
|---|---|---|
| 1 | Call once: `_adapter.call_once`, the wiring at `run.py:1469`, the failed item keeping `exc.meta`, resume rules and the start mark in both stores, `--recall-failed`, `arm-smoke`, the dry-run and first-line text, `run.json` `call_once` | `tests/test_call_once.py`: an adapter with `CALL_ONCE` that raises `TimeoutError("timed out")` is called once and its item is failed, exit 0, not 75; the same adapter without the constant is called up to `EVAL_MAX_RETRIES` times (the existing behaviour); `call_once(params)` per system; the warm-up is retried; resume does not call an output item, a failed item or an item with a start mark, and calls an item with neither; `--recall-failed` calls the failed and in-doubt items once and records `recalled`; refused on a run that is not call-once; a kill during a call (the child process is killed with SIGKILL) leaves a start mark both stores read; `arm-smoke` makes one call per item; `test_replay.py` and `test_failed_items.py` unchanged and green; `make stores-check` |
| 2 | The artifact: write-time normalisation, `item_view` and `info`, the inspector link in `inspect.js`, `comparison-item` text and JSON, the Workbench draw, `artifacts/` as a default served prefix, `nosniff`/`sandbox` on every prefix, the symlink check, the release rules | `tests/test_artifact.py` and additions to `test_catalog.py` (`:660-700`), `test_release_exposure.py`, a browser test: a `..` path, an absolute path outside the project and a path through a symlink are dropped with a reason; a path under `artifacts/` renders a link, a path under no served prefix renders text; the served directory answers a listing and a file with `nosniff` and `sandbox`; a symlink planted in a served directory to `/etc` is 404; the link is absent in `--public`; a hidden dataset's release drops `artifact` and refuses an artifact under `data/runs/`; the inspector escapes a path with markup; every Workbench screen that shows an item is listed and has a test |
| 3 | `evh judge-validate`: `judge_validation.py`, the op and the CLI, the floor, `--fill`, the Workbench part c, the committed records as eight recorded runs (the tools and reports stay as research) | `tests/test_judge_validate.py` with the existing provider stub (`test_judge_score.py:1363-1400`): for each mode a run is made per judge on a 3-item rated fixture and `validation_problems(sc)` returns `[]` after `--fill`; the message the adapter sends is byte-equal to the one `judge-score` sends (`test_judge_message_frozen.py`); the floor's value is the `min_metric`; every refusal in 3.5; the two example sources build the rated shape from a small fixture in each download's format; the gate refuses a fake judge's `--fill`; the Workbench part c in `test_workbench_live_browser.py`; after the migration the eight recorded runs are listed by `scorer-show` and `evh validate` is green with them (the tools stay). The paid reproduction of the committed SummEval `gemma_l` figure (open question 5) was run on 2026-11-20: tau 0.5156 on `summeval_rated_100` against the committed 0.538416, $0.0289; the paired difference per article is -0.0228 with a 95% bootstrap interval of -0.0378 to -0.0091, so it is not article-sampling noise. A second run (2026-11-20, owner's go, same judge, prompt and 100 articles, `order: original`, $0.0293) shows the 16 summaries in the order the item lists them, as the committed run did: tau 0.5360, a difference of -0.0025 (95% bootstrap interval -0.0109 to 0.0061, per-article correlation 0.94 against 0.83), so the gap is the order. The blinded, seeded order stays the default, the fairer setting (a judge does not read the summaries in the order of their systems' names); the figures differ for that reason: 0.5156 blinded, 0.5360 in the original order, the committed 0.5384. The judge's own run-to-run noise was not measured (one run each) |
| 4a | `examples/harbor/` source, importer, tasks, fixtures, `fake_harbor.py` | the importer and source cases of 4.5 |
| 4b | the adapter, the systems, `test_harbor.py` in `self_test.py`, the README, `record_fixtures.py` | the adapter cases of 4.5; the local oracle and nop runs of 4.5 on this machine, their output pasted in the README |
| 5 | Docs of section 9; remove the `IDEAS_0.8.1.md` entry and update `WORKBENCH_GAPS_0.8.0.md` D6; RFC index and mkdocs nav | `mkdocs build --strict`; `make guide-check`; `make site-check`; every command printed in a doc is run by `commands-check` |

## 9. Docs each item changes

| item | docs |
|---|---|
| call once | `harness/docs/INTEGRATION.md` (a paragraph beside `:187-192`; the retries rule in the bundled adapter's comment, `harness/scripts/adapter.py:97-102`); `harness/docs/RUNBOOK.md` (the `--resume` section `:846-868` with the call-once rule and `--recall-failed`; the replay text `:1912-1914` stops saying call-once is only a replay's); UXS-003 (the `run` flags); UXS-005 (the eval screen's resume row, `:667`); `harness/CHANGELOG.md` 0.8.0 Added |
| artifact | `harness/docs/INTEGRATION.md` (`:71-82` the reserved key; `:382` `served_dirs` and the `artifacts/` default; `:396` the view kinds); `harness/docs/RUNBOOK.md` (`:1480` comparison-item); UXS-002 (`:275`, the item view); UXS-003 (`:146`); UXS-005 (the screens that show an item; the commands table); PRD-004 (`:176`) and PRD-017 (`:104`) where they list comparison-item; `docs/rfc/RFC-033` a one-line pointer in "Not changed"; `harness/CHANGELOG.md`; the harness site's release page (built from the CHANGELOG) |
| judge validation | `harness/docs/RUNBOOK.md` (`:1154-1157`, which says neither tool "is an `evh` command", and the section "Validating a judge: what the gate needs", `:1297-1335`); `docs/tutorials/3-frontier-reference-and-judging.md` (step 5, if it names validation; not read); UXS-005 (W7 `:499-507`, which says "this screen does not run one", and the screens table `:663`); PRD-003 (judging); `docs/RELEASING.md:51-52` (the step that rebuilds the reports with `--no-calls`); `docs/DATA.md:52-53` (the two downloads' licences move to the examples' READMEs); `harness/CHANGELOG.md`; `research/internal/IDEAS_0.8.1.md` (the entry is done: removed); `research/internal/WORKBENCH_GAPS_0.8.0.md:21` (D6); `harness/skills/` (an agent skill for the command, if one covers judges: not read) |
| Harbor | `examples/README.md` (the index of examples); `examples/harbor/README.md`; `docs/GUIDE.md` "where to go next" and the tutorials only if an example is listed there (not checked); `harness/docs/INTEGRATION.md` (a pointer under "If your system is not a function call", `:95-104`); `harness/CHANGELOG.md`; the site's examples list if it has one (not checked) |
| the RFC | `docs/rfc/index.md` (a row under Open RFCs after RFC-037's, `:48`) and `mkdocs.yml` (the nav entry after RFC-037's, line 103); `docs/rfc/index.md:62-67` ("Adding one") does not match the RFCs' real structure and is left alone here |

## 10. Decisions (owner, 2026-11-20: all nine recommendations taken)

Each was an open question with a recommendation; the owner took every recommendation as written. The question and the reasoning stay, so a reader can see what was decided and why.

1. **The recall flag.** Name (`--recall-failed`), and whether a failed or in-doubt item is ever called again without a person naming it. **Decided** (the recommendation, taken): as in 1.3: never without the flag; the flag is allowed for an agent too, because it spends money and repeats a side effect but leaks nothing; the run records which items it recalled.
2. **What a Harbor trial that ran and failed is.** A scored 0 (`exception` recorded), or a failed item. **Decided** (the recommendation, taken): a scored 0 when Harbor wrote a trial result (the agent's timeout, crash and wrong answer are the agent's score, and the 20% rule at `run.py:567-571` should not stop a run of hard tasks); a failed item only when there is no trial result (the harness could not run it).
3. **`artifacts/` served by default.** Yes (nothing to configure) or only through `served_dirs`. **Decided** (the recommendation, taken): yes; it is read-only, local, hardened in 2.3, and absent from every public and release copy.
4. **The committed Goyal and Zhang reports.** Re-project at $0 if the records allow (not verified), re-run capped, or drop them from the repository. **Decided** first as the recommendation (re-project if possible, never keep the old files beside the new); then, on 2026-11-20, by the owner differently: the records re-project at $0 (section 3.6), and the old tools, records and reports **stay** as the research report's evidence, since its published figures are defined differently from what the command computes and the new runs cannot replace them. The runs are added beside them, not instead.
5. **Reproducing a committed SummEval figure with the new adapter.** One paid run of `gemma_l` on `summeval_100` (the README puts all 100 articles at $0.03, `examples/summeval-judging/README.md:123-126`). **Decided** (the recommendation, taken): yes, once: it is the only proof that the core adapter and the example adapter measure the same thing.
6. **`--fill` on a scorer that has judged.** Refuse and name `scorer-new --supersedes`, or make the new version itself. **Decided** (the recommendation, taken): refuse; a new version is a decision with a reason (`supersedes`, `why`).
7. **Python and TOML.** `examples/harbor/source.py` reads `task.toml`; `tomllib` is Python 3.11+, and the package's minimum version is not verified here (RFC-018 mentions 3.10). **Decided** (the recommendation, taken): if the minimum is 3.10, parse the five keys the source needs by hand in the example; add no dependency.
8. **Fixtures from a real run.** The pass and fail fixtures come from `oracle` and `nop` runs on this machine ($0, Docker). The exception fixture is edited from the source. **Decided** (the recommendation, taken): record the first two; name the third as synthetic in the README; record a real one when one happens.
9. **A model-backed Harbor system.** `harbor_agent_template.yaml` ships commented and never run in CI or by me. **Decided** (the recommendation, taken): ship the template only.

## Not verified

- **Harbor, after building sections 1, 2 and 4 (2026-11-20).** Verified: `harbor run -a oracle` and `-a nop` run here with an empty environment (`env -i`, no key), cost nothing, and give reward 1.0 and 0.0 on the three tasks; SIGTERM to Harbor's process group removes its container (10 to 15 s) and a SIGKILL leaves it; an agent timeout exits `harbor run` with 0 and records an `AgentTimeoutError` beside the verifier's reward; `harbor dataset download` lays a registry dataset out at `DIR/<name>/<task>/`. **Not verified:** whether podman works (it is not installed here); the exit code of `harbor run` when Harbor itself crashes; a model-backed agent; `harbor run -d … -i …` (the download was run, the trial was not); an `environment` other than Docker.
- Verified: `jobs-resume` copies a job's inputs to the new job (it now drops `recall_failed`), and `sweep.py` names `--resume` nowhere, so a sweep cannot pass it. The start mark is a checkpoint line (section 1.3). `run.json` and the score's record accept `call_once` and `recalled`: `schemas/metrics.schema.json` is closed, declares both now, and `evh validate` reads call-once runs clean (it complains when the declaration is taken out). The format-7 constant was not needed: no format changed.
- Built after the first review: the Workbench's recall decision (section 5), "not in this deployment" (section 2.4), and failing-case tests for the single-slash url guard (inspector and Workbench, a stub hands the page `//host`, `javascript:`, `/\host`, `https:`), for `jobs-resume` dropping `recall_failed`, and for the public strip through a live `catalog-serve --public`. No Workbench screen shows a finished run's item (section 2.4: decided, not built).
- Section 3, after building it: no real judge was called (the tests script the judge; the one paid check, open question 5, is not run); `--fill` is shown on scripted judges and refused on fake ones; the Workbench's part c is run in a browser against fake judges only; `--resume` after a killed process is not tested.
- Verified, sections 1 and 2: no Workbench screen reads `comparison-item` (section 2.4); `end_headers` sent the headers to the data prefix only, so `served_dirs` got none (the test failed before the change); a symlink under a served prefix is followed by the stdlib handler (the file behind it was served until the check was added).
- Verified: RFC-023's file is `RFC-023-labels-and-references.md` (the Related line says so now); `esc` in `inspect.js` escapes `&`, `<`, `>` and `"`, not `'` (the link's attribute is double-quoted); `evh validate` tolerates an `artifacts/` directory at the project root, a symlink out of it included. **Still not read:** RFC-019 section 4's text on hidden datasets (the release rules were checked in code and by a test instead); `docs/tutorials/3-…` and `harness/skills/` (a search of `harness/skills/` finds no `resume`).
- Line numbers I took from research reports and did not open myself: `catalog_serve.py` except `:1515-1523`, `catalog_views.py`, `ops/*.py`, `model/scorers.py`, `faithfulness.py:146`, `sweep.py` (searched, not read), `_fingerprint.py:378-385`, `stats.py`. Read since, and as stated: `arm_smoke.py:305` and `:334-340`, `catalog_serve.py`, `catalog_views.py`, `ops/inspect.py`, `harness/tests/self_test.py:1282-1286`.
