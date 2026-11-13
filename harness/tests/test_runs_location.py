#!/usr/bin/env python3
"""Where runs land: a warning when a run writes where git will not keep it, validate's note for finished runs
already sitting there, and the rules `evh init` writes for data/runs (a pass's record, outputs and scores are kept, its
checkpoint and a throwaway pass are not). The self-hosted triage runs went to an ignored folder, and nothing said so.

python tests/test_runs_location.py
"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _common, _format, catalog_build, validate_tree
from evaluation_harness._check import check, summary
from evaluation_harness.init_project import IGNORE

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore

RUN = "arm_v1_20261031T000000Z"
REC = {"dataset_id": "x", "config_id": "arm_v1", "created_at": "2026-10-31", "n_items": 1}


def project(root: Path, ignore: str) -> Path:
    """A git checkout with `ignore` as its .gitignore and one finished run in data/runs."""
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".gitignore").write_text(ignore, encoding="utf-8")
    first = {"scorer": "s1", "reference": "gold/x", "first": True, "metrics": {"scores": {"acc": 1.0}}}
    _runstore.make_run(
        root / "data" / "runs", RUN, REC, outputs={"i1": "a"}, scores=[{**first, "rows": [{"item_id": "i1"}]}]
    )
    return root / "data"


def ignored(root: Path, rel: str) -> bool:
    return subprocess.run(["git", "-C", str(root), "check-ignore", "-q", rel], check=False).returncode == 0


with tempfile.TemporaryDirectory() as tmp:
    kept_root, ignoring_root = Path(tmp) / "kept", Path(tmp) / "ignoring"
    kept = project(kept_root, IGNORE)
    ignoring = project(ignoring_root, ".build/\ndata/runs/\n")

    run_rel = f"data/runs/{RUN}"
    for what, rel, want in (
        ("a run's record", f"{run_rel}/run.json", False),
        ("its outputs", f"{run_rel}/outputs.jsonl", False),
        ("a score's record", f"{run_rel}/scores/s1@gold.x/score.json", False),
        ("a score's metrics", f"{run_rel}/scores/s1@gold.x/metrics.json", False),
        ("a score's rows", f"{run_rel}/scores/s1@gold.x/predictions.jsonl", False),
        ("the pass's checkpoint", f"{run_rel}/rows.partial.jsonl", True),
        ("a throwaway pass (evh run --scratch)", f".build/scratch/runs/{RUN}/run.json", True),
    ):
        check(
            f"init's .gitignore: {what} is {'ignored' if want else 'kept'}",
            ignored(kept_root, rel) is want,
            rel,
        )

    check(
        "ignored_by_git: data/runs of a project that keeps its runs is False",
        _common.ignored_by_git(kept / "runs") is False,
    )
    check(
        "ignored_by_git: data/runs of a project that ignores them is True",
        _common.ignored_by_git(ignoring / "runs") is True,
    )
    check(
        "ignored_by_git: a directory not yet created, under an ignored one",
        _common.ignored_by_git(kept_root / ".build" / "scratch" / "runs") is True,
    )
    check(
        "ignored_by_git: outside a checkout is False",
        _common.ignored_by_git(Path(tempfile.gettempdir())) is False,
    )

    def warned(d: Path) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _common.warn_if_ignored(d)
        return buf.getvalue()

    check(
        "warn: data/runs of a project that keeps its runs is silent",
        warned(kept / "runs") == "",
        warned(kept / "runs"),
    )
    out = warned(ignoring / "runs")
    check(
        "warn: an ignored runs directory warns, and says where a throwaway pass goes",
        "WARNING" in out and "data/runs" in out and "--scratch" in out,
        out,
    )

    # validate's note for finished runs git ignores: through the command, in each project.
    def validated(root: Path) -> str:
        env = {k: v for k, v in os.environ.items() if not k.startswith("EVAL_")}
        env.update(EVAL_HOME=str(root), EVAL_BUILD_REF="test-runs-location")
        (root / "data" / "project.yaml").write_text(f"format: {_format.FORMAT}\n")
        r = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "cli.py"), "validate"],
            cwd=root, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
        )  # fmt: skip
        return r.stdout + r.stderr

    got = validated(ignoring_root)
    check(
        "validate: one note, for the runs git ignores: a finished run",
        got.count("finished run(s) that git ignores") == 1 and "1 finished run(s)" in got,
        got[-400:],
    )
    got = validated(kept_root)
    check("validate: no such note where git keeps the runs", "git ignores" not in got, got[-400:])

    from evaluation_harness.catalog_adapter import HarnessAdapter

    # the catalog reads the runs git keeps, never one it ignores (it shows what a clone and the release show)
    (kept_root / ".gitignore").write_text(IGNORE + "data/runs/local_*/\n")
    _runstore.make_run(
        kept / "runs",
        "local_v1_20261031T000000Z",
        {**REC, "config_id": "local_v1"},
        scores=[
            {"scorer": "s1", "reference": "gold/x", "first": True, "rows": [{"item_id": "i1", "acc": 1.0}]}
        ],
    )
    seen = {a.split("/")[-1] for a in HarnessAdapter(kept).arms()}
    check(
        "catalog: reads the runs git keeps, never one it ignores (it shows what a clone and the release show)",
        seen == {"arm_v1"},
        seen,
    )

    # An arm someone committed is checked even when validate.json's list was not edited too.
    saved = validate_tree.policy, validate_tree.tracked_arms
    validate_tree.policy = lambda: {"committed": ["runs", "repeats"]}
    validate_tree.tracked_arms = lambda: ["runs", "new-set", "repeats"]
    try:
        arms_got = validate_tree.committed_arms()
    finally:
        validate_tree.policy, validate_tree.tracked_arms = saved
    check(
        "committed: the declared arms first, then every other tracked one",
        arms_got == ["runs", "repeats", "new-set"],
        arms_got,
    )


# One row per arm: a re-score with the current scorer stands in for the run it re-read.
def arm(name: str, runs: list, ref: str = "gold/x") -> dict:
    return {"arm": name, "reference": ref, "run_list": runs}


def run(rid: str, at: str, kind: str = "", src: str = "") -> dict:
    return {"run_id": rid, "created_at": at, "derived": kind, "from": src}


measured = arm("runs/x/a_v1", [run("a_v1_T1", "2026-10-30")])
rescored = arm("rescored-current/x/a_v1", [run("a_v1_T1", "2026-10-31", "rescore", "a_v1_T1")])
later = arm("rescored-later/x/a_v1", [run("a_v1_T1", "2026-11-01", "rescore", "a_v1_T1")])
silver = arm("silver/x/a_v1", [run("a_v1_T1", "2026-10-31", "rescore", "a_v1_T1")], ref="silver/x")
repeat = arm("repeats/x/a_v1", [run("a_v1_T2", "2026-10-31")])
half = arm("runs/x/b_v1", [run("b_v1_T1", "2026-10-30"), run("b_v1_T2", "2026-10-30")])
half_re = arm("rescored-current/x/b_v1", [run("b_v1_T1", "2026-10-31", "rescore", "b_v1_T1")])
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

# A measured arm whose run was re-scored says so on the arms page and in `evh arms`, beside the goals' choice: the
# re-score is a second score of the same run, under its own label.
with tempfile.TemporaryDirectory() as tmp:
    data = Path(tmp) / "data"
    ref = {"fingerprint": {"data": {"reference_id": "gold/x"}}}
    meta: dict = {"dataset_id": "x", "config_id": "a_v1", "created_at": "2026-10-31", **ref}
    rows = [{"item_id": "i1", "acc": 1.0}]
    _runstore.make_run(
        data / "runs",
        "a_v1_T1",
        meta,
        outputs={"i1": "a"},
        scores=[
            {"scorer": "old", "reference": "gold/x", "first": True, "rows": rows},
            {
                "scorer": "cur",
                "reference": "gold/x",
                "label": "rescored current",
                "metrics": {"derived": {"kind": "rescore", "from": "a_v1_T1", "from_dir": "runs/a_v1_T1"}},
                "rows": rows,
            },
        ],
    )
    from evaluation_harness import catalog_arms

    A = HarnessAdapter(data)
    arm_rows = {r["arm"]: r for r in catalog_arms.arm_rows(A, catalog_build.collect(A))}
    check(
        "arms: a measured arm re-scored against the same reference names the arm the goals read",
        arm_rows["runs/x/a_v1"]["superseded_by"] == "rescored-current/x/a_v1"
        and not arm_rows["rescored-current/x/a_v1"]["superseded_by"],
        arm_rows,
    )

sys.exit(summary())
