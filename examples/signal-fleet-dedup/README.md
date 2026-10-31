# signal-fleet-dedup: a regression guard for the triage fleet's de-duplication

The homelab triage fleet folds repeated error signals into one GitHub issue before any model sees them. This
example replays 100 real, scrubbed GlitchTip signals through the fleet's own filing-stage functions and checks
that they still answer as they did at a pinned commit. There is no model and no cost.

| file | what |
|---|---|
| `fetch.py` | downloads `chipi-nbgd/signal-fleet-dedup` at `v1` from Hugging Face (sha256-pinned) and restores the capture's records and the dataset's items |
| `adapter.py` | each signal through `triage.operational_class`, `sources._is_test_signal`, `filing.low_signal`, `filing.normalized_key`; `score()` gives `key_match` and `class_match` against the pinned commit's answers |
| `configs/dedup_guard.yaml` | the one arm: the fleet's code at the commit `TRIAGE_FLEET_SRC` holds |
| `test_dedup.py` | deterministic, and a planted change to `normalized_key` is caught |

```bash
python examples/signal-fleet-dedup/fetch.py
TRIAGE_FLEET_SRC=/path/to/signal-fleet evh experiment-run --config examples/signal-fleet-dedup/configs/dedup_guard.yaml
evh leaderboard --dataset-id fleet_dedup_v1
```

The reference, `silver/fleet_dedup_v1`, is the fleet's own output at `f07efa9` (`evh reference-create --from-run`).
`key_match` below 1 on a later commit means its normalized keys merge or split signals differently: read the
changed items before deciding whether the change is a fix or a regression. When the fleet's de-duplication
changes on purpose, make a new reference from the new commit's run.
