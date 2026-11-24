#!/usr/bin/env python3
"""The Zhang source: the file's format in, the rated shape `evh judge-validate` reads out.

    python examples/judge-validation-zhang/test_zhang.py

Two articles in the download's own format (a JSON list of one row per rating, an empty summary as NaN, a row of another
dataset), no network: the items are {source, outputs} with one summary per system in name order, the ratings are over
the judge's dimensions (faithfulness is the judge's consistency), the three ratings of a summary are three raters, an
empty summary is kept, rows of other datasets are left out, and the dataset is a rated one for a scorer over those
dimensions, and for one that also asks for fluency, which the raters did not rate: the dataset carries three of its four.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[1] / "harness"
sys.path.insert(0, str(HARNESS))
# a script outside harness/ names it as its project, then makes one of its own
os.environ.setdefault("EVAL_HOME", str(HARNESS))
sys.path.insert(0, str(HARNESS / "tests"))
proj = Path(tempfile.mkdtemp(prefix="evh-zhang-"))
os.environ.update(EVAL_HOME=str(proj), EVAL_BUILD_REF="test-zhang")
os.environ.setdefault("EVAL_STORE", "files")

import _cli  # noqa: E402
from evaluation_harness import _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(HERE))
from source import PAIRS, Source, article_id  # noqa: E402

NAN = float("nan")


def rows(article, model, summary_text, ratings, dataset="cnndm"):
    return [
        {"dataset": dataset, "article": article, "model": model, "summary": summary_text, "coherence": c, "relevance": r, "faithfulness": f}
        for c, r, f in ratings
    ]  # fmt: skip


DATA = [
    *rows("A council met.", "brio", "brio on the council", [(5, 4, 1), (4, 4, 1), (5, 5, 1)]),
    *rows("A council met.", "gpt3", "gpt3 on the council", [(2, 2, 0), (3, 2, 0), (2, 3, 1)]),
    *rows("A council met.", "reference", NAN, [(1, 1, 0), (1, 1, 0), (1, 2, 0)]),
    *rows("A bridge reopened.", "brio", "brio on the bridge", [(4, 4, 1), (4, 5, 1), (5, 4, 1)]),
    *rows("A bridge reopened.", "gpt3", "gpt3 on the bridge", [(3, 3, 1), (2, 3, 0), (3, 3, 1)]),
    *rows("A bridge reopened.", "reference", "the reference", [(5, 5, 1), (5, 5, 1), (5, 5, 1)]),
    *rows("A xsum article.", "brio", "xsum", [(1, 1, 0)] * 3, dataset="xsum"),
]
fpath = Path(tempfile.mkdtemp(prefix="evh-zhang-file-")) / "likert_evaluation_results.json"
_store.write_text(fpath, json.dumps(DATA))  # json.dumps writes NaN, which json.loads reads: as the file does

src = Source({})
got = list(src.items({"file": str(fpath)}))
a, ref = json.loads(got[0]["text"]), json.loads(got[0]["answer"])
check(
    "items: one per CNN/DailyMail article, the other dataset's row left out, ids the article's hash",
    [g["item_id"] for g in got] == [article_id("A council met."), article_id("A bridge reopened.")],
)
check(
    "items: {source, outputs}, one summary per system in name order, an empty summary kept as an empty output",
    a == {"source": "A council met.", "outputs": ["brio on the council", "gpt3 on the council", ""]},
    a,
)
check(
    "ratings: over the judge's dimensions, faithfulness as consistency; each the mean of the three ratings",
    set(ref["ratings"]) == {"coherence", "relevance", "consistency"}
    and abs(ref["ratings"]["coherence"][0] - 14 / 3) < 1e-9
    and ref["ratings"]["consistency"][1] == 1 / 3,
    ref["ratings"],
)
check(
    "raters: the three ratings of each summary, in a seeded order, each a list per dimension of one number per output",
    len(ref["raters"]) == 3
    and all(len(r["coherence"]) == 3 for r in ref["raters"])
    and sorted(r["coherence"][0] for r in ref["raters"]) == [4.0, 5.0, 5.0],
    ref["raters"],
)
check(
    "raters: the same on a second read",
    [g["answer"] for g in got] == [g["answer"] for g in src.items({"file": str(fpath)})],
)
check(
    "describe: no licence stated, pinned to a commit",
    src.describe({})["licence"] == "unknown"
    and len(src.describe({})["source"]["revision"]) == 40
    and PAIRS[2] == ("faithfulness", "consistency"),
)

r = _cli.run(proj, os.environ, "init", "--store", os.environ["EVAL_STORE"])
r = (
    r
    if r.returncode
    else _cli.run(
        proj,
        os.environ,
        "dataset-create",
        "--dataset-id",
        "zhang_t",
        "--source",
        str(HERE / "source.py") + ":Source",
        "--query",
        json.dumps({"file": str(fpath), "answer": "ratings"}),
    )
)
r = r if r.returncode else _cli.run(proj, os.environ, "dataset-materialize", "--dataset-id", "zhang_t")
r = (
    r
    if r.returncode
    else _cli.run(
        proj,
        os.environ,
        "reference-promote",
        "--dataset-id",
        "zhang_t",
        "--labels",
        "answers",
        "--tier",
        "gold",
        "--reason",
        "raters rated them",
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

items, refs = jv._load_rated("zhang_t")


def tree(sub: str) -> dict[str, bytes]:
    return {x.name: _store.read_bytes(x) for x in _store.glob(proj / "data" / sub / "zhang_t", "*.txt")}


kept = {"sources": tree("sources"), "gold": tree("references/gold")}
fetched = subprocess.run(
    [
        sys.executable,
        str(HERE / "fetch.py"),
        "--dataset-id",
        "zhang_t",
        "--query",
        json.dumps({"file": str(fpath)}),
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
three = {
    "scorer_id": "s3",
    "kind": "judge",
    "task": {"dimensions": ["coherence", "consistency", "relevance"], "scale": [1, 5]},
}
four = {
    "scorer_id": "s4",
    "kind": "judge",
    "task": {"dimensions": ["coherence", "consistency", "fluency", "relevance"], "scale": [1, 5]},
}
check(
    "the dataset is a rated one for a scorer over coherence, consistency and relevance",
    jv.rated_problems(three, items, refs) == [],
    jv.rated_problems(three, items, refs),
)
check(
    "a scorer that also asks for fluency still takes it: the raters did not rate it, so the dataset carries three of the four",
    jv.rated_problems(four, items, refs) == []
    and jv.carried_dimensions(four, refs) == ["coherence", "consistency", "relevance"],
    (jv.rated_problems(four, items, refs), jv.carried_dimensions(four, refs)),
)
sys.exit(summary())
