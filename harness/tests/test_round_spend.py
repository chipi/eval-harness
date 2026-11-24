#!/usr/bin/env python3
"""A round's spend is the runs' recorded costs and how many recorded none (RFC-041 F3): never an unknown cost as $0.

    python tests/test_round_spend.py

In a throwaway project, $0 and offline: a round whose runs mix known and unknown costs says how many recorded none
wherever it shows its spend (round-evidence), and the budget guard counts only what is known but names the runs that
recorded none; a round whose runs all recorded none shows no spend, not $0.0000; a known $0 is a value. A run that
recorded a cost for only some of its items says so wherever its total is shown.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-round-spend-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
import _cli  # noqa: E402
import _runfix  # noqa: E402
import _runstore  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _outputs, _store  # noqa: E402
from evaluation_harness._check import check, store_under_test, summary  # noqa: E402

env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_BUILD_REF="test-round-spend")
DATA = proj / "data"
WHO = {"type": "person", "name": "tester", "from": "flag"}
ROWS = [{"item_id": "i1", "acc": 1.0}]


def evh(*args: str):
    return _cli.run(proj, env, *args, timeout=600)


def run(run_id: str, system: str, rnd: str, cost: float | None, **rec) -> None:
    scores = {"acc": 1.0, **({} if cost is None else {"total_cost_usd": cost})}
    _runfix.put_run(
        DATA,
        {"run_id": run_id, "config_id": system, "system_id": system, "dataset_id": "ds_v1", "scores": scores, "primary_metric": "acc",
         "round": rnd, "goal": "g1", **rec},
        ROWS,
    )  # fmt: skip


def round_file(rid: str, budget: float, runs: tuple[str, ...]) -> None:
    doc = {"round_id": rid, "goal": "g1", "dataset_id": "ds_v1", "hypothesis": "h", "status": "open",
           "opened_at": "2026-11-01T00:00:00Z", "actor": WHO, "budget_usd": budget,
           "arms": [{"system": s, "runs": [r for r in runs if r.startswith(s[-1])],
                     "entered": {"how": "ran", "at": "2026-11-01T00:00:00Z"}} for s in ("sys_a", "sys_b", "sys_c")]}  # fmt: skip
    _runstore.write_text(proj, f"rounds/g1/{rid}.yaml", yaml.safe_dump(doc, sort_keys=False))


def spend_note(rid: str) -> str:
    r = evh("round-evidence", "g1", rid, "--json")
    notes = json.loads(r.stdout)["result"].get("notes", []) if r.returncode == 0 else [r.stdout + r.stderr]
    return next(
        (n for n in notes if "of $" in n or "budget" in n),
        "<no spend note> " + r.stdout[:700] + r.stderr[-300:],
    )


try:
    _outputs.reset()
    _store.close()
    shutil.rmtree(proj, ignore_errors=True)
    proj.mkdir()
    evh("init", "--store", store_under_test())
    for s in ("sys_a", "sys_b", "sys_c"):
        _runstore.write_text(proj, f"systems/{s}.yaml", f"system_id: {s}\n")
    _runstore.write_text(
        proj,
        "goals/g1.yaml",
        yaml.safe_dump({"goal_id": "g1", "title": "G", "success_criteria": {"primary": {"measure": "acc", "direction": "higher"}},
                        "datasets": [{"dataset_id": "ds_v1", "role": "validation"}]}, sort_keys=False),
    )  # fmt: skip
    _outputs.reset()

    round_file("r1", 1.0, ("a_1", "b_1", "c_1"))
    run("a_1", "sys_a", "r1", 0.012)
    run("b_1", "sys_b", "r1", None)
    run("c_1", "sys_c", "r1", None)
    note = spend_note("r1")
    check(
        "round-evidence: a round with 2 of 3 runs unpriced says so beside what is known",
        "spent $0.0120 of $1.00 (2 runs recorded no cost)" in note,
        note,
    )

    round_file("r2", 1.0, ("a_2", "b_2"))
    run("a_2", "sys_a", "r2", None)
    run("b_2", "sys_b", "r2", None)
    note = spend_note("r2")
    check(
        "round-evidence: a round whose runs all recorded no cost shows an unknown spend, not $0.0000",
        "$0.0000" not in note and "unknown" in note and "2 runs recorded no cost" in note,
        note,
    )

    round_file("r3", 1.0, ("a_3",))
    run("a_3", "sys_a", "r3", 0.0)
    note = spend_note("r3")
    check(
        "round-evidence: a run that recorded $0 is a known $0, with nothing unrecorded to say",
        "spent $0.0000 of $1.00" in note and "recorded no cost" not in note,
        note,
    )

    from evaluation_harness import _rounds, _spend

    with _runstore._InProject(proj):
        _outputs.reset()
        r1 = _rounds.load_rounds("g1")
        r1 = next(r for r in r1 if r["round_id"] == "r1")
        r2 = next(r for r in _rounds.load_rounds("g1") if r["round_id"] == "r2")
        got1, got2 = _rounds.spend_of(r1), _rounds.spend_of(r2)
        check(
            "_rounds.spend_of: the sum of the runs that recorded a cost, and how many recorded none",
            got1 == (0.012, 2) and got2 == (None, 2),
            f"{got1} {got2}",
        )
        left = _spend.round_left(r1)
        check(
            "_spend.round_left counts the known spend only (budget less what is recorded)",
            left is not None and abs(left - (1.0 - 0.012)) < 1e-9,
            left,
        )
        r1["budget_usd"] = 0.01
        try:
            _spend.reserve(r1, "run")
            msg = "no refusal"
        except SystemExit as exc:
            msg = str(exc)
        check(
            "the budget guard refuses on the known spend and names the runs that recorded none",
            "over-budget" in msg and "2 runs recorded no cost" in msg,
            msg,
        )
finally:
    shutil.rmtree(proj, ignore_errors=True)
summary()
