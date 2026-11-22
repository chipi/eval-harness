# Contributing

## Adding an example

An example is a directory under `examples/` with its own dependency chain — uv:
`pyproject.toml` + `uv.lock` + `.python-version` — so it provisions its own interpreter and
cannot bleed into a sibling. An example that only replays another system's own code
(`triage-fleet`, `signal-fleet-dedup`, which import the fleet from a checkout it names) has
none: it runs in the harness's environment.

**Working in this checkout** (an agent included): `evh` here keeps its data in `harness/data/`,
whichever directory you run it from, because a checkout's own `data/` wins over the working
directory (`EVAL_HOME` overrides it). Never edit or delete anything already committed under
`harness/data/` (datasets, runs, labels, references, baselines), the published reports in
`research/`, or the journal (`research/internal/NOTES.md`: append only).

It needs:

- **`adapter.py`** — the single seam. `call_system`, `score`, `warmup`, `fingerprint`, plus
  `PRIMARY_METRIC` and `METRIC_KINDS` so the leaderboard knows which column is the headline
  and which way each one points.
- **`fetch.py`** — a download recipe. **Never commit a third-party corpus.** Redistributing
  one is a licence question nobody should inherit by cloning a repo.
- **systems** — one YAML per arm. Hold everything constant except the one thing you vary,
  and say in the system why the varying thing varies.

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

## Changing the harness: PRD first

A new capability starts with a [PRD](docs/prd/index.md) (what the user needs, and why), then a
[UXS](docs/uxs/index.md) when it has a page or a command, then an [RFC](docs/rfc/index.md) for the
design. A key architectural decision gets a few lines as an [ADR](docs/adr/index.md). A view added
to the catalog or the inspector gets its `evh` command in the same change.

## Before you open a PR

```bash
cd harness && make ci      # validate, self-tests, the GUIDE as written, the site; no network, no keys
make budget-check          # from the root: the inspector's memory and answer times (harness/docs/TESTING.md)
make quality               # from the root: lint, types, security, dead code, spelling, shell
```

CI runs more, all from the root: `make quality` (quality.yml), `make guard-check` (guards.yml),
and `make verify`, `make budget-check`, `make browser-real-check`, `make commands-check` and
`make browser-check` (reproduce.yml). `make verify` is the first level of
[REPRODUCE](docs/REPRODUCE.md): every number recomputed from the committed runs. A PR is ready
when all of them pass.

`make quality-install` installs the tools once (`harness/requirements-dev.txt`); `make format`
applies ruff's formatting. The scorers whose source is hashed into every run
(`examples/_shared/{classification,extraction,retrieval}.py`, `examples/*/adapter.py`) are
excluded from the formatter: reformatting one would invalidate the committed runs.
