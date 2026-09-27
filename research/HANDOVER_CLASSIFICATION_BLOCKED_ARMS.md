# Handover — the two AG News arms that cannot run on x86_64 macOS

State as of 2026-09-27. Branch `classification-ag-news-blocked-arms`, branched from
`classification-ag-news`. Four configs, all dry-run clean, none runnable here.

Read [`HANDOVER_CLASSIFICATION_AG_NEWS.md`](HANDOVER_CLASSIFICATION_AG_NEWS.md) first —
this is the leftover slice of that study, not a separate one.

## Why they are blocked

`textattack/bert-base-uncased-ag-news` and `fabriceyhc/bert-base-uncased-ag_news` both
ship `pytorch_model.bin` and no safetensors. `transformers` refuses to `torch.load` a
pickle below torch 2.6 (CVE-2025-32434), and PyTorch publishes no Intel-Mac wheel above
2.2.2, so the condition cannot be met on this machine.

Identical to the summarisation example's distilbart situation. The procedure, the machine
requirements and the corpus-integrity check are all in
[`../examples/summarization-cnn-dailymail/RUNNING_THE_ML_ARMS.md`](../examples/summarization-cnn-dailymail/RUNNING_THE_ML_ARMS.md)
— read it, then substitute the commands below.

**Nothing in the adapter or the configs needs changing.** The example's `uv.lock` resolves
torch 2.14.0 for every platform except x86_64 macOS, by marker, so a clone on Linux or
Apple Silicon picks a torch that satisfies the guard with no edit.

## What the arms are for

`ag_bert_mini` (44MB, distilled) already finished **first of 28** at 0.9450, ahead of all
24 hosted LLMs. These are the same task with ~10x the parameters:

> Was the 44MB result a floor or a ceiling? Does a full bert-base buy anything over a
> distilled one, on a task both were trained for?

Two independent fine-tunes of the same base model on the same dataset, by different
authors, are also a check on each other. If they disagree by more than a point or two,
that is a finding about fine-tuning variance, not about the harness.

## THE HAZARD: label order is an assumption, and it fails silently

Both checkpoints carry `id2label` = `LABEL_0 … LABEL_3`, the training default. **Neither
says which class each position means.** The configs assume the HuggingFace `ag_news`
`class_label` order:

```yaml
label_order: [World, Sports, Business, "Sci/Tech"]
```

That is almost certainly what they were trained against. It is still an assumption.

A wrong order does not error. Every prediction remains one of four valid labels, nothing
looks malformed, and the arm just reports a bad number — the model blamed for the config's
mistake. This is exactly why `label_order` is in the fingerprint for `hf_local` arms.

### How to verify rather than trust

`textattack`'s model card publishes its own eval-set accuracy: **0.9514**.

| observed | reading |
| --- | --- |
| ~0.95 | the order is right, and the published figure is also an instrument check on us |
| ~0.25 | permuted — accuracy collapses to chance on a balanced set |
| in between | read the confusion matrix |

```bash
$PY scripts/classification_report.py --dataset-id ag_news_200 --arm ag_bert_base_ta_n200_v1
```

A consistent off-diagonal band **is** a permutation. Rotate `label_order` until the
diagonal lands, and record which rotation was needed — that is a fact about the
checkpoint worth keeping, not a config tweak to bury.

`fabriceyhc` publishes no accuracy, so its check is the sibling arm: it should land near
`textattack`'s figure.

## Steps

```bash
git clone https://github.com/chipi/eval-harness.git
cd eval-harness
git checkout classification-ag-news-blocked-arms

cd examples/classification-ag-news
uv sync --extra local
uv run python -c 'import torch; print(torch.__version__)'    # must be >= 2.6

uv run fetch.py --n 200
uv run fetch.py --n 20

cd ../../harness
PY=../examples/classification-ag-news/.venv/bin/python
PYTHON=$PY make dataset-materialize DATASET_ID=ag_news_200
PYTHON=$PY make dataset-materialize DATASET_ID=ag_news_20
```

`materialize` hashes every item against the `source_sha256` frozen in the tracked dataset
JSON and dies on drift, so it answers "did I fetch the same corpus?" with a command rather
than with trust. **Do not run `dataset-create`** — it would rewrite the frozen dataset to
describe whatever was downloaded and destroy that check.

Then, on a clean tree (or every run records `harness.dirty: true` and cannot be reproduced
from its own fingerprint):

```bash
for c in bert_base_ta bert_base_fy bert_base_ta_n200 bert_base_fy_n200; do
  $PY -u scripts/experiment_run.py \
     --config ../examples/classification-ag-news/configs/arm_${c}.yaml
done
```

Fast — bert-base on ~40-word texts is milliseconds per item on CPU. The downloads (438MB
each) dominate.

## Bringing them back

`data/runs/*` is gitignored, so copy rather than commit:

```bash
cd harness/data/runs
tar czf ag-blocked-arms-runs.tgz ag_bert_base_*
```

Unpack into `harness/data/runs/` on the other side. Each directory carries its own
`metrics.json` with the full fingerprint, so a run is self-describing wherever it lands.

## What to run when they arrive

```bash
$PY scripts/classification_report.py --dataset-id ag_news_200
$PY scripts/family_test.py --dataset-id ag_news_200 --a ag_bert_mini_n200_v1 \
     --against _n200_v1 --metric correct
```

The family test is the one that matters: it currently says `bert_mini` is ahead of 27 of
27 opponents and separated from 18. Adding two strong arms will change both numbers, and
**adding arms at the top can move the count either way** — the summarisation study
predicted a fall from more arms and got a rise, because the new arms widened the observed
span faster than Nemenyi's critical difference grew. Do not assume the direction.

## Open items carried from the parent branch

- `fetch.py` draws the dev slice as the FIRST k per class, which guarantees nesting but
  not representativeness — `ag_keyword` scored 0.35 on the 20 and 0.67 on the 200. The fix
  is a seeded random subset of the measurement slice. Not applied, because it would
  invalidate 28 measured runs.
- No family test on `macro_f1`: it is not a per-item metric, so `family_test.py` cannot
  take it. A real gap.
- Calibration recorded (`confidence`) and unanalysed. Hosted arms have no `confidence` at
  all — logprobs were never requested.
- Runs live on one machine and are gitignored. Nothing is backed up.
