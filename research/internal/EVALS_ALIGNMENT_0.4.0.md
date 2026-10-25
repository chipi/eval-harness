# Aligning this repository's evals with 0.4.0

Decided 2026-10-25. The owner's rule: everything moves to the latest format, with no old
formats, hacks or debt, and when in doubt, ask. The owner takes these recommendations for
0.4.0 and reviews them in depth for 0.5.0. The assessment behind them, with costs and
evidence, is in the claude.ai artifact "Evals Alignment Plan".

## Why

The catalog of these evals should show what the harness does, and every conclusion
(reports, site) should match what the catalog says. On 2026-10-25 only Few-NERD's catalog
answer matched its report:

- SummEval and SciFact recommended side runs (`runs-pair`).
- AG News, DBpedia and the CNN heldout set gave no answer: each leader was tied with its own
  `runs-linux` copy.
- No goal had a baseline, round, strategy, judge group or visible gold.
- 136 runs were in fingerprint v1/v2.

## Decisions

| | Decision | Cost |
|---|---|---|
| A | Side runs: `runs-repeats` become their arm's repeats; `runs-pair` become their own arms (own config ids) in a closed "provider pairing" round, retired with the report's conclusion; `runs-linux` become a closed "speed on one machine" round whose arms are retired **by arm id** (rounds learn to retire one arm, not only a config: ADR-0004 updated). | $0 |
| B | Migrate the 136 v1/v2 runs to v4. Fetch the gold, recompute fingerprints, derive what can be derived. Few-NERD and SciFact stay derived (rescore/reparse): their measured sources are not in the repo. No re-runs. | $0 |
| C | Gold stays uncommitted (docs/DATA.md). Each gold reference gets a committed `manifest.json` (id, tier, item count, per-item checksums, written by fetch.py), as silver has; the catalog lists it as fetched, not redistributed. | $0 |
| D | Each report's history becomes rounds. Every config names its goal (`goal:`). Each report's pick is promoted as the baseline, with the report's reason. | $0 |
| E | Each goal encodes its report's rule: strategy, limits, `min_items`, dataset roles that decide, guardrails. Drafted per goal; shown in the next review. | $0 |
| F | Dev slices are recorded as versions of their heldout sets (lineage). No dev runs are derived: the harness has no subset command, and such runs would repeat the same outputs on fewer items. The goal decides on heldout. | $0 |
| G | No new repeat runs. | $0 |
| H | Silver from a run plus silver-calibrate on CNN; the judge panel on SummEval; both from stored outputs. Item fields stay unused (ADR-0003). | $0 |
| I | The site reads every conclusion from the catalog (goal decisions, baselines, reasons), not from `examples/experiments.json`. It describes 0.4.0 and links each experiment to its goal page; a link check joins `--check`. DNS for docs./catalog. is a cutover step. | $0 |
| — | MBPP+ is not part of this alignment: its runs are not in this tree (they wait on the DGX). It joins when they exist. | — |
| — | Other $0 fixes: `cost_usd` from the stored bill where a reply carried one; judged runs rebuilt from the 2,800 stored verdicts (`judge-score --no-calls`) and committed; AG's adjudicated gold as a reference; `METRIC_DESCRIPTIONS` in the six adapters. | $0 |

## Order

1. Data and goals (A–H and the other fixes), each migration verified: scores and report
   claims unchanged unless the migration is the point.
2. Rebuild the catalog; every goal's decision checked against its report.
3. Reports: their numbers and conclusions against the catalog.
4. The site (I).
5. A review document with screenshots, as for the newcomer runs.

## Checked 2026-10-25

- `judge-score --no-calls` rebuilds the judged runs from stored verdicts: CNN judge-summ-v1 gave
  29 runs, 197/200 items, 0 calls, $0. It still prints MISSING-key lines it does not need: fix.
- The datasets and gold were copied from the `harness-0.4.0` worktree (git-ignored);
  `evh validate` V4 found 13 of 14 materialized and matching their frozen hashes.
- Gold licences and policy: docs/DATA.md (never committed; AG News is `unknown`, non-commercial).
