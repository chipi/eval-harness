#!/usr/bin/env python3
"""SummEval as a rated dataset: the rows of the Hub's conversion in, the rated shape `evh judge-validate` reads out.

    python examples/summeval-judging/test_rated_source.py

Two rows in the split's own format, the Hub stood in for (no network): an item is {source, outputs} with the 16
summaries and no human reference, its reference is the experts' scores as ratings over the four dimensions, an item
that keeps the split's row number, a partial row is refused, and what it writes is a rated dataset for a scorer over
SummEval's four dimensions.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[1] / "harness"
sys.path.insert(0, str(HARNESS))
# a script outside harness/ names it as its project, then makes one of its own
os.environ.setdefault("EVAL_HOME", str(HARNESS))
sys.path.insert(0, str(HARNESS / "tests"))
os.environ.update(EVAL_HOME=tempfile.mkdtemp(prefix="evh-summeval-rated-"), EVAL_BUILD_REF="test-rated")
os.environ.setdefault("EVAL_STORE", "files")

from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(HERE))
import rated_source  # noqa: E402
from hf_rows import Row  # noqa: E402

DIMS = rated_source.DIMS


def row(i: int, n: int = 16) -> Row:
    r = Row(
        {
            "id": f"cnn-test-{i}",
            "text": f"Article {i}.",
            "machine_summaries": [f"summary {k} of {i}" for k in range(n)],
            "human_summaries": [f"the reference of {i}"],
            **{d: [1.0 + (k + j) % 5 / 3 for k in range(n)] for j, d in enumerate(DIMS)},
        }
    )
    r.row_idx = i
    return r


calls: list[int] = []


def pages(dataset: str, config: str, split: str, offset: int, length: int) -> list[Row]:
    calls.append(offset)
    return [row(0), row(1)][offset : offset + length]


rated_source._rows_page = pages  # type: ignore[assignment]  # the Hub stood in for
rated_source._revision = lambda *a: "c" * 40  # type: ignore[assignment]
got = list(rated_source.Source({}).items({}))
item, ref = json.loads(got[0]["text"]), json.loads(got[0]["answer"])
check(
    "items: one per row, read page by page, in the split's order, with its id and row number",
    [g["item_id"] for g in got] == ["cnn-test-0", "cnn-test-1"]
    and [g["row"] for g in got] == [0, 1]
    and calls == [0, 2],
)
check(
    "items: {source, outputs}, the 16 summaries, no human reference in the item",
    set(item) == {"source", "outputs"} and len(item["outputs"]) == 16 and item["source"] == "Article 0.",
)
check(
    "reference: the experts' scores as ratings, one list of 16 per dimension",
    set(ref) == {"ratings"}
    and set(ref["ratings"]) == set(DIMS)
    and all(len(v) == 16 for v in ref["ratings"].values())
    and ref["ratings"]["coherence"][0] == 1.0,
)
d = rated_source.Source({}).describe({})
check(
    "describe: pinned to the conversion's commit, MIT",
    d["licence"] == "MIT" and d["source"]["revision"] == "c" * 40 and d["source"]["ref"] == "mteb/summeval",
)
rated_source._rows_page = lambda *a: [row(0, 15)] if a[3] == 0 else []  # type: ignore[assignment]
try:
    list(rated_source.Source({}).items({}))
    refused = ""
except ValueError as exc:
    refused = str(exc)
check("a partial row (15 summaries) is refused, not scored on fewer pairs", "incomplete" in refused, refused)

from evaluation_harness import judge_validate as jv  # noqa: E402

sc = {"scorer_id": "s", "kind": "judge", "task": {"dimensions": list(DIMS), "scale": [1, 5]}}
texts = {g["item_id"]: g["text"] for g in got}
refs = {g["item_id"]: g["answer"] for g in got}
check(
    "what it writes is a rated dataset for a scorer over SummEval's four dimensions",
    jv.rated_problems(sc, texts, refs) == [],
    jv.rated_problems(sc, texts, refs),
)
sys.exit(summary())
