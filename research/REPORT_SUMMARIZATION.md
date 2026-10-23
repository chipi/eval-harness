# Evaluation report — 24 LLMs on news summarisation

**Dataset** `cnn_dailymail_200` · 200 articles — **all from CNN** (the first 200 test rows; the test split is 91% DailyMail) · human-written gold references
**Arms** 24 hosted models, 8 vendors, 3 price tiers each
**Protocol** test split, first 200 rows (all CNN) · metric `coverage` is ours; ROUGE-1/2/L F1 reported beside it · calibration: LEAD-3 on the full test set, ROUGE-1 39.94 ±0.22 vs 40.34 published (0.40 below, outside that interval) — [docs/PROTOCOL.md](../docs/PROTOCOL.md#summarisation--cnndailymail)
**Design** 1 pass per arm · 4,800 calls · **$5.74 billed** · hosted LLMs zero-shot, one identical prompt, temperature 0, reasoning off, **no upstream provider pinned** (§1)
**Date** 2026-09-26; three local BART arms added 2026-09-30 · **Harness** [`../harness`](../harness) · **Journal** [`NOTES.md`](internal/NOTES.md) entries 56, 59

## Executive summary

**On `coverage`: use `bart_l` if you can run a free 1.6 GB model on CPU and your text looks like CNN news; rent `deepseek_m` if you need speed; do not buy `anthropic_l`.** On `coverage` (this repo's overlap metric, 0 to 1), `bart_l` (BART-large-CNN, MIT) scores 0.3461 and the best hosted arm, `deepseek_m`, 0.3460: not separated (p = 0.99), so the extra spend bought no measured quality. `bart_l` costs $0 but takes 11.0 s per article on a 12-core Mac CPU; `deepseek_m` costs $191 per 1M articles at 1.6 s. `anthropic_l` costs $9,826 per 1M articles, 52× `deepseek_m`, and scores 0.0306 lower (p < 0.0001).

Three limits could change this. `coverage` agrees with expert judgement poorly: τ 0.1011 on SummEval, below plain ROUGE-1's 0.1487 ([REPORT_SUMMEVAL](REPORT_SUMMEVAL.md) §3.3), and on ROUGE-1 the LLMs lead (`bart_l` 12th of 29). Re-scored by SummEval-validated LLM judges, every hosted LLM ranks above every BART model and `anthropic_l` is first on the point estimate (§3.8); one reader's blind check of 20 pairs went the other way, not significantly, so nobody has yet shown which to believe and `coverage` stays the primary metric. And `bart_l`'s result is specific to CNN-style text: an XSum-trained BART scores last of 29 on `coverage`, and no hosted arm was run outside CNN. As run here: the first 200 CNN test articles, hosted LLMs zero-shot on one prompt, one run per arm (§5).

Cross-cutting context for all six experiments: [`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).

### Supporting facts

| the choice | what the data says |
|---|---|
| **Self-host · small ML** | **`bart_l` (BART-large-CNN, MIT, 1.6 GB, CPU): 0.3461, not separated from `deepseek_m` (0.3460; gap 0.0001, p = 0.99).** 11.0 s per item on the 12-core Mac, 6.3 s on a 4-core Linux box. Distilled `bart_m` (1.2 GB): 0.3367, 1.5× faster on one machine (4.1 s vs 6.3 s), not separated from `bart_l` (gap 0.0095, p = 0.16–0.17). |
| **Self-host · open-weight LLM, absolute** | **`deepseek_m` (DeepSeek-V4.1-Flash, MIT): 0.3460 as served by 12 unpinned providers.** The published checkpoint is 510 GB (48 safetensors shards; the card's 552B count excludes a 196B Engram memory). Whether it fits one node is not established. |
| **Self-host · open-weight LLM, ≤128 GB** | **`llama_m` (Llama-3.3-70B): 0.3382 as served, 0.0078 behind `deepseek_m` (not separated, p = 0.27).** ~70 GB at 8 bits is a sizing estimate: no int8 run was made, and the scored run was served by 9 unpinned providers of unrecorded precision. Alternative: `mistral_s` (24B, ~48 GB at 16 bits), 0.3255. |
| **Self-host · open-weight LLM, ≤64 GB** | **`mistral_s`: 0.3255 as served (~48 GB at 16 bits).** Llama at 4 bits (~35 GB) was not run; `llama_m`'s 0.3382 is not evidence about it. |
| **Deploy — rented API** | **`deepseek_m`: $191 per 1M articles (billed mix of 12 providers; the rate moves with routing), 0.3460.** 0.0001 behind `bart_l`, not separated (p = 0.99); 7× faster per item than `bart_l` on the Mac (4× against its Linux timing). It is also MIT open-weight, so this row is a latency choice, not a licensing one. |
| **What should I not deploy?** | **`anthropic_l` at $9,826 per 1M articles: separated below both `bart_l` and `deepseek_m` (+0.0307 and +0.0306, p ≤ 0.0008).** It ranks 18th of 29 on `coverage` (15th of the 24 hosted arms) and is 8.9% below the free arm. |
| **Does paying more help?** | **Not detectably, as run here.** Price and `coverage` were uncorrelated across the 24 hosted arms: r = −0.07 (95% CI −0.46 to +0.34, Spearman −0.04), **−0.4%** quality per 10× cost over a 143× price range. That interval does not exclude a moderate effect either way, and price is confounded with vendor: the seven dearest arms were each served by one provider, and every arm served by several cost $0.1532 or less. Specific pairs are separated: `anthropic_l` and `anthropic_m` sit below `deepseek_m` in both test families; `openai_l` only in the four named pairs (§3.1b), not the 28-arm family (p = 0.0049 against 0.0045). |
| **How many arms are not separated from the leader?** | **15 of the 28 others are not separated from `bart_l`: 13 paid arms and both distilled BARTs.** That is not equal: they trail it by 0.0001 to 0.0257, and the weakest, `gemma_l` (p = 0.0044 against a Holm threshold of 0.0033), is just inside. The cheapest paid one among them, `deepseek_s`, trails by 0.0176 and is 143× cheaper than the dearest paid arm. From `deepseek_m` the count is 11 of 28. |
| **Is a pilot enough?** | **No.** ρ(20 articles, 200) = 0.722 over the arms the uncommitted dev run had (0.667 over the 24 hosted arms, §3), both inflated because the 20 sit inside the 200. On disjoint articles ρ = 0.597 (0.698 with the overlap). The pilot's first hosted arm, `deepseek_m`, is still first among them, but the 200 do not separate it from `bart_l` (§3.6). |
| **Does it hold outside CNN?** | **For the local arms, yes; for the paid ones, unknown.** On 200 DailyMail articles the five local arms keep every verdict: `bart_l` beats LEAD-3 by +0.073 (CNN +0.074), `bart_m` is not separated from `bart_l`, the XSum control is last (§3.7). The hosted arms were not re-run there. |
| **Fine-tune or pay?** | **Fine-tune for cost, and only on text like yours.** `bart_l` is not separated from the best paid arm and is free, but slower (11.0 s vs 1.6 s, both timed from the Mac); distilled, 1.5–1.8× faster than `bart_l` on one machine. The same architecture fine-tuned on XSum scores 0.2071, last of 29 on `coverage`, below LEAD-3; its decode settings differ too, so it cannot separate house style from length. |

*How to read this table: every bare score (0.3461, 0.3460, …) is `coverage` on the 200 CNN
articles — 0 to 1, higher is better (§2 defines it); gaps such as "0.0078" are in the same
units. **$/month** is what the provider billed for the 200-article run, scaled to 1M
articles a month (`deepseek_m`: $0.0381 ÷ 200 × 1,000,000 ≈ $191). Times are mean seconds
per article on the machine named; the hosted arms were timed from the Mac, through a local
proxy.*

**Findings, decision-relevant first.**

**The dearest arms tested did not earn their price, as run here, and this is the firmest
result in this report.** `deepseek_m` at **$0.0381** per 200 articles beats `anthropic_l` at **$1.9652** — 52×
dearer — by +0.0306 coverage, p = 0.0000, and it holds on the 180 out-of-sample articles
and on the literature-standard metric too. At n=20 that same comparison came back
"not separated"; the question was never unanswerable, twenty articles just could not
answer it.

| pair named after the n=20 pilot | all 200 articles · Δ coverage, p | 180 held-out articles · Δ coverage, p |
|---|---|---|
| `deepseek_m` > `anthropic_l` (52× dearer) | +0.0306, p=0.0000 | +0.0308, p=0.0000 |
| `deepseek_m` > `anthropic_m` (19.6×) | +0.0224, p=0.0006 | +0.0224, p=0.0010 |
| `deepseek_m` > `openai_l` (11.4×) | +0.0193, p=0.0032 | +0.0171, p=0.0153 |
| `deepseek_s` > `qwen_m` (control) | +0.0255, p=0.0000 | +0.0208, p=0.0003 |

Δ is the first arm's `coverage` minus the second's (mean over articles; positive = the
cheaper arm is ahead). p is the uncorrected two-sided sign-flip permutation p (20,000
permutations); **p=0.0000 means p < 0.0001** — no permutation came close. The 180 held-out
articles are the ones the n=20 run never saw. The pairs were chosen after the n=20 pilot,
while the n=200 sweep was running, and the family changed once (§3.1b); the Holm below
covers the four, not the choosing of them.

All four survive a Holm step-down over the four named pairs on `coverage`, in both cuts. In
the wider family of `deepseek_m` against all 28 other arms, `openai_l` does not: p = 0.0049
against a Holm threshold of 0.0045 (`anthropic_l` and `anthropic_m` do; §3.1b). **On the point
estimates, $1.9652 buys 15th place among the 24 hosted arms; $0.0381 buys 1st.**

**Sixteen of the 24 hosted arms are dominated on the point estimates:** each is behind some
other hosted arm on `coverage` *and* billed cost *and* mean latency at once. That is a
ranking of point estimates, not a test, and latency is machine- and proxy-bound (§2). For
11 of the 16 the best dominator's quality lead is separated (paired sign-flip, uncorrected
p < 0.01); for `deepseek_l` and `glm_m` only at p = 0.025 and 0.029; for three it is not —
`llama_l` (behind `deepseek_m` by +0.0074, p = 0.26, at 2% higher cost), `mistral_s`
(behind `deepseek_s` by +0.0029, p = 0.65, 30% higher cost) and `gemma_l` (behind `llama_s`
by +0.0129, p = 0.063, 7% higher cost) — and for those the case is a cost tiebreak and a
noisy speed reading, not a quality loss. Eight remain on the frontier (§3.4). That is the most directly actionable output here.

**On deployment:** `bart_l` (1.6 GB, MIT, CPU) is not separated from the best open-weight
LLM, DeepSeek-V4.1-Flash, on `coverage` — 0.3461 against 0.3460, p = 0.99 — which is **510 GB
in the published checkpoint (whether it fits one node is not established)**. Capping an
open-weight LLM at what fits 128 GB gives up **0.0078** on the point estimate (Llama-3.3-70B,
`llama_m`, **0.3382** as served, against `deepseek_m`; not separated, p = 0.27), and `bart_l`
fits any budget. In this experiment the free model is also *slower* than renting (11.0 s vs
1.6 s per item), because generation on a CPU is genuinely expensive. Distillation narrows
that, at a price that differs by arm. Timed on one machine (`data/runs-linux/`), `bart_l`
takes **6.3 s**, `bart_m` (1.2 GB, 0.3367) **4.1 s** and `bart_s` (460 MB, 0.3276) **3.4 s**.
In the 28-arm Holm family neither is separated from `bart_l`; in the five-arm family of §3.7
`bart_s` is (gap 0.0186, p = 0.017), and on DailyMail by 0.0382.

**The XSum control points to house style, and cannot separate it from length.**
`bart_l_xsum` is the same BART-large architecture fine-tuned on XSum, whose references are
single-sentence summaries of BBC articles. Scored against CNN/DailyMail's references it
finishes **last of 29 on `coverage` (recall) at 0.2071** — separated from all 28 other
arms, below even LEAD-3's copy-the-first-three-sentences (0.2718) — and first of 29 on
`concision` (precision, 0.3120). Its outputs are 21 words against a 35-word reference, and
its grounding falls from `bart_l`'s 0.884 into the LLM range (0.422). **`bart_l`'s tie with
the frontier is consistent with CNN/DailyMail's house style, learned from its training
split** — the report's caveat from the start. The control is not single-variable: its decode
settings differ as well (XSum's 62/11 max/min tokens, 6 beams and no length penalty against
142/56, 4 beams and a length penalty of 2.0), so it does not separate *style* from
*length*; a sixth arm at CNN/DailyMail decode settings would.

**Ten times the articles separated 34 pairs instead of 1, and that was not enough to rank.**
Pairs separated on `coverage` went from **1 of 276** at n=20 to **34 of 276** at n=200 (25
on the held-out 180), and the critical difference fell from 8.13 rank positions to 2.57. A leaderboard
printing a smooth 1-to-24 ordering is still asserting hundreds of comparisons it cannot
support.

*Both figures are over the **24 hosted arms**, reproducible with the command in §2. Over
all 29 arms the critical difference is **3.18** with **80 of 406** pairs separating
(71 of 406 on the held-out 180).*

**The n=20 ranking largely did not survive.** Spearman between the two orderings of the
same 24 arms is **+0.667**. `qwen_s` fell 15 places, `llama_s` rose 12, `anthropic_m` fell
8. Only `deepseek_m` held its position. Any arm selected on 20 articles was selected
substantially by luck. The n=20 ranks, that 0.667 and the 0.722 above come from the earlier
run, whose hosted per-arm runs are not committed (only `cnn_bart_l_v1` and `cnn_lead3_v1`
are), so this tree cannot recompute them; and the 20 articles sit inside the 200, which
inflates the agreement. What the committed n=200 runs do give: their first 20 articles
against the other 180 correlate at ρ = 0.597 over the 24 hosted arms, against all 200 at
0.698.

**And ten times the data does not stabilise a ladder.** Two *independent* 100-article
evals of these arms agree at only ρ = 0.79 and crown the same winner 1% of the time; at
20 articles it is ρ = 0.44 and 11% (29 arms). What is stable is membership, not order —
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

**Two findings below are from the n=20 run and were not re-measured at n=200.** A
model-authored reference ("silver") is biased, not merely noisy: silver rankings agree with
gold at ρ = 0.33 against a retest ceiling of 0.92, and **silver authors promote models of
their own family** — +7.4 rank positions on average, positive for 22 of 24 authors,
p < 0.001. And **temperature 0 is not deterministic**: 9.8% of outputs were byte-identical
across three repeats, 12 of 24 arms with none; this run is r=1 by design (with articles
available, repeats are the wrong place to spend the same budget), so it does not re-measure
it.

**Nine findings in this report's own history were retracted**, two caused by bugs in this
harness's own scorer, and two more by the n=20 sample itself. §6 records them, because
the retraction rate measures how much of a first-pass eval is instrument rather than
signal.

---

## 1. What was measured

One task: *summarise a news article in 2–3 short sentences, in the terse style of a news
wire summary.* One prompt, 119 bytes, zero-shot (no examples), stored once in `prompt.txt`, its sha256
recorded in every run's fingerprint. Not prompt optimisation — a per-model prompt would make the
comparison meaningless.

**Corpus.** `abisee/cnn_dailymail` (config 1.0.0; the same articles as 3.0.0, which the
literature uses), Apache-2.0 per its dataset card, the **first** 200 articles of the
11,490-article test split, mean 555 words. Because the split puts CNN's articles first, that
is **all CNN** (196 with CNN's dateline, 4 partner pieces CNN republished) — not a sample of
the benchmark, a sample of its
CNN portion, which is 9.5% of the split. Read every figure below with that scope; §3.7 measures the other outlet. References are the `highlights` written by the journalists who
filed each article — genuinely human-authored, mean 34.7 words. The corpus is never
committed; the repo ships a download recipe (`fetch.py`, stdlib only). `fetch.py` pages
from offset 0, so the earlier 20-article slice is a **subset** of these 200 — verified, 20
of 20 — which is why every result is also given on the 180 that are new.

**Held constant.** Dataset, prompt file, temperature 0, `max_tokens` 1200,
`reasoning: {enabled: false}`. Each arm's config differs from its n=20 predecessor in
exactly two lines, `config_id` and `dataset_id`, verified by diff. Every run records
`reasoning_tokens` from the provider's own accounting: **0 on all 4,800 calls**.

**Not held constant: the provider.** No upstream provider was pinned; the proxy sent each
call to OpenRouter, which routed it. `providers_seen` in each run's `metrics.json` records
who served it. 13 of the 24 hosted arms were served by 2 to 14 providers within one run
(`deepseek_m` 12, `llama_m` 9, `deepseek_l` 13, `gemma_m` 14); the other 11, including
`anthropic_l` and `openai_l`, by one. A hosted score here is the score of that run's provider
mix, as served — not of a model at a fixed precision and serving stack, and the runs do not
record each provider's quantisation. The corpus is public, and whether any arm saw it in
training (contamination) was not measured.

**One repeat per arm, not three.** With articles available, repeats are the wrong place to
spend the same budget — at fixed cost, n=60/r=1 gave sd(delta) 0.0090 against n=20/r=3 at
0.0133. The consequence is stated rather than hidden: this run measures no within-arm
variance, and the determinism figures in §3.3 come from the earlier r=3 sweep.

**Provenance caveats.** 23 of the 24 hosted runs record `harness.dirty: true` (`anthropic_l` does not). The cause:
`_fingerprint.py` derives that flag from `git status --porcelain`, which counts UNTRACKED
files, and a sweep's own configs are untracked at the moment it starts. The first 8 arms
record earlier commits (`d9def7c7` for seven, `5790bb31` for `qwen_m`) than the last 16
(`e0810991`). The measurement is unaffected:
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
0.30; 24 points is a thin basis for a correlation either way.

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
over 30 s (median 7855 ms).
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

Spearman between the n=20 and n=200 orderings: **+0.667** (the n=20 column is the earlier
run's; its hosted runs are not committed, so it cannot be recomputed from this tree).

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
lead and `bart_l` is 12th. `bart_l` is first on `coverage` (tied with `deepseek_m`: 0.3461
against 0.3460, p = 0.99), third on ROUGE-2 behind its two distillations, and 12th on
ROUGE-1 — consistent with what BART learned being CNN's *phrasing*, which bigrams reward and
unigrams barely see. None of these absolute figures is comparable to published
ROUGE, which is computed on the full test set (§5).

`bart_m` is distilbart-cnn-12-6 (12 encoder / 6 decoder layers, 1.2 GB) and `bart_s`
distilbart-cnn-6-6 (460 MB, stored at fp16; the CNN run executed at fp16 although its config
declares `precision: fp32`, because the adapter did not apply that field when it ran — see the
note in §6) — both distilled from `bart_l`, so they sit below it as they
should, in the order their size predicts. Their grounding stays in `bart_l`'s range
(0.85–0.88) against 0.25–0.43 for the hosted field. `bart_l_xsum`'s concision is the best
in the table only because concision rewards brevity and XSum writes one sentence.

No local arm here differed between runs. On the same machine all three new arms re-ran
**200 of 200 outputs byte-identical** (`bart_s` three times, counting the resumed run in
`data/runs-repeats/`), and across machines (Mac → Linux) so did `bart_l` and `lead3`
(`data/runs-linux/README.md`). Hosted arms at temperature 0 do not: 47 of 480 article
outputs were identical across three repeats in the earlier sweep here (§3.3), and 13–78 of
200 across five pairs of runs of four SciFact rerankers (`REPORT_RETRIEVAL.md`).

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
| `bart_l` | 13 of 28 | 28 of 28 | — |
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
four pairs were **named after the n=20 pilot and before the last arm finished running**
(there is no timestamped registration, only the journal), and are Holm-corrected as a
family of four. In each cell: Δ (first arm minus second, mean over articles), then the
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

Unlike the six pairs in the n=20 version of this section, these were named before the last
arm finished, not after the table was read. They were still chosen after the n=20 pilot and
while the sweep's first arms had already run, so the 180 held-out articles are held out from
the pilot's articles but not from the choice of pairs. The family also changed once: the
journal's earlier draft (`NOTES.md` entry 45, "named before `anthropic_m`'s number existed")
names `deepseek_m` > `deepseek_s` as the fourth pair; the published draft ("before the last
arm finished") names `deepseek_m` > `anthropic_l`. The Holm over four covers the four, not
the choosing of them.

In the wider family — `deepseek_m` against all 28 other arms, Holm over 28
(`python scripts/family_test.py --dataset-id cnn_dailymail_200 --a cnn_deepseek_m_n200_v1
--against cnn_ --metric coverage`) — `anthropic_l` (p = 0.0000) and `anthropic_m` (p = 0.0003)
are separated; `openai_l` is not (p = 0.0049 against a threshold of 0.0045), and 17 of the
28 are separated, so 11 are not.

### 3.2 Variance decomposition (`coverage`)

| source | share |
|---|---|
| between articles | **67.8%** |
| between arms | **1.0%** |
| residual | 31.2% |

Which article you drew moves the number ~68× more than which model wrote the summary.

### 3.3 Determinism at temperature 0

**Not re-measured here.** This run is r=1. From the earlier r=3 sweep: 47 of 480 (9.8%)
article-outputs byte-identical across three repeats, and 12 of 24 arms with none at all.
Nothing in this run contradicts that; nothing in it confirms it either.

**The local contrast was measured.** Every local arm was re-run (`data/runs-linux/`):
`bart_m`, `bart_s` and `bart_l_xsum` on the same Linux machine, `bart_l` and `lead3` on a
different one from their recorded Mac runs. **All five reproduced 200 of 200 outputs
byte-identically** — beam search on a CPU, at fp32 except `bart_s`, which ran at its stored
fp16. Run-to-run variance for these local arms,
on these two CPUs, is zero; for a hosted one it is not, and no test in this report sees it
(every separation test is over items within one run). GPUs and other torch builds were not
tried.

### 3.4 Pareto frontier (coverage / cost / latency)

**8 of 24 arms**: `deepseek_m`, `deepseek_s`, `gemma_m`, `glm_s`, `llama_m`, `llama_s`,
`openai_s`, `qwen_m`. The other **16 are dominated on the point estimates** — behind some
other arm on `coverage` *and* billed cost *and* mean latency. That is a ranking of point
estimates, not a test, and latency is machine- and proxy-bound (§2). Taking each dominated
arm's best dominator (paired sign-flip on `coverage`, uncorrected): 11 are behind it by a
separated margin (p < 0.01); `deepseek_l` (by `deepseek_m`, +0.0136, p = 0.025) and `glm_m`
(by `deepseek_m`, +0.0141, p = 0.029) only at p < 0.05; three not at all:

| dominated arm | its only dominator | quality lead, p | cost | mean latency |
|---|---|---|---|---|
| `llama_l` | `deepseek_m` | +0.0074, p = 0.26 | $0.0389 vs $0.0381 (+2%) | 3473 vs 1595 ms |
| `mistral_s` | `deepseek_s` | +0.0029, p = 0.65 | $0.0179 vs $0.0137 (+30%) | 2820 vs 2753 ms |
| `gemma_l` | `llama_s` | +0.0129, p = 0.063 | $0.0237 vs $0.0222 (+7%) | 2591 vs 2388 ms |

For those three the case against is a cost tiebreak of 2% to 30% and a speed reading from
means that §2 says are machine-bound — not a quality loss.

**The five local arms are left out on purpose.** At $0 an arm can only be dominated by
another free arm, so every local arm that is not beaten by a *faster, better* local arm is
on the frontier by construction, not by merit. Over all 29 the frontier adds `bart_l`,
`bart_m`, `bart_s` and `lead3` — each fastest-for-its-quality among the free — and still
excludes `bart_l_xsum`, which `bart_s` beats on quality and speed.

At n=20 the frontier held 10 arms. The three that dropped off did so because more data
moved their quality estimate, not because their cost or latency changed — a reminder that
even the point-estimate part of this report depends on the sample.

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

| articles per half | ρ(half A, half B), mean over draws | ρ, 5th percentile | P(both halves crown the same arm) | median rank move (positions) | arms sharing 1st place |
|---|---|---|---|---|---|
| 10 | 0.336 | 0.033 | 0.08 | 4.84 | 1.0 |
| 20 | **0.443** | 0.191 | **0.11** | 3.91 | 1.0 |
| 50 | 0.640 | 0.452 | 0.12 | 2.67 | 1.0 |
| 100 | **0.793** | 0.689 | **0.01** | 1.63 | 1.0 |

*Each row averages 400 random draws of two disjoint halves. ρ is the Spearman correlation
between the two halves' orderings of the 29 arms (1 = they agree exactly). "Median rank
move" is how many positions an arm typically sits from its
full-200 rank in a half of that size. "Arms sharing 1st place" is the average number of
arms tied for the best score in a half; 1.0 means no ties. Bold marks the 20-article size
of the original experiment and the 100-article size quoted in the summary.*

At 20 articles — the size of the original experiment — two independent evals of these arms
agree at ρ = 0.44. At 100 they still disagree at ρ = 0.79.

### P(same winner) is 0.01 at 100 articles, and that is a result rather than a regression

`coverage` is continuous and never ties, so the cause is the arm set.

```
cnn_bart_l      0.346121   wins half A in 179 of 400 draws
cnn_deepseek_m  0.346039   wins half A in 178 of 400 draws
```

**Two arms 0.00008 apart over 200 articles.** Adding `bart_l` gave the field a co-leader
that 200 articles do not separate from the previous one (p = 0.99), so the two halves crown
the same arm essentially never — a coin flip between two arms this data does not separate.

The statistic is reporting exactly the right thing, and it happens to be the same finding
the ML arms produced from the other direction: BART's apparent lead at n=20 was 0.0737 and
at n=200 it is 0.00008. "P(both halves crown the same arm)" is near zero **because there is
no winner to crown**, not because the evaluation got noisier.

Note also that the "arms sharing 1st place" column of the table above is 1.0 at every size: these two arms are not *tied* to the last decimal, they
are 0.00008 apart, which a continuous metric resolves into a strict order that means
nothing. On items `deepseek_m` is ahead on 96 of 200 and `bart_l` on 85 (19 exact ties), and the
paired test (p = 0.99) names no winner either. A tie count cannot catch that; only the separation tests in §3.1 can.

This is the most transferable result in the report: it is about evaluation rather than
about 24 models, and it does not go stale when the models change.

### 3.7 Does it hold outside CNN? The DailyMail slice

Every result above was measured on CNN's articles alone (§1). To test whether the
conclusions travel, `cnn_dailymail_dm200` draws **200 DailyMail articles at random** (seed
20261014) from the same test split — none carries a CNN or CNN-partner dateline — and the
five local arms re-ran on it with their parameters unchanged. All five runs are clean
(`build.dirty: false`; four on commit `a81669ca`, `bart_s` on `8165bd94`, the fp32 run) and committed as
`harness/data/runs/cnn_*_dm200_v1_*`.

`coverage` is on the same 0–1 scale as above (higher is better); ROUGE is printed ×100, as
in the ROUGE table in §3; words are the mean summary length. **Bold** = best on DailyMail
`coverage` — `bart_l` and `bart_m` tie to four decimals.

| arm | CNN · coverage | DailyMail · coverage | DailyMail · ROUGE-1 / ROUGE-2 F1 ×100 | DailyMail · words / summary |
|---|---|---|---|---|
| `bart_l` | 0.3461 | **0.4430** | 46.16 / 23.18 | 67 |
| `bart_m` | 0.3367 | **0.4430** | 46.95 / 24.09 | 76 |
| `bart_s` | 0.3276 | 0.4048 | 44.78 / 21.92 | 54 |
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
| `bart_s` | +0.0186, separated (p = 0.017) | +0.0382, separated |
| `bart_m` | +0.0095, not separated (p = 0.16) | +0.0000, not separated (p = 1.00) |

**Among the local arms, every verdict transfers.** The fine-tune beats LEAD-3 by the same
margin on both outlets (+0.074 and +0.073); the XSum control fails harder on DailyMail;
`bart_m` is not separated from `bart_l` on either (gaps +0.0095 and +0.0000); `bart_s` is
separated on both here and gives up twice as much on DailyMail as on CNN. *(The CNN column is a five-arm family, so its thresholds are looser
than §3.1's 28-arm family, where `bart_s` is not separated.)*

**What this does not test: the hosted arms.** Whether `bart_l` is still not separated from `deepseek_m`,
whether 15 arms are still not separated from the leader, whether the dearest arm still trails — every
comparison involving a paid model — is unmeasured outside CNN. Configs for the four
hosted arms in the CNN top six are committed beside the local ones
(`configs/arm_{deepseek_m,llama_l,llama_m,llama_s}_dm200.yaml`); they need an
OpenAI-compatible endpoint, which the environment that ran this slice did not have.

**And a calibration aside.** `bart_l` is the published `facebook/bart-large-cnn`, reported
at ROUGE-1 44.16 on the full test set. Weighting this repo's two slices by the split's
outlet mix (9.5% CNN, 90.5% DailyMail) estimates **45.1 ±1.6** (the two slices' 95%
sampling interval) — 0.9 above, inside that interval, though a different ROUGE
implementation and 400 articles rather than 11,490 are also in play. The instrument is
close to the literature on the model, and on LEAD-3 (R1 0.40 below, outside its ±0.22).

### 3.8 Re-measured with SummEval-validated LLM judges

The same 29 outputs were scored again by two LLM judges validated on SummEval (`gemma_l`,
τ 0.5384; `qwen_s`, τ 0.5192), with scorer `judge-summ-v1`
([ADR-0001](../docs/adr/ADR-0001-judge-scorers.md)). Each judge read the article and up to 15
summaries per call, blinded and shuffled: 960 calls, $0.31, 197 of 200 articles. On the
judges' score every hosted LLM ranks above every BART model: `bart_l` scores 3.87 of 5 and is
separated below all 24 hosted LLMs, which score 4.53–4.98, with `anthropic_l` first. The two
judges agree closely: Spearman 0.93 over arm means, item τ 0.74. Re-ordering the summaries
moved per-article scores by 0.11–0.21, and a repeat call by 0.03–0.12.

People have not confirmed this ranking on these outputs. The one direct check, a blind
comparison by one non-expert reader on 20 `bart_l`/`deepseek_m` pairs shown truncated
articles, preferred `bart_l` 14 to 6 (sign test p = 0.115), while the judges preferred
`deepseek_m` on all 20. The reader was asked which summary is better, "most accurate and clear
about what happened"; the judges score four dimensions, so the two did not answer quite the
same question. On three other systems, the GPT-3, BART-based BRIO and T0 summaries of Goyal,
Li & Durrett (2022, CC BY 4.0; 100 CNN articles, three annotators each), the judges agree with
people about as well as people agree with each other: picking the best of the three, against
one annotator they score 0.498 (`gemma_l`) and 0.526 (`qwen_s`), annotators against each other
0.454, chance 0.333. On the same articles they prefer the GPT-3 summary to BRIO's more often
than the annotators do (72.7% and 77.0% against 63.6% and 63.2%; each rate's 95% interval is
computed on its own, not as a paired test, and the intervals overlap for both judges). Scored one summary at a time
instead of in lists (unvalidated), they still rated `deepseek_m` above `bart_l` on 192 of 200
articles and never below. So the judged scores are directional at most and unconfirmed on these
arms, and `coverage` stays the primary metric. The record is
`examples/summarization-cnn-dailymail/human_check_judge.json`; the verdicts are in
`harness/data/judge-verdicts/judge-summ-v1/`, and `make judge-score ... ARGS=--no-calls`
rebuilds the scored runs from them for $0.

**Frontier judges, the same verdict (`judge-summ-v2`).** To test whether the disagreement came
from small judges, the two highest-scoring SummEval judges from vendors not in the first pair,
`openai_l` (τ 0.5398) and `anthropic_l` (τ 0.5283; the first pair's `gemma_l` reached τ 0.5384, so
they are not clearly better judges, only larger and dearer ones), each validated by its
committed SummEval run under the same prompt and protocol, reasoning off, judged the same
judging set with the same prompt: 960 calls, $12.92, 200 of 200 articles, no reply unparsed.
They reach the same verdict. Every hosted LLM ranks above every BART model: `bart_l` scores 3.82
of 5 and is separated below all 24 hosted LLMs, which score 4.04–4.89, with `anthropic_l` first,
as under the first judges, and separated from 27 of its 28 opponents, all but `deepseek_m`. The two
scorers order the arms alike (Spearman 0.85 over arm means), and the frontier judges agree with
each other at Spearman 0.94. On the 20 human-check pairs they prefer `deepseek_m` 20 to 0, as
the first judges did. On the Goyal et al. systems they score 0.466 (`openai_l`) and 0.488
(`anthropic_l`) against one annotator, annotators against each other 0.454; on the articles
both decided, `openai_l` prefers the GPT-3 summary on 70.4% against the annotators' 61.7%, and
`anthropic_l` on 64.2% against 64.2%. Their own-family gaps are larger: `openai_l` scored OpenAI's
arms 0.53 above the others and `anthropic_l` Anthropic's 0.59, against 0.18 and 0.30 for the
first judges (raw gaps, not bias estimates: families differ in real quality). So judges of very
different size and price agree with each other and not with the one reader, at 41× the cost,
and the judged scores stay directional at most. The verdicts are in
`harness/data/judge-verdicts/judge-summ-v2/`, the Goyal records in
`harness/data/judge-validation/judge-summ-v2/`.

**Checked against people on LLM-written summaries (Zhang et al. 2024).** SummEval's systems are
from 2019. Zhang, Ladhak, Durmus, Liang, McKeown & Hashimoto (2024, TACL) released crowd ratings
of 19 summarisers on 100 CNN/DailyMail articles: GPT-3-era LLMs, base and instruction-tuned,
zero- and few-shot; the fine-tunes BRIO and Pegasus; and the reference highlights, three ratings
each for coherence, relevance (1–5) and faithfulness (0/1); 38 of the 1,900 summaries are empty
and are kept, as empty summaries. All four judges scored each article's
19 summaries under the validated prompt, in blocks of 10 and 9. Each is measured against the mean
of two ratings with the third held out, rotating, and so is one rating against the other two. On
the 18 non-reference summaries, mean τ over the three dimensions is 0.496 (`gemma_l`), 0.479
(`qwen_s`), 0.457 (`openai_l`) and 0.483 (`anthropic_l`), against 0.384 for one rater and 0.338
and 0.326 for ROUGE-1 and `coverage` against the reference highlights. Every judge is ahead of
one rater on 72–80 articles and of `coverage` on 88–94 (paired sign-flip over articles, p < 0.001
for each). By dimension the judges lead on coherence and relevance and trail one rater on
faithfulness (0.48–0.61 against 0.64; the judges' consistency score is set against the raters'
0/1 faithfulness). Ranking the systems by mean coherence and relevance (faithfulness left out),
the raters rank BRIO 5th of 19
and Pegasus 6th, after four instruction-tuned OpenAI models; the judges rank BRIO 1st or 2nd,
with Spearman 0.71–0.79 between the judges' and the raters' rankings of the 19. They deviate
system by system in both directions: the raters rank the reference highlights 16th, the judges
3rd to 6th. So on these summaries the judges show no blanket preference for LLM-written
summaries over a BART-based fine-tune, and the cheap pair does as well as the frontier pair for
$0.11 against $4.35. The limits: one crowd rating is a noisy baseline, and these τ are against
crowd raters on another set, so they do not compare with SummEval's (one expert against the
other two there: 0.559); the 19 systems span a wide range of quality, which makes a high
Spearman easier; the articles and ratings have been public since 2023, so a judge may have seen
them. The systems are 2022's, not this experiment's arms: this is evidence about the judges, not
a check of the ranking above. The
ratings are downloaded at run time, not committed; the records, which hold article ids, the
judges' replies (kept only as a hash when one is not bare JSON scores or repeats 8 consecutive
words of the article or a summary),
scores and hashes, are in `harness/data/judge-validation/<scorer>/zhang2023-cnndm/`.

## 4. Discussion

**The experiment's resolution is set by the corpus, not the models.** With 67.8% of
variance between articles and 1.0% between arms, the paired design is doing nearly all the
work. This is not a small-sample complaint that more data fixes at the margin — it is the
shape of the task. Ten times the articles moved `coverage` from 1 separated pair to 34, and
still left the top six mutually unseparated.

**The free model that leads is a specialist in this corpus; the control is consistent with
that and does not isolate why.** Three BARTs trained on CNN/DailyMail finish 1st, 5th and
10th of 29 on `coverage` in the order of their size; one BART trained on XSum finishes 29th,
below the LEAD-3 baseline. Same architecture and same $0, but not the same decoding: the
XSum checkpoint runs at 62/11 max/min tokens, 6 beams and no length penalty against 142/56,
4 beams and a length penalty of 2.0, and its 21-word outputs fall short of the 35-word
reference that `coverage` recalls against. So two things differ at once — which corpus's
references the model learned to imitate, and how much it writes — and single-reference
ROUGE against *this* corpus rewards imitating this corpus. The production advice keeps its
shape and gains its scope: fine-tune on summaries that look like the ones you want, and a
1 GB model on a CPU is not separated from the frontier; one XSum-trained arm, scored on
`coverage`, shows that fine-tuning on someone else's can land below copying the first three
sentences.

**Discriminating power is not informativeness.** Ranked by pairs separated:
`summary_words` (208) > `grounding` (172) > `concision` (146) > `rouge1` (97) >
`rougeLsum` (95) > `coverage` (34). That is almost exactly the order of how much each
measure depends on output length or extractiveness — and it is the same order as at n=20,
so it is a property of the metrics rather than of the sample. The most "sensitive" metric
available is a word count. An eval that picks its headline metric by which one separates
cleanest will pick a length measure and call it quality.

**Price and quality were uncorrelated in this field, as run here.** Across the 24 hosted
arms r = −0.07 (95% CI −0.46 to +0.34, Spearman −0.04, n = 24): a moderate relation in
either direction is not excluded, and price is confounded with vendor — the seven dearest
arms were each served by one provider (a vendor's own endpoint), every multi-provider arm
cost $0.1532 or less. What is separated is specific pairs. `anthropic_l` at **$1.9652**
ranks 15th; `deepseek_m` at **$0.0381** ranks 1st, and that gap is separated at p = 0.0000
in both item cuts and on both ROUGE facets; `anthropic_m` is separated below `deepseek_m`
in both test families, `openai_l` in the four named pairs but not in the 28-arm family. At
n=20 the same `anthropic_l` comparison was "not separated" (p = 0.52) and the honest
reading was *"if a model 52× cheaper cannot be shown to be worse, the expensive one has not
earned its price."* That reading was right, and for that pair n=200 gives the stronger
version: it **is** shown to be better. One pair is not a trend.

**The eliminations are the actionable output, with their gaps.** 16 of 24 arms are
dominated on the point estimates: behind another arm on quality *and* cost *and* speed
simultaneously (§3.4). For 13 of them some dominator's quality lead is separated at
p < 0.05; for three (`llama_l`, `mistral_s`, `gemma_l`) it is not, and the case there is a
2%–30% cost difference and a noisy speed reading. It answers the question a team actually
has — not "which is best" but "which are not worth considering".

**A ladder needs more data than a decision, and possibly more than exists.** §3.6 measures
it: two independent 100-article evals of these arms still disagree at ρ = 0.79. The gap
between 1st and 3rd here is 0.0078 coverage; between 2nd and 3rd, 0.0005. Closing the
latter needs a sample in the six figures. The correct output is therefore a *set* — the
six arms with P(top 5) ≥ 0.47 — not a podium.

**Selection on a small sample is expensive in a way that does not announce itself.** The
n=20 ordering and the n=200 ordering of the same 24 arms correlate at 0.667. `qwen_s` was
7th and is 22nd; `llama_s` was 16th and is 4th. Anyone who had shortlisted the n=20 top
five (`deepseek_m` 1st, `deepseek_s` 2nd, `llama_l` 3rd, `anthropic_m` 4th, `llama_m` 5th)
would have carried `deepseek_s` (7th at n=200) and `anthropic_m` (12th), and missed
`llama_s` (4th) and `deepseek_l` (5th). (The n=20 ranks are the earlier run's, not recomputable here.)

**The tier ladders are mixed.** By `coverage`: `llama` large > mid > small and `gemma`
large > mid > small; `openai` mid = large (0.3268 each) > small; `anthropic` the reverse,
small (0.3238) > mid (0.3236) > large; `deepseek` mid > large > small, `glm` mid > small >
large, `mistral` small > large > mid, `qwen` large > small > mid. Two families run large >
mid > small, `openai` ties mid and large, one runs the opposite way, four are mixed. Since each ladder mixes model
generations with price steps, this experiment cannot say whether that is size, generation,
or noise.

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

- **No measure here has been confirmed by people on these summaries.** `coverage` tracks
  experts less well than ROUGE-1 (on SummEval), and the SummEval-validated LLM judges disagreed
  with a blind human check on 20 pairs (§3.8).
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
  (§3.7) re-ran the five local arms only. Nor with reasoning enabled, few-shot, on a
  different prompt (the one zero-shot prompt of §1 is the only one run), on longer inputs,
  or on any other corpus.
- **Whether a hosted score belongs to the model or to its providers.** No provider was
  pinned and each arm has one run: 13 of the 24 were served by 2 to 14 providers within it
  (§1), and the closed vendors' arms by one. The open-weight scores are that mix's, as
  served; no quantisation was chosen or recorded, so nothing here says what any model scores
  at int8 or int4.
- **Whether any arm saw this corpus in training.** CNN/DailyMail is public; contamination
  was not measured, and a high score here may be partly memorisation.
- **How fast the models are.** Latency is a property of this machine, this proxy and the
  upstream provider on the day.
- **Anything comparable to published ROUGE, on the committed slice.** Published figures
  are over the full test set, which is 91% DailyMail; this slice is all CNN, and CNN
  articles score ~11 ROUGE-1 lower (LEAD-3: 29.59 on CNN, 41.02 on DailyMail,
  `docs/evidence/calibration/summarization.json`). The scorer is a small part of the gap, not none of it:
  LEAD-3 over the full test set scores 39.94 ±0.22 here against 40.34 published (R2 17.37
  ±0.21 against 17.70), 0.40 and 0.33 below and outside those intervals, with the cause not
  isolated, and `bart_l`'s outlet-weighted estimate is 45.1 ±1.6 against 44.16 (§3.7),
  inside its interval. `grounding`, `concision` and `coverage` are this repo's own
  and comparable to nothing published.
- **Whether `bart_l`'s lead is style or length.** The XSum control fails for two reasons
  at once — it was trained on BBC single-sentence summaries *and* it decodes at 62/11
  tokens against 142/56 (and 6 beams with no length penalty, against 4 and 2.0). An arm at
  CNN/DailyMail decode settings would separate them; it was not run.
- **Within-arm variance for the hosted arms.** This run is r=1; the determinism figures are
  from the earlier r=3 sweep and were not re-measured. For the five local arms it was: each
  re-run was 200 of 200 byte-identical (`data/runs-linux/`).

---

## 6. Retracted findings, and what is enforced in code

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
| "10 of 24 arms are on the Pareto frontier" | **8 of 24** | three arms' quality estimates moved with more data |
| "CI stops baking a 990 MB model" (commit c7f47e4c) | it kept shipping, restored from cache | manifest drives the preload, not the artifact |

Two were caused by defects in this harness's own scorer, and two by trusting 20 articles.
**All of the first six were found by adversarial review, none by the person who produced
them**; the last three were found by re-measuring and by a log line added in the same
commit whose claim it falsified. Two further rounds of review
found stale numbers in the first published version of this example's README, and a bug that
would have crashed a fresh clone *after paying for its first API call*.

> **This is one of six experiments.** What all six agree on — and where they disagree
> with the conventional reading of a leaderboard — is in
> [`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).

> **`bart_s` on CNN ran at fp16.** Its checkpoint is stored at half precision, and when the CNN run was
> made the adapters did not apply a config's `precision`, so the CNN `bart_s` record (0.3276) is an
> fp16 measurement under an fp32 label. It stays the record because the LLM judges' verdicts in
> §3.8 were made on its outputs. The DailyMail `bart_s` record is the fp32 measurement (0.4048).

The practical lessons, all enforced in code:

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

No `rescore` step is needed: scores are written at 10 decimals, because the tie tolerance
is load-bearing for `coverage` (13-23% of arm pairs tie exactly on an item, depending on how
short the reference is) and 6 decimals cannot tell a genuine tie from a rounding artifact.
The leaderboard warns if it reads runs written at less.

Expect different absolute numbers. Providers update models behind stable names, and
`reasoning_tokens`, `providers_seen` and the resolved upstream model id are recorded per run
precisely so a future divergence can be attributed rather than guessed at.

---

## Costs are what the provider billed

The `$` figures are what the provider reported charging, per call, in `usage.cost`, not a price computed from `usd_per_mtok_in/out` in each arm's config. A config holds one price per model **alias**, and an alias is not a price. OpenRouter routes each request to one of several upstream providers — a single run in this repo recorded Novita 262 times, Parasail 9, DeepInfra 6, Nebius 3 — and they charge differently, so the effective price is a routing-dependent mixture no config can state in advance. Measured over the hosted runs of the five experiments other than SummEval, the price table is wrong **per arm by 0.67× to 3.76×, in both directions**.

**The error is not uniform, and that is what makes it matter.** Arms served by a single provider — the Anthropic models, notably — match the table exactly. The cheap, multi-routed models are undercounted. So the table systematically **understates the cheap end of the field, and therefore inflates every price-ratio claim.** It also reorders arms by cost: on `few_nerd_280`, `glm_s` is the 2nd-cheapest arm by the table and the 9th by what was billed. Rankings by *quality* never depended on cost.

Every experiment's adapter records `usage.cost` when the provider supplies it and falls back to the table only when it is silent. Runs made before the adapters recorded it keep the estimate in `cost_usd`; the billed figure is in `_meta.usage.cost` in each stored run.
