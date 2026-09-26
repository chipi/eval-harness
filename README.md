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
research/    findings from the summarisation example — a report and an append-only journal
```

## The worked example

`examples/summarization-cnn-dailymail` runs **24 hosted LLMs over 200 news articles**
against human-written references. It exists to show the harness doing something real, and
because its results make the point better than documentation can:

- the dearest arm, at **66× the price** of the cheapest, ranks **15th of 24**
- **34 of 276** arm pairs are distinguishable — and none of them are inside the top six
- two *independent* 100-article evals of the same models agree at only **ρ = 0.753**, and
  at 20 articles at **ρ = 0.346**

`research/REPORT.md` has the numbers. `research/NOTES.md` is the append-only journal of how
it went, corrections included — nine findings were retracted along the way, two of them
caused by bugs in this harness's own scorer. The retraction rate is itself a result: it
measures how much of a first-pass eval is instrument rather than signal.

No corpus is committed. Examples ship a download recipe.
