# Handover — the ML arms

> **Update 2026-09-30 — the three blocked arms ran** (Linux, torch 2.14.0, configs
> unchanged): `bart_m` 0.3367 (5th of 29, 5.1 s), `bart_s` 0.3276 (10th, 4.5 s), neither
> separated from `bart_l`; `bart_l_xsum` 0.2071, **last of 29**, below `lead3`, separated
> from all 28. Open items below, resolved: `bart_s` is 230M params stored at fp16, hence
> 460 MB; `rank_stability` re-run at k=29 (ρ 0.44 at 20 items, 0.79 at 100);
> REPORT_SUMMARIZATION and NOTES (entry 59) now carry all of it. Still open: the XSum arm
> cannot separate training distribution from decode length. The runs listed below as
> uncommitted were committed on 2026-09-29. The rest of this file is as of 2026-09-26.

State as of 2026-09-26. Facts, numbers and locations. This covers the session that added
the first non-LLM arms to the summarisation example; the 24-arm LLM study it extends is in
[`HANDOVER.md`](HANDOVER.md), with reasoning in [`NOTES.md`](NOTES.md) and results in
[`REPORT_SUMMARIZATION.md`](REPORT_SUMMARIZATION.md).

## Repo state

Branch `ml-arms-bart-lead3`, 4 commits ahead of `main`. Working tree clean.
`make ci` green. `gitleaks detect`: no leaks found, 6 commits scanned.

```
d33c4d8  Three arms that cannot run here, and the machine they run on instead
9e71ce6  Correct a claim I made in the pin comment and could not support
a57d778  A family test that actually does Holm, and an item set that is not a dataset
fb7366a  The ML half of "ML vs LLM", and the three things that were wrong with the path
```

## What ran, and where the runs are

Four runs in `harness/data/runs/` (uncommitted — they exist only on the machine that
made them, an Intel i7 macOS box; untracked rather than ignored since 2026-09-29, so
`git add` will take them):

| run | dataset | coverage | grounding | latency/item |
|---|---|---|---|---|
| `cnn_bart_l_v1_20260926T153353Z` | cnn_dailymail_20 | 0.365996 | 0.871262 | 11861 ms |
| `cnn_lead3_v1_20260926T152800Z` | cnn_dailymail_20 | 0.261655 | 1.000000 | 0.07 ms |
| `cnn_bart_l_n200_v1_20260926T153757Z` | cnn_dailymail_200 | 0.346121 | 0.883821 | 11010 ms |
| `cnn_lead3_n200_v1_20260926T153351Z` | cnn_dailymail_200 | 0.271806 | 1.000000 | 0.07 ms |

Both arms cost `$0.00`. `bart_l` reports `input_truncated` 0.20 (n=20) and 0.23 (n=200).

## Headline results, n=200, k=26

`bart_l` ranks **1st on coverage at 0.346121**, ahead of `deepseek_m` at 0.346039 — a gap
of 0.00008. A tie in everything but sort order.

```
global test    p = 0.0002       Nemenyi CD 2.80   span 6.70
pairs          54 of 325 distinguishable   (was 34 of 276 at k=24)
bootstrap      bart_l   P(1st) 0.49   avg rank 11.98
               deepseek_m P(1st) 0.42   avg rank 10.75
frontier       9 of 26 arms; both free arms on it
```

`bart_l` wins the most items outright of any arm while ranking 5th on average — a bimodal
arm. Replicates on the 180 out-of-sample items (`P(1st)` 0.52, avg rank 12.11).

### BART vs the field — `family_test.py`, Holm, m=25 declared in advance

| stratum | separated | ahead on point estimate |
|---|---|---|
| 200 items, coverage | **12 of 25** | 25 of 25 |
| 154 items (fits window), coverage | 8 of 25 | 24 of 25 |
| 200 items, concision | 9 of 25 | 17 of 25 |

Against `deepseek_m`: delta +0.0001, p = 0.9923, 85 of 200 items won. Ahead of everyone on
the mean, separated from half of them.

### `lead3`

Last of 26 at n=200 (`coverage` 0.271806), `P(bottom 5)` = 1.00. Every hosted arm beats it,
the worst by 0.031. At n=20 it beat six of them — more data made the floor a floor.

Incidental control: `fmt_narration` = 0.01 on LEAD-3, whose output is verbatim source text
and cannot narrate. Those two hits are the regex's false-positive rate on ordinary news
prose, which puts a floor under the 65 contaminated outputs found across the LLM arms.

## Three things I predicted and got wrong

Recorded because the predictions are in the repo and someone will otherwise trust them.

1. **The adapter docstring's prediction is refuted.** `adapter.py` still says to "expect an
   LLM to beat BART on ROUGE AND ground less: better and riskier at once". BART leads
   coverage, concision, rouge1 and rougeLsum, and grounds at 0.884 against a field of
   0.25–0.43. Better *and* safer, both halves backwards. **The docstring has not been
   updated** — left in place deliberately so the next reader sees the prediction and the
   measurement, but it should not stay that way indefinitely.

2. **Adding arms did not weaken the ladder.** I predicted fewer separated pairs at higher
   k, because Nemenyi's CD grows with k. It rose: 34/276 → 54/325, 12.3% → 16.6%. CD did
   grow (2.57 → 2.80) but the two new arms sit at the extremes and stretched the span from
   5.1 to 6.70. Adding arms weakens a ladder only when they land in the middle.

3. **The truncation caveat was not the confound I called it.** Restricting to the 154
   articles inside BART's window made it look *worse*, not better, and flipped its delta
   against `deepseek_m` negative. Long articles are harder for everyone:

   ```
   arm                       fits(154)   long(46)   long-fits
   cnn_bart_l_n200_v1           0.3633     0.2887     -0.0745
   cnn_deepseek_m_n200_v1       0.3670     0.2758     -0.0913
   cnn_anthropic_l_n200_v1      0.3349     0.2503     -0.0846
   cnn_lead3_n200_v1            0.2807     0.2421     -0.0386
   ```

   BART degrades *less* than the best LLM. Truncation costs it nothing relative to the
   field — consistent with lead-biased references, which is also why LEAD-3 degrades least.

## The caveat that does stand

`bart_l` was fine-tuned on cnn_dailymail; the 24 LLMs are zero-shot. Single-reference ROUGE
rewards reproducing the reference's house style, and BART learned that style from this
dataset's training split. **This is not "a 406M model matches frontier LLMs at
summarisation."** It is an in-distribution specialist against generalists, scored by
similarity to that distribution. `bart_l_xsum` (below) is the control and has not run.

Second caveat, structural: an arm at `cost_usd = 0.0` can only be dominated by another free
arm, because `_frontier` requires `cost_b <= cost_a`. Both free arms are on the frontier by
construction, not by merit. Say so wherever the frontier is reported.

## Three bugs fixed in the local path

None could surface until an arm used it; `hf_local` had never been run.

1. **The encoder window was read from the tokenizer, which does not know it.**
   `bart-large-cnn`'s `tokenizer_config.json` sets no `model_max_length`, so the tokenizer
   reported HuggingFace's `VERY_LARGE_INTEGER` sentinel (~1e30). `truncation=True`
   truncates *to* that, i.e. not at all, so a 1460-token article would have hit a
   1024-position encoder and raised `IndexError` on the first long item. Now resolved from
   `model.config.max_position_embeddings` and copied onto the tokenizer at build.
2. **The truncation the docstring called "recorded" was not recorded.** `_hf_local`
   returned output and `cost_usd` and nothing else. Now `input_truncated` per item, plus
   `tokens_in`, `tokens_out`, the resolved generation config and the window.
3. **`warmup()` would have sent a paid request for a free arm.** `if hf_local … else
   _litellm(...)`; `lead_k` has no weights and no endpoint and fell into the `else`.

Also: decode settings are now declared in configs rather than inherited from the
checkpoint. The previous `max_length=128 / min_length=32` lived in `adapter.py`, appeared in
no config and no run record, and silently overrode the settings the published CNN/DailyMail
numbers were produced with.

Verified none of this moved anything already published: `score()` recomputed over all 200
items of `cnn_deepseek_m_n200_v1` reproduces the stored metrics exactly, max abs delta
`0.000e+00`.

## New tooling

- **`scripts/family_test.py`** + `make family-test` — one arm against a family declared by
  `--against`, real Holm step-down (sorted ascending, `alpha/(m-i)`, first failure carried
  forward). Reuses `pair_test.per_item`. Registered in `self_test`'s CLI list, which is
  explicit, not a glob.
- **`--items FILE`** on `pair_test.py` and `family_test.py` — some strata are not datasets.
  The 154-item set is a property of a *run*, which `--exclude-dataset` cannot express.
- Makefile: `pair-test`'s comment claimed `FAMILY=n` applies Holm. It applies Bonferroni,
  as the script's own docstring always said. Corrected.

## What is blocked, and why

`bart_m` (distilbart-cnn-12-6), `bart_s` (distilbart-cnn-6-6) and `bart_l_xsum`
(bart-large-xsum) are written, dry-run clean, and **cannot run on x86_64 macOS**. All three
ship `pytorch_model.bin` without safetensors; `transformers` refuses `torch.load` below
torch 2.6 (CVE-2025-32434); torch has no Intel-Mac wheel above 2.2.2.

Procedure for a machine that can: [`../examples/summarization-cnn-dailymail/RUNNING_THE_ML_ARMS.md`](../examples/summarization-cnn-dailymail/RUNNING_THE_ML_ARMS.md).
No code changes are needed there — the lock resolves torch 2.14.0 for every platform except
x86_64 macOS, by marker.

**Correction to `HANDOVER.md:105-106`**, which records the restriction as arriving in
transformers 4.56. It is present in **4.55.4**; tested against `sshleifer/distilbart-cnn-6-6`.
Capping below 4.56 unblocks nothing. The cap stays for a different reason: transformers 5.x
does not recognise torch 2.2 and silently disables the torch backend.

## Environment, x86_64 macOS

Three ceilings, each found by an actual failure, all scoped by marker so no other platform
inherits them:

| pin | why |
|---|---|
| `torch>=2.2,<2.3` | no Intel-Mac wheel above 2.2.2; an open resolve picks 2.14 and fails at install |
| `transformers>=4.40,<4.56` | 5.17 installs, imports, prints "PyTorch was not found", then fails at model load |
| `numpy<2` | torch 2.2.2 is built against the 1.x C API; with NumPy 2 every tensor→array conversion raises |

Resolved: torch 2.2.2, transformers 4.55.4, numpy 1.26.4.

## Open items

- **`bart_l_xsum` cannot separate training distribution from output length.** XSum decodes
  at `max_length` 62 / `min_length` 11 against 142/56. A sixth arm at CNN/DailyMail decode
  lengths would separate them.
- **`bart_s`'s checkpoint is 460MB against `bart_m`'s 1.22GB**, which layer counts do not
  explain — possibly half precision. The Hub publishes no parameter count and there is no
  safetensors header. The run's `weight_files` sizes settle it.
- **The n=20 table cannot include the new arms.** `leaderboard --match _v2` scopes by config
  version, and a new arm correctly starts at `v1`. Not a naming slip — a gap in the version
  convention. n=200 is unaffected; every arm there is `_n200_v1`.
- **A noisy warning.** `Token indices sequence length is longer than the specified maximum
  (1163 > 1024)` comes from the untruncated token-counting call in `_hf_local`, not from
  generation, which truncates correctly. Harmless, and reads as if a 1024 encoder were
  being fed 1163 tokens.
- `rank_stability` not re-run at k=26. No family test on `grounding` (the gap is large and
  untested). `research/REPORT_SUMMARIZATION.md` and `NOTES.md` carry none of this yet.
- These four ML runs are NOT among the 143 committed on 2026-09-29 — they are on one
  machine and uncommitted. They are untracked rather than ignored, so `git add` works.

## Reproducing the numbers above

```bash
cd harness
PY=../examples/summarization-cnn-dailymail/.venv/bin/python

$PY scripts/leaderboard.py --dataset-id cnn_dailymail_200
$PY scripts/holdout_significance.py --dataset-id cnn_dailymail_200 \
     --exclude-dataset cnn_dailymail_20 --metric coverage
$PY scripts/family_test.py --dataset-id cnn_dailymail_200 \
     --a cnn_bart_l_n200_v1 --against _n200_v1 --metric coverage
```

The 154-item stratum is regenerated from the BART run's `input_truncated` column; there is
no committed copy, because it is derived from a run that is itself uncommitted.
