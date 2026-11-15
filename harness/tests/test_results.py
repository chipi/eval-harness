#!/usr/bin/env python3
"""A run's per-item results as a model (RFC-033, format 7): the usage slim, the run settings, how rows are written.

    python tests/test_results.py

`model.results`: the usage slim (every shape: full, zero or one of the cache counts, no cost, `None`, not an object,
already slim, details that are not an object), twice the same; the settings a run's rows share (constant, differing,
one row, a row without one, no `_meta`, key order); stripping them from a row (equal goes, different stays, nothing
mutated); the check's reading of a stored row. Writes, in the store the suite runs in: `write_rows` slims usage and
strips a setting equal to the run's `call` and keeps one that differs, in a later score of the run as in the first;
`rows_as_written` is the text it writes (what rescore compares with); the crash checkpoint keeps the settings and
slims; a directory that is no score's is written as it comes. `evh run`: an adapter whose meta carries the settings
and a full billing object gives run.json a `call`, rows without them and slimmed usage, a first score with no
`unset: ["call"]`, a merged record that passes the schema (V1); an adapter whose `generation_config` varies keeps it in
its rows and out of `call`. `validate` V28: a clean project passes; a row holding its run's setting, a usage key outside
the kept set, each fails; a setting that differs from the run's is not a finding.
"""

import contextlib
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-results-"))
os.environ["EVAL_HOME"] = str(proj)
os.environ.setdefault("EVAL_STORE", "files")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR"):
    os.environ.pop(k, None)
import _runstore  # noqa: E402
import jsonschema  # noqa: E402
from evaluation_harness import _format, _outputs, _store  # noqa: E402
from evaluation_harness import validate_tree as vt  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import results as R  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402

env = dict(os.environ, EVAL_BUILD_REF="test-results", EVAL_MAX_RETRIES="0")

GC = {"max_tokens": 300, "temperature": 0}
GR = {"max_tokens": 300, "reasoning": {"effort": "none"}, "temperature": 0}
RICH = {
    "completion_tokens": 20,
    "completion_tokens_details": {"reasoning_tokens": 5},
    "cost": 0.0012,
    "cost_details": {"upstream_inference_cost": 0.001},
    "is_byok": False,
    "prompt_tokens": 100,
    "prompt_tokens_details": {"audio_tokens": 0, "cache_write_tokens": 10, "cached_tokens": 40},
    "total_tokens": 120,
}
SLIM_RICH = {
    "cached_tokens": 40,
    "cache_write_tokens": 10,
    "completion_tokens": 20,
    "cost": 0.0012,
    "prompt_tokens": 100,
}


def details(**kw):
    return {
        **RICH,
        "prompt_tokens_details": {"audio_tokens": 0, "cache_write_tokens": 0, "cached_tokens": 0, **kw},
    }


# ── the slim ────────────────────────────────────────────────────────────────────────────────────────────────────────
cases = {
    "full": (RICH, SLIM_RICH),
    "no cache counts (zero)": (details(), {"completion_tokens": 20, "cost": 0.0012, "prompt_tokens": 100}),
    "only cached_tokens": (
        details(cached_tokens=7),
        {"cached_tokens": 7, "completion_tokens": 20, "cost": 0.0012, "prompt_tokens": 100},
    ),
    "only cache_write_tokens": (
        details(cache_write_tokens=3),
        {"cache_write_tokens": 3, "completion_tokens": 20, "cost": 0.0012, "prompt_tokens": 100},
    ),
    "no cost: none is added": (
        {
            "completion_tokens": 0,
            "completion_tokens_details": None,
            "prompt_tokens": 0,
            "prompt_tokens_details": None,
            "total_tokens": 0,
        },
        {"completion_tokens": 0, "prompt_tokens": 0},
    ),
    "cost zero is kept": ({"cost": 0, "prompt_tokens": 1}, {"cost": 0, "prompt_tokens": 1}),
    "details is not an object": (
        {"cost": 1.0, "prompt_tokens": 1, "prompt_tokens_details": "x"},
        {"cost": 1.0, "prompt_tokens": 1},
    ),
    "already slim, cached at the top": (
        {"cached_tokens": 3, "completion_tokens": 2, "cost": 0.5, "prompt_tokens": 1},
        {"cached_tokens": 3, "completion_tokens": 2, "cost": 0.5, "prompt_tokens": 1},
    ),
    "empty object": ({}, {}),
    "only keys that are dropped": ({"total_tokens": 9, "is_byok": True}, {}),
    "None": (None, None),
    "a string": ("n/a", "n/a"),
    "a list": ([1, 2], [1, 2]),
    "a number": (7, 7),
}
for name, (given, want) in cases.items():
    before = copy.deepcopy(given)
    got = R.slim_usage(given)
    check(f"slim: {name}", got == want and given == before, (got, want))
    check(f"slim: {name}: slimming again gives the same", R.slim_usage(got) == got)
check(
    "slim: the kept keys are the five the RFC names",
    R.USAGE_KEPT == ("cost", "prompt_tokens", "completion_tokens", "cached_tokens", "cache_write_tokens"),
    R.USAGE_KEPT,
)
check(
    "model.results: the run settings are the three, and CALL_META holds them with the call's other facts",
    R.RUN_SETTINGS == ("generation_config", "generation_requested", "encoder_window")
    and set(R.RUN_SETTINGS) < set(R.CALL_META)
    and {"provider", "response_model", "usage", "finish_reason", "resumed_from_disk"} <= set(R.CALL_META),
    R.CALL_META,
)


def row(i, **meta):
    return {"item_id": i, "acc": 1.0, "_extra": {}, "_meta": {"provider": "p", **meta}}


ALL = {"generation_config": GC, "generation_requested": GR, "encoder_window": 512}

# ── the settings a run's rows share ─────────────────────────────────────────────────────────────────────────────────
check(
    "run_call: every row holds all three with one value: all three, in the settings' order",
    R.run_call([row("a", **ALL), row("b", **ALL), row("c", **ALL)]) == ALL
    and list(R.run_call([row("a", **ALL)])) == list(R.RUN_SETTINGS),
)
check(
    "run_call: a run of one row holds them",
    R.run_call([row("a", **ALL)]) == ALL,
)
check(
    "run_call: a setting with two values is not the run's; the others are",
    R.run_call([row("a", **ALL), row("b", **{**ALL, "generation_config": {**GC, "temperature": 1}})])
    == {"generation_requested": GR, "encoder_window": 512},
)
check(
    "run_call: a row without a setting leaves it in the rows",
    R.run_call([row("a", **ALL), row("b", generation_config=GC, generation_requested=GR)])
    == {"generation_config": GC, "generation_requested": GR},
)
check(
    "run_call: a row with no _meta, or a _meta that is not an object, leaves none",
    R.run_call([row("a", **ALL), {"item_id": "b"}]) == {}
    and R.run_call([row("a", **ALL), {"item_id": "b", "_meta": "x"}]) == {},
)
check("run_call: no rows, no settings", R.run_call([]) == {})
check(
    "run_call: the same object with its keys in another order is the same value",
    R.run_call([row("a", generation_config={"a": 1, "b": 2}), row("b", generation_config={"b": 2, "a": 1})])
    == {"generation_config": {"a": 1, "b": 2}},
)
check(
    "run_call: a null setting on every row is the run's (null)",
    R.run_call([row("a", encoder_window=None), row("b", encoder_window=None)]) == {"encoder_window": None},
)
check(
    "run_call: 1 and 1.0 are two values; so are false and 0",
    R.run_call([row("a", encoder_window=1), row("b", encoder_window=1.0)]) == {}
    and R.run_call([row("a", encoder_window=False), row("b", encoder_window=0)]) == {},
)

# ── stripping them ─────────────────────────────────────────────────────────────────────────────────────────────────
src = row("a", **ALL, usage=RICH)
frozen = copy.deepcopy(src)
got = R.strip_call(src, ALL)
check(
    "strip_call: the settings equal to the run's go, the rest of `_meta` stays, the row is not changed in place",
    got["_meta"] == {"provider": "p", "usage": RICH} and src == frozen,
    got,
)
got = R.strip_call(row("a", **{**ALL, "encoder_window": 1024}), ALL)
check(
    "strip_call: a setting that differs from the run's stays",
    got["_meta"] == {"provider": "p", "encoder_window": 1024},
    got,
)
check(
    "strip_call: a row whose `_meta` held only settings keeps `_meta: {}`",
    R.strip_call({"item_id": "a", "_meta": dict(ALL)}, ALL) == {"item_id": "a", "_meta": {}},
)
check(
    "strip_call: no call, an empty call, no `_meta`: the row itself",
    R.strip_call(src, None) is src
    and R.strip_call(src, {}) is src
    and R.strip_call({"item_id": "a"}, ALL) == {"item_id": "a"},
)
check(
    "prepare: the usage slimmed and the settings off, at once",
    R.prepare(src, ALL)["_meta"] == {"provider": "p", "usage": SLIM_RICH} and src == frozen,
    R.prepare(src, ALL),
)
check(
    "prepare: a row with nothing to do comes back as it is",
    R.prepare({"item_id": "a", "acc": 1.0}) == {"item_id": "a", "acc": 1.0},
)

# ── what the check reads ────────────────────────────────────────────────────────────────────────────────────────────
check(
    "problems: a setting equal to the run's, and a usage key outside the kept set, each named",
    R.problems(row("a", generation_config=GC, usage={"cost": 1, "total_tokens": 3}), ALL)
    == [
        "_meta.generation_config equals its run's call.generation_config",
        "_meta.usage.total_tokens is not kept",
    ],
    R.problems(row("a", generation_config=GC, usage={"cost": 1, "total_tokens": 3}), ALL),
)
check(
    "problems: a setting that differs from the run's, a run with no call, a slim usage, no `_meta`: none",
    R.problems(row("a", generation_config={"x": 1}), ALL) == []
    and R.problems(row("a", **ALL), None) == []
    and R.problems(row("a", usage=SLIM_RICH), ALL) == []
    and R.problems({"item_id": "a"}, ALL) == []
    and R.problems("not a row", ALL) == []
    and R.problems(row("a", usage="n/a"), ALL) == [],
)

try:
    data = proj / "data"
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    runs = data / "runs"

    def mk_run(run_id, call=None):
        rec = {"run_id": run_id, "dataset_id": "ds", "system_id": "s", **({"call": call} if call else {})}
        d = runs / run_id
        _store.mkdir(d, parents=True, exist_ok=True)
        _store.write_text(d / "run.json", json.dumps(rec, indent=2) + "\n")
        return d

    def score(d, key):
        sd = d / "scores" / key
        _store.mkdir(sd, parents=True, exist_ok=True)
        return sd

    def stored(sd):
        return _runstore.rows(sd)

    # ── writes ──────────────────────────────────────────────────────────────────────────────────────────────────────
    d = mk_run("plain_1")
    sd = score(d, "a@gold.ds")
    _outputs.write_rows(sd, [row("a", usage=RICH, **ALL), row("b", usage=None), row("c", usage="n/a")])
    got = stored(sd)
    check(
        "write_rows: usage slimmed on every row; None and a non-object pass through; a run with no `call` keeps the settings",
        got[0]["_meta"] == {"provider": "p", "usage": SLIM_RICH, **ALL}
        and got[1]["_meta"]["usage"] is None
        and got[2]["_meta"]["usage"] == "n/a",
        got,
    )

    d = mk_run("called_1", call={"generation_config": GC, "encoder_window": 512})
    first = score(d, "a@gold.ds")
    _outputs.write_rows(first, [row("a", usage=RICH, **ALL), row("b", usage=RICH, **ALL)])
    later = score(d, "b@gold.ds")
    _outputs.write_rows(
        later,
        [
            row("a", usage=RICH, **ALL),
            row("b", usage=RICH, **{**ALL, "generation_config": {**GC, "temperature": 1}}),
        ],
    )
    f, g = stored(first), stored(later)
    check(
        "write_rows: the first score of a run with a `call` loses the settings the call holds, and keeps the rest",
        all(r["_meta"] == {"provider": "p", "usage": SLIM_RICH, "generation_requested": GR} for r in f),
        f,
    )
    check(
        "write_rows: a later score of the run strips a setting equal to the call and keeps one that differs",
        g[0]["_meta"] == {"provider": "p", "usage": SLIM_RICH, "generation_requested": GR}
        and g[1]["_meta"]
        == {
            "provider": "p",
            "usage": SLIM_RICH,
            "generation_requested": GR,
            "generation_config": {**GC, "temperature": 1},
        },
        g,
    )
    rows_in = [row("a", usage=RICH, **ALL), row("b", usage=RICH, **ALL)]
    check(
        "rows_as_written: the text write_rows keeps, so a comparison with what is held (rescore, judge_score) holds",
        _outputs.rows_as_written(first, rows_in) == _outputs.rows_text(first),
    )
    check(
        "rows_as_written: a second write of the same rows leaves the text as it was",
        _outputs.rows_text(first) == _outputs.rows_as_written(first, rows_in),
    )

    loose = proj / "scratch_scores" / "x"
    _store.mkdir(loose, parents=True, exist_ok=True)
    _outputs.write_rows(loose, [row("a", usage=RICH, **ALL)])
    check(
        "write_rows: a directory that is no score's has no run to hold the settings: they stay, the usage is slimmed",
        stored(loose)[0]["_meta"] == {"provider": "p", "usage": SLIM_RICH, **ALL},
        stored(loose),
    )

    cp = mk_run("checkpoint_1", call={"generation_config": GC})
    _outputs.append_partial(cp, row("a", usage=RICH, **ALL))
    part = _runstore.rows(cp, partial=True)
    check(
        "append_partial: the checkpoint's row has its usage slimmed and its settings kept (the run's call is not known yet)",
        part == [{**row("a", usage=SLIM_RICH, **ALL)}],
        part,
    )

    # ── `call` and the schema ───────────────────────────────────────────────────────────────────────────────────────
    schema = json.loads((HARNESS / "schemas" / "metrics.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    check("model.runs: `call` is a run-only key", "call" in model_runs.RUN_ONLY, model_runs.RUN_ONLY)

    # ── `evh run` ───────────────────────────────────────────────────────────────────────────────────────────────────
    ADAPTER = """
import json
from types import SimpleNamespace

N = [0]
RICH = json.loads('@RICH@')

def call_system(text, params):
    N[0] += 1
    gc = {"max_tokens": 300, "temperature": 0}
    if params.get("vary") and N[0] % 2:
        gc = {"max_tokens": 300, "temperature": 0.5}
    meta = {"generation_config": gc, "generation_requested": {"max_tokens": 300}, "encoder_window": 512,
            "usage": RICH, "provider": "p", "finish_reason": "stop", "predicted": text[:5]}
    return SimpleNamespace(output=text[:40], tokens_in=10, tokens_out=5, cost_usd=0.0012, latency_ms=None,
                           extra={}, meta=meta)

def score(output, reference):
    return {"words": float(len(output.split()))}

PRIMARY_METRIC = "words"
""".replace("@RICH@", json.dumps(RICH))

    def evh(*args):
        return subprocess.run(
            [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=300,
        )  # fmt: skip

    def system(name, **params):
        body = "".join(f"  {k}: {json.dumps(v)}\n" for k, v in params.items())
        _runstore.write_text(
            proj, f"systems/{name}_v1.yaml", f"system_id: {name}_v1\nadapter: res_adapter.py\nparams:\n{body}"
        )
        return ["--system", f"{name}_v1", "--dataset", "tickets_v1"]

    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True, exist_ok=True)
    shutil.copytree(HARNESS / "tutorial" / "tickets", proj / "tutorial" / "tickets")
    (proj / "res_adapter.py").write_text(ADAPTER)
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset is frozen and materialized", r.returncode == 0, r.stderr[-300:])

    r = evh("run", *system("const", provider="echo"), "--run-id", "const_run", "--json")
    check(
        "evh run: an adapter that reports the settings and a full billing object runs",
        r.returncode == 0,
        r.stderr[-400:],
    )
    rd = runs / "const_run"
    with _runstore._InProject(proj):
        run_rec = model_runs.run(rd) or {}
        sd = model_runs.first_score(rd)
        assert sd is not None
        rows_ = _runstore.rows(sd)
        score_meta = model_runs.meta(sd)
        merged = model_runs.record(sd)
    want_call = {
        "generation_config": {"max_tokens": 300, "temperature": 0},
        "generation_requested": {"max_tokens": 300},
        "encoder_window": 512,
    }
    check(
        "evh run: run.json holds `call`, the settings every row held",
        run_rec.get("call") == want_call,
        run_rec.get("call"),
    )
    check(
        "evh run: the 6 rows hold neither setting, keep the call's other facts and the parser's, and slimmed usage",
        len(rows_) == 6
        and all(
            r["_meta"]
            == {
                "provider": "p",
                "finish_reason": "stop",
                "predicted": r["_meta"]["predicted"],
                "usage": SLIM_RICH,
            }
            for r in rows_
        ),
        rows_[:1],
    )
    check(
        "evh run: the first score does not unset `call`, and the merged record passes the schema (V1) with it",
        "call" not in (score_meta.get("unset") or [])
        and "call" in (merged or {})
        and not list(validator.iter_errors(merged)),
        (score_meta, [e.message for e in validator.iter_errors(merged)][:2]),
    )

    r = evh("run", *system("vary", provider="echo", vary=True), "--run-id", "vary_run", "--json")
    with _runstore._InProject(proj):
        vrun = model_runs.run(runs / "vary_run") or {}
        vsd = model_runs.first_score(runs / "vary_run")
        assert vsd is not None
        vrows = _runstore.rows(vsd)
    check(
        "evh run: a setting that takes two values over the rows stays in the rows and out of `call`; the others move",
        r.returncode == 0
        and vrun.get("call") == {k: v for k, v in want_call.items() if k != "generation_config"}
        and len(vrows) == 6
        and all("generation_config" in x["_meta"] and "encoder_window" not in x["_meta"] for x in vrows),
        (r.stderr[-300:], vrun.get("call"), vrows[:1]),
    )

    # ── validate V28 ────────────────────────────────────────────────────────────────────────────────────────────────
    def v28():
        vt.problems.clear()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            vt.v28_rows_in_format_7()
        return [p for p in vt.problems if "V28" in p], out.getvalue()

    bad, out = v28()
    check("V28: the project's runs, written by this release, pass", not bad and "ok   V28" in out, out)

    with _runstore._InProject(proj):
        sd = model_runs.first_score(runs / "const_run")
        assert sd is not None
        good = _outputs.rows_text(sd) or ""
        planted = {
            "a setting equal to its run's call": lambda r: r["_meta"].update(encoder_window=512),
            "a usage key outside the kept set": lambda r: r["_meta"]["usage"].update(total_tokens=9),
        }
        for what, plant in planted.items():
            lines = [json.loads(x) for x in good.splitlines()]
            plant(lines[2])
            _runstore.put_rows_text(sd, "".join(json.dumps(x, sort_keys=True) + "\n" for x in lines))
            bad, out = v28()
            check(
                f"V28: {what} fails, naming the score set and the line",
                bool(bad) and "line 3" in out and "const_run" in out,
                out,
            )
        lines = [json.loads(x) for x in good.splitlines()]
        lines[2]["_meta"]["encoder_window"] = 1024
        _runstore.put_rows_text(sd, "".join(json.dumps(x, sort_keys=True) + "\n" for x in lines))
        bad, out = v28()
        check("V28: a setting that differs from the run's is the row's own, not a finding", not bad, out)
        _runstore.put_rows_text(sd, good)
finally:
    _outputs.reset()
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
