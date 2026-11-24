"""The four projects test_reader_agreement.py reads, built in the store EVAL_STORE names (RFC-041, PLAN 0.8.1 R3): the
tutorial's, with three datasets, and R2's three look-alikes of the beta projects (`_foreign.py`), the bake-off's with one
more arm whose cost was never recorded, and a fifth that holds a 0.7 `--repeat 2` set (`purpose: repeat`, no `of`) that was
re-scored: the arm read as `rescored 3d3a6afd, repeats`, whose id is the label's slug and not the label.

    python tests/_reader_proc.py build NAME DIR      (NAME: tutorial, imported, fleet, bakeoff, rescored)

Each is built in a process of its own: the builders write through the store's in-process state, which two projects at
once would share.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _foreign  # noqa: E402
import _runstore  # noqa: E402

KIT = HERE.parent / "tutorial"
STORE = "sqlite" if _runstore.sqlite() else "files"


def tutorial(proj: Path, env: dict[str, str]) -> dict[str, Any]:
    """The tutorial's kit with three datasets: `tk_v1` (gold, a repeat set, two arms, a goal and its baseline),
    `tk_late_v1` (an arm run before the dataset had a reference and again after: two references) and `tk_hidden_v1`
    (`text: hidden`)."""
    env["EVAL_BUILD_REF"] = "test-agreement"
    b = _foreign.Build(proj, env)
    b.must("init", "--store", STORE, "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    for ds in ("tk_v1", "tk_late_v1", "tk_hidden_v1"):
        b.must("dataset-create", "--dataset-id", ds, "--source-dir", "tickets")
        b.must("dataset-materialize", "--dataset-id", ds)
    gold = ("--sheet", str(KIT / "gold"), "--set", "g", "--by", "ana")
    for ds in ("tk_v1",):
        b.must("label-import", *gold, "--dataset-id", ds)
        b.must(
            "reference-promote", "--dataset-id", ds, "--labels", "g", "--tier", "gold",
            "--reason", "The hand-written summaries decide this.", "--by", "ana",
        )  # fmt: skip
    for n, sentences in (("s1_v1", 1), ("s2_v1", 2)):
        b.put(f"systems/{n}.yaml", f"system_id: {n}\nparams:\n  provider: echo\n  sentences: {sentences}\n")
    b.must(
        "run",
        "--system",
        "s1_v1",
        "--dataset",
        "tk_v1",
        "--repeat",
        "2",
        "--run-id",
        "s1_v1_20261110T100000Z",
    )
    b.must("run", "--system", "s2_v1", "--dataset", "tk_v1", "--run-id", "s2_v1_20261110T110000Z")
    b.must("run", "--system", "s1_v1", "--dataset", "tk_late_v1", "--run-id", "s1_v1_20261110T120000Z")
    b.must("label-import", *gold, "--dataset-id", "tk_late_v1")
    b.must(
        "reference-promote", "--dataset-id", "tk_late_v1", "--labels", "g", "--tier", "gold",
        "--reason", "The hand-written summaries decide this too.", "--by", "ana",
    )  # fmt: skip
    b.must("run", "--system", "s1_v1", "--dataset", "tk_late_v1", "--run-id", "s1_v1_20261110T130000Z")
    b.must("run", "--system", "s2_v1", "--dataset", "tk_hidden_v1", "--run-id", "s2_v1_20261110T140000Z")
    # a run re-scored in place: its score's created_at is the re-score's time, its id keeps when it was measured
    rid = "s2_v1_20261110T140000Z"
    for score in _runstore.listdir(proj, f"runs/{rid}/scores"):
        rel = f"runs/{rid}/scores/{score}/metrics.json"
        metrics = _runstore.read_json(proj, rel)
        metrics["derived"] = {"kind": "reparse", "from": rid, "at": "2026-11-30T09:00:00Z"}
        metrics["created_at"] = "2026-11-30T09:00:00Z"
        _runstore.write_text(proj, rel, json.dumps(metrics, indent=2) + "\n")
    rec = _runstore.read_json(proj, "datasets/tk_hidden_v1.json")
    rec["text"] = "hidden"
    _runstore.write_text(proj, "datasets/tk_hidden_v1.json", json.dumps(rec, indent=2) + "\n")
    b.must(
        "goal-new", "tickets_summary", "--set", "title=Ticket summaries",
        "--set", "statement=A one-line summary of a support ticket for the person triaging it.",
        "--set", "decision=Which system writes the summary.", "--set", "success_criteria.primary.measure=overlap_f1",
        "--set", "success_criteria.primary.direction=higher", "--set", "datasets.0.dataset_id=tk_v1",
        "--set", "datasets.0.role=test",
    )  # fmt: skip
    b.must(
        "run-promote", "--run", "s2_v1_20261110T110000Z", "--goal", "tickets_summary",
        "--reason", "It leads the goal on the kit's tickets.", "--by", "ana",
    )  # fmt: skip
    # the promoted run re-scored: the goal reads the re-score (RFC-022), on every reader
    base = "s2_v1_20261110T110000Z"
    src = _runstore.listdir(proj, f"runs/{base}/scores")[0]
    dst = "rs3d3a6afd@" + src.split("@", 1)[1]
    for rel in _runstore.files_under(proj, f"runs/{base}/scores/{src}"):
        name = rel.split(f"scores/{src}/", 1)[1]
        text = _runstore.read_text(proj, rel)
        if name == "score.json":
            meta = {**json.loads(text), "scorer": "rs3d3a6afd", "label": "rescored 3d3a6afd"}
            meta.pop("first", None)  # the run's first score is the one it made when it ran
            text = json.dumps(meta, indent=2) + "\n"
        elif name == "metrics.json":
            m = json.loads(text)
            m["derived"] = {
                "kind": "rescore",
                "from": base,
                "from_dir": f"runs/{base}",
                "at": "2026-11-28T09:00:00Z",
            }
            text = json.dumps(m, indent=2) + "\n"
        _runstore.write_text(proj, f"runs/{base}/scores/{dst}/{name}", text)
    _runstore.copy_rows(proj, f"runs/{base}/scores/{src}", f"runs/{base}/scores/{dst}")
    return {"datasets": ["tk_v1", "tk_late_v1", "tk_hidden_v1"]}


def bakeoff(proj: Path, env: dict[str, str]) -> dict[str, Any]:
    """R2's bake-off project and a system with no price on a dataset: a cost that was never recorded."""
    out = _foreign.bakeoff(proj, env)
    b = _foreign.Build(proj, {**env, "EVAL_BUILD_REF": "bakeoff-fixture-1"})
    b.put(
        "systems/local_delta.yaml",
        "system_id: local_delta\nparams:\n  provider: stub\n  model: local_delta-7b\n",
    )
    b.must(
        "run",
        "--system",
        "local_delta",
        "--dataset",
        _foreign.BAKEOFF_SMALL,
        "--run-id",
        "local_delta_20261120T150000Z",
    )
    return out


RESCORED_DS = "tickets_rescored_v1"
RESCORED_ADAPTER = """
from types import SimpleNamespace

def call_system(text, params):
    return SimpleNamespace(output=text[:40], tokens_in=10, tokens_out=5, cost_usd=None, latency_ms=None, extra={}, meta={})

def score(output, reference):
    return {"words": float(len(output.split())) + SHIFT}

PRIMARY_METRIC = "words"
SHIFT = 0
"""


def rescored(proj: Path, env: dict[str, str]) -> dict[str, Any]:
    """A `--repeat 2` set written as 0.7 wrote one (`purpose: repeat`, no `of`), then re-scored by another scorer: one
    arm under `repeats` and one under `rescored 3d3a6afd, repeats`, which `arm_prefix` slugs to `rescored-3d3a6afd-repeats`."""
    b = _foreign.Build(proj, {**env, "EVAL_BUILD_REF": "rescored-fixture-1"})
    b.init()
    shutil.copytree(KIT / "tickets", proj / "tickets")
    b.must("dataset-create", "--dataset-id", RESCORED_DS, "--source-dir", "tickets")
    b.must("dataset-materialize", "--dataset-id", RESCORED_DS)
    (proj / "a.py").write_text(RESCORED_ADAPTER, encoding="utf-8")
    b.put("systems/arm_w_v1.yaml", "system_id: arm_w_v1\nadapter: a.py\nparams:\n  provider: echo\n")
    base = "arm_w_v1_20261110T150000Z"
    b.must("run", "--system", "arm_w_v1", "--dataset", RESCORED_DS, "--repeat", "2", "--run-id", base)
    for n in (f"{base}_r1", f"{base}_r2"):
        rec = _runstore.read_json(proj, f"runs/{n}/run.json")
        _runstore.write_text(
            proj, f"runs/{n}/run.json", json.dumps({**rec, "purpose": "repeat"}, indent=2) + "\n"
        )
    (proj / "a.py").write_text(RESCORED_ADAPTER.replace("SHIFT = 0", "SHIFT = 1"), encoding="utf-8")
    b.must("rescore", "--dataset-id", RESCORED_DS, "--match", "arm_w", "--label", "rescored 3d3a6afd")
    return {"datasets": [RESCORED_DS], "runs": [f"{base}_r1", f"{base}_r2"]}


BUILDERS = {
    "tutorial": tutorial,
    "imported": _foreign.imported,
    "fleet": _foreign.fleet,
    "bakeoff": bakeoff,
    "rescored": rescored,
}


def build(name: str, proj: Path) -> dict[str, Any]:
    """The project `name` in `proj`, and a profile of each dataset (what `evh dataset-items` reads for the public flag)."""
    import os  # noqa: PLC0415

    proj.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, EVAL_HOME=str(proj), EVH_ACTOR="person:fixture")
    for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_BUILD_REF", "EVAL_GOALS_DIR", "EVH_PUBLIC"):
        env.pop(k, None)
    out = BUILDERS[name](proj, env)
    b = _foreign.Build(proj, env)
    r = b.must("dataset-list", "--json")
    for d in json.loads(r.stdout)["result"]["datasets"]:
        b.must("dataset-profile", "--dataset-id", d["dataset"])
    return out
