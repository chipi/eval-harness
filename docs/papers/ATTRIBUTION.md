# Attribution for the papers mirrored in this directory

The twelve PDFs here are **redistributed under Creative Commons licences**, which permit
copying provided the author, title and licence travel with the copy. This file is that
attribution. It is a licence obligation, not documentation — **if you fork this repo or
copy these files, this file comes too.**

**None of these files has been modified.** Each is the publisher's PDF, byte-for-byte as
served, fetched on 2026-09-29 by [`fetch_papers.py`](fetch_papers.py). Licences were read
from each publisher's own page on the same date.

| File | Work | Author(s) | Licence | Source |
|---|---|---|---|---|
| `lin-2004-rouge.pdf` | *ROUGE: A Package for Automatic Evaluation of Summaries* (2004) | Chin-Yew Lin | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [ACL W04-1013](https://aclanthology.org/W04-1013/) |
| `conll-2003-ner.pdf` | *Introduction to the CoNLL-2003 Shared Task: Language-Independent Named Entity Recognition* (2003) | Erik F. Tjong Kim Sang, Fien De Meulder | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [ACL W03-0419](https://aclanthology.org/W03-0419/) |
| `dror-2018-significance.pdf` | *The Hitchhiker's Guide to Testing Statistical Significance in Natural Language Processing* (2018) | Rotem Dror, Gili Baumer, Segev Shlomov, Roi Reichart | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [ACL P18-1128](https://aclanthology.org/P18-1128/) |
| `kryscinski-2019-summarization-critique.pdf` | *Neural Text Summarization: A Critical Evaluation* (2019) | Wojciech Kryscinski, Nitish Shirish Keskar, Bryan McCann, Caiming Xiong, Richard Socher | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [ACL D19-1051](https://aclanthology.org/D19-1051/) |
| `wadden-2020-scifact.pdf` | *Fact or Fiction: Verifying Scientific Claims* (2020) | David Wadden, Shanchuan Lin, Kyle Lo, Lucy Lu Wang, Madeleine van Zuylen, Arman Cohan, Hannaneh Hajishirzi | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [ACL 2020.emnlp-main.609](https://aclanthology.org/2020.emnlp-main.609/) |
| `ding-2021-few-nerd.pdf` | *Few-NERD: A Few-shot Named Entity Recognition Dataset* (2021) | Ning Ding, Guangwei Xu, Yulin Chen, Xiaobin Wang, Xu Han, Pengjun Xie, Haitao Zheng, Zhiyuan Liu | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [ACL 2021.acl-long.248](https://aclanthology.org/2021.acl-long.248/) |
| `reimers-2019-sentence-bert.pdf` | *Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks* (2019) | Nils Reimers, Iryna Gurevych | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | [arXiv 1908.10084](https://arxiv.org/abs/1908.10084) |
| `thakur-2021-beir.pdf` | *BEIR: A Heterogenous Benchmark for Zero-shot Evaluation of Information Retrieval Models* (2021) | Nandan Thakur, Nils Reimers, Andreas Rücklé, Abhishek Srivastava, Iryna Gurevych | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | [arXiv 2104.08663](https://arxiv.org/abs/2104.08663) |
| `he-2021-deberta-v3.pdf` | *DeBERTaV3: Improving DeBERTa using ELECTRA-Style Pre-Training with Gradient-Disentangled Embedding Sharing* (2021) | Pengcheng He, Jianfeng Gao, Weizhu Chen | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [arXiv 2111.09543](https://arxiv.org/abs/2111.09543) |
| `wang-2022-e5.pdf` | *Text Embeddings by Weakly-Supervised Contrastive Pre-training* (2022) | Liang Wang, Nan Yang, Xiaolong Huang, Binxing Jiao, Linjun Yang, Daxin Jiang, Rangan Majumder, Furu Wei | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [arXiv 2212.03533](https://arxiv.org/abs/2212.03533) |
| `zaratiana-2023-gliner.pdf` | *GLiNER: Generalist Model for Named Entity Recognition using Bidirectional Transformer* (2023) | Urchade Zaratiana, Nadi Tomeh, Pierre Holat, Thierry Charnois | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [arXiv 2311.08526](https://arxiv.org/abs/2311.08526) |
| `zhang-2024-gsm1k.pdf` | *A Careful Examination of Large Language Model Performance on Grade School Arithmetic* (2024) | Hugh Zhang, Jeff Da, Dean Lee, Vaughn Robinson, Catherine Wu, Will Song, et al. | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [arXiv 2405.00332](https://arxiv.org/abs/2405.00332) |

## Share-alike obligation on two of them

`reimers-2019-sentence-bert.pdf` and `thakur-2021-beir.pdf` are **CC BY-SA 4.0**, not
CC BY. If you produce a *derivative* of either — an edited or adapted version — that
derivative must itself be CC BY-SA 4.0. Redistributing them unchanged, as here, carries no
such obligation, which is one reason they are mirrored unmodified.

## What is NOT here, and why

Twelve further works cited by this repo are **not** redistributable and are therefore not
in this directory: ten arXiv papers under `arxiv.org/licenses/nonexclusive-distrib/1.0`
(which grants arXiv a distribution right and says nothing about third parties), plus
Järvelin & Kekäläinen (2002) behind the ACM Digital Library and Holm (1979) behind JSTOR.
[`README.md`](README.md) lists each with its licence and a link.

`python docs/papers/fetch_papers.py --all` downloads those for reading. They are gitignored
by name so they cannot be committed by accident.
