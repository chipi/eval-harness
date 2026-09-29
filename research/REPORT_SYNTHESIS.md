# What five experiments agree on

**Five tasks · four metric shapes · 127 measured arms · $12.01 billed · one harness**

A cross-cutting report. Each of the four underlying reports answers *"which model is best
at this task"*; this one asks what is true in **all** of them, and it is written because
several findings only became visible once there were five corpora to compare.

| | task | metric shape | report |
|---|---|---|---|
| CNN/DailyMail | summarise a news article | continuous (ROUGE) | [REPORT_SUMMARIZATION](REPORT_SUMMARIZATION.md) |
| AG News | 4-way topic label | binary per item | [REPORT_CLASSIFICATION](REPORT_CLASSIFICATION.md) |
| DBpedia-14 | 14-way ontology label | binary, **saturated** | [REPORT_CLASSIFICATION](REPORT_CLASSIFICATION.md) |
| Few-NERD | entities + types | set vs set | [REPORT_NER](REPORT_NER.md) |
| SciFact | retrieve from 5,183 docs | ranked list | [REPORT_RETRIEVAL](REPORT_RETRIEVAL.md) |

Every number below is computed from the stored runs, not quoted from the reports.
Reproduction commands are in §8.

---

## The seven findings

### 1. The dearest arm is never first. Five times out of five.

| experiment | dearest paid arm | cost | its rank |
|---|---|---|---|
| summarisation | `anthropic_l` | $1.9652 | **16 of 25** |
| AG News | `anthropic_l` | $0.1750 | 3 of 26 |
| DBpedia | `anthropic_l` | $0.3784 | 2 of 25 |
| Few-NERD | `anthropic_l` | $0.6897 | 3 of 25 |
| SciFact | `glm_m` | $0.4576 | 2 of 17 |

**But the naive version of this claim is false, and worth killing.** "Price buys nothing"
is not supported: the dearest arm beats the *cheapest* arm in 4 of 5 experiments. Price is
weakly informative across the whole field and uninformative at the top — the money
separates bad from mediocre, then stops.

The practical form: **paying the most is never the optimum, and paying the least is
usually not either.** Among paid arms the best was a *mid*-tier model in four of five
experiments and a *small*-tier one in the fifth — the large tier never won anything here.

### 2. The top of a leaderboard is a group, not a podium

Every winner leads on the point estimate against **100%** of its declared family. How many
it actually *separates* from, under Holm step-down at α = 0.05:

| experiment | winner | ahead of | separated from | |
|---|---|---|---|---|
| Few-NERD | `span_marker` | 26 of 26 | **26 of 26** (100%) | a real podium |
| AG News | `bert_mini` | 27 of 27 | 18 of 27 (67%) | a group of 9 |
| summarisation | `bart_l` | 25 of 25 | 12 of 25 (48%) | a group of 13 |
| SciFact | `glm_s` | 18 of 18 | 6 of 18 (33%) | a group of 12 |
| DBpedia | `qwen_m` | 26 of 26 | 8 of 26 (31%) | a group of 18 |

**Four of five leaderboards have a top group the data cannot order.** Reading rank 1 as
"the best model" would have been wrong four times. The gap between "ahead of everything"
and "distinguishable from a third of it" is the single most repeated result here.

### 3. A free local model wins or ties, whenever one can run at all

| experiment | best free arm | rank | margin over the best **paid** arm |
|---|---|---|---|
| Few-NERD | `span_marker`, 476 MB | **1 of 25** | +0.0810 over `openai_m` |
| AG News | `bert_mini`, 44 MB | **1 of 26** | +0.0350 over `anthropic_m` |
| summarisation | `bart_l`, 1.6 GB | **1 of 25** | **+0.0001** over `deepseek_m` |
| SciFact | `e5_base`, 438 MB | 9 of 17 | −0.0246 vs `glm_s`, **not separated** |
| DBpedia | `bart_mnli` (zero-shot) | 25 of 25 | −0.3643 |

Read the third row before the first two. **`bart_l` "wins" summarisation by 0.0001** — it
is first on the leaderboard and tied with a hosted model in every sense that matters. An
earlier draft of this table reported +0.0176 there, because it compared against
`anthropic_l` rather than against the best paid arm; the corrected number turns an
apparent win into the winner's-curse case of §4.

So: two clear wins, two ties, one loss — and the loss is the one arm **not trained for its
task** (zero-shot NLI), because DBpedia's fine-tuned checkpoint could not be loaded. The
pattern is narrower and stronger than "small models win":

> **A small model fine-tuned on your task beats every frontier LLM at that task, for $0.**
> A small model *not* trained on your task loses to all of them.

Few-NERD isolates this with a matched pair — `span_marker` and `gliner` are the same model
class differing only in exposure to the training split — and the difference is **+0.3134
F1**.

**And the optimum was a mid-tier arm in four of five experiments** (`_m_` in
summarisation, AG News, DBpedia and Few-NERD; `_s_` in SciFact). Not once was it the large
tier.

**The caveat the NER report insists on:** 57% of `span_marker`'s margin comes from one
entity type whose meaning exists only inside that corpus, and 38% of its lead survives only
because it agrees with annotation the rest of the field rejects. Fine-tuned models partly
learn *your conventions*, which is exactly what you want in production and is not the same
as being right.

### 4. A pilot correlates beautifully and picks the wrong winner

Every experiment ran a small dev slice before the full one. Comparing the two:

| experiment | ρ(dev, full) | dev leader | true leader | dev leader's real rank |
|---|---|---|---|---|
| Few-NERD | 0.895 | `span_marker` | `span_marker` | 1 of 27 ✓ |
| AG News | 0.852 | `anthropic_l` | `bert_mini` | 3 of 28 |
| SciFact | 0.756 | `llama_s` | `glm_s` | **10 of 19** |
| DBpedia | 0.728 | `anthropic_l` | `qwen_m` | 2 of 27 |
| summarisation | 0.722 | `bart_l` | `bart_l` | 1 of 26 ✓ |

**ρ between 0.72 and 0.90 in every case — and the pilot picked the wrong winner in three of
five.** On SciFact it picked the tenth-best of nineteen.

This is the most transferable finding in the repo, because ρ is the number people quote to
justify a pilot and it is **the wrong number for the decision being made**. A high rank
correlation says the *ordering* is broadly preserved. Selecting one arm depends on the
ordering at the very top, which is where the noise concentrates and where the field is
tied (§2).

Related, from the summarisation study: BART's lead over the best LLM was **0.0737 at n=20**
and **0.00008 at n=200** — a 900× shrink. Same arms, same metric, more data.

### 5. The gold is wrong, in every corpus that was checked

| corpus | gold errors found | method |
|---|---|---|
| Few-NERD | **34 of 768** gold types (4.4%) unanimously rejected by all 25 learned arms | consensus pass |
| DBpedia | 3 items disputed by the entire field; the top ten arms are separated by four items | consensus pass |
| AG News | systematic label noise; revised a published finding | consensus pass |
| CNN/DailyMail | **not checked** | — |
| SciFact | **not checked** (qrels incompleteness unmeasured) | — |

Three for three where anyone looked. The honest statement is not "60% of corpora have
noisy gold" — it is **every corpus we examined had it, and two were never examined.**

On a saturated benchmark this stops being a footnote and becomes the ceiling: DBpedia's top
ten arms are separated by four items, and three of those are items the whole field disputes
because the label is wrong. **The measurement was resolving annotation, not capability.**

The diagnostic is cheap and general: items nearly every *learned* arm gets wrong are items
whose gold is probably wrong. Independent models do not agree on a mistake.

### 6. The instrument was broken before the models got interesting — every time

Defects found **by** running the experiments, each of which changed published numbers or
would have:

| experiment | defect | cost if unfound |
|---|---|---|
| summarisation | scorer bug surviving two sweeps | drove `rescore.py` into existence |
| AG News | duplicate-run check flagged honest ties as copies | 4 false alarms in one sweep |
| AG News | the **label parser** is worth **8.6 accuracy points** to one arm | wider than most of the field's spread |
| Few-NERD | an unreadable answer scored **1.0** on empty-gold items | +0.0214 f1 to one arm |
| Few-NERD | `normalizer_sha256` covered the normaliser, not the scorer | a scorer change was invisible in the fingerprint |
| SciFact | the adapter never disabled reasoning, unlike the other three | one arm went **0.6124 → 0.6991** once fixed |
| all | cost computed from a price table, not what was billed | wrong per arm by 0.67×–3.21× |
| all | Spearman had no tie correction; ranks broke ties **alphabetically** | ρ measured the alphabet on saturated tasks |

Three of these — the parser, the unparsed-as-empty rule, the reasoning flag — moved a
single arm by **more than the gap separating most of the field**. So:

> **The scoring code is a model-sized lever.** Changing how you parse an answer can matter
> more than changing which model produced it.

This is why every run fingerprints `parser_sha256`, `scorer_sha256` and `normalizer_sha256`,
and why `rescore.py` exists: recomputing every score from stored outputs costs $0, so
checking a scorer is never the expensive option.

### 7. The metric's shape decides which diagnostics can be read at all

Not which model wins — which *tools* work.

| shape | ties? | consequence |
|---|---|---|
| continuous (ROUGE, nDCG) | ~never | rank correlation is meaningful; duplicate-detection by mean is safe |
| binary per item (accuracy) | constantly | two different models report identical means; ρ degenerates |
| set (F1 per item) | rarely | per-item F1 is legitimate, so permutation tests work directly |
| ranked list (nDCG) | rarely | but **corpus ≠ items**, which breaks fingerprinting |

Concretely: on DBpedia at n=10, **19.8 of 27 arms tied**, so the rank statistic was
correlating *arm names*. Requiring a unique winner, **400 of 400 resampling draws are
undecided at every size tested** — that corpus has no winner to agree about, and every
earlier stability figure for it was an artifact of alphabetical tie-breaking.

The same tool on Few-NERD reports `arms tied 1st = 1.0` at every size and is perfectly
readable. **The tool was never wrong in general; it was wrong for a metric shape.**

---

## What this means if you are choosing a model

1. **Do not buy the most expensive arm.** It was never the best, in five for five.
2. **Do not read rank 1 as the winner** without a separation test. Four of five top spots
   are ties, and "ahead on the average" was true of the leader in 100% of cases while
   meaning almost nothing.
3. **If you can label a few thousand examples, fine-tune a small model.** It won outright
   in three of five, and tied in a fourth, at $0 and CPU latency.
4. **Do not select on a pilot.** ρ ≈ 0.8 feels like enough and picked the wrong winner
   three times in five. Use the pilot to catch instrument bugs, which is what it is
   genuinely good for.
5. **Read the items your whole field gets wrong before you read the ranking.** On a
   saturated benchmark that is where the ceiling is.
6. **Budget attention for the scorer, not just the model.** Three separate scoring bugs
   here moved an arm further than most model swaps did.

## What this cannot say

- **Five tasks, all English, all text.** No multilingual, multimodal, long-context,
  agentic or generative-quality task. The tie-at-the-top result may be a property of
  *saturated-ish academic benchmarks* rather than of frontier models.
- **One pass per arm, temperature 0.** Every interval here is over *items*, never over
  *runs*. Run-to-run variance is real and unmeasured — two runs of an identical SciFact
  config scored 0.6691 and 0.6617, because OpenRouter routes across providers.
- **24 hosted arms, one snapshot in time, no verifiable identity.** A provider can change
  weights behind an alias; runs record `identity_declared: true`, not proof.
- **Five of the 24 arms never ran on SciFact** (the frontier tier, $31.40 against that
  sweep's $2.45), so §1 and §2 are weaker there than elsewhere. One NER arm and several
  local ML arms are also unrun — see the handovers in this directory.
- **Nothing here measures factual accuracy, safety, or instruction-following.** ROUGE is
  n-gram overlap; accuracy is label match. A confident, fluent, wrong answer scores well on
  several of these metrics, and the reports say so individually.
- **§5 is three corpora, not five.** Two were never checked for gold errors, and their
  absence from the table is a gap, not a clean bill.

---

## Reproduction

```bash
cd harness
# §1, §3 — cost and rank by experiment, from what the provider billed
python scripts/leaderboard.py --dataset-id few_nerd_280        # and the other four
# §2 — separation
python scripts/family_test.py --dataset-id few_nerd_280 \
    --a fn_span_marker_n200_v1 --against _n200_v1 --metric f1
# §4 — pilot vs full, and holdout
python scripts/holdout_significance.py --dataset-id few_nerd_280 \
    --exclude-dataset few_nerd_56 --metric f1 --match fn_
# §5 — gold errors
python scripts/extraction_report.py --dataset-id few_nerd_280 --match fn_
python scripts/classification_report.py --dataset-id dbpedia_280
# §7 — tie behaviour by metric shape
python scripts/rank_stability.py --dataset-id dbpedia_280 --metric correct --match db_
```

Terms, models, datasets and tests are defined in
[`../docs/REFERENCE.md`](../docs/REFERENCE.md). The append-only journal of how each finding
arrived — including the ones that were retracted — is [`NOTES.md`](NOTES.md), 56 entries.
