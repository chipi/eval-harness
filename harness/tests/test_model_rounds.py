#!/usr/bin/env python3
"""Rounds store their arms (RFC-032 step 5): the format 5 migration, in the suite's store.

    python tests/test_model_rounds.py

A format 4 project made here has a round whose arms ran in it (r1, which promoted a baseline), a round that only
retired a re-timing (r2), and a round that carried two systems and is read under a re-score its scoring wrote, one of
them retired with no runs named (r3). `evh migrate` moves it to format 5, and then:

- each round's arms are the systems format 4 read in play, each read under the round's label through its runs, how
  it entered (ran, or carried from the round before), and the retired with when, why and who; `carried` and
  `retired` are gone;
- the re-timing a round retired is an arm of its own, read under its machine, retired;
- the baseline r1 promoted names the round and the arm; a migrated project migrates to nothing;
- a retirement naming some but not all of a system's runs is refused, nothing written.
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
proj = Path(tempfile.mkdtemp(prefix="evh-rounds-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
import _runfix  # noqa: E402
import _runstore  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _outputs, _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_BUILD_REF="test-model-rounds")
DATA = proj / "data"
WHO = {"type": "person", "name": "tester", "from": "flag"}
ROWS = [{"item_id": "i1", "acc": 1.0}]


def evh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), *args], cwd=proj, env=env, capture_output=True,
        text=True, stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def run(run_id: str, system: str, rnd: str | None = None, **kw) -> None:
    rec = {"run_id": run_id, "config_id": system, "dataset_id": "ds_v1", "scores": {"acc": 1.0},
           "primary_metric": "acc", **({"round": rnd, "goal": "g1"} if rnd else {})}  # fmt: skip
    _runfix.put_run(DATA, rec, ROWS, **kw)


def round_file(rid: str, doc: dict) -> None:
    base = {"round_id": rid, "goal": "g1", "dataset_id": "ds_v1", "hypothesis": "h", "status": "closed",
            "opened_at": f"2026-11-0{rid[1]}T00:00:00Z", "closed_at": "2026-11-09T00:00:00Z", "actor": WHO}  # fmt: skip
    _runstore.write_text(proj, f"rounds/g1/{rid}.yaml", yaml.safe_dump({**base, **doc}, sort_keys=False))


def fresh() -> None:
    _outputs.reset()
    _store.close()
    shutil.rmtree(proj, ignore_errors=True)
    proj.mkdir()
    evh("init")
    _runstore.write_text(proj, "project.yaml", "format: 4\n")
    _outputs.reset()


try:
    fresh()
    run("a_1", "sys_a", "r1")
    run("b_1", "sys_b", "r1")
    run("b_lx", "sys_b", "r2", purpose="retime", machine="linux")
    run("c_1", "sys_c")
    for rid, sys_id in (("a_1", "sys_a"), ("c_1", "sys_c")):  # a round's scoring re-scored them
        rec = {
            "run_id": rid,
            "config_id": sys_id,
            "dataset_id": "ds_v1",
            "scores": {"acc": 0.5},
            "primary_metric": "acc",
        }
        _runfix.put_run(DATA, rec, ROWS, label="rescored aaaaaaaa", scorer="a" * 12, first=False)
    round_file("r1", {"conclusion": {"text": "a leads", "promoted_run": "a_1"}})
    round_file("r2", {"from": "r1", "retired": [{"config_id": "sys_b", "reason": "a re-timing", "at": "2026-11-02T01:00:00Z",
                                                 "runs": ["b_lx"]}], "conclusion": {"text": "same"}})  # fmt: skip
    round_file("r3", {"from": "r2", "carried": ["sys_c", "sys_a"],
                      "scoring": [{"at": "2026-11-03T01:00:00Z", "scorer": "a" * 12, "why": "w",
                                   "written": ["rescored aaaaaaaa", "rescored aaaaaaaa, repeats"], "runs": 2}],
                      "retired": [{"config_id": "sys_a", "reason": "dropped", "at": "2026-11-03T02:00:00Z", "actor": WHO}],
                      "conclusion": {"text": "c"}})  # fmt: skip
    _runstore.write_text(proj, "baselines/g1/ds_v1/1.json",
                         json.dumps({"version": 1, "goal": "g1", "dataset_id": "ds_v1", "promoted_from": "a_1"}) + "\n")  # fmt: skip

    m = evh("migrate")
    _outputs.reset()
    rounds = {r: yaml.safe_load(_runstore.read_text(proj, f"rounds/g1/{r}.yaml")) for r in ("r1", "r2", "r3")}
    check("evh migrate brings it to format 5", m.returncode == 0 and "format: 5" in _runstore.read_text(proj, "project.yaml"), (m.stdout + m.stderr)[-400:])  # fmt: skip

    def arm(rid: str, system: str) -> dict:
        return next((a for a in rounds[rid].get("arms") or [] if a["system"] == system), {})

    check(
        "the arms that ran in a round: the plain runs, entered by running, when it opened, by whom",
        [a["system"] for a in rounds["r1"]["arms"]] == ["sys_a", "sys_b"]
        and arm("r1", "sys_a")
        == {
            "system": "sys_a",
            "runs": ["a_1"],
            "entered": {"how": "ran", "at": "2026-11-01T00:00:00Z", "actor": WHO},
        },
        rounds["r1"].get("arms"),
    )
    check(
        "a re-timing a round retired is an arm of its own: read under its machine, entered by running, retired",
        arm("r2", "sys_b").get("label") == "linux"
        and arm("r2", "sys_b").get("runs") == ["b_lx"]
        and arm("r2", "sys_b").get("entered", {}).get("how") == "ran"
        and arm("r2", "sys_b").get("retired") == {"at": "2026-11-02T01:00:00Z", "reason": "a re-timing"},
        rounds["r2"].get("arms"),
    )
    check(
        "carried arms are read under the re-score the round's scoring wrote, entered by being carried from the round "
        "before; one retired with no runs named is retired, with who",
        arm("r3", "sys_c")
        == {
            "system": "sys_c",
            "label": "rescored aaaaaaaa",
            "runs": ["c_1"],
            "entered": {"how": "carried", "at": "2026-11-03T00:00:00Z", "from": "r2", "actor": WHO},
        }
        and arm("r3", "sys_a").get("retired")
        == {"at": "2026-11-03T02:00:00Z", "reason": "dropped", "actor": WHO}
        and not any(k in rounds["r3"] for k in ("carried", "retired")),
        rounds["r3"],
    )
    base = json.loads(_runstore.read_text(proj, "baselines/g1/ds_v1/1.json"))
    check("the baseline a round promoted names the round and the arm", base.get("round") == "r1" and base.get("arm") == "sys_a", base)  # fmt: skip
    listed = sorted(str(p) for p in _store.rglob(DATA / "rounds", "*"))
    again = evh("migrate")
    _outputs.reset()
    check(
        "a migrated project migrates to nothing",
        again.returncode == 0 and sorted(str(p) for p in _store.rglob(DATA / "rounds", "*")) == listed,
        (again.stdout + again.stderr)[-300:],
    )

    # A retirement that names some of a system's runs, not all: format 4 kept it in play; refused, nothing written.
    fresh()
    run("a_1", "sys_a", "r1")
    run("a_2", "sys_a", "r1")
    round_file(
        "r1",
        {"retired": [{"config_id": "sys_a", "reason": "x", "at": "2026-11-01T01:00:00Z", "runs": ["a_1"]}]},
    )
    before = _runstore.read_text(proj, "rounds/g1/r1.yaml")
    r = evh("migrate")
    _outputs.reset()
    check(
        "refused: a retirement naming some but not all of a system's runs, nothing written",
        r.returncode != 0
        and "not every run of it" in r.stderr
        and _runstore.read_text(proj, "rounds/g1/r1.yaml") == before,
        r.stderr[-400:],
    )
finally:
    _outputs.reset()
    _store.close()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
