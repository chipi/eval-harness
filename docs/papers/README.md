# Papers — what may be mirrored here, what may not, and why nothing is

Every work cited in [`../REFERENCE.md`](../REFERENCE.md) and the per-experiment
`METHOD.md` files, with the redistribution licence **read from the publisher's own page**
on 2026-09-29 rather than assumed.

[`fetch_papers.py`](fetch_papers.py) downloads the redistributable ones into this
directory for offline reading. **Its output is gitignored.** See
[Why nothing is committed](#why-nothing-is-committed).

```bash
python docs/papers/fetch_papers.py          # the 12 that permit redistribution
python docs/papers/fetch_papers.py --all    # all 24, for personal use only
```

---

## Redistributable — CC BY / CC BY-SA, attribution required

Mirroring these is permitted provided the author and licence travel with the copy.

| Work | Licence | Source |
|---|---|---|
| Lin (2004), *ROUGE: A Package for Automatic Evaluation of Summaries* | CC BY 4.0 | [ACL W04-1013](https://aclanthology.org/W04-1013/) |
| Tjong Kim Sang & De Meulder (2003), *Introduction to the CoNLL-2003 Shared Task* | CC BY 4.0 | [ACL W03-0419](https://aclanthology.org/W03-0419/) |
| Dror et al. (2018), *The Hitchhiker's Guide to Testing Statistical Significance in NLP* | CC BY 4.0 | [ACL P18-1128](https://aclanthology.org/P18-1128/) |
| Kryscinski et al. (2019), *Neural Text Summarization: A Critical Evaluation* | CC BY 4.0 | [ACL D19-1051](https://aclanthology.org/D19-1051/) |
| Wadden et al. (2020), *Fact or Fiction: Verifying Scientific Claims* | CC BY 4.0 | [ACL 2020.emnlp-main.609](https://aclanthology.org/2020.emnlp-main.609/) |
| Ding et al. (2021), *Few-NERD: A Few-shot Named Entity Recognition Dataset* | CC BY 4.0 | [ACL 2021.acl-long.248](https://aclanthology.org/2021.acl-long.248/) |
| Reimers & Gurevych (2019), *Sentence-BERT* | CC BY-SA 4.0 | [arXiv 1908.10084](https://arxiv.org/abs/1908.10084) |
| Thakur et al. (2021), *BEIR* | CC BY-SA 4.0 | [arXiv 2104.08663](https://arxiv.org/abs/2104.08663) |
| He et al. (2021), *DeBERTaV3* | CC BY 4.0 | [arXiv 2111.09543](https://arxiv.org/abs/2111.09543) |
| Wang et al. (2022), *Text Embeddings by Weakly-Supervised Contrastive Pre-training* (E5) | CC BY 4.0 | [arXiv 2212.03533](https://arxiv.org/abs/2212.03533) |
| Zaratiana et al. (2023), *GLiNER* | CC BY 4.0 | [arXiv 2311.08526](https://arxiv.org/abs/2311.08526) |
| Zhang et al. (2024), *A Careful Examination of LLM Performance on Grade School Arithmetic* | CC BY 4.0 | [arXiv 2405.00332](https://arxiv.org/abs/2405.00332) |

## NOT redistributable — link only

| Work | Licence | Why not |
|---|---|---|
| Hermann et al. (2015), *Teaching Machines to Read and Comprehend* | [arXiv non-exclusive 1.0](https://arxiv.org/abs/1506.03340) | Grants **arXiv** the right to distribute, not third parties |
| Zhang, Zhao & LeCun (2015), *Character-level Convolutional Networks* | arXiv non-exclusive 1.0 | same |
| Nallapati et al. (2016), *Abstractive Text Summarization Using Seq2Seq RNNs* | arXiv non-exclusive 1.0 | same |
| See, Liu & Manning (2017), *Get To The Point* | arXiv non-exclusive 1.0 | same |
| Guo et al. (2017), *On Calibration of Modern Neural Networks* | arXiv non-exclusive 1.0 | same |
| Devlin et al. (2018), *BERT* | arXiv non-exclusive 1.0 | same |
| Yin et al. (2019), *Benchmarking Zero-shot Text Classification* | arXiv non-exclusive 1.0 | same |
| Lewis et al. (2019), *BART* | arXiv non-exclusive 1.0 | same |
| Song et al. (2020), *MPNet* | arXiv non-exclusive 1.0 | same |
| Xiao et al. (2023), *C-Pack* (BGE) | arXiv non-exclusive 1.0 | same |
| Järvelin & Kekäläinen (2002), *Cumulated gain-based evaluation of IR techniques* | © ACM | [ACM DL](https://dl.acm.org/doi/10.1145/582415.582418), subscription |
| Holm (1979), *A Simple Sequentially Rejective Multiple Test Procedure* | © Scandinavian Journal of Statistics | Paywalled. **Also the one citation in this repo that could not be verified programmatically** — JSTOR serves a bot challenge and Crossref does not index the 1979 volume, so the reference is given in full text instead of linked |
| Demšar (2006), *Statistical Comparisons of Classifiers over Multiple Data Sets* | not machine-readable on the page | [JMLR v7](https://www.jmlr.org/papers/v7/demsar06a.html) states no licence this check could read; freely readable there |

> **The arXiv non-exclusive licence is the common trap.** It reads like an open licence and
> is not: it grants arXiv a perpetual right to distribute the work. It says nothing about
> anyone else mirroring it. Ten of the sixteen arXiv papers cited here are under it.

---

## Why nothing is committed

Twelve of the twenty-four **could** be mirrored. They are not, for three reasons:

1. **A half-mirror misleads.** A `papers/` directory holding 12 of 24 tells a browsing
   reader that those twelve are the canon and the rest are optional. They are not — the
   split is by *publisher licensing policy*, which correlates with nothing about
   importance. nDCG and Holm, two of the most load-bearing citations in the repo, are both
   in the un-mirrorable half.
2. **CC BY is an obligation, not a permission slip.** Each mirrored PDF must carry its
   author and licence. That is twelve ongoing obligations in a public repo, for offline
   convenience that a script provides on demand.
3. **It is 20–40 MB of PDFs** in a repository whose entire design is that it commits no
   corpora, no weights and no third-party content — only recipes. Mirroring papers would
   be the one exception, and it would be the least defensible one.

So: a fetcher, a ledger, and a link. Same reasoning as
[`data/corpora/`](../../harness/data/corpora/README.md) — **the recipe travels, the bytes
do not.**

If you want the twelve committed anyway, `fetch_papers.py` writes them here and the
gitignore rule is one line; the licence column above is what an attribution file would be
built from.
