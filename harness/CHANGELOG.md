# Changelog

Every release of the harness, newest first. The version lives in `scripts/_version.py`; a
release is the git tag `v<version>`, and the release workflow refuses a tag that disagrees
with that file or has no section here. A change that can move a result is never a patch
release without saying so under **Changed**.

## 0.3.0 — 2026-10-21

Re-measuring a frozen experiment: judge scorers, an adjudicated-gold pass, and the checks that
keep both honest. Design: [ADR-0001](../docs/adr/ADR-0001-judge-scorers.md).

### Added
- **`evh judge-score`** (and `make judge-score`). Re-measure an experiment's frozen outputs
  with a validated LLM judge, billed, cost-capped and resumable. It runs from the installed
  package in a project that has only its own data directory, scorer, prompt and runs: the
  prompt builder, reply parser, tau-b and Spearman, and an OpenAI-compatible judge client
  (LiteLLM proxy, OpenRouter direct, per-judge `base_url` / `api_key_env`, billed cost read
  from the response, retries) are in `evaluation_harness.judging`, with no dependency on
  `examples/`.
- **The judge scorer artifact** (`data/scorers/<id>.yaml`): two or more judges from different
  vendor families, the prompt (with its sha256 at 16 summaries), the protocol, a `validation`
  block and a cost cap.
- **A validation gate.** A scorer runs only if its `validation` block names a committed run
  for each judge that has the stated metric, the judge's model, temperature, reasoning,
  provider, max tokens and prompt. Otherwise `--unvalidated` runs it and labels every number
  "unvalidated judge". `provider: fake` judges (offline, free, for testing a scorer) can never
  pass the gate.
- **Judging sets and stored verdicts.** One item is the article plus every arm's output, arm
  identities hidden, order shuffled by a seed; the set is hashed into its id and frozen in
  `data/judging-sets/`. Every raw reply is stored per call in `data/judge-verdicts/`, so a
  rerun resumes and re-reading costs $0. A different arm set is a new set, never an append.
- **Controls.** A position check (a second shuffle that re-forms the blocks) and a noise check
  (a repeat on a subset), plus per-judge agreement and a self-family flag, in `summary.json`.
- **Adjudicated gold re-measurement** (repository tooling, `examples/_shared/adjudicate.py`,
  not in the package): a committed adjudication file overwrites only the disputed items of a
  local gold reference set to make a new reference version, and `rescore` re-scores every run
  against it for $0, the old reference kept beside it.
- **`validate` V11-V13.** V11: every judging set's stored hash is the hash of its content.
  V12: every stored verdict names a real set, item, pass and block, and its `n` is that
  block's size. V13: every judge scorer loads, is structurally valid, and its prompt file
  resolves. They read the configured data directory.
- Experiment-level results this enables are reported in the repository's reports (the
  summarisation experiment re-measured with two validated judges; AG News and DBpedia against
  adjudicated gold); none of them is in the package.

### Changed
- **`prompt.file` in a scorer resolves against the project root**, then the scorer file's own
  directory, then (in a checkout of this repository only) the repository root. A committed
  scorer's repo-relative path resolves exactly as before.
- Nothing that scores a run changed: committed runs and their recorded hashes are untouched.

## 0.2.0 — 2026-10-20

The first version meant to be installed rather than copied.

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

## 0.1.0

The harness as extracted, before it was packaged; see `docs/UPGRADING.md` for what changed
between extraction and 0.2.0.
