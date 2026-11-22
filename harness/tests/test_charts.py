#!/usr/bin/env python3
"""The evidence charts (RFC-034), every kind end to end: $0, offline, on the store EVAL_STORE names (files by default).

    python tests/test_charts.py

A project with 24 validation items, three echo arms, a round, a grid study, two categorical label sets, two baseline
versions and a judge pass on fake judges: each chart kind's numbers (`rows`), its drawing (well formed, no script) and
its refusals; the quadrant named only for a significant difference; a lower-is-better measure turned so right is
better; the API's answer the command line's; the drawing written to a file; the catalog's goal, study and dataset
pages carrying them.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-charts-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-charts")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)
os.environ.setdefault("EVAL_STORE", "files")
env["EVAL_STORE"] = os.environ["EVAL_STORE"]
WORDS = [
    "login",
    "invoice",
    "export",
    "api",
    "delete",
    "mobile",
    "refund",
    "billing",
    "search",
    "upload",
    "report",
    "password",
]
QUADRANTS = ("better and cheaper", "better, costs more", "worse and cheaper", "worse, costs more")
# what a significant point may be called: a quadrant, or, with no cost difference, the same cost (never cheaper)
NAMED = (*QUADRANTS, "better at the same cost", "worse at the same cost")


import _cli  # noqa: E402


def evh(*args: str) -> subprocess.CompletedProcess:
    return _cli.run(proj, env, *args, timeout=900)


def result(r: subprocess.CompletedProcess) -> dict:
    try:
        return json.loads(r.stdout.splitlines()[-1]).get("result") or {}
    except (IndexError, ValueError):
        return {}


def chart(*args: str) -> dict:
    r = evh("chart", *args, "--json")
    return result(r) or {"error": (r.stderr or r.stdout)[-300:], "rows": []}


def well_formed(svg: str) -> bool:
    """Every drawing parses as XML (inside one root), and carries no script or javascript: link."""
    try:
        ET.fromstring(f"<root>{svg}</root>")  # noqa: S314  # nosec B314 - the drawings this test made
    except ET.ParseError:
        return False
    return "<script" not in svg.lower() and "javascript:" not in svg.lower()


def run_of(system: str) -> str:
    rows = (
        result(evh("runs-list", "--json")).get("values", {}).get("runs")
        or result(evh("runs-list", "--json")).get("runs")
        or []
    )
    return next((r["run_id"] for r in rows if r.get("system_id") == system), "")


try:
    for side, rng in (("val", range(24)), ("test", range(24, 36))):
        src, gold = proj / f"src_{side}", proj / f"gold_{side}"
        src.mkdir(parents=True)
        gold.mkdir()
        for i in rng:
            s = [
                f"Ticket{i} " + " ".join(WORDS[(i + j * 3 + w) % len(WORDS)] for w in range(5)) + "."
                for j in range(4)
            ]
            (src / f"t{i:02d}.txt").write_text(" ".join(s) + "\n")
            (gold / f"t{i:02d}.txt").write_text(" ".join(s[:2]) + "\n")
    ids = [f"t{i:02d}" for i in range(24)]
    (proj / "cat_a.csv").write_text(
        "item_id,label\n" + "".join(f"{x},{'a' if k % 3 else 'b'}\n" for k, x in enumerate(ids))
    )
    (proj / "cat_b.csv").write_text(
        "item_id,label\n" + "".join(f"{x},{'a' if k % 4 else 'b'}\n" for k, x in enumerate(ids))
    )
    (proj / "data" / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    r: subprocess.CompletedProcess = subprocess.CompletedProcess([], 0)
    for ds, side in (("tk_val", "val"), ("tk_test", "test")):
        for argv in (
            ("dataset-create", "--dataset-id", ds, "--source-dir", f"src_{side}"),
            ("dataset-materialize", "--dataset-id", ds),
            ("label-import", "--sheet", f"gold_{side}", "--dataset-id", ds, "--set", "g", "--by", "t"),
            ("reference-promote", "--dataset-id", ds, "--labels", "g", "--tier", "gold", "--reason", "the first two sentences", "--by", "t"),
        ):  # fmt: skip
            r = r if r.returncode else evh(*argv)
    for name in ("cat_a", "cat_b"):
        r = (
            r
            if r.returncode
            else evh(
                "label-import", "--sheet", f"{name}.csv", "--dataset-id", "tk_val", "--set", name, "--by", "t"
            )
        )
    _runstore.write_text(
        proj, "goals/g.yaml",
        "goal_id: g\ntitle: t\nstatement: s\ndecision: d\n"
        "success_criteria: {primary: {measure: overlap_f1, direction: higher}}\n"
        "datasets:\n  - {dataset_id: tk_val, role: validation}\n  - {dataset_id: tk_test, role: test}\n",
    )  # fmt: skip
    _runstore.write_text(
        proj, "goals/short.yaml",
        "goal_id: short\ntitle: short\nstatement: s\ndecision: d\n"
        "success_criteria: {primary: {measure: output_words, direction: lower}}\n"
        "datasets:\n  - {dataset_id: tk_val, role: validation}\n",
    )  # fmt: skip
    # s1b_v1 writes what s1_v1 writes: in the round it is not separated from the baseline, so it must stay unnamed.
    for name, n in (("s1_v1", 1), ("s2_v1", 2), ("s3_v1", 3), ("s1b_v1", 1)):
        _runstore.write_text(
            proj, f"systems/{name}.yaml", f"system_id: {name}\nparams:\n  provider: echo\n  sentences: {n}\n"
        )
        r = r if r.returncode else evh("run", "--system", name, "--dataset", "tk_val", "--goal", "g")
    r = (
        r
        if r.returncode
        else evh(
            "run-promote",
            "--run",
            run_of("s1_v1"),
            "--goal",
            "g",
            "--reason",
            "the first arm, to start the line",
        )
    )
    r = (
        r
        if r.returncode
        else evh(
            "run-promote",
            "--run",
            run_of("s2_v1"),
            "--goal",
            "g",
            "--reason",
            "two sentences cover more of the gold",
        )
    )
    r = r if r.returncode else evh("round-open", "--goal", "g", "--dataset", "tk_val", "--keep", "s1_v1,s2_v1,s3_v1,s1b_v1",
                                   "--baseline", "s1_v1", "--hypothesis", "longer summaries cover more")  # fmt: skip
    spec = proj / "grid.yaml"
    spec.write_text("dataset: tk_val\nbaseline: {system: s1_v1}\nmeasure: overlap_f1\nsampler: grid\n"
                    "accept: {point: {min_gain: 0}}\nstop: {trials: 3}\n"
                    "space:\n  groups:\n    - {name: length, reason: how much to keep, params: {sentences: [2, 4]}}\n")  # fmt: skip
    st = r if r.returncode else evh("study-run", "--study", "g/s1", "--spec", str(spec))
    (proj / "tutorial").mkdir(exist_ok=True)
    shutil.copy2(KIT / "judge_prompt.txt", proj / "tutorial" / "judge_prompt.txt")
    sc = yaml.safe_load((KIT / "scorers" / "tickets-judge-v1.yaml").read_text()) | {"dataset_id": "tk_val"}
    _runstore.write_text(
        proj, "scorers/judge-v1.yaml", yaml.safe_dump(sc | {"scorer_id": "judge-v1"}, sort_keys=False)
    )
    jd = evh("judge-score", "--dataset-id", "tk_val", "--scorer", "judge-v1", "--unvalidated")
    check(
        "setup: 24 items, four arms, two baseline versions, a round, a grid study, two label sets, a judge pass",
        r.returncode == 0 and st.returncode == 0 and jd.returncode == 0,
        ((r.stdout + r.stderr)[-300:], (st.stdout + st.stderr)[-300:], (jd.stdout + jd.stderr)[-300:]),
    )

    # ── each kind ────────────────────────────────────────────────────────────
    got = {
        "intervals": chart("intervals", "--goal", "g", "--dataset", "tk_val"),
        "gain-cost round": chart("gain-cost", "--goal", "g", "--round", "r1"),
        "gain-cost study": chart("gain-cost", "--goal", "g", "--study", "s1"),
        "study-progress": chart("study-progress", "--goal", "g", "--study", "s1"),
        "rank-stability": chart("rank-stability", "--dataset", "tk_val"),
        "latency": chart("latency", "--goal", "g"),
        "agreement dataset": chart("agreement", "--dataset", "tk_val"),
        "agreement scorer": chart("agreement", "--scorer", "judge-v1"),
        "items": chart("items", "--goal", "g"),
        "trend": chart("trend", "--goal", "g"),
    }
    check(
        "every kind answers its rows, its columns, a title and a caption, and a drawing that is well formed",
        all(c.get("rows") and c.get("columns") and c.get("title") and c.get("caption") and well_formed(c.get("svg", "")) for c in got.values()),
        {k: c.get("error") or (len(c.get("rows") or []), well_formed(c.get("svg", ""))) for k, c in got.items()},
    )  # fmt: skip

    iv = got["intervals"]["rows"]
    lead = [x for x in iv if x["verdict"] == "the leader"]
    check(
        "intervals: the leader at 0, every other arm's difference inside its interval, the verdict in words",
        len(lead) == 1 and lead[0]["difference"] == 0
        and all(x["low"] <= x["difference"] <= x["high"] for x in iv if x["low"] is not None)
        and all(x["verdict"].split(",")[0] in ("better", "worse", "not separated", "identical", "the leader") for x in iv),
        iv,
    )  # fmt: skip
    short = chart("intervals", "--goal", "short")["rows"]
    check(
        "a lower-is-better measure is turned so right is better: the shortest arm leads, every other arm is to its left",
        any(x["verdict"] == "the leader" and x["arm"].startswith("s1_v1") for x in short)
        and all(x["difference"] <= 0 for x in short),
        short,
    )

    def claim_ok(x: dict) -> bool:
        significant = x["verdict"] in ("better", "worse")
        return (x["claim"] in NAMED) == significant and (
            significant or x["claim"] in ("not separated", "no gain shown, costs more")
        )

    gr = got["gain-cost round"] or {"rows": []}
    check(
        "gain-cost on a round: each arm against the run it started from, named by its quadrant only when significant",
        gr.get("baseline", "").startswith("s1_v1") and {x["arm"].split(" ")[0] for x in gr["rows"]} == {"s1b_v1", "s2_v1", "s3_v1"}
        and all(claim_ok(x) for x in gr["rows"])
        and any(x["claim"] == "not separated" for x in gr["rows"]) and any(x["claim"] in NAMED for x in gr["rows"]),
        gr["rows"],
    )  # fmt: skip
    shown = result(evh("study-show", "g", "s1", "--json"))
    outs = {f"t{t['k']}": t.get("outcome") for t in shown.get("trials", [])}
    gs, sp = got["gain-cost study"] or {"rows": []}, got["study-progress"] or {"rows": []}
    check(
        "gain-cost on a study: a point per trial with its change and outcome, named only when its own test was significant",
        {x["arm"]: x["outcome"] for x in gs["rows"]} == {k: v for k, v in outs.items() if v != "failed"}
        and all(claim_ok(x) for x in gs["rows"]),
        (gs["rows"], outs),
    )
    check(
        "study-progress: a row per trial, its outcome as the study recorded it",
        {f"t{x['trial']}": x["outcome"] for x in sp["rows"]} == outs
        and all(x["mean"] is not None for x in sp["rows"]),
        (sp["rows"], outs),
    )
    # A study is named as study-list prints it (<goal>/<id>) or by its id, wherever --goal is given; one that is not
    # there is a not-found refusal, never a traceback.
    both = {
        "study-progress goal/study": chart("study-progress", "--goal", "g", "--study", "g/s1"),
        "gain-cost goal/study": chart("gain-cost", "--goal", "g", "--study", "g/s1"),
    }
    sh = result(evh("study-show", "g", "g/s1", "--json"))
    check(
        "a study named <goal>/<id> with --goal gives what its bare id gives (study-progress, gain-cost, study-show)",
        both["study-progress goal/study"].get("rows") == sp["rows"]
        and both["gain-cost goal/study"].get("rows") == gs["rows"]
        and sh.get("trials") == shown.get("trials")
        and bool(sh),
        (both["study-progress goal/study"].get("error"), both["gain-cost goal/study"].get("error"), sh),
    )
    gone = {
        "chart study-progress missing": evh("chart", "study-progress", "--goal", "g", "--study", "nope"),
        "chart study-progress missing goal/study": evh(
            "chart", "study-progress", "--goal", "g", "--study", "g/nope"
        ),
        "chart gain-cost missing": evh("chart", "gain-cost", "--goal", "g", "--study", "nope"),
        "chart other goal's study": evh("chart", "study-progress", "--goal", "g", "--study", "h/s1"),
        "study-show missing": evh("study-show", "g", "nope"),
        "study-show missing goal/study": evh("study-show", "g", "g/nope"),
    }
    check(
        "a study that is not there is a not-found refusal (exit 1), never a traceback",
        all(
            r.returncode == 1 and "not-found" in r.stderr and "Traceback" not in r.stderr
            for r in gone.values()
        ),
        {k: (r.returncode, r.stderr[-200:]) for k, r in gone.items()},
    )
    rs = got["rank-stability"]["rows"]
    check(
        "rank-stability: 24 items allow halves of 5, 10 and 12, its agreement between -1 and 1",
        [x["n_per_half"] for x in rs] == [5, 10, 12] and all(-1 <= x["rho_mean"] <= 1 for x in rs),
        rs,
    )
    lt = got["latency"]["rows"]
    arms_n = len(got["items"]["columns"]) - 2  # the goal's arms: the three, and the study's trial systems
    check(
        "latency: an arm a row, its p50 at most its p95",
        len(lt) == arms_n >= 3 and all(x["p50_ms"] <= x["p95_ms"] for x in lt),
        lt,
    )
    ag = got["agreement dataset"]["rows"]
    check(
        "agreement on a dataset: the two categorical label sets compared, with their kappa",
        any({x["a"], x["b"]} == {"tk_val/cat_a", "tk_val/cat_b"} and x["kappa"] is not None for x in ag)
        and got["agreement dataset"]["svg"].count("<svg") == sum(1 for x in ag if x["kappa"] is not None),
        ag,
    )
    aj = got["agreement scorer"]["rows"]
    check(
        "agreement on a judge scorer: each judge's controls and the judges with each other",
        {x["judge"] for x in aj} >= {"judge_a", "judge_b", "judge_a~judge_b"},
        aj,
    )
    it = got["items"]
    check(
        "items: an item a row, the most disputed first, a column per arm",
        len(it["rows"]) == 24
        and it["rows"][0]["spread"] >= it["rows"][-1]["spread"]
        and {"s1_v1", "s2_v1", "s3_v1"} <= {c.split(" ")[0] for c in it["columns"][2:]},
        it["columns"],
    )
    tr = got["trend"]["rows"]
    check(
        "trend: the goal's baseline at each of its two versions, each as its record has it",
        [x["version"] for x in tr if x["line"] == "the baseline on tk_val"] == [1, 2]
        and all(x["read"] == "the version's record" for x in tr),
        tr,
    )
    # A closed round that promoted a run joins the same time line, its point named by the round, never by a version
    # (review, 2026-11-19: a round's point sat under "v1" and its title read "· v1").
    rc = evh(
        "round-close", "--goal", "g", "--round", "r1", "--conclusion", "Two sentences cover more of the gold than one.", "--promote",
        run_of("s2_v1"), "--by", "t",
    )  # fmt: skip
    t2 = chart("trend", "--goal", "g")
    rows2 = t2.get("rows") or []
    titles = re.findall(r"<title>([^<]+)</title>", t2.get("svg", ""))
    check(
        "trend: a closed round's promoted run is a point on the same time line, named by its round; the versions by theirs",
        rc.returncode == 0
        # the promotion made version 3 as the round closed: three versions and the round, in the order they happened
        and sorted(x["version"] for x in rows2 if x["line"] == "the baseline on tk_val") == [1, 2, 3]
        and [x["version"] for x in rows2 if x["line"] == "each closed round's promoted run"] == ["r1"]
        and [x["at"] for x in rows2] == sorted(x["at"] for x in rows2)
        and any("r1" in x and "round" in x for x in titles)
        and not any("round" in x and "v1" in x for x in titles)
        and any("baseline" in x and "v2" in x for x in titles),
        ((rc.stdout + rc.stderr)[-300:], rows2, titles),
    )
    from evaluation_harness import charts as _charts

    one = _charts.few_points_note(1, 1, 0, 4)
    check(
        "trend: one point says why (one baseline version, rounds that kept it add none); two or more say nothing",
        "Only 1 point" in one
        and "1 baseline version" in one
        and "0 of 4 closed rounds promoted a run" in one
        and _charts.few_points_note(2, 2, 0, 4) == ""
        and "Only" not in (t2.get("caption") or ""),
        one,
    )

    # ── refusals, words, the file, the API ─────────────────────────────────────
    refused = {
        "an unknown kind": evh("chart", "nope", "--goal", "g"),
        "gain-cost with neither a round nor a study": evh("chart", "gain-cost", "--goal", "g"),
        "rank-stability where fewer than 3 arms ran": evh("chart", "rank-stability", "--dataset", "tk_test"),
        "a goal that does not exist": evh("chart", "intervals", "--goal", "nope"),
    }
    check(
        "a chart with too little to draw, or asked wrongly, is refused in words, never drawn empty",
        all(x.returncode == 1 and "ERROR (" in x.stderr for x in refused.values()),
        {k: (x.returncode, x.stderr[-160:]) for k, x in refused.items()},
    )
    words = evh("chart", "intervals", "--goal", "g", "--svg", str(proj / "iv.svg"))
    drawn = (proj / "iv.svg").read_text() if (proj / "iv.svg").is_file() else ""
    check(
        "in words: the title, the table, the caption; --svg writes the drawing as a file an SVG reader opens",
        words.returncode == 0 and got["intervals"]["title"] in words.stdout and "95% interval" in words.stdout
        and well_formed(drawn) and 'xmlns="http://www.w3.org/2000/svg"' in drawn and "--ink:" in drawn,
        (words.stdout[-500:], drawn[:200]),
    )  # fmt: skip
    from evaluation_harness import charts as ch

    check(
        "the claim (RFC-034 §3): a quadrant only for a significant difference; otherwise not separated, or no gain shown at a cost",
        ch._claim(True, 0.1, -0.1) == QUADRANTS[0] and ch._claim(True, 0.1, 0.1) == QUADRANTS[1]
        and ch._claim(True, -0.1, -0.1) == QUADRANTS[2] and ch._claim(True, -0.1, 0.1) == QUADRANTS[3]
        and ch._claim(False, 0.1, -0.1) == "not separated" and ch._claim(False, 0.1, 0.1) == "no gain shown, costs more",
        "",
    )  # fmt: skip

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    evh("catalog")
    srv = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        for _ in range(300):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        time.sleep(0.5)
        token = (proj / ".build" / "api-token").read_text().strip()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/charts/intervals?goal=g&dataset=tk_val",
            headers={"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}", "X-EVH-Data": "1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - the test's own server  # nosec B310
                api = json.loads(resp.read()).get("result")
        except urllib.error.HTTPError as exc:
            api = {"status": exc.code}
        check(
            "the API's /charts/{kind} gives the command line's answer",
            api == got["intervals"],
            str(api)[:300],
        )
    finally:
        srv.terminate()
        srv.wait(timeout=20)

    goal_page = (
        (proj / ".build" / "catalog" / "g" / "g.html").read_text()
        if (proj / ".build" / "catalog" / "g" / "g.html").is_file()
        else ""
    )
    ds_pages = list((proj / ".build" / "catalog").rglob("*tk_val*.html"))
    ds_page = "".join(p.read_text() for p in ds_pages)
    check(
        "the catalog's goal page draws the goal over time, the evidence per dataset and the study's trials",
        goal_page.count('class="chart evidence"') >= 5 and "The evidence, drawn" in goal_page
        and "each arm against the leader" in goal_page and "trial (0: the baseline)" in goal_page,
        (goal_page.count('class="chart evidence"'), [p.name for p in (proj / ".build" / "catalog").rglob("*.html")][:20]),
    )  # fmt: skip
    check(
        "the catalog's dataset page draws each pair of label sets as a heat map",
        "tk_val/cat_a against tk_val/cat_b" in ds_page or "tk_val/cat_b against tk_val/cat_a" in ds_page,
        [p.name for p in ds_pages],
    )
    # Two arms whose names differ only at the end stay apart when a label is shortened to fit (the tail is kept), and no
    # label is longer than its room: text-anchor end would run it out of the drawing's left edge.
    from evaluation_harness import catalog_charts as cc

    names = ("briefs_mistral_small_v1 ×3", "briefs_mistral_small_v2 ×3")
    named_svgs = {
        "forest": cc.forest([{"name": n, "est": 0.1 * i, "lo": -0.1, "hi": 0.2, "word": ""} for i, n in enumerate(names)], "m", "x"),
        "strip": cc.strip({n: [(0.1 * i, "t")] for i, n in enumerate(names)}, "m", width=cc.NARROW),
        "heat": cc.heatmap(list(names), ["c1"], {(n, "c1"): {"value": 0.5} for n in names}, "m", 0, 1),
    }  # fmt: skip
    texts = {
        k: [t for t in re.findall(r'class="tick"[^>]*>(?:<title>[^<]*</title>)?([^<]*)<', v) if "×" in t]
        for k, v in named_svgs.items()
    }
    # A forest, a strip and a heat map make room for a row's name and wrap it at a separator: never cut (scenario 080d).
    whole = {
        k: ["".join(re.findall(r"<tspan[^>]*>([^<]*)</tspan>", chunk)).replace(" ", "") for chunk in re.findall(r"<text[^>]*>(?:<title>[^<]*</title>)?((?:<tspan[^>]*>[^<]*</tspan>)+)</text>", named_svgs[k])]
        for k in ("forest", "strip", "heat")
    }  # fmt: skip
    check(
        "a long arm name in a forest, a strip or a heat map is whole (wrapped at a separator), v1 and v2 apart",
        all(set(v) >= {n.replace(" ", "") for n in names} and "…" not in "".join(v) for v in whole.values()),
        whole,
    )
    # Two marks of one row closer than a label is wide (a p50 and a p95 a few ms apart) lean apart, so the labels read.
    lat = cc.strip(
        {"near": [(1.0, "a"), (100.0, "b")], "far": [(1.0, "a"), (100.0, "b")]}, "m",
        marks={"near": [(2.0, "p50"), (3.0, "p95")], "far": [(20.0, "p50"), (90.0, "p95")]}, width=cc.NARROW,
    )  # fmt: skip
    labels = re.findall(r'text-anchor="(\w+)" class="tick">(p\d\d[^<]*)<', lat)
    check(
        "a p50 and a p95 drawn nearer than a label's width with no room to lean left are one label ('p50 · p95' over "
        "the row's name otherwise); far apart, centred",
        labels == [("start", "p50 · p95"), ("middle", "p50"), ("middle", "p95")],
        labels,
    )
    mid = cc.strip(
        {"near": [(1.0, "a"), (100.0, "b")]},
        "m",
        marks={"near": [(50.0, "p50"), (52.0, "p95")]},
        width=cc.NARROW,
    )
    labels = re.findall(r'text-anchor="(\w+)" class="tick">(p\d\d[^<]*)<', mid)
    check(
        "a p50 and a p95 drawn nearer than a label's width with room at the left lean apart",
        labels == [("end", "p50"), ("start", "p95")],
        labels,
    )
    # An arm a round retired has no interval against the leader (it is outside the family the decision tests): the chart
    # names it, with the round, where it would have been drawn (ADR-0006: a retired arm is shown, never recommended).
    opened = evh(
        "round-open",
        "--goal",
        "g",
        "--dataset",
        "tk_val",
        "--keep",
        "s1_v1,s2_v1,s3_v1",
        "--hypothesis",
        "is three sentences too many",
    )
    ret = (
        opened
        if opened.returncode
        else evh(
            "round-retire",
            "--goal",
            "g",
            "--round",
            "r3",
            "--arm",
            "s3_v1",
            "--reason",
            "it keeps too much text",
        )
    )
    after = chart("intervals", "--goal", "g", "--dataset", "tk_val")
    check(
        "intervals: an arm a round retired is named in the chart's note with its round, not dropped silently",
        ret.returncode == 0
        and not any(x["arm"].startswith("s3_v1") for x in after["rows"])
        and "Left out: s3_v1" in after.get("caption", "")
        and "retired in r3" in after.get("caption", "")
        and "retired in r3" in after.get("svg", ""),
        (opened.stderr[-200:], ret.stderr[-200:], after.get("caption", "")[-300:]),
    )
    # A left-out arm's flags name other arms by their full label: the group's common scorer is named once, not there.
    from unittest import mock

    from evaluation_harness import charts as _charts

    _fake = {
        "direction": "higher",
        "measure": "f1",
        "dataset": "d",
        "scored_against": "ref",
        "scorer": "5f2c057c",
        "arms": [
            {"arm": "a", "label": "lead", "leader": True, "vs_leader": {}},
            {
                "arm": "z",
                "label": "tested",
                "leader": False,
                "vs_leader": {"delta": -0.1, "ci": [-0.2, 0.0], "p": 0.05, "verdict": "not separated"},
            },
            {
                "arm": "b",
                "label": "other",
                "leader": False,
                "vs_leader": {},
                "flags": ["worse than the baseline base_v1 · rescored 5f2c057c (p 0.03)"],
            },
            {
                "arm": "c",
                "label": "third",
                "leader": False,
                "vs_leader": {},
                "flags": ["worse than base_v1 · rescored 5f2c057c, repeats ×3"],
            },
        ],
    }
    with mock.patch.object(_charts, "_group", return_value=_fake):
        _cap = _charts.intervals("g")["caption"]
    check(
        "intervals: the left-out note never names the group's common scorer (the caption names it once)",
        "Left out:" in _cap
        and "rescored 5f2c057c" not in _cap.split("Left out:")[1]
        and "base_v1 · repeats" in _cap,
        _cap[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
