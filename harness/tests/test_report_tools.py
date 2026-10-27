#!/usr/bin/env python3
"""The repository's report tools (tools/*_report.py, tools/goal_decisions.py) compute what they
say, on data where the answer is known.

    python tests/test_report_tools.py

The tools read gold references a fresh checkout does not have (the repository commits their
checksums only; the texts come with the public data). So each runs here on a small data tree
written for it (EVAL_DATA_DIR), whose right answer is worked out below by hand:

  - extraction_report: micro P/R/F1 pooled over items and the per-item mean, for a perfect arm
    and one that misses one of three entities;
  - retrieval_report: each arm's nDCG@10 as recorded, and the ceiling (a perfect reordering of
    its own candidates): 1 when every relevant document is among them, less when one is not;
  - classification_report: accuracy, macro-F1 and the worst class on a two-class set;
  - each of the three refuses, naming the fix, when the gold references are only a manifest;
  - goal_decisions: on this repository's goals, one row per goal with a deciding dataset, the
    recommendation `evh goals` prints for the same goal.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402


def tool(script: str, data: Path | None, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("EVAL_HOME", "EVAL_DATA_DIR", "EVAL_RUNS_DIR")}
    if data is not None:
        env["EVAL_DATA_DIR"] = str(data)
    return subprocess.run(
        [sys.executable, str(HARNESS / "tools" / script), *args],
        cwd=HARNESS,
        capture_output=True,
        text=True,
        env=env,
    )


def write_run(
    data: Path, run_id: str, dataset: str, config: str, rows: list, scores: dict | None = None
) -> None:
    d = data / "runs" / run_id
    d.mkdir(parents=True)
    (d / "metrics.json").write_text(
        json.dumps({"run_id": run_id, "dataset_id": dataset, "config_id": config, "scores": scores or {}}),
        encoding="utf-8",
    )
    (d / "predictions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def write_gold(data: Path, dataset: str, items: dict) -> None:
    g = data / "references" / "gold" / dataset
    g.mkdir(parents=True)
    for item, value in items.items():
        (g / f"{item}.txt").write_text(
            value if isinstance(value, str) else json.dumps(value), encoding="utf-8"
        )


def row_of(out: str, arm: str) -> list:
    """The numbers on an arm's line of a report table."""
    line = next((ln for ln in out.splitlines() if ln.split()[:1] == [arm]), "")
    return [float(x.rstrip("%")) for x in re.findall(r"-?\d+\.\d+%?", line)]


def close(a: float, b: float) -> bool:
    return abs(a - b) < 6e-4


def test_extraction(tmp: Path) -> None:
    data = tmp / "ner"
    write_gold(
        data,
        "fx_ner",
        {
            "a": [{"text": "Paris", "type": "location"}],
            "b": [{"text": "Ada Lovelace", "type": "person"}, {"text": "IBM", "type": "organization"}],
        },
    )
    perfect = {
        "a": [{"text": "Paris", "type": "location"}],
        "b": [{"text": "Ada Lovelace", "type": "person"}, {"text": "IBM", "type": "organization"}],
    }
    write_run(
        data,
        "p1",
        "fx_ner",
        "fx_perfect_v1",
        [{"item_id": i, "_meta": {"predicted": v}} for i, v in perfect.items()],
    )
    write_run(
        data,
        "h1",
        "fx_ner",
        "fx_half_v1",
        [
            {"item_id": "a", "_meta": {"predicted": perfect["a"]}},
            {"item_id": "b", "_meta": {"predicted": [{"text": "Ada Lovelace", "type": "person"}]}},
        ],
    )
    r = tool("extraction_report.py", data, "--dataset-id", "fx_ner")
    out = r.stdout + r.stderr
    check("extraction_report: runs on the fixture", r.returncode == 0, out[-400:])
    check(
        "extraction_report: reads both items and their 3 gold entities",
        "2 item(s), 3 gold entities" in out,
        out[:200],
    )
    # mean f1, micro f1, micro P, micro R. The half arm: item a 1.0, item b P 1 R 0.5 F1 2/3, mean 5/6;
    # pooled tp 2 fp 0 fn 1: P 1, R 2/3, F1 0.8.
    p, h = row_of(r.stdout, "fx_perfect_v1"), row_of(r.stdout, "fx_half_v1")
    check("extraction_report: a perfect arm scores 1 on every column", p[:4] == [1.0, 1.0, 1.0, 1.0], p)
    check(
        "extraction_report: the arm missing one of three entities: mean F1 5/6, micro F1 0.8, P 1, R 2/3",
        len(h) >= 4 and close(h[0], 5 / 6) and close(h[1], 0.8) and close(h[2], 1.0) and close(h[3], 2 / 3),
        h,
    )


def test_extraction_arm(tmp: Path) -> None:
    """--arm on the half arm: per type, the organization it missed scores 0, the rest 1."""
    r = tool("extraction_report.py", tmp / "ner", "--dataset-id", "fx_ner", "--arm", "fx_half_v1")
    per = {}
    for ln in r.stdout[r.stdout.find("PER TYPE") :].splitlines()[2:5]:
        parts = ln.split()
        if len(parts) == 5:
            per[parts[0]] = [float(x) for x in parts[1:4]]
    check(
        "extraction_report --arm: per type, location and person 1, the missed organization 0",
        per == {"location": [1.0, 1.0, 1.0], "organization": [0.0, 0.0, 0.0], "person": [1.0, 1.0, 1.0]},
        per or r.stdout[-400:],
    )


def test_retrieval(tmp: Path) -> None:
    data = tmp / "ret"
    write_gold(data, "fx_ret", {"q1": [{"doc_id": "d1", "score": 1}, {"doc_id": "d2", "score": 1}]})
    write_run(
        data,
        "all",
        "fx_ret",
        "fx_all_v1",
        [
            {
                "item_id": "q1",
                "_meta": {"first_stage": ["d3", "d1", "d4", "d2"], "ranking": ["d1", "d2", "d3", "d4"]},
            }
        ],
        {"ndcg_10": 1.0},
    )
    write_run(
        data,
        "part",
        "fx_ret",
        "fx_part_v1",
        [{"item_id": "q1", "_meta": {"first_stage": ["d3", "d1"], "ranking": ["d1", "d3"]}}],
        {"ndcg_10": 0.5},
    )
    r = tool("retrieval_report.py", data, "--dataset-id", "fx_ret", "--arm", "fx_all_v1")
    out = r.stdout + r.stderr
    check("retrieval_report: runs on the fixture", r.returncode == 0, out[-400:])
    check("retrieval_report: one query, two arms", "1 queries, 2 arm(s)" in out, out[:200])
    # nDCG@10, ceiling. Every relevant document among the candidates: ceiling 1. Only d1 of
    # {d1, d2}: the best order puts d1 first, gain 1 against the ideal 1 + 1/log2(3).
    a, p = row_of(r.stdout, "fx_all_v1"), row_of(r.stdout, "fx_part_v1")
    partial = 1 / (1 + 1 / math.log2(3))
    check(
        "retrieval_report: an arm with every relevant candidate has ceiling 1",
        len(a) >= 2 and a[:2] == [1.0, 1.0],
        a,
    )
    check(
        f"retrieval_report: an arm missing one relevant candidate: nDCG as recorded, ceiling {partial:.4f}",
        len(p) >= 2 and close(p[0], 0.5) and close(p[1], partial),
        p,
    )
    check(
        "retrieval_report --arm: both relevant documents moved up by the reranker",
        "moved up 2   unchanged 0   moved DOWN 0" in r.stdout,
        r.stdout[-300:],
    )


def test_classification(tmp: Path) -> None:
    data = tmp / "cls"
    write_gold(data, "fx_cls", {"i1": "A", "i2": "A", "i3": "B", "i4": "B"})
    preds = {"i1": "A", "i2": "B", "i3": "B", "i4": "B"}
    write_run(
        data,
        "c1",
        "fx_cls",
        "fx_arm_v1",
        [{"item_id": i, "_meta": {"predicted": v}} for i, v in preds.items()],
    )
    r = tool("classification_report.py", data, "--dataset-id", "fx_cls")
    out = r.stdout + r.stderr
    check("classification_report: runs on the fixture", r.returncode == 0, out[-400:])
    # n, accuracy, macro_f1, unparsed, worst_f1. A: tp 1 fn 1, F1 2/3; B: tp 2 fp 1, F1 0.8;
    # accuracy 3/4, macro (2/3 + 0.8) / 2, worst class A.
    c = row_of(r.stdout, "fx_arm_v1")
    check(
        "classification_report: accuracy 0.75, macro-F1 0.7333, worst class A at 2/3",
        len(c) >= 4
        and close(c[0], 0.75)
        and close(c[1], (2 / 3 + 0.8) / 2)
        and close(c[2], 0.0)
        and close(c[3], 2 / 3)
        and r.stdout.rstrip().splitlines()
        and any(
            ln.split()[:1] == ["fx_arm_v1"] and ln.rstrip().endswith("A") for ln in r.stdout.splitlines()
        ),
        c,
    )
    r = tool("classification_report.py", data, "--dataset-id", "fx_cls", "--arm", "fx_arm_v1")
    matrix = {
        ln.split()[0]: ln.split()[1:]
        for ln in r.stdout[r.stdout.find("CONFUSION MATRIX") :].splitlines()[2:4]
        if ln.split()
    }
    check(
        "classification_report --arm: the confusion matrix, gold A read as B once, B always B",
        matrix == {"A": ["1", "1", "0"], "B": ["0", "2", "0"]},
        matrix or r.stdout[-400:],
    )
    write_run(data, "c2", "fx_cls_other", "fx_other_v1", [{"item_id": "z9", "_meta": {"predicted": "A"}}])
    write_gold(data, "fx_cls_other", {"i1": "A"})
    r = tool("classification_report.py", data, "--dataset-id", "fx_cls_other")
    check(
        "classification_report: no run scored a gold item: refused in words, not a traceback",
        r.returncode != 0
        and "scored an item the gold references have" in r.stderr
        and "Traceback" not in r.stderr,
        (r.stdout + r.stderr)[-300:],
    )


def test_manifest_only(tmp: Path) -> None:
    """A fresh checkout: the gold directory holds its manifest only. Each tool refuses."""
    data = tmp / "fresh"
    for script, ds in (
        ("extraction_report.py", "fx_ner"),
        ("retrieval_report.py", "fx_ret"),
        ("classification_report.py", "fx_cls"),
    ):
        g = data / "references" / "gold" / ds
        g.mkdir(parents=True)
        (g / "manifest.json").write_text("{}", encoding="utf-8")
        write_run(
            data, f"r_{ds}", ds, f"{ds}_v1", [{"item_id": "a", "_meta": {"predicted": "A"}}], {"ndcg_10": 0.1}
        )
        r = tool(script, data, "--dataset-id", ds)
        check(
            f"{script}: gold references that are only a manifest are refused, naming the fetch",
            r.returncode != 0 and "are not on this machine" in r.stderr and "make data" in r.stderr,
            (r.stdout + r.stderr)[-300:],
        )


def test_goal_decisions() -> None:
    """On this repository's own goals and runs: one row per goal and deciding dataset, and the
    recommendation `evh goals` prints for that goal."""
    r = tool("goal_decisions.py", None)
    check("goal_decisions: runs on the repository", r.returncode == 0, r.stderr[-300:])
    try:
        rows = json.loads(r.stdout)
    except ValueError:
        rows = []
    goals = {p.stem for p in (HARNESS / "data" / "goals").glob("*.yaml")}
    check(
        f"goal_decisions: a row for each of the repository's {len(goals)} goals",
        bool(goals) and {x.get("goal_id") for x in rows} == goals,
        sorted({x.get("goal_id") for x in rows} ^ goals),
    )
    env = {k: v for k, v in os.environ.items() if k not in ("EVAL_HOME", "EVAL_DATA_DIR", "EVAL_RUNS_DIR")}
    g = subprocess.run(
        [sys.executable, "-m", "evaluation_harness", "goals"],
        cwd=HARNESS,
        capture_output=True,
        text=True,
        env=env,
    )
    # Columns are separated by two or more spaces (a dataset list has single ones inside it).
    lines = [re.split(r"\s{2,}", ln.strip()) for ln in g.stdout.splitlines()]
    head = next((c for c in lines if c[:1] == ["goal"]), [])
    col = head.index("recommended") if "recommended" in head else -1
    cli = {c[0]: c[col] for c in lines if col >= 0 and len(c) == len(head) and c[0] in goals}
    by_goal: dict = {}
    for x in rows:
        by_goal.setdefault(x["goal_id"], set()).add((x.get("recommended") or "none yet").rsplit("/", 1)[-1])
    # The CLI names one recommendation per goal (its deciding dataset's); it must be one of the
    # goal's rows here.
    differ = [gid for gid, rec in cli.items() if rec not in by_goal.get(gid, set())]
    check(
        "goal_decisions: each goal's recommendation is the one `evh goals` prints",
        bool(cli) and not differ,
        f"differ: {differ}; cli {cli}",
    )


def main() -> int:
    print("the report tools compute what they say\n")
    tmp = Path(tempfile.mkdtemp(prefix="evh-report-tools-"))
    try:
        test_extraction(tmp)
        test_extraction_arm(tmp)
        test_retrieval(tmp)
        test_classification(tmp)
        test_manifest_only(tmp)
        test_goal_decisions()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return summary()


if __name__ == "__main__":
    raise SystemExit(main())
