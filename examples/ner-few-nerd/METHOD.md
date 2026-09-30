# Method — why this experiment is built the way it is

Companion to [`README.md`](README.md) and
[`REPORT_NER.md`](../../research/REPORT_NER.md). Terms in
[`docs/REFERENCE.md`](../../docs/REFERENCE.md).

---

## The task, and what it broke

Find every named entity in a sentence and say what kind it is. The answer is **a set** —
variable size on both sides, order irrelevant — and that broke things the first two shapes
never touched:

1. **Matching has to be decided.** With sets, you must say which predicted member
   satisfies which gold member. Matching is **one-to-one** here: without it, one prediction
   overlapping three gold entities counts as three true positives and precision becomes
   unbounded nonsense.
2. **The empty case is 12% of the corpus.** 34 of 280 sentences contain no entities, so
   "gold empty, prediction empty" is not an edge case — it is where an arm that invents
   entities gets caught, and it fixes the floor.
3. **An unreadable answer looked like an empty one.** The first version of the scorer took
   only the parsed set, so a model whose output could not be read arrived as `[]` and
   collected **1.0** on every empty-gold item. `glm_s`'s predecessor `glm_l` did exactly
   that six times. `parsed` is now passed *through* to the scorer, not merely reported
   beside it.
4. **The scorer itself was unfingerprinted.** `normalizer_sha256` covered the string
   normaliser and nothing else — the bug lived in the per-item rule, which no hash covered.
   `scorer_sha256` now covers the whole thing.

## Why Few-NERD

[`DFKI-SLT/few-nerd`](https://huggingface.co/datasets/DFKI-SLT/few-nerd),
[Ding et al. 2021](https://aclanthology.org/2021.acl-long.248/), **CC BY-SA 4.0** — an
actual grant, and the cleanest licence of the five corpora here.

The alternatives do not offer one: CoNLL-2003's Reuters text needs a separate agreement,
[`tner/wnut2017`](https://huggingface.co/datasets/tner/wnut2017) is licensed `other`, and
OntoNotes is behind the LDC.

> **What that costs.** WNUT-2017 is noisy user-generated text — far closer to podcast
> transcripts, which is the actual application. **Relevance was traded for a clean
> licence**, and the report says so.

Two properties of the data that shape every number:

- **IO tagging, not BIO.** Two adjacent entities of the same type merge into one span. Some
  gold boundaries are therefore wrong *by construction* and no arm can recover the intended
  ones. How much of each arm's error is this is **not quantified anywhere** — a stated gap.
- **The draw is plain random, not stratified.** Unlike the classification fetchers: a
  sentence carries several entities of several types at once, so there is no single class
  to stratify on. The unit of sampling is the sentence.

## Why these arms

The pair is the whole point of this example:

| Arm | Trained on Few-NERD? | Why it is here |
|---|---|---|
| [`span_marker`](https://huggingface.co/guishe/span-marker-generic-ner-v1-fewnerd-fine-super) | **Yes** | [SpanMarker](https://github.com/tomaarsen/SpanMarkerNER), 499 MB. The in-distribution ceiling. Predicts the 66 fine types, deterministically mapped to the coarse 8. |
| [`gliner`](https://huggingface.co/urchade/gliner_medium-v2.1) | **No** | [GLiNER](https://arxiv.org/abs/2311.08526), 745 MB. Zero-shot, and the **caller supplies the label set** — so it can be handed Few-NERD's eight types directly with no lossy mapping. |

**Why this pair and not an off-the-shelf NER model.** Most predict their own taxonomy —
CoNLL's four types, OntoNotes' eighteen — and using one would need a lossy mapping onto
Few-NERD's eight, confounding *model quality* with *mapping loss*. GLiNER takes the labels
as input, so the comparison is clean **and** the model has never seen this dataset. That is
why spaCy is not here.

The DBpedia example could not load a fine-tuned ML arm at all, so its ML-vs-LLM question
went unanswered. This pair exists to answer it: the two differ in **exactly one variable**,
exposure to the training split, and it is worth **+0.3134 F1**.

Plus two floors: `nothing` (the empty set, always) and `capitalized` (every capitalised
run minus an orthography stoplist).

> **`gliner`'s threshold is untuned** — 0.5, the library default. It is this arm's decision
> boundary and is in the fingerprint. Tuning it on the dev slice would be legitimate, but
> it would then be a *tuned* arm and would have to say so. A tuned GLiNER might close some
> of that +0.3134, and nothing here bounds how much.

## Why these success criteria

**Ranked by per-item `f1`** — and unlike classification, a per-item F1 is *legitimate*
here. An item has its own gold set and its own predicted set, so precision, recall and F1
are all well defined on that item. Their means are honest per-item metrics, which means
the sign-flip permutation test works directly and no bootstrap is needed.

What is still **not** per-item is corpus micro-F1 — pooling every tp/fp/fn into one figure.
Mean-of-per-item-F1 and micro-F1 answer different questions ("how did it do on a typical
sentence" vs "over all the entities"), so the raw counts ride along and micro-F1 lives in
[`extraction_report.py`](../../harness/scripts/extraction_report.py).

**The typed/untyped pair is the design's core.** `untyped_f1` asks *did it find the entity
at all*; `f1` asks *and did it label it right*; `type_penalty` is the difference. A
type-confusion problem is fixed differently from a detection problem, and a single number
cannot say which you have. `capitalized` is the extreme: untyped **0.6191**, typed
**0.1913**.

**The empty conventions, fixed before any arm ran:**

| gold | prediction | F1 | why |
|---|---|---|---|
| empty | empty | **1.0** | it correctly found nothing |
| empty | non-empty | 0.0 | everything predicted is a false positive |
| non-empty | empty | 0.0 | everything missed |
| any | **unreadable** | **0.0** | it did not predict the empty set; it failed |

Leaving precision undefined and dropping the first row — the common shortcut — would delete
exactly the items on which a hallucinating arm should be punished.

**Normalisation is part of the system under test.** Casefold, strip accents and
punctuation, drop a leading article. Deliberately **not** stemming: "Olympics" and
"Olympic" are surface forms a reader would judge differently, and collapsing them grades a
different task. The whole rule is hashed into `scorer_sha256`.

**The consensus pass is the label-noise instrument**, and for sets it has *two* directions
that are not symmetric: a gold span almost nobody found (often an IO artifact), and a span
almost everybody predicted that is not in gold — the stronger signal, because independent
models do not agree on a hallucination. A span in **both** lists differs only in type, and
that is the highest-confidence annotation error available: 34 of 768 gold types are
unanimously rejected by all 25 learned arms.

---

## Credits

**Dataset** — [Few-NERD](https://huggingface.co/datasets/DFKI-SLT/few-nerd), **CC BY-SA
4.0**. [Ding et al., ACL 2021](https://aclanthology.org/2021.acl-long.248/). Not
redistributed; [`fetch.py`](fetch.py) downloads a slice.

**Models** —
[`guishe/span-marker-generic-ner-v1-fewnerd-fine-super`](https://huggingface.co/guishe/span-marker-generic-ner-v1-fewnerd-fine-super)
([SpanMarker](https://github.com/tomaarsen/SpanMarkerNER), Tom Aarsen) ·
[`urchade/gliner_medium-v2.1`](https://huggingface.co/urchade/gliner_medium-v2.1)
([GLiNER](https://arxiv.org/abs/2311.08526), Zaratiana et al., built on
[DeBERTa-v3](https://arxiv.org/abs/2111.09543)). Hosted models in
[`docs/REFERENCE.md`](../../docs/REFERENCE.md#hosted--24-arms-8-vendors--3-price-tiers).

**Method** — entity F1 follows the
[CoNLL-2003 shared task](https://aclanthology.org/W03-0419/) convention.

**Software** — [gliner](https://github.com/urchade/GLiNER) ·
[span-marker](https://github.com/tomaarsen/SpanMarkerNER) ·
[transformers](https://github.com/huggingface/transformers) 4.55.4 ·
[torch](https://github.com/pytorch/pytorch) 2.2.2 ·
[sentencepiece](https://github.com/google/sentencepiece) ·
[protobuf](https://protobuf.dev/) · [LiteLLM](https://github.com/BerriAI/litellm) ·
[uv](https://github.com/astral-sh/uv).
