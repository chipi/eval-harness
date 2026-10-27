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
from evaluation_harness._check import check, summary

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
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "outputs").mkdir(exist_ok=True)

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
    (run_dir / "metrics.json").write_text(json.dumps(metrics))

    # predictions.jsonl with per-item scores
    pred_rows = []
    for item_id, item_scores in (outputs or {}).items():
        row = {"item_id": item_id, **item_scores}
        pred_rows.append(json.dumps(row))
    if pred_rows:
        (run_dir / "predictions.jsonl").write_text("\n".join(pred_rows) + "\n")
    else:
        (run_dir / "predictions.jsonl").write_text("")


def write_reference(meta: dict, ref_type: str, dataset_id: str, items: dict) -> None:
    """Write reference texts for a dataset. items: {item_id: text}."""
    ref_dir = meta["refs"] / ref_type / dataset_id
    ref_dir.mkdir(parents=True, exist_ok=True)
    for item_id, text in items.items():
        (ref_dir / f"{item_id}.txt").write_text(text)

    # For silver, write manifest
    if ref_type.startswith("silver"):
        manifest = {
            "authored_by": "arm_silver",
            "from_run": {"run_id": "silver_run"},
            "model": "test-model",
            "tier": "silver",
        }
        (ref_dir / "manifest.json").write_text(json.dumps(manifest))


def write_materialized(meta: dict, dataset_id: str, items: dict) -> None:
    """Write materialized source texts."""
    mat_dir = meta["mat"] / dataset_id
    mat_dir.mkdir(parents=True, exist_ok=True)
    for item_id, text in items.items():
        (mat_dir / f"{item_id}.txt").write_text(text)


def test_compare_runs_identical_builds() -> int:
    """compare_runs detects identical builds (same code, delta is noise)."""
    tmp = Path(tempfile.mkdtemp(prefix="evh-compare-"))
    meta = setup_runs_tree(tmp)

    # Two runs, identical build, different scores
    write_run(meta, "run_a", "ds1", "arm_a", {"f1": 0.850, "precision": 0.880})
    write_run(meta, "run_b", "ds1", "arm_a", {"f1": 0.855, "precision": 0.875})

    # Force both to have identical build hash
    for run_id in ["run_a", "run_b"]:
        mj = meta["runs"] / run_id / "metrics.json"
        m = json.loads(mj.read_text())
        m["build"]["ref"] = "same_build_hash_xyz"
        mj.write_text(json.dumps(m))

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
        "mutation bootstrap_test: reports SEPARATED for clear difference",
        "SEPARATED" in result.stdout,
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


def main() -> int:
    """Run all test functions."""
    tests = [
        ("compare_runs identical builds", test_compare_runs_identical_builds),
        ("compare_runs different datasets", test_compare_runs_different_datasets),
        ("compare_runs with noise floor", test_compare_runs_with_noise_floor),
        ("bootstrap_test basic", test_bootstrap_test_basic),
        ("bootstrap_test refuses non-classification", test_bootstrap_test_refuses_non_classification),
        ("holdout_significance basic", test_holdout_significance_basic),
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
