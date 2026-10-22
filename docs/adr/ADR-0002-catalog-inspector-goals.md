# ADR-0002 — Catalog, run inspector and goals in the harness (0.4.0)

**Status:** Accepted (2026-10-21). The owner approved the design and all four open questions as
recommended (see the end of this note), except the alpha tags: 0.4.0 is built on one branch,
layer by layer, and released once. Built: layers 1 (stats), 2 (catalog and inspector), 3 (goals)
and the code of 4b (the deployment). Left: layer 4 (the podcast repo on the harness) and layer 5
(the release). Where the build differs from this note, see "As built" below.
**Date:** 2026-10-21

## Context

A project that pins the harness (the private podcast eval repo, on 0.3.0) built three things
the harness does not have:

1. **A catalog.** A static site over the project's data tree with:
   - pages for datasets, references, runs, baselines and reports;
   - charts of runs against references;
   - a "ceiling" chart: how far two references agree with each other.
2. **A run inspector.** A local server: pick runs on one `dataset_id`, see the per-item scores,
   and get a paired test of every run against a baseline, with:
   - an exact p-value;
   - a Holm correction over a declared family;
   - an exact confidence interval;
   - the verdict in words.
3. **Goals.** A registry of what a measurement is *for*:
   - who reads the output;
   - the output contract (format, length);
   - the measure that decides;
   - the references that count;
   - which runs are evidence.

   The project's configs name their goal; promotion records the output format; the validator
   checks both.

The owner decided (2026-10-21) that these are the main content of **0.4.0**:
- move them into the harness as a generic core with project adapters;
- make goals first-class in the harness;
- keep one implementation of the paired test.

This note proposes the split. **Nothing is moved until it is approved.**

### What exists today (podcast repo, `tools/catalog/`, about 3,900 lines)

| file | lines | what it is | generic? |
|---|---|---|---|
| `inspect_core.py` | 185 | `exact_p`, `sign_flip_p`, `holm`, `exact_ci`, `compare` | yes: no imports from the project |
| `serve.py` | 427 | inspector HTTP server: 127.0.0.1, Host check, path allowlist, `compare`, `episode` | mostly; calls the adapter |
| `build.py` | 2,199 | static catalog | mixed: page rendering is generic; task inference, model families, report and path conventions are not |
| `goals.py` | 466 | goal registry: collect, expand, answer blocks, pages | mostly; reads the adapter's references and arms |
| `podcast_adapter.py` | 583 | everything that knows the podcast layout | no, by design |
| `assets/` | — | `forest.js`, `inspect.js`, `catalog.js`, `catalog.css` | yes |

The generic code calls the adapter through about 18 functions:
- `arms_of`, `split_arm`, `scores`, `recorded_means`, `describe`, `notes`, `input_hashes`;
- `benchmark_results`, `dataset_of`, `run_metrics`;
- `references`, `reference_format`, `reference_view`, `episode_view`;
- `summary_format`, `is_neutral`, `lower_is_better`;
- plus two private helpers that must become public or go.

That set is the interface proposed below.

### What the harness has today

The paired test is written twice, each as a seeded Monte Carlo sign-flip (`(hits + 1) /
(permutations + 1)`, 20,000 permutations):
- `pair_test.py`;
- `family_test.py` (with Holm).

`leaderboard.py` has no pairwise sign-flip: its significance block is a Friedman permutation
test with Nemenyi, a different question, and it stays as it is. (A first draft of this note
counted it as a third copy; it is not.)

`inspect_core.exact_p` enumerates all 2^n sign patterns up to n = 30, so it is exact there,
and falls back to Monte Carlo above that. In the podcast repo, the Monte Carlo estimate flipped
three published verdicts that sat on the 0.05 line.

## Decision (proposed)

### 1. One paired-test module: `evaluation_harness.stats`

- `inspect_core.py` moves into the harness as `scripts/stats.py`, installed as
  `evaluation_harness.stats`.
- `pair_test`, `family_test` and the inspector all call it.
- The two private copies are deleted.

**This can change published numbers.** Above n = 30 nothing changes (it stays seeded Monte
Carlo). At n ≤ 30, a p that was a Monte Carlo estimate becomes exact. The harness's reports
are checked by `check_report_claims.py`, so the release is gated on that check: every p it
finds must be re-derived and either agree or be corrected in the same release. The changelog
lists each moved verdict under **Changed**. This is the "a change that can move a result"
case the changelog rules already require.

### 2. The adapter interface: `evaluation_harness.catalog.Adapter`

A `typing.Protocol` (Python 3.9 compatible; the package's floor stays 3.9). Grouped by
question:

| question | methods |
|---|---|
| what runs exist, on which data | `arms()`, `dataset_of(arm)`, `describe(arm)`, `notes(arm)` |
| what did each run score, per item | `scores(arm, rescore=False)`, `recorded_means(arm)`, `input_hashes(arm)` |
| which way is better | `lower_is_better(metric)`, `is_neutral(metric)` (descriptive keys) |
| what references exist | `references()`, `reference_format(ref)` |
| what was asked, what came back | `output_format(arm)` → `{asked, got, how}` (today `summary_format`) |
| one item, side by side (inspector only, never in static output) | `item_view(arm, item)`, `reference_view(ref, item)` |

Names change from podcast words to harness words: episode → item, `summary_format` →
`output_format`, `split_arm`/`arms_of` → `arms()` returning arm ids that already carry the
dataset.

The harness ships **one built-in adapter, `HarnessAdapter`**, over its own layout:
- `runs/*/metrics.json`, `predictions.jsonl`, `outputs/`;
- `baselines/`, `references/`, `datasets/`;
- the 0.3.0 judged runs under `runs-judged/<scorer>/`.

So `evh catalog` works on the harness's own data and on the tutorial with no project code. The
podcast repo keeps `podcast_adapter.py`, which implements the protocol over its older layout
and wraps its own re-scorers (ROUGE, NER) and `summary_format`.

### 3. Commands

- `evh catalog build [--adapter module:Class] [--out DIR]`: static site, default
  `.build/catalog`.
- `evh catalog serve [--port 8765]`: the inspector.

The adapter is named in `config.yaml` (`catalog.adapter: tools.catalog.podcast_adapter:Adapter`)
or by flag; the default is `HarnessAdapter`.

**Kept exactly as now, and tested in the harness:**
- No transcript, prediction or reference text in static output. Item text is served only by
  the local inspector.
- The server binds 127.0.0.1, checks the Host header, and serves only the build directory and
  the data tree.
- No mixed `dataset_id` in one comparison: a refusal, as in `run-compare`.

### 4. What stays project-side

These go in the adapter, or in an optional `catalog.yaml` the builder reads:
- task inference from run names;
- model-family rules (for the ⚑ same-family flag);
- ML vs LLM kind;
- report locations and `ANNOTATIONS.yaml`;
- the retired-pages list.

The harness ships the mechanism (flag same-family, show retired, annotate a reference), not the
podcast rules.

### 5. Goals become first-class

- **Schema:** `schemas/goal.schema.json`, from the podcast repo's 19 goals. Required:
  - `id`, `purpose`, `reader`;
  - `output_contract` (format, length);
  - `primary_measure`;
  - `references`, `evidence`;
  - `min_items`.

  Optional:
  - `secondary_measures`;
  - `generalization` (checks that never decide);
  - `links` (truth that lives elsewhere).
- **Location:** `data/goals/<id>.yaml`, beside `datasets/` and `configs/`.
- **Configs:** a `goal:` field on experiment configs. `experiment-run` copies it into the run
  fingerprint and `run-promote` copies it into the baseline.
- **Promotion:** `run-promote` records `format` (asked) and `format_observed` (got), using the
  adapter's or harness's `output_format`.
- **Validate:** `evh validate` gains the podcast repo's check A10, as a harness check:
  - every `goal:` resolves;
  - the format matches the goal;
  - a note when n < `min_items`;
  - new configs need a goal.

  "New" is measured from a date set in `config.yaml`, so an existing project is not failed
  retroactively.
- **Catalog:** goal pages, with the leader on each goal's primary measure and the paired test
  against it, as in the podcast repo now.

Goals are **optional for a project and required only from its cut-over date**: an existing
project upgrading from 0.3.0 changes nothing until it sets that date.

### 6. Build sequence: one branch, one release

| step | layer (one commit or more, same branch) | content | gate |
|---|---|---|---|
| 1 | stats | `stats.py` + `pair-test` and `family-test` moved onto it | self-test; `check_report_claims` re-derived; moved verdicts listed |
| 2 | catalog | `catalog` package, `Adapter` protocol, `HarnessAdapter`, `evh catalog build/serve` | catalog builds on harness data and the tutorial; server security tests ported |
| 3 | goals | goals: schema, `goal:` on configs, promotion `format`, validate check | tutorial gets one goal; validate passes on harness data |
| 4 | podcast repo | pins the branch head, deletes its copies of the generic code, keeps `podcast_adapter.py` | its full suite (1,212 tests) and `make catalog` give the same pages |
| 4b | site on the VPS | three addresses: `evals.humancopilot.eu` (the harness site: the harness and its findings) and `catalog.evals.humancopilot.eu` (the harness deployed on these experiments: catalog, goal pages, live inspector, item outputs included) on the prod VPS, Caddy in front and Docker behind; `docs.evals.humancopilot.eu` on GitHub Pages, old `/docs/...` URLs redirected. The inspector gets a public mode (host allowlist, arm cap, per-client rate, cache, warm start). Both sites pass a CSP with no `'unsafe-inline'`. Runbook: `infra/README.md` | deploy from `main` through a protected `prod` environment; the on-box health check; the live probes on both hosts |
| 5 | release | changelog, UPGRADING, GUIDE step for goals and the catalog | owner's merge |


Step 4 is the proof the split is right: if the podcast pages change other than by intent, the
interface is wrong, and that gets fixed before 0.4.0.

## Consequences

- The inspector's statistics and the CLI's statistics can no longer disagree.
- Any project on the harness gets a catalog and inspector with one adapter file, or none if it
  uses the harness layout.
- The package gains a `markdown` dependency (the catalog renders reports). Proposal: make it an
  extra, `evaluation-harness[catalog]`, so the core stays `pyyaml` + `jsonschema`.
- The podcast code uses 3.10 syntax (`X | None`). The move needs `from __future__ import
  annotations` throughout (already in most files) or `Optional`, because the package's floor
  is 3.9.

## Owner's decisions (2026-10-21)

1. **Exact p in the CLI: yes.** `pair-test` and `family-test` are exact at n ≤ 30 in 0.4.0.
   Re-deriving the reports moved nothing: all 201 report claims hold, because every published
   pair and family test is on more than 30 items. The tutorial's 6-item p-values changed and
   its verdicts did not (CHANGELOG 0.4.0).
2. **Goal cut-over: a date the project sets.** Nothing is required of an upgrading project
   until it sets one.
3. **The harness's own catalog: published** with the harness site, since it holds only public
   data. The privacy rule (no item text in static output) applies there as everywhere.
4. **No intermediate releases.** One branch, one layer per step, CI on every push, one 0.4.0
   release at the end.
5. **Hosting:** the public site moves to the prod VPS with the catalog beside it; the docs move
   to their own host on GitHub Pages (layer 4b).

## As built

The decision above is kept as it was accepted. Where the code came out differently, this is
what it does (checked against the branch, 2026-10-22):

| the note says | the code does |
|---|---|
| `evh catalog build` and `evh catalog serve` | two commands: `evh catalog` and `evh catalog-serve` (`make catalog`, `make catalog-serve`) |
| the adapter named as `module:Class` in `config.yaml` | `catalog: {adapter: path/to/file.py:Class}` or `--adapter`, a file path or a module |
| the module `evaluation_harness.catalog.Adapter` | `evaluation_harness.catalog_adapter.Adapter`; the built-in adapter is `HarnessAdapter` in the same module |
| goal fields `id`, `purpose`, `reader`, `output_contract`, `primary_measure`, `references`, `evidence`, `min_items` | `schemas/goal.schema.json` requires `goal_id`, `title`, `statement`, `decision`, `success_criteria` (the primary measure and its direction) and `datasets`; `context`, `output_contract`, `references`, `measures` and `min_items` (inside `success_criteria`) are optional |
| `experiment-run` copies `goal:` into the run fingerprint | the run records `goal` and `format` beside the fingerprint, not in it: they change what a run answers, not what it measured |
| `run-promote` records `format` and `format_observed` | `run-promote` carries `goal` and `format` (asked) onto the baseline; no observed format is recorded |
| a cut-over date in `config.yaml` | `required_from` in `data/goals/policy.yaml` |
| the catalog renders reports, so a `markdown` dependency (an extra) | the catalog renders no reports; no dependency was added |

## Not covered by this note

- **Performance.** Build time over the harness's ~36,000 run files has not been measured; the
  podcast tree is smaller. The note assumes it is acceptable; step 2 measures it.
- **The podcast-specific re-scorers** (ROUGE against every live reference, NER) stay
  project-side. Whether the harness's own `rescore` should feed the inspector is left for
  later.
- **The judge-assisted insight gold set** (podcast goal G3) and the human check on judge
  rankings are project work, not harness work.
