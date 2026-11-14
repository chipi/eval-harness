#!/usr/bin/env python3
"""The model's runs, rounds and goals take a data root, and each thing has one listing (RFC-032 step 8), in the suite's
store.

    python tests/test_model_data_root.py

A project `evh init` makes, with a goal, a dataset, a gold reference, three systems' runs, a closed round with their
arms, a baseline, a label set made on another dataset (its labels follow the items by their bytes), picks, a tag set, a
capture and a judge's verdicts. It is copied as it stands (the release's copy of a project's data, files on disk) before
the sqlite store takes the project in. Then:

- the catalog adapter over the copy gives what it gives over the project: its arms, rounds (their arms in play and
  retired), references, captures, label sets, coverage and agreement, the labels of an item, the picks waiting, the tag
  counts, the spend and the baselines; and the round's evidence and the goal's status, computed from the copy, are the
  project's;
- they are the copy's: a copy changed after it was made (a run's rows, the materialized items) gives other evidence and
  another status, and the project's are as they were;
- one listing per entity: a reference's item count is its manifest's (`n_items`), not a count of the texts in its
  folder; label coverage is one decision for `evh labels` and the catalog (the catalog also counts the labels whose text a
  release does not keep); a captures listing for `evh captures` and the catalog; picks and tag counts are read through
  `_picks` and `_tags`; the judge spend the catalog charts is what `evh cost-report` counts, estimated apart;
- the comparison and a model's state live in the model: `catalog_serve.compare` is `model.compare.compare`, a round's
  evidence imports no server, `catalog_models` reads a model's state from `model.models`.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
tmp = Path(tempfile.mkdtemp(prefix="evh-data-root-"))
proj = tmp / "proj"
copy = tmp / "copy"
proj.mkdir()
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
import _runstore  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _common, _label_sets, _outputs, _picks, _rounds, _store, _tags, catalog_models  # noqa: E402
from evaluation_harness import catalog_serve as cs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.catalog_adapter import HarnessAdapter  # noqa: E402
from evaluation_harness.model import compare as model_compare  # noqa: E402
from evaluation_harness.model import dataset_views  # noqa: E402
from evaluation_harness.model import datasets as model_datasets  # noqa: E402
from evaluation_harness.model import goals as model_goals  # noqa: E402
from evaluation_harness.model import models as model_models  # noqa: E402
from evaluation_harness.model import rounds as model_rounds  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402
from evaluation_harness.model import spend as model_spend  # noqa: E402

env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_BUILD_REF="test-model-data-root")
DATA = proj / "data"
ITEMS = [f"i{n}" for n in range(6)]
SHA = {i: f"{n + 1:064x}" for n, i in enumerate(ITEMS)}
SCORES = {
    "sys_a": [1, 1, 1, 1, 1, 0],
    "sys_b": [1, 1, 0, 1, 0, 0],
    "sys_c": [0, 0, 1, 0, 0, 0],
}


def evh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), *args], cwd=proj, env=env, capture_output=True,
        text=True, stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def put(data: Path, rel: str, text: str) -> None:
    f = data / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")


def putj(data: Path, rel: str, doc: object) -> None:
    put(data, rel, json.dumps(doc, indent=2) + "\n")


def make_run(data: Path, system: str, scores: list[int], in_round: bool = True) -> None:
    rid = f"{system[-1]}_1"
    putj(data, f"runs/{rid}/run.json", {
        "run_id": rid, "system_id": system, "dataset_id": "ds_v1", "purpose": "run",
        **({"round": "r1", "goal": "g1"} if in_round else {}),
        "fingerprint": {"data": {"reference_id": "gold/ds_v1"}}, "created_at": "2026-11-01T10:00:00Z",
    })  # fmt: skip
    key = "0" * 12 + "@gold.ds_v1"
    putj(data, f"runs/{rid}/scores/{key}/score.json",
         {"scorer": "0" * 12, "reference": "gold/ds_v1", "label": "", "first": True})  # fmt: skip
    putj(data, f"runs/{rid}/scores/{key}/metrics.json", {
        "primary_metric": "acc", "metric_kinds": {"acc": "quality", "cost_usd": "cost"},
        "scores": {"acc": sum(scores) / len(scores), "total_cost_usd": 0.01},
    })  # fmt: skip
    per_item = {"sys_a": 0.001, "sys_b": 0.002, "sys_c": 0.003}.get(
        system, 0.004
    )  # costs that differ item by item
    put(data, f"runs/{rid}/scores/{key}/predictions.jsonl",
        "".join(json.dumps({"item_id": i, "acc": float(s), "cost_usd": per_item * (1 + 0.1 * n)})
                + "\n" for n, (i, s) in enumerate(zip(ITEMS, scores))))  # fmt: skip


def build(data: Path) -> None:
    putj(data, "datasets/ds_v1.json", {
        "dataset_id": "ds_v1", "version": "1.0", "created_at": "2026-11-10T00:00:00Z", "made_from": {"capture": "cap_1"},
        "items": [{"item_id": i, "source_path": f"{i}.txt", "source_sha256": SHA[i]} for i in ITEMS],
    })  # fmt: skip
    put(data, "materialized/ds_v1/i0.txt", "item zero\n")
    put(data, "goals/g1.yaml", yaml.safe_dump({
        "goal_id": "g1", "title": "G one", "success_criteria": {"primary": {"measure": "acc", "direction": "higher"}},
        "datasets": [{"dataset_id": "ds_v1", "role": "validation"}], "references": [{"reference_id": "gold/ds_v1"}],
    }, sort_keys=False))  # fmt: skip
    for tier, texts in (("gold", True), ("silver", False)):
        putj(data, f"references/{tier}/ds_v1/manifest.json", {
            "dataset_id": "ds_v1", "tier": tier, "n_items": 6, "items_sha256": {i: SHA[i] for i in ITEMS},
            "caveat": "c", "reason": "r", "promoted_from": {}, "authored_by": "sys_c",
        })  # fmt: skip
        for i in ITEMS[:5] if texts else []:  # the gold's manifest says 6 items, its folder holds 5 texts
            put(data, f"references/{tier}/ds_v1/{i}.txt", f"{i} right\n")
    for system, scores in SCORES.items():
        make_run(data, system, scores)
    put(data, "rounds/g1/r1.yaml", yaml.safe_dump({
        "round_id": "r1", "goal": "g1", "dataset_id": "ds_v1", "hypothesis": "h", "status": "closed",
        "baseline": "b_1", "opened_at": "2026-11-01T00:00:00Z", "closed_at": "2026-11-09T00:00:00Z",
        "arms": [{"system": s, "runs": [f"{s[-1]}_1"], "entered": {"how": "ran", "at": "2026-11-01T00:00:00Z"}}
                 for s in SCORES] + [{"system": "sys_gone", "runs": [], "entered": {"how": "ran", "at": "2026-11-01T00:00:00Z"},
                                      "retired": {"at": "2026-11-02T00:00:00Z", "reason": "x"}}],
        "conclusion": {"text": "a leads"},
    }, sort_keys=False))  # fmt: skip
    putj(data, "baselines/g1/ds_v1/1.json", {"version": 1, "goal": "g1", "dataset_id": "ds_v1", "promoted_from": "b_1",
                                             "promoted_at": "2026-11-09T00:00:00Z", "reason": "r"})  # fmt: skip
    # a label set made on another dataset: its labels follow the items by their bytes (i0, i1 here; i2 is ambiguous there)
    putj(data, "labels/ds_other/lab_o/labels.json", {
        "dataset_id": "ds_other", "set": "lab_o", "source": {"kind": "person", "by": "o"}, "created_at": "2026-11-05T00:00:00Z",
        "n_items": 4, "guideline": None, "items": {
            "o0": {"item_sha256": SHA["i0"]}, "o1": {"item_sha256": SHA["i1"]},
            "o2": {"item_sha256": SHA["i2"]}, "o2b": {"item_sha256": SHA["i2"]}},
    })  # fmt: skip
    for k, t in {"o0": "yes", "o1": "no", "o2": "yes", "o2b": "no"}.items():
        put(data, f"labels/ds_other/lab_o/{k}.txt", t + "\n")
    putj(data, "labels/ds_v1/lab_h/labels.json", {
        "dataset_id": "ds_v1", "set": "lab_h", "source": {"kind": "person", "by": "h"}, "created_at": "2026-11-06T00:00:00Z",
        "n_items": 3, "guideline": None, "items": {i: {"item_sha256": SHA[i]} for i in ("i0", "i1", "i3")},
    })  # fmt: skip
    for k, t in {"i0": "yes", "i1": "yes", "i3": "no"}.items():
        put(data, f"labels/ds_v1/lab_h/{k}.txt", t + "\n")
    put(data, "picks.jsonl", "\n".join([
        json.dumps({"action": "pick", "item": "p1", "from": "prod", "for": ["ds_v1"]}),
        "not json",
        "[1, 2]",
        json.dumps({"action": "pick", "item": "p2", "from": "prod", "for": ["ds_v1"]}),
        json.dumps({"action": "drop", "item": "p2", "from": "prod"}),
    ]) + "\n")  # fmt: skip
    putj(data, "tags/ds_v1/t1/tags.json", {
        "kind": "tag-set", "dataset_id": "ds_v1", "set": "t1", "failure_modes": "m", "created_at": "x",
        "runs": {"a_1": {"i0": {"modes": ["wrong", "long"]}, "i1": {"modes": []}}, "b_1": {"i0": {"modes": ["wrong"]}}},
    })  # fmt: skip
    putj(data, "captures/cap_1/capture.json", {
        "capture_id": "cap_1", "importer": "x", "captured_at": "2026-11-01T00:00:00Z", "n_records": 2, "scrubbed": False,
        "query": {"q": 1}, "records": [{"id": "1", "created_at": "2026-10-01T00:00:00Z"}, {"id": "2", "created_at": "2026-10-02T00:00:00Z"}],
    })  # fmt: skip
    putj(data, "judging-sets/set1.json", {"dataset_id": "ds_v1", "arms": []})
    for name, v in {
        "v1": {
            "cost_usd": 0.5,
            "cost_known": True,
            "created_at": "2026-11-12T10:00:00Z",
            "tokens_in": 10,
            "tokens_out": 5,
        },
        "v2": {"cost_usd": 0.25, "cost_known": True, "created_at": "2026-11-12T11:00:00Z"},
        "v3": {"cost_usd": 0.125, "cost_known": False, "created_at": "2026-11-13T10:00:00Z", "tokens_in": 7},
    }.items():
        putj(data, f"judge-verdicts/js1/set1/j1/{name}.json", v)


def scrub(d: dict) -> dict:
    """A listing row without the folder it was read from (the copy's is another)."""
    return {k: v for k, v in d.items() if k != "dir"}


def listings(A: HarnessAdapter) -> dict:
    return {
        "arms": A.arms(),
        "rounds": A.rounds(),
        "references": [scrub(r) for r in A.references()],
        "captures": A.captures(),
        "label_sets": [scrub(s) for s in A.label_sets()],
        "coverage": A.label_coverage("ds_v1"),
        "item_labels": {i: A.item_labels("ds_v1", i) for i in ITEMS},
        "picks": A.picks_waiting("ds_v1"),
        "tags": {a: A.tag_counts("ds_v1", a) for a in A.arms()},
        "spend": A.spend(),
        "baselines": A.baselines(),
        "datasets": A.datasets(),
        "goals": A.goals(),
    }


def evidence(A: HarnessAdapter, data: Path | None) -> dict:
    rnd = _rounds.find("g1", "r1", data)
    assert rnd is not None
    return model_rounds.evidence("g1", rnd, A)


try:
    evh("init")
    build(DATA)
    shutil.copytree(DATA, copy / "data", ignore=shutil.ignore_patterns("project.sqlite*"))
    _runstore.migrate_in(proj)
    _outputs.reset()
    _store.close()
    CD = copy / "data"

    A, C = HarnessAdapter(), HarnessAdapter(CD)
    LP, LC = listings(A), listings(C)
    check(
        "the project's own data is what the adapter's default reads (a copy is another directory)",
        A.data_dir == _common.DATA and C.data_dir == CD and LP["arms"] and len(LP["arms"]) == 3,
        LP["arms"],
    )
    for name in LP:
        check(f"the adapter over a copy of the data lists the same {name} as over the project", LC[name] == LP[name], f"{LP[name]!r:.400} != {LC[name]!r:.400}")  # fmt: skip
    r1 = next(r for r in LP["rounds"] if r["round_id"] == "r1")
    check(
        "a round's arms in play are the stored ones the index has, and its retired ones are named",
        r1["arms"] == sorted(f"runs/ds_v1/{s}" for s in SCORES)
        and r1["retired_arms"] == ["runs/ds_v1/sys_gone"],
        (r1["arms"], r1["retired_arms"]),
    )

    ev_p, ev_c = evidence(A, None), evidence(C, CD)
    check(
        "a round's evidence read from a copy of the data is the project's: the leader, the tests, the notes",
        ev_p == ev_c and ev_p["leader"] == "runs/ds_v1/sys_a" and ev_p["rows"] and ev_p["against"],
        (ev_p.get("leader"), len(ev_p.get("rows") or []), len(ev_p.get("against") or [])),
    )
    check(
        "evidence names the data it reads: no data given, the adapter's is read",
        evidence(C, None) == ev_c,
    )
    st_p, st_c = model_goals.status("g1"), model_goals.status("g1", data=CD)
    ds0 = st_p["datasets"][0]
    check(
        "a goal's status read from a copy is the project's: its datasets, references, runs, arms, baseline and rounds",
        st_p == st_c
        and ds0["made"]
        and ds0["materialized"]
        and ds0["runs"] == 3
        and ds0["arms"] == 3
        and ds0["references"] == ["gold/ds_v1", "silver/ds_v1"]
        and ds0["baseline"] == {"version": 1, "run": "b_1"}
        and st_p["rounds"]
        == [
            {"round": "r1", "status": "closed", "dataset": "ds_v1", "question": "h", "arms": 3, "retired": 1}
        ],
        st_p,
    )
    check(
        "the run index and the rounds' files are listed from the data directory asked",
        model_runs.run_ids(CD) == model_runs.run_ids() == ["a_1", "b_1", "c_1"]
        and [r["round_id"] for r in _rounds.load_rounds("g1", CD)] == ["r1"]
        and _rounds.path_of("g1", "r1", CD) == CD / "rounds" / "g1" / "r1.yaml",
    )

    # A copy changed after it was made is read as it is: nothing comes from the project.
    sd = CD / "runs" / "a_1" / "scores" / ("0" * 12 + "@gold.ds_v1")
    (sd / "predictions.jsonl").write_text(
        "".join(
            json.dumps({"item_id": i, "acc": float(s), "cost_usd": 0.001}) + "\n"
            for i, s in zip(ITEMS, [0, 0, 0, 0, 0, 1])
        )
    )
    shutil.rmtree(CD / "materialized")
    shutil.rmtree(CD / "runs" / "c_1")
    make_run(CD, "sys_x", [1, 1, 1, 1, 1, 1], in_round=False)  # a run the project has not
    (CD / "baselines" / "g1" / "ds_v1" / "1.json").unlink()
    (CD / "picks.jsonl").unlink()
    (CD / "tags" / "ds_v1" / "t1" / "tags.json").unlink()
    shutil.rmtree(CD / "captures")
    shutil.rmtree(CD / "references" / "silver")
    (CD / "judge-verdicts" / "js1" / "set1" / "j1" / "v3.json").unlink()
    put(CD, "rounds/g1/r2.yaml", yaml.safe_dump({"round_id": "r2", "goal": "g1", "dataset_id": "ds_v1", "from": "r9",
                                                  "hypothesis": "h2", "status": "open", "opened_at": "2026-11-10T00:00:00Z", "arms": []}, sort_keys=False))  # fmt: skip
    C2 = HarnessAdapter(CD)
    ev_2, st_2 = evidence(C2, CD), model_goals.status("g1", data=CD)
    d2 = st_2["datasets"][0]
    check(
        "evidence read from a changed copy is the copy's: sys_a no longer leads there, and the project's is as it was",
        ev_2["leader"] != ev_p["leader"]
        and evidence(HarnessAdapter(), None) == ev_p
        and round(ev_p["spent"], 8) == 0.03
        and round(ev_2["spent"], 8) == 0.02,
        (ev_2.get("leader"), ev_p.get("leader"), ev_2.get("spent"), ev_p.get("spent")),
    )
    check(
        "evidence names the data it reads: from a changed copy with no data given, the adapter's is read",
        evidence(C2, None) == ev_2 and evidence(C2, None) != ev_p,
    )
    check(
        "status read from a changed copy is the copy's: no materialized copy, other runs and arms, no baseline, two rounds; the "
        "project's as it was",
        not d2["materialized"]
        and d2["runs"] == 3
        and d2["arms"] == 3
        and d2["baseline"] is None
        and model_goals.status("g1") == st_p
        and [r["round"] for r in st_2["rounds"]] == ["r1", "r2"],
        d2,
    )
    bad = _rounds.problems(CD)
    check(
        "validate's check of the rounds reads the data directory asked: the copy's round names a run the copy has lost "
        "and another a round it has not, the project's rounds are whole",
        _rounds.problems() == []
        and len(bad) == 2
        and "c_1 is not a run of sys_c" in bad[0]
        and bad[0].startswith("rounds/g1/r1.yaml")
        and bad[1] == "rounds/g1/r2.yaml: from 'r9', which does not exist",
        (_rounds.problems(), bad),
    )
    check(
        "the silver reference's author is read from the data directory's manifests: gone from the copy, none there",
        model_rounds._silver_authors(HarnessAdapter(), "ds_v1") == [("silver/ds_v1", "runs/ds_v1/sys_c")]
        and model_rounds._silver_authors(C2, "ds_v1") == [],
    )
    check(
        "the listings of a changed copy are the copy's: no picks, no baseline, no tags, no captures, another set of arms and runs, "
        "another round list; the project's as they were",
        C2.picks_waiting("ds_v1") == []
        and C2.baselines() == []
        and C2.arms() == ["runs/ds_v1/sys_a", "runs/ds_v1/sys_b", "runs/ds_v1/sys_x"]
        and C2.tag_counts("ds_v1", "runs/ds_v1/sys_a") is None
        and [r["round_id"] for r in C2.rounds()] == ["r1", "r2"]
        and C2.rounds()[1]["arms"] == []
        and model_runs.run_ids(CD) == ["a_1", "b_1", "x_1"]
        and [r["round_id"] for r in _rounds.load_rounds(data=CD)] == ["r1", "r2"]
        and C2.captures() == []
        and [r["id"] for r in C2.references()] == ["gold/ds_v1"]
        and [(x["at"], x["usd"]) for x in C2.spend() if x["kind"] == "judge"] == [("2026-11-12", 0.75)]
        and listings(HarnessAdapter()) == LP,
    )

    put(CD, "goals/g1.yaml", yaml.safe_dump({
        "goal_id": "g1", "title": "G two", "success_criteria": {"primary": {"measure": "cost_usd", "direction": "lower"}},
        "datasets": [{"dataset_id": "ds_v1", "role": "validation"}],
    }, sort_keys=False))  # fmt: skip
    ev_3 = evidence(HarnessAdapter(CD), CD)
    check(
        "a round's evidence reads the goal from the data directory: the copy's goal measures the cost, lower the better",
        ev_3["metric"] == "cost_usd" and evidence(HarnessAdapter(), None)["metric"] == "acc" and ev_3 != ev_p,
        ev_3["metric"],
    )
    put(CD, "goals/g1.yaml", yaml.safe_dump({
        "goal_id": "g1", "title": "G two", "success_criteria": {"primary": {"measure": "acc", "direction": "higher"}},
        "datasets": [{"dataset_id": "ds_v1", "role": "validation", "cluster": "grp"}],
    }, sort_keys=False))  # fmt: skip
    C3 = HarnessAdapter(CD)
    model_compare.set_adapter(C3)
    by_copy = model_compare._goal_cluster_on("ds_v1")
    model_compare.set_adapter(A)
    check(
        "the goals are the data directory's: the copy's goal is another title and clusters the tests, the project's does not",
        [g["title"] for g in C3.goals()] == ["G two"]
        and [g["title"] for g in A.goals()] == ["G one"]
        and by_copy == "grp"
        and model_compare._goal_cluster_on("ds_v1") is None
        and _common.load_goals()["g1"]["title"] == "G one",
        (by_copy, [g["title"] for g in C3.goals()]),
    )

    # -- one listing per entity -------------------------------------------------------------------------------------
    texts = len(list((CD / "references" / "gold" / "ds_v1").glob("*.txt")))
    refs = {r["id"]: r for r in LP["references"]}
    check(
        "a reference's item count is its manifest's n_items, the same in every listing, fetched or not",
        refs["gold/ds_v1"]["items"] == refs["silver/ds_v1"]["items"] == 6
        and refs["silver/ds_v1"]["fetched"]
        and not refs["gold/ds_v1"]["fetched"]
        and texts == 5
        and model_datasets.reference_items({"n_items": 4, "items_sha256": {"a": "x"}}) == 4
        and model_datasets.reference_items({"items_sha256": {"a": "x", "b": "y"}}) == 2
        and {r["reference"]: r["items"] for r in dataset_views.list_references()}
        == {"gold/ds_v1": 6, "silver/ds_v1": 6},
        (refs["gold/ds_v1"]["items"], refs["silver/ds_v1"]["items"]),
    )
    cov = _label_sets.coverage("ds_v1")
    by_set = {c["set"]: c["items"] for c in cov}
    check(
        "label coverage is one decision for `evh labels` and the catalog: by id on the set's dataset, by the item's bytes on "
        "another's, an ambiguous label (two items alike, labelled differently) carried to none",
        by_set == {"lab_h": ["i0", "i1", "i3"], "lab_o": ["i0", "i1"]}
        and {s["set"]: s["covers"] for s in LP["coverage"]["sets"]} == by_set
        and [(p["a"], p["b"], p["both"], p["same"]) for p in LP["coverage"]["agreement"]]
        == [("ds_other/lab_o", "ds_v1/lab_h", 2, 1)]
        and [p["same"] for p in _label_sets.agreement("ds_v1")] == [1],
        (by_set, LP["coverage"]["agreement"]),
    )
    check(
        "an item's labels are the sets' rows that label it, read through the same decision",
        [(x["set"], x["text"]) for x in LP["item_labels"]["i0"]]
        == [("ds_other/lab_o", "yes"), ("ds_v1/lab_h", "yes")]
        and [x["set"] for x in LP["item_labels"]["i2"]] == []
        and [x["set"] for x in LP["item_labels"]["i3"]] == ["ds_v1/lab_h"],
        LP["item_labels"],
    )
    # a release keeps labels.json only: the catalog still counts what the labels cover, the command (which reads texts) has none
    for f in (CD / "labels").rglob("*.txt"):
        f.unlink()
    cd = HarnessAdapter(CD)
    check(
        "without label texts (a release's copy) the catalog's coverage still lists the items a set labels, with no agreement; "
        "`evh labels` over the same tree lists none (it reads the texts)",
        {s["set"]: s["covers"] for s in cd.label_coverage("ds_v1")["sets"]} == by_set
        and cd.label_coverage("ds_v1")["agreement"] == []
        and _label_sets.coverage("ds_v1", CD) == []
        and [x["text"] for x in cd.item_labels("ds_v1", "i0")] == [None, None],
        cd.label_coverage("ds_v1"),
    )
    ds1 = json.loads((CD / "datasets" / "ds_v1.json").read_text())
    ds1["items"] = [it for it in ds1["items"] if it["item_id"] != "i3"]
    putj(CD, "datasets/ds_v1.json", ds1)
    only = [t for *_, t in _label_sets.matches("ds_v1", DATA, only="i0")]
    check(
        "labels follow the items of the dataset asked: the copy's dataset has no i3, so its set no longer covers it; the "
        "project's still does; `only` reads one item's labels",
        {s["set"]: s["covers"] for s in HarnessAdapter(CD).label_coverage("ds_v1")["sets"]}
        == {"lab_h": ["i0", "i1"], "lab_o": ["i0", "i1"]}
        and "i3" in {i for c in _label_sets.coverage("ds_v1", DATA, texts=False) for i in c["items"]}
        and only
        and all(set(t) <= {"i0"} for t in only),
    )
    shutil.rmtree(CD / "labels" / "ds_v1" / "lab_h")
    check(
        "the label sets are the data directory's: with one gone from the copy the catalog lists the other, the project still both",
        [s["id"] for s in HarnessAdapter(CD).label_sets()] == ["ds_other/lab_o"]
        and [s["set"] for s in HarnessAdapter(CD).label_coverage("ds_v1")["sets"]] == ["lab_o"]
        and [s["id"] for s in HarnessAdapter().label_sets()] == ["ds_other/lab_o", "ds_v1/lab_h"],
    )
    caps_cmd = json.loads(evh("captures", "--json").stdout)["captures"]
    check(
        "captures: `evh captures` and the catalog list one thing (the dataset made from each, its first and last record)",
        caps_cmd == LP["captures"] == dataset_views.capture_views()
        and caps_cmd[0]["datasets"] == ["ds_v1"]
        and caps_cmd[0]["first"] == "2026-10-01T00:00:00Z"
        and caps_cmd[0]["records"] == 2
        and [c["capture"] for c in dataset_views.list_captures()] == ["cap_1"],
        caps_cmd,
    )
    try:
        _picks.waiting("ds_v1", data=_common.DATA)
        strict = False
    except ValueError:
        strict = True
    check(
        "picks: the waiting list is _picks', whatever data directory; a line that is no JSON is the command's refusal and the "
        "catalog's skip",
        [p["item"] for p in LP["picks"]] == ["p1"]
        and [p["item"] for p in _picks.waiting("ds_v1", data=DATA, strict=False)] == ["p1"]
        and strict,
        LP["picks"],
    )
    tg = _tags.counts("ds_v1", {"a_1": "arm_a"}, DATA)["arm_a"]
    check(
        "tag counts: the catalog's arm counts are _tags' per-arm counts (outputs read, tagged, each mode)",
        LP["tags"]["runs/ds_v1/sys_a"] == {"outputs": 2, "tagged": 1, "modes": {"wrong": 1, "long": 1}}
        and tg == {"tagged": 1, "outputs": 2, "modes": {"wrong": 1, "long": 1}}
        and LP["tags"]["runs/ds_v1/sys_c"] is None
        and [x["set"] for x in _tags.tag_sets("ds_v1", DATA)] == ["t1"]
        and _tags.tag_sets("ds_v1", CD) == [],
        LP["tags"],
    )

    # -- judge spend: one computation for `evh cost-report` and the catalog's chart ---------------------------------------
    cr = json.loads(evh("cost-report", "--json").stdout)["result"]["values"]["judging"]
    judge = [s for s in LP["spend"] if s["kind"] == "judge"]
    check(
        "judge spend: what the catalog charts is what cost-report counts (billed), the unpriced calls shown apart",
        round(sum(r["billed"] for r in cr), 8) == round(sum(s["usd"] or 0 for s in judge), 8) == 0.75
        and round(sum(r["estimated"] for r in cr), 8)
        == round(sum(s["estimated_usd"] or 0 for s in judge), 8)
        == 0.125
        and [(s["at"], s["usd"], s["estimated_usd"], s["tokens"]) for s in judge]
        == [("2026-11-12", 0.75, None, 15), ("2026-11-13", None, 0.125, 7)]
        and cr == model_spend.judge_costs()
        and cr[0]["verdicts"] == 3
        and cr[0]["estimated_verdicts"] == 1,
        (cr, judge),
    )

    # -- layering ------------------------------------------------------------------------------------------------------
    def imports(rel: str) -> set[str]:
        tree = ast.parse((HARNESS / "scripts" / rel).read_text())
        out: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom):
                out |= {n.module or ""} | {a.name for a in n.names}
            elif isinstance(n, ast.Import):
                out |= {a.name for a in n.names}
        return out

    check(
        "the comparison is the model's: catalog_serve answers its route with it, a round's evidence imports no server",
        cs.compare is model_compare.compare
        and cs.goal_clusters_on is model_compare.goal_clusters_on
        and cs.LIMITS is model_compare.LIMITS
        and not any(
            "catalog_serve" in m
            for m in imports("model/rounds.py") | imports("model/models.py") | imports("model/compare.py")
        ),
    )
    cs.set_adapter(A)
    check(
        "the server's adapter is the comparison's",
        model_compare.A is A and cs.A is A,
    )
    check(
        "a model's state is the model's: catalog_models reads it from model.models",
        catalog_models.status_of is model_models.status_of
        and model_models.status_of(
            {"deployments": [{"onboarding": {"status": "pass"}}], "smokes": {"s": {"status": "pass"}}}
        )
        == "vetted",
    )
finally:
    _outputs.reset()
    _store.close()
    shutil.rmtree(tmp, ignore_errors=True)
sys.exit(summary())
