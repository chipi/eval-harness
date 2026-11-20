"""Zhang et al. (2024) as a rated dataset: crowd ratings of 19 summarisers on CNN/DailyMail articles.

    evh dataset-create --dataset-id zhang2023_cnndm_v1 --source examples/judge-validation-zhang/source.py:Source \\
        --query '{"answer": "ratings"}'
    evh dataset-materialize --dataset-id zhang2023_cnndm_v1
    evh reference-promote --dataset-id zhang2023_cnndm_v1 --labels answers --tier gold --reason "..." --by person:NAME

"Benchmarking Large Language Models for News Summarization" (Zhang, Ladhak, Durmus, Liang, McKeown & Hashimoto, TACL
2024) released Likert ratings of 19 summarisers on 100 CNN/DailyMail articles: GPT-3-era LLMs (zero- and few-shot),
fine-tunes (BRIO, Pegasus) and the reference highlights, three crowd ratings per summary. The source writes the rated
shape `evh judge-validate` reads: an item is {"source": the article, "outputs": [one summary per system, systems in
name order]}, and its reference is {"ratings": {dimension: [one number per output]}, "raters": [...]}.

The raters rated coherence and relevance 1-5 and faithfulness 0/1; they did not rate fluency. Naming the judge's
dimension for a human one is the source's to do: faithfulness stands for the judge's `consistency`, so the ratings
carry coherence, consistency and relevance. `raters` holds the three ratings of each summary in a seeded order
(a rating is not tied to a person across summaries), so a rotating "one against the other two" is what it was in the
tool this replaces. A summary a model left empty (114 of the ratings are of one) is kept as an empty output: a judge
should put it last.

Query: `file` (a local copy of likert_evaluation_results.json: no download, no pin); `answer` (any name: the ratings
become the dataset's own answers, a label set to promote to a reference). The file, pinned to the commit it was read
at and its sha256, is downloaded once to the project's item cache.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from evaluation_harness import _fetch, _store

#: The repository's commit when the file was fetched (2026-10-21), and the file's sha256 (31,259,080 bytes).
COMMIT = "4e87890ed070c7db3dd5c1125adb5bde0ccd2eb1"
URL = f"https://raw.githubusercontent.com/Tiiiger/benchmark_llm_summarization/{COMMIT}/likert_evaluation_results.json"
PINNED = "5f9936bb9c09877f758605a1767031d547db8edfd45ab1f93608a0fd6f56b56c"
#: Human dimension -> the judge dimension that orders the same property.
PAIRS = (("coherence", "coherence"), ("relevance", "relevance"), ("faithfulness", "consistency"))


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def article_id(article: str) -> str:
    """An article's item id: the first 16 hex digits of its text's sha256."""
    return _sha(article.encode())[:16]


class Source:
    """The Zhang et al. ratings as a rated dataset."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def describe(self, query: dict) -> dict:
        """The file as a source block, with what it holds."""
        return {
            "source": {
                "provider": "zhang2023",
                "ref": "likert_evaluation_results.json",
                "url": URL,
                "revision": COMMIT,
            },
            "licence": "unknown",
            "description": (
                "Zhang et al. 2024: Likert ratings of 19 summarisers on 100 CNN/DailyMail articles, three ratings per "
                "summary, as a rated dataset for evh judge-validate. The authors state no licence; cite the paper."
            ),
        }

    def _rows(self, query: dict) -> list[dict[str, Any]]:
        if query.get("file"):
            raw = _store.read_bytes(Path(str(query["file"])))
        else:
            try:
                path, _ = _fetch.fetch(URL, PINNED)
            except _fetch.FetchError as exc:
                raise OSError(str(exc)) from exc
            raw = _store.read_bytes(Path(path))
        return json.loads(raw)

    def items(self, query: dict) -> Iterator[dict]:
        """One item per CNN/DailyMail article in the file's order, its summaries by system name."""
        arts: dict[str, dict[str, Any]] = {}
        for r in self._rows(query):
            if r["dataset"] != "cnndm":
                continue
            a = arts.setdefault(article_id(r["article"]), {"article": r["article"], "systems": {}})
            # An empty summary is NaN in the file: kept, as an empty output.
            text = r["summary"] if isinstance(r["summary"], str) else ""
            s = a["systems"].setdefault(r["model"], {"summary": text, "ratings": []})
            s["ratings"].append({h: float(r[h]) for h, _ in PAIRS})
        for aid, a in arts.items():
            names = sorted(a["systems"])
            ordered = {
                m: sorted(
                    a["systems"][m]["ratings"],
                    key=lambda r, m=m: _sha(f"zhang-ho:{aid}:{m}:{json.dumps(r, sort_keys=True)}".encode()),
                )
                for m in names
            }
            k = min(len(v) for v in ordered.values())
            people = [{j: [ordered[m][i][h] for m in names] for h, j in PAIRS} for i in range(k)]
            mean = {j: [sum(p[j][x] for p in people) / k for x in range(len(names))] for _, j in PAIRS}
            yield {
                "item_id": aid,
                "text": json.dumps(
                    {"source": a["article"], "outputs": [a["systems"][m]["summary"] for m in names]}
                ),
                "answer": json.dumps({"ratings": mean, "raters": people}),
            }
