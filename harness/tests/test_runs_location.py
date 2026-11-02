#!/usr/bin/env python3
"""Where runs land: a warning when a run or a re-score writes where git will not keep it, and validate's
note for finished runs already sitting there. The self-hosted triage runs went to data/runs-local, which
git ignores, and nothing said so.

python tests/test_runs_location.py
"""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _common, catalog_build, validate_tree
from evaluation_harness._check import check, summary

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    # the shape of the harness's own rules: deny every runs-* directory, re-allow one derived set
    (root / ".gitignore").write_text(
        "data/runs/*/*\n!data/runs/*/metrics.json\n"
        "data/runs-*/\n!data/runs-derived/\ndata/runs-derived/*/*\n!data/runs-derived/*/metrics.json\n"
        "data/runs-smoke*/\n",
        encoding="utf-8",
    )
    data = root / "data"
    for d in ("runs", "runs-derived", "runs-local", "runs-smoke-x", "runs-empty"):
        (data / d).mkdir(parents=True)
    for d in ("runs", "runs-derived", "runs-local", "runs-smoke-x"):
        (data / d / "arm_v1_20261031T000000Z").mkdir()
        (data / d / "arm_v1_20261031T000000Z" / "metrics.json").write_text(json.dumps({}), encoding="utf-8")

    for d, want in (("runs", False), ("runs-derived", False), ("runs-local", True), ("runs-smoke-x", True)):
        check(f"ignored_by_git: data/{d} is {want}", _common.ignored_by_git(data / d) is want)
    check("ignored_by_git: a directory not yet created", _common.ignored_by_git(data / "runs-new") is True)
    check(
        "ignored_by_git: outside a checkout is False",
        _common.ignored_by_git(Path(tempfile.gettempdir())) is False,
    )

    def warned(d) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _common.warn_if_ignored(data / d if isinstance(d, str) else d, data)
        return buf.getvalue()

    check("warn: data/runs is silent", warned("runs") == "")
    check("warn: a re-allowed derived set is silent", warned("runs-derived") == "")
    check("warn: a throwaway directory is silent (losing it is the point)", warned("runs-smoke-x") == "")
    out = warned("runs-local")
    check(
        "warn: an ignored results directory warns, and says where runs go",
        "WARNING" in out and "data/runs" in out,
        out,
    )
    away = warned(Path(tempfile.gettempdir()) / "elsewhere-runs")
    check(
        "warn: a runs directory outside the project's data warns that nothing reads it",
        "WARNING" in away and "outside the project's data" in away,
        away,
    )

    from evaluation_harness.catalog_adapter import HarnessAdapter

    for d in ("runs", "runs-derived", "runs-local", "runs-smoke-x"):
        m = data / d / "arm_v1_20261031T000000Z" / "metrics.json"
        m.write_text(json.dumps({"dataset_id": "x", "config_id": "arm_v1", "created_at": "2026-10-31"}))
    seen = {a.split("/")[0] for a in HarnessAdapter(data).arms()}
    check(
        "catalog: reads the directories git keeps, never one it ignores (it shows what a clone and the release show)",
        seen == {"runs", "runs-derived"},
        seen,
    )

    old = validate_tree.DATA
    validate_tree.DATA = data
    try:
        validate_tree.notes.clear()
        validate_tree.note_uncommitted_runs()
        got = list(validate_tree.notes)
    finally:
        validate_tree.DATA = old
        validate_tree.notes.clear()
    check(
        "validate: one note, for the ignored directory that holds a finished run",
        len(got) == 1 and "runs-local" in got[0] and "1 finished run" in got[0],
        got,
    )


# One row per arm: a re-score with the current scorer stands in for the run it re-read.
def arm(name: str, runs: list, ref: str = "gold/x") -> dict:
    return {"arm": name, "reference": ref, "run_list": runs}


def run(rid: str, at: str, kind: str = "", src: str = "") -> dict:
    return {"run_id": rid, "created_at": at, "derived": kind, "from": src}


measured = arm("runs/x/a_v1", [run("a_v1_T1", "2026-10-30")])
rescored = arm("runs-current/x/a_v1", [run("a_v1_T1", "2026-10-31", "rescore", "a_v1_T1")])
later = arm("runs-later/x/a_v1", [run("a_v1_T1", "2026-11-01", "rescore", "a_v1_T1")])
silver = arm("runs-silver/x/a_v1", [run("a_v1_T1", "2026-10-31", "rescore", "a_v1_T1")], ref="silver/x")
repeat = arm("runs-repeats/x/a_v1", [run("a_v1_T2", "2026-10-31")])
half = arm("runs/x/b_v1", [run("b_v1_T1", "2026-10-30"), run("b_v1_T2", "2026-10-30")])
half_re = arm("runs-current/x/b_v1", [run("b_v1_T1", "2026-10-31", "rescore", "b_v1_T1")])
by_ds = {"x": {"arms": [measured, rescored, later, silver, repeat, half, half_re]}}
catalog_build._mark_superseded(by_ds)
check(
    "supersede: the measured run gives way to its latest re-score",
    measured.get("superseded_by") == later["arm"],
)
check(
    "supersede: an earlier re-score gives way to the later one", rescored.get("superseded_by") == later["arm"]
)
check("supersede: the latest re-score stands", "superseded_by" not in later)
check("supersede: a re-score against another reference is its own row", "superseded_by" not in silver)
check("supersede: a second measurement is its own row", "superseded_by" not in repeat)
check("supersede: an arm with a run nobody re-scored stays", "superseded_by" not in half)

# A measured arm whose run was re-scored says so on the arms page and in `evh arms`, beside the goals' choice.
with tempfile.TemporaryDirectory() as tmp:
    data = Path(tmp) / "data"
    ref = {"fingerprint": {"data": {"reference_id": "gold/x"}}}
    for d, extra in (("runs", {}), ("runs-current", {"derived": {"kind": "rescore", "from": "a_v1_T1"}})):
        rdir = data / d / "a_v1_T1"
        rdir.mkdir(parents=True)
        meta: dict = {
            "dataset_id": "x",
            "config_id": "a_v1",
            "run_id": "a_v1_T1",
            "created_at": "2026-10-31",
            **ref,
            **extra,
        }
        (rdir / "metrics.json").write_text(json.dumps(meta))
        (rdir / "predictions.jsonl").write_text(json.dumps({"item_id": "i1", "acc": 1.0}) + "\n")
    from evaluation_harness import catalog_arms
    from evaluation_harness.catalog_adapter import HarnessAdapter

    A = HarnessAdapter(data)
    rows = {r["arm"]: r for r in catalog_arms.arm_rows(A, catalog_build.collect(A))}
    check(
        "arms: a measured arm re-scored against the same reference names the arm the goals read",
        rows["runs/x/a_v1"]["superseded_by"] == "runs-current/x/a_v1"
        and not rows["runs-current/x/a_v1"]["superseded_by"],
        rows,
    )

# A directory re-allowed in .gitignore is checked even when validate.json's list was not edited too.
saved = validate_tree.policy, validate_tree.tracked_run_dirs
validate_tree.policy = lambda: {"committed": ["runs", "runs-repeats"]}
validate_tree.tracked_run_dirs = lambda: ["runs", "runs-new-set", "runs-repeats"]
try:
    got = validate_tree.committed_dirs()
finally:
    validate_tree.policy, validate_tree.tracked_run_dirs = saved
check(
    "committed: the declared directories first, then every other tracked one",
    got == ["runs", "runs-repeats", "runs-new-set"],
    got,
)

sys.exit(summary())
