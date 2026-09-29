# `runs-reparsed/` — SciFact rankings rebuilt with the corrected parser

Produced by [`examples/retrieval-scifact/reparse.py`](../../../examples/retrieval-scifact/reparse.py).
**`REPORT_RETRIEVAL.md` §3.1 quotes these figures.**

## Why `rescore.py` could not do it

`rescore` recomputes scores from a run's stored `output`. Here the output is not the
model's answer: the pipeline parses the LLM reply, applies whatever ordering it can
recover to the BM25 head, and writes the *result* as the output. The parser runs at
**call** time, so its mistakes are baked into every stored output and rescoring them
changes nothing.

The raw reply survives in `_meta.llm_raw`, because an earlier review asked for it. That
is what this rebuilds from.

## What changed

Three of nineteen arms. The rest are byte-identical passthroughs.

| arm | before | after | items reordered |
|---|---|---|---|
| `sf_llama_l_n200_v1` | 0.7281 | **0.6864** | 15 of 200 |
| `sf_qwen_s_n200_v1` | 0.7338 | **0.7183** | 16 of 200 |
| `sf_llama_s_n200_v1` | 0.7172 | **0.7129** | 2 of 200 |

## Why you can trust a rebuild over a measurement

1. Re-parsing `_meta.llm_raw` with a reimplementation of the **old** parser reproduces
   the recorded `llm_returned` for **200/200 items on all 12 reranking arms** — so the
   2000-character cap on the stored reply hides nothing the parser would have used.
2. Two of the three arms were **re-measured from scratch**, and the rebuild predicted
   them to within **0.0004** (`llama_s` 0.7129 vs 0.7132, `qwen_s` 0.7183 vs 0.7187).
3. The 2026-09-29 re-runs pass through this tool **unchanged**, because they were
   already made with the corrected parser.

`llama_l`'s re-measurement came out lower still (0.6386), and that is **not** the
parser: it invented document ids on 30 of 200 queries in the new run against 1 of 200
in the old. See REPORT_RETRIEVAL for what that says about run-to-run variance.

## What these are not

Not measurements. Every file carries `reparsed_from`, `reparsed_with` and a **null**
`fingerprint.hash` with `hash_invalid_because`. Regenerate for $0:

```bash
python examples/retrieval-scifact/reparse.py
```

Needs the corpus, which is gitignored — run the example's `fetch.py` first.
