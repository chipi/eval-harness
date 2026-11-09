# RFC-028: Prompt versions, and the code a system runs

- **Status**: Accepted (owner, 2026-11-09: "accept and build"), built 2026-11-09 (one Prompts page with a section per name, not a page per name). Revision 2 (2026-11-09): the owner's answers to its three questions, and an independent
  review's findings (Fable), each checked against the code. Revision 1 the same day. Step 4.3 of `research/internal/PLAN_0.8.0.md`. It
  reworks the 0.5.0 drafts' RFC-009 (prompt versions, revision 3 of 2026-10-27) and PRD-009 FR1 (not merged; on
  `backup/050-pre-rebase-20261028`) onto what shipped since: fingerprint v5 (RFC-021), the store in files or SQLite
  (RFC-025) in place of the drafts' record store (RFC-017), who acted (RFC-027) and the API (RFC-026).
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-021](RFC-021-fingerprint-v5.md) (the parts, `settings.declared`), [RFC-025](RFC-025-runs-in-sqlite.md),
  [RFC-027](RFC-027-who-acted-and-baselines-per-goal.md) (the actor), [RFC-026](RFC-026-an-api-for-every-command.md)
  (the commands as reads and jobs), RFC-029 (studies make versions), PLAN R1 (the code version per item extends
  `code_ref`), the fleet's feedback 27 (a record for code under test: R's)

## Abstract

A config may declare the prompt files its system reads, wherever they live: by name, or a prompt **root** (the
directory the system loads prompts from) and the files in it that may change. At each run the harness hashes them,
finds or records the version those bytes are, gives the adapter their text (and, for a root, a per-run copy of the
root with the run's versions in it), and records each under the fingerprint's `settings`, so two runs that differ
only in a prompt differ in the fingerprint only there. Versions are kept in `data/prompts/<name>/`, named by their
content's hash, each with who made it, its parent and a note; `evh prompts`, `prompt-diff`, `prompt-version` and
`prompt-export` read and write them. Separately, the code a system runs gets one standard place: `code_ref`, the
repository, commit and dirty state of the system's code, declared by the config or the adapter's hook and recorded in
the deployment, so `run-compare` names a code change as the variable.

## What exists today (read 2026-11-09)

- An inline prompt in `params` is hashed with the settings (`settings_of`). A prompt in a file reaches the fingerprint
  only when the adapter's `fingerprint(params)` hook declares `prompt_sha256` or `system_prompt_sha256`, which v5 moves
  to `settings.declared` (`_fingerprint.split_declared`). Nothing keeps the text, so a run says that its prompt
  changed but not from what to what, and nothing lists which runs used which text.
- The code of a system that is not the adapter (a pipeline library, a service) has no standard place: a hook may put a
  commit under `deployment.declared`, by any key it likes; the fleet put its code version in an item field.
- `filter_dirt` ignores untracked run output under `data/runs*` only (`_fingerprint.py:116`).

## Design

### Declaring prompts (the config)

```yaml
config_id: summary_qwen_v3
dataset_id: curated_5feeds_dev_v1
prompts:
  summary/user:   {file: prompts/summary_user.j2}
  summary/system: {file: ../podcast_scraper/src/podcast_scraper/prompts/openai/summarization/system_v1.j2}
prompt_root:                                    # or: the directory the system loads prompts from
  name: podcast
  path: ../podcast_scraper/src/podcast_scraper/prompts
  include: ["**/*.j2"]                          # what the root's digest covers (default: every file but caches)
  vary: [openai/summarization/long_v1.j2, openai/summarization/system_v1.j2]
```

- A path is the path the system reads, relative to the project or absolute. The harness does not resolve package
  names: its environment need not be the system's.
- A name is a path of segments joined by `/`. For a root, each varied file's name is `<root name>/<relative path>`.
  A name and a longer one under it (`summary` and `summary/user`) can both exist: a name's versions are the `.txt`
  files directly in its folder.
- A varied file must exist in the root: the copy never adds a file (a system with fallbacks would otherwise read a
  different one). Choosing another file (`long_v1` against `long_v2`) is another name, each with its own versions.
- `schemas/config.schema.json` gains `prompts` and `prompt_root`. A config with neither behaves as today.

### Versions (`data/prompts/<name>/`)

- `<sha16>.txt` (the bytes as read; the first 16 hex digits of their sha256) and `<sha16>.json`
  (`schemas/prompt-version.schema.json`): `id` (`<name>/<sha16>`), `sha256`, `parent` (an id or null), `note`,
  `actor` (RFC-027), `created_at`, `source` (the path it was read from, with the commit when it is in a git tree; or
  the study and trial that made it, RFC-029), `extension`. There is no index: a name's versions are its files, in
  `created_at` order, and "v3" is only a display number.
- Written through `_store` (either store, RFC-025) with `_store.create_new`: the file's name is its content's hash,
  so two runs, two people or two clones that record the same bytes write the same record once, and different bytes
  never share a name. No lock is needed.
- **At run time** (`_prompts.resolve(cfg)`): hash each declared file; use the version with that hash, or record a new
  one (parent null, note "recorded by run <run id>", the run's actor). Every run's prompts are in the history without
  a separate step (owner, 2026-11-09: "automatically at run"). Lineage is recorded only when someone states it
  (`prompt-version --parent`, a study), and only when the version is made: a record is written once, so a version a run
  recorded first keeps `parent: null`. Recording a version with `prompt-version` before running it keeps its lineage.
- **The tree stays clean**: `filter_dirt` ignores untracked files under `data/prompts/` as it ignores run output, so
  recording a version never makes the next run `dirty`; V24 guards their integrity.

### What the adapter receives

`call_system(text, params)` is unchanged. When the config declares prompts, `params` gains (after the fingerprint is
made, so no per-run path enters it):

- `params["prompts"]`: `{name: {"text", "path", "version", "sha256"}}`;
- `params["prompt_root"]`: the path of a per-run copy of the root, with the varied files at the versions this run
  uses (a plain run: the files as they are; a study's trial: its versions), under `.build/prompt-roots/<run id>/`,
  removed when the run ends. No tracked file is written. The root's digest (below) is taken over this copy: what the
  system read.

An adapter that ignores these keys behaves as before. The wrapping guide shows the two ways a system takes the copy:
a subprocess gets `PROMPT_DIR=<copy>`; an in-process library is pointed at it and its template cache cleared.

### The fingerprint

`settings.prompts`: `{name: sha256}`, and for a root `settings.prompt_root_sha256` (the sorted relative paths and
sha256 of the files `include` matches; `__pycache__`, `*.pyc` and dotfiles left out). Both are inside the settings'
hash, beside the inline prompt and the hook's `declared` prompt hash, which keep working. A config that declares no
prompts gets neither key, so no existing fingerprint moves and v5 stays the version. `run-compare` names
`settings.prompts.<name>` as the variable.

### `code_ref`: the code a system runs

```yaml
code: {path: ../podcast_scraper}                # the system's checkout, read at run time
```

- With `code:`, the harness records `deployment.code = {"repo": <the remote, credentials stripped>, "commit",
  "dirty": [paths], "path"}` from that checkout. `repo`, `commit` and `dirty` are in the deployment's hash, so two
  runs of one model on two commits of the pipeline differ in `deployment.code.commit`; `path` is provenance, kept
  beside the hash (`hashed_view` leaves it out, as it does the instrument's path), so two clones of one commit are one
  system.
- An adapter's hook may return `code_ref` with the same keys (a system the harness cannot read: a remote service
  reporting its build); it lands in the same place, and the config's wins when both are given, with a note.
- A dirty checkout is recorded, not refused, as the project's own is (`run` warns on a dirty project tree,
  `run.py:1095`; `run-promote` refuses a dirty build unless `--allow-dirty`). The record says which files.
- R1 extends this per item (the code version a recorded output came from); the fleet's `kind: code` record (feedback
  27) is R's.

### Commands (each with `--json`; RFC-026 serves them)

| command | what | served |
| --- | --- | --- |
| `evh prompts [NAME]` | names, versions (display numbers), lineage, and per version the runs that used it with their goal's measure | read |
| `evh prompt-diff A B` | a unified diff, and the runs of each | read |
| `evh prompt-version NAME (--from-file F \| --text T) [--parent ID] --note "…" [--by]` | records a version; a hash already recorded is named, not duplicated | job, `--from-file` an upload |
| `evh prompt-export ID --to PATH` | writes a version's bytes; refuses a path inside an installed package and a tracked file with uncommitted changes | job, `--to` an artifact (a download) |

### The catalog

A prompts page (every name, its versions, the baseline that uses each) and a page per name: the versions as a lineage
with notes and actors, and per version its runs and scores. A prompt's text and the diffs go into the static pages only
when the project publishes them (`catalog: {publish: [prompts]}` in `config.yaml`, a new setting; owner, 2026-11-09):
prompts may be private and pages may be public. Otherwise the pages show hashes and sizes, and `evh prompt-diff` shows the text. Arm pages link the
versions they used and name the code commit.

### Validation (V24)

Every `<sha16>.txt` hashes to its name and its record; parents exist; every run's `settings.prompts.<name>` names a
recorded version with that hash; `deployment.code` has the four keys.

## Migration

None: no committed config declares prompts or `code:`, and no fingerprint moves.

## Alternatives considered

- **Prompts in the arm's hash** (the draft): v5 put how the system was asked under `settings`; prompts are that.
- **Keep no history, only the hash** (today, through the hook): a run can say its prompt changed but not to what, and
  a study cannot make or reuse versions.
- **A prompt store the project moves its prompts into**: the owner's decision of 2026-10-26: prompts stay where
  production reads them.
- **Write the run's version into the project's tree**: the build becomes dirty and promotion refuses it; an installed
  package cannot be written at all.
- **Symlinks for the root's copy**: not on every platform; the podcast root is 848 KB.
- **`code_ref` only from the hook**: a project with a checkout beside it should not need code to say its commit.

## Testing

- `tests/test_prompts.py` (both stores): declare, run, version recorded; edit, run, a second version; the same bytes
  reuse it; the root's copy holds the varied files and is removed; a varied file missing from the root refused; the
  run after a recorded version is not dirty; two arms differing only in a prompt differ only in
  `settings.prompts`; a config with no prompts keeps its fingerprint byte for byte; eight runs recording the same new
  bytes at once make one version; no per-run path in the fingerprint; export refuses `site-packages`; V24 catches a
  changed snapshot.
- `code:`: a commit recorded, a second commit moves `deployment.code` only, a dirty checkout recorded, a hook's
  `code_ref` landing in the same place, the config's winning with a note.
- The commands' `--json` and the API's parity test; the catalog pages with and without `publish: [prompts]`.

## Decided by the owner (2026-11-09)

1. **Prompt text on pages**: only when the project publishes it (`catalog: {publish: [prompts]}`).
2. **`code_ref`**: the config's `code:` (the harness reads the checkout) and the hook's `code_ref`; the config wins.
3. **Recording**: automatic at every run; `prompt-version` adds lineage and notes.
