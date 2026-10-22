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
| pip-audit | harness requirements: 0 | 0 | none in what the package declares; see "Open" for the examples' locks |
| vulture (80%) | 1 | 0 | dead code (removed); later, an unused parameter in a test written the same day |
| interrogate | 53.5% | ratchet at 53% | none (a coverage measure, not a defect finder) |
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

## Open, for the owner

- **The examples' `uv.lock` files carry advisories**: transformers 4.55.4 (13 in every
  example), pillow 12.3.0 (34, scifact), aiohttp 3.14.3 (8, few-nerd), sentence-transformers
  3.4.1, nltk 3.10.3 and certifi 2026.7.22. Those pins are the environment the published
  numbers were measured in, so upgrading one changes the instrument. `make audit-locks`
  reports them and does not fail. Whether to gate on them is a decision, not a fix.
- **Docstrings**: podcast requires 100% with the same exemptions; this repo is at 53.5% (161
  public functions without one). The gate is a ratchet that stops it falling.
- **The `quality` CI job is not yet a required check on `main`.**
- Three separate `spearman` implementations exist (`judging`, `rank_stability`,
  `summeval_analysis`). Not changed here.
