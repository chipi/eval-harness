# Handover — the five frontier reranking arms that were not run

**Status** 19 of 24 standard arms measured. Five were never run, by decision, not failure.
**Date** 2026-09-29 · **Branch** `retrieval-scifact`
**Report** [`REPORT_RETRIEVAL.md`](REPORT_RETRIEVAL.md) — every "of 18" in it is a family
of 18, not 23, because of this.

---

## What is missing, and why

| arm | model | input $/Mtok | est. cost at 200 queries |
|---|---|---|---|
| `sf_anthropic_s_n200_v1` | `eval-claude-haiku` | 1.00 | $2.41 |
| `sf_openai_m_n200_v1` | `eval-gpt-55` | 1.25 | $3.40 |
| `sf_openai_l_n200_v1` | `eval-gpt-6sol` | 2.50 | $6.29 |
| `sf_anthropic_m_n200_v1` | `eval-claude-sonnet` | 3.00 | $7.23 |
| `sf_anthropic_l_n200_v1` | `eval-opus-5` | 5.00 | **$12.05** |
| | | | **$31.40 total** |

Costs are *enforced* (this repo's price table × the measured 2.41 proxy multiplier).

**The entire 19-arm sweep that WAS run cost $2.45.** These five cost 12.8× the rest of the
experiment put together, because a reranking prompt carries 20 full abstracts — 3,926
input tokens per query against 125 for the NER example — and these five are priced 6–100×
above the arms that were run.

The cut was **"every arm under $0.60/Mtok input"**: price-ordered, declared before any
result was read, and applied to the whole tier rather than to individual models. It is not
a selection on outcome.

## What this costs the report

**The 12-way tie in §3.2 is a tie among cheap and free models.** The report cannot say
whether a frontier model is a better reranker, and says so. That is the single largest
open question in the example: every hosted arm measured lands in 0.7017–0.7437 across a
3.6× price range, and whether a 100× price step breaks that pattern is exactly what these
five would answer.

The prior from three other examples is that it would not — summarisation had the dearest
arm at 15th of 24, DBpedia a ten-way tie across 126×, NER an eight-way tie across 121×.
**That is a prior, not a result, and it must not be written up as one.**

## How to run them

Configs already exist and need no edits. On a fresh budget:

```bash
cd harness
for a in anthropic_s openai_m openai_l anthropic_m anthropic_l; do
  EVAL_RUNS_DIR=data/runs EVAL_MAX_RETRIES=5 \
    ../examples/retrieval-scifact/.venv/bin/python scripts/experiment_run.py \
    --config ../examples/retrieval-scifact/configs/arm_${a}_n200.yaml
done
```

Cheapest-first is deliberate: if `anthropic_s` lands inside the existing tie group, the
remaining four are buying a negative result at $29, and that is worth knowing before
spending it.

## What must be recomputed afterwards

**All of this, not some of it** — the report's statistics are over a declared family and
adding members moves every Holm threshold.

```bash
# family goes from 18 to 23; every threshold changes
python scripts/family_test.py --dataset-id scifact_200 --a sf_glm_s_n200_v1 \
    --against _n200_v1 --metric ndcg_10
# and re-run it for whichever arm leads, if the leader changes
python scripts/retrieval_report.py --dataset-id scifact_200 --match sf_
python scripts/holdout_significance.py --dataset-id scifact_200 \
    --exclude-dataset scifact_40 --metric ndcg_10 --match sf_
python scripts/rank_stability.py --dataset-id scifact_200 --metric ndcg_10 --match sf_
```

Then update in `REPORT_RETRIEVAL.md`: the §3.1 table, the §3.2 family block and its tie
list, §3.3's three deltas, §3.4's ceiling table, §3.5's rank correlation, and delete the
first bullet of §7.

## Instrument notes for whoever runs them

- These will carry a **different `harness.commit`** from the 19 already measured, and that
  is fine. What must match is `adapter.sha256` = `cedb9f962a…`; check it before believing
  a comparison. If the adapter has moved on, rescore everything into one directory first:
  `python scripts/rescore.py --dataset-id scifact_200 --match sf_ --out data/runs-rescored`
- `sf_llama_s_n200_v1` carries `harness.dirty: true` — an uncommitted analysis script, not
  an instrument difference. Its adapter hash matches the rest.
- The four `*first*` arms in `data/runs-pair/` are the first-stage swap and use a LATER
  adapter. **Do not merge them into the main table.**

## What must NOT be done

- **Do not run them at a smaller `--n` to save money.** A different denominator is not a
  cheaper version of the same measurement.
- **Do not reduce `rerank_k` or `snippet_chars` for these arms.** Every arm in the family
  ran k=20 and 900 chars; changing one makes it incomparable, and the report's claim is
  that only the model differs.
- **Do not substitute a dev-slice number.** None of these ran on dev either.

## Expected result

They land inside the existing 0.7017–0.7437 group. **This is a prior from three other
examples, not evidence**, and it is recorded so that a wildly different result is noticed
as surprising rather than quietly accepted.
