"""The run reader (`_runs`), the adapter loader (`_adapter`) and the judge panel's use of both.

Each case is a defect the holistic review found: a direction remembered only by a flag, two
adapter registries that never saw each other, a panel that judged placeholder text.
"""

import contextlib
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

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _catalog_fixture as fx  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness._runs import direction, item_rows, matrix, per_item, runs_on  # noqa: E402


def _run(data: Path, name: str, metrics: dict, rows: list, outputs: dict | None = None) -> Path:
    """A run, its own score the plain label's (data/runs/<name>/scores/...); returns the score's directory."""
    return fx.put(
        data, name, metrics, "".join(json.dumps(r) + "\n" for r in rows), outputs=outputs, purpose="run"
    )


with tempfile.TemporaryDirectory() as tmp, _runstore._InProject(tmp) as data:
    m = {"dataset_id": "ds", "scores": {"f1": 0.5}, "primary_metric": "f1"}
    _run(data, "b_r2", {**m, "config_id": "b", "run_id": "b_r2"}, [{"item_id": "i1", "f1": 0.4}])
    _run(data, "b_r1", {**m, "config_id": "b", "run_id": "b_r1"}, [{"item_id": "i1", "f1": 0.2}])
    a_dir = _run(
        data,
        "a",
        {**m, "config_id": "a", "run_id": "a"},
        [{"item_id": "i1", "f1": 0.9}, {"item_id": "i2", "f1": True}],
        outputs={"i1": "the first output"},
    )
    _run(data, "other", {**m, "dataset_id": "elsewhere", "config_id": "c", "run_id": "c"}, [])
    _run(data, "no_config", {"dataset_id": "ds", "run_id": "no_config"}, [])
    base = data / "runs"

    runs = runs_on("ds")
    check(
        "runs_on: sorted by run id, one dataset, a run needs a config_id",
        [m["run_id"] for _, m in runs] == ["a", "b_r1", "b_r2"],
        [m["run_id"] for _, m in runs],
    )
    check(
        "runs_on: match filters config_ids",
        [m["config_id"] for _, m in runs_on("ds", match="b")] == ["b", "b"],
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

    _runstore.put_rows_text(a_dir, '{"item_id": "i1", "f1": 0.9}\nnot json\n')
    try:
        list(item_rows(a_dir))
        raised = False
    except ValueError as exc:
        raised = "predictions.jsonl:2" in str(exc)
    check("item_rows: a malformed line names its file and line", raised)
    check(
        "item_rows: strict=False skips it (a page may, a test may not)",
        len(list(item_rows(a_dir, strict=False))) == 1,
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
    moded = adapters[0].parent / "moded.py"
    moded.write_text(
        "PRIMARY_METRIC = 'tau'\n"
        "def primary_metric(params):\n    return {'pick': 'top1'}.get(params.get('mode'), PRIMARY_METRIC)\n"
        "def call_system(item, params):\n    return None\n"
        "def score(output, reference):\n    return {}\n",
        encoding="utf-8",
    )
    check(
        "adapter: primary_metric(params) names an arm's primary by its params, else PRIMARY_METRIC",
        _adapter.primary_metric(moded, {"mode": "pick"}) == "top1"
        and _adapter.primary_metric(moded, {}) == "tau"
        and _adapter.primary_metric(moded) == "tau",
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
    _runstore.put_rows_text(a_dir, '{"item_id": "i1", "f1": 0.9}\n')
    from evaluation_harness import judge_panel as runner

    cands = runner._candidates_from({"runs_from": "runs", "dataset_id": "ds"})
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
        runner._candidates_from({"runs_from": "runs", "dataset_id": "ds", "primary_metric": "latency_ms"})
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
from evaluation_harness import _providers  # noqa: E402
from evaluation_harness._providers import billed, price  # noqa: E402

check("billed: the provider's usage.cost is the cost", billed({"cost": 0.0123}) == 0.0123)
check("billed: no cost reported is None, not 0", billed({"prompt_tokens": 5}) is None)
check("price: unpriced is None, never free", price({}, 10, 10) is None)
check(
    "the bundled adapter's hosted providers are the ones the judges call (one provider layer)",
    set(bundled.PROVIDERS) == {"echo", *_providers.PROVIDERS},
    sorted(bundled.PROVIDERS),
)

# The instrument's code hash: the code that can move a number, nothing else. Editing a test or
# a report checker changed it, and run-compare then reported a confound that was not one.
import shutil  # noqa: E402

from evaluation_harness import _fingerprint  # noqa: E402

hashed = {p.name for p in _fingerprint.measuring_modules()}
check(
    "code hash: the run-writing commands and the adapter are in it",
    {"run.py", "rescore.py", "judge_score.py", "adapter.py", "_common.py"} <= hashed,
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

# The project's runs are <project>/data/runs, wherever the shell is: EVAL_HOME decides, not the working directory.

with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as elsewhere:
    r = subprocess.run(
        [sys.executable, "-c", "from evaluation_harness import _common; print(_common.RUNS.resolve())"],
        cwd=elsewhere,
        env={
            **{k: v for k, v in os.environ.items() if not k.startswith("EVAL_")},
            "PYTHONPATH": str(HERE.parent),
            "EVAL_HOME": proj,
        },
        capture_output=True,
        text=True,
    )
    check(
        "runs: <project>/data/runs, not relative to the shell's directory",
        r.stdout.strip() == str((Path(proj) / "data" / "runs").resolve()),
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


@contextlib.contextmanager
def aimed():
    """_runstore re-aims the paths at a test project but not the project root, which _common caches."""
    _common.project_root.cache_clear()
    try:
        yield
    finally:
        _common.project_root.cache_clear()


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
    for sub in ("goals", "datasets"):
        (data / sub).mkdir(parents=True)
    src = HERE.parent / "data" / "goals" / "entities_few_nerd.yaml"
    (data / "goals" / "g1.yaml").write_text(
        src.read_text(encoding="utf-8").replace("goal_id: entities_few_nerd", "goal_id: g1"), encoding="utf-8"
    )
    fx.put(
        data,
        "r1",
        {
            "run_id": "r1",
            "config_id": "c",
            "dataset_id": "few_nerd_280",
            "goal": "g1",
            "created_at": "2026-10-23",
            "build": {"ref": "t"},
            "scores": {"f1": 0.5},
            "metric_directions": {"f1": "lower"},
        },
    )
    _runstore.migrate_in(tmp)
    r = subprocess.run(
        [sys.executable, str(HERE / "validate_tree.py")],
        cwd=tmp,
        env={**os.environ, "EVAL_HOME": tmp, "EVAL_DATA_DIR": ""},
        capture_output=True,
        text=True,
    )
    check(
        "V14: a goal saying higher while its runs record lower fails",
        "FAIL V14" in r.stdout and "f1 is higher-is-better, its runs record lower-is-better" in r.stdout,
        r.stdout[-400:],
    )

# V1 holds systems, scorers, judging sets and verdicts to their schemas: a mistyped key in an
# arm was read by nothing and passed.
with tempfile.TemporaryDirectory() as tmp:
    data = Path(tmp) / "data"
    (data / "systems").mkdir(parents=True)
    (data / "systems" / "a.yaml").write_text("system_id: a\nparams: {}\nadaptor: mine.py\n", encoding="utf-8")
    verdict = data / "judge-verdicts" / "s" / "set" / "j" / "i.primary.b0.json"
    verdict.parent.mkdir(parents=True)
    verdict.write_text(json.dumps({"set_id": "set", "judge": "j", "pass": "first"}), encoding="utf-8")
    _runstore.migrate_in(tmp)
    r = subprocess.run(
        [sys.executable, str(HERE / "validate_tree.py")],
        cwd=tmp,
        env={**os.environ, "EVAL_HOME": tmp, "EVAL_DATA_DIR": ""},
        capture_output=True,
        text=True,
    )
    check(
        "V1: a system key nothing reads, and a malformed verdict, fail",
        "FAIL V1 schemas" in r.stdout
        and "data/systems/a.yaml" in r.stdout
        and "i.primary.b0.json" in r.stdout,
        r.stdout[-600:],
    )

# B1: a system that names no adapter uses the project's own <project>/adapter.py, recorded as
# `adapter.py`; without one, the bundled adapter.
with tempfile.TemporaryDirectory() as tmp:
    adapter_probe = Path(tmp) / "probe.py"
    adapter_probe.write_text(
        f"import sys\nsys.path.insert(0, {str(HERE)!r})\nimport _adapter\n"
        "print(_adapter.load_adapter(None)[2])\n",
        encoding="utf-8",
    )
    env = {**os.environ, "EVAL_HOME": tmp, "EVAL_DATA_DIR": ""}

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
    fx.put(
        Path(tmp) / "data",
        "r1",
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
        },
    )
    _runstore.migrate_in(tmp)
    env = {
        **os.environ,
        "EVAL_HOME": tmp,
        "EVAL_DATA_DIR": "",
        "EVH_ACTOR": "person:test",
    }
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
    bl_rel = "baselines/_dataset/d/1.json"
    with aimed():
        bl = _runstore.read_json(tmp, bl_rel) if _runstore.is_file(tmp, bl_rel) else {}
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
    with aimed():
        _runstore.write_text(tmp, bl_rel, json.dumps({**bl, "reference_tier": "silver"}))
    edited = _v6()
    check("V6: a baseline as promoted passes", as_promoted.startswith("  ok "), as_promoted)
    check("V6: a baseline whose tier no longer matches its run fails", edited.startswith("  FAIL "), edited)

# `rescore --out` is gone: a re-score is a score of the run it reads, never a copy somewhere else.
with tempfile.TemporaryDirectory() as tmp:
    fx.put(
        Path(tmp) / "data",
        "r1",
        {"run_id": "r1", "config_id": "c", "dataset_id": "d", "scores": {}},
        '{"item_id": "i1"}\n',
    )
    _runstore.migrate_in(tmp)
    r = subprocess.run(
        [
            sys.executable,
            str(HERE / "rescore.py"),
            "--dataset-id",
            "d",
            "--out",
            str(Path(tmp) / "elsewhere"),
        ],
        env={**os.environ, "EVAL_HOME": tmp, "EVAL_DATA_DIR": ""},
        capture_output=True,
        text=True,
    )
    check(
        "rescore: --out is not a flag any more",
        r.returncode != 0 and "unrecognized arguments: --out" in r.stderr and "Traceback" not in r.stderr,
        r.stderr[-300:],
    )

# A run record with a field no harness version writes now fails V1 (a 0.3.0 import's
# primary_metric_asc was read by nothing and passed); EVAL_GOALS_DIR puts the goals outside the
# data root, and V14 reads them there.
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


def _stats_project(tmp: str, rec: dict) -> None:
    """A project whose data root is data/eval/stats and whose goals sit beside it, with one run `rec`."""
    data = Path(tmp) / "data" / "eval" / "stats"
    goals = Path(tmp) / "data" / "eval" / "goals"
    for d in (data / "datasets", goals):
        d.mkdir(parents=True)
    src_goal = HERE.parent / "data" / "goals" / "entities_few_nerd.yaml"
    (goals / "g1.yaml").write_text(
        src_goal.read_text(encoding="utf-8").replace("goal_id: entities_few_nerd", "goal_id: g1"),
        encoding="utf-8",
    )
    fx.put(data, "r1", rec)
    if _runstore.sqlite():  # the data root is not data/, so _runstore.migrate_in does not apply
        env = {**os.environ, "EVAL_HOME": tmp, "EVAL_DATA_DIR": "data/eval/stats"}
        env.pop("EVAL_GOALS_DIR", None)
        moved = subprocess.run(
            [sys.executable, "-m", "evaluation_harness", "data-migrate", "--to", "sqlite"],
            env=env,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        if moved.returncode != 0:
            raise RuntimeError(f"data-migrate --to sqlite failed: {(moved.stdout + moved.stderr)[-500:]}")


def _validate(tmp: str, extra: dict) -> str:
    r = subprocess.run(
        [sys.executable, str(HERE / "validate_tree.py")],
        env={
            **os.environ,
            "EVAL_HOME": tmp,
            "EVAL_DATA_DIR": "data/eval/stats",
            **extra,
        },
        capture_output=True,
        text=True,
    )
    return r.stdout


with tempfile.TemporaryDirectory() as tmp:
    _stats_project(tmp, record)
    elsewhere = _validate(tmp, {"EVAL_GOALS_DIR": "data/eval/goals"})
    unset = _validate(tmp, {"EVAL_GOALS_DIR": ""})
    check(
        "EVAL_GOALS_DIR: V14 reads the goals there (and finds its contradiction)",
        "FAIL V14" in elsewhere and "f1 is higher-is-better" in elsewhere and "FAIL V14" not in unset,
        elsewhere[-400:],
    )
with tempfile.TemporaryDirectory() as tmp:
    _stats_project(tmp, {**record, "primary_metric_asc": True})
    old_field = _validate(tmp, {"EVAL_GOALS_DIR": ""})
    check(
        "V1: a run record with a field no harness writes fails",
        "FAIL V1 schemas" in old_field and "primary_metric_asc" in old_field,
        old_field[-400:],
    )

sys.exit(summary())
