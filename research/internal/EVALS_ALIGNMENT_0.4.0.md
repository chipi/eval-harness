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
- B done: the 136 v1/v2 runs are fingerprint v4 (code digests mapped through git history,
  none unresolved). The reference digest is today's gold: 131 of the 136 re-scored item by item
  from their stored outputs exactly as recorded, on every dataset. The other 5 (SciFact
  `qwen_s` and four side runs) are reparsed runs: their recorded scores come from re-parsing
  the raw replies with the fixed parser (KNOWN_ISSUES, round 2), which a re-score of the
  original output text cannot reproduce. They keep their recorded scores. A first pass replaced
  them with the re-score and was reverted: that would have undone the parser fix.
- The reference digest counts only a manifest's authorship fields (who wrote the texts); a gold
  manifest adds nothing, so the 57 v4 gold-scored runs still match. The demo silver run moved
  with its manifest.
- cost_usd is the bill where a reply carried one: 79 runs (17,473 items) moved from the price
  table to `_meta.usage.cost`; their total $4.70 -> $7.06. Nothing else in those files changed
  (semantic diff); reports already quoted bills (claims 200/200), the site's pages did not move.
- Judged runs committed: CNN judge-summ-v1 (29 runs, 197/200 items), v2 (29, 200/200) and the
  unvalidated pointwise scorer (2), projected from the stored verdicts by `judge-score
  --no-calls` ($0; their judging cost was $13.33). Their output copies are blobs already in git.
- Goals aligned (A, D, E): every run names its goal; each experiment's record is round r1 and
  each side tree a closed round whose arms are retired by runs directory (13 rounds); every
  config names its goal (343), but no round, so `make reproduce` still runs; each goal encodes
  its report's rule (DBpedia, SciFact, SummEval `frugal`; SciFact `tie_break: [cost, quality]`),
  dev and generalization datasets `decides: false`, guardrails from the reports; each report's
  pick is the promoted baseline with the report's reason. The catalog now recommends the
  report's pick for five goals. AG News reads "still tied" among its three BERTs: the report's
  pick, `bert_mini`, rests on speed measured on one machine (round r2), and the record's BERTs
  ran on two, so speed is not compared there.
- Harness changes found on the way: `decides: false` on a goal dataset; quality may be a
  tie-break axis; the glance's leader is the decision's (never a retired or flagged arm).
- F settled differently from the plan (owner, 2026-10-25): a dev slice is no version of its
  heldout set (the dates disagree: CNN's dev was made first, Few-NERD's after, three in the same
  second), so no lineage; `decides: false` and a note that every item is in the heldout set.
- AG News's adjudicated gold is a reference (gold/ag_news_200_adj1, built by
  examples/_shared/adjudicate.py from the committed adjudication; manifest committed, labels not)
  and data/runs-adjudicated holds the 30 runs re-scored against it ($0): anthropic_l 0.9850, the
  three fine-tunes 0.9050, as the report says. The goal page shows it as a second gold group.
- METRIC_DESCRIPTIONS for all 59 undescribed metrics, read from the scoring code; the catalog
  reads the adapter's current descriptions over the recorded ones, and no code hash moved. Found
  on the way: `is_neutral` was global (SummEval's descriptive `parsed` hid the others' quality
  `parsed`), now per dataset; V9 passed when `git ls-files` failed, now it fails.
- H, silver: silver-calibrate re-measured at n=200 from the stored outputs ($0): the 24 hosted
  authors agree with gold at mean ρ 0.163 (best `llama_l` 0.378), every one promotes its own
  family (+10.4 positions); `lead3` and the BARTs make better silver (0.58–0.72). No retest
  ceiling at n=200 (one run per arm): silver-calibrate used to print 1.000 there, now it says
  "not measured". The frontier arm's silver (`anthropic_l`) is `silver/cnn_dailymail_200`, manifest
  only (its texts quote the articles), rebuilt by the command its manifest records
  (`reference-create --from-run … --not-redistributed`, new). Report §3.5 and the CNN README
  carry the n=200 numbers.
- H, judge panel: dropped (owner, 2026-10-25). `evh judge` calls hosted or fake judges, has no
  stored-verdict mode, and its verdicts never reach the catalog; SummEval already measures
  judges against experts in fingerprinted runs.
