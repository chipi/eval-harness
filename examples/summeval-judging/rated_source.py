"""SummEval as a rated dataset, for `evh judge-validate`: the same 100 articles and expert scores `fetch.py` writes.

    evh dataset-create --dataset-id summeval_rated_100 \\
        --source examples/summeval-judging/rated_source.py:Source --query '{"answer": "answer"}'
    evh dataset-materialize --dataset-id summeval_rated_100
    evh reference-promote --dataset-id summeval_rated_100 --labels answers --tier gold --reason "..." --by person:NAME
    evh judge-validate --scorer judge-summ-v1 --judges gemma_l --dataset summeval_rated_100 --dry-run

`summeval_100`'s items are this example's own shape (an article, its 16 summaries and the human references), which its
adapter reads. `evh judge-validate` reads the rated shape: an item is {"source": the article, "outputs": the 16
summaries} and its reference is {"ratings": {dimension: [16 numbers]}}, the mean of three experts per dimension
(Fabbri et al. 2021), as `fetch.py` takes them as gold. The judges are never shown the human references: they are not
in the item. Read through the Hub's parquet conversion at one pinned commit, as `fetch.py` reads it.

What it is for: one judge of `judge-summ-v1`, validated by the core adapter on these items, measures what this
example's adapter measured of the same judge (the committed `se_gemma_l_n100_v1`, tau 0.5384); the two differ in the
order the 16 summaries are shown in (the core adapter blinds it, seeded): 0.5156 blinded, 0.5360 with `order: original`, against the
committed 0.5384 (RFC-038 section 8).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
from hf_rows import page as _rows_page
from hf_rows import revision as _revision

DATASET, CONFIG, SPLIT = "mteb/summeval", "default", "test"
DIMS = ("coherence", "consistency", "fluency", "relevance")


class Source:
    """The SummEval split as a rated dataset."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def describe(self, query: dict) -> dict:
        """The split as a source block, with its licence."""
        return {
            "source": {
                "provider": "huggingface",
                "ref": DATASET,
                "config": CONFIG,
                "split": SPLIT,
                "revision": _revision(DATASET, CONFIG, SPLIT),
            },
            "licence": "MIT",
            "description": (
                "SummEval (Fabbri et al. 2021): 100 CNN/DailyMail articles, 16 machine summaries each, the mean of three "
                "experts' scores on coherence, consistency, fluency and relevance, as a rated dataset for evh judge-validate."
            ),
        }

    def items(self, query: dict) -> Iterator[dict]:
        """One item per article: the article and its 16 summaries, and the experts' scores."""
        offset = 0
        while True:
            rows = _rows_page(DATASET, CONFIG, SPLIT, offset, 100)
            if not rows:
                return
            for r in rows:
                n = len(r["machine_summaries"])
                if n != 16 or any(len(r[d]) != n for d in DIMS):
                    raise ValueError(
                        f"row {r.get('id')}: incomplete ({n} summaries): refusing a partial item"
                    )
                yield {
                    "item_id": str(r["id"]),
                    "row": r.row_idx,
                    "text": json.dumps(
                        {"source": r["text"], "outputs": r["machine_summaries"]}, ensure_ascii=False
                    ),
                    "answer": json.dumps({"ratings": {d: [round(float(v), 10) for v in r[d]] for d in DIMS}}),
                }
            offset += len(rows)
