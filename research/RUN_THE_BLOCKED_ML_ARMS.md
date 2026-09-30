# Run the 6 blocked ML arms — copy/paste

> **Done 2026-09-30** — all six ran on Linux; results in REPORT_CLASSIFICATION and
> REPORT_SUMMARIZATION, the account in NOTES entry 59. Kept as the recipe for a re-run.
> Three corrections to the first version of this file, all found by following it:
>
> - "The lock already resolves torch 2.14 on Linux" was true for summarisation only; the
>   two classification locks resolved **2.2.2** everywhere. Fixed in `4068ea23` (the local
>   extra now says `torch>=2.6` off Intel Mac, in all five examples).
> - `dataset_create` **refuses** on a committed dataset (exit 1, nothing written) — it is
>   dropped below. `materialize` alone verifies a fresh fetch against the frozen hashes.
> - Run with `EVAL_RUNS_DIR` **outside the git tree**, or every run after the first is
>   recorded `dirty` (the earlier run directories are untracked files). Copy the finished
>   runs into `harness/data/runs/` afterwards, without `run.json` and `outputs/_rows.jsonl`.
>
> And a shortcut nobody took: each checkpoint has a safetensors conversion PR on the Hub
> that loads on torch 2.2.2 — see [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).

These six need **torch ≥ 2.6**, which has no Intel-Mac wheel. On Linux or Apple Silicon
the lock resolves torch 2.14 by platform marker — **no code changes, no config edits.**
Just clone, sync, fetch, run.

```bash
git clone https://github.com/chipi/eval-harness && cd eval-harness
cp harness/.env.example harness/.env       # only needed for the hosted arms; these six are local
```

---

## 1 · Summarisation — 3 arms

```bash
cd examples/summarization-cnn-dailymail
uv sync --extra local
uv run fetch.py --n 200

cd ../../harness
PY=../examples/summarization-cnn-dailymail/.venv/bin/python
# (dataset_create skipped: cnn_dailymail_200 is committed, and it refuses)
$PY scripts/materialize.py --dataset-id cnn_dailymail_200

for a in bart_m bart_s bart_l_xsum; do
  $PY scripts/experiment_run.py --config ../examples/summarization-cnn-dailymail/configs/arm_${a}_n200.yaml
done
```

## 2 · AG News — 2 arms

```bash
cd ../examples/classification-ag-news
uv sync --extra local
uv run fetch.py --n 200

cd ../../harness
PY=../examples/classification-ag-news/.venv/bin/python
# (dataset_create skipped: ag_news_200 is committed, and it refuses)
$PY scripts/materialize.py --dataset-id ag_news_200

for a in bert_base_fy bert_base_ta; do
  $PY scripts/experiment_run.py --config ../examples/classification-ag-news/configs/arm_${a}_n200.yaml
done
```

## 3 · DBpedia — 1 arm, and the one that matters most

```bash
cd ../examples/classification-dbpedia-14
uv sync --extra local
uv run fetch.py --n 280

cd ../../harness
PY=../examples/classification-dbpedia-14/.venv/bin/python
# (dataset_create skipped: dbpedia_280 is committed, and it refuses)
$PY scripts/materialize.py --dataset-id dbpedia_280
$PY scripts/experiment_run.py --config ../examples/classification-dbpedia-14/configs/arm_bert_base_fy_n200.yaml
```

**Why this one first if you only run one.** DBpedia is the only experiment with *no*
fine-tuned local arm, so its report cannot answer "should I fine-tune instead of paying".
Every other experiment says yes. This single run closes the biggest open question in the
set — and AG News's near-identical setup predicts it will land near the top.

---

## Then send back

```bash
cd harness
make ci                                                   # must be green before you commit
python scripts/leaderboard.py --dataset-id dbpedia_280    # and the other two
python scripts/cost_report.py --dataset-id dbpedia_280    # $0 for these, but it proves the arm is local
git add data/runs && git commit -m "ML arms from a torch>=2.6 machine" && git push
```

`metrics.json`, `predictions.jsonl` and `outputs/` are committed; `run.json` and
`outputs/_rows.jsonl` are crash-recovery files and are gitignored. Or just send the
`harness/data/runs/<arm>_*/` directories.

**Three things that will bite, all found in review:**

- **Do not run an arm that already has a run** unless you move the old one out of
  `data/runs/` first. Two runs sharing a `config_id` are averaged together by every
  loader; `runs_by_arm` now raises and the loaders warn, but the cleanest answer is one
  run per arm in that directory. Second runs belong in `data/runs-repeats/`.
- **Commit before you run.** `runs-list` marks runs made from a dirty tree with `*`;
  their `build.ref` does not identify the code that produced them, and they are not
  promotable.
- **If a run dies partway**, `--resume <run_id>` replays what is on disk and pays only
  for what is missing. It refuses if the source is a different arm or cannot be
  identified. `--resume` and `--repeat` are mutually exclusive.

## What to expect, so a surprise is noticed

| arm | prediction | based on |
|---|---|---|
| `db_bert_base_fy` | **top 3 of 28**, ≥0.98 | `bert_mini` won AG News outright, and DBpedia is the more saturated corpus |
| `ag_bert_base_fy` / `_ta` | near `bert_mini`'s **0.9450** | same architecture, same task. Note `bert_mini` leads AG News but is **not separated** from the nine arms behind it (p = 0.0136 vs a 0.0083 Holm threshold), so landing inside that group is the expected result, not a null one |
| `cnn_bart_m` / `_s` | **below** `bart_l`'s 0.3461 | distilled from it |
| `cnn_bart_l_xsum` | **well below** — XSum trains one-sentence summaries | out of distribution |

These are priors, not results. A wildly different number means something is wrong with the
run, not that the prior was interesting.

## If it fails

- **`torch.load` / CVE-2025-32434** → your torch is < 2.6. Check `$PY -c "import torch; print(torch.__version__)"`. The lock only pins old torch on Intel Mac.
- **`uv sync` succeeds but the model won't load** → you likely ran plain `uv sync`; the ML arms need `--extra local`.
- **gated repo 403** → `huggingface-cli login`, then accept the licence on the model page.

Full background: [`HANDOVER_ML_ARMS.md`](HANDOVER_ML_ARMS.md) ·
[`HANDOVER_DBPEDIA_BLOCKED_ARM.md`](HANDOVER_DBPEDIA_BLOCKED_ARM.md) ·
[`../examples/summarization-cnn-dailymail/RUNNING_THE_ML_ARMS.md`](../examples/summarization-cnn-dailymail/RUNNING_THE_ML_ARMS.md)
