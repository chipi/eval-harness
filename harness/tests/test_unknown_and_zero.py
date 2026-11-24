#!/usr/bin/env python3
"""Unknown, none and zero are three answers, and a reader keeps them apart (RFC-041 F3).

    EVAL_STORE=files python tests/test_unknown_and_zero.py
    EVAL_STORE=sqlite python tests/test_unknown_and_zero.py

In a throwaway project ($0, offline: the tutorial's tickets, two echo arms):

- a run whose build git could not read records `dirty: null`, not `false` (clean); `run-promote` and `label-from-run`
  refuse it, `compare-runs` says it is unknown; a ref the owner declared (EVAL_BUILD_REF) is still the sanctioned way
  and is not refused;
- an arm whose recorded spend is $0 (a local model) shows `$0` on the catalog's systems table and in `evh models`'s
  sibling, the view of the same table, not `—`, which means "not recorded";
- a study's `stop: {usd: 0, wall_h: 2}` is a stop rule (`open_study` already honours `usd: 0`).
"""

import math
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KIT = HERE.parent / "tutorial"
from evaluation_harness import _common, _fingerprint, _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness.model import runs as _R  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-unknown-zero-"))
env = dict(os.environ, EVH_ACTOR="person:ana", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-unknown-zero")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_FOR"):
    env.pop(k, None)


def evh(*args):
    return _cli.run(proj, env, *args)


def out(r):
    return r.stdout + r.stderr


def run_of(cid):
    return next((n for n in sorted(_runstore.listdir(proj, "runs")) if n.startswith(cid + "_")), "")


def clone(run_id, name, build):
    """A copy of a run (its first score too) under a new id, with another build."""
    with _runstore._InProject(proj) as data:
        src, dst = data / "runs" / run_id, data / "runs" / name
        _runstore.copy_run(src, dst)
        first = _R.first_score(src)
        _runstore.copy_run(first, dst / "scores" / first.name)
        sd, meta = dst / "scores" / first.name, _R.meta(first)
        m = _R.record(sd)
        m["run_id"] = name
        m["build"] = build
        _R.write_run(name, {**(_R.run(dst) or {}), **_R.run_part(m)})
        _R.write_score(name, meta["scorer"], meta["reference"], m, label_as=meta["label"], first=True)
    return name


# ── F3a: what the build records when git cannot say ──────────────────────────────────────────────────────────────
real = _fingerprint.tree_dirt
saved_ref = os.environ.pop("EVAL_BUILD_REF", None)
try:
    _fingerprint.tree_dirt = lambda *a, **k: None  # git could not say (a timeout, a broken index)
    unknown = _common.build_info()
    _fingerprint.tree_dirt = lambda *a, **k: ["M x.py"]
    dirty = _common.build_info()
    _fingerprint.tree_dirt = lambda *a, **k: []
    clean = _common.build_info()
finally:
    _fingerprint.tree_dirt = real
    if saved_ref is not None:
        os.environ["EVAL_BUILD_REF"] = saved_ref
check(
    "build: git that cannot say records dirty null, a dirty tree true, a clean one false",
    (unknown["dirty"], dirty["dirty"], clean["dirty"]) == (None, True, False),
    (unknown, dirty, clean),
)

try:
    (proj / "data" / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    (proj / "data" / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tickets")
    goal = (KIT / "goals" / "tickets_summary.yaml").read_text(encoding="utf-8").replace("tickets_v1", "tk_v1")
    _runstore.write_text(proj, "goals/g_one.yaml", goal.replace("goal_id: tickets_summary", "goal_id: g_one"))
    r = evh("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tk_v1")
    r = (
        r
        if r.returncode
        else evh(
            "label-import", "--sheet", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "ana"
        )
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold",
            "--reason", "the kit's hand-written summaries", "--by", "ana",
        )
    )  # fmt: skip
    check("setup: a dataset with gold", r.returncode == 0, out(r)[-300:])
    for cid, n in (("one_v1", 1), ("two_v1", 2)):
        _runstore.write_text(
            proj, f"systems/{cid}.yaml", f"system_id: {cid}\nparams:\n  provider: echo\n  sentences: {n}\n"
        )
        r = evh("run", "--system", cid, "--dataset", "tk_v1", "--goal", "g_one")
        check(f"setup: {cid} runs", r.returncode == 0, out(r)[-300:])

    one, two = run_of("one_v1"), run_of("two_v1")
    git_null = {"ref": "abc123def456", "dirty": None, "source": "git"}
    a = clone(one, "one_v1_gitnull", git_null)
    b = clone(two, "two_v1_gitnull", git_null)

    r = evh("run-promote", "--run", a, "--reason", "git could not say whether it was clean")
    check(
        "run-promote refuses a run whose tree git could not read, saying so",
        r.returncode != 0 and "could not say" in out(r) and "--allow-dirty" in out(r),
        out(r)[-400:],
    )
    r = evh("run-promote", "--run", a, "--reason", "git could not say whether it was clean", "--allow-dirty")
    check("run-promote --allow-dirty overrides it", r.returncode == 0, out(r)[-300:])
    r = evh("run-promote", "--run", one, "--reason", "a build declared by its owner, as asked")
    check(
        "run-promote still takes a build the owner declared (dirty null by declaration)",
        r.returncode == 0,
        out(r)[-300:],
    )
    # import-run writes `dirty: null` with its own source, and so does a declared EVAL_BUILD_REF: that is "the owner's
    # word", not "git was asked and could not say", so each promotes (and labels) as before (RFC-041 F3).
    for name, build in (
        ("imported", {"ref": "abc123def456", "dirty": None, "source": "import-run --build-ref"}),
        ("declared", {"ref": "v1.2.3", "dirty": None, "source": "EVAL_BUILD_REF"}),
    ):
        run = clone(two, f"two_v1_{name}", build)
        r = evh("run-promote", "--run", run, "--reason", f"a {name} build, dirty unknown by its source")
        check(f"run-promote takes a {name} build whose dirty is null", r.returncode == 0, out(r)[-300:])
    # A record older than `source` with `dirty: null` is an unknown build (owner 2026-11-23): refused as git's null is,
    # and the same flag takes it.
    legacy = clone(two, "two_v1_legacy", {"ref": "abc123def456", "dirty": None})
    r = evh("run-promote", "--run", legacy, "--reason", "a legacy build, dirty unknown")
    check(
        "run-promote refuses a legacy build (dirty null, no source), saying git could not say",
        r.returncode != 0 and "could not say" in out(r) and "--allow-dirty" in out(r),
        out(r)[-400:],
    )
    r = evh("label-from-run", "--run", legacy, "--set", "s_legacy")
    check(
        "label-from-run refuses it too, and leaves no set",
        r.returncode != 0
        and "could not say" in out(r)
        and not _runstore.exists(proj, "labels/tk_v1/s_legacy"),
        out(r)[-400:],
    )
    r = evh("run-promote", "--run", legacy, "--reason", "a legacy build, dirty unknown", "--allow-dirty")
    check("run-promote --allow-dirty takes it", r.returncode == 0, out(r)[-300:])
    # A project outside git has no ref and no tree status: the unknown build is what is refused, and one flag allows it.
    nogit = clone(two, "two_v1_nogit", {"ref": "unknown", "dirty": None, "source": "git"})
    r = evh("run-promote", "--run", nogit, "--reason", "a project outside git, its build unknown")
    check(
        "run-promote: no git at all is refused as an unknown build",
        r.returncode != 0 and "does not identify its build" in out(r),
        out(r)[-300:],
    )
    r = evh(
        "run-promote",
        "--run",
        nogit,
        "--reason",
        "a project outside git, its build unknown",
        "--allow-unknown-build",
    )
    check(
        "... and --allow-unknown-build alone takes it, not also --allow-dirty",
        r.returncode == 0,
        out(r)[-300:],
    )
    r = evh("label-from-run", "--run", nogit, "--set", "s_nogit", "--allow-unknown-build")
    check("label-from-run: the same, one flag", r.returncode == 0, out(r)[-300:])
    r = evh("label-from-run", "--run", "two_v1_imported", "--set", "s_imported")
    check("label-from-run takes an imported build too", r.returncode == 0, out(r)[-300:])

    r = evh("label-from-run", "--run", a, "--set", "s_unknown")
    check(
        "label-from-run refuses it too, and leaves no set",
        r.returncode != 0
        and "could not say" in out(r)
        and not _runstore.exists(proj, "labels/tk_v1/s_unknown"),
        out(r)[-400:],
    )
    r = evh("run-compare", "--baseline", a, "--candidate", b)
    check(
        "run-compare says the build is unknown, not that it is clean",
        r.returncode == 0 and "could not say" in out(r),
        out(r)[-500:],
    )
    r = evh("run-compare", "--baseline", a, "--candidate", b, "--json")
    check(
        "run-compare --json: dirty_build is null (unknown), not false",
        r.returncode == 0 and '"dirty_build": null' in r.stdout.replace('":null', '": null'),
        out(r)[-400:],
    )
    r = evh("runs-list")
    rows = [ln for ln in r.stdout.splitlines() if "one_v1_gitnull" in ln]
    check("runs-list shows a ? for it", bool(rows) and "abc123def456?" in rows[0], rows)
    check(
        "build: the three are told apart by one function",
        [_common.tree_state(b) for b in (unknown, dirty, clean)] == [None, True, False]
        and _common.tree_state({"ref": "v1", "dirty": None, "source": "EVAL_BUILD_REF"}) is False
        and _common.tree_state({"ref": "v1", "dirty": None}) is None,
        None,
    )

    # ── F3b: $0 is recorded, not "not recorded" ──────────────────────────────────────────────────────────────────
    r = evh("catalog")
    page = proj / ".build" / "catalog"
    check("setup: the catalog builds", r.returncode == 0, out(r)[-300:])
    html = (page / "arms.html").read_text(encoding="utf-8")
    spend_cells = re.findall(r'<span data-v="0">([^<]*)</span>', html)
    check(
        "the arms page's systems table: an arm that recorded $0 shows $0, not the — of not recorded",
        len(spend_cells) == 2 and set(spend_cells) == {"$0"},
        spend_cells,
    )
    r = evh("arm-list", "--systems", "1")
    rows = [ln.split() for ln in r.stdout.splitlines() if ln.strip().startswith(("one_v1", "two_v1"))]
    check(
        "arm-list --systems prints it the same way",
        len(rows) == 2 and all(cols[5] == "$0" for cols in rows),
        r.stdout[-600:],
    )
    from evaluation_harness import catalog_build as cb

    check(
        "the one spend cell: nothing recorded is —, $0 is $0, an amount is its dollars",
        [cb.fmt_spend(v) for v in (None, 0, 0.0, 0.5)] == ["—", "$0", "$0", "$0.5000"],
        [cb.fmt_spend(v) for v in (None, 0, 0.0, 0.5)] if hasattr(cb, "fmt_spend") else "no fmt_spend",
    )

    # ── F3d: a stop of $0 is a stop rule ─────────────────────────────────────────────────────────────────────────
    from evaluation_harness import _looks, _study

    _common.load_goals = lambda *a, **k: {"g": {}}
    _looks.is_test_set = lambda ds: False  # type: ignore[assignment,misc]

    def stop_problems(stop):
        spec = {
            "dataset": "tk_v1",
            "baseline": {"system": "one_v1"},
            "measure": "overlap_f1",
            "sampler": "grid",
            "accept": "test",
            "space": {"groups": [{"name": "x"}]},
            "stop": stop,
        }
        return [p for p in _study.problems("g", "s1", spec) if p.startswith("stop")]

    check(
        "a study's stop needs one bound, not two (RUNBOOK 685, owner 2026-11-23): usd 0 is a bound (open_study caps the "
        "spend at 0), so is usd, wall_h or trials alone; none is not",
        stop_problems({"usd": 0, "wall_h": 2}) == []
        and stop_problems({"usd": 0}) == []
        and stop_problems({"usd": 1, "wall_h": 0}) == []
        and stop_problems({"usd": 1}) == []
        and stop_problems({"wall_h": 2}) == []
        and stop_problems({"trials": 5}) == []
        and stop_problems({"trials": 20, "usd": 5, "patience": 5}) == []
        and stop_problems({}) != []
        and stop_problems({"patience": 5}) != [],
        [stop_problems(s) for s in ({"usd": 0}, {"usd": 1}, {"wall_h": 2}, {}, {"patience": 5})],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

# A catalog build reads a million scores; an int one (an accuracy of 0 or 1) is answered before the general rule, as a
# finite float is: 0.8.1's arm-list ran ~10% over 0.8.0's for want of it (profile 2026-11-24).
from evaluation_harness import _number, _runs  # noqa: E402

slow: list[object] = []
_is_scored = _number.is_scored
_runs.is_scored = lambda v: slow.append(v) or _is_scored(v)
try:
    got = [_runs.score_of({"acc": v}, "acc") for v in (1, 0, 0.5, True, "x", None, float("nan"))]
finally:
    _runs.is_scored = _is_scored
check(
    "score_of: an int and a finite float skip the general rule; the rule still decides a bool, text, None and NaN",
    got == [1.0, 0.0, 0.5, None, None, 0.0, 0.0]
    and type(got[0]) is float
    and slow == [True, "x", None, slow[-1]],
    (got, slow),
)


class _Int(int):
    pass


class _Float(float):
    pass


def _rule(v: object) -> tuple[bool, bool, float]:
    num = not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)  # type: ignore[arg-type]
    scored = v is None or (not isinstance(v, (bool, str, list, dict)) and isinstance(v, (int, float)))
    return num, scored, (float(v) if num else 0.0)  # type: ignore[arg-type]


values = [
    1,
    0,
    -3,
    2**70,
    1.5,
    -0.0,
    float("nan"),
    float("inf"),
    -float("inf"),
    None,
    True,
    False,
    "x",
    [],
    {},
]
values += [_Int(4), _Float(2.5), _Float("nan")]
fast = [(_number.is_number(v), _number.is_scored(v), _number.counted(v)) for v in values]
check(
    "_number's fast paths answer as the general rule does, for every kind of value (bool, NaN, None, subclasses)",
    all(repr(f) == repr(_rule(v)) for f, v in zip(fast, values, strict=True)),
    [(v, f, _rule(v)) for f, v in zip(fast, values, strict=True) if repr(f) != repr(_rule(v))],
)

sys.exit(summary())
