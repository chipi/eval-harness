# RFC-003: The catalog, the inspector server and the adapter protocol

- **Status**: Completed (v0.4.0); the podcast repository runs on it from its own `harness-0.4.0` branch (layer 4)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-004](../prd/PRD-004-catalog-and-inspector.md), [PRD-005](../prd/PRD-005-goals-and-rounds.md), [PRD-006](../prd/PRD-006-datasets-versions-fields.md)
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md), [UXS-002](../uxs/UXS-002-inspector.md), [UXS-003](../uxs/UXS-003-cli-and-onboarding.md)
- **Related ADR**: [ADR-0002](../adr/ADR-0002-catalog-inspector-goals.md)
- **Code**: `harness/scripts/catalog_adapter.py` (protocol, `HarnessAdapter`, loader),
  `catalog_build.py` (pages), `catalog_serve.py` (server), `catalog_views.py` (the terminal
  views), `stats.py` (the paired test); tests `harness/tests/test_catalog.py`,
  `harness/tests/test_inspector_browser.py`

## Abstract

The catalog builder and the inspector server never read a project's files directly: they ask an
**adapter** a fixed set of questions (which arms exist, what each scored per item, which way is
better, which references exist, what one item looked like). The harness ships one adapter,
`HarnessAdapter`, over its own layout, so a project on that layout writes no code; a project with
another layout writes one class. The terminal views (`evh datasets`, `references`, `metrics`,
`goals`, `search`, `inspect`) ask the same adapter and call the same functions, which is how
command-line parity is kept.

## Background

A project that pins the harness (the private podcast evaluation repository, on 0.3.0) had built
a catalog, an inspector and goals of its own, about 3,900 lines in `tools/catalog/`: the paired
test (`inspect_core.py`), the server (`serve.py`), the static builder (`build.py`), the goal
registry (`goals.py`), a project adapter (`podcast_adapter.py`) and the assets. The harness's own
paired test was written twice (`pair_test.py`, `family_test.py`), as seeded Monte Carlo; the
project's `exact_p` was exact up to 30 items, and in that repository the Monte Carlo estimate had
flipped three published verdicts that sat on the 0.05 line. The owner decided (2026-10-21) that
the generic part moves into the harness as 0.4.0, with one implementation of the paired test
([ADR-0002](../adr/ADR-0002-catalog-inspector-goals.md)).

## Design

### One paired test

`evaluation_harness.stats` (standard library only) holds `exact_p` and `sign_flip_p`, `holm`,
`exact_ci`, `compare` (every arm against a baseline, with verdicts in words) and `compare_by`
(the same within each group of items, Holm-corrected over every group and arm together).
`pair-test`, `family-test`, the inspector and `evh inspect` all call it. The leaderboard's
Friedman and Nemenyi test answers another question and stays separate.

### The adapter protocol (`catalog_adapter.Adapter`)

A `typing.Protocol`; every method must be cheap to call twice.

| question | members |
| --- | --- |
| which arms, on which data | `arms()`, `arms_of(path)`, `describe(arm)`, `notes(arm)` |
| what each scored, per item | `scores(arm, rescore=False)`, `recorded_means(arm)`, `input_hashes(arm)`, `can_rescore` |
| which way is better | `lower_is_better(metric, dataset)`, `is_neutral(metric, dataset)`, `preferred_metrics`, `shape_metrics` |
| which references | `references()`, `reference_format(ref)`, `reference_archived(ref)` |
| what was asked, what came back | `output_format(arm)` → `{asked, got, how}` |
| one item, side by side (the inspector only) | `item_view(arm, item)`, `reference_view(ref, item)` |
| what it is for | `goals()`; an arm's goal is `describe(arm)["goal"]` |
| words and places | `item_word`, `data_dir` |

Optional members, each read with `getattr` so an adapter without them still works:
`item_fields(dataset)`, `dataset_items(dataset)`, `metric_descriptions()`, `conditions(arm)`,
`baselines()`, `arm_of(dataset, config_id)`, `reference_free(metric)`, `rounds()`, `datasets()`,
`dataset_lineage(dataset)`, `dataset_created(dataset)` (when it was frozen; the period pages count it
new from that day, else from its first run), `dataset_profile(dataset)` (0.5.0: what is inside a dataset,
without its text, from `data/profiles/<dataset>.json`; the dataset page's "what's inside", with `stale` when its
items digest is not the dataset's), `served_dirs`, `arm_runs(arm)` → `[{"run_id", "created_at", "items",
"cost_usd", "derived"}]`, `arm_config(arm)` → `{"config_id", "params" (credentials removed),
"adapter"}`, `spend()` → `[{"at", "usd", "tokens", "kind": "arm"|"judge", "dataset", "what", "arm"}]`
(usd or tokens None when unknown; measured runs and judging per set and day; `arm` names a
measured run's arm, which the arms and activity pages bill it to), and on
`HarnessAdapter` `item_text(dataset, item)` (the item itself, local inspector only).
`item_view(arm, item)` returns one of the inspector's view kinds: `text`, `none`, or a
structured `insights`, `nodes` or `entities`, each optionally with `info`. `describe(arm)` may
carry `reference`, `judge`, `wrote_reference`, `goal`, `format`, `primary` and `runs`, which
drive the row tints and the goal page. `notes(arm)` says, in words, why something could not be
scored, and which of the arm's runs were left out; the inspector's comparison prints it among its
notes, and so does `evh inspect`.

### `HarnessAdapter`

Reads `<data>/runs*/<run_id>/{metrics.json, predictions.jsonl, outputs/}`,
`<data>/runs-judged/<scorer_id>/`, `<data>/references/<tier>/<dataset_id>/`, `<data>/datasets/`,
`<data>/goals/`, `<data>/baselines/` and `<data>/rounds/`. An arm id is
`<runs dir>/<dataset_id>/<config_id>`: every repeat of a config on a dataset, averaged per item,
as `pair-test` reads them, so the inspector gives the same p. An arm is read against one
reference, the one its latest run (by `created_at`) was scored against: its runs scored against
another reference are left out, never averaged in, and `notes(arm)` names them ("N earlier
run(s) scored against <ref> left out: this arm is read against <ref>, the reference of its
latest run"). `can_rescore` is false. Item scores
are read with the same `score_of` the paired tests use.

### Loading a project adapter

`load_catalog_adapter(spec)`: `--adapter`, else `config.yaml`'s
`catalog: {adapter: path/to/file.py:Class}` (a file path or a module, then the class), else
`HarnessAdapter`. Subclassing `HarnessAdapter` and overriding what differs is usually shorter
than starting empty ([Integration](../../harness/docs/INTEGRATION.md#the-catalog-and-the-inspector)).

### The build (`catalog_build.build`)

`collect(A)` reads every arm once into `{dataset: {arms, refs, items, baselines, parent,
children}}`, then renders home, datasets, goals, metrics, references, the search index
(`search.js`), and the inspector shell with `runs.js` (arm id → dataset). The output embeds counts
and means only. Pages load `assets/head.js`, `search.js`, `catalog.js` and, on the inspector,
`inspect.js` as files: no inline script or style, so a CSP without `'unsafe-inline'` holds. On
this repository's data (194 arms, 9 datasets) the build takes under a second
(`evh catalog`, measured 2026-10-24: 0.58 s wall time).

### The server (`catalog_serve.py`)

- `GET /api/compare?runs=…[&baseline=][&metric=][&rescore=0][&family=][&threshold=][&where=…][&by=]`:
  every arm's per-item scores on one metric, each arm tested against the baseline with
  `stats.compare`, plus notes, conditions, fields and the breakdown. Every answer ends in one of
  four states: `compared`, `average only`, `no shared metric`, `not scorable`.
- `GET /api/item?arms=…&item=…[&ref=]`: each arm's output for one item, the reference's, the
  item's fields and, locally, the item itself.
- `GET /api/health`.
- **Local mode** (default): binds 127.0.0.1, answers only a `127.0.0.1` or `localhost` Host
  (against DNS rebinding), serves only the built catalog, the data tree and the adapter's
  `served_dirs`, never a `..` path or a dot-folder; refuses `--bind` other than 127.0.0.1 without
  `--public`, and a `--build-dir` outside the project.
- **Requests name only what the catalog lists:** an arm `arms()` reaches, a reference
  `references()` lists. (The podcast adapter mapped any path to itself, which let `compare` read
  `runs=../../.git`; fixed in 0.4.0.)
- **Public mode** (`--public HOST[,HOST]`): the API only, behind a proxy that serves the static
  pages; named hosts only; `--rate` requests per client per minute (`CF-Connecting-IP`, else the
  peer); `--max-arms` per comparison (40 by default, locally too); two computations at once;
  every answer cached by its exact question; errors without internals; only public fields; no
  item itself from `/api/item`, and outputs or reference text only for what `--publish outputs,references`
  names (default: neither). `--warm DIR` computes every comparison the built catalog links to.
- The server reads the runs once; a new run needs a restart.

### This repository's deployment

`evals.humancopilot.eu/catalog` serves this repository's catalog and a public-mode inspector on
the prod VPS behind Caddy, beside the public site and the docs (at /docs/; a copy is also on GitHub Pages). Runbook:
[`infra/README.md`](https://github.com/chipi/eval-harness/blob/main/infra/README.md).

## As built, against the accepted note

ADR-0002's note (2026-10-21) proposed names and fields that changed while it was built:

| the note said | the code does |
| --- | --- |
| `evh catalog build` and `evh catalog serve` | `evh catalog` and `evh catalog-serve` (`make catalog`, `make catalog-serve`) |
| the adapter as `module:Class` in `config.yaml` | `catalog: {adapter: path/to/file.py:Class}` or `--adapter`, a file path or a module |
| `evaluation_harness.catalog.Adapter` | `evaluation_harness.catalog_adapter.Adapter`, with `HarnessAdapter` in the same module |
| goal fields `id`, `purpose`, `reader`, `output_contract`, `primary_measure`, `references`, `evidence`, `min_items` | `goal_id`, `title`, `statement`, `decision`, `success_criteria`, `datasets` required (see [PRD-005](../prd/PRD-005-goals-and-rounds.md)) |
| `experiment-run` copies `goal:` into the fingerprint | `goal` and `format` beside the fingerprint, not in it |
| `run-promote` records `format` and `format_observed` | it carries `goal` and `format` (asked); no observed format |
| a cut-over date in `config.yaml` | `required_from` in `data/goals/policy.yaml` |
| a `markdown` dependency to render reports | the catalog renders no reports; no dependency was added |

## Alternatives Considered

- **Keep the catalog in the project.** Rejected: two paired tests that could disagree, and every
  project rebuilding the same pages.
- **A database behind the inspector.** Rejected: the data tree is the record; the adapter reads
  it as it is.
- **A server that writes decisions.** Set aside: the public deployment depends on "the server
  never writes" ([ADR-0004](../adr/ADR-0004-experiment-rounds.md)).

## Open

- **Layer 4:** the podcast repository pins the branch, deletes its copies of the generic code and
  keeps `podcast_adapter.py`; its suite and its catalog must give the same pages. Not done at the
  time of writing; ADR-0002's code column stays Partial until it is and 0.4.0 is released.
- Whether the harness's own `rescore` should feed the inspector (`can_rescore` on
  `HarnessAdapter`) is left open.

## Testing

- `harness/tests/test_catalog.py`: the build, no item text in the static pages, the inspector's
  numbers against `pair-test`'s, its refusals (mixed datasets, unknown arms), and the server's
  rules (127.0.0.1 Host only, only the catalog and the data tree, no dot-folders).
- `harness/tests/test_inspector_browser.py` (`make browser-check`): the pages and the inspector in
  headless Chromium.
- `harness/scripts/test_stats.py`: the paired test's own suite, shipped with the package.
