# Upgrading

Two cases. **If you pin a release**, read the section for each release you cross, below:
change the pin, then check what it says can move. **If you copied `harness/` into your
repository** before October 2026, read the rest of this page first: your copy has
correctness bugs, not just missing features.

## From 0.8.0 to 0.8.1

Change the pin to `@v0.8.1` and reinstall. No format changes: `evh migrate --check` finds nothing to do, and no run, baseline
or fingerprint is rewritten or re-scored. **Some numbers read differently**, and some commands refuse what they used to write;
the full list, by project, is in the [0.8.1 notes](../../docs/releases/0.8.1.md). Run `evh validate` after upgrading: it
has two new checks (V29 for every `of`, V30), and a note for each measure whose direction nobody declares.

- **What reads differently** (nothing is re-scored; the runs are the same, their reading is not):
  - **A repeat joins its arm.** A run made with `--purpose repeat --of RUN`, as RUN was run (the same data, deployment,
    settings and adapter; a later harness build does not matter), is now read in RUN's arm, which gains a run: its mean,
    its pair tests and its goal page can change, and so can the count of arms. It was a separate `repeats` arm. A repeat that
    differs in one of those is still read under `repeats`, and `evh run --purpose repeat` says which before its first call
    (`--dry-run` too), naming each field that differs with its value then and now. A repeat with `--items` is a subset, which is other
    data than a run of the whole dataset: it joins only a run of exactly those items.
    A closed round's numbers do not change.
  - **A repeat set is what the runs record, not what they are called.** `--repeat N` records `repeat_index`, and that, or a
    joined repeat, makes a set. Two runs named `foo_r1` and `foo_r2` by hand (copied in, or made before 0.6.0 recorded
    `repeat_index`) are two plain runs: `evh validate` fails them as V8 does any two measurements of one system. List the pair
    under `duplicate_ok` in `validate.json`, or put each run's `repeat_index` in its `run.json`. Runs that carry the same
    `repeat_index` (two `--repeat` invocations of one system, each with an `r1`) are two sets, not one: V8 fails them, or
    notes them where `duplicate_ok` lists the pair.
  - **`evh leaderboard` reads an arm's value as `arm-show` does:** the mean over its items, repeats pooled per item, not the mean
    of its runs' means. The two differ only where an arm's runs score different item counts; the `spread` is still of the runs.
  - **A 0.7-era `--repeat` set with no `of` stays under `repeats`.** A `--repeat N` set recorded with `purpose: repeat` and no `of` (0.7 and earlier) is read as it was in 0.8.0: under `repeats`, as an arm of its own beside the plain run. Only a repeat that names the run it repeats (`--of`) joins that run's arm, and `evh run --purpose repeat` now refuses to write one without `--of`.
  - **An arm is read against one reference in every view.** `leaderboard`, `pair-test`, `cost-report` and the other commands
    that read runs by arm now leave out a run scored against another reference than its latest run's, as the catalog did, and
    name it in a `WARNING` line, where they averaged it in.
  - **`wer`, `cer` and `der` read lower-is-better** wherever no goal, adapter (`METRIC_DIRECTIONS`) or `import-run --asc`
    says otherwise; they read as higher before, so a project whose datasets rank on one of them (the podcast project's `wer`)
    sees every ranking and test on it turn the right way up. A declaration still wins.
  - **A goal that lists the dataset is heard before a goal the runs name** when both declare a measure's direction on it
    (a goal that names the dataset speaks for it; a run's `goal` only says what the run was made for). A goal with
    `datasets: []` is heard only through a run that names it, or by a question with no dataset (`metric-list`,
    `metric-show`). `output_words`, `output_chars`, `lines`, `chars`, `n_items` and `reasoning_tokens` are neutral by name:
    an adapter's own `chars` or `lines` that is a quality measure needs a `METRIC_DIRECTIONS` entry or a goal.
  - **A measure nothing declares is still read as higher-is-better**, as before, and now says so: `leaderboard`,
    `run-compare` and `goal-leaderboard` print a `NOTE`, and `evh validate` prints a `V14` note for each goal measure and
    each primary metric that rests on it. Declare the direction in the goal (`direction:`) or the adapter.
  - **A command that is not given `--metric` reads the measure that decides on the dataset**: the goal's, when a run records
    it, else the runs' primary metric (`leaderboard`, `pair-test`, `family-test`, `rank-stability`, `holdout`,
    the sheet and the inspector's first metric). Where a goal's measure is not the runs' primary metric, the default changes;
    pass `--metric` to pin one.
  - **A measure whose datasets disagree reads "mixed"** on the metric pages and the goal's pages, with each dataset's answer;
    a descriptive measure reads "neutral", never "higher is better", in the leaderboard's heading.
  - **A baseline is the goal's own.** The datasets page names the goal beside each baseline, and a goal's page shows the
    baseline its own goal promoted, not the latest of any goal on the dataset.
  - **A score that is not a number is a failed item.** A NaN, an infinity or a None from an adapter's `score()` fails the item
    in `evh run` (scored as a failed item is, never averaged; `--resume` calls it again). A run already recorded with one
    is read the same way, as a failed item scored 0, on read as on write. The tests used to leave such an item out and say
    how many (`non_finite`), so the verdict on old data with a NaN can move: an arm that was significant on N-1 items can
    stop being so on N.
  - **A cost nobody reported is unknown, not `$0`.** `arm-smoke`'s full-run projection says "cost unknown" instead of
    `about $0`, the cost charts leave an arm with an unknown cost off the cost axis and name it (they read it as 0), and refuse
    (`not-enough`) when no arm has a known cost, where they drew every arm at 0; and a
    run where only some items reported a cost records `cost_coverage` (its `total_cost_usd` is of those items). A recorded
    cost of 0 shows `$0` where a table showed "—".
- **What a script or a pipeline must change** (each is refused by name, before anything is spent or written):
  - `--purpose repeat` without `--of RUN` (`bad-argument`): name the run it repeats, or leave `--purpose` out. A `--scratch`
    pass is exempt.
  - `--of` on a `repeat`, `retime` or `pair` run that names another system's or dataset's run (`mismatch`). V29 fails one
    already committed: correct the `of` in its `run.json`.
  - `--purpose repeat --round R --of RUN` where RUN's arm is retired in round R (`bad-argument`): it would bring the arm
    back into play. Repeat the run outside the round, or bring the arm back on purpose with a run of its own.
  - A `--run-id`, `import-run --system-id` or `reference-promote --name` that is not a plain name (ASCII letters, digits, `.`,
    `_`, `-`; `bad-argument`).
  - `run-promote` of a run whose build records `dirty: null` and no `source` (a run from before 0.8.0, which says nothing of
    its tree): it refused only a build git could not read; `--allow-dirty` overrides, as for `label-from-run`.
  - `evh leaderboard --goal G` where no run records the goal's measure: exit 7, `ERROR (nothing-measured)`, naming what
    the runs record. It was `not-found` (exit 1): a script that matched `not-found` there must match the new kind. Without `--goal` it ranks each arm on its own headline with one `NOTE`.
  - `import-run` with a `--reference-id` that is not there (`not-found`), a `--reference-tier` that contradicts the id
    (`mismatch`; the id says the tier: `gold/x`), or a tier with no reference (`bad-argument`).
  - `arm-smoke` with a `--goal` or `--round` that is not there (`not-found`), or a `--round` with no `--goal`.
  - **A run with no goal, once the goal policy says so.** If `data/goals/policy.yaml` has a `required_from` date that has
    come, `evh run` (not `--scratch`) and `evh import-run` refuse a run with no `--goal` (`bad-argument`); validate's V14
    only failed it afterwards. `import-run` takes `--goal G` now: add it to the scripts that bring runs in.
- **`evh validate` has two checks that can fail a tree that passed.**
  - **V30:** a run the harness scored (`evh run`, `rescore`, `judge-score`, `sheet-import`) whose reference or label set
    is gone fails, named with the file that holds the link (`runs/<id>/run.json`). A goal's `datasets:` entry that names
    no dataset (a plain id, prose or a pattern) is a warning, and an imported run's reference kept outside `data/` is a
    note: neither fails. From 0.9, a plain id that names no dataset fails: make the dataset (`evh dataset-create`),
    remove the entry, or write it as prose. A project that deleted a reference its harness-scored runs were scored
    against fails it: restore the folder (`evh reference-promote`), re-score against a reference that is
    there (`evh rescore --reference-id`), or remove the runs. `evh validate` also notes (V16) each run scored against a
    reference that is no longer under `data/references/`.
  - **V29** now holds a `retime` and a `pair` run's `of` too, not a repeat's alone: it fails one that names a run of another
    system or dataset. It only notes an `of` whose run was deleted (the repeat is read under `repeats`), and a round that
    recorded a repeat under `repeats` where the repeat now joins its arm (the round reads what it recorded; the repeat is
    listed in its "since then"): no migration, and nothing to do.
- **A study's `stop` takes one bound** (`trials`, `usd` or `wall_h`): a spec that needed `trials`, or both `usd` and `wall_h`,
  still works.
- **A public deployment shows less.**
  - A system's `params.prompt` (any prompt text its yaml carries) and a recorded prompt file's text (`prompt-show --text`,
    `prompt-diff`) are shown on a public surface only with `--publish prompts` (`evh catalog-serve`) or `catalog: {publish:
    [prompts]}` in `config.yaml` (the catalog's pages and the public MCP server). Without it a page shows `(prompt text: not
    published here)` where `params.prompt` stood. A reference's promotion reason and a prompt version's note stay public.
  - A read a public server leaves out (`judge-verdicts`, `comparison-item`, `comparison-items`, `sheet-show`, `exposure`, `sealed-counts`,
    `validate`, `data-ls`, `data-show`, `label-mutants`, `label-coverage-show`) now refuses in-process too (`not-allowed`)
    when the call is a public one (`EVH_PUBLIC` set, or `--public` hosts), not only over HTTP. A script that called them with `EVH_PUBLIC` set must run without it.
  - A dataset whose file is missing or unreadable is hidden on a public server, not shown.

## From 0.7.2 to 0.8.0

- **A pin on a commit of the 0.8.0 branch, from before the release, installed `0.8.0.dev0`**, the version every commit of
  it carried. Move it to `@v0.8.0`: that reports `0.8.0`, so a plain `pip install` replaces it. The general rule holds for
  any two commits that report one version: moving such a pin from one commit to another does nothing with a plain
  `pip install`, because pip says "Requirement already satisfied" and keeps the old commit. Use
  `pip install --force-reinstall --no-deps "evaluation-harness @ git+https://github.com/chipi/eval-harness@<new commit>#subdirectory=harness"`
  (`--no-deps` keeps pip from reinstalling every dependency). To see which commit is installed, read the install's record
  of its source:
  `python -c "import importlib.metadata as m; print(m.distribution('evaluation-harness').read_text('direct_url.json'))"`
  prints the `url` and, for a git install, `vcs_info.commit_id`. `evh --version` shows only the version, which does
  not tell two commits of it apart.
- **The legacy read commands and MCP tools are gone, no alias** (RFC-032 step 9). A script, a Makefile, a skill or an
  agent's configuration that runs the commands `overview`, `activity`, `arms`, `datasets`, `references`, `metrics`, `goals`,
  `rounds`, `inspect`, `labels`, `tags`, `captures`, `models`, `prompts`, `studies` or `label-coverage`, or that
  calls an MCP tool of one of those names, takes the operation instead: the CHANGELOG's 0.8.0 "Changed" entry lists
  each with its replacement (`goals --goal G` is `evh goal-leaderboard G`; `inspect --runs A,B` is `evh
  comparison-show --runs A,B`, where A and B are now arm or system ids, not run ids: a run id is refused with
  `not-found`, and `evh arm-list` names the arms; `inspect --sheet --dataset-id D --runs A,B` is `evh sheet-show D --runs A,B`, and
  with `--csv` it is `evh sheet-export --dataset-id D --runs A,B --csv FILE`). Where these hide in a project made
  before 0.8.0:
  - **its `AGENTS.md`**: the one `evh init` wrote up to 0.7.2 runs the old `overview`, `goals --goal G`, `datasets`,
    `arms`, `rounds --goal G` and `inspect --runs A,B`, and an agent that follows it runs commands that no longer
    exist. `evh init` never overwrites the file: run `evh init --store files` in an empty folder
    and carry the new `AGENTS.md` over, keeping your own additions;
  - **its installed skills** (`.claude/skills/`, from `evh skills-install`): two of 0.7.2's run the old reads;
    `evh skills-install --force` replaces them with this release's (it overwrites copies you changed);
  - **its own Makefile targets, README examples and scripts**.

  `grep -rnE "evh[[:space:]]+(overview|activity|arms|datasets|references|metrics|goals|rounds|inspect|labels|tags|captures|models|prompts|studies|label-coverage)([^a-z-]|$)|evh[[:space:]]+leaderboard[[:space:]]+--dataset-id" AGENTS.md CLAUDE.md .claude/skills Makefile README.md`
  finds them (add your scripts' folders). The reads that kept their name take the
  dataset, system or model as their argument (`evh leaderboard D`, `evh deploy-sheet S`, `evh periods M`), and what
  they print in `--json` is the operation's structured result (`result.runs` for `runs-list`, `result.sets` for
  `looks`, `result.schema` and `result.baselines` for `baselines`). MCP clients: a tool is named as its operation, and
  takes the operation's inputs.
- **The commands that work on the project take named options, and a job is an operation and its inputs** (RFC-032 step
  9). What was a positional of a command that runs as a job is a named option: `evh data-put PATH FILE` is `evh data-put
  --path PATH --file FILE` (`--file -` reads standard input), `evh data-put PATH --set K=V` is `evh data-put --path PATH
  --set K=V`, `evh data-rm PATH` is `evh data-rm --path PATH`; each command's `--help` names them. A script or Makefile that
  ran a harness script by its path (`scripts/catalog_build.py`, `migrate.py`, `data_migrate.py`, `data_put.py`, ...)
  runs `evh` instead (`evh catalog --out DIR`, `evh migrate --check`). `evh jobs-start` names an operation and has no
  `--reason`: a decision's reason is one of its inputs (`--arg reason=...`, `--arg conclusion=...` for `round-close`).
  Through the API a job is `{"operation", "inputs", "by", "for", "max_cost_usd"}` (or a POST on the operation's own
  resource), an input named as the operation names it (`dataset_id`, not `dataset-id`), and an estimate is
  `{"operation", "inputs"}`; `{"command", "args"}` is refused. Jobs recorded before this in a project's `.build/jobs/`
  name a command the harness no longer runs: let them end, then delete the folder.
- **`evh mcp`'s `--write-answers` and `--answers` are gone** (RFC-032 step 9): a deployment that wrote answers ahead and
  served them drops both (the server answers the first `goal-list` in 7 to 8 s at cpus 0.5 without them); a stale
  `mcp-answers.jsonl` beside the release is read by nothing and can be deleted.
- **Run `evh migrate` once** (`--dry-run` first shows what each step will do, running the real steps on a copy of the data
  under the project's `.build/`, as large as the data while it runs and deleted after; a second run changes nothing). It
  brings the data to format 7 and records it in `data/project.yaml` (RFC-032): from 0.8.0 a project's data has a
  format, `evh migrate --check` compares it with the release's, and a deploy runs that check (the RUNBOOK's "The
  data's format"). A SQLite project's database is copied beside it first, as `data/project.sqlite-before-format-<n>-<time>`: the undo, to delete once the project works on format 7. Commit `data/project.yaml` with the
  migrated data. Its steps, in order:
  - *runs* (RFC-024): a run's outputs become one `outputs.jsonl` instead of an `outputs/` folder of `<item>.txt`,
    a derived run whose outputs are byte copies of its source's keeps none of its own, and the leftover row
    checkpoint goes. Each run is checked byte for byte before its folder is removed; nothing in a fingerprint
    moves. Then let git see the new files: a `.gitignore` that re-admits `outputs/**` in a run directory needs
    `!…/outputs.jsonl` instead (this repository's `harness/.gitignore` shows the pattern). The old layout is not
    read after the upgrade.
  - *datasets* (E3): each dataset record's `version` is recomputed from its lineage and a record without a
    `source` block gets the one its committed profile recorded; `validate` V22 then holds the records to the
    0.8.0 format. Item ids and hashes do not change, so no run or fingerprint moves.
  - *records* (RFC-027): each `data/baselines/<dataset>_baseline.json` becomes version 1 of the goal it names
    (`data/baselines/<goal>/<dataset>/1.json`), or of the dataset's own (`_dataset/`) when it names none, marked
    "promoted before 0.8.0, evidence not recorded"; every record without an actor gets `before 0.8.0`; a split
    side's `split.by` becomes `split.split_by`. No fingerprint moves.
  - *fingerprints* (RFC-021): a run still at version 4 moves to 5 (none left once `fingerprint-migrate` ran on 0.6.0).
  - *deployments* (RFC-032 step 2, format 2): each model record's `deployments` become
    `data/deployments/<model>/<deployment>.yaml`, in the order the record listed them, each with its onboarding as
    its first check; each of the record's `smokes` becomes a check of the deployment its arm's config names (or the
    model's only deployment). A smoke whose deployment is neither is refused before anything is written, naming the
    config: set its `deployment:` and migrate again. The model record keeps its comments and loses only those two
    keys. `evh model-list` and the catalog's model pages read the same as before.
  - *systems* (RFC-032 step 3, format 3): each config becomes a system, `<folder>/<system_id>.yaml` (a folder named
    `configs` becomes `systems`: `data/systems/`, and the folders validate.json's `systems` globs name, which were its
    `configs` globs; config.yaml's `configs:` folders are added to them), with `system_id` and without `dataset_id`,
    `goal` or `round`, its comments kept. Configs in one folder whose ids differ only by a dataset token (`_n200`,
    `_n100`, `_dm200`) and their version, on different datasets and alike in every other key, become one system
    whose id drops the token and keeps the highest version; any other group is left as it is, and a group on different
    datasets that differs in another key is refused, naming the key. Every live reference to a renamed id is renamed
    with it (runs' `config_id`, rounds' carried and retired arms, smoke checks, which name `system:` now, a sealed
    dataset's unseals, study specs, whose `baseline.config` becomes `baseline.system`, faithfulness records,
    validate.json); judging sets with their verdicts, and reference manifests, keep the ids they were made with (a
    judging set's id and a run's reference hash are made of them). `data/renames.json` lists each renamed id; the
    catalog redirects an old arm page to its new one. Then change your commands: `evh run --system ID --dataset ID
    [--goal G] [--round R]` (a run names its goal and round now), `evh sweep --systems … --dataset …`, `arm-smoke`,
    `faithfulness`, `model-onboard` take `--system`/`--dataset`, `period-compare` takes the system positionally and `--dataset`, `periods` takes the model positionally with `--system`/`--dataset` as optional filters, `deploy-sheet` and
    `dataset-unseal` take `--system`, `arm-from-capture --like` takes a system id, `make run SYSTEM=… DATASET_ID=…`.
  - *runs and scores* (RFC-032 step 4, format 4): every pass of a system over a dataset is one run in
    `data/runs/<run_id>/` (`run.json`, `outputs.jsonl`) and every score of it sits under it, in
    `scores/<scorer>@<reference>/` (`score.json`, `metrics.json`, `predictions.jsonl`). The folders `runs-linux`,
    `runs-pair` and `runs-repeats` become a run's `purpose` (`retime`, `pair`, `repeat`, with `machine` and, when
    there is exactly one other run of the system on the dataset, `of`); `runs-silver`, `runs-adjudicated`,
    `runs-rescored/<scorer>/<folder>`, `runs-judged/<scorer>` and `runs-labels-*` become scores of the runs they
    re-scored, each read under the label its folder gave it ("silver", "rescored cd35dc1f", "judged/<scorer>"). A
    judging pass's `summary.json` moves to `data/judge-summaries/`. A record reads back exactly as its metrics.json
    did; a re-score by the scorer a run already had, with the same rows, is the same measurement and is kept once. A
    round's retirement names its runs instead of a folder; validate.json's `committed`, `floors` and
    `scorer_sources` name arms by label (`runs`, `linux`, `silver`, `judged-<scorer>`), `scorer_sources[].dir`
    becomes `arms`. A pass in a folder whose purpose is not one of those is refused before anything is written:
    move it into one, or delete it, and migrate again. `data/renames.json` lists each arm whose id changed, and the
    catalog redirects its old page. Then: a `.gitignore` that re-admits run files names the new ones (this
    repository's `harness/.gitignore` shows the pattern), and change your commands: `EVAL_RUNS_DIR` is gone (a
    throwaway pass is `evh run --scratch`; a re-run is `evh run --purpose repeat|retime|pair [--of RUN_ID]`),
    `--runs-dir` (pair-test, family-test) and the inspector's `--from` are `--label`, `round-retire --runs-dir` is `--label`
    (below), and `rescore`/`judge-score` write under the runs they score (no `--out`; `rescore --label` names what its
    scores are read as).
  - *rounds* (RFC-032 step 5, format 5): a round stores its arms, `arms:` in its record, each a system, the label it
    is read under, the runs it is read through, how and when it entered (`ran` in the round, or `carried` from an
    earlier one) and its retirement (when, why, who); `carried` and `retired` go. Each round's arms are what it read
    before: the systems whose plain runs name it and those it carried, less the retired, read under the re-score its
    `scoring` last wrote; a retirement of a re-timing, a repeat or a pair run is an arm read under that label,
    retired. A retirement naming some but not all of a system's runs is refused before anything is written. A
    baseline version a round promoted names the round and the arm. Then: `round-retire` retires an arm whole, every
    arm of the system in play or the one `--label` names (`--runs` is gone), `evh round-carry` carries an arm of an
    earlier round into the open one, and `evh round-show --json` gives a round's `arms` (`round-list --json` gives a count). A run made with `--round` joins
    its system's arm, so the round's file changes with every run: commit it with the runs.
  - *system_id* (RFC-032 step 8, format 6): a run's `config_id` named its system, so the stored key is `system_id`
    ("config" is no longer the name of anything): in `run.json`, a score's `metrics.json` (and the `unset` list of its
    `score.json`), a faithfulness record, a study log's trial lines and a sealed dataset's unseals. Each file is written
    as it was, only the key changed. The keys inside a hash keep their name, so no hash moves: the fingerprint's
    `arm.config_id` (a run's hash), a judging set's `arms[].config_id` (the set's id), a label set's `source.config_id`
    (a set is hashed whole into every fingerprint of a run scored against it) and a reference manifest's
    `from_run.config_id` and `promoted_from.source.config_id`. A record holding both keys, or a `config_id` that is not
    the id of a system of the project, is refused before anything is written, naming it: add the system (or delete the
    run) and migrate again. Then change what reads the JSON answers: `system_id` replaces `config_id` in `evh leaderboard
    --json` (its rows and its column list), `evh runs-list --json`, `evh run --json` (the dry run and the run written),
    `evh baselines`, `evh prompt-show --json`'s runs, an arm's `config` block (`evh arm-show --json`), the compare answer
    of `catalog-serve`, the key file `evh sheet-export` writes and, for a catalog adapter, the `{"system_id", ...}`
    its `arm_config(arm)` returns; the table headers follow, and `evh arm-show` says `system` where it said `config`.
    `evh validate`'s V8 is "no two runs share a system_id".
  - *results* (RFC-033, format 7, both stores): the three run settings in a row's `_meta` (`generation_config`,
    `generation_requested`, `encoder_window`) that every row of every score of a run holds with one value move to
    `run.json`'s `call`; a run whose rows differ keeps them in its rows. `_meta.usage` is cut to `cost`,
    `prompt_tokens`, `completion_tokens` and, when nonzero, `cached_tokens` and `cache_write_tokens` (the rest of the
    provider's billing object is not kept: it only comes back from the provider; a `usage` that is `null` or not an
    object is left as it is), and rows are written as canonical text. `--dry-run` counts each (a large diff in git: commit it with the migration). A SQLite project's
    database is copied first, as for every step; its per-item rows, kept as table `rows`, move into the tables
    `score_sets`, `metrics`, `call_facts`, `score_rows` and `score_values` (RFC-033, ADR-0030); `rows` is dropped and
    the database is vacuumed. A VACUUM that cannot run, for want of free disk about the size of the database, leaves the data
    moved and says so. A line of a score's rows that is not a JSON object with an `item_id` is refused, writing nothing:
    correct the file first. A SQLite project that an early build of this release stamped format 7 but left with
    table `rows` is finished by `evh migrate` too, and every command refuses it until then (`ERROR (old-format)`).
    What reads a row's `_meta.generation_config` (or the other two) from a stored row reads the run's `call` instead;
    what reads a full `usage` object from a stored row keeps only what is listed; `Result.meta` itself stays free-form,
    the slimming happens when it is written ([INTEGRATION](INTEGRATION.md)); `evh validate`'s V28 checks both.

  `run-migrate`, `dataset-migrate`, `baselines-migrate` and `fingerprint-migrate` are this one command now. Moving the data into SQLite is
  `data-migrate`, not a format step.
- **`evh scorer-new` makes a scorer whose judges explain** (`explain: true`, RFC-034): each verdict carries a reason,
  and costs its output tokens. Pass `--set explain=false` for one that does not. Existing scorers have no field and are
  unchanged; to get reasons from one that has judged, make a new version (`supersedes`), and validate it with reasons.
- **`goal-leaderboard`'s `vs_leader` has a fourth key, `ci`** (the test's 95% interval, before Holm): a reader that
  checked the keys exactly reads it now.
- **A system on the bundled adapter that declares its prompt now sends it.** A system whose `prompts:` names one
  prompt (a file or a recorded version) and has no `params.prompt` was sent "Summarise:" before 0.8.0; it now sends the
  declared text, so its outputs, and the numbers on them, change. Its fingerprint already held the declared prompt's
  hash, so the runs before and after differ only there. A system on it declaring two prompts is refused (the bundled
  adapter sends one); a system with `params.prompt` is as before.
- **A study whose baseline has no run on its dataset is refused**, its dry run too (`evh run --system <baseline>
  --dataset <dataset>` first): every trial of such a study was run, paid for and dropped as compared with nothing.
- **`evh jobs-resume` refuses a run that stopped before it wrote anything** (it started a job that then failed):
  start the run again.
- **The Workbench is served from the package** (`/workbench/`, its five files): the mockup's data no longer ships;
  nothing to do.
- **Three new dependencies** install with the package: `ruamel.yaml` (a setting saved keeps its comments),
  `pyarrow` (tables and Hugging Face parquet) and `huggingface_hub` (Hub datasets in and out). `pip install` of the
  new pin brings them; nothing to enable.
- **Every `evh` command keeps the paired tests' p's** in `<project>/.cache/evh-p.jsonl`, as `evh mcp` already did:
  keep `.cache/` ignored (`evh init`'s `.gitignore` does). `EVH_P_CACHE=` (empty) turns it off; set it to another
  file to keep them elsewhere.
- **Scripts reading a paired test's JSON:** from 10,000 items (or clusters) its p is the normal limit (ADR-0028):
  `pair-test`'s `method` is `"normal limit"` (was `"sampled"`) and `permutations` is `null`; `family-test`'s
  `method` can be `"normal limit"` or `"mixed"` and its rows have a `p_method`. Such a p can be `0.0`. Below 10,000
  every p is what it was.
- **A project's data can live in SQLite** (RFC-025), if you want it: nothing changes unless `config.yaml` says
  `store: sqlite` (or `EVAL_STORE=sqlite`). Then `evh data-migrate --to sqlite` moves everything under `data/` into
  `data/project.sqlite`; `--to files` moves it back. Python under `data/` moves out first (it is never in the
  database).
- **A goal's recommendation can move.** Contenders are now the arms shown no worse than the leader by more than
  the margin (ADR-0026), and the default margins are 5% (`balanced`) and 10% (`frugal`) of the leader. Read
  `evh goal-leaderboard G` after upgrading. A goal that wants its old breadth back sets `axes.quality.margin` in the
  measure's units; one on fewer than 100 items with a continuous measure now recommends its leader and says
  "too few items to call a tie". `evh validate` notes every goal on a default margin. No run, score or
  fingerprint changes.
- **A run with one failing item now finishes** and scores that item 0 (`failed_items` in metrics.json, `failed`
  on its row): a script that expected the run to stop reads those instead. A provider error that outlasts its
  retries exits `75`.
- **Scripts and CI that branch on exit codes:** the cost cap is `4` (was `2`), nothing measured `7` (was `1`), an
  unreachable server `75` (was `1`), and a check that found problems `6` (was `1`) for `validate`, `self-test`,
  `env-check`, `importer-check`, `arm-smoke`, `model-onboard` and `deploy-sheet --capture`; a partly failed
  `sweep` is `5`. A check for "non-zero" needs no change. The table: RUNBOOK, Exit codes.
- **Who acted** (RFC-027), after `evh migrate`'s records step: a
  promotion, `baseline-rollback`, `round-close`, `round-carry` and `dataset-unseal` need a named actor off a terminal (`--by person:NAME`, or
  `EVH_ACTOR`; an agent `EVH_ACTOR=agent:NAME` with `EVH_FOR=person:NAME`), and `reference-promote` needs `--by` or `EVH_ACTOR` even at a terminal; `runs-list --baselines` is now
  `evh baselines`; `dataset-split --by hash|time` is `--split-by`.
- **Scripts matching a refusal's text:** the line is `ERROR (<kind>): <why>` (was `ERROR: <why>`). Match the
  kind (RUNBOOK, Refusals), not the wording. A project's `AGENTS.md` written by `evh init` before 0.8.0 lacks
  the "When a command stops" section; copy it from a new `evh init` if your agents read the file.

- **A repeat set beside a plain run is refused.** A script that runs an arm once and then `--repeat N` of the same
  system on the same dataset gets `ERROR (would-overwrite)` at the second command: run it as `--repeat N` alone, or repeat
  the run with `--purpose repeat --of <run_id>`. Runs already committed that way still fail V8: give all but one a
  purpose (`repeat`, `retime`, `pair`) in its `run.json`, or remove the extra one.
- **A closed round reads the runs it recorded.** Its numbers are the ones it closed on; a later run of one of its
  systems is listed "since then". A comparison you read from a closed round after re-running its arms can differ from
  what 0.7.2 showed, which mixed the later runs in.
- **`dataset-split` on a dataset with references** needs an actor (`--by person:NAME`, or `EVH_ACTOR`), and gives each
  side the parent's references: drop any step that promoted each side's gold by hand.
- **`round-carry` and `round-open --from` never read an earlier round's runs on another dataset**: a system is
  carried through its runs on the round's own dataset, and refused when it has none there.
- **A judge scorer in grade mode** whose prompt does not name each of its task's dimensions is refused by
  `judge-score` before any call: name them in the prompt, as tutorial 3's does.
- **Scripts reading `family-test`'s text**: the `A wins` column is `A wins-losses (ties)`; read `--json` (`wins`, and
  now `losses` and `ties`).
- **`rank-stability`** prints rows for halves of 5 and of half the dataset too, and its "saturated" reads from halves
  of 10 up.
- **A goal's `datasets:` entry takes only `dataset_id`, `role`, `cluster`, `decides` and `notes`.** Any other key
  (`n: 25`, `real: false`) is now refused; 0.7.2 accepted it silently, which let a YAML mis-parse (an unquoted comma
  in a note, say) become a stray key nobody saw. `evh validate` fails `V14 goals` with "Additional properties are
  not allowed ('n', 'real' were unexpected)", one per goal file; `evh migrate` does not touch goal files. Move the
  value into `notes`, or delete it.

## From 0.7.1 to 0.7.2

Change the pin to `@v0.7.2`. Nothing to migrate and no result moves. A deployment that serves `evh mcp --public
--answers` should write its answers again (`evh mcp --write-answers`): files written by 0.6.2 to 0.7.1 from a
relative `EVAL_HOME` hold empty answers. `--write-answers` now exits non-zero when a call fails.

## From 0.7.0 to 0.7.1

Change the pin to `@v0.7.1`. No format changes; no committed run's scores or fingerprint move.

- **A tree with empty judge replies from 0.7.0 or before** fails `evh validate`'s V12; the message names the
  command that rewrites them (`evh judge-score --dataset-id … --scorer … --retry-unparsed`). A retry calls the
  judge again for those blocks only; if the same scorer returns nothing again, save a new scorer version with a
  higher `max_tokens` or `reasoning: {enabled: false}`.
- **What can read differently** ([changelog](https://github.com/chipi/eval-harness/blob/main/harness/CHANGELOG.md),
  **Changed**): `family-test --round`'s p (it now reads re-scores in place, as the round does), the billed
  figure (arm smokes counted), and `runs-list --baselines` (the repeats' mean).
- **Scripts reading `--json`:** the leaderboard's text table shows the columns that fit the terminal (the JSON
  keeps all); `evh goal-leaderboard`'s last table column is `decision`, not `""`.

## From 0.6.2 to 0.7.0

Change the pin to `@v0.7.0`. No format changes and nothing to migrate: no committed run's scores or fingerprint
move.

What can read differently (the [changelog](https://github.com/chipi/eval-harness/blob/main/harness/CHANGELOG.md),
**Changed**):

- **`pair-test --round` and a round's promotion gate correct for the pick**, so a leader that was significant can
  read not significant. A round whose leader is tied, or whose arms were scored differently, now holds instead of
  promoting; its baseline is read re-scored. Re-read an open round's status (`evh round-list G`).
- **A new run never reuses a directory.** A script that passes `--run-id` for a run that exists is refused; name a
  new id.
- **`dataset-from-capture --from` and `--fieldset`** make a version that differs from what 0.6.2 made from the same
  inputs (the capture's bodies, the declared fields). Versions already made are not changed.
- **`evh run --dry-run --json`** keeps its fields and adds `estimate_is_upper_bound` (false), `calls_per_item` and
  `measured_usd_per_item`. A script that read the estimate as a ceiling should read the measured cost, or cap the
  spend with `EVAL_MAX_COST_USD`.

New, nothing to do unless you want them: a project made before 0.7.0 has no `AGENTS.md`. `evh init` in the
project adds `AGENTS.md` and `CLAUDE.md` and overwrites nothing that exists; `evh skills-install` adds the skills. An arm config may
now carry a `hypothesis:` block (V20 checks it). A captured project's own importer should add new record fields
only behind a query key, so its past captures restore as recorded (`evh capture-restore` checks it).

## From 0.6.1 to 0.6.2

Change the pin to `@v0.6.2`. No format changes, nothing to migrate, and no answer changes: views and the catalog build
read each arm's scores once, and `evh mcp` can serve answers written ahead (`--write-answers`, `--answers`).

## From 0.6.0 to 0.6.1

Change the pin to `@v0.6.1`. No format changes and nothing to migrate: no run's score or fingerprint moves.

What can read differently (the [changelog](https://github.com/chipi/eval-harness/blob/main/harness/CHANGELOG.md),
**Changed**): the sheet's win rates and verdict; a goal recommends only from the group it decides on; a config's place
in a goal's field counts one place per config, without the arms a round retired; and the catalog's run and spend
figures count runs re-scored in place, once each.

## From 0.5.0 to 0.6.0

Change the pin to `@v0.6.0`. Two formats change, and both are migrated by a script, never read in the old shape:

- **Fingerprints are version 5** (RFC-021): `instrument`, `data`, `deployment`, `settings`, each hashed, and the
  machine `evh` ran on as `runner`, outside the hash. A run made with 0.6.0 compares with a v4 run on no hash. Move
  your committed runs once, from your project's root:
  `fingerprint-migrate` in 0.6.0 to 0.7.2, the fingerprints step of `evh migrate` from 0.8.0 (`--dry-run`
  counts first; it is idempotent and prints its counts; a baseline's `fingerprint_hash` follows its run). Code that read `fingerprint.host` reads `fingerprint.runner`;
  `fingerprint.system_under_test.model` is `fingerprint.deployment`; `fingerprint.arm.params` is gone (`arm` keeps only
  `config_id` and `labels`): its params are `fingerprint.settings`, minus the deployment keys, credentials and labels, so
  an imported run's `source` is `fingerprint.settings.source`, and also `fingerprint.imported.source` (an adapter's `fingerprint(params)` hook keeps
  its vocabulary; what it declares about the prompt is now `settings.declared`).
- **`data/models.yaml` is replaced by `data/models/<model_id>.yaml`** (RFC-020): one record per model, its key in
  the old file the record's alias. Write a record per entry (`model_id`, `kind`, `aliases`, `weights`,
  `licence`) and delete the file; `validate` (V1, V18) checks them.

**Reference sets are labels you promote** (RFC-023, ADR-0022). `reference-create` and `reference-from-outcomes` are
removed. A run's outputs become a model's labels (`evh label-from-run`: the same refusals, and `--not-redistributed`),
a sheet or a folder of answers a person's (`evh label-sheet`, `evh label-import`), a capture's outcomes a `rule` set
(`evh label-from-capture`, the same rule language); `evh reference-promote` makes a reference of a set, at the tier
you choose, with a reason and who promoted it. A reference made before has no `promoted_from` and fails `validate`
(V1, V16) until it records one: `harness/tools/migrate_references_to_labels.py`, run from a checkout, records how each
was made and copies its texts into a label set, no run's score or hash moving. A reference made from outcomes has no rule of its own any
more: promoted, it is a silver like any (with gold beside it, gold still decides).

Renamed to the field's words, with no alias (the old names stop working):

- **The command `experiment-run` is `evh run`**, and its make target `make run` (was `experiment-run`). What 0.5.0 called an experiment
  is an eval; the site's `experiments.html` redirects to `evals.html`.
- **The paired test's verdict is `significant: better`, `significant: worse` or `not significant`** (was
  `separated: …` and `not separated`), in `evh` output, the catalog, the inspector and the site; `pair-test`
  prints `SIGNIFICANT` or `NOT-SIGNIFICANT`, `family_test` and `bootstrap_test` `SIGNIFICANT`. A script that
  matched the old strings matches the new ones.
- **A goal's arms that may win the tie-break are its contenders**: the decision's key is `contenders` (was
  `tied`), and `evh arm-list --quality contender|below` (was `ties|below`).

A goal's dataset `role:` is free text and keeps whatever you wrote; the docs now say validation, test and pilot
(were dev and heldout).

Seven behaviours change without a migration:

- **The `--items` flag of `evh comparison-show` is gone**, replaced by the sheet: `evh sheet-show D --runs A,B`
  shows every item's scores per arm, beside what each wrote, the labels and the winner (`--scores-only` for the
  scores alone). A script that parsed `--items` reads `--sheet --csv FILE` instead.

- **A reference folder with no manifest fails `validate` (V16).** Texts copied into `data/references/<tier>/<id>/`
  by hand said nothing of where they came from, and runs scored against them as if promoted. Import them as a
  person's labels where they are and promote them (`evh label-import --sheet data/references/<tier>/<id> --dataset-id D
  --set S --by WHO`, then `evh reference-promote … --tier … --reason …`): the promotion adopts the folder, its
  texts being the labels', so no run's reference moves.
- **`evh reference-manifest` is a promotion too**: it takes `--labelled-by` (whose labels a script builds),
  `--reason` and `--by`, and records them as `promoted_from` with the reason; a call without them is refused.
- **Each project serves on a port of its own**: `catalog-serve` on one in 18000–18999 and `mcp --http` on one in
  19000–19999, the same every time for a project's folder, the next free one if taken (`--port` overrides;
  `catalog-serve --public` keeps 8765). Bookmarks of 127.0.0.1:8765 move; the command prints the address.

- **The local catalog reads only what git keeps.** A `data/runs-*` directory your `.gitignore` ignores is no
  longer shown, as it was never in a clone or the published catalog. Runs you meant to keep: re-allow the
  directory in `.gitignore` and commit them, or move them into `data/runs`.
- **`evh run` and `rescore` warn** when they write to a directory git ignores or outside the project's
  data (throwaway `data/runs-smoke*` and `data/runs-tune*` stay silent), and `validate` notes one that holds
  finished runs.
- **`evh rescore` writes to one designated place**, `data/runs-rescored/<scorer>/<source>/`, unless `--out` names
  another; the catalog, the goals and the rounds read an arm from its latest re-score there.

Everything else is added and optional: the capture lane (`evh capture`, `importer-check`, `capture-list`,
`capture-scrub`, `dataset-from-capture`, `dataset-split`, `text: hidden`; RFC-019); evaluating what production did
(`evh dataset-list`, a label accepting more than one answer, `{"accept": [...]}`, read by `answers(reference)` from
`evaluation_harness.adapter`, scoring against a label set with `--labels`, `evh arm-from-capture`, `comparison-show --disagree 1` and
the sheet (`sheet-show`, `sheet-export --csv`, `--fill`, read back by `evh sheet-import`), `evh pick`, `evh picks`,
`evh dataset-extend`, `evh deploy-sheet`; the catalog's Labels page; an adapter's optional `same(a, b)`,
`decision(output)`, `title(item)`, `recorded_output(record)` and `production_ran(record)`; RFC-023); judging modes (a scorer's
`mode: pick` or `pairwise`, validated in that mode; RFC-005) and an adapter's optional `primary_metric(params)`;
model onboarding (`evh model-onboard`, `evh arm-smoke`, `evh model-list`, `model_record:` and `deployment:` in a
config; RFC-020); scoring that evolves (`evh score-preview`, `evh rescore --goal --round --why`,
`round-open --keep all --scoring` and `--adopt`, a goal axis's `limit: baseline`; RFC-022); `call_timeout_s` for
the built-in providers. `evh init`'s `.gitignore` now ignores `data/runs-smoke*/` and `data/runs-tune*/`; add the
two lines to an existing project's to keep scratch runs out of git.

## From 0.4.4 to 0.5.0

Change the pin to `@v0.5.0`. No record, hash or p-value moves. Three things to check first:

- **Python 3.10 or later.** The package's floor moves from 3.9, because the official MCP SDK
  needs 3.10. On 3.9, stay on `@v0.4.4`.
- **One new dependency, `mcp>=2.3,<3`**, installed with the package like every other (it brings
  `starlette`, `uvicorn`, `pydantic` and a few more; the CHANGELOG lists them). A lock file or a
  vendored install changes.
- **`evh mcp` writes one file: `<project>/.cache/evh-p.jsonl`**, the goals' paired tests kept
  between calls (`EVH_P_CACHE`). Add `.cache/` to the project's `.gitignore` if it is not there.
  Deleting the file only makes the next call slower.

A dataset id must now be a name (letters, digits, `.`, `_`, `-`): an id with `/` or `..` is
refused by every command that reads or writes a dataset's file. An arm's params as a page or
`evh arm-show` shows them hide a URL's user and password and a nested credential-named key
(`headers: {Authorization: …}`), so a page can differ from 0.4.4's where a config held one.
Everything else is added and optional: `evh mcp`, `--json` on the views, `evh catalog --mcp`; `evh dataset-profile` and a committed `data/profiles/<id>.json` give a dataset page its
"what's inside"; an adapter may answer `dataset_profile(dataset)`.

## From 0.4.3 to 0.4.4

Change the pin to `@v0.4.4`. No record, hash or p-value moves. Added and optional: `evh catalog
--about FILE` and `--repo URL`, and a goal's `links` are shown. A catalog built as a command now
puts `--brand`, `--link`, `--head` and `--api` on the arms page too, where 0.4.3 left them out.

## From 0.4.2 to 0.4.3

Change the pin to `@v0.4.3`. No record, hash or p-value moves. `evh catalog-serve` answers 404 to
any `/api/` path that is not one of its endpoints, where 0.4.2 could serve a file through it. A
`--hooks` module now sees such requests as the route `/api/other`.

## From 0.4.1 to 0.4.2

Change the pin to `@v0.4.2`. No record, hash or p-value moves. One command line changes:
**`evh overview-show` no longer takes `--all`**: `evh overview-show --period all` says the same (`--period P` on every list now,
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
- **The judge panel** is a command (it sat beside the package and could not run from a pin; removed in 0.8.0,
  RFC-032 step 7); the tutorial kit shipped its config.
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
  earlier runs they leave out; `evh round-list` reads a round against the reference most of its arms
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
  view is also a command: `evh overview-show`, `evh dataset-list`, `evh arm-list`, `evh reference-list`,
  `evh metric-list`, `evh goal-list`, `evh search`, `evh comparison-show` (with `--items` for the per-item table
  and `--analysis` for the charts as numbers). **The home page** is now a dashboard (index.html
  moved, the datasets table is datasets.html). **Metric links** now go to m/<metric>.html pages
  (metrics.html#m-<metric> anchors still exist for compatibility). A project's own catalog
  builder that reuses `render_inspect` gets the arm and metric links only when the built pages
  exist (`pages=True` parameter).
- **Goals** (`data/goals/<goal_id>.yaml`, `goal:` on configs, validate V14). Nothing is
  required of an upgrading project until it sets `required_from` in `data/goals/policy.yaml`.
- **Eval rounds** (`evh round-open`, `evh round-retire`, `evh round-close`, `evh round-list`;
  `round: rN` on configs; validate V14). `--round rN` on `leaderboard`, `family-test`,
  `pair-test` and `comparison-show`: `comparison-show --round` and `pair-test --round` default to the goal's
  measure and the round's leader (`pair-test`'s B: the baseline the round started from). A
  project that never opens a round sees none of it
  ([tutorial 4](https://evals.humancopilot.eu/docs/tutorials/4-rounds-and-versions/)).
- **A run becomes a reference:** `reference-create --from-run <run_id>` copied a finished
  run's outputs and called nothing; the reference recorded the run, and it refused an empty output and
  outputs that stopped at `max_tokens` (`--allow-cut-off`). (Removed in 0.6.0: `evh label-from-run`, then
  `evh reference-promote`.)
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
| used `pair_test --family N` and called it Holm | it was **Bonferroni labelled as Holm** (more conservative, so some real significant differences were reported as not significant). `family_test.py` now does the genuine step-down; `pair_test` says what it does | `a57d778b` |
| had a run crash or stop mid-sweep | **every paid item before the crash was lost**: outputs reached disk only after the pass. Now each output is written as it arrives | `c6e8365f` |
| resumed a run (`--resume`) | a fully resumed run **wrote empty scores and reported success**; replayed items lost their cost, tokens and diagnostics (a resumed run under-reported spend: $0.03 for $0.05 real); `--resume` **accepted another arm's outputs** without complaint | `c6e8365f`, `897c0bbc`, `3f16a79b` |
| ran out of disk, or killed a run | writes were not atomic, so a **half-written output was replayed as the model's answer** and scored | `8e98a885` |
| re-scored against a gold set that had changed | the rescored run **asserted the old reference hash** while scoring against the new files | `ebd54b60` |
| used a cost cap (`EVAL_MAX_COST_USD`) in scripts or CI | a cap that stopped the run before any item **exited 0**, leaving an empty run that looked complete. Exit codes are now 0 complete, 2 stopped early, 1 nothing measured | `2b6a129a` |
| ran `silver_calibrate` on exactly 3 arms | it crashed; the minimum is now stated as 4, with the reason | `ebd54b60` |
| read `dirty: true` on your runs | every run after the first on a machine was marked dirty, because earlier run directories are untracked files. Untracked paths under `data/runs/` no longer count | `9ec2513a` |
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
| `make holdout` | tune on a pilot slice, confirm on the held-out rest |
| `make bootstrap-test` | intervals for corpus-level metrics (with the caveat that it is anti-conservative) |
| `make cost-report` | billed cost and projections per arm |
| `make validate` / `make check` | schema and tree validation that exits non-zero, for CI |
| `pair_test` / `family_test --items FILE` | test on a declared item subset (a stratum), the same ids everywhere |
| `make judge-score` / `evh judge-score` (0.3.0) | optional: re-measure stored outputs with LLM judges, refused until validated against human ratings; any text task, declared in the scorer (RUNBOOK §12) |

### 4. What not to copy

These exist for this repository's public showcase and assume its six evals, its
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
