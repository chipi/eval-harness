# Evaluation protocol

What each experiment measured, on which data, with which metric — and how that relates to
the protocol the field uses for the same benchmark. Everything a reader needs to decide
what a number in this repo speaks for, in one place.

**The short version.** Every experiment scores a **declared sample** of a public
benchmark's test split (200–280 items), not the full test set. That is enough for the
question this repo asks — *which models can be told apart, at what cost* — and the reports
test separations rather than read rank order. It is not enough to produce a leaderboard
number comparable to a paper's. So each experiment also carries a **calibration row**: one
known model or baseline, run by this repo's own code on the benchmark's full test set (or a
large seeded sample of it), against the value its authors published. The calibration rows
are the evidence that the instrument measures what the field measures. They are how the
one sampling defect found so far was found.

## At a glance

| experiment | benchmark · split (official size) | our sample | our primary metric | field-standard metric | calibration: ours vs published |
|---|---|---|---|---|---|
| Summarisation · CNN/DM | `abisee/cnn_dailymail` · test (11,490) | 200 = **first 200 rows, all CNN**; plus a seeded DailyMail slice of 200 | `coverage` — ours | ROUGE-1/2/L F1 | LEAD-3, full test: R1 **39.94** / R2 **17.37** vs 40.34 / 17.70 |
| Classification · AG News | `fancyzhx/ag_news` · test (7,600) | 200 = first 50 per class from the first 1,600 rows | accuracy | accuracy | full test, three fine-tunes vs their model cards: `bert_mini` **0.9338** vs 0.9339 · `bert_base_ta` **0.9514** vs 0.9514 · `bert_base_fy` **0.9375** vs 0.9375 |
| Classification · DBpedia | `fancyzhx/dbpedia_14` · test (70,000) | 280 = 20 per class, seeded (20260927) | accuracy | accuracy | `bert_base_fy`, seeded 5,600 of 70,000: **0.9879** ±0.003 vs 0.9903 (card) |
| Extraction · Few-NERD | `DFKI-SLT/few-nerd` supervised · test (37,648 sentences) | 280 sentences, seeded (20260928), ≥3 tokens | mean per-sentence F1, 8 coarse types, string match — ours | entity micro-F1, 66 fine types, token spans | `span_marker`, seeded 2,000 sentences: **0.7047** ±0.016 vs 0.7040 (card) |
| Retrieval · SciFact | `BeIR/scifact` · test (300 queries, full 5,183-doc corpus) | 200 queries, seeded (20260928), **full corpus** | nDCG@10 | nDCG@10 | BM25, all 300 queries: **0.6523** ±0.045 vs 0.665 (BEIR) |

Calibration results are machine-checked against `docs/evidence/calibration/*.json`, which
each example's `calibrate.py` writes.

## What is the same in every experiment

- **Pinned data.** Each dataset is a JSON file under `harness/data/datasets/` listing every
  item with the sha256 of its text. Every run records the hash of the whole item set
  (`fingerprint.data.items_sha256`), so two runs that disagree on it did not see the same
  data. No corpus is committed; each example's `fetch.py` downloads it from the public
  Hugging Face datasets API, stdlib only, and `make dataset-materialize` refuses bytes
  whose hash does not match.
- **A dev slice, nested inside the sample.** Prompts and parsers may be tuned on it and
  on nothing else; every headline is also reported on the held-out remainder.
- **One pass per arm, temperature 0, one prompt per task.** An *arm* is one system under
  test: a model plus its configuration (prompt, decoding, provider). Between-run variance
  of hosted models is not measured except where stated (five SciFact repeat pairs).
- **Comparisons are tested, not read.** Separation between arms is a paired permutation
  test with Holm correction over each family; rank order alone is never a finding.
- **Costs are what the provider billed**, read from each response, not a price table.

## Per experiment

### Summarisation · CNN/DailyMail

- **Benchmark.** `abisee/cnn_dailymail`, config 1.0.0 — the same articles as the 3.0.0
  the literature uses (checked: all 200 identical). Test split: 11,490 articles, **1,093
  CNN and 10,397 DailyMail** (published counts), with CNN's articles first.
- **Sample.** `cnn_dailymail_200` is the **first 200 rows**: all CNN — 196 with CNN's dateline, 4 partner pieces CNN
  republished. It is a
  sample of the benchmark's CNN portion (9% of the split), and every committed summarisation finding is scoped
  to CNN-style news. `cnn_dailymail_dm200` is 200 DailyMail articles drawn at random
  (seed 20261014) to test whether findings travel. It was run for the five local arms, and
  every comparison among them held; the hosted arms were not re-run on it.
- **Dev slice.** `cnn_dailymail_20`, the first 20 (nested).
- **Reference.** The journalists' `highlights` — gold.
- **Our metric.** `coverage`: ROUGE-Lsum recall with the summary clipped to the
  reference's length, so a model cannot buy recall with words. It is ours and not
  comparable to any published number. ROUGE-1 and ROUGE-Lsum F1 are reported beside it.
- **Comparability.** Absolute scores on the committed slice are **not** comparable to the
  literature — not because of the scorer (calibrated within 0.4 ROUGE-1 on the full test
  set) but because of the slice: CNN articles score ~11 ROUGE-1 lower than DailyMail ones.
- **Reproduce.** `examples/summarization-cnn-dailymail/README.md`; calibration:
  `calibrate.py` in the same directory.

### Classification · AG News

- **Benchmark.** `fancyzhx/ag_news`, test split: 7,600 headlines + snippets, 4 balanced classes.
- **Sample.** `ag_news_200`: the first 50 of each class in split order, from the first
  1,600 rows; unseeded but deterministic. Checked for order bias on 2026-10-14 against a
  seeded random class-balanced 200: `bert_mini` 0.9450 vs 0.9400 (±0.033), `keyword` 0.670
  vs 0.605 (±0.065) — within sampling error.
- **Dev slice.** `ag_news_20`, the first 5 per class (nested).
- **Reference.** Dataset labels — gold, and disputed: 17 items are labelled against the
  judgement of ≥80% of the hosted field; they stay in the score and are analysed apart
  (REPORT_CLASSIFICATION §3.4).
- **Metric.** Accuracy — the standard one.
- **Comparability.** Comparable in kind to published accuracy; at n=200 a single figure
  carries ±0.03.
- **Reproduce.** `examples/classification-ag-news/README.md`; calibration: `calibrate.py`.

### Classification · DBpedia-14

- **Benchmark.** `fancyzhx/dbpedia_14`, test split: 70,000 (5,000 per class), 14 classes.
- **Sample.** `dbpedia_280`: 20 per class from a seeded per-class permutation (seed
  20260927). Dev slice `dbpedia_56`, nested.
- **Reference.** Dataset labels — gold; three items' gold is disputed by 24–25 of 26 arms
  and analysed apart (REPORT_CLASSIFICATION §3.4).
- **Metric.** Accuracy — the standard one. The benchmark is saturated: the top group is
  separated from the rest, not ordered within itself.
- **Reproduce.** `examples/classification-dbpedia-14/README.md`; calibration: `calibrate.py`.

### Extraction · Few-NERD

- **Benchmark.** `DFKI-SLT/few-nerd`, `supervised` config, test split: 37,648 sentences,
  8 coarse / 66 fine entity types.
- **Sample.** `few_nerd_280`: seeded random (seed 20260928) over sentences of ≥3 tokens.
  Dev slice `few_nerd_56`, nested.
- **Reference.** Dataset annotation — gold; 34 of 768 gold entities carry a type that
  ≥80% of the learned arms reject, analysed as an annotation bound (REPORT_NER §3.6).
- **Our metric.** The mean over sentences of set F1 on **coarse** types, matched on
  normalised surface strings — chosen so a free-text LLM answer can be scored at all.
  It is ours and not comparable to published Few-NERD figures.
- **Field standard.** Entity-level micro-F1 over the 66 fine types on exact token spans —
  what the calibration row uses.
- **Reproduce.** `examples/ner-few-nerd/README.md`; calibration: `calibrate.py`.

### Retrieval · SciFact

- **Benchmark.** `BeIR/scifact`, test qrels: 300 queries, 339 relevance judgments, over the
  full 5,183-abstract corpus.
- **Sample.** `scifact_200`: 200 of the 300 queries, seeded (seed 20260928), 227
  judgments. **The corpus is never sliced** — every arm searches all 5,183 documents.
  Dev slice `scifact_40`, nested.
- **Metric.** nDCG@10 — the BEIR standard. LLM arms are **rerankers** of BM25's top 20
  (with BM25's next 80 appended), a design choice the report states throughout.
- **Comparability.** BM25 by this code scores 0.6523 on all 300 queries against BEIR's
  0.665; the gap is within sampling error and within what a different BM25 implementation
  (one field, no stemming) explains.
- **Reproduce.** `examples/retrieval-scifact/README.md`; calibration: `calibrate.py`.

## What a number here does and does not support

- **Supports:** whether two arms on the same sample can be told apart, at what billed cost
  and latency, with the separation test and its multiple-comparison correction stated.
- **Supports, with the calibration row:** that the instrument scores a known system the
  way the field does.
- **Does not support:** a leaderboard position against published papers — the samples are
  200–280 items, and two of five primary metrics are this repo's own.
