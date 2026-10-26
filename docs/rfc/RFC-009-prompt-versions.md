# RFC-009: Prompt versions

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) (FR1)
- **Related RFCs**: RFC-014 (the grammar; fingerprint v5), RFC-010 (studies create versions), RFC-013 (commands,
  schemas, the actor), [RFC-001](RFC-001-fingerprint-and-code-identity.md)
- **Code**: new `harness/scripts/_prompts.py`; `experiment_run.py` (resolve, overlay, fingerprint),
  `_fingerprint.py` (`arm.prompts`; `filter_dirt` ignores the harness's record directories), new commands `prompt_version.py`, `view_prompts.py` (`evh prompts`),
  `prompt_diff.py`, `prompt_export.py`; `catalog_build.py` (prompt pages); `validate_tree.py` (V19);
  `schemas/prompt-version.schema.json`, `config.schema.json`

## Abstract

A config declares the prompt files its system uses, wherever they live, by name; or a prompt **root** directory and
the files in it that may vary. When a run starts, the harness hashes each declared file, finds or records the version
those bytes are, passes the text (and, for a root, a per-run overlay directory) to the adapter, and records name,
version and hash under the fingerprint's `arm`. Versions live in `data/prompts/<name>/` as content snapshots with a
manifest each (parent, note, author, date), so any version can be read, diffed or exported later, and a study can
create a version without touching a tracked file. Names follow RFC-014's grammar (`prompt:summary/system/3`,
`@production`).

## Problem Statement

- A prompt inside `params` is hashed as text; a prompt in a file reaches the fingerprint only if the adapter's
  `fingerprint(params)` hook hashes it, under `system_under_test.model`, where `run-compare` reads it as a different
  system, not a different arm.
- The podcast project's prompts live in its pipeline library (`podcast_scraper/prompts/`: 204 `.j2` files among 209,
  the rest code, a README and `__pycache__`), loaded from one directory the library can be pointed at (`set_prompt_dir`,
  or the `PROMPT_DIR` environment variable, which wins: `store.py:68-72`). Templates are cached by name
  (`lru_cache`), and only `set_prompt_dir` or `clear_cache()` clears the cache. The whole-pipeline runner runs the
  library from a separate checkout (`PYTHONPATH=<checkout>/src`, `run_dataset_through_pipeline.py:349-396`), not the
  installed copy. A trial cannot write into an installed package, and writing into a tracked checkout makes the build
  dirty (`run-promote` refuses dirty builds).
- The podcast project also varies prompts by choosing a different file (`long_v1` against `long_v2`,
  `run_experiment.py:847-905`), not only by editing one.

## Design

### Declaring prompts (config)

```yaml
config_id: summary_qwen_v3
dataset_id: curated_5feeds_dev_v1
prompts:
  summary/user:   {file: prompts/summary_user.j2}            # a file in the project
  summary/system: {file: "pkg:podcast_scraper/prompts/openai/summarization/system_v1.j2"}   # in an installed package
prompt_root:                                                  # or: the directory the system loads from
  name: podcast                                               # the root's name (required)
  path: cache/podcast_scraper/src/podcast_scraper/prompts     # the directory the system reads (here a checkout)
  include: ["**/*.j2"]                                        # what the root's digest covers (default below)
  vary: [openai/summarization/long_v1.j2, openai/summarization/system_v1.j2]
params: {provider: openai, model: gpt-5-mini}
```

- `pkg:<distribution>/<path>` resolves through `importlib.resources` **in the harness's environment**; use it only when
  the system runs in that environment. A system run from another checkout or environment (the podcast pipeline) declares
  the path it actually reads, or the harness would hash bytes that do not run.
- A name is a path in the grammar (RFC-014: lowercase segments, `/` allowed, no all-digit segment). For a root, each
  varied file's name is `<root name>/<relative path without extension>`, lowercased, with any other character than
  `[a-z0-9_-]` replaced by `_`, unless the config names it (`vary: [{file: …, name: …}]`); two files that map to one
  name are refused.
- A varied file must exist in the root; the overlay never adds a file. A system with fallbacks (the podcast library reads
  `shared/summarization/X` when `<provider>/summarization/X` is missing, `store.py:81-96`) could otherwise change which
  file it reads. The root's digest (below) covers the fallback files, so a change to one shows.
- Choosing a different file (`long_v1` against `long_v2`) is a different prompt name, each with its own versions; the
  arm records which names it used.
- `schemas/config.schema.json` gains `prompts` and `prompt_root`.

### Versions (`data/prompts/<name>/`)

- `<n>.txt` (the bytes, as read) and `<n>.json` (`schemas/prompt-version.schema.json`): `id`
  (`prompt:<name>/<n>`), `sha256`, `parent` (a version id or null), `note`, `actor` (RFC-013), `created_at`, `source`
  (the declared path, or `study:<goal>/<id>` with the trial for a sampler's version), `extension` (to export with the
  right name). `index.json`: `{"versions": [...], "aliases": {"production": 3}}`.
- **Resolving at run time** (`_prompts.resolve(config) -> {name: Version}`): hash the declared file; if a version with
  that hash exists, use it; otherwise record a new version (parent = null, `source` = the path and, when it is in a git
  tree, its commit; note = "recorded by run <run id>", actor = the run's actor), so every run's prompts are in the
  history without a separate step. Lineage is recorded only when someone states it (`prompt-version --parent`, a
  study's sampler): bytes seen at a path do not say which earlier bytes they came from.
- **Concurrent runs** (RFC-011 runs jobs in parallel): a version is allocated under an exclusive lock on
  `data/prompts/<name>/.lock`; inside it the harness re-reads the index, reuses a version with the same hash if one
  appeared meanwhile, and creates `<n>.json` with `O_EXCL`, so two runs never get one number for different bytes.
- **The tree stays clean**: the harness's record directories (`data/prompts/`, `data/studies/`, `data/looks/`,
  `data/champions/`) are records, not code, as run output is. `filter_dirt` (`_fingerprint.py:98-112`) ignores changes
  under them, tracked or not, so recording a version never makes the next run `dirty`; validation (V19) guards their
  integrity instead.
- **Aliases** are set only by `evh prompt-alias <name> <alias> <n>`; promotion never moves them (RFC-014).

### What the adapter receives

`call_system(text, params)` is unchanged; `params` gains, when the config declares prompts (added after the fingerprint
and the run record are made, so no per-run path enters `arm.params`; the warm-up call gets them too):

- `params["prompts"]`: `{name: {"text": …, "path": …, "version": n, "sha256": …}}`;
- `params["prompt_root"]`: the path of a **per-run overlay directory**: a copy of the root with the varied files
  replaced by the versions this run uses (for a plain run, the files as they are; for a study's trial, the trial's
  versions). The overlay lives under the run's own temporary directory and is removed after the run; no tracked file is
  written, so the build stays clean.

A 0.4.0 adapter that ignores these keys behaves as before. The wrapping recipe (RFC-007) shows both ways a system takes
the overlay: a subprocess gets `PROMPT_DIR=<overlay>` in its environment (the podcast runner); an in-process library is
pointed at it and its template cache cleared (`set_prompt_dir(params["prompt_root"])`, which clears it, or
`clear_cache()`), because a cached template would otherwise be served from the previous trial.

### The fingerprint

`arm.prompts`: `{name: {"version": n, "sha256": …}}`, inside the hash, so two runs that differ only in a prompt
version differ only there, and `run-compare` names `arm.prompts.<name>` as the variable. For a root, also
`arm.prompt_root_sha256`: the digest of the files `include` matches (sorted relative paths and their sha256), so a
change to an unvaried file in the root still shows. The default `include` is every file except `__pycache__/`, `*.pyc`,
`*.pyo` and dotfiles, which differ between Python versions and machines and are not prompts. Credentials never enter (`identity_params` unchanged).

### Commands

- `evh prompt-version <name> (--from-file F | --text T) [--parent <id>] --note "…"`: records a version (refuses a
  duplicate hash, naming the existing version); `--dry-run`.
- `evh prompts [<name>] [--json]`: names, versions, lineage, aliases, and per version the runs that used it with their
  scores on the goal's measure.
- `evh prompt-diff <a> <b> [--json]`: a unified diff, and the runs of each.
- `evh prompt-export <id> --to PATH [--force]`: writes the version's bytes; refuses a path inside an installed package
  (`site-packages`, `dist-packages`, or not writable) and a tracked file with uncommitted changes; the person commits it.
- `evh prompt-alias <name> <alias> <n>`: moves an alias; records who and why (`--reason`).

### The catalog

A prompts page (every name, its versions, aliases) and a page per name: the versions as a lineage list with notes and
authors, the diff between consecutive versions, and per version the runs and their scores. Arm pages link the prompt
versions they used. Every view has its command (above). Prompt text (the diffs) is written into the static pages only
when the project publishes it (`catalog: {publish: [prompts]}` in `config.yaml`), since a project's prompts may be
private and the pages may be published; otherwise the pages show hashes and sizes, and the diff is `evh prompt-diff`
([UXS-004](../uxs/UXS-004-studies-champions-prompts.md#a-prompts-page)).

### Validation (V19)

Every `<n>.txt` hashes to its `<n>.json` `sha256`; parents exist; `index.json` lists exactly the versions present;
every run's `arm.prompts.<name>` names an existing version with that hash; aliases point at existing versions.

## Migration

None required: 0.4.0 configs declare no prompts. A project adopts it by adding `prompts:` or `prompt_root:`; its next
run records version 1 of each.

## Alternatives Considered

- **Hash prompts but keep no history.** Rejected (owner's decision): studies must create and reuse versions, and a
  winner must be exportable.
- **A prompt store the project moves its prompts into.** Rejected (owner's decision): prompts stay where production
  reads them.
- **Write the trial's file into the project's tree.** Rejected: the build becomes dirty and promotion refuses it; an
  installed package cannot be written at all.
- **Symlink overlays.** Rejected: Windows and `core.symlinks=false`; a copy is small (the podcast root is 209 files,
  848 KB measured with `du`).
- **Templating in the harness.** Rejected: the project renders; the harness hashes bytes.

## Testing

- `harness/tests/test_prompts.py`: declare, run, version 1 recorded; edit the file, run, version 2,
  with parent null; unchanged bytes reuse the version; a `pkg:` path resolves; the overlay holds the varied files and is
  removed; a varied file missing from the root is refused; the tree stays clean (the run after a recorded version is
  not dirty); two arms differing only in a prompt differ only in `arm.prompts`; `__pycache__` does not enter the root
  digest; eight parallel runs recording the same new bytes get one version, and different bytes get distinct numbers;
  no overlay path enters `arm.params`; an in-process library with a template cache serves the overlay's text; export
  refuses `site-packages`; V19 catches a tampered snapshot.
- Catalog and command tests for the prompt pages and `--json` outputs.

## Decisions (ADR candidates)

1. The harness versions declared prompt files (content snapshots in `data/prompts/`), resolved automatically at run
   time; prompts stay where the project keeps them (amends PRD-001's "not a prompt store").
2. Prompts and a root's digest are part of the arm in the fingerprint.
3. A per-run overlay directory gives the system its prompts without writing a tracked file.
4. The harness's record directories do not make a build dirty; their integrity is checked by validation instead.
