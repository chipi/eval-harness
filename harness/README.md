# Eval harness — drop-in evaluation for a project that already works

You have a project. It summarises, classifies, extracts, answers — and it
works, mostly. What you do not have is a way to tell whether a change made it
better. You swap a model or edit a prompt, read a few outputs, and form an
impression.

This is the missing half. Pin it into your project, write **one function**
that calls your existing code, and you have a repeatable loop: frozen datasets,
runs that know what produced them, cost and speed alongside quality, and
comparisons that **refuse** to mislead you.

```bash
cd your-project
pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.5.0#subdirectory=harness"
evh init --tutorial    # the data folders, a .gitignore, and the tutorial kit
evh --help             # the verbs, in the order you need them
```

One install is everything: hosted-model clients, judges, the catalog, the inspector and `evh mcp`, the read
commands as tools for an agent ([INTEGRATION](docs/INTEGRATION.md#for-an-agent-evh-mcp)). Python 3.10 or later. It
imports nothing from your project until an arm names your adapter, and your project imports
nothing from it.

## The loop

Create a dataset, materialize it, run your arms, make a reference if you have none (often from
the best arm's run), compare, choose:

```bash
evh dataset-create --dataset-id my_v1 --source-dir data/sources/my_v1
evh dataset-materialize --dataset-id my_v1
evh experiment-run --config data/configs/best_model.yaml          # the arm that writes the reference
evh reference-create --dataset-id my_v1 --from-run <its run_id>    # optional: silver from that run
evh experiment-run --config data/configs/arm_a.yaml --repeat 3     # + the arm's own noise
evh leaderboard --dataset-id my_v1                                 # the ranking, and whether it is real
evh family-test --dataset-id my_v1 --a arm_a_v1 --against arm_     # is the winner separated?
evh run-promote --run <run_id> --reason "what the tests showed"    # the choice, with why
```

**[Getting started](../docs/GUIDE.md)** walks it once, offline, in about fifteen minutes; the
[tutorials](../docs/GUIDE.md#where-to-go-next) add a local model, a hosted LLM with your own
key, a frontier reference and judges, experiment rounds and dataset versions, and the catalog.
In a checkout of this repository every `evh` command is also a `make` target (`make demo` runs
the whole loop on bundled data, no API key, no network).

## Install it as a dependency

The package is code and schemas; your data stays in your project (`EVAL_HOME`, default the
nearest directory up from where you run with a `data/` folder; `EVAL_DATA_DIR`, default `data`). Already have runs scored by your own
code? `evh import-run` brings their per-item scores in, so the significance tests
can read them without re-running anything. Moving from a copied `harness/`:
[docs/UPGRADING.md](docs/UPGRADING.md).

## Why evaluation usually fails

Not for lack of a metric. It fails because the numbers turn out not to mean
what people thought:

| what goes wrong | what this does about it |
| --- | --- |
| two numbers measured on different data, compared anyway | `run-compare` **refuses** across `dataset_id`s |
| a delta smaller than the run-to-run jitter, called an improvement | `--repeat 3` reports the arm's own spread; deltas below it are marked noise |
| nobody knows which code produced a number | every run records `build.ref`; `validate` fails without it |
| a source file changed under a frozen dataset | every item is hashed; `materialize` re-verifies and fails loudly |
| model-generated references quoted as ground truth | gold and silver are distinct; every run records which it used |
| "model B is better" with no mention of 4× the cost | cost, tokens and latency recorded beside quality |
| a baseline nobody can justify | `promote` refuses a dirty build, an unknown build, or a reason under three words |

The refusals are the product. A tool that always yields a number teaches people
to trust numbers.

---

## How it works

Five directories and a contract between them:

```text
data/sources/        your raw inputs — IMMUTABLE, never edited in place
      ↓  evh dataset-create          freeze a selection + a sha256 per item
data/datasets/       the dataset_id — the thing that makes two numbers comparable
      ↓  evh dataset-materialize     rebuild run inputs, re-verify every hash
data/materialized/   derived, regenerable, disposable
      ↓  evh experiment-run          → scores + cost + speed + build provenance
data/runs/
      ↓  evh reference-create        ground truth to score against (gold | silver; --from-run a run's outputs)
data/references/
      ↓  evh leaderboard / pair-test / family-test / run-compare
data/baselines/      evh run-promote — the number future work is judged against

optional, later, from the same frozen outputs (the originals are never touched):
data/runs-rescored/  evh rescore        new reference or new code scorer, $0
data/runs-judged/    evh judge-score    a validated LLM judge, billed and capped

beside them, also optional:
data/goals/          what each evaluation is for; configs name one with `goal:`
data/rounds/         experiment rounds of a goal: evh round-open / rounds / round-close
data/fields/         field sets: the typed facts a project's items carry (`--fieldset`)
data/profiles/       evh dataset-profile   what is inside a dataset, for its page (no text by default)
.build/catalog/      evh catalog / evh catalog-serve   pages over the runs, and the inspector
(an agent)           evh mcp            the read commands as MCP tools
```

`evh validate` checks the whole tree — sixteen integrity rules (V1–V16), exits non-zero,
so it can gate CI.

### The three inputs

Every run records three things, and is worthless without all of them:

- **system under test** — `build.ref`, set by `EVAL_BUILD_REF` or the git SHA
- **instrument** — `config_id`, the arm you ran
- **data** — `dataset_id`, what it was measured on

Drop any one and a delta cannot be attributed to anything.

---

## Integrating your system

One function, `call_system()`, in `adapter.py` at your project's root. An arm whose
config names no `adapter:` uses it; a project with several tasks names one per arm
(`adapter: adapters/ner.py`):

```python
from evaluation_harness.adapter import Result

def call_system(text, params):
    from myproject.summarise import summarise        # your existing code
    out = summarise(text, model=params["model"])
    return Result(output=out.text,
                  tokens_in=out.usage.prompt_tokens,
                  tokens_out=out.usage.completion_tokens)
```

And one more, `score()`, for what "good" means in your domain. That is the
whole integration — no refactor, no wrapper, no base class.

Arms are **config files**, not code edits: four models to compare is four YAML
files sharing a `dataset_id`.

→ **[docs/INTEGRATION.md](docs/INTEGRATION.md)** — the first hour, concretely.

---

## Is the ranking real?

A table sorted by a mean always produces an ordering. Whether that ordering survives
re-running the experiment is a different question, and `evh leaderboard` answers it
before it shows you anything else:

```
IS THE ORDERING REAL?   metric=coverage  k=24 arms  N=20 items
  global test (permutation on within-item ranks): p = 0.0054 -> an arm effect exists
  Nemenyi critical difference = 8.13 rank positions; observed span = 8.57
  pairs distinguishable: 1 of 276
```

Three readings, all computed over the whole table at once:

- **Global test** — rank every arm *within* each item, then ask whether the average ranks
  are further apart than chance. On a real dataset most variance is "some items are hard
  for everyone" (66% here, against 3% between arms), and ranking inside the item is what
  removes it. If this fails, no ordering is supported and the output says so.
- **Nemenyi critical difference** — from the number of arms and items alone, how far apart
  two average ranks must be before that *pair* is distinguishable. Applied to every pair
  simultaneously, so it accounts for the fact that 24 arms means 276 comparisons and ~14
  of them will look significant by luck.
- **Rank probabilities** — resample the items, re-rank everything from scratch, and report
  how often each arm lands 1st / in the top 5 / in the bottom 5. This replaced a 95% rank
  interval per arm: those were marginal, so two non-overlapping intervals read as "this
  pair is separated" — exactly the claim they cannot make. Context, never a pairwise
  verdict; the critical-difference line is the verdict.

What this deliberately does **not** do is walk down the table comparing each arm to a
running "leader". That is a sorting algorithm, not a comparison: walked bottom-up instead
of top-down it partitions the same arms differently, and it once supported both a finding
and its retraction from one dataset.

## Re-measuring without re-running

Scores are arithmetic over outputs, and outputs are the expensive part. So a metric change
should not cost a sweep:

```
evh rescore --dataset-id my_v1 --match _v2 --out data/runs-rescored
EVAL_RUNS_DIR=data/runs-rescored evh leaderboard --dataset-id my_v1
```

Rescored runs go to a separate directory and record `derived: {kind: rescore, from, at, with}`:
the source run, when, and the sha256 of the adapter (and its scorer) that rescored it, so a
recomputation can never be mistaken for a measurement. Latency, cost
and token counts are carried across untouched — they describe the call that happened, not
how it was later measured.

This exists because a scorer bug survived two full sweeps: checking it would have cost a
third. When verifying a measurement is expensive, it does not get verified.

The same frozen outputs can be measured again in three ways, and none of them is required:

| kind | what changes | cost | command |
| --- | --- | --- | --- |
| new reference | what an output is scored against (gold a person adjudicated) | $0 | `evh rescore --reference-id gold/<id>` |
| new code scorer | the metric, as code | $0 | `evh rescore` |
| judge scorer | the metric, delivered by LLM judges validated against people | billed, capped | `evh judge-score` |

A **judge scorer** (`data/scorers/<id>.yaml`) names two or more judges from different vendor
families, the task they score, the prompt, and the runs that validated each judge against
human ratings. The command refuses a judge nobody validated (`--unvalidated` runs it with
every number labelled), freezes a blinded, shuffled judging set, stores every verdict so a
rerun costs $0, and writes scored runs that `leaderboard`, `pair-test` and `family-test`
read unchanged. An experiment's primary metric changes only by a recorded decision.
Walkthrough: [tutorial 3](../docs/tutorials/3-frontier-reference-and-judging.md#5-re-measure-with-an-llm-judge-optional);
reference: [RUNBOOK §12](docs/RUNBOOK.md#12-re-measure-with-a-validated-judge); why:
[ADR-0001](../docs/adr/ADR-0001-judge-scorers.md).

## Do you trust your reference?

Most of the time there is no gold, so a strong model writes the references — "silver" — and
you rank candidates against those. This asks whether that ranking matches the one real
ground truth would have given:

```
evh silver-calibrate --dataset-id my_v1 --ref-match _v1 --arm-match _v2
```

It costs nothing, because "author silver with model X using the same prompt and settings as
the arms" is exactly what X already produced — so every arm on disk is a candidate author
and all of them are tried.

Read the result against the **ceiling** it prints. Two runs of the same arms against the
same gold do not rank identically either, so that retest correlation is the best any proxy
could score. In the summarisation experiment's 24 hosted arms
([REPORT_SUMMARIZATION §3.5](../research/REPORT_SUMMARIZATION.md)): ceiling 0.92, silver
authors −0.01–0.70 (mean 0.33).

The number that matters most is the last one. Grouping arms by `family`, a silver author
**promotes models of its own kind by ~7 rank positions, for 22 of 24 authors** — and
excluding the author's own row does not remove it, because the bias is not an author
scoring itself, it is an author rewarding its own kind's style. A silver-ranked leaderboard
is not merely noisier than a gold one; it is biased in a direction you can predict from who
wrote it.

## Scoping a dataset that has grown

A dataset accumulates arms across config versions, and v1 and v2 of one arm are different
measurements that must not share a row:

```
evh leaderboard --dataset-id my_v1 --match _v2    only the v2 arms
evh leaderboard --dataset-id my_v1 --round r2     only the arms in play in a round
EVAL_RUNS_DIR=<dir> evh leaderboard --dataset-id my_v1   run or read somewhere else
```

`EVAL_RUNS_DIR` is how a smoke pass avoids adding repeats to a real sweep's arms and
silently moving numbers you have already reported. Use it whenever you are validating a
change rather than measuring something.

**Deleting old runs to make a table shorter is not the alternative to scoping it.** That is
how 18 arms of paid results were lost during this harness's own development.

## Docs

| | |
| --- | --- |
| **[Getting started](../docs/GUIDE.md)** | the loop once, offline, in about fifteen minutes |
| **[Tutorials](../docs/GUIDE.md#where-to-go-next)** | a local model against a baseline; a hosted LLM with your own key; a frontier reference, gold and judging; rounds and dataset versions; the catalog and the inspector |
| **[INTEGRATION.md](docs/INTEGRATION.md)** | plugging in an existing system; getting ground truth when you have none; connecting an agent (`evh mcp`) |
| **[CHANGELOG.md](CHANGELOG.md)** | what each release shipped, what can move a result |
| **[RUNBOOK.md](docs/RUNBOOK.md)** | every command and flag, step by step, with the reasoning; environment variables and exit codes |
| **[RELEASING.md](docs/RELEASING.md)** | pinning a release in your project, and cutting one: version, changelog, tag, GitHub Release |
| **[SCENARIO.md](docs/SCENARIO.md)** | the newcomer scenario run before every release: two experiments, real models, under $1 |
| **[UPGRADING.md](docs/UPGRADING.md)** | from one release to the next (what can move a number), and for a copy of the harness taken before October 2026 |
| **[CONCEPTS.md](docs/CONCEPTS.md)** | why each refusal exists, and the failure it prevents |

---

## The judge panel

The harness this grew around, and not the same thing as `evh judge-score` above: the
panel judges finalists one at a time and keeps no verdicts; the judge scorer judges every
arm, listwise and blind, behind a validation gate, and stores every verdict. Given many
candidate runs (`runs_from:` reads them where every command does, ranked by their primary
metric), the panel narrows to finalists (top-K per stratum + floor + global cap), scores
each finalist's stored outputs with an LLM judge, **aborts mid-run** if a cost cap is hit,
aggregates to per-dimension means, and flags finalists where two judges disagree.

```bash
evh judge --config tutorial/judge_panel.yaml --use-fake-judge   # no API key (`evh init --tutorial`)
ANTHROPIC_API_KEY=... evh judge --config judge_panel.yaml        # your own config
```

Use it when the cheap metric is known to be biased in your domain but you have
an expensive judge you trust: cheap metric for triage, judge for the answer.

Cost discipline is a **mid-run abort, not a pre-flight estimate** — estimates
are usually wrong, and an abort stops the bill the moment the cap is hit, with
partial results preserved so a blown budget still yields a usable report.

---

## Files

In a checkout of this repository; the package installs `scripts/` as `evaluation_harness`, so the
bundled adapter a pinned project has is `evaluation_harness/adapter.py`.

| Path | What it is |
| --- | --- |
| `Makefile` | the verbs — start with `make help` |
| `scripts/adapter.py` | the bundled adapter (token overlap, the worked example's), used when a project has no `adapter.py`; start yours from a copy |
| `scripts/dataset_create.py` | freeze a selection into a `dataset_id` |
| `scripts/materialize.py` | build run inputs, verifying every hash |
| `scripts/reference_create.py` | ground truth: a run's outputs as silver (`--from-run`), or authored with a config |
| `scripts/experiment_run.py` | run an arm → scores, cost, speed, provenance |
| `scripts/compare_runs.py` | compare two runs, or refuse |
| `scripts/promote_baseline.py` | run → baseline, or refuse |
| `scripts/validate_tree.py` | sixteen integrity checks (V1–V16) |
| `scripts/list_runs.py` | what runs and baselines exist |
| `schemas/` | the contracts: dataset, metrics (a run), baseline, config (an arm), goal, field set, judge scorer, judging set, verdict |
| `scripts/_fields.py`, `scripts/_fetch.py` | item fields (types, checks, the catalog's summary) and items fetched from a pinned URL (ADR-0003) |
| `scripts/stats.py` | the one paired test: `pair-test`, `family-test` and the inspector all call it |
| `scripts/rescore.py` | re-score stored outputs for a new reference or scorer, $0 |
| `scripts/judge_score.py`, `scripts/judging.py` | the judge scorer: gate, judging set, verdicts, projection; prompt, parser, judge client |
| `scripts/catalog_build.py`, `scripts/catalog_serve.py`, `catalog_assets/` | the catalog's pages, and the run inspector; `catalog_periods.py` the period (from today) and the trends, `catalog_arms.py` the arms page |
| `scripts/catalog_adapter.py` | what the catalog asks of a project's data, and `HarnessAdapter`, the answer for this layout |
| `scripts/catalog_views.py`, `scripts/view_*.py` | the catalog and the inspector in the terminal: `evh overview`, `activity`, `datasets`, `arms`, `references`, `metrics`, `goals`, `inspect` |
| `tests/` | this repository's tests (`make test`, `tests/self_test.py`) and the GUIDE and the offline tutorials run in a fresh project (`make guide-check`); not in the package. The ones that run `evh` install the real wheel (`tools/_wheel.py`, which the deploy uses too). `scripts/test_stats.py` ships: `evh self-test` runs it |
| `tools/` | this repository's report checks (`check_report_claims.py` and friends), judge validations and `*_report.py` tables; not in the package |
| `tests/test_inspector_browser.py`, `requirements-browser.txt` | the catalog and the inspector in headless Chromium: `make browser-install`, then `make browser-check` |
| `requirements-dev.txt` | the code-quality tools; from the repository root, `make quality-install`, then `make quality` |
| `scripts/judge_panel.py`, `scripts/panel_judges.py` | the judge panel (`evh judge`) |

Bundled providers: `echo` (no network), `openai` (OpenAI or any OpenAI-compatible endpoint),
`openrouter` (`OPENROUTER_API_KEY`, OpenRouter's address), `anthropic` and `litellm` (a LiteLLM
proxy). You choose one and bring your own key;
which variable each reads: [tutorial 2](../docs/tutorials/2-hosted-llm.md#1-choose-a-provider).
Most real integrations replace them with one function that calls their own system.

---

## See also

- [`../examples/`](../examples) — six worked examples, what each one found, and
  what each one broke in this harness.
- [`../research/`](../research) — the reports, the append-only journal, and a
  handover per example for the work that was not finished.
