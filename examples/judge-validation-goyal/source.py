"""Goyal, Li & Durrett (2022) as a rated dataset: modern news summaries, three annotators' best and worst.

    evh dataset-create --dataset-id goyal2022_cnn_v1 --source examples/judge-validation-goyal/source.py:Source \\
        --query '{"answer": "ratings"}'
    evh dataset-materialize --dataset-id goyal2022_cnn_v1
    evh reference-promote --dataset-id goyal2022_cnn_v1 --labels answers --tier gold --reason "..." --by person:NAME
    evh judge-validate --scorer judge-summ-v1 --dataset goyal2022_cnn_v1 --dry-run

For 100 CNN articles of 2022, "News Summarization and Evaluation in the Era of GPT-3" (Goyal, Li & Durrett, CC BY 4.0)
released summaries by GPT-3 (text-davinci-002), BRIO (a BART fine-tune) and T0, each set judged best and worst by three
annotators. The source writes the rated shape `evh judge-validate` reads: an item is {"source": the article, "outputs":
[GPT-3's, BRIO's, T0's summary]}, and its reference is {"ratings": {dimension: [one number per output]}, "raters":
[...]}.

The annotators gave one overall preference, not a score per dimension. It is the source's to map: a summary ranked
best is 2, one named in neither list 1, one ranked worst 0, an annotator's ranks stand for every dimension of the
scorer (the query's `dimensions`, default SummEval's four), and `ratings` is their mean over the three annotators.

Query: `dimensions` (a list; default coherence, consistency, fluency, relevance); `file` (a local copy of the
archive: no download, and no pin); `answer` (any name: it makes the ratings the dataset's own answers, a label set to
promote to a reference). The archive is downloaded once to the project's item cache, pinned by its sha256 and
checked again for the file in it, so the same query reads the same bytes.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from evaluation_harness import _fetch, _store

URL = "https://tagoyal.github.io/zero-shot-explorer/human_annotations.zip"
#: sha256 of the zip served at URL on 2026-10-20 (327,103 bytes), and of the cnn_human.json in it.
ZIP_SHA256 = "0139228dd09f652865015495551685caf886e540f816f06d4fc7961b82124cf6"
CNN_JSON_SHA256 = "4e13a6eeb2aeb2c300b32e870360f0118d4855bcbb1ade8d8946976c4b203fe4"
MEMBER = "human_annotations/cnn_human.json"
SYSTEMS = ("gpt3", "brio", "t0")
DIMENSIONS = ("coherence", "consistency", "fluency", "relevance")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def rank(annotator: dict[str, Any], system: str) -> int:
    """One annotator's rank of a system: best 2, named in neither list 1, worst 0."""
    return 2 if system in annotator["best_summary"] else 0 if system in annotator["worst_summary"] else 1


class Source:
    """The Goyal et al. annotations as a rated dataset."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def describe(self, query: dict) -> dict:
        """The archive as a source block, with its licence and what it holds."""
        return {
            "source": {"provider": "goyal2022", "ref": "human_annotations.zip", "url": URL},
            "licence": "CC-BY-4.0",
            "description": (
                "Goyal, Li & Durrett 2022: summaries of 100 CNN articles by GPT-3, BRIO and T0, each set ranked best "
                "and worst by three annotators, as a rated dataset for evh judge-validate. The ratings are the "
                "annotators' ranks (best 2, unranked 1, worst 0), the same for every dimension."
            ),
        }

    def _data(self, query: dict) -> dict[str, Any]:
        if query.get("file"):
            raw = _store.read_bytes(Path(str(query["file"])))
        else:
            try:
                path, _ = _fetch.fetch(URL, ZIP_SHA256)
            except _fetch.FetchError as exc:
                raise OSError(str(exc)) from exc
            raw = _store.read_bytes(Path(path))
        try:
            member = zipfile.ZipFile(io.BytesIO(raw)).read(MEMBER)
        except (zipfile.BadZipFile, KeyError) as exc:
            raise ValueError(f"the archive holds no {MEMBER}: {exc}") from exc
        if not query.get("file") and _sha(member) != CNN_JSON_SHA256:
            raise ValueError(f"{MEMBER} has sha256 {_sha(member)}, not the pinned {CNN_JSON_SHA256}")
        return json.loads(member)

    def items(self, query: dict) -> Iterator[dict]:
        """One item per article, in the archive's order: the article and the three summaries, and the ratings."""
        dims = list(query.get("dimensions") or DIMENSIONS)
        for aid, v in self._data(query).items():
            outputs = [v[s]["text"] for s in SYSTEMS]
            people = [{d: [float(rank(a, s)) for s in SYSTEMS] for d in dims} for a in v["annotators"]]
            mean = {
                d: [sum(p[d][i] for p in people) / len(people) for i in range(len(SYSTEMS))] for d in dims
            }
            yield {
                "item_id": str(aid),
                "text": json.dumps({"source": v["article"], "outputs": outputs}),
                "answer": json.dumps({"ratings": mean, "raters": people}),
            }
