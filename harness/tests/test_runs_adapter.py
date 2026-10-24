"""The run reader (`_runs`), the adapter loader (`_adapter`) and the judge panel's use of both.

Each case is a defect the holistic review found: a direction remembered only by a flag, two
adapter registries that never saw each other, a panel that judged placeholder text.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
sys.path.insert(0, str(HERE.parent))

from evaluation_harness import _adapter  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness._runs import direction, item_rows, matrix, per_item, runs_on  # noqa: E402


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
    asc_runs = [(d, {**mm, "metric_directions": {"wer": "lower"}}) for d, mm in runs]
    check(
        "direction: metric_directions, which an adapter or import-run --asc records, is read",
        direction(asc_runs, "wer"),
    )
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
    from evaluation_harness import adapter as bundled

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
    from evaluation_harness import judge_panel as runner

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
from evaluation_harness.judging import billed, price  # noqa: E402

check("billed: the provider's usage.cost is the cost", billed({"cost": 0.0123}) == 0.0123)
check("billed: no cost reported is None, not 0", billed({"prompt_tokens": 5}) is None)
check("price: unpriced is None, never free", price({}, 10, 10) is None)
check("the adapter and the judges share one price rule", bundled.price is price and bundled.billed is billed)

# The instrument's code hash: the code that can move a number, nothing else. Editing a test or
# a report checker changed it, and run-compare then reported a confound that was not one.
import shutil  # noqa: E402

from evaluation_harness import _fingerprint  # noqa: E402

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
        + "\n\ndef _late():\n    from evaluation_harness import _new_scorer  # noqa\n",
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

with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as elsewhere:
    r = subprocess.run(
        [sys.executable, "-c", "from evaluation_harness import _common; print(_common.RUNS.resolve())"],
        cwd=elsewhere,
        env={
            **os.environ,
            "PYTHONPATH": str(HERE.parent),
            "EVAL_HOME": proj,
            "EVAL_RUNS_DIR": "data/runs-scratch",
        },
        capture_output=True,
        text=True,
    )
    check(
        "EVAL_RUNS_DIR: a relative path is the project's, not the shell's directory",
        r.stdout.strip() == str((Path(proj) / "data" / "runs-scratch").resolve()),
        (r.stdout + r.stderr).strip()[-200:],
    )

# In a project (not this checkout) the project's parent is an arbitrary directory: a recorded
# adapter id must not be looked for there, and the bundled id is the package's own copy, not a
# stray `scripts/adapter.py` that happens to sit in the project.
with tempfile.TemporaryDirectory() as top:
    pinned = Path(top) / "pinned"
    (pinned / "scripts").mkdir(parents=True)
    (pinned / "scripts" / "adapter.py").write_text("STRAY = 1\n", encoding="utf-8")
    (Path(top) / "examples" / "x").mkdir(parents=True)
    (Path(top) / "examples" / "x" / "adapter.py").write_text("STRAY = 2\n", encoding="utf-8")
    probe = (
        "from evaluation_harness import _common as c\n"
        "print(c.in_checkout())\n"
        "print(c.resolve_adapter_path('scripts/adapter.py') == c.CODE / 'adapter.py')\n"
        "print(c.resolve_adapter_path('x/adapter.py'))\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=pinned,
        env={**os.environ, "PYTHONPATH": str(HERE.parent), "EVAL_HOME": str(pinned)},
        capture_output=True,
        text=True,
    )
    check(
        "pinned project: the bundled adapter id is the package's copy, and the parent is not searched",
        r.stdout.split() == ["False", "True", "None"],
        (r.stdout + r.stderr).strip()[-300:],
    )
from evaluation_harness import _common, self_check  # noqa: E402

check("checkout: in_checkout() is true here", _common.in_checkout())
check("checkout: `evh self-test` finds the full suite in tests/", self_check.in_checkout())

# ONE DIRECTION RULE: --asc/--desc, then the goal the runs name, then the adapter's declaration
# recorded on the run, then the name table. A goal page and the inspector disagreed before.
from evaluation_harness._runs import lower_is_better_on  # noqa: E402

wer_goal = {"g": {"success_criteria": {"primary": {"measure": "wer", "direction": "lower"}}}}
plain = [(Path("."), {"config_id": "a", "goal": "g"})]
check("direction: the goal the runs name decides (wer, lower)", lower_is_better_on(plain, "wer", wer_goal))
check(
    "direction: without a goal or a declaration, wer is not known to go down",
    not lower_is_better_on(plain, "wer", {}),
)
declared = [(Path("."), {"config_id": "a", "metric_directions": {"wer": "lower"}})]
check("direction: the adapter's declaration, recorded on the run", lower_is_better_on(declared, "wer", {}))
both = [(Path("."), {"config_id": "a", "goal": "g", "metric_directions": {"wer": "higher"}})]
check("direction: the goal outranks the recorded declaration", lower_is_better_on(both, "wer", wer_goal))
check("direction: a flag outranks the goal", not direction(both, "wer", desc=True))
with tempfile.TemporaryDirectory() as tmp:
    ad = Path(tmp) / "wer_adapter.py"
    ad.write_text(
        "METRIC_DIRECTIONS = {'wer': 'lower', 'bad': 'sideways'}\n"
        "def call_system(item, params):\n    return None\n"
        "def score(output, reference):\n    return {}\n",
        encoding="utf-8",
    )
    check(
        "adapter: METRIC_DIRECTIONS is read, and only lower/higher are kept",
        _adapter.metric_directions(ad) == {"wer": "lower"},
        _adapter.metric_directions(ad),
    )

# V14 fails a goal that contradicts what its runs record.
with tempfile.TemporaryDirectory() as tmp:
    data = Path(tmp) / "data"
    for sub in ("goals", "runs/r1", "datasets"):
        (data / sub).mkdir(parents=True)
    src = HERE.parent / "data" / "goals" / "entities_few_nerd.yaml"
    (data / "goals" / "g1.yaml").write_text(
        src.read_text(encoding="utf-8").replace("goal_id: entities_few_nerd", "goal_id: g1"), encoding="utf-8"
    )
    (data / "runs" / "r1" / "metrics.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "config_id": "c",
                "dataset_id": "few_nerd_280",
                "goal": "g1",
                "created_at": "2026-10-23",
                "build": {"ref": "t"},
                "scores": {"f1": 0.5},
                "metric_directions": {"f1": "lower"},
            }
        ),
        encoding="utf-8",
    )
    r = subprocess.run(
        [sys.executable, str(HERE / "validate_tree.py")],
        cwd=tmp,
        env={**os.environ, "EVAL_HOME": tmp, "EVAL_DATA_DIR": "", "EVAL_RUNS_DIR": ""},
        capture_output=True,
        text=True,
    )
    check(
        "V14: a goal saying higher while its runs record lower fails",
        "FAIL V14" in r.stdout and "f1 is higher-is-better, its runs record lower-is-better" in r.stdout,
        r.stdout[-400:],
    )

# V1 holds configs, scorers, judging sets and verdicts to their schemas: a mistyped key in an
# arm was read by nothing and passed.
with tempfile.TemporaryDirectory() as tmp:
    data = Path(tmp) / "data"
    (data / "configs").mkdir(parents=True)
    (data / "configs" / "a.yaml").write_text(
        "config_id: a\ndataset_id: d\nparams: {}\nadaptor: mine.py\n", encoding="utf-8"
    )
    verdict = data / "judge-verdicts" / "s" / "set" / "j" / "i.primary.b0.json"
    verdict.parent.mkdir(parents=True)
    verdict.write_text(json.dumps({"set_id": "set", "judge": "j", "pass": "first"}), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(HERE / "validate_tree.py")],
        cwd=tmp,
        env={**os.environ, "EVAL_HOME": tmp, "EVAL_DATA_DIR": "", "EVAL_RUNS_DIR": ""},
        capture_output=True,
        text=True,
    )
    check(
        "V1: a config key nothing reads, and a malformed verdict, fail",
        "FAIL V1 schemas" in r.stdout
        and "data/configs/a.yaml" in r.stdout
        and "i.primary.b0.json" in r.stdout,
        r.stdout[-600:],
    )

# B1: a config that names no adapter uses the project's own <project>/adapter.py, recorded as
# `adapter.py`; without one, the bundled adapter.
with tempfile.TemporaryDirectory() as tmp:
    adapter_probe = Path(tmp) / "probe.py"
    adapter_probe.write_text(
        f"import sys\nsys.path.insert(0, {str(HERE)!r})\nimport _adapter\n"
        "print(_adapter.load_adapter(None)[2])\n",
        encoding="utf-8",
    )
    env = {**os.environ, "EVAL_HOME": tmp, "EVAL_DATA_DIR": "", "EVAL_RUNS_DIR": ""}

    def _default_id() -> str:
        r = subprocess.run([sys.executable, str(adapter_probe)], env=env, capture_output=True, text=True)
        return r.stdout.strip() or r.stderr[-300:]

    bundled_id = _default_id()
    (Path(tmp) / "adapter.py").write_text(
        "def call_system(item, params):\n    return None\ndef score(output, reference):\n    return {}\n",
        encoding="utf-8",
    )
    own_id = _default_id()
    check(
        "adapter: no adapter named and none in the project -> the bundled one",
        bundled_id == "scripts/adapter.py",
        bundled_id,
    )
    check("adapter: no adapter named -> the project's adapter.py", own_id == "adapter.py", own_id)

# B11: a baseline carries what its number means (reference tier, adapter, fingerprint), and
# V6 fails a baseline that no longer says what its run records.
with tempfile.TemporaryDirectory() as tmp:
    run_dir = Path(tmp) / "data" / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "metrics.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "config_id": "c",
                "dataset_id": "d",
                "created_at": "2026-10-23",
                "build": {"ref": "abc", "dirty": False},
                "scores": {"f1": 0.5},
                "reference_tier": "gold",
                "adapter": "adapter.py",
                "fingerprint": {"hash": "0" * 64},
            }
        ),
        encoding="utf-8",
    )
    env = {**os.environ, "EVAL_HOME": tmp, "EVAL_DATA_DIR": "", "EVAL_RUNS_DIR": ""}
    subprocess.run(
        [
            sys.executable,
            str(HERE / "promote_baseline.py"),
            "--run",
            "r1",
            "--reason",
            "the test's own baseline",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    bl_path = Path(tmp) / "data" / "baselines" / "d_baseline.json"
    bl = json.loads(bl_path.read_text(encoding="utf-8")) if bl_path.is_file() else {}
    check(
        "promote: the baseline carries the run's tier, adapter and fingerprint hash",
        (bl.get("reference_tier"), bl.get("adapter"), bl.get("fingerprint_hash"))
        == ("gold", "adapter.py", "0" * 64),
        bl,
    )

    def _v6() -> str:
        r = subprocess.run(
            [sys.executable, str(HERE / "validate_tree.py")], env=env, capture_output=True, text=True
        )
        return next((ln for ln in r.stdout.splitlines() if " V6 " in ln), r.stdout[-300:])

    as_promoted = _v6()
    bl_path.write_text(json.dumps({**bl, "reference_tier": "silver"}), encoding="utf-8")
    edited = _v6()
    check("V6: a baseline as promoted passes", as_promoted.startswith("  ok "), as_promoted)
    check("V6: a baseline whose tier no longer matches its run fails", edited.startswith("  FAIL "), edited)

# rescore refuses to write over the directory it reads its runs from: it died with a
# SameFileError traceback after creating directories there.
with tempfile.TemporaryDirectory() as tmp:
    runs_dir = Path(tmp) / "data" / "runs"
    _run(
        runs_dir,
        "r1",
        {"run_id": "r1", "config_id": "c", "dataset_id": "d", "scores": {}},
        [{"item_id": "i1"}],
    )
    files_before = sorted(p_.relative_to(tmp) for p_ in Path(tmp).rglob("*"))
    r = subprocess.run(
        [sys.executable, str(HERE / "rescore.py"), "--dataset-id", "d", "--out", str(runs_dir)],
        env={**os.environ, "EVAL_HOME": tmp, "EVAL_DATA_DIR": "", "EVAL_RUNS_DIR": ""},
        capture_output=True,
        text=True,
    )
    files_after = sorted(p_.relative_to(tmp) for p_ in Path(tmp).rglob("*"))
    check(
        "rescore: --out the runs' own directory is refused, and nothing is written",
        r.returncode == 1
        and "is where the runs being rescored are read from" in r.stderr
        and "Traceback" not in r.stderr
        and files_before == files_after,
        r.stderr[-300:],
    )

# A run record with a field no harness version writes now fails V1 (a 0.3.0 import's
# primary_metric_asc was read by nothing and passed); EVAL_GOALS_DIR puts the goals outside the
# data root, and V14 reads them there.
with tempfile.TemporaryDirectory() as tmp:
    data = Path(tmp) / "data" / "eval" / "stats"
    goals = Path(tmp) / "data" / "eval" / "goals"
    for d in (data / "runs" / "r1", data / "datasets", goals):
        d.mkdir(parents=True)
    src_goal = HERE.parent / "data" / "goals" / "entities_few_nerd.yaml"
    (goals / "g1.yaml").write_text(
        src_goal.read_text(encoding="utf-8").replace("goal_id: entities_few_nerd", "goal_id: g1"),
        encoding="utf-8",
    )
    record = {
        "run_id": "r1",
        "config_id": "c",
        "dataset_id": "d",
        "goal": "g1",
        "created_at": "2026-10-23",
        "build": {"ref": "t"},
        "scores": {"f1": 0.5},
        "n_items": 1,
        "metric_directions": {"f1": "lower"},
    }
    (data / "runs" / "r1" / "metrics.json").write_text(json.dumps(record), encoding="utf-8")
    env = {**os.environ, "EVAL_HOME": tmp, "EVAL_DATA_DIR": "data/eval/stats", "EVAL_RUNS_DIR": ""}

    def _validate(extra: dict) -> str:
        r = subprocess.run(
            [sys.executable, str(HERE / "validate_tree.py")],
            env={**env, **extra},
            capture_output=True,
            text=True,
        )
        return r.stdout

    elsewhere = _validate({"EVAL_GOALS_DIR": "data/eval/goals"})
    unset = _validate({"EVAL_GOALS_DIR": ""})
    check(
        "EVAL_GOALS_DIR: V14 reads the goals there (and finds its contradiction)",
        "FAIL V14" in elsewhere and "f1 is higher-is-better" in elsewhere and "FAIL V14" not in unset,
        elsewhere[-400:],
    )
    (data / "runs" / "r1" / "metrics.json").write_text(
        json.dumps({**record, "primary_metric_asc": True}), encoding="utf-8"
    )
    old_field = _validate({"EVAL_GOALS_DIR": ""})
    check(
        "V1: a run record with a field no harness writes fails",
        "FAIL V1 schemas" in old_field and "primary_metric_asc" in old_field,
        old_field[-400:],
    )

sys.exit(summary())
