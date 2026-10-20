# Changelog

Every release of the harness, newest first. The version lives in `scripts/_version.py`; a
release is the git tag `v<version>`, and the release workflow refuses a tag that disagrees
with that file or has no section here. A change that can move a result is never a patch
release without saying so under **Changed**.

## 0.2.0 — unreleased

The first version meant to be installed rather than copied.

### Added
- **Installable package.** `pip install "eval-harness @ git+https://github.com/chipi/eval-harness@v0.2.0#subdirectory=harness"`
  gives the `eval-harness` command: every Makefile target, running the same scripts.
- **`EVAL_HOME` / `EVAL_DATA_DIR`.** The project's data lives in the project, never in the
  installed package; the data root can be nested (for example `data/eval/stats`).
- **The harness identifies itself in every run.** `fingerprint.instrument.harness` gains
  `version`, `code_sha256` and `installed`.
- **`eval-harness import-run`.** Per-item scores produced by another tool become a run the
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
