# runs/ — every run, and each score of it

One directory per run, the pass of one system over one dataset. A run's scores sit under it.

```
runs/<run_id>/run.json                        the pass: system (config_id), dataset, purpose, machine,
                                              settings, fingerprint, cost, latency
runs/<run_id>/outputs.jsonl                   what the system answered, per item
runs/<run_id>/scores/<scorer>@<reference>/
    score.json                                the scorer, the reference, the label the score is read under
    metrics.json                              the score: what it measured, where it differs from run.json
    predictions.jsonl                         its rows, per item
```

A score's key is the scorer, an adapter's 12-character sha256 (or a judge scorer's id), then the reference it was
scored against: `gold.<dataset>`, `silver.<dataset>`, `labels.<dataset>.<set>`, or for a judge, its judging set. A
judging pass's own summary is `data/judge-summaries/<judge scorer>@<judging set>.json`.

`run.json` and a score's `metrics.json` together carry the three things that make a number mean something:
`dataset_id` (what it measured), `config_id` (the instrument), and `build` (the system under test). A run missing any
of them cannot be attributed, and `make validate` fails on it. Reading a score gives the run's facts with the
score's over them, as one record.

There is no other run folder. What a folder used to say is a field:

- the run's **purpose**: `run` (the measurement of the system), `repeat`, `pair` or `retime`, and its **machine**
  (the operating system its fingerprint's runner names). `of` names the run a repeat, pair or retime is of, when
  exactly one other run of the system on the dataset exists;
- the score's **label**: `silver`, `adjudicated`, `rescored <scorer>`, `judged/<judge scorer>` or
  `labels-<dataset>-<set>`.

Every view reads an **arm**: a system on a dataset under one label, the score's and the run's purpose's joined
(`silver`, `repeats`, `rescored cd35dc1f, repeats`). The first score of a plain run is the arm every goal reads. A
throwaway pass (a smoke check, a tuning sweep) is `evh run --scratch`: it writes under `.build/`, outside the data,
and nothing that reads runs sees it.

**A run you make shows up as untracked, not ignored.** The rules force-include `run.json`, `outputs.jsonl` and each
score's three files, so `git status` offers you a new one: a fresh `data/runs/<id>/` appears as
`?? data/runs/<id>/`, and `git check-ignore -v` names the un-ignore rule (`!data/runs/*/run.json`). Commit the ones
you promote (see `baselines/`), not every experiment. The pass's checkpoint, `rows.partial.jsonl`, is never
committed. See [What is committed here](#what-is-committed-here-and-what-is-not).

---

## A repeat: a second run of an arm already measured

`evh run --purpose repeat --of RUN_ID` runs a system again to see how far two runs of it disagree. **A repeat is not
the record**: the plain run is. It is a run of its own, read under the label `repeats`, because two runs sharing a
`config_id` in one arm make every loader pick one, and none of them said so:

- `check_report_claims.py` globbed in five places, three taking the last hit and two the first, so its verdict
  depended on filesystem order: **29/29 on APFS, 28/29 on ext4**, and the ext4 answer was the right one, two cost
  cells were genuinely stale.
- `leaderboard` printed `sf_llama_l_v1 runs=2 0.683350`, the mean of 0.7281 and 0.6386, a number in no run and no
  report.
- `pair_test`, `family_test`, `rank_stability` and `holdout_significance` averaged them per item; the report scripts
  silently took the newer one.

`runs_by_arm()` in `scripts/_runs.py` raises on this for two runs of one arm. A `--repeat N` set (`<id>_r1.._rN`) is
one arm measured N times and still loads normally: that distinction is pinned by
`test_two_runs_sharing_a_config_id_are_refused`.

Three SciFact arms were re-run on 2026-09-29 to check the parser fix against a fresh measurement; they are evidence
for between-run variance:

| arm | 2026-09-28 | 2026-09-29 | like-for-like Δ |
|---|---|---|---|
| `sf_llama_l_v1` | 0.7281 | 0.6386 | **0.0126** |
| `sf_llama_s_v1` | 0.7172 | 0.7132 | −0.0003 / +0.0047 |
| `sf_qwen_s_v1` | 0.7338 | 0.7187 | −0.0004 |

Most of `llama_l`'s apparent 0.0895 swing is **not** between-run variance: 0.0417 is the parser fix applied to the
original bytes, and most of the rest is a parser artifact in the new comma path. Round 3 measured the like-for-like
delta at **0.0126**. See `REPORT_RETRIEVAL.md` §*Between-run variance*. These runs were made from a dirty tree, so
their fingerprints do not identify the code that produced them.

`cnn_bart_s_n200_v1_20260930T085713Z` is a local arm, run twice: the first run of `bart_s` (2026-09-30). A background
job was killed at item 196 of 200 and the run was finished with `--resume`; it is marked `dirty` only because the
previous run's directory was untracked in the same tree. A clean re-run is the record. **Two things it is evidence
for.** First, this arm's generation is deterministic on this machine: the two runs produced **200 of 200
byte-identical outputs**, beam search, CPU, fp16 (its stored dtype; the config's `precision: fp32` is recorded but
not applied). The retimes below extend that to all nine local arms of summarisation and classification, including
three re-run on a second machine. Hosted arms at temperature 0 do not repeat like this: 13–78 of 200 across two runs
of five SciFact arms (`REPORT_RETRIEVAL.md`). Second, it is the run that exposed the resume bug: its
`input_truncated` reads **0.75**, averaged over only the 4 items computed fresh, because resume did not carry adapter
`extra` metrics onto replayed rows. The true value, 46 of 200 articles over the 1,024-token window in the clean run,
is 0.23. Fixed; see `KNOWN_ISSUES.md`.

## A retime: every local arm re-run on one machine

`evh run --purpose retime --of RUN_ID` runs a system again on this machine for its latency. A retime is read under
the label of its machine, `linux`, and **is not the record** (the plain run is). On 2026-09-30 all nine local arms of
three experiments were re-run on one idle machine, one at a time. The point was one latency axis.

**Why this was needed.** The published latency column mixes two machines:

- **Intel Mac** (12 cores, Darwin): `bart_l`, `lead3`, `bert_mini` and every hosted arm.
- **Linux container** (4 cores): the six arms whose pickle checkpoints need torch ≥ 2.6, namely `bart_m`, `bart_s`,
  `bart_l_xsum`, AG's two `bert_base` models and DBpedia's `bert_base_fy`.

A Mac-versus-Linux ratio measures the machines as much as the models. On top of that, the recorded `bart_s` mean
(4,484 ms) was slowed by analysis work run on the same CPU while it generated. Its median, 3,683 ms, is close to the
idle figure below.

**How they were run.**

- Code identical to each recorded run: `4068ea23` for AG/DBpedia, `798c6305` for CNN/DailyMail. `build.dirty` is
  false on all nine.
- They were written outside the git tree, so earlier run directories could not mark the tree dirty.
- Load average ≈ 4 at the start of each run; nothing else was running on the machine.
- The pass's checkpoint (`rows.partial.jsonl`, resume state) is not kept.

**Latency: one machine (Linux, 4 cores), per item.** The median is the primary figure. The first one to three items
of a local run pay a one-off initialisation cost that the warm-up does not absorb: the warm-up loads the model but
runs no forward pass. That cost reached **23–24 s on one item** in the two `bert_base_fy` runs, so their means
(202 ms and 166 ms) describe that item, not the model. See `KNOWN_ISSUES.md`.

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

- `bart_m` takes **0.66×** `bart_l`'s median time (1.5× faster) and `bart_s` **0.54×** (1.8× faster). Distillation
  saves a third to a half of the time, not "half" across the board.
- On AG News `bert_mini` is **11–13×** faster than the two `bert_base` fine-tunes.
- The Linux container ran `bart_l` **1.7× faster** than the Mac did (6.3 s against 10.7 s median). A local arm timed
  on one machine and a hosted arm timed from another cannot be compared to better than that factor.

**Determinism: what was measured.**

- **Same machine, same code, six arms** (`bart_m`, `bart_s`, `bart_l_xsum`, both AG `bert_base` models, DBpedia
  `bert_base_fy`): every scored field and every output is **byte-identical** to the recorded run. That is 200 of 200
  items each, and 280 of 280 for DBpedia.
- **Across machines** (Mac → Linux, three arms):
  - `bart_l` and `lead3`: **200 of 200 outputs byte-identical**.
  - `bert_mini`: all 200 labels identical. The softmax `confidence` differs in 37 of 200 items by at most
    1.8 × 10⁻⁶ (float32 rounding), and every aggregate is unchanged.

This covers the nine local arms of these three experiments, on two CPUs. It says nothing about GPUs, other torch
builds, or the local arms of NER and retrieval, which were not re-run. Hosted arms at temperature 0 do not repeat
like this: 47 of 480 article outputs (9.8%) were byte-identical across three repeats in the earlier CNN/DailyMail
sweep, and 13–78 of 200 across two runs of five SciFact arms (`REPORT_RETRIEVAL.md`, *Between-run variance*).

To re-derive the tables, compare each retime with the run of the same `config_id` that its `of` names (or, where it
names none, the plain run of that system): `latency_ms` from the score's `predictions.jsonl`, and `outputs.jsonl`
item by item.

---

## What is committed here, and what is not

Every run's `run.json` and `outputs.jsonl`, and every score's `score.json`, `metrics.json` and `predictions.jsonl`, is
committed, so every number in the reports can be recomputed by anyone, not only by its author.

| | committed | why |
|---|---|---|
| `run.json` | **yes** (~1.2 MB) | the pass: system, dataset, fingerprint, cost, latency |
| `metrics.json`, `score.json` | **yes** (~2.5 MB) | every leaderboard, cost figure and headline number |
| `predictions.jsonl` | **yes** (~107 MB) | per-item scores, so every separation test, rank-stability curve and holdout can be rerun |
| `outputs.jsonl` | **yes** (~43 MB) | the models' generated text, which a re-score reads. Most of it is single class words, document ids, or CC BY-SA 4.0 entity spans; only summarisation's ~60-word model paraphrases raise a copyright question |

(Sizes as of 2026-11-13, over every score of the 305 runs; a re-score adds a score to a run, not a copy of it.)

**What committing `outputs.jsonl` does NOT buy.** A clone still cannot rescore, because the corpora are gitignored:
none of them is ours to redistribute. A clone has the smoke example's five reference files and none of the reference
sets the example runs were scored on, so those must be rebuilt with each example's seeded `fetch.py` first:
`ag_news_200`, `cnn_dailymail_20`, `cnn_dailymail_200`, `cnn_dailymail_dm200`, `dbpedia_280`, `few_nerd_280`,
`scifact_200`, `summeval_100`. Corpora are a free deterministic re-fetch; model outputs were paid for once, and they
ship.

Running `rescore.py` without the references refuses and names the fetcher: scoring would treat every gold set as
empty and report a plausible wrong number (f1 0.1071 for an arm whose recorded f1 is 0.6798, every prediction a false
positive).

**Checked before committing: `predictions.jsonl` carries no article text.** `_meta` holds provider metadata, a
predicted label, a list of document ids, or Few-NERD entity spans (CC BY-SA 4.0, redistributable with attribution).
No summary, no source sentence, no abstract.

### The exception: the summarisation dev runs

`cnn_dailymail_20`'s three-repeat runs are **excluded**. They predate `_portable_id` and record an absolute adapter
path containing a username and a former project name.

They are excluded rather than edited: rewriting a field inside a finished run would leave `fingerprint.hash`,
computed over the original bytes, describing content that no longer exists, which is a worse failure than withholding
a file. **No measurement run is affected**; every number in the reports comes from the committed runs. What cannot
be recomputed from this repo alone is the n=20 dev-slice half of `REPORT_SUMMARIZATION.md` §3.6 and its variance
decomposition. Regenerate with:

```bash
make run SYSTEM=<id, in examples/summarization-cnn-dailymail/systems/> DATASET_ID=cnn_dailymail_20 ARGS="--repeat 3"
```
