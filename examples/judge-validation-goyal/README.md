# Goyal et al. 2022 as a rated dataset

A dataset source for [`evh judge-validate`](../../harness/docs/RUNBOOK.md#validating-a-judge-what-the-gate-needs): it
turns a published human evaluation of news summaries into the rated shape the command reads, so a news-summary judge
can be measured against people on summaries written by modern models.

[Goyal, Li & Durrett (2022)](https://arxiv.org/abs/2209.12356), "News Summarization and Evaluation in the Era of
GPT-3", released, for 100 CNN articles of 2022, summaries by GPT-3 (text-davinci-002), BRIO (a BART fine-tune) and T0,
each set ranked best and worst by three annotators. The data is CC BY 4.0 (the archive's `LICENSE.txt`): attribute the
authors. Its items are CNN articles, so CNN/DailyMail's terms apply to them too.

## Use

From the project's directory, with the harness installed (the source is this one file; `--source` takes its path):

```bash
evh dataset-create --dataset-id goyal2022_cnn_v1 \
    --source examples/judge-validation-goyal/source.py:Source --query '{"answer": "ratings"}'
evh dataset-materialize --dataset-id goyal2022_cnn_v1
evh reference-promote --dataset-id goyal2022_cnn_v1 --labels answers --tier gold \
    --reason "three annotators ranked each article's summaries" --by person:NAME
evh judge-validate --scorer my-judge-v1 --dataset goyal2022_cnn_v1 --dry-run
```

The download (327 KB) is pinned by its sha256 and kept in the project's item cache; the source reads the same bytes
on every machine. `--query '{"file": "path/to/human_annotations.zip"}'` reads a copy you already have, unpinned.

## What it writes

Each item is `{"source": the article, "outputs": [GPT-3's, BRIO's, T0's summary]}`. Its reference is
`{"ratings": {dimension: [one number per output]}, "raters": [one per annotator]}`.

The annotators gave **one overall preference**, not a score per dimension, so mapping it to the judge's dimensions is
the source's: a summary named best is 2, one named in neither list 1, one named worst 0; each annotator's ranks stand
for every dimension of the scorer (the query's `dimensions`, default SummEval's four: coherence, consistency, fluency,
relevance), and `ratings` is their mean over the three. The judge's per-dimension tau against the same ranks is then
how well it orders the three summaries as people prefer them. `human_tau` beside it is one annotator against the other
two. Three summaries per item is little to order: a judge's tau over 100 articles is noisy, and the figure is read
against the people's own, not against 1.

## What it cannot say

The three systems are GPT-3, BRIO and T0 only: a judge that orders them as people do may still not order other models'
summaries so. An annotator's best-or-worst is an overall preference; the judge scores four named dimensions and the
source gives it the same ranks on each. The articles are CNN's, from 2022.

Tested without the network by `test_goyal.py` (a two-article archive in the download's own format).
