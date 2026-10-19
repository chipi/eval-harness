<img src="site/assets/icon.svg" alt="" width="64" height="64">

# eval-harness

[![verify](https://github.com/chipi/eval-harness/actions/workflows/reproduce.yml/badge.svg?branch=main)](https://github.com/chipi/eval-harness/actions/workflows/reproduce.yml)
[![site](https://github.com/chipi/eval-harness/actions/workflows/pages.yml/badge.svg?branch=main)](https://evals.humancopilot.eu/)
[![docs](https://img.shields.io/badge/docs-evals.humancopilot.eu-c8ff3d)](https://evals.humancopilot.eu/docs/)
[![python](https://img.shields.io/badge/python-3.11%2B-3776ab)](harness/README.md)
[![demo](https://img.shields.io/badge/demo-no%20API%20key-2ea44f)](#try-it-in-a-minute)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**A drop-in harness for evaluating AI systems on your own data, built to ask the question
most leaderboards skip: is this ranking real, or a lucky sample?**

Freeze a dataset, run your system against it, and get an answer that says whether one
system is actually better than another, or only ahead on this sample.

This is ongoing work. The harness and its method are the point; the six experiments below are
worked examples of them, not a benchmark, and they are still being extended. As those
examples, it measured 24 LLMs, small fine-tuned models and baselines on six public
benchmarks. The most expensive hosted model never won (on SciFact only the twelve cheapest
hosted models ran), and in five of six the leader could not be separated from other arms,
each time including one that cost less than the dearest hosted model, at 100–280 items — not
shown different, which is not the same as equal.

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
   GPU was first, or not separable from first, in five of the six experiments, against LLMs
   run with one prompt and no examples; the clearest wins were on text like the text it was
   trained on. On the sixth, judging summaries, even a free model
   trained for the task lost, and an LLM judge scored above every free scorer measured: the best judges
   reach 93% of a human expert's agreement (the best of 24, chosen on the same 100
   articles; 92% held out; 2019-era summaries, all 16 ranked in one call, reasoning off),
   the best free scorer, UniEval, 64%. A no-model lookup of which system wrote each summary
   reaches 63%, so how much of a score is reading the summary is not measured. Why the
   trained model lost there is not tested; one task, one model.
4. **Own it or rent it?** Every cost is read off the provider's bill and set beside
   quality. Here the best proprietary arm never separated from the best open-weight arm, and
   at native precision the best model that fits a 64 GB machine matched the
   unlimited-hardware answer on two of the six tasks, was not separated from it on two more,
   and was separated below it on summarisation and SummEval (scores as the providers served
   them; nothing was run on a 64 GB machine).

**Start where you are:**

| you want to | go to |
|---|---|
| **see what it is** | **[evals.humancopilot.eu](https://evals.humancopilot.eu/)**: the harness, what it does, and what it found |
| **measure your own system** | [**Use the harness**](docs/GUIDE.md): your first evaluation end to end in twenty minutes, offline. Freeze a dataset, build a golden reference set, measure, compare, promote. Or [**Use it on your problem**](https://evals.humancopilot.eu/use.html), the patterns and a walkthrough |
| **learn the method** | [**The method**](https://evals.humancopilot.eu/method.html): six habits for measuring AI systems, as these experiments taught them |
| **read what it found** | [**The experiments**](https://evals.humancopilot.eu/experiments.html): 24 LLMs, fine-tunes and baselines on six benchmarks, generated from the runs in this repository, so every number on it is checked |
| **check it yourself** | [**Reproduce it**](docs/REPRODUCE.md): five levels, from recomputing every number ($0, one command) to rerunning every model with one OpenRouter key |
| **read the full documentation** | [evals.humancopilot.eu/docs](https://evals.humancopilot.eu/docs/): guide, concepts, runbook, integration, protocol, reference |
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

You need `git`, `make` and Python ≥ 3.11.

```bash
git clone https://github.com/chipi/eval-harness && cd eval-harness/harness
make install       # creates harness/.venv; the make targets use it from then on
make demo          # the whole loop on bundled synthetic data: no API key, no network
make leaderboard   # the ranking, and whether it is real
```

### Setup, in full

There are three separate environments. Install only the ones you need.

| for | install once | then |
| --- | --- | --- |
| **the harness**: the demo, your own evals, `make verify` | `make -C harness install` | `make verify` from the repository root |
| **the six worked examples** | [uv](https://docs.astral.sh/uv/). Each example gets its own uv environment, so its pinned libraries cannot disturb another's | `make data EXP=<name>` runs `uv sync` and fetches the data ([docs/REPRODUCE.md](docs/REPRODUCE.md)) |
| **the documentation site** | `harness/.venv/bin/pip install -r site/requirements-docs.txt` (MkDocs + Material, into the harness venv) | `source harness/.venv/bin/activate && make docs` writes `build/docs-site/` |

`make docs` is the exception: it calls `mkdocs` from your `PATH`, which is why the venv
has to be activated first.

The demo, `make verify` and the local arms need no API key. To run hosted LLM arms, copy
`harness/.env.example` to `harness/.env`, set `OPENROUTER_API_KEY` (or the LiteLLM or
direct-provider keys listed there), and set `EVAL_MAX_COST_USD` to cap the spend. Then
check with `make -C harness env-check`.

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

Six tasks, five metric shapes, one harness. Each experiment exists because it breaks
something the previous one did not, and each ships a download recipe rather than a corpus.
On the site: **[the experiments](https://evals.humancopilot.eu/experiments.html)**;
what all six agree on: **[`research/REPORT_SYNTHESIS.md`](research/REPORT_SYNTHESIS.md)**.

| Example | Task | Shape of the answer | Report |
|---|---|---|---|
| `summarization-cnn-dailymail` | summarise a news article | one text, scored continuously | [`REPORT_SUMMARIZATION.md`](research/REPORT_SUMMARIZATION.md) |
| `classification-ag-news` | 4-way topic label | one label, scored 0 or 1 | [`REPORT_CLASSIFICATION.md`](research/REPORT_CLASSIFICATION.md) |
| `classification-dbpedia-14` | 14-way ontology label | same, but saturated | same report |
| `ner-few-nerd` | named entities + types | **a set**, matched one-to-one | [`REPORT_NER.md`](research/REPORT_NER.md) |
| `retrieval-scifact` | find the abstract supporting a claim | **a ranked list** over a 5,183-doc corpus | [`REPORT_RETRIEVAL.md`](research/REPORT_RETRIEVAL.md) |
| `summeval-judging` | grade summaries the way experts do | **a vector of judgements**, scored by rank correlation | [`REPORT_SUMMEVAL.md`](research/REPORT_SUMMEVAL.md) |

What they found, and what a plain leaderboard would have hidden. Each report opens with its
pick, as run here:

- **Summarisation:** `bart_l` if you can run a free 1.6 GB model on CPU and your text looks
  like CNN news; `deepseek_m` ($191 per 1M articles) if you need speed; not `anthropic_l`.
- **AG News:** fine-tune, starting with `bert_mini`; if you must rent, `gemma_m` ($8 per 1M).
- **DBpedia-14:** the cheapest arm you can run at 0.9857: `gemma_m` (~$12), `qwen_s` (~$26)
  or the fine-tuned `bert_base_fy`.
- **Few-NERD:** with labelled data, fine-tune `span_marker`; if you rent, `gemma_m`.
- **SciFact:** `e5_base` first (0.7191, $0); add an LLM reranker on its top 20 only if about
  +0.07 nDCG@10 is worth about $732 per 1M queries.
- **SummEval:** an LLM judge, starting with `gemma_l`; check it against a small set of your
  own human judgements first.

- **Summarisation.** The dearest arm, at **143× the price** of the cheapest, ranks **18th of
  29**. Two *independent* 100-article evals of the same models agree at only **ρ = 0.79**;
  at 20 articles, **ρ = 0.44**. BART fine-tuned on this corpus is not separated from the
  best LLM (0.0001 apart), for $0; the same BART fine-tuned on XSum finishes **last** on
  `coverage`, below copying the first three sentences (it also decodes shorter). *Scope: the 200 articles are all CNN's.* Re-run on 200 DailyMail articles,
  the local models keep every verdict; the paid ones were not re-run
  ([§3.7](research/REPORT_SUMMARIZATION.md#37-does-it-hold-outside-cnn-the-dailymail-slice)).
- **Classification.** Three small fine-tuned models lead the 24 hosted LLMs on AG News on
  the point estimate, LLMs as run here; only the first is separated from all but one paid
  arm. The lead is concentrated in 17 items the hosted field mostly gets wrong — about half
  a learnable convention, half mislabels, on one rater's reading. On DBpedia a **115× price
  difference** was not shown to buy accuracy (no gap under 10 items is detectable at n = 280), and the fine-tuned model is not separated from
  the top group: the top eleven arms are within four items, three of them items whose
  label the field disputes, unadjudicated.
- **Extraction.** A 499 MB span tagger separated from **all 27** opponents, but **57%** of
  its margin over the best LLM is one entity type whose meaning exists only inside that
  corpus, and **up to 38%** of that lead is agreeing with annotation the rest of the field
  rejects: an upper bound, one reader's judgement. The two overlap and cannot be added.
- **Retrieval.** The leading LLM reranker cannot be separated from eleven or twelve other arms (a Holm boundary),
  ten rerankers *and two free local encoders*. A prediction registered before the arm existed (that swapping only the
  first stage would move the pipeline from 0.74 to 0.786–0.797) came back at **0.7891** for
  one of the two rerankers tested; the other landed outside the range.
- **Judging.** Asked to grade summaries the way three experts did, 23 of the 24 LLMs are
  separated from, and ahead of, the best free scorer measured — UniEval, an evaluator
  trained for exactly this — and all 24 from BARTScore and ROUGE. That is against free
  scorers that were measured: the judges rank all 16 summaries in one call while UniEval
  scores one at a time, and a pointwise LLM judge was not run. Scored against two experts, as one expert is against the
  other two, the best judges reach 93% of a human's agreement (the best of 24, on the same
  articles; 92% held out) and UniEval 64%, on 2019-era summaries with reasoning off. A
  no-model lookup of which system wrote each summary reaches 63%, so how much of a judge's
  score is reading the summary is not measured. The leader
  cannot be separated from five other judges, and an open-weight one sits 0.0013 behind it for $0.0278 per 100
  articles. ROUGE agrees with the experts at τ 0.14–0.16, and
  this repository's own summarisation metric below that.

Every experiment has a $0 answer you can run on hardware you own — on SummEval a 63 GB
open-weight judge, which a 64 GB machine holds only at int8, a precision that was not
measured. Full index,
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
all seven measurements and what each billed; `LEVEL=hosted` reruns the LLMs with one
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
enforces that framing and six experiments that test it. Idea by idea, with chapters, and
the statistics it also stands on: [docs/INFLUENCES.md](docs/INFLUENCES.md).

## Layout

```
harness/     the harness. Liftable into another project as-is (harness/README.md).
examples/    the six experiments, each with its own uv environment
research/    the experiment reports and the synthesis; research/internal/ is the lab
             notebook: handovers, review rounds and an append-only journal
site/        the public site, generated from the runs (make site; checked by make ci)
docs/        the guide, REPRODUCE, PROTOCOL, REFERENCE, evidence/: published as the
             documentation site by mkdocs.yml
Makefile     verify / plan / data / reproduce / compare: the way in for a rerun
```

## Who built this

**Marko Dragoljevic**: twenty years leading engineering teams (ServiceNow, EclecticIQ,
Backbase), now advising technology leaders through
**[Human Copilot](https://www.humancopilot.eu/?utm_source=eval-harness&utm_medium=github&utm_campaign=launch&utm_content=readme)**.
Which model, build or buy, own or rent: the questions this harness answers are the ones
he helps teams answer on their own data. Principles for engineers who build end to end:
**[DevWhateverOps](https://devwhateverops.com/?utm_source=eval-harness&utm_medium=github&utm_campaign=launch&utm_content=readme)**.

`research/internal/NOTES.md` is the append-only journal, corrections included. Findings
have been retracted along the way, several caused by bugs in this harness's own scorer.
The retraction rate is itself a result: it measures how much of a first-pass eval is
instrument rather than signal.

No corpus is committed; examples ship a download recipe. What *is* committed, each dataset's licence, and what it asks of you: **[docs/DATA.md](docs/DATA.md)**.
