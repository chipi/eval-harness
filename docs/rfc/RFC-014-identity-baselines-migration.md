# RFC-014: Identity in 0.5.0: baselines, fingerprint version 5, run ids, one grammar, the migration

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-013](../prd/PRD-013-identity-and-ties.md) (FR1, FR2, FR4, FR7, FR8),
  [PRD-011](../prd/PRD-011-evidence-registry.md) (FR1, the baseline record)
- **Related RFCs**: [RFC-001](RFC-001-fingerprint-and-code-identity.md) (the fingerprint, version 4),
  [RFC-002](RFC-002-run-records-and-derived-runs.md) (run records), [RFC-003](RFC-003-catalog-adapter.md)
  (the catalog adapter's `baselines()`), [RFC-004](RFC-004-experiment-rounds.md) (rounds),
  RFC-012 (baseline evidence and export), RFC-015 (the statistics, and the prior use of heldout datasets the migration records)
- **Code**: `harness/scripts/_fingerprint.py`, `promote_baseline.py`, `rounds.py`, `experiment_run.py`,
  `import_run.py`, `compare_runs.py`, `validate_tree.py`, `catalog_adapter.py`, `catalog_serve.py`,
  `catalog_build.py`, `list_runs.py`, `_common.py`, `site/figures.py`; new `harness/scripts/_ids.py`,
  `_lock.py` (one exclusive-create lock helper for every record that parallel commands write),
  `baseline_rollback.py`, `harness/scripts/migrate_0_5_0.py`

## Abstract

Four identity changes, and the one-time script that moves committed data to them. A **baseline** becomes
the current **baseline** of a goal on a dataset, stored as numbered versions with a pointer to the
current one. The fingerprint becomes **version 5**: the host's label, kernel, processor string and CPU
count move to a `machine` block outside the hash, while what can change a result (platform, Python,
accelerator stack) stays inside; an imported run's whole host block moves outside; the fields the hash
excludes become an explicit, versioned list; and `validate` recomputes every hash. **Run ids** gain
milliseconds and a random suffix, and creating a run refuses an existing directory. One **grammar**
(`kind:path/n`, `kind:path@alias`) names every versioned thing. **`harness/scripts/migrate_0_5_0.py`**
migrates this repository and the podcast project in ten checked steps.

## Problem Statement

- A baseline is per dataset (`<dataset_id>_baseline`, `promote_baseline.py:141`), so two goals on one
  dataset share it; former baselines live only in git; several catalog paths pick "the last baseline for
  a dataset" without the goal.
- The fingerprint's hash covers `host.label` and the rest of `_host_identity`
  (`_fingerprint.py:258-273, 370`), so the same arm on two machines reads as uncontrolled; the hash
  excludes only its own field (`_hash_of`), and nothing recomputes it.
- Run ids are `<config_id>_<timestamp to the second>` (`experiment_run.py:586`, and separately
  `import_run.py:166`); the run directory is created with `exist_ok=True` before the pass (`experiment_run.py:725`):
  two runs started in the same second share a directory.
- Ids of different things use colons and slashes inconsistently (`imported:<scorer>`,
  `gold/ag_news_200`, run ids repeated across runs directories).
- 0.4.0's data changes were one-off scripts kept outside the repository.

## Design

### Baselines per goal and dataset

**Storage.** `data/baselines/<goal>/<dataset>/<n>.json`, one file per version (n = 1, 2, …), and
`data/baselines/<goal>/<dataset>/index.json`:

```json
{"goal": "news_summary_cnn", "dataset": "cnn_dailymail_200", "current": 3,
 "history": [{"version": 1, "at": "...", "by": "..."}, {"version": 2, "...": "..."},
             {"version": 3, "at": "...", "by": "...", "replaces": 2}]}
```

The goal is `_` for a goal-less run's baseline (`data/baselines/_/smoke_v1/`). No symlinks (Windows,
`core.symlinks=false`); the pointer is a field, so moving it back to an earlier version is a recorded
history entry (`{"version": 2, "at": …, "by": …, "rollback_from": 3, "reason": …}`), not a file rename.

**A version's record** (`schemas/baseline.schema.json`, replacing `baseline.schema.json`): `id`
(`baseline:<goal>/<dataset>/<n>`), `goal`, `dataset`, `version`, `promoted_from` (the run, named with its
runs directory, `run:runs/<run_id>`), `promoted_at`, `actor` (PRD-012 FR3), `reason`, `scores`, `build`,
the fields `carried()` keeps today (`reference_tier`, `adapter`, `fingerprint_hash` (version 5), `format`),
`repeats` when the arm has them, `replaces` (the version current at promotion, absent for a first; after a
rollback that is not n − 1), `round` (when promoted by `round-close`), and `evidence`
(the comparison frozen at promotion; its shape is RFC-012's, its tests RFC-015's). A migrated version
also has `migrated_from` (the 0.4.0 baseline id and its version-4 `fingerprint_hash`).

**Commands.**

- `run-promote --run <run> --reason "…" [--goal G]`: the goal defaults to the run's; a run without a goal
  promotes to `_`; `--baseline-id` is removed (a custom id was the one ambiguity the data model allowed).
  `--run` takes an id (`run:runs/<run_id>`), a runs directory and id (`runs/<run_id>`), or a bare run id,
  which must name exactly one run across the runs directories (else refused, `ambiguous-run`, listing them).
- **Writing a version** (`_lock.py`): under an exclusive lock on `data/baselines/<goal>/<dataset>/.lock`
  (created with `O_EXCL`, holding the pid and host; a lock older than 60 s whose pid is gone is taken over),
  n = 1 + the largest version among the files on disk and the index's history; `<n>.json` is created with an
  exclusive create, then `index.json` is rewritten atomically (temp file and rename) with `current: n`. Two
  promotions never get one n, and an interruption leaves the old pointer valid. A version file missing from
  the history is an interrupted promotion: `validate` reports it, and the next promotion records it in the
  history as `{"version": n, "interrupted": true}` and never makes it current.
- `baseline-rollback --goal G --dataset D --to N --reason "…"` moves `current` back to an existing version
  under the same lock, recorded as a history entry. It needs consent as promotion does (RFC-013).
- The checks `run-promote` has today (unknown build, dirty tree, a reason that is a sentence) are
  unchanged.
- `round-close --promote` calls the promotion in-process (not as a subprocess, so the goal, the actor and
  consent pass through as they are), then saves the round. The baseline version records its `round`; a
  `round-close` re-run after a failure between the two finds the version naming this round and does not
  promote again.
- `evh baselines` (RFC-012) lists them.

**Readers.** One function, `_common.baseline(goal, dataset) -> record | None` (and `baselines()` for all),
replaces every direct read of `baselines/`: `rounds.py:86-95` (the baseline a round starts from: the
round's goal and dataset), `validate_tree.py:143, 368, 1009` (schema and V6, now over baseline versions),
`list_runs.py:34` (`runs-list --baselines` lists current baselines), `catalog_adapter.py:666-690`
(`baselines()` keeps its name and shape for the adapter protocol and gains `version` and `id`; it returns
current versions), the harness Makefile's `run-promote` target. The catalog's "last baseline for a dataset"
reads (`catalog_build.py:586, 664, 1239, 2236`, `catalog_views.py:119`, `catalog_serve.py:428-431`) filter by
goal; a page without a goal (a dataset page) shows each goal's baseline on that dataset.

### Fingerprint version 5

```text
fingerprint = {
  version: 5,
  instrument: {...},                       # unchanged
  system_under_test: {model, libraries},   # unchanged
  data: {...},                             # unchanged
  host: {platform, python, accelerator},   # in the hash
  arm: {config_id, params, prompts?},      # prompts per PRD-009 FR1.2
  machine: {label, release, processor, cpu_count},   # NOT in the hash
  hash: "...",
  # also outside the hash when present:
  hash_v4, imported, imported_by, hash_invalid_because
}
```

- `_fingerprint.HASH_EXCLUDES[5] = ("hash", "hash_v4", "imported", "imported_by", "hash_invalid_because",
  "machine")`; `_hash_of(fp)` drops `HASH_EXCLUDES[fp["version"]]`. Version 4 excludes `("hash", "imported")`,
  since `import_run.py:209` adds `imported` after hashing.
- `host.accelerator`: what the adapter's `fingerprint(params)` hook declares under `accelerator`
  (`{"cuda": "12.4", "driver": "550.54", "torch": "2.5.1"}`), else `{"declared": false}`; a migrated run
  has exactly `{"recorded": false}` (one literal, since it is inside the hash; the catalog explains it).
  Never inferred from `system_under_test.libraries.torch`.
- An **imported run** (`import_run.py`) puts all six of `_host_identity`'s fields under `machine` and none
  under `host`, and moves `system_under_test.libraries` and `instrument.harness` to `imported_by: {libraries,
  harness}`, outside the hash: all of them describe the machine and the harness that imported it, not the
  ones that measured. The scorer's identity (`instrument.adapter`, `imported:<scorer>`) stays inside.
- **V17** (validate): every fingerprint with a non-null hash has `hash == _hash_of(fingerprint)`; every
  version-5 fingerprint has `version`, `host`, `machine` and no unknown top-level key.
- **`run-compare`** (`compare_runs.py:68, 77-89`): differences under `machine` are reported as "different
  machine" and do not make the comparison uncontrolled on quality; they flag speed and cost axes.
  Differences under `host` still do.
- **The conditions check** (`catalog_adapter.py:216-219`, `catalog_serve.py:561`): `machine.*` conditions
  read `machine` (and `host` for platform and Python); latency across different `machine.label`s keeps its
  warning. `catalog_build.py:505-507` and `site/figures.py:226-233` read `host.platform` and
  `machine.cpu_count`.

### Run ids

`<config_id>_<YYYYMMDDTHHMMSS.fff>Z_<4 hex>` (UTC, milliseconds, `secrets.token_hex(2)`), e.g.
`cnn_bart_l_v1_20261026T153757.123Z_7f3a`, made by `_ids.new_run_id(config_id)`, which `experiment_run` and
`import_run` both use. Repeats append `_r<i>` as today, and the hex suffix can never match `_runs._REPEAT`
(`_r\d+$`), since it is four hexadecimal characters that cannot be `r`. `--run-id` still names a run explicitly.
**Creating a run refuses an existing directory**: `run_dir.mkdir(parents=True, exist_ok=False)` where the
directory is first created (`experiment_run.py:725`, before `outputs/` and `run.json`); the later `mkdir` calls
(`:752`, `:760`) stay as they are, since the directory is the run's own by then. On `FileExistsError` with a
generated id, a new suffix is drawn (up to 3 times); with `--run-id`, the run is refused (`run-exists`).
`import_run.py:168-170` already refuses an existing directory. `--resume <run>` already replays a run's outputs
into a new run, so nothing needs to write into an existing one. A job (RFC-011) records each **attempt**'s run id
when it is queued; a resumed job's next attempt resumes from the last attempt's run.

### One grammar (`_ids.py`)

`<kind>:<path>/<n>` names a fixed version; `<kind>:<path>@<alias>` a moving pointer; `<kind>:<path>` a thing
that is not versioned.

- **Kinds** (closed): `prompt`, `baseline`, `run`, `study`, `trial`, `round`, `reference`, `dataset`, `goal`,
  `jobset`, `look`.
- **Path**: one or more segments joined by `/`. A segment is `_` or `[A-Za-z0-9][A-Za-z0-9_.-]*`, compared
  case-sensitively, and never all digits (so the version is unambiguous); `_` is the goal-less goal. Upper case
  and `.` are allowed because every existing run id has them (`…T153757Z`, 256 of 259 run directories here);
  names the harness derives itself (prompt names, RFC-009) are lower case.
- `baseline:<goal>/<dataset>/<n>` and `baseline:<goal>/<dataset>@current`; `prompt:<name…>/<n>` and
  `prompt:<name…>@<alias>`; `run:<runs dir>/<run_id>`, where `<runs dir>` is the runs directory's own name
  (`runs`, `runs-linux`, `runs-silver`; the directory is part of the path, since derived copies share run ids;
  `config.yaml` maps names to paths, so a runs directory outside the data directory has a name too);
  `round:<goal>/<round_id>`; `study:<goal>/<study_id>`; `trial:<goal>/<study_id>/<k>` (a trial is numbered, so
  it is written as a fixed version of its study); `reference:<tier>/<dataset>`; `jobset:<set id>`;
  `look:<dataset>/<k>`.
- `_ids.parse(text) -> Id(kind, path, version, alias)` and `Id.__str__`. `validate` V18 checks the fields listed in
  `_ids.ID_FIELDS` (each record type's fields that hold an id), not every string. A run's own `run_id` in
  `metrics.json` is its name, not a reference, and stays bare. The migration converts the references that were
  bare (rounds' `baseline` and `conclusion.promoted_run`) to ids. Existing dataset and goal ids already fit.
  Strings that only look like ids and are not (`imported:<scorer>` in an adapter id, a judge's `judge:<scorer>`)
  are fields of their own and are not parsed as ids.

### The migration script (`harness/scripts/migrate_0_5_0.py`)

Shipped in the package (so a project that installs the harness has it) and run with Python
(`python -m evaluation_harness.migrate_0_5_0 [--dry-run] [--yes]`), not an `evh` command. It reads the
project's directories as the CLI does (`config.yaml`, `EVAL_*`).

**Re-runnable.** Each step detects, per record, whether it is already done (a version-5 fingerprint, a baseline
version with `migrated_from`, a `prior.json`) and skips it, so a run that crashed half-way is
finished by running it again, and a second run on migrated data changes nothing. The tag is reused when it
already points at the commit the migration started from; otherwise the script refuses with both commits.

1. **Pre-flight** (read-only): the tree is clean for every path the plan touches; the installed harness is
   0.5.0; the data, runs and goals directories resolve. `UPGRADING.md` says to run `evh validate` with 0.4.0
   before moving the pin; the script does not embed 0.4.0's rules, and checks only what its steps rely on:
   the hashes (step 2), the shapes of the files it rewrites (baselines, goals, rounds, manifests) against their
   0.4.0 schemas, and the baseline refusals (step 6).
2. **Hash check**: for every `metrics.json` (every runs directory), recompute the version-4 hash from the
   stored body (`_hash_of` over the body minus `hash`, with `imported` removed first, as `import_run.py:209`
   adds it after hashing). Never recompute item, reference or code digests: references are gitignored,
   adapters change, imported runs have none. A mismatch refuses the migration; a derived run's null hash
   with `hash_invalid_because` is expected.
3. **Plan** (`--dry-run` stops here): every file and field to change; every refusal with the command that
   resolves it; the prior use it will record per heldout dataset (RFC-015); the margins it moves;
   the files a tag cannot restore.
4. **Tag** `pre-0.5.0-migrate` in the repository; the plan lists what it does not cover: gitignored run
   files (`data/runs/*/run.json`, `outputs/_rows.jsonl`), `materialized/`, `.cache/`, `.build/`, other
   repositories, the published site. The script refuses to touch a gitignored file.
5. **Fingerprints** to version 5, from the stored body: `host` keeps `platform` and `python`, gains
   `accelerator: {recorded: false}`; `machine` takes `label`, `release`, `processor`, `cpu_count` (all six
   for an imported run, whose `libraries` and `instrument.harness` move to `imported_by`); the version-4 hash
   moves to `hash_v4`; the version-5 hash is computed. Derived runs keep `hash: null` and get the same split.
6. **Baselines per goal**: each `baselines/<dataset>_baseline.json` becomes
   `baselines/<goal or _>/<dataset>/1.json` with `migrated_from`, the version-5 `fingerprint_hash` of its run
   (absent when the run's hash is null), `promoted_from` resolved to `run:runs/<run_id>` (the `runs/` copy,
   as `catalog_adapter.py:675-676` already prefers); `index.json` with `current: 1`; `baselines/` is removed.
   Refusals: a baseline id that is not `<dataset>_baseline`; two goals sharing one baseline; a goal-less
   baseline on a dataset a goal uses. None occurs in this repository's 7 baselines; the podcast project has
   none.
7. **Goals and rounds**: dataset roles are not renamed (`dev` and `heldout` stay). A declared
   `axes.<axis>.margin` stays where it is and is listed in the plan, because its meaning changes (RFC-015);
   rounds' bare `baseline` and `conclusion.promoted_run` become `run:` ids.
8. **Prior use of heldout datasets**: per heldout dataset,
   `data/looks/<dataset>/prior.json` with the number of distinct configurations that had runs on it in the
   heldout role, and no looks (RFC-015, the owner's decision).
9. **The silver reference manifests**: `from_run.fingerprint_hash` stays as recorded, and the manifest gains
   a top-level `from_run_fingerprint_version: 4`. It goes at the top level, not inside `from_run`: `from_run`
   is one of the `AUTHORSHIP` keys the reference digest hashes (`_fingerprint.py:378, 407-416`), so a field
   inside it would move the digest of every reference made from a run and contradict every run scored
   against it.
10. **Check**: `evh validate` with V17 and V18 passes; the catalog builds; the baselines it shows are the 7
    baselines it showed before; every reference digest is unchanged.

It writes nothing unless the dry run was clean and `--yes` is given. This repository migrates first; the
podcast project after its harness pin moves to 0.5.0. `UPGRADING.md` documents it; a later release removes
it.

## Migration

This RFC is the migration (above). Sizes, from the final migration review: here 313 `metrics.json` (140
hashed, 173 derived), 7 baselines, 7 goals (6 + the tutorial's); the podcast project 242 imported runs, 19
goals, no baselines. Every stored hash in both recomputes from its body; in memory, version 5 maps 135
distinct version-4 hashes to 135 distinct version-5 hashes, and 242 to 242.

## Alternatives Considered

- **Keep per-dataset baselines, add a goal field.** Rejected: two goals on one dataset still collide on the
  file name.
- **Drop `host` from the fingerprint entirely.** Rejected: platform, Python and the accelerator stack do
  change results of local models.
- **Store `@current` as a symlink or as "the highest n".** Rejected: symlinks break on Windows and with
  `core.symlinks=false`; "highest n" cannot express a rollback.
- **Recompute version-5 digests from the source data.** Rejected: references are gitignored, adapters have
  changed, imported runs have no source; only the stored body is reliable.
- **An `evh migrate` command.** Rejected by the owner: two known projects, a one-time move.
- **UUID run ids.** Rejected: unreadable in listings; a timestamp plus a short suffix sorts and is unique
  enough together with refusing an existing directory.

## Testing

- `harness/tests/test_baselines.py`: promote twice on one dataset for two goals; versions and pointer;
  goal-less `_`; an interrupted promotion leaves the old pointer valid and is recorded as interrupted by the
  next; two concurrent promotions get different versions; rollback moves the pointer and records it;
  `round-close --promote` re-run after a failed round save does not promote twice; `run-promote` refuses a
  custom id and an ambiguous bare run id.
- `harness/tests/test_fingerprint_v5.py`: the exclusion list; a host-label change keeps the hash; a Python
  change moves it; an imported run's host, libraries and harness are outside; a version-4 imported run
  passes V17; V17 catches a tampered hash.
- `harness/tests/test_ids.py`: parse and print every example above; every run id in this repository parses;
  all-digit segments refused; V18 checks `ID_FIELDS` only.
- `harness/tests/test_run_ids.py`: two runs of one config in one millisecond get different ids; an existing
  directory is refused; the suffix never matches `_REPEAT`.
- `harness/tests/test_migrate_0_5_0.py`: on a copy of the example project with a v4 fixture: the dry run's
  plan, each refusal, the ten steps, idempotence (a second run changes nothing), a run killed after step 5
  finished by a second run, the tag reused, reference digests unchanged, and the baselines page equal to the
  old baselines page.
- Run on this repository and the podcast project's data before release; both validate.

## Decisions (ADR candidates)

1. Baselines become versioned baselines per goal and dataset, with a pointer file, no symlinks
   (no earlier ADR decided the per-dataset baseline; ADR-0002 only carries the goal on it).
2. Fingerprint version 5: `machine` outside the hash, `host` (platform, Python, accelerator) inside, an
   explicit exclusion list per version, hashes recomputed by `validate`.
3. Run ids with milliseconds and a random suffix; creating a run never reuses a directory.
4. One identifier grammar with a closed list of kinds; segments allow the existing run ids' upper case and dots.
5. The 0.5.0 migration is a one-time, re-runnable script, not a command; it trusts only stored bodies.
6. Records that parallel commands write (baselines, looks, prompt versions, round files) are written under one
   exclusive-create lock helper; version files are created exclusively and pointers rewritten atomically.
