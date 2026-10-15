# eval-harness

[![verify](https://github.com/chipi/eval-harness/actions/workflows/reproduce.yml/badge.svg?branch=main)](https://github.com/chipi/eval-harness/actions/workflows/reproduce.yml)
[![site](https://github.com/chipi/eval-harness/actions/workflows/pages.yml/badge.svg?branch=main)](https://chipi.github.io/eval-harness/)
[![docs](https://img.shields.io/badge/docs-chipi.github.io-c8ff3d)](https://chipi.github.io/eval-harness/docs/)
[![python](https://img.shields.io/badge/python-3.11%2B-3776ab)](harness/README.md)
[![demo](https://img.shields.io/badge/demo-no%20API%20key-2ea44f)](#try-it-in-a-minute)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**A drop-in harness for evaluating AI systems on your own data, built to ask the question
most leaderboards skip: is this ranking real, or a lucky sample?**

Freeze a dataset, run your system against it, and get an answer that says whether one
system is actually better than another, or only ahead on this sample. To show it doing
something real, it measured 24 LLMs, small fine-tuned models and baselines on five public
benchmarks. The most expensive model never won, and four of five leaderboard tops were
statistical ties.

### Why it exists

It was built to answer four questions anyone building with AI ends up asking:

1. **Agentic AI can do months of work in days. How do I trust what it builds?** Frozen
   data, a fingerprint on every run and refusals when a comparison is unsound let an
   agent iterate at full speed without a regression passing as progress. This project
   was built that way, with AI agents, and a checker re-verifies the reports' claims
   against the runs on every commit.
2. **Which model is best for what *I* need, not for someone else's benchmark?** Run five,
   ten or twenty-four models on your own frozen data and see quality, cost and latency
   side by side, with a test that says whether the ranking is real.
3. **Do I need an LLM, or a GPU, at all?** Put a small classic model or a plain baseline
   in the same comparison, on the same data and scoring. Here a free model that needs no
   GPU was first or tied for first in all five experiments, but only on text like the
   text it was trained on.
4. **Own it or rent it?** Every cost is read off the provider's bill and set beside
   quality. Here a proprietary model never separated from the best open-weight one, and
   64 GB of memory matched the unlimited-hardware answer on four of five tasks.

**Start where you are:**

| you want to | go to |
|---|---|
| **see what it is** | **[chipi.github.io/eval-harness](https://chipi.github.io/eval-harness/)**: the harness, what it does, and what it found |
| **measure your own system** | [**Use the harness**](docs/GUIDE.md): your first evaluation end to end in twenty minutes, offline. Freeze a dataset, build a golden reference set, measure, compare, promote. Or [**Use it on your problem**](https://chipi.github.io/eval-harness/use.html), the patterns and a walkthrough |
| **learn the method** | [**The method**](https://chipi.github.io/eval-harness/method.html): six habits for measuring AI systems, as these experiments taught them |
| **read what it found** | [**The experiments**](https://chipi.github.io/eval-harness/experiments.html): 24 LLMs, fine-tunes and baselines on five benchmarks, generated from the runs in this repository, so every number on it is checked |
| **check it yourself** | [**Reproduce it**](docs/REPRODUCE.md): five levels, from recomputing every number ($0, one command) to rerunning every model with one OpenRouter key |
| **read the full documentation** | [chipi.github.io/eval-harness/docs](https://chipi.github.io/eval-harness/docs/): guide, concepts, runbook, integration, protocol, reference |
| **review or contribute** | [KNOWN_ISSUES](research/internal/KNOWN_ISSUES.md) (what is open), [CONTRIBUTING](CONTRIBUTING.md) |

## What it is

Most eval code answers "which scored highest". That is the easy half. The hard half is
whether the answer survives being asked again, and this harness is built around that. It
is deliberately small: it imports nothing domain-specific, and everything about your
system lives in one file, `adapter.py`, with four functions.

- **A frozen dataset.** Items are hashed; a run records `items_sha256`. Change the data
  and you get a different id, not a silently different number.
- **A fingerprint per run.** The resolved upstream model id (not your gateway's alias),
  the prompt's sha256, the adapter's sha256, library versions, whether the tree was dirty.
  So "we varied one thing" is *checkable* rather than asserted.
- **A leaderboard that argues with itself.** Before printing an ordering it runs a
  Friedman permutation test and a Nemenyi critical difference over every pair at once, and
  says plainly when nothing is distinguishable.
- **Re-scoring for $0.** `make rescore` recomputes metrics from stored outputs. Checking a
  metric should not cost another sweep; when it did, a broken metric survived two.

And it **refuses** to mislead: it won't compare runs measured on different data, it won't
promote a baseline from a dirty or unknown build, and it records whether a reference is
gold (checked by a person) or silver (written by a model). The refusals are the product.

## Try it in a minute

```bash
git clone https://github.com/chipi/eval-harness && cd eval-harness/harness
make install
make demo          # the whole loop on bundled synthetic data: no API key, no network
make leaderboard   # the ranking, and whether it is real
```

## The loop, on your system

```bash
make dataset-create  DATASET_ID=my_v1 ARGS='--source-dir data/sources/my_v1'
make dataset-materialize DATASET_ID=my_v1
# edit scripts/adapter.py -> call_system() talks to YOUR system
make experiment-dry-run CONFIG=data/configs/arm_a.yaml    # costs nothing, shapes the run
make experiment-run     CONFIG=data/configs/arm_a.yaml
make leaderboard DATASET_ID=my_v1
```

`make help` lists every verb. Start with [`docs/GUIDE.md`](docs/GUIDE.md) (a worked example,
offline), then [`harness/docs/INTEGRATION.md`](harness/docs/INTEGRATION.md) to drop it into
your project and [`harness/docs/RUNBOOK.md`](harness/docs/RUNBOOK.md) for every step.

### Asking better questions of your results

| command | answers |
| --- | --- |
| `make leaderboard DATASET_ID=my_v1` | rank arms on quality, cost and speed, and whether the order is real |
| `make pair-test DATASET_ID=my_v1 A=… B=…` | one comparison you named in advance, without paying the multiplicity price for 275 you didn't |
| `make holdout DATASET_ID=my_v1 EXCLUDE=…` | the same test minus items a smaller dataset already contained |
| `make rank-stability DATASET_ID=my_v1` | how many items before the ordering stops moving: measured, not assumed |
| `make silver-calibrate DATASET_ID=my_v1` | is a model-authored reference usable? Read it against the ceiling it prints |
| `make rescore DATASET_ID=my_v1` | recompute scores from stored outputs, no API calls |

Each needs `DATASET_ID`; without it the Makefile falls back to the demo dataset, `smoke_v1`.

## Pointed at 24 LLMs: the experiments

Five tasks, four metric shapes, one harness. Each experiment exists because it breaks
something the previous one did not, and each ships a download recipe rather than a corpus.
On the site: **[the experiments](https://chipi.github.io/eval-harness/experiments.html)**;
what all five agree on: **[`research/REPORT_SYNTHESIS.md`](research/REPORT_SYNTHESIS.md)**.

| Example | Task | Shape of the answer | Report |
|---|---|---|---|
| `summarization-cnn-dailymail` | summarise a news article | one text, scored continuously | [`REPORT_SUMMARIZATION.md`](research/REPORT_SUMMARIZATION.md) |
| `classification-ag-news` | 4-way topic label | one label, scored 0 or 1 | [`REPORT_CLASSIFICATION.md`](research/REPORT_CLASSIFICATION.md) |
| `classification-dbpedia-14` | 14-way ontology label | same, but saturated | same report |
| `ner-few-nerd` | named entities + types | **a set**, matched one-to-one | [`REPORT_NER.md`](research/REPORT_NER.md) |
| `retrieval-scifact` | find the abstract supporting a claim | **a ranked list** over a 5,183-doc corpus | [`REPORT_RETRIEVAL.md`](research/REPORT_RETRIEVAL.md) |

What they found, and what a plain leaderboard would have hidden:

- **Summarisation.** The dearest arm, at **52× the price** of the cheapest, ranks **18th of
  29**. Two *independent* 100-article evals of the same models agree at only **ρ = 0.79**;
  at 20 articles, **ρ = 0.44**. BART fine-tuned on this corpus ties the best LLM for $0;
  the same BART fine-tuned on XSum finishes **last**, below copying the first three
  sentences. *Scope: the 200 articles are all CNN's.* Re-run on 200 DailyMail articles,
  the local models keep every verdict; the paid ones were not re-run
  ([§3.7](research/REPORT_SUMMARIZATION.md#37-does-it-hold-outside-cnn-the-dailymail-slice)).
- **Classification.** Three small fine-tuned models took the top three places on AG News
  from 24 frontier LLMs, and their lead turns out to live almost entirely in 17 items
  whose gold labels nearly the whole LLM field disputes (8 a labelling convention, 7
  mislabels, 2 ambiguous). On DBpedia a **115× price difference** bought nothing
  measurable, and the fine-tuned model bought a tie, not a win: the top eleven arms are
  separated by four items, three of which the field disputes because the gold label is
  wrong.
- **Extraction.** A 499 MB span tagger separated from **all 27** opponents, but **57%** of
  its margin is one entity type whose meaning exists only inside that corpus, and **38%**
  of its lead over the best LLM is agreeing with annotation the rest of the field rejects.
- **Retrieval.** Twelve LLM rerankers tie with each other *and with two free local
  encoders*. A prediction registered before the arm existed (that swapping only the
  first stage would move the pipeline from 0.74 to 0.786–0.797) came back at **0.7891**.

Every experiment has an answer you can run on your own 64 GB machine for $0. Full index,
with what each one broke in the harness: **[`examples/README.md`](examples/README.md)**.

### Check it yourself, in four commands

```bash
git clone https://github.com/chipi/eval-harness && cd eval-harness
make verify                                  # every number in every report, from the committed runs ($0)
make plan EXP=scifact LEVEL=local            # what a rerun involves, before anything is spent
make data EXP=scifact && make reproduce EXP=scifact LEVEL=local && make compare EXP=scifact
```

`make compare` writes a replication card: each rerun arm against its committed run, and
every committed separation and tie re-tested with your reruns in place. `make list` shows
all six measurements and what each billed; `LEVEL=hosted` reruns the LLMs with one
`OPENROUTER_API_KEY` in `harness/.env`. The full walkthrough, including what a rerun
cannot reproduce and how to add a model of your own: **[docs/REPRODUCE.md](docs/REPRODUCE.md)**.

What each experiment measured, on which data, against which published baseline:
**[`docs/PROTOCOL.md`](docs/PROTOCOL.md)**. Every metric, model, dataset and statistical test
explained and linked to source: **[`docs/REFERENCE.md`](docs/REFERENCE.md)**.

## Influences

The approach builds on **Chip Huyen's books**, *AI Engineering* (O'Reilly, 2025) and
*Designing Machine Learning Systems* (O'Reilly, 2022): evaluation as engineering work on
your own data, a private leaderboard rather than a public one, the dataset as a design
decision, every experiment tracked and versioned. This repository adds a tool that
enforces that framing and five experiments that test it. Idea by idea, with chapters, and
the statistics it also stands on: [docs/INFLUENCES.md](docs/INFLUENCES.md).

## Layout

```
harness/     the harness. Liftable into another project as-is (harness/README.md).
examples/    the five experiments, each with its own uv environment
research/    the experiment reports and the synthesis; research/internal/ is the lab
             notebook: handovers, review rounds and an append-only journal
site/        the public site, generated from the runs (make site; checked by make ci)
docs/        the guide, REPRODUCE, PROTOCOL, REFERENCE, evidence/: published as the
             documentation site by mkdocs.yml
Makefile     verify / plan / data / reproduce / compare: the way in for a rerun
```

`research/internal/NOTES.md` is the append-only journal, corrections included. Findings
have been retracted along the way, several caused by bugs in this harness's own scorer.
The retraction rate is itself a result: it measures how much of a first-pass eval is
instrument rather than signal.

No corpus is committed. Examples ship a download recipe.
