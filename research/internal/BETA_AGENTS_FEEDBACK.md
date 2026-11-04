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

- **A crosstab of two per-item scores by a field of the output** (fleet, 2026-11-04). How many
  dismiss-gate downgrades saved a model false dismissal, and how many cost a right dismissal (12 saved,
  8 cost, by the fleet's own script). Fixed: `evh inspect --runs … --crosstab A,B --group FIELD`
  (`--group-match` to narrow it) gives the same 12 and 8. A name that is not a per-item score (a recorded
  field) is refused and pointed at `--group`.
- **Per-item output and reference together** (fleet). Fixed: `evh inspect --runs … --items-out` shows
  each item's whole output and scores beside the reference and labels (`--disagree`: only where runs differ).
- **`evh goals --goal` on a goal with 80+ arms** (fleet). Fixed: `--arms` (globs or substrings,
  comma-separated) and `--top N` choose the rows shown. The decision is still made over every arm, and
  the baseline, the leader and the recommended arm are always shown.
- **A hypothesis recorded before the run** (fleet). Fixed (ADR-0025): a `hypothesis:` block in the arm
  config, recorded in each run with whether it was committed before the run. `pair-test` and
  `evh goals --goal` show it. An arm with runs that predate the block reads "not named in advance", since
  those runs are averaged in.
- **`pair-test` across two versions of a dataset** (fleet, for v2). `--b-dataset` pairs one arm on two
  versions by item id, refuses a reference that differs, and names the runs of each side and where they
  were read. A measure stored only in re-scored runs is refused as a missing metric that names
  `evh rescore`, not as "no shared items".
- **Two runs started in the same second shared one directory** (found in the final review,
  2026-11-04). A run id is the config plus the start to the second, so the second run wrote over the
  first, a committed run included. Fixed: a run never writes into an existing run directory; it takes
  the next second's id, and an explicit `--run-id` that exists is refused.
- **Rebuilt answers that leak hindsight** (fleet, 2026-11-04). Some probe answers said
  `<UNAVAILABLE: GlitchTip issue X no longer exists …>`: 12 of 65 items, and 7 of the baseline's 18
  model false dismissals. Some `lastRelease`/`lastSeen` values were later than the decision or wrong.
  The fleet is building a v2 of the dataset from what it had at decision time; later rounds use it.

## Open (owner to decide)

1. **Lineage for a dataset version already cited** (fleet). v2 was made without `--from` (bug above)
   and runs cite it now, so it cannot be re-made to gain its `derived_from` link to v1. Its lineage
   lives in its description and commit. Wanted, if the owner wants the link: a command that adds
   lineage to a cited dataset without touching its items.
