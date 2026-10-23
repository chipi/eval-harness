# Quality tooling: the ruff experiment (2026-10-22)

podcast_scraper gates its code with black, isort, flake8 (+ bugbear), mypy, bandit, pip-audit,
vulture, interrogate, radon and codespell. This repository runs the same gates with one
deliberate difference: **ruff** does the formatting, import order and linting that black,
isort and flake8 do there. Everything else is the same tool. This note records what that
difference did, measured on this repository, so the two approaches can be compared.

`make quality` runs it all; `.github/workflows/quality.yml` runs the same target. Tools are
pinned in `harness/requirements-dev.txt`, ruff's rules in `ruff.toml`, mypy and interrogate in
`harness/pyproject.toml`, codespell in `.codespellrc`.

## What each gate found

| Gate | First run | After | Real defects it found |
|---|---|---|---|
| ruff (lint) | 1,593 findings over a broad rule set | 0 | dead code, unused imports and variables, a mutable class default, `lru_cache` on methods (an instance kept alive: now a per-instance cache, with a test) |
| ruff (format) | 97 files reformatted | 0 | none; style only |
| mypy | 329 errors (default mode, 65 files) | 0 | **the bundled adapter's `anthropic` provider raised TypeError on every call** with the installed SDK (1.x dropped `temperature=`); `runner.py` crashed without a primary judge; `validate_judge_goyal` returned None into a dict caller; two report-claims checks could crash instead of reporting |
| bandit (medium+) | 21 | 0 | **`_fetch.fetch` read any URL scheme**, so a manifest row `file:///…` copied a local file into the item cache and pinned it; now refused, with a test |
| pip-audit | harness requirements: 0 | 0 | none in what the package declares; the examples' locks: see "The example lock upgrade" |
| vulture (80%) | 1 | 0 | dead code (removed); later, an unused parameter in a test written the same day |
| interrogate | 53.5% | 100% (161 added later; see below) | none (a coverage measure, not a defect finder) |
| codespell | 189 hits | 0 | none: every hit was a domain word, a variable name, a paper title or a deliberate test typo |
| shellcheck | 7 findings in 3 scripts | 0 | unquoted paths in an evidence script; one `A && B \|\| C` in the deploy script that was correct but read as a bug (rewritten as `if !`, both forms checked to decide identically) |
| actionlint | 1 at the first baseline | 0 | the baseline's one finding no longer reproduces; which change removed it was not traced |
| radon | 137 functions rated C or worse | report only | none (podcast reports it too) |

Most of mypy's 329 were one shape: a module-level script reusing a throwaway name for a
different type (`_v` a float in one claim block, a string in the next). Those were renamed,
not silenced; each of the seven `# type: ignore` comments that remain says why.

## How the ruff approach compared

**Faster, by a lot, but that is not where it mattered.** `ruff check` over 175 files takes
0.04 s; the whole `make quality` takes about 8 s, 6.7 s of it pip-audit's network lookups. The
podcast tool chain was not timed on this repository, so no ratio is claimed.

**One config instead of three.** Rules, import order and format live in `ruff.toml`; every
rule turned off there says why.

**Its auto-fixes needed watching.** Three things went wrong, each caught by a later gate
rather than by ruff:

1. `ruff check --select RUF100 --fix` (remove unused `noqa`) removed 199 `noqa` comments that
   were needed, together with their written reasons, because with only RUF100 selected every
   other rule looked unused. Reverted; re-run as `--fixable RUF100` under the full rule set.
2. The F401 fix (remove unused imports) removed `render_prompt` from `judge_score`, which
   other modules use as `judge_score.render_prompt`. Nothing static saw it; `make ci` failed
   at V13 at run time. The re-export is now explicit (`# noqa: F401 — re-exported`).
3. The broad rule set includes bandit's checks as `S` rules. While configuring ruff, S310
   (urlopen with any scheme) was switched off for the whole repository with the written reason
   "fetchers download public data on purpose (scheme-checked)", and the parenthesis was not
   checked before it was written. It was false for `_fetch.py`. bandit, run separately,
   flagged the same call, and that is how the `file://` hole was found. S310 is now on, and
   every `urlopen` carries its own reason.
4. Ruff 0.17 also formats the Python blocks inside Markdown. The first `ruff format .`
   rewrote three docs' hand-laid examples into 110-column lines, unnoticed until a later diff.
   Reverted; `*.md` is excluded from the formatter.

The lesson from 3 is the useful one: with ruff's `S` rules *and* bandit, a rule waved off in
one is still checked by the other. Keeping both is redundant on paper and was not in practice.

**Frozen instrument code needs a carve-out.** The scorers whose source is hashed into every
run (`examples/_shared/{classification,extraction,retrieval}.py`, `examples/*/adapter.py`) are
excluded from the formatter, and the style rules are off for them, because a reformat changes
the hash and invalidates committed runs. Comments added on lines outside the hashed functions
(five `nosec`/`noqa` reasons in `summeval-judging/adapter.py`) were checked against V10, which
still matches every run.

**Small frictions.** bandit reads every word after `nosec` as a test id, so the reason goes
first (`# why  # nosec B310`). bandit warns "nosec encountered, but no failed test" on a line
holding two calls (`from_pretrained(...).eval()`), though without the `nosec` it does fail
there. mypy 2.x no longer type-checks for Python 3.9, so mypy targets 3.10; the 3.9 floor is
held by CI's package job, which runs `evh self-test` on 3.9.

## What followed (2026-10-22/23)

The owner's decisions on the open items: docstrings to 100% (podcast's bar, now the gate;
161 added, the code unchanged, checked by comparing each file's AST without docstrings);
`quality` added to `main`'s required checks; the vulnerable example pins upgraded, on Linux.

### The example lock upgrade

| Package | Was | Now (Linux) | Advisories cleared |
|---|---|---|---|
| transformers | 4.55.4 | 5.20.2 (few-nerd: stays 4.55.4) | 13 |
| torch | 2.14.0 | 2.14.0 | the Intel-Mac fork's 2.2.2 carries 23; that platform is out of scope |
| sentence-transformers | 3.4.1 | 6.2.0 | 1 |
| pillow | 12.3.0 | 13.0.0 | 34 |
| aiohttp | 3.14.3 | 3.14.5 | 8 |
| nltk | 3.10.3 | 3.10.4 | 1 |
| certifi | 2026.7.22 | 2026.10.19 | 1 |

`make audit-locks` (`examples/audit_locks.py`) resolves each lock per platform before
auditing: a plain `pip-audit` evaluates the lock's markers against the machine it runs on, so on
Linux it had silently skipped the Intel-Mac fork, torch 2.2.2 included. After the upgrade every
lock is clean on Linux and Apple-silicon macOS except few-nerd's transformers, accepted below.

### Every local arm re-run against the committed record (`make compare`)

| Experiment | Arms | Result |
|---|---|---|
| Classification · AG News | 6 | exact, 200/200 items each |
| Classification · DBpedia | 4 | exact, 280/280 |
| Retrieval · SciFact | 7 | exact, 200/200 (sentence-transformers 3 to 6) |
| Extraction · Few-NERD | 4 | exact, 280/280 (on transformers 4.55.4) |
| Summarisation · CNN/DM | 5 | 4 exact; bart_s 199/200, see below |
| Judging · SummEval | 9 | 7 exact; unieval 65/100 and unievalpub 63/100 items identical, means within 0.0002, paired p 0.42 and 0.49 |
| Summarisation · CNN/DM (DailyMail slice) | 5 | 4 exact; bart_s 187/200, mean +0.0009, paired p 0.52 (its committed run records `precision_not_applied`: it ran fp16) |

Every committed separation and tie holds in all seven.

The DailyMail slice waited a night: its random draw reads the whole split (~115 pages), and
the datasets-server answered HTTP 429 to every request from this machine for hours. Its fetcher
retried for ~40 s and gave up; it now paces its pages and backs off on a 429 (5 s to 60 s, as
ner-few-nerd's fetcher does), and the data came through, every item's hash verified.

What transformers 5 broke, and what was done:

1. **The summarization pipeline is gone.** The summarization adapter's `pipeline("summarization")`
   is replaced by `_Summarizer`, which repeats what transformers 4.55's pipeline did (its
   generation-config assembly, `task_specific_params`, prefix, tokenisation, decoding), read from
   the 4.55.4 source. Checked: on the same text the real 4.55.4 pipeline and `_Summarizer` give
   the same summary, and the BART arms reproduce.
2. **bart_s's one moved item is not the upgrade.** Its committed run (2026-09-30) predates the
   2026-10-14 fix that made `precision: fp32` real, so it ran distilbart-cnn-6-6 in fp16 as
   stored. The real 4.55.4 pipeline at fp16 reproduces the committed output; at fp32, the rerun's.
3. **span-marker has no transformers 5 release.** 1.6 to 1.8.1 (the last) declare
   transformers<5; forced onto 5.x, its config loses `num_labels` and its span attention mask is
   a shape 5.x's RoBERTa masking rejects. The owner chose to keep few-nerd on transformers
   4.55.4; its advisories are listed as accepted in `audit_locks.py`.
4. **UniEval's tokenizer changed.** transformers 5 builds a different T5 tokenizer from the same
   `spiece.model`: it drops the space token before each literal `</s>` in UniEval's prompts, which
   moved one arm's tau by +0.0031. The tokenizer 4.55 built is now shipped
   (`examples/summeval-judging/unieval_tokenizer/tokenizer.json`, sha256 pinned and checked at
   load) and gives 4.55's token ids exactly. What remains is T5 arithmetic in 5.x differing by
   about 1e-7 in P(Yes) (eager attention does not remove it), enough to reorder near-tied
   summaries within an article, not to move a finding.

### Code kept in more than one copy (2026-10-23)

A survey of the repository for logic written two or more times. Each item below now has one
home; after each change all 201 report claims re-derive unchanged and `make validate` matches
every run's scorer hash.

| What | Copies | Now |
|---|---|---|
| Spearman (and Pearson, ranks) | 5 scripts | `stats.spearman`, `stats.pearson`, `stats.ranks`; a constant input returns `constant` (NaN by default; `silver_calibrate` keeps its 0.0) |
| Holm | 3 | `stats.holm` (family_test, bootstrap_test, summeval_analysis) |
| Sign-flip p | 3 | `stats.sign_flip_p` (summeval_analysis, validate_judge_zhang, reproduce), same seed and stream: zhang's reports regenerate byte-identical, reproduce's p equal on 60 random cases |
| Loading a module from a path | 8 harness scripts, 6 example scripts | `_common.load_module`; `examples/_shared/modules.py` (this also fixed summeval's calibrate, which lacked the `_shared` path) |
| The test scripts' `check()` | 11 | `scripts/_check.py`; a test script that ran no check now fails |
| The datasets-server fetcher | 6 `fetch.py` + `calibration.page` | `examples/_shared/hf_rows.page`: paced, backs off on 429 and 5xx, stops on another 4xx; its own test |
| Cost sums | 2 beside `cost_report` | `cost_report.billed_and_recorded` (check_report_claims, site figures) |
| Pinned downloads, file hashes, item selection, `.env` | 2 or more each | `_fetch.fetch` + `write_bytes_atomic`; `_common.sha256`, `read_item_ids`, `item_selection`, `load_dotenv` |
| Deploy link probes | 2 | `infra/deploy/probe_link.sh [group\|one]` |
| Gateway parity (judge scorer vs. the gateway's copy) | by hand | a test in `test_judge_score` |

Bugs the survey found in the copies, fixed:

- **summeval split-half named a tied top's alphabetically first arm as the winner**, the bug
  `rank_stability` already fixed. It now counts only a unique winner and reports the rest as
  `undecided`. No published draw has a tied top, so no number moved.
- **scifact priced an unbilled call with no declared price at 0.0**, a claim it was free; every
  other adapter records None (unpriced). No committed run reached it: every hosted arm is billed.
- `check_report_claims` read runs in filesystem order; its globs are now sorted.

Left as copies, on purpose:

- Functions inside frozen adapters (their tau, Spearman, billing and `_cached`): the scorer hash
  covers them, and a change would invalidate every run recorded with them.
- `_fingerprint`'s hash, the `item_id` helpers, `e()` / `evh()` / `_mean`, the Makefile help
  text, infra's `restore()` and reproduce's newest-rerun discovery: each copy is a few lines,
  differs where it matters, or sits on a boundary (package vs. examples vs. infra) that a shared
  helper would cross.

### A holistic design review (2026-10-23)

After the duplication pass, a read-only review of the whole tree for what accumulates over
increments: 22 findings, every one acted on. The ones that could give a wrong reading in a new
run (none moved a committed number):

| Finding | What was wrong | Now |
|---|---|---|
| Direction by flag | "A wins 180/200" on latency meant A was slower unless `--asc` was passed; `holdout` had no direction at all; `primary_metric_asc`, written by `import-run --asc`, was read by nothing | `_runs.direction`, inferred from the metric and the runs, in every test and the leaderboard |
| Two adapter registries | every example adapter loaded as `eval_adapter_adapter`, and the kind lookup fell back to the bundled adapter | `_adapter.py`, one cache keyed by the file |
| Code hash over tests | editing a test made `run-compare` report a confound | `measuring_modules()`: the run-writing commands and what they import |
| The judge panel | judged "Synthetic item i for <run>" for every candidate, real runs included | judges each finalist's stored outputs |
| Package imports | `import evaluation_harness.judging` failed; `_common` loaded twice | the package puts its directory on sys.path, one import style |
| A typo'd provider | fell back to `echo` | refused |

The structural ones: run discovery in ~15 places (now `_runs.py`), a validator hard-coded to
this repository's directory names (now `<data>/validate.json`), a core command importing a
showcase report (now `_labels.py`), ~14,500 lines of tests and report checks in the wheel (now
`harness/tests/` and `harness/tools/`), a second hand-written experiment registry in the claims
checker (now read from `experiments.json`), the deploy running a copy instead of the wheel. And
the small ones: a `check()` with its arguments reversed, eight Makefile targets not `.PHONY`
(`make docs` did nothing), a test check that could not fail, a checker (`check_terminology`)
that was failing with nothing running it, refusals on stdout, unknown arguments ignored, two
environment-variable prefixes.

Kept on purpose, by the owner's call: `pair-test --family N` (Bonferroni for one
pre-registered pair, which cannot run Holm) and `--out` meaning a runs directory in `rescore`
and a site directory in `catalog` (published commands use both).

### A second design review: architecture (2026-10-23)

A second read-only review, of the architecture rather than the code: where a contract lived,
who could reach what, and what a project pinning the package would meet. Five findings that
could give a wrong reading, twelve structural ones. The owner's two decisions set its terms:
no backward compatibility (nobody uses the harness yet), and one record per
arm, the latest.

| Finding | What was wrong | Now |
|---|---|---|
| The data root | the fingerprint read `<root>/data`, so a project with `EVAL_DATA_DIR` recorded no reference hash, and its own run output made the tree dirty | the data root everywhere |
| Unchecked run directories | V1, V2, V3, V5 and V14 read `data/runs` alone; 68 committed derived runs were never validated | every committed directory |
| Direction | a goal's direction ordered the goal page while every command read the name table | flag > goal > adapter (`METRIC_DIRECTIONS`) > name, one function; V14 holds goals to their runs |
| Derived runs | rescore, judge-score and the re-parse each wrote their own provenance fields, and a derived run kept its source's `created_at` | `_record.py`: `derived: {kind, from, at, with}`; the derived directories folded into one record per arm |
| Import side effects | importing the package read `.env` into the environment and fixed every path from the current directory | `.env` read by the commands; paths resolved on first use |

The structural ones: run walks left in `_common` (now `_runs`), thirty `sys.path` inserts at
import, the judge panel outside the package (now `evh judge`), checkout-only lookups taken in
a pinned project, a cache key listing its dependencies by hand, the seam documented as an edit
to the package's own `scripts/adapter.py` (now `<project>/adapter.py`), configs, scorers,
judging sets and verdicts with no schema (V1 now checks 3023 documents), baselines that dropped
the reference tier and fingerprint (V6 now checks them against the run), and three commands
whose `main` ran to a cyclomatic complexity of 67 to 77 (rescore 77 → 26, experiment-run 67 →
48, leaderboard 71 → 56), with one aggregation instead of three copies.

Found on the way: `rescore` recorded `untyped_tp` as a dropped metric on 24 NER runs that
report it (corrected in the data); the GUIDE quoted a file count the judge panel's kit file
had moved; 2798 verdicts written before `output_sha256` existed (backfilled from the stored
reply). Every leaderboard and run-compare reads the same before and after the refactors, and
rescore writes the same 1337 files.
