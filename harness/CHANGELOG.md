# Changelog

Every release of the harness, newest first: what it shipped, and what a project pinning it
should know. These are the release notes. The same section is the text of the release's
GitHub Release, and the harness site shows them at
[evals.humancopilot.eu/releases.html](https://evals.humancopilot.eu/releases.html).

The version lives in `scripts/_version.py`; a release is the git tag `v<version>`, and the
release workflow refuses a tag that disagrees with that file or has no section here. A change
that can move a result is never a patch release without saying so under **Changed**.

## 0.8.0 — unreleased

### Added

- **A private inspector behind a proxy** (homelab, 2026-11-05): `evh catalog-serve --behind-proxy HOST[,HOST]`
  serves the whole local inspector (pages, items, outputs, references) to the named Hosts as well as this machine,
  with `--bind 0.0.0.0` in a container behind a team's own proxy; no rate limit and nothing withheld, unlike
  `--public`. The data page's writes are not served through it.
- **A round's baseline can be named** (the fleet's feedback 22): `evh round-open … --baseline <config_id or run id>`
  records the run the round starts from when the dataset has no promoted baseline (arms carried in with `--keep`), so
  `pair-test --round` and `evh rounds` read its arms against it instead of refusing ("records no other baseline
  run"). `round-open` says which run the round starts from.
- **A regression guard** (the fleet's feedback 28): `expect_identical_to: <config_id>` in an arm's config says its
  runs must reproduce that config's, item for item and output for output (the same code at another commit).
  `evh validate` V5 reads such a pair as the agreement asked for, not as an inert knob, and fails the guard when they
  differ. Recorded on the run, outside the fingerprint.
- **A project's data in SQLite, a project's choice** (RFC-025). Files stay the default; `store: sqlite` in
  `config.yaml`, or `EVAL_STORE=sqlite`, keeps everything under `data/` in one database, `data/project.sqlite`
  (write-ahead logged; a run's outputs and rows committed as they are produced), and nothing under `data/` on disk
  but it. Every command, the catalog and the inspector read and write through one module (`_store`); a test fails on
  path I/O anywhere else. `evh data-migrate --to sqlite|files` moves a project either way, every file read back by
  its sha256; on this repository's data the round trip gives back every file byte for byte. `validate` V23 names a
  project in both. Python code is never in the database.
- **The Configure page** (PRD-016, UXS-004, ADR-0027), for a SQLite project that sets `configure: true`: a menu
  item of its own after Inspector, served by a local `catalog-serve`. Without it the catalog is built and served
  with no Configure part at all; a files project cannot turn it on (it is edited in its files; `validate` V23 names
  it). `make serve [STORE=sqlite] [CONFIGURE=1]` stands the whole thing up on 127.0.0.1, in SQLite from a copy of
  this repository's data. The page: everything a project keeps under `data/` and its settings (arm configs, goals,
  fieldsets, judge scorers, model records, failure-mode lists, `validate.json`) created, edited and deleted there,
  in a form built from each kind's schema: a field per key, the right control for its type, the project's datasets,
  goals and model records suggested; no YAML to type. A setting is saved only after it passes the check (it matches
  its schema, its id is its file name but for an arm config), each problem shown at its field; a save keeps the
  file's comments and every line it does not change (every setting in this repository written back unchanged is the
  same file, and 5,159 one-value edits kept every comment). Harness-written data is shown read-only with the
  command that writes it; a run is deleted whole.
  It is the one catalog page that writes, on this machine only: a public server answers no `/api/data` call. The
  same in the terminal: `evh data-ls`, `data-show [--fields]`, `data-put [--set KEY=VALUE] [--unset KEY]`, `data-rm`.
  A save runs `evh validate` before and after it: what the project's own check newly refuses (a scorer with judges
  of one family, a config naming a goal that does not exist) puts the file back and comes back as the save's
  problems. **Rebuild the catalog** on the page rebuilds the other pages beside the served ones and swaps them in.
  Every kind of setting can be created, changed and deleted through the page alone, so a project in SQLite needs
  no terminal to manage its settings. In SQLite mode it is how a person's settings get into the database without
  `data-migrate`. New dependency:
  `ruamel.yaml` (owner yes, 2026-11-06), which writes a setting back with its comments.
- **`schemas/validate.schema.json`** and **`schemas/goal-policy.schema.json`**: the validate policy's keys and the goal
  policy's `required_from`, written from what `validate` and `goal_policy` read; the data page builds their forms from
  them. A judge's `params.family`, which `judge_score` requires two of, is in the scorer schema.
- **Tests that know when items are related.** `--cluster FIELD` on `pair-test`, `family-test` and
  `bootstrap-test`, and `cluster: FIELD` on a goal's dataset (used by the goal page, `evh goals`, the inspector,
  rounds and `--round`): items that share a value of the field (one thread's comments, one incident's decisions)
  count as one. The sign-flip test flips one sign per cluster, the interval is cluster-robust above 30 clusters,
  the bootstrap draws whole clusters. Tested items one by one, related items made p too small: in a simulation
  of 12 clusters of 5 with no real difference, the item test called 45% of them significant, the cluster test
  4%. `validate` (V14) refuses a goal whose cluster field no item carries.
- **The contender test is shown.** `evh goals` has a column "contender test (within the margin)" (p, its Holm
  threshold, shown or not, or "too few"), `--json` carries it per arm (`noninferior`), the goal page's cell says it,
  and `evh pair-test --margin M` runs it for any one pair.
- **What a goal can detect.** Its decision says the smallest margin a contender could be shown within, with its
  number of candidates and items or clusters (80% power): on ag_news, 29 candidates on 200 items need about 0.10,
  so its 5% (0.048) admits nobody. `axes.quality.reference: baseline` tests contenders against the promoted
  baseline ("no worse than what runs now") instead of the leader.
- **How repeats combine, named.** `success_criteria.primary.reduce` on a goal, and `--reduce` on `pair-test` and
  `family-test`: `mean` (the default, as before), `majority` or `at_least_K` for 0/1 scores (`at_least_1` is
  pass@k's question). The catalog keeps each item's repeats beside their mean.
- **Agreement over every label set, and where people disagree with the reference.** `evh labels --dataset-id D`
  gives Krippendorff's alpha over all the sets together (three or more), with a 95% bootstrap interval (it is
  Krippendorff's 0.743 on his 2011 example); `--contested` lists, per item, how many people's sets agree with the
  gold reference. The pairwise alpha now counts labels in one pass (it compared every pair of labels, 4 × 10^8 at
  10,000 items).
- **Judges: length bias, a 0/1 start, and why a rubric changed.** A judging's `summary.json` gives each judge's
  `length_bias`, Spearman's rho of its score with the output's length in words (the committed judge-summ-v1: 0.23
  and 0.29; judge-summ-v2: 0.02 and 0.21; both summaries re-summarised from their verdicts, $0, nothing else
  changed). The RUNBOOK recommends `scale: [0, 1]` to start a project's own judge. A scorer that replaces another
  says so: `supersedes:` and `why:`, checked by `validate` (V13) and printed by `judge-score`.
- **How an arm fails: failure modes and tags.** A project names its failure modes once
  (`data/failure-modes/<id>.yaml`); `evh inspect --sheet … --fill tags --modes <id>` writes a sheet with a
  `failure_modes:` cell beside each arm's output, `evh sheet-import … --tags <name> --modes <id>` reads it back as a
  tag set (checked against its key, never edited); `evh tags` and the goal page count each arm's modes, and the
  sheet shows each item's in an `<arm>: failure modes` column. `ok`
  marks an output read and found fine; a blank cell was not read. `validate` V21 checks the lists and the sets.

- **A dataset can name its licence.** Optional: `dataset-create --licence ID`, or `evh dataset-describe
  --dataset-id D --licence ID` later (a licence or description change is no new version). `evh licences` lists the
  SPDX ids a line each (`--search`, `--json`, an MCP tool); `unknown` and `LicenseRef-<name>` are allowed;
  `validate` V22 refuses others. The committed Hub datasets carry the licence their Hub page states (2026-11-05):
  ag_news unknown, cnn_dailymail Apache-2.0, dbpedia_14 CC-BY-SA-3.0, few-nerd and scifact CC-BY-SA-4.0, summeval MIT.

- **Where the items came from, the same for every source.** A dataset record has a `source` block: `provider`, `ref`,
  `url`, `revision` (the source's own version), `config`, `split`, `gated`, `description_sha256` and `item_url` (one
  item's page, with `{row}` or `{item_id}`); each item its `source_row`. `dataset-create` reads it from a fetcher's
  `data/sources/<id>.rows.json`; the profile and the catalog link items from the record, no longer from that file.
  `validate` V22 checks it. The committed Hub datasets and their profiles were migrated by `evh dataset-migrate`
  from what their profiles recorded; `revision` and `gated` were never recorded for them and are null.

- **A dataset card.** The datasheet questions, answered in a `card` block under Croissant RAI 1.0's property names
  (`dataUseCases`, `dataCollection`, `dataAnnotationProtocol`, `dataBiases`, `dataLimitations`, …, twenty in all):
  `evh dataset-describe --card-template` prints them with their questions, `--card FILE` records the answers. No new
  version; `validate` V22 checks the keys.

- **Dataset sources: one interface for every place items come from.** `evh dataset-create --source NAME --query
  JSON` reads a source: a class with `describe(query)` (source block, licence, description, card, features) and
  `items(query)`, found as importers are (built-in `folder` and `manifest`, a project's `data/dataset_sources/NAME.py`,
  or `path.py:Class`). Its items are written to `data/sources/<id>/`, never over files already there.

- **A dataset as Croissant 1.1.** `evh dataset-card --dataset-id D --format croissant` writes the record as
  Croissant JSON-LD (licence, version, source url, parent, the card as `rai:` properties, its files with their
  sha256, the items as a record set with typed fields); without `--format` it prints the card as text (also an MCP
  tool). A required property the record cannot give is named, never invented. Not run through `mlcroissant`.
  `--format hf-readme` writes the card as a Hugging Face dataset README.

- **A dataset from a Croissant description.** `--source croissant` reads any Croissant file or URL whose record set is
  columns of one parquet, CSV, JSON or JSON-lines file (its sha256 checked), with the description's licence, version
  (as `source.revision`) and `rai:` card. A FileSet is refused, naming its format: Hugging Face's descriptions keep
  their parquet in one, whose files only the Hub can list.
- **pyarrow is a dependency** (owner, 2026-11-05), to read parquet: `pyarrow>=15`, installed with the harness.

- **A field set proposed from a source.** `evh fieldset-propose --source NAME --query JSON --fieldset-id ID` turns
  the features a source describes into a field set (types mapped, few-valued text proposed as a choice from a
  sample), printed for a person to read; `--write` writes it, never over one that exists.

- **A dataset from the Hugging Face Hub, pinned.** `--source huggingface --query '{"ref", "split", "text", …}'` reads
  the Hub's parquet conversion of a split at one commit (`source.revision`), each file checked against the Hub's
  sha256, with the card's licence and metadata, and each row's viewer page as its link.

- **Publishing a dataset to the Hugging Face Hub.** `evh dataset-publish --to huggingface --query '{"repo": …}'`
  writes a new repo, private by default (items as parquet, the record, the card as README), reads it back by sha256,
  and records where it went on the dataset. Hidden datasets are never published. `huggingface_hub>=0.26` is a new
  dependency (owner, 2026-11-05). Checked live: a private repo published, read back and deleted.

- **Datasets from Zenodo and OpenML.** `--source zenodo` reads a record's table file (md5 checked, the record id as
  revision); `--source openml` reads a dataset's parquet copy with its version and typed features.

- **Datasets from Kaggle, without kagglehub.** `--source kaggle` reads a table file of a dataset's zip at a version
  through Kaggle's own API (public datasets need no credentials), with its licence mapped from Kaggle's name.

- **The examples fetch through the huggingface source.** Their shared reader (`examples/_shared/hf_rows.py`) reads
  each split's parquet conversion at a commit pinned once a fetch, each file sha256-checked, instead of the
  datasets-server's `/rows` (whose 2026-11-02 outage held back a release); the retry ladder, the parquet fallback
  and the fetchers' `--delay` are gone. The rows were checked equal to `/rows` at 21 places across the 8 splits the
  fetchers read, and the 12 committed Hub datasets fetched fresh match every frozen hash and gold checksum. The
  examples cap pyarrow below 26, which refuses the NumPy 1.x they pin on Intel macOS (18.1 to 25.0 checked).

### Changed

- **The paired tests take their normal limit from 10,000 units** (ADR-0028). From 10,000 items (or clusters) the
  sign-flip p is erfc(|z|/sqrt 2) with z = sum d / sqrt(sum d^2), and the contender test's bootstrap-t p is
  1 - Phi(T), instead of 20,000 permutations and 9,999 resamples; a simulation over seven kinds of data
  (`tools/large_sample_check.py`) found them within the resampling's own Monte Carlo error there, and not at 1,000
  to 5,000 for heavy-tailed or sparse data, so below 10,000 nothing changes and no committed result moves.
  `pair-test` and `family-test` say which (`method`: `exact`, `sampled`, `normal limit`, in the text and `--json`;
  `family-test` a `p_method` per row). A p from the limit can be 0.0 (it prints `<0.0001`). A family that mixes
  sizes keeps its other opponents' p's: the one random stream moves past a large opponent as if it were drawn.
- **Every `evh` command keeps the p's it draws** in `<project>/.cache/evh-p.jsonl` (`EVH_P_CACHE`; an empty value
  turns it off), as `evh mcp` did: `goals` right after `catalog` reads them instead of drawing them again (142 s to
  0.4 s on a 1,000-item, 50-arm project).
- **Resampled tests are drawn at once in child processes**: a catalog's, a goal's and a comparison's bootstrap-t's
  and sign-flips are found first, drawn in parallel, and read back, the same p's bit for bit (each is seeded by its
  data or its seed). The 1,000-item, 50-arm project's catalog took 16.3 s instead of 150.4 s, `goals --goal --json`
  12.5 s instead of 147.7 s, with the same JSON and the same pages. Small projects are drawn as before, and so is
  everything in a container under one whole CPU (the quota is read, as `cpus: 0.5` hides it from the core count);
  `EVH_WORKERS` sets the number, `1` turns it off.
- **A dataset page lists 200 items a page**, the rest on pages beside it (`d/<dataset>~items-2.html`, ...): the
  10,000-item page was 13.8 MB, now 0.32 MB. The page's filter reads its own page; `evh dataset-items` lists all.
- **The agent skills put a setting in with `evh data-put` and read one with `evh data-show --text`**, in a
  temporary folder, so they work in either store and never touch a folder of the project's own.
- **A run's outputs are one file** (RFC-024). `outputs.jsonl`, a line per item (`item_id`, `text`, `sha256`),
  appended as each output is produced and rewritten in dataset order when the run completes, replaces the `outputs/`
  folder of one file per item. Re-scores, judgings and sheet imports no longer copy their source's outputs: they read
  them through `derived.from`. Every module reads outputs through one function. `evh run-migrate` moves a project's
  runs (`--dry-run` first); in this repository it turned 94,796 files into 305 (`harness/data/` from 106,492 files
  to 12,001), every output and V5 signature checked equal before and after. A derived run records its source's
  directory (`derived.from_dir`) and reads only that run; `validate` V23 names a run left in the old layout or a
  derived run whose source is gone. A resume from a run that kept no row checkpoint no longer crashes (`_Resumed`
  read `_extra` from an empty row).

- **A dataset's version means something.** `version` is MAJOR.MINOR, two integers (1.10 follows 1.9), computed from
  the lineage when the dataset is made: 1.0 for a first dataset and for each side of a split (which names its
  parent's version, `split.from_version`); from a parent (`--from`, `dataset-extend`), MINOR + 1 when items were only
  added, MAJOR + 1 and MINOR 0 when any was removed or changed. A licence or description change is no new version.
  `validate` (V22) recomputes it; `evh dataset-migrate` writes it for records made before (every committed dataset
  is 1.0 by the rule, as it was). Neither key is in a run's fingerprint: no run moves.

- **One failed item no longer stops a run** (owner, 2026-11-05). An item whose call fails (not transiently) is
  scored as an empty answer (0 on most measures, or the adapter's `score_failure(reference)`), marked `failed` on its
  row, listed in metrics.json's `failed_items`, and called again by `--resume`; the run goes on. A 429 or a timeout
  that outlasts the retries now stops the run with `75` like an unreachable server (it used to end in a traceback),
  and more than 5 failures that are also over 20% of the items called stop it with `ERROR (failed)`.
- **A contender is shown no worse than the leader** ([ADR-0026](../docs/adr/ADR-0026-contenders-by-non-inferiority.md)).
  It had to be "not significantly different", which more arms are the fewer items there are, and `frugal` then
  recommended the cheapest. Now a one-sided non-inferiority test against the leader decides, Holm across the
  candidates: Tango's score test for 0/1 scores at any size, the bootstrap-t from 100 items or clusters for other
  scores, "too few items to call a tie" below. A strategy is a default margin: `balanced` 5% of the leader (was 2%,
  with the old test), `frugal` 10% (had none), `quality_first` the same quality; a goal's `axes.quality.margin`
  wins, and `validate` notes each goal on a default. **Recommendations move** on goals whose contenders the old
  rule over- or under-counted: on this repository's 7 goals, scifact recommends deepseek_s (was the free e5_base, not
  shown within 10% once 18 arms are corrected for), ag_news bert_base_ta and triage its leader (both were undecided).
- **Each exit code has one meaning** ([RUNBOOK, Exit codes](docs/RUNBOOK.md#exit-codes)). The cost cap that stops
  `evh run` or `judge-score` early exits `4` (was `2`, which is also a usage error); a run that measured nothing
  exits `7` (was `1`, which is also a refusal); a server that could not be reached exits `75` (was `1`); a check
  that ran and found problems exits `6` (was `1`): `validate`, `self-test`, `env-check`, `importer-check`,
  `arm-smoke`, `model-onboard`, `deploy-sheet --capture`; a `sweep` in which some runs failed exits `5` (was `1`).
  `evh` exits `70` for an error nothing caught (a traceback) and `130` on Ctrl-C, without a traceback.
- **Every refusal names its kind:** `ERROR (<kind>): <why>`, the kind one of twelve
  ([RUNBOOK, Refusals](docs/RUNBOOK.md#refusals)): `not-found`, `bad-argument`, `would-overwrite`, `mismatch`,
  `invalid-file`, `not-materialized`, `not-enough`, `not-public`, `not-allowed`, `not-configured`, `failed`,
  `missing-dependency`. A script or an agent reads the kind, which stays when a message is reworded. The
  project's `AGENTS.md` (`evh init`) says what to do for each exit code and the common kinds.

### Fixed

- **A judge that runs out of `max_tokens` is stopped after 3 calls, not after the whole pass.** A reasoning judge
  that spends its tokens thinking replies with nothing, every time; judge-score said so only at the end, after every
  call was paid for (the 0.7.1 newcomer run: tutorial 3's judge at 400 tokens). Now a judge whose first 3 replies all
  come back empty at the token limit stops the pass (`STOPPED EARLY`), keeps what it stored, and prints the hint.
- **The newcomer scenario and tutorial 3 commit what judging writes** (`data/runs-silver`, `data/judging-sets`,
  `data/judge-verdicts`, `data/runs-judged`), which they left untracked.
- **The inspector opens on large comparisons.** At 10,000 items and 40 arms it never showed its verdicts: its charts
  took the least and greatest of 400,000 values with `Math.min(...values)`, which overflows the call stack. Past
  500 items a run its charts now draw shaded bins instead of a dot each (they were 1.2 million dots), and its
  per-item table draws only the rows it shows (10, then more on request; "show all" up to 1,000 items), where it
  drew all of them and hid the rest (3.2 million elements). Found measuring S3 in a browser.
- **The catalog's pages are the same whatever the process's hash seed.** The arms page's per-config rows came out in
  another order every build, and on the models page a model's best rank, when two of its configs tied, could come
  from either: both iterated a set. Found comparing two builds of one project; a test now builds under six seeds.
- **A goal's dataset notes with a comma were cut short.** `notes: first 200 test rows, all CNN; ...` inside a
  `{...}` entry is YAML for `notes: first 200 test rows` and a stray key; seven goals (the tutorial's among them)
  showed half a note on their pages. The notes are quoted, and the goal schema now refuses a key a dataset entry
  does not have (`validate` V14 names it). Found by the data page's round trip.
- **A release cuts a hidden dataset's judged and re-scored runs too.** The deployment's copy decided "hidden" for
  each folder directly under `data/runs*`, so a run a level deeper (`runs-judged/<scorer>/<run>`,
  `runs-rescored/<scorer>/<source>/<run>`) on a hidden dataset was copied whole, its rows' `_meta` (which a judging
  carries over from the source row) included. Each run is now decided by its own dataset. This repository has no
  hidden dataset, so its published catalog never carried any.
- **`evh <command> --help` names the command.** 43 of the 67 commands printed the script behind them
  (`evh run-promote --help` said `usage: promote_baseline.py`).
- **`evh validate` survives a file that does not parse.** A dataset, run, baseline or capture that is not valid
  JSON is named by V1, and every later check runs; before, the first check to read it ended `validate` in a
  traceback. A reference manifest, capture record or label set that does not parse is named by its own check.
- **A cancelled MCP call stops its command.** The server waited for the command to finish, so a call a client
  gave up on kept running to its timeout and held one of the server's slots.

## 0.7.2 — 2026-11-04

The public MCP server's answers written ahead were empty. From 0.6.2 to 0.7.1 its `goals`, `datasets`, `arms`,
`models`, `references` and `runs-list` answered as if the project held nothing, and 0.7.1's leaderboards written
ahead were never written. A project's own server (`evh mcp` without `--answers`) and every command were not
affected. No result moves.

### Fixed

- **Answers written ahead are answered from the project's data.** `evh mcp --write-answers` runs each command
  inside the project; the deployment passed `EVAL_HOME` as a relative path (`_release/inspector`), which each
  command read from inside the project, where there is no such folder. A relative `EVAL_HOME` or `EVH_P_CACHE` is
  now made absolute from where the caller stands before the command runs.
- **A broken write is no longer silent.** `--write-answers` names what it could not write (a dataset with no runs,
  an answer too large, or a call that failed with its error) and exits non-zero when a call failed; the
  deployment's render also refuses answers whose `goals` do not list the release's goals, or that hold no
  leaderboard.

## 0.7.1 — 2026-11-04

Fixes from the fifth newcomer scenario (the first on a release, 0.7.0) and from releasing 0.7.0. A judge that
returns empty replies no longer leaves a tree that fails `evh validate`; the commands say more about what they
did and what they spent; the public MCP server answers a leaderboard at once. No committed run's scores move;
three figures read differently (**Changed**).

### Changed

- **`family-test --round` tests the round's leader against every other arm in play**, without `--a` and
  `--against` (as `pair-test --round` picks its pair), and reads a re-score in place of the run it re-read, as the
  round does. A family test of a round can give a different p than 0.7.0's runs-only read.
- **The billed figure counts arm smokes.** `evh overview`'s billed tile and the catalog's include what
  `evh arm-smoke` spent (recorded in the model records), and the spend lists name it as "arm smokes".
- **`runs-list --baselines` shows the baseline's mean over its repeats**, as every other view does; `--json`
  `scores` is that mean and a `repeats` column says over how many.
- **`--json` fields:** the leaderboard's frontier gains `dominated_by`; `evh goals --goal`'s last column is named
  `decision` (it was `""`); the dry run gains `input_tokens_counts`; `arm-smoke` has `--json`.

### Fixed

- **An empty judge reply is withheld like any other unparsed reply.** A reasoning judge that spent its whole
  `max_tokens` thinking returned nothing; `judge-score` stored it as text and `evh validate`'s V12 then failed on
  the harness's own record. Now it is withheld (its hash kept), V12 names the command that rewrites one stored
  before 0.7.1 (`evh judge-score … --retry-unparsed`), each unparsed reply says why (empty, cut off at the token
  limit, not JSON, not the expected shape), a pass whose replies were cut off ends with a `HINT` (raise
  `max_tokens`, or `reasoning: {enabled: false}`), and its progress lines arrive as they happen through a pipe.
- **`evh arm-smoke`** prints each reply (its first 300 characters; `--replies` for all) and what it spent, and
  times a call that the adapter did not time.
- **`evh run`** says whether "spent" is the provider's bill or the config's price table, prints no "warmed up in
  0ms" for an arm with nothing to load, and counts the config's prompt in the dry run's input estimate.
- **`rescore`** ends with a whole sentence that says when a re-score stands in for a run, and warns about outputs
  cut off at `max_tokens`. **`score-preview`** says when a goal holds no measured run to re-score.
- **`silver-calibrate`** says what `--ref-match` and `--arm-match` take, with an example from your runs.
- **Leaderboards fit the terminal** (the ranking metric first, the rest named; `--wide` for every column), and
  "dominated" says what it means (as good on all three, better on at least one) and by which arm.
- **`inspect`** shows a model name whole in its conditions, and `--round` names the round's leader as such;
  **`evh goals --goal`**'s headers line up; **`cost-report`** names each repeat; **`evh rounds`** prints a round's
  conclusion whole.
- **The catalog and the inspector:** the inspector names the silver reference's author and marks its row; an
  item's cards show each arm's score; a goal page's "test every arm against its leader" leaves out retired arms;
  a judged group below the goal's `min_items` says so; a recommended dataset id may break, so the goals table
  fits; home tiles keep their number on one line at 1400 px.
- **The public MCP server answers `leaderboard` for each dataset at once:** `evh mcp --write-answers` writes it
  ahead per dataset, and the leaderboard's permutation test is kept in the p cache (`EVH_P_CACHE`) with the
  generator state the rank intervals draw on, so every number is the same. A first call took 47-60 s.
- **The website's on-this-page line** names each section in a word or two and leaves out "Who built this".
- **Deploys and CI:** the release renders while CI runs, and the site's build check runs beside `verify`.
- **Docs:** tutorial 3 shows the whole judge scorer and what to do when a reasoning judge returns nothing;
  tutorial 5 lists the inspector's URL parameters; the RUNBOOK has a complete goal file; the newcomer scenario
  smokes each arm first, says what each step writes (all committed), and seeds pip in a `uv venv`.

## 0.7.0 — 2026-11-04

Agents as users. `evh init` writes an `AGENTS.md`, three skills teach the loop, and the ranking and the tests answer
in `--json`, so an agent with a shell needs neither the catalog nor MCP. The features and fixes the first beta
agents asked for are in, among them crosstabs of per-item scores, a hypothesis recorded before a run, `pair-test`
across two versions of a dataset, and `capture-restore`. Upgrading can change a verdict: a leader the tool picked
is now corrected for the pick, and a round no longer promotes on a tie (**Changed**). No committed run's scores or
fingerprint move.

### Changed

- **A leader the tool picked is corrected for the pick.** `pair-test --round` takes A from the table, so its p is
  Bonferroni-corrected for the comparisons A could have been (every arm in play but B); a round's promotion gate
  corrects the same way (p × K over the round's arms). A verdict that was significant uncorrected can read
  not significant. A pair you name yourself is unchanged, and still uncorrected.
- **A round promotes nothing when its leader is tied, or its arms were scored differently.** Before, it promoted
  the first of the tied arms. The hold names the arms and says how to break the tie (the goal's tie-break picks
  among them; `evh goals --goal` names the arm it recommends). A closed round suggests nothing.
- **A round's baseline is read re-scored.** It was read as first scored, so the rule "a leader must beat the
  baseline" did not run on re-scored rounds; it does now, and can hold a promotion it let through.
- **The leaderboard's JSON lists no distinguishable pairs without an arm effect.** Pairs are read only after the
  global (Friedman) test finds one: without it, `pairwise_valid` is false and `distinguishable_pairs` is empty.
- **`dataset-from-capture --from` replaces an item with the capture's record of the same id**, counted as changed
  in the lineage. Before, the earlier version's body was kept and the lineage read "0 changed". **`--fieldset`
  alone keeps every field it declares**; before, it kept none without `--field`.
- **A run is never written into another run's directory.** A run id is the config and the start time to the
  second, so two runs of one config started in the same second shared a directory and the second wrote over the
  first, a committed run included. The second now takes the next second's id; `--run-id` naming an existing run
  is refused.
- **`evh run --dry-run` no longer calls its estimate an upper bound.** It counts one call per item, or an adapter's
  `CALLS_PER_ITEM`, and says more calls or a growing conversation cost more. Where the model record has an
  arm-smoke of the config, it shows the measured cost per item projected over the run. `--json` adds
  `estimate_is_upper_bound: false`, `calls_per_item` and `measured_usd_per_item`.

### Added

- **`AGENTS.md` (and `CLAUDE.md` importing it) in every new project** from `evh init`: the rules an agent must not
  break, the loop from nothing to a decision, the `--json` command for each question, and what an agent may do
  (run arms, label and promote when its operator asked, under `EVAL_MAX_COST_USD`; closing a round stays the
  operator's).
- **Three skills, and `evh skills-install`**: `evh-evaluate-a-system`, `evh-compare-and-read` and
  `evh-promote-with-evidence`, shipped with the package and copied into `.claude/skills/` (or `--target`). Every
  `evh` block in them runs as written in the tests.
- **`--json` on `leaderboard`, `pair-test`, `family-test`, `run-compare`, `rank-stability`, `runs-list` and
  `rounds`**: one envelope, `{"command", "version", "result": {"blocks", "values"}}`, with raw numbers. The text
  output is unchanged. `evh run` prints each run id it wrote (`values.runs` under `--json`), and its progress as
  one `[n/N] item outcome seconds` line per item while it runs (on stderr under `--json`).
- **Five more MCP tools**: `leaderboard`, `pair-test`, `family-test`, `rank-stability` and `run-compare` (23 tools,
  22 with `--public`).
- **A hypothesis recorded before the run** ([ADR-0025](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0025-a-hypothesis-lives-in-the-arm-config.md)):
  a `hypothesis:` block in an arm config (which way, against which arm, on which measure) is recorded in each run
  with whether it was committed before the run. `pair-test` and `evh goals --goal` show it; an arm with runs made
  before it reads "not named in advance". `evh validate` V20 checks it. Not in the fingerprint.
- **`evh inspect --runs … --crosstab A,B [--group FIELD [--group-match RE]]`**: two per-item scores crossed, per
  value of a field of the run's prediction rows, the items off the diagonal named. **`--items-out`**: each run's
  whole output and scores beside the reference and labels (`--disagree`: only the items the runs decided
  differently).
- **`evh goals --goal G --arms PATTERNS --top N`**: the rows shown filtered; the decision is still made over every
  arm, and the baseline, the leader and the recommended arm are always shown. Each row has its paired test
  against the leader.
- **`pair-test --b-dataset D2`**: one arm on two versions of a dataset, paired by item id. Refused unless the
  reference is the same text for each shared item; it says it is cross-version, what that establishes and what
  not, and names the runs of each side (`run_ids_a`, `run_ids_b`).
- **`evh capture-restore --capture C [--query KEY=VALUE]`**: a capture's records, and the item files of every
  dataset made from it, read again from the recorded importer and query (a key replaced, e.g. the same files in a
  download folder), a recorded scrubber run again; every record and item must match its recorded sha256, or
  nothing is written.

- **The triage example's v2** (`orrery_triage_v1_labelled_v2`): the same 65 owner-labelled decisions with the
  rebuild's hindsight taken out (probe answers that stated an outcome, release and last-seen times after the
  decision), as revision `v2` of the dataset on Hugging Face; `examples/triage-fleet/fetch.py --revision v2`
  restores it. Round r4 of `triage_orrery` runs on it.

### Fixed

- **An importer path in a capture works from the project root** as well as from the directory it was given in.
- **The triage example's fetch restores its capture again**: the importer's newer fields come only when the query
  asks (`prompt_fields`, `v2_fields`), so a past capture's records hash as recorded.
- **`evh inspect --items` is no longer read as `--items-out`**, and `--crosstab` refuses a name that is not a
  per-item score, pointing at `--group`.
- **A label set is written whole or not at all**: to a temporary folder renamed into place.
- **`pair-test --b-dataset`** refuses a measure stored only in re-scored runs as a missing metric (naming
  `evh rescore`), not as "no shared items".
- `family-test --against` takes a list; `--family` below 1 is refused; a mixed family's `n` is its range; a goal's
  `--goal` cannot name a file outside `data/rounds`; `round-open --keep`'s help says it accepts any arm already run.

## 0.6.2 — 2026-11-03

Faster answers from `evh` and its MCP server. No result moves.

### Added

- **`evh mcp --write-answers FILE` and `evh mcp --public --answers FILE`: a release's answers written ahead.** Each
  call to the MCP server runs a fresh `evh` process, several seconds of CPU; a deployment that limits the server's CPU
  pays it in tens of seconds (the evals server's first `goals` after each start, and after each hour, took 33 s at
  half a core). `--write-answers` writes the answer of every tool that takes no argument and does not depend on the
  date (not `overview` or `activity`); a public server started with `--answers` serves them without running the
  command, for as long as it runs. A line another harness version wrote is not read.

### Fixed

- **A view and a catalog build read each arm's scores once.** `evh goals` read 1,054 arms' scores for 686 arms; that
  reading was 79% of its CPU. The answers are byte for byte the same; `goals`, `arms` and `models` take about a
  quarter to a third less CPU.

## 0.6.1 — 2026-11-03

Fixes to 0.6.0, from two reviews of what it shows. Six can move a number or a verdict a project sees (Changed): the
sheet's win rates and verdicts, a goal's recommendation and the places in its field, and the catalog's run and
spend figures. One keeps a hidden dataset's labels and notes off public surfaces (Security). The rest restore what
0.6.0 documented or make the catalog say what a number means beside it (Fixed).

### Changed

- **A goal recommends from the group it decides on, once per dataset.** A judged group (a grade, a pick, a pairwise
  pass) or another measure of a scorer is shown with its leader, never recommended: 0.6.0's CNN goal page printed
  four "Recommended:" verdicts, three of them from judging passes the goal does not decide on.
- **A goal's field places one arm per config, without the arms a round retired** (a re-timing, a second run, a
  paired side run). A config run twice took two places: AG News `anthropic_l` read "#8 of 33" in the catalog where
  the site reads 5th of 30, and the Models page put Gemma 4 31B first on SummEval through its paired side run.
- **Runs re-scored or re-parsed in place count in every period figure**, dated when they were measured: 0.6.0 left
  Few-NERD's and SciFact's 54 runs and $5.58 out of the activity, the datasets page and the home tiles. A copied
  re-score (judged, re-scored, silver, adjudicated) keeps its run's id too and is still never counted.
- **The sheet's verdict compares only the arms scored on the metric**: an arm with no score on it reads "no <metric>
  in this run", where 0.6.0 named the other arm the leader and recommended.

- **The sheet's win rate on a pick or pairwise verdict is each arm's share of what the judge gave** over the rows it
  judged (its `judge_won`), so with every arm shown it is the judging pass's own win rate. 0.6.0 gave a shown arm a
  whole row when it held the largest share among the arms shown, however small: on the CNN pick pass `anthropic_l`
  read 0.646 in the sheet against the pass's 0.402.
- **The sheet's win rate on a metric is over the rows each arm was scored on**, "—" for an arm scored on none. 0.6.0
  divided by every row with a winner, so an arm with no value on a row counted as beaten there, and one never scored
  read 0.000.

### Security

- **A hidden dataset's labels and notes stay off public surfaces** (RFC-019 §4: per-item labels, adjudication notes).
  0.6.0 showed its label sets' confusion matrices, whose rows and columns are the label values, on the catalog's
  dataset page and in a public server's `labels`; listed a person's sheet notes on its items in a public server's
  `labels`; and copied those notes into a deployment's data. The counts, Cohen's kappa and Krippendorff's alpha stay.

### Fixed

- **The installed `evh` reads the project's `.env`.** 0.6.0's `evh`, as pip installs it, loaded none (`env-check`:
  "loaded 0 var(s)"), so a key or a cost cap put there was not in force; `python -m evaluation_harness` and a
  checkout were unaffected. Found by the newcomer scenario.
- **`reference-promote` adopting a hand-made folder keeps its files' bytes.** It added a newline to each, so the
  reference digest every run scored against the folder had recorded no longer matched (`rescore` warned the
  reference had changed), where UPGRADING said no run's reference moves.
- **Fetching the examples' public data falls back to the Hub's parquet files** when the Hugging Face
  datasets-server's `/rows` keeps failing (its outage of 2026-11-02 answered HTTP 503 for every dataset): the same
  rows and row numbers, read with `pyarrow`, now in each example's environment; every item is still checked against
  the frozen dataset. The installed harness does not depend on it.
- **`inspect --sheet --wrong-against NAME` refuses a name two datasets' sets share** on this dataset's items (labels
  follow an item into every dataset holding it), naming each as DATASET/SET; it read whichever it found first.
- **A round's best is read as its goal decides**: on the deciding reference, never the arm that wrote it (CNN round
  r1's best read `anthropic_l` 1.000, the silver's author scored against itself, beside a conclusion naming `bart_l`).
- **Gold reference sets are dated by when their labels came to be**: the dataset's freeze, or the adjudication. The
  0.4.0 migration had stamped every one with its own time, so the references page listed sets a month old as new.
  No run's reference digest moves (the digest leaves the date out).
- **`evh deploy-sheet` and the goal page say a key production never recorded "cannot be checked"**, where they read
  "prompt_sha 0 match; not recorded: 233".
- **The catalog says each thing once, and what a number means beside it.** A goal page names a re-score's scorer
  once, counts a long list of contenders, folds a conclusion its answer already shows, and explains its groups and
  strategy once. Dataset pages open on the deciding measure, give one inspect button per judging pass, name the
  machine in one form ("served on", "run on"), say how much of a period's spend was judging, and show a rise past
  doubling as a multiple. The answer column no longer scrolls off at 1280 px; chart names never overlap; a cost every
  arm shares draws no axis; a metric's strip leaves out the arm scored against what it wrote; ids break between
  words at phone width; the sheet's rows stay short and name arms by what sets them apart; probes read yes or no.
  The triage datasets and `fleet_dedup_v1` have their profiles (`evh dataset-profile`).
- Site: SciFact leads with the compared field (the best reranker +0.025, not significant) and names the extra
  +0.07 run with its caveats; the method page describes fingerprint v5 with 0.6.0's own `run-compare` output; the
  use page counts its steps; the XSum control's caveat and the judging spend's passes are carried where they are
  quoted.
- Docs: tutorial 5 and the RUNBOOK named the old fixed ports (8765, 8766) where 0.6.0 gives each project its own;
  the home page's MCP section names what 0.6.0 added and that the public server never answers with an item's text.

## 0.6.0 — 2026-11-02

What you get: datasets made from what production did (capture, scrub, split, `dataset-from-capture`); labels that say
who decided what is right, and reference sets promoted from them; production's own decisions scored as an arm;
models onboarded before they are run; scoring that evolves without re-running an arm; judges that grade, pick the
best or compare two; and one sheet of every item and arm, filled in Excel or another tool and read back. Upgrading
moves no committed score. Two formats (fingerprint v5, model records) and the old references are migrated by a
command, and a few names change to the field's words with no alias (`evh run`, `significant`, `contenders`):
[UPGRADING](https://github.com/chipi/eval-harness/blob/main/harness/docs/UPGRADING.md) has the steps.

### Added

- **Labels, and the reference sets promoted from them** (RFC-023, PRD-002, ADR-0022). A **label** says what is right
  for one item and who said it: a `person`, a `model` or a `rule`. Labels come in **sets**, never edited, under
  `data/labels/<dataset>/<set>/`, and follow an item by its sha256 into any dataset holding the same bytes.
  - **`evh label-from-run`**: a finished run's outputs as a model's labels, no calls, the refusals a reference's
    provenance needs (a dirty or unknown build, an unfinished or derived run, an empty output, one cut off at
    `max_tokens` unless `--allow-cut-off`). **`--not-redistributed`** keeps the texts out of git (a `.gitignore` beside
    them) and records the command that rebuilds them, checked against the set's checksums.
  - **`evh label-sheet`** writes a sheet of the items to label (unlabelled, all, where runs disagree, or chosen),
    each run's decision and a proposal beside an empty label; **`evh label-import`** reads it back, or a folder of
    `<item_id>.txt`, as a person's set (`yes` takes the proposal; notes kept). The sheet is CSV that Excel opens
    and saves (UTF-8 with its mark, `,` or `;`); **`--choices`** puts the allowed answers in the label column's
    header and the import refuses any other; the local inspector downloads it. **`evh label-from-capture`** turns a
    capture's recorded outcomes into a `rule` set by the rules `reference-from-outcomes` read. **`evh labels`** lists
    the sets, what each covers and how two agree: the same answers, sharing one, Cohen's kappa, Krippendorff's
    alpha and (`--confusion`) the confusion matrix; free-text labels are not compared as text (an MCP tool).
    **V19** checks every set.
  - **A label can accept more than one answer**, when several are right for an item: `{"accept": ["escalate",
    "file"]}`, sorted and without repeats, made by the sheet's `also right` column, a rule's `label: [file,
    escalate]` or a folder's text, shown "escalate or file". A decision is wrong against a label when it is none of
    them; two labels agree only when they accept the same answers. An adapter's `score` reads a reference with
    **`answers(reference)`** (`evaluation_harness.adapter`); the bundled one keeps the best overlap. The triage gold's
    23 `file-or-escalate` labels (and their reference) are written so now, by `labels_from_verdicts.py` byte for byte:
    every one of the 18,460 item scores of the 284 runs against it is the same replayed old and new. The outcome
    rules give the same two answers, so gold and the rules accept the same answers on 34 of the 34 items both label
    (kappa 1.00).
  - **`evh reference-promote`** makes a reference set of a label set, at the tier you choose, with a reason and who promoted
    it; the manifest records where it came from (for a model's set, the run and model that wrote it). No rule ties
    the tier to the source. Every existing reference set records how it was promoted (20 here; 6 copied byte for byte
    into label sets, 209 labels), every run's fingerprint unchanged.
  - **Scoring against a label set without promoting it**: `evh rescore --labels SET`, `evh run --labels
    SET`. The run records `reference_id: labels/<dataset>/<set>` and lands in `data/runs-labels-<dataset>-<set>/`, an
    arm of its own; a goal groups such arms under the set, the arm that made a model's labels flagged.
  - The catalog: a tier is a **pill** in its own colour, a label set a **source chip**, wherever either is named; a
    **Labels** page; a dataset's label sets and how often two agree; where each reference set was promoted from.
- **Evaluating what production did** (RFC-023, PRD-014, ADR-0023). A capture's decisions are evaluated against
  labels; the governed datasets grow only by a version you make:
  - **`evh arm-from-capture`** makes production's recorded decisions an arm (`provider: recorded`): each output the
    capture's record of the same id, read by the adapter's **`recorded_output(record)`** (else `--field`), scored,
    tested and compared like any arm, cost 0. The catalog badges it `recorded`, its cost and speed "recorded, no
    call".
  - **Agreement**: the adapter's **`same(a, b)`** says when two outputs are one decision (default: the same text;
    the triage adapter compares dispositions). **`evh inspect --disagree`** and the inspector's "only where they
    disagree" keep the items where the arms decided differently; `label-sheet --items disagree` reads the same hook.
  - **The sheet**, `evh inspect --sheet --dataset-id D --runs A,B,…` and the inspector's **05 sheet** (the dataset
    page's "Open its sheet"): the items down, a column per arm across with what it wrote and every score it has
    (its run's metrics, and a judging pass's where one covered the run; `--metric M` or `SCORER/M` chooses the one it
    is read on; `--scores-only` leaves the outputs out), every label set and reference set, the winner per item (on
    that metric, and per pick or pairwise judge), the signals **wrong** (`--wrong-against SET`), **disagree**,
    **split**, **new** (`--new-vs D`: a field value it never had), **unlabelled**, each a filter beside `--where` and
    `--by`, and a footer per arm: its mean, its win rate and its verdict (the goal's decision, else the paired test
    against the leader). On a pick or pairwise verdict only an arm the judge preferred wins a row; a row it gave to
    an arm not shown is nobody's win. The item column stays in place as the arms scroll; the rows you tick give the `evh pick`
    and `evh label-sheet` commands. `--csv FILE` writes it (UTF-8 with the mark Excel needs), and the inspector
    downloads the same (`/api/sheet`, `&format=csv`). Local only: a public server refuses it.
  - **A sheet to fill, and `evh sheet-import`** (`make sheet-import`): `--csv FILE --fill label` adds `label`, `also
    right` and `note` (`--choices`); `--fill pick` or `scores` writes the outputs as blind columns A, B, C… shuffled
    per row (`--seed`), a `pick` or a `score: X` column per output (`--scale LO..HI`), the rubric as the first row
    (`#rubric`; `--rubric FILE`) and its key beside the sheet (`sheet.key.json`). `evh sheet-import FILE --dataset-id
    D --by WHO` reads back what was filled: labels as a label set (`--set`, `--kind person|model`), picks or scores
    as judged runs under `data/runs-judged/<scorer>/` (`--scorer`), `judge_won_unvalidated` or
    `judge_score_unvalidated` per arm per item, through the key. A row or text the key does not have, a letter not on
    its row, a score off the scale and a name already used are refused, with nothing written.
  - **Picks**: `evh pick` marks a production item for the next version of one or more governed datasets (targets,
    tags, a note) in `data/picks.jsonl`, append-only; **`evh picks`** lists what waits (an MCP tool), and the target
    dataset's page shows them with a box per row. **`evh dataset-extend V1 --dataset-id V2 --picks`** (or `--pick`)
    makes V2 of V1's items and the picks chosen, each checked against the bytes picked, `extended_from` recorded;
    labels follow the items; nothing is promoted.
  - **`evh deploy-sheet --config ARM [--capture C]`**: what production must match to run what you promoted (the
    model, its record and deployment, every setting sent and a record's setting that was not, what each item
    reported, the adapter), and with a capture, whether each record says production ran it (the adapter's
    **`production_ran(record)`**); exit 1 unless every record matches. On the promoted arm's page, and folded beside a
    goal's baseline. The triage importer keeps the ledger's `prompt_ver` and `prompt_sha`.
- **Several projects on one machine** (ADR-0024): `catalog-serve` and `mcp --http` take a port of the project's own
  (18000–18999, 19000–19999), the same every time, the next free one if taken; a local catalog names its project;
  every command notes a stray `EVAL_HOME`; a model record's lock is keyed by the record.
- **Datasets from production: the capture lane** (RFC-019, PRD-014, ADR-0019). A project keeps what a
  production system did as a **capture**, then makes datasets and labels from it:
  - **`evh capture`** reads records through an **importer** (`--importer jsonl|tsv|github|langfuse`, or a
    project's own `path.py:Class`) into `data/captures/<id>/`: each record's id, body, fields, time, source
    and outcome, hashed one by one (`capture.json`); `--since-capture` continues from an earlier capture.
    **`evh importer-check`** tests an importer against the contract, including that it keeps to `since` and
    `until`; **`evh captures`** lists them, and the catalog's **Captures** page shows them with the datasets made
    from each. A capture keeps the window it records: a record outside it is named and nothing is written
    (`--late` keeps the ones older than `since` that the earlier capture never saw). Newer outcomes of the same
    records are a fresh capture, labelled with `label-from-capture --capture` (tutorial 6 §5).
  - **`evh capture-scrub`** runs a project's own scrubber over a capture's records and re-hashes the ones
    it changed, keeping their earlier hashes.
  - **`evh capture --sample-rate R --seed S`** keeps a share of the records, by a hash of each id, as they are
    read: the same rule draws the same records again, an importer may sample at the source, and a continued
    capture keeps the rule.
  - **`evh dataset-from-capture`** freezes a selection (`--where`, `--dedup`, `--one-per`),
    typed fields from a field set, and `--tag K=V` labels; only the body becomes the item.
  - What happened afterwards becomes labels by a small rule set (`when`, `unless`, `exists`, `absent`, `range`,
    `min_age_days`): `evh label-from-capture`, above.
  - **`evh dataset-split`** makes `<D>_validation` and `<D>_test` by hash (stable across versions, a group
    kept whole with `--key`) or by time.
  - **V17** checks every capture's records against their hashes; a capture whose records a project keeps
    out of git (fetched from where it publishes them) is named as not fetched, not failed.
- **`text: hidden` on a dataset**: none of its text, nor anything derived from it, on any public surface:
  the catalog's pages, the inspector and `evh mcp` in public mode, and a deployment's copy of the data
  (`_release.py copy-data`, which also refuses a release carrying reference texts or run outputs git does
  not track). `dataset-from-capture --hide-text` sets it.
- **Dataset tags on the views**: the catalog's datasets page groups by each tag key and shows where a
  dataset came from (a capture and its selection); **`evh datasets --tag K=V`** filters the same way.
- **Two examples from a production fleet**: `examples/triage-fleet/` (an agent's real triage decisions,
  replayed through its own code; the operator's verdicts as gold; the model's own decision scored beside
  the fleet's, before and after its gates) and `examples/signal-fleet-dedup/` (a regression guard for the
  fleet's de-duplication functions; no model). Their data is published on Hugging Face and fetched by a
  pinned revision.
- **A share card on every catalog page**: its title and its opening line as `description`, `og:*` and
  `twitter:card`, and with **`evh catalog --card URL`** the image a shared link shows. The pages stay
  `noindex`.
- **Onboarding models, once, for every eval** (RFC-020). A project keeps a **model record** per model,
  `data/models/<model_id>.yaml`: its aliases, weights and licence, what it can do, the settings that hold
  whatever the task (`reasoning_effort`; device, precision, batch size for an ML model) with why, its history,
  and its **deployments** (each place and build it runs: machine or host, server and version, digest, revision
  or hash, the route for a hosted one), each onboarded on its own.
  - **`evh model-onboard <id> --deployment <d>`** probes an LLM through the deployment's endpoint: the digest the
    server reports, whether it reasons at the default and with the record's settings, JSON, determinism and
    speed (the deployment's, not the record's); a different build than the record's is flagged and kept in its
    history. An ML model or a baseline through an arm (`--config`). `ONBOARD PASS` or `ONBOARD CHECK`.
  - **`evh arm-smoke --config <arm>`** runs any arm on a few items before its full run and writes no run: runs,
    valid output for the scorer, a projection of the full run's time and cost, build pinned, determinism; for an
    LLM every model call (reasoning, slow, long, cut off, no answer, from a provider's `_meta` or an adapter's
    `meta["calls"]`; a reply is long past half the arm's reply cap, or with no cap against the arm's own median,
    so neither a summarising arm nor an agent's short probe calls beside its answers make a long reply).
    `SMOKE PASS` or `SMOKE CHECK`, written into the record.
  - An arm names a record and a deployment (**`model_record:`**, **`deployment:`**): the record's settings go under
    its params, which add the task's own (its reply cap, its call limit: a record refuses them, since they would
    reach every other eval's arms); the run records both. **V18** checks the records, and the arm configs in `data/configs` and those validate.json's `configs` globs name; `validate` notes an arm never smoked, a
    reasoning model with no `max_tokens`, a tag that is a different build on two deployments.
  - The catalog's **Models** page and a page per model, a smoke badge on the arms page, a models tile; **`evh
    models`** for the same (and over `evh mcp`). A model is *vetted* when an arm that names it passed its smoke;
    its onboarding alone makes it *onboarded*.
- **Scoring that evolves** (RFC-022). A round records the scorer it is judged by, and a scoring change is a
  step of its own:
  - **`evh score-preview --goal G [--round rN]`** re-scores the goal's arms (or the round's) with the scorer in
    the working tree, in a temporary directory, and prints each arm before and after and the decision before
    and after; it writes nothing and spends nothing.
  - **`evh rescore --goal G --round rN --why "…"`** re-scores a round's arms; the round records the change
    (`scoring`: when, the scorer, why, where).
  - **`evh round-open --from rN --keep all --scoring "…"`** opens the next round judged by the current scorer:
    every carried arm another scorer judged is re-scored first ($0), each one's measure printed before and after.
  - Re-scores land in **one place the tool designates**, `data/runs-rescored/<scorer>/<source>/`, read by the
    catalog, the goals, the rounds and `validate`; `--out` still names any other. Rounds read an arm from its
    re-score as the goals do, and `evh rounds` and the goal page show a round's scorer and scoring changes.
  - **`evh round-open --adopt`** records a goal's first round from the arms already run for it.
  - A goal axis's **`limit: baseline`**: an arm is out when the paired test finds it worse than the group's
    baseline arm on that measure.
  - `validate` notes a round whose arms one adapter scored in more than one version.
  - `evh init`'s `.gitignore` ignores the throwaway `data/runs-smoke*/` and `data/runs-tune*/`.
- **`call_timeout_s`, an arm's call limit, for the built-in providers**: the SDK client's timeout (its own
  default is 10 minutes). The RUNBOOK told arms to set a call limit only the triage adapter honoured.
- **The triage example's adapter takes `reasoning_effort` and `max_tokens` per arm**, reports every model call
  for `arm-smoke`, and records a call that fails the same way twice at temperature 0 as the fleet's own "no
  terminal decision" (`no_decision`, `deferred`). With `reply_in_tool_call: <name>` it reads an answer a server
  returns as a tool call to that name, with no text: Ollama 0.40 does that to every gpt-oss answer, and the fleet,
  which reads only the text, got nothing.
- **No key for a local server**: the `openai` provider asks for no `OPENAI_API_KEY` when its address is on this
  machine (localhost, 127.x, ::1) or on Ollama's port, 11434; Ollama takes any key. Any other address still
  needs one, and a key that is set is used.
- **Tutorial 7, set up a model before you test it**: a model record, onboarding it where it runs, an arm that
  names it, a smoke before the full run; on your own machine with Ollama.
- **Judging modes** (RFC-005, PRD-003 FR5): a scorer's **`mode`** says what a judge is asked: `grade` (the default,
  as before), `pick` (the best of an item's outputs, in one call: `outputs_per_call` must hold every arm) or
  `pairwise` (the better of two, every pair of arms; `outputs_per_call` 2). Pick and pairwise project `won` per arm
  per item (judged runs' primary `judge_won`) and report each arm's win rate and Bradley-Terry strength with a 95%
  interval from resampling the items, and the position and noise checks as the share of verdicts that held. A judge
  is validated in its mode (`validation.mode` must be `mode`). The SummEval example validates `gemma_l` and
  `qwen_s` in both (`mode: pick`, scored `top1` beside `top1_chance`; `mode: pairwise`, scored `pair_agreement`
  with `n_pairs`; a `random` floor each): picks 0.364 and 0.263 against a random 0.070, pairwise 0.825 and 0.813
  against 0.473; the prompts ask for the JSON first and nothing after it. `judge-summ-pick-v1` and
  `judge-summ-pairwise-v1` are the summarisation eval's judges in those modes; the pick pass is run (29 arms in
  one pick: the order moved about half the picks, see the SummEval README), the pairwise one not yet.
- **An adapter's optional `primary_metric(params)`**: it names an arm's primary metric from the arm's params,
  beside `PRIMARY_METRIC` (its fallback); `run` and `rescore` record it. The SummEval adapter's is `tau`, `top1` or
  `pair_agreement` by mode.

### Changed

- **`evh experiment-run` is `evh run`, and an *experiment* is an *eval***: industry words (OpenAI evals,
  inspect_ai, Weave, Langfuse); what Braintrust and LangSmith call an experiment is a run here. The site's
  Experiments page is Evals (`evals.html`); the old address redirects.
- **Dataset roles are *validation* and *test*** (were dev and heldout): `evh dataset-split --test SHARE` (was
  `--heldout`) writes `<D>_validation` and `<D>_test`, and a split dataset records `split.test` and `part`
  validation or test. A goal's `role:` says validation, test or pilot. The reports' dev slice is the *pilot slice*,
  a small slice inside the test slice (not a validation split), and their measurement slice the *test slice*.
  `evh holdout` keeps its name.
- **The paired test's verdict is *significant*** (was separated): `significant: better`, `significant: worse`,
  `not significant`, everywhere they are printed or shown (`evh` output, the catalog, the inspector, the site,
  the reports); `family_test` and `bootstrap_test` print `SIGNIFICANT`, `pair-test` `SIGNIFICANT` or
  `NOT-SIGNIFICANT`. A project reading the old verdict strings reads the new ones.
- **A goal's arms that may win the tie-break are its *contenders*** (were tied): the decision's key is
  `contenders` (was `tied`), `evh arms --quality contender|below` (was `ties|below`), the arms page's facet
  "a contender", and the why-lines say "Contenders beside it" and "Still undecided after the tie-break". A tie
  is still what it was in a paired test: an item where two arms score the same.
- **A promoted reference is a *reference set*** (the governed collection under `data/references/<tier>/<name>/`);
  a *reference* is the expected answer for one item. The catalog's References page is Reference sets. Commands,
  paths and keys (`reference-promote`, `reference_id`, `reference_tier`) keep their names. REFERENCE.md maps
  every term to what inspect_ai, lm-evaluation-harness, HELM, OpenAI evals, Braintrust, LangSmith, Langfuse and
  Hugging Face call it.
- **`reference-create` and `reference-from-outcomes` are removed** (ADR-0022): a reference set is made only by
  promoting labels. A run's outputs are `label-from-run`'s (with the same refusals and `--not-redistributed`),
  outcomes `label-from-capture`'s (the same rules). A reference set made from outcomes has no rule of its own any more:
  promoted, it is a silver like any (with gold beside it, gold still decides; ADR-0020 is superseded). The one
  reference set here that named `reference-create` as its rebuild says where its texts come from instead.
- **`validate` fails a reference set with no manifest (V16)**, where it noted one: texts copied into
  `data/references/` by hand are a reference set nobody promoted. Import them as labels where they are and promote
  them: `reference-promote` adopts the folder when its texts are the labels' (writing its manifest; a folder whose
  texts differ is still never overwritten). Tutorial 1, the newcomer scenario, `evh self-test` and the tests make
  gold that way.
- **`evh reference-manifest` is a promotion**: it takes `--labelled-by`, `--reason` and `--by` (and `--kind`), and
  records them as `promoted_from` and the reason, so every reference set says where it came from; the reference schema
  requires both. This repository's reference sets are aligned: the caveats name where their labels came from (no
  "human-authored" or "model-generated" tier wording), the two that named a removed command as their rebuild name
  the 0.6.0 ones, and `from_outcomes` and `cost_usd`, which only the removed commands wrote, are gone. No run's
  fingerprint moves (none of these is hashed).
- **The sheet shows each arm's decision, the signals first**: an adapter's optional `decision(output)` (the
  triage example's: its disposition) is what an arm's column shows, the output itself otherwise; with no
  `same(a, b)`, two outputs agree when their decisions do. The browser's columns follow the terminal's (UXS-002).
  An adapter's optional `title(item)` names each item (the triage example's: the signal's alert name, not the
  probes that open it).
- **`evh inspect --items` is gone, and so is `--rows`; the sheet replaces both** (no aliases): `evh inspect --sheet
  --dataset-id D --runs …` shows every item's scores per arm and the rows view's signals in one table. The
  inspector's endpoints `/api/rows` and `/api/label-sheet` are gone; `/api/sheet` serves the sheet, and its
  `&format=csv` the download. The MCP tool `inspect` offers the sheet's options but not the ones that write a file
  (`--csv`, `--fill` and theirs).
- **The triage example's `write_gold.py` is `labels_from_verdicts.py`**: a source's labels from `verdicts.jsonl`,
  one file per item, for `evh label-import`; the tier is the promotion's. Its owner labels rebuild the committed
  gold set byte for byte.
- **`catalog-serve` serves on the project's own port**, not 8765 (`--port` overrides; `--public` keeps 8765), and
  `mcp --http` on another; a bookmark of `127.0.0.1:8765` moves.
- **The release leaves the pick list out**: picks are working notes that name production items, so a published
  catalog shows none waiting.
- **The tutorial kit's desk export records where the desk's router sent each ticket** (`routed`): tutorial 6 scores
  that decision against what happened, and picks the misrouted tickets for a dataset it governs.
- **The goal page explains, then answers, then shows how it got there**: what it is for first; then the answer
  so far, led by the latest round's conclusion when one closed after the baseline was promoted (the promotion's
  reason folded under it); then its rounds, one folded section each, headed by its row (round and status, the
  conclusion, what it set out to learn, arms and best), and inside it a heading per part (what changed, arms
  with retirements grouped by reason and the carried ones folded, scoring, evidence, suggested next, notes). The
  rounds table is gone.
- **The Models page has one line per cell**: the first build and "+k", the deployments' ids, "N goals" with the
  first named, the single best placing with "+k more"; vetted records first. **A model's page** has one folded
  section per deployment, holding its build and its own onboarding with the flags it accepts and why; its arms
  table names each arm's deployment and reads a re-scored arm as the goals do.
- **The datasets table shows each tag as a chip.**

- **Fingerprint v5** (RFC-021): what each part identifies. `instrument` (the harness and the adapter's code),
  `data`, `deployment` (the system under test as it executed: from the arm's model record and deployment, the
  adapter's hook, or the params; the weights, the server, where it ran; in process only when the arm calls
  nothing elsewhere) and `settings` (how it was asked: the params that change behaviour, and what a hook declares
  about its prompt), each hashed, and `hash` over the four. The machine `evh` ran on is `runner`, recorded outside
  the hash: the same deployment run from two machines is the same measurement. `evh run-compare` names the part
  that moved; the inspector's speed warning tells a deployment that differs from a runner that does. Every
  committed run is migrated by **`evh fingerprint-migrate`** (idempotent, `--dry-run`); v4 fingerprints are not kept.
- **`data/models.yaml` is replaced by the model records** (`data/models/`): its 41 entries are migrated one record
  each, and the arms page's open / proprietary filter reads the records.

- **CI runs once per merge, not twice**: a squash onto main whose tree is its pull request's head,
  tested green and up to date with main, skips the workflows that already passed on it; the deploy
  no longer waits ~13 minutes for a second run of the same files. Anything else runs them again.
- **An item id may contain `:`, `@`, `+` and `=`** (a production record's id, e.g. a fingerprint and its
  time), on the inspector's item view too; still never a path.
- **A deployment copies its data through `_release.py copy-data`**, not a list in `render.sh`: the same
  directories, plus each capture's `capture.json` (never its records), with the `text: hidden` rules
  applied and the untracked-text refusal checked before anything is written.

### Fixed

- **Every `evh` command is a `make` target again**, as the READMEs and the RUNBOOK say: the 22 added in 0.5.0 and
  0.6.0 had none (`make labels`, `make reference-promote ARGS="…"`, …).
- **The home page's "recorded" feed shows the period's events.** Its period filter read the date from the table
  cell, not the span inside it, so it hid every event and said "Nothing recorded in this period" (since 0.4.2).
- **Coverage counts an arm scored against a label set as `labels`**, on the home page and in `evh overview`; it
  counted as `none`.
- **The home page's glance reads a goal's baseline from its re-score** (RFC-022), as the goal page does: a baseline
  promoted before a re-score showed no value and no test.
- **A frontier chart's names stay inside the chart**: a long name on a dot in the middle ran past the right edge;
  it goes to the side it fits, shortened when neither does, never over the y axis.
- **The label-set and agreement tables keep their promoted and agreement columns on screen** on a desktop: long set
  ids may break there (a phone still scrolls the table sideways).
- **`evh deploy-sheet` says "against no reference"** for a run scored against none, not `None (None)`.
- **The leaderboard's silver note no longer says "model-generated"**: a silver reference set can be a person's or a
  rule's labels.
- **A retired arm read through its re-score is out of the goal's contenders.** A round's retirements name the arm's
  config, and an arm read from `runs-rescored/<scorer>/` kept the prefix, so it was never matched as retired and
  stayed among the contenders (the triage goal's: 76 arms, 51 once read right).
- **Sorting a page's later table sorts it by the column clicked.** Its header's index was counted over every sortable
  header on the page, so a second table sorted by a column it does not have and threw.
- **`evh mcp --public` sees only public fields in `inspect`.** The tool runs the command in its own
  process, where the inspector's public rules were never set, so a `--where` or `--by` on a field not
  marked public was accepted and its values could be read through the counts (0.5.0). A public
  server now runs its commands as public (`EVH_PUBLIC`), and such a filter is refused by name. This
  repository's own deployment declares no field sets, so it exposed nothing.
- **A command's own refusal through `evh mcp`** (exit 1, its `ERROR:` line, no traceback, such as a
  dataset id that is a path) is told to `--hooks` as `refused: "command"`, not as an error: a
  deployment's metrics count it as refused and its analytics send no event for it.
- **The site's links to its home page** point at `/`, never `index.html` (analytics counted the two
  apart, search engines saw two addresses for one page), and each of its pages names its own address
  as `<link rel="canonical">` and `og:url`, checked by `site/build.py --check`.
- **`validate` checks every git-tracked runs directory**, those `committed` in validate.json with their floors
  and every other one: a directory re-allowed in `.gitignore` but not added to the list was never checked
  (a set of 65 re-scored triage runs, before RFC-022 gave re-scores one place).
- **The local catalog reads what is committed.** It read every `data/runs*` directory on disk, so a smoke
  pass in an ignored `runs-smoke*` showed as a result locally and was gone from a clone and the published
  catalog. Directories git ignores are no longer read (outside a git checkout everything is). A measured arm
  the goals read from its re-score says so on its page, on the arms page and in `evh arms`.
- **Runs written where git does not keep them are named.** `EVAL_RUNS_DIR` pointed at any
  `data/runs-*` directory that `.gitignore` does not re-allow wrote runs that were never committed
  and that no catalog showed, without a word: 35 self-hosted triage runs sat in `data/runs-local`
  that way. `run` and `rescore` now print a `WARNING` when they write to such a directory
  (throwaway `runs-smoke*` and `runs-tune*` stay silent), or outside the project's data, where nothing
  reads them, and `evh validate` notes one that holds
  finished runs. The RUNBOOK's scratch example is `data/runs-smoke`, the throwaway name git already
  ignores.
- **One row per arm when a scorer changed.** A goal listed an arm twice when its runs had been
  re-scored (`evh rescore`) into a derived set, once per directory, and dropped the measured runs
  whose older score lacked the goal's measure: 37 triage arms were listed twice, 15 only from
  the re-score. A re-score against the same reference now stands in for the run it re-read on the
  goal pages, in `evh goals` and in the recommendation, which says how many arms it read that way.
  `evh goals --goal` also prints a dataset's notes, as its page did.
- **A deployment the adapter's hook declares keeps the server it was called on.** Its `server` was
  always null, so a self-hosted run whose adapter has a `fingerprint()` hook lost its Ollama or vLLM
  URL. The 130 triage runs are backfilled with the fleet they replayed (`tools/backfill_triage_fleet.py`:
  the fleet's code hash and commit `f07efa9`, the prompt's hash, each checked against what the runs'
  own items recorded) and re-sealed.
- **Onboarding a model on several machines at once keeps every result.** `model-onboard` and `arm-smoke` read the
  record when they started and wrote all of it back when they finished, so the slower erased the other machine's
  result. They re-read it under a lock and write only their own deployment or smoke.
- **A LiteLLM address given with `/v1` is not given a second one** (`http://host:4000/v1` became `/v1/v1`, a 404),
  and a reasoning setting sent through LiteLLM is named in `allowed_openai_params`: most hosted model groups refused
  `reasoning_effort` without it (`UnsupportedParamsError`).
- **A record can accept a flag as the model's nature** (`accepted: {reasoning: "<why>"}`): onboarding and arm smokes
  report it as accepted and pass (gpt-oss reasons whatever it is asked). A deployment accepts kinds of its own
  beside the record's: a hosted gateway's build cannot be pinned, and its repeats at temperature 0 vary.
- **A round with more than 40 arms is compared.** Its evidence asked the inspector for one comparison of every
  arm, which refuses past 40, and the refusal left the rows empty without a word (the triage round, 52 arms). Past
  the inspector's limit the round runs the same paired test on the scores directly; a refusal becomes a note.
- **A project module edited within the second is what runs.** Adapters and hooks were imported through
  Python's bytecode cache, which trusts a `.pyc` while the source's modification time (whole seconds) and size
  match: a scorer edited to a value of the same length (`BONUS = 0.0` to `0.5`) and re-scored at once ran the
  old code while the re-score recorded the new code's hash. They are compiled from the source every time.
- **A system that ran in the harness's own process, with no hook, is in process.** A deployment taken
  from the params was always `in_process: false`, so a local baseline (Lead-3, a keyword rule) kept its
  libraries on the runner instead of the deployment. `evh fingerprint-migrate` brings existing v5
  fingerprints to the rule when it has the run's params (11 runs here, one baseline's hash).
- **A run stops when its server cannot be reached.** An adapter that turns a failed model call into an
  answer (the triage replay records it as the fleet's "no terminal decision") wrote a complete-looking run
  when a tunnel dropped: 54 and 65 refused items scored as the model's own failures. When every call an
  item reports (`meta["calls"]`) failed reaching its server (connection refused, no route, a name that does
  not resolve), `run` stops there with `STOPPED`, that item unwritten, and `--resume` calls it
  again. A model's own failure is still a measurement.
- **`evh pair-test --round` reads each arm as the round does**: from its latest re-score when one stands in for
  its runs. It read `data/runs` alone, so a measure an arm's re-score added (production's triage run on
  `triage_cost`) found "only 0 shared item(s)" while the round's own evidence tested it. "(its leader)" is said
  only when the test chose the leader.

## 0.5.0 — 2026-10-29

Two things to know before upgrading: the package now needs **Python 3.10 or later**, and it depends on the
official **MCP SDK** (`mcp>=2.3,<3`). On 3.9, stay on `v0.4.4`. What you get: `evh mcp`, the project's read
commands as tools for any agent (stdio on your machine, or `--http` for a team or the public), and a dataset page
that shows what is inside a dataset without republishing its text. [UPGRADING](docs/UPGRADING.md) has the steps.

### Added

- **`evh mcp`: the project's read commands as MCP tools, for an agent** (stdio, the official SDK,
  [RFC-018](https://github.com/chipi/eval-harness/blob/main/docs/rfc/RFC-018-read-only-mcp-server.md)). Thirteen
  tools: `overview`, `datasets`, `dataset-items`, `arms`, `goals`, `references`, `metrics`, `activity`,
  `search`, `inspect`, `rounds`, `runs-list`, `validate`. Each call runs the command as a child process, so a tool
  answers what the command prints; each is annotated read-only; no tool writes project data, spends or runs a
  model (the one file a call writes is the p cache in the project's ignored `.cache/`, below). For Claude
  Code, in the project: `claude mcp add evh -- evh mcp`.
- **`evh mcp --http`: the same server for a team, or for anyone.** Streamable HTTP, stateless, JSON responses:
  clients on every protocol revision since 2025-03-26 call tools without a session. The Host is checked against DNS
  rebinding (`--allowed-host` is required to bind beyond the loopback); `--public` leaves out the options that
  answer with an item's text, and the `validate` tool; `--rate`, `--concurrent` and `--timeout` bound the load; a
  missing required argument is refused before anything runs; `--hooks` takes a deployment's error reporting,
  tracing, metrics and analytics, in the inspector's shape. Each call is logged as one JSON line: the tool, its
  arguments' names (never their values), how it ended, its time; never the caller's address or user agent.
  `--rate` counts calls a minute per caller (an IPv6 caller by its /64), `--rate-total` for all callers together;
  over HTTP a caller has one call running at a time.
- **`EVH_P_CACHE`: the goals' paired tests kept on disk.** Every `evh` command is a fresh process, so a view that
  shows the goals drew the same tests again each time (about 50 s on this repository's runs). With the variable
  naming a file, each estimated p is stored and read back exactly; `evh mcp` sets it to the project's ignored
  `.cache/`. `goals`, `overview` and `arms` answer in under two seconds after the first.
- **This repository's MCP server, `https://evals.humancopilot.eu/mcp`** (the deployment, not the package): the six
  worked examples for any agent, read-only, without sign-in.
- **`--json` on the catalog's view commands** (`overview`, `datasets`, `arms`, `goals`, `references`, `metrics`,
  `activity`, `search`, `inspect`): one object, `{"command", "version", "result": {"blocks": [...]}}`, each table as
  columns and rows of values, every other line as text. It is collected from the same calls that print the text, so
  the two cannot disagree. 0.7.0 gives each command its own result schema and retires this generic form: do not
  build on `blocks`.

- **What is inside a dataset, on its page and as a command.** `evh dataset-profile --dataset-id D`,
  run where the dataset is materialized, writes `data/profiles/D.json` (`schemas/profile.schema.json`,
  checked by validate V1): the number of items and their words, the shape of each gold reference
  (labels and how many of each, entries per item, a record's fields, or words per reference), and
  per item its length, its gold and, when known, where it can be read at its source. A gold of labels
  (a few short values that repeat) is listed per item; any other gold is summarised, never listed. It
  holds no item text, which a dataset's licence may not let you redistribute, unless written with
  `--with-text`, which is refused unless git has committed every item's file (a project's own synthetic data). Commit the profile and the dataset page shows "what's
  inside" wherever the catalog is built; `evh dataset-items --dataset-id D [--item ID]` prints the
  same, and an item's text when it is materialized here.
- **An item's link to its source** comes from the dataset: an item's `source_url`, or a
  `data/sources/<dataset_id>.rows.json` that a fetch or import step writes (`{"source", "item_url",
  "rows": {item_id: {"row", "sha256"}}}`), matched by the item's bytes, so an id that recurs in
  another dataset never takes its link. This repository's Hugging Face fetchers write one, so each
  item opens at its row in the dataset viewer.
- **`inspect.html?…&item=ID`** opens that item once the comparison has loaded; a dataset page's
  **inspect** link uses it.
- Adapter: `dataset_profile(dataset)`, optional (RFC-003).
- **Every catalog page names its command**, in its footer (`evh goals --goal G`, the inspector's from the arms
  picked). **`evh catalog --mcp URL`** names the same as an MCP tool call, with the server and how to connect
  (`--mcp-howto`); this repository's catalog passes its `/mcp`, and its header links to the site's MCP section.
- **`evh dataset-profile --json` and `evh dataset-items --json`** print the profile inside the same envelope as
  the views, `{"command", "version", "result": <the profile>}`; the Makefile targets `dataset-profile` and
  `dataset-items`.

### Changed

- **Python 3.10 or later.** The official MCP SDK needs it, and every feature comes with one install, so the
  package's floor moves from 3.9 to 3.10 (CI tests 3.10, 3.11 and 3.14). On 3.9, pin `v0.4.4`.
- **A new dependency: `mcp>=2.3,<3`**, which brings `anyio`, `httpx2`, `mcp-types`, `opentelemetry-api`,
  `pydantic>=2.12`, `pyjwt[crypto]`, `python-multipart`, `sse-starlette`, `starlette`, `typing-extensions`,
  `typing-inspection` and `uvicorn`. No result moves.
- **A dataset id is a name, never a path.** Every command that reads or writes `data/…/<id>.json` refuses an id
  that is not letters, digits, `.`, `_` and `-` (or that holds `..`); before, `../x` read or wrote outside `data/`.
- **A param shown on a catalog page or by `evh arms --arm`** hides a URL's user and password and a nested key
  named like a credential (`headers: {Authorization: …}`), as it already hid a top-level `api_key`.

### Security

From two independent reviews before this release, each reproduced before it was fixed:

- **The inspector served any `.txt` under its data tree** through `/api/item?item=../../…` (an item id was never
  checked; on `main` since 0.4.0). An item id is now a file's name, refused otherwise, in the server and the adapter.
- **The inspector's answers were cached by count, not size**: a hundred distinct 40-arm questions took a 256 MiB
  container past its limit, and `--warm` alone did on this repository's data. The cache is bounded by the bytes it
  keeps (32 MB), keeps no refusals, takes no question over 4 KB, and `--warm` stops when it is three quarters full;
  the deployment's inspector has 384 MB (it peaked at 228 of 256 under load). Its rate key is an address, never a header's
  text.
- **`evh mcp --http`**: a few parallel 4 MiB bodies killed the server; held GETs and ping floods cost memory no rate
  saw. Now `--max-body`, `--max-connections`, 8 open requests per caller, a 10 s deadline on a request's body
  (eight callers holding slow bodies took every connection), `--request-rate`, GET is 405, refusals do not count toward
  `--rate-total`, and `--public` answers are kept and their errors carry no paths. Values with NUL bytes or over 512
  characters are refused.
- **The deployment**: Caddy refuses a body over 64 KB on `/mcp` (and its `handle` line now adapts); nginx limits
  each visitor (20 requests a second, a burst of 200, 32 connections); the deploy checks the inspector is up and
  under 80% of its memory once `--warm` is done, and rolls back otherwise; the MCP hooks no longer export the
  SDK's own spans; the containers'
  `/tmp` caps files as well as bytes; `render.sh`'s check for reference texts in a release could pass with 1,657 of
  them (a pipe's SIGPIPE) and refused the five tracked ones: it now compares against what git tracks; a deploy keeps
  two releases (the live one and the rollback), prunes at its start as well as its end, and refuses to start short of
  2 GB or 300,000 inodes; the upload hard-links unchanged files again (no file ever linked: each release took ~69k new
  inodes).

### Fixed

- **The deployment's release ships `data/models.yaml`** (`render.sh`, and the item fields and profiles with it):
  from 0.4.2 it was never copied, so the deployed arms page called every model's weights unknown.
  `tests/test_render_data.py` fails when a part of `data/` the adapter reads is not copied.
- **The CNN/DailyMail and SummEval fetchers deleted the committed gold `manifest.json`** on every refetch; they
  now clear only the item files.
- **`--hooks` files with a module-level `@dataclass`** failed to load (the module was not registered before it
  ran); they load as any other module now.
- **A page links only to `http(s)` URLs**: a `source_url` or rows map that held `javascript:…` was written into
  an `href`.
- **The p cache** reads an unreadable or non-UTF-8 file as no cache instead of failing the command, starts a new
  line after a torn one, and keys each p by how it was computed.
- **`evh dataset-profile --with-text`** counts a file as tracked only once it is committed, not when it is
  merely staged.

## 0.4.4 — 2026-10-28

The catalog says what it is and links out: `--about` puts a deployment's own paragraph on the
overview, a goal's `links` are shown, and `--repo` turns project paths into links. The arms page
now carries the deployment's options like every other page. No result moves.

### Added

- **`evh catalog --about FILE`**: a deployment's own paragraph on the overview, under its
  description. It says which project the catalog shows and where its findings are. None by
  default.
- **A goal's `links` on its page and in `evh goals --goal G`.** The field was in the goal
  schema but shown nowhere. A web address opens; a path in the project is named as text, because
  the static pages cannot know where the project is hosted.
- **`evh catalog --repo URL`**: where the project's files can be read (e.g. a GitHub `blob/main/`
  address). A project path in a goal's links, or at the start of a guardrail's source, then links
  there. Without it, the path stays text.

### Changed

- **The overview says what the catalog is**: "pages the harness builds from this project's
  committed runs", and that the inspector tests any arms against a baseline, item by item.

### Fixed

- **`evh catalog` built the arms page without the deployment's options.** Run as a command, the
  builder is `__main__`, and the arms page was rendered by a second copy of it with the
  defaults. So `arms.html` said "eval catalog" whatever `--brand` was, and had no `--link`
  switcher, no `--head` and the default `--api`. Every page now carries them.

## 0.4.3 — 2026-10-27

A security fix to the inspector: `evh catalog-serve` no longer serves files through `/api/`.
Upgrade if you run it where anyone else can reach it. No result moves.

### Fixed

- **Nothing is read through `/api/`.** A path under `/api/` skipped the server's path checks
  and fell through to the file server, so `/api/../.env`, encoded or not, returned files from
  the project root, keys included. This happened in local and in `--public` mode. Now a `..`
  anywhere in a path is refused first, and only the API's three endpoints (`/api/health`,
  `/api/compare`, `/api/item`) answer under `/api/`. Any other `/api/` path is 404. In
  `--public` mode no path outside the API serves a file.
- **`--hooks` see one route for every unknown `/api/` path.** It is named `/api/other`, so
  someone asking for many made-up paths cannot create a metric series for each.

## 0.4.2 — 2026-10-27

A catalog that says what changed, and where: every count on the home page has a trend and opens a
page that shows the rows behind it, for the same period. An activity page and an arms and configs
page. No result moves.

### Added

- **A period on every page, counted from today.** Four chips (14 days, 30 days, this month, all
  time) and a list with the rest (7 and 90 days, this and last week, last month, this year); the
  browser works it out from the viewer's date, so a catalog built days ago still shows this week.
  A trend compares with the same days of the period before. The period travels in the link
  (`datasets.html#p30d`). On the goals, datasets, arms, references and metrics pages a row made
  in the period has a **new** badge, chips keep only the new or the active rows, and in-period
  columns give the runs and spend with their trend (▲ 12%, ▼ 31%, ▲ from 0) and a line of runs
  per day. The goals page lists what happened to each goal (baselines, rounds).
- **The activity page** (`activity.html`, `evh activity`): the home page's charts at full width,
  and the period's runs, spend and tokens by dataset, by arm and by kind of call, the busiest
  first. The measured runs, billed and tokens tiles open it.
- **The arms and configs page** (`arms.html`): every arm, saying how it was measured (measured,
  rescored against a reference, judged by a scorer, re-parsed, run again), grouped by dataset,
  config, model, provider or what it is scored against, filtered to local or hosted arms or a
  price tier, with its role in each goal's decision; tick arms on one dataset to open them in the
  inspector. Every config across the datasets it ran on, with its rank on each goal. What changed
  for arms in the period, and each goal's trade-off charts. The arms tile opens it; the configs
  tile opens it grouped by config.
- **`--period P` on every list**: `evh datasets`, `goals`, `references`, `metrics`, `arms` print
  the page's period columns. `evh arms` lists the arms page's rows (`--by`, `--where`, `--tier`)
  and `--configs` the configs. Each page's period numbers come from one builder the page and the
  command both read.
- **Adapter:** `dataset_created(dataset)`, optional: the day a dataset counts as new (else its
  first run). `spend()` events may name a measured run's `arm`, which the arms and activity pages
  bill it to; `HarnessAdapter` does.
- **Grouping on the datasets page (by goal) and the metrics page (by role: decides, weighs,
  describes)**, as the arms page groups; one script (`group.js`) groups and filters all three.
- **The arms page filters on quality and on weights:** ties the leader or below it (the arm's place
  in a goal's decision), and open weights or proprietary. `evh arms --quality ties|below` and
  `--weights open|proprietary` list the same.
- **`data/models.yaml`** (optional, `schemas/models.schema.json`, validate V1): each model's
  weights, open or proprietary, and licence, keyed by the model a run records. The adapter's
  optional `model_facts()` reads it.
- **A derived arm says how far it moved** from the config's measured arm on the same dataset
  (rescored, re-parsed, run again: "0.712 → 0.745 (+0.033) vs measured", in `evh arms` too).
- **An arm a goal leaves out for a limit it breaks is badged "over a limit"**, not "not eligible".
- **`evh catalog-serve --hooks FILE.py|MODULE`**: a deployment's error reporting, tracing or
  metrics, on a generic hook point (`start`, `request`, `error`, extra `routes` such as
  `/metrics`). The harness ships no tracker and depends on none; without `--hooks` nothing
  changes. This repository's deployment uses it (`infra/inspector/hooks.py`).

### Changed

- **The home page's tiles carry trends.** Measured runs, billed and tokens show the period's
  total, ▲/▼ % against the period before and a line per day; goals, datasets, configs, arms,
  references and metrics show the total and how many are new. The tiles are grouped and coloured
  by subject (goals; data; experiments; work and spend), with a legend; never red or green for a
  direction. The charts and the feed follow the period.
- **The menu is grouped by the same subjects:** Overview, Goals, Data (Datasets, References),
  Experiments (Arms, Configs, Metrics), Activity, Inspector; a phone's menu lists every page.
- **`evh overview --period P`** prints the tiles and trends; `--all` is gone (`--period all`).
- **The activity page and `evh activity` list what moved most first** against the period before
  (up or down), then the busiest; for all time, the busiest.
- **"What changed in the period" on the arms page folds** three or more arms of one dataset
  re-measured the same way on one day into one line ("12 arms on `<dataset>`").
- **A period select never makes a page wider than a phone**, however long its options.

### Fixed

- **`evh bootstrap-test` and this repository's report tools refuse when the gold references are
  not on the machine** (the repository commits their checksums only): they name the fetch step.
  The extraction and retrieval reports printed tables of zeros instead, as if they were results,
  and the classification report died with a traceback.

## 0.4.1 — 2026-10-27

A catalog that works on a phone and sits inside a deployment's own site, and an inspector that
no longer runs out of memory. No result moves.

### Added

- **`evh catalog --head FILE`**: HTML added to every page's `<head>`, for a deployment's own
  analytics or tags. The harness adds none of its own.
- **`evh catalog --api PATH`**: where the inspector's API answers, for a catalog served under a
  path (default `/api/`; e.g. `/catalog/api/`).
- **`evh catalog --brand NAME`**: the product's name beside the logo (default "eval catalog").

### Changed

- **`--link LABEL=URL` is a switcher between the parts of a publication**, not extra nav entries:
  the links head every page in order, the catalog marked (`LABEL=.` places it; without one it
  comes first as Catalog), and the logo opens the first. The catalog's own pages stay in its nav
  (a ☰ menu at the left of the bar on phones), and its front page is called Overview. The search
  box reads "Search ( / )", and on a phone it is a round search button in the bar that opens it below; a long
  count on the overview shows in short form on a phone (19.5M). The bar's buttons are SVG icons.
- **Tables on a phone**: a cell breaks between words, never inside a name, so a narrow screen
  scrolls a wide table sideways; running text keeps a readable width; a long item id is
  shortened in the inspector's per-item table (the whole id is its title); no catalog or
  inspector page is wider than the screen.
- **No inline styles**: the charts' legend colours are classes, so a deployment's content
  security policy can forbid `style` attributes.

### Fixed

- **The inspector no longer runs out of memory.** The paired test kept the signs it draws for
  every item count it met (~31 MB each), so `--warm` on a large catalog grew past a 256 MiB
  container limit and the server was killed every few minutes. At most two sign tables are kept
  now, stored as bytes, and at most 4096 estimates; a warmed inspector settles at ~150 MB. The
  p-values are the same, bit for bit.

## 0.4.0 — 2026-10-25

See your runs, not only tables of them. `evh catalog` builds static pages over a project's
runs, and `evh catalog-serve` runs an inspector that tests chosen arms against a baseline and
shows one item's outputs beside its reference. A project on the harness's layout needs no code;
one with its own layout writes one adapter. Goals record what an evaluation is for; items carry
the typed fields a project declares, and can live at a pinned URL. The paired test now lives in
one place, `evaluation_harness.stats`, exact at 30 items or fewer.
**Upgrading can move a result** only where `pair-test` or `family-test` ran on 30 items or fewer,
in a wins count or an order on a lower-is-better metric, or where `--exclude-dataset` named a
dataset whose items are not `.txt` files under `data/sources/<id>/` (all below), and adds no
dependency. Design:
[ADR-0002](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0002-catalog-inspector-goals.md),
[ADR-0003](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0003-item-fields-and-url-items.md);
how to upgrade: [UPGRADING](https://github.com/chipi/eval-harness/blob/main/harness/docs/UPGRADING.md).

This repository now deploys the harness on its own example experiments:
- the catalog and run inspector are public at
  [evals.humancopilot.eu/catalog](https://evals.humancopilot.eu/catalog/);
- the public site, the harness and its findings, moves from GitHub Pages to the same server;
- the docs move to [evals.humancopilot.eu/docs](https://evals.humancopilot.eu/docs/), and old
  `/docs/` links redirect there.

The deployment files are in `infra/` (runbook: `infra/README.md`). They are not part of the
package.

The example experiments keep one record per arm, the latest: the rescored and re-parsed runs
are folded into `data/runs` as derived runs, and DailyMail's `bart_s` is its fp32 run
(coverage 0.4048; the fp16 run read 0.4039). CNN's `bart_s` stays the fp16 run, the one the
judge's verdicts were made on. The reports state the current figures only; their correction
logs are gone (git keeps them). Two published statements were stale and are restated:
SciFact's `qwen_s` e5-first against the e5-first leader is +0.0178, p 0.10 (it read +0.0092,
p 0.36, from the pre-fix run), and DBpedia's 56-item dev slice, over today's 28 arms, puts
`bert_base_fy` alone at the top rather than 13 arms in a tie.

### Added
- **The rest of the inspector and catalog in the terminal.** Every page and view now has a
  command:
  - `evh search TEXT` is the catalog's search box, ranked the same way, with the command that
    shows each hit;
  - `evh inspect --items` is the per-item table (each arm's score and its Δ against the
    baseline);
  - `evh inspect --analysis [--x METRIC]` gives the analysis charts as numbers: spread per run,
    the difference from the baseline, and each arm's mean against a second metric.
- **`pair-test --round rN`** tests within a round. A defaults to the round's leader, B to the
  baseline the round started from, and the metric to the goal's measure. An arm that is not in
  play is refused.
- **On the goal page:**
  - each round has an inspect button that opens its arms against its leader (`evh inspect
    --round`);
  - every suggested command has a copy button;
  - a retired arm is greyed out.
- **Experiment rounds, optional** ([ADR-0004](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0004-eval-rounds.md)).
  Experiments go round on round: try some arms, keep what wins, drop what lost, change something,
  compare again. `evh round-open --goal G --dataset D [--from rN]` records what a round sets out to
  learn, what changed, the arms carried in unchanged (`--keep`) and those dropped with the reason
  (`--retire ... --reason`); arms join by naming it in their config (`round: rN`, recorded on the
  run). `evh rounds --goal G` reads the evidence the way the inspector does — the round's arms
  against its leader, its best against the previous round's best and against the baseline it
  started from, its spend against `budget_usd` — and suggests the next decision, each as the
  command that makes it: `evh round-retire`, `evh rank-stability`, `evh round-close --conclusion
  ... --promote <run>` (which promotes the baseline with the conclusion as its reason). A closed
  round refuses new runs; validate (V14) checks the records; `leaderboard` and `family-test` take
  `--round`. The goal page shows the rounds, newest first, with the open round's suggestions. The
  catalog stays read-only: decisions are commands. A project that never opens a round sees none of it.
- **A goal page leads with its answer.** First the promoted baseline on each of its datasets and
  why (or "no decision yet", with the command that makes one), then what the goal is for, then on
  each dataset its references and its arms in groups by what they are scored against: gold,
  silver, a judge. Arms are ranked only within a group, and a group's leader is never an arm graded
  against its own outputs. A dataset page shows its baseline and reason, and the baseline's row is
  tagged. `evh goals --goal` and `evh datasets --dataset-id` say the same.
- **Everything the catalog and the inspector show is a command.** `evh datasets` (one dataset:
  its versions, references and arms), `evh references` (one: who wrote it, from which run, what
  is scored against it), `evh metrics`, `evh goals` (one: its arms per dataset) and
  `evh inspect --runs …` (the inspector's verdicts, conditions, `--where`/`--by` on fields,
  `--item` for one item's outputs beside the reference). Same adapter, same computation: the
  numbers are the pages'. Each is also a `make` target.
- **The catalog says what every number is measured against.** A metrics page (what each metric
  measures, which way is better, where it is recorded, which goals decide on it) and a page per
  reference (who wrote it, from which run, every arm scored against it); every metric and
  reference on the pages links there. Each arm's row says what it is scored against, and rows
  scored against silver, by a judge, or against the reference the arm wrote itself are tinted; a
  judged arm reads "judge <scorer>", no longer "gold". A goal page flags the arm that wrote the
  reference it is scored against, so it is never the leader. The inspector's charts section is
  "analysis", and its verdict rows carry the same tints. Actions are compact and tinted.
- **Long tables page.** Every catalog table and the inspector's per-item table show 10 rows, with
  "show 10 more" and "show all"; the filter and the sort work over every row, and a link to a row
  opens the table at it. The verdict tables stay whole: their Holm thresholds are read together.
- **Dataset versions keep their lineage.** `evh dataset-create --dataset-id x_v2 --from x_v1`
  records where a version came from and the item ids it adds, removes and changes
  (`derived_from` in the dataset file); `validate` V2 fails a version whose parent is gone. The
  catalog links versions both ways with what changed, and a version no arm has run on yet gets
  a page when it is linked to one that has.
- **The inspector says whether the compared runs ran under the same conditions**, from their
  fingerprints: the machine, library versions, the harness, the scorer (adapter code), the
  items and the reference's bytes. One line when all match; otherwise the fields that differ,
  arm by arm, with a warning when the scorer or the reference bytes differ (different
  measurements) or latency is compared across machines. A dataset page names each arm's machine
  when its arms ran on more than one.
- **`METRIC_DESCRIPTIONS`** in an adapter, one sentence per metric, is recorded on every run
  (`metric_descriptions` in metrics.json) and refreshed by `evh rescore`; the catalog reads the
  adapter's current descriptions over the recorded ones, so describing a metric later needs no
  new run. The harness describes its own metrics (cost, tokens, latency, judge scores).
- **A run becomes a reference: `evh reference-create --from-run <run_id>`** (`make
  reference-create RUN=<run_id>`). The usual way to get references is to run the expensive
  model as an arm, read its results, and score the cheaper arms against what it wrote. Until now
  that took a second paid pass (`--config`), whose outputs could differ from the run you read,
  and the reference did not say which run it came from. `--from-run` copies a finished run's
  outputs and calls nothing; the manifest records the run, its config, fingerprint, build and
  cost. It refuses what `run-promote` refuses (a dirty tree, an unknown build), an unfinished,
  derived or other-dataset run, and `--tier gold` (gold is what a person wrote or checked).
  With `--not-redistributed` only the manifest is committed: it records the command that rebuilds
  the texts from the run, and that command, on a checkout with the manifest alone, writes them
  again and checks them against its checksums without touching it.
- **`reference-create` refuses an empty output, and outputs that stopped at `max_tokens`**, by
  either path (`--allow-cut-off` for outputs that end at the cap by design). A frontier arm at
  `max_tokens: 80` wrote 19 of 20 summaries cut off mid-sentence and one empty reply, and they
  were frozen as the reference with no word.
- **The leaderboard marks the arm that wrote the reference it is scored against** (`arm *`, and
  a note): that row is graded against its own outputs.
- `reference-create` says when gold exists (new runs keep scoring against gold; how to rescore
  against the new silver), and to commit the reference before the next run: an uncommitted
  reference makes every later run dirty.
- **A newcomer scenario for every release**
  ([SCENARIO](https://github.com/chipi/eval-harness/blob/main/harness/docs/SCENARIO.md)): a fresh
  project, the published docs only, a summariser and a classifier with small CPU models, cheap
  hosted LLMs, a frontier reference and a judge, browsed in the catalog, under $1. RELEASING
  runs it before the merge.
- **A goal weighs cost, quality and speed, and recommends**
  ([ADR-0006](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0006-goal-axes-and-strategies.md)).
  Cost (USD per item, tokens beside it) and speed (latency p50 and p95) are built in;
  `success_criteria.axes` adds limits, another measure, `role: ignore`, or the project's own
  per-item metric in one line. A `strategy` says who is tied with the quality leader
  (`balanced`, the default: not separated by the paired test and within a margin, 2% of the
  leader unless the goal sets one; `quality_first`; `frugal`) and `tie_break` (default cost,
  then speed) picks among them. Limits come first; flagged and retired arms are never
  recommended, nor is an arm measured on fewer items than the rest of its group; identical
  scores are always tied; a missing number is "not recorded", and an axis a tied arm does not
  record cannot break the tie; speed is not compared across machines the runs recorded. Some
  groups show their leader and never recommend: a dataset marked `decides: false`, a silver
  group beside a gold one, and a group measured by unvalidated judges ("Shown, not
  recommended", with the reason). The helpers are public as `evaluation_harness.axes`.
  The goal page shows the decision with its reasons, an axis column per arm and quality
  against each axis as charts; the home page's glance a **recommended** column with cost and
  speed against the baseline; the dataset and arm pages cost and speed; the inspector's scatter
  cost and tokens. `evh goals --goal` and `evh overview` print the same. Guardrails are shown
  on the goal page and in the CLI. When the recommendation is not the promoted baseline, the
  goal page and `evh goals --goal` say by how much and whether the test separates them; with no
  eligible arm, they count the reasons. The goals page and `evh goals` count configs filed and
  show each goal's recommendation. Cost and speed metrics are their own kinds, with the goals
  that weigh them, and costs print to six places; chart names no longer overlap.

- **Reference manifests and V16.** Every reference carries a `manifest.json` with the checksum of
  each item's text (`schemas/reference.schema.json`); `evh reference-manifest` writes it for gold a
  script builds, `reference-create` for the references it makes. It is committed even when the texts
  are not redistributed: `evh validate` (V16) checks a rebuilt copy against it, and the catalog lists
  such a reference as fetched. The manifest names the dataset (`dataset_id`), so a second gold for
  one dataset can have a name of its own (`reference-manifest --dataset-id`, e.g.
  gold/ag_news_200_adj1 for ag_news_200). This repository's gold references now have one.
- **`round-retire --runs-dir`** retires one copy of a config (its runs in another runs directory,
  such as a re-timing on another machine) and leaves the arm in the project's runs directory in play.
- **`evaluation_harness.stats`**. Standard library only, and the one place the paired test
  lives:
  - `exact_p` and `sign_flip_p`;
  - `holm`, with a declared family larger than the p-values passed;
  - `exact_ci`, an interval for the mean difference that agrees with the test: none at 5
    items or fewer, where no shift can be rejected;
  - `compare`, every arm against a baseline with verdicts in words;
  - `compare_by`, the same test within each group of items, Holm-corrected over every group
    and arm together;
  - `ranks`, `pearson` and `spearman` (average ranks for ties; a constant input returns
    `constant`, NaN unless you pass another), which the judging, rank-stability and
    report-check scripts share instead of keeping their own copies.

  It has its own test suite, `scripts/test_stats.py`, run by `make test`.
- **The exact count is ~4x faster** (0.03 s at 30 items, was 0.11 s): the sign-pattern sums are
  built by doubling a list instead of enumerating each pattern. The same sums, so the same p.
  The exact interval bisects to ~1e-9 of its span, not ~1e-14: 1.4 s at 30 items, was 11 s.
  It is shown to 3 decimals.
- **`evh catalog` and `evh catalog-serve`** (`make catalog`, `make catalog-serve`).
  - **The catalog:** static pages over a project's runs, by dataset, built into
    `.build/catalog/`. Each dataset page lists every arm with its headline number, and links
    to the inspector for one arm, or for all the arms on one metric scored against one
    reference.
  - **The run inspector:** a server on 127.0.0.1 that tests any arms on one dataset against
    a baseline with `stats.py`, so it gives the same p as `pair-test` on the same pair. It
    shows the verdicts, charts of the per-item scores and differences, and, for one item,
    each arm's output beside the reference.
  - **The same rules as everywhere else:**
    - Arms on different `dataset_id`s are refused.
    - On a metric scored against a reference, an arm scored against another reference than
      the baseline's (silver against gold, say) is named and not tested against it; cost,
      latency, tokens and length compare across references.
    - The static pages carry counts and means only, never an item's text.
    - The server answers only to a 127.0.0.1 Host. It serves only the catalog and the
      data tree, and no dot-folder in either.
  - **An adapter is the only project code needed.** `catalog_adapter.Adapter` lists the
    questions both tools ask. The built-in `HarnessAdapter` reads the harness's own layout
    (`runs*/`, `runs-judged/`, `references/`): an arm is one config on one dataset, its
    repeats averaged per item. A project with another layout names its own adapter in
    `config.yaml` (`catalog: {adapter: path/to/file.py:Class}`) or passes `--adapter`.

  - **A public mode** (`evh catalog-serve --public HOST`), for a deployment behind a reverse
    proxy that serves the static pages:
    - it answers only the named host;
    - each client gets `--rate` requests a minute;
    - at most `--max-arms` arms in one comparison;
    - two computations at once, every answer cached;
    - errors never show the server's internals;
    - `--warm` computes, at start, every comparison the built catalog links to.

    `evh catalog --link LABEL=URL` adds the deployment's other sites to the nav.
  - **CSP-clean:** no inline script or style. The theme script is a file, and the legend
    colours are set from JS.

  Tests: `tests/test_catalog.py` (54 assertions), run by `make test`.
- **Goals: what an evaluation is for** (`data/goals/<goal_id>.yaml`, `schemas/goal.schema.json`).
  - **What a goal says:** who uses the output, the decision it informs, the measure that
    decides (and which direction is better), the output formats it accepts, its datasets
    and their roles, and optionally `min_items`, the fewest items a winner may rest on.
  - **Configs name their goal** (`goal:`) and may declare the `format` they ask for.
    - `experiment-run` refuses an unknown goal before it runs.
    - The run records both, outside the fingerprint: they change what a run answers, not
      what it measured.
    - `run-promote` carries both onto the baseline.
  - **`validate` V14** fails:
    - a goal that breaks its schema, or whose `goal_id` is not its file name;
    - a config, run or baseline naming a goal that does not exist, or a format the goal
      does not accept.

    A dataset smaller than a goal's `min_items` gets a note.
  - **Optional until a project opts in.** Set `required_from: YYYY-MM-DD` in
    `data/goals/policy.yaml`, and every run created from then on must name a goal. A
    project upgrading changes nothing until it sets the date.
  - **In the catalog:** a goals page, and a page per goal. On each of the goal's datasets
    it ranks the arms that record the goal's measure. An arm under `min_items` or in a format
    the goal does not accept is flagged and never the leader. Each arm links to the
    inspector, tested against the leader.
  - **This repository's six experiments have goals** (`data/goals/`), and so does the
    tutorial (`tutorial/goals/tickets_summary.yaml`). No date is set here, so nothing
    already committed is held to one.

  Tests: `tests/test_goals.py` (14 assertions), run by `make test`.
- **Item fields** (`data/fields/<fieldset_id>.yaml`, `schemas/fieldset.schema.json`, ADR-0003).
  The harness defines no field: a project declares its own in a field set, and any number of
  its datasets name it.
  - **Types:** text, number, integer, boolean, date, duration (seconds; `h:mm:ss` accepted),
    url, and choice with its values; a field can be `required` and `public`.
  - **`dataset-create --fieldset ID --fields FILE`** attaches values from a CSV or JSONL, one
    row per `item_id`, and refuses an undeclared column, a mistyped value, a value outside a
    choice, an unknown item and an empty required field. `--update-fields` corrects values on
    an existing dataset.
  - **Not the identity.** A run's fingerprint hashes item ids and bytes only, so a corrected
    field invalidates no run; the dataset records `fields_sha256` beside them.
  - **`validate` V15** fails a field set that breaks its schema, fields with no field set or an
    unknown one, an undeclared or mistyped value, a missing required value, and a
    `fields_sha256` that does not match (a hand edit).
  - **In the catalog:** each field with its coverage, and a summary of its values only when it
    is `public`. **In the inspector:** an item's fields beside its outputs; a filter on any
    field; a breakdown by a choice or yes/no field, tested per group with `stats.compare_by`.
    A public deployment answers with public fields only.
  - The adapter protocol gains an optional `item_fields(dataset)`.
- **Items fetched from a pinned URL.** `dataset-create --manifest FILE` takes one row per item:
  `item_id`, `source_url` and `source_sha256` (empty: fetched and pinned now), and field
  columns. `dataset-materialize` downloads each into `.cache/items/` and refuses bytes that
  hash to anything else, as it refuses a changed file. A transient failure is retried like a
  provider call; a host that needs a header gets it from `EVAL_FETCH_HEADERS` (that host only,
  never on a redirect elsewhere, never written into a dataset). With `--update-fields`, an
  empty cell clears a value.

  Tests: `tests/test_fields.py` (47 assertions), run by `make test`; the catalog's in
  `test_catalog.py`.
- **`evh init [DIR] [--tutorial]`** starts a project: `data/sources`, `data/configs`,
  `data/goals`, `data/fields` and a `.gitignore` for what the harness derives. `--tutorial`
  copies the GUIDE's kit (tickets, their fields, gold, arms, a goal, a judge scorer and its
  prompt, the judge panel's config) into `tutorial/`; the kit ships inside the package. It never overwrites a file.
- **`make guide-check`** (part of `make check`) runs `docs/GUIDE.md` in a fresh project, as a
  reader would, and fails when a quoted output no longer matches what the command prints.
  Lines that the unseeded `lead2_noisy` arm moves are marked in the GUIDE and not compared.
- **The tests that run `evh` install the real wheel** (`tools/_wheel.py`), built from
  `pyproject.toml`, instead of copying folders. A file the package data leaves out now fails
  them, where a copy would have included it.
- **`make browser-check`** drives the catalog and the inspector in headless Chromium: a
  tutorial project with fields, the main paths and the field controls, the phone-width layout,
  and no console error. A development extra (`requirements-browser.txt`, `make
  browser-install`), never a dependency of the package; CI runs it as its own job. The root
  `make browser-check` also drives the public site, served with production's headers.
- **`tests/test_installed_commands.py`** (in `make test`) runs every `evh` command in a
  project that pins the package; a command without a case fails it.
- **`tests/check_commands.py`** (in `make test`) checks every `make` target, `evh` command
  and flag shown in the current docs still exists: 274 of them across 27 docs today.
- **The deploy's health check** also asks the inspector the question readers send most, a
  group of arms on one metric (`infra/deploy/probe_link.sh`), and rolls back without verdict
  rows.
- **Code-quality gates**, `make quality` at the repository root and a CI job of the same name:
  ruff (lint and format), mypy, bandit, pip-audit, vulture, interrogate, codespell, shellcheck
  and actionlint, with radon's complexity report. Tools pinned in `requirements-dev.txt`
  (`make quality-install`), never a dependency of the package. What they found, and how ruff
  compares with the black, isort and flake8 that podcast_scraper runs:
  `research/internal/QUALITY_TOOLING_EXPERIMENT.md`. Every public function, class and method
  has a docstring (interrogate at 100%, the bar podcast_scraper sets). Logic kept in two or
  more copies (Spearman, Holm, the sign-flip test, module loading, the test scripts' `check()`,
  cost sums, file hashing) now lives in one place each, and every report claim re-derives
  unchanged; a test script that runs no check now fails.
- **This repository's worked examples run on patched libraries** (Linux): transformers 5.20.2,
  sentence-transformers 6.2.0, pillow 13.0.0, aiohttp 3.14.5, nltk 3.10.4, certifi 2026.10.19,
  clearing 58 published advisories in their locks; few-nerd stays on transformers 4.55.4,
  because span-marker has no transformers 5 release. `make audit-locks` audits every lock per
  platform. Every local arm was re-run against the committed record: every published finding
  holds, and all but four arms reproduce item for item (why, per arm, in the record).
  Not part of the package.

### Changed
- **A config with a key written into its params is refused** (`api_key`, `access_token`,
  `secret`, ...): it would be copied into every run record and onto the arm page. Name the
  variable with `api_key_env` instead; the catalog shows any such param as "(hidden)".
- **`success_criteria.secondary` is removed**: its entries are `axes` (UPGRADING); a goal that
  still has it fails V14.
- **Documentation never moves a fingerprint (fingerprint version 4).** Code is hashed by what it
  does: its syntax tree without docstrings, comments, formatting or `METRIC_DESCRIPTIONS`
  (assigned, or imported from a shared module). That
  holds for the adapter, the harness's measuring modules, judge_score's own hash and the examples'
  `code_digest`. A judge scorer YAML is hashed by its parsed content, and a reference manifest's
  `caveat` is outside the reference digest. Adding metric descriptions to an adapter used to make
  run-compare and the inspector call every earlier run "not the same conditions". The tree is
  serialised without empty fields, so one file hashes the same on Python 3.11, 3.12 and 3.14
  (`ast.dump` does not). v3 and v4 digests are not comparable. The committed v3 runs here were
  migrated: each recorded hash was matched to the code or reference state it came from (git
  history, unreachable objects included) and recomputed. No score changed.
- **import-run hashes the scoring code itself: `--scorer-file` replaces `--scorer-sha256`.**
  Give the file (or several, repeated in a fixed order) and the harness hashes it by the same
  rule, so a docstring in your scorer is not a new scorer. The hash is now the run's
  `instrument.adapter.sha256`, inside the fingerprint hash: before, it sat only in `imported`,
  outside the hash, so two imports scored by different versions of the code looked like the same
  conditions.
- **One install calls hosted models.** `openai` and `anthropic` are core dependencies; the
  `[llm]` extra is gone. A newcomer's first hosted arm failed on the import, and only one RUNBOOK
  section named the extra.
- **The core times every call.** `latency_ms` is recorded for any adapter that does not report
  its own (the attempt that answered, not the retries' backoff); only the bundled adapter used to
  time itself, so a project's adapter recorded no speed. **This can move a result**: a project's
  runs gain a latency column, and the leaderboard its cost/speed frontier.
- **experiment-run warns when outputs stop at `max_tokens`**, by the provider's `finish_reason`
  (the bundled OpenAI-compatible and Anthropic providers now record it) or tokens_out reaching the
  cap, naming the items: they are scored as if complete.
- **A run that stops mid-pass says what to do**: which run, after how many items, the exact
  `--resume` command, or delete it; V7's failure says the same.
- **validate V5 no longer fails two different arms that are both perfect.** On a saturated binary
  metric their per-item scores agree too; different outputs now tell two measurements from a copy.
- The inspector's item view shows the item itself (what every arm read), folded when long; the
  local inspector only. `evh inspect --item` prints it.
- Bookkeeping fields (`resumed`, the judge's `self_family_*`) stay in the record but are listed as
  metrics nowhere (leaderboard, runs-list, the spread, the inspector).
- The leaderboard's version note fires only for one arm at two versions, not for different arms at
  different versions (judge-score's too); "P(top 1)" is no longer printed beside "P(1st)" when they
  are the same; the rounding note names the scorer as what rounds.
- `evh init`'s `.gitignore` ignores `__pycache__/`; experiment-run ends "wrote N run(s) to …".
- **Exact p-values at 30 items or fewer.** `pair-test` and `family-test` now count the
  two-sided sign-flip p over all 2^n sign patterns when a pair shares 30 items or fewer, instead
  of estimating it from 20,000 seeded permutations. Above 30 items the estimate is unchanged,
  bit for bit, including `family-test`'s single stream across opponents. Near a threshold the
  estimate could land on either side of it; the count cannot. **This can move a result**:
  - **in this repository's reports:** none moved. All 200 report claims re-derive unchanged,
    because every published pair and family test is on more than 30 items;
  - **in the tutorial** (6 items): `pair-test` reads 0.0312 (was 0.0330), and the family test
    0.0938 against `lead1` and 0.3125 against `author` (`lead2_noisy`'s is unseeded and moves
    with every run). The verdicts are the same (getting started step 7, tutorial 3 step 4);
  - **in your project:** re-run `pair-test` / `family-test` on any pair with 30 or fewer
    shared items. Whether a verdict near its threshold moves depends on your data.
- `pair-test` says which it did: `(exact, all 2^n sign patterns)` or `(20000 permutations)`.
- `family-test`'s cache key includes `stats.py`, so a cached answer from 0.3.0 is recomputed.
- **`validate` V4 no longer passes what it did not check.** A materialized copy that has lost
  an item file now fails; it used to be skipped. A dataset with no materialized copy on the
  machine (materialized data is not committed, so a CI job has none) is named as not checked,
  and the ok line says how many were checked, e.g. "3 of 14 datasets materialized here". A
  project whose materialized copy is incomplete goes red where it was green.
- **The bundled adapter names its primary metric** (`PRIMARY_METRIC = "overlap_f1"`). New runs
  on it record `primary_metric: overlap_f1`. The leaderboard already ranked them by it, first
  by name; it no longer prints that the metric was "chosen by sort order", and the catalog and
  the inspector open on it. Runs made before keep what they recorded.
- **`docs/GUIDE.md` is getting started, in your own project**: install the package, `evh init
  --tutorial`, then the loop with `evh` (a dataset, arms, a reference from a run, a comparison, a
  choice). It used to run inside a checkout of this repository, with `make`, and to hold every
  step. The rest is in five tutorials (`docs/tutorials/`): a local model against a baseline, a
  hosted LLM with your own key (which variable each provider reads), a frontier model's run as
  the reference with gold and judging, experiment rounds and dataset versions, and the catalog
  and the inspector with the command behind each view. `make guide-check` runs getting started
  and the three offline tutorials, each from where getting started ends. The README and the
  RUNBOOK lead with `evh`.
- **The default metric is the one your runs recorded.** `pair-test`, `family-test`, `holdout`
  and `rank-stability` defaulted to `coverage`, the summarisation example's metric: in any
  project that does not score it they found no runs, or crashed. Without `--metric` they now
  read the primary metric the runs on the dataset recorded, and refuse, naming the recorded
  metrics, when none did.
- **`evh self-test` in a project checks the installed harness**: the paired test's own suite,
  then the tutorial end to end in a scratch folder (dataset with fields, runs, pair-test,
  rescore, validate, catalog). It used to run this repository's development suite, which
  checks this repository's reports and failed 52 checks in every project; in a checkout it
  still does.
- **A metric's direction is inferred, not remembered by a flag**, by one rule for every command
  and the inspector: a flag, else the goal the runs name, else the adapter's `METRIC_DIRECTIONS`
  (new, recorded on the run) or `import-run --asc` (a field nothing read until now), else the
  name (cost, latency and token metrics go down); V14 fails a goal that contradicts its runs.
  So lower is better without `--asc` for `pair-test`'s "A wins", `family-test`'s wins
  and "ahead", the leaderboard's order and significance block, `holdout` and `rank-stability`.
  `leaderboard --sort latency_ms` ranked the slowest arm first. p-values do not change (the
  tests are two-sided); `--asc` and `--desc` override. **This can move** a wins or "ahead"
  count, and an order, on a lower-is-better metric; no published claim is on one (200/200
  re-derive).
- **`validate` checks the project's own run directories.** V7, V8 and V9 read this
  repository's six directory names, so a project's `data/runs-adjudicated` was never checked;
  V10's scorer sources were this repository's example paths. They are project policy in
  `<data>/validate.json` (`committed`, `floors`, `scorer_sources`, `duplicate_ok`); without it
  every git-tracked `runs*` directory is checked (`validate_floors.json` is gone).
- **The package holds the harness, not this repository's tests.** The wheel shipped ~14,500
  lines of tests and report checkers; they are in `harness/tests/` and `harness/tools/` in the
  checkout. `self-test`'s own suite (`test_stats.py`) still ships. A run's `code_sha256` hashes
  the code that can move a number (the run-writing commands and what they import, read from
  the source), so editing a test no longer shows in `run-compare` as a confound; 0.4.0 runs
  record a different value from 0.3.0 runs. The deploy installs the inspector from the wheel
  too.
- **Refusals and arguments.** Every command refuses with `ERROR: …` on stderr and exit 1 (four
  printed to stdout); a command that takes no arguments refuses one with exit 2 (`validate`,
  `self-test` and five checkers ignored them). RUNBOOK: exit codes and every environment
  variable.
- **The bundled adapter refuses an unknown `provider:`** (a typo fell back to `echo` and
  recorded the echoed input as the model's output), and records what an OpenAI-compatible
  provider billed when the response carries it. One price rule for it and the judges.
- **One run record, one format; a derived run says what it was derived from.** `rescore`,
  `judge-score` and the SciFact re-parse write `derived: {kind, from, at, with}`, their own
  `created_at`, and `source_created_at`. `rescored_from`, `rescored_with`, `judged_from`,
  `judged_with`, `judge_label`, `reparsed_*` and `primary_metric_asc` are gone, and nothing
  reads them: a 0.3.0 derived run is read as a measured one. Every field the harness writes
  is declared in `metrics.schema.json`, and V1 fails a run record with any other (0.3.0's
  `import-run --asc` wrote `primary_metric_asc`, which nothing read; 0.4.0 writes
  `metric_directions`, which every command reads). `EVAL_GOALS_DIR` reads goals from outside
  the data root; `latency_s` is a speed metric, lower is better, as `latency_ms` is. A goal may name no dataset (one checked by a gate) and may set
  `direction: non_inferior`, a guard that ranks nothing (no significant drop against a baseline). `rescore` no longer records a metric it kept as
  dropped (`rescore_dropped_metrics` named whichever key a loop ended on).
- **`--resume-unverified` is gone.** `experiment-run --resume` refuses rows written before
  0.4.0 (no `_extra`); experiment-run writes `_extra` on every row, so its own rows resume.
- **The integration seam is `adapter.py` at the project root.** An arm whose config names no
  `adapter:` uses it, recorded as `adapter.py`, and the bundled adapter only when there is
  none. The docs lead with the pin and `evh init` rather than a copied `harness/`.
- **Importing the package changes nothing.** `.env` is read when a harness command starts,
  not on import, and the project's paths resolve on first use, so an adapter's tests or a
  notebook can set `EVAL_HOME` after the import. `evaluation_harness.catalog_adapter` reads
  no path at import, and its `load_adapter` is `load_catalog_adapter`.
- **Configs, judge scorers, judging sets and verdicts have schemas, and `validate` V1 checks
  them.** A config key other than `config_id`, `dataset_id`, `params`, `adapter`, `goal` and
  `format` fails (a mistyped key was read by nothing and passed).
- **A baseline carries what its number means**: `run-promote` records the run's reference
  tier, adapter and fingerprint hash, `runs-list --baselines` prints the tier and adapter, and
  V6 fails a baseline that no longer matches its run. A 0.3.0 baseline fails V6 until it is
  promoted again. Promoting replaces the baseline: the copy archived to
  `data/baselines/superseded/` and the `supersedes` field are gone, and git keeps the old one.
- **A command run from a project's subfolder finds the project**: without `EVAL_HOME`, the
  root is the nearest directory up with a `data/` folder (it was the current directory, so
  `evh validate` in a subfolder read an empty project).
- **The judge panel is a command, `evh judge`** (it sat beside the package and could not run
  from a pin); the tutorial kit ships `tutorial/judge_panel.yaml`.

### Fixed
- **V9 fails when git cannot list the committed runs.** A `git ls-files` that refused (a committed
  directory behind a link that leaves the repository) listed nothing, and V9 read that as nothing
  missing: a run with no rows passed. It now fails and quotes git's error; a project that is not a
  git repository has nothing committed, and V9 says it was not checked.
- **`silver-calibrate` no longer prints a ceiling it did not measure.** With one set of runs
  serving as both references and arms, it correlated a ranking with itself and printed "rho =
  +1.000 … from two different sets of runs". The ceiling now counts only arms whose two sides are
  different runs, and says "not measured" when fewer than three are.
- **From an external review of the core and the UI surfaces (0.4.0 candidate):**
  - **A run scored against references for only some items says so.** experiment-run took a
    reference directory as covering the dataset, so gold for 20 of 200 items gave a 20-item mean
    recorded as a 200-item gold run. It now counts coverage before any call. With no file for any
    item it refuses. With some, it warns, records `reference_coverage` on the run (schema), and
    the leaderboard names the run. **This can move a result**: a run that was refused now stops.
  - **A pair opened from a goal page's group is held to the group's family.** "test vs leader"
    passes `family=<group size − 1>`, so it is not tested as if it were the only pair. The
    inspector refuses a `family` smaller than the arms tested, and a `threshold` above alpha or
    below what the family allows, instead of obeying a URL.
  - **rescore and judge-score keep a project adapter's call-time extras** (named in the row's
    `_extra`) and `resumed`; they were dropped and reported as metrics the scorer dropped.
  - **The adapter contract:**
    - INTEGRATION gives `lower_is_better(metric, dataset)`, as the code calls it;
    - `catalog_adapter` re-exports `load_fieldset` and `fieldset_problems`, so an adapter needs
      no private `_fields`;
    - two new optional members: `arm_of(dataset, config_id)` (rounds, `inspect --round`; it
      follows `EVAL_RUNS_DIR`) and `reference_free(metric)` (from the metric's kinds, not its
      name);
    - the structured view kinds (`insights`, `nodes`, `entities`) are documented;
    - `evh rounds` reads the project's catalog adapter;
    - the inspector's default baseline is the promoted baseline's arm.
  - **A public inspector publishes text only when told.** `catalog-serve --public` served every
    arm's output and the reference text for any item, while INTEGRATION and the adapter contract
    said that text never leaves the machine. It now serves numbers, adds outputs or reference text
    only for what `--publish outputs,references` names, and never serves the item itself; the item
    view says what it withholds. **This can change a deployment**: one that relied on the old
    behaviour adds `--publish`. This repository's own publishes outputs (already public in the
    repository), not references.
  - **The catalog opens on the whole project, and every name is a link.**
    - **Home is a dashboard:** counts (goals, datasets, configs, arms, references, metrics, runs,
      USD billed, tokens), each goal's answer at a glance (its baseline, the leader of the gold
      group and the paired test between them), activity and spend side by side (spend in USD or
      in tokens, so a free local model's use is tracked too), what each dataset covers, and
      everything recorded; each for the last 14 days of activity or all time. `evh overview`
      prints the same.
    - **New pages:** Datasets (what the home page listed) and References in the menu; a page per
      arm (its metrics, runs, config without credentials, conditions, the same config scored other
      ways, its rounds; `evh arms --arm`) and per metric (what it measures and how, which way is
      better, its kind, the goals it decides, every arm recording it with a strip chart;
      `evh metrics --metric`).
    - **Links everywhere:** arms, metrics, datasets, references and goals link to their pages
      from every page and table, a reference's author to its arm, a round's configs to theirs; in
      the inspector, arm names and the metric open their pages.
    - **Metric explanations:** the harness explains its own metrics at length; a project's
      `METRIC_DESCRIPTIONS` value may be `{"summary": ..., "details": ...}` for its metric pages.
    - **The catalog adapter** gains optional `arm_runs`, `arm_config` and `spend`.
    - **From the second newcomer run:** the inspector warns when the baseline wrote the reference
      the arms are scored against; a judged arm's item shows each judge's score beside the output;
      the goal page says what "filed" means.
  - **One provider layer for the systems under test and the judges, keys by role.** The bundled
    adapter, judge-score's judges and the judge panel call hosted models through one module,
    `_providers`: `openai` (OpenAI or any compatible endpoint), `anthropic`, `openrouter` and
    `litellm`, each taking `model`, `base_url`, `api_key_env`, `temperature` and `max_tokens`.
    - **A judge goes where its `provider:` says.** Judges ignored it and went to a LiteLLM
      proxy if `LITELLM_BASE_URL` was set, else to OpenRouter with an alias looked up in
      `models.json`, while the record said the declared provider. The scorer schema now
      requires `provider` on every judge. **This can change a setup**: re-running the
      committed scorers (`provider: litellm`) needs a LiteLLM proxy.
    - **Judging can have its own keys.** A judge reads every variable as `EVAL_JUDGE_<NAME>`
      first, then `<NAME>`, so it runs on separate keys, budgets and spend logs, or shares the
      experiments' with no setting. `evh env-check` shows what each role reads.
    - **A key is not identity.** `api_key_env` is left out of a run's fingerprint and a judge's;
      no committed hash moved (all 2,800 committed verdicts keep their `judge_fp`).
    - **judge-score names each judge's route and key**, dry run included, and stops before any
      call when a key or address is missing.
    - **The judge panel's judges are declared like judge-score's** (`id`, `provider`, `model`,
      prices). It called only Anthropic, priced Sonnet in code, and ran the fake judge when
      `ANTHROPIC_API_KEY` was missing; the fake judge now runs only with `--use-fake-judge`.
    - **Anthropic takes `base_url` and `api_key_env`** like the others. **Arms pass `reasoning`,
      `reasoning_effort` and `provider_routing`** to the request as judges did, and record
      `reasoning_tokens` (descriptive, as every committed run declares it), the model and the
      host that answered.
  - **The harness imports itself as a package.** Its modules imported each other as bare
    top-level names (`import stats`) with their own directory on `sys.path`, so a project's own
    `stats.py` first on the path replaced the harness's paired test inside
    `evaluation_harness.judging`. Under `evh`, the harness's `adapter`, `stats` or `rounds` could
    also hide a project's module of that name. They now import `evaluation_harness.*`, and nothing
    of the harness goes on `sys.path`. In a checkout `harness/evaluation_harness` links to
    `scripts/`, and `python scripts/x.py` still runs. A project script that relied on the
    harness's directory being on the path writes `from evaluation_harness.adapter import Result`,
    as INTEGRATION documents.
  - **The public server trusts no client header unless told** (`--client-header NAME`); a
    spoofed `CF-Connecting-IP` no longer buys a fresh rate bucket. The deployment names
    Cloudflare's header (origin lock).
  - **The rest of the page features have commands:** `evh inspect --no-rescore` (the inspector's
    box), its "Average only" table, and the dataset page's fields block in
    `evh datasets --dataset-id`.
  - **Statistics, consistently:**
    - `family-test` marks an estimated p (~) when a family mixes exact and estimated rows;
    - pair-test separates at `p <= threshold`, as Holm and the inspector do;
    - the bootstrap ties ranks with the same tolerance as the within-item ranks;
    - runs that disagree on a direction or a primary metric are named;
    - rescore refreshes `metric_directions`;
    - the inspector and `evh inspect` show each row's 95% interval of Δ (exact up to 30 items, a
      t interval above, as its docstring now says).
  - **Accessibility:** a sortable column's header works from the keyboard and states `aria-sort`;
    every chart mark with a tooltip carries an SVG `<title>`.
  - **Messages:** rescore's missing-reference message no longer sends a project to
    `examples/`; RFC-002 tells `_extra` (adapter extras) from `_meta` (provider metadata).
- **From the second newcomer run** (`/work/evh-scenario-040`; SCENARIO, 0.4.0 candidate):
  - **A baseline promoted from one of an arm's repeats** records every repeat and their mean
    under `repeats`, and `run-promote` prints the two side by side. The catalog, the inspector
    and the tests read the mean; `scores` stays the run's own (V6).
  - **A judged run keeps its source's cost and speed kinds**, so the judged leaderboard has its
    frontier. That leaderboard also prints the judging pass's agreement and its position and
    noise checks, from `summary.json`.
  - **The arm that wrote a silver reference is left out of the ordering test and the frontier**,
    and the leaderboard says so (its row measures agreement with itself).
  - **A judge reply that is not committed** (not bare JSON, or repeating the source) keeps its
    text in a git-ignored `.withheld/` beside its record, and the log names the file. An
    unparsed reply's cause can then be read; the record keeps only the hash (V12).
  - **The dataset page and `evh datasets`** sort arms by what they are scored against (gold,
    silver, a judge, nothing) before the mean. A silver and a gold mean no longer interleave.
  - **The goal page and `evh goals --goal`** show a judge's group, read on its own score. `evh
    goals --goal` also lists the rounds and marks retired arms.
  - **One p format everywhere** (`stats.fmt_p`: four decimals, `<0.0001` below that).
    `family-test` says whether p is exact or a seeded estimate. Above 30 items it draws one
    random stream for the family, so `pair-test` and the inspector, which estimate one pair at a
    time, can differ in the third decimal. Its wins column is labelled `A wins`.
  - **Round messages:**
    - `round-open --keep` says carried arms need no change and no new run;
    - `evh rounds` does not suggest promoting the run that is already the baseline;
    - `leaderboard --round` does not warn about two versions of an arm in a round that compares
      them.
  - **`evh cost-report` sees the bundled adapter's bills.** A provider's bill (OpenRouter, or a
    LiteLLM proxy passing it through) was the run's cost but was not kept where cost-report reads
    it, so every run read as "price table only". It is now kept in the item's `_meta.usage.cost`.
  - **`evh inspect --item`** prints which run each output is from and, for a repeated arm, that it
    is the latest of N repeats beside their mean (as the page does). `evh datasets` counts configs.
  - **Smaller items:**
    - `experiment-run` prints what the command spent, and its repeat spread calls cost and speed
      what they are, not "deterministic";
    - `judge-score` says its spend is the provider's bill where one is reported, else the price
      table;
    - `silver-calibrate` explains rho and sibling lift;
    - the catalog counts the configs behind its arms;
    - "filed" reads "filed under this goal";
    - the item view says it shows the latest of N repeats beside their mean;
    - judged arms keep their version in the inspector;
    - a heading scrolled to is not hidden under the header;
    - `env-check` names the example arms only in a checkout;
    - the tutorial scorer points at tutorial 3.
- **One reference per table and per arm.** The leaderboard averaged an arm's runs whatever they
  were scored against: a silver 0.90 next to a gold 0.24, in one table labelled silver. It now
  prints one table per reference, gold first, each with its own tests. The catalog, the
  inspector and `evh rounds` read an arm against the reference of its latest run (by
  `created_at`), and they name the earlier runs they leave out. A judged run is grouped by its judge,
  not by its source run's reference. `evh rounds` reads a round against the reference most
  of its arms use and names any arm scored against another. This repository's data, the
  trial and the podcast project have no such arm.
- **`provider: openrouter` uses OpenRouter.** It read `OPENAI_API_KEY` and called OpenAI's
  address unless the arm set both `base_url` and `api_key_env`. It now reads
  `OPENROUTER_API_KEY` and calls `https://openrouter.ai/api/v1`, and an arm's own values still
  win.
- **`evh inspect --round` reads the round as `evh rounds` does:** on the goal's measure, against
  the round's leader. It defaulted to the first arm, so an arm with no score became the
  baseline and the metric fell back to `cost_usd`. Arms with no score are named and left out.
- **The bundled adapter stores `overlap_f1` as computed.** It rounded the value to 6 decimals,
  which made ties that are not there (the leaderboard warned about its own example). **This can
  move a result** only where two arms tied at the sixth decimal.
- **Hints and messages:**
  - with no reference, `experiment-run` names `reference-create --from-run` first;
  - `evh --help` describes `reference-create` as "from a run or with a config";
  - `env-check` and the `litellm` provider no longer tell a pinned project to copy a
    `.env.example` it does not have;
  - `run-promote` no longer prints `resumed` and `self_family_*` among the scores (the baseline
    file still keeps them);
  - inspector notes are no longer all labelled "Re-scoring";
  - the bundled adapter and `dataset-create --help` describe what the code does now, not its
    history.
- **A judge scorer must state its position and noise checks.** ADR-0001 makes them part of the
  pass, not optional, but a scorer that left `protocol.position_check_fraction` or
  `noise_check_fraction` out ran with them off. Both are now required. The noise check must be
  above 0, and so must the position check whenever a call sees more than one output (a pointwise
  scorer has no order to check). `judge-score` and V1 refuse a scorer that breaks this.
- **A round is read against the arm that wrote its silver reference.** `evh rounds` and the goal
  page now compare the leader with the previous round's best, the baseline and, new, the
  frontier arm whose outputs became a silver reference of the dataset. Cost per item is shown
  for each of those arms. That arm is the yardstick, so it is never suggested for retirement.
- **The inspector reads only arms and references the catalog lists.** It asked the
  adapter's `arms_of` about any path a request named; an adapter that maps a path to itself
  (the podcast repo's did) let `compare` read outside the data tree (`runs=../../.git`). A
  request may name an arm, or a path that selects arms (a run directory), but only arms the
  adapter's `arms()` reach, and a reference `references()` lists.
- A catalog nav entry may carry a CSS class as a fourth element (`hide-sm` hides it on a
  phone), and the inspector page names the command that serves it (`serve`).
- **`evh rescore` and `evh silver-calibrate` in a project that pins the package.** A run
  made with no `adapter:` uses the bundled adapter and records it as `scripts/adapter.py`, a
  path that exists only in a checkout, so both failed with "adapter not found" in every pinned
  project on the default adapter (0.2.0 and 0.3.0 alike). They now score with the package's
  own copy, the one that made the run, through one shared lookup. Found by following the GUIDE
  in a brand-new project.
- **The "next, run this" hints name a command you have.** Every one said `make …`, a target
  only a checkout of this repository has; through `evh` they now say `evh …` (the first was
  GUIDE step 1's "Next: make dataset-materialize"). Two were wrong in a checkout too: an empty
  baselines list suggested `make promote` (the target is `run-promote`), and an empty runs list
  suggested `make demo`, which a project without the bundled sample data cannot run.
- **`evh catalog-serve` on a port another program holds** says so and suggests `--port`,
  instead of a Python traceback.
- **`rescore` onto another reference no longer claims the references changed.** Moving runs
  from silver to gold (`--reference-id`) compared the gold files' hash with the silver files'
  and, as they always differ, wrote `references_changed_since_measurement: true` into every
  re-scored run and printed "the reference files have CHANGED". The move is recorded as
  before (`reference_id_at_measurement`); the flag and the warning are kept for the same
  reference's files changing. No committed run in this repository carries the false flag.
- **Commands that assumed a checkout**, each found by running every `evh` command in a
  project that pins the package:
  - `rank-stability` crashed (`set.intersection()`) instead of saying no arm had the metric;
    on a lower-is-better metric it named the worst arm the leader; with too few items for two
    halves it now says so.
  - `--exclude-dataset` (`pair-test`, `family-test`, `holdout`, `bootstrap-test`) read
    `data/sources/<id>/*.txt` instead of the dataset file: wrong for any item that is not a
    .txt, any dataset from a manifest, any project keeping sources elsewhere, and "nothing
    excluded" was then reported as true.
  - The leaderboard's metric kinds, `run-compare`'s, and the classification report's label
    parser looked for a run's adapter in the checkout only; they now find the bundled one in
    the package, as `rescore` does.
  - `bootstrap-test` on a gold set of free text (summaries) treated every summary as a class
    and would have reported a macro-F1; it now refuses, and its "too few items" refusal names
    the threshold and the opponents.
  - `catalog-serve` printed its address without flushing, so under a log file or a process
    supervisor the line did not appear; `--build-dir` outside the project was a traceback,
    now a refusal; `self-test --help` ran the whole suite instead of printing help.
- **The catalog counted a dataset's items from the harness's own path**, not the adapter's,
  so a project with its own layout got "the most items any arm scored". It now asks the
  adapter (`dataset_items`, optional).
- **The bundled adapter's `anthropic` provider failed every call** with the anthropic SDK 1.x,
  which dropped the `temperature=` keyword: a TypeError before the request was sent. The
  temperature now travels in the request body, so the request is the one every SDK version
  sends. A self-test checks the call against the installed SDK's own signature. Found by mypy.
- **A manifest URL could read a local file.** `dataset-create --manifest` fetched any scheme
  `urlopen` accepts, so a `file:///…` row was copied into the item cache and pinned, although
  a dataset's schema allows only http(s). Every fetch now refuses other schemes before reading
  anything. Found by bandit.
- **The judge panel judged placeholder text.** Every finalist, real runs included, was scored
  on "Synthetic item i for <run>". It now reads each finalist's stored outputs, finds runs
  where every command does (`EVAL_RUNS_DIR`, the project), ranks by their primary metric, and
  refuses a lower-is-better one rather than promote the worst.
- **`rescore` could record the bundled adapter's metric kinds** in a project's run: two
  registries named loaded adapters differently, and the lookup fell back to the bundled one.
  One loader (`_adapter.py`), keyed by the resolved file.
- **`import evaluation_harness.judging` failed** in an installed package (`No module named
  'stats'`), and importing `catalog_adapter` beside it loaded `_common` twice.
- **`holdout`'s significance block had no direction**, so on a lower-is-better metric it ranked
  the worst arm first.
- **Checks that could not fail, or did not run:** `self-test`'s cost-cap control turned any
  failure into a skip; `check_terminology` was failing and nothing ran it (it is in `make test`
  now); `make -C harness docs` was a no-op (eight targets were not `.PHONY`).

## 0.3.0 — 2026-10-21

Re-measure what you already have. Stored outputs can now be scored again by LLM judges, as an
optional pass that never touches a committed run: `evh judge-score`, for any text task you
declare (what an item is, what the outputs are, the dimensions, the scale). The harness refuses
a judge until the scorer names, for each judge, a committed run that measured it against human
ratings; it runs at least two judges from different vendors blind, measures their position bias
and noise, and stores every verdict so a rerun costs $0. The tutorial has an offline, $0
judging step (GUIDE step 10). Upgrading from 0.2.0 changes no committed run or score and adds
no dependency. Design: [ADR-0001](https://github.com/chipi/eval-harness/blob/main/docs/adr/ADR-0001-judge-scorers.md);
what it found here: the [judging page](https://evals.humancopilot.eu/experiments/judging.html).

### Added
- **`evh judge-score`** (and `make judge-score`). Re-measure an experiment's frozen outputs
  with a validated LLM judge, billed, cost-capped and resumable. It runs from the installed
  package in a project that has only its own data directory, scorer, prompt and runs: the
  prompt builder, reply parser, tau-b and Spearman, and an OpenAI-compatible judge client
  (LiteLLM proxy, OpenRouter direct, per-judge `base_url` / `api_key_env`, billed cost read
  from the response, retries) are in `evaluation_harness.judging`, with no dependency on
  `examples/`.
- **The judge scorer artifact** (`data/scorers/<id>.yaml`): two or more judges from different
  vendor families, the task, the prompt (with its sha256), the protocol, a `validation`
  block and a cost cap.
- **Any text task, declared in the scorer.** An optional `task` block names what each item is
  (`source_label`), what the arms wrote (`output_label`), the `dimensions` the judge scores
  and the `scale`; a prompt writes `{n}` where the number of outputs per call goes. Without a
  `task` block a scorer judges SummEval's news-summary task (ARTICLE, SUMMARIES, four
  dimensions, 1-5), byte for byte as before. A declared task is hashed into the judging set.
- **A judging step in the tutorial** (`docs/GUIDE.md` step 10):
  `harness/tutorial/scorers/tickets-judge-v1.yaml` re-measures the tutorial's arms with two
  fake judges, offline and $0,
  through the refusal, the dry run, the pass and the leaderboard.
- **A validation gate.** A scorer runs only if its `validation` block names a committed run
  for each judge whose metric equals the stated value (and is at least `min_metric`, when the
  scorer sets one) and whose model, temperature, reasoning, provider, max tokens, prompt file
  and prompt sha256 are the judge's. The gate checks that a validation exists and is current,
  not that it transfers to your outputs. Otherwise `--unvalidated` runs it and labels every number
  "unvalidated judge". `provider: fake` judges (offline, free, for testing a scorer) can never
  pass the gate.
- **Judging sets and stored verdicts.** One item is the article plus every arm's output, arm
  identities hidden, order shuffled by a seed; the set is hashed into its id and frozen in
  `data/judging-sets/`. Every reply is stored per call in `data/judge-verdicts/`, with its
  scores, so a rerun resumes and re-reading costs $0; a reply that is not bare JSON scores, or
  repeats 8 consecutive words of the item or an output, is kept only as its hash, since a
  judge that reasons aloud can copy the source. A different arm set is a new set, never an
  append. A block retried with `--retry-unparsed` keeps the earlier calls' cost in its record.
- **Controls.** A position check (a second shuffle that re-forms the blocks) and a noise check
  (a repeat on a subset), plus per-judge agreement and a self-family flag, in `summary.json`.
- **Adjudicated gold re-measurement** (repository tooling, `examples/_shared/adjudicate.py`,
  not in the package): a committed adjudication file overwrites only the disputed items of a
  local gold reference set to make a new reference version, and `rescore` re-scores every run
  against it for $0, the old reference kept beside it.
- **Judge validation on published human ratings** (repository tooling, not in the package):
  `validate_judge_goyal.py` (Goyal, Li & Durrett 2022) and `validate_judge_zhang.py` (Zhang et
  al. 2024, crowd ratings of 19 LLM-era summarisers) check a scorer's judges against people.
  The ratings are downloaded when the check runs, pinned by sha256, and never committed; the
  committed records hold article ids, the judges' replies and scores, and hashes; a reply that
  is not bare JSON scores, or repeats 8 consecutive words of the source, is kept only as its hash.
- **`validate` V11-V13.** V11: every judging set's stored hash is the hash of its content.
  V12: every stored verdict names a real set, item, pass and block, and its `n` is that
  block's size, and every committed judge reply (verdicts and validation records) is bare
  JSON or kept only as its hash. V13: every judge scorer loads, is structurally valid (its `task` included),
  and its prompt file resolves and renders. They read the configured data directory.
- **`judge-score` judges every arm on the dataset by default.** A scorer's `arms_match`,
  `--match` and `--arms` narrow it, and it warns when the arm set mixes config versions (`_v1`
  and `_v2` of one arm are judged as two arms).
- **A scorer's `prompt.file` resolves against the project root**, then the scorer file's own
  directory, then (in a checkout of this repository only) the repository root.
- **Judged runs carry no `reference_tier`**, since a judge reads no reference: the source
  run's tier is kept as `judged_with.source_reference_tier`, and `leaderboard` says the scores
  come from a judge, with its label.
- **A refused judge call stops the pass cleanly.** A call refused, or still failing after its
  retries (a provider's own budget guardrail answering 403, for example), stops the pass the
  way the cost cap does: every stored verdict is kept, the partial result is projected and
  labelled, and the same command resumes.
- **Scorer checks.** `task.scale` must be whole numbers, and a prompt with both `{n}` and
  SummEval's fixed count phrases is refused (the phrases would keep saying 16). V13 renders
  each prompt at 2 outputs, so a prompt that cannot be rendered fails there, not at run time.
- Experiment-level results this enables are reported in the repository's reports (the
  summarisation experiment re-measured with two pairs of SummEval-validated judges, not confirmed by people on those outputs; AG News and DBpedia
  against adjudicated gold); none of them is in the package.

### Changed
- **`leaderboard`'s precision note** no longer fires on values that are exact small-integer
  fractions (a mean of 1-5 ratings over two judges and four dimensions is in eighths); scores
  rounded on the way to disk still get it.
- Nothing that scores a run changed: committed runs and their recorded hashes are untouched,
  and the committed summarisation judging set rebuilds from its stored verdicts with the same
  id.

## 0.2.0 — 2026-10-20

The first version meant to be installed rather than copied: pin a release tag, run `evh`, and
your project's data stays in your project, never in the installed package. Runs now record
which harness produced them, other tools' scores can be imported as runs, and the paired tests
handle lower-is-better metrics.

### Added
- **Installable package.** `pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.2.0#subdirectory=harness"`
  gives the `evh` command: every Makefile target, running the same scripts.
- **`EVAL_HOME` / `EVAL_DATA_DIR`.** The project's data lives in the project, never in the
  installed package; the data root can be nested (for example `data/eval/stats`).
- **The harness identifies itself in every run.** `fingerprint.instrument.harness` gains
  `version`, `code_sha256` and `installed`.
- **`evh import-run`.** Per-item scores produced by another tool become a run the
  significance tests read, with the source, the scorer and the sha256 of the imported bytes
  on the record.
- **`--asc` for `pair-test` and `family-test`.** For lower-is-better metrics, "wins" and
  "ahead" count the lower score. The p-values were already two-sided and do not change.

### Changed
- `validate`'s V9 evidence floors are read from `<data>/validate_floors.json` (project
  policy) instead of being hardcoded for this repository's run directories.
- The `family-test` cache lives under the project root, not beside the code.

## 0.1.0 — 2026-10-19

The harness as first published with its six worked experiments, before it was packaged: a copy
you take into your project rather than install. Frozen, hash-checked datasets; one adapter
function for your system; runs that record their data, prompt, code, model and build; each
arm's own noise; paired tests with Holm correction that say separated or tied; billed cost
beside quality; re-scoring from stored outputs for $0; validation that fails CI; baselines
promoted only with a reason. Tagged afterwards, at the commit the site was deployed from on
2026-10-19 (`9454f19`), so a project that took a copy that week can name what it took. What
changed between this copy and 0.2.0, including fixes that can move results:
[UPGRADING](https://github.com/chipi/eval-harness/blob/main/harness/docs/UPGRADING.md).
