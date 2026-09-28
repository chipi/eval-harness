# eval-harness

A drop-in evaluation harness. Freeze a dataset, run your system against it, and get an
answer to the question most leaderboards skip: **is this ordering real, or did I just
draw a lucky sample?**

It is deliberately small. The harness imports nothing domain-specific; everything about
your system lives in one file — `adapter.py`, with four functions.

```bash
cd harness
make install
make demo          # the whole loop on bundled synthetic data — no API key, no network
```

## What it is for

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

`make help` lists every verb. Start with `harness/docs/INTEGRATION.md`, then
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
research/    reports, handovers, and an append-only journal of how each example went
```

## The worked examples

Four tasks, three metric shapes, one harness. Each ships a download recipe rather than a
corpus, and each exists because it breaks something the previous one did not.

| Example | Task | Shape of the answer | Report |
|---|---|---|---|
| `summarization-cnn-dailymail` | summarise a news article | one text, scored continuously | [`REPORT.md`](research/REPORT.md) |
| `classification-ag-news` | 4-way topic label | one label, scored 0 or 1 | [`REPORT_CLASSIFICATION.md`](research/REPORT_CLASSIFICATION.md) |
| `classification-dbpedia-14` | 14-way ontology label | same, but saturated | same report |
| `ner-few-nerd` | named entities + types | **a set**, matched one-to-one | [`REPORT_NER.md`](research/REPORT_NER.md) |

They exist to show the harness doing something real, and because the results make the point
better than documentation can:

- **Summarisation.** The dearest arm, at **66× the price** of the cheapest, ranks **15th of
  24**. Two *independent* 100-article evals of the same models agree at only **ρ = 0.753**
  — at 20 articles, **ρ = 0.346**.
- **Classification.** A 44MB fine-tuned model beat 24 frontier LLMs on AG News. On DBpedia
  a **126× price difference** bought nothing measurable, and the top ten arms are separated
  by four items — three of which the entire field disputes because the gold label is wrong.
- **Extraction.** A 476MB span tagger separated from **all 26** opponents — but **57%** of
  its margin is one entity type whose meaning exists only inside that corpus, and **38%**
  of its lead over the best LLM is agreeing with annotation the rest of the field rejects.

`research/NOTES.md` is the append-only journal, corrections included — findings have been
retracted along the way, several caused by bugs in this harness's own scorer. The
retraction rate is itself a result: it measures how much of a first-pass eval is instrument
rather than signal.

No corpus is committed. Examples ship a download recipe.
