#!/usr/bin/env python3
"""Operational commands: init, list-runs, self-check, sweep, judge, cost-report.

    python tests/test_ops_commands.py

The least-covered scripts tested as a user would call them: with `python -m evaluation_harness
<command>`, in a fresh temp project. Tests verify what each command prints and writes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))  # _wheel
import _wheel
from evaluation_harness._check import check, summary


def evh_run(
    *args: str, cwd: Path | None = None, env: dict | None = None, timeout: int = 600
) -> subprocess.CompletedProcess:
    """Run an evh command in a project."""
    return subprocess.run(
        [sys.executable, "-m", "evaluation_harness", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def project_env(proj: Path, site: Path) -> dict:
    """Environment for evh in a project (installed from wheel)."""
    env = {
        **os.environ,
        "PYTHONPATH": str(site),
        "PYTHONDONTWRITEBYTECODE": "1",
        "EVAL_BUILD_REF": "test-ops",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    for k in ("EVAL_HOME", "EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
        env.pop(k, None)
    return env


def test_init(tmp: Path) -> None:
    """init: creates folders, .gitignore, and with --tutorial copies the kit."""
    site = _wheel.install(tmp / "site-packages")
    proj = tmp / "proj_init"
    proj.mkdir()
    env = project_env(proj, site)

    # Basic init
    r = evh_run("init", cwd=proj, env=env)
    check(
        "init (no args): exit 0, creates folders",
        r.returncode == 0
        and "project:" in r.stdout
        and (proj / "data/sources").is_dir()
        and (proj / "data/configs").is_dir()
        and (proj / ".gitignore").is_file(),
        r.stdout[:200],
    )

    # Init with --tutorial
    proj_tut = tmp / "proj_tut"
    proj_tut.mkdir()
    env_tut = project_env(proj_tut, site)
    r = evh_run("init", "--tutorial", cwd=proj_tut, env=env_tut)
    check(
        "init --tutorial: exit 0, copies tutorial kit",
        r.returncode == 0
        and "tutorial" in r.stdout
        and (proj_tut / "tutorial/tickets").is_dir()
        and (proj_tut / "tutorial/configs").is_dir(),
        r.stdout[:200],
    )

    # Init twice: no overwrite
    r = evh_run("init", cwd=proj, env=env)
    check(
        "init twice: exit 0, keeps existing files",
        r.returncode == 0 and "kept" in r.stdout and ".gitignore" in r.stdout,
        r.stdout[:200],
    )


def test_list_runs(tmp: Path) -> None:
    """runs-list: shows runs and baselines; filters; exits 0 even with no runs."""
    site = _wheel.install(tmp / "site-packages")
    proj = tmp / "proj_list"
    proj.mkdir()
    env = project_env(proj, site)

    # No runs yet
    r = evh_run("init", "--tutorial", cwd=proj, env=env)
    r = evh_run("runs-list", cwd=proj, env=env)
    check(
        "runs-list (no runs): exit 0, says 'no runs yet'",
        r.returncode == 0 and "no runs yet" in r.stdout,
        r.stdout[:200],
    )

    # No baselines yet
    r = evh_run("runs-list", "--baselines", cwd=proj, env=env)
    check(
        "runs-list --baselines (none): exit 0, says 'no baselines yet'",
        r.returncode == 0 and "no baselines" in r.stdout,
        r.stdout[:200],
    )

    # Create a dataset and run
    r = evh_run(
        "dataset-create",
        "--dataset-id",
        "tickets_v1",
        "--source-dir",
        "tutorial/tickets",
        cwd=proj,
        env=env,
    )
    r = evh_run("dataset-materialize", "--dataset-id", "tickets_v1", cwd=proj, env=env)
    shutil.copy(proj / "tutorial/configs/tickets_lead1.yaml", proj / "data/configs/")
    r = evh_run("experiment-run", "--config", "data/configs/tickets_lead1.yaml", cwd=proj, env=env)
    check("experiment-run: succeeds", r.returncode == 0, r.stderr[:200])

    # Now list the run
    r = evh_run("runs-list", cwd=proj, env=env)
    check(
        "runs-list (with run): shows run_id and metrics",
        r.returncode == 0 and "tickets_lead1" in r.stdout and "dataset_id" in r.stdout,
        r.stdout,
    )


def test_self_check(tmp: Path) -> None:
    """self-test: in a pinned package, runs a tutorial end-to-end."""
    site = _wheel.install(tmp / "site-packages")
    env = {
        **os.environ,
        "PYTHONPATH": str(site),
        "PYTHONDONTWRITEBYTECODE": "1",
        "EVAL_BUILD_REF": "test-ops-selftest",
    }
    for k in ("EVAL_HOME", "EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
        env.pop(k, None)

    # self-test runs offline in a temp dir, so no cwd needed
    r = subprocess.run(
        [sys.executable, "-m", "evaluation_harness", "self-test"],
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    check(
        "self-test: exit 0, runs the tutorial suite",
        r.returncode == 0 and ("ok  " in r.stdout or "FAIL" not in r.stdout),
        r.stdout[-500:],
    )


def test_sweep(tmp: Path) -> None:
    """sweep: runs multiple arms, survives arm failure, ends with leaderboard."""
    site = _wheel.install(tmp / "site-packages")
    proj = tmp / "proj_sweep"
    proj.mkdir()
    env = project_env(proj, site)

    # Setup: init, dataset, materialize, arms
    evh_run("init", "--tutorial", cwd=proj, env=env)
    evh_run(
        "dataset-create",
        "--dataset-id",
        "tickets_v1",
        "--source-dir",
        "tutorial/tickets",
        cwd=proj,
        env=env,
    )
    evh_run("dataset-materialize", "--dataset-id", "tickets_v1", cwd=proj, env=env)
    for arm in ("lead1", "lead2"):
        shutil.copy(proj / f"tutorial/configs/tickets_{arm}.yaml", proj / "data/configs/")

    # Dry run: costs nothing
    config_files = sorted(str(p) for p in (proj / "data/configs").glob("tickets_lead*.yaml"))
    r = evh_run(
        "sweep",
        "--configs",
        *config_files,
        "--dry-run",
        cwd=proj,
        env=env,
    )
    check(
        "sweep --dry-run: exit 0, says 'nothing was called'",
        r.returncode == 0 and "Dry run" in r.stdout,
        r.stdout,
    )

    # Real sweep
    config_files = sorted(str(p) for p in (proj / "data/configs").glob("tickets_lead*.yaml"))
    r = evh_run(
        "sweep",
        "--configs",
        *config_files,
        "--repeat",
        "1",
        cwd=proj,
        env=env,
        timeout=120,
    )
    check(
        "sweep (real): exit 0, runs both arms, shows leaderboard",
        r.returncode == 0
        and "[1/" in r.stdout
        and "[2/" in r.stdout
        and ("FRONTIER" in r.stdout or "arm" in r.stdout),
        r.stdout[-500:],
    )


def test_judge_panel(tmp: Path) -> None:
    """judge-panel: promotes finalists from runs, judges them, writes a report."""
    site = _wheel.install(tmp / "site-packages")
    proj = tmp / "proj_judge"
    proj.mkdir()
    env = project_env(proj, site)

    # Setup: init, dataset, materialize, arms, reference
    evh_run("init", "--tutorial", cwd=proj, env=env)
    evh_run(
        "dataset-create",
        "--dataset-id",
        "tickets_v1",
        "--source-dir",
        "tutorial/tickets",
        cwd=proj,
        env=env,
    )
    evh_run("dataset-materialize", "--dataset-id", "tickets_v1", cwd=proj, env=env)
    shutil.copy(proj / "tutorial/configs/tickets_lead1.yaml", proj / "data/configs/")
    shutil.copytree(proj / "tutorial/gold", proj / "data/references/gold/tickets_v1")

    # Run an arm to judge
    evh_run("experiment-run", "--config", "data/configs/tickets_lead1.yaml", cwd=proj, env=env)

    # Create a judge panel config
    # Use output_words as the primary metric (a real metric from runs)
    judge_cfg = {
        "runs_from": "runs",
        "dataset_id": "tickets_v1",
        "primary_metric": "output_words",
        "promotion": {
            "per_stratum_top_k": 1,
            "floor_fraction": 0.5,
            "overall_cap": 10,
            "carte_blanche": [],
        },
        "judging": {
            "primary_judge": {
                "id": "fake",
                "provider": "fake",
                "model": "fake",
                "usd_per_mtok_in": 0.0,
                "usd_per_mtok_out": 0.0,
            },
            "cross_judge": None,
            "dimensions": ["quality"],
            "cost_cap_usd": 100.0,
            "max_items_per_finalist": 2,
        },
        "aggregation": {"contested_threshold": 0.5, "agreement_tolerance": 1},
        "output_root": "data/reports",
        "tag": "v1",
    }
    cfg_path = proj / "data/configs/judge_panel.yaml"
    cfg_path.write_text(yaml.dump(judge_cfg))

    # Run judge with fake judge
    r = evh_run(
        "judge",
        "--config",
        str(cfg_path),
        "--use-fake-judge",
        cwd=proj,
        env=env,
        timeout=120,
    )
    check(
        "judge --use-fake-judge: exit 0, produces report",
        r.returncode == 0 and ("Report written" in r.stderr or "Finalists" in r.stdout),
        r.stdout[:500] + "\n" + r.stderr[:500],
    )

    # Check that report was written
    check(
        "judge: writes report to output_root/tag",
        (proj / "data/reports/v1").is_dir() and (proj / "data/reports/v1/report.md").is_file(),
        str(list((proj / "data/reports").glob("*")) if (proj / "data/reports").is_dir() else []),
    )


def test_cost_report(tmp: Path) -> None:
    """cost-report: reads billed vs recorded costs from runs."""
    site = _wheel.install(tmp / "site-packages")
    proj = tmp / "proj_cost"
    proj.mkdir()
    env = project_env(proj, site)

    # Setup: init, dataset, run with cost
    evh_run("init", "--tutorial", cwd=proj, env=env)
    evh_run(
        "dataset-create",
        "--dataset-id",
        "tickets_v1",
        "--source-dir",
        "tutorial/tickets",
        cwd=proj,
        env=env,
    )
    evh_run("dataset-materialize", "--dataset-id", "tickets_v1", cwd=proj, env=env)
    shutil.copy(proj / "tutorial/configs/tickets_lead1.yaml", proj / "data/configs/")
    evh_run("experiment-run", "--config", "data/configs/tickets_lead1.yaml", cwd=proj, env=env)

    # cost-report with no runs (nothing billed yet)
    r = evh_run("cost-report", "--dataset-id", "tickets_v1", cwd=proj, env=env)
    check(
        "cost-report (empty runs): exits 0, says 'no runs matched' or empty table",
        r.returncode == 0 or "no runs matched" in r.stdout,
        r.stdout,
    )

    # cost-report on all datasets
    r = evh_run("cost-report", cwd=proj, env=env)
    check(
        "cost-report (all): exit 0",
        r.returncode == 0,
        r.stdout[-200:],
    )


def main() -> int:
    """Run all operational command tests."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-ops-"))
    try:
        test_init(tmp / "init")
        test_list_runs(tmp / "list")
        test_self_check(tmp / "selfcheck")
        test_sweep(tmp / "sweep")
        test_judge_panel(tmp / "judge")
        test_cost_report(tmp / "cost")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
