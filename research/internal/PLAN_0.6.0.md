# Plan: 0.6.0, datasets from production (RFC-019) — the engineering plan

Status: revised after an independent review (advisor, 2026-10-29: "not ready as written; ready after the
fixes"); every mechanical finding is folded in, tagged with its review id (B1–B3 blockers, M1–M11 major,
m1–m12 minor). **What we build.** How it is applied to the triage fleet (the data, the references, the arms,
the runs, the cost, and the labelling question) is the separate application plan,
[PLAN_0.6.0_FLEET.md](PLAN_0.6.0_FLEET.md). Branch `060` (PR #30 open, green). Governing design:
[RFC-019](../../docs/rfc/RFC-019-datasets-from-production.md), second draft (`18bc9de2`), updated where this
plan corrects it (P4's mapping and caveat, P8's references).

## 1. Goal and what "done" means

0.6.0 adds a **capture lane** beside the method: an importer reads a production system, `evh capture` keeps
the records, `evh dataset-from-capture` makes a dataset version, `evh reference-from-outcomes` takes a reference
from what happened afterwards, `evh dataset-split` makes dev and heldout. The lane ends in ordinary dataset and
reference files, which the method (materialize, run, rescore, compare, goals, catalog) reads as it reads any
other.

Done (engineering) when:

1. Every command of the lane works, with its tests, on fixtures, offline.
2. The triage example's code (P8) and the de-duplication example's code (P9) run on the delivered data with a
   stand-in model, with no billed call; the billed runs are the application plan's.
3. `text: hidden` is enforced on every public surface, proved by a marker test.
4. Nothing existing changes behaviour for data without the new optional fields. The whole current suite
   (`make ci`, `make browser-check`, `make commands-check`, `make quality`) stays green unchanged, apart from
   the new commands' own required cases.
5. PR CI stays within the 0.6.0 goal (<= 8 min) and the release follows RELEASING.

## 2. Already done on 060

- Part 1, in PR #30, CI green in 7 min 6 s: SEO, share cards, MCP in phone menus, Node 24 actions, MCP
  observability, CI speed-up.
- `1a6d2341`: `evh mcp --public` sees only public fields in `inspect` (the 0.5.0 hole). Tested and
  mutation-checked; not pushed.
- `18bc9de2`: RFC-019 second draft; strict docs build green. Not pushed.
- The data, in the session scratchpad:
  - Orrery's 236 decisions, built by homelab from every store as of each decision's time and scrubbed by the
    fleet's `scrub.py`: `orrery-triage-items.jsonl`, sha256 `cacaf75f…`;
  - per evidence level: exact 33, full-rebuild 6, no-traces 17, no-logs 89, ledger-only 91;
  - the outcomes snapshot.
- The fleet's per-decision probe capture: the owner said yes, and homelab was asked to roll it out. Its
  confirmation is pending.
- Drafted, uncommitted: `harness/scripts/_importers.py` and `harness/scripts/importers/*`. P1 below fixes them.

## 3. Rules the plan keeps

- **A lane, not a rewrite.** New commands. Existing files gain optional fields only, outside identity: a
  dataset's `labels`, `made_from` and `text`; a reference manifest's `from_outcomes`. No existing command changes
  its arguments or its output for data without them.
- **Stateless.** Commands read and write the project's files. No server, no schedule.
- **Core stays generic.** The importer mechanism is core. The four built-in importers live in
  `evaluation_harness/importers/`, loaded only by `--importer NAME`. Fleet specifics live in
  `examples/triage-fleet/`, including the fleet's own importer (B1).
- **Everything works by default.** The built-in importers need only the standard library and `gh`; no new
  dependency.
- **Vocabulary kept.** New words: capture, importer, record, outcome.
- **CLI parity.** Every new view has an `evh` command; the MCP read tools gain it.

## 4. Phases

Each phase ends with its tests green, `make quality` clean, and a local commit. A phase starts only when the
phases it depends on are committed.

### P1. Importers (core) — depends on nothing

- `_importers.py`:
  - resolve `--importer`:
    - a built-in name, through `importlib.import_module("evaluation_harness.importers." + name)` (m9);
    - `<data>/importers/<name>.py:Importer`, the name checked like a dataset id so `../x` cannot leave
      `data/` (m5);
    - `path.py:Class`;
  - the record shape and its `problems()`. Ids: `[A-Za-z0-9][A-Za-z0-9._:@+=-]{0,199}` (m5). Ids containing
    `:` are valid file names on Linux and macOS; Windows is not supported for captures, and the docs say so;
  - `normalise()`;
  - **`record_sha256` over the canonical JSON of the whole normalised record** (body, fields, created_at,
    source, labels, outcome), so an edited outcome is caught (M2);
  - `body_sha256` separately, for the item's bytes.
- Built-in importers, with the review's fixes:
  - `jsonl` and `tsv`:
    - the `_matches` precedence bug fixed, so a `None` cell now matches `where: {col: ""}` (M1);
    - rows dropped for an unparsable time are counted and printed (m2);
  - `github`:
    - stops paging once `createdAt >= until`, since issues come in ascending creation order (m7);
    - the GraphQL array variables (`key[]=value`) and `ClosedEvent.duplicateOf` were verified live by the
      review;
  - `langfuse`:
    - refuses a host that is not `http(s)://` (closes the `file:` scheme; `# noqa: S310` after the check) (M1);
    - `source.url` is the path only (`/project/<p>/traces/<id>`), so no internal host name is committed (m6);
  - docstrings on every class and function, to the 100% interrogate floor (M1).
- `evh importer-check NAME --query JSON [--limit N]`. It checks that:
  - ids are unique and well-formed;
  - every record is well-formed;
  - `created_at` parses;
  - both hashes are stable over two reads.

  PASS/FAIL lines; exit 1 on a failure.
- Packaging: `evaluation_harness.importers` added to `pyproject.toml`.
- Tests (`tests/test_importers.py`):
  - `jsonl` and `tsv` on fixtures: mapping, where (including an empty cell), window, the dropped-row count;
  - `github` against a stand-in `gh` (`EVH_GH`) replaying a recorded GraphQL answer: pagination, a duplicate,
    a reopen, the early stop;
  - `langfuse` against a local HTTP stand-in: a non-http host refused, the path-only url;
  - `importer-check` red on a duplicate id, a bad id, an over-long id, a bad time, an unstable hash, and an
    importer name that escapes `data/`.

  No network in CI.
- A live check, once, read-only: `importer-check github` on chipi/orrery `triage-fleet/filed`, and `langfuse` on
  the agents project, each reported with its output. This also verifies the Langfuse parameter names.

### P2. Captures — depends on P1

- `evh capture --importer NAME --query JSON|@file --capture C [--since-capture C_prev] [--force]`.
  - It writes `data/captures/<C>/capture.json`: the importer, its file's sha256, the query verbatim, its
    window, when, the count, and per record its id, created_at, url, `sha256` and `body_sha256`.
  - **No user name** (m4).
  - It writes `data/captures/<C>/records/<id>.json`.
  - A capture is never overwritten without `--force`.
  - `--since-capture` sets `since` to the earlier capture's `until` (or its newest `created_at`), and **skips
    records already in it, by id** (m3).
- `evh capture-scrub C --command "python scrub.py --dir {records}"`.
  - It runs the project's scrubber and re-hashes. `capture.json` keeps `sha256` (current) and
    `sha256_before_scrub` per record; V17 checks `sha256` (M2).
  - `scrubbed` records the command, the sha256 of each file it names, when, and how many records changed.
  - A non-zero exit leaves the capture marked unscrubbed and says so.
- `evh captures [C]`: every capture, or one: importer, window, count, scrubbed, datasets made from it.
- `schemas/capture.schema.json`, and V17 in `validate`: a capture is valid and its records match `sha256`. It
  passes with no captures.
- **Dirty-tree rule (M3).** `_fingerprint.filter_dirt` ignores untracked paths only under `<data>/runs*`, so
  untracked captures, sources or importers mark every run dirty, and a dirty run cannot be promoted or be a
  reference's author. The lane's docs and RUNBOOK say: commit the capture, the sources and the dataset before
  any billed run. `evh capture` prints the same reminder.
- Tests: end to end on `jsonl`:
  - capture, the files, the `--force` refusal;
  - `--since-capture` skipping by id;
  - scrub with a stand-in scrubber, the two hashes, a failed scrubber;
  - V17 red on an edited outcome.

### P3. A dataset version from a capture — depends on P2

- `evh dataset-from-capture C --dataset-id D [--from D_prev] [--where F:V ...] [--dedup exact|text] [--sample N
  [--by F] --seed S] [--fieldset FS --field F ...] [--label k=v ...] [--description ...]`.
  - `--field` is repeatable; `--fields FILE` keeps its meaning in `dataset-create` (m8).
  - `--where` matches dotted paths into the record's fields.
- What it writes:
  - each kept record's **body** goes to `data/sources/<D>/<id>.<txt|json>`, through `body_bytes`. Only the
    body: fields, outcome and source never enter an item's bytes (B1);
  - the dataset is written through `dataset_create`'s functions (`_write`, `_lineage`, the field checks);
  - `made_from: {capture, query, where, dedup, sample, seed}` and `labels` are recorded.
- Fields become item fields only through a declared field set (RFC-006). Times are typed `date` as `YYYY-MM-DD`
  (a `decision_date`), or `text` for a full timestamp (M5).
- `--dedup text` folds case and whitespace. With `--from`, earlier items stay and new ones are added.
- Schema: `dataset.schema.json` gains optional `labels` (a string map), `made_from` (an object, with an
  optional `split`, m11) and `text` (`shown|hidden`, default shown).
- The catalog and `evh datasets` show labels and origin; `evh datasets --label k=v` filters.
- Tests:
  - selection: where on a dotted field, both dedup modes, a seeded sample that repeats, stratified sampling;
  - lineage on `--from`;
  - materialize and a run on the result;
  - labels round-trip; `datasets --label`;
  - an item's bytes unchanged when only its outcome changes.

### P4. References from outcomes — depends on P3

- `evh reference-from-outcomes --dataset-id D --capture C --map outcomes.yaml [--name NAME]`.
  - **No `--as-of`** (M4): outcomes live in the capture, so the reference's default name is
    `<D>_outcomes_<capture date>`, and newer outcomes mean a newer capture.
- The mapping language (M4) is an ordered list of rules. Each rule has:
  - `when: {dotted.path: value | [values]}`; a list in the record matches when any element does;
  - an optional `min_age_days: N`, which needs the record's `created_at` to be at least N days before the
    capture;
  - and `label: <text>`, or `skip: true`.

  The first match wins; no match means no reference for that item.
- The result is a gold reference under its own name (`gold/<NAME>/`, the second-reference route
  `gold/ag_news_200_adj1` uses):
  - its manifest carries `from_outcomes: {capture, mapping, mapping_sha256, matched, skipped, unmatched}`;
  - **its own caveat**: "OUTCOME: what production recorded afterwards, as of <date>; not a person's label"
    (M10). The tier stays gold, because people closed those issues; the RFC says why;
  - `reference.schema.json` gains the optional `from_outcomes`. `authored_by` and its readers are unchanged.
- Runs are scored against it with **`rescore --dataset-id D --reference-id gold/<NAME> --out
  data/runs-outcomes`** (B2). `experiment-run` scores only against `gold/<D>` (`experiment_run.py:189-198`).
  Coverage is recorded as today.
- Tests:
  - the language: nested paths, list "any", `min_age_days`, first match, skip, unmatched counted;
  - the manifest and its caveat; V16 on it;
  - a rescore against it, with coverage recorded.

### P5. Splits — depends on P3

- `evh dataset-split D --heldout 0.3 [--by hash|time] --seed S` writes `D_dev` and `D_heldout`.
  - By hash of (item id, seed), stable across versions; by time, the newest share is heldout.
  - Each records `made_from.split`, so the versions section says "a split of D", not "70% removed" (m11).
- Tests: the proportion, stability across a grown version, the time split, the ids valid under the schema.

### P6. `text: hidden` on every public surface — depends on P3

- One function, `_visibility.text_shown(dataset_id, *, public) -> bool`.
- The release's data copy moves from bash into a module, **`_release.py copy-data SRC DST`** (M9), which
  applies `text_shown`, refuses untracked run outputs and keeps today's reference refusal. `render.sh` calls it.
  The marker test calls it directly, so it runs in CI without the network.
- The surfaces (code audit 2026-10-29) each ask the function:
  - the catalog dataset page: profile text, per-item gold labels, URLs;
  - inspector `/api/item`; `/api/compare` checked;
  - MCP `dataset-items` and `inspect`;
  - `evh dataset-items` and `evh inspect` under `EVH_PUBLIC`;
  - the release copy.
- A profile written `--with-text` is checked again when the catalog builds.
- **The marker test** (`tests/test_hidden_text.py`), in-process (m10):
  - a fixture project with a hidden dataset, with markers planted in its sources, outputs, reference texts,
    judge reasons, field values and URLs;
  - it builds the catalog, serves the inspector `--public --publish outputs,references` and MCP `--public`,
    calls every route and tool, and runs `_release.copy-data`;
  - it fails if a marker appears anywhere;
  - its can-fail check removes one surface's call and requires the test to go red.
- Scope note (m10): no 0.6.0 dataset sets the label, since the triage data is public. It is built small: one
  function, one module, one test.

### P7. Views and MCP — depends on P2 to P5

- The catalog's datasets page shows labels as groups and filters, origin, and a version's profile beside its
  parent's.
- MCP: `captures` joins the read tools. `capture`, `capture-scrub`, `dataset-from-capture`,
  `reference-from-outcomes`, `dataset-split` and `importer-check` join NOT_TOOLS, with the reason that they
  write; MCP write tools are 0.7.0.
- **`test_installed_commands.py` needs a case per command (M8):** the seven new commands each get one.
- `check_commands` covers every new command and flag. The browser checks cover the datasets page.

### P8. The triage example's code — depends on P3, P4, P6

What the application plan's runs need, built and tested without a billed call.

- **Its own importer, `examples/triage-fleet/importer.py`** (B1), about 30 lines. It yields:
  - `id`;
  - `body = {signal, probes}`: only what the model sees, so the reference never enters an item's bytes;
  - `fields = {evidence_level, fleet_disposition, stage, model, fingerprint, decision_date}` (m12, M5);
  - `created_at = fleet_decision.ts`;
  - `outcome = row.outcome` plus `ground_truth`.
- **`adapter.py`** calls `investigate(signal, probe_table=probes)` from the fleet checkout named by
  `TRIAGE_FLEET_SRC`, at a recorded commit. It also (M6):
  1. sets `SF_OBSERV_DISABLED=1` before the fleet's config is imported, and stubs `observ.new_trace_id` to
     `None`, so no generation is written into the fleet's Langfuse project;
  2. sets `config.TRIAGE_MODEL = params.model`, and `SF_OPENROUTER_URL` / `OPENROUTER_API_KEY` from the run's
     environment;
  3. computes cost from `_meta.usage` × the config's `usd_per_mtok_in/out` (the fleet's `RATES` know only its
     own models);
  4. declares `TRANSIENT_MARKERS = ("triager call failed",)`.
- **The scorer** (m1), per item:
  - `table_miss` (0/1) on every item; nothing else is scored on a miss;
  - `escalated` on every scored item; it needs no reference;
  - `correct`, `false_dismiss` and `silent_drop` only where the reference has a label;
  - `cost_usd`, `latency_ms`, `n_probes`.

  The reference text is a bare label or JSON `{disposition, correct_autonomous}` (M11).
- **The goal file format** (B2): a primary measure with its direction and limit, an `escalated` axis with a
  limit, cost and speed shown, and a strategy; the goal names the reference it is decided on. Which measure
  and limits is the application plan's.
- **Reference routes, as they are** (M11, B2):
  - hand labels: files written as `gold/<D>/<item>.txt`, then `evh reference-manifest`;
  - outcomes: `reference-from-outcomes` (P4);
  - scoring a run against a second reference: `rescore --reference-id`.
- Packaging for `reproduce.py` (M8):
  - `examples/triage-fleet/pyproject.toml`;
  - a `fetch.py` that verifies the `TRIAGE_FLEET_SRC` pin;
  - the `experiments.json` entry only after the billed runs are committed, since `self_test` requires
    committed runs and their leader;
  - no reproduce-matrix entry: there is no no-key rerun.
- Tests:
  - the importer on the delivered JSONL: 236 records, the body free of `outcome` and `ground_truth`, an item's
    bytes unchanged when its outcome changes;
  - the adapter with a stubbed `_call`: no network, no Langfuse write (the stub asserts `trace_id is None`),
    cost from usage, the disposition and metrics recorded, a table miss counted;
  - the scorer on hand-made cases for each metric.

### P9. The de-duplication example's code — depends on P8 (corrected, B3)

- The fleet has no replay mode for `file_or_update` or `ledger_lookup`, and its corpus holds 100 signals and no
  expected issue. Its own eval uses pure functions: `filing.normalized_key`, `filing.low_signal`,
  `triage.operational_class`, `sources._is_test_signal`.
- The adapter returns `{operational, test, low_signal, norm_key}` from those functions.
- The per-item metrics are `key_match` and `merged` (the item's norm_key is shared within the run).
- Tests: on the fleet's 100 signals, offline, deterministic; two runs identical.

### P10. Docs — with each phase, finished before release

- RFC-019 updated:
  - accepted, with what was built;
  - the outcome caveat and why outcomes are gold;
  - the mapping language;
  - `rescore` as the route;
  - the project importer for the fleet.
- A basic PRD (PRD-014, the lane for users); a UXS section for the datasets page.
- GUIDE: one link to an advanced tutorial, "Datasets from production"; it is not in the getting-started path.
- RUNBOOK: the commands, and the commit-before-billed-runs rule. CHANGELOG 0.6.0. The strict docs build.
- `examples/triage-fleet/README.md`: the case, the references, the circularity, the numbers.

### P11. Release

- The full local gates. Then, with the owner's go, push 060 (PR #30 grows) and get CI green.
- Merge, deploy within the 5-minute goal, tag, per RELEASING. No newcomer scenario: the newcomer path does not
  change.

## 5. What changes in existing code (the whole list)

- `pyproject.toml`: one package.
- `cli.py`: new commands.
- Schemas:
  - `dataset.schema.json` and `reference.schema.json` gain optional fields;
  - `capture.schema.json` is new.
- `validate_tree.py`: V17.
- `catalog_build.py`, `catalog_views.py`, `view_datasets.py`: labels, origin, version profiles, `text: hidden`.
- `catalog_serve.py`, `mcp_server.py`, `dataset_profile.py`: the visibility function on their text surfaces.
- `infra/deploy/render.sh`: calls `_release.py copy-data` instead of its inline copy.
- `tests/test_installed_commands.py`: a case per new command.
- `dataset_create.py`: its writing functions reused. Any change is a refactor, with its tests unchanged.
- Untouched: `experiment_run`, `rescore` (used as it is), the stats, compare, goals, rounds.

## 6. Engineering assumptions (stated, not asked)

- Outcome references are gold under their own name, with their own caveat (M10).
- A licence does not set `text: hidden` by itself.
- The fleet's code comes from a `TRIAGE_FLEET_SRC` checkout at a recorded commit.
- Captures are not supported on Windows (ids contain `:`).
- The importer mechanism gains no auto-generated field sets: a project declares its own.

## 7. Needs the owner

Nothing for the engineering. The application's decisions (references, arms, budget) are in
[PLAN_0.6.0_FLEET.md](PLAN_0.6.0_FLEET.md).

## 8. Engineering risks

- **Dirty trees (M3).** An untracked capture, source or importer marks runs dirty, which blocks promotion and
  the reference route. The lane prints the reminder; the docs say commit first.
- **The adapter depends on another repository's code.** Pinning the commit makes a fleet change a visible
  re-pin. The adapter's tests run against the pinned checkout.
- **P6 touches the most existing code** for a label no 0.6.0 dataset sets. It is kept small: one function, one
  module, one test.
- **Size.** Eleven phases. Each lands as its own commit, with its tests, before the next one starts.

## 9. Not in scope

A schedule, a server, write tools for agents (0.7.0), runners on another machine (0.7.0), a labelling interface,
holding a project's private data, concurrency in `experiment-run`.
