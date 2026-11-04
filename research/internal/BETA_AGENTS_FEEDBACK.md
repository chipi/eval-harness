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

## Open (owner to decide)

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
3. **`evh goals --goal` on a goal with 80+ arms** (fleet). The table is about 300 columns wide and
   the baseline row falls far below; no filter or limit. Wanted: `--only`/`--top N`, the baseline
   row always shown.
