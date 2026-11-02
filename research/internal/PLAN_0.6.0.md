# Plan: 0.6.0, datasets from production (RFC-019) — the engineering plan, v3

## Status

- **v3**, 2026-10-30: after three independent reviews (advisor, Fable 5).
  - Review 1: B1–B3, M1–M11, m1–m12.
  - Review 2: R2-A to R2-K, r2-m1 to r2-m8.
  - Review 3: "ready to build after three changes": R3-E1 to R3-E5, r3-m1 to r3-m9.
  - Every finding is folded in, tagged with its id.
- v1 and v2 are in git history: `c944a1a9`, `ee5b8bbd` on main.
- **What we build.** How it is applied to the triage fleet is the application plan,
  [PLAN_0.6.0_FLEET.md](PLAN_0.6.0_FLEET.md): the data, the references, the arms, the runs, the cost.
- Branch: `060-capture`, from main `5e6209cc` (PR #30 merged and deployed).
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

**The order: one thin path end to end first, then the breadth** (owner, 2026-10-30). The phases below are
what gets built; they are built in two passes.

1. **The walking skeleton**, the triage case with a stand-in model ($0):
   - P1, `jsonl` only, plus `importer-check`;
   - P2, `capture` only;
   - P3, without `--one-per` or tags;
   - P4, with its proof (exactly one recommendation on the goal page);
   - P8, the triage importer, adapter and scorer;
   - one run on the delivered 236 items, and its goal page.

   This proves the risky parts first: the reference route (R2-A, R3-E3), the outcome mapping on real data
   (R3-E2), and the adapter calling the fleet (M6). Each step lands as its own commit with its tests.
2. **The breadth**, each widening a path that already works:
   - P1's `tsv`, `github` and `langfuse`;
   - P2's scrub and `captures`;
   - P3's `--one-per` and tags;
   - P5;
   - P6;
   - P7;
   - P9;
   - P10's docs, finished.

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
- **records, for every close and reopen event, its actor and the comment beside it** (R2-I, R3-E1): author,
  time and the first 300 characters. A fleet that writes to GitHub with its owner's token (the triage fleet
  does: every close and reopen is `chipi`'s) can only be told apart by its comment text (`Recurred …`,
  `signal-fleet`), and a person's close comment carries the verdict ("Fixed in v0.8.0", "external browser
  noise"). Each outcome lists `close_events: [{at, reason, actor, comment}]` and `reopen_events: [{at, actor,
  comment}]`;
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
- `github` against a stand-in `gh` (`EVH_GH`): pagination, a duplicate, a reopen with its actor and comment, the early stop;
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
- **It never overwrites a reference** (R3-E4): if the target exists, it refuses and names `--name`.

**The mapping language stays small** (M4, R3-E2): an ordered list of rules over a record's **flat outcome
fields**. A project's importer computes those fields (`issue_verdict`, `days_to_filing`, `seen_again`, …;
P8 lists the triage fleet's), because the time arithmetic and list logic a real mapping needs (signed
differences, "a later element with both conditions", "an empty list") are the project's semantics, not a
language's. Each rule has:

| key | meaning |
|---|---|
| `when: {field: value or [values]}` | all must hold |
| `unless: {field: value or [values]}` | none may hold |
| `exists: [field, ...]` / `absent: [field, ...]` | the field is present and not null / missing or null |
| `range: {field: {min: N, max: N}}` | a number within bounds (either bound optional; signed) |
| `min_age_days: N` | the record is at least N days older than the capture |
| `label: <text>` or `skip: true` | what the rule gives |

The first matching rule wins. A record that matches no rule gets no label. Fields are top-level names in the
record's `outcome`, so there is no path syntax to define.

**The result** is a reference, gold or silver by its name:
- its manifest carries `from_outcomes: {capture, mapping, mapping_sha256, matched, skipped, unmatched}`;
- **its own caveat** (M10): "OUTCOME: what production recorded afterwards, as of <capture date>; not a person's
  label";
- `reference.schema.json` gains the optional `from_outcomes`, and `authored_by` is unchanged.

**A goal decides on `gold/<D>`.** Every other reference on the same dataset carries a tier and a second name
(R3-E3): `reference_manifest` requires `<gold|silver>/<name>`, `rescore` derives the tier from the prefix, and the
catalog lists only `gold/*` and `silver/*`. Two gold references on one dataset would each get a decision on
the goal page (`catalog_build.py:1928-1930, 2375`), while silver groups are shown beside gold and never decide
(`:2564-2569`). So a second reference is **`silver/<name>`**, with its own caveat saying what it is
(ADR-0020; the owner's vocabulary call, proposed there). It is read through `rescore --reference-id
silver/<name> --out data/runs-<name>`.

**Proof first** (R2-A, R3-E3): before P4 lands, a fixture catalog with a run in `runs` scored on `gold/<D>`, and
its rescore on `silver/<name>` in `runs-<name>`. The goal page shows **exactly one recommendation**, from
`gold/<D>`, and the silver group beside it. If not, P4 adds the smallest fix in the goal's grouping, and §5
names it.

**Tests:**
- the language: `when`, `unless`, `exists`, `absent`, `range` with a signed value, `min_age_days`, first
  match, skip, unmatched counted;
- the refusal to overwrite an existing reference;
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
- `outcome`: the **flat fields** P4's rules read (R3-E2), computed here from the fleet's record:
  - `issue_number`, `issue_verdict` (`fixed`, `noise`, `duplicate`, `open`, `unknown`: from the close comment,
    following a duplicate to its target), `is_escalation_issue`, `is_config_followup` (the dismiss decision's
    own `[config]` proposal), `issue_predates_decision`, `days_to_filing` (signed), `reopened`;
  - `seen_again`, `later_file_within_days`, `age_days`;
  - `test_signal` (a blank-stage probe, R3 A5), `stage`;
  - and `ground_truth` (the fixture labels).

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

**The scorer** (m1, R3-E5), per item:
- `table_miss` on every item; nothing else is scored on a miss;
- `escalated` on every scored item;
- only where the reference has a label, and **otherwise the key is left out, never `None` or 0** (the aggregate
  averages only the rows that carry a key, `experiment_run.py:310-312`; `_runs.score_of` returns None for a
  missing key):
  - `correct`: the disposition equals the label;
  - `false_dismiss`: the label is `file` or `escalate`, and the arm dismissed or cleaned up;
  - `false_alarm`: the label is `dismiss` or `cleanup`, and the arm filed or escalated;
  - `silent_drop`: `correct_autonomous` is `escalate`, and the arm dismissed;
- `cost_usd`, `latency_ms`, `n_probes`.

A `not-file` label (a filed issue closed as not planned) counts as `dismiss` for these rules.

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
- the `gold/<D>` route, and second references as `silver/<name>` with their own caveat (R3-E3);
- outcomes read from the close comment's verdict, not GitHub's close reason (R3-E1);
- the mapping language over flat fields a project computes (R3-E2);
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

- The deciding reference is `gold/<D>`; every other one is `silver/<name>` with its own caveat (R3-E3), proposed
  to the owner in ADR-0020 because silver means "a model wrote it" today.
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
