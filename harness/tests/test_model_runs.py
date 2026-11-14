#!/usr/bin/env python3
"""Runs and scores (RFC-032 step 4): the format 4 migration and the model that reads it, in the suite's store.

    python tests/test_model_runs.py

A format 3 project made here holds a pass in each folder that meant a purpose (data/runs, runs-repeats, runs-linux),
a silver re-score, a re-score by the scorer the run already had (the same rows: the same measurement made twice),
a judged score with its pass's summary, a round that retired a system in runs-repeats, and validate.json naming
folders. `evh migrate` moves it to format 4, and (step 5) to format 5, and then:

- every record reads back through model.runs as it was (`derived.from_dir` naming the run's new directory), its rows
  and outputs the same, read under the label its folder gave it;
- each pass is one run whose purpose and machine say what its folder meant, `of` naming the run a re-run re-does
  when there is exactly one; the copy is kept once, its old arm sent to the run's;
- the round keeps its retired runs as an arm read under its label, the policy names arms, the summary sits in data/judge-summaries, no data/runs-* is
  left;
- a pass in a folder whose purpose is not known, and two different scores of one key, are refused with nothing
  written; a migrated project migrates to nothing.
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
proj = Path(tempfile.mkdtemp(prefix="evh-runs-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
from evaluation_harness import _outputs, _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import runs as R  # noqa: E402

env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_BUILD_REF="test-model-runs")
SHA_A = "a" * 64
SHA_B = "b" * 64
DATA = proj / "data"


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project."""
    return subprocess.run(
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), *args], cwd=proj, env=env, capture_output=True,
        text=True, stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def record(run_id: str, system: str, *, platform: str = "Linux/x86_64", sha: str = SHA_A, ref: str = "gold/ds_v1",
           derived: dict | None = None, score: float = 0.5) -> dict:  # fmt: skip
    """A format 3 record: what a run's metrics.json held."""
    r = {
        "run_id": run_id, "config_id": system, "dataset_id": "ds_v1", "created_at": "2026-11-01T00:00:00Z",
        "n_items": 2, "params": {"provider": "echo"}, "adapter": "adapter.py", "primary_metric": "acc",
        "metric_kinds": {"acc": "quality"}, "scores": {"acc": score}, "reference_tier": ref.split("/")[0],
        "fingerprint": {"hash": "f" * 64, "instrument": {"adapter": {"id": "adapter.py", "sha256": SHA_A}},
                        "data": {"dataset_id": "ds_v1", "reference_id": ref}, "runner": {"platform": platform}},
    }  # fmt: skip
    if (
        derived
    ):  # a re-score records no actor of its own (format 3's did not), so the run's must not show through
        r["derived"] = derived
        r["created_at"] = "2026-11-02T00:00:00Z"
    else:
        r["actor"] = {"type": "person", "name": "tester"}
    return r


ROWS = '{"item_id": "i1", "acc": 1.0}\n{"item_id": "i2", "acc": 0.0}\n'
OUTS = {"i1": "one", "i2": "two"}


def put(folder: str, run_id: str, rec: dict, *, outputs: bool | dict = False, rows: str = ROWS) -> Path:
    """A format 3 run directory: metrics.json, its rows, its outputs for a pass, in the project's store."""
    d = DATA / folder / run_id
    _store.mkdir(d, parents=True, exist_ok=True)
    _store.write_text(d / "metrics.json", json.dumps(rec, indent=2) + "\n")
    _outputs.store().put_rows(d, rows)
    if outputs:
        outs = outputs if isinstance(outputs, dict) else OUTS
        _outputs.store().write_all(d, outs, list(outs))
    return d


def rescore_of(run_id: str, folder: str, sha: str, ref: str = "gold/ds_v1", kind: str = "rescore") -> dict:
    return {"at": "2026-11-02T00:00:00Z", "from": run_id, "from_dir": f"{folder}/{run_id}", "kind": kind,
            "with": {"adapter": "adapter.py", "sha256": sha}}  # fmt: skip


try:
    r = evh("init")
    check("setup: a project", r.returncode == 0, r.stderr[-300:])
    _store.write_text(DATA / "project.yaml", "format: 3\n")
    _outputs.reset()
    base = put("runs", "sys_a_1", record("sys_a_1", "sys_a"), outputs=True)
    put("runs", "sys_b_1", record("sys_b_1", "sys_b", platform="Darwin/x86_64", score=0.25), outputs=True)
    put("runs-repeats", "sys_a_2", record("sys_a_2", "sys_a", score=0.75), outputs=True)
    put("runs-linux", "sys_b_2", record("sys_b_2", "sys_b", score=0.3), outputs=True)
    put("runs-silver", "sys_a_1", record("sys_a_1", "sys_a", ref="silver/ds_v1",
        derived=rescore_of("sys_a_1", "runs", SHA_B), score=0.4))  # fmt: skip
    # The scorer sys_a_1 already had, the same rows: the same measurement made twice, the scores rounded otherwise.
    put("runs-rescored/aaaaaaaaaaaa/runs", "sys_a_1", record("sys_a_1", "sys_a", derived=rescore_of("sys_a_1", "runs", SHA_A), score=0.5000001))  # fmt: skip
    judged = record("sys_a_1", "sys_a", score=0.9)
    judged["derived"] = {"at": "2026-11-03T00:00:00Z", "from": "sys_a_1", "from_dir": "runs/sys_a_1", "kind": "judge",
                         "with": {"scorer_id": "judge-x", "judging_set_id": "ds_v1-2arms-abc"}}  # fmt: skip
    put("runs-judged/judge-x", "sys_a_1", judged)
    _store.write_text(DATA / "runs-judged" / "judge-x" / "summary.json", '{"scorer_id": "judge-x"}\n')
    _store.mkdir(DATA / "rounds" / "g1", parents=True, exist_ok=True)
    _store.write_text(DATA / "rounds" / "g1" / "r1.yaml", (
        "round_id: r1\ngoal: g1\ndataset_id: ds_v1\nstatus: open\nretired:\n- config_id: sys_a\n  runs_dir: runs-repeats\n"
        "  reason: a re-run\n  at: '2026-11-04T00:00:00Z'\nscoring:\n- at: '2026-11-05T00:00:00Z'\n  scorer: aaaaaaaaaaaa\n"
        "  why: x\n  written:\n  - runs-rescored/aaaaaaaaaaaa/runs\n  runs: 1\n"))  # fmt: skip
    _store.write_text(DATA / "validate.json", json.dumps({
        "committed": ["runs", "runs-repeats", "runs-judged/judge-x"], "floors": {"runs": 2, "runs-linux": 1},
        "scorer_sources": [{"dir": "runs-repeats", "glob": "sys_*"}]}, indent=2) + "\n")  # fmt: skip
    old = {
        (f, rid): json.loads(_store.read_text(DATA / f / rid / "metrics.json"))
        for f, rid in (("runs", "sys_a_1"), ("runs", "sys_b_1"), ("runs-repeats", "sys_a_2"),
                       ("runs-linux", "sys_b_2"), ("runs-silver", "sys_a_1"), ("runs-judged/judge-x", "sys_a_1"))
    }  # fmt: skip

    dry = evh("migrate", "--dry-run")
    check(
        "the dry run counts the runs, the scores, the copy kept once and the arms renamed, writing nothing",
        dry.returncode == 0
        and "4 run(s) into data/runs; 6 score(s) under them (1 identical copy(ies) kept once)" in dry.stdout
        and _store.is_dir(DATA / "runs-silver"),
        (dry.stdout + dry.stderr)[-800:],
    )
    m = evh("migrate")
    _outputs.reset()
    check("evh migrate brings it to format 5", m.returncode == 0 and "format: 5" in _store.read_text(DATA / "project.yaml"), (m.stdout + m.stderr)[-500:])  # fmt: skip

    def score(run_id: str, key: str) -> Path:
        return R.run_dir(run_id) / "scores" / key

    where = {
        ("runs", "sys_a_1"): score("sys_a_1", f"{SHA_A[:12]}@gold.ds_v1"),
        ("runs", "sys_b_1"): score("sys_b_1", f"{SHA_A[:12]}@gold.ds_v1"),
        ("runs-repeats", "sys_a_2"): score("sys_a_2", f"{SHA_A[:12]}@gold.ds_v1"),
        ("runs-linux", "sys_b_2"): score("sys_b_2", f"{SHA_A[:12]}@gold.ds_v1"),
        ("runs-silver", "sys_a_1"): score("sys_a_1", f"{SHA_B[:12]}@silver.ds_v1"),
        ("runs-judged/judge-x", "sys_a_1"): score("sys_a_1", "judge-x@ds_v1-2arms-abc"),
    }
    same, rows_same = [], []
    for key, sd in where.items():
        want = dict(old[key])
        if (want.get("derived") or {}).get("from_dir"):
            want["derived"] = {**want["derived"], "from_dir": f"runs/{want['derived']['from']}"}
        got = {x: v for x, v in (R.record(sd) or {}).items() if x not in R.RUN_ONLY}
        same.append(got == want)
        rows_same.append(_outputs.rows_text(sd) == ROWS)
    check("every record reads back as it was, through model.runs", all(same), list(zip(where, same)))
    check("every score's rows are its rows", all(rows_same), list(zip(where, rows_same)))
    check("a score's outputs are its run's", _outputs.outputs(where[("runs-silver", "sys_a_1")]) == OUTS)
    labels = {k[0]: R.label(sd) for k, sd in where.items()}
    check(
        "each score is read under the label its folder gave it",
        labels
        == {
            "runs": "",
            "runs-repeats": "repeats",
            "runs-linux": "linux",
            "runs-silver": "silver",
            "runs-judged/judge-x": "judged/judge-x",
        },
        labels,
    )
    runs = {rid: R.run(rid) for rid in R.run_ids()}
    check(
        "each pass is one run: its purpose and machine what its folder meant, `of` the one run a re-run re-does",
        {
            rid: ((x or {}).get("purpose"), (x or {}).get("machine"), (x or {}).get("of"))
            for rid, x in runs.items()
        }
        == {
            "sys_a_1": ("run", "linux", None),
            "sys_b_1": ("run", "darwin", None),
            "sys_a_2": ("repeat", "linux", "sys_a_1"),
            "sys_b_2": ("retime", "linux", "sys_b_1"),
        },
        runs,
    )
    renames = json.loads(_store.read_text(DATA / "renames.json"))["arms"]
    check(
        "the copy is kept once, its old arm the run's; the other arms renamed to their labels",
        len(R.scores_of("sys_a_1")) == 3
        and renames.get("runs-rescored/aaaaaaaaaaaa/runs/ds_v1/sys_a") == "runs/ds_v1/sys_a"
        and renames.get("runs-silver/ds_v1/sys_a") == "silver/ds_v1/sys_a"
        and renames.get("runs-judged/judge-x/ds_v1/sys_a") == "judged-judge-x/ds_v1/sys_a",
        (R.scores_of("sys_a_1"), renames),
    )
    import yaml

    rnd = yaml.safe_load(_store.read_text(DATA / "rounds" / "g1" / "r1.yaml"))
    policy = json.loads(_store.read_text(DATA / "validate.json"))
    check(
        "the round keeps the retired runs as an arm read under its label, its scoring names labels; the policy names arms",
        [(a["system"], a.get("label"), a["runs"], "reason" in a["retired"]) for a in rnd["arms"]]
        == [("sys_a", "repeats", ["sys_a_2"], True)]
        and "retired" not in rnd
        and "runs_dir" not in json.dumps(rnd)
        and rnd["scoring"][0]["written"] == ["rescored aaaaaaaa"]
        and policy["committed"] == ["runs", "repeats", "judged-judge-x"]
        and policy["floors"] == {"runs": 2, "linux": 1}
        and policy["scorer_sources"] == [{"arms": "repeats", "glob": "sys_*"}],
        (rnd, policy),
    )
    check(
        "the judging pass's summary is in data/judge-summaries; no data/runs-* is left",
        _store.is_file(DATA / "judge-summaries" / "judge-x@ds_v1-2arms-abc.json")
        and not [p.name for p in _store.glob(DATA, "runs-*")],
        [p.name for p in _store.glob(DATA, "runs*")],
    )
    listed = sorted(str(p) for p in _store.rglob(DATA, "*"))
    again = evh("migrate")
    _outputs.reset()
    check(
        "a migrated project migrates to nothing",
        again.returncode == 0 and sorted(str(p) for p in _store.rglob(DATA, "*")) == listed,
        (again.stdout + again.stderr)[-300:],
    )

    # The refusals, each on a fresh format 3 project, nothing written.
    for why, setup, says in (
        ("a pass in a folder whose purpose is not known",
         lambda: put("runs-other", "sys_c_1", record("sys_c_1", "sys_c"), outputs=True), "a pass in runs-other"),
        ("two different scores of one key",
         lambda: (put("runs", "sys_d_1", record("sys_d_1", "sys_d"), outputs=True),
                  put("runs-rescored/aaaaaaaaaaaa/runs", "sys_d_1",
                      record("sys_d_1", "sys_d", derived=rescore_of("sys_d_1", "runs", SHA_A)), rows='{"item_id": "i1", "acc": 0.0}\n')),
         "two different scores of sys_d_1"),
        ("a score that keeps outputs of its own",
         lambda: (put("runs", "sys_e_1", record("sys_e_1", "sys_e"), outputs=True),
                  put("runs-silver", "sys_e_1", record("sys_e_1", "sys_e", ref="silver/ds_v1",
                      derived=rescore_of("sys_e_1", "runs", SHA_B)), outputs={"i1": "edited", "i2": "two"})),
         "keeps outputs of its own"),
    ):  # fmt: skip
        _outputs.reset()
        _store.close()
        shutil.rmtree(proj)
        proj.mkdir()
        evh("init")
        _store.write_text(DATA / "project.yaml", "format: 3\n")
        _outputs.reset()
        setup()
        before = sorted(str(p) for p in _store.rglob(DATA, "*"))
        r = evh("migrate")
        _outputs.reset()
        check(
            f"refused: {why}, nothing written",
            r.returncode != 0
            and says in r.stderr
            and sorted(str(p) for p in _store.rglob(DATA, "*")) == before,
            r.stderr[-400:],
        )
finally:
    _store.close()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
