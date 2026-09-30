# Evaluation report — 24 LLMs, four fine-tuned classifiers and a regex on two classification tasks

**Datasets** `ag_news_200` · 200 news snippets · 4 classes — and `dbpedia_280` · 280 Wikipedia abstracts · 14 classes
**Arms** 24 hosted models (8 vendors × 3 price tiers), plus fine-tuned classifiers (three on AG News, one on DBpedia), a zero-shot NLI model, ~20 regex rules and a constant
**Design** 1 pass per arm · identical prompt, temperature 0, reasoning off · **$0.58 and $1.17 billed** ($0.49 and $1.00 by the price table — see Correction)
**Date** 2026-09-28; the three bert-base arms added 2026-09-30 · **Harness** [`../harness`](../harness) · **Journal** [`NOTES.md`](NOTES.md) entries 47–50, 59

> **Updated 2026-09-30 with the three fine-tuned arms that could not run on the original
> machine** (`ag_bert_base_ta`, `ag_bert_base_fy`, `db_bert_base_fy` — pickle checkpoints,
> which need torch ≥ 2.6). They moved both verdicts: AG News has a new leader, whose lead
> turns out to live almost entirely in items with disputed gold labels; DBpedia's
> fine-tuned arm ties the top group rather than beating it. Old figures are named where
> they changed.

> **This report covers two corpora on purpose, and should not be read one at a time.**
> They were chosen to sit in opposite statistical regimes. Either alone would have
> supported whichever conclusion it happened to produce; the disagreement between them is
> the result.


> **This is one of five experiments.** What all five agree on — and the four
> places they disagree with the conventional reading of a leaderboard — is in
> [`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).

---

## Executive summary

### The decision, in one table

| the choice | AG News (headroom) | DBpedia-14 (saturated) |
|---|---|---|
| **Self-host · small ML** | **`bert_base_ta`** — BERT-base fine-tuned on AG News, **438 MB**, 76 ms/item on CPU. **0.9600 — 1st of 30**, separated from 26 of the 29 others. But **`bert_mini`** (44 MB, 7 ms) scores 0.9450 and is **not separated** from it (p = 0.55): ten times smaller and faster for no measurable loss. **Read §3.4 before relying on either** — the fine-tuned lead lives in items whose gold labels the whole LLM field disputes. | **`bert_base_fy`** — BERT-base fine-tuned on DBpedia-14, **438 MB**, 87 ms/item on CPU. **0.9857 — tied 3rd**, two items in 280 behind the leader and **not separated** from it (p = 0.62). Ties the top; does not clear it. |
| **Self-host · open-weight LLM, absolute** | **`llama_m`** — Llama-3.3-70B, **70.6B / ~141 GB**. **0.8800** — **0.0800 behind a 438 MB fine-tune and separated from it**; 0.0650 behind the 44 MB one (**3,205× smaller**) and **not separated** from that (p = 0.0149 vs a 0.0063 threshold at m=29). | **`glm_m`** — GLM-4.6, MIT, **357B / ~714 GB**. **0.9857**, **not separated** from the overall winner. Needs a multi-node cluster. |
| **Self-host · open-weight LLM, ≤128 GB** | **The same model at int8, ~70 GB.** 0.8800 — no loss on paper. Native alternative: `gemma_s` (27B, 55 GB) at 0.8750. | **`gemma_m`** — Gemma-4-26B-A4B, **52 GB native**. **0.9857 — identical to GLM-4.6 at 1/14 the size.** |
| **Self-host · open-weight LLM, ≤64 GB** | **The same model at int4, ~35 GB.** 0.8800 on paper. Native alternative: `gemma_s` at 55 GB, 0.8750 — and still **0.0700 below a 44 MB fine-tune.** | **Still `gemma_m`**, 52 GB native. Halving the budget costs nothing here. |
| **Deploy — rented API** | **`anthropic_m`** at **$351/month per 1M items**, 0.9100 — **5.2% worse than free** (3.7% before the bert-base arms). The only paid arm the new leader cannot separate from (p = 0.022 vs 0.0167). | **`qwen_m`** at **$51/month**, **0.9929** — the best score here, and **proprietary: no self-host option at any price**. |
| **What should I not deploy?** | `anthropic_l` at $875/mo: **−6.3%** vs free (was −4.8% against `bert_mini`) | `anthropic_l` at **$1,351/mo**: **−0.4%** vs $51/mo |
| **Does paying more help?** | Marginally: **+2.3%** per 10× cost | **Barely: +0.9%** per 10× cost |
| **Arms tied at the top?** | **3 of the 29 others** — two fine-tunes and `anthropic_m` (was 9 of 26 around `bert_mini`) | **19 of the 27 others** (was 18 of 26 before the fine-tuned arm joined, and it joined the tie) — the ranking is mostly noise |
| **What limits the score?** | **the annotation, more than it looked.** 17 items are disputed by ≥80% of the hosted field; the fine-tunes agree with the gold on 12–14 of them, the best hosted arms on 0–3 | **the annotation.** Top ten separated by 4 items, 3 disputed by the whole field |
| **Is a pilot enough?** | No — ρ = 0.852 and it picked `anthropic_l`, truly **5th of 30** (3rd before the bert-base arms) | No — ρ = 0.728, picked `anthropic_l`, truly 2nd |
| **Fine-tune or pay?** | **Fine-tune — for this corpus's labels.** Three independent fine-tunes take 1st, 2nd and 3rd of 30 at $0. What they learned is partly AG News's labelling convention (§3.4): on your own data that is exactly what you want; as evidence that a small model "understands news" better than an LLM, it is not. | **Fine-tune for cost, not for quality.** Measured 2026-09-30: the fine-tuned arm scores **0.9857**, statistically tied with the $51/mo leader (−0.0071, 1 item won against 3 lost, p = 0.62) at **$0**. On a saturated task training buys a free seat in the top group, not a lead. The prior from AG News — that it would win — **did not hold.** |

**Read the two together or not at all.** They were chosen before any result was seen to
sit in opposite regimes; either alone supports whichever conclusion it happens to produce.

**On deployment, the two corpora disagree here too.** On AG News a **438 MB** fine-tune is
ahead of the best self-hostable LLM (Llama-3.3-70B, ~141 GB) by **0.0800 and separated
from it**; the **44 MB** one is ahead by 0.0650 — a 3,205× size difference — but that gap
does not survive Holm (p = 0.0149, threshold 0.0063). Either way the answer is a CPU model
under half a gigabyte, not an LLM. On DBpedia the fine-tuned arm — measured 2026-09-30, once a machine
with torch ≥ 2.6 could load it — scores **0.9857 at 438 MB**, exactly what **Gemma-4-26B
scores at 52 GB and GLM-4.6 at 714 GB**, and like them it is not separated from the overall
winner. So DBpedia now has a $0 answer at every size: a 438 MB classifier on a CPU, or a
52 GB open-weight LLM. Neither needs a proprietary model.

*Cross-cutting context for all five experiments:
[`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).*

### What these experiments specifically found


**On a task with headroom, three small fine-tuned models took the top three places from 24
frontier LLMs — largely by agreeing with the corpus's labels where every LLM disagreed. On a
saturated task, a 115× price difference bought nothing measurable, and neither did
fine-tuning: it bought a tie at $0. Same harness, same arms, same statistics.**

1. **AG News.** Three independent fine-tunes lead: `bert_base_ta` **0.9600** (438 MB, 76 ms),
   `bert_base_fy` 0.9500, `bert_mini` 0.9450 (44 MB, 7 ms) — all ahead of every hosted arm,
   whose field spans 0.835–0.910. The leader, Holm over m=29: ahead of all 29, **separated
   from 26**; not from the other two fine-tunes nor from `anthropic_m` (p = 0.022 vs 0.0167).
   The two bert-base fine-tunes, by different authors, agree on 192 of 200 labels.

2. **The AG News lead is mostly label convention.** 17 items are called "wrong" by ≥80% of
   the 24 hosted arms. The fine-tunes agree with the gold on 12–14 of them; `anthropic_l`
   on none. About half follow a convention a trained model learns and a zero-shot one has no
   reason to — business news about technology companies (HP, IBM, Dell, Sohu, Vodafone)
   filed under `Sci/Tech`; the rest are plain mislabels (Olympic results filed as `World`).
   On the other 183 items the order reverses — `anthropic_l` 0.984, `bert_base_ta` 0.973 —
   though that cut is selected by the hosted arms' own errors and so flatters them. **What
   fine-tuning bought here is this corpus's labelling; on your own labels that is the point,
   and as evidence of better reading it is not.**

3. **DBpedia-14.** `qwen_m` led at **0.9929 for $0.0143**; `anthropic_l` was one item in
   280 behind at **0.9893 for $0.3784**, p = 1.0000. The leader separated from only **8 of
   27**. The top eleven arms are one group across a 115× price range — and one of them
   costs nothing: the **fine-tuned `bert_base_fy` scores 0.9857 at $0**, two items behind
   the leader, p = 0.62. Where there is no headroom, training buys a tie, not a win.

4. **Both corpora have systematic label noise, and on DBpedia it is the same size as the
   signal.** Items the entire field gets "wrong" are items whose gold label is wrong: a
   canal filed under `NaturalPlace`, a "historic school" filed under `Building`, an IPO
   story filed under `World`. The top eleven DBpedia arms are separated by four items;
   three items are disputed by 24–25 of the 26 learned arms — and where one of those items
   has a dissenter that agrees with the gold, it is the arm trained on DBpedia.

5. **This revised a finding already published — twice.** The AG News result was written up
   before the label-noise diagnostic existed; the ranking survived, the interpretation did
   not. Then the bert-base arms made the label noise measurable as the *source* of the
   fine-tuned lead, not just a caveat beside it.

6. **The scoring code is a bigger lever than the model choice, for some arms.** The label
   parser is worth 8.6 accuracy points to `glm_l` — wider than the gap separating most of
   the field.

---

## 1. What was measured

| | AG News | DBpedia-14 |
| --- | --- | --- |
| task | news snippet → 1 of 4 topics | Wikipedia abstract → 1 of 14 ontology classes |
| measurement slice | 200 items, 50/class | 280 items, 20/class |
| dev slice | 20 items (first-k per class) | 56 items (seeded-random per class) |
| licence | **`unknown`**, source says non-commercial | **CC-BY-SA 3.0 + GFDL** |
| median length | 40 words | 52 words |
| hosted spend (billed) | $0.58 | $1.17 |

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

How much it matters, measured:

| arm | corpus | `correct_after_repair` | accuracy without the parser |
| --- | --- | --- | --- |
| `glm_l` | AG News | 0.075 (15 of 200) | 0.860 → **0.785** |
| `glm_l` | DBpedia | 0.086 (24 of 280) | 0.968 → **0.882** |
| `gemma_s` | DBpedia | 0.043 (12 of 280) | 0.975 → **0.932** |

`glm_l` narrates on every corpus tried — summarisation, AG News, DBpedia — worth 7.5, 8.6
and 8.6 points. That is a model property reproduced across three independent tasks, which
no single example could claim.

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
(fabriceyhc) added 2026-09-30: 438 MB each, 76 and 90 ms/item on CPU; `bert_mini` is
44 MB at 7 ms. textattack's model card reports 0.9514 on its own eval set; 0.9600 here on
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

**The pre-registered test on `bert_mini`**, re-run at m=29: ahead of 27 of 29, **separated
from 16** — down from 18 of 27, and not because anything about `bert_mini` changed. Two more
arms in the family tighten every Holm threshold, and four comparisons that sat just under
the old thresholds (`gemma_l`, `deepseek_l`, `gemma_s`, `qwen_s`, each p ≈ 0.005) now sit
just over. A count that moves by two when unrelated arms join is a count to quote with its
family size.

**Macro-F1** (paired bootstrap, `bert_base_ta` vs the m=29 others): separated from 27, and
only 2 of 29 intervals span zero — the two other fine-tunes. On this metric the leader *does*
separate from `anthropic_m` (+0.0494, p = 0.0104 vs 0.0167); the bootstrap is the more liberal
test (§3.3), so that is an upper bound, not a reversal.

The defensible claim is therefore: **three fine-tuned classifiers of 44–438 MB are
statistically indistinguishable from each other, ahead of every hosted arm, and clearly
separated from all but one of them, at zero marginal cost and 20–270× lower latency** —
with the qualification in §3.4 about *what* they are better at.

### 3.2 DBpedia-14 — no winner, a group of eleven

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

◆ = fine-tuned on DBpedia-14, local, $0, 87 ms/item on CPU. Added 2026-09-30.

`p = 0.0002`, **CD 2.58**, **77 of 378** pairs distinguishable, observed span 12.90
(k=28). Holdout on the 224 items outside the dev slice: CD 2.89, **76 of 378**.

*Before the fine-tuned arm joined, this read "CD 2.48, 74 of 351" at k=27 — and before
that "CD 2.45", from a reused k=25 value, then withdrawn, then computed. Adding an arm
changes every pair count, so the old figures are superseded rather than wrong.*

**Pre-registered family test** (`qwen_m`, Holm over m=27): ahead against **27 of 27**,
separated from **8**. Against `anthropic_l`: delta **+0.0036** — one item in 280 — at
**p = 1.0000**. Against the fine-tuned arm: **+0.0071**, two items, **p = 0.62**.

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
anything. `gemma_m` costs $0.0033, `anthropic_l` $0.3784, the fine-tuned arm nothing, and
all three are within one item of each other.

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

The models are right in every case. **On DBpedia the top ten arms are separated by four
items in total and three items are disputed by the entire field: the noise floor and the
signal are the same size.** Any ranking inside that group ranks which model best
reproduces the corpus's ontology quirks.

**The fine-tuned arm is the one that "gets" Dukart's Canal** — it files a canal under
`NaturalPlace`, as the corpus does and as no LLM in the field did. That is not
skill: it is having been trained on DBpedia's labels, including the odd ones. It misses
the other two disputed items like everyone else. Its only other two errors are borderline
rather than wrong in any interesting way — a "physician, novelist and politician" filed as
`Artist` (gold `OfficeHolder`), a joke book transcribed from album tracks filed as `Album`
(gold `WrittenWork`) — and they are exactly the two items it scored below 0.8 confidence.

#### Where the AG News fine-tuned lead comes from

The two AG News arms named above — "Charles Schwab" and "Card fraud" — were "missed by
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

**Almost the entire fine-tuned lead lives in those 17 items.** Reading them, they split in
two:

- **About half follow a convention.** Business news *about technology companies* is filed
  under `Sci/Tech`: HP's earnings, IBM's hiring, Dell leaving China's consumer market, Sohu
  shares, Vodafone's Czech bid, Charles Schwab's rivals. A model trained on AG News learns
  that; a zero-shot LLM, asked for the topic, says Business — defensibly.
- **The rest are mislabels.** Two Olympic results filed under `World`; "Stocks Climb on
  Drop in Consumer Prices" under `World`; Google cutting its IPO price range under
  `World`; a Chinese crackdown on phone-sex lines under `Sci/Tech`.

**Two cautions about the table.** The "other 183" column is selected by the hosted arms'
own errors, so it flatters them by construction — it does *not* show that LLMs are more
accurate readers of news. And "agrees with gold" on a mislabel is not a virtue. The
defensible reading is narrower and more useful: **the fine-tuned arms win AG News by
reproducing AG News's labelling, conventions and mistakes included.** For a classifier
trained on *your* labels, reproducing your conventions is the whole point, so the
production advice stands. As a claim that a 44 MB model understands news better than a
frontier LLM, it does not.

This is the in-distribution caveat [`HANDOVER_CLASSIFICATION_AG_NEWS.md`](HANDOVER_CLASSIFICATION_AG_NEWS.md)
was corrected to state, now with a number on it. `bert_mini` alone could not show it
clearly — it was one arm; three independent fine-tunes agreeing with the gold where 24
LLMs agree with each other is a pattern.

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

`bert_mini`'s 186 items above 0.8 confidence were 96.2% correct; its 6 items below 0.6
were coin flips. **That is what makes a cheap classifier deployable** — a reliable "I am
not sure" you can route to something dearer. The bert-base arms are more accurate and
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
AG News      9.1     3.8     1.6     1.3    clears by n=50 (k=30)
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

| | n=10 | n=20 | n=50 | n=100 |
|---|---|---|---|---|
| **AG News** ρ (was) | 0.492 | 0.470 | 0.540 | 0.675 |
| **AG News** ρ (fixed, k=28) | 0.403 | 0.453 | 0.548 | 0.715 |
| AG News undecided draws (k=28) | 361/400 | 316/400 | 173/400 | 34/400 |
| AG News P(same winner), of decided (k=28) | 0.74 | 0.77 | 0.78 | 0.97 |
| **AG News** ρ (k=30, with the bert-base arms) | **0.410** | **0.502** | **0.621** | **0.768** |
| AG News undecided draws (k=30) | 395/400 | 373/400 | 257/400 | 210/400 |
| AG News P(same winner), of decided (k=30) | 0.20 | 0.41 | 0.21 | **0.24** |
| **DBpedia** ρ (was) | 0.782 | 0.709 | 0.671 | 0.742 |
| **DBpedia** ρ (fixed, k=27) | 0.667 | 0.602 | 0.616 | 0.713 |
| **DBpedia** ρ (k=28, with the fine-tuned arm) | **0.657** | **0.600** | **0.605** | **0.706** |
| DBpedia undecided draws (k=28) | **399/400** | **391/400** | **379/400** | **354/400** |
| DBpedia P(same winner), of decided (k=28) | 0.00 | 0.00 | 0.00 | 0.00 |

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
won decisively — on this corpus's labels (§3.4) — and the price tiers spread over 7.5
points. On DBpedia, everything above 0.97 is one group and the cheapest paid arm in it costs
1/115 of the dearest; the fine-tuned arm in it costs nothing. A practitioner
reading only the first would buy a fine-tuned model; reading only the second, the cheapest
API. **Which is right depends entirely on whether the task has headroom — and that is
cheap to measure and almost never measured.**

**Fine-tuning wins where there is room, and ties where there is not.** Until 2026-09-30
the DBpedia half of this sentence read "cannot be tested": the fine-tuned checkpoint would
not load on the machine this was written on. Run elsewhere, it lands exactly where the
headroom argument says it should — inside the top group, not above it. On AG News the
best fine-tune is 0.050 clear of the best paid arm; on DBpedia it is two items behind it and
statistically level. **Same kind of model, same kind of training, opposite verdicts on
"better" — and the same verdict on "cheaper".** The comparison now exists on both corpora,
and it says headroom decides whether training buys quality; it always buys the price.

**Label noise is not a curiosity.** It sets a ceiling no arm can cross, and it
preferentially rewards the arm trained on those labels. This paragraph used to say that
*part* of `bert_mini`'s lead *may* be having learned that the corpus thinks an IPO story is
`World`. With three fine-tunes it is measured (§3.4): the fine-tuned lead on AG News sits
almost entirely in 17 items the LLM field disputes, half of them a learnable convention and
half plain mislabels. That is not classifying news, and it transfers only to data labelled
the same way — which, for a model trained on your own labels, is your data.

---

## 5. What this experiment cannot say

- **Whether a *different* DBpedia fine-tune would clear the top group.** One was measured
  (`fabriceyhc/bert-base-uncased-dbpedia_14`, 2026-09-30, on Linux — no DBpedia-14
  fine-tune loads on x86_64 macOS, because the whole 2021–2023 cohort ships pickles only).
  One checkpoint is not the cohort, and the top ten are separated by four items, three of
  them disputed labels; a RoBERTa or a newer fine-tune could land one item higher or lower
  and nothing here would say which.
- **How much of each arm's error is irreducible.** Doing that properly means adjudicating
  the disputed items against fresh human judgement. Nobody has — and since the AG News
  fine-tuned lead now rests on 17 such items, that adjudication would decide how much of
  the lead is convention (defensible) and how much is memorised mislabels (not).
- **The pilot ρ values, from committed data.** ρ = 0.852 (AG News) and 0.728 (DBpedia)
  came from dev-slice runs that were never committed. Recomputing the dev ranking from the
  dev items *inside* the committed n=200 runs gives 0.677 and 0.757, with a 10- to 13-way
  tie at the top of the dev slice. The two methods need not agree, but the published
  figures cannot be checked from this repository.
- **Whether hosted arms are calibrated.** Logprobs were never requested.
- **Anything about a corpus you care about.** Both are public benchmarks with known
  quirks, and AG News carries its syndication tags (`(AP)`, `(Reuters)`, `(SPACE.com)`)
  inline, which correlate with the label.

---

## 6. Corrections

**The AG News result was published before the label-noise diagnostic existed.** Its
handover reported 0.9450 with an in-distribution caveat and no mention of label noise.
The ranking stands; the interpretation was corrected in place with the old reading named
rather than replaced. See [`HANDOVER_CLASSIFICATION_AG_NEWS.md`](HANDOVER_CLASSIFICATION_AG_NEWS.md)
and [`NOTES.md`](NOTES.md) entry 48.

**`parser_sha256` was described as unexercised machinery** in the first classification
commit, when 3 of 24 arms had been tried. It is worth 8.6 points to one arm. Entry 47.

**`rank_stability`'s AG News row was read at face value** in entry 47; its n=10 figure had
9.5 arms tied, so only n=50 and n=100 were ever trustworthy there. Entry 50.

**"A 44MB model beat 24 frontier LLMs" was true and incomplete** (2026-09-30, entry 59).
Two larger fine-tunes of the same kind, run once a machine could load them, took 1st and
2nd; and the three together showed the lead is mostly agreement with disputed gold labels.
`bert_mini`'s pre-registered separation count also moved, 18 of 27 → 16 of 29, purely
because the family grew — no measurement of `bert_mini` changed. Both old figures are
named in §3.1 rather than replaced.

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
identical predictions — see [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).

The `ag_news_200` and `dbpedia_280` runs are committed (metrics, predictions and
outputs, since 2026-09-29), so these commands run against the same bytes the report was
written from. The corpora are not committed — rebuild them with each example's seeded
`fetch.py` first, or `rescore.py` refuses. The datasets are frozen by `items_sha256`, and
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
