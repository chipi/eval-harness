"""The run reader (`_runs`), the adapter loader (`_adapter`) and the judge panel's use of both.

Each case is a defect the holistic review found: a direction remembered only by a flag, two
adapter registries that never saw each other, a panel that judged placeholder text.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import _adapter  # noqa: E402
from _check import check, summary  # noqa: E402
from _runs import direction, item_rows, matrix, per_item, runs_on  # noqa: E402


def _run(base: Path, name: str, metrics: dict, rows: list, outputs: dict | None = None) -> Path:
    d = base / name
    d.mkdir(parents=True)
    (d / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    (d / "predictions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    for item, text in (outputs or {}).items():
        (d / "outputs").mkdir(exist_ok=True)
        (d / "outputs" / f"{item}.txt").write_text(text, encoding="utf-8")
    return d


with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp) / "runs"
    m = {"dataset_id": "ds", "scores": {"f1": 0.5}, "primary_metric": "f1"}
    _run(base, "b_r2", {**m, "config_id": "b", "run_id": "b_r2"}, [{"item_id": "i1", "f1": 0.4}])
    _run(base, "b_r1", {**m, "config_id": "b", "run_id": "b_r1"}, [{"item_id": "i1", "f1": 0.2}])
    _run(
        base,
        "a",
        {**m, "config_id": "a", "run_id": "a"},
        [{"item_id": "i1", "f1": 0.9}, {"item_id": "i2", "f1": True}],
        outputs={"i1": "the first output"},
    )
    _run(base, "other", {**m, "dataset_id": "elsewhere", "config_id": "c", "run_id": "c"}, [])
    (base / "no_config").mkdir()
    (base / "no_config" / "metrics.json").write_text('{"dataset_id": "ds"}', encoding="utf-8")

    runs = runs_on("ds", runs_dir=base)
    check(
        "runs_on: sorted by directory, one dataset, a run needs a config_id",
        [d.name for d, _ in runs] == ["a", "b_r1", "b_r2"],
        [d.name for d, _ in runs],
    )
    check(
        "runs_on: match filters config_ids",
        [m["config_id"] for _, m in runs_on("ds", runs_dir=base, match="b")] == ["b", "b"],
    )
    check(
        "per_item: repeats are averaged",
        abs(per_item([r for r in runs if r[1]["config_id"] == "b"], "f1")["i1"] - 0.3) < 1e-12,
    )
    check(
        "per_item: a boolean is not a score",
        per_item(runs[:1], "f1") == {"i1": 0.9},
        per_item(runs[:1], "f1"),
    )
    check("matrix: config_id -> item -> mean", set(matrix(runs, "f1")) == {"a", "b"})

    (base / "a" / "predictions.jsonl").write_text(
        '{"item_id": "i1", "f1": 0.9}\nnot json\n', encoding="utf-8"
    )
    try:
        list(item_rows(base / "a"))
        raised = False
    except ValueError as exc:
        raised = "predictions.jsonl:2" in str(exc)
    check("item_rows: a malformed line names its file and line", raised)
    check(
        "item_rows: strict=False skips it (a page may, a test may not)",
        len(list(item_rows(base / "a", strict=False))) == 1,
    )

    check("direction: a cost metric is lower-is-better without a flag", direction(runs, "cost_usd"))
    check("direction: a quality metric is higher-is-better", not direction(runs, "f1"))
    asc_runs = [(d, {**mm, "primary_metric": "wer", "primary_metric_asc": True}) for d, mm in runs]
    check("direction: primary_metric_asc, which import-run records, is read", direction(asc_runs, "wer"))
    check("direction: --desc overrides what the runs declare", not direction(asc_runs, "wer", desc=True))
    check("direction: --asc overrides", direction(runs, "f1", asc=True))
    try:
        direction(runs, "f1", asc=True, desc=True)
        contradicted = False
    except SystemExit:
        contradicted = True
    check("direction: --asc with --desc is refused", contradicted)

    # Two adapters, both named adapter.py, declaring different kinds. One stem-keyed registry
    # returned the bundled adapter's kinds for either; each must answer for itself.
    adapters = []
    for name, kind in (("one", "descriptive"), ("two", "quality")):
        p = Path(tmp) / name / "adapter.py"
        p.parent.mkdir()
        p.write_text(
            f"METRIC_KINDS = {{'m': {kind!r}}}\nPRIMARY_METRIC = {name!r}\n"
            "def call_system(item, params):\n    return None\n"
            "def score(output, reference):\n    return {}\n",
            encoding="utf-8",
        )
        adapters.append(p)
    first = _adapter.load_adapter(str(adapters[0]))
    _adapter.load_adapter(str(adapters[1]))
    check(
        "adapter: two adapter.py files keep their own METRIC_KINDS",
        _adapter.metric_kinds(adapters[0])["m"] == "descriptive"
        and _adapter.metric_kinds(adapters[1])["m"] == "quality",
    )
    check(
        "adapter: and their own PRIMARY_METRIC",
        (_adapter.primary_metric(adapters[0]), _adapter.primary_metric(adapters[1])) == ("one", "two"),
    )
    check(
        "adapter: a recorded spec resolves to the module that ran",
        _adapter.adapter_module(str(adapters[0])) is _adapter.module_at(adapters[0])
        and first[3] == adapters[0],
    )
    import adapter as bundled

    check(
        "adapter: the bundled adapter is the `adapter` module itself",
        _adapter.module_at(_adapter.BUNDLED) is bundled,
    )
    check(
        "adapter: metric_kinds adds the core's `resumed`",
        _adapter.metric_kinds(adapters[1]).get("resumed") == "descriptive",
    )

    # The judge panel: real runs are judged on their own outputs, found where every command looks.
    (base / "a" / "predictions.jsonl").write_text('{"item_id": "i1", "f1": 0.9}\n', encoding="utf-8")
    import runner

    cands = runner._candidates_from({"runs_from": str(base), "dataset_id": "ds"})
    check(
        "panel: candidates come from the runs, ranked by their primary metric",
        sorted(c.run_id for c in cands) == ["a", "b_r1", "b_r2"] and all(c.run_dir for c in cands),
    )
    a = next(c for c in cands if c.run_id == "a")
    items = runner._items_of(a, n=20)
    check(
        "panel: a real run is judged on its stored output, not placeholder text",
        items == [{"item_id": "i1", "content": "the first output"}],
        items,
    )
    try:
        runner._candidates_from({"runs_from": str(base), "dataset_id": "ds", "primary_metric": "latency_ms"})
        refused = False
    except SystemExit as exc:
        refused = "lower-is-better" in str(exc)
    check("panel: promotion by a lower-is-better metric is refused, not ranked upside down", refused)

# The bundled adapter: an unknown provider fell back to echo, so a typo recorded the echoed
# input as the model's output; its cost now comes from the bill when there is one.
try:
    bundled.call_system("some text", {"provider": "anthropc"})
    typo_refused = False
except SystemExit as exc:
    typo_refused = "unknown provider 'anthropc'" in str(exc)
check("bundled adapter: an unknown provider is refused, not echoed", typo_refused)
check("bundled adapter: echo still runs", bundled.call_system("a b. c d.", {"provider": "echo"}).output != "")
from judging import billed, price  # noqa: E402

check("billed: the provider's usage.cost is the cost", billed({"cost": 0.0123}) == 0.0123)
check("billed: no cost reported is None, not 0", billed({"prompt_tokens": 5}) is None)
check("price: unpriced is None, never free", price({}, 10, 10) is None)
check("the adapter and the judges share one price rule", bundled.price is price and bundled.billed is billed)

# The instrument's code hash: the code that can move a number, nothing else. Editing a test or
# a report checker changed it, and run-compare then reported a confound that was not one.
import shutil  # noqa: E402

import _fingerprint  # noqa: E402

hashed = {p.name for p in _fingerprint.measuring_modules()}
check(
    "code hash: the run-writing commands and the adapter are in it",
    {"experiment_run.py", "rescore.py", "judge_score.py", "adapter.py", "_common.py"} <= hashed,
    sorted(hashed),
)
check(
    "code hash: no test, checker or read-only command is in it",
    not hashed & {"test_stats.py", "self_check.py", "leaderboard.py", "catalog_serve.py", "validate_tree.py"},
    sorted(hashed),
)
with tempfile.TemporaryDirectory() as tmp:
    code = Path(tmp) / "scripts"
    shutil.copytree(HERE, code, ignore=shutil.ignore_patterns("__pycache__"))
    before = {p.name for p in _fingerprint.measuring_modules(code)}
    (code / "_new_scorer.py").write_text("X = 1\n", encoding="utf-8")
    (code / "rescore.py").write_text(
        (code / "rescore.py").read_text(encoding="utf-8")
        + "\n\ndef _late():\n    import _new_scorer  # noqa\n",
        encoding="utf-8",
    )
    after = {p.name for p in _fingerprint.measuring_modules(code)}
    check(
        "code hash: a module a producer imports, even lazily, is covered the day it is",
        after - before == {"_new_scorer.py"},
    )
    (code / "test_unrelated.py").write_text("check = 1\n", encoding="utf-8")
    check(
        "code hash: a new test file is not",
        "test_unrelated.py" not in {p.name for p in _fingerprint.measuring_modules(code)},
    )

# EVAL_RUNS_DIR is relative to the project, as EVAL_DATA_DIR is. It resolved against the shell's
# directory, so with EVAL_HOME set a run was written in one place and read from another.
import subprocess  # noqa: E402

with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as elsewhere:
    r = subprocess.run(
        [sys.executable, "-c", "import _common; print(_common.RUNS.resolve())"],
        cwd=elsewhere,
        env={**os.environ, "PYTHONPATH": str(HERE), "EVAL_HOME": proj, "EVAL_RUNS_DIR": "data/runs-scratch"},
        capture_output=True,
        text=True,
    )
    check(
        "EVAL_RUNS_DIR: a relative path is the project's, not the shell's directory",
        r.stdout.strip() == str((Path(proj) / "data" / "runs-scratch").resolve()),
        (r.stdout + r.stderr).strip()[-200:],
    )

sys.exit(summary())
