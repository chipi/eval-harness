# RFC-009: Prompt versions

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) (FR1)
- **Related RFCs**: RFC-014 (the grammar; fingerprint v5), RFC-010 (studies create versions), RFC-013 (commands,
  schemas, the actor), [RFC-001](RFC-001-fingerprint-and-code-identity.md)
- **Code**: new `harness/scripts/_prompts.py`; `experiment_run.py` (resolve, overlay, fingerprint),
  `_fingerprint.py` (`arm.prompts`), new commands `prompt_version.py`, `view_prompts.py` (`evh prompts`),
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
- The podcast project's prompts live in its installed pipeline library (`podcast_scraper/prompts/`, 204 files), loaded
  from one directory the library can be pointed at (`set_prompt_dir`); a trial cannot write into an installed package,
  and writing into a tracked checkout makes the build dirty (`run-promote` refuses dirty builds).

## Design

### Declaring prompts (config)

```yaml
config_id: summary_qwen_v3
dataset_id: curated_5feeds_dev_v1
prompts:
  summary/user:   {file: prompts/summary_user.j2}            # a file in the project
  summary/system: {file: "pkg:podcast_scraper/prompts/openai/summarization/system_v1.j2"}   # in an installed package
prompt_root:                                                  # or: the directory the system loads from
  path: "pkg:podcast_scraper/prompts"
  vary: [openai/summarization/long_v1.j2, openai/summarization/system_v1.j2]
params: {provider: openai, model: gpt-5-mini}
```

- `pkg:<distribution>/<path>` resolves through `importlib.resources`; other paths are relative to the project root.
- A name is a path in the grammar (lowercase segments, `/` allowed, no all-digit segment). For a root, each varied
  file's name is `<root name>/<relative path without extension>` unless the config names it.
- `schemas/config.schema.json` gains `prompts` and `prompt_root`.

### Versions (`data/prompts/<name>/`)

- `<n>.txt` (the bytes, as read) and `<n>.json` (`schemas/prompt-version.schema.json`): `id`
  (`prompt:<name>/<n>`), `sha256`, `parent` (a version id or null), `note`, `actor` (RFC-013), `created_at`, `source`
  (the declared path, or `study:<goal>/<id>` with the trial for a sampler's version), `extension` (to export with the
  right name). `index.json`: `{"versions": [...], "aliases": {"production": 3}}`.
- **Resolving at run time** (`_prompts.resolve(config) -> {name: Version}`): hash the declared file; if a version with
  that hash exists, use it; otherwise record a new version (parent = the latest, note = "recorded by run <run id>",
  actor = the run's actor), so every run's prompts are in the history without a separate step.
- **Aliases** are set only by `evh prompt-alias <name> <alias> <n>`; promotion never moves them (RFC-014).

### What the adapter receives

`call_system(text, params)` is unchanged; `params` gains, when the config declares prompts:

- `params["prompts"]`: `{name: {"text": …, "path": …, "version": n, "sha256": …}}`;
- `params["prompt_root"]`: the path of a **per-run overlay directory**: a copy of the root with the varied files
  replaced by the versions this run uses (for a plain run, the files as they are; for a study's trial, the trial's
  versions). The overlay lives under the run's own temporary directory and is removed after the run; no tracked file is
  written, so the build stays clean.

A 0.4.0 adapter that ignores these keys behaves as before. The wrapping recipe (RFC-007) shows a system that needs its
prompt directory set (`set_prompt_dir(params["prompt_root"])`).

### The fingerprint

`arm.prompts`: `{name: {"version": n, "sha256": …}}`, inside the hash, so two runs that differ only in a prompt
version differ only there, and `run-compare` names `arm.prompts.<name>` as the variable. For a root, also
`arm.prompt_root_sha256`: the digest of every file in the root (sorted relative paths and their sha256), so a change to
an unvaried file in the root still shows. Credentials never enter (`identity_params` unchanged).

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
versions they used. Every view has its command (above).

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
- **Symlink overlays.** Rejected: Windows and `core.symlinks=false`; a copy is small (the podcast root is 204 files).
- **Templating in the harness.** Rejected: the project renders; the harness hashes bytes.

## Testing

- `harness/tests/test_prompts.py`: declare, run, version 1 recorded; edit the file, run, version 2 with parent 1;
  unchanged bytes reuse the version; a `pkg:` path resolves; the overlay holds the varied files and is removed; the tree
  stays clean; two arms differing only in a prompt differ only in `arm.prompts`; export refuses `site-packages`; V19
  catches a tampered snapshot.
- Catalog and command tests for the prompt pages and `--json` outputs.

## Decisions (ADR candidates)

1. The harness versions declared prompt files (content snapshots in `data/prompts/`), resolved automatically at run
   time; prompts stay where the project keeps them (amends PRD-001's "not a prompt library").
2. Prompts and a root's digest are part of the arm in the fingerprint.
3. A per-run overlay directory gives the system its prompts without writing a tracked file.
