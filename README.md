# eval-harness

Twenty-four LLMs, small fine-tuned models and baselines, measured on five public
benchmarks by a harness built to ask one question most leaderboards skip: **is this
ordering real, or a lucky sample?** The most expensive model never won; four of five
leaderboard tops are statistical ties; and every instrument is calibrated against the
published literature.

**Start where you are:**

| you want to | go to |
|---|---|
| **read what was found** | **[chipi.github.io/eval-harness](https://chipi.github.io/eval-harness/)** — the findings, for people; generated from the runs in this repository, so every number on it is checked |
| **learn the method** | [**The method**](https://chipi.github.io/eval-harness/method.html) — six habits for measuring AI systems, as these experiments taught them — and [**Use it on your problem**](https://chipi.github.io/eval-harness/use.html) |
| **check it yourself** | [**Reproduce it**](docs/REPRODUCE.md) — five levels, from recomputing every number ($0, one command) to rerunning every model with one OpenRouter key |
| **measure your own system** | [**Use the harness**](docs/GUIDE.md) — your first evaluation end to end in twenty minutes, offline: freeze a dataset, build a golden reference set, measure, compare, promote. [What the harness is](#what-it-is-for), below |
| **read the full documentation** | [chipi.github.io/eval-harness/docs](https://chipi.github.io/eval-harness/docs/) — protocol, reference, concepts, runbook |
| **review or contribute** | [KNOWN_ISSUES](research/internal/KNOWN_ISSUES.md) (what is open), [CONTRIBUTING](CONTRIBUTING.md) |

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

### Or try the harness on its own

```bash
cd harness
make install
make demo          # the whole loop on bundled synthetic data — no API key, no network
```

## Influences

The approach builds on **Chip Huyen's books**, *AI Engineering* (O'Reilly, 2025) and
*Designing Machine Learning Systems* (O'Reilly, 2022): evaluation as engineering work on
your own data, a private leaderboard rather than a public one, the dataset as a design
decision, every experiment tracked and versioned. This repository adds a tool that
enforces that framing and five experiments that test it. Idea by idea, with chapters, and
the statistics it also stands on: [docs/INFLUENCES.md](docs/INFLUENCES.md).

## What it is for

A drop-in evaluation harness. Freeze a dataset, run your system against it, and get an
answer to the question most leaderboards skip. It is deliberately small: the harness
imports nothing domain-specific, and everything about your system lives in one file —
`adapter.py`, with four functions.

Most eval code answers "which scored highest". That is the easy half. The hard half is
whether the answer survives being asked again, and this harness is built around that:

- **A frozen dataset.** Items are hashed; a run records `items_sha256`. Change the data
  and you get a different id, not a silently different number.
- **A fingerprint per run.** The resolved upstream model id (not your gateway's alias),
  the prompt's sha256, the adapter's sha256, library versions, whether the tree was dirty.
  So "we varied one thing" is *checkable* rather than asserted.
- **A leaderboard that argues with itself.** Before printing an ordering it runs a
  Friedman permutation test and a Nemenyi critical difference over every pair at once, and
  says plainly when nothing is distinguishable.
- **Re-scoring for $0.** `make rescore` recomputes metrics from stored outputs. Checking a
  metric should not cost another sweep — when it did, a broken metric survived two.

## The loop

```bash
make dataset-create  DATASET_ID=my_v1 ARGS='--source-dir data/sources/my_v1'
make dataset-materialize DATASET_ID=my_v1
# edit scripts/adapter.py -> call_system() talks to YOUR system
make experiment-dry-run CONFIG=data/configs/arm_a.yaml    # costs nothing, shapes the run
make experiment-run     CONFIG=data/configs/arm_a.yaml
make leaderboard DATASET_ID=my_v1
```

`make help` lists every verb. Start with [`docs/GUIDE.md`](docs/GUIDE.md) (a worked example, offline), then `harness/docs/INTEGRATION.md` and
`harness/docs/RUNBOOK.md`.

## Asking better questions of your results

| | |
| --- | --- |
| `make leaderboard` | rank arms on quality, cost and speed — and whether the order is real |
| `make pair-test A=… B=…` | one comparison you named in advance, without paying the multiplicity price for 275 you didn't |
| `make holdout EXCLUDE=…` | the same test minus items a smaller dataset already contained |
| `make rank-stability` | how many items before the ordering stops moving — measured, not assumed |
| `make silver-calibrate` | is a model-authored reference usable? Read it against the ceiling it prints |
| `make rescore` | recompute scores from stored outputs, no API calls |

## Layout

```
harness/     the harness. Liftable into another project as-is.
examples/    worked examples, each with its own uv environment
research/    the five experiment reports and the synthesis; research/internal/ is the lab
             notebook — handovers, review rounds and an append-only journal
site/        the public site, generated from the runs (make site; checked by make ci)
docs/        PROTOCOL.md (what each experiment measured), REPRODUCE.md, REFERENCE.md,
             evidence/ — published as the documentation site by mkdocs.yml
Makefile     verify / plan / data / reproduce / compare — the way in for a rerun
```

## The worked examples

**[`research/REPORT_SYNTHESIS.md`](research/REPORT_SYNTHESIS.md)** — what all five
experiments agree on, and where that contradicts how leaderboards are usually read:
the dearest arm was never the best, four of five leaderboard tops are ties, and **every
experiment has an answer you can run on your own 64 GB machine for $0**.

Full index, with what each one found and what it broke: **[`examples/README.md`](examples/README.md)**.
Every metric, model, dataset and statistical test explained and linked to source: **[`docs/REFERENCE.md`](docs/REFERENCE.md)**.
What each experiment measured, on which data, against which published baseline: **[`docs/PROTOCOL.md`](docs/PROTOCOL.md)**.
Reviewing? Start with what is open and known: **[`research/internal/KNOWN_ISSUES.md`](research/internal/KNOWN_ISSUES.md)**.

Five tasks, four metric shapes, one harness. Each ships a download recipe rather than a
corpus, and each exists because it breaks something the previous one did not.

| Example | Task | Shape of the answer | Report |
|---|---|---|---|
| `summarization-cnn-dailymail` | summarise a news article | one text, scored continuously | [`REPORT_SUMMARIZATION.md`](research/REPORT_SUMMARIZATION.md) |
| `classification-ag-news` | 4-way topic label | one label, scored 0 or 1 | [`REPORT_CLASSIFICATION.md`](research/REPORT_CLASSIFICATION.md) |
| `classification-dbpedia-14` | 14-way ontology label | same, but saturated | same report |
| `ner-few-nerd` | named entities + types | **a set**, matched one-to-one | [`REPORT_NER.md`](research/REPORT_NER.md) |
| `retrieval-scifact` | find the abstract supporting a claim | **a ranked list** over a 5,183-doc corpus | [`REPORT_RETRIEVAL.md`](research/REPORT_RETRIEVAL.md) |

They exist to show the harness doing something real, and because the results make the point
better than documentation can:

- **Summarisation.** The dearest arm, at **52× the price** of the cheapest, ranks **18th of
  29**. Two *independent* 100-article evals of the same models agree at only **ρ = 0.79**
  — at 20 articles, **ρ = 0.44**. BART fine-tuned on this corpus ties the best LLM for $0;
  the same BART fine-tuned on XSum finishes **last**, below copying the first three
  sentences. *Scope: the 200 articles are all CNN's.* Re-run on 200 DailyMail articles,
  the local models keep every verdict; the paid ones were not re-run
  ([§3.7](research/REPORT_SUMMARIZATION.md#37-does-it-hold-outside-cnn-the-dailymail-slice)).
- **Classification.** Three small fine-tuned models took the top three places on AG News
  from 24 frontier LLMs — and their lead turns out to live almost entirely in 17 items
  whose gold labels nearly the whole LLM field disputes (8 a labelling convention, 7
  mislabels, 2 ambiguous). On DBpedia a **115× price difference**
  bought nothing measurable, and the fine-tuned model bought a tie, not a win: the top
  eleven arms are separated by four items, three of which the field disputes because the
  gold label is wrong.
- **Extraction.** A 499 MB span tagger separated from **all 27** opponents — but **57%** of
  its margin is one entity type whose meaning exists only inside that corpus, and **38%**
  of its lead over the best LLM is agreeing with annotation the rest of the field rejects.
- **Retrieval.** Twelve LLM rerankers tie with each other *and with two free local
  encoders*. A prediction registered before the arm existed — that swapping only the
  first stage would move the pipeline from 0.74 to 0.786–0.797 — came back at **0.7891**.

`research/internal/NOTES.md` is the append-only journal, corrections included — findings have been
retracted along the way, several caused by bugs in this harness's own scorer. The
retraction rate is itself a result: it measures how much of a first-pass eval is instrument
rather than signal.

No corpus is committed. Examples ship a download recipe.
