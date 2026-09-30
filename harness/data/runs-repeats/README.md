# `runs-repeats/` — a second run of an arm already measured

Three SciFact arms re-run on 2026-09-29 to check the parser fix against a fresh
measurement. **They are not the record** — `data/runs/` is — and they are here rather
than beside it for a concrete reason.

## Why they cannot live in `data/runs/`

Two runs sharing a `config_id` make every loader pick one, and none of them said so:

- `check_report_claims.py` globbed in five places — three took the last hit, two the
  first — so its verdict depended on filesystem order. **29/29 on APFS, 28/29 on ext4**,
  and the ext4 answer was the right one: two cost cells were genuinely stale.
- `leaderboard` printed `sf_llama_l_n200_v1 runs=2 0.683350` — the mean of 0.7281 and
  0.6386, a number in no run and no report.
- `pair_test`, `family_test`, `rank_stability` and `holdout_significance` averaged them
  per item; the report scripts silently took the newer one.

`runs_by_arm()` in `scripts/_common.py` now raises on this. A `--repeat N` set
(`<id>_r1.._rN`) is one arm measured N times and still loads normally — that
distinction is pinned by `test_two_runs_sharing_a_config_id_are_refused`.

## What they are evidence for

| arm | 2026-09-28 | 2026-09-29 | like-for-like Δ |
|---|---|---|---|
| `sf_llama_l_n200_v1` | 0.7281 | 0.6386 | **0.0126** |
| `sf_llama_s_n200_v1` | 0.7172 | 0.7132 | −0.0003 / +0.0047 |
| `sf_qwen_s_n200_v1` | 0.7338 | 0.7187 | −0.0004 |

Most of `llama_l`'s apparent 0.0895 swing is **not** between-run variance: 0.0417 is the
parser fix applied to the original bytes, and most of the rest is a parser artifact in
the new comma path. Round 3 measured the like-for-like delta at **0.0126**. See
`REPORT_RETRIEVAL.md` §*Between-run variance*.

These runs were made from a dirty tree, so their fingerprints do not identify the code
that produced them. `runs-list` marks them.

## `cnn_bart_s_n200_v1_20260930T085713Z` — a local arm, run twice

The first run of `bart_s` (2026-09-30). A background job was killed at item 196 of 200
and the run was finished with `--resume`; it is marked `dirty` only because the previous
run's directory was untracked in the same tree. A clean re-run is the record in
`data/runs/`.

**Two things it is evidence for.** First, local generation is deterministic here: the two
runs produced **200 of 200 byte-identical outputs** — beam search, CPU, fp32 — against
13–78 of 200 for hosted arms at temperature 0. Second, it is the run that exposed the
resume bug: its `input_truncated` reads **0.75**, averaged over only the 4 items computed
fresh, because resume did not carry adapter `extra` metrics onto replayed rows. The true
value — 46 of 200 articles over the 1,024-token window, in the clean run — is 0.23. Fixed;
see `KNOWN_ISSUES.md`.
