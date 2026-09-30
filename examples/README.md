# The worked examples

Five experiments, four metric shapes, one harness. Each exists because it **breaks
something the previous one did not** — the harness grew by meeting a task it could not
already express, and every example's most interesting output is the defect it exposed.

None of them ships a corpus. Each ships a `fetch.py` download recipe, and the data is
gitignored.

> ### Start here
>
> **[`../docs/REFERENCE.md`](../docs/REFERENCE.md)** — the encyclopedia. Every metric
> explained with a link to its paper, every model with a link to its weights, every
> dataset with its licence, and every statistical test with the reason it was chosen.
> Read it once and the five examples stop needing footnotes.
>
> Each example then has **three** documents:
>
> | file | answers |
> |---|---|
> | `README.md` | **how** — commands, arms, what the data licence permits |
> | `METHOD.md` | **why** — why this dataset, why these arms, why these criteria, and what each choice gives up |
> | the report in [`../research/`](../research) | **what happened** — results, statistics, corrections, and what was *not* covered |

| Example | Task | Shape of the answer | What it broke | Why | Report |
|---|---|---|---|---|---|
| [`summarization-cnn-dailymail`](summarization-cnn-dailymail) | summarise a news article | one text vs one text, **continuous** | nothing — it *is* the baseline the others are measured against | [METHOD](summarization-cnn-dailymail/METHOD.md) | [report](../research/REPORT_SUMMARIZATION.md) |
| [`classification-ag-news`](classification-ag-news) | 4-way topic label | one label vs one label, **0 or 1** | a discrete metric ties, and the duplicate-run check flagged honest ties as copies | [METHOD](classification-ag-news/METHOD.md) | [report](../research/REPORT_CLASSIFICATION.md) |
| [`classification-dbpedia-14`](classification-dbpedia-14) | 14-way ontology label | same, but **saturated** | rank-stability measured the alphabet when most arms tie | [METHOD](classification-dbpedia-14/METHOD.md) | [report](../research/REPORT_CLASSIFICATION.md) |
| [`ner-few-nerd`](ner-few-nerd) | named entities + types | **a set** vs a set, order irrelevant | an unreadable answer scored 1.0, and no fingerprint covered the scorer | [METHOD](ner-few-nerd/METHOD.md) | [report](../research/REPORT_NER.md) |
| [`retrieval-scifact`](retrieval-scifact) | find the abstract supporting a claim | **a ranked list** over a 5,183-doc corpus | the corpus is not the items, so nothing in the fingerprint identified it | [METHOD](retrieval-scifact/METHOD.md) | [report](../research/REPORT_RETRIEVAL.md) |

Shared scoring code lives in [`_shared/`](_shared): `classification.py`, `extraction.py`,
`retrieval.py`, plus `hf_identity.py` for pinning local model weights.

---

## What all five agree on

**[`../research/REPORT_SYNTHESIS.md`](../research/REPORT_SYNTHESIS.md)** — the
cross-cutting report. Seven findings that hold across every experiment, each computed
from the stored runs rather than quoted: the dearest arm is never first (5/5), four of
five leaderboard tops are statistical ties, a pilot with ρ ≈ 0.8 picked the wrong winner
three times in five, and the scoring code moved single arms further than most model swaps
did.

It also answers the deployment question directly. **Every experiment has a $0 answer**:
a model fine-tuned on its dataset ranked first in 3 of 3, a proprietary model never
separated from the best open-weight one in any of the five, and **a 64 GB machine reaches
the same answer as unlimited hardware on four of the five tasks**. Three of the four
task-specific winners are under 2 GB and need no GPU.

## What each one actually found

### Summarisation — price does not predict quality
24 hosted models over 200 news articles. The dearest arm, at **52× the price** of the
cheapest, ranks **15th of 24**. Two *independent* 100-article evals of the same models
agree at only **ρ = 0.80**, and at 20 articles at **ρ = 0.42**.

Later, ML arms were added and BART took the lead — by **0.00008** over the best LLM across
200 articles. Its lead at n=20 had been 0.0737. That is the cleanest winner's-curse
demonstration in the repo, and it turns up twice: in the leaderboard, and in
`P(both halves crown the same arm)` collapsing to 0.01.

### AG News — a small model wins, on a task with headroom
A 44MB fine-tuned classifier scored **0.9450** against a hosted field of 0.835–0.910, and
was ahead of all 24. It separated from 18 of 27 — **a group, not a podium**.

The example also found that **the scoring code is a bigger lever than the model choice for
some arms**: the label parser is worth 8.6 accuracy points to `glm_l`, wider than the gap
separating most of the field.

### DBpedia-14 — the same experiment, the opposite regime
Deliberately paired with AG News, and **they should not be read one at a time.** Here the
task is saturated: the leader separated from only **8 of 26**, and the top ten arms are one
group across a **115× price range**.

Both corpora carry systematic label noise, and on DBpedia it is the size of the signal —
the top ten are separated by four items, three of which the entire field disputes because
the gold label is wrong.

### Few-NERD — task-specific training, isolated
A 476MB span tagger fine-tuned on the corpus beat all 24 LLMs and separated from **26 of
26** — the only unambiguous winner in the repo. But **57% of its margin is one entity
type**, `other`, whose membership you cannot infer from the label because it is a
convention of that corpus. On `person` — the one type that means the same thing everywhere
— a frontier LLM beats it.

A matched zero-shot control (`gliner`, same model class, never trained on Few-NERD) scores
**0.0000** on `other`, 0 of 86. And 34 of 768 gold types are unanimously rejected by the
whole field; resolving them moves every hosted arm ~+0.03 and the fine-tuned model +0.006,
so **38% of its lead is agreeing with the annotator rather than being right**.

### SciFact — pipelines have a ceiling they did not choose
Twelve LLM rerankers tie with each other **and with two free local encoders**. `e5_base`
(0.7191, $0, CPU) is not statistically distinguishable from any paid arm.

A reranker cannot rank a document its first stage never returned, so the ceiling analysis
produced a **prediction registered before the arm existed**: swapping only the first stage
should move the pipeline from 0.74 to 0.786–0.797. Measured: **0.7891**, and the mechanism
transferred too — the share of available headroom taken moved 90.9% → 90.2%.

---

## The pattern across all five

**At the top of a field, price stops predicting quality well before quality stops
varying.** Every example produced a tie group spanning a large price range:

| | tie at the top | price span |
|---|---|---|
| summarisation | dearest arm ranks 15th of 24 | 52× |
| AG News | leader tied with 9 | — |
| DBpedia | a group of 10 | 115× |
| Few-NERD | 8 hosted arms | 78× |
| SciFact | 12 arms, **2 of them free** | 7.6× billed, among cheap arms |

And every example found something wrong with the instrument before it found anything about
the models. The append-only journal, [`../research/NOTES.md`](../research/NOTES.md), is the
record of that — including the retractions.

---

## Running one

```bash
cd examples/<name>
uv sync --extra local      # --extra local pulls the local ML arms; plain `uv sync` does not
uv run fetch.py --n <N>
cd ../../harness
make dataset-create DATASET_ID=<id> ARGS='--source-dir data/sources/<id>'
make dataset-materialize DATASET_ID=<id>
for f in ../examples/<name>/configs/arm_*_n200.yaml; do
  ../examples/<name>/.venv/bin/python scripts/experiment_run.py --config "$f"
done
```

Each example's own README has the exact commands, its arms, and what its data licence
permits. Costs are what the provider billed (`usage.cost`), not a price table — see
[`REPORT_RETRIEVAL.md`](../research/REPORT_RETRIEVAL.md) §7 for why that distinction
cost this repo four reports' worth of corrections.

## Unfinished work

Every example has a handover for what was not run and why, in
[`../research/`](../research): blocked ML arms needing a machine that can load pickle
checkpoints, one NER arm rate-limited upstream, and five frontier rerankers that cost
About $12 against the retrieval sweep's $1.94 billed.

---

## Credits

Every dataset, model, paper and library used across the five examples is credited with its
licence in **[`../docs/REFERENCE.md#credits`](../docs/REFERENCE.md#credits)**, and again
per-experiment at the bottom of each `METHOD.md`.

Every cited paper's redistribution licence is recorded in
[`../docs/papers/README.md`](../docs/papers/README.md), with a fetcher for the twelve that
permit mirroring. All citations were verified by fetching them and comparing titles.

**Nothing is redistributed here** — no corpus, no model weights, no papers, no provider output. Each
example ships a download recipe, and dataset identity travels as a content hash
(`items_sha256`, `corpus_sha256`) recorded inside every run.
