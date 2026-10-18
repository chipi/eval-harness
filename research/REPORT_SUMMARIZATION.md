# Evaluation report — 24 LLMs on news summarisation

**Dataset** `cnn_dailymail_200` · 200 articles — **all from CNN** (the first 200 test rows; the test split is 91% DailyMail) · human-written gold references
**Arms** 24 hosted models, 8 vendors, 3 price tiers each
**Protocol** test split, first 200 rows (all CNN) · metric `coverage` is ours; ROUGE-1/2/L F1 reported beside it · calibration: LEAD-3 on the full test set, ROUGE-1 39.94 vs 40.34 published — [docs/PROTOCOL.md](../docs/PROTOCOL.md#summarisation--cnndailymail)
**Design** 1 pass per arm · 4,800 calls · **$5.74 billed** ($4.93 by the price table — see Correction) · identical prompt, temperature 0, reasoning off
**Date** 2026-09-26; three local BART arms added 2026-09-30 · **Harness** [`../harness`](../harness) · **Journal** [`NOTES.md`](internal/NOTES.md) entries 56, 59

> **Scope correction, 2026-10-14 — read this first.** Every result in this report was
> measured on the first 200 rows of the CNN/DailyMail test split, and the split puts CNN's
> articles first: all 200 rows are **CNN's** (196 with CNN's own dateline, 4 partner pieces CNN
> republished), while the test split as a whole is 1,093 CNN and 10,397 DailyMail. So the findings below are findings about
> **CNN-style news**, not about CNN/DailyMail. It was caught by comparing a baseline with
> the literature for the first time: this repo's LEAD-3 scores ROUGE-1 **39.94** on the full
> 11,490-article test set (published: 40.34), but 30.20 on this slice, because CNN
> articles are harder to summarise from their lead (29.59) than DailyMail ones (41.02)
> (`docs/evidence/calibration/summarization.json`). The scorer is right; the sample was
> not representative. A seeded random **DailyMail slice** (`cnn_dailymail_dm200`) tests
> whether the conclusions travel (§3.7): **among the five local arms every comparison
> transfers** — the fine-tune beats LEAD-3 by the same margin, the XSum control still
> finishes last, distillation still costs nothing measurable. **Every comparison
> involving a paid model is untested outside CNN.**

> **Updated 2026-09-30 with the three local arms that could not run on the original
> machine** — two distilled BARTs (`bart_m`, `bart_s`) and BART fine-tuned on XSum
> (`bart_l_xsum`), all pickle checkpoints that need torch ≥ 2.6. The field is now 29.
> They answer the two questions `bart_l` left open: distillation takes a third (`bart_m`) to
> nearly half (`bart_s`) off `bart_l`'s time on the same machine with no separable loss, and the same architecture trained on a *different* corpus's house style
> finishes last — below LEAD-3. Old figures are named where they changed.

> **This report was re-measured at n=200 on 2026-09-26.** It previously covered
> `cnn_dailymail_20` — 20 articles, 3 repeats, $1.45 — and several of its headline claims
> did not survive. Where a number changed, the old one is named rather than quietly
> replaced; §6 carries the full list. The 20 articles are a subset of these 200, so every
> result below is also reported on the **180 that took no part** in the earlier run.


> **This is one of six experiments.** What all six agree on — and where they disagree
> with the conventional reading of a leaderboard — is in
> [`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).

---

## Executive summary

### The decision, in one table

| the choice | what the data says |
|---|---|
| **Self-host · small ML** | **`bart_l`** — BART-large-CNN, fine-tuned on this corpus, MIT, **1.6 GB**, runs on CPU. **0.3461 — wins outright.** Costs 11.0 s/item on the 12-core Mac's CPU (6.3 s on a 4-core Linux box). **Or its distillation `bart_m`** (1.2 GB): **0.3367, 1.5× faster than `bart_l` on the same machine (4.1 s vs 6.3 s), not separated from `bart_l`** (p = 0.16–0.17). |
| **Self-host · open-weight LLM, absolute** | **`deepseek_m`** — DeepSeek-V4.1-Flash, MIT, **552B backbone params** — but **510 GB of weights in the published checkpoint** (measured: 48 safetensors shards), because the card's headline count excludes a 196B Engram memory that ships with it. **0.3460** — statistically identical to the 1.6 GB model. Whether it fits one node depends on whether the Engram memory must be GPU-resident; **this report does not know, and no longer claims it cannot fit.** |
| **Self-host · open-weight LLM, ≤128 GB** | **`llama_m`** — Llama-3.3-70B at **int8, ~70 GB**. **0.3382**, costing **0.0078** against a 510 GB model. Native-precision alternative: `mistral_s` (24B, 48 GB) at 0.3255. |
| **Self-host · open-weight LLM, ≤64 GB** | **The same model at int4, ~35 GB** — 0.3382, **no further loss on paper**. If you would rather not quantise that far: `mistral_s` at 48 GB native, 0.3255. |
| **Deploy — rented API** | **`deepseek_m`** at **$191/month per 1M items**, 0.3460 — **0.0001** behind, and 7× faster per item than `bart_l` on the Mac it was timed from (4× against `bart_l`'s faster Linux timing). It is *also* MIT open-weight, so this row is a latency choice, not a licensing one. |
| **What should I not deploy?** | `anthropic_l` at **$9,826/month**. It ranks **18th of 29** (16th of 25 before the distilled arms, both of which beat it) and is 8.9% below free. |
| **Does paying more help?** | **No.** Quality per 10× cost: **−0.4%**, correlation r = −0.07. Over 24 arms and a 143× price range, price carried no information. |
| **How many arms are really tied at the top?** | **15 of the 28 others** — 13 paid arms and both distilled BARTs (was 13 of 25). The cheapest paid one is 143× cheaper than the dearest. |
| **Is a pilot enough?** | ρ(20 articles, 200) = 0.722 over the arms the uncommitted dev run had (0.667 over the 24 hosted arms, §3.1b) and it did pick the right winner here — but see the margin: 0.0001. |
| **Does it hold outside CNN?** | **For the local arms, yes; for the paid ones, unknown.** On 200 DailyMail articles the five local arms keep every verdict they had on CNN: `bart_l` beats LEAD-3 by +0.073 (CNN +0.074), `bart_m` ties `bart_l`, the XSum control is last (§3.7). The hosted arms were not re-run, so the price verdicts above are CNN-only. |
| **Fine-tune or pay?** | **Cost only — and only if it is fine-tuned on text like yours.** `bart_l` (fine-tuned on this corpus) matches the best paid arm to 0.0001 and is free, but *slower* (11.0 s vs 1.6 s, both timed from the Mac); distilled, 1.5–1.8× faster than `bart_l` on one machine. The control is decisive: **the same architecture fine-tuned on XSum scores 0.2071 — last of 29, below LEAD-3**. What `bart_l` has is this corpus's house style, not summarisation. |

*How to read this table: every bare score (0.3461, 0.3460, …) is `coverage` on the 200 CNN
articles — 0 to 1, higher is better (§2 defines it); gaps such as "0.0078" are in the same
units. **$/month** is what the provider billed for the 200-article run, scaled to 1M
articles a month (`deepseek_m`: $0.0381 ÷ 200 × 1,000,000 ≈ $191). Times are mean seconds
per article on the machine named; the hosted arms were timed from the Mac, through a local
proxy.*

*Cross-cutting context for all six experiments:
[`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).*

### What this experiment specifically found


**Two hundred articles separate a top group and a price verdict, and still cannot rank 24
models.** Those are different questions, and conflating them is the easiest way to misread
this report in either direction.

**On deployment:** `bart_l` (1.6 GB, MIT, CPU) wins outright, and the best open-weight LLM
that matches it — DeepSeek-V4.1-Flash — is **510 GB**, a cluster model. This is the one
experiment where capping your hardware costs quality: the best arm that fits 128 GB is
Llama-3.3-70B at int8, **0.3382**, giving up **0.0078**. It is also the one where the free
model is *slower* than renting (11.0 s vs 1.6 s per item), because generation on a CPU is
genuinely expensive. Distillation narrows that without a measurable cost. Timed on one
machine (`data/runs-linux/`), `bart_l` takes **6.3 s**, `bart_m` (1.2 GB, 0.3367) **4.1 s**
and `bart_s` (460 MB, 0.3276) **3.4 s**, neither separated from `bart_l` under Holm.

> **`bart_s` ran at fp16.** Its checkpoint is stored at half precision, and until the
> 2026-10-14 instrument fix the adapters did not apply a config's `precision`, so every
> committed `bart_s` figure here is an fp16 measurement under an fp32 label. Re-measured
> at fp32 (`harness/data/runs-fp32/`): **0.3274** on CNN and **0.4048** on DailyMail,
> identical scores on 199 and 187 of 200 items, and no verdict in this report moves. The
> fp16 runs stay the record.

**The expensive arms do not earn their price, and this is now the firmest result here.**
`deepseek_m` at **$0.0381** per 200 articles beats `anthropic_l` at **$1.9652** — 52×
dearer — by +0.0306 coverage, p = 0.0000, and it holds on the 180 out-of-sample articles
and on the literature-standard metric too. At n=20 that same comparison came back
"not separated"; the question was never unanswerable, twenty articles just could not
answer it.

| pre-registered pair | all 200 articles · Δ coverage, p | 180 held-out articles · Δ coverage, p |
|---|---|---|
| `deepseek_m` > `anthropic_l` (52× dearer) | +0.0306, p=0.0000 | +0.0308, p=0.0000 |
| `deepseek_m` > `anthropic_m` (19.6×) | +0.0224, p=0.0006 | +0.0224, p=0.0010 |
| `deepseek_m` > `openai_l` (11.4×) | +0.0193, p=0.0032 | +0.0171, p=0.0153 |
| `deepseek_s` > `qwen_m` (control) | +0.0255, p=0.0000 | +0.0208, p=0.0003 |

Δ is the first arm's `coverage` minus the second's (mean over articles; positive = the
cheaper arm is ahead). p is the uncorrected two-sided sign-flip permutation p (20,000
permutations); **p=0.0000 means p < 0.0001** — no permutation came close. The 180 held-out
articles are the ones the n=20 run never saw.

All four survive a Holm step-down on `coverage`, in both cuts. **$1.9652 buys 15th place among the 24 hosted arms;
$0.0381 buys 1st.**

**Sixteen of the 24 hosted arms are off the table entirely**, with no statistics required:
each is beaten by some other hosted arm on quality *and* billed cost *and* speed at once.
Eight remain on the frontier (§3.4; this said seventeen and seven, on the price-table cost
axis, until the bill replaced it). That is the most directly actionable output here.

**The XSum control settles what `bart_l` is good at.** `bart_l_xsum` is the same
BART-large architecture fine-tuned on XSum, whose references are single-sentence summaries
of BBC articles. Scored against CNN/DailyMail's references it finishes **last of 29 at
0.2071** — separated from all 28 other arms, below even LEAD-3's copy-the-first-three-
sentences (0.2718). Its outputs are 21 words against a 35-word reference, and its grounding
falls from `bart_l`'s 0.884 into the LLM range (0.422). **`bart_l`'s tie with the frontier is
a tie in CNN/DailyMail's house style, learned from its training split** — which the
report's caveat always said, and which is now measured rather than argued. (Its decode
length differs too — XSum's 62/11 tokens against 142/56 — so this control does not
separate *style* from *length*; a sixth arm would.)

**Resolution improved tenfold, and it was not enough to rank.** Pairs separated on
`coverage` went from **1 of 276** at n=20 to **34 of 276** at n=200 (25 on the held-out
180). The critical difference fell from 8.13 rank positions to 2.57. A leaderboard
printing a smooth 1-to-24 ordering is still asserting hundreds of comparisons it cannot
support.

*Both figures are over the **24 hosted arms** this section was computed on. The field
is now 29 — `bart_l` and `lead3` were added later, the three other BARTs on 2026-09-30 —
and over all 29 the critical difference is **3.18** with **80 of 406** pairs separating
(71 of 406 on the held-out 180). At k=26 it was 2.81 and 54 of 325; before that the CD
could not be given at all, because the studentised-range table stopped at 25 — it is now
computed rather than transcribed. The 2.57 figures above remain those of the original
24, reproducible with the command in §2.*

**The n=20 ranking largely did not survive.** Spearman between the two orderings of the
same 24 arms is **+0.667**. `qwen_s` fell 15 places, `llama_s` rose 12, `anthropic_m` fell
8. Only `deepseek_m` held its position. Any arm selected on 20 articles was selected
substantially by luck.

**And ten times the data does not stabilise a ladder.** Two *independent* 100-article
evals of these arms agree at only ρ = 0.79 and crown the same winner 1% of the time; at
20 articles it is ρ = 0.44 and 11% (29 arms; at 26 arms it was 0.80/1% and 0.42/14%). What is stable is membership, not order —
`deepseek_m` has P(top 5) = 1.00, `llama_l` 0.95, `llama_m` 0.90, and everything from 13th
down has P(top 5) = 0.00.

**Which article you drew matters ~68× more than which model summarised it.** 67.8% of the
variance in the primary facet is between articles, 1.0% between arms. Without pairing, the
model signal is buried.

**Beware the metric that separates most.** Ranked by pairs distinguished —
`summary_words` 208, `grounding` 172, `concision` 146, `rouge1` 97, `rougeLsum` 95,
`coverage` 34 — the order is almost exactly how much each measure depends on output
length. The most "sensitive" metric available is a word count. An eval that picks its
headline facet by which one separates cleanest will pick a length measure and call it
quality. This replicated exactly at ten times the sample size.

**A model-authored reference ("silver") is biased, not merely noisy.** Measured at n=20
and not re-measured here: silver rankings agree with gold at ρ = 0.33 against a retest
ceiling of 0.92, and **every silver author promotes models of its own family** — +7.4 rank
positions, 22 of 24 authors, p < 0.001.

**Temperature 0 is not deterministic** — 9.8% of outputs byte-identical across three
repeats, 12 of 24 arms with none. That figure is from the n=20 run at r=3. This run is
r=1 by design (with articles available, repeats are the wrong place to spend the same
budget), so it does not re-measure it.

**Nine findings in this report's own history were retracted**, two caused by bugs in this
harness's own scorer, and two more by the n=20 sample itself. §6 records them, because
the retraction rate measures how much of a first-pass eval is instrument rather than
signal.

## 1. What was measured

One task: *summarise a news article in 2–3 short sentences, in the terse style of a news
wire summary.* One prompt, 119 bytes, stored once in `prompt.txt`, its sha256 recorded in
every run's fingerprint. Not prompt optimisation — a per-model prompt would make the
comparison meaningless.

**Corpus.** `abisee/cnn_dailymail` (config 1.0.0; the same articles as 3.0.0, which the
literature uses), Apache-2.0 per its dataset card, the **first** 200 articles of the
11,490-article test split, mean 555 words. Because the split puts CNN's articles first, that
is **all CNN** (196 with CNN's dateline, 4 partner pieces CNN republished) — not a sample of
the benchmark, a sample of its
CNN portion, which is 9% of the split. Read every figure below with that scope; §3.7 measures the other outlet. References are the `highlights` written by the journalists who
filed each article — genuinely human-authored, mean 34.7 words. The corpus is never
committed; the repo ships a download recipe (`fetch.py`, stdlib only). `fetch.py` pages
from offset 0, so the earlier 20-article slice is a **subset** of these 200 — verified, 20
of 20 — which is why every result is also given on the 180 that are new.

**Held constant.** Dataset, prompt file, temperature 0, `max_tokens` 1200,
`reasoning: {enabled: false}`. Each arm's config differs from its n=20 predecessor in
exactly two lines, `config_id` and `dataset_id`, verified by diff. Every run records
`reasoning_tokens` from the provider's own accounting: **0 on all 4,800 calls**.

**One repeat per arm, not three.** With articles available, repeats are the wrong place to
spend the same budget — at fixed cost, n=60/r=1 gave sd(delta) 0.0090 against n=20/r=3 at
0.0133. The consequence is stated rather than hidden: this run measures no within-arm
variance, and the determinism figures in §3.3 come from the earlier r=3 sweep.

**Provenance caveats.** All 24 runs record `harness.dirty: true`. The cause is now known:
`_fingerprint.py` derives that flag from `git status --porcelain`, which counts UNTRACKED
files, and a sweep's own configs are untracked at the moment it starts. The fix is
procedural — commit configs before launching — and it was applied for the last 16 arms but
not the first 8, which therefore sit on an earlier commit. The measurement is unaffected:
the fingerprint stores content, not pointers (`arm.params` inline, `items_sha256`,
`adapter.sha256`, `prompt_sha256`, the resolved upstream model id).

**Reasoning off, verified not assumed.** Where a vendor's endpoint makes reasoning
mandatory, that model is excluded and the nearest same-family model that permits
reasoning-off is used instead (`claude-opus-5` not 5.5; `glm-4.6` not 5.3-prime). Every
run records `reasoning_tokens` from the provider's own accounting: **0 on all 4,800 calls.**

**Arms.** 8 families × 3 **price tiers**. Price, not size: every family mixes model
generations within its tier ladder (qwen's "large" is the *oldest* of its three), so this
experiment cannot attribute any difference between tiers to model size, and does not.

---

## 2. How quality was measured, and what each measure is biased toward

This is the part that decided the results, twice.

**ROUGE F1 against a single reference is a length ranking in a quality costume.** Across
these 24 arms in the n=20 run, ρ(output words, precision) = **−0.73** and ρ(words, recall)
= **+0.81**; at n=200 the precision correlation is stronger still, **−0.84** (the
`concision` row of the table below).
Choosing recall over F1 does not remove the bias — it flips its sign. Any single-number
quality claim on this task is substantially a claim about output length.

So quality is carried by two facets chosen to pull in opposite directions:

All correlations below are **across the 24 arm means**, not across individual outputs —
the same basis as the n=20 version of this table, so the two are comparable. (Pooled over
all 4,800 outputs the same relationships are much weaker, because the article effect
dominates any single row; that is a different quantity and is not what this table reports.)
ρ is Spearman's rank correlation between an arm's mean summary length in words and its
mean score on the facet: 0 means the facet ignores length, ±1 means it is a length ranking.

| facet | what it is | length bias: ρ(output words, facet), n=200 | same ρ in the earlier n=20 run |
|---|---|---|---|
| **`coverage`** | rougeLsum **recall**, output clipped to that item's reference length | ρ(words) = **+0.07** | +0.28 |
| **`concision`** | rougeLsum **precision**, whole output | ρ(words) = **−0.84** | −0.73 |
| `rougeLsum` | sentence-level LCS F1, the CNN/DM convention | ρ(words) = **−0.31** | −0.30 |
| `rouge1` | unigram F1 | ρ(words) = **−0.35** | −0.21 |
| `grounding` | share of summary bigrams present in the article | ρ(words) = **+0.12** | +0.25 |

ρ(coverage, concision) = **+0.36** — related, not independent, and not opposed. Both are
kept because which one you want is a product decision the eval must not make for you.

**`coverage` came out much closer to length-neutral at n=200 than at n=20** — |ρ(words)|
0.07 against `rougeLsum`'s 0.31 — where at n=20 the two were indistinguishable at 0.28 and
0.30, and this report said so. That earlier reading was not wrong about the data it had; 24
points is a thin basis for a correlation, and the honest conclusion is that the n=20 figure
could not support the claim either way.

The clip still only binds *above* the reference length: **577 of 4,800 outputs (12.0%) are
shorter than their reference and are never clipped at all**. `coverage` is the primary
facet because it asks the interpretable question ("did the summary carry the story"), not
because it is unbiased.

**`grounding` cannot tell a good paraphrase from a fabrication.** High means extractive,
low means abstractive; which of those is a hallucination it has no way to know. It is also
not length-neutral. Read beside ROUGE, never instead of it. It is ~20 lines of our own
code and is not comparable to any published number.

**Format compliance is computed over every output, not sampled.** Six flags:
`fmt_narration`, `fmt_label`, `fmt_markdown`, `fmt_bullets`, `fmt_paragraphs`,
`fmt_overlong`. **262 of 4,800 outputs (5.5%)** trip at least one — the same rate as at n=20 (5.3%). This exists because five
outputs were once read by hand and all 1440 declared clean.

**Speed is machine-bound and not a model property.** The latency column mixes this
machine, a local proxy, and the upstream provider, and it is a **mean**, so a few slow
calls dominate it. Two values are mostly tail: `mistral_l`'s 11045 ms comes from 36 of its
200 calls taking over 30 s (its median is 2272 ms), and `qwen_s`'s 25038 ms from 43 calls
over 30 s (median 7855 ms). (This sentence used to quote 16100 ms for `mistral_l` and
blame retry backoff; the committed run's mean is 11045 ms, and the harness times each
attempt that succeeds, so its own retry backoff is not in it.)
The local arms add a second machine: `bart_l` and `lead3` ran on a 12-core Intel Mac, the
other three on a 4-core Linux container, which ran `bart_l` itself 1.7× faster. All five
were re-timed on the Linux container alone, one at a time, and that is the table to compare
local arms on (below, and `data/runs-linux/README.md`).

---

## 3. Results

All 24 hosted arms, sorted by `coverage` (best first). Every score is 0 to 1 and higher is
better: `coverage` is the primary facet, `concision`, `rougeLsum` and `rouge1` are defined
in §2. `words / summary` is the mean output length (the references average 35). Cost is
what the provider billed for the whole 200-article pass. Latency is the mean per article,
timed from the Mac through a local proxy. `format flags / summary` is the mean number of
the six format flags (§2) an output trips, so 0 is clean and 0.93 means `mistral_l`
averages almost one flag per summary. The last column is the arm's rank among these 24 in
the earlier 20-article run, then in this one. **Bold** marks each column's extreme: the
best score, the fewest words and the fastest time — but in the cost and flags columns the
*worst* (dearest, most flagged) — and, in the rank column, the three moves of 8 or more
places named in the text.

| arm | coverage | concision | rougeLsum | rouge1 | words / summary | billed $/200 articles | ms / article (mean) | format flags / summary | rank: n=20 → n=200 |
|---|---|---|---|---|---|---|---|---|---|
| deepseek_m | **0.3460** | 0.2539 | 0.3188 | 0.3612 | 57 | $0.0381 | 1595 | 0.01 | 1 → 1 |
| llama_l | 0.3387 | 0.2714 | **0.3221** | **0.3636** | 49 | $0.0389 | 3473 | 0.00 | 3 → 2 |
| llama_m | 0.3382 | 0.2616 | 0.3098 | 0.3477 | 49 | $0.0330 | 4045 | 0.01 | 5 → 3 |
| llama_s | 0.3333 | 0.2475 | 0.3081 | 0.3526 | 56 | $0.0222 | 2388 | 0.01 | **16 → 4** |
| deepseek_l | 0.3325 | 0.2595 | 0.3116 | 0.3547 | 50 | $0.1389 | 2665 | 0.00 | 10 → 5 |
| glm_m | 0.3320 | 0.2566 | 0.3080 | 0.3517 | 50 | $0.0995 | 3230 | 0.01 | 13 → 6 |
| deepseek_s | 0.3285 | 0.2628 | 0.3081 | 0.3504 | 48 | $0.0137 | 2753 | 0.01 | 2 → 7 |
| openai_m | 0.3268 | 0.2787 | 0.3122 | 0.3599 | 42 | $1.0717 | 1745 | 0.00 | 11 → 8 |
| openai_l | 0.3268 | **0.2800** | 0.3151 | 0.3620 | 42 | $0.4362 | 1775 | 0.01 | 12 → 9 |
| mistral_s | 0.3255 | 0.2346 | 0.2895 | 0.3285 | 54 | $0.0179 | 2820 | 0.18 | 6 → 10 |
| anthropic_s | 0.3238 | 0.2084 | 0.2815 | 0.3259 | 71 | $0.2611 | 2025 | 0.08 | 8 → 11 |
| anthropic_m | 0.3236 | 0.2207 | 0.2903 | 0.3347 | 64 | $0.7478 | 3034 | 0.03 | **4 → 12** |
| gemma_l | 0.3204 | 0.2739 | 0.3086 | 0.3511 | 42 | $0.0237 | 2591 | 0.00 | 17 → 13 |
| openai_s | 0.3171 | 0.2508 | 0.2977 | 0.3506 | 48 | $0.1672 | **1277** | 0.01 | 18 → 14 |
| anthropic_l | 0.3155 | 0.2092 | 0.2878 | 0.3289 | 75 | **$1.9652** | 3402 | 0.23 | 9 → 15 |
| glm_s | 0.3139 | **0.2800** | 0.3012 | 0.3489 | **39** | $0.0304 | 1610 | 0.00 | 21 → 16 |
| gemma_m | 0.3136 | 0.2661 | 0.3016 | 0.3442 | 44 | $0.0154 | 1873 | 0.00 | 22 → 17 |
| glm_l | 0.3124 | 0.2456 | 0.2939 | 0.3334 | 65 | $0.1532 | 5689 | 0.38 | 14 → 18 |
| gemma_s | 0.3120 | 0.2328 | 0.2835 | 0.3215 | 53 | $0.0200 | 6956 | 0.01 | 20 → 19 |
| qwen_l | 0.3108 | 0.2309 | 0.2803 | 0.3309 | 55 | $0.1689 | 2945 | 0.01 | 15 → 20 |
| mistral_l | 0.3080 | 0.2356 | 0.2798 | 0.3188 | 48 | $0.0973 | 11045 | **0.93** | 24 → 21 |
| qwen_s | 0.3068 | 0.2600 | 0.2874 | 0.3360 | 43 | $0.0270 | 25038 | 0.00 | **7 → 22** |
| mistral_m | 0.3043 | 0.2507 | 0.2806 | 0.3197 | 43 | $0.0871 | 2654 | 0.01 | 19 → 23 |
| qwen_m | 0.3030 | 0.2206 | 0.2737 | 0.3164 | 57 | $0.0661 | 1534 | 0.00 | 23 → 24 |

Spearman between the n=20 and n=200 orderings: **+0.667**.

**The five local arms**, all $0 and run on CPU. `bart_l` and `lead3` since 2026-09-26; the
other three on 2026-09-30, on Linux, because their checkpoints are pickles that need torch
≥ 2.6. Same columns as above (scores 0 to 1, higher is better), plus `grounding` (§2:
share of summary bigrams found in the article, 1.000 = pure copying, so higher is not
simply better). **Bold** = best of all 29 arms on `coverage` and on `concision`; no local
arm leads the field on `rougeLsum` or `rouge1`.

| arm | rank of 29 (by coverage) | coverage | concision | rougeLsum | rouge1 | grounding | words / summary | ms / article, recorded run (mean; machine) | ms / article, Linux re-time (median) |
|---|---|---|---|---|---|---|---|---|---|
| bart_l | 1 | **0.3461** | 0.2608 | 0.3161 | 0.3477 | 0.884 | 51 | 11010 (Mac) | 6257 |
| bart_m | 5 | 0.3367 | 0.2578 | 0.3153 | 0.3457 | 0.853 | 55 | 5062 (Linux) | 4108 |
| bart_s | 10 | 0.3276 | 0.2599 | 0.3111 | 0.3418 | 0.877 | 52 | 4484 † (Linux) | 3387 |
| lead3 | 28 | 0.2718 | 0.2145 | 0.2701 | 0.3020 | 1.000 | 62 | 0 (Mac) | 0 |
| bart_l_xsum | 29 | 0.2071 | **0.3120** | 0.2458 | 0.2836 | 0.422 | 21 | 4621 (Linux) | 3934 |

*The recorded-run column is the committed run's mean, on the machine it ran on (Mac = the
12-core Intel Mac, Linux = the 4-core Linux container). The re-time column is the median
of a re-run of all five on the Linux container, idle and one at a time
(`data/runs-linux/`). `lead3` reads 0 because it runs no model: it copies the first three
sentences, in about 0.1 ms. The median is used because a local run's first one to three items
pay a one-off initialisation cost that the warm-up does not absorb. † The recorded
`bart_s` mean is inflated by analysis work I ran on the same CPU during the run; its own
median was 3,683 ms. On one machine `bart_m` takes 0.66× `bart_l`'s time and `bart_s`
0.54×.*

**The winner depends on the metric, and the standard ones say so.** Scored with standard
ROUGE F1 (`rouge_score`, stemmed — what the literature reports), the 29 arms order
differently from `coverage`. Six of the 29 arms are shown — the two hosted leaders and the
four local arms that score above the XSum control — in ROUGE-1 order. Note the scale: ROUGE
is printed ×100, as the literature prints it, while `coverage` stays on its 0–1 scale.
Ranks are out of all 29; **bold** = 1st of 29 in that column.

| arm | coverage (rank of 29) | ROUGE-1 F1 ×100 (rank of 29) | ROUGE-2 F1 ×100 (rank of 29) |
|---|---|---|---|
| `llama_l` | 0.3387 (3) | **36.36 (1)** | 13.20 (4) |
| `deepseek_m` | 0.3460 (2) | 36.12 (3) | 12.99 (5) |
| `bart_l` | **0.3461 (1)** | 34.77 (12) | 14.24 (3) |
| `bart_m` | 0.3367 (5) | 34.57 (14) | **14.41 (1)** |
| `bart_s` | 0.3276 (10) | 34.18 (16) | 14.26 (2) |
| `lead3` | 0.2718 (28) | 30.20 (28) | 12.14 (7) |

On bigrams the three CNN-trained BARTs take the top three places; on unigrams the LLMs
lead and `bart_l` is 12th. "`bart_l` wins outright" is true of `coverage` and of ROUGE-2,
not of ROUGE-1 — consistent with what BART learned being CNN's *phrasing*, which bigrams
reward and unigrams barely see. None of these absolute figures is comparable to published
ROUGE, which is computed on the full test set (§5).

`bart_m` is distilbart-cnn-12-6 (12 encoder / 6 decoder layers, 1.2 GB) and `bart_s`
distilbart-cnn-6-6 (460 MB, stored and **run** at fp16, although its config declares
`precision: fp32` — the adapter records that field without applying it) — both distilled from `bart_l`, so they sit below it as they
should, in the order their size predicts. Their grounding stays in `bart_l`'s range
(0.85–0.88) against 0.25–0.43 for the hosted field. `bart_l_xsum`'s concision is the best
in the table only because concision rewards brevity and XSum writes one sentence.

No local arm here differed between runs. On the same machine all three new arms re-ran
**200 of 200 outputs byte-identical** (`bart_s` three times, counting the resumed run in
`data/runs-repeats/`), and across machines (Mac → Linux) so did `bart_l` and `lead3`
(`data/runs-linux/README.md`). Hosted arms at temperature 0 do not: 47 of 480 article
outputs were identical across three repeats in the earlier sweep here (§3.3), and 13–78 of
200 across two runs of five SciFact arms (`REPORT_RETRIEVAL.md`).

### 3.1 Is the ordering real?

Friedman-style permutation test on within-item ranks, with a Nemenyi critical difference
applied simultaneously to all 276 pairs of the 24 hosted arms. Each arm gets a mean rank
from its within-article ranks over the 200 articles; two arms are separated when their mean
ranks differ by more than the critical difference. The spread column is the distance
between the best and worst arm's mean rank — a metric whose spread barely exceeds the
critical difference can separate few pairs.

| metric | Friedman p | Nemenyi critical difference (mean-rank positions) | spread of mean ranks (best to worst) | pairs separated (of 276) |
|---|---|---|---|---|
| `coverage` | 0.0002 | 2.57 | 4.46 | **34** |
| `rougeLsum` | 0.0002 | 2.57 | 5.69 | 95 |
| `rouge1` | 0.0002 | 2.57 | 5.63 | 97 |
| `concision` | 0.0002 | 2.57 | 9.66 | 146 |
| `grounding` | 0.0002 | 2.58 | 13.99 | 172 |
| `summary_words` | 0.0002 | 2.57 | 18.23 | 208 |

*p = 0.0002 is the floor of the permutation test (5,000 permutations, none as extreme as
the data), not a coincidence of six metrics: every one rejects "all arms are alike". **Bold** marks the primary facet.*

On the **180 held-out** articles, `coverage` gives p = 0.0002, CD 2.71, span 4.26, **25 of
276**. At n=20 the same metric gave 1 of 276 against a CD of 8.13 — wider than the entire
table's span, which is why nothing separated.

Membership is far better determined than order. From 2,000 item-resamples:

```
  arm            avg rank   P(1st)   P(top 5)   P(bot 5)
  deepseek_m        10.00     0.76       1.00       0.00
  llama_l           10.83     0.10       0.95       0.00
  llama_m           11.07     0.11       0.90       0.00
  llama_s           11.56     0.02       0.59       0.00
  deepseek_l        11.03     0.01       0.53       0.00
  glm_m             11.24     0.01       0.47       0.00
  …
  qwen_m            14.36     0.00       0.00       0.96
  mistral_m         14.47     0.00       0.00       0.88
```

`deepseek_m` is in the top five in every resample. Which of the six *is* first is not a
claim this data supports.

**Over all 29 arms** (k=29: CD 3.18, 80 of 406 pairs): `bart_l` P(1st) 0.45 and
`deepseek_m` 0.41 — the same coin flip — with `bart_m` P(top 5) 0.57 (`scripts/leaderboard.py --dataset-id cnn_dailymail_200 --sort coverage`, rank bootstrap). Family tests, Holm
over the 28 others on `coverage` — each row tests one local arm against all 28 others at
once:

| arm | separated from (Holm, of 28) | ahead on the point estimate (of 28) | Δ coverage vs `bart_l`, p |
|---|---|---|---|
| `bart_l` | 13 of 28 (was 12 of 25) | 28 of 28 | — |
| `bart_m` | 4 of 28 | 24 of 28 | −0.0095, p = 0.17 |
| `bart_s` | 2 of 28 — only `lead3` and `bart_l_xsum` | 19 of 28 | −0.0186, p = 0.017 (threshold 0.0020) |
| `bart_l_xsum` | **28 of 28, all from below** | 0 of 28 | −0.1390, p = 0.0000 |

*The "against `bart_l`" column is from each arm's own family. The same pair tested from
`bart_l`'s side gives p = 0.16 for `bart_m` and 0.017 for `bart_s`: the sign-flip test is
Monte Carlo (20,000 permutations, fixed seed), so the two directions differ in the second
decimal, and the Holm threshold differs because each family is sorted by its own
p-values. Deltas here are per-item means against `bart_l`; §0 of the synthesis gives
them against the best paid arm, `deepseek_m`, which is why its figures differ by 0.0001.*

### 3.1b Decision questions, asked one at a time

§3.1 asks "which of all 276 pairs differ?" and pays the multiplicity price for all 276.
That is the right price for that question and the wrong question for a decision. These
four pairs were **named before the last arm finished running**, and are Holm-corrected as
a family of four. In each cell: Δ (first arm minus second, mean over articles), then the
number of articles on which the first arm scored strictly higher (ties count for neither),
then the uncorrected sign-flip p (20,000 permutations; p=0.0000 means p < 0.0001). **Bold
p** = separated after Holm correction across the four questions. A row with "(same pair)"
asks the question above it on a second metric.

| question | metric | all 200 articles | 180 held-out articles |
|---|---|---|---|
| `deepseek_m` vs `anthropic_l` — is 52× the price worth it? | coverage | +0.0306, 114/200, **p=0.0000** | +0.0308, 102/180, **p=0.0000** |
| (same pair) | rougeLsum | +0.0310, 139/200, **p=0.0000** | +0.0331, 127/180, **p=0.0000** |
| `deepseek_m` vs `anthropic_m` — 19.6× | coverage | +0.0224, 112/200, **p=0.0006** | +0.0224, 104/180, **p=0.0010** |
| `deepseek_m` vs `openai_l` — 11.4× | coverage | +0.0193, 96/200, **p=0.0032** | +0.0171, 85/180, **p=0.0153** |
| (same pair) | rougeLsum | +0.0037, 107/200, p=0.47 | +0.0038, 97/180, p=0.47 |
| `deepseek_s` vs `qwen_m` — the control | coverage | +0.0255, 107/200, **p=0.0000** | +0.0208, 93/180, **p=0.0003** |

All four separate on `coverage` in both cuts. On `rougeLsum` three of four do; the
`openai_l` comparison is the one the facets disagree about, and it is disclosed rather
than dropped.

Unlike the six pairs in the n=20 version of this section, these were fixed in advance, so
no fishing correction is owed beyond the family Holm.

### 3.2 Variance decomposition (`coverage`)

| source | share |
|---|---|
| between articles | **67.8%** |
| between arms | **1.0%** |
| residual | 31.2% |

Which article you drew moves the number ~68× more than which model wrote the summary.
(At n=20 this read 73.5 / 2.6 / 23.9; the shape is unchanged, and the arm share shrinking
is expected when the article pool widens.)

### 3.3 Determinism at temperature 0

**Not re-measured here.** This run is r=1. From the earlier r=3 sweep: 47 of 480 (9.8%)
article-outputs byte-identical across three repeats, and 12 of 24 arms with none at all.
Nothing in this run contradicts that; nothing in it confirms it either.

**The local contrast was measured.** Every local arm was re-run (`data/runs-linux/`):
`bart_m`, `bart_s` and `bart_l_xsum` on the same Linux machine, `bart_l` and `lead3` on a
different one from their recorded Mac runs. **All five reproduced 200 of 200 outputs
byte-identically** — beam search on a CPU, at fp32 except `bart_s`, which runs at its stored
fp16. Run-to-run variance for these local arms,
on these two CPUs, is zero; for a hosted one it is not, and no test in this report sees it
(every separation test is over items within one run). GPUs and other torch builds were not
tried.

### 3.4 Pareto frontier (coverage / cost / latency)

**8 of 24 arms**: `deepseek_m`, `deepseek_s`, `gemma_m`, `glm_s`, `llama_m`, `llama_s`,
`openai_s`, `qwen_m`. The other **16 are beaten on quality *and* cost *and* speed** by
some other arm — off the table at any budget, with no statistics required.

*This listed seven arms, on the price-table cost axis, until 2026-09-30. On the bill
`gemma_m` and `deepseek_s` join the frontier and `mistral_s` leaves it — the ranking by
cost changes because the price table was wrong per arm by 0.67× to 3.76×, not by a
constant.*

**The five local arms are left out on purpose.** At $0 an arm can only be dominated by
another free arm, so every local arm that is not beaten by a *faster, better* local arm is
on the frontier by construction, not by merit. Over all 29 the frontier adds `bart_l`,
`bart_m`, `bart_s` and `lead3` — each fastest-for-its-quality among the free — and still
excludes `bart_l_xsum`, which `bart_s` beats on quality and speed.

At n=20 the frontier held 10 arms. The three that dropped off did so because more data
moved their quality estimate, not because their cost or latency changed — a reminder that
even the statistics-free part of this report depends on the sample.

### 3.5 Can a model-authored reference be trusted?

Every arm used in turn as the silver author, its own row excluded, ranking the other 23:

| quantity | value |
|---|---|
| retest ceiling (same arms, same gold, two run sets) | **ρ = +0.924** |
| silver agreement with gold | **−0.013 … +0.697**, mean **+0.326** |
| best authors | `llama_s` (0.697), `deepseek_m`, `llama_m` |
| worst author | `mistral_m` (−0.013) |
| sibling lift (own family promoted) | **+7.4** rank positions, positive for **22 of 24** |
| ρ(author agreement, sibling lift) | **−0.70** |

The lift is worst where the author is worst: authors above ρ 0.5 average +4.2 positions,
those below ρ 0.3 average +9.4.

---

### 3.6 How much data does a ranking need?

Measured from these runs at no extra cost: draw two **disjoint** subsets of *n* articles,
rank the arms independently in each, and correlate the two orderings. Neither half is
treated as truth.

**Re-measured 2026-09-30 over the 29-arm field.** The table first published here described
24 arms, then 26 once `bart_l` and `lead3` arrived; the three BARTs added on 2026-09-30
move it again, a little. The 26-arm figures are kept beside the new ones.

| articles per half | ρ(half A, half B), mean over draws | ρ, 5th percentile | P(both halves crown the same arm) | median rank move (positions) | arms sharing 1st place | *earlier 26-arm field · ρ / P(same)* |
|---|---|---|---|---|---|---|
| 10 | 0.336 | 0.033 | 0.08 | 4.84 | 1.0 | *0.278 / 0.12* |
| 20 | **0.443** | 0.191 | **0.11** | 3.91 | 1.0 | *0.416 / 0.14* |
| 50 | 0.640 | 0.452 | 0.12 | 2.67 | 1.0 | *0.643 / 0.17* |
| 100 | **0.793** | 0.689 | **0.01** | 1.63 | 1.0 | *0.799 / 0.01* |

*Each row averages 400 random draws of two disjoint halves. ρ is the Spearman correlation
between the two halves' orderings of the 29 arms (1 = they agree exactly). "Median rank
move" is how many positions an arm typically sits from its
full-200 rank in a half of that size. "Arms sharing 1st place" is the average number of
arms tied for the best score in a half; 1.0 means no ties. Bold marks the 20-article size
of the original experiment and the 100-article size quoted in the summary; italics, the
superseded 26-arm figures.*

At 20 articles — the size of the original experiment — two independent evals of these arms
agree at ρ = 0.44. At 100 they still disagree at ρ = 0.79. The three new arms nudge ρ up
at small n (two of them sit at the extremes, which is easy to agree about) and leave the
winner question exactly where `bart_l` left it.

### P(same winner) went from 0.58 to 0.01, and that is a result rather than a regression

It is not the tie-correction fix: re-measured on identical data, the old and new statistics
agree to **0.0075 vs 0.0075** here, because `coverage` is continuous and never ties. It is
the arm set.

```
cnn_bart_l      0.346121   wins half A in 179 of 400 draws
cnn_deepseek_m  0.346039   wins half A in 178 of 400 draws
```

**Two arms separated by 0.00008 over 200 articles.** Adding `bart_l` gave the field a
co-leader indistinguishable from the previous one, so the two halves crown the same arm
essentially never — a coin flip between two arms that no quantity of this data separates.

The statistic is reporting exactly the right thing, and it happens to be the same finding
the ML arms produced from the other direction: BART's apparent lead at n=20 was 0.0737 and
at n=200 it is 0.00008. "P(both halves crown the same arm)" is near zero **because there is
no winner to crown**, not because the evaluation got noisier.

Note also that the "arms sharing 1st place" column of the table above is 1.0 at every size: these two arms are not *tied*, they
are 0.00008 apart, which a continuous metric resolves into a strict order that means
nothing. A tie count cannot catch that; only the separation tests in §3.1 can.

This is the most transferable result in the report: it is about evaluation rather than
about 24 models, and it does not go stale when the models change.

### 3.7 Does it hold outside CNN? The DailyMail slice

Every result above was measured on CNN's articles alone (§1). To test whether the
conclusions travel, `cnn_dailymail_dm200` draws **200 DailyMail articles at random** (seed
20261014) from the same test split — none carries a CNN or CNN-partner dateline — and the
five local arms re-ran on it with their parameters unchanged. All five runs are clean
(`build.dirty: false`, commit `a81669ca`) and committed as
`harness/data/runs/cnn_*_dm200_v1_*`.

`coverage` is on the same 0–1 scale as above (higher is better); ROUGE is printed ×100, as
in the ROUGE table in §3; words are the mean summary length. **Bold** = best on DailyMail
`coverage` — `bart_l` and `bart_m` tie to four decimals.

| arm | CNN · coverage | DailyMail · coverage | DailyMail · ROUGE-1 / ROUGE-2 F1 ×100 | DailyMail · words / summary |
|---|---|---|---|---|
| `bart_l` | 0.3461 | **0.4430** | 46.16 / 23.18 | 67 |
| `bart_m` | 0.3367 | **0.4430** | 46.95 / 24.09 | 76 |
| `bart_s` | 0.3276 | 0.4039 | 44.78 / 22.03 | 54 |
| `lead3` | 0.2718 | 0.3697 | 42.20 / 18.69 | 77 |
| `bart_l_xsum` | 0.2071 | 0.1522 | 24.72 / 7.04 | 20 |

Every arm scores higher on DailyMail except the XSum control — DailyMail's highlights are
longer (57 words against 35) and its leads more extractable. The question is whether the
*comparisons* hold, so the same family test was run on both slices over the same five
arms (Holm, `bart_l` against the other four, sign-flip, 20,000 permutations):

Each cell is `bart_l`'s `coverage` minus the other arm's (positive = `bart_l` ahead), then
the Holm verdict within that slice's family of four.

| `bart_l` vs | CNN · Δ coverage, Holm verdict | DailyMail · Δ coverage, Holm verdict |
|---|---|---|
| `bart_l_xsum` | +0.1390, separated | +0.2908, separated |
| `lead3` | +0.0743, separated | +0.0733, separated |
| `bart_s` | +0.0186, separated (p = 0.017) | +0.0391, separated |
| `bart_m` | +0.0095, not separated (p = 0.16) | +0.0000, not separated (p = 1.00) |

**Among the local arms, every verdict transfers.** The fine-tune beats LEAD-3 by the same
margin on both outlets (+0.074 and +0.073); the XSum control fails harder on DailyMail;
distilling to `bart_m` costs nothing measurable on either; `bart_s` gives up twice as much
on DailyMail as on CNN. *(The CNN column is a five-arm family, so its thresholds are looser
than §3.1's 28-arm family, where `bart_s` is not separated.)*

**What this does not test: the hosted arms.** Whether `bart_l` still ties `deepseek_m`,
whether 15 arms still tie at the top, whether the dearest arm still trails — every
comparison involving a paid model — is unmeasured outside CNN. Configs for the four
hosted arms in the CNN top six are committed beside the local ones
(`configs/arm_{deepseek_m,llama_l,llama_m,llama_s}_dm200.yaml`); they need an
OpenAI-compatible endpoint, which the environment that ran this slice did not have.

**And a calibration aside.** `bart_l` is the published `facebook/bart-large-cnn`, reported
at ROUGE-1 44.16 on the full test set. Weighting this repo's two slices by the split's
outlet mix (9.5% CNN, 90.5% DailyMail) estimates **45.1** — consistent, given a different
ROUGE implementation and 400 articles rather than 11,490. The instrument agrees with the
literature on the model as well as on LEAD-3.

## 4. Discussion

**The experiment's resolution is set by the corpus, not the models.** With 67.8% of
variance between articles and 1.0% between arms, the paired design is doing nearly all the
work. This is not a small-sample complaint that more data fixes at the margin — it is the
shape of the task. Ten times the articles moved `coverage` from 1 separated pair to 34, and
still left the top six mutually indistinguishable.

**The winning free model is a specialist in this corpus, and the evidence is now a
control rather than a caveat.** Three BARTs trained on CNN/DailyMail finish 1st, 5th and
10th of 29 in the order of their size; one BART trained on XSum finishes 29th, below the
LEAD-3 baseline. Same architecture, same decoding machinery, same $0. The variable is
which corpus's references the model learned to imitate — and single-reference ROUGE
against *this* corpus rewards imitating this corpus. That makes the production advice
sharper, not weaker: fine-tune on summaries that look like the ones you want, and a 1 GB
model on a CPU ties the frontier; fine-tune on anyone else's and it loses to copying the
first three sentences.

**Discriminating power is not informativeness.** Ranked by pairs separated:
`summary_words` (208) > `grounding` (172) > `concision` (146) > `rouge1` (97) >
`rougeLsum` (95) > `coverage` (34). That is almost exactly the order of how much each
measure depends on output length or extractiveness — and it is the same order as at n=20,
so it is a property of the metrics rather than of the sample. The most "sensitive" metric
available is a word count. An eval that picks its headline metric by which one separates
cleanest will pick a length measure and call it quality.

**Price behaves almost independently of quality, and now demonstrably so.** `anthropic_l`
at **$1.9652** ranks 15th; `deepseek_m` at **$0.0381** ranks 1st, and the gap is separated
at p = 0.0000 in both item cuts and on both ROUGE facets. At n=20 the same comparison was
"not separated" (p = 0.52) and the honest reading was *"if a model 52× cheaper cannot be
shown to be worse, the expensive one has not earned its price."* That reading was right,
and the stronger version is now available: it **is** shown to be better.

**The eliminations are the actionable output.** 16 of 24 arms are beaten on quality *and*
cost *and* speed simultaneously. No statistics are required for that, and it answers the
question a team actually has — not "which is best" but "which are not worth considering".

**A ladder needs more data than a decision, and possibly more than exists.** §3.6 measures
it: two independent 100-article evals of these arms still disagree at ρ = 0.79. The gap
between 1st and 3rd here is 0.0078 coverage; between 2nd and 3rd, 0.0005. Closing the
latter needs a sample in the six figures. The correct output is therefore a *set* — the
six arms with P(top 5) ≥ 0.47 — not a podium.

**Selection on a small sample is expensive in a way that does not announce itself.** The
n=20 ordering and the n=200 ordering of the same 24 arms correlate at 0.667. `qwen_s` was
7th and is 22nd; `llama_s` was 16th and is 4th. Anyone who had shortlisted the n=20 top
five would have carried two arms that belong in the bottom half and missed two that belong
at the top.

**No family's tier ladder predicts quality.** `deepseek` runs mid > large > small,
`llama` large > mid > small, `anthropic` mid > small > large, `mistral` small > large >
mid. Since each ladder mixes model generations with price steps, this experiment cannot
say whether that is size, generation, or noise.

**Silver's problem is direction, not magnitude.** (From n=20; not re-measured.) A noisy
proxy costs precision; a proxy that promotes the author's own family by 7 rank positions
produces a *wrong ranking that looks clean*. Excluding the author's own row does not remove
it, because the bias is stylistic affinity rather than self-preference — and the case
silver exists for is the one where there is no gold to detect it with.

**Format contamination is rare but concentrated.** By format flags per summary (mean):
`mistral_l` 0.93, `glm_l` 0.38, `anthropic_l` 0.23, `mistral_s` 0.18, `anthropic_s` 0.08 —
every other arm at or below 0.01. Three of the five are their vendor's large tier, so a
higher price tier does not buy cleaner output — worth checking before paying for one.


## 5. What this experiment cannot say

- **How well `coverage` tracks what a person prefers.** Measured since on SummEval, against
  expert judgement of 1,600 summaries, it agrees at τ 0.1011, below plain ROUGE-1 (0.1487)
  ([REPORT_SUMMEVAL](REPORT_SUMMEVAL.md) §3.3). The comparisons here are separations under
  `coverage`; a lead under it is weaker evidence of a better summary than its size suggests.
- **Which model is best.** 34 of 276 pairs separate on the primary facet, and none of them
  are inside the top six. The output is a set, not a winner.
- **Whether the ordering would hold on another 200 articles.** Measured, and it largely
  would not: two independent 100-article evals agree at rho = 0.79 (section 3.6).
- **Anything about model size.** The tier axis is price, and confounds generation.
- **Whether abstractive outputs are accurate.** No metric here detects fabrication;
  `grounding` measures extractiveness and cannot distinguish paraphrase from invention.
- **How the hosted models rank on anything but CNN's articles.** The DailyMail slice
  (§3.7) re-ran the five local arms only. Nor with reasoning enabled, on a different
  prompt, on longer inputs, or on any other corpus.
- **How fast the models are.** Latency is a property of this machine, this proxy and the
  upstream provider on the day.
- **Anything comparable to published ROUGE, on the committed slice.** Published figures
  are over the full test set, which is 91% DailyMail; this slice is all CNN, and CNN
  articles score ~11 ROUGE-1 lower. The scorer is not the gap: LEAD-3 over the full test
  set scores 39.94 here against 40.34 published, and `bart_l`'s outlet-weighted estimate
  is 45.1 against 44.16 (§3.7). `grounding`, `concision` and `coverage` are this repo's own
  and comparable to nothing published.
- **Whether `bart_l`'s lead is style or length.** The XSum control fails for two reasons
  at once — it was trained on BBC single-sentence summaries *and* it decodes at 62/11
  tokens against 142/56. An arm at CNN/DailyMail decode lengths would separate them; it
  was not run. (This bullet used to read "ML versus LLM: not built" — five local arms have
  since run, so the comparison exists; what it cannot yet say is *why* the specialist wins.)
- **Within-arm variance for the hosted arms.** This run is r=1; the determinism figures are
  from the earlier r=3 sweep and were not re-measured. For the five local arms it was: each
  re-run was 200 of 200 byte-identical (`data/runs-linux/`).

---

## 6. Corrections, and why they belong in the report

Nine findings were retracted during this work. They are listed because the retraction rate
*is* a result: it measures how much of a first-pass eval is instrument rather than signal.
The first six came from bugs, untested assumptions and reading samples. The seventh and
eighth came from the 20-article sample itself, and only the re-measurement at n=200
exposed them; the ninth was a claim about CI that a log line falsified.

| retracted claim | what was actually true | cause |
|---|---|---|
| "`llama_l` is the only separated arm" | nothing was separated by that method | band-walk depended on traversal direction |
| "nothing is distinguishable at n=20, at any number of arms" | up to 33 pairs separate | `rougeLsum` was silently plain `rougeL` |
| "the arm effect is substantially a length effect" | true for the *pairwise* signal, false for the global one | over-correction of the above |
| "tier measures size; anthropic is flat across sizes" | tier is price and confounds generation | assumed, never checked |
| "no arm emitted preamble or bullets" | 77 of 1440 outputs trip a format flag | read 5 outputs, generalised to 1440 |
| "Anthropic arms bill hidden reasoning tokens" | provider reports 0 on all 1440 calls | inferred from a token/word ratio |
| "`deepseek_m` vs `anthropic_l` is not separated" (p=0.52) | separated at p=0.0000, both cuts, both metrics | 20 articles could not resolve a real 0.031 gap |
| "10 of 24 arms are on the Pareto frontier" | **8 of 24** | three arms' quality estimates moved with more data, and the cost axis now uses the bill rather than the price table (7 of 24 under the old cost figures) |
| "CI stops baking a 990 MB model" (commit c7f47e4c) | it kept shipping, restored from cache | manifest drives the preload, not the artifact |

Two were caused by defects in this harness's own scorer, and two by trusting 20 articles.
**All of the first six were found by adversarial review, none by the person who produced
them**; the last three were found by re-measuring and by a log line added in the same
commit whose claim it falsified. Two further rounds of review
found stale numbers in the first published version of this example's README, and a bug that
would have crashed a fresh clone *after paying for its first API call*.

The practical lessons, all now enforced in code:

1. **If it can be computed over the whole corpus, it must not be reported from a sample.**
2. **Verifying a measurement must be cheap** — `make rescore` recomputes scores from stored
   outputs for $0, because when checking a metric cost $1.45 and 80 minutes, it went
   unchecked through two sweeps.
3. **A comparison method whose answer depends on traversal order is not a comparison.**
4. **Never delete measurements to tidy a table.** 18 arms of paid results were lost that
   way during this work; the fix is scoping (`--match`, `EVAL_RUNS_DIR`), not deletion.
5. **A power calculation fed a delta from the pilot inherits the pilot's error.** Journal
   entry 40 predicted `deepseek_m` vs `deepseek_s` needed n~2472, from a delta measured on
   20 articles. It separated at 200. The arithmetic was fine; the input was not.
6. **Report the claim and the check in the same commit.** The line that caught the cache
   claim above was added by the commit that made it.

---

## 7. Reproduction

```bash
cd examples/summarization-cnn-dailymail
uv sync
uv run fetch.py --n 200

cd ../../harness
cp .env.example .env                      # point at a proxy
# The dataset file is committed and frozen; materialize checks the fetched bytes against it.
make dataset-materialize DATASET_ID=cnn_dailymail_200
make sweep PYTHON=../examples/summarization-cnn-dailymail/.venv/bin/python \
     CONFIGS="../examples/summarization-cnn-dailymail/configs/arm_*_n200.yaml" REPEAT=1
make leaderboard DATASET_ID=cnn_dailymail_200

# the two questions the leaderboard cannot answer on its own
make holdout   DATASET_ID=cnn_dailymail_200 EXCLUDE=cnn_dailymail_20
make pair-test DATASET_ID=cnn_dailymail_200 A=cnn_deepseek_m_n200_v1 B=cnn_anthropic_l_n200_v1 FAMILY=4
python scripts/rank_stability.py --dataset-id cnn_dailymail_200

# the local arms (bart_m, bart_s, bart_l_xsum need torch >= 2.6: uv sync --extra local)
python scripts/family_test.py --dataset-id cnn_dailymail_200 --a cnn_bart_l_n200_v1 --against _n200_v1 --metric coverage
python scripts/family_test.py --dataset-id cnn_dailymail_200 --a cnn_bart_l_xsum_n200_v1 --against _n200_v1 --metric coverage
```

The three 2026-09-30 BART arms load `main`'s `pytorch_model.bin`; each checkpoint also has
a safetensors conversion PR on the Hub (distilbart-cnn-12-6 `refs/pr/29`, -6-6 `refs/pr/2`,
bart-large-xsum `refs/pr/9`). On torch 2.2.2 the `bart_m` and `bart_l_xsum` PRs reproduce the
recorded outputs on 20 of 20 items checked; the `bart_s` PR does not run, because it is
fp16 and torch 2.2.2 has no fp16 LayerNorm on CPU (`docs/evidence/conversion_pr_check.py`) — see
[`KNOWN_ISSUES.md`](internal/KNOWN_ISSUES.md).

No `rescore` step is needed here. It was, for the n=20 sweep: scores were written rounded
to 6 decimals, which cannot tell a genuine tie from a rounding artifact, and the tie
tolerance is load-bearing for `coverage` (13-23% of arm pairs tie exactly on an item,
depending on how short the reference is). Score precision is 10 decimals since journal
entry 31, and the leaderboard warns if it ever reads runs written at less.

Expect different absolute numbers. Providers update models behind stable names, and
`reasoning_tokens`, `providers_seen` and the resolved upstream model id are recorded per run
precisely so a future divergence can be attributed rather than guessed at.

---

## Correction — every cost figure here was an estimate, and the estimate was wrong

**Added 2026-09-29.** The `$` figures originally published in this report were computed
from `usd_per_mtok_in/out` in each arm's config: one price per model **alias**. An alias
is not a price. OpenRouter routes each request to one of several upstream providers — a
single run in this repo recorded Novita 262 times, Parasail 9, DeepInfra 6, Nebius 3 —
and they charge differently, so the effective price is a routing-dependent mixture no
config can state in advance.

The provider reports what it actually charged, per call, in `usage.cost`. That was in
every stored run all along and nothing read it. Measured across all four examples, the
price table was wrong **per arm by 0.67× to 3.76×, in both directions**.

**The error is not uniform, and that is what makes it matter.** Arms served by a single
provider — the Anthropic models, notably — match the table exactly. The cheap,
multi-routed models were undercounted. So the error systematically **understates the cheap
end of the field, and therefore inflates every price-ratio claim.** It also reorders arms
by cost: on `few_nerd_280`, `glm_s` is the 2nd-cheapest arm by the table and the 9th by
what was billed.

Every cost figure in this report is now corrected to what the provider billed. Rankings by *quality* are
untouched — cost was never an input to them.

**Fixed at cause:** all four adapters now record `usage.cost` when the provider supplies
it and fall back to the table only when it is silent. Runs made before that fix keep the
estimate in `cost_usd`; the billed figure is in `_meta.usage.cost` in each stored run, and
these corrections were computed from it.
