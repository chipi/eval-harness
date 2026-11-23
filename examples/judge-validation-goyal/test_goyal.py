#!/usr/bin/env python3
"""The Goyal source: the archive's format in, the rated shape `evh judge-validate` reads out.

    python examples/judge-validation-goyal/test_goyal.py

A two-article archive in the download's own format (a zip holding human_annotations/cnn_human.json), no network: the
items are {source, outputs}, an annotator's ranks become ratings and raters over the query's dimensions, a query's
dimensions replace the default four, `dataset-create` hands the ratings on as the dataset's own answers, and what it
writes is a rated dataset for a scorer over those dimensions.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[1] / "harness"
sys.path.insert(0, str(HARNESS))
# a script outside harness/ names it as its project, then makes one of its own
os.environ.setdefault("EVAL_HOME", str(HARNESS))
sys.path.insert(0, str(HARNESS / "tests"))
proj = Path(tempfile.mkdtemp(prefix="evh-goyal-"))
os.environ.update(EVAL_HOME=str(proj), EVAL_BUILD_REF="test-goyal")
os.environ.setdefault("EVAL_STORE", "files")

import _cli  # noqa: E402
from evaluation_harness import _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(HERE))
from source import MEMBER, SYSTEMS, Source  # noqa: E402


def ann(best, worst):
    return {"best_summary": best, "worst_summary": worst}


ARCHIVE = {
    "7": {
        "article": "A council met on Tuesday.",
        "gpt3": {"text": "gpt3 on seven"}, "brio": {"text": "brio on seven"}, "t0": {"text": "t0 on seven"},
        "annotators": [ann(["gpt3"], ["t0"]), ann(["gpt3"], ["brio"]), ann(["brio"], ["t0"])],
    },
    "9": {
        "article": "A bridge reopened.",
        "gpt3": {"text": "gpt3 on nine"}, "brio": {"text": "brio on nine"}, "t0": {"text": "t0 on nine"},
        "annotators": [ann(["t0"], []), ann(["t0", "brio"], ["gpt3"]), ann([], ["gpt3"])],
    },
}  # fmt: skip
zpath = Path(tempfile.mkdtemp(prefix="evh-goyal-zip-")) / "human_annotations.zip"
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr(MEMBER, json.dumps(ARCHIVE))
_store.write_bytes(zpath, buf.getvalue())

src = Source({})
got = list(src.items({"file": str(zpath)}))
a = json.loads(got[0]["text"])
ref = json.loads(got[0]["answer"])
check(
    "items: one per article, in the archive's order, ids the archive's keys",
    [g["item_id"] for g in got] == ["7", "9"],
)
check(
    "items: {source, outputs} with the outputs in the systems' order",
    a == {"source": "A council met on Tuesday.", "outputs": ["gpt3 on seven", "brio on seven", "t0 on seven"]}
    and SYSTEMS == ("gpt3", "brio", "t0"),
)
check(
    "ratings: best 2, unranked 1, worst 0 per annotator; the mean over the three annotators, the same for each of the four dimensions",
    ref["raters"][0] == {d: [2.0, 1.0, 0.0] for d in ("coherence", "consistency", "fluency", "relevance")}
    and ref["raters"][1]["fluency"] == [2.0, 0.0, 1.0]
    and ref["ratings"]["coherence"] == [(2 + 2 + 1) / 3, (1 + 0 + 2) / 3, (0 + 1 + 0) / 3]
    and len(ref["raters"]) == 3,
    ref,
)
nine = json.loads(got[1]["answer"])
check(
    "ratings: two systems named best are both 2, nobody named is 1",
    nine["raters"][1]["coherence"] == [0.0, 2.0, 2.0] and nine["raters"][0]["coherence"] == [1.0, 1.0, 2.0],
    nine["raters"],
)
two = list(src.items({"file": str(zpath), "dimensions": ["overall"]}))
check(
    "query: `dimensions` names the dimensions the ratings carry",
    set(json.loads(two[0]["answer"])["ratings"]) == {"overall"},
)
d = src.describe({})
check(
    "describe: the archive's licence and a source block that names it",
    d["licence"] == "CC-BY-4.0"
    and d["source"]["provider"] == "goyal2022"
    and d["source"]["url"].startswith("https://"),
)

r = _cli.run(proj, os.environ, "init", "--store", os.environ["EVAL_STORE"])
check("setup: a project", r.returncode == 0, r.stdout + r.stderr)
r = _cli.run(
    proj,
    os.environ,
    "dataset-create",
    "--dataset-id",
    "goyal_t",
    "--source",
    str(HERE / "source.py") + ":Source",
    "--query",
    json.dumps({"file": str(zpath), "answer": "ratings"}),
)
r = r if r.returncode else _cli.run(proj, os.environ, "dataset-materialize", "--dataset-id", "goyal_t")
r = (
    r
    if r.returncode
    else _cli.run(
        proj,
        os.environ,
        "reference-promote",
        "--dataset-id",
        "goyal_t",
        "--labels",
        "answers",
        "--tier",
        "gold",
        "--reason",
        "people ranked them",
        "--by",
        "tester",
    )
)
check(
    "dataset-create: the ratings are the dataset's own answers, promoted to its reference",
    r.returncode == 0,
    r.stdout + r.stderr,
)

from evaluation_harness import judge_validate as jv  # noqa: E402

items, refs = jv._load_rated("goyal_t")


def tree(sub: str) -> dict[str, bytes]:
    return {x.name: _store.read_bytes(x) for x in _store.glob(proj / "data" / sub / "goyal_t", "*.txt")}


kept = {"sources": tree("sources"), "gold": tree("references/gold")}
fetched = subprocess.run(
    [
        sys.executable,
        str(HERE / "fetch.py"),
        "--dataset-id",
        "goyal_t",
        "--query",
        json.dumps({"file": str(zpath)}),
    ],
    env=os.environ,
    capture_output=True,
    text=True,
    stdin=subprocess.DEVNULL,
    timeout=600,
    check=False,
    encoding="utf-8",
)
check(
    "fetch.py brings back the item texts and the gold texts byte for byte as dataset-create and reference-promote wrote them",
    fetched.returncode == 0
    and kept["gold"]
    and kept == {"sources": tree("sources"), "gold": tree("references/gold")},
    fetched.stdout + fetched.stderr,
)
sc = {
    "scorer_id": "s",
    "kind": "judge",
    "task": {"dimensions": ["coherence", "consistency", "fluency", "relevance"], "scale": [1, 5]},
}
check(
    "the dataset is a rated one for a scorer over SummEval's four dimensions",
    jv.rated_problems(sc, items, refs) == [] and set(items) == {"7", "9"},
    jv.rated_problems(sc, items, refs),
)
sys.exit(summary())
