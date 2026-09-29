# Run the 6 blocked ML arms — copy/paste

These six need **torch ≥ 2.6**, which has no Intel-Mac wheel. On Linux or Apple Silicon
the lock already resolves torch 2.14 by platform marker — **no code changes, no config
edits.** Just clone, sync, fetch, run.

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
$PY scripts/dataset_create.py --dataset-id cnn_dailymail_200 --source-dir data/sources/cnn_dailymail_200
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
$PY scripts/dataset_create.py --dataset-id ag_news_200 --source-dir data/sources/ag_news_200
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
$PY scripts/dataset_create.py --dataset-id dbpedia_280 --source-dir data/sources/dbpedia_280
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
python scripts/leaderboard.py --dataset-id dbpedia_280        # and the other two
git add data/runs && git commit -m "ML arms from a torch>=2.6 machine" && git push
```

Or just send me `harness/data/runs/<arm>_*/` for each — `metrics.json` and
`predictions.jsonl` are all that's needed.

## What to expect, so a surprise is noticed

| arm | prediction | based on |
|---|---|---|
| `db_bert_base_fy` | **top 3 of 26**, ≥0.98 | `bert_mini` won AG News outright |
| `ag_bert_base_fy` / `_ta` | near `bert_mini`'s **0.9450** | same architecture, same task |
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
