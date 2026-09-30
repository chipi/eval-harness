# `runs-linux/`: every local arm re-timed on one machine

On 2026-09-30 all nine local arms of three experiments were re-run on one idle machine,
one at a time. The point was one latency axis. **They are not the record** (`data/runs/`
is), and they live here for the same reason as `runs-repeats/`: two runs sharing a
`config_id` in one directory are refused by `runs_by_arm()`.

## Why this was needed

The published latency column mixes two machines:

- **Intel Mac** (12 cores, Darwin): `bart_l`, `lead3`, `bert_mini` and every hosted arm.
- **Linux container** (4 cores): the six arms whose pickle checkpoints need torch ≥ 2.6,
  namely `bart_m`, `bart_s`, `bart_l_xsum`, AG's two `bert_base` models and DBpedia's
  `bert_base_fy`.

A Mac-versus-Linux ratio measures the machines as much as the models. On top of that,
the recorded `bart_s` mean (4,484 ms) was slowed by analysis work I ran on the same CPU
while it generated. Its median, 3,683 ms, is close to the idle figure below.

## How they were run

- Code identical to each recorded run: `4068ea23` for AG/DBpedia, `798c6305` for
  CNN/DailyMail. `build.dirty` is false on all nine.
- `EVAL_RUNS_DIR` was pointed outside the git tree, so earlier run directories could not
  mark the tree dirty.
- Load average ≈ 4 at the start of each run; nothing else was running on the machine.
- `run.json` and `outputs/_rows.jsonl` (resume state) are not kept.

## Latency: one machine (Linux, 4 cores), per item

The median is the primary figure. The first one to three items of a local run pay a
one-off initialisation cost that the warm-up does not absorb: the warm-up loads the model
but runs no forward pass. That cost reached **23–24 s on one item** in the two
`bert_base_fy` runs, so their means (202 ms and 166 ms) describe that item, not the model.
See `KNOWN_ISSUES.md`.

| arm | median | 5%-trimmed mean | recorded run (host, mean) |
|---|---|---|---|
| `cnn_bart_l` | **6,257 ms** | 6,459 ms | 11,010 ms (Mac) |
| `cnn_bart_m` | **4,108 ms** | 4,317 ms | 5,062 ms (Linux) |
| `cnn_bart_l_xsum` | **3,934 ms** | 4,197 ms | 4,621 ms (Linux) |
| `cnn_bart_s` | **3,387 ms** | 3,408 ms | 4,484 ms (Linux, contaminated) |
| `cnn_lead3` | 0.1 ms | 0.1 ms | 0.1 ms (Mac) |
| `ag_bert_base_fy` | **55 ms** | 62 ms | 90 ms (Linux) |
| `ag_bert_base_ta` | **49 ms** | 54 ms | 76 ms (Linux) |
| `ag_bert_mini` | **4.3 ms** | 4.5 ms | 7.1 ms (Mac) |
| `db_bert_base_fy` | **61 ms** | 65 ms | 87 ms (Linux) |

On one machine:

- `bart_m` takes **0.66×** `bart_l`'s median time (1.5× faster) and `bart_s` **0.54×**
  (1.8× faster). Distillation saves a third to a half of the time, not "half" across the
  board.
- On AG News `bert_mini` is **11–13×** faster than the two `bert_base` fine-tunes.
- The Linux container ran `bart_l` **1.7× faster** than the Mac did (6.3 s against
  10.7 s median). A local arm timed on one machine and a hosted arm timed from another
  cannot be compared to better than that factor.

## Determinism: what was measured

- **Same machine, same code, six arms** (`bart_m`, `bart_s`, `bart_l_xsum`, both AG
  `bert_base` models, DBpedia `bert_base_fy`): every scored field and every output file
  is **byte-identical** to the recorded run. That is 200 of 200 items each, and 280 of 280
  for DBpedia.
- **Across machines** (Mac → Linux, three arms):
  - `bart_l` and `lead3`: **200 of 200 outputs byte-identical**.
  - `bert_mini`: all 200 labels identical. The softmax `confidence` differs in 37 of 200
    items by at most 1.8 × 10⁻⁶ (float32 rounding), and every aggregate is unchanged.

This covers the nine local arms of these three experiments, on two CPUs. It says nothing
about GPUs, other torch builds, or the local arms of NER and retrieval, which were not
re-run. Hosted arms at temperature 0 do not repeat like this: 47 of 480 article outputs
(9.8%) were byte-identical across three repeats in the earlier CNN/DailyMail sweep, and
13–78 of 200 across two runs of five SciFact arms (`REPORT_RETRIEVAL.md`, *Between-run
variance*).

To re-derive the tables, compare each run here with the run of the same `config_id` in
`data/runs/`: `latency_ms` from `predictions.jsonl`, and `outputs/*.txt` byte for byte.
