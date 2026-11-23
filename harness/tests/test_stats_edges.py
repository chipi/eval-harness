#!/usr/bin/env python3
"""The statistics on the shapes real data takes and the tutorial's does not (R7).

    python tests/test_stats_edges.py        # EVAL_STORE=files (default) or sqlite

A project of eleven datasets, each one a shape (an arm pair over it, a goal on it, the arms run by `evh run` with a
stand-in adapter whose score per item the shape sets): one item; every item failed for one arm; the arms identical;
every delta zero; the arms on disjoint items; every cluster of one item, and one cluster of every item; three items
(the smallest real dataset); half of 22 items missing for one arm; a NaN score; a None score. For each, through the
commands, as the code names it (stats.py `_set_verdict`, charts `_word`, the refusals of pair-test):

- `evh run` ends 0 or in a named refusal, with no traceback, and records no score as nan;
- pair-test gives a verdict word (or the named refusal `not-enough`), its p a probability, no nan; its --json is strict;
- leaderboard and goal-status: no traceback, strict JSON, no nan, the state named in words;
- the catalog's goal page is built, has no nan and no empty cell, and states the shape;
- `stats.compare` gives the verdict the data has, and the functions give probabilities and finite intervals on the
  lists the shapes make (none, one, all zero, three, a nan).

A score that is not a number (NaN, an infinity, None) makes its item a failed item (RFC-041 F7: a writer records a
number or refuses), so no new run holds one; the "old data" checks give the readers a run recorded before that, a NaN
in an item and in the run's mean. The checks that start "observation:" ask for more than the verdict word (why an arm
is out, that an arm failed everything, what the smallest p is). Shapes whose runs break the catalog build come last,
each with its own build, so one crash does not hide the pages before it. `EDGES_KEEP=1` leaves the project for a look.
"""

import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/
proj = Path(tempfile.mkdtemp(prefix="evh-edges-"))
env = dict(
    os.environ,
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-edges",
    EVH_ACTOR="person:tester",
    EVAL_MAX_RETRIES="0",
)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVH_PUBLIC"):
    env.pop(k, None)
env.setdefault("EVAL_STORE", "files")
os.environ.clear()
os.environ.update(env)
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import stats  # noqa: E402
from evaluation_harness._check import check, store_under_test, summary  # noqa: E402

ADAPTER = """
import json
import math
from types import SimpleNamespace

def call_system(text, params):
    item = text.split()[1]
    v = params.get("values", {}).get(item, params.get("default"))
    if v == "fail":
        raise RuntimeError("the system failed on " + item)
    return SimpleNamespace(output=json.dumps(v), tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=1.0,
                           extra={}, meta={})

def score(output, reference):
    if not output:  # a failed item is scored as an empty answer
        return {"q": 0.0}
    v = json.loads(output)
    return {"q": float("nan") if v == "nan" else None if v == "none" else v}

PRIMARY_METRIC = "q"
"""
FIELDSET = """fieldset_id: edge
description: test fields
fields:
  - {name: thread, type: text, label: Thread, description: a thread, public: true}
  - {name: batch, type: text, label: Batch, description: one batch, public: true}
"""


def evh(*args: str):
    return _cli.run(proj, env, *args, timeout=600)


def vals(n: int, f) -> dict:
    return {f"i{i:02d}": f(i) for i in range(1, n + 1)}


#: shape -> its items, each arm's score per item (a number, "nan", "none" or "fail"), the items an arm is run on, the
#: cluster field the test is given
SHAPES: dict[str, dict] = {
    "one_item": {"n": 1, "a": vals(1, lambda i: 0.9), "b": vals(1, lambda i: 0.4)},
    "all_failed_b": {"n": 5, "a": vals(5, lambda i: 0.5 + i / 20), "b": vals(5, lambda i: "fail")},
    "identical": {"n": 6, "a": vals(6, lambda i: i / 10), "b": vals(6, lambda i: i / 10)},
    "all_zero_deltas": {"n": 6, "a": vals(6, lambda i: 0.0), "b": vals(6, lambda i: 0.0)},
    "disjoint": {"n": 8, "a": vals(8, lambda i: i / 10), "b": vals(8, lambda i: i / 12), "on_a": range(1, 5), "on_b": range(5, 9)},
    "singleton_clusters": {"n": 8, "a": vals(8, lambda i: 0.2 + i / 20), "b": vals(8, lambda i: 0.1 + i / 30), "cluster": "thread"},
    "one_cluster": {"n": 8, "a": vals(8, lambda i: 0.2 + i / 20), "b": vals(8, lambda i: 0.1 + i / 30), "cluster": "batch"},
    "three_items": {"n": 3, "a": vals(3, lambda i: 0.3 + i / 10), "b": vals(3, lambda i: 0.2 + i / 20)},
    "half_missing_22": {"n": 22, "a": vals(22, lambda i: 0.3 + i / 40), "b": vals(22, lambda i: 0.2 + i / 50), "on_b": range(1, 12)},
    "nan_scores": {"n": 8, "a": vals(8, lambda i: "nan" if i == 2 else 0.5 + i / 20), "b": vals(8, lambda i: 0.4 + i / 30), "stage": 3},
    "none_scores": {"n": 8, "a": vals(8, lambda i: "none" if i == 5 else 0.5 + i / 20), "b": vals(8, lambda i: 0.4 + i / 30), "stage": 2},
}  # fmt: skip


def make(name: str) -> None:
    sp = SHAPES[name]
    src = proj / f"src_{name}"
    src.mkdir()
    for i in range(1, sp["n"] + 1):
        (src / f"i{i:02d}.txt").write_text(f"item i{i:02d} body\n", encoding="utf-8")
    (proj / f"{name}.csv").write_text(
        "item_id,thread,batch\n" + "".join(f"i{i:02d},t{i:02d},all\n" for i in range(1, sp["n"] + 1)),
        encoding="utf-8",
    )
    for step in (
        ("dataset-create", "--dataset-id", f"e_{name}", "--source-dir", f"src_{name}", "--fieldset", "edge",
         "--fields", f"{name}.csv"),
        ("dataset-materialize", "--dataset-id", f"e_{name}"),
    ):  # fmt: skip
        r = evh(*step)
        assert r.returncode == 0, f"{step}: {(r.stdout + r.stderr)[-400:]}"
    cluster = f", cluster: {sp['cluster']}" if sp.get("cluster") else ""
    _runstore.write_text(
        proj,
        f"goals/g_{name}.yaml",
        f"goal_id: g_{name}\nschema_version: '0.1'\ntitle: Edge {name}\nstatement: A shape.\nstatus: active\n"
        "decision: Which.\nsuccess_criteria:\n  primary: {measure: q, direction: higher}\n"
        f"datasets:\n  - {{dataset_id: e_{name}, role: validation{cluster}}}\n"
        "measures:\n  - {id: q, kind: metric, validity: unvalidated}\n",
    )
    sp["runs"] = {}
    for arm in "ab":
        table = dict(sp[arm])
        _runstore.write_text(
            proj,
            f"systems/e_{name}_{arm}.yaml",
            f"system_id: e_{name}_{arm}\nadapter: edge_adapter.py\nparams:\n  values: {json.dumps(table)}\n",
        )
        args = ["run", "--system", f"e_{name}_{arm}", "--dataset", f"e_{name}", "--goal", f"g_{name}"]
        if on := sp.get(f"on_{arm}"):
            (proj / f"{name}_{arm}.items").write_text("".join(f"i{i:02d}\n" for i in on), encoding="utf-8")
            args += ["--items", f"{name}_{arm}.items"]
        sp["runs"][arm] = evh(*args)


def cmd_json(*args: str) -> tuple[dict | None, str, subprocess.CompletedProcess]:
    """A command with --json: (its parsed answer or None, its text, the completed process). The answer is parsed
    strictly: a NaN or an Infinity in it is an error, as it is to any JSON reader but Python's."""
    r = evh(*args, "--json")

    def refuse(token: str) -> None:
        raise ValueError(f"{token} in the JSON")

    try:
        doc = json.loads(r.stdout, parse_constant=refuse)
        lines = [ln for b in doc["result"].get("blocks", []) for ln in b.get("lines", [])]
        text = "\n".join(lines)
    except (ValueError, KeyError, AttributeError) as exc:
        doc, text = None, f"{exc}; stdout: {r.stdout[:200]}"
    return doc, text + "\n" + r.stderr, r


def pair(name: str):
    sp = SHAPES[name]
    cluster = ["--cluster", sp["cluster"]] if sp.get("cluster") else []
    return cmd_json("pair-test", f"e_{name}", "--a", f"e_{name}_a", "--b", f"e_{name}_b", *cluster)


def page_of(out: Path, name: str) -> tuple[str, str]:
    """A goal page of the catalog: (its HTML, its text, a cell to a line)."""
    f = out / "g" / f"g_{name}.html"
    if not f.is_file():
        return "", ""
    raw = f.read_text(encoding="utf-8")
    raw_text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S)
    raw_text = re.sub(r"</(td|th|tr|p|div|li|h\d|table)>", "\n", raw_text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw_text))
    return raw, "\n".join(" ".join(ln.split()) for ln in text.splitlines() if ln.strip())


def has_nan(text: str) -> bool:
    return bool(re.search(r"(?<![A-Za-z_])-?(nan|inf)(?![A-Za-z_])", text, re.I))


def p_of(text: str) -> float | None:
    m = re.search(r"sign-flip p\s+([0-9.eE+-]+|nan)", text)
    return float(m.group(1)) if m else None


def scores_of(sp: dict, arm: str) -> dict:
    """What a run of the shape holds for the arm: a failed item scored as an empty answer (0)."""
    on = sp.get(f"on_{arm}") or range(1, sp["n"] + 1)
    out = {}
    for i in on:
        v = sp[arm][f"i{i:02d}"]
        if v != "none":
            out[f"i{i:02d}"] = 0.0 if v == "fail" else float("nan") if v == "nan" else v
    return out


#: Per shape, what the code says (stats.py `_set_verdict`, charts._word, axes' flags, the commands' refusals):
#: `pair` the pair-test's verdict word, or "refuse" for the named refusal (not-enough); `board` and `page` the words a
#: leaderboard and a goal page use for it; `stats` `compare`'s verdict.
EXPECT: dict[str, dict] = {
    "one_item": {"pair": "refuse", "board": r"Not enough paired data|is out", "page": r"too few items", "stats": "untestable"},
    "all_failed_b": {"pair": "NOT-SIGNIFICANT", "board": r"NO detectable arm effect", "page": r"not separated", "stats": "not significant"},
    "identical": {"pair": "NOT-SIGNIFICANT", "board": r"NO detectable arm effect", "page": r"identical", "stats": "identical"},
    "all_zero_deltas": {"pair": "NOT-SIGNIFICANT", "board": r"NO detectable arm effect", "page": r"identical", "stats": "identical"},
    "disjoint": {"pair": "refuse", "board": r"Not enough paired data", "page": r"shares fewer than 2 items", "stats": "untestable"},
    "singleton_clusters": {"pair": "SIGNIFICANT", "board": r"an arm effect exists", "page": r"better", "stats": "significant: better"},
    "one_cluster": {"pair": "refuse", "board": r"is out|Not enough paired data", "page": r"too few items", "stats": "untestable"},
    "three_items": {"pair": "NOT-SIGNIFICANT", "board": r"NO detectable arm effect", "page": r"not separated", "stats": "not significant"},
    "half_missing_22": {"pair": "SIGNIFICANT", "board": r"is out: n 11 of 22", "page": r"n 11 of 22 items", "stats": "significant: better"},
    # RFC-041 F7: the item whose score is not a number is a failed item, 0 as every failed item is: a wins 7 of 8 and
    # loses that one, sign-flip p 18/256 (owner 2026-11-23; before, the nan put the arm out)
    "nan_scores": {"pair": "any", "board": r"NO detectable arm effect", "page": r"too few items|not separated|shares fewer", "stats": None},
    "none_scores": {"pair": "any", "board": r"NO detectable arm effect", "page": None, "stats": None},
}  # fmt: skip


def check_shape(name: str, out: Path) -> None:
    sp, ex = SHAPES[name], EXPECT[name]
    w = lambda what: f"{name}: {what}"  # noqa: E731
    # the writers: `evh run` accepts what it can score, or refuses it by name
    for arm in "ab":
        r = sp["runs"][arm]
        said = r.stdout + r.stderr
        check(
            w(f"evh run, arm {arm}: no traceback; it ends 0, or in a named refusal"),
            "Traceback" not in said and (r.returncode == 0 or "ERROR (" in r.stderr),
            f"exit {r.returncode}: " + " | ".join(r.stderr.strip().splitlines()[-2:]),
        )
    check(
        w("evh run: no score is recorded as nan"),
        "q=nan" not in sp["runs"]["a"].stdout and "q=nan" not in sp["runs"]["b"].stdout,
        "the run line says q=nan",
    )
    if name in ("nan_scores", "none_scores"):
        # RFC-041 F7: a score that is not a number is a failed item of the run, named, and never in a mean
        said = sp["runs"]["a"].stdout + sp["runs"]["a"].stderr
        word = "nan" if name == "nan_scores" else "None"
        check(w("evh run: the item whose score is not a number is a failed item, with its reason"),
              "FAILED item i0" in said and f"score q is not a number: {word}" in said, said[-400:])  # fmt: skip
        rid = next(x for x in _runstore.listdir(proj, "runs") if x.startswith(f"e_{name}_a_"))
        rec = _runstore.record_of(proj, rid)
        check(w("evh run: the run record lists it in failed_items and its mean is over finite scores"),
              [f["error"] for f in rec.get("failed_items") or []] == [f"score q is not a number: {word}"]
              and math.isfinite(rec["scores"]["q"]), json.dumps(rec.get("failed_items"))[:200])  # fmt: skip
    # pair-test
    doc, text, r = pair(name)
    check(w("pair-test: no traceback; exit 0, or a named refusal"),
          "Traceback" not in text and (r.returncode == 0 or "ERROR (" in r.stderr), text[-300:])  # fmt: skip
    if (
        ex["pair"] == "any"
    ):  # no verdict is pinned (the shape has no right one in the docs): a refusal by name, or a sound one
        p = p_of(text)
        check(w("pair-test: a named refusal, or a verdict with a p that is a probability and no nan"),
              "ERROR (" in r.stderr or (p is not None and 0 <= p <= 1 and not has_nan(text)), text[-400:])  # fmt: skip
    elif ex["pair"] == "refuse":
        check(
            w("pair-test: refuses by name, ERROR (not-enough): too few to test"),
            "ERROR (not-enough)" in r.stderr,
            text[-300:],
        )
    else:
        check(
            w(f"pair-test: the verdict is {ex['pair']}"),
            doc is not None and f"verdict            {ex['pair']}" in text,
            text[-400:],
        )
        p = p_of(text)
        check(w("pair-test: its p is a probability"), p is not None and 0 <= p <= 1, f"sign-flip p {p}")
        check(w("pair-test: no nan or inf in what it says"), not has_nan(text), text[-400:])
    check(
        w("pair-test --json: strict JSON, no NaN or Infinity"),
        r.returncode != 0 or doc is not None,
        text[:300],
    )
    if doc and (v := doc["result"].get("values")):
        check(w("pair-test --json: p is null or a probability, delta is a number or null"),
              (v.get("p") is None or 0 <= v["p"] <= 1) and (v.get("delta") is None or v["delta"] == v["delta"]), json.dumps(v)[:300])  # fmt: skip
    # leaderboard
    doc, text, r = cmd_json("leaderboard", f"e_{name}")
    check(w("leaderboard: no traceback, exit 0"), "Traceback" not in text and r.returncode == 0, text[-300:])
    check(w("leaderboard --json: strict JSON"), doc is not None, text[:300])
    check(w(f"leaderboard: says it ({ex['board']})"), bool(re.search(ex["board"], text)), text[-500:])
    check(w("leaderboard: no nan or inf in a cell or a sentence"), not has_nan(text) and "NaN" not in r.stdout, [ln for ln in text.splitlines() if has_nan(ln)][:3])  # fmt: skip
    # the goal's own reads
    doc, text, r = cmd_json("goal-status", f"g_{name}")
    check(
        w("goal-status --json: no traceback, strict JSON"),
        "Traceback" not in text and doc is not None,
        text[:300],
    )
    # the goal page
    raw, page = page_of(out, name)
    check(w("goal page: the catalog built it"), bool(raw), f"no {out.name}/g/g_{name}.html")
    if raw:
        check(w("goal page: no nan or inf, no empty cell"), not has_nan(page) and not re.search(r"<td[^>]*>\s*</td>", raw),
              [ln for ln in page.splitlines() if has_nan(ln)][:3])  # fmt: skip
        if ex["page"]:
            check(
                w(f"goal page: states it ({ex['page']})"),
                bool(re.search(ex["page"], page)),
                page[page.find("scored against") :][:500],
            )
    # what a reader needs to be told beyond the verdict word (observations: the code names the state, but does it say why)
    if name == "all_failed_b":
        check(w("observation: the goal page says arm b failed on every item (it shows q 0.000 as a score)"),
              bool(re.search(r"\bfail", re.sub(r"all_\s*failed_\s*b", "", page))), "no mention of a failure on the page: " + " ".join(page[page.find("mean q") :].split())[:200])  # fmt: skip
    if name == "one_cluster":
        out_line = next((ln for ln in page.splitlines() if "is out" in ln), "")
        check(w("observation: the reason an arm is out names the clusters (8 items are shared, 1 cluster)"), "cluster" in out_line.split("is out:")[-1], out_line)  # fmt: skip
    if name == "three_items":
        _doc, said, _r = pair(name)
        check(w("observation: pair-test says no p can reach 0.05 on 3 items (the smallest is 0.25)"),
              bool(re.search(r"smallest|cannot|can't|never|attainable|too few", said)), said.strip().splitlines()[-3:])  # fmt: skip
    # the statistics, directly
    if ex["stats"]:
        arms = {a: scores_of(sp, a) for a in "ab"}
        cl = (
            {f"i{i:02d}": f"t{i:02d}" for i in range(1, sp["n"] + 1)}
            if name == "singleton_clusters"
            else None
        )
        cl = {f"i{i:02d}": "all" for i in range(1, sp["n"] + 1)} if name == "one_cluster" else cl
        row = stats.compare(arms, "b", clusters=cl)["rows"][0]
        check(
            w(f"stats.compare: the verdict is {ex['stats']}"),
            row["verdict"] == ex["stats"],
            {k: row[k] for k in ("n", "p", "min_p", "verdict")},
        )
    if name == "nan_scores":
        row = stats.compare({a: scores_of(sp, a) for a in "ab"}, "b")["rows"][0]
        check(
            w("stats.compare: a nan score gives a p that is a probability or None"),
            row["p"] is None or 0 <= row["p"] <= 1,
            row["p"],
        )
        try:
            json.dumps(row, allow_nan=False)
            clean = True
        except ValueError:
            clean = False
        check(
            w("stats.compare: a row with a nan score holds no NaN"),
            clean,
            {k: row[k] for k in ("n", "mean", "delta", "ci", "p")},
        )


try:
    r = evh("init", "--store", store_under_test(), "--tutorial")
    assert r.returncode == 0, r.stderr[-400:]
    _runstore.write_text(proj, "fields/edge.yaml", FIELDSET)
    (proj / "edge_adapter.py").write_text(ADAPTER, encoding="utf-8")
    first = [n for n, sp in SHAPES.items() if not sp.get("stage")]
    for name in first:
        make(name)
    r1 = evh("catalog", "--out", str(proj / ".build" / "edges-1"))
    check(
        "the catalog builds over the shapes that run clean",
        r1.returncode == 0,
        (r1.stdout + r1.stderr)[-300:],
    )
    for name in first:
        check_shape(name, proj / ".build" / "edges-1")
    # the shapes with a missing or a nan score come last, each with its own catalog: one that breaks the build would
    # hide every page built with it
    for stage in (2, 3):
        names = [n for n, sp in SHAPES.items() if sp.get("stage") == stage]
        for name in names:
            make(name)
        rs = evh("catalog", "--out", str(proj / ".build" / f"edges-{stage}"))
        check(
            f"the catalog builds with {' and '.join(names)} in the project",
            "Traceback" not in rs.stderr and rs.returncode == 0,
            " | ".join(rs.stderr.strip().splitlines()[-3:]),
        )
        for name in names:
            check_shape(name, proj / ".build" / f"edges-{stage}")

    # ── old data: a run recorded before RFC-041 F7 holds a NaN in an item and in its mean ──────────────────────────
    rid = next(x for x in _runstore.listdir(proj, "runs") if x.startswith("e_nan_scores_a_"))
    with _runstore._InProject(proj) as data:
        sd = _runstore.model_runs.first_score(data / "runs" / rid)
        assert sd is not None
        rows = _runstore.rows(sd)
        for row in rows:
            if row["item_id"] == "i02":
                row["q"] = float("nan")
        _runstore.put_rows(sd, rows)
        mj = json.loads(_runstore._store.read_text(sd / "metrics.json"))
        mj["scores"]["q"] = float("nan")
        _runstore._store.write_text(sd / "metrics.json", json.dumps(mj))
    old = "old data (a NaN already recorded)"
    doc, text, r = cmd_json("leaderboard", "e_nan_scores")
    check(f"{old}: leaderboard: no traceback, strict JSON, no nan or inf in a cell or a sentence",
          "Traceback" not in text and r.returncode == 0 and doc is not None and not has_nan(text) and "NaN" not in r.stdout,
          [ln for ln in text.splitlines() if has_nan(ln)][:3] or text[-300:])  # fmt: skip
    doc, text, r = pair("nan_scores")
    check(f"{old}: pair-test: a verdict with a p that is a probability, no nan",
          r.returncode == 0 and 0 <= (p_of(text) or -1) <= 1 and not has_nan(text), text[-400:])  # fmt: skip
    ro = evh("catalog", "--out", str(proj / ".build" / "edges-old"))
    check(f"{old}: the catalog builds", "Traceback" not in ro.stderr and ro.returncode == 0,
          " | ".join(ro.stderr.strip().splitlines()[-3:]))  # fmt: skip
    raw, page = page_of(proj / ".build" / "edges-old", "nan_scores")
    check(f"{old}: the goal page has no nan or inf", bool(raw) and not has_nan(page), [ln for ln in page.splitlines() if has_nan(ln)][:3])  # fmt: skip

    # ── the writer that takes numbers from outside refuses a nan by name ───────────────────────────────────────────
    (proj / "nan.jsonl").write_text(
        '{"item_id": "i01", "q": NaN}\n{"item_id": "i02", "q": 0.5}\n{"item_id": "i03", "q": 0.5}\n',
        encoding="utf-8",
    )
    r = evh("import-run", "--dataset-id", "e_three_items", "--system-id", "imp_nan", "--scores", "nan.jsonl",
            "--primary-metric", "q", "--build-ref", "abc123", "--source", "here", "--scorer-id", "imp")  # fmt: skip
    check(
        "import-run: a nan score is refused by name",
        r.returncode == 1 and "Traceback" not in r.stderr and "ERROR (" in r.stderr,
        (r.stdout + r.stderr)[-300:],
    )

    # ── the functions, on the lists the shapes give them ──────────────────────────────────────────────────────────
    nan = float("nan")
    for label, d in (("no items", []), ("one item", [0.5]), ("all zero", [0.0] * 6), ("three items", [0.1, 0.2, 0.3]),
                     ("a nan among six", [nan, 0.1, 0.2, 0.3, 0.4, 0.5])):  # fmt: skip
        w = f"stats on {label}"
        try:
            ps = [stats.exact_p(d), stats.sign_flip_p(d), stats.min_attainable_p(len(d))]
            ci = stats.exact_ci(d)
            ok = all(0 <= p <= 1 for p in ps) and (
                ci is None or (all(math.isfinite(x) for x in ci) and ci[0] <= ci[1])
            )
            said: object = {"p": ps, "ci": ci}
        except Exception as exc:  # noqa: BLE001 - a raise is a finding, not a crash of this test
            ok, said = False, f"{type(exc).__name__}: {exc}"
        check(
            f"{w}: exact_p, sign_flip_p, min_attainable_p are probabilities; exact_ci is None or a finite interval",
            ok,
            said,
        )
    units, sizes = stats.clustered({}, {})
    check(
        "stats on no clusters: clustered gives nothing, cluster_ci None",
        units == [] and stats.cluster_ci(units, sizes) is None,
    )
    check("stats on one cluster: cluster_ci None (nothing to test)", stats.cluster_ci([0.6], [8]) is None)
    check("stats on no p-values: holm is empty", stats.holm({}) == {})
finally:
    if os.environ.get("EDGES_KEEP"):
        print("PROJECT", proj)
    else:
        shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
