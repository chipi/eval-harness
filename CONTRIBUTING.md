# Contributing

## Adding an example

An example is a directory under `examples/` with its own dependency chain — uv:
`pyproject.toml` + `uv.lock` + `.python-version` — so it provisions its own interpreter and
cannot bleed into a sibling.

It needs:

- **`adapter.py`** — the single seam. `call_system`, `score`, `warmup`, `fingerprint`, plus
  `PRIMARY_METRIC` and `METRIC_KINDS` so the leaderboard knows which column is the headline
  and which way each one points.
- **`fetch.py`** — a download recipe. **Never commit a third-party corpus.** Redistributing
  one is a licence question nobody should inherit by cloning a repo.
- **configs** — one YAML per arm. Hold everything constant except the one thing you vary,
  and say in the config why the varying thing varies.

## Rules the harness enforces, and why

- **The harness imports nothing domain-specific.** If you find yourself editing
  `harness/scripts/` to make your example work, that belongs in your `adapter.py`.
- **Never skip on a missing committed fixture.** Absence is a failure, not a skip. Two
  tests here went vacuous the moment a file moved, and the suite stayed green.
- **If it can be computed over the whole corpus, do not report it from a sample.** Five
  outputs were once read by hand and 1,440 declared clean; 77 had format violations.
- **Do not delete measurements to tidy a table.** Scope the view instead — `--match`,
  `EVAL_RUNS_DIR`. Eighteen arms of paid results were lost to that once.
- **When a check passes, ask what would make it fail.** If nothing would, it is not a check.
  Several assertions here were vacuous until someone mutation-tested them.

## Before you open a PR

```bash
cd harness && make ci      # validate the tree + self-tests, no network, no keys
```
