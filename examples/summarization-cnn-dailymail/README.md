# Summarising news, 24 models at once

One task — summarise a news article in 2–3 sentences — measured across 24 hosted models
from 8 vendors, on three axes at once: **quality, cost and wall-clock speed**.

It is a worked example for [`../../harness`](../../harness), and it is also a record
of what a small eval can and cannot tell you. Most of what is interesting here was found
by *disbelieving the first answer*: several headline findings in
[`research/internal/NOTES.md`](../../research/internal/NOTES.md) were retracted after the numbers were checked
properly, including one caused by a one-line bug in this example's own scorer.

> **Rerun this experiment** from the repository root — `EXP=summarization` / `EXP=summarization-dailymail`:
>
> ```bash
> make plan EXP=summarization  &&  make data EXP=summarization  &&  make reproduce EXP=summarization  &&  make compare EXP=summarization
> ```
>
> `LEVEL=hosted` adds the LLM arms with one `OPENROUTER_API_KEY`. What each level checks and
> what to expect: [`docs/REPRODUCE.md`](../../docs/REPRODUCE.md). The rest of this page is what
> those commands do underneath, and why.

---

## Get the data

**Nothing is committed.** CNN/DailyMail belongs to its publishers; this repo ships a
download recipe, never the text.

```bash
cd examples/summarization-cnn-dailymail
uv sync                       # provisions its own Python 3.11 and deps
uv run fetch.py --n 200       # the measurement slice, cnn_dailymail_200 (~5 seconds)
uv run fetch.py --n 20        # the dev slice, a strict prefix of the 200
```

That writes the articles into `../../harness/data/sources/cnn_dailymail_<n>/` and their
human-written highlights into `../../harness/data/references/gold/cnn_dailymail_<n>/`.
Both paths are gitignored.

**Why this dataset.** `abisee/cnn_dailymail` is Apache-2.0 — the only clearly-licensed
option among the usual summarisation benchmarks — and it is the most-cited baseline, so
published ROUGE numbers exist to sanity-check ours against. That is the point of using a
standard set rather than inventing data: somebody else's baseline is a check on your
instrument.

**Which articles.** `--n` takes the *first* n rows of the test split, and the split is
CNN-first, so `cnn_dailymail_200` is **all CNN** (196 with CNN's dateline, 4 partner pieces) while the split is
91% DailyMail. Every committed hosted-model result is therefore about CNN-style news. The
sanity check above is what shows it: LEAD-3 scores ROUGE-1 39.94 on the full test set
(published 40.34) but 30.20 on the CNN slice (`calibrate.py`,
`docs/evidence/calibration/summarization.json`). For a sample of the whole benchmark, draw
at random:

```bash
uv run fetch.py --n 200 --draw random --seed 20261014                    # both outlets
uv run fetch.py --n 200 --draw random --seed 20261014 --source dailymail \
    --dataset-id cnn_dailymail_dm200                                     # the DailyMail slice
```

**Why the references are gold.** `highlights` are written by the journalists who filed
the article. Human-authored, so `references/gold/`. Most evals never get this, which is
what makes the silver experiment below possible.

## Run it

```bash
cp ../../harness/.env.example ../../harness/.env      # OPENROUTER_API_KEY, or your proxy
cd ../../harness

make experiment-dry-run CONFIG=../summarization-cnn-dailymail/configs/arm_qwen_s_n200.yaml
make sweep CONFIGS="../summarization-cnn-dailymail/configs/arm_*_n200.yaml" REPEAT=1
make leaderboard DATASET_ID=cnn_dailymail_200
```

`arm_*_n200.yaml` matches all 29 arms on the 200-article slice, the five local ones included
(those need `uv sync --extra local`). A sweep refuses configs that do not share one
`dataset_id`, so the unsuffixed `arm_*.yaml` files (the 20-article dev slice) cannot be mixed in.

Dry-run first; it costs nothing and tells you what the sweep will. The committed result is
one pass per arm: 24 hosted arms × 200 articles = 4,800 calls, **$5.74 billed**. The
earlier 20-article pilot, three repeats, was 1,440 calls, $1.45 and 80 minutes; its runs are
not committed. Run scores are written at 10 decimals, so no `make rescore` step is needed
(`make rescore` exists for runs written at lower precision; `make leaderboard` warns when
it sees them).

Validating a change rather than measuring something? Use four cheap arms and a scratch
directory, so a smoke pass cannot add repeats to a real sweep's arms:

```bash
EVAL_RUNS_DIR=/tmp/smoke make sweep REPEAT=1 \
  CONFIGS="../summarization-cnn-dailymail/configs/arm_{qwen_s,glm_s,gemma_m,mistral_s}.yaml"
```

## What is held constant

Every arm shares the dataset, the prompt file, temperature 0, `max_tokens: 1200` and
`reasoning: {enabled: false}`. The hosted models run zero-shot on that one prompt. The
upstream **provider is not pinned**: OpenRouter routes each call, and 13 of the 24 hosted
arms were served by 2 to 14 providers within one run (`providers_seen` in each run's
`metrics.json`), so a hosted score is that mix's, as served.

All 24 hosted runs carry the same `adapter.sha256`. 23 of them also carry `harness.dirty: true`,
meaning the recorded commit does not identify the code that ran (the cause is the sweep's own
untracked configs, REPORT_SUMMARIZATION §1); the fingerprint stores content, not pointers.
Only the model varies — and the run fingerprint records all of it, so "we varied one thing"
is *checkable* rather than asserted.

The prompt lives in `prompt.txt`, is 119 bytes, and its sha256 is in every fingerprint:

> Summarise this news article in 2-3 short sentences, in the terse style of a news wire
> summary. Output only the summary.

This is **not** prompt optimisation. A per-model prompt would make the comparison
meaningless, so the same bytes go to every model and the record proves it.

**Reasoning is off everywhere.** Where a model's endpoint makes reasoning mandatory it is
excluded and replaced by the nearest same-family model that allows it — `claude-opus-5`
rather than 5.5, `glm-4.6` rather than 5.3-prime. Verified rather than assumed: every run
records `reasoning_tokens` from the provider's own accounting, and they are all zero.

## The arms

8 families × 3 **price tiers**. `price_tier`, not "size" — it is the vendor's own
small/mid/large product step, and every family mixes generations within it (qwen's
"large" is the *oldest* of its three). This experiment cannot attribute a difference
between tiers to model size, and no conclusion here does.

| | small | mid | large | weights |
|---|---|---|---|---|
| anthropic | haiku-4.5 | sonnet-5 | opus-5 | closed |
| openai | gpt-5.4-mini | gpt-5.5 | gpt-6-sol | closed |
| llama | 4-scout | 3.3-70b | 4-maverick | open |
| gemma | 3-27b | 4-26b-a4b | 4-31b | open |
| qwen | 3.8-flash | 3.7-plus | 3-max | open |
| deepseek | v4-flash | v4.1-flash | v4-pro | open |
| glm | 4.5-air | 4.6 | 5 | open |
| mistral | small-3.2 | medium-3.1 | large-2512 | open |

`model_provenance.json` records what each proxy alias resolved to, because a run's
fingerprint stores the upstream model and a gateway alias is not one.

## Quality, in two facets that disagree on purpose

ROUGE F1 against a single reference is a **length ranking wearing a quality costume**:
across the 24 hosted arms in the n=20 pilot, ρ(output words, precision) = −0.73 and
ρ(words, recall) = +0.81.
Choosing recall over F1 does not remove the bias, it flips it. So both ends are measured
deliberately:

- **`coverage`** — recall with the output clipped to *that item's* reference length. Every
  arm is judged on the same budget the human used, so writing more cannot buy coverage;
  only putting the important thing first can.
- **`concision`** — precision over the whole output. Padding is punished here exactly as
  raw recall rewards it.

ρ(coverage, concision) = **+0.36** — related but far from the same
ordering, which is the point of carrying both. Which one you want is a product decision the
eval refuses to make for you. `PRIMARY_METRIC = "coverage"`; pass `--sort concision` for the
other view.

**Neither is length-neutral, though `coverage` comes closest.** At n=200, ρ(words,
coverage) = +0.07 against ρ(words, rougeLsum) = −0.31 and ρ(words, concision) = −0.84. The
clip only binds above the reference length — **577 of 4,800 outputs (12.0%) are shorter
than the reference and are never clipped at all** — so "judged on the same budget" holds
for the verbose arms and not for the terse ones. Coverage earns its place by being the
interpretable question ("did the summary carry the story"), not by being bias-free.

`grounding` (share of summary bigrams present in the article) rides along as a third
facet: high means extractive and safe, low means abstractive — which is either a good
paraphrase or a fabrication, and this cannot tell them apart. Read it beside ROUGE, never
instead of it. It is not length-neutral either (ρ = +0.12).

**Format compliance is computed, not eyeballed** — `fmt_narration`, `fmt_label`,
`fmt_markdown`, `fmt_bullets`, `fmt_paragraphs`, `fmt_overlong`, on every output. This
exists because five outputs were once read by hand and declared clean; computing it over
all of them finds **262 of 4,800 (5.5%)** hit at least one flag — including outputs where a
model wrote its reasoning out in the open.

## What 200 articles showed

All on the committed slice — which is **CNN's articles only** (see *Get the data*). A
DailyMail slice (`cnn_dailymail_dm200`) re-ran the five local arms: every comparison
among them held, the XSum control is still last, and the hosted arms were not re-run
([report §3.7](../../research/REPORT_SUMMARIZATION.md#37-does-it-hold-outside-cnn-the-dailymail-slice)).

- **Which article you drew matters ~68× more than which model wrote the summary.** Of the
  variance in `coverage`, **67.8% is between articles and 1.0% between arms.** This is why
  the comparison is paired — ranking arms *within* each article removes the article term.
- **Temperature 0 is not deterministic.** In the earlier three-repeat sweep (n=20), only
  **9.8%** of outputs were byte-identical across repeats and **12 of 24 arms produced zero
  identical outputs**.
- **Price did not buy quality here, as run.** Across the 24 hosted arms price and `coverage`
  were uncorrelated (r = −0.07, 95% CI −0.46 to +0.34): at n = 24 that does not exclude a
  moderate effect. The dearest arm (`anthropic_l`, **$1.9652** billed) costs **143×** the
  cheapest paid arm (`deepseek_s`, $0.0137), ranks **18th of 29** on coverage (15th of the 24
  hosted) and is separated below the best paid arm. The Pareto frontier keeps **8 of 24**
  hosted arms; the other 16 are dominated on the point estimates — behind another arm on
  quality *and* cost *and* speed — and for three of them (`llama_l`, `mistral_s`, `gemma_l`)
  the dominator's quality lead is not separated, so the case is a 2%–30% cost difference.
- **A model-authored reference is biased, not just noisy.** See below.

**Few specific comparisons survive.** At n=200, **34 of 276** hosted pairs separate on
`coverage` after correcting for 276 comparisons (1 of 276 at n=20). The top six cannot be
separated, and a leaderboard that printed a confident 1-to-24 ordering from this data
would be overstating it.

**Beware the metric that separates most.** Ranked by pairs distinguished —
`summary_words` 208, `grounding` 172, `concision` 146, `rouge1` 97, `rougeLsum` 95,
`coverage` 34 — the order is almost exactly how much each measure depends on output
length. A facet that resolves many pairs is not thereby the more informative one.

## Can you trust a model-written reference?

Usually there is no gold, so a strong model writes the references — "silver" — and you
rank candidates against those. Here gold exists, so the proxy can be *measured*, at n=200 from
the stored outputs (REPORT_SUMMARIZATION §3.5):

```bash
evh silver-calibrate --dataset-id cnn_dailymail_200 --ref-match _n200_v1 --arm-match _n200_v1
```

It costs nothing: "author silver with model X using the same prompt and settings as the
arms" is exactly what X already produced, so all 29 arms are tried as authors.

```
silver agreement with gold, the 24 hosted models:   -0.059 .. +0.378, mean +0.163
sibling lift, the 24 hosted models:   +10.4 rank positions, positive for 24 of 24
```

There is no retest ceiling at n=200: each arm ran once, and a ceiling needs two run sets (the
n=20 pilot's was ρ 0.924, its mean agreement 0.326).

The second line is the finding. **A silver author promotes models of its own family**, and
excluding the author's own row does not remove it — the circularity is not a judge scoring
*itself*, it is a judge rewarding its own kind's style. A silver-ranked leaderboard is not
merely noisier than a gold one; it is wrong in a direction you can predict from who wrote
the references.

Two caveats on that number, because a single mean hides them:

- **The lift is worst where the author is worst.** ρ(author agreement, sibling lift) =
  −0.74: the three authors above ρ 0.5 average **+2.2** positions, the 21 below ρ 0.3 average
  **+10.0**.
- **Family and output length are entangled** — models of a family write similar amounts —
  so part of this is length preference rather than "style". Not fully separated here.

And the part that matters outside this example: **the best authors are not LLMs.** The
extractive `lead3` (ρ 0.719) and the local BART models (0.58–0.61) make better silver than
any hosted model; the best of those is `llama_l` (0.378), the worst `qwen_s` (−0.059). In the
case silver is actually *for*, no gold exists, so you cannot check which author you got.

The frontier arm's silver is kept as `silver/cnn_dailymail_200`, by `anthropic_l` (ρ 0.327,
lift +12.5). Its texts quote the articles, so only its manifest is committed; it names the
command that rebuilds them from the run:

```bash
evh reference-create --dataset-id cnn_dailymail_200 --from-run cnn_anthropic_l_n200_v1_20260926T063645Z --tier silver --not-redistributed
```

## Files

| | |
|---|---|
| `fetch.py` | download recipe — stdlib only, writes sources + gold |
| `prompt.txt` | the one prompt, shared by every arm, hashed into every fingerprint |
| `adapter.py` | the integration seam: `call_system`, `score`, `warmup`, `fingerprint` |
| `configs/arm_*_n200.yaml` | the 29 arms on the 200-article slice (24 hosted, 5 local); among the hosted, only `model` and the price fields differ |
| `configs/arm_*.yaml` | the 20-article dev slice: 24 hosted arms plus `bart_l` and `lead3` |
| `configs/arm_*_dm200.yaml` | the DailyMail slice: five local arms, which were run, and four hosted (`deepseek_m`, `llama_l`, `llama_m`, `llama_s`), which were not |
| `model_provenance.json` | what each proxy alias resolved to upstream |
| `reference/` | configs for authoring a reference tier, and when not to |
| `pyproject.toml`, `uv.lock` | isolated environment; `uv sync` provisions its own Python |

## Not covered

- **Zero-shot, one prompt, unpinned providers, one run per arm.** The hosted arms were not
  tried few-shot, with a different prompt or with reasoning on, were served by whichever
  providers OpenRouter chose, and ran once each. CNN/DailyMail is public and
  contamination was not measured.
- **200 articles, not a large sample.** The dev slice is 20; every number above is n=200
  unless it says n=20. At 200 articles 34 of 276 hosted pairs separate and the top six do
  not.
- **One reference per article.** ROUGE against a single human summary is a weak proxy; two
  valid summaries can share few n-grams.
- **`grounding` is ours**, ~20 lines, not a standard metric and not comparable to any
  published number.
- **Speed is machine-bound.** The latency column mixes this machine, the proxy and the
  upstream provider. It is a property of your setup, not of the model — which is
  deliberate: the same experiment measures how fast *your* machine is at *this* task.
  The local arms were recorded on two machines (a 12-core Mac and a 4-core Linux box that
  ran `bart_l` 1.7× faster); `harness/data/runs-linux/` re-times all five on one.
- **Local arms.** `bart_l` (BART fine-tuned on this corpus, 1.6 GB) is not separated from
  the best hosted arm (gap 0.0001, p = 0.99). `lead3` ran too. Three more local arms need
  torch ≥ 2.6: two distillations, `bart_m` 0.3367 (not separated from `bart_l`) and
  `bart_s` 0.3276 (not separated in the 28-arm family; separated in the five-arm family of
  the report's §3.7 and on DailyMail); and `bart_l_xsum` — the same architecture trained
  on XSum, with different decode settings — last of 29 on `coverage` at 0.2071, below
  `lead3`. No hosted arm was run on DailyMail.
