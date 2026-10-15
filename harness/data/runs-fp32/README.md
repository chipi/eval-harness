# `runs-fp32/`: `bart_s` at the precision its config declared

`distilbart-cnn-6-6` (`bart_s`) is stored at fp16, and until the 2026-10-14 instrument
fix no adapter applied a config's `precision`, so its committed runs in `data/runs/` were
computed at **fp16 under a `precision: fp32` label** (KNOWN_ISSUES). The fix casts every
local model to its declared precision; these two runs are `bart_s` re-measured with it.

**They are not the record.** `data/runs/` is: the fp16 runs are what was measured, and
they stay. These live beside them for the same reason as `runs-linux/` — same
`config_id`s, which one directory refuses.

| run | slice | `coverage` fp16 (record) | `coverage` fp32 (here) | identical scores | identical summaries |
|---|---|---:|---:|---:|---:|
| `cnn_bart_s_n200_v1_20261015T040857Z` | CNN, 200 | 0.3276 | 0.3274 | 199 / 200 | 194 / 200 |
| `cnn_bart_s_dm200_v1_20261015T042310Z` | DailyMail, 200 | 0.4039 | 0.4048 | 187 / 200 | 185 / 200 |

Both from a clean tree (`build.dirty: false`, commit `8165bd94`), weights pinned to
`d2fde4ca965b`, `loaded_dtype: float32`, no `precision_not_applied` flag. One 4-core Linux
container, otherwise idle.

**No finding moves.** With these substituted, `bart_l`'s Holm family over the five local
arms gives the same verdicts on both slices: `bart_s` separated from `bart_l` (CNN
p = 0.0166, DailyMail p < 0.0001), `bart_m` not separated. `check_report_claims.py`
verifies both figures against these runs.
