# Handover — the one Few-NERD arm that was not measured

**Status** ~~27 of 28 measurement arms complete.~~ **CLOSED 2026-10-01 — all 28 are
complete.** `fn_mistral_l_n200_v1` measured **f1 0.5979**, parsed 279/280, $0.0419,
`providers_seen {Mistral: 280}`, fingerprint `dirty: false`. It ranks **13th of 28**,
inside the band this document predicted (0.591–0.594), slightly above it.

The retry was the whole fix, as this document said it would be: ~2 h 20 m at ~2
items/minute against the 11 hours the original rate implied. **The 429s never stopped**
— the proxy logged 70–134 per 10 minutes for the entire run — so the retry ladder
absorbed them rather than the upstream limit lifting. No BYOK key was needed.

Everything in "How to finish it" below was done, and it surfaced one defect of its own:
`rescore.py` carried `_meta.predicted` verbatim because `_meta` starts with an
underscore, so `extraction_report.py` — which reads exactly that field — was recomputing
§3.6 from the PRE-FIX parse for the four arms the round-4 parser fix moved. `glm_l` read
0.5269 against its own run's 0.5662, identically in both trees. Fixed at the source with
an adapter `reparse_meta()` hook. The 34 type disagreements and the 38% annotation bound
were NOT affected: `span_marker` and `openai_m` both parse identically before and after.

The rest of this document is kept as the record of why it was blocked.
**Date** 2026-09-28
**Branch** `ner-few-nerd`
**Report** [`REPORT_NER.md`](REPORT_NER.md) — every "of 26" in it is a family of 26, not 27,
because of this.

---

## What is missing

| | |
|---|---|
| Arm | `fn_mistral_l_n200_v1` |
| Model | `mistralai/mistral-large-2512` via OpenRouter, alias `eval-mistral-large` |
| Slice | `few_nerd_280` (measurement) |
| Dev slice | **complete** — `fn_mistral_l_v1` on `few_nerd_56` scored **f1 0.6005**, parsed 1.000, 19.6 s/item |

The dev number is **not** comparable to the measurement table. Every other arm in that
table is on 280 items; this is on 56, and the two slices differ by up to 12 rank positions
for other arms (see report §3.8).

## Why it is missing

Not a harness failure and not a code problem. The upstream provider is rate-limiting:

```
litellm.exceptions.RateLimitError: OpenrouterException -
  {"error":{"message":"Provider returned error","code":429,
   "metadata":{"raw":"mistralai/mistral-large-2512 is temporarily rate-limited upstream.
     Please retry shortly, or add your own key to accumulate your rate limits",
     "provider_name":"Mistral","is_byok":false,
     "limit_source":"upstream_provider_shared_pool"}}}
  LiteLLM Retried: 6 times, LiteLLM Max Retries: 6
```

litellm exhausts **6 internal retries** before returning 429 to the harness, which then
applies its own ladder (`EVAL_MAX_RETRIES=5`, raised from 3 for exactly this). Measured
throughput under that condition: **3 items in 7 minutes** — roughly **11 hours** for the
280-item arm, against ~14 minutes for every other hosted arm.

It ran first in the queue and blocked eight arms behind it for 18 minutes before being
moved to last; at the end of the sweep the pool had not freed up and it was stopped.

## What was tried

- `EVAL_MAX_RETRIES` raised 3 → 5. Verified first that no already-completed arm had lost
  items to the previous ceiling.
- Re-queued to run last, when the rest of the sweep was no longer competing for the pool.
  Same rate.
- The LiteLLM key budget was separately raised 35 → 60 USD earlier in the session; budget
  is **not** the constraint here. Spend on this whole example was **$2.05**.

## How to finish it

The pool is shared and the limit is time-varying, so the fix is simply to retry when it is
quiet. Nothing else needs to change.

```bash
cd harness
EVAL_RUNS_DIR=data/runs EVAL_MAX_RETRIES=5 \
  ../examples/ner-few-nerd/.venv/bin/python scripts/experiment_run.py \
  --config ../examples/ner-few-nerd/configs/arm_mistral_l_n200.yaml
```

Check it is worth starting first — if this returns quickly, the pool is open:

```bash
docker logs --tail 20 --since 2m litellm 2>&1 | grep -c "200 OK"
```

Then fold it in. **All of this is required, not optional** — the report's statistics are
over a declared family and adding a 27th member changes the Holm thresholds:

```bash
# 1. rescore so the new arm carries the SAME scorer as the other 27
python scripts/rescore.py --dataset-id few_nerd_280 --match fn_ --out data/runs-rescored

# 2. re-run the two family tests; the family becomes 27, and every threshold moves
python scripts/family_test.py --dataset-id few_nerd_280 --a fn_span_marker_n200_v1 \
    --against _n200_v1 --metric f1 --runs-dir data/runs-rescored
python scripts/family_test.py --dataset-id few_nerd_280 --a fn_openai_m_n200_v1 \
    --against _n200_v1 --metric f1 --runs-dir data/runs-rescored

# 3. the consensus pass gains a 26th learned arm, so the 34 type disagreements
#    and the upper bound in report §3.6 both move
EVAL_RUNS_DIR=data/runs-rescored python scripts/extraction_report.py \
    --dataset-id few_nerd_280 --match fn_

# 4. holdout and stability
EVAL_RUNS_DIR=data/runs-rescored python scripts/holdout_significance.py \
    --dataset-id few_nerd_280 --exclude-dataset few_nerd_56 --metric f1 --match fn_
EVAL_RUNS_DIR=data/runs-rescored python scripts/rank_stability.py \
    --dataset-id few_nerd_280 --metric f1 --match fn_
```

Then update in `REPORT_NER.md`: the §3.1 table, both family-test blocks in §3.2–3.3, the
§3.6 disagreement count and bound table, §3.8's ρ and rank moves, §3.9's stability table,
and delete the first bullet of §7.

## What must NOT be done

- **Do not substitute the dev number into the measurement table.** Different slice,
  different denominator, not a measurement of the same thing.
- **Do not lower `max_tokens` or change the prompt to make it cheaper.** Every arm in the
  family ran the identical configuration; changing one makes it incomparable, and the
  report's whole claim is that only the model differs.
- **Do not substitute a different Mistral model.** `mistral-large-2512` is the arm.

## Correction to this handover, 2026-09-29

An earlier version said: *"Do not add a personal OpenRouter key just for this arm — then
this arm's routing differs from the other 23 and `providers_seen` would no longer be
comparable."* **That reasoning does not apply to this model, and I did not check before
writing it.**

`mistralai/mistral-large-2512` is served by exactly **one** provider — Mistral itself
(two endpoints, both Mistral, $0.50/$1.50 and $0.55/$1.65 per Mtok). There is nothing to
route between. A BYOK key changes which account is *billed* and which rate-limit bucket
applies; it does not change which provider serves the request, so `providers_seen` would
still read `Mistral` and the measurement would be the same weights on the same endpoint.

It also means the error's other suggestion — "route to another provider with provider
routing" — is boilerplate that cannot help here.

**What the block actually is.** The OpenRouter account is not free-tier and has credit.
The 429 carries `"is_byok": false` and
`"limit_source": "upstream_provider_shared_pool"`: Mistral is throttling OpenRouter's
aggregate pool, upstream of this account. Buying more OpenRouter credit does nothing.

**So: wait for the pool to quieten (free, timing unknown), or add a Mistral API key at
openrouter.ai/settings/integrations so requests bill against your own Mistral rate limits
(~$0.05 for this arm).** Neither changes what is measured. Probed three times on
2026-09-29: HTTP 429 after ~35 s each.

## Expected result

It will land somewhere around the `mistral_m` / `glm_m` / `llama_l` band (0.591–0.594) —
`mistral_m` measured 0.5914, and on the dev slice `mistral_l` was +0.008 above
`mistral_m`. **This is a guess from two adjacent numbers and is not evidence.** It is
recorded so that a wildly different result is noticed as surprising rather than accepted.
