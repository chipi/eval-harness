#!/usr/bin/env python3
"""`as_judged`: the arms of a judge-score pass under the ids a stored judging set judged them as. No network, $0.

    python tests/test_as_judged.py

A judging set is frozen evidence and keeps the ids it was judged under (RFC-032 step 3); a migration renamed the
systems since (data/renames.json), so the live arms carry today's ids and a rebuilt set would be a new one, its verdicts
not found and paid for again. Covered: on a fixture set whose arms carry ids a migration renamed, the live arms are
re-keyed to the stored ids, in the stored ids' order, and only when the set is of exactly these runs; and on this
repository's three judging sets, every arm's run exists, reads as the system the migration renamed it to, and maps back
to the stored id.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Reads this repository's committed data (runs, judging sets), which is files.
os.environ["EVAL_STORE"] = "files"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
from evaluation_harness import _common
from evaluation_harness import judge_score as js
from evaluation_harness._check import check, summary

DATA = Path(__file__).resolve().parents[1] / "data"
RENAMES = json.loads((DATA / "renames.json").read_text())["systems"]

# ── a fixture set whose arms carry ids a migration renamed ───────────────────────────────────────────────────────────
# Two systems renamed by this repository's own migration; the new ids sort the other way round from the old ones, so
# the order the set was made in is visible in the result.
OLD = ["cnn_bart_l_n200_v1", "cnn_deepseek_m_n200_v1"]
NEW = [RENAMES[o] for o in OLD]
RUNS = ["cnn_bart_l_n200_v1_20260926T153757Z", "cnn_deepseek_m_n200_v1_20260925T233650Z"]
check(
    "fixture: the stored ids are ones data/renames.json renamed, and today's ids differ",
    all(o in RENAMES and RENAMES[o] != o for o in OLD),
    NEW,
)


def live(ids, runs):
    return [
        {"config_id": i, "run": r, "dir": f"/runs/{r}", "family": f"fam{k}"}
        for k, (i, r) in enumerate(zip(ids, runs))
    ]


def stored(path, dataset_id, ids, runs):
    path.write_text(
        json.dumps(
            {
                "dataset_id": dataset_id,
                "arms": [{"config_id": i, "run": r, "family": "x"} for i, r in zip(ids, runs)],
            }
        )
    )


with tempfile.TemporaryDirectory(prefix="evh-as-judged-") as td:
    sets = Path(td) / "judging-sets"
    sets.mkdir()
    real_sets = js.SETS
    js.SETS = sets
    try:
        stored(sets / "ds-2arms-aaaa.json", "ds", OLD, RUNS)
        arms = live(NEW, RUNS)
        before = json.dumps(arms)
        got = js.as_judged("ds", arms)
        check(
            "a set of exactly these runs: the arms carry the stored ids",
            [a["config_id"] for a in got] == OLD,
            got,
        )
        check(
            "the run, its directory and its family stay the live arm's own",
            [(a["run"], a["dir"], a["family"]) for a in got]
            == [(a["run"], a["dir"], a["family"]) for a in arms],
            got,
        )
        check("the arms passed in are not changed", json.dumps(arms) == before)

        # The stored ids' order, not the live ids': what the set's blocks were made of.
        swapped = live(NEW[::-1], RUNS[::-1])
        check(
            "the result is in the stored ids' order, whatever order the live arms came in",
            [a["config_id"] for a in js.as_judged("ds", swapped)] == sorted(OLD),
        )

        check(
            "another dataset has no stored set: the arms are as they were",
            js.as_judged("other", arms) is arms,
        )
        fewer, more = live(NEW[:1], RUNS[:1]), live([*NEW, "extra_v1"], [*RUNS, "extra_v1_20260101T000000Z"])
        check("a set of more runs than these: the arms are as they were", js.as_judged("ds", fewer) is fewer)
        check("a set of fewer runs than these: the arms are as they were", js.as_judged("ds", more) is more)
        same = live(OLD, RUNS)
        check(
            "a set under the ids the arms already have: the arms are as they were",
            js.as_judged("ds", same) is same,
        )

        # A set of another run list sorts first; the one of exactly these runs is still found.
        stored(sets / "ds-1arm-0000.json", "ds", OLD[:1], RUNS[:1])
        check(
            "among several sets of the dataset, the one of exactly these runs is found",
            [a["config_id"] for a in js.as_judged("ds", arms)] == OLD,
        )
    finally:
        js.SETS = real_sets

# ── this repository's three judging sets ─────────────────────────────────────────────────────────────────────────────
files = sorted((DATA / "judging-sets").glob("*.json"))
check("this repository has its three judging sets", len(files) == 3, [f.name for f in files])
for f in files:
    s = json.loads(f.read_text())
    ds, sarms = s["dataset_id"], s["arms"]
    by_run = {a["run"]: a["config_id"] for a in sarms}
    missing = [r for r in by_run if not (DATA / "runs" / r).is_dir()]
    check(f"{f.name}: every arm's run exists", not missing, missing)
    found = {a["run"]: a for a in js.discover_arms(ds, "")}
    check(
        f"{f.name}: every arm's run is a live arm, under the id the migration renamed it to",
        set(by_run) <= set(found)
        and all(found[r]["config_id"] == _common.system_now(c) for r, c in by_run.items()),
        {
            r: (found.get(r, {}).get("config_id"), _common.system_now(c))
            for r, c in by_run.items()
            if r not in found or found[r]["config_id"] != _common.system_now(c)
        },
    )
    arms = [found[r] for r in by_run if r in found]
    check(
        f"{f.name}: some live arm has an id other than the stored one (the re-keying is exercised)",
        any(found[r]["config_id"] != c for r, c in by_run.items()),
    )
    got = js.as_judged(ds, arms)
    check(
        f"{f.name}: the live arms are re-keyed to the stored ids",
        {a["run"]: a["config_id"] for a in got} == by_run
        and [a["config_id"] for a in got] == sorted(by_run.values()),
    )

sys.exit(summary())
