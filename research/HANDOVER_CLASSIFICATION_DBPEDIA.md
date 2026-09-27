# Handover — the DBpedia-14 classification example

State as of 2026-09-27. Branch `classification-dbpedia`. This is the second classification
example and it exists to be the OPPOSITE regime from the first — read it beside
[`HANDOVER_CLASSIFICATION_AG_NEWS.md`](HANDOVER_CLASSIFICATION_AG_NEWS.md), because
neither one alone supports the conclusion the pair does.

## Headline

**The top ten arms are one group, and the cheapest of them costs 126x less than the
dearest.**

```
dataset: dbpedia_280   k=27 arms   N=280 items

  db_qwen_m        0.9929   macro_f1 0.9929   $0.0089    278/280
  db_anthropic_l   0.9893            0.9892   $0.3780    one item behind, 42x the price
  db_gemma_m       0.9857            0.9856   $0.0030
  db_glm_m         0.9857            0.9856   $0.0065
  db_deepseek_l    0.9857            0.9855   $0.0117
  db_qwen_s        0.9857            0.9854   $0.0024
  db_openai_m      0.9821            0.9820   $0.0634
  db_anthropic_m   0.9821            0.9818   $0.2272
  ... 16 more hosted arms, 0.939 - 0.979
  db_keyword       0.7071            0.7009   $0        ~20 regex rules
  db_bart_mnli     0.6286            0.6198   $0        zero-shot NLI
  db_constant      0.0714            0.0095   $0        exactly 1/14
```

Global: `p = 0.0002`, Nemenyi CD 2.45, **74 of 351** pairs distinguishable. Holdout on the
224 items the dev slice does not contain: identical, 74 of 351.

### The pre-registered family test

`family_test.py --a db_qwen_m_n200_v1 --against _n200_v1`, Holm over m=26 declared before
the p-values were read:

- **ahead on the point estimate against 26 of 26**
- **separated from 8 of 26**
- against `anthropic_l`: delta **+0.0036** — one item in 280 — at **p = 1.0000**

So the defensible claim is: `qwen_m` is indistinguishable from the nine arms behind it and
better than the rest. Buying the $0.378 arm over the $0.003 arm purchases nothing this
data can detect.

## Why this example exists — the pair, not the example

| | AG News | DBpedia-14 |
| --- | --- | --- |
| classes | 4 | 14 |
| hosted field | 0.835 – 0.910 | 0.939 – 0.993 |
| fine-tuned ML | **beat all 24** (0.945) | **could not be run** |
| zero-shot NLI | 0.70 (2.8x chance) | 0.63 (8.8x chance) |
| rule baseline | 0.67 (2.7x chance) | 0.71 (9.9x chance) |
| pairs separated | 34 of 378 | 74 of 351 |
| licence | `unknown`, non-commercial | CC-BY-SA 3.0 + GFDL |

Same harness, same 24 hosted arms, same prompt discipline, same statistics. One task has
headroom and a winner; the other is saturated and has a group. **A single example would
have supported whichever conclusion it happened to produce.**

## Findings

**1. The seeded-random dev draw fixes what AG News found, and it is demonstrated.**
AG News drew the FIRST k per class: its `keyword` arm read 0.35 on dev and 0.67 on the
measurement slice — about 3 SD, a biased slice. DBpedia draws a seeded-random prefix of a
per-class permutation: `db_keyword` read 0.625 on dev and 0.707 on measurement. At n=56
with p≈0.7 the standard error is 0.061, so that is **1.3 SE** — ordinary sampling noise.
Same arm type, one design change, and the dev slice now predicts the measurement slice.

**2. Label noise is the same magnitude as the entire measured spread between models.**

```
Dukart's Canal            gold NaturalPlace   25/25 said MeanOfTransportation / Building
Bent County High School   gold Building       24/25 said EducationalInstitution
Bharhut                   gold Building       23/25 said NaturalPlace / Village
```

"Bent County High School ... is a historic school" is labelled `Building`, not
`EducationalInstitution`. The top ten arms are separated by four items in total; three
items are disputed by the whole field. **The noise floor and the signal are the same
size.** Any ranking among those ten arms is a ranking of which model best reproduces
DBpedia's ontology quirks.

This is what drove the correction to the AG News handover — the same diagnostic found the
same problem there, on a study already called finished.

**3. Fourteen CamelCase labels make the parser load-bearing.** On AG News one arm of 24
ever needed `_parse_label`. Here:

```
db_glm_l     +0.086   (24 of 280 items rescued; 10% of answers narrate)
db_gemma_s   +0.043   (12 items)
db_llama_s   +0.021
```

`glm_l` narrated on all three corpora now — summarisation, AG News, DBpedia — worth 7.5,
then 8.6, then 8.6 accuracy points. That is a property of the model reproduced across
three independent tasks, which no single example could claim.

**4. The first unparseable answers in either example.** `parsed` was 1.0 across every AG
News arm and every DBpedia dev arm. At n=280 with 14 labels, three arms produced one
unparseable answer each (`deepseek_m`, `deepseek_s`, `glm_s`), and `glm_s`'s was an EMPTY
response — `answer_words` 0.996. `parsed` is classified as **quality**, not descriptive,
on the argument that an arm which cannot be parsed cannot be deployed; this is the first
evidence that makes that more than a stance.

**5. The zero-shot handicap was predicted and is real.** `bart_mnli` is asked whether a
text entails "This text is about EducationalInstitution." — not English. It scores 0.6286
with mean confidence 0.317, against `bert_mini`'s 0.957 confidence on AG News. Written
into the config before the run; a natural-phrasing variant is the obvious second arm and
is NOT done, because mapping labels to nicer phrasings is a tuning decision that belongs
where it can be measured.

## What the harness gained

- **`examples/_shared/classification.py`** — the parser, scorers, five providers and the
  fingerprint shape. Abstracted on the SECOND use: a shared module with one caller is a
  guess about the future. AG News's adapter went 500 -> 120 lines; both now use it, and
  the refactor was proved behaviour-identical by recomputing all 5,600 stored AG News
  item-scores (max abs delta 0.000e+00).
- **`classification_report.py`: ITEMS THE FIELD MISSED** — items at least
  `--miss-threshold` (default 80%) of the LEARNED arms got wrong. It cost ~15 lines and
  revised a headline finding on a study already pushed to main.
- **`fetch.py` retry and rate limiting.** One transient 502 lost a whole 280-item draw;
  then HTTP 429 at offset 11 showed the limiter is on request RATE. 429 has its own
  backoff ladder, and the actual fix is a 0.35s inter-request pause (`--delay`). **The AG
  News fetcher has neither** and works only because 200 requests slip under the limit.

## Not done

- **No fine-tuned ML arm.** Every credible DBpedia-14 fine-tune on the Hub — fabriceyhc,
  Danni, kundank, TheChickenAgent — is `pytorch_model.bin` only; they predate safetensors
  becoming default. So this example's ML-vs-LLM comparison, the thing AG News answered,
  **cannot be run on x86_64 macOS at all.** See the blocked-arms branch.
- **No `macro_f1` significance test.** `family_test.py` cannot take it: macro-F1 has no
  per-item value, so the paired sign-flip test does not apply. That is a property of the
  statistic, not a missing feature. The right tool is a bootstrap over items — resample,
  recompute macro-F1 for both arms, read the distribution of the difference. NOT BUILT.
- ~~Calibration recorded and unanalysed.~~ **MEASURED** — see below. Still open: hosted
  arms have no `confidence` at all, because logprobs were never requested.
- No `rank_stability` at k=27. No README for the example. `research/REPORT.md` and
  `NOTES.md` carry none of this.
- Runs live on one machine and are gitignored. Nothing is backed up.

## Calibration

Measured across the three local arms that report a confidence:

```
ag_bert_mini    conf 0.957   acc 0.945   ECE 0.025    well calibrated
ag_bart_mnli    conf 0.572   acc 0.700   ECE 0.128    underconfident
db_bart_mnli    conf 0.317   acc 0.629   ECE 0.311    badly underconfident
```

The fine-tuned classifier is honest: overconfident by 1.2 points, and its 186 items above
0.8 were 96.2% correct while its 6 items below 0.6 were coin flips. **That is what makes a
cheap classifier deployable** — a reliable "I am not sure" you can route to something
dearer.

The zero-shot arm is systematically UNDER-confident, and worse as the label count grows
(ECE 0.128 at 4 classes, 0.311 at 14). On DBpedia its 0.4–0.6 bucket was **96.8% correct**
and its 0.6–0.8 bucket **100%**. Zero-shot NLI normalises entailment scores across the
candidate labels, so with 14 candidates the probability mass spreads thin however certain
the model is. The raw score is an excellent RANKING signal and is not a probability;
reading it as one would throw away most of the arm's usable accuracy.

Not turned into a script: choosing a confidence threshold and a routing policy is a
product decision, not a harness one.

## Reproducing

```bash
cd examples/classification-dbpedia-14 && uv sync --extra local
uv run fetch.py --n 280 && uv run fetch.py --n 56
cd ../../harness
PY=../examples/classification-dbpedia-14/.venv/bin/python
PYTHON=$PY make dataset-materialize DATASET_ID=dbpedia_280

$PY scripts/classification_report.py --dataset-id dbpedia_280
$PY scripts/family_test.py --dataset-id dbpedia_280 --a db_qwen_m_n200_v1 \
     --against _n200_v1 --metric correct
$PY scripts/holdout_significance.py --dataset-id dbpedia_280 \
     --exclude-dataset dbpedia_56 --metric correct
```

`uv sync --extra local` matters: provisioning with plain `uv sync` leaves the zero-shot
arm unable to load, which is how it failed here. The harness's warm-up guard caught it
before the loop and spent nothing, which is what that guard is for.

Total hosted spend for the 280-item sweep: roughly **$1.25**, dominated by `anthropic_l`
($0.378) and `anthropic_m` ($0.227) — the two arms the result says you do not need.
