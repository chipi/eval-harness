"""The Workbench's screenshot review of 2026-11-21 (scenario 080d), as checks on the live test's project.

Each check names the review's item (`workbench.md` #N, `scenario.md` F3/N8) and fails on the behaviour it described:
what the page says, where the text breaks, what a screen offers of another goal's. Run from test_workbench_live_browser.py
once its project has rounds, jobs, a production capture, judges and a second goal.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import _wblayout as L

HARNESS = Path(__file__).resolve().parents[1]

# the words of a line, broken inside a word: (text, the two letters either side of the break)
BROKEN = r"""
(sel) => { const out = [];
  for (const el of document.querySelectorAll(sel)) {
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let prevTop = null, prevCh = '';
    while (w.nextNode()) { const t = w.currentNode;
      for (let i = 0; i < t.length; i++) { const ch = t.data[i];
        if (/\s/.test(ch)) { prevTop = null; continue; }
        const r = document.createRange(); r.setStart(t, i); r.setEnd(t, i + 1);
        const rc = r.getClientRects()[0]; if (!rc) continue;
        if (prevTop !== null && rc.top > prevTop + 3 && /[A-Za-z0-9]/.test(prevCh) && /[A-Za-z0-9]/.test(ch)) out.push(el.textContent.trim().slice(0, 48) + ' [' + prevCh + '|' + ch + ']');
        prevTop = rc.top; prevCh = ch; } } }
  return out; }
"""

# how many lines a cell's text takes
LINES = r"""
(el) => { const tops = new Set(); const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) { const t = w.currentNode; for (let i = 0; i < t.length; i++) { if (/\s/.test(t.data[i])) continue;
    const r = document.createRange(); r.setStart(t, i); r.setEnd(t, i + 1); const rc = r.getClientRects()[0]; if (rc) tops.add(Math.round(rc.top / 4)); } }
  return tops.size; }
"""


def patch(page: Any, glob: str, change: Callable[[dict], None]) -> None:
    """Answer the page's read of `glob` with the server's answer, changed by `change` (a case the project has none of)."""

    def handle(route: Any) -> None:
        resp = route.fetch()
        body = resp.json()
        change(body)
        route.fulfill(status=resp.status, headers={"Content-Type": "application/json"}, body=json.dumps(body))

    page.route(glob, handle)


def say(page: Any, glob: str, doc: dict) -> None:
    """Answer every request to `glob` with `doc` as JSON."""
    page.route(
        glob,
        lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"}, body=json.dumps(doc)
        ),
    )


EMPTY_CHART = {"command": "chart", "version": "x", "result": None, "kind": "not-enough"}
FIG = "<figure class='chart evidence'><svg role='img' aria-label='stub'><rect x='0' y='0' width='10' height='10'/></svg></figure>"


def run(
    page: Any, phone: Any, port: int, check: Callable[..., bool], evh: Callable[..., Any], proj: Any
) -> None:
    """Run the review's checks on the Workbench pages of the live test's project."""
    U = f"http://127.0.0.1:{port}/workbench/#"

    def open_(pg: Any, route: str, h1: str | None = None) -> None:
        pg.evaluate(
            "() => WB.forgetUnsent && WB.forgetUnsent()"
        )  # a form typed in earlier is not what this check is about
        pg.goto(U + route)
        if h1:
            try:
                pg.wait_for_selector(f"h1:has-text('{h1}')", timeout=30000)
            except Exception:
                print("OPEN", route, pg.url, pg.locator("body").inner_text()[:500])
                raise
        L.settled(pg)

    def api(pg: Any, path: str) -> dict:
        return pg.evaluate(
            "(p) => fetch('/api/v1' + p, {credentials: 'same-origin'}).then((r) => r.json())", path
        )

    page.set_viewport_size({"width": 1280, "height": 900})

    # ── jobs (#5, #6) ──────────────────────────────────────────────────────────────────────────────────────────
    # A catalog job nobody asked for: the server's own rebuild, which a project's history keeps from before RFC-040 (a
    # server renders its pages on request now and starts none), written as the server wrote it.
    subprocess.run(  # nosec B603 - this interpreter and the harness's own module
        [sys.executable, "-c", ("import sys; sys.path.insert(0, sys.argv[1]); from evaluation_harness import _jobs; "
                                "_jobs.create('catalog', {}, None, [('catalog', True)])"), str(HARNESS)],
        cwd=proj, env={**os.environ, "EVAL_HOME": str(proj)}, check=True, timeout=120,
    )  # fmt: skip
    cat = (api(page, "/jobs?operation=catalog&limit=1").get("jobs") or [{}])[0]
    open_(page, f"jobs/{cat.get('id')}", "catalog")
    lead = page.locator("main .lead").inner_text()
    check(
        "review #5: a job nobody asked for (the server's own catalog rebuild) says so, not 'asked by ?'",
        cat.get("by") in (None, "") and "asked by ?" not in lead and "server" in lead,
        (cat.get("id"), lead),
    )
    open_(page, "jobs", "Jobs")
    page.evaluate(
        "() => { WB._jobsF = { state: '', operation: 'catalog', goal: '', offset: 0 }; WB.render(); }"
    )
    L.settled(page)
    who = page.locator("main tbody tr").evaluate_all(
        "(rows) => rows.map((r) => r.children[3].innerText.trim())"
    )
    check(
        "review #5: in the jobs list the who of a job nobody asked for is not blank",
        bool(who) and all(who),
        who[:5],
    )
    twin = None  # a finished job whose result is the very text of its log (what a command prints is both)
    for j in api(page, "/jobs?state=succeeded&limit=40").get("jobs") or []:
        full = api(page, f"/jobs/{j['id']}")
        lines = [
            x
            for b in (((full.get("result") or {}).get("result") or {}).get("blocks") or [])
            for x in b.get("lines", [])
        ]
        log = api(page, f"/jobs/{j['id']}/log?from=0").get("log") or ""
        norm = lambda t: "\n".join(x.strip() for x in t.split("\n") if x.strip())  # noqa: E731
        if lines and norm("\n".join(lines)) == norm(log):
            twin = j
            break
    check(
        "review #6 (setup): the project has a finished job whose result and log are the same text",
        twin is not None,
        None,
    )
    open_(page, f"jobs/{(twin or {}).get('id')}")
    page.wait_for_selector("#jb-log", timeout=30000)
    page.wait_for_function(
        "() => document.getElementById('jb-log')?.textContent !== 'reading…'", timeout=30000
    )
    box = page.evaluate(
        """() => {
      const norm = (t) => t.split('\\n').map((x) => x.trim()).filter(Boolean).join('\\n');
      const log = document.getElementById('jb-log'), h = [...document.querySelectorAll('main h2')];
      const box = (h.find((x) => /Its result/.test(x.textContent)) || {}).nextElementSibling;
      const res = box && (box.tagName === 'PRE' ? box : box.querySelector('pre'));
      const s = getComputedStyle(log), logH = h.find((x) => /Its log/.test(x.textContent));
      return { resultIsPre: !!res, same: !!res && norm(res.innerText) === norm(log.innerText),
        max: parseFloat(s.maxHeight), line: parseFloat(s.lineHeight), gap: log.getBoundingClientRect().top - logH.getBoundingClientRect().bottom }; }"""
    )
    check(
        "review #6: a finished job's result is not shown beside a log that says the same, line for line",
        not box["same"],
        box,
    )
    check(
        "review #6: a text box's height is a whole number of its lines (its last line is not cut in half)",
        box["max"] / box["line"] == int(box["max"] / box["line"]),
        box,
    )
    check("review #6: a heading is not touching the box under it", box["gap"] >= 8, box)
    open_(page, "jobs", "Jobs")
    page.evaluate(
        "() => { WB._jobsF = { state: 'succeeded', operation: '', goal: '', offset: 0 }; WB.render(); }"
    )
    L.settled(page)
    spent = page.locator("main tbody tr").first.locator("td").nth(6).inner_text().strip()
    check(
        "review #6: the jobs list shows what a job spent the way its own page does ($0), not a dash",
        spent.startswith("$"),
        spent,
    )

    # ── the eval: charts that contradict their evidence (#2), always resolve (#3) ──────────────────────────────
    rounds = [x["round_id"] for x in api(page, "/goals/tickets_summary/rounds")["result"]["rounds"]]
    rid = rounds[-1]

    def no_leader(b: dict) -> None:
        b["result"].update(
            leader=None,
            rows=[],
            against=[],
            notes=[
                f"no arm of {rid} can lead, though they record overlap_f1: every one is held back: one_v1 (n 3 < min_items 20)"
            ],
        )

    patch(page, "**/api/v1/goals/tickets_summary/rounds/*/evidence", no_leader)
    say(
        page,
        "**/api/v1/charts/gain-cost*",
        {**EMPTY_CHART, "empty": f"round {rid}: no arm records overlap_f1 yet"},
    )
    say(
        page,
        "**/api/v1/charts/intervals*",
        {**EMPTY_CHART, "empty": "goal tickets_summary: one arm only on tk_v1: nothing to compare"},
    )
    say(
        page,
        "**/api/v1/charts/items*",
        {
            "command": "chart",
            "version": "x",
            "result": {
                "kind": "items",
                "title": "t",
                "caption": "c",
                "columns": ["item"],
                "rows": [],
                "svg": FIG,
            },
        },
    )
    open_(page, f"eval/tickets_summary/{rid}", "Its rounds")
    text = page.locator("main").inner_text()
    check(
        "review #2: a round whose evidence says why no arm leads does not also say 'No chart yet' beside charts that draw "
        "(the contradiction of the review), and the reason is said once",
        "No chart yet" not in text
        and page.locator("[data-chart='items'] svg").count() == 1
        and "every one is held back" in text,
        text[:900],
    )
    page.unroute_all()
    for pat in ("gain-cost", "intervals", "latency", "items"):
        page.route(
            f"**/api/v1/charts/{pat}*", lambda route: (__import__("time").sleep(0.6), route.continue_())
        )
    for r in (rounds[0], rid, rounds[0]):
        page.evaluate("(r) => { location.hash = '#eval/tickets_summary/' + r; }", r)
        page.wait_for_timeout(250)
    page.wait_for_function("() => !document.querySelector('[data-lands]')", timeout=60000)
    check(
        "review #3: the charts' placeholders always resolve, however the rounds are switched under slow reads",
        page.locator("[data-lands]").count() == 0
        and "Reading the chart" not in page.locator("main").inner_text(),
        page.locator("main").inner_text()[:300],
    )
    page.unroute_all()

    # ── another goal's datasets, systems and placeholders (#7, #8, #9, #21; UXS-005 step 4 and "The other workflows") ─
    open_(page, "production/tickets_summary", "Learn from production")
    sel = lambda i: page.eval_on_selector(i, "(s) => [...s.options].map((o) => o.value)")  # noqa: E731
    offers = {i: sel(i) for i in ("#wr-ds", "#ca-ds", "#ex-from", "#ol-ds")}
    sysoffers = {i: sel(i) for i in ("#wr-run",)}
    check(
        "review #7: production offers the goal's own datasets (and ones no goal names), never another goal's (UXS-005 W3: "
        "the same rule as the systems screens)",
        all("tk_v1" in v and "ev1" not in v for v in offers.values()),
        offers,
    )
    check(
        "review #7: production offers the goal's own systems, never one filed for another goal",
        all("one_v1" in v and "elsewhere_v1" not in v for v in sysoffers.values()),
        sysoffers,
    )
    open_(page, "study/tickets_summary", "Studies")
    base_opts = sel("#sn6-base")
    ds_opts = sel("#sn6-ds")
    bl = api(page, "/baselines?goal=tickets_summary")["result"]["baselines"]
    want = next((b["reproduce"]["system_id"] for b in bl if b.get("reproduce")), None)
    check(
        "review #8: a new study offers the goal's own systems and validation datasets, never another goal's",
        "elsewhere_v1" not in base_opts and "one_v1" in base_opts and "ev1" not in ds_opts,
        (base_opts, ds_opts),
    )
    check(
        "review #9: a new study starts from the goal's baseline when it has one, not the first system listed",
        want is not None and page.input_value("#sn6-base") == want,
        (want, page.input_value("#sn6-base"), base_opts),
    )
    open_(page, "eval/other_goal", "Its rounds")
    ph = page.get_attribute("#ro-q", "placeholder") or ""
    check(
        "review #21: the new round's question shows the goal's own measure, not another goal's wording",
        "overlap_f1" in ph and "coverage" not in ph and "cheaper hosted" not in ph,
        ph,
    )
    open_(page, "review/other_goal", "Review the outputs")
    phs = [page.get_attribute(i, "placeholder") or "" for i in ("#rv-new-id", "#rv-new-modes")]
    check(
        "review #20: the review's placeholders are not another goal's (no 'summaries', no 'narration')",
        not any(w in " ".join(phs).lower() for w in ("summaries", "narration", "overlong", "truncated")),
        phs,
    )
    # failure-mode lists exist (the review above made one): the form for a new list shows only when it is chosen
    open_(page, "review/tickets_summary", "Review the outputs")
    lists = sel("#rv-modes")
    shown0 = page.locator("#rv-new-id").is_visible()
    page.select_option("#rv-modes", "")
    shown1 = page.locator("#rv-new-id").is_visible()
    check(
        "review #20: the box for a new list's id is not under the select until 'a new list…' is chosen (a list is chosen first)",
        len(lists) >= 2 and not shown0 and shown1,
        (lists, shown0, shown1),
    )
    fields = page.evaluate(
        "() => { const f = [...document.querySelectorAll('main .screen > .field')]; return f.slice(1).map((e, i) => Math.round(e.getBoundingClientRect().top - f[i].getBoundingClientRect().bottom)); }"
    )
    check(
        "review #20: the review form's fields are not touching each other",
        all(g >= 8 for g in fields),
        fields,
    )

    # ── the goal's primary button (#23) ─────────────────────────────────────────────────────────────────────
    primary = {}
    for g in ("tickets_summary", "rail_a", "rail_b"):
        open_(page, f"goal/{g}")
        primary[g] = page.locator("main .actions .btn.primary").first.inner_text().strip()
    check(
        "review #23: a goal's primary button is its next step, not 'Add a dataset' once it has a prepared dataset",
        primary["rail_a"] == "Add a dataset"
        and primary["tickets_summary"] != "Add a dataset"
        and primary["rail_b"] != "Add a dataset",
        primary,
    )

    # ── systems (#19) ───────────────────────────────────────────────────────────────────────────────────────
    open_(page, "systems/tickets_summary", "Choose the systems")
    cells = (
        page.locator("main table")
        .first.locator("tbody tr")
        .evaluate_all(
            "(rows) => rows.map((r) => [r.children[0].innerText.trim(), r.children[1].innerText.trim()])"
        )
    )
    check(
        "review #19: every system's model cell says something (a dash for a system that names no model), as its prompt cell does",
        bool(cells) and all(m for _, m in cells),
        cells,
    )

    # ── models (#17, #18) ───────────────────────────────────────────────────────────────────────────────────
    say(page, "**/api/v1/models", {"command": "model-list", "version": "x", "result": {"models": []}})
    open_(page, "models", "Models in this project")
    none = page.locator("main").inner_text()
    check(
        "review #18: with no model records the Models screen says what a model record is and why a project that ran "
        "models has none, naming the models its systems send",
        "No models yet." not in none and "model record" in none and "fake" in none.lower(),
        none[:500],
    )
    page.unroute_all()
    open_(page, "model-new", "Bring in a model")
    gaps = page.evaluate(
        "() => { const f = [...document.querySelectorAll('main .screen > .field')]; return f.slice(1).map((e, i) => Math.round(e.getBoundingClientRect().top - f[i].getBoundingClientRect().bottom)); }"
    )
    check("review #17: the model form's fields have room between them", all(g >= 8 for g in gaps), gaps)
    check(
        "review #17: the model form's weights have an answer chosen (not neither open nor proprietary)",
        page.locator("input[name=nm-weights]:checked").count() == 1,
        page.locator("input[name=nm-weights]").count(),
    )
    check(
        "review #17: the form's button says what it makes without a placeholder ellipsis ('Make model …' read as cut off)",
        "…" not in page.locator("#nm-save").inner_text(),
        page.locator("#nm-save").inner_text(),
    )
    open_(page, "goal-new", "Set the goal")
    page.fill("#gf-title", "")
    page.fill("#gf-title", "x")
    page.fill("#gf-title", "")
    check(
        "review #17: the goal form's button says what it makes without a placeholder ellipsis",
        "…" not in page.locator("#gf-save").inner_text(),
        page.locator("#gf-save").inner_text(),
    )

    # ── reference sets (#14, #15) and prepare (#13) ────────────────────────────────────────────────────────────
    def children_labelled(b: dict) -> None:
        r = b["result"]
        r["label_sets"] = []
        r["coverage"] = [
            {
                "set": "my_gold",
                "dataset_id": "tk_parent",
                "source": {"kind": "person", "by": "me"},
                "items": ["t01", "t02"],
                "created_at": "2026-11-21T06:51:30Z",
            }
        ]
        r["agreement"] = []

    patch(page, "**/api/v1/datasets/tk_v1/label-sets", children_labelled)
    open_(page, "reference/tk_v1", "Change the reference set")
    part = page.locator("section.part:has(h2:has-text('Its reference sets now'))").inner_text()
    check(
        "review #14: a dataset whose label sets are its parent's does not say 'None yet' beside them: they are listed, from the parent",
        "None yet. Label it here" not in part and "tk_parent/my_gold" in part,
        part[-400:],
    )
    page.unroute_all()

    def long_ids(b: dict) -> None:
        for r in b["result"]["references"]:
            if r["dataset"] == "tk_v1":
                r["reference"] = r["reference"].replace("tk_v1", "tk_v1_validation_split")

    patch(page, "**/api/v1/references", long_ids)
    open_(page, "reference/tk_v1", "Change the reference set")
    tbl = page.locator("section.part:has(h2:has-text('Its reference sets now')) table").first
    lines = tbl.locator("tbody tr").first.locator("td").evaluate_all(f"(tds) => tds.map((t) => ({LINES})(t))")
    tagtop = tbl.locator("tbody tr").first.evaluate(
        "(r) => { const td = r.querySelector('td:first-child'), tag = td.querySelector('.tag'), g = tag.getBoundingClientRect().top, w = document.createTreeWalker(td, NodeFilter.SHOW_TEXT);"
        " while (w.nextNode()) { const t = w.currentNode; if (tag.contains(t)) continue; const i = t.data.search(/\\S/); if (i < 0) continue;"
        " const rg = document.createRange(); rg.setStart(t, i); rg.setEnd(t, i + 1); return Math.abs(g - rg.getBoundingClientRect().top); } return 999; }"
    )
    check(
        "review #15: a reference's date and its counts stay on one line, and its tier badge stays beside its name",
        all(lines[i] == 1 for i in (1, 4, 5)) and tagtop < 4,
        (lines, tagtop),
    )
    phone.set_viewport_size({"width": 390, "height": 844})
    patch(phone, "**/api/v1/references", long_ids)
    open_(phone, "reference/tk_v1", "Change the reference set")
    broken = phone.evaluate(f"({BROKEN})", "section.part table .mono")
    check("review #15: at a phone's width an id is not broken inside a word", not broken, broken)
    phone.unroute_all()

    def rank_chart(route: Any) -> None:
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps(
                {
                    "command": "chart",
                    "version": "x",
                    "result": {
                        "kind": "rank-stability",
                        "title": "tk_v1: how many items the order needs",
                        "caption": "c",
                        "columns": ["n"],
                        "rows": [],
                        "svg": FIG,
                    },
                }
            ),
        )

    page.route("**/api/v1/charts/rank-stability*", rank_chart)
    open_(page, "prepare/tk_v1", "Prepare the dataset")
    card = page.locator(
        "section.part:has(h2:has-text('how many items the order needs')) [data-chart='rank-stability']"
    )
    check(
        "review #13: the prepare screen's chart sits in a card with a heading of its own (the chart's title), not hanging below the last card",
        card.count() == 1,
        page.locator("main").inner_text()[-300:],
    )
    page.unroute_all()

    # ── the judge (#16) ──────────────────────────────────────────────────────────────────────────────────────
    def verdicts(b: dict) -> None:
        r = b["result"]
        r["total"] = 30
        r["rows"] = [
            {
                "set": "s",
                "item": f"b0{i}_library",
                "judge": "gemma_l",
                "pass": "primary",
                "block": 0,
                "arm": "briefs_lead1_v1",
                "position": 1,
                "said": 3.0,
                "why": "It leaves out the cause.",
                "why_status": "given",
            }
            for i in range(1, 4)
        ]

    def problems(b: dict) -> None:
        b["result"].setdefault("validation", {})["problems"] = [
            "no `validation` block naming a committed run"
        ]

    patch(page, "**/api/v1/scorers/*/verdicts*", verdicts)
    patch(page, "**/api/v1/scorers/*", problems)
    open_(page, "judge/tickets_summary", "A judge for this goal")
    sec = page.locator("main").inner_text()
    why_next = page.locator("#why-next")
    check(
        "review #16: the verdicts' pager says what the next page is (higher scores), not just 'Higher'",
        why_next.count() == 1
        and why_next.inner_text().strip() != "Higher"
        and "higher" in why_next.inner_text().lower(),
        why_next.inner_text() if why_next.count() else sec[-300:],
    )
    page.unroute_all()
    agree = page.locator("section.part:has(h2:has-text('Does it agree with people?'))")
    check(
        "review #16: a judge's problems are written with their code words as code, not with raw backticks",
        "`" not in agree.inner_text() and agree.locator("li code").count() >= 1,
        agree.inner_text()[:300],
    )
    phone.set_viewport_size({"width": 390, "height": 844})
    patch(phone, "**/api/v1/scorers/*/verdicts*", verdicts)
    open_(phone, "judge/tickets_summary", "A judge for this goal")
    broken = phone.evaluate(f"({BROKEN})", "table.why td.mono")
    check("review #16: at a phone's width the verdicts' ids are not broken inside a word", not broken, broken)
    phone.unroute_all()
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(U + "judge/tickets_summary")
    patch(page, "**/api/v1/scorers/*/verdicts*", verdicts)
    page.reload()
    page.wait_for_selector("table.why", timeout=30000)
    L.settled(page)
    wrapped = page.evaluate(f"({BROKEN})", "table.why td.mono")
    check(
        "review #16: on a desktop the verdicts' ids are not broken inside a word either", not wrapped, wrapped
    )
    page.unroute_all()

    # ── spacing, placeholders and targets, on every screen of the review (#12, #17, #20, #22, #26, #27) ────────────
    for screen, h1 in (
        ("model-new", "Bring in a model"),
        ("goal-edit/tickets_summary", "The goal"),
        ("review/tickets_summary", "Review the outputs"),
        ("production/tickets_summary", "Learn from production"),
        ("systems/tickets_summary", "Choose the systems"),
        ("reference/tk_v1", "Change the reference set"),
        ("judge/tickets_summary", "A judge for this goal"),
    ):
        open_(page, screen, h1)
        cut, touch = L.cut_placeholders(page), L.touching(page)
        check(f"review: {screen} has no placeholder cut off at a desktop's width", not cut, cut)
        check(f"review: {screen} has no controls touching at a desktop's width", not touch, touch)
        open_(phone, screen, h1)
        cut, touch, small = L.cut_placeholders(phone), L.touching(phone), L.small_targets(phone)
        check(f"review: {screen} has no placeholder cut off at a phone's width", not cut, cut)
        check(f"review: {screen} has no controls touching at a phone's width", not touch, touch)
        check(
            f"review #27: {screen} has every control at least 40 px high at a phone's width",
            not small,
            small[:8],
        )

    gap = lambda pg: pg.evaluate(  # noqa: E731
        "() => [...document.querySelectorAll('main .screen > .field, main .screen > .tablewrap')].map((f) => { const n = f.nextElementSibling; return n && n.matches('.part,section') ? Math.round(n.getBoundingClientRect().top - f.getBoundingClientRect().bottom) : 99; })"
    )
    gaps = {}
    for screen in (
        "heldout/tickets_summary",
        "judge/tickets_summary",
        "production/tickets_summary",
        "prompts/tickets_summary/prompt",
        "reference/tk_v1",
        "settings",
        "review/tickets_summary",
        "study/tickets_summary",
    ):
        open_(page, screen)
        gaps[screen] = min(gap(page) or [99])
    check(
        "review #22: a name field's hint, and a table, have room above the card that follows them",
        all(v >= 10 for v in gaps.values()),
        gaps,
    )

    for screen in ("goal/tickets_summary", "label/tk_v1"):
        open_(phone, screen)
    open_(phone, "goal/tickets_summary")
    bar_goal = phone.evaluate(
        "() => { const r = document.querySelector('.rail'); const s = getComputedStyle(r); return [Math.round(r.getBoundingClientRect().height), s.borderRightWidth]; }"
    )
    open_(phone, "label/tk_v1")
    bar_label = phone.evaluate(
        "() => { const r = document.querySelector('.rail'); const s = getComputedStyle(r); return [Math.round(r.getBoundingClientRect().height), s.borderRightWidth]; }"
    )
    check(
        "review #26: at a phone's width the folded step bar has no line down its right edge, and is as tall on a short page "
        "(a label page) as on a long one",
        bar_goal[1] == "0px" and bar_label[1] == "0px" and abs(bar_goal[0] - bar_label[0]) <= 2,
        (bar_goal, bar_label),
    )

    # ── the long text a phone cuts (#24, #25) ────────────────────────────────────────────────────────────────
    long = "A goal with a long statement. " * 12
    r = evh("goal-set", "rail_b", "--set", f"statement={long}", "--set", f"decision={long}")
    open_(phone, "goal-edit/rail_b", "The goal")
    hidden = phone.evaluate(
        "() => [...document.querySelectorAll('main textarea')].map((t) => t.scrollHeight - t.clientHeight)"
    )
    check(
        "review #24: a text box shows all of its text at a phone's width (it grows with it), not its first lines with the rest cut",
        r.returncode == 0 and hidden and all(h <= 1 for h in hidden),
        (r.stderr[-200:], hidden),
    )
    open_(phone, "prompts/tickets_summary/prompt", "tickets_summary/prompt")
    broken = phone.evaluate(f"({BROKEN})", "main table .mono")
    check(
        "review #25: at a phone's width the run ids of a prompt's versions are not broken inside a word",
        not broken,
        broken,
    )
