# Testing the harness

The harness began as scripts that compute numbers and grew a catalog, an inspector server and a
public deployment. Its tests are in four tiers; a change goes into the lowest tier that can
catch what it could break, and a bug found in a higher tier gets a test in the lowest one that
reproduces it.

| tier | what it proves | where | run |
|---|---|---|---|
| **unit** | one function's answer: the paired test against the brute-force sign enumeration, Holm, the intervals; the periods and their trends; a scorer, a parser | `scripts/test_stats.py` (ships: `evh self-test` runs it), `tests/test_*.py` for one module (`test_axes`, `test_codeid`, `test_ner_parser`, ...) | `make test` (all), or `python tests/test_<x>.py` |
| **integration** | the modules together on files: a run made and read back, a catalog built from fixture runs and its pages read, every `evh` command in a project that pins the installed wheel, `catalog-serve` answering over HTTP, `--hooks` called | `tests/test_catalog.py`, `tests/test_goals.py`, `tests/test_installed_commands.py`, `tests/test_serve_hooks.py`, `tests/self_test.py` (runs them all) | `make test`, `make ci` |
| **end to end** | what a reader sees: a tutorial project built from the wheel, its catalog and the inspector in headless Chromium (charts, filters, the period chips, the tiles against `evh overview`, the period bounds against Python's on 118 days, no console error, no page wider than a phone); the GUIDE and the tutorials run as written; the public site with production's headers | `tests/test_inspector_browser.py`, `tests/check_guide.py`, `site/test_browser.py` | `make browser-check`, `make guide-check` |
| **resources** | the inspector on this repository's real runs, as the deployment runs it: memory under `--warm` below 200 MB (prod's container has 256 MiB), a cached answer in milliseconds, a cold one in seconds; again with the deployment's hooks and SDKs | `tests/test_inspector_budget.py` | `make budget-check` (from the root, with the hooks) |
| **the checks can fail** | every checker goes red on the defects it exists to catch: a wrong number in a report row, a cell, a code block or prose, a wrong ratio, count or latency, a broken link, a wrong licence, a scorer or parser change the runs predate, a broken, duplicated or truncated run. All of a checker's defects are planted at once in a copy of the repository and it runs once; its output must name each | `tests/test_checks_can_fail.py` | `make guard-check` |

CI runs each tier on every pull request: `make verify` (unit and integration, the reports
recomputed, the site rebuilt), `browser`, `budget` and `rerun` (`.github/workflows/reproduce.yml`),
and `make quality` (lint, types, security, dead code, spelling). `make guard-check`
(`.github/workflows/guards.yml`) runs only when a checker or the harness code it reads changes:
it proves the checkers, and a change to the reports or the runs leaves them as they were
(`make ci` still checks that every string it plants is in its file). A
release does not re-run any of it; it requires CI on the tagged commit to be green on main
(`.github/workflows/harness-release.yml`).

## How a test earns its place

- **It fails for the bug it names.** Before it is kept, break the code it guards and watch it go
  red (CONTRIBUTING: "when a check passes, ask what would make it fail"). The budget test fails on
  the 0.4.0 `stats.py` (a peak of 260 MB); the hooks test fails when the error hook is not called.
- **A real bug gets its test first**, in the lowest tier that reproduces it: the 2026-10-26 OOM
  has one in each (`test_stats.py` bounds the caches; `test_inspector_budget.py` bounds the
  process).
- **Numbers have one source.** A page and its `evh` command read one builder
  (`catalog_build.period_*`); the browser test compares the page with the command rather than
  each with a copy of the expected number.
- **Limits leave room for a slow runner** and say why they are what they are (prod's 256 MiB; a
  cached answer is a dictionary lookup).
- **Absence is a failure, not a skip** ([CONTRIBUTING](https://github.com/chipi/eval-harness/blob/main/CONTRIBUTING.md)).

## Not measured yet

- **Line coverage.** No coverage tool is installed in the harness's environments; measuring it
  once would show which modules no test reaches. It needs `coverage` as a development
  dependency (`requirements-dev.txt`), which is the owner's call.
- **Response times on prod.** The budgets are measured on a laptop and a CI runner; prod's
  `/metrics` (0.4.2, `infra/inspector/hooks.py`) gives the real ones once deployed.
