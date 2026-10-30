# Plan: applying 0.6.0 to the triage fleet — the application plan, v3

## Status

- **v3**, 2026-10-30. The third independent review (advisor, Fable 5) said: "not ready to run as written; ready
  after the owner's answers plus three changes". Its findings are folded in, tagged R3-…; v1 and v2 are in git
  history.
- **What this plan covers:** applying the lane from [PLAN_0.6.0.md](PLAN_0.6.0.md) (the engineering plan) to the
  homelab's triage fleet (signal-fleet, Fleet 2) on Orrery. Two things are measured:
  1. the triage decisions: the model step, billed;
  2. the de-duplication: the deterministic filing step, $0.
- **Where the numbers come from:** the fleet's ledgers and stores (read by homelab); GitHub (the close comments of
  all 42 issues, read by review 3 with `gh api graphql`); Langfuse's database; OpenRouter's price list; the
  gateway's model list. All measured 2026-10-29/30. Every number in §1 was recomputed from the data
  (`review3/v3.py`, `label_counts_v2.py`), not copied from a review.
- **What is still open:** §6, the owner's decisions.

## 1. The data we have

### 1.1 The decisions (dataset `orrery_triage_v1`)

- **236 Orrery triage decisions**, 2026-07-25 → 2026-10-29, one per occurrence.
  - The fleet decided: dismiss 122, escalate 52 (22%), file 50, cleanup 12.
  - One prompt throughout (`c2ece738`); 228 decisions on `fleet-triage-pro`.
- **172 distinct fingerprints.** 113 items share one with another item.
- **Each item** holds the signal and a probe table answered as of the decision's time, plus the decision, the
  outcome and provenance. The fleet's `scrub.py` cleaned it, and gitleaks found no leaks.

| evidence level | items | the probe table |
|---|---|---|
| exact | 33 | the model's own answers, verbatim |
| full-rebuild | 6 | every store covers it |
| no-traces | 17 | logs and metrics |
| no-logs | 89 | metrics only |
| ledger-only | 91 | the signal only |

- **Test signals.** 3 items are blank-stage probes (`orrery tls-node migration probe`): test signals, left out of
  the dataset with `--where stage:…` (R3 A5).
- **Per-decision capture is live.** Since 2026-10-29 22:13 UTC, every new decision is recorded as the model saw
  it, so new items are exact.

### 1.2 What a decision costs and takes today

From 140 production decisions since 2026-10-15:
- 3.04 turns;
- 4,524 input tokens (2,506 of them cached) and 2,020 output tokens;
- $0.0070 billed (p95 $0.0143);
- 34.3 s (p95 62.5 s).

### 1.3 The references: your own close comments carry the verdict (R3 A2)

- **Every one of the 42 issues was closed by you with a comment that says what it was** (review 3,
  `closers.json`):
  - 22 fixed ("Fixed in v0.8.0", "fixed by <commit>", "no event since the fix");
  - 10 noise ("external browser noise, not orrery code", "came from a deployed staging bundle", "low-signal
    rollup", "Triage-bot config noise");
  - 4 duplicates of those;
  - the rest open or reopened.
- **GitHub's close reason carries nothing here:** it is `COMPLETED` on 37 of 41 closes, whatever the comment
  says.
- **Who closed an issue can't tell the fleet from you:** the fleet writes with your token, so every close and
  reopen is `chipi`'s.

**The mapping, v3 (by the issue's verdict, carried to every decision on its fingerprint):**
1. The issue was fixed → `file`.
2. The issue was noise → `dismiss`.
3. A duplicate → its target's verdict.
4. The dismissal's own `[config]` follow-up is not a filing → no label from it.
5. A decision after the issue closed → no label.
6. A file decision with no issue → no label.
7. Not seen again, and at least 14 days old → `dismiss`.
8. Anything else → no label.

**Labels by what the fleet decided:**

| the fleet decided | `file` | `dismiss` | no label | total |
|---|---|---|---|---|
| dismiss | **7** | 90 | 25 | 122 |
| escalate | 20 | **24** | 8 | 52 |
| file | 9 | **16** | 25 | 50 |
| cleanup | 0 | 3 | 9 | 12 |
| **all** | **36** | **133** | **67** | 236 |

- **169 labelled items on 138 fingerprints**; the `file` labels are on 22 fingerprints.
- **Production's 7 false dismissals** (dismissed, and the issue was fixed): 3 chunk-skew import failures, 1
  WebGL, 3 ServiceWorker updates. Each has a named fix.
- **Production's 40 false alarms** (filed or escalated, and the issue was closed as noise). On this stream the
  fleet's problem is **over-filing noise**, not missing defects.
- **Escalations judged:** 20 were right (the issue was fixed), 24 were false alarms.

**Labels by evidence level:**

| evidence level | file | dismiss | no label |
|---|---|---|---|
| exact | 0 | 1 | 32 |
| full-rebuild | 0 | 5 | 1 |
| no-traces | 2 | 10 | 5 |
| no-logs | 19 | 52 | 18 |
| ledger-only | 15 | 65 | 11 |

The exact items are all younger than 14 days and mostly unlabelled (r3-m3): an age effect, not a data fact.
Their labels come from you (§3).

### 1.4 The de-duplication data (`fleet_dedup_v1`)

100 scrubbed signals (the fleet's `reference-dedup/corpus.json`) and its pure functions. No model; $0.

## 2. What we measure, and how a run works

1. **The replay.** The adapter calls the fleet's `investigate(signal, probe_table)`, and the gates run as in
   production.
2. **Per item:**
   - `false_dismiss`: the arm dismissed something whose issue was fixed;
   - `false_alarm`: the arm filed or escalated something closed as noise;
   - also `correct`, `escalated`, `table_miss`, cost and latency;
   - keys are left out on unlabelled items.
3. **The arms differ only in the model.**
4. **The comparison is arm against arm on the same items.** Production's recorded decision is a field, for
   reading.
5. **What v1 measures:** judgement on mostly thin evidence. 78% of the labelled items have no logs or only the
   signal. Results are reported per evidence level. The monthly exact versions (§4.4) measure production's own
   question.
6. **Independence:** the deciding gold covers one item per fingerprint.

## 3. References and the goal

- **Deciding, `gold/orrery_triage_v1`: your verdicts.** You confirm the verdict on the 42 issues: fixed, noise
  or unknown. They are prefilled from your own close comments; 3 "noise?" entries and #468 need your eye, about
  20 minutes. You also label the 33 exact items, about 45 minutes. Then:
  - the issue verdicts carry to the labelled items, one per fingerprint, about 138;
  - the exact items add their own;
  - the goal sets `min_items: 40`.
- **Shown beside it, never deciding** (`silver/…`, ADR-0020):
  - `silver/orrery_triage_v1_outcomes`, the v3 mapping as computed;
  - `silver/orrery_triage_v1_hand`, the 9 fixture labels.

  They disagree with each other on 2 of the 6 items both cover (r3-m5), which is a check worth showing.
- **The goal:**
  - primary `false_dismiss`, lower;
  - axes: `false_alarm` (lower, shown), `escalated` (shown), cost, latency;
  - strategy `frugal`;
  - **no limits in v1** (production escalates 22% here; EVAL.md's 5% came from curated fixtures). In v2 the
    limits come from the baseline's own numbers on this set.

## 4. The arms, the runs, and the cost

### 4.1 Five arms (R3 Q4)

| arm | alias → model | billed key today | per decision (uncached list price) |
|---|---|---|---|
| **baseline** | `fleet-triage-pro` → deepseek-v4-pro | fleet | $0.01370 |
| A | `fleet-triage-flash` → deepseek-v4-flash | fleet | $0.00078 |
| B | `homelab-kimi` → kimi-k2.6 | fleet | $0.00983 |
| E | `eval-claude-haiku` → claude-haiku-4.5 | **podcast** | $0.01462 |
| D | `eval-claude-sonnet` → claude-sonnet-5 | **podcast** | $0.02925 |

- **Dropped:**
  - glm-5.2: output at $7/M makes it dearer than the baseline with no reason to expect better. Its input price
    of $0.006/M looks like an anomaly in the price list (r3-m2);
  - the two qwen flashes.
- **Optional:** the DGX's local Qwen3-30B, when the DGX is idle and with a GPU-mode switch (a shared-state
  action).
- **Arms D and E** need aliases off the podcast key first (§5).

### 4.2 The runs (R3's design)

Run on the labelled set L: about 138 items, one per fingerprint.

| step | what | calls | cost |
|---|---|---|---|
| 0 | smoke: 5 arms × 2 items | 10 | $0.14 |
| 1 | screen: 5 arms × L × k = 1 | 690 | $9.41 |
| 2 | finalists: baseline + 2 best × L × k = 2, fresh; **the decision reads these only** | 828 | $6.70 (A, B) – $15.90 (D, E) |
| **total** | | about 1,530 | **$16–26**, about 4 h |

- **Power** (review 3, paired sign-flip): at n = 55 and k = 3, a 30% against 15% gap separates with power 0.91.
  Gaps of about 5 points do not separate below n = 172 and k = 3.
- **The cap:** one LiteLLM virtual key per arm with `max_budget` at 1.5× its estimate, plus
  `EVAL_MAX_COST_USD`.
- **If L ends up about 60** (you label items rather than issues): stage 1 at k = 2 ($18.80) and stage 2 at
  k = 3; only gaps of about 15 points will separate.

### 4.3 De-duplication

One arm: the fleet's current code, as a regression guard against frozen silver. $0.

### 4.4 Continuous use

- **Monthly:** the new decisions from the live capture, all exact.
- **Runs:** the baseline and the best arm at k = 3, $5–9 a month.
- **Labels:** the month's outcome labels exist 14 days after it ends, and your verdicts on its new issues are a
  few minutes.

## 5. The order of work, with the prerequisites

1. The engineering plan's walking skeleton ($0), then its breadth.
2. **Prerequisites in the homelab repository**, each with your go there:
   - the build script (R2-E) committed and pinned, and extended with:
     - each issue's close and reopen comments (R3 A2, m1);
     - escalations joined to their issue by alert key, not only by fingerprint (R3 A5: 6 escalations lost their
       issue in the join);
   - aliases for D and E on the fleet's key, or an eval key;
   - one capped virtual key per arm, tagged `evh-eval`, which the fleet's own measurements exclude.
3. **Rebuild the delivered file** with comments and the better join; capture; make `orrery_triage_v1` (test
   signals out) and `orrery_triage_smoke`.
4. **Your verdicts and labels (§3)**, which become `gold/orrery_triage_v1`; then the two silver references.
5. Commit everything before any billed call.
6. Dedup ($0).
7. Smoke ($0.14), stage 1 ($9.41), stage 2.
8. The README with the numbers by evidence level; `experiments.json`.
9. The monthly versions.

## 6. To decide

1. **Your verdicts**: confirm the 42 issue verdicts (about 20 minutes) and label the 33 exact items (about 45
   minutes)?
2. **Five arms, $16–26 in all**, capped per arm?
3. **`silver/` for the second references**, with a caveat saying what each one is (ADR-0020)? Silver means "a
   model wrote it" today.
4. **v2's limits**: from production's own numbers, and the operator's escalate tolerance (EVAL.md §7) later?
