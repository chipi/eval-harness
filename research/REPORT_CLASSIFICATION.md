# Evaluation report — 24 LLMs, four fine-tuned classifiers and a regex on two classification tasks

**Datasets** `ag_news_200` · 200 news snippets · 4 classes — and `dbpedia_280` · 280 Wikipedia abstracts · 14 classes
**Protocol** test splits, 200 of 7,600 (the first 50 per class of the first 1,600 rows) and 280 of 70,000 (seeded, 20 per class) · accuracy, the standard metric · calibration: the AG News fine-tunes on the full 7,600-row test set match their model cards (`bert_mini` 0.9338, `bert_base_ta` 0.9514, `bert_base_fy` 0.9375); DBpedia: 0.9879 ±0.003 on 5,600 of 70,000 rows against the card's 0.9903, inside its own interval — [docs/PROTOCOL.md](../docs/PROTOCOL.md#classification--ag-news)
**Arms** 24 hosted models (8 vendors × 3 price tiers), plus fine-tuned classifiers (three on AG News, one on DBpedia), a zero-shot NLI model, ~20 regex rules and a constant
**Design** 1 pass per arm · identical prompt, temperature 0, reasoning off · hosted LLMs run **zero-shot, as run here**: one prompt, no label definitions or examples, no provider pinned (open-weight arms were routed across up to 16 providers), public benchmarks, contamination unmeasured · **$0.58 (AG News) and $1.17 (DBpedia) billed** ($0.49 and $1.00 by the price table — see Correction)
**Date** 2026-09-28; the three bert-base arms added 2026-09-30 · **Harness** [`../harness`](../harness) · **Journal** [`NOTES.md`](internal/NOTES.md) entries 47–50, 59

---

## Executive summary

**AG News: if you have labels, fine-tune: start with `bert_mini` (44 MB, $0 marginal). If you
must rent, start with `gemma_m` ($8 per 1M items).** Three public BERT fine-tunes (0.9600,
0.9500, 0.9450) score above all 24 hosted LLMs (0.835–0.910) on the point estimate, and are
not separated from each other; `bert_mini` is 11× faster than `bert_base_ta` for 0.0150 less.
The paid leader, `anthropic_m`, at $351 per 1M items and 0.9100, is separated from 3 of the 23 other hosted arms; the cheapest it is not separated from is `gemma_m`, at $8 and 0.8550, 0.0550 behind (`qwen_m`, at $35 and 0.8850, sits between), so the extra money is not shown to buy accuracy. The limit that could change this: the fine-tunes'
lead sits in 17 items most hosted arms miss, about half of them an AG News labelling
convention on one rater's reading, and the fine-tunes were trained on AG News's own training
split. What fine-tuning bought is this corpus's labelling; with fewer labels it was not
measured.

**DBpedia-14: take the cheapest arm you can run at 0.9857: `gemma_m` (~$12 per 1M items),
`qwen_s` (~$26) or the fine-tuned `bert_base_fy` (438 MB on a CPU, $0 marginal). Do not pay for
`anthropic_l` ($1,351) or `openai_m` ($850).** The top eleven arms (0.9786–0.9929) sit within 4
items of each other across a 115× price range, and the leader, `qwen_m`, at ~$51 and 0.9929, is
separated from only 8 of the 27 others. At 280 items no gap under 10 items was separated, so
a gain of up to about 3 points from paying more is not ruled out, only not shown.

Both are as run here: hosted LLMs zero-shot with one prompt and no label definitions, one
slice per corpus. Fine-tuning led where the labels follow a corpus convention and drew level
where there was no room left (§4).

Corrections and their dates: §6. This is one of six experiments; what all six agree on is in [`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).

### Supporting facts

#### The decision, in one table

| the choice | AG News (headroom) | DBpedia-14 (saturated) |
|---|---|---|
| **Self-host · small ML** | **`bert_mini`** (44 MB): 0.9450, not separated from `bert_base_ta`, 438 MB and 0.9600 (p = 0.55) and 11× faster when both are timed on one Linux machine (4.3 vs 49 ms median, §3.1). `bert_base_ta` has the best point estimate and is separated from 26 of the 29 others. Read §3.4 first. | **`bert_base_fy`** (438 MB, 87 ms/item on a 4-core Linux CPU): 0.9857, two items behind the leader, not separated (p = 0.62). In the top group; does not lead it. |
| **Self-host · open-weight LLM, absolute** | **`llama_m`** (Llama-3.3-70B, ~141 GB): 0.8800 as providers served it. 0.0800 behind `bert_base_ta` (separated); 0.0650 behind `bert_mini`, 3,205× smaller (p = 0.0149 against 0.0063, not separated). | **`glm_m`** (GLM-4.6, MIT, 357B / ~714 GB): 0.9857, not separated from the overall winner. The score is the providers'; no self-hosted run was made and the hardware it needs is unverified. |
| **Self-host · open-weight LLM, ≤128 GB** | Not measured: `llama_m` at int8 (~70 GB); the 0.8800 is not an int8 build's. Native alternative `gemma_s` (27B, 55 GB): 0.8750. | **`gemma_m`** (Gemma-4-26B-A4B, 52 GB native): 0.9857, the same score as GLM-4.6 at 1/14 the size. The weight size is native; the score is as served by its providers. |
| **Self-host · open-weight LLM, ≤64 GB** | Not measured: int4, ~35 GB. At native precision, with weights in 85% of memory (54.4 GB, the synthesis's rule): `mistral_s` (48 GB), 0.8600. `gemma_s` (55 GB), 0.8750, is just over that line. | Still `gemma_m`, 52 GB native; no self-hosted run was made. |
| **Deploy — rented API** | **Highest point estimate: `anthropic_m`**, $351 per 1M items, 0.9100; separated from only 3 of the 23 other hosted arms. Cheapest it is not separated from: `gemma_m`, $8, 0.8550 (0.0550 behind, p = 0.0081 against 0.0025). `qwen_m`: $35, 0.8850 (0.0250 behind, p = 0.18). | **Cheapest of the top group: `gemma_m`**, ~$12/month per 1M items, 0.9857 (two items behind `qwen_m`, p = 0.50); `qwen_s` ~$26, same score. `qwen_m`, ~$51 and 0.9929, leads on the point estimate, proprietary with no self-host option. |
| **What should I not deploy?** | **`anthropic_l`**, $875/month: 0.9000, 6.3% below `bert_base_ta`. `openai_m` ($636) scores 0.8950. | **`anthropic_l`**, $1,351/month: one item (−0.4%) below `qwen_m`, p = 1.0. `openai_m` ($850) is also in the top group. |
| **Does paying more help?** | **Marginally: +2.3%** per 10× cost (log-cost fit over the 24 hosted arms: +0.0214 accuracy per decade ÷ the best hosted score, 0.9100; r = 0.63). | **Barely: +0.9%** per 10× cost (+0.0094 ÷ 0.9929; r = 0.40). |
| **Not separated from the leader?** | **3 of the 29 others** from `bert_base_ta`: the two other fine-tunes and `anthropic_m` (+0.0100 to +0.0500). "Not separated" is not "equal". | **19 of the 27 others** from `qwen_m`, at gaps of 1 to 8 items (+0.0036 to +0.0286); the ranking is mostly noise. The smallest gap separated is 10 items. |
| **What limits the score?** | **The annotation, and a prompt that states no convention.** 17 items are missed by ≥80% of the hosted field (19 at 75%, 20 at 70%); the fine-tunes get 12–14 of them right, the best hosted arms 0–3. One rater reads about half as convention, half as mislabels. The 17 are selected by the hosted arms' own errors (§3.4). | **The annotation, on one rater's reading; unadjudicated.** Top eleven separated by 4 items; 3 items missed by 24–25 of the 26 learned arms, each with a dissenter (the DBpedia-trained arm on one, `qwen_m` and zero-shot `bart_mnli` on another, `bart_mnli` on the third). |
| **Is a pilot enough?** | **No.** 10 of 28 arms (12 of 30 today) tied at the top of the 20-item dev slice; its "pick", `anthropic_l`, is the alphabetically first and is truly **5th of 30**. ρ = 0.701* at 30 arms. | **No usable signal.** 13 of 27 arms tied at the top of the 56-item dev slice (0.9821); the "pick", `anthropic_l`, is the alphabetically first, within noise of the leader but 115× the price of the cheapest tied arm, `gemma_m`. ρ = 0.757* (0.768 at 28 arms). |
| **Fine-tune or pay?** | **Fine-tune, for this corpus's labels; not shown to beat the best paid arm** (`bert_base_ta` vs `anthropic_m`, p = 0.022 against 0.0167). The three share AG News's labels, so they are not independent confirmations. Licences: AG News `unknown`, non-commercial; `bert_base_fy` apache-2.0; `bert_base_ta` and `bert_mini` state none (checked 2026-10-19). | **Fine-tune for cost, not for quality:** 0.9857 at $0 marginal, not separated from the leader (−0.0071; the leader wins 3 items, the fine-tune 1; p = 0.62). One apache-2.0 checkpoint, trained on CC-BY-SA data (ShareAlike); training cost is not in the $0. |

\* Spearman ρ with midranks for ties: dev-slice accuracy against 200-item accuracy over all arms, recomputed from the dev items inside the committed n=200 runs by `check_report_claims.py`. AG News 0.677 at the 28 arms that existed then, 0.701 at today's 30; DBpedia 0.757 at 27, 0.768 at 28. The pilot ρ first published, 0.852 and 0.728, came from dev-slice runs that were never committed (§5). The pick and its true rank are from committed runs. The **dev slice** is the small pilot set run before the full slices — 20 AG News items and 56 DBpedia items, all contained in the measured 200 and 280 (§1).

*How to read this table: every bare score is accuracy on that corpus's slice (0 to 1,
higher is better; 0.9600 = 192 of 200 right). **$/month** is what the provider billed for
the slice, scaled to 1M items a month (`anthropic_m` on AG News: $0.0703 ÷ 200 ×
1,000,000 ≈ $351). A **% figure** is relative accuracy against a reference arm. "Per 10×
cost" is a log-linear fit over the
24 hosted arms (a fit across vendors, not an experiment): the accuracy change per tenfold
rise in price, as a share of the best hosted score. The self-host rows quote the score of
the hosted alias — what the providers served (`llama_m` came from 9 providers on AG News,
`gemma_m` from 13–14) — not a run of the quantised or native weights; no self-hosted LLM
was run here. Latencies are mean ms per item on the machine
named — the 4-core Linux container or the 12-core Mac — so two figures from different
machines are not directly comparable. p-values are sign-flip permutation p from the
Holm family tests in §3; where a threshold is quoted, it is the Holm threshold that p had
to beat.*

#### What these experiments specifically found

1. **AG News: three fine-tunes lead on the point estimate, and only one is separated from most of the field.**
   `bert_base_ta` **0.9600** (438 MB, 76 ms), `bert_base_fy` 0.9500, `bert_mini` 0.9450
   (44 MB, 7 ms) are all ahead of every hosted arm (0.835–0.910). They are three fine-tunes
   of AG News's own labels, two of them by different authors, not three independent tests.
   Holm over m=29: the leader is ahead of all 29 and **separated from 26**; not from the
   other two fine-tunes nor from `anthropic_m` (p = 0.022 vs 0.0167). `bert_base_fy` is
   separated from 23 (not from `openai_l`, `openai_m`, `anthropic_l`, `anthropic_m`);
   `bert_mini` from 16 (not from 11 hosted arms, among them `anthropic_l`, +0.0450,
   p = 0.063). The two bert-base fine-tunes agree on 192 of 200 labels.

2. **The AG News lead lives in 17 items the hosted arms get wrong; on one rater's reading about
   half a learnable convention, about half mislabels.** 17 items are missed by ≥80% of the 24
   hosted arms (19 at 75%, 20 at 70%; `anthropic_m` gets 3 of the 17 right). The fine-tunes
   agree with the gold on 12–14 of them; `anthropic_l` on none. By a single rater, after the
   fact: 8 follow a convention a trained model learns and a zero-shot prompt that states none
   has no reason to — business news about technology companies (HP, IBM, Dell, Sohu,
   Vodafone) filed under `Sci/Tech`; 7 this rater judges mislabels (Olympic results filed as
   `World`); 2 are ambiguous. Of the 14 the leader gets right, 6 are convention, 2 ambiguous,
   6 mislabels. All 17 are listed in §3.4. The 17 are defined by the hosted arms' own errors,
   so a lead concentrated in them is close to built in. On the other 183 items `anthropic_l`
   (0.984) and `bert_base_ta` (0.973) cannot be told apart — discordant items 3 vs 1, exact
   sign p = 0.625. A prompt that stated the convention is untested, and AG News's inline
   syndication tags (§5) are an unexcluded alternative source of the lead; the AG News text
   is not in this repository, so whether the 17 carry them was not checked. **What
   fine-tuning bought here is this corpus's labelling; on your own labels that is the point,
   and as evidence of better reading it is not.**

3. **DBpedia-14: the top group cannot be ranked, and paying more is not shown to help.**
   `qwen_m` led at **0.9929 for $0.0143**; `anthropic_l` was one item in 280 behind at
   **0.9893 for $0.3784**, p = 1.0000 — and that one item is a disputed-gold item (Bharhut,
   filed `Building`: `qwen_m` gets it, `anthropic_l` misses all three disputed items), so
   the leader exists because of one disputed label. The leader separated from only **8 of
   27**; it is not separated from the other **19**, at gaps of 1 to 8 items, and the top
   eleven arms, leader included, sit within four items of each other across a 115× price
   range. One of those eleven costs nothing: the **fine-tuned `bert_base_fy` scores 0.9857
   at $0 marginal**, two items behind the leader (−0.0071, p = 0.62). At n = 280 the
   smallest gap Holm separated from `qwen_m` is 10 items (+0.0357); 8 items (+0.0286,
   `mistral_l`, p = 0.0076 against 0.0026) and 7 items (+0.0250, `qwen_l`, p = 0.0166
   against 0.0028) are not, so a benefit of up to about 3 points from paying cannot be
   ruled out. Where there is no headroom, training bought a place in the top group, not a
   lead.

4. **Both corpora have recurring label noise, and on DBpedia it is the same size as the
   signal.** Items nearly the whole field misses are candidates for a wrong gold label —
   nobody has adjudicated them (§5), and on one rater's reading the field's answer is
   defensible on each: a canal filed under `NaturalPlace`, a "historic school" filed under
   `Building`, an IPO story filed under `World`. The top eleven DBpedia arms are separated by
   four items; three items are missed by 24–25 of the 26 learned arms, and each has a
   dissenter that agrees with the gold: the arm trained on DBpedia on the canal, `qwen_m`
   and zero-shot `bart_mnli` on Bharhut, `bart_mnli` on the school. `qwen_m` and
   `anthropic_l` make no errors outside those three items.

5. **On deployment the two corpora differ.** On AG News a **438 MB** fine-tune is ahead of
   the best self-hostable LLM (Llama-3.3-70B, ~141 GB) by **0.0800 and separated from it**;
   the **44 MB** one is ahead by 0.0650 — a 3,205× size difference — but that gap does not
   survive Holm (p = 0.0149, threshold 0.0063), and it is not separated from `gemma_s`,
   `gemma_l` or `deepseek_l` either. The highest-scoring self-hostable arm is a CPU model
   under half a gigabyte; whether the 44 MB one is better than the open-weight LLMs is a
   point estimate this data does not confirm. On DBpedia the fine-tuned arm — measured
   2026-09-30, once a machine with torch ≥ 2.6 could load it — scores **0.9857 at 438 MB**,
   the same as Gemma-4-26B at 52 GB and GLM-4.6 at 714 GB (those two as served by providers;
   neither was self-hosted here), and like them it is not separated from the overall winner.
   The top group therefore contains a CPU-sized classifier and open-weight models as well as
   the proprietary leader.

6. **The scoring code is a bigger lever than the model choice, for some arms.** The label
   parser is worth 7.5 accuracy points to `glm_l` on AG News and 8.6 on DBpedia — wider than
   the gap separating most of the field.

---

## 1. What was measured

| property | AG News | DBpedia-14 |
| --- | --- | --- |
| task | news snippet → 1 of 4 topics | Wikipedia abstract → 1 of 14 ontology classes |
| measurement slice | 200 items, 50/class — the first 50 per class of the first 1,600 test rows | 280 items, 20/class, seeded |
| dev slice (pilot subset of the measurement slice) | 20 items (first-k per class) | 56 items (seeded-random per class) |
| licence | **`unknown`**, source says non-commercial | **CC-BY-SA 3.0 + GFDL** (ShareAlike) |
| fine-tuned checkpoint licences (Hub pages, 2026-10-19) | `bert_base_fy` apache-2.0; `bert_base_ta` and `bert_mini` state none | `bert_base_fy` apache-2.0 |
| median length | 40 words | 52 words |
| hosted spend (billed) | $0.58 | $1.17 |

All three AG News fine-tunes score higher on the slice than on the full test set (0.9450 vs
0.9338, 0.9600 vs 0.9514, 0.9500 vs 0.9375), so their absolute scores here are optimistic by
0.009–0.0125; the hosted arms were not run on the full set, so the same offset is unmeasured
for them. The slice is not random — the first 50 per class of the first 1,600 rows — so the
offset need not carry to other slices.

Both slices are class-balanced by construction, so the floor is exact: **0.2500** and
**0.0714**. A `constant` arm is run on every slice and reads those values to four decimal
places. It is a calibration check on the harness before it is a baseline on the task — any
other value would mean the slice is unbalanced or the scorer is broken, and no other row
could be trusted.

**Corpora are never redistributed.** Each example ships a download recipe; the fetched
slices are gitignored.

---

## 2. How quality was measured, and what the measures cannot see

**`correct`** — exact label match after parsing. Binary per item, so its mean is accuracy.
This is the ranking metric.

**`macro_f1`** — computed by `classification_report.py`, **not** as a harness metric.
Accuracy can be scored per item and averaged; F1 needs a confusion matrix, which is not a
property of any item. There is no per-item number whose average is macro-F1, so inventing
one would produce a figure with no interpretation sitting in the leaderboard looking
authoritative. This is a limitation of the harness, recorded rather than papered over.

**`parsed`** — classified as *quality*, not descriptive, on the argument that an arm which
cannot be parsed cannot be deployed. It read 1.0 everywhere until DBpedia, where three
arms produced one unparseable answer each — one of them an empty response.

**`correct_after_repair`** — items scored correct **only because the parser was lenient**.
This is the metric that exposes the parser as part of the system under test.

**`confidence`** — reported by local arms only. Hosted arms have none: logprobs were never
requested, which is a gap rather than a choice.

### The parser is part of the system under test

A model answering `Sports`, `Sports.`, `**Sports**` or `This article is about sports` is
right or wrong depending entirely on `_parse_label`. It is hashed into every arm's
fingerprint as `parser_sha256` — including local arms that never touch it, because the
question those hashes answer is *"would this number change if the parser changed?"* and an
identical hash across both kinds is what makes "no" checkable rather than assumed.

How much it matters, measured. The middle column counts items scored correct only because
the parser cleaned the answer up (the raw output was not exactly the gold label); the last
column shows accuracy with the parser, then with exact-match scoring alone:

| arm | corpus | scored correct only via lenient parser (share, count) | accuracy: with parser → without |
| --- | --- | --- | --- |
| `glm_l` | AG News | 0.075 (15 of 200) | 0.860 → **0.785** |
| `glm_l` | DBpedia | 0.086 (24 of 280) | 0.968 → **0.882** |
| `gemma_s` | DBpedia | 0.043 (12 of 280) | 0.975 → **0.932** |

`glm_l` narrates its answers on both label tasks, and the parser is worth 7.5 points to it
on AG News and 8.6 on DBpedia. That is a model property reproduced on two tasks (it also
narrated in summarisation, 4 of 60 outputs, where there is no label to parse; journal
[`NOTES.md`](internal/NOTES.md)), which no single example could claim.

---

## 3. Results

### 3.1 AG News — three fine-tunes, then the field

```
arm                accuracy  macro_f1    $/200     arm              accuracy   $/200
bert_base_ta ◆       0.9600    0.9600   0.0000     glm_l              0.8600   0.0186
bert_base_fy ◆       0.9500    0.9498   0.0000     mistral_m          0.8600   0.0096
bert_mini ◆          0.9450    0.9453   0.0000     glm_m              0.8600   0.0107
anthropic_m          0.9100    0.9106   0.0703     openai_s           0.8600   0.0190
anthropic_l          0.9000    0.8998   0.1750     gemma_m            0.8550   0.0016
openai_m             0.8950    0.8952   0.1272     glm_s              0.8500   0.0027
openai_l             0.8900    0.8900   0.0487     deepseek_m         0.8450   0.0043
qwen_m               0.8850    0.8855   0.0070     deepseek_s         0.8400   0.0014
llama_m              0.8800    0.8791   0.0040     anthropic_s        0.8400   0.0254
mistral_l            0.8750    0.8751   0.0103     llama_l            0.8400   0.0043
gemma_s              0.8750    0.8748   0.0021     llama_s            0.8350   0.0025
qwen_s               0.8750    0.8747   0.0036     ──────────────────────────────────
qwen_l               0.8700    0.8698   0.0164     bart_mnli          0.7000   0
gemma_l              0.8700    0.8696   0.0028     keyword            0.6700   0
deepseek_l           0.8700    0.8681   0.0114     constant           0.2500   0
mistral_s            0.8600    0.8597   0.0019
```

◆ = fine-tuned on AG News, local, $0. `bert_base_ta` (textattack) and `bert_base_fy`
(fabriceyhc) added 2026-09-30: 438 MB each, 76 and 90 ms/item on a 4-core Linux CPU; `bert_mini`
is 44 MB at 7 ms on the 12-core Mac. Re-timed together on the Linux machine (medians,
`harness/data/runs-linux/`): 49, 55 and 4.3 ms. textattack's model card reports 0.9514 on its own eval set; 0.9600 here on
200 items is consistent with it, and both new arms' confusion matrices are diagonal — the
`label_order` the configs assume (`LABEL_0…3` carry no names) is the right one.

**Is the ordering real?** `p = 0.0002`, **Nemenyi CD 3.30** rank positions,
**38 of 435** pairs distinguishable, observed span 10.65 (k=30). Holdout on the 180 items
outside the dev slice: CD 3.48, **35 of 435**.

*This line has been wrong, then absent, then computed, and has now moved with the field. It
first read "CD 3.01, 34 of 378", produced by silently reusing the k=25 critical value for a
28-arm field. Round 2 made the tool refuse above k=25; a round-3 reviewer observed that the
values are about thirty lines of stdlib, and
[`scripts/nemenyi_table.py`](../harness/scripts/nemenyi_table.py) now solves the
studentised-range integral (all 24 of Demšar's published values reproduced to 0.0007). At
k=28 that gave **CD 3.06, 33 of 378**; at k=30, with the two bert-base arms, it is the
figure above.*

**Family test for the new leader** (`bert_base_ta`, Holm over the m=29 others): ahead on
the point estimate against **29 of 29**, separated from **26**. Not separated from
`bert_mini` (+0.0150, p = 0.55), `bert_base_fy` (+0.0100, p = 0.72), or `anthropic_m`
(+0.0500, p = 0.022 against a threshold of 0.0167 — a boundary case). It **is** separated
from `llama_m`, the best self-hostable LLM, which `bert_mini` never was.

**The leader-conditioned test on `bert_mini`** (it led when the family was declared; the
family was fixed before its p-values were read, but the arm was chosen because it led), re-run
at m=29: ahead of 27 of 29, **separated from 16** — down from 18 of 27, and not because
anything about `bert_mini` changed. Two more
arms in the family tighten every Holm threshold, and four comparisons that sat just under
the old thresholds (`gemma_l`, `deepseek_l`, `gemma_s`, `qwen_s`, each p ≈ 0.005) now sit
just over. A count that moves by two when unrelated arms join is a count to quote with its
family size. `bert_mini` is **not separated from 11 hosted arms**: `anthropic_l` (+0.0450,
p = 0.063), `anthropic_m` (+0.0350, p = 0.116), `openai_m` (+0.0500, p = 0.044 against a
threshold of 0.0100), `openai_l`, `qwen_m`, `llama_m`, `mistral_l`, `qwen_s`, `gemma_s`,
`deepseek_l` and `gemma_l` — nor from the other two fine-tunes. `bert_base_fy` (m=29) is
**separated from 23** and ahead on the point estimate against 28; not from `openai_l`
(+0.0600, p and Holm threshold both 0.0083), `openai_m`, `anthropic_l`, `anthropic_m`, nor the other
two fine-tunes.

**Macro-F1** (paired bootstrap, `bert_base_ta` vs the m=29 others): separated from 27, and
only 2 of 29 intervals span zero — the two other fine-tunes. On this metric the leader *does*
separate from `anthropic_m` (+0.0494, p = 0.0104 vs 0.0167); the bootstrap is the more liberal
test (§3.3), so that is an upper bound, not a reversal.

The defensible claim is therefore, as run here (hosted arms zero-shot, one prompt,
temperature 0, reasoning off, no provider pinned): **`bert_base_ta` leads at 0.9600 and is
separated from 26 of the 29 other arms, not from the other two fine-tunes nor from
`anthropic_m`. The three fine-tunes of 44–438 MB are not separated from each other and lead
every hosted arm on the point estimate; `bert_base_fy` (separated from 23) and `bert_mini`
(separated from 16) are not separated from the best paid arms** — all at zero marginal cost
and lower latency (end-to-end per-request time, network included for the hosted arms, not
compute: `bert_mini` 61×–1,078× faster than the hosted field, timed on the same Mac; the two
bert-base fine-tunes roughly 5×–100×, timed on a Linux machine, a cross-machine ratio good to
about a factor of two) — with the qualification in §3.4 about *what* they are better at.

### 3.2 DBpedia-14 — no winner: the leader is not separated from 19 of the 27 others

```
arm                accuracy  macro_f1     $/280    arm              accuracy    $/280
qwen_m               0.9929    0.9929    0.0143    deepseek_m         0.9750    0.0079
anthropic_l          0.9893    0.9892    0.3784    gemma_s            0.9750    0.0035
bert_base_fy ◆       0.9857    0.9856    0.0000    llama_l            0.9750    0.0089
gemma_m              0.9857    0.9856    0.0033    gemma_l            0.9750    0.0046
glm_m                0.9857    0.9856    0.0159    openai_l           0.9750    0.0921
deepseek_l           0.9857    0.9855    0.0209    openai_s           0.9750    0.0360
qwen_s               0.9857    0.9854    0.0072    glm_l              0.9679    0.0359
openai_m             0.9821    0.9820    0.2380    qwen_l             0.9679    0.0342
anthropic_m          0.9821    0.9818    0.1514    mistral_*      0.957–0.964
llama_m              0.9786    0.9783    0.0084    deepseek_s         0.9429    0.0028
anthropic_s          0.9786    0.9782    0.0536    glm_s              0.9393    0.0052
                                                   ─────────────────────────────────
                                                   keyword            0.7071    0
                                                   bart_mnli          0.6286    0
                                                   constant           0.0714    0
```

◆ = fine-tuned on DBpedia-14, local, $0, 87 ms/item on a 4-core Linux CPU (61 ms median). Added 2026-09-30.

`p = 0.0002`, **CD 2.58**, **77 of 378** pairs distinguishable, observed span 12.90
(k=28). Holdout on the 224 items outside the dev slice: CD 2.89, **76 of 378**.

*Before the fine-tuned arm joined, this read "CD 2.48, 74 of 351" at k=27 — and before
that "CD 2.45", from a reused k=25 value, then withdrawn, then computed. Adding an arm
changes every pair count, so the old figures are superseded rather than wrong.*

**Leader-conditioned family test** (`qwen_m`, Holm over m=27; the family was declared before
the p-values were read, the arm was picked because it led): ahead against **27 of 27**,
separated from **8** — so it is not separated from the other **19** (18 paid arms and the
fine-tune; the top eleven arms, within four items of each other, are the head of that group).
Their gaps run from +0.0036 (one item) to +0.0286 (eight items: `mistral_l`, p = 0.0076
against a threshold of 0.0026; `qwen_l` and `glm_l` are seven items behind). Against
`anthropic_l`: delta **+0.0036** — one item in 280 — at **p = 1.0000**. Against the fine-tuned
arm: **+0.0071**, two items, **p = 0.62**.

**The fine-tuned arm, measured.** This row did not exist until 2026-09-30: the checkpoint
ships only a pickle, which `transformers` refuses below torch 2.6, and the machine this
report was written on has no torch above 2.2.2. On Linux it ran unmodified.
`bert_base_fy` from its own side (Holm over m=27): **separated from 5 of 27** — the three
non-LLM floors, `glm_s` and `deepseek_s` — and ahead on the point estimate against 21.
It sits in the block of five arms tied at 0.9857, and in 9% of item resamples it is the
unique leader. **Training on this dataset bought a free seat in the top group; it did not
buy the top.** That is the handover's first scenario, stated before the run: *"if it lands
~0.99 and does not separate from the top group, the AG News finding does NOT generalise:
task-specific training wins where there is headroom and buys nothing where there is
not."*

Its label order was an assumption — the checkpoint's `id2label` is `LABEL_0…13` — and the
confusion matrix confirms it: 276 of 280 on the diagonal, and no off-diagonal band.

**A 115× price difference buys nothing this data can detect,** and neither does $0 lose
anything it can detect (−0.0071 against the leader, p = 0.62). `gemma_m` costs $0.0033, `anthropic_l` $0.3784, the fine-tuned arm nothing, and
all three are within one item of each other.

**What "can detect" means at n = 280.** Against `qwen_m`, Holm separated no gap smaller than
10 items (+0.0357: `mistral_s`, `llama_s`, `mistral_m`). An 8-item gap (+0.0286, `mistral_l`,
p = 0.0076 against a threshold of 0.0026) and a 7-item gap (+0.0250, `qwen_l`, p = 0.0166
against 0.0028) were not separated. So a benefit of paying of up to about 3 points cannot be
ruled out here, and "not separated" in this section means that, not "no difference".

### 3.3 Macro-F1, and why it needed a different test

`family_test.py` cannot take macro-F1 — the sign-flip permutation requires a per-item
value. `bootstrap_test.py` resamples items, scoring both arms on the same draw.

Accuracy can be tested **both** ways, so it was, on the same arm and Holm family:

```
family_test.py     sign-flip permutation, exact null    separated from  8 of 27
bootstrap_test.py  paired percentile bootstrap          separated from 11 of 27
```

The bootstrap is consistently the more liberal — against `anthropic_l`, p = 0.7340 where
the permutation says 1.0000. That is the known behaviour of a percentile bootstrap with
few items and a metric near its ceiling. **A `SEPARATED` verdict from the bootstrap is an
upper bound**, and the permutation test wins wherever it applies.

On macro-F1, where nothing exact exists: `qwen_m` ahead of 27 of 27, separated from at
most 11, and **8 of 27 intervals span zero** — the fine-tuned arm's among them
(+0.0072, interval −0.0064 to +0.0230). Macro-F1 agrees with accuracy that the top group
is not ordered by this data. *(At m=26, before the fine-tuned arm: 11 of 26, 7 spanning
zero, anthropic_l p = 0.7353.)*

### 3.4 Label noise

`classification_report.py` reports items that at least 80% of the *learned* arms got
wrong. A near-universal miss is evidence about the label, not the models.

```
DBpedia   Dukart's Canal            gold NaturalPlace  25/26 → MeanOfTransportation, Building
          Bent County High School   gold Building      25/26 → EducationalInstitution
          Bharhut                   gold Building      24/26 → NaturalPlace, Village

AG News   "Rivals Try to Turn Tables on Charles Schwab"   gold Sci/Tech   26/28 → Business
          "Card fraud unit nets 36,000 cards"             gold Sci/Tech   26/28 → Business
          "Google Lowers Its IPO Price Range"             gold World      25/28 → Business
          "Stocks Climb on Drop in Consumer Prices"       gold World      25/28 → Business
          "Live: Olympics day four … gold for GB"         gold World      25/28 → Sports
```

The field's answer is defensible on all three; the gold may be wrong on each, and nobody has
adjudicated them (§5). **On DBpedia the top eleven arms are separated by four items in total
and three items are missed by 24–25 of the 26 learned arms: the noise floor and the signal are
the same size.** Any ranking inside that group ranks which model best reproduces the corpus's
ontology quirks, and this data cannot say whether it also ranks which classifies better.
Nor is the field unanimous: `qwen_m` and zero-shot `bart_mnli` side with the gold on Bharhut,
`bart_mnli` on the school. **`qwen_m` leads `anthropic_l` by exactly one disputed item**
(Bharhut, missed by 24 of 26); `qwen_m`'s only two errors are the other two disputed items
and `anthropic_l` misses all three, so the leader exists because of one disputed label.

**The fine-tuned arm is the one that "gets" Dukart's Canal** — it files a canal under
`NaturalPlace`, as the corpus does and as no LLM in the field did. That is not
skill: it is having been trained on DBpedia's labels, including the odd ones. It misses
the other two disputed items like everyone else. Its only other two errors are borderline
rather than wrong in any interesting way — a "physician, novelist and politician" filed as
`Artist` (gold `OfficeHolder`), a joke book transcribed from album tracks filed as `Album`
(gold `WrittenWork`) — and they are exactly the two items it scored below 0.8 confidence.

#### Where the AG News fine-tuned lead comes from

The two AG News items named above — "Charles Schwab" and "Card fraud" — were "missed by
26/26" before the bert-base arms ran. The two arms that now get them right are both
bert-base fine-tunes. That is not a coincidence, and it is worth measuring rather than
noting:

```
17 items that ≥80% of the 24 hosted arms get "wrong"

arm              overall   agrees with gold on the 17   accuracy on the other 183
bert_base_ta      0.9600            14 of 17                    0.9727
bert_base_fy      0.9500            13 of 17                    0.9672
bert_mini         0.9450            12 of 17                    0.9672
anthropic_m       0.9100             3 of 17                    0.9781
anthropic_l       0.9000             0 of 17                    0.9836
llama_m           0.8800             0 of 17                    0.9617
```

**The fine-tuned lead lives in those 17 items** — `bert_base_ta` is 11 items ahead of
`anthropic_m` on them and 1 item behind on the other 183. That concentration is close to built
in: the 17 are defined by the hosted arms' own errors, so an arm that disagrees with them wins
there by construction. On the other 183 the arms cannot be told apart: `bert_base_ta`
alone correct on 1 item against `anthropic_l` alone on 3 (exact sign p = 0.625), against
`anthropic_m` 1 vs 2 (p = 1.0). The set depends on the cut: 17 items at ≥80% of the hosted
arms wrong, 19 at 75%, 20 at 70%. All 17, so the reading below can be checked rather than
taken on trust (the corpus is not redistributed; these are headlines only). The fourth column
lists which of the three fine-tunes (`ta` = `bert_base_ta`, `fy` = `bert_base_fy`, `mini` =
`bert_mini`) agree with the gold label; "—" means none of them does. "Field's majority" is
the label most of the 24 hosted arms chose. Rows are grouped by the reading, which is mine —
a single rater, after the fact, with no second reading: convention, then ambiguous, then
mislabel.

| headline | gold | field's majority | fine-tunes agreeing with gold | reading |
|---|---|---|---|---|
| Storage, servers bruise HP earnings update | Sci/Tech | Business | ta fy mini | convention |
| Some People Not Eligible to Get in on Google IPO | Sci/Tech | Business | fy | convention |
| Consumers Would Pay In Phone Proposal | Sci/Tech | Business | ta fy mini | convention |
| IBM to hire even more new workers | Sci/Tech | Business | ta mini | convention |
| Spam suspension hits Sohu.com shares | Sci/Tech | Business | ta fy mini | convention |
| Vodafone hires Citi for Cesky bid | Sci/Tech | Business | ta fy mini | convention |
| IBM Buys Two Danish Services Firms | Sci/Tech | Business | mini | convention |
| Dell Exits Low-End China Consumer PC Market | Sci/Tech | Business | ta mini | convention |
| Card fraud unit nets 36,000 cards | Sci/Tech | Business | ta fy | ambiguous |
| Rivals Try to Turn Tables on Charles Schwab | Sci/Tech | Business | ta fy | ambiguous |
| China cracks down on "phone sex" services | Sci/Tech | World | ta fy mini | mislabel |
| Live: Olympics day four | World | Sports | ta fy mini | mislabel |
| U.S. Misses Cut in Olympic 100 Free | World | Sports | ta fy mini | mislabel |
| Oil prices bubble to record high | World | Business | — | mislabel |
| India's Tata expands regional footprint via NatSteel buyout | World | Business | ta fy | mislabel |
| Stocks Climb on Drop in Consumer Prices | World | Business | ta fy mini | mislabel |
| Google Lowers Its IPO Price Range | World | Business | ta fy mini | mislabel |

- **8 follow a convention.** Business news *about technology and telecoms companies* is
  filed under `Sci/Tech` — HP, IBM twice, Dell, Sohu, Vodafone, Google, a phone-fee
  proposal. A model trained on AG News learns that; a zero-shot LLM, asked for the topic,
  says Business — defensibly.
- **7 this rater judges mislabels:** Olympic results filed under `World`, a stock-market
  report and an oil-price record under `World`, a Chinese crackdown on phone-sex lines under
  `Sci/Tech`.
- **2 are ambiguous** — a card-fraud unit's arrests and a discount broker's rivals fit
  neither label well. (An earlier version of this section put Charles Schwab in the
  convention group without saying it was arguable.)

**Three cautions about the table.** The "other 183" column is selected by the hosted arms'
own errors, so it flatters them by construction — and even so it shows no separable difference, not a
reversal; it does *not* show that LLMs are more accurate readers of news. "Agrees with gold"
on a mislabel is not a virtue. And the prompt (`prompt.txt`) gives no `Sci/Tech`-versus-
`Business` convention, so the convention gap is partly a prompt gap; a prompt with label
definitions or examples is untested here. The defensible reading is narrower and more useful:
**the fine-tuned arms lead AG News by reproducing AG News's labelling, conventions and
mistakes included.** For a classifier trained on *your* labels, reproducing your conventions
is the whole point, so the production advice stands. As a claim that a 44 MB model
understands news better than the hosted LLMs as run here, it does not. The inline syndication
tags (§5) are a further unexcluded route to the lead: whether the 17 carry them was not
checked, because the AG News text is not in this repository (the fetched slices are
gitignored and none was downloaded for this review).

This is the in-distribution caveat [`HANDOVER_CLASSIFICATION_AG_NEWS.md`](internal/HANDOVER_CLASSIFICATION_AG_NEWS.md)
was corrected to state, now with a number on it. `bert_mini` alone could not show it
clearly — it was one arm; three fine-tunes (all trained on AG News's labels, two of them by
different authors) agreeing with the gold where 24 LLMs agree with each other is a pattern,
though not three independent tests of it.

### 3.5 Calibration

```
arm             mean conf   accuracy    ECE    verdict
bert_mini          0.957      0.945    0.025   well calibrated
bert_base_ta (AGN) 0.986      0.960    0.035   slightly overconfident; 1 item below 0.6
bert_base_fy (AGN) 0.989      0.950    0.039   slightly overconfident; 1 item below 0.6
bert_base_fy (DBP) 0.997      0.986    0.012   well calibrated; both items <0.8 were its errors
bart_mnli (AGN)    0.572      0.700    0.128   underconfident
bart_mnli (DBP)    0.317      0.629    0.311   badly underconfident
```

`bert_mini`'s 186 items above 0.8 confidence were 96.2% correct (179); its 6 items below 0.6
were coin flips (3 correct), and the 8 between 0.6 and 0.8 were 7 correct. Of its 11 errors, 7
sit above 0.8, so routing everything under 0.8 to something dearer sends 14 items to catch
4 of the 11 errors. **That is what makes a cheap classifier usable as a first pass** — its
confidence is honest on average (ECE 0.025) — but it is a partial router, not a reliable "I
am not sure". The bert-base arms are more accurate and
*less* useful for routing on AG News: they put 195–197 of 200 items above 0.8, so there is
almost nothing for a confidence threshold to catch.

The zero-shot arm is systematically *under*-confident, and worse as the label count grows.
On DBpedia its 0.4–0.6 bucket was **96.8% correct** and its 0.6–0.8 bucket **100%**.
Zero-shot NLI normalises entailment scores across candidate labels, so with 14 candidates
the probability mass spreads thin however certain the model is. The raw score is an
excellent ranking signal and is **not** a probability.

### 3.6 How much data does a ranking need?

```
                  arms tied 1st, by items per half
n/half        10      20      50     100
DBpedia     19.9    16.2     9.1     4.8    saturated throughout (k=28)
AG News      9.1     3.8     1.6     1.3    ties fall below 2 by n=50, the winner still does not repeat (k=30)
CNN/DM       1.0     1.0     1.0     1.0    continuous metric, never ties
```

`rank_stability` initially reported DBpedia's `P(same winner)` as **0.94 at n=10 falling to
0.28 at n=100** — backwards. The cause: `sorted` is stable and arms are alphabetical, so
tied arms are ordered by *name*, and at n=10 nearly all 27 arms score 10/10. The statistic
was measuring the alphabet.

**FIXED 2026-09-29, and the corrected numbers are below.** Two bugs, not one. `spearman()`
used `1 - 6*sum(d^2)/(n(n^2-1))`, an algebraic shortcut for Pearson-on-ranks that is an
identity only when every rank is distinct — against tied data it does not approximate rho,
it computes a different quantity. And `ranks_on()` handed every arm a distinct integer, so
ties were broken alphabetically before the correlation ever saw them. Now: midranks for
ties, and rho as Pearson-on-ranks.

`P(same winner)` is also redefined, because the old one could not be salvaged: a draw
counts only when **both** halves have a *unique* best arm. Draws where either half's top is
tied are reported as **undecided** and excluded, never scored as agreement.

Each column is the number of items per half; every cell averages 400 draws of two disjoint
halves. "(was)" rows are the figures published before the 2026-09-29 fix; "(fixed)" rows
are the same field re-measured after it. "Undecided" counts draws, out of 400, in which at
least one half had no unique best arm, so no winner could be compared; P(same winner) is
computed over the remaining, decided draws. k is the number of arms in the field. **Bold
row labels** mark the current field (AG News k=30, DBpedia k=28); the other rows are
superseded and kept for comparison.

| corpus · quantity (arms k) | n=10 | n=20 | n=50 | n=100 |
|---|---|---|---|---|
| AG News · ρ (was) | 0.492 | 0.470 | 0.540 | 0.675 |
| AG News · ρ (fixed, k=28) | 0.403 | 0.453 | 0.548 | 0.715 |
| AG News · undecided draws (k=28) | 361/400 | 316/400 | 173/400 | 34/400 |
| AG News · P(same winner), of decided (k=28) | 0.74 | 0.77 | 0.78 | 0.97 |
| **AG News · ρ (k=30, with the bert-base arms)** | 0.410 | 0.502 | 0.621 | 0.768 |
| **AG News · undecided draws (k=30)** | 395/400 | 373/400 | 257/400 | 210/400 |
| **AG News · P(same winner), of decided (k=30)** | 0.20 | 0.41 | 0.21 | 0.24 |
| DBpedia · ρ (was) | 0.782 | 0.709 | 0.671 | 0.742 |
| DBpedia · ρ (fixed, k=27) | 0.667 | 0.602 | 0.616 | 0.713 |
| **DBpedia · ρ (k=28, with the fine-tuned arm)** | 0.657 | 0.600 | 0.605 | 0.706 |
| **DBpedia · undecided draws (k=28)** | 399/400 | 391/400 | 379/400 | 354/400 |
| **DBpedia · P(same winner), of decided (k=28)** | 0.00 | 0.00 | 0.00 | 0.00 |

**DBpedia has no winner to agree about, at any size tested.** At k=27 every one of 400
draws at every n had at least one half with no unique best arm. Adding the fine-tuned arm
breaks a few ties — 1 to 46 draws per size now have a unique best arm in *both* halves —
and in **every one of them the two halves crowned different arms**. More arms at the top
did not produce a winner; it produced more ways to disagree about one. The old 0.94 was
the alphabet reporting itself as consensus.

AG News's rho *falls* where ties dominate (n=10, n=20) and *rises* where they clear
(n=50, n=100) — the correction is not a uniform shift, because the old formula was not
wrong by a constant.

**AG News's winner stopped being stable when the bert-base arms arrived.** At k=28 two
independent 100-item halves crowned the same arm 97% of the time: `bert_mini` was far enough
ahead to win both. At k=30 it is **24%**, and 210 of 400 draws have a tied top. Three
fine-tunes within 0.015 of each other means the halves crown different ones — the same
thing that happened to summarisation when `bart_l` arrived level with `deepseek_m`. ρ rose
while P(same winner) collapsed: the ordering got more consistent and the winner got less.

**The summarisation report is unaffected.** Re-measured on identical data, old and new
agree to ±0.000 at every n on `cnn_dailymail_200`, and to ≤0.002 on `few_nerd_280` — both
continuous metrics where ties essentially never occur, which is the check that the fix is
sound rather than merely different. An earlier version of this paragraph claimed fixing
this *would* change [`REPORT_SUMMARIZATION.md`](REPORT_SUMMARIZATION.md) §3.6. It does not.

---

## 4. Discussion

**The two corpora disagree, and that is the finding.** On AG News, task-specific training
led — on this corpus's labels (§3.4), against zero-shot hosted arms as run here — and the
price tiers spread over 7.5 points. On DBpedia, everything above 0.97 is not separated from
the leader and the cheapest paid arm in it costs 1/115 of the dearest; the fine-tuned arm in it costs nothing. A practitioner
reading only the first would buy a fine-tuned model; reading only the second, the cheapest
API. **Which is right may turn on whether the task has headroom. Two corpora, each on one
slice, show a pattern and cannot show that it is the cause; headroom is cheap to measure and
almost never measured.**

**On AG News the fine-tune's lead is concentrated in the corpus's labelling; on DBpedia it is
level with the top group.** On AG News the best fine-tune is 0.050 ahead of the best paid arm
(10 items, p = 0.022 against a threshold of 0.0167 — not separated at this n, on the
boundary), and that lead sits in items the corpus's labels reward (§3.4). On DBpedia it is two
items behind the leader and not separated (−0.0071, p = 0.62), inside the top group, not
above it. On neither corpus is a fine-tune separated from the best paid arm; on both it
costs less to run. The pair is consistent with headroom deciding whether training buys
quality, and it always bought the price, but that is two corpora, not a mechanism.

**Label noise is not a curiosity.** It sets a ceiling no arm can cross, and it
preferentially rewards the arm trained on those labels. This paragraph used to say that
*part* of `bert_mini`'s lead *may* be having learned that the corpus thinks an IPO story is
`World`. With three fine-tunes it is measured (§3.4): the fine-tuned lead on AG News is
concentrated in 17 items the hosted field mostly gets wrong — by a single rater's reading 8 a
learnable convention, 7 that this rater judges mislabels, 2 ambiguous. That is not classifying news, and it
transfers only to data labelled the same way — which, for a model trained on your own labels,
is your data. A prompt that stated the convention might close part of the gap; it was not
run.

---

## 5. What this experiment cannot say

- **Whether a *different* DBpedia fine-tune would clear the top group.** One was measured
  (`fabriceyhc/bert-base-uncased-dbpedia_14`, 2026-09-30, on Linux — no DBpedia-14
  fine-tune loads on x86_64 macOS, because the whole 2021–2023 cohort ships pickles only).
  One checkpoint is not the cohort, and the top eleven are separated by four items, three of
  them disputed labels; a RoBERTa or a newer fine-tune could land one item higher or lower
  and nothing here would say which.
- **How much of each arm's error is irreducible.** Doing that properly means adjudicating
  the disputed items against fresh human judgement. Nobody has — and since the AG News
  fine-tuned lead is concentrated in 17 such items, that adjudication would decide how much
  of the lead is convention (defensible) and how much is memorised mislabels (not). The
  split here (8 / 7 / 2) is one rater's, after the fact.
- **The pilot ρ values, from committed data.** The ρ first published, 0.852 (AG News) and
  0.728 (DBpedia), came from dev-slice runs that were never committed and cannot be checked
  from this repository. Ranking the dev items *inside* the committed n=200 runs by accuracy,
  ties given midranks, gives 0.677 and 0.757 on the field as it stood then (28 and 27 arms)
  and 0.701 and 0.768 on today's 30 and 28; `check_report_claims.py` recomputes all four from
  the runs. The ρ matters less than the tie at the top of the dev slice: 10 of 28 arms (12 of
  30) on AG News's 20 items, 13 of 27 on DBpedia's 56. The pilot's "pick", `anthropic_l` in
  both, is the alphabetically first of the tied arms, so it was a tie-break, not a
  measurement. The two methods need not agree.
- **Hosted run-to-run variance.** Every arm was run once; no AG News or DBpedia re-run
  exists. On DBpedia the top eleven are 1–4 items apart and `qwen_m`'s one-item lead over
  `anthropic_l` is a disputed item, so a re-run could move any of those positions by an item
  or two. Unmeasured.
- **What "fine-tune" assumes here.** The three AG News checkpoints are public ones whose
  cards name AG News as the training data (checked 2026-10-19); only `bert_base_fy`'s card
  fixes the size, 74,250 steps at batch size 8 — five epochs over 118,800 rows, 99% of the
  120,000-row training split — and the `bert_base_ta` and `bert_mini` cards give no row
  count. How the arms behave with fewer labels, what training cost, and what hosting costs
  were not measured; "$0" is the marginal cost of running a local checkpoint. The DBpedia
  checkpoint is one (`bert_base_fy`, 346,500 steps at batch size 8, five epochs over 99% of
  the 560,000-row split) under apache-2.0, trained on CC-BY-SA 3.0 data (ShareAlike).
- **How far the AG News slice scores generalise.** The fine-tunes score 0.009–0.0125 higher
  on the slice than on the full test set (§1); the hosted offset is unmeasured and the
  slice is the first 50 per class of the first 1,600 rows, not a random draw.
- **Whether a prompt with label definitions or examples changes the AG News gap.** The
  prompt (`prompt.txt`) states no `Sci/Tech`-versus-`Business` convention and the hosted arms
  ran zero-shot, so the convention part of the fine-tuned lead is partly a prompt gap. Untested.
- **Which provider served an open-weight arm.** No provider was pinned. Distinct providers
  across the 200 AG News requests: `deepseek_s` 16, `deepseek_m` 13, `gemma_m` 13,
  `deepseek_l` 12, `gemma_l` 10, `llama_m` 9; a single provider each for the OpenAI, Qwen and
  Mistral `m`/`l` arms, and per arm for Anthropic. Scores are as those providers served the
  models, not as a pinned or self-hosted build would score.
- **Contamination.** Both are public benchmarks; whether any arm saw them in training is
  unmeasured.
- **Whether hosted arms are calibrated.** Logprobs were never requested.
- **Anything about a corpus you care about.** Both are public benchmarks with known
  quirks, and AG News carries its syndication tags (`(AP)`, `(Reuters)`, `(SPACE.com)`)
  inline, which correlate with the label. A fine-tune can learn the tags as a shortcut; a
  zero-shot prompt is not told to. Whether the fine-tuned lead uses them was not measured:
  the AG News text is not in this repository (the slices are gitignored) and none was downloaded.

---

## 6. Corrections

**Updated 2026-09-30 with the three fine-tuned arms that could not run on the original
machine** (`ag_bert_base_ta`, `ag_bert_base_fy`, `db_bert_base_fy` — pickle checkpoints,
which need torch ≥ 2.6). They moved both verdicts: AG News has a new leader, whose lead
turns out to be concentrated in 17 items the hosted field mostly gets wrong; DBpedia's
fine-tuned arm is not separated from the top group rather than beating it. Old figures are
named where they changed. Until 2026-09-30 the DBpedia half of the discussion read "cannot be
tested": the checkpoint would not load on the machine this was written on.

**Corrected 2026-10-19.** Until 2026-10-19 this report said the three AG News fine-tunes
were "ahead of every hosted arm, and clearly separated from all but one", that the lead
was "mostly label convention", and that the models are "right in every case" on the
disputed items. Only `bert_base_ta` is separated from all but `anthropic_m`;
`bert_base_fy` is separated from 23 of the 29 other arms and `bert_mini` from 16. The
lead is concentrated in 17 items, about half convention and half mislabels by a single
rater, and nobody has adjudicated them. The "pre-registered" test was a leader-conditioned
one. Added: the as-run conditions, provider spread, licences, the slice's provenance.

**Executive summary rewritten 2026-10-19 after an independent review.** What changed:
the rented-API pick on AG News was `anthropic_m` at $351 as the best-scoring paid arm and the
only one the leader could not separate; that is a statement about the leader, and
`anthropic_m` itself is separated from only 6 of 29 arms (3 of the 23 other hosted arms), so
the pick now follows one rule in both columns (highest point estimate, then the cheapest
hosted arm it is not separated from, with the gap).
`bert_base_ta` was shown as "1st of 30" with the other two fine-tunes not separated from it
(`bert_base_fy`, p = 0.72); the default is now `bert_mini`, 11× faster and not separated from
it. "No difference" on the other 183 items became "cannot be told apart". "Three
independent fine-tunes" became three fine-tunes of the same labels. "7 plain mislabels" and
"mislabels by any reading" became "this rater judges mislabels". The DBpedia pilot was
described as ρ = 0.757 and "picked `anthropic_l`" without saying that 13 of 27 arms tied and
the pick was the alphabetically first. The DBpedia rented-API pick named `qwen_m` ($51) and
not the cheapest arm in the top group (`gemma_m`, ~$12). "A 115× price difference bought
nothing measurable" and "training bought a tie" lacked the smallest gap the test can detect
(10 items at n = 280). "Fine-tuning leads where there is room, and ties where there is not"
and "headroom decides whether training buys quality" were stronger than two corpora allow.
"$0" was not labelled as marginal cost. The label parser was said to be worth 8.6 points on
AG News (it is 7.5; 8.6 is DBpedia), and "7.5, 8.6 and 8.6 points" for summarisation, AG
News and DBpedia was wrong in order and, for summarisation, in kind: there is no label to
parse there. "Both corpora have systematic label noise" rested on a handful of items and one
rater's reading and now says "recurring". "Chosen before any result was seen" was wrong for
DBpedia, which was chosen after the AG News result and before any DBpedia result.
The banner "should not be read one at a time" became the summary's last paragraph.

**History moved out of the summary table, 2026-10-19.** Before the bert-base arms joined,
the best paid arm was 3.7% below the free arm and `anthropic_l` 4.8% below `bert_mini`
(now 5.2% and 6.3% against `bert_base_ta`); the AG News pilot's pick was truly 3rd of 28 (now 5th of 30); the leader's tie group was
9 of 26 around `bert_mini` (now 3 of 29 around `bert_base_ta`); on DBpedia the leader was
not separated from 18 of 26 before the fine-tuned arm joined, and the fine-tuned arm joined
them. The prior from AG News — that a fine-tune would lead on DBpedia too — did not hold.

**This report revised a finding already published — twice.** The AG News result was written
up before the label-noise diagnostic existed; the ranking survived, the interpretation did
not. Then the bert-base arms showed the fine-tuned lead concentrated in the items the hosted
field disputes, not just a caveat beside it.

**`rank_stability`'s DBpedia row was backwards until 2026-09-29.** It reported
`P(same winner)` of 0.94 at n=10 falling to 0.28 at n=100, because tied arms were ordered by
name and the statistic measured the alphabet. Fixed with midranks and an undecided-draws
count; §3.6 has the corrected figures, in which no DBpedia draw size produces a winner the
two halves agree on.

**The AG News result was published before the label-noise diagnostic existed.** Its
handover reported 0.9450 with an in-distribution caveat and no mention of label noise.
The ranking stands; the interpretation was corrected in place with the old reading named
rather than replaced. See [`HANDOVER_CLASSIFICATION_AG_NEWS.md`](internal/HANDOVER_CLASSIFICATION_AG_NEWS.md)
and [`NOTES.md`](internal/NOTES.md) entry 48.

**`parser_sha256` was described as unexercised machinery** in the first classification
commit, when 3 of 24 arms had been tried. It is worth 8.6 points to one arm. Entry 47.

**`rank_stability`'s AG News row was read at face value** in entry 47; its n=10 figure had
9.5 arms tied, so only n=50 and n=100 were ever trustworthy there. Entry 50.

**"A 44MB model beat 24 frontier LLMs" was not established** (2026-09-30, entry 59, which
called it "true and incomplete"; corrected 2026-10-19). `bert_mini` led all 24 hosted arms on
the point estimate and was never separated from all of them: at m=29 it is separated from 16
of 29, not from `anthropic_l` (+0.0450, p = 0.063), `anthropic_m` or `openai_m`. The 24 span
small, mid and large tiers, not only frontier models. Two larger fine-tunes of the same kind,
run once a machine could load them, took 1st and 2nd on the point estimate; and the three
together showed the lead is concentrated in items the hosted field mostly gets wrong.
`bert_mini`'s leader-conditioned separation count also moved, 18 of 27 → 16 of 29, purely
because the family grew — no measurement of `bert_mini` changed. Both old figures are
named in §3.1 rather than replaced. Until 2026-10-19 this report also called that test
"pre-registered"; the arm was chosen because it led.

---

## 7. Reproduction

```bash
cd examples/classification-ag-news && uv sync --extra local
uv run fetch.py --n 200 && uv run fetch.py --n 20

cd ../classification-dbpedia-14 && uv sync --extra local
uv run fetch.py --n 280 && uv run fetch.py --n 56

cd ../../harness
PY=../examples/classification-dbpedia-14/.venv/bin/python
$PY scripts/classification_report.py --dataset-id dbpedia_280
$PY scripts/family_test.py    --dataset-id dbpedia_280 --a db_qwen_m_n200_v1 --against _n200_v1 --metric correct
$PY scripts/bootstrap_test.py --dataset-id dbpedia_280 --a db_qwen_m_n200_v1 --against _n200_v1 --metric macro_f1
$PY scripts/rank_stability.py --dataset-id dbpedia_280 --metric correct
$PY scripts/family_test.py    --dataset-id dbpedia_280 --a db_bert_base_fy_n200_v1 --against _n200_v1 --metric correct

PY=../examples/classification-ag-news/.venv/bin/python
$PY scripts/classification_report.py --dataset-id ag_news_200
$PY scripts/family_test.py    --dataset-id ag_news_200 --a ag_bert_base_ta_n200_v1 --against _n200_v1 --metric correct
$PY scripts/family_test.py    --dataset-id ag_news_200 --a ag_bert_mini_n200_v1    --against _n200_v1 --metric correct
$PY scripts/bootstrap_test.py --dataset-id ag_news_200 --a ag_bert_base_ta_n200_v1 --against _n200_v1 --metric macro_f1
$PY scripts/holdout_significance.py --dataset-id ag_news_200 --exclude-dataset ag_news_20 --metric correct
```

The three bert-base arms need torch ≥ 2.6 (`uv sync --extra local` resolves 2.14 everywhere
except x86_64 macOS). Their checkpoints ship only a pickle on `main`; each also has a
safetensors conversion PR on the Hub (`refs/pr/1`), which loads on torch 2.2.2 and gives
byte-identical outputs on every item for all three (`docs/evidence/conversion_pr_check.py`) — see [`KNOWN_ISSUES.md`](internal/KNOWN_ISSUES.md).

The `ag_news_200` and `dbpedia_280` runs are committed (metrics, predictions and
outputs, since 2026-09-29), so these commands run against the same bytes the report was
written from. The corpora are not committed — rebuild them with each example's
`fetch.py` first (DBpedia's is seeded; AG News's takes the first 50 per class, deterministic without a seed), or `rescore.py` refuses. The datasets are frozen by `items_sha256`, and
`make dataset-materialize` verifies a refetch against them.

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

The figures below are corrected to what the provider billed. Rankings by *quality* are
untouched — cost was never an input to them.

**Fixed at cause:** all four adapters now record `usage.cost` when the provider supplies
it and fall back to the table only when it is silent. Runs made before that fix keep the
estimate in `cost_usd`; the billed figure is in `_meta.usage.cost` in each stored run, and
these corrections were computed from it.
