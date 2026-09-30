# Evaluation report — 24 LLMs and two NER models on Few-NERD

**Dataset** `few_nerd_280` · 280 Wikipedia-derived sentences · 768 gold entities · 8 coarse types
**Arms** 24 hosted models (8 vendors × 3 price tiers) · 1 fine-tuned span tagger · 1 zero-shot span tagger · 2 non-learned baselines
**Design** 1 pass per arm · identical prompt, temperature 0, reasoning off, `max_tokens` 600 · **$2.57 billed** ($2.05 by the price table — see Correction)
**Date** 2026-09-28 · **Harness** [`../harness`](../harness) · **Journal** [`NOTES.md`](NOTES.md)

> **The third metric shape.** Summarisation compares one text to one text and scores
> continuously. Classification compares one label to one label and scores 0 or 1.
> Extraction compares a **set** to a **set**, and every interesting decision is in how the
> members are matched. This report is as much about what that shape does to the
> methodology as about which model won.


> **This is one of five experiments.** What all five agree on — and the four
> places they disagree with the conventional reading of a leaderboard — is in
> [`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).

---

## Executive summary

### The decision, in one table

| the choice | what the data says |
|---|---|
| **Self-host · small ML** | **`span_marker`** — SpanMarker fine-tuned on this corpus, CC-BY-SA-4.0, **499 MB**, CPU, 0.76 s/item. **0.7674 — separated from 26 of 26**, the only unambiguous winner in this repo. |
| **Self-host · open-weight LLM, absolute** | **`gemma_m`** — Gemma-4-26B-A4B, Apache-2.0, **25.8B / ~52 GB**. **0.6733** — **0.0941 worse** than a model **109× smaller**. The clearest ML-beats-LLM result in the set. |
| **Self-host · open-weight LLM, ≤128 GB** | **The same model.** At 52 GB native it fits with room to spare — **the absolute open-weight winner here is already the practical one.** |
| **Self-host · open-weight LLM, ≤64 GB** | **Still the same model**, 52 GB native. Memory is not the constraint on this task at any budget — **and it still loses by 0.0941 to a 499 MB tagger.** |
| **Deploy — rented API** | **`openai_m`** at **$2,324/month per 1M items**, 0.6864 — **10.6% below free** and 2× slower. There is no reason to choose this row unless you cannot run a 499 MB model. |
| **What should I not deploy?** | `anthropic_l` at **$2,463/month per 1M items** — **11.4% below free**, the largest free-vs-paid gap in the set. |
| **Does paying more help?** | Most of any experiment here, and still not enough: **+5.9%** per 10× cost, while free beats the whole paid field. |
| **How much of the win is real?** | **57% of its margin is one entity type** (`other`) whose meaning exists only in this corpus, and **38% of its lead** is agreeing with annotation the field rejects. On `person`, a frontier LLM **wins**. |
| **What does fine-tuning buy?** | **+0.3134 F1**, isolated by a matched pair at price zero on both sides (`span_marker` vs `gliner`). |
| **Is a pilot enough?** | Here yes — ρ = 0.895, right winner. It was wrong in 3 of the other 4 experiments. |
| **Fine-tune or pay?** | **Fine-tune.** The matched pair isolates it: `span_marker` (saw the training split) 0.7674 vs `gliner` (did not) 0.4540 — **+0.3134 from exposure alone**, at $0 on both sides. |

*Cross-cutting context for all five experiments:
[`REPORT_SYNTHESIS.md`](REPORT_SYNTHESIS.md).*

### What this experiment specifically found


**A free 476MB span tagger beat all 24 hosted LLMs and separated from every one of them —
the first unambiguous winner in this repo. But 57% of its lead comes from a single entity
type whose meaning is a corpus convention rather than a fact about the world, and on the
one type that means the same thing everywhere, a frontier LLM beats it.**

**On deployment:** this is the task where a small model wins by the widest margin. The
best open-weight LLM you could self-host, Gemma-4-26B at 52 GB, scores **0.6733** — a
model **109× larger** than `span_marker` and **0.0941 worse**. Memory budget changes
nothing here: 52 GB fits a 64 GB box natively, and the answer is the same at every budget
from 64 GB to unlimited.

1. **An actual winner, not a group.** `span_marker` scored **0.7674** against a hosted
   field of 0.524–0.686. Holm step-down over a family of 26 declared in advance:
   **separated from 26 of 26**. Neither classification corpus produced this — AG News gave
   a leader tied with nine others, DBpedia a group of ten.

2. **And behind it, the familiar tie.** The best hosted arm, `openai_m` at 0.6864,
   separates from only **19 of 26**. The seven it cannot separate from span
   `gemma_m` at **$0.0088** to `anthropic_l` at **$0.6897** — a **78× price range** buying
   nothing measurable. DBpedia's figure was 115×. Two unrelated tasks, the same shape.

3. **The lead is concentrated in one label, and that label is a convention.** Broken down
   by type, `span_marker` beats `openai_m` by +0.4693 F1 on `other` — Few-NERD's catch-all
   — which is **57.2%** of its support-weighted advantage. On `person` it **loses**
   (−0.0067). `other` has no inferable meaning; you cannot deduce membership from the word.
   Performance on it is close to a pure measure of corpus exposure.

4. **The zero-shot control scores exactly 0.0000 on that type.** `gliner`, same model
   class, same label set, never trained on Few-NERD, gets **0 of 86** `other` entities
   right — while reaching 0.7701 on `person`. This is the cleanest isolation of
   task-specific training in the repo.

5. **34 of 768 gold types (4.4%) are unanimously rejected by the whole field**, and reading
   them, the field is right: "Georgia Dome" filed as `location`, "Nazis" as `person`,
   "EDFL" as `event`. Resolving them the arms' way moves every hosted arm **+0.024 to
   +0.039** and `span_marker` **+0.0060** — it was trained on the convention and never lost
   those points. Its lead over the nearest hosted arm falls from 0.0810 to **0.0503**:
   **38% of that lead is conformity to the annotator, not correctness.**

6. **A scoring bug paid non-answers full marks, and no fingerprint could have caught it.**
   An unreadable output was indistinguishable from an empty prediction; on the 12% of
   items with no gold entities that scored **1.0**. Found and fixed mid-sweep; see §6.

---

## 1. What was measured

| | |
|---|---|
| Corpus | Few-NERD `supervised` test split, CC BY-SA 4.0 |
| Slice | 280 sentences, seeded random (`--seed 20260928`), `items_sha256` `95a1b9627073` |
| Dev slice | 56 sentences, a strict **prefix** of the same permutation — nested, so holdout analysis is honest |
| Gold | expert annotation, a JSON array of `{text, type}` per item |
| Density | 2.74 entities/sentence; **34 of 280 sentences have none** |
| Types | location 199, organization 172, person 166, other 86, product 58, art 30, building 29, event 26 |

The type distribution is left imbalanced. Rebalancing would make the slice
unrepresentative of the task.

**The 12% of sentences with no entities are load-bearing, not an edge case.** They are
where an arm that invents entities is caught, and they fix the floor.

### Arms

| Arm | What it is | Weights |
|---|---|---|
| `span_marker` | `guishe/span-marker-generic-ner-v1-fewnerd-fine-super`, **fine-tuned on Few-NERD's training split**, predicts the 66 fine types mapped down to 8 | 499 MB |
| `gliner` | `urchade/gliner_medium-v2.1`, zero-shot, **caller supplies the label set**, threshold 0.5 (library default, untuned) | 745 MB |
| 24 hosted | 8 vendors × {small, medium, large}, one prompt, temperature 0 | — |
| `capitalized` | every capitalised run, minus a stoplist written from English orthography | — |
| `nothing` | predicts the empty set, always | — |

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
bootstrap is needed. Corpus micro-F1 pools every tp/fp/fn into one figure. Both are
reported; the mean is the ranking metric.

---

## 3. Results

### 3.1 The leaderboard

| arm | f1 | untyped f1 | parsed | lat/item | cost |
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

`mistral_l` is **not in this table** and was not measured — see §7.

### 3.2 The only unambiguous winner this repo has produced

`span_marker` vs a family of 26 declared before any p-value was read, Holm step-down at
α = 0.05, sign-flip permutation on paired per-item F1:

```
separated from 26 of 26 opponents; ahead on the point estimate against 26 of 26
closest opponent: openai_m  delta +0.0810  wins 86/280  p = 0.0001  thresh 0.0500
```

Every other example in this repo produced a *group* at the top. This one produced a podium.

### 3.3 And behind it, the same tie as everywhere else

`openai_m` vs the same family:

```
separated from 19 of 26; ahead on the point estimate against 25 of 26

  NOT separated:
    gemma_l      +0.0383  p = 0.0084   ($0.0134)
    qwen_m       +0.0316  p = 0.0218   ($0.0396)
    qwen_s       +0.0214  p = 0.1484   ($0.0157)
    anthropic_m  +0.0204  p = 0.1668   ($0.2846)
    openai_l     +0.0148  p = 0.2495   ($0.1715)
    gemma_m      +0.0131  p = 0.4310   ($0.0088)
    anthropic_l  +0.0066  p = 0.6664   ($0.6897)
```

**$0.0088 to $0.6897 — 78× — for a difference the data cannot resolve.** DBpedia gave
115× on a completely different task. The consistency is the finding: at the top of a
hosted field, price stops predicting quality long before quality stops varying.

### 3.4 Where the lead actually comes from

Per-type F1, support-weighted contribution to `span_marker`'s advantage over `openai_m`:

| type | span_marker | openai_m | gliner | Δ | support | share of gap |
|---|---|---|---|---|---|---|
| location | 0.8170 | 0.7744 | 0.5889 | +0.0427 | 199 | 12.0% |
| organization | 0.7692 | 0.6863 | 0.5631 | +0.0829 | 172 | 20.2% |
| **person** | 0.8882 | **0.8949** | 0.7701 | **−0.0067** | 166 | **−1.6%** |
| **other** | 0.7709 | 0.3017 | **0.0000** | **+0.4693** | 86 | **57.2%** |
| product | 0.7407 | 0.6903 | 0.4821 | +0.0505 | 58 | 4.2% |
| art | 0.7761 | 0.7222 | 0.2593 | +0.0539 | 30 | 2.3% |
| building | 0.6567 | 0.5902 | 0.3385 | +0.0666 | 29 | 2.7% |
| event | 0.6296 | 0.5507 | 0.1828 | +0.0789 | 26 | 2.9% |

**Total support-weighted gap: +0.0921, of which `other` is 57.2%.**

(Per-type figures are typed F1 against gold as annotated. §3.6 shows what happens when the
annotation itself is the thing in dispute.)

`other` is Few-NERD's catch-all coarse type — languages, diseases, chemicals, awards,
currencies. The label carries no semantics: you cannot infer membership from the word
"other". So it is close to a pure measure of exposure to the corpus, and the three arms
line up exactly by exposure:

- `span_marker`, trained on the split — **0.7709**
- `openai_m`, general world knowledge, guessing from the label name — **0.3017**
- `gliner`, handed the bare word "other" with no exposure — **0.0000**, 0 of 86

**On `person` — the one label that means the same thing in every corpus — the frontier
hosted model wins.** That is the whole result in one row.

### 3.5 Task-specific training, isolated

`span_marker` 0.7674 vs `gliner` 0.4540 — same model class, same label set, same CPU, same
harness. The one variable is exposure to Few-NERD's training split, and it is worth
**+0.3134 F1**.

This is the question the summarisation and AG News examples kept running into and could not
answer, because neither had a matched zero-shot control. `gliner` is that control.

### 3.6 Annotation noise, and an upper bound on what it costs

34 of 768 gold entities (4.4%) carry a coarse type that ≥80% of the 25 learned arms
unanimously reject:

```
25/25  "georgia dome"                     gold location     -> arms building
25/25  "carolina first arena"             gold organization -> arms building
25/25  "nazis"                            gold person       -> arms organization
25/25  "edfl"                             gold event        -> arms organization
25/25  "olympic club"                     gold location     -> arms organization
25/25  "burgtheater"                      gold location     -> arms building
24/25  "fort wayne daisies"               gold person       -> arms organization
24/25  "maple blues awards"               gold other        -> arms event
24/25  "cameron mitchell restaurants"     gold building     -> arms organization
24/25  "bob evans restaurants"            gold building     -> arms organization
24/25  "tennessee performing arts center" gold location     -> arms building
23/25  "sanitarium"                       gold building     -> arms organization
23/25  "katolska bokforlaget"             gold art          -> arms organization
23/25  "furosemide"                       gold other        -> arms product
```

Independent models do not agree on a hallucination. Where twenty-five of them tag the same
span the same way against the annotation, the annotation is the thing most likely wrong —
and reading these, it is. A football league is not an `event`; a diuretic is not `other`;
a restaurant chain is not a `building`.

Resolving all 34 the arms' way gives an **upper bound**, not an estimate: resolving in the
arms' favour is what raises the number. It answers only "how much of the typed/untyped gap
could annotation account for at most".

| arm | as measured | bound | move |
|---|---|---|---|
| **span_marker** | 0.7674 | 0.7733 | **+0.0060** |
| openai_m | 0.6864 | 0.7230 | +0.0365 |
| openai_l | 0.6716 | 0.7102 | +0.0386 |
| anthropic_l | 0.6798 | 0.7053 | +0.0255 |
| gemma_m | 0.6733 | 0.6975 | +0.0242 |
| *(all 24 hosted)* | | | *+0.0238 to +0.0386* |
| gliner | 0.4540 | 0.4748 | +0.0208 |
| capitalized | 0.1913 | 0.1820 | **−0.0093** |

**`span_marker` moves four to six times less than the hosted field**, because it was
trained on the convention and was never losing those points. Its 0.0810 lead over
`openai_m` becomes **0.0503** under the bound: **38% of that lead is agreeing with the
annotator rather than being right.** It stays ahead, and it stays separated — but the
margin is materially smaller than the leaderboard shows.

`capitalized` moves *negative*, which is the sanity check on the whole calculation: an arm
whose types are near-random gains nothing from relabelling and can lose.

The GLiNER/SpanMarker pair was built to isolate task-specific training. It turned out to
isolate this too, from a direction I was not looking in.

### 3.7 Output budget is a model property, not a config detail

`glm_l` is the only arm with a serious parse failure rate: **0.836 parsed, 0.114 truncated**
at `max_tokens` 600. Of the other 22 hosted arms measured, 19 parsed at exactly 1.000 on
the identical budget; the three that did not are the llama family (0.986 / 0.943 / 0.993),
and none of them truncated — theirs is malformed JSON, a different failure.

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

Spearman ρ between the 56-item dev slice and the 280-item measurement slice, 27 arms:
**0.895**. Dev leader and measurement leader are the same arm.

Mean |rank move| 2.37 positions; **max 12** — `glm_l`, rank 11 → 23, for the reason in §3.7:
the dev slice sampled its truncation rate at 5.4% and the measurement slice found 16.4%.

**No winner's curse.** On the 224 items the dev slice never contained:

```
global test (permutation on within-item ranks): p = 0.0002 -> an arm effect exists
Nemenyi critical difference = 2.77 rank positions; observed span = 13.95
pairs distinguishable: 149 of 351

  fn_span_marker_n200_v1   avg rank 8.64   P(1st) = 1.00
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
         10      0.540     0.247             0.32                 3.23             1.0
         20      0.684     0.474             0.57                 2.49             1.0
         50      0.827     0.721             0.87                 1.70             1.0
        100      0.891     0.837             1.00                 1.12             1.0
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
look.** `span_marker` wins outright and separates from all 26. But decompose it:

- ~57% of the margin is one type whose definition exists only inside this corpus.
- **~38% of the margin** is agreeing with annotation the rest of the field rejects.
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
- On the type with a corpus-independent meaning, it loses.

So the defensible claim is: **if your labels are a fixed in-house taxonomy and you can
label training data, a 476MB model on CPU beats every frontier LLM at 0.76 s/item and $0.**
That is a real and useful claim — it is the podcast-product case. The claim it does *not*
support is that the small model is better at named-entity recognition in general.

**The hosted field is a commodity at the top.** Eight arms, 78× price spread, no
resolvable difference. `gemma_m` at $0.0088 is inside the top group; `anthropic_l` at
$0.6897 is too. Buying the expensive one bought 3.05 s/item of latency and nothing else
measurable.

**`untyped_f1` barely reorders anything but explains a lot.** Spearman between the typed
and untyped orderings is **0.955** over 27 arms, same leader, so it is not an alternative
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
**20 of the 68 items this experiment had scored unreadable were readable all along.**

| arm | f1 before | f1 after | unreadable before | after |
|---|---|---|---|---|
| `glm_l` | 0.5269 | **0.5662** | 46 | **32** |
| `llama_l` | 0.5911 | **0.5990** | 4 | **1** |
| `llama_m` | 0.5704 | **0.5740** | 16 | **13** |
| `deepseek_m` | 0.6122 | **0.6148** | 0 | 0 |

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
no answer there, and mining one out of an explanation would be inventing it. 32 of its
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

- **`mistral_l` was never measured on the 280-item slice.** `mistralai/mistral-large-2512`
  is rate-limited upstream on OpenRouter's shared pool
  (`limit_source: upstream_provider_shared_pool`); litellm burns 6 internal retries per
  call before returning 429. Measured rate: **3 items in 7 minutes**, ~11 hours for the arm.
  Its **dev** score on 56 items is **0.6005** (parsed 1.000) and is *not* comparable to the
  table in §3.1. Every "26 of 26" and "19 of 26" in this report is out of a family of 26,
  not 27, for this reason. Resume with:
  `EVAL_RUNS_DIR=data/runs python scripts/experiment_run.py --config ../examples/ner-few-nerd/configs/arm_mistral_l_n200.yaml`
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
  is not an independent judge.
- **`span_marker`'s fine→coarse mapping is asserted, not verified against a spec.** Few-NERD
  fine labels are literally `coarse-detail`, so the mapping is deterministic, but no test
  compares it to an authoritative list.
- **English Wikipedia prose only.** The relevance this example gives up to keep a clean
  licence is noisy speech — WNUT-2017 would have been closer to podcast transcripts, and is
  licensed `other`.
- **No ML arm ran on GPU.** Both local arms are CPU fp32. Latency figures are not
  deployment figures.

---

## 8. Reproduction

```bash
python examples/ner-few-nerd/fetch.py --n 280
cd harness
make dataset-create DATASET_ID=few_nerd_280 ARGS='--source-dir data/sources/few_nerd_280'
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
