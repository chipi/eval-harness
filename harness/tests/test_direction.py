#!/usr/bin/env python3
"""Which way is better for a measure, answered once (RFC-041 F1): `_runs.direction`.

  EVAL_STORE=files python tests/test_direction.py        (and EVAL_STORE=sqlite)

- the rule: a goal's declaration (its primary measure or an axis) first, the goal that lists the dataset before the
  goals the runs name before any goal; then what the runs record (the adapter's directions, their kinds); then the
  name table (cost, speed, tokens, error rates; the descriptive keys are neutral); a declared direction beats neutral;
- consistency: on one project the leaderboard, `run-compare`, `metric-list`, `metric-show`, a goal's page, a
  metric's page and the study all give a measure the same direction (the goal says `err` is lower on a dataset
  that no run names a goal for; `wer` and `cost_usd` go by the name table; `output_chars` is a count a goal says is
  lower);
- a source check: the name table's `lower_is_better` and `is_descriptive` are asked by `_runs.direction` only, and
  the adapter's `lower_is_better` / `is_neutral` only where a yes or no is all that is wanted;
- V14: two goals declaring opposite directions for one measure on one dataset fail; a `direction` that is neither
  lower nor higher, and a primary measure no run records, are notes.
"""

import io
import json
import os
import re
import shutil
import sys
import tempfile
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _common, _format, _runs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

D = Path(".")


def goal(primary: dict, datasets: list[str] | None = None, axes: dict | None = None) -> dict:
    g: dict = {"success_criteria": {"primary": primary}}
    if axes:
        g["success_criteria"]["axes"] = axes
    if datasets is not None:
        g["datasets"] = [{"dataset_id": d} for d in datasets]
    return g


def prim(measure: str, direction: str | None) -> dict:
    return {"measure": measure, **({"direction": direction} if direction else {})}


def run(**record) -> list:
    return [(D, {"system_id": "a", **record})]


# -- the rule -------------------------------------------------------------------------------------------------------
def rule() -> None:
    only = {"g": goal(prim("der", "lower"))}
    check(
        "rule: a goal the runs do not name still decides (der: lower)",
        _runs.direction("der", runs=run(), goals=only) == "lower"
        and _runs.direction("f1", runs=run(), goals={"g": goal(prim("f1", "lower"))}) == "lower",
        _runs.direction("der", runs=run(), goals=only),
    )
    check(
        "rule: with no goal, `der`, `wer` and `cer` are error rates: lower",
        all(_runs.direction(m, goals={}) == "lower" for m in ("der", "wer", "cer")),
    )
    check(
        "rule: cost, speed and tokens are lower; a quality measure is higher; a count is neutral",
        [
            _runs.direction(m, goals={})
            for m in ("cost_usd", "latency_ms", "total_tokens_in", "f1", "output_chars")
        ]
        == ["lower", "lower", "lower", "higher", "neutral"],
    )
    check(
        "rule: a goal that lists the dataset beats one that does not, and beats one the runs name",
        _runs.direction(
            "m",
            dataset="d2",
            runs=run(goal="named"),
            goals={
                "named": goal(prim("m", "lower")),
                "other_ds": goal(prim("m", "lower"), ["d1"]),
                "this_ds": goal(prim("m", "higher"), ["d2"]),
            },
        )
        == "higher"
        and _runs.direction(
            "m",
            dataset="d1",
            runs=run(goal="named"),
            goals={"named": goal(prim("m", "higher")), "other_ds": goal(prim("m", "lower"), ["d1"])},
        )
        == "lower",
    )
    check(
        "rule: among goals that do not list the dataset, the goal the runs name beats the rest",
        _runs.direction(
            "m",
            runs=run(goal="b"),
            goals={"a": goal(prim("m", "lower")), "b": goal(prim("m", "higher"))},
        )
        == "higher",
    )
    check(
        "rule: a goal weighing the measure as an axis declares it, a primary that says neither lower nor higher does not",
        _runs.direction(
            "size",
            goals={"g": goal(prim("q", "higher"), axes={"s": {"measure": "size", "direction": "lower"}})},
        )
        == "lower"
        and _runs.direction("q", goals={"g": goal(prim("q", "non_inferior"))}) == "higher"
        and _runs.direction("wer", goals={"g": goal(prim("wer", "non_inferior"))}) == "lower",
    )
    check(
        "rule: an axis with no direction of its own is no declaration (the runs' say stands)",
        _runs.direction(
            "m",
            runs=run(metric_directions={"m": "lower"}),
            goals={"g": goal(prim("q", "higher"), axes={"s": {"measure": "m"}})},
        )
        == "lower",
    )
    check(
        "rule: the adapter's recorded direction beats the name table (a cost it says is higher)",
        _runs.direction("cost_usd", runs=run(metric_directions={"cost_usd": "higher"}), goals={}) == "higher"
        and _runs.direction("m", runs=run(metric_directions={"m": "lower"}), goals={}) == "lower",
    )
    check(
        "rule: a goal beats the adapter's recorded direction",
        _runs.direction(
            "m", runs=run(metric_directions={"m": "higher"}), goals={"g": goal(prim("m", "lower"))}
        )
        == "lower",
    )
    check(
        "rule: a kind a run declares descriptive is neutral; one declared otherwise beats the name table's neutral",
        _runs.direction("m", runs=run(metric_kinds={"m": "descriptive"}), goals={}) == "neutral"
        and _runs.direction("output_chars", runs=run(metric_kinds={"output_chars": "quality"}), goals={})
        == "higher"
        and _runs.direction("m", kinds={"m": "descriptive"}, goals={}) == "neutral",
    )
    check(
        "rule: a declared direction beats neutral (goal, adapter), so a count a goal says is lower is lower",
        _runs.direction("output_chars", goals={"g": goal(prim("output_chars", "lower"))}) == "lower"
        and _runs.direction(
            "m", runs=run(metric_kinds={"m": "descriptive"}, metric_directions={"m": "higher"}), goals={}
        )
        == "higher",
    )
    other = {"a": goal(prim("m", "lower"), ["d1"])}
    check(
        "rule: a goal on another dataset does not decide a question about this one (the name table does); with no "
        "dataset in the question, any goal does",
        _runs.direction("m", dataset="d2", goals=other) == "higher"
        and _runs.direction("m", dataset="d2", runs=run(metric_directions={"m": "lower"}), goals={})
        == "lower"
        and _runs.direction("m", goals=other) == "lower"
        and _runs.direction("m", dataset="d2", runs=run(goal="a"), goals=other) == "lower",
    )
    check(
        "rule: direction_source says what decided",
        _runs.direction_source("m", dataset="d1", goals=other) == ("lower", "goal a")
        and _runs.direction_source("m", dataset="d2", goals=other) == ("higher", "the name table")
        and _runs.direction_source("m", runs=run(metric_directions={"m": "lower"}), goals={})
        == ("lower", "the runs' directions"),
    )
    check(
        "rule: the same measure on two datasets follows each dataset's own goal",
        [
            _runs.direction(
                "m",
                dataset=d,
                goals={"a": goal(prim("m", "lower"), ["d1"]), "b": goal(prim("m", "higher"), ["d2"])},
            )
            for d in ("d1", "d2")
        ]
        == ["lower", "higher"],
    )
    check(
        "better_word: the word every page prints for a direction",
        [_runs.better_word(d) for d in ("lower", "higher", "neutral")]
        == ["lower", "higher", "neutral: a description"],
    )
    mixed = {"asr_v1": "lower", "dev_v1": "higher"}
    check(
        "combine: datasets that agree give their answer, datasets that differ give mixed, worded per dataset",
        _runs.combine({"a": "lower", "b": "lower"}) == "lower"
        and _runs.combine(mixed) == "mixed"
        and _runs.better_word("mixed", mixed) == "lower on asr_v1; higher on dev_v1",
    )
    check(
        "lower_is_better_on and verdict_for are the rule's thin callers",
        _runs.lower_is_better_on(run(), "der", only)
        and not _runs.lower_is_better_on(run(), "output_chars", {"g": goal(prim("output_chars", "higher"))})
        and _common.verdict_for("der", 0.1, runs=run(), goals=only) == "worse"
        and _common.verdict_for(
            "output_chars", 5, runs=run(), goals={"g": goal(prim("output_chars", "lower"))}
        )
        == "worse"
        and _common.verdict_for("output_chars", 5, runs=run(), goals={}) == "changed",
    )


rule()


# -- one project, every reader --------------------------------------------------------------------------------------
proj = Path(tempfile.mkdtemp(prefix="evh-direction-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-direction", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

ADAPTER = """
from types import SimpleNamespace

def call_system(text, params):
    v = float(params["v"])
    return SimpleNamespace(output=f"{v}|" + "x" * int(params["pad"]), tokens_in=10, tokens_out=5,
                           cost_usd=v / 100, latency_ms=None, extra={}, meta={})

def score(output, reference):
    v = float(output.split("|")[0])
    return {"err": v, "wer": v, "my_rate": v, "output_chars": float(len(output))}

PRIMARY_METRIC = "err"
"""
#: What each reader must say, from where it comes: err the goal's primary on a dataset no run names a goal for, output_chars
#: the goal's axis (a count a goal says is lower), wer and cost_usd the name table.
EXPECTED = {"err": "lower", "output_chars": "lower", "wer": "lower", "cost_usd": "lower"}


def evh(*args):
    return _cli.run(proj, env, *args)


def result(r):
    return json.loads(r.stdout).get("result", {}) if r.returncode == 0 and r.stdout.strip() else {}


def write_goal(gid: str, primary: str, datasets: list[str], axes: str = "") -> None:
    ds = "".join(f"  - dataset_id: {d}\n" for d in datasets)
    _runstore.write_text(
        proj,
        f"goals/{gid}.yaml",
        f'goal_id: {gid}\nschema_version: "0.1"\ntitle: {gid}\nstatement: {gid}\ndecision: {gid}\nstatus: active\n'
        + (f"datasets:\n{ds}" if datasets else "datasets: []\n")
        + f"success_criteria:\n  primary: {primary}\n{axes}",
    )


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
        (proj / "data" / "models").mkdir()
    shutil.copytree(HARNESS / "tutorial" / "tickets", proj / "tutorial" / "tickets")
    (proj / "dir_adapter.py").write_text(ADAPTER)
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: a frozen dataset", r.returncode == 0, r.stderr[-300:])
    for name, v, pad in (("good", 0.1, 5), ("bad", 0.4, 20)):
        _runstore.write_text(
            proj,
            f"systems/{name}_v1.yaml",
            f"system_id: {name}_v1\nadapter: dir_adapter.py\nparams:\n  v: {v}\n  pad: {pad}\n",
        )
        r = evh("run", "--system", f"{name}_v1", "--dataset", "tickets_v1", "--run-id", name)
        check(f"setup: the run {name} (no goal named)", r.returncode == 0, r.stderr[-300:])
    write_goal(
        "g_err",
        "{measure: err, direction: lower}",
        ["tickets_v1"],
        "  axes:\n    size: {measure: output_chars, direction: lower}\n",
    )

    r = evh("run-compare", "--baseline", "good", "--candidate", "bad", "--json")
    rows = {
        x["metric"]: x["verdict"]
        for b in result(r).get("blocks", [])
        for x in b.get("rows", [])
        if "verdict" in x
    }
    check(
        "run-compare: the candidate is worse on every measure that rose, whoever says lower (goal, axis, name table)",
        all(rows.get(m) == "worse" for m in EXPECTED),
        {m: rows.get(m) for m in EXPECTED},
    )

    for sort in ("err", "wer", "cost_usd"):
        r = evh("leaderboard", "tickets_v1", "--sort", sort, "--json")
        res = result(r)
        group = (res.get("values", {}).get("groups") or [{}])[0]
        table: dict = next((b for b in res.get("blocks", []) if b.get("rows")), {})
        first = (table.get("rows") or [{}])[0].get("system_id")
        check(
            f"leaderboard --sort {sort}: lower is better, so the lower arm leads",
            group.get("direction") == "lower" and first == "good_v1",
            f"{group.get('direction')} {first} {r.stderr[-200:]}",
        )

    listed = {m["metric"]: m["better"] for m in result(evh("metric-list", "--json")).get("metrics", [])}
    check("metric-list: the same direction", all(listed.get(m) == EXPECTED[m] for m in EXPECTED), listed)
    shown = {m: str(result(evh("metric-show", m, "--json")).get("better", "")) for m in EXPECTED}
    check("metric-show: the same direction", all(v.startswith(EXPECTED[m]) for m, v in shown.items()), shown)

    out = proj / "catalog"
    r = evh("catalog", "--out", out)

    def page(rel: str) -> str:
        return (out / rel).read_text() if (out / rel).exists() else ""

    goal_page = page("g/g_err.html")
    check(
        "the goal's page: err is lower is better",
        r.returncode == 0 and "err, lower is better" in goal_page,
        r.stderr[-300:],
    )
    bad: list[tuple] = []
    for m, want in EXPECTED.items():
        own = page(f"m/{m}.html")
        at = own.find("<dt>better</dt>")
        cell = own[at : own.find("</dd>", at)] if at >= 0 else ""
        if want not in cell or "higher" in cell or "neutral" in cell:
            bad.append((m, cell[-80:]))
    metrics_page = page("metrics.html")
    for m, want in EXPECTED.items():
        row = metrics_page[metrics_page.find(f'id="m-{m}"') :]
        row = row[: row.find("</tr>")]
        if f">{want}<" not in row or ">higher<" in row:
            bad.append((m, "metrics.html", row[-120:]))
    check("the catalog's metric pages and metrics table: the same direction", not bad, bad)

    from evaluation_harness import _study

    real_goals = _common.load_goals
    _common.load_goals = lambda *a, **k: {
        "g_err": goal(
            prim("err", "lower"), ["tickets_v1"], {"size": {"measure": "output_chars", "direction": "lower"}}
        )
    }
    try:
        studied = {m: _study.lower_is_better("g_err", m) for m in EXPECTED}
    finally:
        _common.load_goals = real_goals
    check(
        "the study: lower is better on the same measures (a study on cost_usd keeps the cheaper trial)",
        all(studied.values()),
        studied,
    )

    # -- V14 --------------------------------------------------------------------------------------------------------
    def v14() -> tuple[int, str]:
        r = evh("validate")
        return r.returncode, r.stdout

    code, text = v14()
    line = next((ln for ln in text.splitlines() if "V14" in ln and ("ok" in ln or "FAIL" in ln)), "")
    check(
        "V14: the project's own goal passes, with no direction note",
        "ok" in line and "V14 goal g_err: primary" not in text,
        text[-600:],
    )

    write_goal("g_clash", "{measure: err, direction: higher}", ["tickets_v1"])
    code, text = v14()
    check(
        "V14: two goals saying opposite directions for err on one dataset fail",
        code != 0 and "FAIL V14" in text and "g_clash" in text and "g_err" in text and "err" in text,
        text[-800:],
    )
    write_goal("g_clash", "{measure: err, direction: higher}", ["other_v1"])
    code, text = v14()
    check(
        "V14: the same two on different datasets do not clash, but a goal's own dataset is not the other's: a note names both",
        "FAIL V14" not in text
        and "V14 goal g_clash: err is higher-is-better on other_v1, but on tickets_v1, which it does not list, "
        "it is read as lower (goal g_err)"
        in text,
        text[-800:],
    )
    write_goal("g_clash", "{measure: err, direction: higher}", [])
    code, text = v14()
    check(
        "V14: a goal that lists no dataset does not clash with one that lists tickets_v1 (that one is read first there)",
        "FAIL V14" not in text,
        text[-800:],
    )
    write_goal("g_clash", "{measure: zzz, direction: higher}", [])
    write_goal("g_clash2", "{measure: zzz, direction: lower}", [])
    code, text = v14()
    check(
        "V14: two goals that restrict to no dataset and say opposite directions fail (neither restricts)",
        code != 0 and "FAIL V14" in text and "g_clash" in text and "g_clash2" in text,
        text[-800:],
    )
    write_goal("g_clash", "{measure: err, direction: lower}", [])
    write_goal("g_clash2", "{measure: err, direction: lower}", ["tickets_v1"])
    write_goal("g_ni", "{measure: wer, direction: non_inferior}", ["tickets_v1"])
    write_goal("g_der", "{measure: DER, direction: lower}", ["tickets_v1"])
    code, text = v14()
    check("V14: the notes do not fail the check", code == 0 and "FAIL V14" not in text, text[-800:])
    check(
        "V14: a primary direction that is neither lower nor higher is a note naming the goal and what it is read as",
        "V14 goal g_ni: primary direction" in text and "non_inferior" in text and "read as higher" in text,
        text[-800:],
    )
    check(
        "V14: a primary measure no run on its datasets records is a note naming the measures they do record",
        "V14 goal g_der: primary measure" in text
        and "'DER'" in text
        and "err" in text
        and "output_chars" in text,
        text[-800:],
    )
    # -- a measure one goal declares on one dataset and nothing declares on another: mixed, each dataset by its own -----
    r = evh("dataset-create", "--dataset-id", "tickets_b_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_b_v1")
    for name in ("good", "bad"):
        r = (
            r
            if r.returncode
            else evh("run", "--system", f"{name}_v1", "--dataset", "tickets_b_v1", "--run-id", f"{name}_b")
        )
    check("setup: a second dataset with the same two systems", r.returncode == 0, r.stderr[-300:])
    write_goal("g_rate", "{measure: my_rate, direction: lower}", ["tickets_v1"])
    out2 = proj / "catalog2"
    listed = {m["metric"]: m for m in result(evh("metric-list", "--json")).get("metrics", [])}
    check(
        "metric-list: my_rate (declared lower on tickets_v1 only) is mixed, with each dataset's answer",
        listed.get("my_rate", {}).get("better") == "mixed"
        and listed["my_rate"].get("better_on") == {"tickets_b_v1": "higher", "tickets_v1": "lower"}
        and listed["wer"]["better"] == "lower",
        listed.get("my_rate"),
    )
    shown = result(evh("metric-show", "my_rate", "--json"))
    order = {
        d["dataset"]: [a["arm"].rpartition("/")[2] for a in d["arms"]] for d in shown.get("datasets", [])
    }
    check(
        "metric-show: the word names both, and each dataset's arms go by its own direction",
        "lower on tickets_v1" in shown.get("better", "")
        and "higher on tickets_b_v1" in shown.get("better", "")
        and order.get("tickets_v1") == ["good_v1", "bad_v1"]
        and order.get("tickets_b_v1") == ["bad_v1", "good_v1"],
        (shown.get("better"), order),
    )
    r = evh("catalog", "--out", out2)
    own = (out2 / "m" / "my_rate.html").read_text() if (out2 / "m" / "my_rate.html").exists() else ""
    at = own.find("<dt>better</dt>")
    cell = own[at : own.find("</dd>", at)] if at >= 0 else ""

    check(
        "the catalog's metric page agrees: both answers in the word",
        r.returncode == 0 and "lower on tickets_v1" in cell and "higher on tickets_b_v1" in cell,
        cell,
    )
    order_seen = re.findall(r"<tr[^>]*>(?:(?!</tr>).)*?(good|bad)_v1", own, re.S)
    check(
        "the catalog's metric page sorts each dataset's table by its own direction (tickets_b_v1 highest first, "
        "tickets_v1 lowest first)",
        order_seen == ["bad", "good", "good", "bad"],
        order_seen,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

# -- the source: nobody works the direction out itself ---------------------------------------------------------------
SCRIPTS = HARNESS / "scripts"
#: The name table's own questions (`_common`), asked by `_runs.direction` and nobody else.
TABLE = {"lower_is_better", "is_descriptive"}
#: The same words on an adapter or the study (`A.lower_is_better(`, `A.is_neutral(`): a yes or no, where the word is
#: not printed: a sort, a test's sidedness, a default yardstick. Each is a thin caller of the rule (`Adapter.direction`).
ASKS = {"lower_is_better", "is_neutral"}
ALLOWED_TABLE = {("_runs.py", "direction_source")}
#: The study's own `lower_is_better(goal, metric, dataset)`, called bare inside _study.py: not the name table's.
STUDY_OWN = {("_study.py", "trial"), ("_study.py", "weakest")}
ALLOWED_ASKS = {
    ("_study_cmd.py", "_confirm"),  # `_study.lower_is_better`: the study's own wrapper of the rule
    ("catalog_build.py", "_kind_of"),  # which kind a metric is, not which way it goes
    ("charts.py", "ms_lower"),  # `_study.lower_is_better`
    ("model/compare.py", "_other_reference"),  # a neutral count is not set against another reference
    ("model/compare.py", "_default_metric"),  # a neutral count is never the default yardstick
    (
        "model/goal_views.py",
        "by_dataset",
    ),  # the arm's lower flag, for the primary measure the goal decides on
    ("model/goal_views.py", "_group_decision"),  # axes.decide's direction_of
    ("catalog_adapter.py", "direction_on"),  # for an adapter with no `direction`
}


def calls(src: str) -> list[tuple[str, str, int, str]]:
    """(name, the def it is in, line, what it is called on) for each call of a name in TABLE or ASKS, from the tokens;
    called on "" when bare."""
    toks = [
        t
        for t in tokenize.generate_tokens(io.StringIO(src).readline)
        if t.type not in (tokenize.COMMENT, tokenize.NL)
    ]
    out: list[tuple[str, str, int, str]] = []
    defs: list[tuple[int, str]] = []
    fresh = True
    for i, t in enumerate(toks):
        if t.type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            fresh = fresh or t.type == tokenize.NEWLINE
            continue
        if fresh:  # the first token of a line leaves the defs it is no longer inside
            while defs and defs[-1][0] >= t.start[1]:
                defs.pop()
            fresh = False
        before = toks[i - 1].string if i else ""
        after = toks[i + 1].string if i + 1 < len(toks) else ""
        if before == "def" and t.type == tokenize.NAME:
            defs.append((toks[i - 1].start[1], t.string))
        elif t.type == tokenize.NAME and t.string in TABLE | ASKS and after == "(" and before != "def":
            owner = toks[i - 2].string if before == "." and i > 1 else ""
            out.append((t.string, defs[-1][1] if defs else "", t.start[0], owner))
    return out


found: list[str] = []
seen_table: set[tuple[str, str]] = set()
for f in sorted(SCRIPTS.rglob("*.py")):
    rel = f.relative_to(SCRIPTS).as_posix()
    for name, fn, lineno, owner in calls(f.read_text()):
        if (rel, fn) in STUDY_OWN and owner == "":
            continue
        if owner in ("", "_common") and name in TABLE:
            where = (rel, fn)
            seen_table.add(where)
            if where not in ALLOWED_TABLE:
                found.append(f"{rel}:{lineno} {name}( in {fn or 'module'}")
        elif owner not in ("", "_common") and name in ASKS and (rel, fn) not in ALLOWED_ASKS:
            found.append(f"{rel}:{lineno} {owner}.{name}( in {fn or 'module'}")
check(
    "source: the name table's lower_is_better / is_descriptive are asked by _runs.direction_source only; an adapter's "
    "lower_is_better / is_neutral only where listed",
    not found,
    found,
)
check(
    "source: the check finds the one call it allows (it reads the code it checks)",
    seen_table == ALLOWED_TABLE,
    sorted(seen_table),
)

sys.exit(summary())
