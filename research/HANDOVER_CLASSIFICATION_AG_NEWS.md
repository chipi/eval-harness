# Handover — the AG News classification example

State as of 2026-09-27. Facts, numbers and locations. This is the second worked example;
the summarisation study it reuses the harness from is in [`HANDOVER.md`](HANDOVER.md) and
[`HANDOVER_ML_ARMS.md`](HANDOVER_ML_ARMS.md).

## Repo state

Branch `classification-ag-news`, branched from `ml-arms-bart-lead3` (so `family_test.py`
and `--items` are available). Working tree clean. `make ci` green. `gitleaks`: no leaks.

28 runs in `harness/data/runs/` on `ag_news_200` and 28 in `data/runs-smoke/` on
`ag_news_20`. Both directories are gitignored — **the runs exist on one machine and are
not backed up.**

## Headline

**A 44MB model fine-tuned on the task beats all 24 hosted LLMs.**

```
dataset: ag_news_200   k=28 arms   N=200 items

  ag_bert_mini      accuracy 0.9450   macro_f1 0.9453   $0       7.1 ms/item
  ag_anthropic_m             0.9100            0.9106   $0.105   1.9 s      <- best hosted
  ag_anthropic_l             0.9000            0.8998   $0.175   2.0 s
  ag_openai_m                0.8950            0.8952   $0.035
  ag_openai_l                0.8900            0.8900   $0.064
  ...  (19 more hosted arms, 0.835 - 0.885)
  ag_bart_mnli               0.7000            0.6817   $0       <- zero-shot, same arch
  ag_keyword                 0.6700            0.6706   $0       <- ~20 regex rules
  ag_constant                0.2500            0.1000   $0
```

Global block: `p = 0.0002`, Nemenyi CD 3.01, **34 of 378** pairs distinguishable. On the
180 items the dev slice does not contain: 29 of 378, same ordering at the top.

### The pre-registered family test

`family_test.py`, `--a ag_bert_mini_n200_v1 --against _n200_v1`, Holm over m=27 declared
before the p-values were read:

- **ahead on the point estimate against 27 of 27**
- **separated from 18 of 27**
- NOT separated from the six strongest hosted arms: `anthropic_m` (p=0.1164),
  `anthropic_l` (0.0630), `openai_m` (0.0386 vs threshold 0.0167), `openai_l`, `qwen_m`,
  `llama_m`

So the defensible claim is: **a 44MB classifier is statistically indistinguishable from
the best frontier models and clearly better than the other 18, at zero marginal cost and
270x lower latency.** Not "it beats them all" — the top six are a group, not a ranking.

## Five findings

**1. The parser is worth 7.5 accuracy points on one arm.**

```
ag_glm_l_n200   correct=0.860   correct_after_repair=0.075   fmt_verbose=0.090
```

15 of 200 items are scored correct only because `_parse_label` is lenient; without it that
arm reads 0.785 rather than 0.860 — wider than the gap separating most of the field. On
this arm the scoring code matters more than the model choice. This is why `parser_sha256`
is in every arm's fingerprint.

**I stated the opposite earlier and was wrong.** The first commit of this example says
`parser_sha256` was "machinery that is unexercised, not machinery that is proven". Three
of 24 hosted arms had been tried at that point. `glm_l` is the exercise.

**2. The dev slice is nested but NOT representative, and that is a flaw in my fetcher.**

```
ag_keyword   dev(n=20) 0.3500   ->   n=200 0.6700
```

A 32-point swing. The 20 items are a subset of the 200, so `keyword` scores 7/20 on them
and 127/180 on the rest; if the true rate were 0.67, observing 7/20 is ~3 SD low, p≈0.001.
Not noise.

`fetch.py` gets nesting by taking the FIRST k of each class in split order. That
guarantees `holdout_significance --exclude-dataset` works, and it does not make the dev
items a representative sample. **Fix for the next example: draw the dev set as a seeded
RANDOM subset of the measurement slice.** Keeps nesting, buys representativeness.

The dev slice was still sound for what it was used for — finding which arms narrate or
fail to parse, a property of the model rather than of the items — and no arm was selected
on it. That turned out to matter more than was known at the time.

**3. Binary outcomes put the paired tests in a different regime.** `bert_mini` beats
`anthropic_m` by +0.035 while winning only **11 of 200 items**; the other 189 are ties
where both arms are right or both wrong. The sign-flip test operates on discordant pairs
only, which is McNemar's structure arrived at from the other direction. Predicted before
the run, and visible in the `wins` column of every family test here.

**4. Sci/Tech is the systematically hardest class** — worst-F1 class for 17 of 28 arms.
A property of the Sci/Tech-vs-Business boundary in the corpus, not of any arm.

**5. The dev slice saturates and the measurement slice does not.** Seven arms tied at
exactly 1.0000 on n=20. Every one of them fell at n=200 — `anthropic_l` 1.00 -> 0.90,
`gemma_s` 1.00 -> 0.875, `openai_s` 0.95 -> 0.86. The winner's curse in miniature, on a
slice small enough to see it happen.

## Instrument validation

Two independent checks, both passed:

- `ag_constant` reads **0.2500 exactly** at n=20 and n=200. `fetch.py` draws equal numbers
  per class, so any other value would mean the slice is unbalanced or the scorer is wrong.
- `bert_mini`'s **0.945** reproduces the published figure for fine-tuned BERT-class models
  on AG News. Somebody else's baseline confirming ours, which is the reason a standard
  dataset was used.

## What the harness gained

- `scripts/classification_report.py` (+ registered in `self_test`'s CLI list) — confusion
  matrix, macro-F1, per-class precision/recall, built from `_meta.predicted`.
  **Macro-F1 cannot be a per-item metric**: accuracy can be scored per item and averaged,
  F1 needs a confusion matrix, which is not a property of any item. Written down as a
  limitation rather than papered over with a per-item pseudo-F1.
- Fingerprint additions for classification: `parser_sha256`, `labels_sha256` + `labels` on
  every arm; `label_order` and `encoder_window` on `hf_local`; `hypothesis_template` on
  `hf_zeroshot`. `constant` deliberately does NOT carry `rules_sha256` — it runs no rules.
- **V5 was wrong for discrete metrics, and this sweep found it.** The check's premise was
  "independent arms do not agree to full float precision; one of them is not its own
  measurement". True for ROUGE, false for accuracy: 200 binary items give a mean with 201
  possible values, so two genuinely different models both getting 172 right report
  byte-identical 0.86. It fired four times on this sweep, every one a false positive —
  `openai_s`/`mistral_m`/`glm_m` at 0.86, `qwen_l`/`deepseek_l`/`gemma_l` at 0.87, and so on.

  Fixed at the cause rather than muted: V5 now flags only when the means agree **and** the
  per-item results agree. Two arms tying on the mean while disagreeing about which items
  they got right are two measurements; two arms agreeing item by item are the case the
  check exists for, and a low-cardinality metric cannot hide that. Verified in both
  directions by `test_v5_tells_a_tie_from_a_copy` — a tie passes, a copied run with
  different params still fails.

## For the sibling podcast project

`src/podcast_scraper/gi/insight_type_classifier.py` is the `keyword` arm's shape: ordered
regex rules, first match wins, a catch-all default. Its docstring already names the swap
point (`classify_insight_type(text) -> str`).

Here that shape scores **0.67** against a fine-tuned small model at **0.945** and a hosted
LLM call at 0.91. The fine-tuned classifier wins on accuracy, cost AND latency at once —
7 ms against ~2 s, which is the axis that matters at a 10k-episode target.

**This does not transfer without labels.** AG News has gold labels; `insight_type` has
none, so nothing here says what the production rules actually score. Getting that number
means hand-labelling a few hundred insights. The `references/gold` vs `silver` distinction
exists to stop that step being skipped.

## Blocked

The best-known AG News fine-tunes ship `pytorch_model.bin` and no safetensors, so they hit
the same CVE-2025-32434 wall as the summarisation example's distilbart arms:
`fabriceyhc/bert-base-uncased-ag_news`, `textattack/bert-base-uncased-ag-news`. See
`examples/summarization-cnn-dailymail/RUNNING_THE_ML_ARMS.md` for the machine they need.

## Open items

- **`fetch.py`'s dev draw should be seeded-random, not first-k per class** (finding 2).
  Not changed here, because changing it would invalidate the 28 runs already measured.
- No `rank_stability` at k=28. No family test on `macro_f1` (it is not a per-item metric,
  so `family_test.py` cannot take it — a real gap).
- Calibration is recorded (`confidence` on both local arms) and unanalysed. `bert_mini`
  reports 0.957 mean confidence at 0.945 accuracy, which looks well calibrated and has not
  been tested.
- The hosted arms have no `confidence` — logprobs were not requested. That is the obvious
  next fingerprint/metric addition.
- `research/REPORT.md` and `NOTES.md` carry none of this.
- Runs are on one machine and gitignored.

## Reproducing

```bash
cd examples/classification-ag-news && uv sync --extra local
uv run fetch.py --n 200 && uv run fetch.py --n 20
cd ../../harness
PY=../examples/classification-ag-news/.venv/bin/python
PYTHON=$PY make dataset-create DATASET_ID=ag_news_200 ARGS='--source-dir data/sources/ag_news_200'
PYTHON=$PY make dataset-materialize DATASET_ID=ag_news_200

$PY scripts/classification_report.py --dataset-id ag_news_200
$PY scripts/family_test.py --dataset-id ag_news_200 --a ag_bert_mini_n200_v1 \
     --against _n200_v1 --metric correct
$PY scripts/holdout_significance.py --dataset-id ag_news_200 \
     --exclude-dataset ag_news_20 --metric correct
```

Total hosted spend for the 200-item sweep: roughly $0.45, dominated by `anthropic_l`
($0.175) and `anthropic_m` ($0.105).
