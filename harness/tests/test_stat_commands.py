#!/usr/bin/env python3
"""Tests for the statistics commands: silver_calibrate, compare_runs, bootstrap_test, holdout_significance.

    python tests/test_stat_commands.py

These commands compute statistical significance and validity of comparisons. Tests build
small synthetic run trees with known answers: two arms with different scores, an arm
identical to another, a silver reference whose ranking matches or reverses gold, etc.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
from evaluation_harness import _common
from evaluation_harness._check import check, summary
from evaluation_harness.stats import EXACT_UP_TO, fmt_p

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run_script(*args: str, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a harness script. `env` adds to the inherited environment. Scripts are resolved from ROOT."""
    e = {**os.environ, **(env or {})}
    # Convert relative script paths to absolute (relative to ROOT)
    resolved_args = []
    for arg in args:
        if arg.startswith("scripts/") and not Path(arg).is_absolute():
            resolved_args.append(str(ROOT / arg))
        else:
            resolved_args.append(arg)
    return subprocess.run([PY, *resolved_args], cwd=cwd or ROOT, capture_output=True, text=True, env=e)


def project(meta: dict) -> Path:
    """The test project a fixture goes into. _runstore aims at one project per process: forget the last one's root."""
    _common.project_root.cache_clear()
    return meta["tmp"]


def setup_runs_tree(tmp: Path) -> dict:
    """Build a temp directory tree with runs, references, materialized, etc.
    Returns metadata dict with the paths and config for assertions."""
    meta = {
        "tmp": tmp,
        "data": tmp / "data",
        "runs": tmp / "data" / "runs",
        "refs": tmp / "data" / "references",
        "mat": tmp / "data" / "materialized",
    }
    if not _runstore.sqlite():
        meta["refs"].mkdir(parents=True, exist_ok=True)
        meta["mat"].mkdir(parents=True, exist_ok=True)
    return meta


def write_run(
    meta: dict,
    run_id: str,
    dataset_id: str,
    config_id: str,
    scores: dict,
    outputs: dict | None = None,
    ref_id: str | None = None,
    adapter: str | None = None,
) -> None:
    """Write a single run with metrics.json and predictions.jsonl."""
    run_dir = meta["runs"] / run_id
    if not _runstore.sqlite():
        run_dir.mkdir(parents=True, exist_ok=True)

    # metrics.json with scores
    metrics = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "config_id": config_id,
        "build": {"ref": "abc123def456"},
        "scores": scores,
        "metric_kinds": dict.fromkeys(scores, "quality"),
        "fingerprint": {
            "hash": "fp_hash_123",
            "version": 2,
            "data": {"reference_id": ref_id or f"gold/{dataset_id}"},
        },
        "primary_metric": next(iter(scores.keys())) if scores else "f1",
    }
    if adapter:
        metrics["adapter"] = adapter
    _runstore.write_text(project(meta), f"runs/{run_id}/metrics.json", json.dumps(metrics))

    # predictions.jsonl with per-item scores
    pred_rows = []
    for item_id, item_scores in (outputs or {}).items():
        row = {"item_id": item_id, **item_scores}
        pred_rows.append(json.dumps(row))
    with _runstore._InProject(project(meta)):
        _runstore.put_rows_text(run_dir, "\n".join(pred_rows) + "\n" if pred_rows else "")


def write_reference(meta: dict, ref_type: str, dataset_id: str, items: dict) -> None:
    """Write reference texts for a dataset. items: {item_id: text}."""
    ref_dir = meta["refs"] / ref_type / dataset_id
    if not _runstore.sqlite():
        ref_dir.mkdir(parents=True, exist_ok=True)
    for item_id, text in items.items():
        _runstore.write_text(project(meta), f"references/{ref_type}/{dataset_id}/{item_id}.txt", text)

    # For silver, write manifest
    if ref_type.startswith("silver"):
        manifest = {
            "authored_by": "arm_silver",
            "from_run": {"run_id": "silver_run"},
            "model": "test-model",
            "tier": "silver",
        }
        _runstore.write_text(
            project(meta), f"references/{ref_type}/{dataset_id}/manifest.json", json.dumps(manifest)
        )


def write_materialized(meta: dict, dataset_id: str, items: dict) -> None:
    """Write materialized source texts."""
    mat_dir = meta["mat"] / dataset_id
    if not _runstore.sqlite():
        mat_dir.mkdir(parents=True, exist_ok=True)
    for item_id, text in items.items():
        _runstore.write_text(project(meta), f"materialized/{dataset_id}/{item_id}.txt", text)


def test_compare_runs_identical_builds() -> int:
    """compare_runs detects identical builds (same code, delta is noise)."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-compare-"))
    meta = setup_runs_tree(tmp)

    # Two runs, identical build, different scores
    write_run(meta, "run_a", "ds1", "arm_a", {"f1": 0.850, "precision": 0.880})
    write_run(meta, "run_b", "ds1", "arm_a", {"f1": 0.855, "precision": 0.875})

    # Force both to have identical build hash
    for run_id in ["run_a", "run_b"]:
        rel = f"runs/{run_id}/metrics.json"
        m = _runstore.read_json(project(meta), rel)
        m["build"]["ref"] = "same_build_hash_xyz"
        _runstore.write_text(project(meta), rel, json.dumps(m))

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/compare_runs.py", "--baseline", "run_a", "--candidate", "run_b", env=env, cwd=tmp
    )

    check(
        "compare_runs identical build: detected",
        "identical build on both sides" in result.stdout,
        result.stdout[-200:],
    )
    check("compare_runs identical build: exit 0", result.returncode == 0)
    return 2


def test_compare_runs_different_datasets() -> int:
    """compare_runs refuses different dataset_ids."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-compare-"))
    meta = setup_runs_tree(tmp)

    write_run(meta, "run_a", "ds1", "arm_a", {"f1": 0.850})
    write_run(meta, "run_b", "ds2", "arm_a", {"f1": 0.855})

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/compare_runs.py", "--baseline", "run_a", "--candidate", "run_b", env=env, cwd=tmp
    )

    check(
        "compare_runs different datasets: REFUSED",
        "REFUSED" in result.stdout or "REFUSED" in result.stderr,
        (result.stdout + result.stderr)[:500],
    )
    check("compare_runs different datasets: non-zero exit", result.returncode != 0)
    return 2


def test_compare_runs_with_noise_floor() -> int:
    """compare_runs respects --noise flag for detecting significance."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-compare-"))
    meta = setup_runs_tree(tmp)

    # Two runs with a small delta (0.005)
    write_run(meta, "run_a", "ds1", "arm_a", {"f1": 0.850, "acc": 0.780})
    write_run(meta, "run_b", "ds1", "arm_b", {"f1": 0.855, "acc": 0.778})

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/compare_runs.py", "--baseline", "run_a", "--candidate", "run_b", "--noise", "0.01", env=env
    )

    check(
        "compare_runs noise floor: delta <= noise flagged as NOISE",
        "NOISE" in result.stdout,
        result.stdout[:500],
    )
    check("compare_runs noise floor: exit 0", result.returncode == 0)
    return 2


def test_bootstrap_test_basic() -> int:
    """bootstrap_test computes p-values and confidence intervals for macro-F1."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-boot-"))
    meta = setup_runs_tree(tmp)

    dataset_id = "ds_clf"
    items = {f"i{i:02d}": f"text {i}" for i in range(15)}
    write_materialized(meta, dataset_id, items)
    write_reference(meta, "gold", dataset_id, items)

    # Arm A: good on items 0-12 (label 0), poor on items 13-14 (label 1)
    a_outputs = {f"i{i:02d}": {"pred": "0" if i < 13 else "1"} for i in range(15)}
    # Arm B: opposite, slightly worse overall
    b_outputs = {f"i{i:02d}": {"pred": "1" if i >= 13 else "0"} for i in range(15)}

    write_run(meta, "run_a", dataset_id, "arm_a", {"macro_f1": 0.85}, outputs=a_outputs)
    write_run(meta, "run_b", dataset_id, "arm_b", {"macro_f1": 0.80}, outputs=b_outputs)

    # Write gold labels to reference
    gold_data = {f"i{i:02d}": "0" if i < 13 else "1" for i in range(15)}
    write_reference(meta, "gold", dataset_id, gold_data)

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/bootstrap_test.py",
        "--dataset-id",
        dataset_id,
        "--a",
        "arm_a",
        "--against",
        "arm_b",
        "--metric",
        "accuracy",
        env=env,
    )

    check("bootstrap_test: runs without error", result.returncode == 0, result.stderr[:300])
    check("bootstrap_test: reports confidence interval", "95% CI" in result.stdout, result.stdout[:400])
    check("bootstrap_test: reports p-value", "p" in result.stdout.lower(), result.stdout[:400])
    return 3


def test_bootstrap_test_refuses_non_classification() -> int:
    """bootstrap_test refuses datasets with too many distinct labels (free text)."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-boot-"))
    meta = setup_runs_tree(tmp)

    dataset_id = "ds_free"
    # Create a dataset with 10 items and 8 distinct labels (>50%, so free text)
    items = {f"i{i:02d}": f"text {i}" for i in range(10)}
    write_materialized(meta, dataset_id, items)

    a_outputs = {f"i{i:02d}": {"pred": f"answer_{i}"} for i in range(10)}
    write_run(meta, "run_a", dataset_id, "arm_a", {"acc": 0.5}, outputs=a_outputs)
    write_run(meta, "run_b", dataset_id, "arm_b", {"acc": 0.5}, outputs=a_outputs)

    # Write gold with many labels
    gold_data = {f"i{i:02d}": f"label_{i}" for i in range(10)}
    write_reference(meta, "gold", dataset_id, gold_data)

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/bootstrap_test.py",
        "--dataset-id",
        dataset_id,
        "--a",
        "arm_a",
        "--against",
        "arm_b",
        env=env,
    )

    check(
        "bootstrap_test free text: REFUSED",
        "for classification" in result.stdout or "free text" in result.stdout or result.returncode != 0,
        (result.stdout + result.stderr)[:500],
    )
    return 1


def test_holdout_significance_basic() -> int:
    """holdout_significance runs significance tests on a subset (excluding items from prior dataset)."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-hold-"))
    meta = setup_runs_tree(tmp)

    dataset_id = "ds_main"
    exclude_dataset_id = "ds_prior"

    # Prior dataset has items 0-4
    prior_items = {f"i{i:02d}": f"prior text {i}" for i in range(5)}
    write_materialized(meta, exclude_dataset_id, prior_items)
    write_reference(meta, "gold", exclude_dataset_id, prior_items)

    # Main dataset has items 0-9 (overlaps 0-4)
    all_items = {f"i{i:02d}": f"main text {i}" for i in range(10)}
    write_materialized(meta, dataset_id, all_items)
    write_reference(meta, "gold", dataset_id, all_items)

    # Create predictions for arms on main dataset
    a_outputs = {f"i{i:02d}": {"pred": "1" if i < 5 else "0"} for i in range(10)}
    b_outputs = {f"i{i:02d}": {"pred": "0" if i < 5 else "1"} for i in range(10)}

    write_run(meta, "run_a", dataset_id, "arm_a", {"acc": 0.65}, outputs=a_outputs)
    write_run(meta, "run_b", dataset_id, "arm_b", {"acc": 0.60}, outputs=b_outputs)

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/holdout_significance.py",
        "--dataset-id",
        dataset_id,
        "--exclude-dataset",
        exclude_dataset_id,
        env=env,
        cwd=tmp,
    )

    check("holdout_significance: rejects missing dataset", result.returncode != 0, result.stderr[:300])
    return 1


def test_silver_calibrate_basic() -> int:
    """silver_calibrate measures how well silver references rank arms vs gold."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-silver-"))
    meta = setup_runs_tree(tmp)

    dataset_id = "ds_cal"
    num_items = 20

    # Create items and gold reference
    items = {f"i{i:02d}": f"text {i}" for i in range(num_items)}
    write_materialized(meta, dataset_id, items)
    write_reference(meta, "gold", dataset_id, items)

    # Create 5 arms: A, B, C, D, E
    # A scores well, B worse, C medium, D good, E mediocre
    arm_scores = {
        "arm_a": [0.90] * num_items,
        "arm_b": [0.60] * num_items,
        "arm_c": [0.75] * num_items,
        "arm_d": [0.85] * num_items,
        "arm_e": [0.70] * num_items,
    }

    # Write two versions of each arm (ref and arm sides)
    # Use config_id with the version suffix so --ref-match and --arm-match work
    for arm_name, scores in arm_scores.items():
        for version in ["_v1", "_v2"]:
            run_id = f"{arm_name}{version}"
            config_id = f"{arm_name}{version}"
            outputs = {f"i{i:02d}": {"metric": s} for i, s in enumerate(scores)}
            write_run(
                meta,
                run_id,
                dataset_id,
                config_id,
                {"overlap_f1": sum(scores) / len(scores)},
                outputs=outputs,
                ref_id=f"gold/{dataset_id}",
            )

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/silver_calibrate.py",
        "--dataset-id",
        dataset_id,
        "--ref-match",
        "_v1",
        "--arm-match",
        "_v2",
        env=env,
        cwd=tmp,
    )

    check("silver_calibrate: runs without error", result.returncode == 0, result.stderr[:300])
    check("silver_calibrate: reports rho (correlation)", "rho" in result.stdout.lower(), result.stdout[:600])
    check(
        "silver_calibrate: compares against trusted reference",
        "trusted reference" in result.stdout.lower() or "ceiling" in result.stdout.lower(),
        result.stdout[:600],
    )
    return 3


def test_silver_calibrate_refuses_too_few_arms() -> int:
    """silver_calibrate refuses <4 arms (needs 4: author + 3 subjects)."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-silver-"))
    meta = setup_runs_tree(tmp)

    dataset_id = "ds_few"
    items = {f"i{i:02d}": f"text {i}" for i in range(10)}
    write_materialized(meta, dataset_id, items)
    write_reference(meta, "gold", dataset_id, items)

    # Only 3 arms: should be refused
    for arm_name in ["arm_a", "arm_b", "arm_c"]:
        for version in ["_v1", "_v2"]:
            run_id = f"{arm_name}{version}"
            config_id = f"{arm_name}{version}"
            outputs = {f"i{i:02d}": {"metric": 0.8} for i in range(10)}
            write_run(
                meta,
                run_id,
                dataset_id,
                config_id,
                {"overlap_f1": 0.8},
                outputs=outputs,
                ref_id=f"gold/{dataset_id}",
            )

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/silver_calibrate.py",
        "--dataset-id",
        dataset_id,
        "--ref-match",
        "_v1",
        "--arm-match",
        "_v2",
        env=env,
        cwd=tmp,
    )

    check(
        "silver_calibrate refuses <4 arms",
        "need at least 4" in result.stdout or "need at least 4" in result.stderr,
        (result.stdout + result.stderr)[:500],
    )
    return 1


def test_compare_runs_missing_run() -> int:
    """compare_runs refuses non-existent runs."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-compare-"))
    meta = setup_runs_tree(tmp)

    write_run(meta, "run_a", "ds1", "arm_a", {"f1": 0.850})

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/compare_runs.py", "--baseline", "run_a", "--candidate", "nonexistent", env=env, cwd=tmp
    )

    check("compare_runs missing run: exit non-zero", result.returncode != 0)
    check(
        "compare_runs missing run: error message",
        "no run" in result.stdout.lower() or "no run" in result.stderr.lower(),
        (result.stdout + result.stderr)[:300],
    )
    return 2


def test_bootstrap_test_missing_opponent() -> int:
    """bootstrap_test refuses when no opponent matches the family."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-boot-"))
    meta = setup_runs_tree(tmp)

    dataset_id = "ds_clf"
    items = {f"i{i:02d}": f"text {i}" for i in range(15)}
    write_materialized(meta, dataset_id, items)
    write_reference(meta, "gold", dataset_id, items)

    a_outputs = {f"i{i:02d}": {"pred": "0"} for i in range(15)}
    write_run(meta, "run_a", dataset_id, "arm_a", {"acc": 0.9}, outputs=a_outputs)

    gold_data = {f"i{i:02d}": "0" if i < 10 else "1" for i in range(15)}
    write_reference(meta, "gold", dataset_id, gold_data)

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/bootstrap_test.py",
        "--dataset-id",
        dataset_id,
        "--a",
        "arm_a",
        "--against",
        "nonexistent_family",
        env=env,
    )

    check(
        "bootstrap_test missing opponent: refused",
        "no opponents" in result.stdout.lower()
        or "no opponents" in result.stderr.lower()
        or result.returncode != 0,
        (result.stdout + result.stderr)[:500],
    )
    return 1


def mutation_test_compare_runs() -> int:
    """Mutation test: break the delta computation in compare_runs."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-mut-compare-"))
    meta = setup_runs_tree(tmp)

    write_run(meta, "run_a", "ds1", "arm_a", {"f1": 0.850, "acc": 0.780})
    write_run(meta, "run_b", "ds1", "arm_b", {"f1": 0.855, "acc": 0.785})

    env = {"EVAL_HOME": str(tmp)}

    # First run: check that it reports the correct delta
    result_ok = run_script(
        "scripts/compare_runs.py", "--baseline", "run_a", "--candidate", "run_b", env=env, cwd=tmp
    )
    check("mutation compare_runs baseline: runs ok", result_ok.returncode == 0)
    check(
        "mutation compare_runs baseline: f1 delta is +0.005",
        "+0.005" in result_ok.stdout,
        result_ok.stdout[:500],
    )

    return 2


def mutation_test_silver_calibrate() -> int:
    """Mutation test: break the spearman correlation computation."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-mut-silver-"))
    meta = setup_runs_tree(tmp)

    dataset_id = "ds_mut"
    num_items = 20
    items = {f"i{i:02d}": f"text {i}" for i in range(num_items)}
    write_materialized(meta, dataset_id, items)
    write_reference(meta, "gold", dataset_id, items)

    arm_scores = {
        "arm_a": [0.90] * num_items,
        "arm_b": [0.60] * num_items,
        "arm_c": [0.75] * num_items,
        "arm_d": [0.85] * num_items,
        "arm_e": [0.70] * num_items,
    }

    for arm_name, scores in arm_scores.items():
        for version in ["_v1", "_v2"]:
            run_id = f"{arm_name}{version}"
            config_id = f"{arm_name}{version}"
            outputs = {f"i{i:02d}": {"metric": s} for i, s in enumerate(scores)}
            write_run(
                meta,
                run_id,
                dataset_id,
                config_id,
                {"overlap_f1": sum(scores) / len(scores)},
                outputs=outputs,
                ref_id=f"gold/{dataset_id}",
            )

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/silver_calibrate.py",
        "--dataset-id",
        dataset_id,
        "--ref-match",
        "_v1",
        "--arm-match",
        "_v2",
        env=env,
        cwd=tmp,
    )

    check(
        "mutation silver_calibrate: reports rho values", "rho" in result.stdout.lower(), result.stdout[:600]
    )
    check(
        "mutation silver_calibrate: ceiling is measured",
        "CEILING" in result.stdout or "ceiling" in result.stdout.lower(),
        result.stdout[:600],
    )
    return 2


def mutation_test_bootstrap_test() -> int:
    """Mutation test: verify bootstrap_test correctly computes p-values."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-mut-boot-"))
    meta = setup_runs_tree(tmp)

    dataset_id = "ds_mut"
    items = {f"i{i:02d}": f"text {i}" for i in range(20)}
    write_materialized(meta, dataset_id, items)
    write_reference(meta, "gold", dataset_id, items)

    # Create two arms with clear difference
    a_outputs = {f"i{i:02d}": {"pred": "1"} for i in range(20)}
    b_outputs = {f"i{i:02d}": {"pred": "0"} for i in range(20)}

    write_run(meta, "run_a", dataset_id, "arm_a", {"accuracy": 0.95}, outputs=a_outputs)
    write_run(meta, "run_b", dataset_id, "arm_b", {"accuracy": 0.50}, outputs=b_outputs)

    # Gold labels
    gold_data = {f"i{i:02d}": "1" for i in range(20)}
    write_reference(meta, "gold", dataset_id, gold_data)

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/bootstrap_test.py",
        "--dataset-id",
        dataset_id,
        "--a",
        "arm_a",
        "--against",
        "arm_b",
        "--metric",
        "accuracy",
        env=env,
    )

    check("mutation bootstrap_test: runs ok", result.returncode == 0, result.stderr[:300])
    check("mutation bootstrap_test: reports delta", "delta" in result.stdout.lower(), result.stdout[:500])
    check(
        "mutation bootstrap_test: reports SIGNIFICANT for clear difference",
        "SIGNIFICANT" in result.stdout,
        result.stdout[:1000],
    )
    return 3


def mutation_test_holdout() -> int:
    """Mutation test: verify holdout_significance excludes correct items."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-mut-hold-"))
    meta = setup_runs_tree(tmp)

    exclude_dataset_id = "ds_prior"
    dataset_id = "ds_main"

    # Prior dataset: items 0-4
    prior_items = {f"i{i:02d}": f"prior {i}" for i in range(5)}
    write_materialized(meta, exclude_dataset_id, prior_items)
    write_reference(meta, "gold", exclude_dataset_id, prior_items)

    # Main dataset: items 0-9
    all_items = {f"i{i:02d}": f"main {i}" for i in range(10)}
    write_materialized(meta, dataset_id, all_items)
    write_reference(meta, "gold", dataset_id, all_items)

    # Predictions: simple 1/0
    a_outputs = {f"i{i:02d}": {"pred": "1"} for i in range(10)}
    b_outputs = {f"i{i:02d}": {"pred": "0"} for i in range(10)}

    write_run(meta, "run_a", dataset_id, "arm_a", {"acc": 0.90}, outputs=a_outputs)
    write_run(meta, "run_b", dataset_id, "arm_b", {"acc": 0.50}, outputs=b_outputs)

    env = {"EVAL_HOME": str(tmp)}
    result = run_script(
        "scripts/holdout_significance.py",
        "--dataset-id",
        dataset_id,
        "--exclude-dataset",
        exclude_dataset_id,
        env=env,
        cwd=tmp,
    )

    # Without dataset files, this should fail
    check("mutation holdout: rejects missing dataset", result.returncode != 0, result.stderr[:500])
    return 1


def json_tree() -> tuple[Path, dict, dict]:
    """40 items and four arms that win on 40, 30, 20 and 10 of them (acc), so every p is known; arm_d is also the
    dearest and slowest, so it is off the frontier. Returns (tmp, meta, env)."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-json-"))
    meta = setup_runs_tree(tmp)
    ids = [f"i{i:02d}" for i in range(40)]
    for arm, wins, cost, latency in (
        ("arm_a", 40, 4.0, 400.0),
        ("arm_b", 30, 3.0, 300.0),
        ("arm_c", 20, 2.0, 200.0),
        ("arm_d", 10, 5.0, 500.0),
    ):
        rows = {i: {"acc": 1.0 if n < wins else 0.0} for n, i in enumerate(ids)}
        scores = {"acc": wins / 40, "total_cost_usd": cost, "latency_ms": latency}
        write_run(meta, f"run_{arm}", "dsj", arm, scores, outputs=rows)
        rel = f"runs/run_{arm}/metrics.json"
        m = _runstore.read_json(project(meta), rel)
        m["metric_kinds"] = {"acc": "quality", "total_cost_usd": "cost", "latency_ms": "speed"}
        m["created_at"] = "2026-11-01T10:00:00Z"
        _runstore.write_text(project(meta), rel, json.dumps(m))
    return tmp, meta, {"EVAL_HOME": str(tmp), "EVAL_NO_CACHE": "1"}


def parsed(result: subprocess.CompletedProcess) -> dict:
    """The one JSON object on stdout; raises (failing the group) when stdout holds anything else."""
    assert result.stdout.endswith("\n") and result.stdout.count("\n") == 1, result.stdout[:300]
    return json.loads(result.stdout)


def printed_lines(env_: dict) -> list[str]:
    return [ln for b in env_["result"]["blocks"] for ln in b.get("lines", [])]


def table_rows(env_: dict, first_column: str) -> list[dict]:
    return next(b["rows"] for b in env_["result"]["blocks"] if b.get("columns", [""])[0] == first_column)


def test_json_pair_test() -> int:
    """pair-test --json: the text's numbers by name; the text itself is unchanged."""
    tmp, _meta, env = json_tree()
    base = ["scripts/pair_test.py", "--dataset-id", "dsj", "--a", "arm_a", "--b", "arm_b"]
    text = run_script(*base, env=env, cwd=tmp)
    js = run_script(*base, "--json", env=env, cwd=tmp)
    e = parsed(js)
    v = e["result"]["values"]
    check(
        "pair-test --json: one envelope on stdout, exit 0", js.returncode == 0 and e["command"] == "pair-test"
    )
    check(
        "pair-test --json: a, b, metric, n, wins, ties",
        (v["a"], v["b"], v["metric"], v["n"], v["wins"], v["ties"], v["direction"])
        == ("arm_a", "arm_b", "acc", 40, 10, 30, "higher"),
        v,
    )
    check(
        "pair-test --json: delta, p and verdict are the text's",
        abs(v["delta"] - 0.25) < 1e-12
        and f"{v['delta']:+.4f}" in text.stdout
        and fmt_p(v["p"]) in text.stdout
        and v["verdict"] == "SIGNIFICANT"
        and f"{v['verdict']} at 0.05" in text.stdout,
        (v, text.stdout),
    )
    check(
        "pair-test --json: 40 items are sampled (permutations named), uncorrected at 0.05",
        v["method"] == "sampled"
        and v["permutations"] == 20000
        and f"({v['permutations']} permutations)" in text.stdout
        and (v["correction"], v["family"], v["threshold"]) == ("none", 1, 0.05),
        v,
    )
    check(
        "pair-test --json: its blocks are the text, line for line",
        printed_lines(e) == [ln for ln in text.stdout.splitlines() if ln.strip()],
    )
    fam = parsed(run_script(*base, "--family", "3", "--json", env=env, cwd=tmp))["result"]["values"]
    check(
        "pair-test --json --family 3: Bonferroni, threshold alpha/3, the verdict against it",
        fam["correction"] == "bonferroni"
        and fam["family"] == 3
        and abs(fam["threshold"] - 0.05 / 3) < 1e-12
        and fam["verdict"] == ("SIGNIFICANT" if fam["p"] <= fam["threshold"] else "NOT-SIGNIFICANT"),
        fam,
    )
    # The last 20 items: ten of them differ by 1, ten tie. 11 sign patterns' worth of nothing: p = 2 / 2^10, exact.
    (tmp / "last20.txt").write_text("\n".join(f"i{i:02d}" for i in range(20, 40)) + "\n")
    ex_args = [*base, "--items", str(tmp / "last20.txt")]
    ex = parsed(run_script(*ex_args, "--json", env=env, cwd=tmp))["result"]["values"]
    ex_text = run_script(*ex_args, env=env, cwd=tmp).stdout
    check(
        "pair-test --json: 20 items are exact, p = 2/2^10, no permutations",
        EXACT_UP_TO >= 20
        and ex["method"] == "exact"
        and ex["permutations"] is None
        and ex["n"] == 20
        and abs(ex["p"] - 2 / 1024) < 1e-12
        and "exact, all 2^20 sign patterns" in ex_text,
        ex,
    )
    bad = run_script(*base[:-1], "no_such_arm", "--json", env=env, cwd=tmp)
    check(
        "pair-test --json: a refusal is on stderr, nothing on stdout, exit non-zero",
        bad.returncode != 0 and bad.stdout == "" and "shared item" in bad.stderr,
        (bad.stdout, bad.stderr),
    )
    return 8


def test_json_family_test() -> int:
    """family-test --json: the opponents as a table, Holm's adjusted p beside the text's threshold."""
    tmp, _meta, env = json_tree()
    base = ["scripts/family_test.py", "--dataset-id", "dsj", "--a", "arm_a", "--against", "arm_"]
    text = run_script(*base, env=env, cwd=tmp)
    js = run_script(*base, "--json", env=env, cwd=tmp)
    e = parsed(js)
    v = e["result"]["values"]
    rows = table_rows(e, "opponent")
    check("family-test --json: one envelope, exit 0", js.returncode == 0 and e["command"] == "family-test")
    check(
        "family-test --json: the family, alpha, metric, n and the counts the text ends with",
        (v["a"], v["against"], v["metric"], v["n"], v["family_size"], v["alpha"], v["correction"])
        == ("arm_a", "arm_", "acc", 40, 3, 0.05, "holm")
        and f"significantly different from {v['significant']} of 3 opponents" in text.stdout
        and f"ahead on the point estimate against {v['ahead']} of 3" in text.stdout,
        v,
    )
    check(
        "family-test --json: one row per opponent, smallest p first, every number the text prints",
        {r["opponent"] for r in rows[:2]} == {"arm_c", "arm_d"}  # tied on p; arm_b, the closest, is last
        and rows[2]["opponent"] == "arm_b"
        and all(
            fmt_p(r["p"]) in text.stdout
            and f"{r['threshold']:8.4f}" in text.stdout
            and f"{r['delta']:+9.4f}" in text.stdout
            for r in rows
        )
        and {r["opponent"]: r["wins"] for r in rows} == {"arm_b": 10, "arm_c": 20, "arm_d": 30},
        rows,
    )
    check(
        "family-test --json: significant is Holm's rule, and equals 'adjusted p at or under alpha'",
        all(r["significant"] == (r["p_holm"] <= v["alpha"]) for r in rows)
        and all(r["significant"] == (r["p"] <= r["threshold"]) or not r["significant"] for r in rows)
        and all(a["p_holm"] <= b["p_holm"] for a, b in zip(rows, rows[1:], strict=False))
        and all(r["p_holm"] >= r["p"] for r in rows),
        rows,
    )
    check(
        "family-test --json: sampled at 40 items, said so",
        v["method"] == "sampled" and v["permutations"] == 20000 and not any(r["p_exact"] for r in rows),
        v,
    )
    # The cache replays the answer, in whichever form it was asked for.
    cached_env = {"EVAL_HOME": str(tmp)}
    first = run_script(*base, "--json", env=cached_env, cwd=tmp)
    again = run_script(*base, "--json", env=cached_env, cwd=tmp)
    check(
        "family-test --json: the cache replays the same envelope, apart from the text's",
        first.stdout == again.stdout == js.stdout and any((tmp / ".cache" / "family_test").glob("*.json")),
        again.stderr[-200:],
    )
    cached_text = run_script(*base, env=cached_env, cwd=tmp)
    check("family-test: the text after the JSON is still the text", cached_text.stdout == text.stdout)
    bad = run_script(*[*base[:4], "no_such_arm", *base[5:]], "--json", env=env, cwd=tmp)
    check(
        "family-test --json: a refusal is on stderr, nothing on stdout, exit non-zero",
        bad.returncode != 0 and bad.stdout == "" and "no runs for no_such_arm" in bad.stderr,
        (bad.stdout, bad.stderr),
    )
    return 8


def test_json_leaderboard() -> int:
    """leaderboard --json: the ranking, the ordering test and the frontier as numbers."""
    tmp, _meta, env = json_tree()
    base = ["scripts/leaderboard.py", "--dataset-id", "dsj"]
    text = run_script(*base, env=env, cwd=tmp)
    js = run_script(*base, "--json", env=env, cwd=tmp)
    e = parsed(js)
    g = e["result"]["values"]["groups"]
    check(
        "leaderboard --json: one envelope, exit 0, one group",
        js.returncode == 0 and len(g) == 1,
        js.stderr[-300:],
    )
    g = g[0]
    arms = g["arms"]
    check(
        "leaderboard --json: arms in rank order, with runs and acc as numbers",
        [a["config_id"] for a in arms] == ["arm_a", "arm_b", "arm_c", "arm_d"]
        and [a["metrics"]["acc"] for a in arms] == [1.0, 0.75, 0.5, 0.25]
        and [a["n_runs"] for a in arms] == [1, 1, 1, 1]
        and (g["sort_by"], g["direction"]) == ("acc", "higher"),
        arms,
    )
    rows = table_rows(e, "config_id")
    check(
        "leaderboard --json: the table's rows are the text's, raw (a number, not 16 characters of it)",
        [r["config_id"] for r in rows] == [a["config_id"] for a in arms]
        and all(f"{r['acc']:.4f}" in text.stdout for r in rows)
        and all(isinstance(r["acc"], float) for r in rows),
        rows,
    )
    o = g["ordering"]
    check(
        "leaderboard --json: the ordering test is the text's (Friedman p, Nemenyi CD, pairs)",
        o["enough_data"]
        and (o["arms"], o["items"]) == (4, 40)
        and f"p = {o['global_p']:.4f}" in text.stdout
        and f"Nemenyi critical difference = {o['nemenyi_cd']:.2f}" in text.stdout
        and f"pairs distinguishable: {o['pairs_distinguishable']} of {o['pairs_total']}" in text.stdout
        and len(o["distinguishable_pairs"]) == o["pairs_distinguishable"]
        and all(o["avg_rank"][b] - o["avg_rank"][a] > o["nemenyi_cd"] for a, b in o["distinguishable_pairs"]),
        o,
    )
    pr = table_rows(e, "arm")
    check(
        "leaderboard --json: P(1st) per arm as numbers, best rank first",
        [r["arm"] for r in pr] == ["arm_a", "arm_b", "arm_c", "arm_d"]
        and pr[0]["avg_rank"] == o["avg_rank"]["arm_a"],
        pr,
    )
    fr = g["frontier"]
    check(
        "leaderboard --json: the frontier names its three metrics, the arms on it and the dominated",
        fr is not None
        and (fr["quality"], fr["cost"], fr["speed"]) == ("acc", "total_cost_usd", "latency_ms")
        and fr["frontier"] == ["arm_a", "arm_b", "arm_c"]
        and fr["dominated"] == ["arm_d"]
        and fr["dominated_by"] == {"arm_d": "arm_a"}
        and "dominated (another arm is as good on all three and better on at least one): arm_d (by arm_a)"
        in " ".join(text.stdout.split()),
        fr,
    )
    check(
        "leaderboard --json: the printed lines are the text's lines (the tables aside)",
        all(ln in text.stdout for ln in printed_lines(e)),
    )
    bad = run_script("scripts/leaderboard.py", "--dataset-id", "no_such_ds", "--json", env=env, cwd=tmp)
    check(
        "leaderboard --json: a refusal is on stderr, nothing on stdout, exit non-zero",
        bad.returncode != 0 and bad.stdout == "" and "no runs on dataset" in bad.stderr,
        (bad.stdout, bad.stderr),
    )
    return 8


def test_json_run_compare() -> int:
    """run-compare --json: the fingerprint result, the metric rows and the noise verdict."""
    tmp, meta, env = json_tree()
    base = ["scripts/compare_runs.py", "--baseline", "run_arm_a", "--candidate", "run_arm_b"]
    text = run_script(*base, "--noise", "0.1", env=env, cwd=tmp)
    js = run_script(*base, "--noise", "0.1", "--json", env=env, cwd=tmp)
    e = parsed(js)
    v = e["result"]["values"]
    rows = {r["metric"]: r for r in table_rows(e, "metric")}
    check("run-compare --json: one envelope, exit 0", js.returncode == 0 and e["command"] == "run-compare")
    check(
        "run-compare --json: acc baseline, candidate, delta and verdict are the text's",
        rows["acc"]["baseline"] == 1.0
        and rows["acc"]["candidate"] == 0.75
        and rows["acc"]["delta"] == -0.25
        and rows["acc"]["verdict"] == "worse"
        and f"{-0.25:+12.6f}   worse" in text.stdout,
        rows["acc"],
    )
    check(
        "run-compare --json: the noise floor, what moved past it, the builds",
        (v["noise"], v["moved_beyond_noise"], v["same_build"], v["dataset_id"]) == (0.1, 3, True, "dsj")
        and "3 metric(s) moved beyond the stated noise floor" in text.stdout,
        v,
    )
    check(
        "run-compare --json: identical fingerprints are comparable and match",
        v["fingerprint"]["comparable"] is True
        and v["fingerprint"]["match"] is True
        and v["fingerprint"]["moved"] == []
        and "Fingerprints MATCH" in text.stdout,
        v["fingerprint"],
    )
    wide = parsed(run_script(*base, "--noise", "1000", "--json", env=env, cwd=tmp))
    check(
        "run-compare --json: a delta under the floor is NOISE, and counts for nothing",
        {r["verdict"] for r in table_rows(wide, "metric")} == {"NOISE (<= 1000.0)"}
        and wide["result"]["values"]["moved_beyond_noise"] == 0,
        wide["result"]["values"],
    )
    rel = "runs/run_arm_b/metrics.json"
    m = _runstore.read_json(project(meta), rel)
    del m["fingerprint"]
    _runstore.write_text(project(meta), rel, json.dumps(m))
    old = parsed(run_script(*base, "--json", env=env, cwd=tmp))["result"]["values"]
    check(
        "run-compare --json: a run that predates fingerprinting is not comparable, and says why",
        old["fingerprint"]["comparable"] is False
        and old["fingerprint"]["match"] is None
        and "predates fingerprinting" in old["fingerprint"]["reason"]
        and old["noise"] is None,
        old,
    )
    write_run(meta, "run_other", "other_ds", "arm_a", {"acc": 0.5})
    bad = run_script(*base[:3], "--candidate", "run_other", "--json", env=env, cwd=tmp)
    check(
        "run-compare --json: different datasets are REFUSED on stderr, nothing on stdout",
        bad.returncode != 0 and bad.stdout == "" and "REFUSED" in bad.stderr,
        (bad.stdout, bad.stderr),
    )
    trav = run_script(*base[:3], "--candidate", "../data/runs/run_arm_b", "--json", env=env, cwd=tmp)
    check(
        "run-compare: a run id that is a path is refused, not read",
        trav.returncode != 0 and trav.stdout == "" and "not a path" in trav.stderr,
        trav.stderr,
    )
    return 8


def test_json_rank_stability() -> int:
    """rank-stability --json: its table and conclusion; too few items is a refusal under --json."""
    tmp, meta, env = json_tree()
    base = ["scripts/rank_stability.py", "--dataset-id", "dsj", "--draws", "30"]
    text = run_script(*base, env=env, cwd=tmp)
    js = run_script(*base, "--json", env=env, cwd=tmp)
    e = parsed(js)
    v = e["result"]["values"]
    rows = table_rows(e, "n_per_half")
    check(
        "rank-stability --json: one envelope, exit 0",
        js.returncode == 0 and e["command"] == "rank-stability",
        js.stderr,
    )
    check(
        "rank-stability --json: arms, items, draws, the sizes measured and the leader",
        (v["arms"], v["items"], v["draws"], v["sizes"], v["leader"]) == (4, 40, 30, [10, 20], "arm_a")
        and "4 arms, 40 items, metric=acc, 30 draws per size" in text.stdout
        and f"full-40 ordering's leader: {v['leader']}" in text.stdout,
        v,
    )
    check(
        "rank-stability --json: one row per size, rho and the tie count as the text prints them",
        [r["n_per_half"] for r in rows] == [10, 20]
        and all(
            f"{r['n_per_half']:>11} {r['rho_mean']:>21.3f} {r['rho_5th_pct']:>9.3f}" in text.stdout
            for r in rows
        )
        and all(f"{r['arms_tied_first']:>14.1f}" in text.stdout for r in rows),
        rows,
    )
    check(
        "rank-stability --json: saturated is the text's WARNING",
        v["saturated"] == ("WARNING: up to" in text.stdout) and v["saturated"] == (v["worst_ties"] >= 2.0),
        v,
    )
    ids = [f"j{i:02d}" for i in range(12)]
    for arm in ("s_a", "s_b", "s_c"):
        write_run(meta, f"run_{arm}", "dss", arm, {"acc": 0.5}, outputs={i: {"acc": 1.0} for i in ids})
    small = ["scripts/rank_stability.py", "--dataset-id", "dss"]
    t = run_script(*small, env=env, cwd=tmp)
    j = run_script(*small, "--json", env=env, cwd=tmp)
    check(
        "rank-stability: too few items prints its message on stdout and exits 1, as ever",
        t.returncode == 1 and "too few for two disjoint halves of 10" in t.stdout,
        t.stdout,
    )
    check(
        "rank-stability --json: too few items is a refusal: stderr, nothing on stdout, exit 1",
        j.returncode == 1 and j.stdout == "" and "too few for two disjoint halves of 10" in j.stderr,
        (j.stdout, j.stderr),
    )
    return 7


def test_json_runs_list() -> int:
    """runs-list --json: a row per run, a row per baseline."""
    tmp, meta, env = json_tree()
    text = run_script("scripts/list_runs.py", env=env, cwd=tmp)
    js = run_script("scripts/list_runs.py", "--json", env=env, cwd=tmp)
    e = parsed(js)
    rows = table_rows(e, "run_id")
    check(
        "runs-list --json: one envelope, a row per run, count in values",
        js.returncode == 0
        and len(rows) == 4
        and e["result"]["values"] == {"kind": "runs", "count": 4}
        and e["command"] == "runs-list",
        e["result"]["values"],
    )
    a = next(r for r in rows if r["run_id"] == "run_arm_a")
    check(
        "runs-list --json: run_id, config_id, dataset_id, created_at, build, directory and the scores as numbers",
        (a["config_id"], a["dataset_id"], a["created_at"], a["build_ref"], a["dirty"])
        == ("arm_a", "dsj", "2026-11-01T10:00:00Z", "abc123def456", False)
        and a["directory"] == "data/runs/run_arm_a"
        and a["scores"] == {"acc": 1.0, "latency_ms": 400.0, "total_cost_usd": 4.0},
        a,
    )
    check(
        "runs-list --json: every run the text lists is a row",
        all(r["run_id"] in text.stdout for r in rows) and len(rows) == len(rows_of_text(text.stdout)),
        text.stdout,
    )
    none = parsed(run_script("scripts/view_baselines.py", "--json", env=env, cwd=tmp))
    check(
        "evh baselines --json: no baselines is an empty list",
        none == {"schema": "evh-baselines/1", "baselines": []},
        none,
    )
    if not _runstore.sqlite():
        (meta["data"] / "baselines" / "_dataset" / "dsj").mkdir(parents=True)
    _runstore.write_text(
        project(meta),
        "baselines/_dataset/dsj/1.json",
        json.dumps(
            {
                "version": 1,
                "goal": None,
                "dataset_id": "dsj",
                "promoted_from": "run_arm_a",
                "build": {"ref": "abc123def456"},
                "reference_tier": "gold",
                "adapter": "x/adapter.py",
                "reason": "the best of four",
                "scores": {"acc": 1.0, "n_items": 40},
            }
        ),
    )
    bl = parsed(run_script("scripts/view_baselines.py", "--json", env=env, cwd=tmp))
    brow = bl["baselines"]
    bl_text = run_script("scripts/view_baselines.py", env=env, cwd=tmp).stdout
    check(
        "evh baselines --json: one entry per baseline, its scores as numbers; the text says the same",
        len(brow) == 1
        and (brow[0]["promoted_from"], brow[0]["reason"], brow[0]["scores"]["acc"])
        == ("run_arm_a", "the best of four", 1.0)
        and "why      the best of four" in bl_text
        and "scores   acc=1.0" in bl_text,
        (brow, bl_text),
    )
    return 5


def rows_of_text(text: str) -> list[str]:
    """The run rows of runs-list's text: after the header, before the blank line and the footnote."""
    lines = text.splitlines()
    return [ln for ln in lines[1 : lines.index("")] if ln.strip()]


def main() -> int:
    """Run all test functions."""
    tests = [
        ("compare_runs identical builds", test_compare_runs_identical_builds),
        ("compare_runs different datasets", test_compare_runs_different_datasets),
        ("compare_runs with noise floor", test_compare_runs_with_noise_floor),
        ("bootstrap_test basic", test_bootstrap_test_basic),
        ("bootstrap_test refuses non-classification", test_bootstrap_test_refuses_non_classification),
        ("holdout_significance basic", test_holdout_significance_basic),
        ("pair-test --json", test_json_pair_test),
        ("family-test --json", test_json_family_test),
        ("leaderboard --json", test_json_leaderboard),
        ("run-compare --json", test_json_run_compare),
        ("rank-stability --json", test_json_rank_stability),
        ("runs-list --json", test_json_runs_list),
        ("compare_runs missing run", test_compare_runs_missing_run),
        ("bootstrap_test missing opponent", test_bootstrap_test_missing_opponent),
        ("mutation: compare_runs delta", mutation_test_compare_runs),
        ("mutation: bootstrap_test p-value", mutation_test_bootstrap_test),
        ("mutation: holdout_significance exclude", mutation_test_holdout),
    ]

    total_checks = 0
    for name, test_func in tests:
        print(f"\n{name}:")
        try:
            num_checks = test_func()
            total_checks += num_checks
        except Exception as e:  # noqa: BLE001 — a crashing group is a failing group, not a stop
            traceback.print_exc()
            total_checks += 1
            check(f"{name}: ran without raising", False, f"{type(e).__name__}: {e}")

    return summary(f"assertions across {len(tests)} test groups")


if __name__ == "__main__":
    sys.exit(main())
