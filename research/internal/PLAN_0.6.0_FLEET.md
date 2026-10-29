# Plan: applying 0.6.0 to the triage fleet — the application plan

Status: draft for discussion, 2026-10-29. It applies the lane built in
[PLAN_0.6.0.md](PLAN_0.6.0.md) (the engineering plan) to the homelab's triage fleet (signal-fleet, Fleet 2) on
Orrery. **Two things are measured:**
1. **the triage decisions**: the model step, billed;
2. **the de-duplication**: the deterministic filing step, $0.

Every number below was measured on 2026-10-29. Sources: the fleet's ledgers and stores, read by homelab;
Langfuse's database (ClickHouse) on the mini; OpenRouter's public price list; the gateway's model list
(`infra/litellm/config.yaml`). Section 6 lists what is still to be decided.

## 1. The data we have

### 1.1 The decisions (dataset `orrery_triage_v1`)

- **236 Orrery triage decisions**, 2026-07-25 → 2026-10-29: one per occurrence; recurrence rows are left out.
  - By month: Jul 47, Aug 71, Sep 63, Oct 55.
  - The fleet decided: dismiss 122, escalate 52, file 50, cleanup 12.
  - All on one prompt (`mvp-1`, sha `c2ece738`). Models: `fleet-triage-pro` 228, `deepseek-v4-flash` 8.
- Each item holds the signal and a **probe table** (every probe the model can ask for, answered as of the
  decision's time), plus the fleet's decision, the outcome, and provenance.
- Built by homelab from every store, as of each decision's time, and scrubbed by the fleet's `scrub.py`. 0
  secrets: gitleaks reports "no leaks found". sha256 `cacaf75f…`, 1.39 MB.

| evidence level | items | period | what the probe table is |
|---|---|---|---|
| exact | 33 | since 10-15 | the model's own probe answers, verbatim from Langfuse, plus the rest of the menu rebuilt |
| full-rebuild | 6 | 10-08 → 10-15 | every store covers the decision |
| no-traces | 17 | 09-30 → 10-07 | logs and metrics; no traces |
| no-logs | 89 | 08-14 → 09-29 | metrics; no logs (VictoriaLogs keeps 30 days) |
| ledger-only | 91 | 07-25 → 08-13 | the signal only. For 102 items in all, the GlitchTip issue no longer exists (projects recreated) |

- Probe entries in all: 59 verbatim, 508 rebuilt, 743 unavailable, 236 static.

### 1.2 What a decision costs and takes today

Measured from Langfuse, on the 140 production decisions since 2026-10-15, all on `deepseek-v4-pro`:

| measure | mean | p95 |
|---|---|---|
| model turns per decision | 3.04 | 4 (max) |
| input tokens per decision | 4,524 (2,018 uncached + 2,506 cache read) | — |
| output tokens per decision | 2,020 | 3,745 |
| cost per decision (billed) | $0.0070 | $0.0143 |
| latency per decision | 34.3 s | 62.5 s |

### 1.3 The references

**Hand labels.** 9 items carry a label carried over from the fleet's frozen fixtures, matched by fingerprint:
- 5 cleanup and 4 dismiss;
- no `file`, so they cannot measure a false dismissal.

**Outcome labels**, from what happened afterwards: counted on the real data with the mapping in §3.2.

| the fleet decided | outcome says `file` | outcome says `dismiss` | no label | total |
|---|---|---|---|---|
| dismiss | **21** | 85 | 16 | 122 |
| escalate | 33 | 12 | 7 | 52 |
| file | 30 | 0 | 20 | 50 |
| cleanup | 3 | 3 | 6 | 12 |
| **all** | **87** | **100** | **49** | 236 |

- **The 21 in bold are production's own false dismissals** by this measure: the fleet dismissed a signal whose
  fingerprint was filed later. They are the most informative items: does a new arm catch what production
  missed?
- Why items have no label:
  - 24 are younger than 14 days;
  - 19 were seen again but never filed;
  - 2 issues are still open with no close;
  - 20 are file decisions with no issue mapped (a comment on an existing issue, or a rollup).
- Labels by evidence level:

| evidence level | file | dismiss | no label |
|---|---|---|---|
| exact | 6 | 0 | 27 |
| full-rebuild | 0 | 5 | 1 |
| no-traces | 3 | 11 | 3 |
| no-logs | 50 | 31 | 8 |
| ledger-only | 28 | 57 | 6 |

  **The most faithful items are the least labelled**: they are recent, so their outcome is not known yet.

### 1.4 The de-duplication data (dataset `fleet_dedup_v1`)

- 100 scrubbed GlitchTip signals: the fleet's committed `reference-dedup/corpus.json`.
- Its own eval measures the collapse ratio through pure functions (`normalized_key`, `low_signal`,
  `operational_class`, `_is_test_signal`). No model; deterministic.

## 2. What we measure, and how a run works

1. **One item = one decision.** The adapter calls the fleet's own `investigate(signal, probe_table)`. The model
   asks for probes and gets the table's answers; then it decides. The fleet's deterministic gates run as in
   production.
2. **Per item:**
   - the disposition, `correct`, `false_dismiss` (the reference says file, the arm dismissed), `silent_drop`,
     `escalated`;
   - `table_miss`: counted, not scored;
   - cost and latency.
3. **Arms differ only in the model.** Same prompt (`c2ece738`), same gates, same tables. A prompt change later is
   a new arm the same way.
4. **Fair comparisons are arm against arm on the same items.** An arm against production's recorded decision
   is not fair: production saw live evidence and the arm sees the rebuilt table. Production's recorded decision
   is kept as an item field, for reading.
5. **Reported on all items, and on the exact ones** (`--where evidence_level:exact`). The difference shows what
   rebuilt evidence does.

## 3. References and the goal (to discuss: §6.1–6.3)

### 3.1 The proposal

- **Deciding**: the outcome reference.
- **Primary measure**: `false_dismiss`, lower, limit 0. It is measured on the 87 `file` labels, which come from
  issues people fixed, de-duplicated or reopened.
- **Second limit**: `escalated` at most 0.05, the fleet's own escalate bar (EVAL.md).
- **Shown beside them**: `correct` (all 187 labels), cost, latency.
- **Strategy `frugal`**: the cheapest arm that meets both limits.
- **Not deciding**: the hand-label reference, shown for reading.

### 3.2 The outcome mapping, as counted above

1. A filed issue closed as completed, as a duplicate, or reopened → `file`.
2. Closed as not planned → `not-file`. No such issue exists yet, so this rule labels nothing in v1.
3. No mapped issue, and the fingerprint filed later → `file`.
4. A file decision with no mapped issue → no label.
5. Not seen again within 14 days → `dismiss`.
6. Anything else → no label.

## 4. The arms, the runs, and the cost

### 4.1 The arms

All of them are aliases the fleet's gateway already exposes: no new provider, no new key type.

| arm | gateway alias → model | list price, in / out per M tokens | cost per decision (list, with cache) |
|---|---|---|---|
| **baseline** | `fleet-triage-pro` → deepseek-v4-pro (production) | $1.600 / $3.200 | $0.01003 (billed today: $0.0070) |
| A | `fleet-triage-flash` → deepseek-v4-flash | $0.091 / $0.182 | $0.00060 |
| B | `homelab-kimi` → kimi-k2.6 | $0.650 / $3.410 | $0.00858 |
| C | `homelab-glm` → glm-5.2 | $0.006 / $7.000 | $0.01416 |
| D | `eval-claude-sonnet` → claude-sonnet-5 | $2.000 / $10.000 | $0.02474 |
| E | `eval-claude-haiku` → claude-haiku-4.5 | $1.000 / $5.000 | $0.01237 |
| F | `homelab-qwen37-flash` → qwen3.7-flash | $0.030 / $0.130 | $0.00034 |
| G | `eval-qwen-flash` → qwen3.8-flash | $0.150 / $0.470 | $0.00129 |

How the cost per decision is computed:
- token counts from production (§1.2): 2,018 uncached input, 2,506 cached, 2,020 output;
- each model's list price on OpenRouter, 2026-10-29.

How far it can be off:
- output length varies by model. A model that writes twice as much costs up to about 2× on output; at p95
  output (3,745 tokens) the costs are about 1.7×;
- production is billed 30% below list today, so list prices are the conservative side.

### 4.2 The runs, in two stages

The harness repeats an arm with `--repeat`. Each arm runs as its own process (`experiment-run` is sequential),
so arms run side by side.

| stage | what | calls | cost (list) | wall time |
|---|---|---|---|---|
| 1. Screen | 8 arms × 236 items × 1 | 1,888 | **$17.02** | about 2.5 h (slower models longer) |
| 2. Repeat finalists | baseline + 3 best × 236 × 2 more (k = 3 in all) | 1,888 | $7–29, by which arms | about 4.5 h |
| **Total** | | 3,776 | **about $24–46** | about 7 h |

- Stage 2's range runs from the cheapest finalists (flash, kimi, qwen) to the dearest (sonnet, glm, haiku).
- **For comparison, every arm at k = 3: $51.06.**
- **A cap per arm** on the minted key, at 1.5× its estimate. A run that hits it stops; it never overspends.
- `--dry-run` prices each arm first, with the gateway's prices.

### 4.3 De-duplication runs

100 signals × 2 arms (`alert_key_dedup_enabled` on and off). The reference is the current code's output,
frozen as silver (a regression guard). $0, seconds.

### 4.4 Continuous use, after v1

The fleet now keeps each decision's probe answers as it decides; homelab's confirmation of the rollout is
pending. So every new decision is an **exact** item.

Each month:
- capture the new decisions (`--since-capture`) as the next version: about 55–70 Orrery decisions;
- run the baseline and the current best arm at k = 3: about 70 × 3 × 2 × $0.012 ≈ **$5 a month**;
- read the trend.

Adding the fleet's other projects (podcast, homelab) multiplies the item count. That is the step if Orrery's
labels stay thin.

## 5. The order of work

1. The engineering plan's P1–P7 (no spend).
2. P8 and P9 with a stand-in model (no spend).
3. Capture, dataset, both references; all committed before any billed call.
4. Dedup runs ($0).
5. Stage 1 ($17), read; stage 2 (finalists), read.
6. The goal decided on the outcome reference.
7. The example's README with the numbers; `experiments.json` registration.
8. The first monthly version from the fleet's own captures, once some exist.

## 6. To discuss before any billed run

### 6.1 Which reference decides

The outcome reference has 187 labels, but it is partly circular:
- 85 of its 100 `dismiss` labels are on items production itself dismissed. "Nothing happened afterwards"
  echoes production's own choice: an arm that dismisses as production did scores well on them;
- the 87 `file` labels are sounder, since people fixed, de-duplicated or reopened those issues.

Hence the proposal: `false_dismiss` decides, `correct` is shown. Options:
- **(a) Outcomes only**, as proposed.
- **(b) The owner labels a sample**: EVAL.md's "operator labels the ground truth, ~20–30 cases". For example 60
  items:
  - all 21 of production's false dismissals;
  - the 33 exact items;
  - a few escalations.

  About 1–2 h of the owner's time. It gives a person's gold where the outcomes are weakest.
- **(c) A silver judge**: a strong model labels the items. Fast, but it brings a model's bias into the
  reference.

### 6.2 Escalations and cleanups

They are labelled by their fingerprint's fate, like the rest: 33 of 52 escalations had their fingerprint filed
later. So an arm that escalates is scored on them too. Keep that, or leave escalations and cleanups unlabelled
("a person's call")?

### 6.3 The 14-day rule

A dismissal is right if the fingerprint is not seen again within 14 days. 14 is a guess. A longer window labels
fewer items but makes each label more certain.

### 6.4 The budget and the arms

The proposal:
- stage 1 on all 8 arms ($17);
- stage 2 on the baseline and the 3 best ($7–29);
- a cap of 1.5× each arm's estimate.

Questions: drop or add an arm? The DGX's local Qwen3-30B is possible at $0, but it needs the GPU mode switched
to it.

### 6.5 Rebuilt evidence

Only 33 items are exact; 91 are ledger-only, where the model sees only the signal. Results on those measure
judgement with little evidence, which is a different question from production's. They are reported separately,
by evidence level, never mixed silently.
