#!/usr/bin/env python3
"""What a sealed side's reads, a test set's looks and the prompt versions are read from: the data directory asked for
(RFC-032 step 8), in the suite's store.

    python tests/test_data_root_reads.py

A project `evh init` makes with a goal, a dataset sealed with three of its six items read (its exposure register), three
systems' runs, a closed round and a round that has a budget; then the project's data as it stands (the release's copy,
files on disk) before the sqlite store takes the project in. In the copy the register holds two other items, the goal
declares the dataset a test set with its own limit, a prompt version is recorded and one run cost more. Each reader takes
`data`: the register, the seal, the looks, the prompt versions and the round's spend are the copy's when the copy is
asked and the project's when nothing is. A score read over the copy leaves out the copy's read items (`aware`, the
adapter's own data directory), a round's evidence over the copy is computed from them, and neither is the project's.
"""

from __future__ import annotations

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
tmp = Path(tempfile.mkdtemp(prefix="evh-data-root-reads-"))
proj, copy = tmp / "proj", tmp / "copy"
proj.mkdir()
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
import _runstore  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _exposure, _looks, _outputs, _prompts, _rounds, _runs, _spend, _store  # noqa: E402
from evaluation_harness._check import check, store_under_test, summary  # noqa: E402
from evaluation_harness.catalog_adapter import HarnessAdapter  # noqa: E402
from evaluation_harness.model import rounds as model_rounds  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402

env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_BUILD_REF="test-data-root-reads")
DATA = proj / "data"
ITEMS = [f"i{n}" for n in range(6)]
SCORES = {"sys_a": [1, 1, 1, 1, 1, 0], "sys_b": [1, 1, 0, 1, 0, 0], "sys_c": [0, 0, 1, 0, 0, 0]}
PROJECT_READ, COPY_READ = ["i3", "i4", "i5"], ["i0", "i1"]


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


def register(data: Path, items: list[str]) -> None:
    put(
        data,
        "exposure/ds_v1.jsonl",
        "".join(json.dumps({"item_id": i, "what": "read", "by": "x"}) + "\n" for i in items),
    )


def make_run(data: Path, system: str, scores: list[int]) -> None:
    rid = f"{system[-1]}_1"
    putj(data, f"runs/{rid}/run.json", {
        "run_id": rid, "system_id": system, "dataset_id": "ds_v1", "purpose": "run", "round": "r1", "goal": "g1",
        "fingerprint": {"data": {"reference_id": "gold/ds_v1"}}, "created_at": "2026-11-01T10:00:00Z",
    })  # fmt: skip
    key = "0" * 12 + "@gold.ds_v1"
    putj(data, f"runs/{rid}/scores/{key}/score.json",
         {"scorer": "0" * 12, "reference": "gold/ds_v1", "label": "", "first": True})  # fmt: skip
    putj(data, f"runs/{rid}/scores/{key}/metrics.json", {
        "primary_metric": "acc", "metric_kinds": {"acc": "quality", "cost_usd": "cost"},
        "scores": {"acc": sum(scores) / len(scores), "total_cost_usd": 0.01},
    })  # fmt: skip
    put(data, f"runs/{rid}/scores/{key}/predictions.jsonl",
        "".join(json.dumps({"item_id": i, "acc": float(s)}) + "\n" for i, s in zip(ITEMS, scores)))  # fmt: skip


def build(data: Path) -> None:
    putj(data, "datasets/ds_v1.json", {
        "dataset_id": "ds_v1", "version": "1.0", "created_at": "2026-11-10T00:00:00Z",
        "sealed": {"at": "2026-11-10T00:00:00Z"},
        "items": [{"item_id": i, "source_path": f"{i}.txt", "source_sha256": f"{n + 1:064x}"} for n, i in enumerate(ITEMS)],
    })  # fmt: skip
    put(data, "goals/g1.yaml", yaml.safe_dump({
        "goal_id": "g1", "title": "G one", "success_criteria": {"primary": {"measure": "acc", "direction": "higher"}},
        "datasets": [{"dataset_id": "ds_v1", "role": "validation"}], "references": [{"reference_id": "gold/ds_v1"}],
    }, sort_keys=False))  # fmt: skip
    for system, scores in SCORES.items():
        make_run(data, system, scores)
    put(data, "rounds/g1/r1.yaml", yaml.safe_dump({
        "round_id": "r1", "goal": "g1", "dataset_id": "ds_v1", "hypothesis": "h", "status": "open",
        "budget_usd": 1.0, "opened_at": "2026-11-01T00:00:00Z",
        "arms": [{"system": s, "runs": [f"{s[-1]}_1"], "entered": {"how": "ran", "at": "2026-11-01T00:00:00Z"}}
                 for s in SCORES],
    }, sort_keys=False))  # fmt: skip
    register(data, PROJECT_READ)


try:
    evh("init", "--store", store_under_test())
    build(DATA)
    shutil.copytree(DATA, copy / "data", ignore=shutil.ignore_patterns("project.sqlite*"))
    CD = copy / "data"
    register(CD, COPY_READ)
    put(CD, "goals/g1.yaml", yaml.safe_dump({
        "goal_id": "g1", "title": "G one", "success_criteria": {"primary": {"measure": "acc", "direction": "higher"}},
        "test_looks": 3, "datasets": [{"dataset_id": "ds_v1", "role": "test"}], "references": [{"reference_id": "gold/ds_v1"}],
    }, sort_keys=False))  # fmt: skip
    sha = "ab" * 32
    putj(
        CD,
        f"prompts/ask/{sha[:16]}.json",
        {"id": f"ask/{sha[:16]}", "sha256": sha, "created_at": "2026-11-12T00:00:00Z"},
    )
    put(CD, f"prompts/ask/{sha[:16]}.txt", "Answer in one word.")
    putj(CD, "runs/a_1/scores/" + "0" * 12 + "@gold.ds_v1/metrics.json", {
        "primary_metric": "acc", "metric_kinds": {"acc": "quality", "cost_usd": "cost"},
        "scores": {"acc": 5 / 6, "total_cost_usd": 0.5},
    })  # fmt: skip
    _runstore.migrate_in(proj)
    _outputs.reset()
    _store.close()

    # -- the exposure register and the seal -------------------------------------------------------------------
    check(
        "the register is the project's by default and the copy's when the copy is asked",
        _exposure.exposed("ds_v1") == frozenset(PROJECT_READ)
        and _exposure.exposed("ds_v1", CD) == frozenset(COPY_READ)
        and [r["item_id"] for r in _exposure.rows("ds_v1", CD)] == COPY_READ
        and _exposure.path("ds_v1", CD) == CD / "exposure" / "ds_v1.jsonl",
        (sorted(_exposure.exposed("ds_v1")), sorted(_exposure.exposed("ds_v1", CD))),
    )
    other = CD / "datasets" / "ds_open.json"
    other.write_text(json.dumps({"dataset_id": "ds_open", "items": []}))
    sealed_here = CD / "datasets" / "ds_sealed_here.json"
    sealed_here.write_text(
        json.dumps(
            {
                "dataset_id": "ds_sealed_here",
                "items": [{"item_id": "x1"}, {"item_id": "x2"}],
                "sealed": {"at": "x"},
                "unsealed": [{"system_id": "c1", "at": "y", "look": {"key": "uk", "number": 1, "set": "z"}}],
            }
        )
    )
    put(CD, "exposure/ds_sealed_here.jsonl", json.dumps({"item_id": "x1", "what": "read", "by": "x"}) + "\n")
    check(
        "applies is asked of the directory: a dataset sealed in the copy only is held out there and not in the project",
        _exposure.applies("ds_sealed_here", CD)
        and not _exposure.applies("ds_sealed_here")
        and not _exposure.applies("ds_open", CD),
    )
    _exposure.left().clear()
    check(
        "keep leaves out the register's items, the copy's own when the copy is asked, and counts them",
        _exposure.keep("ds_v1", ITEMS) == {"i0", "i1", "i2"}
        and _exposure.keep("ds_v1", ITEMS, CD) == {"i2", "i3", "i4", "i5"}
        and {"ds_v1": {"i0", "i1", "i3", "i4", "i5"}} == _exposure.left(),
        _exposure.keep("ds_v1", ITEMS, CD),
    )
    check(
        "line says a held-out side's reads from the directory asked",
        "3 of 6" in (_exposure.line("ds_v1") or "")
        and "2 of 6" in (_exposure.line("ds_v1", CD) or "")
        and "1 of 2" in (_exposure.line("ds_sealed_here", CD) or "")
        and _exposure.line("ds_sealed_here") is None,
        (_exposure.line("ds_v1"), _exposure.line("ds_v1", CD), _exposure.line("ds_sealed_here", CD)),
    )

    # -- the scores, per item and through an adapter --------------------------------------------------------------
    P, C = HarnessAdapter(), HarnessAdapter(CD)
    runs_c = list(model_runs.scored("ds_v1", data=CD))
    check("the copy's runs are read for the test", len(runs_c) == 3, len(runs_c))
    _exposure.left().clear()
    check(
        "per_item leaves out the register of the data directory the runs are of",
        set(_runs.per_item(runs_c, "acc", data=CD)) == {"i2", "i3", "i4", "i5"}
        and set(_runs.per_item(runs_c, "acc")) == {"i0", "i1", "i2"},
    )
    pa, ca = _exposure.aware(HarnessAdapter()), _exposure.aware(HarnessAdapter(CD))
    arm = "runs/ds_v1/sys_a"
    check(
        "an adapter made aware leaves out the read items of its own data directory: the copy's, not the project's",
        set(pa.scores(arm)["acc"]["values"]) == {"i0", "i1", "i2"}
        and set(ca.scores(arm)["acc"]["values"]) == {"i2", "i3", "i4", "i5"}
        and set(P.scores(arm)["acc"]["values"]) == set(ITEMS),
        (sorted(pa.scores(arm)["acc"]["values"]), sorted(ca.scores(arm)["acc"]["values"])),
    )

    # -- one process, many calls (the MCP server answers in threads of its own process) -----------------------------
    import threading

    from evaluation_harness import _jsonout
    from evaluation_harness.catalog_adapter import scores_once

    inside, done = threading.Barrier(2), threading.Barrier(2)
    seen: dict = {}

    def including_call() -> None:
        with _exposure.including():
            inside.wait()
            done.wait()

    def other_call() -> None:
        inside.wait()
        seen["kept"] = _exposure.keep("ds_v1", ITEMS)
        done.wait()

    calls = [threading.Thread(target=f) for f in (including_call, other_call)]
    for t in calls:
        t.start()
    for t in calls:
        t.join(30)
    check(
        "one call's --include-exposed keeps the exposed items in its own scores only, not in a call running beside it",
        seen.get("kept") == {"i0", "i1", "i2"},
        seen.get("kept"),
    )
    held = scores_once(_exposure.aware(HarnessAdapter()), held=True)
    said = []
    for _ in range(2):
        with _jsonout.own_notes():
            values = set(held.scores(arm)["acc"]["values"])
            said.append((values, dict(_exposure.left())))
    with _jsonout.own_notes(), _exposure.including():
        including_values = set(held.scores(arm)["acc"]["values"])
    check(
        "held scores are filtered on every call: a cached answer still leaves the read items out and says so, and a "
        "call that includes them gets them without the cache keeping that for the next",
        said == [({"i0", "i1", "i2"}, {"ds_v1": {"i3", "i4", "i5"}})] * 2
        and including_values == set(ITEMS)
        and set(held.scores(arm)["acc"]["values"]) == {"i0", "i1", "i2"},
        (said, sorted(including_values)),
    )
    printed: dict = {}
    both_in = threading.Barrier(2)

    def printing_call(name: str) -> None:
        with _jsonout.capture() as c:
            print(f"{name} one")
            both_in.wait()
            print(f"{name} two")
            both_in.wait()
        printed[name] = [ln for b in c.result()["blocks"] for ln in b.get("lines", [])]

    calls = [threading.Thread(target=printing_call, args=(n,)) for n in ("first", "second")]
    for t in calls:
        t.start()
    for t in calls:
        t.join(30)
    check(
        "two calls captured at once each answer with their own printing, none of the other's",
        printed == {"first": ["first one", "first two"], "second": ["second one", "second two"]},
        printed,
    )

    # -- a round's evidence over the copy ----------------------------------------------------------------------
    rnd_p, rnd_c = _rounds.find("g1", "r1"), _rounds.find("g1", "r1", CD)
    assert rnd_p is not None and rnd_c is not None
    ev_p = model_rounds.evidence("g1", rnd_p, pa, DATA)
    ev_c = model_rounds.evidence("g1", rnd_c, ca, CD)
    ev_plain = model_rounds.evidence("g1", rnd_c, C, CD)
    ns = lambda ev: sorted({r["n"] for r in ev["rows"]})  # noqa: E731
    check(
        "a round's evidence over the copy counts the copy's items, over the project the project's, over neither's "
        "register all of them",
        ns(ev_p) == [3] and ns(ev_c) == [4] and ns(ev_plain) == [6],
        (ns(ev_p), ns(ev_c), ns(ev_plain)),
    )

    # -- the round's spend ---------------------------------------------------------------------------------------
    left_p, left_c, left_d = (
        _spend.round_left(rnd_p),
        _spend.round_left(rnd_c, CD),
        _spend.round_left(rnd_p, DATA),
    )
    assert left_p is not None and left_c is not None and left_d is not None
    check(
        "what a round has left is its budget less the spend of the runs under the directory asked",
        round(left_p, 6) == 0.97 and round(left_c, 6) == 0.48 and round(left_d, 6) == 0.97,
        (left_p, left_c),
    )
    check(
        "the evidence of an open round says what is left from its own directory",
        ev_p.get("left") == 0.97 and ev_c.get("left") == 0.48,
        (ev_p.get("left"), ev_c.get("left")),
    )

    # -- the looks and the prompt versions -----------------------------------------------------------------------
    check(
        "a test set's limit is the smallest test_looks of the goals of the directory asked",
        _looks.limit("ds_v1") == 10 and _looks.limit("ds_v1", CD) == 3,
        (_looks.limit("ds_v1"), _looks.limit("ds_v1", CD)),
    )
    check(
        "a dataset is a test set by the goals of the directory asked",
        _looks.is_test_set("ds_v1", CD)
        and "test set" in (_looks.said("ds_v1", CD) or "")
        and _looks.summary("ds_v1", CD)["limit"] == 3
        and _looks.summary("ds_v1")["limit"] == 10,
    )
    digest = _looks.digest("ds_v1", CD)
    putj(
        CD,
        "baselines/g1/ds_v1/1.json",
        {
            "version": 1, "goal": "g1", "dataset_id": "ds_v1", "promoted_from": "a_1", "promoted_at": "2026-11-12T00:00:00Z",
            "reason": "r", "evidence": {"look": {"key": "bk", "number": 2, "set": digest}},
        },
    )  # fmt: skip
    put(CD, "studies/g1/s1.yaml", yaml.safe_dump({"study_id": "s1", "goal": "g1"}))
    put(
        CD,
        "studies/g1/s1.events.jsonl",
        json.dumps(
            {
                "event": "confirm",
                "at": "2026-11-13T00:00:00Z",
                "look": {"key": "sk", "number": 3, "set": digest},
            }
        )
        + "\n",
    )
    got = {(x["key"], x["number"]) for x in _looks.recorded("ds_v1", CD)}
    check(
        "the looks recorded on a set are those of the directory asked: its unseals, the baselines it promoted and the "
        "studies it confirmed, the project's none",
        got == {("bk", 2), ("sk", 3)}
        and _looks.recorded("ds_v1") == []
        and {(x["key"], x["number"]) for x in _looks.recorded("ds_sealed_here", CD)} == {("uk", 1)}
        and _looks.next_number("ds_v1", data=CD) == (3, False)
        and _looks.next_number("ds_v1") == (1, False),
        (sorted(got), _looks.recorded("ds_v1")),
    )
    check(
        "a dataset is a test set, and has its digest and its prior use, by the record of the directory asked",
        _looks.is_test_set("ds_sealed_here", CD)
        and not _looks.is_test_set("ds_sealed_here")
        and _looks.digest("ds_sealed_here", CD) != _looks.digest("ds_sealed_here")
        and _looks.prior_use("ds_sealed_here", CD) == 0
        and _looks.double_spent("ds_v1", CD) == [],
    )
    check(
        "the prompt versions are the directory asked: the copy has one, the project none",
        _prompts.names() == []
        and _prompts.names(CD) == ["ask"]
        and [v["id"] for v in _prompts.versions("ask", CD)] == [f"ask/{sha[:16]}"]
        and _prompts.versions("ask") == []
        and _prompts.text_of(f"ask/{sha[:16]}", CD) == b"Answer in one word."
        and _prompts.prompts_dir(CD) == CD / "prompts",
    )
    try:
        _prompts.text_of(f"ask/{sha[:16]}")
        missing = False
    except FileNotFoundError:
        missing = True
    check("a version the project does not have is not found there", missing)
finally:
    _store.close()
    shutil.rmtree(tmp, ignore_errors=True)

sys.exit(summary())
