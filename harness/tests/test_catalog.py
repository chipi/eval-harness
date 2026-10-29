#!/usr/bin/env python3
"""Assertions for the catalog and the run inspector (catalog_build.py, catalog_serve.py).

    python tests/test_catalog.py

On a small data tree written here: the build, that no item text reaches the static pages, the
inspector's numbers against pair-test's, its refusals (mixed datasets, unknown arms), and the
server's rules (127.0.0.1 Host only, only the catalog and the data tree, no dot-folders).
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/

from evaluation_harness import catalog_build as cb  # noqa: E402
from evaluation_harness import catalog_serve as cs  # noqa: E402
from evaluation_harness import stats  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.catalog_adapter import HarnessAdapter  # noqa: E402

SECRET = "zebra-quokka-unique-output-text"
tmp = Path(tempfile.mkdtemp(prefix="evh-catalog-"))
data = tmp / "data"


def run(runs_dir, run_id, dataset, config, scores, text=SECRET, kinds=None, ref=None, root=None):
    d = (root or data) / runs_dir / run_id
    (d / "outputs").mkdir(parents=True)
    (d / "metrics.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "dataset_id": dataset,
                "config_id": config,
                "primary_metric": "acc",
                "metric_kinds": kinds or {"acc": "quality", "words": "descriptive"},
                "fingerprint": {"data": {"reference_id": ref or f"gold/{dataset}"}},
            }
        )
    )
    rows = []
    for i, s in enumerate(scores):
        rows.append(json.dumps({"item_id": f"i{i:02d}", "acc": s, "words": 10.0 + i}))
        (d / "outputs" / f"i{i:02d}.txt").write_text(f"{text} {config} {i}")
    (d / "predictions.jsonl").write_text("\n".join(rows) + "\n")


try:
    base = [0.5] * 12
    run("runs", "a_1", "ds1", "arm_a", base)
    run("runs", "b_1", "ds1", "arm_b", [0.6] * 10 + [0.5, 0.4])
    run("runs", "b_2", "ds1", "arm_b", [0.8] * 10 + [0.5, 0.4])  # a repeat: averaged per item
    run("runs", "c_1", "ds2", "arm_c", base)
    (data / "references" / "gold" / "ds1").mkdir(parents=True)
    (data / "references" / "gold" / "ds1" / "i00.txt").write_text(SECRET + " reference")
    (data / "runs" / ".hidden").mkdir()
    (data / "runs" / ".hidden" / "x.txt").write_text("hidden")

    A = HarnessAdapter(data)
    arms = sorted(A.arms())
    check(
        "arms: one per config per dataset, repeats folded",
        arms == ["runs/ds1/arm_a", "runs/ds1/arm_b", "runs/ds2/arm_c"],
        arms,
    )
    vals = A.scores("runs/ds1/arm_b")["acc"]["values"]
    check("scores: repeats averaged per item, as pair-test does", abs(vals["i00"] - 0.7) < 1e-12)
    check("descriptive metric kinds are neutral", A.is_neutral("words") and not A.is_neutral("acc"))
    # One adapter's descriptive `parsed` must not make it neutral where another declares it quality.
    kinds_tree = tmp / "mixed"
    run("runs", "q_1", "dq", "arm_q", base, kinds={"acc": "quality", "parsed": "quality"}, root=kinds_tree)
    run(
        "runs", "d_1", "dd", "arm_d", base, kinds={"acc": "quality", "parsed": "descriptive"}, root=kinds_tree
    )
    M = HarnessAdapter(kinds_tree)
    check(
        "neutral per dataset: a quality on one, descriptive on another",
        not M.is_neutral("parsed", "dq") and M.is_neutral("parsed", "dd") and not M.is_neutral("parsed"),
    )
    check(
        "the metric page's kind names where it is descriptive",
        "(descriptive on dd)" in cb._kind_of(M, "parsed", {"dq": 1, "dd": 1}),
    )

    out = tmp / ".build" / "catalog"
    counts = cb.build(A, out)
    check(
        "build: datasets, arms, configs and references counted",
        counts == {"goals": 0, "datasets": 2, "arms": 3, "configs": 3, "references": 1},
        counts,
    )
    html_pages = list(out.rglob("*.html"))
    t = cb.table(
        "t",
        ["a", "b"],
        [["<a>gold/ag_news_200</a>", "Pick a classifier that labels each news headline with its topic."]],
    )
    check(
        "table: a sentence cell is prose (a readable width on phones); an id cell is not",
        '<td class="prose">Pick' in t and "<td><a>gold/ag_news_200" in t,
    )
    check(
        "build: no page carries a style attribute (a deployment's policy forbids them)",
        not [p.name for p in html_pages if 'style="' in p.read_text()],
    )
    check(
        "build: the harness adds nothing to a page's head of its own (no analytics)",
        all("<script defer" not in p.read_text() for p in html_pages),
    )
    # --head: a deployment's own HTML (its analytics, a tag) in every page's head.
    cb.HEAD = '<meta name="deploy-tag" content="ours">\n'
    head_out = tmp / ".build" / "catalog-head"
    cb.build(A, head_out)
    cb.HEAD = ""
    head_pages = list(head_out.rglob("*.html"))
    check(
        "--head: its HTML is in every page's head",
        head_pages
        and all('<meta name="deploy-tag" content="ours">\n</head>' in p.read_text() for p in head_pages),
    )
    # --about: a deployment's paragraph on the overview only.
    cb.ABOUT = '<p id="deploy-about">Our six experiments.</p>'
    about_out = tmp / ".build" / "catalog-about"
    cb.build(A, about_out)
    cb.ABOUT = ""
    check(
        "--about: its HTML is on the overview, under the description, and on no other page",
        '<div class="about"><p id="deploy-about">Our six experiments.</p></div>'
        in (about_out / "index.html").read_text()
        and not [
            p.name
            for p in about_out.rglob("*.html")
            if p.name != "index.html" and "deploy-about" in p.read_text()
        ],
    )
    check(
        "build: without --about the overview has no about block",
        'class="about"' not in (out / "index.html").read_text(),
    )
    # --link: the parts of the publication, one switcher on every page, the catalog marked.
    parts_out = tmp / ".build" / "catalog-parts"
    cb.build(
        A, parts_out, (("Site", "https://s.example/"), ("Catalog", "."), ("Docs", "https://s.example/docs/"))
    )
    ds_page = next((parts_out / "d").glob("*.html")).read_text()
    check(
        "--link: Site · Catalog · Docs in order on every page, the catalog marked, the logo opens the first",
        all('class="sections"' in p.read_text() for p in parts_out.rglob("*.html"))
        and re.findall(r'<nav class="sections"[^>]*>(.*?)</nav>', ds_page)[0]
        == '<a href="https://s.example/">Site</a><a href="../index.html" aria-current=page>Catalog</a>'
        '<a href="https://s.example/docs/">Docs</a>'
        and '<a class="brand" href="https://s.example/"' in ds_page
        and "<span>eval catalog</span></a>" in ds_page,
    )
    check(
        "overview tiles: a long count also in short form for a phone, a short one as it is",
        cb.tile_value("19,534,609") == '<span class="full">19,534,609</span><span class="short">19.5M</span>'
        and cb.tile_value(140) == "140"
        and cb.tile_value("$27.98") == "$27.98",
    )
    pages = {p.relative_to(out).as_posix() for p in out.rglob("*.html")}
    check(
        "build: home, a page per dataset, the inspector",
        {"index.html", "d/ds1.html", "d/ds2.html", "inspect.html"} <= pages,
        pages,
    )
    leaked = [
        p.name
        for p in out.rglob("*")
        if p.is_file() and SECRET in p.read_text(encoding="utf-8", errors="ignore")
    ]
    check("build: no item text in any static file", not leaked, leaked)
    page_ds1 = (out / "d/ds1.html").read_text()
    check(
        "build: one inspector link for all the dataset's arms, best first",
        "inspect.html?runs=runs/ds1/arm_b,runs/ds1/arm_a" in page_ds1,
    )

    # Metrics and references: a silver set written by arm_s, arm_s and arm_t scored against it,
    # and arm_t judged. Each row says what it is scored against; metric and reference link out.
    data3 = tmp / "data3"
    run("runs", "s_1", "ds3", "arm_s", [0.9] * 6, ref="silver/ds3", root=data3)
    run("runs", "t_1", "ds3", "arm_t", [0.5] * 6, ref="silver/ds3", root=data3)
    run("runs-judged/sc1", "t_1", "ds3", "arm_t", [3.0] * 6, ref="silver/ds3", root=data3)
    for rid, extra in (
        ("runs/s_1", {"metric_descriptions": {"acc": "share of items right"}}),
        ("runs-judged/sc1/t_1", {"derived": {"kind": "judge", "with": {"scorer_id": "sc1"}}}),
    ):
        mj = data3 / rid / "metrics.json"
        mj.write_text(json.dumps({**json.loads(mj.read_text()), **extra}))
    silver = data3 / "references" / "silver" / "ds3"
    silver.mkdir(parents=True)
    (silver / "i00.txt").write_text("x")
    (silver / "manifest.json").write_text(
        json.dumps({"authored_by": "arm_s", "from_run": {"run_id": "s_1"}, "model": "m-1", "tier": "silver"})
    )
    out3 = tmp / ".build" / "catalog3"
    cb.build(HarnessAdapter(data3), out3)
    ds3 = (out3 / "d/ds3.html").read_text()
    check(
        "dataset page: rows tinted by what they are scored against",
        re.search(r'<tr class="t-author"><td><a class="cell-link" href="\.\./a/[^"]+">arm_s<', ds3)
        is not None
        and re.search(r'<tr class="t-silver"><td><a class="cell-link" href="\.\./a/[^"]+">arm_t<', ds3)
        is not None
        and re.search(
            r'<tr class="t-judged"><td><a class="cell-link" href="\.\./a/[^"]+">arm_t · judged/sc1', ds3
        )
        is not None,
        ds3[:0],
    )
    check(
        "dataset page: the metric links to its page, the reference to its page, a judged row names its judge",
        'href="../m/acc.html"' in ds3 and 'href="../r/silver-ds3.html"' in ds3 and "judge <code" in ds3,
    )
    metrics = (out3 / "metrics.html").read_text()
    check(
        "metrics page: the project's description, under the anchor every metric link uses; only recorded metrics listed",
        'id="m-acc"' in metrics and "share of items right" in metrics and "Prompt tokens" not in metrics,
    )
    home = (out3 / "index.html").read_text()
    check(
        "home: the catalog at a glance (counts, goals, activity and spend, coverage, what was recorded)",
        all(
            x in home
            for x in ('class="tiles"', "goals at a glance", "activity and spend", "coverage", "recorded")
        )
        and 'href="datasets.html"' in home
        and 'href="references.html"' in home,
    )
    nav = re.findall(r'<nav class="nav">(.*?)</nav>', home)[0]
    check(
        "nav: Overview, Goals, Data (Datasets, References), Experiments (Arms, Configs, Metrics), Activity, Inspector",
        nav.count("<a ") == 9
        and re.findall(r"<summary[^>]*>([^<]+)</summary>", nav) == ["Data", "Experiments"]
        and all(
            x in nav for x in (">Datasets<", ">References<", ">Arms<", ">Configs<", ">Metrics<", ">Activity<")
        ),
        nav[:300],
    )
    menu = re.findall(r'<nav class="menu-links">(.*?)</nav>', home)[0]
    check(
        "the phone's menu lists every page, a group's under its name",
        menu.count("<a ") == 9 and menu.count('class="menu-group"') == 2,
    )
    check(
        "the home tiles open their pages: activity, arms, configs grouped by config",
        all(
            x in home
            for x in (
                'href="activity.html"',
                'href="arms.html"',
                'href="arms.html?group=config"',
                'class="legend groups"',
            )
        ),
    )
    for name in ("activity.html", "arms.html"):
        check(f"build: {name}", (out3 / name).is_file())
    check("no switcher without --link: a catalog on its own", 'class="sections"' not in home)
    dsp = (out3 / "datasets.html").read_text()
    check("datasets page: every dataset, linked", 'href="d/ds3.html"' in dsp)
    refs_idx = (out3 / "references.html").read_text()
    check(
        "references page: every reference, its tier, dataset and author linked to the author's arm",
        'href="r/silver-ds3.html"' in refs_idx
        and 'href="d/ds3.html"' in refs_idx
        and ">arm_s</a>" in refs_idx,
    )
    arm_pages = sorted(p.name for p in (out3 / "a").glob("*.html"))
    arm_s_page = next((out3 / "a" / n for n in arm_pages if n.endswith("arm_s.html")), None)
    check(
        "arm pages: one per arm",
        len(arm_pages) == len(HarnessAdapter(data3).arms()) and arm_s_page is not None,
        str(arm_pages),
    )
    if arm_s_page:
        ap_ = arm_s_page.read_text()
        check(
            "arm page: dataset, what it is scored against, its metrics linked, its runs, its config, and the note that it wrote its reference",
            'href="../d/ds3.html"' in ap_
            and 'href="../r/silver-ds3.html"' in ap_
            and 'href="../m/acc.html"' in ap_
            and "runs" in ap_
            and "wrote the reference it is scored against" in ap_,
        )
    mpage = (out3 / "m" / "acc.html").read_text()
    check(
        "metric page: its description, which way is better, and the arms recording it, linked",
        "share of items right" in mpage and "higher" in mpage and 'href="../a/' in mpage,
    )
    check("metrics page: each metric links to its own page", 'href="m/acc.html"' in metrics)
    # The same pages in the terminal (CLI parity): one adapter, one computation.
    import contextlib as _cl
    import io as _io

    from evaluation_harness import catalog_views as _cv

    def _view(fn, argv):
        buf = _io.StringIO()
        real = _cv.load_catalog_adapter
        _cv.load_catalog_adapter = lambda spec=None: HarnessAdapter(data3)
        try:
            with _cl.redirect_stdout(buf):
                fn(argv)
        finally:
            _cv.load_catalog_adapter = real
        return buf.getvalue()

    ov = _view(_cv.overview, ["--period", "all"])
    tiles = cb.home_counts(
        HarnessAdapter(data3), cb.collect(HarnessAdapter(data3)), HarnessAdapter(data3).spend()
    )
    lines = {ln.split()[0]: ln.split()[1] for ln in ov.splitlines()[1:10] if ln.startswith("  ")}
    check(
        "evh overview --period all: every stock tile is the page's count, then the sections",
        all(lines.get(k) == str(n) for k, n, _ in tiles[:6])
        and all(x in ov for x in ("goals at a glance", "activity", "coverage:")),
        ov[:600],
    )
    from datetime import date as _date

    from evaluation_harness import catalog_periods as cp

    def _b(k, d):
        b = cp.bounds(k, _date.fromisoformat(d), "2025-01-01")
        return b["since"], b["until"], b["prev"]

    check(
        "periods: a month to date is against the same days of the month before, clamped to its end",
        _b("month", "2026-03-31") == ("2026-03-01", "2026-03-31", ("2026-02-01", "2026-02-28")),
    )
    check(
        "periods: weeks start on Monday; last week is whole, against the week before",
        _b("week", "2026-10-28") == ("2026-10-26", "2026-10-28", ("2026-10-19", "2026-10-21"))
        and _b("lastweek", "2026-10-26") == ("2026-10-19", "2026-10-25", ("2026-10-12", "2026-10-18")),
    )
    check(
        "periods: last month across a new year, and a year to date on 29 February",
        _b("lastmonth", "2026-01-15") == ("2025-12-01", "2025-12-31", ("2025-11-01", "2025-11-30"))
        and _b("year", "2028-02-29") == ("2028-01-01", "2028-02-29", ("2027-01-01", "2027-02-28")),
    )
    check(
        "periods: the last N days against the N before; all time has no trend",
        _b("7d", "2026-10-27") == ("2026-10-21", "2026-10-27", ("2026-10-14", "2026-10-20"))
        and _b("all", "2026-10-27") == ("2025-01-01", "2026-10-27", None),
    )
    check(
        "trends: a percent, 'new' when the period before had none, nothing to say when neither has",
        cp.trend(150, 100)["text"] == "▲ 50%"
        and cp.trend(50, 100)["text"] == "▼ 50%"
        and cp.trend(5, 0)["text"].startswith("new")
        and cp.trend(0, 0)["pct"] is None,
    )
    check(
        "a table cell's trend: ▲/▼ %, '▲ from 0' when the period before had none, nothing when neither",
        cp.cell(5, 10) == "5 ▼ 50%"
        and cp.cell(5, 0) == "5 ▲ from 0"
        and cp.cell(0, 0) == "0"
        and cp.cell(3, None) == "3",
    )

    # The period on the other pages: one builder per page, read by the page and by evh.
    from evaluation_harness import catalog_arms as ca

    A3 = HarnessAdapter(data3)
    by3 = cb.collect(A3)
    first3 = cb.window(A3, by3)["first"]
    pds = cb.period_datasets(A3, by3)
    per = cp.in_period(pds, "all", _date.today(), first3)
    page_keys = set(re.findall(r'<tr[^>]* data-key="([^"]+)"', (out3 / "datasets.html").read_text()))
    check(
        "datasets page: one dated row per dataset, keyed as its builder keys it",
        page_keys == set(pds) and "window.PERIOD_ROWS=" in (out3 / "datasets-rows.js").read_text(),
        f"{page_keys} {set(pds)}",
    )
    dl = next(
        ln for ln in _view(_cv.datasets, ["--period", "all"]).splitlines() if ln.strip().startswith("ds3")
    )
    check(
        "evh datasets --period all: the builder's runs for the dataset (all time: no trend)",
        re.split(r"\s{2,}", dl.strip())[-2] == str(per["ds3"]["runs"])
        and per["ds3"]["runs"]
        == sum(
            1
            for a in by3["ds3"]["arms"]
            for r in a["run_list"]
            if r.get("created_at") and not r.get("derived")
        ),
        dl,
    )
    rows3 = {r["arm"]: r for r in ca.arm_rows(A3, by3)}
    check(
        "arms page: each arm says how it was measured",
        rows3["runs/ds3/arm_s"]["how"] == "measured"
        and rows3["runs-judged/sc1/ds3/arm_t"]["how"] == "judged by sc1",
        str({k: v["how"] for k, v in rows3.items()}),
    )
    arms_html = (out3 / "arms.html").read_text()
    check(
        "arms page: every arm a row, with what the grouping and the filters read",
        len(re.findall(r'<tr[^>]* data-key="runs', arms_html)) == len(rows3)
        and 'data-config="arm_t"' in arms_html
        and 'data-scored="judge"' in arms_html
        and "judged by sc1" in arms_html,
    )
    grouped = _view(_cv.arms, ["--by", "config"])
    check(
        "evh arms --by config: a heading per config, its arms under it",
        "config arm_t (2 arms)" in grouped and "config arm_s (1 arms)" in grouped,
        grouped[:400],
    )
    check(
        "evh arms --configs: one row per config across its datasets",
        all(x in _view(_cv.arms, ["--configs"]) for x in ("arm_s", "arm_t", "rank on each goal")),
    )
    act = _view(_cv.activity, ["--period", "all"])
    check(
        "evh activity: by dataset, by arm, by kind, from the activity page's builder",
        all(x in act for x in ("by dataset:", "by arm (", "by kind:", "ds3")),
        act[:400],
    )
    arm_id = next(a for a in HarnessAdapter(data3).arms() if a.endswith("/arm_s"))
    ar = _view(_cv.arms, ["--arm", arm_id])
    check(
        "evh arms --arm: the arm page's facts, its metrics and the note that it wrote its reference",
        "scored against  silver/ds3" in ar and "metrics:" in ar and "wrote the reference" in ar,
        ar[:500],
    )
    cs.set_adapter(HarnessAdapter(data3))
    r_ = cs.compare({"runs": ["runs/ds3/arm_s,runs/ds3/arm_t"], "baseline": ["runs/ds3/arm_s"]})
    check(
        "inspector: a baseline that wrote the reference is called out",
        any("wrote the reference these arms are scored against" in w for w in r_.get("warnings", [])),
        r_.get("error") or r_.get("warnings"),
    )
    mt = _view(_cv.metrics, ["--metric", "acc"])
    check(
        "evh metrics --metric: the metric page's description and the arms recording it",
        "share of items right" in mt and "on ds3:" in mt,
        mt[:400],
    )
    ref_page = (out3 / "r/silver-ds3.html").read_text()
    check(
        "reference page: who wrote it, from which run, and every arm scored against it (not the judged one)",
        "arm_s" in ref_page
        and "s_1" in ref_page
        and "m-1" in ref_page
        and ref_page.count('class="btn small"') == 2,
    )

    cs.set_adapter(A)
    r = cs.compare({"runs": ["runs/ds1/arm_a,runs/ds1/arm_b"], "baseline": ["runs/ds1/arm_a"]})
    check(
        "compare: default metric is the primary one, never the descriptive one",
        r.get("metric") == "acc",
        r.get("metric"),
    )
    row = r["rows"][0]
    deltas = [vals[i] - 0.5 for i in sorted(vals)]
    check("compare: p is stats.sign_flip_p on the per-item deltas", row["p"] == stats.sign_flip_p(deltas))
    check("compare: verdict and direction", row["verdict"] == "separated: better" and row["wins"] == 10)
    pair = {"runs": ["runs/ds1/arm_a,runs/ds1/arm_b"], "baseline": ["runs/ds1/arm_a"]}
    check(
        "compare: a threshold above alpha from the URL is refused, not obeyed",
        "error" in cs.compare({**pair, "threshold": ["1.0"]}),
    )
    check(
        "compare: family=1 for the one pair tested is accepted",
        "error" not in cs.compare({**pair, "family": ["1"]}),
    )
    check(
        "compare: a threshold below what the family allows (alpha/5 = 0.01) is refused",
        "error" in cs.compare({**pair, "family": ["5"], "threshold": ["0.001"]}),
    )
    big = cs.compare({**pair, "family": ["5"]})
    check(
        "compare: a pair opened from a group is held to the group's family (alpha/5)",
        "error" not in big and abs(big["rows"][0]["threshold"] - stats.ALPHA / 5) < 1e-12,
        str(big.get("rows", [{}])[0].get("threshold")),
    )
    check("compare: shape metrics feed the scatter", "words" in r["shape"])

    # Conditions: two arms measured on different machines, by different scorer code.
    data4 = tmp / "data4"
    for rid, cfg, machine, scorer in (
        ("p_1", "arm_p", "Linux/x86_64", "aa"),
        ("q_1", "arm_q", "Darwin/arm64", "bb"),
    ):
        run("runs", rid, "ds4", cfg, [0.5] * 6, ref="gold/ds4", root=data4)
        mj = data4 / "runs" / rid / "metrics.json"
        m = json.loads(mj.read_text())
        m["fingerprint"] = {
            "version": 4,
            "host": {"platform": machine, "cpu_count": 8},
            "system_under_test": {"libraries": {"numpy": "2.0"}},
            "instrument": {
                "harness": {"version": "0.4.0"},
                "adapter": {"id": "adapter.py", "sha256": scorer * 32},
            },
            "data": {"reference_id": "gold/ds4", "items_sha256": "c" * 64, "references_sha256": "d" * 64},
        }
        mj.write_text(json.dumps(m))
    cs.set_adapter(HarnessAdapter(data4))
    c4 = (
        cs.compare({"runs": ["runs/ds4/arm_p,runs/ds4/arm_q"], "baseline": ["runs/ds4/arm_p"]}).get(
            "conditions"
        )
        or {}
    )
    differ = {d["name"] for d in c4.get("differ", [])}
    check(
        "compare: the conditions that differ (machine, scorer), not those that match (library, items)",
        differ == {"machine.platform", "scorer.sha256"} and c4.get("fields", 0) >= 8,
        c4,
    )
    check(
        "compare: a different scorer is named as making the numbers different measurements",
        any("different scorers" in w for w in c4.get("warnings", [])),
        c4.get("warnings"),
    )
    cs.set_adapter(A)
    bad = cs.compare({"runs": ["runs/ds1/arm_a,runs/ds2/arm_c"]})
    check("compare: refuses arms on different datasets", "different datasets" in bad.get("error", ""), bad)
    check(
        "compare: refuses an unknown arm",
        "no arm known" in cs.compare({"runs": ["runs/nope"]}).get("error", ""),
    )
    check("compare: a run directory selects its arm", A.arms_of("runs/b_2") == ["runs/ds1/arm_b"])
    it = cs.item({"arms": ["runs/ds1/arm_a,runs/ds1/arm_b"], "item": ["i00"], "ref": ["gold/ds1"]})
    check(
        "item: each arm's output, the latest repeat",
        it["views"]["runs/ds1/arm_b"]["text"] == f"{SECRET} arm_b 0",
    )
    check("item: the reference's text", it["reference"]["view"]["text"] == SECRET + " reference")
    check("item: refuses an unknown arm", "error" in cs.item({"arms": ["../etc"], "item": ["i00"]}))
    check(
        "compare: a run directory selects its arm",
        "error" not in cs.compare({"runs": ["runs/b_2,runs/ds1/arm_a"]}),
        cs.compare({"runs": ["runs/b_2,runs/ds1/arm_a"]}).get("error"),
    )

    class Permissive(HarnessAdapter):
        """An adapter whose arms_of accepts any path it is handed (the podcast one did)."""

        def arms_of(self, path):
            return super().arms_of(path) or [path]

    cs.set_adapter(Permissive(data))
    check(
        "server: a path the catalog does not list is refused, whatever arms_of says",
        "error" in cs.compare({"runs": ["../../.git"]})
        and "error" in cs.item({"arms": ["../../.git"], "item": ["i00"]}),
    )
    check(
        "server: an unknown reference is refused",
        "error" in cs.item({"arms": ["runs/ds1/arm_a"], "item": ["i00"], "ref": ["../../etc"]}),
    )
    cs.set_adapter(A)

    # the server's document root is the project root: serve this temp tree as one
    cs.ROOT = tmp
    prefixes = cs.served(out, data)
    check(
        "served: the catalog and the data tree, nothing else",
        prefixes == ("/.build/catalog/", "/data/"),
        prefixes,
    )
    (tmp / "docs").mkdir(exist_ok=True)
    check(
        "served: a directory the adapter names in served_dirs, and only that",
        cs.served(out, data, (tmp / "docs",)) == ("/.build/catalog/", "/data/", "/docs/"),
        cs.served(out, data, (tmp / "docs",)),
    )
    cs.Handler.prefixes = prefixes
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(cs.Handler, directory=str(tmp)))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def get(path, host=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}", headers={"Host": host or f"127.0.0.1:{port}"}
        )
        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310 — the test's own server on 127.0.0.1  # nosec B310
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, ""

    st, body = get("/api/compare?runs=runs/ds1/arm_a,runs/ds1/arm_b")
    check("http: /api/compare answers", st == 200 and json.loads(body)["metric"] == "acc", st)
    check("http: the catalog is served", get("/.build/catalog/index.html")[0] == 200)
    check("http: the data tree is served", get("/data/runs/a_1/metrics.json")[0] == 200)
    check(
        "http: a foreign Host is refused (DNS rebinding)",
        get("/.build/catalog/index.html", "evil.example")[0] == 403,
    )
    check("http: nothing outside the two trees", get("/scripts/catalog_serve.py")[0] == 404)
    check("http: no dot-folder inside them", get("/data/runs/.hidden/x.txt")[0] == 404)
    check("http: no climbing out", get("/data/../secret")[0] == 404)
    # THROUGH /api/: a path under /api/ skipped every rule above and fell through to the file
    # server, so /api/../.env read a project's keys (found reviewing 0.4.2). Sent as-is: urllib
    # would leave `..` alone too, but http.client says so.
    import http.client

    def raw(path, host=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", path, headers={"Host": host or f"127.0.0.1:{port}"})
        r = c.getresponse()
        body = r.read().decode(errors="replace")
        c.close()
        return r.status, body

    (tmp / ".env").write_text("OPENAI_API_KEY=sk-test-not-served\n")
    leaks = {
        p: raw(p)
        for p in (
            "/api/../.env",
            "/api/%2e%2e/.env",
            "/api/../data/runs/a_1/metrics.json",
            "/api/x/../../.env",
        )
    }
    check(
        "http: nothing is read through /api/ (`..`, encoded or not, and data paths)",
        all(st == 404 and "sk-test" not in body for st, body in leaks.values()),
        {p: st for p, (st, _b) in leaks.items()},
    )
    check("http: an /api/ path that is no endpoint is 404", raw("/api/nope")[0] == 404)
    check(
        "http: every /api/ path that is no endpoint has one route name for the hooks",
        cs._route("/api/nope") == cs._route("/api/../x") == "/api/other"
        and cs._route("/api/compare") == "/api/compare",
        (cs._route("/api/nope"), cs._route("/api/compare")),
    )
    srv.shutdown()

    # PUBLIC mode: the API only, to the named host, rate-limited, arms capped, answers cached
    cs.LIMITS.update(hosts=("catalog.example.org",), rate=5, max_arms=2)
    cs.Handler.prefixes = ()
    cs.cache_clear()
    cs._HITS.clear()
    pub = ThreadingHTTPServer(("127.0.0.1", 0), partial(cs.Handler, directory=str(tmp)))
    port = pub.server_address[1]
    threading.Thread(target=pub.serve_forever, daemon=True).start()
    H = "catalog.example.org"
    check("public: answers the named host", get("/api/health", H)[0] == 200)
    check("public: refuses any other host, localhost included", get("/api/health")[0] == 403)
    check(
        "public: serves no files, catalog or data",
        get("/.build/catalog/index.html", H)[0] == 404 and get("/data/runs/a_1/metrics.json", H)[0] == 404,
    )
    pub_leaks = {
        p: raw(p, H)[0]
        for p in ("/api/../.env", "/api/../data/runs/a_1/metrics.json", "/api/%2e%2e/data/", "/api/../")
    }
    check("public: serves no files through /api/ either", set(pub_leaks.values()) == {404}, pub_leaks)
    st, body = get("/api/compare?runs=runs/ds1/arm_a,runs/ds1/arm_b", H)
    check("public: compares", st == 200 and json.loads(body)["metric"] == "acc", st)
    st, body = get("/api/compare?runs=runs/ds1/arm_a,runs/ds1/arm_b,runs/ds2/arm_c", H)
    capped = next((v for k, v in cs._CACHE.items() if "arm_c" in k), (0, b""))
    check(
        "public: at most --max-arms arms in one comparison",
        st == 400 and "at most 2" in json.loads(capped[1] or b"{}").get("error", ""),
        (st, capped),
    )
    key = next(k for k in cs._CACHE if "arm_b" in k)
    check("public: an answer is cached by its exact question", cs._CACHE[key][0] == 200)
    # Text is published only when the deployment names it: by default an item answer carries
    # no output and no reference text, and says so.
    item_q = "/api/item?arms=runs/ds1/arm_a&item=i00&ref=gold/ds1"
    st, body = get(item_q, H)
    j = json.loads(body) if st == 200 else {}
    view = (j.get("views") or {}).get("runs/ds1/arm_a") or {}
    check(
        "public: no output or reference text unless --publish names it",
        st == 200
        and SECRET not in body
        and view.get("kind") == "none"
        and "does not publish outputs" in view.get("note", ""),
        body[:300],
    )
    cs.cache_clear()
    cs.LIMITS["publish"] = ("outputs",)
    hits = {k: list(v) for k, v in cs._HITS.items()}  # the public rate (5 a minute) is not what these test
    for path_id in ("../../references/gold/ds1/i00", "..%2F..%2Fx", "a/b"):
        st, body = get(f"/api/item?arms=runs/ds1/arm_a&item={path_id}", H)
        check(
            f"public: an item id that is a path is refused ({path_id})",
            st == 400
            and "not an item id"
            in json.dumps(cs.item(urllib.parse.parse_qs(f"arms=runs/ds1/arm_a&item={path_id}"))),
            (st, body[:120]),
        )
        cs._HITS.clear()
    cs._HITS.update(hits)
    st, body = get(item_q, H)
    j = json.loads(body) if st == 200 else {}
    check(
        "public: --publish outputs serves the outputs, still not the references",
        st == 200
        and SECRET in body
        and ((j.get("reference") or {}).get("view") or {}).get("kind") in ("none", None),
        body[:300],
    )
    cs.LIMITS["publish"] = ()
    cs.cache_clear()
    codes = [get("/api/health", H)[0] for _ in range(2)] + [
        get("/api/item?arms=runs/ds1/arm_a&item=i00", H)[0] for _ in range(4)
    ]
    check("public: a client over --rate requests a minute gets 429", 429 in codes, codes)
    # A header names the client only when --client-header says which: by default a new
    # CF-Connecting-IP per request is ignored, so it cannot buy a fresh bucket.

    cs._HITS.clear()
    spoofed = []
    for n in range(7):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request(
            "GET",
            "/api/item?arms=runs/ds1/arm_a&item=i00",
            headers={"Host": H, "CF-Connecting-IP": f"10.0.0.{n}"},
        )
        spoofed.append(c.getresponse().status)
        c.close()
    check(
        "public: a spoofed client header does not escape the limit (no --client-header)",
        429 in spoofed,
        spoofed,
    )
    pub.shutdown()
    cs.LIMITS.update(hosts=(), rate=0, max_arms=40)
    # The cache is bounded by the bytes it keeps, not only by its count.
    cs.cache_clear()
    keep = cs._CACHE_BYTES
    cs._CACHE_BYTES = 4000
    for i in range(20):
        cs.answer("/api/compare", f"arms=runs/ds1/arm_a,runs/ds1/arm_b&metric=m&z={i}")
    check(
        "public: the cache keeps at most its byte bound",
        cs._cache_size[0] <= 4000 and sum(len(v[1]) for v in cs._CACHE.values()) == cs._cache_size[0],
        (cs._cache_size[0], len(cs._CACHE)),
    )
    cs._CACHE_BYTES = keep
    check(
        "public: the rate's key is an address (the header's when it is one), never the header's text",
        cs.client_key("203.0.113.9", "10.0.0.1") == "203.0.113.9"
        and cs.client_key("x" * 60000, "10.0.0.1") == "10.0.0.1"
        and cs.client_key("2001:db8:1:2::7", "10.0.0.1") == cs.client_key("2001:db8:1:2::9", "10.0.0.1"),
    )
    cs.cache_clear()
    cs._HITS.clear()

    # Item fields (ADR-0003): a public choice field and a hidden text field on ds1.
    HIDDEN = "walrus-hidden-customer-name"
    (data / "fields").mkdir()
    (data / "fields" / "fs.yaml").write_text(
        "fieldset_id: fs\nfields:\n"
        "  - {name: product, type: choice, values: [x, y], public: true}\n"
        "  - {name: size, type: number}\n"
        "  - {name: customer, type: text}\n"
    )
    (data / "datasets").mkdir()
    (data / "datasets" / "ds1.json").write_text(
        json.dumps(
            {
                "dataset_id": "ds1",
                "version": "1.0",
                "created_at": "x",
                "fieldset": "fs",
                "items": [
                    {
                        "item_id": f"i{k:02d}",
                        "source_sha256": "0" * 64,
                        "fields": {"product": "x" if k < 6 else "y", "size": k, "customer": HIDDEN},
                    }
                    for k in range(12)
                ],
            }
        )
    )
    (data / "datasets" / "ds2.json").write_text(
        json.dumps(
            {
                "dataset_id": "ds2",
                "version": "1.0",
                "created_at": "x",
                "items": [{"item_id": f"i{k:02d}", "source_sha256": "0" * 64} for k in range(20)],
            }
        )
    )
    # An adapter's caches die with it: lru_cache on its methods kept every instance alive.
    import gc
    import weakref

    throwaway = HarnessAdapter(data)
    throwaway.arms(), throwaway.references(), throwaway.item_fields("ds1"), throwaway.goals()
    ref = weakref.ref(throwaway)
    del throwaway
    gc.collect()
    check("adapter: its caches do not keep it alive", ref() is None)
    AF = HarnessAdapter(data)
    by = cb.collect(AF)
    check(
        "collect: a dataset's size is its dataset file's, read through the adapter's data_dir "
        "(20 items, though its one arm scored 12)",
        by["ds2"]["items"] == 20,
        by["ds2"]["items"],
    )
    cs.set_adapter(AF)
    out_f = tmp / ".build" / "catalog-fields"
    cb.build(AF, out_f)
    page_f = (out_f / "d/ds1.html").read_text()
    check(
        "fields: the dataset page lists the declared fields and their coverage",
        "item fields" in page_f and "product" in page_f and "customer" in page_f and "12 of 12" in page_f,
    )
    check("fields: a public field's values are summarised", "x <b>6</b>" in page_f and "y <b>6</b>" in page_f)
    ids = re.findall(r'\bid="([^"]+)"', page_f)
    check(
        "fields: every element id on the page is unique",
        len(ids) == len(set(ids)),
        sorted(i for i in set(ids) if ids.count(i) > 1),
    )
    leaked = [
        p.name
        for p in out_f.rglob("*")
        if p.is_file() and HIDDEN in p.read_text(encoding="utf-8", errors="ignore")
    ]
    check(
        "fields: a field not marked public shows no value on any static page",
        not leaked
        and page_f.count("not public") == 2
        and "0 – 11" not in page_f
        and "distinct" not in page_f,
        leaked or page_f.count("not public"),
    )
    # The dataset page's fields block, in the terminal (CLI parity): fields listed, a field not
    # marked public shows no value there either.
    import contextlib
    import io

    from evaluation_harness import catalog_views as cv

    buf = io.StringIO()
    real_loader = cv.load_catalog_adapter
    cv.load_catalog_adapter = lambda spec=None: AF
    try:
        with contextlib.redirect_stdout(buf):
            cv.datasets(["--dataset-id", "ds1"])
    finally:
        cv.load_catalog_adapter = real_loader
    txt = buf.getvalue()
    check(
        "evh datasets --dataset-id: the fields block, with no value of a field not marked public",
        "fields (field set" in txt and "product" in txt and HIDDEN not in txt and "not public" in txt,
        txt[-600:],
    )
    two = ["runs/ds1/arm_a,runs/ds1/arm_b"]
    r = cs.compare({"runs": two, "baseline": ["runs/ds1/arm_a"], "where": ["product:x"]})
    check(
        "fields: a filter compares only the matching items",
        r.get("rows") and r["rows"][0]["n"] == 6 and any("Filtered to the 6" in w for w in r["warnings"]),
        r.get("error") or r.get("rows"),
    )
    r = cs.compare({"runs": two, "baseline": ["runs/ds1/arm_a"], "where": ["size:..2"]})
    check("fields: a number filter takes a range", r.get("rows") and r["rows"][0]["n"] == 3, r.get("error"))
    check(
        "fields: filtering by an undeclared field is refused",
        "error" in cs.compare({"runs": two, "where": ["colour:red"]}),
    )
    r = cs.compare({"runs": two, "baseline": ["runs/ds1/arm_a"], "by": ["product"]})
    bd = r.get("breakdown") or {}
    joint = {
        (g["group"], x["arm"]): x["p"] for g in bd.get("groups", []) for x in g["rows"] if x["p"] is not None
    }
    check(
        "fields: a breakdown tests each group, Holm over all of them together",
        [g["group"] for g in bd.get("groups", [])] == ["x", "y"]
        and bd.get("family_size") == len(joint) == 2
        and all(
            x["threshold"] == stats.holm(joint)[(g["group"], x["arm"])][0]
            for g in bd["groups"]
            for x in g["rows"]
            if x["p"] is not None
        ),
        r.get("error") or bd,
    )
    check(
        "fields: a breakdown by a number field is refused",
        "error" in cs.compare({"runs": two, "by": ["size"]}),
    )
    it = cs.item({"arms": two, "item": ["i00"]})
    got = {f["name"]: f["value"] for f in it.get("fields", [])}
    check(
        "fields: the local inspector shows every field of an item",
        got == {"product": "x", "size": 0, "customer": HIDDEN},
        got,
    )
    cs.LIMITS.update(hosts=("catalog.example.org",))
    it = cs.item({"arms": two, "item": ["i00"]})
    r = cs.compare({"runs": two})
    check(
        "fields: a public deployment shows only public fields",
        {f["name"] for f in it.get("fields", [])} == {"product"}
        and [f["name"] for f in r.get("fields", [])] == ["product"],
    )
    check(
        "fields: a public deployment refuses a filter on a hidden field",
        "error" in cs.compare({"runs": two, "where": [f"customer:{HIDDEN}"]}),
    )
    cs.LIMITS.update(hosts=())
    cs.set_adapter(A)

    # One reference per comparison: an arm scored against silver and one scored against gold
    # (runs/ and a rescored copy, say) both record `acc`, but the numbers measure different
    # things, so the inspector must not pair them on it. Output length needs no reference.
    data2 = tmp / "data2"
    run("runs", "g_1", "ds1", "arm_g", [0.5] * 12, root=data2)
    run("runs-silver", "s_1", "ds1", "arm_s", [0.9] * 12, ref="silver/ds1", root=data2)
    cs.set_adapter(HarnessAdapter(data2))
    mixed = cs.compare({"runs": ["runs/ds1/arm_g,runs-silver/ds1/arm_s"], "baseline": ["runs/ds1/arm_g"]})
    check(
        "compare: an arm scored against another reference is not tested against the baseline",
        mixed.get("metric") == "acc"
        and "runs-silver/ds1/arm_s" not in mixed.get("series", {})
        and not mixed.get("rows"),
        list(mixed.get("series", {})),
    )
    check(
        "compare: ...and the answer names it and its reference",
        any("silver/ds1" in w and "arm_s" in w for w in mixed.get("warnings", []))
        and not any("on record" in w for w in mixed.get("warnings", [])),
        mixed.get("warnings"),
    )
    words = cs.compare(
        {
            "runs": ["runs/ds1/arm_g,runs-silver/ds1/arm_s"],
            "baseline": ["runs/ds1/arm_g"],
            "metric": ["words"],
        }
    )
    check(
        "compare: a metric that needs no reference compares them anyway",
        "runs-silver/ds1/arm_s" in words.get("series", {}) and len(words.get("rows", [])) == 1,
        words.get("warnings"),
    )
    # The dataset page offers one "inspect together" link per group the inspector can test as
    # a whole: same metric, same reference. One link over all four would mix gold and silver.
    run("runs", "g_2", "ds1", "arm_h", [0.6] * 12, root=data2)
    run("runs-silver", "s_2", "ds1", "arm_t", [0.8] * 12, ref="silver/ds1", root=data2)
    out2 = tmp / "out2"
    cb.build(HarnessAdapter(data2), out2)
    page2 = (out2 / "d" / "ds1.html").read_text(encoding="utf-8")
    together = re.findall(
        r'inspect\.html\?runs=([^"&]+)&metric=acc">Inspect the 2 arms on acc, scored against ([^<]+)<', page2
    )
    check(
        "build: one 'inspect together' link per reference, none mixing them",
        sorted(ref for _, ref in together) == ["gold/ds1", "silver/ds1"]
        and all(
            ("runs-silver" in runs) == (ref == "silver/ds1") and runs.count(",") == 1
            for runs, ref in together
        ),
        together,
    )

    # No primary metric on record (the bundled adapter declares none): the default yardstick
    # fell to the name order, so a fresh project's inspector opened on cost_usd. A score is the
    # yardstick; the bill and the clock only when nothing else was recorded.
    data3 = tmp / "data3"
    for arm, accs in (("arm_p", [0.5] * 8), ("arm_q", [0.7] * 8)):
        d = data3 / "runs" / f"{arm}_1"
        (d / "outputs").mkdir(parents=True)
        (d / "metrics.json").write_text(
            json.dumps(
                {
                    "run_id": f"{arm}_1",
                    "dataset_id": "ds1",
                    "config_id": arm,
                    "fingerprint": {"data": {"reference_id": "gold/ds1"}},
                }
            )
        )
        (d / "predictions.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        "item_id": f"i{i}",
                        "overlap_f1": v,
                        "cost_usd": 0.0,
                        "latency_ms": 1.0 + i,
                        "tokens_in": 10 + i,
                        "tokens_out": 5,
                    }
                )
                + "\n"
                for i, v in enumerate(accs)
            )
        )
    cs.set_adapter(HarnessAdapter(data3))
    plain = cs.compare({"runs": ["runs/ds1/arm_p,runs/ds1/arm_q"], "baseline": ["runs/ds1/arm_p"]})
    check(
        "compare: with no primary metric on record, a score is the default, never cost or latency",
        plain.get("metric") == "overlap_f1",
        plain.get("metric"),
    )
    shape = plain.get("shape") or {}
    check(
        "compare: the scatter's x axis offers latency, cost and tokens (in + out) per item",
        {"latency_ms", "cost_usd", "tokens"} <= set(shape)
        and shape["tokens"]["runs/ds1/arm_p"]["i0"] == 15.0,
        sorted(shape),
    )
    cs.set_adapter(A)

    # the command line: evh catalog builds into the project
    env_root = tmp / "proj"
    shutil.copytree(data, env_root / "data")
    proc = subprocess.run(
        [sys.executable, str(HERE / "cli.py"), "catalog"],
        cwd=env_root,
        capture_output=True,
        text=True,
        env={"EVAL_HOME": str(env_root), "PATH": "/usr/bin:/bin"},
    )
    check(
        "evh catalog: builds into <project>/.build/catalog",
        proc.returncode == 0 and (env_root / ".build/catalog/index.html").is_file(),
        proc.stderr[-300:],
    )
    # The deployment's options reach EVERY page when the builder runs as a command (the module is
    # __main__ then; arms.html was rendered by a second copy of it with the defaults: "eval
    # catalog", no switcher, no --head, /api/, found reviewing the 0.4.4 render).
    (env_root / "head.html").write_text('<meta name="deploy-tag" content="ours">\n')
    (env_root / "about.html").write_text("<p>Ours.</p>\n")
    proc = subprocess.run(
        [
            sys.executable,
            str(HERE / "cli.py"),
            "catalog",
            "--out",
            str(env_root / ".build/catalog-opts"),
            "--link",
            "Site=https://s.example/",
            "--link",
            "Catalog=.",
            "--brand",
            "deploy-brand",
            "--api",
            "/catalog/api/",
            "--head",
            str(env_root / "head.html"),
            "--about",
            str(env_root / "about.html"),
        ],
        cwd=env_root,
        capture_output=True,
        text=True,
        env={"EVAL_HOME": str(env_root), "PATH": "/usr/bin:/bin"},
    )
    opt_pages = sorted((env_root / ".build/catalog-opts").rglob("*.html"))
    missing = [
        p.relative_to(env_root / ".build/catalog-opts").as_posix()
        for p in opt_pages
        if not all(
            s in p.read_text()
            for s in (
                'class="sections"',
                "<span>deploy-brand</span>",
                'content="ours"',
                'data-api="/catalog/api/"',
            )
        )
    ]
    check(
        "evh catalog --link/--brand/--head/--api: every page carries them, arms.html included",
        proc.returncode == 0 and "arms.html" in {p.name for p in opt_pages} and not missing,
        missing or proc.stderr[-300:],
    )

    # a port another program holds: say so, never a traceback
    import socket

    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        busy = held.getsockname()[1]
        proc = subprocess.run(
            [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(busy)],
            cwd=env_root,
            capture_output=True,
            text=True,
            timeout=60,
            env={"EVAL_HOME": str(env_root), "PATH": "/usr/bin:/bin"},
        )
    elsewhere = Path(tempfile.mkdtemp(prefix="evh-elsewhere-"))
    shutil.copytree(env_root / ".build/catalog", elsewhere / "catalog")
    r2 = subprocess.run(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--build-dir", str(elsewhere / "catalog")],
        cwd=env_root,
        capture_output=True,
        text=True,
        timeout=60,
        env={"EVAL_HOME": str(env_root), "PATH": "/usr/bin:/bin"},
    )
    shutil.rmtree(elsewhere, ignore_errors=True)
    check(
        "evh catalog-serve: a build dir outside the project is refused in words, not a traceback",
        r2.returncode != 0 and "inside the project" in r2.stderr and "Traceback" not in r2.stderr,
        r2.stderr[-300:],
    )
    check(
        "evh catalog-serve: a port in use is named, with --port as the way out",
        proc.returncode != 0
        and f"port {busy} is in use" in proc.stderr
        and "--port" in proc.stderr
        and "Traceback" not in proc.stderr,
        proc.stderr[-300:],
    )

    # The inspector's "Average only" table in the terminal (CLI parity): an arm that recorded
    # only a run-level average is listed beside the comparison, never tested.
    import contextlib
    import io

    from evaluation_harness import catalog_views as cv

    data6 = tmp / "data6"
    run("runs", "p_1", "ds6", "arm_p", [0.5] * 6, root=data6)
    run("runs", "q_1", "ds6", "arm_q", [0.7] * 6, root=data6)
    avg = data6 / "runs" / "z_1"
    avg.mkdir(parents=True)
    (avg / "metrics.json").write_text(
        json.dumps(
            {
                "run_id": "z_1",
                "dataset_id": "ds6",
                "config_id": "arm_z",
                "primary_metric": "acc",
                "scores": {"acc": 0.9},
            }
        )
    )
    A6 = HarnessAdapter(data6)
    real_loader = cv.load_catalog_adapter
    cv.load_catalog_adapter = lambda spec=None: A6
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            cv.inspect(["--runs", "arm_p,arm_q,arm_z", "--no-rescore"])
    finally:
        cv.load_catalog_adapter = real_loader
    txt = buf.getvalue()
    check(
        "evh inspect: the Average only table lists an arm with no per-item scores (and --no-rescore runs)",
        "Average only · 1" in txt and "arm_z" in txt and "+0.400" in txt,
        txt[-700:],
    )

    # Arm ids come from the adapter (arm_of), which names the runs directory as the project does:
    # with EVAL_RUNS_DIR=data/runs-v2 a round's arms are runs-v2/..., not an empty runs/... list.
    import os
    import subprocess

    proj7 = tmp / "proj7"
    (proj7 / "data" / "runs-v2").mkdir(parents=True)
    harness_dir = str(Path(__file__).resolve().parents[1])  # the evaluation_harness package
    probe = (
        f"import sys; sys.path.insert(0, {harness_dir!r}); "
        "from evaluation_harness.catalog_adapter import HarnessAdapter; "
        "print(HarnessAdapter().arm_of('ds', 'c'))"
    )
    pf = tmp / "probe_arm_of.py"
    pf.write_text(probe)
    env7 = {k: v for k, v in os.environ.items() if not k.startswith("EVAL_")}
    out7 = subprocess.run(
        [sys.executable, str(pf)],
        cwd=proj7,
        env={**env7, "EVAL_HOME": str(proj7), "EVAL_RUNS_DIR": "data/runs-v2"},
        capture_output=True,
        text=True,
    )
    check(
        "arm_of names the runs directory as the project does (EVAL_RUNS_DIR)",
        out7.stdout.strip() == "runs-v2/ds/c",
        out7.stdout + out7.stderr[-300:],
    )
finally:
    shutil.rmtree(tmp, ignore_errors=True)

sys.exit(summary())
