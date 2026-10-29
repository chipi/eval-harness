# Plan: applying 0.6.0 to the triage fleet — the application plan, v2

**Status.** v2, 2026-10-29, after the second independent review (advisor, Fable 5), which said: "not ready to run
as written". Every finding is folded in, tagged R2-…; v1 is in git history (`777b6cac`).

**What it covers.** It applies the lane from [PLAN_0.6.0.md](PLAN_0.6.0.md) (the engineering plan) to the
homelab's triage fleet (signal-fleet, Fleet 2) on Orrery. **Two things are measured**:
1. the triage decisions: the model step, billed;
2. the de-duplication: the deterministic filing step, $0.

**Where the numbers come from.** Every number was measured on 2026-10-29, and the scripts are named in §7:
- the fleet's ledgers and stores, read by homelab;
- Langfuse's database on the mini;
- OpenRouter's price list;
- the gateway's model list (`infra/litellm/config.yaml`).

§6 lists what is still to be decided.

## 1. The data we have

### 1.1 The decisions (dataset `orrery_triage_v1`)

- **236 Orrery triage decisions**, 2026-07-25 → 2026-10-29, one per occurrence.
  - By month: Jul 47, Aug 71, Sep 63, Oct 55.
  - The fleet decided: dismiss 122, escalate 52 (22%), file 50, cleanup 12.
  - One prompt throughout (`c2ece738`). Models: `fleet-triage-pro` 228, `deepseek-v4-flash` 8.
- **172 distinct fingerprints.** 113 items share a fingerprint with another item, across 49 fingerprints
  (R2-H). The independent version is `orrery_triage_v1_fp`: one item per fingerprint, the newest
  (`dataset-from-capture --one-per fingerprint`), **172 items**.
- **Each item** holds the signal, a probe table answered as of the decision's time, the fleet's decision, the
  outcome, and provenance. The items were scrubbed by the fleet's `scrub.py`, and gitleaks found no leaks.

| evidence level | items | period | the probe table |
|---|---|---|---|
| exact | 33 | since 10-15 | the model's own answers, verbatim; the rest of the menu rebuilt |
| full-rebuild | 6 | 10-08 → 10-15 | every store covers it |
| no-traces | 17 | 09-30 → 10-07 | logs and metrics |
| no-logs | 89 | 08-14 → 09-29 | metrics only |
| ledger-only | 91 | 07-25 → 08-13 | the signal only (102 items have no GlitchTip issue left) |

**Where the data comes from (R2-E).** Homelab's build script read the stores (GlitchTip's and Langfuse's
databases, VictoriaLogs, VictoriaMetrics, VictoriaTraces). It is not in any repository yet, so committing it in
the fleet's repo and pinning its commit is a prerequisite (§5).

### 1.2 What a decision costs and takes today

From Langfuse, 140 production decisions since 2026-10-15, all on `deepseek-v4-pro`:

- **Turns:** 3.04 (max 4).
- **Tokens:** 4,524 input (2,018 uncached + 2,506 cache read); 2,020 output (p95 3,745).
- **Billed:** $0.0070 a decision (p95 $0.0143).
- **Latency:** 34.3 s (p95 62.5 s).

### 1.3 The references

#### Hand labels

9 items: 5 cleanup and 4 dismiss, carried onto occurrences by fingerprint. There is no `file` label among them.

#### Outcome labels, after review 2 (R2 Blocker 1)

What v1 got wrong:
- **45** of its 87 `file` labels rested on the fleet's **own escalation issues** (label
  `triage-fleet/escalated`): an escalation the fleet opened and a person closed says that a person acted, not
  that filing was right.
- **8** rested on issues that **pre-dated** the decision.
- **6** were filed **39–49 days later**, which contradicts the 14-day rule.
- **60** were closed as "completed" in **three bulk sessions of about an hour each** (2026-08-27 23h: 13 issues;
  10-01 06h: 11; 10-20 07h: 5). Completed is GitHub's default close reason.
- Some reopens can be the fleet's own (`filing.py:736`), and the data records **no actor**. P1's github importer
  now records one.

The v2 mapping, first match wins:
1. the fleet's escalation issue → no label;
2. an issue that pre-dates the decision → no label;
3. an issue filed within 14 days and closed as not planned → `not-file`;
4. an issue filed within 14 days and closed as completed or duplicate, or reopened → `file`;
5. a later `file` decision within 14 days → `file`;
6. a file decision with no issue mapped → no label;
7. not seen again, and at least 14 days old → `dismiss`;
8. anything else → no label.

| the fleet decided | `file` | `dismiss` | no label | total |
|---|---|---|---|---|
| dismiss | **3** | 85 | 34 | 122 |
| escalate | 0 | 12 | 40 | 52 |
| file | 24 | 0 | 26 | 50 |
| cleanup | 0 | 3 | 9 | 12 |
| **all** | **27** | **100** | **109** | 236 |

Why 109 items carry no label:

| reason | items |
|---|---|
| the issue is the fleet's own escalation | 45 |
| seen again but not filed, or too young | 30 |
| a file decision with no issue mapped | 18 |
| the issue pre-dates the decision | 8 |
| filed more than 14 days later | 6 |
| the issue is still open | 2 |

Labels by evidence level:

| evidence level | file | dismiss | no label |
|---|---|---|---|
| exact | 2 | 0 | 31 |
| full-rebuild | 0 | 5 | 1 |
| no-traces | 1 | 9 | 7 |
| no-logs | 14 | 29 | 46 |
| ledger-only | 10 | 57 | 24 |

**What this means:**
- **27 `file` labels, on 23 fingerprints**, of which **17 are on issues closed in a bulk hour.** The outcomes
  alone can barely measure a false dismissal: production has 3 by this measure.
- **85 of the 100 `dismiss` labels are on items that production itself dismissed.** "Nothing happened" echoes
  production's choice back (the circularity).
- The 33 exact items have **2** labels.
- A 30-day window instead of 14 gives 85 `dismiss` labels, and still 27 `file`.

#### The consequence

**The outcome reference cannot decide v1.** It is kept as a second-named reference, for reading. The deciding
reference is a person's, §3.

### 1.4 The de-duplication data (`fleet_dedup_v1`)

100 scrubbed signals, from the fleet's committed `reference-dedup/corpus.json`. The fleet's pure functions run
over them; no model, deterministic.

## 2. What we measure, and how a run works

1. **The replay.** One item is one decision. The adapter calls `investigate(signal, probe_table)`; the model asks
   for probes and gets the table's answers; the fleet's gates run as in production.
2. **Per item:** the disposition, `correct`, `false_dismiss`, `silent_drop`, `escalated`, `table_miss` (counted,
   not scored), cost and latency.
3. **The arms differ only in the model.** Same prompt, gates and tables.
4. **The fair comparison is arm against arm on the same items.** Against production's recorded decision it is
   not fair: production saw live evidence. Production's recorded decision is kept as a field, for reading.
5. **What v1 measures (R2-G).** 90% of the outcomes' `file` labels, and most items, have no logs or only the
   signal. So v1 measures **judgement on thin evidence**, not production's own question. The first measurement
   of that question is the monthly exact versions from the fleet's live per-decision capture (§4.4). Results are
   always reported per evidence level.
6. **Dependence (R2-H).** The deciding comparison runs on items with one per fingerprint, because the paired test
   treats items as independent.

## 3. References and the goal

### 3.1 The proposal

**The deciding reference.** It is `gold/orrery_triage_v1`: **the owner's labels on a chosen set** (§6.1).
`experiment-run` scores against it directly (R2-A).

**The goal** (R2 Blocker 2):
- primary measure `false_dismiss`, lower, **no limit in v1**;
- `escalated`, lower, shown and **not limited in v1**;
- cost and latency shown.

The limits from the fleet's EVAL.md (false-dismiss 0, escalate at most 5%) were met on 27 curated fixtures.
Production on this stream escalates 22%, so every arm would fail them. In v2, the limits are set from the
baseline's own numbers on these items, for example "no worse than production".

**Second-named references, read only:**
- `orrery_triage_v1_outcomes` (§1.3);
- `orrery_triage_v1_hand` (the 9 fixture labels).

Both are read through `rescore --reference-id`.

### 3.2 The owner's labelling set (to confirm: §6.1)

About 60 items, one per fingerprint, chosen so that the hard cases are in:

| group | items | why |
|---|---|---|
| contested dismissals | 21 | production dismissed them, and the fingerprint came back as an escalation or a filing |
| exact items | 33 | the only items where the replay sees what the model saw |
| escalations | about 6 | so that `escalated` is judged and not only counted |

The groups overlap, so the total is about 60. The sheet (P8's `label_sheet.py`) shows each item's signal, its
probe answers in short, production's decision and the outcome; the owner writes `file`, `dismiss`, `escalate` or
`cleanup`.

**About 1–2 minutes an item, so 1–2 hours.** It is the fleet's own EVAL.md step: "operator labels the ground
truth".

## 4. The arms, the runs, and the cost

### 4.1 The arms

Gateway aliases, all verified to exist and to route as stated.

| arm | alias → model | billed key today | list in / out per M | per decision |
|---|---|---|---|---|
| **baseline** | `fleet-triage-pro` → deepseek-v4-pro | fleet | $1.600 / $3.200 | $0.01370 |
| A | `fleet-triage-flash` → deepseek-v4-flash | fleet | $0.091 / $0.182 | $0.00078 |
| B | `homelab-kimi` → kimi-k2.6 | fleet | $0.650 / $3.410 | $0.00983 |
| C | `homelab-glm` → glm-5.2 | fleet | $0.006 / $7.000 | $0.01417 |
| D | `eval-claude-sonnet` → claude-sonnet-5 | **podcast** | $2.000 / $10.000 | $0.02925 |
| E | `eval-claude-haiku` → claude-haiku-4.5 | **podcast** | $1.000 / $5.000 | $0.01462 |
| F | `homelab-qwen37-flash` → qwen3.7-flash | fleet | $0.030 / $0.130 | $0.00040 |
| G | `eval-qwen-flash` → qwen3.8-flash | **podcast** | $0.150 / $0.470 | $0.00163 |

**How the per-decision figure is computed:** 4,524 input tokens at the **uncached** price plus 2,020 output
tokens, which is how the adapter computes cost (R2-C). Production is billed below this ($0.0070 against $0.0137
for the baseline), so these figures are an upper bound on price. Output length varies by model: at p95 output,
costs are about 1.7×.

**Arms D, E and G bill the podcast project's OpenRouter key** (R2-B). They need aliases on the fleet's key, or
on an eval key, first: a homelab-repo change (§5).

### 4.2 The runs

Each arm runs as its own `experiment-run` process, so the arms run side by side.

| step | what | calls | cost | wall time |
|---|---|---|---|---|
| 0. Smoke | 8 arms × 2 items (`orrery_triage_smoke`, a 2-item version) | 16 | $0.17 | minutes |
| 1. Screen | 8 arms × 236 × 1 | 1,888 | **$19.91** | about 2.3 h (4.1 h at p95) |
| 2. Finalists | baseline + 3 best × 236 × **2 fresh repeats** | 1,888 | $7.79–$33.86 | about 4.5 h |
| **Total** | | 3,792 | **$27.87–$53.94** | about 7 h |

- **The smoke step** catches a provider that rejects the fleet's call shape (`response_format: json_object`)
  before any arm burns its retries on 236 items (R2-C).
- **The winner's curse (R2-H).** The finalists are picked on stage 1, and **decided on stage 2's two fresh
  repeats only**; stage 1 is never pooled into the decision.
- Every arm at k = 3 would cost $59.74.
- The runs cover all 236 items: the outcome rescore and the escalate rate read all of them. The decision reads
  the labelled, one-per-fingerprint set.
- **The cap**, two layers:
  - one LiteLLM virtual key per arm, with `max_budget` at 1.5× its estimate;
  - `EVAL_MAX_COST_USD` in the harness, per run.

  `--dry-run` prices each arm from the config's `usd_per_mtok_in/out`, which are set from the table above
  (r2-m2).
- **Power, honestly (R2-H).** On about 60 labelled independent items, only large differences separate (on the
  order of 15 points of `false_dismiss`). Arms within about 5 points will not separate, and the cheapest of the
  tied wins. That is the intent of a frugal goal, and the page says so.

### 4.3 De-duplication

One arm, the fleet's current code, as a regression guard against a frozen silver reference (R2-D). It runs on the
100 signals, costs $0 and takes seconds. When the fleet changes its dedup functions, the previous commit becomes
the baseline arm.

### 4.4 Continuous use

**Every decision is now captured as the model saw it** (live since 2026-10-29 22:13 UTC), so every new decision
is an exact item.

Each month:
- capture the new decisions (`--since-capture`), about 55–70 Orrery decisions;
- run the baseline and the current best arm at k = 3: about $5 a month (baseline + kimi). The dearest pair
  (baseline + sonnet) costs about $9.

**When a month's references exist (r2-m6).** A month's outcomes are complete only 14 days after it ends, so the
month's outcome reference is made then. The owner labels a few hard cases from the month, or none.

Adding podcast and homelab decisions multiplies the items, if Orrery's stay thin.

## 5. The order of work, with the prerequisites

1. The engineering plan's P1–P7 (no spend), and P4's fixture proof of the reference route.
2. P8 and P9 with a stand-in model (no spend).
3. **Prerequisites in the homelab repository** (R2-B, R2-C, R2-E), each with the owner's go there:
   - commit and pin the build script;
   - add aliases for D, E and G on the fleet's key, or on an eval key;
   - mint one capped virtual key per arm, tagged `evh-eval`;
   - exclude that tag in the fleet's own cost and ClickHouse measurements.
4. Capture; then `orrery_triage_v1` (236), `orrery_triage_v1_fp` (172) and `orrery_triage_smoke` (2).
5. **The owner labels the set (§3.2)**, which becomes `gold/orrery_triage_v1`. Then the outcome reference and the
   hand reference, under their second names.
6. Commit everything before any billed call (M3).
7. Dedup ($0).
8. Smoke ($0.17), stage 1 ($19.91), stage 2 (finalists), read.
9. Then:
   - the README with the numbers, by evidence level;
   - `experiments.json`;
   - the first monthly exact version once a month of captures exists.

## 6. To discuss before any billed run

1. **The deciding reference.** Do you label about 60 items (§3.2, 1–2 h)? This is recommended by review 2, and the
   recount backs it: 27 outcome `file` labels, 17 of them bulk-closed.
2. **Escalations and cleanups.**
   - In the v2 mapping no outcome labels an escalation `file`: its issue is the fleet's own.
   - In your labelling set, a few escalations are judged by you.
   - Keep that?
3. **The window.** 14 days gives 100 `dismiss` labels; 30 days gives 85. These are for reading only now, since
   they do not decide.
4. **The arms and the budget.**
   - 8 arms, $27.87–$53.94 in all, about 7 h, capped per arm.
   - D, E and G need aliases off the podcast key.
   - Drop any? The DGX's local Qwen3-30B could be added at $0, with a GPU mode switch.
5. **The limits.** None in v1, and from production's own numbers in v2. Agreed?
6. **What v1 measures.** Mostly judgement on thin evidence. The monthly exact versions answer production's
   question. Is v1 worth running now, or only once a month of exact captures exists (about 60 items by the end
   of November)?

## 7. How these numbers were made

The scripts are in the session scratchpad. They are reproduced into `examples/triage-fleet/` when P8 lands:
- `label_counts_v2.py`: the label tables, the bulk hours and the fingerprints;
- `lf_tokens.sh` and `lf_cache.sh`: tokens, turns, cost and latency, from ClickHouse;
- `or_prices.py`: the prices;
- the inline cost computation above;
- review 2's own recounts, in its `review2/` scripts.
