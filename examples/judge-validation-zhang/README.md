# Zhang et al. 2024 as a rated dataset

A dataset source for [`evh judge-validate`](../../harness/docs/RUNBOOK.md#validating-a-judge-what-the-gate-needs): it
turns a published crowd rating of 19 summarisers into the rated shape the command reads, so a news-summary judge can be
measured against people on summaries by LLMs, fine-tunes and the reference highlights.

[Zhang, Ladhak, Durmus, Liang, McKeown & Hashimoto (2024)](https://aclanthology.org/2024.tacl-1.3/), "Benchmarking Large
Language Models for News Summarization" (TACL 12), released Likert ratings of 19 summarisers on 100 CNN/DailyMail
articles, three ratings per summary. The authors state no licence: cite the paper. The items are CNN/DailyMail articles,
so CNN/DailyMail's terms apply to them too.

## Use

```bash
evh dataset-create --dataset-id zhang2023_cnndm_v1 \
    --source examples/judge-validation-zhang/source.py:Source --query '{"answer": "ratings"}'
evh dataset-materialize --dataset-id zhang2023_cnndm_v1
evh reference-promote --dataset-id zhang2023_cnndm_v1 --labels answers --tier gold \
    --reason "three crowd ratings per summary" --by person:NAME
```

The download (31 MB) is pinned to the repository's commit and the file's sha256 and kept in the project's item cache.
`--query '{"file": "path/to/likert_evaluation_results.json"}'` reads a copy you already have, unpinned.

## What it writes

Each item is `{"source": the article, "outputs": [one summary per system, in the systems' name order]}` (19 outputs; one
system is the reference highlights; a summary a model left empty, 38 in the file, is kept as an empty output: a judge
should put it last). Its reference is `{"ratings": {dimension: [one number per
output]}, "raters": [three]}`.

The raters rated **coherence and relevance 1-5 and faithfulness 0/1**, not fluency. Naming the judge's dimension for a
human one is the source's: faithfulness stands for the judge's `consistency`, so the ratings carry **coherence,
consistency and relevance**, each the mean of the three ratings. A scorer whose `task.dimensions` also names `fluency`
(SummEval's default four) is validated on the three the ratings carry: the block records them
(`validation.dimensions`), nothing is averaged in for fluency, and the gate, `evh scorer-show` and the Workbench say
"fluency: not validated on" this dataset. The three ratings of a
summary are not three persons across summaries, so `raters` holds them in a seeded order and `human_tau` is one rating
against the mean of the other two, rotating.

## What it cannot say

Crowd ratings are noisier than experts'. The judge scores a block of at most `outputs_per_call` summaries (10 + 9 at
16) and the order inside a block is blinded and seeded, so a judge's tau also measures how it holds up across blocks
(`judge-score` does the same on a real eval).

Tested without the network by `test_zhang.py` (two articles in the download's own format).
