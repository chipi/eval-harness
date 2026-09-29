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

**One arm of nineteen.** The rest are byte-identical passthroughs.

| arm | before | after | items reordered |
|---|---|---|---|
| `sf_qwen_s_n200_v1` | 0.7338 | **0.7183** | 16 of 200 |

*Two more arms appeared here until 2026-09-30 — `llama_l` 0.7281 → 0.6864 and `llama_s`
0.7172 → 0.7129. Both were artifacts of the round-2 parser fix rather than corrections
to it: its new comma path let the line parser accept `[8925851` and `21884449]` as
document ids out of a reply that opened with an array and then corrected itself in
prose. Both revert under the tightened parser. See REPORT_RETRIEVAL §"The parser fix,
what it actually moved".*

## Why you can trust a rebuild over a measurement

1. Re-parsing `_meta.llm_raw` with a reimplementation of the **old** parser reproduces
   the recorded `llm_returned` for **200/200 items on all 12 reranking arms** — so the
   2000-character cap on the stored reply hides nothing the parser would have used.
2. `qwen_s` was **re-measured from scratch** and the rebuild predicted it to within
   **0.0004** (0.7183 against 0.7187).
3. The 2026-09-29 re-runs in `../runs-repeats/` pass through this tool unchanged.

## What these are not

Not measurements. Every file carries `reparsed_from`, `reparsed_with` and a **null**
`fingerprint.hash` with `hash_invalid_because`. Regenerate for $0:

```bash
python examples/retrieval-scifact/reparse.py
```

Needs the corpus, which is gitignored — run the example's `fetch.py` first.
