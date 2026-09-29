# Evaluation report — 24 LLMs, a 44MB classifier and a regex on two classification tasks

**Datasets** `ag_news_200` · 200 news snippets · 4 classes — and `dbpedia_280` · 280 Wikipedia abstracts · 14 classes
**Arms** 24 hosted models (8 vendors × 3 price tiers), plus a fine-tuned classifier, a zero-shot NLI model, ~20 regex rules and a constant
**Design** 1 pass per arm · identical prompt, temperature 0, reasoning off · **$0.58 and $1.17 billed** ($0.45 and $1.25 by the price table — see Correction)
**Date** 2026-09-28 · **Harness** [`../harness`](../harness) · **Journal** [`NOTES.md`](NOTES.md) entries 47–50

> **This report covers two corpora on purpose, and should not be read one at a time.**
> They were chosen to sit in opposite statistical regimes. Either alone would have
> supported whichever conclusion it happened to produce; the disagreement between them is
> the result.


> **This is one of five experiments.** What all five agree on — and the four
> places they disagree with the conventional reading of a leaderboard — is in
> [`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).

---

## Executive summary

**On a task with headroom, a 44MB model beat 24 frontier LLMs. On a saturated task, a 115×
price difference bought nothing measurable. Same harness, same arms, same statistics.**

1. **AG News.** `bert_mini` — 44MB, fine-tuned, $0, 7 ms/item — scored **0.9450** and was
   ahead of all 24 hosted arms, whose field spanned 0.835–0.910. Holm over a family of 27
   declared in advance: ahead of 27 of 27, **separated from 18**. Not separated from the
   top six. A group, not a podium.

2. **DBpedia-14.** `qwen_m` led at **0.9929 for $0.0143**; `anthropic_l` was one item in
   280 behind at **0.9893 for $0.3784**, p = 1.0000. The leader separated from only **8 of
   26**. The top ten arms are one group across a 115× price range.

3. **Both corpora have systematic label noise, and on DBpedia it is the same size as the
   signal.** Items the entire field gets "wrong" are items whose gold label is wrong: a
   canal filed under `NaturalPlace`, a "historic school" filed under `Building`, an IPO
   story filed under `World`. The top ten DBpedia arms are separated by four items; three
   items are disputed by all 25 learned arms.

4. **This revised a finding already published.** The AG News result was written up before
   the label-noise diagnostic existed. The ranking survived; the interpretation did not.

5. **The scoring code is a bigger lever than the model choice, for some arms.** The label
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

### 3.1 AG News — a winner, and a group behind it

```
arm                accuracy  macro_f1    $/200     arm              accuracy   $/200
bert_mini            0.9450    0.9453   0.0000     mistral_s          0.8600   0.0099
anthropic_m          0.9100    0.9106   0.1054     glm_l              0.8600   0.0092
anthropic_l          0.9000    0.8998   0.1750     mistral_m          0.8600   0.0096
openai_m             0.8950    0.8952   0.0345     glm_m              0.8600   0.0032
openai_l             0.8900    0.8900   0.0636     openai_s           0.8600   0.0069
qwen_m               0.8850    0.8855   0.0043     gemma_m            0.8550   0.0015
llama_m              0.8800    0.8791   0.0026     glm_s              0.8500   0.0013
mistral_l            0.8750    0.8751   0.0124     deepseek_m         0.8450   0.0030
gemma_s              0.8750    0.8748   0.0015     deepseek_s         0.8400   0.0021
qwen_s               0.8750    0.8747   0.0012     anthropic_s        0.8400   0.0254
qwen_l               0.8700    0.8698   0.0083     llama_l            0.8400   0.0038
gemma_l              0.8700    0.8696   0.0022     llama_s            0.8350   0.0017
deepseek_l           0.8700    0.8681   0.0057     ──────────────────────────────────
                                                   bart_mnli          0.7000   0
                                                   keyword            0.6700   0
                                                   constant           0.2500   0
```

**Is the ordering real?** `p = 0.0002`, Nemenyi CD 3.01, **34 of 378** pairs
distinguishable. On the 180 items the dev slice does not contain: 29 of 378.

**Pre-registered family test** (`bert_mini` vs all others, Holm over m=27 named before the
p-values were read): ahead on the point estimate against **27 of 27**, separated from
**18**. Not separated from `anthropic_m` (p = 0.1164), `anthropic_l` (0.0630), `openai_m`,
`openai_l`, `qwen_m`, `llama_m`.

The defensible claim is therefore: **a 44MB classifier is statistically indistinguishable
from the best frontier models and clearly better than the other 18, at zero marginal cost
and 270× lower latency.**

### 3.2 DBpedia-14 — no winner, a group of ten

```
arm                accuracy  macro_f1     $/280    arm              accuracy    $/280
qwen_m               0.9929    0.9929    0.0089    deepseek_m         0.9750    0.0061
anthropic_l          0.9893    0.9892    0.3780    gemma_s            0.9750    0.0029
gemma_m              0.9857    0.9856    0.0030    llama_l            0.9750    0.0076
glm_m                0.9857    0.9856    0.0065    gemma_l            0.9750    0.0043
deepseek_l           0.9857    0.9855    0.0117    openai_l           0.9750    0.1190
qwen_s               0.9857    0.9854    0.0024    openai_s           0.9750    0.0128
openai_m             0.9821    0.9820    0.0634    glm_l              0.9679    0.0176
anthropic_m          0.9821    0.9818    0.2272    qwen_l             0.9679    0.0173
llama_m              0.9786    0.9783    0.0054    mistral_*      0.957–0.964
anthropic_s          0.9786    0.9782    0.0536    deepseek_s         0.9429    0.0042
                                                   glm_s              0.9393    0.0026
                                                   ─────────────────────────────────
                                                   keyword            0.7071    0
                                                   bart_mnli          0.6286    0
                                                   constant           0.0714    0
```

`p = 0.0002`, CD 2.45, **74 of 351** pairs distinguishable. Holdout on the 224 items
outside the dev slice: identical, 74 of 351.

**Pre-registered family test** (`qwen_m`, Holm over m=26): ahead against **26 of 26**,
separated from **8**. Against `anthropic_l`: delta **+0.0036** — one item in 280 — at
**p = 1.0000**.

**A 115× price difference buys nothing this data can detect.** `gemma_m` costs $0.0033 and
`anthropic_l` $0.3784, and they differ by one item.

### 3.3 Macro-F1, and why it needed a different test

`family_test.py` cannot take macro-F1 — the sign-flip permutation requires a per-item
value. `bootstrap_test.py` resamples items, scoring both arms on the same draw.

Accuracy can be tested **both** ways, so it was, on the same arm and Holm family:

```
family_test.py     sign-flip permutation, exact null    separated from  8 of 26
bootstrap_test.py  paired percentile bootstrap          separated from 11 of 26
```

The bootstrap is consistently the more liberal — against `anthropic_l`, p = 0.7353 where
the permutation says 1.0000. That is the known behaviour of a percentile bootstrap with
few items and a metric near its ceiling. **A `SEPARATED` verdict from the bootstrap is an
upper bound**, and the permutation test wins wherever it applies.

On macro-F1, where nothing exact exists: `qwen_m` ahead of 26 of 26, separated from at
most 11, and **7 of 26 intervals span zero**. Macro-F1 agrees with accuracy that the top
group is not ordered by this data.

### 3.4 Label noise

`classification_report.py` reports items that at least 80% of the *learned* arms got
wrong. A near-universal miss is evidence about the label, not the models.

```
DBpedia   Dukart's Canal            gold NaturalPlace  25/25 → MeanOfTransportation, Building
          Bent County High School   gold Building      24/25 → EducationalInstitution
          Bharhut                   gold Building      23/25 → NaturalPlace, Village

AG News   "Rivals Try to Turn Tables on Charles Schwab"   gold Sci/Tech   26/26 → Business
          "Card fraud unit nets 36,000 cards"             gold Sci/Tech   26/26 → Business
          "Google Lowers Its IPO Price Range"             gold World      25/26 → Business
          "Stocks Climb on Drop in Consumer Prices"       gold World      25/26 → Business
          "Live: Olympics day four … gold for GB"         gold World      25/26 → Sports
```

The models are right in every case. **On DBpedia the top ten arms are separated by four
items in total and three items are disputed by the entire field: the noise floor and the
signal are the same size.** Any ranking inside that group ranks which model best
reproduces the corpus's ontology quirks.

### 3.5 Calibration

```
arm             mean conf   accuracy    ECE    verdict
bert_mini          0.957      0.945    0.025   well calibrated
bart_mnli (AGN)    0.572      0.700    0.128   underconfident
bart_mnli (DBP)    0.317      0.629    0.311   badly underconfident
```

`bert_mini`'s 186 items above 0.8 confidence were 96.2% correct; its 6 items below 0.6
were coin flips. **That is what makes a cheap classifier deployable** — a reliable "I am
not sure" you can route to something dearer.

The zero-shot arm is systematically *under*-confident, and worse as the label count grows.
On DBpedia its 0.4–0.6 bucket was **96.8% correct** and its 0.6–0.8 bucket **100%**.
Zero-shot NLI normalises entailment scores across candidate labels, so with 14 candidates
the probability mass spreads thin however certain the model is. The raw score is an
excellent ranking signal and is **not** a probability.

### 3.6 How much data does a ranking need?

```
                  arms tied 1st, by items per half
n/half        10      20      50     100
DBpedia     19.8    16.9    10.0     5.1    saturated throughout
AG News      9.5     4.4     1.6     1.1    clears by n=50
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
| **AG News** ρ (fixed) | **0.403** | **0.453** | **0.548** | **0.715** |
| AG News undecided draws | 361/400 | 316/400 | 173/400 | 34/400 |
| AG News P(same winner), of decided | 0.74 | 0.77 | 0.78 | 0.97 |
| **DBpedia** ρ (was) | 0.782 | 0.709 | 0.671 | 0.742 |
| **DBpedia** ρ (fixed) | **0.667** | **0.602** | **0.616** | **0.713** |
| DBpedia undecided draws | **400/400** | **400/400** | **400/400** | **400/400** |
| DBpedia P(same winner) | — | — | — | — |

**DBpedia has no winner to agree about, at any size tested.** In 400 of 400 draws at every
n, at least one half had no unique best arm. The honest value is undefined, and the old
0.94 was the alphabet reporting itself as consensus.

AG News's rho *falls* where ties dominate (n=10, n=20) and *rises* where they clear
(n=50, n=100) — the correction is not a uniform shift, because the old formula was not
wrong by a constant.

**The summarisation report is unaffected.** Re-measured on identical data, old and new
agree to ±0.000 at every n on `cnn_dailymail_200`, and to ≤0.002 on `few_nerd_280` — both
continuous metrics where ties essentially never occur, which is the check that the fix is
sound rather than merely different. An earlier version of this paragraph claimed fixing
this *would* change [`REPORT_SUMMARIZATION.md`](REPORT_SUMMARIZATION.md) §3.6. It does not.

---

## 4. Discussion

**The two corpora disagree, and that is the finding.** On AG News, task-specific training
won decisively and the price tiers spread over 7.5 points. On DBpedia, everything above
0.97 is one group and the cheapest arm in it costs 1/126 of the dearest. A practitioner
reading only the first would buy a fine-tuned model; reading only the second, the cheapest
API. **Which is right depends entirely on whether the task has headroom — and that is
cheap to measure and almost never measured.**

**Fine-tuning wins where there is room and cannot be tested where there is not.** The
DBpedia fine-tuned arm could not be run at all (§5), so the strongest version of the
comparison exists on one corpus only.

**Label noise is not a curiosity.** It sets a ceiling no arm can cross, and it
preferentially rewards the arm trained on those labels. `bert_mini` was fine-tuned on AG
News including its wrong labels, so part of its lead may be having learned that the corpus
thinks an IPO story is `World` — which is not classifying news and does not transfer.

---

## 5. What this experiment cannot say

- **Whether a fine-tuned model beats LLMs on DBpedia.** No credible DBpedia-14 fine-tune
  loads on x86_64 macOS: fabriceyhc, Danni, kundank and TheChickenAgent are all
  `pytorch_model.bin` only, 2021–2023 uploads predating safetensors. Not one unlucky
  checkpoint — the whole cohort.
- **How much of each arm's error is irreducible.** Doing that properly means adjudicating
  the disputed items against fresh human judgement. Nobody has.
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
```

Runs are gitignored and live on one machine. The datasets are frozen by `items_sha256`,
and `make dataset-materialize` verifies a refetch against them.

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
price table was wrong **per arm by 0.67× to 3.21×, in both directions**.

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
