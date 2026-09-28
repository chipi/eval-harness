# Pulling entities out of a sentence — 24 LLMs against two span taggers

One task — find every named entity in a sentence and say what kind it is — measured across
24 hosted models from 8 vendors, a span tagger fine-tuned on this very corpus, a zero-shot
span tagger that has never seen it, a capitalisation heuristic and an arm that predicts
nothing at all.

It is the third worked example for [`../../harness`](../../harness), and it exists because
**the answer to this task is a set**. Summarisation compares one text to one text and
scores continuously. Classification compares one label to one label and scores 0 or 1.
Neither prepares the instrument for a comparison where both sides have a variable number of
members and you have to decide which member matches which.

Every interesting decision in this example is in that matching.

---

## Get the data

**Nothing is committed.** The slice downloads to your machine and is gitignored.

```bash
cd examples/ner-few-nerd
uv sync --extra local         # --extra local pulls gliner + span_marker; plain `uv sync` does not
uv run fetch.py --n 280       # the measurement slice
uv run fetch.py --n 56        # the dev slice, a strict PREFIX of the 280
```

`uv sync` without `--extra local` provisions only the hosted arms, and the two ML arms then
fail at import. That is how the DBpedia zero-shot arm was lost for a sweep.

Texts land in `../../harness/data/sources/few_nerd_<n>/`, gold in
`../../harness/data/references/gold/few_nerd_<n>/`. A gold file holds a **JSON array of
`{text, type}`**, not one word — because the answer is a set. Then freeze:

```bash
cd ../../harness
PYTHON=../examples/ner-few-nerd/.venv/bin/python make dataset-create \
    DATASET_ID=few_nerd_280 ARGS='--source-dir data/sources/few_nerd_280'
PYTHON=../examples/ner-few-nerd/.venv/bin/python make dataset-materialize DATASET_ID=few_nerd_280
```

### The draw is plain random, and the other two fetchers stratify

The classification fetchers stratify by class because there an item **has** a class. A
sentence here carries several entities of several types at once, so there is no class to
stratify on — the unit of sampling is the sentence. Measured on the first 300 test rows the
split is not sorted by anything visible either, so a random draw is both necessary and
sufficient.

Seeded, and **nested**: `--n 56` takes a prefix of the same permutation `--n 280` does,
which is what `holdout_significance --exclude-dataset` needs to be honest.

### Degenerate items are filtered, and that is not cherry-picking

`--min-tokens 3` drops sentences too short to pose the task. The dev slice contained one
whose entire text was the single character `p`.

It is a real row, and keeping it would be defensible on faithfulness grounds — except for
what it measures. Three of 24 hosted arms failed it, and the two that failed **worst** were
right: they replied "You didn't provide the sentence." One arm tagged the letter `p` as an
entity and scored better for it. An arm that blindly answers `[]` scores 1.0.

The item rewards not looking and punishes noticing. That is different from the label noise
the classification examples deliberately kept — a mislabelled item still poses the task.
The filter is declared, its threshold is a flag, and what it removed is printed at the end
of every fetch. A silent drop would be the cherry-pick.

### Licence — the cleanest of the four corpora here

CC BY-SA 4.0, stated on the dataset card. The usual alternatives do not offer one:
CoNLL-2003's Reuters text needs a separate agreement, `tner/wnut2017` is licensed `other`,
OntoNotes is behind LDC. WNUT would have been closer to podcast-style noisy speech, and
that relevance is what this example gives up to keep the licence clean.

---

## Run it

```bash
cd harness
for f in ../examples/ner-few-nerd/configs/arm_*_n200.yaml; do
  ../examples/ner-few-nerd/.venv/bin/python scripts/experiment_run.py --config "$f"
done
```

~14 minutes and ~$0.09 per hosted arm; the two ML arms are free and run on CPU. The whole
measurement sweep is **$2.05**.

Then the analysis — all of it $0, all of it from stored outputs:

```bash
python scripts/rescore.py --dataset-id few_nerd_280 --match fn_ --out data/runs-rescored
EVAL_RUNS_DIR=data/runs-rescored python scripts/extraction_report.py --dataset-id few_nerd_280 --match fn_
python scripts/family_test.py --dataset-id few_nerd_280 --a fn_span_marker_n200_v1 \
    --against _n200_v1 --metric f1 --runs-dir data/runs-rescored
```

---

## What a set breaks that a label did not

### The empty cases are 12% of the corpus, so they are not edge cases

34 of 280 sentences contain no entities. The conventions were fixed before any arm ran:

| gold | prediction | F1 |
|---|---|---|
| empty | empty | **1.0** — it correctly found nothing |
| empty | non-empty | 0.0 |
| non-empty | empty | 0.0 |
| any | **unreadable** | **0.0** |

The first row is the one people get wrong by leaving precision undefined and dropping the
item — which would delete exactly the items where a hallucinating arm should be punished.

The last row exists because the first version did not have it, and an arm whose output
could not be read arrived at the scorer as an empty list and collected the full 1.0. See
[the report](../../research/REPORT_NER.md) §6.

### Matching is one-to-one

A prediction satisfies at most one gold member and vice versa. Without that, one prediction
overlapping three gold entities counts as three true positives and precision becomes
unbounded nonsense.

### Per-item F1 is a legitimate metric here, and macro-F1 was not

`_shared/classification.py` could not give the harness a macro-F1 metric, because macro-F1
needs a confusion matrix over the whole run — there is no per-item number whose average is
macro-F1. An extraction item has its own gold set and its own predicted set, so precision,
recall and F1 are all well defined **on that item**, and their means are honest per-item
metrics. `family_test.py`'s sign-flip permutation therefore works directly and no bootstrap
is needed.

What is still not per-item is **corpus micro-F1**, and it lives in `extraction_report.py`.

### Typed and untyped, because they say which problem you have

`untyped_f1` asks "did it find the entity at all"; `f1` asks "and did it label it right".
`type_penalty` is the difference, and a type-confusion problem is fixed differently from a
detection problem. `capitalized` is the extreme: untyped **0.6191**, typed **0.1913**.

### The scorer is fingerprinted, all of it

`normalizer_sha256` covered only the string normaliser, on the reasoning that a normaliser
has the most room to move a score. The reasoning was right and the scope was wrong — the
bug above lived in the matcher. `scorer_sha256` now covers normalisation, member coercion,
matching, the per-item rule and the metric block together.

---

## Two caveats in the data itself, both visible in the first three sentences

**IO tagging.** Few-NERD tags with IO rather than BIO, so two adjacent entities of the same
type merge into one span. Some gold boundaries are wrong by construction and no arm can
recover the intended ones. **This report does not quantify how much of each arm's error is
that.**

**Annotation noise, and rather a lot of it.** 34 of 768 gold entities carry a coarse type
that ≥80% of the 25 learned arms unanimously reject — "Georgia Dome" as `location`, "Nazis"
as `person`, a football league as an `event`, a diuretic as `other`.
`extraction_report.py`'s TYPE DISAGREEMENTS section is the tool for it.

---

## The arms

| Arm | What it is | Why it is here |
|---|---|---|
| `span_marker` | `guishe/span-marker-generic-ner-v1-fewnerd-fine-super`, 476MB, **fine-tuned on this corpus** | the in-distribution ceiling |
| `gliner` | `urchade/gliner_medium-v2.1`, 745MB, zero-shot, **caller supplies the labels** | the matched control: same class, never trained here |
| 24 hosted | 8 vendors × 3 price tiers, one prompt, temperature 0, `max_tokens` 600 | the field |
| `capitalized` | every capitalised run minus an orthography stoplist | finds spans, cannot type them |
| `nothing` | the empty set, always | a calibration check on the scorer, then a floor |

`max_tokens` is 600 here against 200 in the classification examples, because the answer is
a JSON array of ~2.7 objects rather than one word. One arm still ran out of it — see the
report §3.7.

**The GLiNER/SpanMarker pair is the point of this example.** The DBpedia example could not
run a fine-tuned ML arm at all, so its ML-vs-LLM question went unanswered. Here both load,
differing in exactly one variable: exposure to Few-NERD's training split.

---

## Results

Full write-up: [`../../research/REPORT_NER.md`](../../research/REPORT_NER.md).

```
span_marker   0.7674   $0        separated from 26 of 26 under Holm
openai_m      0.6864   $0.2034   best hosted; separated from only 19 of 26
gemma_m       0.6733   $0.0057   inside the top group, 121x cheaper than anthropic_l
gliner        0.4540   $0        same model class, no training-split exposure
capitalized   0.1913   $0
nothing       0.1250   $0        = the rate at which an empty answer is correct
```

Three things worth reading the report for:

1. **The first unambiguous winner in this repo.** Both classification corpora produced a
   tied group at the top. This produced a podium.
2. **57% of that winner's lead is one entity type** — `other`, Few-NERD's catch-all, whose
   membership you cannot infer from the label. On `person`, the one type that means the
   same thing everywhere, the frontier LLM **wins**.
3. **38% of its lead over the nearest hosted arm survives only because it agrees with
   annotation the rest of the field rejects.**
