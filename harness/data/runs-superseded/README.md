# Runs superseded mid-development, kept rather than deleted

Runs whose instrument changed after they were produced, moved here instead of removed so
the record of what was measured and why it was replaced survives.

- `sf_qwen_s_v1_*`, `sf_mistral_s_v1_*` (2026-09-28) — the first two retrieval reranking
  dev runs, at `max_tokens: 400` and before the adapter stored the LLM's raw reply.
  `qwen_s` hit the 400-token ceiling on 40 of 40 queries, produced nothing parseable, and
  the pipeline fell back to BM25 on every one — scoring exactly BM25's nDCG@10 of 0.6124.
  That is what raised the budget to 700 and added `_meta.llm_raw`. Superseded because the
  arms that follow run a different instrument, not because the numbers were unwelcome.

- `sf_qwen_s_v1_20260928T16*`, `sf_gemma_m_v1_*` (2026-09-28) — every reranking run made
  before the reasoning fix. `qwen_s` was still `llm_parsed` 0.000 / `truncated` 1.000 at
  `max_tokens: 700`, and `_meta.llm_raw` (added for this) came back as the EMPTY STRING
  with 700 completion tokens spent: a model reasoning silently, not one running out of
  room. The cause was mine. This adapter never passed `reasoning: {enabled: false}`
  through `extra_body`, which the other three examples all do, so these arms ran at the
  provider's default — breaking the one property the four examples exist to support,
  that only the TASK differs between them.

  `gemma_m` is here for the same reason and not because anything looked wrong with it
  (`llm_parsed` 1.000, nDCG@10 0.6908). A uniform instrument means re-running the arms
  that were fine, too.

  The `data/runs-tune/` sweep that chose `rerank_k: 20` and `snippet_chars: 900` also
  predates the fix. Those choices are not revisited: they were made by comparing
  configurations to each other under one instrument, and that comparison is still
  internally valid.
