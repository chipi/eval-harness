# Evaluation report — 24 LLMs and two NER models on Few-NERD

**Dataset** `few_nerd_280` · 280 Wikipedia-derived sentences · 768 gold entities · 8 coarse types
**Protocol** supervised test split, 280 of 37,648 sentences, seeded · metric is ours (mean per-sentence F1, coarse types, string match); standard micro-F1 in §2 · calibration: `span_marker`, standard fine-type micro-F1, 0.7047 vs 0.7040 published, inside its own bootstrap 95% interval (±0.016) — [docs/PROTOCOL.md](../docs/PROTOCOL.md#extraction--few-nerd)
**Arms** 24 hosted models (8 vendors × 3 price tiers) · 1 fine-tuned span tagger · 1 zero-shot span tagger · 2 non-learned baselines
**Design** 1 pass per arm · one zero-shot prompt for every hosted arm (bare type names, no definitions, no examples), temperature 0, reasoning off, `max_tokens` 600, no provider pinned (OpenRouter routed the open-weight arms across many providers; `gemma_m` across 13) · Few-NERD is public, contamination unmeasured (§7) · **$2.61 billed** ($2.05 by the price table — see Correction)
**Date** 2026-09-28 · **Harness** [`../harness`](../harness) · **Journal** [`NOTES.md`](internal/NOTES.md)

> **The third metric shape.** Summarisation compares one text to one text and scores
> continuously. Classification compares one label to one label and scores 0 or 1.
> Extraction compares a **set** to a **set**, and every interesting decision is in how the
> members are matched. This report is as much about what that shape does to the
> methodology as about which model won.


> **This is one of six experiments.** What all six agree on — and where they disagree
> with the conventional reading of a leaderboard — is in
> [`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).

---

## Executive summary

### The decision, in one table

| the choice | what the data says |
|---|---|
| **Self-host · small ML** | **`span_marker`** — SpanMarker fine-tuned on this corpus, CC-BY-SA-4.0, **499 MB**, CPU, 0.76 s/item. **0.7674 — separated from all 27 other arms** (the 24 hosted, `gliner`, `capitalized`, `nothing`), the only unambiguous winner in this repo, as run here. |
| **Self-host · open-weight LLM, by point estimate** | **`gemma_m`** — Gemma-4-26B-A4B, Apache-2.0, **25.8B parameters / ~52 GB of weights**. **0.6733** as served by 13 OpenRouter providers (not run locally) — **0.0941 worse** than a tagger with **103× less download size** (≈207× fewer parameters: 25.8B against the tagger's 124.75M). The clearest ML-beats-LLM result in the set, as run here. |
| **Self-host · open-weight LLM, ≤128 GB** | **The same model, on weight size alone.** 52 GB of weights fits 128 GB with room to spare; KV cache and runtime memory were not measured and nothing was run locally. |
| **Self-host · open-weight LLM, ≤64 GB** | **The same model on weight size alone**: 52 GB of weights leaves 12 GB of a 64 GB box for KV cache and runtime. Nothing was run on a 64 GB machine, so whether it fits in practice is untested. The score is the served model's — **and it trails a 499 MB tagger by 0.0941.** |
| **Deploy — rented API** | **`openai_m`** is best by point estimate: **$2,324/month per 1M items**, 0.6864 — **10.6% below free** and 2× slower. It is not separated from seven other hosted arms, up to 0.0383 F1 behind it (`gemma_l`: p = 0.0084 against a Holm threshold of 0.0071); `gemma_m` is 74× cheaper (≈$32/month) at a +0.0131 gap (p = 0.43). The data does not choose between them. There is no reason to rent unless you cannot run a 499 MB model. |
| **What should I not deploy?** | `anthropic_l` — the **most expensive arm in the set**, **$2,463/month per 1M items**, scoring **11.4% below free**; 0.0066 behind the cheaper `openai_m` (p = 0.67, not separated, §3.3) and 78× the price of `gemma_m` for a +0.0065 point-estimate gap (not tested pairwise). |
| **Does paying more help?** | **A little, and not enough.** Across the 24 hosted arms a log-linear fit gives **+0.0407 F1 per 10× in cost** (r = 0.50, 95% Fisher interval 0.13 to 0.75) — 5.9% of the best hosted arm's F1, 5.3% of `span_marker`'s. It is a cross-vendor association, confounded with vendor, not a measure of what paying buys. It is the steepest absolute slope of the six experiments, though SummEval's is larger as a share of its best score ([synthesis](REPORT_SYNTHESIS.md)) — and the free tagger still beats every paid arm. |
| **How much of the win is real?** | **Against `openai_m`, 57% of its margin is one entity type** (`other`; 30–57% across the 24 hosted arms, for a prompt that defines no type), and **up to 38% of its lead** disappears if the 34 labels 80% of the field rejects are resolved the field's way (19–34% against the next three hosted arms; 7–53% across thresholds 90% to 70%) — an upper bound, and the voters share zero-shot priors. On `person`, three hosted arms edge it by 0.004–0.007 (untested). |
| **Is a pilot enough?** | Here yes — ρ = 0.895 over the 27 arms measured at the time (0.903 with all 28, §3.8), right winner. Across experiments, it was wrong in 3 of the 4 others that ran a pilot (a count from the [synthesis](REPORT_SYNTHESIS.md), not a result of this run). |
| **Fine-tune or pay?** | **Fine-tune, if you have labelled data — as run here.** `span_marker` (fine-tuned on the training split) scores 0.7674 against 0.6864 for the best of 24 zero-shot hosted arms, at $0; an LLM given definitions or examples was not run. The zero-shot control `gliner` (0.4540, +0.3134 F1 behind) differs in training exposure and in architecture, so that gap is exposure plus architecture, split unmeasured (§3.5); the case for fine-tuning rests on `span_marker` beating the LLMs, not on it. |

*How to read this table.* Scores are **mean per-sentence F1** over 280 sentences (0–1,
higher is better; §2). **Free** = `span_marker`, self-hosted at $0. **% below free** is the
relative gap: (0.7674 − the arm's score) / 0.7674. **$/month per 1M items** = what the
provider billed for the 280 sentences, scaled to one million items a month.
**Separated** = a paired sign-flip permutation test on per-sentence F1, Holm-corrected
over the declared family of 27 opponents at α = 0.05 (§3.2).

*Cross-cutting context for all six experiments:
[`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).*

### What this experiment specifically found


**In this run, a free 499 MB tagger fine-tuned on Few-NERD scored 0.7674 and separated from
all 27 other arms — 24 hosted LLMs run once, zero-shot, on one prompt of bare type names (no
definitions, no examples), temperature 0, reasoning off, provider unpinned — scored on 8
coarse types by string match. It is the first unambiguous winner in this repo. Against
`openai_m`, 57% of its lead is one catch-all type, `other`, that the prompt never defined;
on `person`, three hosted arms edge it. How much of the lead is training exposure is not
isolated.**

**On deployment:** this is the task where a small model wins by the widest margin. The
best open-weight LLM you could self-host by point estimate, Gemma-4-26B at 52 GB of weights,
scores **0.6733** — **103× the download size** of `span_marker` (≈207× the parameters:
25.8B against 124.75M) and **0.0941 worse**. Nothing was run on a 64 GB machine: 52 GB is
weights only, before KV cache and runtime, and the 0.6733 is the model as 13 OpenRouter
providers served it. On weight size alone it fits a 64 GB box; whether it runs there is
untested.

1. **An actual winner, not a group.** `span_marker` scored **0.7674** against a hosted
   field of 0.524–0.686. Holm step-down over a family of 27 declared in advance:
   **separated from all 27 other arms** (the 24 hosted, plus `gliner`, `capitalized` and
   `nothing`). Neither classification corpus produced this — AG News's
   leader is tied with three other arms, DBpedia's with nineteen (counts per
   [`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md), after the 2026-09-30 fine-tune runs).

2. **And behind it, the familiar tie.** The best hosted arm, `openai_m` at 0.6864,
   separates from 16 of the 23 other hosted arms (20 of the 27 opponents once `span_marker`,
   `gliner`, `capitalized` and `nothing` are counted). The seven it cannot separate from span
   `gemma_m` at **$0.0088** to `anthropic_l` at **$0.6897** — a **78× price range**, with
   gaps of 0.0066 to 0.0383 F1 that these 280 sentences cannot resolve: not shown different,
   not shown equal. DBpedia's figure was 115×. Two unrelated tasks, the same shape.

3. **The lead is concentrated in one label, and the prompt never defined it.** Broken down
   by type, `span_marker` beats `openai_m` by +0.4693 F1 on `other` — Few-NERD's catch-all
   — which is **57.2%** of its support-weighted advantage over that arm. Across the 24
   hosted arms the share runs from 29.8% (`llama_l`) to 57.2% (`openai_m`; `openai_l` 52.2%,
   `anthropic_l` 43.3%, `gemma_m` 39.2%), and it is conditional on a prompt that gave bare
   type names and no definitions. Membership of `other` follows an annotation convention
   (languages, diseases, currencies); `openai_m` still gets 0.3017 on it from the label
   alone. On `person`, three hosted arms edge `span_marker` — `openai_m` by 0.0067,
   `anthropic_l` by 0.0054, `openai_l` by 0.0040, untested at n = 166 — and the other 21
   trail it by 0.0007 to 0.0894.

4. **The zero-shot control almost never predicts `other`.** `gliner`, handed the same
   eight labels and never trained on Few-NERD, emitted `other` 3 times in 280 sentences
   (`openai_m` 93, `anthropic_l` 131, `span_marker` 97) and gets **0 of 86** right — while
   reaching 0.7701 on `person`. With the label predicted 3 times, the 0.0000 is mostly that
   this label-prompted matcher skips the bare word "other"; why is not measured. `gliner`
   also differs from `span_marker` in architecture and encoder (§3.5), so the 0.0000 is not
   a measure of task-specific training alone.

5. **34 of 768 gold types (4.4%) are rejected by at least 80% of the 26 learned arms, agreeing on one alternative**, and of the 14 listed in §3.6
   the field looks right to this reader: "Georgia Dome" filed as `location`, "Nazis" as
   `person`, "EDFL" as `event`. Resolving all 34 the arms' way moves every hosted arm
   **+0.024 to +0.039** and `span_marker` **+0.0060** — it was trained on the convention and
   never lost those points. Its lead over `openai_m` falls from 0.0810 to **0.0503**: **up
   to 38% of that lead is agreement with the annotation** — an upper bound that depends on
   the selection rule (7% to 53% across the four top hosted arms and thresholds of 90% to
   70%, §3.6), scored with votes from arms that include the ones being scored and share
   zero-shot priors.

6. **A scoring bug paid non-answers full marks, and no fingerprint could have caught it.**
   An unreadable output was indistinguishable from an empty prediction; on the 12% of
   items with no gold entities that scored **1.0**. Found and fixed mid-sweep; see §6.

> **Reframed 2026-10-19.** Until then this summary said: the winner "separated from 27 of
> 27" (24 hosted plus `gliner`, `capitalized`, `nothing`; `openai_m`'s "20 of 27" counts
> `span_marker` and those three, so 16 of 23 other hosted arms); that `gliner` was the "same
> model class" and "the cleanest isolation of task-specific training" (it is a different
> architecture and emitted `other` 3 times, §3.4–3.5); that "57% of the margin is one type"
> (it is 57% against `openai_m`, the maximum; 30–57% across the 24 hosted arms) whose
> meaning "has no inferable meaning" (`openai_m` gets 0.3017 on it from the label alone);
> that "a frontier LLM wins" on `person` (three of 24 hosted arms edge it, by at most
> 0.0067, untested); that "38% of that lead is conformity to the annotator, not
> correctness" (up to 38%, selection-dependent, §3.6); and that 52 GB "fits a 64 GB box
> natively" with "the same answer at every budget" (nothing was run on 64 GB; 52 GB is weights
> only). The numbers did not change; the claims around them were wider than the evidence.

---

## 1. What was measured

| property | value |
|---|---|
| Corpus | Few-NERD `supervised` test split, CC BY-SA 4.0 |
| Slice | 280 sentences, seeded random (`--seed 20260928`), `items_sha256` `95a1b9627073` |
| Dev slice | 56 sentences, a strict **prefix** of the same permutation — nested, so holdout analysis is honest |
| Gold | expert annotation, a JSON array of `{text, type}` per item — **768 entities as annotated, 766 scorable**: the two bare "£" tags in §5 normalise to nothing and drop out |
| Density | 2.74 entities/sentence; **34 of 280 sentences have none** (35 once the "£" item is normalised, §5) |
| Types (of the 766 scorable) | location 199, organization 172, person 166, other 86, product 58, art 30, building 29, event 26 |

The type distribution is left imbalanced. Rebalancing would make the slice
unrepresentative of the task.

**The 12% of sentences with no entities are load-bearing, not an edge case.** They are
where an arm that invents entities is caught, and they fix the floor.

### Arms

| Arm | What it is | Weights (download size) |
|---|---|---|
| `span_marker` | `guishe/span-marker-generic-ner-v1-fewnerd-fine-super`, **fine-tuned on Few-NERD's training split**, predicts the 66 fine types mapped down to 8 | 499 MB |
| `gliner` | `urchade/gliner_medium-v2.1`, zero-shot, **caller supplies the label set**, threshold 0.5 (library default, untuned) | 781 MB |
| 24 hosted | 8 vendors × {small, medium, large}, one prompt, temperature 0 | — |
| `capitalized` | every capitalised run, minus a stoplist written from English orthography | — |
| `nothing` | predicts the empty set, always | — |

— = no local weights (a hosted API, or a rule-based baseline).

`nothing` is a calibration check on the scorer before it is a baseline on the task. It must
score exactly the rate at which an empty prediction is correct, and §5 is about the 1/280
where that did not reconcile.

---

## 2. How a set is scored

### The empty cases, decided before any arm ran

| gold | prediction | F1 |
|---|---|---|
| empty | empty | **1.0** — it correctly found nothing |
| empty | non-empty | 0.0 — everything predicted is a false positive |
| non-empty | empty | 0.0 — everything missed |
| any | **unreadable** | **0.0** — see §6 |

The first row is the one people get wrong by leaving precision undefined and dropping the
item. Dropping it would delete exactly the items on which a hallucinating arm should be
punished.

### Matching is one-to-one

A prediction satisfies at most one gold member and vice versa. Without that, one prediction
overlapping three gold entities counts as three true positives and precision becomes
unbounded nonsense.

### Normalisation is part of the system under test

Casefold, strip accents and punctuation, drop a leading article, squeeze whitespace.
Deliberately **not** stemming: "Olympics" and "Olympic" are surface forms a reader would
judge differently, and a normaliser that collapses them is quietly grading a different task.

The whole rule is hashed into `scorer_sha256` and carried on every run. §6 is about the
version of this report that would have been wrong without it.

### Typed and untyped are both reported, and they disagree

`untyped_f1` asks "did it find the entity at all"; `f1` asks "and did it label it right".
`type_penalty` is the difference. A type-confusion problem is fixed differently from a
detection problem, and the pair says which you have. `capitalized` is the extreme case:
untyped 0.6191, typed **0.1913** — it finds spans well and types them almost at random.

### Per-item mean and corpus micro-F1 are different numbers

An item has its own gold set, so its F1 is well defined and the mean of those is an honest
per-item metric — which means the sign-flip permutation test works directly and no
bootstrap is needed. Corpus micro-F1 pools every tp/fp/fn into one figure. The mean is
the ranking metric; this sentence used to say "both are reported" and no micro-F1 figure
appeared anywhere. They do now
(`EVAL_RUNS_DIR=data/runs-rescored scripts/extraction_report.py --dataset-id few_nerd_280`):

| arm | mean per-sentence F1 (ranking) | corpus micro-F1 | micro precision | micro recall |
|---|---|---|---|---|
| `span_marker` | 0.7674 | **0.7951** | 0.7875 | 0.8029 |
| `openai_m` | 0.6864 | 0.7006 | 0.6760 | 0.7272 |
| `anthropic_l` | 0.6798 | 0.7038 | 0.6763 | 0.7337 |
| `gemma_m` | 0.6733 | 0.6921 | 0.6749 | 0.7102 |
| `gliner` | 0.4540 | 0.5189 | 0.4795 | 0.5653 |

The winner and the gap behind it hold under both; `anthropic_l` and `openai_m` swap
places, inside a difference no test separates. **Neither figure is comparable to published
Few-NERD results**, which are entity-level micro-F1 over the 66 *fine* types on exact token
spans; ours are 8 coarse types matched on normalised strings. The comparable number is the
calibration row: `span_marker` scored the standard way on 2,000 seeded test sentences,
**0.7047** against the 0.7040 its model card publishes, inside its own bootstrap 95%
interval of ±0.016 (`docs/PROTOCOL.md`). Only `span_marker` was calibrated this way.

---

## 3. Results

### 3.1 The leaderboard

*How to read this table.* Sorted by `f1`, descending. **f1** = typed mean per-sentence F1
(span and type must both match; 0–1, higher is better). **untyped f1** = the same score
ignoring the type label — did the arm find the span at all. **parsed** = share of the 280
replies the parser could read; an unreadable reply scores 0 (§6). **latency per item** =
mean wall-clock seconds per sentence — hosted arms include the network, local arms ran on
CPU fp32; `~0` = under a millisecond (rule-based baselines). **cost** = what the provider
billed for all 280 sentences. **Bold** marks the winner, the fastest arm and the free
learned arms. `span_marker` is separated from all 27 other arms (§3.2); `openai_m` is
separated from 16 of the 23 other hosted arms (20 of 27 opponents counting `span_marker`,
`gliner`, `capitalized` and `nothing`) — not from `anthropic_l`, `gemma_m`, `openai_l`,
`anthropic_m`, `qwen_s`, `qwen_m` or `gemma_l` (§3.3).

| arm | f1 | untyped f1 | parsed (share of items) | latency per item | cost (billed, 280 items) |
|---|---|---|---|---|---|
| **span_marker** | 0.7674 | 0.8370 | 1.000 | 0.76 s | **$0** |
| openai_m | 0.6864 | 0.7783 | 1.000 | 1.60 s | $0.6507 |
| anthropic_l | 0.6798 | 0.7820 | 1.000 | 2.76 s | $0.6897 |
| gemma_m | 0.6733 | 0.7750 | 1.000 | 3.05 s | $0.0088 |
| openai_l | 0.6716 | 0.7691 | 1.000 | 1.90 s | $0.1715 |
| anthropic_m | 0.6661 | 0.7666 | 1.000 | 2.69 s | $0.2846 |
| qwen_s | 0.6650 | 0.7649 | 1.000 | 2.15 s | $0.0157 |
| qwen_m | 0.6548 | 0.7525 | 1.000 | 2.24 s | $0.0396 |
| gemma_l | 0.6481 | 0.7689 | 1.000 | 2.91 s | $0.0134 |
| qwen_l | 0.6240 | 0.7283 | 1.000 | 1.67 s | $0.0722 |
| deepseek_m | 0.6148 | 0.7265 | 1.000 | 1.23 s | $0.0200 |
| llama_l | 0.5990 | 0.7146 | 0.996 | 4.80 s | $0.0176 |
| mistral_l | 0.5979 | 0.6946 | 0.996 | 10.25 s | $0.0419 |
| openai_s | 0.5948 | 0.6855 | 1.000 | 1.21 s | $0.0784 |
| glm_m | 0.5939 | 0.7151 | 1.000 | 3.66 s | $0.0445 |
| mistral_m | 0.5914 | 0.6870 | 1.000 | 0.79 s | $0.0462 |
| deepseek_l | 0.5872 | 0.6940 | 1.000 | 3.73 s | $0.0853 |
| anthropic_s | 0.5843 | 0.7279 | 1.000 | 1.34 s | $0.1552 |
| deepseek_s | 0.5756 | 0.6996 | 1.000 | 2.28 s | $0.0091 |
| llama_m | 0.5740 | 0.6769 | 0.954 | 5.40 s | $0.0194 |
| llama_s | 0.5686 | 0.6812 | 0.993 | 2.64 s | $0.0103 |
| glm_l | 0.5662 | 0.6529 | 0.889 | 3.01 s | $0.1023 |
| glm_s | 0.5529 | 0.6863 | 1.000 | 2.11 s | $0.0194 |
| gemma_s | 0.5500 | 0.6758 | 1.000 | 5.94 s | $0.0093 |
| mistral_s | 0.5243 | 0.6446 | 1.000 | 2.06 s | $0.0076 |
| gliner | 0.4540 | 0.5522 | 1.000 | **0.17 s** | **$0** |
| capitalized | 0.1913 | 0.6191 | 1.000 | ~0 | $0 |
| nothing | 0.1250 | 0.1250 | 1.000 | ~0 | $0 |


### 3.2 The only unambiguous winner this repo has produced

`span_marker` vs a family of 27 declared before any p-value was read, Holm step-down at
α = 0.05, sign-flip permutation on paired per-item F1:

```
separated from 27 of 27 opponents; ahead on the point estimate against 27 of 27
closest opponent: openai_m  delta +0.0810  wins 86/280  p = 0.0001  thresh 0.0500
```

Every other example in this repo produced a *group* at the top. This one produced a podium
— as run here: a fine-tuned tagger against 24 hosted arms on one zero-shot prompt, no
definitions, no examples. It does not say how an LLM given labelled examples would do.

### 3.3 And behind it, the same tie as everywhere else

`openai_m` vs the same family:

```
separated from 20 of 27; ahead on the point estimate against 26 of 27

  NOT separated:
    gemma_l      +0.0383  p = 0.0084   ($0.0134)
    qwen_m       +0.0316  p = 0.0244   ($0.0396)
    qwen_s       +0.0214  p = 0.1481   ($0.0157)
    anthropic_m  +0.0204  p = 0.1668   ($0.2846)
    openai_l     +0.0148  p = 0.2492   ($0.1715)
    gemma_m      +0.0131  p = 0.4310   ($0.0088)
    anthropic_l  +0.0066  p = 0.6664   ($0.6897)
```

**$0.0088 to $0.6897 — 78× — for differences of 0.0066 to 0.0383 F1 that the data cannot
resolve.** DBpedia gave 115× on a completely different task. The consistency is the
finding: near the top of a hosted field, a 78× price range sits inside gaps these 280
sentences cannot resolve — not shown different, which is not the same as equal. The gaps
are measured against `openai_m` only; `gemma_l`, at 0.0383 and p = 0.0084 against a Holm
threshold of 0.0071, is the closest call.

### 3.4 Where the lead actually comes from

Per-type F1, support-weighted contribution to `span_marker`'s advantage over `openai_m`:

| type | gold entities | F1 span_marker | F1 openai_m | Δ (span_marker − openai_m) | share of lead | F1 gliner (reference) |
|---|---|---|---|---|---|---|
| location | 199 | 0.8170 | 0.7744 | +0.0427 | 12.0% | 0.5889 |
| organization | 172 | 0.7692 | 0.6863 | +0.0829 | 20.2% | 0.5631 |
| **person** | 166 | 0.8882 | **0.8949** | **−0.0067** | **−1.6%** | 0.7701 |
| **other** | 86 | 0.7709 | 0.3017 | **+0.4693** | **57.2%** | **0.0000** |
| product | 58 | 0.7407 | 0.6903 | +0.0505 | 4.2% | 0.4821 |
| art | 30 | 0.7761 | 0.7222 | +0.0539 | 2.3% | 0.2593 |
| building | 29 | 0.6567 | 0.5902 | +0.0666 | 2.7% | 0.3385 |
| event | 26 | 0.6296 | 0.5507 | +0.0789 | 2.9% | 0.1828 |

*How to read this table.* Rows are sorted by **gold entities** (how many of the 766
scorable gold entities carry that type), descending. Each **F1** is that type's F1 pooled
over the whole slice — all its matches, false positives and misses counted together.
**share of lead** = the type's Δ weighted by its gold-entity count, as a share of the
total weighted lead of **+0.0921** (= Σ Δ × count / 766). `gliner` is shown for reference
and does not enter Δ.

**Why +0.0921 and not the 0.0810 lead in §3.2?** They are different averages. +0.0921
weights every gold *entity* equally and uses per-type F1 pooled over the slice; 0.0810 is
the difference in *mean per-sentence* F1, which weights every *sentence* equally. Both say
`span_marker` leads; the percentages in this section are shares of the +0.0921.

**Total entity-weighted lead over `openai_m`: +0.0921, of which `other` is 57.2%.** That is
the maximum over the 24 hosted arms. The same calculation against each of them gives an
`other` share of 29.8% (`llama_l`) to 57.2% (`openai_m`): `openai_l` 52.2%, `anthropic_l`
43.3%, `gemma_m` 39.2%. It is conditional on the prompt, which gave bare type names and no
definitions.

(Per-type figures are typed F1 against gold as annotated. §3.6 shows what happens when the
annotation itself is the thing in dispute.)

`other` is Few-NERD's catch-all coarse type — languages, diseases, chemicals, awards,
currencies. The label names no category and the prompt gave no definition, so a model has
only the word "other" to go on; membership follows an annotation convention. Three arms
score it very differently:

- `span_marker`, trained on the split — **0.7709**
- `openai_m`, general world knowledge, guessing from the label name — **0.3017**
- `gliner`, handed the bare word "other" — **0.0000**, 0 of 86, having emitted the label
  3 times in 280 sentences (`openai_m` 93, `anthropic_l` 131, `span_marker` 97)

The ordering supports one reading: `span_marker`, which saw the split, beats the two arms
that did not. It does not isolate exposure, because `gliner` differs from `span_marker` in
architecture and encoder (§3.5) and its 0.0000 comes mostly from almost never predicting
the label. Since a definition was never offered to `openai_m`, how much of its 0.3017 a
definition or examples would recover is not measured.

*Until 2026-10-19 this section called `other` a label that "carries no semantics", "close to
a pure measure of exposure to the corpus", with "the three arms line up exactly by
exposure". `openai_m` gets 0.3017 from the label alone, so it is not meaningless to a
model, and the `gliner` figure is confounded.*

**On `person`, three of the 24 hosted arms edge `span_marker`:** `openai_m` by 0.0067,
`anthropic_l` by 0.0054, `openai_l` by 0.0040 — differences not tested, at n = 166 gold
`person` entities. The other 21 trail it by 0.0007 (`gemma_l`) to 0.0894 (`mistral_s`).
*Until 2026-10-19 this read "the frontier hosted model wins. That is the whole result in
one row."*

### 3.5 Task-specific training, against a zero-shot control

`span_marker` 0.7674 vs `gliner` 0.4540 — same label set, same CPU, same harness, and a gap
of **+0.3134 F1**. It is not one variable. `span_marker` saw Few-NERD's training split and
`gliner` did not, but they are also different models: a SpanMarker span classifier on a
RoBERTa encoder (`numind/generic-entity_recognition-v1`, per its config) against GLiNER's
label-prompted matcher on DeBERTa-v3-base. An earlier version of this section called them
the same model class with exposure as "the one variable"; that was wrong. The gap is
exposure plus architecture, and how it splits is not measured.

This is the question the summarisation and AG News examples kept running into, and
summarisation has the cleaner answer: the same BART-large fine-tuned on CNN/DailyMail and on
XSum, first and last of 29.

### 3.6 Annotation noise, and an upper bound on what it costs

34 of 768 gold entities (4.4%) carry a coarse type that at least 80% of the 26 learned
arms (all 28 except the two baselines, `capitalized` and `nothing`) reject, agreeing on
the same alternative type. The first 14 of the 34, as `extraction_report.py` prints them
(count = arms that agree, out of 26):

```
26/26  "georgia dome"                     gold location     -> arms building
26/26  "carolina first arena"             gold organization -> arms building
26/26  "fort wayne daisies"               gold person       -> arms organization
26/26  "nazis"                            gold person       -> arms organization
26/26  "edfl"                             gold event        -> arms organization
26/26  "olympic club"                     gold location     -> arms organization
26/26  "burgtheater"                      gold location     -> arms building
26/26  "tennessee performing arts center" gold location     -> arms building
25/26  "maple blues awards"               gold other        -> arms event
25/26  "edmonton mcclung"                 gold person       -> arms location
25/26  "cameron mitchell restaurants"     gold building     -> arms organization
25/26  "bob evans restaurants"            gold building     -> arms organization
24/26  "sanitarium"                       gold building     -> arms organization
24/26  "katolska bokforlaget"             gold art          -> arms organization
```

*This block previously showed counts out of 25, printed before `mistral_l` joined the
field; it is re-run here on the committed 28-arm runs. The re-run reproduces the count of
34 and every figure in the table below.*

Independent models do not agree on a hallucination, but they do share priors: all 24 hosted
arms are zero-shot LLMs prompted with the same bare labels. Where 21 or more of 26 tag the
same span the same way against the annotation, the disagreement sits with the annotation
in the cases I read — a football league is not an `event`; a diuretic is not `other`; a
restaurant chain is not a `building`. That is one reader's judgement, and only 14 of the 34
labels are shown above; no second annotator checked.

Resolving all 34 the arms' way gives an **upper bound**, not an estimate: resolving in the
arms' favour is what raises the number. It answers only "how much of the typed/untyped gap
could annotation account for at most".

| arm | F1 as measured | F1 with the 34 disputed labels resolved the arms' way (upper bound) | change |
|---|---|---|---|
| **span_marker** | 0.7674 | 0.7733 | **+0.0060** |
| openai_m | 0.6864 | 0.7230 | +0.0365 |
| openai_l | 0.6716 | 0.7102 | +0.0386 |
| anthropic_l | 0.6798 | 0.7053 | +0.0255 |
| gemma_m | 0.6733 | 0.6975 | +0.0242 |
| gliner | 0.4540 | 0.4748 | +0.0208 |
| capitalized | 0.1913 | 0.1820 | **−0.0093** |

Rows are the winner, the top four hosted arms, the zero-shot control and a baseline.
**Across all 24 hosted arms the change runs from +0.0242 to +0.0386** — the two ends are
the `gemma_m` and `openai_l` rows above. F1 is mean per-sentence F1 throughout.

**`span_marker` moves four to six times less than the hosted field**, because it was
trained on the convention and was never losing those points. Its 0.0810 lead over
`openai_m` becomes **0.0503** under the bound: **up to 38% of that lead is agreement with
the annotation.** It stays ahead, and it stays separated — but the margin is materially
smaller than the leaderboard shows. The 38% is the figure against the arm the relabelling
helps most: against `anthropic_l` it is 22.3%, `gemma_m` 19.4%, `openai_l` 34.1%.

*Until 2026-10-19 this read "38% of that lead is agreeing with the annotator rather than
being right". The bound cannot say which of the two it is.*

**The 38% depends on how the 34 labels were selected.** Share of `span_marker`'s lead
removed by the bound, recomputed with `extraction_report`'s consensus and ceiling functions
at other settings (not a committed script):

| selection rule | disputed labels | vs `openai_m` | vs `anthropic_l` | vs `gemma_m` | vs `openai_l` |
|---|---|---|---|---|---|
| ≥70% of the 26 learned arms | 40 | 53.0% | 31.0% | 21.1% | 46.2% |
| **≥80% of the 26 (above)** | **34** | **37.8%** | **22.3%** | **19.4%** | **34.1%** |
| ≥90% of the 26 | 17 | 20.2% | 7.0% | 12.0% | 17.0% |
| ≥80%, only the 24 hosted arms vote | 35 | 42.2% | 25.1% | 23.2% | 37.9% |

The bound scores each arm against labels voted by a field that contains that arm, and the
24 hosted voters share zero-shot priors, so agreement among them is not independent
evidence that the annotation is wrong.

`capitalized` moves *negative*, which is the sanity check on the whole calculation: an arm
whose types are near-random gains nothing from relabelling and can lose.

### 3.7 Output budget is a model property, not a config detail

`glm_l` is the only arm with a serious parse failure rate: **0.889 parsed, 0.114 truncated**
at `max_tokens` 600. Of the other 23 hosted arms, 19 parsed at exactly 1.000 on the
identical budget; the four that did not are the llama family (large / medium / small:
0.996 / 0.954 / 0.993) and `mistral_l` (0.996). Only `llama_m` hit the budget at all
(0.025 truncated); the rest of their failures are malformed JSON, a different failure.

*This paragraph read "0.836 parsed" for `glm_l` and 0.986 / 0.943 / 0.993 for the llama
family — figures from before the §6 parser fix — while §3.1 carried the corrected ones.*

It is not producing malformed JSON. It is producing no JSON. On item `0e88aabc` —
*"Epsilon Centauri is a relatively young star, with an age of around 16 million years"* —
it spent the entire budget reasoning aloud about which benchmark it was being evaluated on:

> *"...this is the type set of the OntoNotes? No, OntoNotes has 18 types. It matches FIGER?
> No, FIGER has 112 types. Hmm, it could be from BBN? No."*

...and never answered. Its mean output is 136 tokens against `glm_m`'s 59, and **`glm_m`
outscores `glm_l` 0.5939 to 0.5662** — the larger model in the same family loses to the
smaller one by talking itself out of an answer.

The budget was not tuned after seeing this, because that would be tuning on the measurement
set. It is reported as a property of the arm.

### 3.8 The dev slice predicted the ranking, and the winner held

Spearman ρ between the 56-item dev slice and the 280-item measurement slice, 28 arms:
**0.903**. Dev leader and measurement leader are the same arm.

Mean |rank move| 2.36 positions; **max 11** — `glm_l`, rank 11 → 22, for the reason in §3.7:
the dev slice sampled its truncation rate at 5.4% and the measurement slice found 11.4%, the 0.114 in §3.7. (This sentence said 16.4% until 2026-10-15: that is the share of its replies the original parser could not read, 1 − 0.836, not the share that was truncated.)

**No winner's curse.** On the 224 items the dev slice never contained:

```
global test (permutation on within-item ranks): p = 0.0002 -> an arm effect exists
Nemenyi critical difference = 2.89 rank positions; observed span = 14.44
pairs distinguishable: 152 of 378

  fn_span_marker_n200_v1   avg rank 8.98   P(1st) = 1.00
```

> **Twice corrected, and the second correction is the interesting one.** This block first
> read *"critical difference = 2.74; pairs distinguishable: 156 of 351"*, from silently
> reusing the k=25 critical value for a 27-arm field — too small, so the CD was
> understated and more pairs called distinguishable than the test supports. Round 2 made
> the tool refuse above k=25 and this block printed NOT AVAILABLE. A round-3 reviewer
> pointed out the values are about thirty lines of stdlib, which they are:
> [`scripts/nemenyi_table.py`](../harness/scripts/nemenyi_table.py) solves the
> studentised-range integral and reproduces all 24 of Demsar's published values to
> within 0.0007.
>
> Computed for k=27 the CD is **2.77** and **149 of 351** pairs separate — against the
> 2.74 and 156 first published. So the original was biased in exactly the direction
> stated, by seven pairs. **The global test is unaffected**, and so is every separation
> claim here: those come from `family_test.py`'s Holm step-down, which never used this
> table.

This is the direct opposite of the summarisation result, where BART's 0.0737 lead at n=20
collapsed to 0.00008 at n=200. A lead can be an artifact of a small slice; this one is not,
and the same machinery says so in both directions.

### 3.9 Rank stability — and why the tie column earned its place

```
 n per half   rho(A,B)   5th pct   P(same winner)   median |rank move|   arms tied 1st
         10      0.524     0.261             0.33                 3.46             1.0
         20      0.662     0.441             0.57                 2.67             1.0
         50      0.811     0.698             0.87                 1.83             1.0
        100      0.878     0.823             1.00                 1.17             1.0
```

Monotone in every column — which DBpedia's was not. There, P(same winner) *fell* from 0.94
to 0.28 as n grew, because a saturated binary metric made most arms tie at the top and the
tie was broken alphabetically. `arms tied 1st` = **1.0 at every size** here.

**The metric's shape decides whether this diagnostic can be read at all.** Per-item set F1
takes many values, ties essentially never happen, and ρ measures the data. Binary accuracy
on a saturated task ties constantly, and ρ measures the sort order. The tie column was
added after DBpedia; Few-NERD is the case that shows what it looks like when nothing is
wrong.

The formula itself was fixed on 2026-09-29 — `spearman()` had no tie correction and
`ranks_on()` broke ties alphabetically — and the table above is the corrected one. On this
corpus the change is ≤0.008 at any n, which is the point: a metric that does not tie is
not affected by how ties are handled. The two classification corpora moved by up to 0.115.
See [`REPORT_CLASSIFICATION.md`](REPORT_CLASSIFICATION.md) §3.6.

---

## 4. Discussion

**The honest summary of "small ML model vs LLM" is narrower than the leaderboard makes it
look.** `span_marker` wins outright and separates from all 27 opponents. But decompose it:

- 57% of the margin over `openai_m` (30–57% across the 24 hosted arms) is one type,
  `other`, which the bare-label prompt never defined.
- **Up to ~38% of the margin over `openai_m`** (19–34% against the next three hosted arms;
  7–53% across the selection thresholds in §3.6) is agreeing with annotation the rest of the
  field rejects.
  Under the annotation bound the lead over `openai_m` falls from **0.0810 to 0.0503**,
  and `1 − 0.0503/0.0810 = 37.9%`. `span_marker` itself gains only 0.0060 under the
  bound; `openai_m` gains 0.0365, and it is the **difference** between the two that
  closes the margin.

  *This bullet said "~7%" for a week, from dividing span_marker's own 0.0060 gain by
  the margin. That is the wrong quantity: a share of the margin is about how the margin
  MOVES, and the margin moves by the difference between the two arms, not by one arm's
  gain. §0 and §3.6 of this same report already said 38% and were right.*

  *Worse, when round 3 flagged the inconsistency I recorded it here as a disagreement
  and wrote that I "could not reproduce 38% from any pairing of the committed numbers".
  It was my own figure, 350 lines up in the file I was editing. Round 4 had to point at
  my own lines 34, 82 and 323 to show me. I was defending a number against myself.*
- On `person`, three hosted arms edge it, by at most 0.0067 (untested).

So the defensible claim is: **if your labels are a fixed in-house taxonomy and you can
label training data, a 499 MB model on CPU beat every hosted LLM as run here — one
zero-shot prompt of bare type names, no examples, temperature 0, reasoning off, provider
unpinned, scored on 8 coarse types by string match — at 0.76 s/item and $0.** How much of
that lead is training exposure is not isolated: the only untrained span tagger, `gliner`,
differs in architecture too. That is a real and useful claim — it is the podcast-product
case. The claim it does *not* support is that the small model is better at named-entity
recognition in general, or better than an LLM given definitions or examples.

**The top of the hosted field is not resolved.** Eight arms, 78× price spread, gaps to
the leader up to 0.0383 F1 that these 280 sentences cannot resolve — not shown different,
not shown equal. `gemma_m` at $0.0088 is inside the top group (+0.0131 behind `openai_m`);
`anthropic_l` at $0.6897 is too (+0.0066 behind). `anthropic_l` ran at 2.76 s/item, against
`gemma_m`'s 3.05 s and `openai_m`'s 1.60 s, so the dearest arm was neither the fastest nor
the slowest, and its price bought no F1 gain these data can show. Latency includes the
network and whichever provider served the call.

*Until 2026-10-19 this paragraph opened "The hosted field is a commodity at the top" and
said "Buying the expensive one bought 3.05 s/item of latency and nothing else measurable".
3.05 s is `gemma_m`'s latency; `anthropic_l`'s is 2.76 s.*

**`untyped_f1` barely reorders anything but explains a lot.** Spearman between the typed
and untyped orderings is **0.955** over 28 arms, same leader, so it is not an alternative
leaderboard. What it does is split each arm's error into detection and labelling.
`anthropic_s` is typed 0.5843 / untyped 0.7279 (`type_penalty` 0.1436) and rises six places
on the untyped view — a labelling problem. `openai_s` is 0.5948 / 0.6855 and *falls* seven
places — it is typing well what little it finds. `glm_l` is 0.5662 / 0.6529 (penalty
0.0867): not a labelling problem at all, a *not answering* problem.

---

## 5. A calibration check that did not reconcile, and what was under it

`nothing` scored **0.1250**. The empty-gold rate is **34/280 = 0.1214**. One item.

Item `a68981540c14` is *"Its revenue quickly increased, from £ 4,424 in 1901 to £ 274,989 in
1910"*, and Few-NERD tags the bare symbol **"£"** as an entity of type `other`, **twice**.
The normaliser strips punctuation, both members normalise to the empty string and are
dropped, and the item behaves as empty-gold for every arm.

Neither half is wrong enough to change for one item: stripping punctuation is right for
comparing entity mentions, and calling a currency sign an entity is the odd end of it. But
the floor moves, and a 1/280 discrepancy between a baseline and its predicted value is
exactly the kind of thing that gets explained away instead of opened. `extraction_report.py`
now prints these, and `fetch.py` no longer claims the floor is *exactly* the empty-gold rate.

---

## 6. Corrections

### An unreadable answer was scoring 1.0

`score_sets` took only the parsed set, so the caller could not distinguish *"the model
answered `[]`"* from *"the model's output could not be read"*. Both arrived as an empty
list. On the 12% of items whose gold is also empty, the empty-empty convention paid a
non-answer the **full 1.0**.

`glm_l` collected six of them. It was worth **+0.0214 f1** — 0.5484 as first measured,
**0.5269** after that correction. It reordered nothing.

### And then the parser was refusing answers that were there

A second external review found the JSON parser's array matcher was `\[.*\]` with
DOTALL — **greedy**, so it spanned from the first `[` in a reply to the last `]`
anywhere in it. Two real answers died that way:

- `[{...}] See [1]` became one span covering both brackets and the prose between them.
  Not JSON, so a correct answer scored zero.
- `llama_l` emitted a malformed array, wrote *"Here is the correct output:"*, then a
  valid one. The greedy match swallowed both and parsed neither.

Balanced spans are now scanned left to right and the first that reads as entities wins.
**21 of the 68 items this experiment had scored unreadable were readable all along.**

| arm | F1 before parser fix | F1 after parser fix | unreadable items before | unreadable items after |
|---|---|---|---|---|
| `glm_l` | 0.5269 | **0.5662** | 46 | **31** |
| `llama_l` | 0.5911 | **0.5990** | 4 | **1** |
| `llama_m` | 0.5704 | **0.5740** | 16 | **13** |
| `deepseek_m` | 0.6122 | **0.6148** | 0 | 0 |

F1 = mean per-sentence F1; unreadable items = replies, of 280, that the parser could not
read (each scores 0). Only the four arms the fix moved are shown.

`deepseek_m` moved without any item changing readability: it had answered `[[{...}]]`,
doubly wrapped, and the old code dropped the inner list as a non-object and returned an
**empty set** — scoring six found entities as *"correctly found nothing."*

**My first version of the fix broke two answers to fix the others**, and only a
before/after comparison of every arm caught it. Requiring *every* element of an array to
be entity-shaped rejected `llama_s`'s otherwise-valid list that carried one stray bare
string, and refused `deepseek_m`'s double wrap outright. The rule is now *at least one*
entity-shaped element — enough to reject `[1]` from "See [1]", which is the case the
shape test exists for, without demanding tidiness from an answer that has entities in it.

**What is still refused, and should be:** prose, and arrays cut off mid-object. `glm_l`
runs out of tokens on `[{"text": "Corfu International` with no closing bracket. There is
no answer there, and mining one out of an explanation would be inventing it. 31 of its
280 items are still unreadable and that is the model's behaviour, not the parser's.

**The earlier claim that "both parser fixes change zero recorded numbers" was about the
ROUND-1 fixes and remains true of them.** This is a different bug, found later, and it
moves four arms.

**No fingerprint could have caught it.** `normalizer_sha256` covered `normalize` and nothing
else, on the reasoning that a normaliser has the most room to move a score. The reasoning
was right and the scope was wrong — the bug lived in `prf`, which no hash covered. The
scorer could change between two runs and neither fingerprint would say so. `scorer_sha256`
now covers the whole rule.

`rescore.py` was blind the same way: it re-records the *adapter file's* sha256, and the
scoring rule lives in a shared module, so an extraction-only change — precisely this one —
left the adapter hash identical. Adapters now expose `scorer_id()`.

**No re-run was needed, and that was checked rather than assumed.** The 14 arms already
finished were rescored from stored outputs and compared **per item** against the originals:
13 differ on zero items, max |Δf1| = 0; `glm_l` differs on exactly 6, each by 1.0.

### Consensus counted occurrences, not arms

The first version of the consensus pass printed `25/17` — a consensus larger than the field
— because one arm emitting the same span twice voted twice. The claim is "N independent
arms agree", so the unit is the arm.

### Every number here comes from one instrument

All 27 measurement runs and all 28 dev runs were rescored into a single directory and
verified to share one `items_sha256`, one adapter sha256, one `scorer_sha256` and one
`parser_sha256`. The dev rescore changed **0 of 28** arms beyond 1e-6, as predicted (no dev
arm had an unreadable item with empty gold).

---

## 7. NOT covered, NOT measured, NOT verified

This section is deliberately as detailed as the results.

- ~~**`mistral_l` was never measured on the 280-item slice.**~~ **MEASURED 2026-10-01.**
  It had been blocked for five review rounds: `mistralai/mistral-large-2512` is
  rate-limited upstream on OpenRouter's shared pool
  (`limit_source: upstream_provider_shared_pool`), litellm burns 6 internal retries per
  call before returning 429, and the measured rate was **3 items in 7 minutes** — about
  11 hours for the arm. Retried when the pool was quieter and it completed in ~2 h 20 m
  at ~2 items/minute; the 429s never stopped (the proxy logged 70–134 per 10 minutes
  throughout) and the retry ladder absorbed them, so this is "retried hard enough", not
  "the limit lifted". **f1 0.5979**, parsed 279/280, $0.0419, `providers_seen`
  `{Mistral: 280}`, fingerprint `dirty: false`.

  It lands **13th of 28**, inside the `mistral_m` / `glm_m` / `llama_l` band the handover
  predicted (0.591–0.594), slightly above it. The family is now **27**, so every Holm
  threshold in §3.2 and §3.3 is stricter than it was: `span_marker` still separates from
  **27 of 27** and `openai_m` from **20 of 27**, the same seven arms unseparated.
  Its **dev** score on 56 items was **0.6005**; the measurement is 0.5979, a 0.0026 move.
- **No confidence/calibration analysis.** Hosted arms have no `confidence`: logprobs were
  never requested. The classification report's calibration section has no counterpart here.
- **Boundary errors are not separated from detection errors.** A prediction that overlaps a
  gold span but does not match it after normalisation counts as one fp and one fn, exactly
  like a miss. Few-NERD's IO tagging guarantees some gold boundaries are unrecoverable by
  construction (two adjacent same-type entities merge into one span), so some share of
  every arm's error is structural. **That share is not quantified anywhere in this report.**
- **`gliner`'s threshold (0.5) is untuned.** It is the library default, and it is this arm's
  decision boundary — moving it trades precision against recall. Tuning it on the dev slice
  would be legitimate, but it would then be a tuned arm. A tuned GLiNER might close some of
  the +0.3134 gap in §3.5, and nothing here bounds how much.
- **Corpus micro-F1 still forgives an unreadable empty-gold item.** The per-item fix in §6
  sets f1 = 0 and counts fn = |gold|, but does not count a false positive, because the arm
  predicted nothing. So an unreadable item with empty gold contributes 0/0/0 to the pooled
  counts. The per-item mean — the ranking metric — is unaffected.
- **One pass per arm, temperature 0.** No variance estimate over repeated sampling. Every
  interval here is over *items*, not over *runs*.
- **The upper bound in §3.6 is an upper bound.** It is not an estimate of performance
  against clean annotation, and the 34 spans were found by the field's own agreement, which
  is not an independent judge: the voters include the arms being scored and the 24 hosted
  voters share zero-shot priors. The 38% moves from 7% to 53% with the selection threshold
  and the arm compared, and only 14 of the 34 labels are shown and read.
- **`span_marker`'s fine→coarse mapping is asserted, not verified against a spec.** Few-NERD
  fine labels are literally `coarse-detail`, so the mapping is deterministic, but no test
  compares it to an authoritative list.
- **English Wikipedia prose only.** The relevance this example gives up to keep a clean
  licence is noisy speech — WNUT-2017 would have been closer to podcast transcripts, and is
  licensed `other`.
- **No ML arm ran on GPU.** Both local arms are CPU fp32. Latency figures are not
  deployment figures.
- **One zero-shot prompt, nothing else.** Every hosted arm got bare type names: no
  definitions (so none for `other`), no examples, no reasoning, temperature 0, and no
  provider pinned — OpenRouter routed the open-weight arms across many providers (`gemma_m`
  across 13 within one run). The per-type shares in §3.4 and every hosted figure are
  conditional on that prompt; an LLM given definitions or labelled examples is the obvious
  rival to a fine-tune and was not run.
- **No matched exposure control.** `span_marker` vs `gliner` differs in architecture,
  encoder and training exposure at once; a same-architecture pair (a SpanMarker trained
  elsewhere, or GLiNER fine-tuned on Few-NERD) was not run. How the +0.3134 splits is not
  measured.
- **Scoring choices are not analysed beyond typed vs untyped.** The metric uses 8 coarse
  types, normalised string match and no positions; the only sensitivity check is typed vs
  untyped (ρ = 0.955). The calibration against the published figure covers `span_marker`
  only (0.7047 vs 0.7040, bootstrap ±0.016, on 2,000 sentences scored the standard way);
  no hosted arm and not `gliner` was scored on the standard metric.
- **Contamination is not measured.** Few-NERD is public (Wikipedia text, CC BY-SA), so its
  sentences or labels may be in the hosted models' training data. What
  `span_marker`'s encoder (`numind/generic-entity_recognition-v1`, per its config) was
  trained on, and whether that overlaps the test split, was not checked.
- **Nothing was self-hosted.** `gemma_m`'s 0.6733 is the model as 13 providers served it.
  No run on a 64 GB or 128 GB machine was made; 52 GB is weights only, without KV cache.
  The 103× is download size (the ~52 GB of weights against the tagger's 499 MB file), the ≈207× is
  parameters (25.8B, this report's figure for Gemma-4-26B-A4B, against 124.75M from the
  tagger's safetensors metadata); neither is a measured memory footprint.

---

## 8. Reproduction

```bash
python examples/ner-few-nerd/fetch.py --n 280
cd harness
# The dataset file is committed and frozen; materialize checks the fetched bytes against it.
make dataset-materialize DATASET_ID=few_nerd_280

for f in ../examples/ner-few-nerd/configs/arm_*_n200.yaml; do
  python scripts/experiment_run.py --config "$f"
done

python scripts/rescore.py --dataset-id few_nerd_280 --match fn_ --out data/runs-rescored
EVAL_RUNS_DIR=data/runs-rescored python scripts/extraction_report.py --dataset-id few_nerd_280 --match fn_
python scripts/family_test.py --dataset-id few_nerd_280 --a fn_span_marker_n200_v1 \
    --against _n200_v1 --metric f1 --runs-dir data/runs-rescored
EVAL_RUNS_DIR=data/runs-rescored python scripts/holdout_significance.py \
    --dataset-id few_nerd_280 --exclude-dataset few_nerd_56 --metric f1 --match fn_
EVAL_RUNS_DIR=data/runs-rescored python scripts/rank_stability.py \
    --dataset-id few_nerd_280 --metric f1 --match fn_
```

The corpus is never committed: `fetch.py` downloads it to whoever runs this and the slice is
gitignored. Dataset identity travels as `items_sha256`, not as bytes in the repo.

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
