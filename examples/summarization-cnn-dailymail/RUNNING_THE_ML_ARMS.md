# Running the three blocked ML arms on another machine

`cnn_bart_m_n200_v1`, `cnn_bart_s_n200_v1` and `cnn_bart_l_xsum_n200_v1` cannot run on
x86_64 macOS. Everything else in this example can, and already has. This document is how
to produce those three runs somewhere else and bring them back so they join the same
leaderboard as the other 26 arms.

## Why they are blocked

All three checkpoints ship `pytorch_model.bin` and no safetensors. `transformers` refuses
to `torch.load` a pickle below torch 2.6:

```
ValueError: Due to a serious vulnerability issue in `torch.load`, even with
`weights_only=True`, we now require users to upgrade torch to at least v2.6 in order to
use the function. This version restriction does not apply when loading files with
safetensors.                                                        CVE-2025-32434
```

PyTorch publishes no Intel-Mac wheel above 2.2.2, so on that machine the condition cannot
be met. `facebook/bart-large-cnn` ships safetensors, which is the only reason `bart_l` ran
there at all.

This is a machine problem, not a code problem. Nothing in the adapter or the configs needs
changing — the same files produce these runs unmodified on a machine that can take a
current torch.

## What the machine needs

Linux (x86_64 or aarch64) or Apple Silicon. The lock already resolves torch **2.14.0** for
every platform except x86_64 macOS, so there is nothing to pin or edit — `uv sync` picks
the right one by marker.

Roughly 8 GB free disk: ~3.3 GB of checkpoints plus the torch wheel and its CUDA payload
on Linux.

No GPU needed. The configs say `device: cpu` deliberately, so the wall-clock numbers stay
comparable with the arms already measured. If you want GPU numbers that is a separate,
legitimate experiment — but it is a different arm, because `latency_ms` is one of the three
axes the frontier is computed on, and changing the device silently would make the local
arms' speed column incomparable with each other.

## Steps

```bash
git clone https://github.com/chipi/eval-harness.git
cd eval-harness
git checkout ml-arms-bart-lead3

cd examples/summarization-cnn-dailymail
uv sync --extra local
```

**Confirm you got a torch that satisfies the guard** before spending an hour on downloads:

```bash
uv run python -c 'import torch; print(torch.__version__)'    # must be >= 2.6
```

If that prints 2.2.2 you are on the machine this document exists to avoid.

**Get the corpus.** Nothing is committed — CNN/DailyMail belongs to its publishers, so the
repo ships a download recipe:

```bash
uv run fetch.py --n 200
```

**Verify you got the same corpus.** This is the step that makes the comparison valid, and
it is not optional:

```bash
cd ../../harness
PYTHON=../examples/summarization-cnn-dailymail/.venv/bin/python \
  make dataset-materialize DATASET_ID=cnn_dailymail_200
```

`materialize` hashes every item and checks it against the `source_sha256` frozen in
`data/datasets/cnn_dailymail_200.json`, which is tracked in git. If it prints drift, stop —
your fetch produced different bytes and any number computed from it is not comparable with
the 26 runs already on disk. If it passes, your corpus is byte-identical to theirs.

Do **not** run `make dataset-create`. That would rewrite the frozen dataset to describe
whatever you just downloaded, which destroys the check you just ran.

**Run the three arms:**

```bash
PY=../examples/summarization-cnn-dailymail/.venv/bin/python
for c in bart_m bart_s bart_l_xsum; do
  $PY -u scripts/experiment_run.py \
     --config ../examples/summarization-cnn-dailymail/configs/arm_${c}_n200.yaml
done
```

Dry-run one first if you want the shape without the wait:
`$PY scripts/experiment_run.py --config .../arm_bart_m_n200.yaml --dry-run`

**Commit before you run**, or every run records `harness.dirty: true` and cannot be
reproduced from its own fingerprint. The runner warns when the tree is dirty; the warning
is worth obeying.

## How long

The only measured anchor: `bart_l` took **11.0 s/item** on an Intel i7 CPU at `num_beams=4`,
so 200 items was ~37 minutes. On your machine it will differ, possibly a lot. Relative
expectations, not measurements:

| arm | vs `bart_l` | why |
| --- | --- | --- |
| `bart_m` | faster | half the decoder layers (12-6 against 12-12) |
| `bart_s` | fastest | half the encoder too (6-6) |
| `bart_l_xsum` | similar or faster | same size, 6 beams not 4, but `max_length` 62 not 142 |

Budget an evening, check after the first arm.

## Bringing them back

Run directories are gitignored (`data/runs/*`), so copy them rather than committing:

```bash
cd harness/data/runs
du -sh cnn_bart_m_n200_v1_* cnn_bart_s_n200_v1_* cnn_bart_l_xsum_n200_v1_*
tar czf ml-arms-runs.tgz cnn_bart_m_n200_v1_* cnn_bart_s_n200_v1_* cnn_bart_l_xsum_n200_v1_*
```

Unpack into `harness/data/runs/` on the other side. Each directory carries its own
`metrics.json` with the full fingerprint, so a run is self-describing wherever it lands.

## What to check when they arrive

```bash
make leaderboard DATASET_ID=cnn_dailymail_200
make family-test DATASET_ID=cnn_dailymail_200 A=cnn_bart_l_n200_v1 AGAINST=_n200_v1
```

Three things are worth looking at before any ranking:

1. **`input_truncated`.** All three have the same 1024-token encoder window as `bart_l`, so
   all three should report 0.23 on this corpus. A different figure means a different
   tokenisation and is a bug, not a finding.
2. **`bart_s`'s `weight_files` sizes** in `metrics.json`. Its checkpoint is 460MB against
   `bart_m`'s 1.22GB, which the layer counts do not fully explain — it may be stored at half
   precision. The fingerprint settles it; see the note in `arm_bart_s_n200.yaml`.
3. **`bart_l_xsum`'s `summary_words` and `length_vs_reference`.** It is decoded at
   `max_length: 62` because that is what XSum trained it to produce. If it scores badly on
   `coverage`, length is at least as plausible an explanation as training distribution, and
   the two cannot be separated without a second arm at CNN/DailyMail decode lengths.

## Optional, and genuinely useful

Re-run `bart_l` there too:

```bash
$PY scripts/experiment_run.py --config ../examples/summarization-cnn-dailymail/configs/arm_bart_l_n200.yaml
```

Its numbers are already known from the Intel Mac (`coverage` 0.346121, `grounding`
0.883821, `input_truncated` 0.23). Greedy-free beam search at `do_sample: false` is
deterministic, so a second run on different hardware, a different torch and a different
NumPy is a real cross-platform reproducibility check — the kind this harness claims to
support and has never actually been asked to demonstrate. If the numbers move, that is a
more interesting result than any of the three new arms.
