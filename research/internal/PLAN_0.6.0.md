# Plan: 0.6.0, datasets from production (RFC-019) — the engineering plan, v2

## Status

- **v2**, 2026-10-29: after two independent reviews (advisor, Fable 5).
  - Review 1: B1–B3, M1–M11, m1–m12.
  - Review 2: "ready to build after three changes": R2-A to R2-K, r2-m1 to r2-m8.
  - Every finding is folded in, tagged with its id.
- v1 is in git history: `777b6cac`.
- **What we build.** How it is applied to the triage fleet is the application plan,
  [PLAN_0.6.0_FLEET.md](PLAN_0.6.0_FLEET.md): the data, the references, the arms, the runs, the cost.
- Branch: `060` (PR #30 open, green).
- Design: [RFC-019](../../docs/rfc/RFC-019-datasets-from-production.md), second draft. It is brought in line
  with this plan in P10, and every divergence is listed there.

## 1. Goal and what "done" means

0.6.0 adds a **capture lane** beside the method:

- an importer reads a production system;
- `evh capture` keeps the records;
- `evh dataset-from-capture` makes a dataset version;
- `evh reference-from-outcomes` takes a reference from what happened afterwards;
- `evh dataset-split` makes dev and heldout.

The lane ends in ordinary dataset and reference files. The method (materialize, run, rescore, compare, goals,
catalog) reads them as it reads any other.

Done (engineering) when:

1. Every command of the lane works, with its tests, on fixtures, offline.
2. The triage example's code (P8) and the de-duplication example's code (P9) run on the delivered data with a
   stand-in model, with no billed call. The billed runs belong to the application plan.
3. **The reference route is proven on a fixture catalog** (R2-A): the goal page decides on the reference the
   goal names.
4. `text: hidden` is enforced on every public surface, proved by a marker test.
5. Nothing existing changes behaviour for data without the new optional fields. The whole current suite (`make
   ci`, `make browser-check`, `make commands-check`, `make quality`) stays green. The only exceptions are the
   new commands' own required cases and the one render test that P6 updates (R2-J).
6. PR CI stays within the 0.6.0 goal (<= 8 min), and the release follows RELEASING.

## 2. Already done on 060

- **Part 1**, in PR #30: CI green in 7 min 6 s.
- **`1a6d2341`**: `evh mcp --public` sees only public fields in `inspect` (the 0.5.0 hole). Not pushed.
- **`18bc9de2`**: RFC-019 second draft. **`777b6cac`**: plans v1. Neither pushed.
- **Drafted, uncommitted**: `_importers.py` and `importers/*`. P1 fixes them.
- **The fleet's per-decision probe capture is live** (homelab, 2026-10-29: deployed with the owner's go; first
  file `20261029T221320Z__glitchtip_DELIVERY-4.json`).

## 3. Rules the plan keeps

- **A lane, not a rewrite.** New commands. Existing files gain optional fields only, outside identity:
  - a dataset's `tags`, `made_from` and `text`;
  - a reference manifest's `from_outcomes`.

  No existing command changes its arguments or its output for data without them.
- **Stateless.** Commands read and write the project's files. No server, no schedule.
- **Core stays generic.**
  - The importer mechanism is core.
  - The built-in importers live in `evaluation_harness/importers/`, loaded only by `--importer NAME`.
  - Fleet specifics live in the example.
  - Reading the fleet's production stores is the fleet's own script, not the lane (R2-E).
- **Everything works by default.** The standard library and `gh` only.
- **Vocabulary.** The new words are capture, importer, record and outcome. A dataset's own descriptors reuse the
  existing word **tags** (R2-K): the dataset-level form of `items[].tags` and `--tag`. This avoids `labels`,
  which already means a reference's answers and GitHub's labels.
- **CLI parity.** Every new view has an `evh` command, and the MCP read tools gain it.

## 4. Phases

Each phase ends with its tests green, `make quality` clean, and a local commit. A phase starts only when the
phases it depends on are committed.

### P1. Importers (core) — depends on nothing

**`_importers.py`:**
- `resolve --importer`:
  - built-ins through `importlib.import_module("evaluation_harness.importers." + name)` (m9);
  - `<data>/importers/<name>.py:Importer`, the name checked like a dataset id (m5);
  - `path.py:Class`.
- Ids: `[A-Za-z0-9][A-Za-z0-9._:@+=-]{0,199}` (m5).
- `normalise()`.
- **`record_sha256` over the canonical JSON of the whole normalised record**, outcome included (M2).
  `body_sha256` is kept apart, for the item's bytes.
- Docstrings everywhere, to the 100% floor (M1).

**`jsonl` and `tsv`:**
- the `_matches` precedence bug fixed (M1, r2-m8);
- dropped rows counted and printed (m2).

**`github`:**
- stops paging at `until` (m7);
- **records `actor { login }` on every close and reopen event** (R2-I), so a mapping can tell a person from a
  bot. Each outcome lists `close_events: [{at, reason, actor}]` and `reopen_events: [{at, actor}]`;
- the array variables and `duplicateOf` were verified live in review 1.

**`langfuse`:**
- refuses a non-`http(s)` host, then `# noqa: S310` (M1);
- writes `source.url` as a path only (m6).

**`evh importer-check NAME --query JSON [--limit N]`:**
- ids unique and well-formed, records well-formed, `created_at` parsed;
- both hashes stable over two reads;
- PASS/FAIL lines, exit 1 on a failure.

**Packaging:** `evaluation_harness.importers` added to `pyproject.toml`.

**Tests** (`tests/test_importers.py`), no network in CI:
- `jsonl` and `tsv`: mapping, where (an empty cell too), window, dropped-row count;
- `github` against a stand-in `gh` (`EVH_GH`): pagination, a duplicate, a reopen with its actor, the early stop;
- `langfuse` against a local HTTP stand-in: a non-http host refused, the path-only url;
- `importer-check` goes red on:
  - a duplicate id;
  - a bad id;
  - an over-long id;
  - a bad time;
  - an unstable hash;
  - an importer name that escapes `data/`.

**A live check, once, read-only:**
- `importer-check github` on chipi/orrery `triage-fleet/filed`;
- `importer-check langfuse` on the agents project;
- each reported with its output.

### P2. Captures — depends on P1

**`evh capture --importer NAME --query JSON|@file --capture C [--since-capture C_prev] [--force]`** writes:
- `data/captures/<C>/capture.json`:
  - the importer and its file's sha256;
  - the query verbatim, and its window;
  - when, and the count;
  - per record: id, created_at, url, `sha256`, `body_sha256`;
  - no user name (m4);
- `data/captures/<C>/records/<id>.json`.

Its rules:
- a capture is never overwritten without `--force`;
- `--since-capture` sets `since` from the earlier capture and skips its records by id (m3);
- it prints the commit-first reminder (M3).

**`evh capture-scrub C --command "... {records}"`:**
- runs the project's scrubber over the records;
- re-hashes: `sha256` (current) and `sha256_before_scrub` (M2);
- records the command, the sha256 of each file it names, when, and how many records changed;
- marks the capture unscrubbed if the scrubber fails.

**`evh captures [C]`**: every capture, or one.

**`schemas/capture.schema.json`, and V17 in `validate`**: a capture is valid and its records match `sha256`. It
passes with no captures.

**Tests:** end to end on `jsonl`:
- the files, and the `--force` refusal;
- `--since-capture` skipping by id;
- scrub with a stand-in scrubber, the two hashes, a failed scrubber;
- V17 red on an edited outcome.

### P3. A dataset version from a capture — depends on P2

**The command:** `evh dataset-from-capture C --dataset-id D [--from D_prev] [--where F:V ...]
[--dedup exact|text] [--one-per F] [--sample N [--by F] --seed S] [--fieldset FS --field F ...] [--tag k=v ...]
[--description ...]`.

**Selection:**
- `--where` matches dotted paths into the record's fields.
- `--one-per F` keeps one record per value of a field: the newest by `created_at`, ties broken by id (R2-H).
  The fleet's 236 decisions share 172 fingerprints, so a one-per-fingerprint version gives independent items
  for the paired test. Selection only; the stats are unchanged.
- `--field` is repeatable (m8).

**What it writes:**
- each kept record's **body** goes to `data/sources/<D>/<id>.<txt|json>`, through `body_bytes`. Only the body
  (B1);
- the dataset, through `dataset_create`'s functions (`_write`, `_lineage`, field checks);
- `made_from: {capture, query, where, dedup, one_per, sample, seed}`, and the tags.

**Fields:** only through a declared field set. Times are typed `date` (`YYYY-MM-DD`) or `text` (M5).

**Schema:** `dataset.schema.json` gains optional `tags` (a string map, dataset-level), `made_from` (an object,
with an optional `split`, m11) and `text` (`shown|hidden`).

**Views:** the catalog and `evh datasets` show tags and origin; `evh datasets --tag k=v` filters.

**Tests:**
- where on a dotted field; both dedup modes; `--one-per` keeps the newest per value;
- a seeded sample that repeats, and stratified sampling;
- lineage;
- materialize and a run on the result;
- tags round-trip, and `--tag` filters;
- an item's bytes unchanged when only its outcome changes;
- **an id containing `:` through materialize, a run, the inspector (URL-encoded) and an MCP call** (r2-m4).

### P4. References from outcomes — depends on P3

**The command:** `evh reference-from-outcomes --dataset-id D --capture C --map outcomes.yaml [--name NAME]`.
- No `--as-of` (M4): outcomes live in the capture.
- **The default name is `gold/<D>`**, the reference `experiment-run` scores against directly
  (`experiment_run.py:189-198`). `--name` writes it under another name, read by `rescore --reference-id` (R2-A).

**The mapping language** (M4, R2-I): an ordered list of rules. Each rule has:

| key | meaning |
|---|---|
| `when: {path: value or [values]}` | all must hold; a list in the record matches when any element does |
| `unless: {path: value or [values]}` | none may hold. For example, `close_events[*].actor: <the fleet's login>` excludes the bot's own closes, and `labels: triage-fleet/escalated` excludes escalation issues |
| `min_age_days: N` | the record is at least N days older than the capture |
| `within_days: {from: path, to: path, max: N}` | two times in the record at most N days apart. For example, the decision and the issue's filing |
| `label: <text>` or `skip: true` | what the rule gives |

The first matching rule wins. A record that matches no rule gets no label.

**The result** is a gold reference:
- its manifest carries `from_outcomes: {capture, mapping, mapping_sha256, matched, skipped, unmatched}`;
- **its own caveat** (M10): "OUTCOME: what production recorded afterwards, as of <capture date>; not a person's
  label";
- `reference.schema.json` gains the optional `from_outcomes`, and `authored_by` is unchanged.

**A goal decides on `gold/<D>`.** Another reference on the same dataset (a second outcome version, hand labels)
is second-named and read through `rescore --reference-id <name> --out data/runs-<name>`.

**Proof first** (R2-A): before P4 lands, a fixture catalog with one run in `runs` and its rescore in
`runs-<name>`. Read the goal page: it decides on `gold/<D>` only, and the rescore shows as its own base and does
not join the decision group. If it does join, P4 adds the smallest fix in the goal's grouping, and §5 names it.

**Tests:**
- the language: nested paths, `any`, `unless`, `min_age_days`, `within_days`, first match, skip, unmatched
  counted;
- the manifest and caveat, and V16;
- a run scored against it, coverage recorded, and the second-name route through rescore.

### P5. Splits — depends on P3

**The command:** `evh dataset-split D --heldout 0.3 [--by hash|time] [--key F] --seed S` writes `D_dev` and
`D_heldout`.

- `--key F` splits by a field's value, so all items with one fingerprint land on one side (R2-H).
- The default key is the item id.
- Each half records `made_from.split` (m11).

**Tests:**
- the proportion;
- stability across a grown version;
- `--key`: no value on both sides;
- the time split;
- the ids valid under the schema.

### P6. `text: hidden` on every public surface — depends on P3

- One function, `_visibility.text_shown(dataset_id, *, public) -> bool`.
- **`_release.py copy-data SRC DST`** (M9):
  - applies `text_shown`;
  - refuses untracked run outputs;
  - keeps today's reference refusal.

  `render.sh` calls it, and **`tests/test_render_data.py` is updated** (R2-J): it asserted the literal
  `harness/data/runs*` in `render.sh` (`:33`), and now it reads the module's list.
- The surfaces each ask the function:
  - the catalog's dataset page;
  - the inspector's `/api/item`, with `/api/compare` checked too;
  - MCP `dataset-items` and `inspect`;
  - `evh dataset-items` and `evh inspect` under `EVH_PUBLIC`;
  - the release copy.
- A profile written `--with-text` is checked again when the catalog builds.
- **The marker test** (`tests/test_hidden_text.py`), in-process (m10):
  - plant markers;
  - build the catalog, serve the inspector (`--public --publish outputs,references`) and MCP (`--public`);
  - call every route and tool, and run `copy-data`;
  - any marker that appears is a failure;
  - removing one surface's call to the function must turn it red.

### P7. Views and MCP — depends on P2 to P5

- **The datasets page**: tags as groups and filters, origin, and a version's profile beside its parent's.
- **MCP**: `captures` joins the read tools. The writing commands join NOT_TOOLS, with the reason: MCP write
  tools are 0.7.0.
- **`test_installed_commands.py`**: one case per new command (M8).
- **`check_commands`** knows every new command and flag. The browser checks cover the datasets page.

### P8. The triage example's code — depends on P3, P4 (r2-m7)

The code the application plan's runs need, built and tested without a billed call.

**`examples/triage-fleet/importer.py`** (B1) reads the JSONL the fleet's own build script makes (R2-E: that
script is committed in the fleet's repository, and its commit is recorded in the capture's query). It yields:
- `id`;
- `body = {signal, probes}`;
- `fields = {evidence_level, fleet_disposition, fleet_model, stage, fingerprint, decision_date}` (m12, r2-m3,
  M5);
- `created_at = fleet_decision.ts`;
- `outcome = row.outcome` plus `ground_truth`.

**`adapter.py`** calls `investigate(signal, probe_table=probes)` from the `TRIAGE_FLEET_SRC` checkout at a
recorded commit. It:
1. sets `SF_OBSERV_DISABLED=1` before the fleet's config is imported, and stubs `observ.new_trace_id` to `None`
   (M6). This keeps the fleet's own trace out of the run. **The gateway still logs every call to Langfuse**
   (R2-C):
   - the adapter adds `metadata: {tags: ["evh-eval", <run id>], trace_name: "evh-eval"}` to each call, through a
     wrapper on the fleet's `post_json`;
   - the eval key is tagged too (application plan).

   So eval traffic can always be told apart from production's.
2. sets `config.TRIAGE_MODEL = params.model`, and the gateway URL and key from the run's environment.
3. computes cost from `_meta.usage` × the config's `usd_per_mtok_in/out` (the fleet's `RATES` know only its own
   models). The usage carries no cached split (`triage.py:429-436`), so cost is computed at the uncached price,
   and the application plan estimates the same way (R2-C).
4. declares `TRANSIENT_MARKERS = ("triager call failed",)`.

**The call shape is the fleet's own** (`response_format: json_object`, `temperature: 0`). Whether every provider
accepts it is the application plan's smoke step (R2-C).

**The scorer** (m1), per item:
- `table_miss` on every item; nothing else is scored on a miss;
- `escalated` on every scored item;
- `correct`, `false_dismiss` and `silent_drop` only where the reference has a label;
- `cost_usd`, `latency_ms`, `n_probes`.

The reference text is a bare label or JSON `{disposition, correct_autonomous}` (M11).

**The goal file:** its primary measure, its axes (limits optional), and its strategy. It decides on `gold/<D>`
(R2-A). Which reference that is, and the limits, are the application plan's decisions.

**Reference routes:**
- hand labels: files, then `evh reference-manifest`;
- outcomes: P4;
- second names: rescore.

**Packaging** (M8):
- `pyproject.toml`;
- `fetch.py`, which verifies the `TRIAGE_FLEET_SRC` pin;
- `experiments.json`, only after the billed runs;
- no reproduce-matrix entry.

**A labelling sheet**, `examples/triage-fleet/label_sheet.py`. It writes the owner's labelling file for a chosen
set of items: id, signal summary, the probe answers in short, the fleet's decision and the outcome, plus an
empty `disposition` column. It also reads the file back into `gold/<D>/<item>.txt` and its manifest. It is a
file, not an interface (labelling interfaces are out of scope).

**Tests:**
- the importer on the delivered JSONL: 236 records; bodies free of `outcome` and `ground_truth`; bytes unchanged
  when an outcome changes;
- the adapter with a stubbed `_call`:
  - no network;
  - no Langfuse trace from the fleet (`trace_id is None`);
  - the `evh-eval` tag on every call;
  - cost from usage;
  - metrics recorded;
  - a table miss counted;
- the scorer on hand-made cases;
- the label sheet round-trip.

### P9. The de-duplication example's code — depends on P3 (r2-m7)

- **The adapter** returns `{operational, test, low_signal, norm_key}` from the fleet's pure functions
  (`filing.normalized_key`, `filing.low_signal`, `triage.operational_class`, `sources._is_test_signal`) (B3).
- **One arm, a regression guard** (R2-D). `alert_key_dedup_enabled()` is read only inside `ledger_lookup`, so
  switching it changes nothing here. The axis worth comparing is **the fleet's code itself**: the pinned
  previous commit against the current one, when the fleet changes its dedup functions.
- **Metrics:** `key_match` and `merged`.
- **Tests:** on the 100 signals, offline; two runs identical; a planted change to `normalized_key` shows up as
  `key_match` < 1.

### P10. Docs — with each phase, finished before release

**RFC-019** is updated, and **every divergence from the second draft is listed** (r2-m5). It is accepted with
what was built:
- importers by `<data>/importers/<name>.py` or `path:Class`, not `config.yaml`;
- `as_of` dropped, since outcomes live in the capture;
- escalations and cleanups labelled by rule, or not, as the application plan decides;
- the fleet's v1 is the 236 decisions, not 12 fixtures;
- "older decisions accepted as lost" was replaced by "everything kept, by evidence level";
- `labels` became `tags`;
- the mapping language;
- the caveat;
- the `gold/<D>` route;
- reading production is the project's own script.

**Other docs:**
- a basic PRD-014 (the lane for users), and a UXS section for the datasets page;
- the GUIDE links to an advanced tutorial;
- the RUNBOOK gets the commands and the commit-first rule;
- CHANGELOG 0.6.0, and the strict docs build;
- the example's README.

### P11. Release

- The full local gates.
- With the owner's go: push 060, then CI green.
- Merge, deploy within the 5-minute goal, tag, per RELEASING.
- No newcomer scenario.

## 5. What changes in existing code (the whole list)

- `pyproject.toml`: one package.
- `cli.py`: the new commands.
- `schemas/dataset.schema.json`, `schemas/reference.schema.json`: optional fields. `schemas/capture.schema.json`
  is new.
- `validate_tree.py`: V17.
- `catalog_build.py`, `catalog_views.py`, `view_datasets.py`: tags, origin, version profiles, `text: hidden`.
- `catalog_serve.py`, `mcp_server.py`, `dataset_profile.py`: the visibility function.
- `infra/deploy/render.sh`: calls `_release.py copy-data`.
- `tests/test_render_data.py`: reads the module's list (R2-J).
- `tests/test_installed_commands.py`: one case per new command.
- `dataset_create.py`: its writing functions are reused. Any change is a refactor, with its tests unchanged.
- **Only if P4's proof fails:** the smallest fix in the goal's grouping (`catalog_views.py` or
  `catalog_adapter.py`), named here before it is made.
- Untouched: `experiment_run`, `rescore`, the stats, compare, goals (unless the proof says otherwise), rounds.

## 6. Engineering assumptions (stated, not asked)

- Outcome references are gold, with their own caveat (M10).
- A dataset-level `tags`, not a new word (R2-K).
- A licence does not set `text: hidden` by itself.
- The fleet's code comes from a `TRIAGE_FLEET_SRC` checkout at a recorded commit.
- Captures are not supported on Windows.
- No auto-generated field sets.

## 7. Needs the owner

Nothing for the engineering. The application's decisions are in [PLAN_0.6.0_FLEET.md](PLAN_0.6.0_FLEET.md) §6.

## 8. Engineering risks

- **Dirty trees** (M3): commit first. The lane reminds.
- **The goal's grouping** (R2-A): proven on a fixture before P4 lands, not assumed.
- **Another repository's code**: pinned, and re-pinned visibly.
- **P6's reach**: kept to one function, one module and one test.
- **Size**: eleven phases, each its own commit.

## 9. Not in scope

A schedule, a server, write tools for agents (0.7.0), runners on another machine (0.7.0), a labelling interface
(P8's sheet is a file), holding a project's private data, concurrency in `experiment-run`, a paired test at a
cluster level (the `--one-per` version is the answer to dependence).
