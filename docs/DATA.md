# Data and licences

What of each dataset is in this repository, what you download yourself, the licence that
governs it, and what that asks of you. The harness code is MIT; the data is not ours to
relicense, and nothing here grants rights the original licence does not.

*This is a plain-language summary to help you comply, not legal advice. The licence on
each dataset's own page is what binds.*

## The short version

| | in this repository | you download |
|---|---|---|
| **The corpora** (articles, snippets, abstracts, sentences) | **no** | yes, with each example's `fetch.py`, from the public source |
| **Gold and silver references** for the six experiments | **no** | rebuilt by `fetch.py`, byte for byte (seeded) |
| **Run outputs** (`outputs/`, `predictions.jsonl`) | **yes**: what each system produced, and its scores | — |
| **Scores, costs, fingerprints** (`metrics.json`) | yes | — |
| **Demo and tutorial data** (`harness/data/sources`, `harness/tutorial/`) | yes: synthetic or invented, written for this repository | — |

A dataset's identity travels as a hash (`items_sha256`, `corpus_sha256`), not as its
bytes, so you can prove you have the same items without anyone redistributing them.

## What the committed run outputs contain

Run outputs are committed so every number can be recomputed for $0. They are derived from
the datasets, so each one's licence follows its data:

| experiment | what an output is | contains dataset text? | governed by |
|---|---|---|---|
| **Summarisation · CNN/DM** | a summary of one article | **yes.** The lead-3 baseline's output *is* each article's first three sentences, verbatim, and other systems' summaries may quote sentences from the article | CNN/DailyMail: **Apache-2.0** |
| **Classification · AG News** | one topic label | no: a class word | AG News terms (see below) |
| **Classification · DBpedia** | one ontology label | no: a class word | CC-BY-SA 3.0 + GFDL |
| **Extraction · Few-NERD** | a list of entity spans and types | short spans (names, places) quoted from the sentences | **CC BY-SA 4.0** |
| **Retrieval · SciFact** | a ranked list of document ids | no: numeric ids | CC BY-SA 4.0 |
| **Judging · SummEval** | 64 scores (16 summaries × 4 dimensions), as JSON | no: numbers | MIT (SummEval); the articles are CNN/DailyMail, Apache-2.0 |
| **Re-measurement · judging sets** (`judging-sets/`) | which arms' outputs go in which block, in which order | no: item ids, run ids and sha256 hashes | the experiment's dataset |
| **Re-measurement · verdicts** (`judge-verdicts/`) | each judge's reply, its scores per output, and hashes | no: a reply is committed only as bare JSON scores; one that is not, or that repeats 8 consecutive words of the article or an output, is kept as its hash (validate V12 checks every one) | the experiment's dataset: CNN/DailyMail, Apache-2.0 |
| **Judge validation** (`judge-validation/`) | each judge's reply on a published human-rated set, its scores and hashes, and `report.json` | no: the same rule as the verdicts | the rated set's terms (below) |

## Each dataset

| dataset | licence | what it asks of you |
|---|---|---|
| [CNN/DailyMail](https://huggingface.co/datasets/abisee/cnn_dailymail) | Apache-2.0 | Keep the attribution and licence notice when you redistribute it or text from it. The articles themselves are CNN's and the Daily Mail's journalism. |
| [AG News](https://huggingface.co/datasets/fancyzhx/ag_news) | **`unknown`** on the card; its description says non-commercial research use | Treat it as **non-commercial research only**. If you are evaluating a commercial product, use a different corpus for anything you ship or publish. |
| [DBpedia-14](https://huggingface.co/datasets/fancyzhx/dbpedia_14) | CC-BY-SA 3.0 + GFDL, inherited from Wikipedia | Attribute Wikipedia/DBpedia; anything you redistribute that contains its text is share-alike. |
| [Few-NERD](https://huggingface.co/datasets/DFKI-SLT/few-nerd) | CC BY-SA 4.0 | Attribute the authors; derived text you redistribute is share-alike (CC BY-SA 4.0). |
| [BEIR SciFact](https://huggingface.co/datasets/BeIR/scifact) | CC BY-SA 4.0 | The same: attribute, and share-alike for redistributed text. |
| [SummEval](https://huggingface.co/datasets/mteb/summeval) | MIT ([original repo](https://github.com/Yale-LILY/SummEval) also MIT) | Keep the MIT notice when you redistribute the annotations. Each item also carries a CNN/DailyMail article and its human references, so those follow CNN/DailyMail's terms. |
| [UniEval's SummEval inputs](https://github.com/maszhongming/UniEval/tree/d33e7b6cfebe97b2bafe435adbd818230d5a416a/reproduce/data/summarization) | MIT (the UniEval repository) | Downloaded by the SummEval adapter for its `unievalpub` arm, pinned to a commit and hashed into the run. It is SummEval's own text, tokenised and cased differently, so SummEval's and CNN/DailyMail's terms apply to its content as well. |
| [Goyal, Li & Durrett 2022 human annotations](https://tagoyal.github.io/zero-shot-explorer/human_annotations.zip) | CC BY 4.0 (the archive's `LICENSE.txt`) | Attribute the authors. Its items are CNN articles, so CNN/DailyMail's terms apply to them too. Downloaded by `validate_judge_goyal.py` (sha256 pinned) and not committed; the committed records hold article ids, our judges' replies and scores, and hashes. |
| [Zhang et al. 2024 human ratings](https://github.com/Tiiiger/benchmark_llm_summarization) | not stated by the authors | Cite the paper (Zhang, Ladhak, Durmus, Liang, McKeown & Hashimoto, TACL 2024). Its items are CNN/DailyMail articles, so CNN/DailyMail's terms apply to them too. Downloaded by `validate_judge_zhang.py` (pinned to a commit and its sha256) and not committed; the committed records hold article ids, our judges' replies and scores, and hashes, never the articles, summaries or individual ratings (`report.json` holds aggregates): a reply that is not bare JSON scores, or that repeats 8 consecutive words of the article or a summary, is kept only as its hash. |

Licence was a selection criterion, not an afterthought: Few-NERD was chosen over a corpus
closer to the original application because that one is licensed `other`. Sources, papers
and the full table: [REFERENCE, datasets](REFERENCE.md#datasets) and
[credits](REFERENCE.md#credits).

## What we ask of you

1. **Fetch the data from its source** with each example's `fetch.py`. Don't redistribute a
   corpus or its references; the repository deliberately doesn't.
2. **Each dataset's licence applies to your copy and to what you derive from it**,
   including the committed run outputs above. Our MIT licence covers the code only.
3. **AG News is for non-commercial research.** For a commercial evaluation, swap it out.
4. **CC BY-SA data is share-alike.** If you publish text derived from DBpedia, Few-NERD
   or SciFact, attribute it and publish that text under the same licence.
5. **Cite the work you use.** The papers behind each dataset and metric are listed in
   [REFERENCE](REFERENCE.md#credits) and [papers](papers/README.md).

## Models

Model weights have licences too, and they differ: three of the local models state no
licence at all (`bert_mini`, `textattack/bert-base-uncased-ag-news` and UniEval's
`MingZhong/unieval-sum`), which is a reuse blocker rather than a permission, and several open-weight LLMs
carry use conditions. Each is listed, read from the publisher, in
[REFERENCE, models](REFERENCE.md#models). Check before you deploy one.

## Your own data

When you point the harness at your own system, your data stays where you put it: datasets,
references and runs are files under your project's `data/` directory (or `EVAL_HOME`). It goes nowhere unless you configure
a hosted model, and then each item is sent to that provider (via OpenRouter or your own gateway),
under that provider's terms. Read them before you send anything confidential, and prefer a
local model for data that cannot leave your machine.
