# Finding a document in 5,183 of them — BM25, four encoders and twelve LLM rerankers

One task — given a scientific claim, find the abstracts that support or refute it —
measured across BM25, four sentence-transformer bi-encoders, twelve hosted LLMs reranking
BM25's output, and two floors.

It is the fourth worked example for [`../../harness`](../../harness), and it exists because
**the answer is a ranked list, and the corpus is not the items**. Summarisation compares
one text to one text. Classification compares one label to one label. Extraction compares
a set to a set, where order is irrelevant. Here order carries meaning, and the thing being
searched is a 5,183-document corpus that no item mentions and no arm is scored on.

---

## Get the data

**Nothing is committed** — neither the queries nor the corpus.

```bash
cd examples/retrieval-scifact
uv sync --extra local          # --extra local pulls sentence-transformers; plain `uv sync` does not
uv run fetch.py --n 200        # queries + qrels + the WHOLE corpus (~2 min)
uv run fetch.py --n 40 --skip-corpus   # dev slice, a strict PREFIX of the 200
```

The fetcher writes **three** things, and the third is new to this repo:

```
data/sources/scifact_<n>/<qid>.txt          the query
data/references/gold/scifact_<n>/<qid>.txt  JSON [{doc_id, score}] — the qrels
data/corpora/scifact/corpus.jsonl           all 5,183 abstracts, ALWAYS all of them
```

### The corpus is never sliced, and that is not an oversight

`--n` slices the **queries**. The corpus stays at 5,183 documents whatever `--n` says.

Sampling it would be the most damaging shortcut available here. Retrieval difficulty is a
property of the haystack: drop 90% of the documents and every arm's nDCG rises, because
most of what it could have wrongly ranked above the answer is gone. A 200-query run and a
40-query run over the same corpus are comparable; over different corpora they are two
different tasks wearing one name.

### Why the corpus gets its own directory

It is **not `sources/`** — no one-file-per-item correspondence, 200 queries search 5,183
documents. **Not `references/`** — it is the haystack, not ground truth. **Not
`materialized/`** — not derived from anything in this repo. See
[`../../harness/data/corpora/README.md`](../../harness/data/corpora/README.md).

**`corpus_sha256` is in every arm's fingerprint.** Two runs over the same queries against
different corpora agree on `dataset_id`, `items_sha256`, `reference_id`, adapter hash and
every parameter. Nothing else would tell them apart, and the corpus is where the answer is.

---

## Run it

```bash
cd harness
for f in ../examples/retrieval-scifact/configs/arm_*_n200.yaml; do
  ../examples/retrieval-scifact/.venv/bin/python scripts/experiment_run.py --config "$f"
done
```

The whole 19-arm measurement sweep is **$1.94 as the provider billed it** — $1.04 by
this repo's price table, which understates it by 1.87×, the widest gap of the five
experiments (see the report §7). The local arms are free; the dense ones cost time
instead, and that cost is reported rather than hidden.

---

## What a ranked list breaks

### `warmup()` stops being a smoke test and becomes the build

For every other example, warmup proves the endpoint answers. Here it **indexes the
corpus** — and the harness already timed warmup separately and excluded it from per-item
latency, a decision made for model loading in the first example that turns out to be
exactly right for an index build. So index cost becomes a reported column:

```
bm25         0.8 s
minilm     194 s
bge_small  874 s
mpnet     1825 s
e5_base   1825 s
```

Dense embeddings are cached to disk keyed on **corpus hash**, model, prefix and device, so
a rerun loads in ~6 s instead of rebuilding. Keyed on the hash and not the path, so a
corpus change misses every cache rather than silently searching the wrong haystack;
`index_built_this_run` is in the fingerprint, because 1825 s and 6 s of warmup are both
honest and the number alone cannot say which.

### The arm is a pipeline, so it has a ceiling it did not choose

A reranking arm is BM25 top-100 → the LLM reorders the top-20 → **BM25's remaining 80 are
appended below, unchanged**. The pipeline's recall@100 is therefore BM25's recall@100 *by
construction*, and every nDCG@10 movement is the reordering alone. Verified: all twelve
rerankers report `recall_100 = 0.8586`, identical to BM25's.

`retrieval_report.py` computes the oracle ceiling — a perfect reordering of the arm's own
candidates — because that is the only honest denominator for "how much better could this
get *without* a better retriever".

### Three things that look like leniency and are rewards for bad behaviour

Decided and asserted **before any arm ran**, because the extraction scorer in this repo
shipped with exactly this class of bug:

- an **unreadable answer** is not an empty ranking — it scores zero
- a **hallucinated document id keeps its slot** — dropping it would slide real documents up
  and improve the score, making invention a strategy
- a **duplicate is collapsed**, not counted — or one document fills the top 10

The suite caught a real parser bug before any arm ran: a preamble before the JSON array
made it return the literal string `["a","b"]` as a document id.

---

## The arms

| Arm | What it is | Cost |
|---|---|---|
| `bm25` | `rank_bm25.BM25Okapi`, defaults, no stemming or stoplist | $0, 0.8 s build |
| `minilm` / `mpnet` | general sentence-similarity encoders, symmetric, no prefix | $0 |
| `bge_small` / `e5_base` | **retrieval-trained**, asymmetric query/document prefixes | $0 |
| 12 hosted ⟳ | reranking BM25's top-20, temperature 0, reasoning off | ~$0.05–0.15 |
| `random` / `first_k` | a seeded permutation; the corpus in id order | $0 |

**The query prefix is part of the model, not a style choice.** BGE and e5 are trained with
specific instructions on the query side (and e5 on the document side too); omitting one
costs several nDCG points and raises no error. Both are fingerprinted, and `doc_prefix` is
part of the index cache key so a prefixed arm cannot silently reuse an unprefixed index.

---

## Results

Full write-up: [`../../research/REPORT_RETRIEVAL.md`](../../research/REPORT_RETRIEVAL.md).

```
glm_s   ⟳ BM25      0.7437   $0.055    best overall, separates from only 6 of 18
e5_base             0.7191   $0        FREE, and in the tie group
bge_small           0.7097   $0        FREE, and in the tie group
bm25                0.6451   $0        every reranker beats it
random              0.0005   $0

glm_s   ⟳ e5_base   0.7891   $0.055    the registered prediction: 0.786-0.797
```

Four things worth reading the report for:

1. **A tie of twelve or thirteen arms, and two of them are free.** `e5_base` and `bge_small` — local,
   CPU, $0 — are not statistically distinguishable from any paid reranker.
2. **A prediction registered before the arm existed.** The ceiling analysis said swapping
   only the first stage would reach 0.786–0.797. It reached **0.7891**, and the *mechanism*
   transferred too: headroom-used moved 90.9% → 90.2%.
3. **The dev slice picked the wrong winner** — its leader finished 10th of 19.
4. **One arm looked broken and was misconfigured by me:** this adapter never disabled
   reasoning, which the other three examples all do.
