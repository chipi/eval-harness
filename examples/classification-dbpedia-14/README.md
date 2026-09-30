# Fourteen classes, a ceiling, and why one example is not enough

One task — put a Wikipedia abstract into one of fourteen DBpedia ontology classes —
measured across 24 hosted models, a zero-shot NLI model, a hand-written rule set and a
constant.

It is the sibling of [`../classification-ag-news`](../classification-ag-news) and it
exists to be the **opposite regime**. Read the two together; neither alone supports the
conclusion the pair does.

| | AG News | DBpedia-14 |
| --- | --- | --- |
| classes | 4 | 14 |
| hosted field | 0.835 – 0.910 | 0.939 – 0.993 |
| fine-tuned ML arm | beat all 24 | **0.9857 — tied with the top group, not above it** (needs torch ≥ 2.6) |
| licence | `unknown`, non-commercial | **CC-BY-SA 3.0 + GFDL** |
| outcome | a winner | a group of eleven |

---

## Get the data

```bash
cd examples/classification-dbpedia-14
uv sync --extra local          # --extra local matters; the zero-shot arm needs torch
uv run fetch.py --n 280        # 20 per class
uv run fetch.py --n 56         # dev slice, a random subset of the 280
```

Then freeze them:

```bash
cd ../../harness
PYTHON=../examples/classification-dbpedia-14/.venv/bin/python make dataset-create \
    DATASET_ID=dbpedia_280 ARGS='--source-dir data/sources/dbpedia_280'
PYTHON=../examples/classification-dbpedia-14/.venv/bin/python make dataset-materialize \
    DATASET_ID=dbpedia_280
```

### The fetcher seeks, and it draws at random

DBpedia's test split is **sorted by class** — the first 600 rows are all `Company`. A
pool scan would need ~70,000 rows to reach the last class, so this fetcher seeks: class
*c* occupies offsets `[c*5000, (c+1)*5000)`, verified at both ends of all fourteen blocks,
and re-checked on every row it receives. A re-upload that reordered the split would
otherwise produce a confidently mislabelled dataset.

Within each block the draw is a **seeded random** prefix of a permutation, not the first
k. That is the fix for what AG News found: its first-k dev slice was nested but
unrepresentative, and one arm read 0.35 there against 0.67 on the full set — about 3 SD.
Here the same arm reads 0.625 and 0.707, which is 1.3 SE. Nested *and* representative.

It also retries, with a separate backoff ladder for HTTP 429 and a `--delay` between
requests. One transient 502 lost an entire 280-item draw before that existed.

### Licence

**CC-BY-SA 3.0 and GFDL**, inherited from Wikipedia and stated on the dataset card — an
actual grant of rights, unlike AG News's `unknown`. Nothing is committed regardless: the
slice downloads to whoever runs the fetcher and is gitignored.

---

## Run it

```bash
cd ../../harness
PY=../examples/classification-dbpedia-14/.venv/bin/python
CFG=../examples/classification-dbpedia-14/configs

$PY scripts/experiment_run.py --config $CFG/arm_qwen_m_n200.yaml --dry-run
$PY scripts/classification_report.py --dataset-id dbpedia_280
$PY scripts/family_test.py --dataset-id dbpedia_280 --a db_qwen_m_n200_v1 \
     --against _n200_v1 --metric correct
```

The full 27-arm sweep is **$1.17 as billed**, dominated by the two most expensive arms —
which the result says you do not need.

---

## What this example shows that AG News could not

**A 133× price difference buys nothing measurable.** `qwen_m` leads at 0.9929 for
**$0.0143 billed**; `anthropic_l` is one item behind at 0.9893 for **$0.3784**. Holm over a family of 26
declared in advance: the leader is ahead of 26 of 26 and **separated from only 8**. The
top ten arms are one group.

**Label noise is the same size as the signal.** Three items are disputed by the entire
field — a canal labelled `NaturalPlace`, a "historic school" labelled `Building` rather
than `EducationalInstitution`. The top ten arms are separated by four items in total. Any
ranking within that group is a ranking of which model best reproduces DBpedia's ontology
quirks, not of which classifies better.

**Fourteen CamelCase labels make the parser load-bearing.** On AG News one arm of 24 ever
needed `_parse_label`; here it is worth 8.6 points to `glm_l`, 4.3 to `gemma_s`. And the
first unparseable answers in either example appear here — including one empty response.

**The fine-tuned ML arm needs torch ≥ 2.6, so it does not run on x86_64 macOS.** Every
credible DBpedia-14 fine-tune on the Hub ships `pytorch_model.bin` without safetensors;
they predate safetensors becoming default, and `transformers` refuses a pickle below torch
2.6. On Linux or Apple Silicon `uv sync --extra local` resolves torch 2.14 and it runs
unmodified. Measured 2026-09-30: **0.9857 at $0, 87 ms/item on CPU — statistically tied
with the $0.0143 leader (p = 0.62), not above it.** AG News's "fine-tune beats paying" does
not carry over to a saturated task; "fine-tune costs nothing" does.

---

## Results

See [`../../research/HANDOVER_CLASSIFICATION_DBPEDIA.md`](../../research/HANDOVER_CLASSIFICATION_DBPEDIA.md).
