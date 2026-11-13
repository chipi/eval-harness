# RFC-030: Replay the code that ran, and prove the replay faithful before it is scored

- **Status**: Accepted and built (0.8.0, 2026-11-11); what the build changed is under **As built**. Revision 2 the
  same day: an independent review's eleven findings (Fable), each checked against the code and the fleet's reference,
  folded in; the owner's four answers (below), and "accept and build". Step R
  of `research/internal/PLAN_0.8.0.md` (owner, 2026-11-05: in scope, at the end of 0.8.0; 2026-11-11: "yes on rfc
  030"). Its reference implementation is the triage fleet's `examples/signal-fleet-filing/replay.py`,
  `faithfulness.py` and README (`/work/eval-harness-v072`, commit `9a318e61`, handed over 2026-11-05).
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-019](RFC-019-datasets-from-production.md) (captures; `arm-from-capture`: production's outputs as an
  arm), [RFC-023](RFC-023-labels-and-references.md) (`same(a, b)`: when two outputs are one decision),
  [RFC-028](RFC-028-prompt-versions-and-code-ref.md) (`code_ref`, which R1 takes down to each item),
  [RFC-029](RFC-029-studies-and-test-set-looks.md) (looks), the fleet's feedback 27 (a record for code under test)

## Abstract

Some systems under test are code with state and side effects: the fleet's filing reads GitHub and its own ledger,
writes issues, and runs a sweep. To measure a change to such code on production's own history, the harness replays the
**real code** (imported from a copy of the version that ran, never re-written) over the recorded items in time order,
each at the **version its production output came from** (R1). Before a replay is scored against gold, a
**faithfulness gate** (R2) replays the recorded versions and compares the replay, item by item, with **production's
own arm** (what production did, as a run), by the adapter's `same()`: a replay that does not reproduce production
measures the replay, not the system. The world a replay reads (a stand-in answering reads and recording writes),
joining production's writes to its decisions, and mutants are example code (R3 to R5): they are where systems differ.

## Why (what the reference run showed)

- A naive replay of the fleet's filing agreed with production on 86 of 92 decisions; all 6 misses were bugs in the
  replay or its data (reads made after the decision's own writes; keys computed by today's code instead of the code
  that ran; labels a freezer lost; a scrubber that changed what the system routes on; a create scored without its
  repo), none in the system. Scored against gold, those would have read as the system's errors.
- With each decision run on the version checked out when its cycle started: 324 of 324 rows agreed (253 decisions and
  34 sweeps on 21 code versions, 10-02 to 11-05; the fleet counts sweep nudges as rows, and a create agrees on its
  repo). Seven mutants applied in every version: six caught; one survived because no decision in the window exercised
  its rule, a coverage finding, not a replay fault.

## What exists today (read 2026-11-11)

- `run` calls `call_system(text, params)` per item in dataset order (`run.py:424`); the item's fields are not passed to
  the adapter (`run.py:443`, `460`); a call is retried on a transient-looking failure (`call_with_retries`,
  `run.py:458`); `--resume` replays outputs from disk without calling the system (`run.py:433-446`); `--items` runs a
  subset (`run.py:981`); `--repeat` runs passes in one process after one warm-up.
- `code:` (RFC-028) records one checkout's commit for a whole run (`deployment.code`, `_fingerprint.code_of`); a
  recorded run's adapter hash is one file (`_fingerprint.py:315`).
- Production's outputs can already be an arm: `arm-from-capture` makes a run from recorded outputs (`run.py:363`,
  `447-450`), and two runs are compared item by item with the adapter's `same(a, b)` (`_adapter.same_of`, used by the
  sheet and `--disagree`).
- An item field's types have a `date` (`YYYY-MM-DD`), no time of day (`_fields.py:30`).

## Design

### R1: the code version per item, and a replay run

- **The code record** is the model record of `kind: code` the fleet's feedback 27 already added
  (`data/models/<id>.yaml`): the system's `repo` and its `versions`, each a `commit`, when it was `deployed` in
  production (`[{from, to}]`) and the `faithfulness` a replay measured; the Models page and `evh models` show it. R1
  adds `checkout`, a local clone the harness reads versions from when `repo` is a URL, and requires the periods to be
  date-times with an offset that never overlap (V18).
- **The version an item came from**: a declared item field (`version_field`) when production recorded its own commit,
  else the version deployed at the item's time (`time_field`). An item no period covers is refused by name.
  Items gain a **`datetime` field type** (ISO 8601 with a time and an offset); a time the system derives (the fleet's
  cycle start, from a cycle id in the host's time zone) is written as a field by the project's freezer.
- **A replay config**:

  ```yaml
  config_id: filing_replay_v1
  dataset_id: fleet_decisions_v3
  model_record: signal_fleet                   # a kind: code record, named as any arm names its record
  replay:
    order: [ts, kind]                          # items run in this order (fields; later ones break ties)
    time_field: cycle_start                    # what picks the version deployed then
    version_field: deployed_commit             # optional: production's own record of its commit wins
    support: [replay_world.py]                 # the adapter's own modules, hashed with it
  adapter: replay_filing.py
  ```

- **A replay run** differs from a model run where state makes it: items in `order`; each call made once (no retries:
  a retried call would repeat side effects); `--resume`, `--items` and `--repeat` above 1 refused (state from skipped or
  replayed items would be missing, or a second pass would inherit the first's); the adapter gets
  `params["item"] = {"item_id", "fields"}` and `params["code"] = {"path", "commit", "changed"}`, `changed` true on the
  first item of a new version, where the adapter imports that version and re-applies its patches.
- **Each version as a copy**: `git archive <commit>` from the record's checkout, unpacked under
  `.build/code/<id>/<commit>/` (nothing written into the project's checkout: no `git worktree`), under a `code:<id>`
  lock so two jobs never unpack one commit at once; clean by construction, kept for the next run.
- **Importing a version**: `_codeload.use(path, modules)` imports named modules from a version's copy, dropping every
  module loaded from any other version's copy first (by path prefix, subpackages included). Module-level state does
  not survive a switch: what the system keeps across items (a ledger, a world) lives in files or in the adapter.
  Pure-Python systems only: a C extension cannot be unloaded, so a version with one is refused at the switch.
- **The fingerprint**, computed before the run from the dataset and the record: `deployment.code` lists every commit
  and how many items each runs, the record's id and the hash of its versions' commits and periods; `settings.replay`
  holds the fields
  above; the adapter's hash covers the adapter and its `support` files.
- **A candidate**: `replay: {..., commit: <the change>}` runs every item at that one commit, in the same replay
  mode: the arm a change is measured as.

### R2: the faithfulness gate

- **Production's arm**: what production did per item, as a run on the same dataset: a recorded arm
  (`arm-from-capture`, or a config with `provider: recorded`) reading each item's action from the capture, which the
  project's freezer writes (the fleet's actions are derived by joining GitHub writes to decisions by time window: R4).
  Writes production made that no item accounts for (the fleet's "stray" comments) are the freezer's to report: the
  example's join returns them.
- `evh faithfulness --system <replay> --dataset <id> --production <arm>` runs the replay at the **recorded** versions over
  **every** item of the dataset (no subset) and compares each with production's arm by the adapter's `same(a, b)`
  (RFC-023; text equality when it has none). It records `data/faithfulness/<id>/<n>.json`, written once: the
  items digest, the record's versions hash, every commit and its count, the adapter-and-support hash, the counts
  (agree, differ, replay errors, items production has no output for), each disagreement with both sides, the
  coverage (below), and the actor; and writes each version's summary into the code record's `faithfulness`.
- **Named exceptions**: `evh faithfulness-name --model ID --item ITEM --cause "..."` names a disagreement whose cause
  is outside the system (a record production lost); appended beside the record (`<n>.exceptions.jsonl`) with who named
  it and when, shown on every page that shows the result, never hidden. A person's decision: an agent is refused.
- **Coverage**: functions of the system's code (in the versions' copies) that the replay entered, traced with the
  standard library (`sys.settrace` and `threading.settrace`, `call` events only, so the cost is one callback per
  function call); per version, the functions defined (an AST inventory) and never entered are listed. A rule no item
  exercised is named, so a passing gate does not hide what it never tested.
- **The gate**: a replay config, or a candidate made from it, is scored against gold (`run` with a reference, a
  rescore, a promotion) only when the newest faithfulness record made with its adapter-and-support hash agrees on every
  item but those named, and was made with the same items digest and versions hash. A finished run is judged by what
  its own fingerprint names. Otherwise refused (`ERROR (not-allowed)`,
  with the counts), unless a person passes `--unfaithful` (an agent is refused, as with `--confirm-extra-look`): the
  run, its scores and every page that shows them then carry "unfaithful replay: N of M disagree", and the run records
  the faithfulness record it was scored against (decision 1).
- **What it does not prove**: the gate shows the replay mechanism reproduces production at the recorded versions. A
  candidate commit may call the world in a way the stand-in does not catch (a renamed function the adapter patches): the
  example's stand-in raises on any call it does not know, and replay runs set `EVH_REPLAY=1` so a system can refuse
  real calls; the harness cannot prove a candidate made none.

### R3 to R5: examples, not core

- **R3, the world a replay reads**: the fleet freezes each issue's timeline, and one shared stand-in answers reads as of
  each decision and records the replay's own writes, which later decisions then see (a replay's create at item 5 is
  read at item 9). Shipped as `examples/replay-filing/`, the fleet's stand-in generalised, with synthetic data.
- **R4, joining production's writes to decisions**: by each decision's write window and a measured clock slack, not by
  a key a write may not carry; the fleet's `write_windows` and `observed_action`, writing production's arm for R2.
- **R5, mutants**: a named change applied to every version's copy, the gate expected to fail; a survivor is reported
  with the coverage that explains it.

## Commands (each with `--json`; RFC-026 serves them)

| command | what | served |
| --- | --- | --- |
| `evh faithfulness --system S --dataset D --production ARM [--dry-run]` | replay at the recorded versions, compare, record | job, spends |
| `evh faithfulness-name --model ID --item ITEM --cause "..."` | name a disagreement's outside cause | job, a decision |
| `evh faithfulness-show --model ID [--n N]` | a recorded result | read |
| `evh models --model ID` | the code record: its versions, when each ran, its latest faithfulness | read |

## As built (2026-11-11)

- **The code record is the `kind: code` model record**, not a record of its own. The first build added
  `data/code/<id>.yaml` beside it: a second record of the same thing, made because the draft (mine) never looked for
  the fleet's feedback 27, which was already built. Rebuilt on the model record the same day: a replay names it with
  `model_record:`, a candidate with `replay.commit`; `evh faithfulness` writes each version's summary into it, so
  the Models page and `evh models` are its view; the code command and the Code page of the first build are gone.
- **Commands**: one command is either a read or a job for the API (RFC-026), so naming and showing are commands of
  their own: `faithfulness` (a job that spends), `faithfulness-name` (a decision) and `faithfulness-show` (a read, also
  an MCP tool).
- **Records by code record**, `data/faithfulness/<id>/<n>.json`: a candidate is a config of its own, and its gate is
  the record of the replay it was made from, found by the code record, the dataset and the adapter's hash.
- **The newest record made with this adapter**, not the newest of the code record: a second adapter (a stand-in being
  fixed) never stands in for the first. Found by the test: the buggy stand-in's record shadowed the good one's.
- **What the gate does not cover**: the config's `params` (a system's own setting a candidate may vary: putting them
  in the gate would refuse every such candidate) and data the adapter reads that is not a `support` file (a frozen
  world under the project). Said in the RUNBOOK and the example; changing them asks for a new `evh faithfulness`.
- **Copies**: `git archive` members with an absolute path, `..`, or a link are not unpacked, and Python's tar data
  filter is used where it exists.
- **Production's arm** is a recorded arm from a capture: `import-run` takes scores, not outputs.
- **Also built**: `datetime` item fields; `validate` V26 (faithfulness records and their exceptions) and V18 (a code
  record's periods); a replay's line on its arm page, linked to its code record's page (a badge when it was scored
  unfaithful); the example
  `examples/replay-filing/` (R3 to R5) and `tests/test_replay.py`, which runs it end to end.
- **A bug the example found** (fixed in 0.8.0): items with the same text took each other's labels, since labels
  followed an item by its text's hash; 13 of the example's 20 decisions share their text.
- **Not built**: a recorded field per item as production's output (R2 reads production's arm instead, as revision 2
  decided); coverage below the function (lines, branches).

## Migration

None: no committed config replays code. The fleet moves its two files onto this when 0.8.0 is released.

## Alternatives considered

- **Re-implement the system's logic in the harness**: what a replay must never do.
- **Every item at the newest commit**: the reference run's first misses were exactly this.
- **`git worktree add`**: writes into the project's checkout (`.git/worktrees/`) and races; `git archive` into
  `.build/` writes nothing outside the harness's folder.
- **A recorded field on each item for R2**: the fleet has none; what production did is derived by a join, and an arm
  is what the harness already compares item by item.
- **coverage.py**: a new dependency; call-level tracing answers "which functions never ran".
- **The stand-in world in the core**: every system reads a different world.

## Testing

- `tests/test_replay.py` ($0, offline): the example's system in a git repository with three commits, a code record
  with three periods, items with `datetime` fields; each item runs at its period's commit (each commit unpacked once,
  reused), `changed` on the first item of each; the ledger file kept across items and switches; a replay run refuses
  `--resume`, `--items` and `--repeat 2`, and calls a failing item once; faithfulness agrees on all 20 and names the
  rule no item reached; a stand-in that reads after its own writes disagrees; scoring it is refused, allowed with a
  person's `--unfaithful` (labelled on the run, its re-score and its arm page) and refused for an agent; naming each
  disagreement lets it through; editing a support module or a version's period after the record closes the gate;
  V26; the code record's versions carry the latest summary.
- The example's mutants: each killed but the one no item exercises, which coverage names.

## Decisions (owner, 2026-11-11)

1. **An unfaithful replay scored against gold**: allowed when a person passes `--unfaithful`, labelled everywhere; an
   agent is refused.
2. **The code record** (the fleet's feedback 27): in this RFC. Asked on a wrong premise: I put it as a new record
   (`data/code/`), when feedback 27 had already built one (`kind: code`). Built on that one (As built, above).
3. **Coverage**: in every faithfulness run.
4. **R3 to R5**: one example in this repository, `examples/replay-filing/`, with synthetic data.
