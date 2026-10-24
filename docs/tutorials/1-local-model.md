# Tutorial 1 · A local model against a baseline

[Getting started](../GUIDE.md) used the harness's stand-in systems. This tutorial measures a
real one: a small summarisation model that runs on a CPU, against a baseline that uses no model
at all, on items of your own. The question it answers is the first one worth asking about any
model: **does it beat doing nothing clever?** The loop is the same; what is new is your own
`adapter.py`, the file that hands your system to the harness.

It follows the newcomer scenario this release was tried on: one-sentence summaries of short
local-news briefs. Your items can be anything text-shaped. Nothing here is run by
`make guide-check`: it needs the model's libraries, which are your system's, not the harness's.

## 0. A project of your own

<!-- guide-check: skip -->
```bash
mkdir briefs-evals && cd briefs-evals && git init -q
python3 -m venv .venv && . .venv/bin/activate
pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.4.0#subdirectory=harness"
evh init
# your system's own libraries: a CPU build of torch, the model's, and the metric's
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers sentencepiece rouge-score
```

## 1. Items, and gold if you have it

Put one item per file under `data/sources/briefs/`, and, if a person has written the answer for
each, one `<item_id>.txt` per item under `data/references/gold/briefs_v1/` (the item id is the
file name without `.txt`). Twenty items is enough to learn something; write them yourself if
nothing can be fetched or licensed. No gold yet?
[Tutorial 3](3-frontier-reference-and-judging.md) makes silver from a frontier model's run.

<!-- guide-check: skip -->
```bash
evh dataset-create --dataset-id briefs_v1 --source-dir data/sources/briefs --glob "*.txt"
evh dataset-materialize --dataset-id briefs_v1
```

## 2. Your adapter

`adapter.py` at the project root is the integration seam: an arm whose config names no
`adapter:` uses it. Two functions: `call_system` runs your system on one item, `score` says how
good one output is. This one has a **baseline** that uses no model (the brief's first sentence)
and a seq2seq model through `transformers`; the hosted providers bundled with the harness are
imported too, for [tutorial 2](2-hosted-llm.md).

```python
# adapter.py
from __future__ import annotations

from functools import lru_cache
from typing import Any

from evaluation_harness.adapter import PROVIDERS, Result

PRIMARY_METRIC = "rouge_l"
METRIC_DESCRIPTIONS = {
    "rouge_l": "ROUGE-L F1 (stemmed) against the reference.",
    "rouge_1": "ROUGE-1 F1 (stemmed) against the reference: shared single words.",
    "output_words": "How many words the summary has.",
}


def _lead(text: str, params: dict[str, Any]) -> Result:
    return Result(output=text.strip().split(". ")[0].rstrip(".") + ".", cost_usd=0.0)


@lru_cache(maxsize=2)
def _model(name: str):
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    return AutoTokenizer.from_pretrained(name), AutoModelForSeq2SeqLM.from_pretrained(name).eval()


def _hf(text: str, params: dict[str, Any]) -> Result:
    import torch

    tok, model = _model(params["model"])
    enc = tok(params.get("prefix", "") + text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        ids = model.generate(**enc, max_new_tokens=int(params.get("max_new_tokens", 48)),
                             num_beams=int(params.get("num_beams", 4)), do_sample=False)
    return Result(output=tok.decode(ids[0], skip_special_tokens=True).strip(),
                  tokens_in=int(enc["input_ids"].shape[1]), tokens_out=int(ids.shape[1]),
                  cost_usd=0.0)


def warmup(params: dict[str, Any]) -> None:
    """Load the model before the first item, so loading is not timed as the first call."""
    if params.get("provider") == "hf":
        _model(params["model"])


def call_system(text: str, params: dict[str, Any]) -> Result:
    provider = params["provider"]
    if provider == "lead":
        return _lead(text, params)
    if provider == "hf":
        return _hf(text, params)
    hosted = PROVIDERS[provider]                  # echo, openai, openrouter, anthropic, litellm
    return hosted(text, params)


def score(output: str, reference: str | None) -> dict[str, float]:
    words = float(len(output.split()))
    if reference is None:
        return {"output_words": words}
    from rouge_score import rouge_scorer

    s = rouge_scorer.RougeScorer(["rouge1", "rougeL"], use_stemmer=True).score(reference, output)
    return {"output_words": words, "rouge_1": s["rouge1"].fmeasure, "rouge_l": s["rougeL"].fmeasure}
```

`score` is called with `reference=None` when there is no reference yet, so the same adapter works
before and after you have one. Do not round the scores: the paired tests read ties, and rounding
makes some. `PRIMARY_METRIC` is the metric that decides; `METRIC_DESCRIPTIONS` show on the
catalog's metrics page. The harness times every call (`latency_ms`); `warmup(params)`, optional,
runs once before the first item so a model's loading time is not counted as the first call's.
The whole contract, and how to wrap a system that is not a Python function:
[INTEGRATION](../../harness/docs/INTEGRATION.md).

## 3. The arms

```yaml
# data/configs/briefs_lead1.yaml: the baseline, no model
config_id: briefs_lead1_v1
dataset_id: briefs_v1
params:
  provider: lead
```

```yaml
# data/configs/briefs_t5_small.yaml
config_id: briefs_t5_small_v1
dataset_id: briefs_v1
params:
  provider: hf
  model: t5-small
  prefix: "summarize: "
```

```yaml
# data/configs/briefs_flan_t5_small.yaml
config_id: briefs_flan_t5_small_v1
dataset_id: briefs_v1
params:
  provider: hf
  model: google/flan-t5-small
  prefix: "Summarize in one sentence: "
```

Add a goal (`data/goals/brief_summary.yaml`, the shape of the tutorial kit's
`tutorial/goals/tickets_summary.yaml`, with `rouge_l` as its measure) and name it in each config
(`goal: brief_summary`): it says what the summaries are for, and the catalog's goal page leads
with its answer.

## 4. Measure

<!-- guide-check: skip -->
```bash
git add -A && git commit -qm "briefs_v1: dataset, gold, adapter, arms"
evh experiment-run --config data/configs/briefs_lead1.yaml
evh experiment-run --config data/configs/briefs_t5_small.yaml --repeat 3
evh experiment-run --config data/configs/briefs_flan_t5_small.yaml --repeat 3
evh leaderboard --dataset-id briefs_v1
```

Without sampling (`do_sample=False`) a local model on one machine usually gives the same output
every time; the three repeats check that instead of assuming it (a `rouge_l` spread of 0 means
every delta is real). Its `latency_ms` has a spread, and depends on the machine:
set `EVAL_HOST_LABEL` in `.env` to name the machine, so latency is compared only where it was
measured alike (the inspector warns when it is not).

## 5. Compare, and choose

You named the question before you looked: does the model beat the baseline?

<!-- guide-check: skip -->
```bash
evh pair-test --dataset-id briefs_v1 --a briefs_flan_t5_small_v1 --b briefs_lead1_v1
evh family-test --dataset-id briefs_v1 --a briefs_flan_t5_small_v1 --against briefs_
evh run-promote --run <run_id> --reason "<what the tests showed, and what it costs>"
```

`pair-test` is for the one pair you named in advance; once you are choosing the best of several,
`family-test` corrects for every comparison you could have made. The leading sentence of a news
brief is a strong baseline: in the scenario, on twenty briefs, the first sentence was not
separated from the leading hosted LLM, and both small models were separated below that LLM. Find
out which holds on your items before paying for a model.

Next: [tutorial 2](2-hosted-llm.md) adds a hosted LLM to the same comparison, and
[tutorial 5](5-catalog-and-inspector.md) browses it.
