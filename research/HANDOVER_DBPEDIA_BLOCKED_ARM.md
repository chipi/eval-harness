# Handover — the DBpedia arm that cannot run on x86_64 macOS

State as of 2026-09-27. Branch `classification-dbpedia-blocked-arms`, branched from
`classification-dbpedia`. Two configs (both slices), dry-run clean, not runnable here.

Read [`HANDOVER_CLASSIFICATION_DBPEDIA.md`](HANDOVER_CLASSIFICATION_DBPEDIA.md) first —
this is the missing piece of that study, and it is a bigger missing piece than the
equivalent branch for AG News.

## Why this one matters more than the other blocked arms

The classification pair exists to ask one question: **does a small task-specific model
beat frontier LLMs?**

- **AG News answered it.** `bert_mini` — 44MB, safetensors, ran on the Intel Mac — scored
  0.9450 and beat all 24 hosted arms, separated from 18 of 27 under Holm.
- **DBpedia cannot answer it at all.** Not one credible DBpedia-14 fine-tune on the Hub
  loads here.

```
fabriceyhc/bert-base-uncased-dbpedia_14      pytorch_model.bin only    438 MB
Danni/distilbert-base-uncased-finetuned-...  pytorch_model.bin only    268 MB
kundank/dspt-roberta-base-dbpedia14          pytorch_model.bin only    499 MB
TheChickenAgent/DBPedia_Classes_BERT-*       pytorch_model.bin only    438 MB
```

All of them are 2021–2023 uploads, predating safetensors becoming the default. This is
not one unlucky checkpoint; it is the whole cohort for this dataset.

`transformers` refuses `torch.load` below torch 2.6 (CVE-2025-32434), and PyTorch
publishes no Intel-Mac wheel above 2.2.2, so the condition cannot be met. Machine
requirements and the corpus-integrity check are in
[`../examples/summarization-cnn-dailymail/RUNNING_THE_ML_ARMS.md`](../examples/summarization-cnn-dailymail/RUNNING_THE_ML_ARMS.md).

Nothing in the adapter or configs needs changing: the example's `uv.lock` resolves torch
2.14.0 for every platform except x86_64 macOS, by marker.

## THE HAZARD: label order, and 14 classes make it worse

`config.json` carries `id2label` = `LABEL_0 … LABEL_13`, the training default. **The
checkpoint does not say which class each position means.** The config assumes the
HuggingFace `dbpedia_14` `class_label` order, which is almost certainly correct and is
still an assumption.

A wrong order does not error. Every prediction remains one of fourteen valid labels,
nothing looks malformed, and the arm reports a bad number with the model taking the blame
for the config. With four classes a permutation might be noticed by eye; **with fourteen,
the confusion matrix is the only thing that will show it.**

### Verify, do not trust

The model card publishes no accuracy, so the checks are:

| observed | reading |
| --- | --- |
| ~0.98–0.99 | right — the published range for fine-tuned transformers on DBpedia-14, and a confirmation of our instrument |
| ~0.07 | permuted — accuracy collapses to 1/14 chance on a balanced set |
| in between | read the confusion matrix |

```bash
$PY scripts/classification_report.py --dataset-id dbpedia_280 --arm db_bert_base_fy_n200_v1
```

A consistent off-diagonal band **is** a permutation. Rotate `label_order` until the
diagonal lands, and **record which rotation was needed** — that is a fact about the
checkpoint, not a config tweak to bury.

## Steps

```bash
git clone https://github.com/chipi/eval-harness.git
cd eval-harness && git checkout classification-dbpedia-blocked-arms

cd examples/classification-dbpedia-14
uv sync --extra local
uv run python -c 'import torch; print(torch.__version__)'    # must be >= 2.6

uv run fetch.py --n 280
uv run fetch.py --n 56

cd ../../harness
PY=../examples/classification-dbpedia-14/.venv/bin/python
PYTHON=$PY make dataset-materialize DATASET_ID=dbpedia_280
PYTHON=$PY make dataset-materialize DATASET_ID=dbpedia_56
```

`materialize` hashes every item against the frozen `source_sha256` and dies on drift, so
"did I fetch the same corpus?" is answered by a command. **Do not run `dataset-create`** —
it would rewrite the frozen dataset to describe whatever was downloaded and destroy that
check.

The fetch is seeded (`--seed 20260927` by default), so the same `--n` reproduces the same
items on any machine. It takes a few minutes: 280 sequential API calls with a 0.35s
politeness delay.

Then, on a clean tree:

```bash
for c in bert_base_fy bert_base_fy_n200; do
  $PY -u scripts/experiment_run.py \
     --config ../examples/classification-dbpedia-14/configs/arm_${c}.yaml
done
```

Fast — bert-base on ~50-word abstracts is milliseconds per item on CPU. The 438MB
download dominates.

## Bringing it back

```bash
cd harness/data/runs && tar czf db-blocked-arm-runs.tgz db_bert_base_fy_*
```

Unpack into `harness/data/runs/`. Each directory carries its own `metrics.json` with the
full fingerprint.

## What to run when it arrives

```bash
$PY scripts/classification_report.py --dataset-id dbpedia_280
$PY scripts/family_test.py --dataset-id dbpedia_280 --a db_bert_base_fy_n200_v1 \
     --against _n200_v1 --metric correct
```

**The question to ask it.** On DBpedia the hosted leader `qwen_m` is at 0.9929 and the
top ten arms span four items in 280. A fine-tuned model would have to exceed 0.9929 to
lead, and it is competing against a ceiling that label noise partly sets — three items
are disputed by the entire field. So:

- **if it lands ~0.99 and does not separate from the top group**, the AG News finding does
  NOT generalise: task-specific training wins where there is headroom and buys nothing
  where there is not. That is the more useful result for deciding what to ship.
- **if it clears the group decisively**, the AG News finding holds on a second, harder
  taxonomy, and the case for a small fine-tuned classifier over an LLM call gets much
  stronger.

Either way, run `classification_report.py`'s ITEMS THE FIELD MISSED section afterwards and
check whether the fine-tuned arm gets the three disputed items "right". If it does, that
is not skill — it is having learned DBpedia's ontology quirks, which is exactly the
in-distribution caveat the AG News handover was corrected to state.

## Open items carried from the parent branch

- No `macro_f1` significance test. Macro-F1 has no per-item value so the sign-flip test
  cannot take it; the right tool is a bootstrap over items and it is not built.
- Calibration recorded and unanalysed; hosted arms have no `confidence` at all.
- No `rank_stability` at k=27.
- Runs live on one machine and are gitignored.
