# Agents as beta users: what they hit

**Status:** living, from 2026-11-04. The owner's fleet agent (improving signal-fleet) and personal
assistant use evh on their own systems and report friction. Each entry: what the agent needed,
what the harness has today (checked), and what was done or what is open.

## Fixed in this release

- **The ranking and the tests as data.** `leaderboard`, `pair-test`, `family-test`, `run-compare`,
  `rank-stability` and `runs-list` had no `--json`; `evh run` did not print the run ids it wrote.
  (Docs audit, 2026-11-04; the owner chose to add them now.)
- **One place for an agent's rules.** `evh init` writes `AGENTS.md` (and `CLAUDE.md` importing it):
  the rules, the loop from nothing, how to read results; the owner's rule on what an agent may do.
- **No catalog, no MCP needed with a shell.** Said in `AGENTS.md`, README and INTEGRATION.

- **A clean clone could not rebuild the triage data** (fleet, 2026-11-04; reproduced in a fresh clone).
  `examples/triage-fleet/fetch.py` refused capture `orrery_2026_10`: "233 record(s) differ from what it
  recorded", so no dataset items were restored. The importer had gained two fields (the prompt's
  version and hash, for the deploy sheet) after the capture, and a record's hash covers its fields.
  Fixed: the fields come only when a query asks (`prompt_fields`); a fresh clone restores 233 records
  and the 65 labelled items, hashes ok, and materializes. Why no check caught it before is not yet
  established.

- **`dataset-from-capture --from` kept the earlier version's bodies** (fleet, building the triage v2;
  reproduced in test_capture). A captured record whose id the earlier version had was skipped, so v2's
  corrected bodies never replaced v1's and the lineage read "0 changed". Fixed: the record replaces the
  item and is counted as changed.
- **`--fieldset` alone kept no item fields** (fleet). Fields were kept only with `--field`. Fixed: a
  field set keeps every field it declares; `--field` narrows it.
- **An importer path only worked from one directory** (fleet). Fixed: from the current directory, else
  from the project root, so the path a capture recorded works from either.

- **A round must exist before its arms run, and nothing said so in time** (fleet). It ran the v2
  baseline before opening r4. Fixed in the docs: AGENTS.md and the skill's step 4 say to open the round
  first, and that an arm already run joins through `round-open --keep` (whose help claimed "from earlier
  rounds" only; it accepts any config already run, and now says so).

## Open (owner to decide)

7. **Lineage for a dataset version already cited** (fleet). v2 was made without `--from` (bug above) and
   runs cite it now, so it cannot be re-made to gain its `derived_from` link to v1; its lineage lives in
   its description and commit. Wanted, if the owner wants the link: a command that adds lineage to a cited
   dataset without touching its items.

1. **A crosstab of two per-item scores by a field of the output** (fleet, 2026-11-04). The question:
   how many dismiss-gate downgrades saved a model false dismissal, and how many turned a right
   dismissal into a false alarm (baseline: 12 saved, 8 cost, by the fleet's own script). No command
   crosstabs `model_false_dismiss` against `false_dismiss` grouped by the gate that fired;
   `inspect --by` groups by an item's field, not an output's.
2. **Per-item output and reference together** (fleet). `predictions.jsonl` has no reason text or
   gold label; reading why an item flipped means joining `outputs/*.txt` and the reference by
   hand. `inspect --item` shows one item at a time.
4. **Rebuilt probe answers leak hindsight** (fleet, 2026-11-04; checked in this checkout). In
   `orrery_triage_v1_labelled`, 12 of 65 materialized items have a frozen probe answer
   `<UNAVAILABLE: GlitchTip issue X no longer exists …>`, which production never saw (the issue
   existed when it decided); 39 of 65 have some UNAVAILABLE answer. In the baseline run, 7 of its 18
   model false dismissals cite exactly that as the reason (ORRERY-DEV-7/8, STAGING-13/14/1H/1I/1V, all
   real problems in the gold); the dismiss gate turned all 7 into escalations, so the after-gate
   scores on them are unaffected, but `model_false_dismiss` is inflated and any arm that changes the
   gate or the dismiss rules is measured on them. Suggested: a neutral sentinel for a probe the
   rebuild could not answer (`<UNAVAILABLE: not captured>`), an item field flagging rebuilt hindsight
   so a goal or `inspect --by` can split them, and a check of other rebuilt answers that describe the
   present rather than the decision's time. A fix is a new dataset version (`_v2`), the owner's call.
5. **More rebuilt fields that are not as of the decision** (fleet, 2026-11-04; recounted here). In
   `orrery_triage_v1_labelled` (49 items carry `signal.raw.lastSeen`): `lastRelease.dateCreated` is
   later than the decision itself on 2 items, ORRERY-9 (release 2026-08-27, decided 08-22) and
   ORRERY-PROD-8 (release 09-16, decided 09-04): hindsight, as the issue was re-fetched after the
   decision. (The fleet counted 7 by comparing with `lastSeen`; the others are explained by the next
   point, not by a late release.) `lastSeen` is wrong on others: 10 items have it at day precision
   (`T00:00:00`), and ORRERY-L/M/O/P have 2023-11-14, before the project existed. Same remedy as
   item 4: a `_v2` built from what the fleet had at decision time.
6. **A hypothesis recorded before the run** (fleet). `pair-test` is valid only for a comparison
   named in advance, and nothing records the naming. Wanted: a `hypothesis:` in the arm config
   (which items should flip, and which way), committed before the run, so the claim can be checked.
3. **`evh goals --goal` on a goal with 80+ arms** (fleet). The table is about 300 columns wide and
   the baseline row falls far below; no filter or limit. Wanted: `--only`/`--top N`, the baseline
   row always shown.
