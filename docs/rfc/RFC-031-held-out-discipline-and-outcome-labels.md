# RFC-031: Held-out discipline, labels that mature from outside systems, and decisions scored by what followed

- **Status**: Accepted (owner, 2026-11-12: "accept and build"; decisions below). The triage fleet's seven new gaps, approved by the owner on 2026-11-12
  ("I did approve them … implement all of them"), sent by the homelab session from fleet-eval-data's
  `BOUNDARY-PROPOSAL.md`; each one's reason is the fleet session's own answer (2026-11-12) and its hand-built tool in
  fleet-eval-data, read the same day.
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-019](RFC-019-datasets-from-production.md) (captures, importers),
  [RFC-023](RFC-023-labels-and-references.md) (label sets, outcome rules), [RFC-029](RFC-029-studies-and-test-set-looks.md)
  (sealed splits, looks), [RFC-030](RFC-030-replay-and-faithfulness.md) (replay per item, faithfulness), the fleet's
  feedback log (homelab `docs/wip/eval-harness-feedback-fleet.md`, entries 23-33).

## Abstract

The owner decided (2026-11-12) that evaluation in any form lives in Eval Harness: flotilla produces records,
fleet-eval-data keeps one project's data, rules and adapters, the harness keeps the machinery. The fleet has been
doing seven parts of its evaluation by hand. They are three pieces of machinery:

| | Gaps | What the harness gains |
|---|---|---|
| **H. A sealed side kept sealed** | 1 exposure register, 2 counts-only reports | a per-item read register that every score on a sealed side honours; a leak check over public repos; a counts-only report whose groupings are fixed when the side is sealed |
| **L. Labels from what happened later** | 3 labels that mature, 4 labels from outside systems, 7 per-decision outcome scoring | an outcome joined from another capture by key and time window; two dates per label; a relabel that only adds what matured and counts what changed; labels that hold only under production's own action |
| **P. Replays of the past** | 5 production's writes hidden, 6 a baseline from a past period | the replay told which of production's own writes to hide, a "history confound" count on every score; a period slice: production, the code as it ran, the candidate |

Nothing fleet-specific enters `harness/`: id patterns, repos, rules, windows, join keys and fetchers stay in
fleet-eval-data, as config or hooks.

## Why (the fleet's own account, 2026-11-12)

1. **Exposure register.** On 2026-11-11 another session's live/shadow comparison read the disposition and reason of
   75 test-side captures and paraphrased ten in a public repo; the fleet session's own bug fix of 11-08 had put two
   test-side labels into public test fixtures. **78 of 91 sealed items were exposed before anyone noticed.** A seal
   that refuses runs (RFC-029) did not stop any of it: they were reads, not runs. Built by hand:
   `projects/triage-heldout/exposed.tsv` (80 rows), `SPLIT.md` rules 6-8, `exposure_check.py` (searches every commit
   of the public repos for sealed ids named after their decision; it missed ids written as "-F, -J" lists).
2. **Counts-only reports.** The live watch the plan wanted reads the test side. Built instead: `safety_watch.py`, per
   UTC day the live decisions by disposition and gate, issues filed and their state, GlitchTip issues never decided
   ("drops"); its first run found 10 dropped errors. The operator's ruling (SPLIT rule 5): counts for safety, never to
   judge the effect. Small counts matter (one dropped error is news), so the protection is which fields may be
   grouped by, chosen when the side is sealed, not a minimum count. The signal class was left out on purpose: it is
   what tuning would read.
3. **Labels that mature.** "Not seen again within 14 days" is knowable only 14 days after the decision. Of 98 tuning
   items: 3 labelled, 31 skipped, 44 waiting for an issue verdict, 17 not mature, 3 for the operator. Every relabel is
   a note ("rerun about 11-20") and a hand rerun (`outcome_count.py`, `build_items.py`'s `matures`,
   `label_nudges.py`). An outcome that changes after maturing (a reopen, a recurrence after "not seen again") is lost
   or silently overwritten.
4. **Labels from outside systems.** GitHub close reasons and GlitchTip counts are read live at label time and never
   frozen: a rerun can give other labels, and nothing records what was read. The outcome of a decision lives on
   another object (the issue it filed, created within -1 to +15 minutes; later errors of the fingerprint), so the
   capture's own record does not hold it.
5. **Production's own writes hidden.** Varying the stale check's quiet days, 10 and 14 days nudged nothing: the
   frozen GitHub carried production's own `stale-candidate` labels and the sweep skips labelled issues. Hiding them
   fixed it; hiding labels from before the window re-nudged 5 old issues; hiding only labels written inside the
   replayed window reproduced production exactly (324/324). What hiding cannot fix: a later variant meets the
   operator's reactions to nudges it never sent.
6. **A baseline from a past period.** The code changed 10 times in 19 days (feedback 24); the rollup's "buried more
   than it promoted" reading was wrong because all 6 misses came before a fix. A fair comparison is the period's own
   items at the code that ran then, beside the candidate on the same items.
7. **Per-decision outcome scoring.** The item is a decision and its label arrives later (3 + 4). Two more things:
   the world reacted to production's action, so a variant that acts differently has no observed outcome of its own
   (the operator closed the issue production filed); and one fingerprint is decided many times (194 decided more than
   once).

## What exists in 0.8.0 (read 2026-11-12)

- `dataset-split --seal`, `dataset-unseal`, `_seal.refuse_if_sealed` (run, score, label refused on a sealed side),
  `_looks` (looks counted per test set). Nothing is recorded per item; nothing about reads.
- `label-from-capture` (rules over the same capture's record of the item), `label-coverage` (labelled now, skipped,
  not yet mature with its date, unmatched, not in the capture), `_outcome_rules` (`min_age_days` against the
  capture's time). A label set is one pass, never edited; a newer outcome is a new capture and a new set.
- Captures and importers (`github` with state, state_reason, close events; `jsonl`, `tsv`, `langfuse`); a project's
  own importer by path. No join between captures.
- Replay per item at the deployed version, the faithfulness gate, `replay.commit` for a candidate (RFC-030);
  production's writes joined to decisions (R4) and the shared world stand-in (R3) as an example.
- A goal's `cluster: FIELD` and `pair-test --cluster`: related items count as one in every paired test. This already
  answers gap 7's "decisions are not independent".

## Design

### H1: the exposure register (gap 1)

- **The register**: `data/exposure/<dataset_id>.jsonl`, append-only, a row per read: `item_id`, `by` (the actor, as
  RFC-027 records it), `what` (free text: "decision and reason", "label in a test fixture"), `at` (when it was read),
  `recorded_at`, `recorded_by`. The dataset is the sealed side (or one sealed and later unsealed).
- **Recorded by hand**: `evh exposure-add --dataset-id D --item ID --what TEXT [--at T]` (repeatable `--item`), or
  `--from FILE.tsv` (the fleet's `exposed.tsv` imports as is). A person or an agent may record; nobody may remove.
- **Recorded by the harness**: a command that shows a person or an agent a sealed item's content, or an output or
  label on it, records the read itself: `inspect --item`, `inspect --sheet`, `--items-out`, `label-sheet`, the catalog
  and inspector's per-item views (served pages record the reader as "catalog-serve" with the client), a run or import
  for the items it prints. A command that prints counts only records nothing.
- **Every score on that dataset leaves exposed items out**, not only the confirmation (the fleet: "once read, always
  read"): `pair-test`, `family-test`, `leaderboard`, `goals`, `study-confirm`, the catalog and the inspector print
  "N left out (exposed)" beside the number. `--include-exposed` shows the full number beside it, marked; it never
  replaces it.
- **The leak check**: `evh exposure-check --dataset-id D` scans the repos named in `config.yaml`
  (`exposure: {public_repos: [...], ids: [item fields holding natural ids]}`) with `git log --all -G` over patches
  and messages, for each sealed item's `item_id` and natural ids, counting a hit only in a commit after the item's
  time. A hit not in the register exits 6 and prints the register rows to add. It says what it cannot catch:
  paraphrases, titles, ranges and ids written without their prefix. A project hook (`exposure.ids_hook`) may add
  forms, such as the fleet's "PREFIX-X, -Y" lists.
- **Index, not name**: a command that lists sealed items for a person prints an index ("sealed item 37 of 91"); the
  ids are printed only by `evh exposure --dataset-id D --ids`, which records nothing and is refused to an agent.

### H2: counts-only reports (gap 2)

- **The allow-list is fixed when the side is sealed**: `dataset-split --seal --count-by FIELD,...` writes
  `sealed.count_by`. A person may extend it later with `evh dataset-seal-counts --dataset-id D --add FIELD --reason
  "…"` (recorded, with who); an agent may not.
- **`evh sealed-counts --dataset-id D [--by FIELD,...] [--per day]`**: counts per UTC day (the split's time key) and
  per allowed field, over the sealed items and, with `--capture C`, over a capture's records on the sealed side of
  the boundary (the live watch: records that arrived after the split). It refuses any field not on the list, any id
  or text field, and prints "for safety only, never to judge effect". It records no read.
- **Derived counts by hook**: `exposure.counts_hook: file.py:fn` returns extra `(day, name, n)` rows (the fleet's
  drops: GitHub issue state, GlitchTip issues never decided); the hook sees records, the report prints only counts.

### L1: an outcome from another capture (gap 4)

- `label-from-capture` and `label-coverage` gain `--outcomes CAPTURE --join ITEM_FIELD=RECORD_FIELD [--within
  -1m,+15m]`: each item's outcome fields come from the other capture's records that match the key and fall in the time
  window after the item's time (the fleet's issue created within -1 to +15 minutes of the decision), named
  `<capture>.<field>` beside the item's own. More than one match: the rules see `count` and the first by time, and the
  label set records how many items had more than one.
- **Frozen, with provenance**: the outside system is read once, as a capture (an importer, the project's own for
  GlitchTip: core stays generic), so what was read is kept, hashed and dated (`captured_at`); the set records each
  outcome capture's id and sha256. A token never enters a capture. A new read is a new capture, and the relabel below.

### L2: labels that mature (gap 3)

- **Two dates per label**, written in the set per item: `happened_at` (a rule's `date: FIELD`, e.g. the issue's
  `closed_at`) and `knowable_at` (the item's time plus the rule's `min_age_days`, or `happened_at` when the rule has no
  window). A set records its `as_of`: the outcome capture's time. A score on it names it.
- **A relabel adds what matured**: `label-from-capture … --set S2 --from-set S1` writes a new set (sets stay never
  edited) holding S1's labels unchanged, the labels matured since, and, for any item whose label differs from S1's
  (a reopen, a recurrence), the new label with `changed_after_maturing: {from, at}`. It refuses an S1 label that
  vanished without a reason. Every report on S2 (`labels`, `label-coverage`, the catalog) counts "changed after
  maturing", and `label-coverage --from-set S1` says what a relabel would add today.

### L3: decisions scored by what followed (gap 7)

- **Action-dependent labels**: a rule may say `under: action` (the outcome was observed only under production's
  action: an issue's close reason exists only because production filed). The set then records, per item, production's
  recorded action (the capture's output, as `arm-from-capture` reads it).
- **Scoring a variant**: on an item whose label is action-dependent, a variant whose output is not `same()`
  (RFC-023) as production's recorded action has no observed outcome: it is left out, and every score says "N not
  scorable under this variant". An action-independent label (the error recurred whatever was done) scores every
  variant.
- **Not independent**: a goal's `cluster: FIELD` (the fingerprint) already counts related decisions once; L3 says so
  in the docs and the fleet's goal sets it.

### P1: replays with production's own writes hidden (gap 5)

- **The config names what to hide**: `replay.hide: {kinds: [...], window: replayed}`; the harness passes it to the
  adapter as `params["hide"]`, with the window's start (the first replayed item's time). The adapter's stand-in hides
  production's writes of those kinds made inside the window (the fleet's label; the operator's comments stay, they are
  history). The hide setting is part of the replay plan, so the faithfulness record must be one made with it.
- **Required before a variant counts**: the default variant with hiding on reproduces production (RFC-030's gate, on
  the same plan). A variant with a `hide` and no faithfulness record made with it is refused, as an unfaithful replay is.
- **The history confound**: the adapter reports per item whether the variant met a human reaction recorded after a
  production action it did not take (`Result.extra["history_confound"] = 1`). The run carries the count, every score
  on it prints "history confound: N of M items", the catalog marks it, and the item ids go to the run's
  `confound.jsonl`, except for sealed items (a count only).

### P2: a baseline from a past period (gap 6)

- **`evh period-compare --config REPLAY --candidate CONFIG --from T --to T`**: on the items whose replay time falls in
  the period, three columns per measure: what production recorded (`arm-from-capture`), the code that ran then
  (the replay run, which must agree with production on those items or the report says it does not count), and the
  candidate on the same items; the paired test between the last two, on the period's items only.
- **Periods from the code record**: `evh periods --model RECORD` lists the record's deployed periods (RFC-030's
  `kind: code` versions) with each period's item count and faithfulness; `--period N` takes one by number. A result
  can be split at a deploy boundary.

### X1 to X3: three needs from the fleet's notes (confirmed by the fleet session, 2026-11-12)

- **X1, the labeller mutation-tested.** Three of the fleet's labeller mistakes were caught only by reading results,
  none by a test. `evh label-mutants --dataset-id D --capture C --map RULES [--outcomes …] --mutants FILE.py` applies
  named mutants to the rules or the join (a project's mutants file, as RFC-030's R5 for a replay), labels again with
  each, and reports per mutant how many labels moved. A mutant that moves none is a finding: the labelled set does not
  reach that rule. The fleet's five: the recurrence definition (every ledger row instead of real recurrences: 12,635
  against 1,351 to 11-05), a close reason mapped to the wrong label ("closed as duplicate" as noise: 2 items), the
  input rebuilt from the wrong field (the event's culprit instead of the issue's: 55 of 76 items failed faithfulness),
  the window shifted (14 days to 7 and 21), the join taken from another source (the ledger instead of the freeze's
  issue timelines). The harness ships the generic ones (a window shifted, rules swapped, a `when` value changed, the
  join's window moved); the project adds its own.
- **X2, a label counts only where production's decision is reproduced.** A label is valid where the recorded decision
  is reproduced by the rule version deployed at that decision, on the input rebuilt for that time (the replay of
  RFC-030, at the item's version). Per item: reproduced, reproduced at an approximate version, or not reproduced;
  labels on items not reproduced are left out and counted. The version's dating is kept apart: a version dated by
  commit time (the host's reflog reaches back 90 days: 62 of the fleet's 74) is "approximate", not mixed with one dated
  by the actual pull (12); the code record's period carries `dated_by: pull | commit`. The rollup: 74 of 76
  reproduced, 2 "path unexplained".
- **X3, items gone from the source, or their id reused.** A joined outside record (L1) that is gone, or whose id now
  names another object (a GlitchTip short id reused after a project is deleted: the fleet's bug of 10-17), is its own
  class in `label-coverage` and the label set: "gone from the source, or its id reused", with when it was last seen;
  never "no outcome", never a negative label. The join checks identity, not only the id: a record whose first-seen
  differs from the item's recorded one is gone (`--outcomes … --identity FIELD`). The fleet: 17 of 93 rollup items,
  498 re-triage fingerprints.

## Commands (each with `--json`; RFC-026 serves them)

| command | what | served |
|---|---|---|
| `exposure-add` | record a read (or a TSV) | job (a person or an agent, recorded) |
| `exposure` | a sealed set's reads: counts by reader and what; `--ids` for a person only | read |
| `exposure-check` | the leak check over the configured public repos | job (it reads repos) |
| `sealed-counts` | counts only, by the allowed fields | read |
| `dataset-seal-counts` | extend the allow-list | a person's command |
| `periods` | a code record's periods | read |
| `period-compare` | production, as it ran, the candidate, on a period | job |
| `label-from-capture --outcomes … --from-set …`, `label-coverage --outcomes … --from-set …` | (above) | as now |

## The Workbench

Each of these is a view the Workbench mockups gain after the build (the owner's order): the exposure register and
"N left out (exposed)" on a held-out set, the counts-only watch, a label set's maturing and "changed after maturing",
"not scorable under this variant" and "history confound" beside a score, the period comparison.

## Alternatives considered

- **Exposure as a look (RFC-029)**: a look is a decision to spend the test set; a read is an accident. Counting reads
  as looks would spend the budget on leaks and still not remove the read items from the score.
- **A minimum count for the counts-only report**: the fleet needs counts of one (one dropped error). The allow-list
  of fields protects what matters (the signal class tuning would read).
- **Editing a label set in place on relabel**: label sets are never edited (ADR-0022); a new set with `--from-set`
  keeps every earlier score reproducible by naming its set.
- **Calling GitHub and GlitchTip from the harness**: the token and endpoints are the project's; a capture through an
  importer freezes what was read without the harness holding a credential.
- **Hiding writes in the harness**: what a write is, and which are the system's, is the system's own vocabulary; the
  harness carries the setting and enforces the faithfulness gate on it.

## Testing

Each part with a test that fails before it: H1 a read recorded by `inspect --item` on a sealed set, a score printing
"N left out (exposed)", the leak check finding an id in a synthetic repo's later commit and missing it in an earlier
one; H2 a refused field, counts per day with a capture; L1 a join in and out of the window; L2 a relabel that adds
only matured items, keeps the old ones and counts a changed one; L3 a variant scored only where its action matches;
P1 a hidden write, the gate refusing a variant without a matching faithfulness record, the confound count; P2 the
three columns on a period, refused when the as-run replay disagrees. The `examples/replay-filing/` world gains a
hidden-write case and a period. Both stores.

## Migration

None: every record gains optional fields; nothing existing changes.

## Decisions (owner, 2026-11-12)

1. **A person or an agent records a read**; every row names who recorded it, and nobody removes one.
2. **`--include-exposed` is offered**: the full number beside the clean one, marked; the clean one is the one that
   counts.
3. **The three needs in the fleet's notes are in this RFC**, each confirmed with the fleet session before it is built:
   mutation-testing a labeller (as RFC-030's mutants do for a replay), a faithfulness check on labelled items (the
   rule as deployed then labelled them), and items gone from the source.
4. **Accepted and built**, in the order H1, H2, L1, L2, L3, P1, P2, then the three; then the Workbench mockups.

Context (owner, 2026-11-12): Flotilla, the owner's new platform managing the fleets, is the next version of the
triage fleet and the source of this segment's use cases: evaluating the whole feedback loop, bringing signals back
from production and integrating with other systems.
