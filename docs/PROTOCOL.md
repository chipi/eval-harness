# Evaluation protocol

What each experiment measured, on which data, with which metric — and how that relates to
the protocol the field uses for the same benchmark. Everything a reader needs to decide
what a number in this repo speaks for, in one place.

**The short version.** Five of the six experiments score a **declared sample** of a public
benchmark's test split (200–280 items), not the full test set; the sixth, SummEval, scores
the whole of its benchmark, which is 100 annotated articles. That is enough for the
question this repo asks — *which models can be told apart, at what cost* — and the reports
test separations rather than read rank order. It is not enough to produce a leaderboard
number comparable to a paper's. So each experiment also carries a **calibration row**: one
known model or baseline, run by this repo's own code on the benchmark's full test set (or a
large seeded sample of it), against the value its authors published. The calibration rows
are the evidence that the instrument measures what the field measures. They are how the
one sampling defect found so far was found.

## At a glance

**What was sampled.**

| Experiment | benchmark · test split (official size) | our sample |
|---|---|---|
| Summarisation · CNN/DM | `abisee/cnn_dailymail` · test (11,490) | 200 = **first 200 rows, all CNN**; plus a seeded DailyMail slice of 200 |
| Classification · AG News | `fancyzhx/ag_news` · test (7,600) | 200 = first 50 per class from the first 1,600 rows |
| Classification · DBpedia | `fancyzhx/dbpedia_14` · test (70,000) | 280 = 20 per class, seeded (20260927) |
| Extraction · Few-NERD | `DFKI-SLT/few-nerd` supervised · test (37,648 sentences) | 280 sentences, seeded (20260928), ≥3 tokens |
| Retrieval · SciFact | `BeIR/scifact` · test (300 queries, full 5,183-doc corpus) | 200 queries, seeded (20260928), **full corpus** |
| Judging · SummEval | `mteb/summeval` · test (100 annotated articles, 16 summaries each) | **all 100** |

**How it was scored, and whether the scorer agrees with the field.**

| Experiment | our primary metric | field-standard metric | calibration in the field-standard metric: our run vs published |
|---|---|---|---|
| Summarisation · CNN/DM | `coverage` — ours | ROUGE-1/2/L F1 | LEAD-3, full test: R1 **39.94** / R2 **17.37** vs 40.34 / 17.70 |
| Classification · AG News | accuracy | accuracy | full test, three fine-tunes vs their model cards: `bert_mini` **0.9338** vs 0.9339 · `bert_base_ta` **0.9514** vs 0.9514 · `bert_base_fy` **0.9375** vs 0.9375 |
| Classification · DBpedia | accuracy | accuracy | `bert_base_fy`, seeded 5,600 of 70,000: **0.9879** ±0.003 vs 0.9903 (card) |
| Extraction · Few-NERD | mean per-sentence F1, 8 coarse types, string match — ours | entity micro-F1, 66 fine types, token spans | `span_marker`, seeded 2,000 sentences: **0.7047** ±0.016 vs 0.7040 (card) |
| Retrieval · SciFact | nDCG@10 | nDCG@10 | BM25, all 300 queries: **0.6523** ±0.045 vs 0.665 (BEIR) |
| Judging · SummEval | Kendall τ-b per article against the expert means | Kendall τ-b | the ROUGE arms and UniEval, all 100 articles, vs G-Eval: ROUGE-1 **0.1487** ±0.032 vs 0.150 · ROUGE-2 **0.1578** ±0.028 vs 0.161 · ROUGE-L **0.1435** ±0.032 vs 0.128 · UniEval, on its own inputs, **0.3717** ±0.022 vs 0.377 |

How to read it: **bold** is this repo's own run; the figure after "vs" is the published
one. **±** is the half-width of a 95% confidence interval on our run. **"— ours"** marks a
metric this repo defines; it is not comparable to any paper's number, which is why each
row is calibrated in the field-standard metric instead.

Calibration results are machine-checked against `docs/evidence/calibration/*.json`, which
each example's `calibrate.py` writes.

SummEval's rows need a note. Its sample is the benchmark, so the "±" there is the spread
over the same 100 articles the paper scored, not sampling error against it: a gap inside it
can still be a difference of protocol. ROUGE-1 and ROUGE-2 agree with the paper within 0.01
on every one of the four dimensions; ROUGE-L agrees on average but is 0.054 above it on
coherence, outside that dimension's interval (±0.042) and inside it only with the 0.02
allowance the rule adds for protocol differences; the paper does not say which ROUGE-L it
ran. UniEval's row is the arm scored on UniEval's own published inputs, the protocol behind
the paper's figure; it agrees on every dimension. On this experiment's own text the same
weights score 0.3476, outside the interval, and the report treats that gap as a finding
about the inputs ([REPORT_SUMMEVAL §3.3](../research/REPORT_SUMMEVAL.md)).

## The hardware

Every run on the site records the machine it ran on (`fingerprint.runner`), and
[`evidence/hardware.json`](evidence/hardware.json) maps those records to machines, each
described from the machine itself:

| machine | what it is | what it measured |
|---|---|---|
| Mac mini (2018) | Intel Core i7-8700B, 6 cores / 12 threads, 32 GB | the first five experiments: their local arms on its CPU, their hosted arms as API calls |
| cloud runner | 4-core Linux (x86_64) containers; the operator's cloud coding sessions | the six local models that need torch 2.6 or later, SummEval's seven free scorers, and the one-machine BART re-timing |
| GMKtec EVO-X3 | AMD Ryzen AI Max+ 395 (Strix Halo), 128 GB unified memory | SummEval's 24 hosted judges, as API calls, and its two UniEval arms on CPU. No open-weight LLM was run on any of these machines for the committed results |
| NVIDIA DGX Spark | NVIDIA GB10, 128 GB unified memory | none of the committed runs; the workhorse for the runs of the operator's other projects, where it serves the local models |
| MacBook Pro | Apple M4 Pro, 48 GB unified memory | none of the committed runs; the laptop the work is driven from, and a workhorse for the operator's other projects |

What it means for a number. **A hosted arm's quality and cost come from the provider**, not
the machine that called it. **A local arm's outputs are expected to repeat on any CPU**, and
that is measured for nine of them, not all: the summarisation and classification local arms
re-ran with identical outputs (three of them on a different machine; `bert_mini`'s
confidences moved by up to 2 × 10⁻⁶, its labels not at all). The NER, retrieval and SummEval
local arms were not re-run. **Latency depends on the machine**, local and hosted alike: a
hosted latency includes the caller's network and gateway (the Mac mini called through a
gateway on itself, the EVO-X3 through one on the Mac mini), and a ratio between arms timed
on two different machines is good to about a factor of two, which the reports say wherever
they compare them.

## What is the same in every experiment

- **Pinned data.** Each dataset is a JSON file under `harness/data/datasets/` listing every
  item with the sha256 of its text. Every run records the hash of the whole item set
  (`fingerprint.data.items_sha256`), so two runs that disagree on it did not see the same
  data. No corpus is committed; each example's `fetch.py` downloads it from the public
  Hugging Face datasets API, stdlib only, and `make dataset-materialize` refuses bytes
  whose hash does not match.
- **A dev slice, nested inside the sample.** Prompts and parsers may be tuned on it and
  on nothing else; every headline is also reported on the held-out remainder. SummEval has
  no dev slice, and so no held-out remainder.
- **One pass per arm, temperature 0, one prompt per task.** Hosted LLMs ran zero-shot with
  reasoning off and no provider pinned, as run here; contamination of the public benchmarks
  was not measured. An *arm* is one system under
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
  sample of the benchmark's CNN portion (9.5% of the split), and every committed summarisation finding is scoped
  to CNN-style news. `cnn_dailymail_dm200` is 200 DailyMail articles drawn at random
  (seed 20261014) to test whether findings travel. It was run for the five local arms, and
  every comparison among them held; the hosted arms were not re-run on it.
- **Dev slice.** `cnn_dailymail_20`, the first 20 (nested).
- **Reference.** The journalists' `highlights` — gold.
- **Our metric.** `coverage`: ROUGE-Lsum recall with the summary clipped to the
  reference's length, so a model cannot buy recall with words. It is ours and not
  comparable to any published number. ROUGE-1 and ROUGE-Lsum F1 are reported beside it.
- **Comparability.** Absolute scores on the committed slice are **not** comparable to the
  literature, mainly because of the slice (the scorer reads LEAD-3 0.40 ROUGE-1 below the
  published figure on the full test set, outside its ±0.22 interval): CNN articles score ~11 ROUGE-1 lower than DailyMail ones.
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
  (REPORT_CLASSIFICATION §3.4); adjudicated by topic by one reader shown the hosted answer, the
  gold was wrong on all 17. The dataset's own gold stays primary.
- **Metric.** Accuracy — the standard one.
- **Comparability.** Comparable in kind to published accuracy; at n=200 a single figure
  carries ±0.03.
- **Reproduce.** `examples/classification-ag-news/README.md`; calibration: `calibrate.py`.

### Classification · DBpedia-14

- **Benchmark.** `fancyzhx/dbpedia_14`, test split: 70,000 (5,000 per class), 14 classes.
- **Sample.** `dbpedia_280`: 20 per class from a seeded per-class permutation (seed
  20260927). Dev slice `dbpedia_56`, nested.
- **Reference.** Dataset labels — gold; three items' gold is disputed by 24–25 of 26 arms
  and analysed apart (REPORT_CLASSIFICATION §3.4); adjudicated by one reader shown the hosted answer, the gold was
  wrong on all three. The dataset's own gold stays primary.
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

### Judging · SummEval

- **Benchmark.** `mteb/summeval` (MIT; the original Yale-LILY/SummEval is MIT): the 100
  CNN/DailyMail test articles that carry expert annotations, 87 DailyMail and 13 CNN, each
  with 16 summaries from 2019-era systems and 11 human reference summaries.
- **Sample.** `summeval_100`: all 100. Nothing is drawn, so nothing is seeded.
- **Reference.** The mean of three expert annotators' 1–5 scores per summary, on
  coherence, consistency, fluency and relevance — gold. The crowd ratings are not used.
- **Metric.** Kendall τ-b per article between a judge's scores and the expert means over
  the 16 summaries, averaged over the four dimensions (`tau`); Spearman (`rho`) beside it.
  This is the summary-level protocol G-Eval reports, and τ-b corrects for the ties integer
  scores produce. Because it is per article, the paired permutation tests apply unchanged.
- **Comparability.** Directly comparable to G-Eval's Table 1 for the same metric, which is
  what the calibration rows use. A judge's prompt, decoding and one-call-per-article design
  are this repo's, so a judge's τ is comparable in kind, not as a reproduction of G-Eval.
- **Reproduce.** `examples/summeval-judging/README.md`; calibration: `calibrate.py`;
  the derived figures in its report: `harness/tools/summeval_analysis.py`.

## What a number here does and does not support

- **Supports:** whether two arms on the same sample can be told apart, at what billed cost
  and latency, with the separation test and its multiple-comparison correction stated.
- **Supports, with the calibration row:** that the instrument scores a known system the
  way the field does.
- **Does not support:** a leaderboard position against published papers — the samples are
  100–280 items, and two of six primary metrics are this repo's own.
