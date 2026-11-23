#!/usr/bin/env python3
"""The catalog of this repository's own runs in a real browser: hundreds of arms, not a tutorial's
three. test_inspector_browser.py proves each control on a small project; this proves the pages hold
at the size the deployment serves.

    python tests/test_catalog_real_browser.py --catalog .build/budget-catalog
    make browser-real-check            (builds the catalog first when it is missing)

With the inspector on a free port, over a built catalog:

  - every page a reader reaches from the menu, and a goal, a dataset, an arm and a metric page,
    loads with no console error and no sideways scroll at phone width;
  - the arms page lists as many arms as it says, groups them into as many systems as it says,
    and its open-weights, proprietary and ties-the-leader filters each keep some arms and only
    arms of that kind;
  - the datasets page groups by goal (one heading per goal at least) and the metrics page by role
    (decides, weighs, describes);
  - the activity page lists what moved most against the period before first;
  - "what changed" on the arms page is shorter than one line per arm (a day's rescores are one);
  - the inspector answers the largest comparison the catalog links to, and every arm in it is
    compared or named in a note saying why not (no score on the metric, scored against another
    reference, a repeat).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _slow
import _slow  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

PAGES = (
    "index.html",
    "goals.html",
    "datasets.html",
    "references.html",
    "metrics.html",
    "arms.html",
    "activity.html",
)


def serve(cat: Path, log: Path) -> tuple:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.Popen(
            [
                sys.executable,
                str(HARNESS / "scripts" / "catalog_serve.py"),
                "--port",
                str(port),
                "--build-dir",
                str(cat),
            ],
            cwd=HARNESS,
            stdout=fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    for _ in range(300):
        if "catalog:" in log.read_text():
            break
        if p.poll() is not None:
            raise SystemExit(f"catalog-serve exited:\n{log.read_text()}")
        time.sleep(0.1)
    return p, f"http://127.0.0.1:{port}/{cat.resolve().relative_to(HARNESS).as_posix()}/"


def visible_rows(page, tid: str) -> int:
    return page.evaluate(
        f"""[...document.querySelectorAll('table#{tid} tbody tr')].filter(r=>!r.classList.contains('grouphead')
        &&!r.hidden&&!r.classList.contains('fout')&&!r.classList.contains('pout')).length"""
    )


def captures_table_has_no_empty_columns(html_text: str) -> bool:
    """Check that the captures table has no column where all body cells are empty or '—'.
    Returns True if every column has at least one non-empty, non-dash cell."""

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_captures_table = False
            self.in_thead = False
            self.in_tbody = False
            self.headers = []
            self.rows = []
            self.current_row = []
            self.current_cell_text = []

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            if tag == "table" and attrs_dict.get("id") == "captures":
                self.in_captures_table = True
            elif self.in_captures_table and tag == "thead":
                self.in_thead = True
            elif self.in_captures_table and tag == "tbody":
                self.in_tbody = True
            elif self.in_captures_table and tag in ("th", "td"):
                self.current_cell_text = []

        def handle_data(self, data):
            if self.in_captures_table and (self.in_thead or self.in_tbody):
                self.current_cell_text.append(data.strip())

        def handle_endtag(self, tag):
            if tag == "table" and self.in_captures_table:
                self.in_captures_table = False
            elif tag == "thead" and self.in_thead:
                self.in_thead = False
            elif tag == "tbody" and self.in_tbody:
                self.in_tbody = False
            elif self.in_captures_table and tag == "th" and self.in_thead:
                self.headers.append("".join(self.current_cell_text))
            elif self.in_captures_table and tag == "td" and self.in_tbody:
                cell_content = "".join(self.current_cell_text)
                self.current_row.append(cell_content)
            elif self.in_captures_table and tag == "tr" and self.in_tbody and self.current_row:
                self.rows.append(self.current_row)
                self.current_row = []

    parser = TableParser()
    parser.feed(html_text)

    if not parser.headers or not parser.rows:
        return True  # No table found, consider it OK

    # Check each column
    num_cols = len(parser.headers)
    for col_idx in range(num_cols):
        # Check if all cells in this column are empty or "—"
        all_empty = True
        for row in parser.rows:
            if col_idx < len(row):
                cell_value = row[col_idx].strip()
                if cell_value and cell_value != "—":
                    all_empty = False
                    break
        if all_empty:
            return False  # Found a column with all empty/dash cells
    return True


def check_arms_skip_and_address(browser, base: str) -> None:
    """The arms page's second critique (2026-11-12): the skip link drew accent text on the accent when hovered, and
    a grouping or facet picked was lost on reload."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(base + "arms.html")
    page.wait_for_selector("#arms tbody tr", timeout=30000)
    page.keyboard.press("Tab")
    page.locator("a.skip").hover()
    fg, bg = page.evaluate(
        "(() => { const s = getComputedStyle(document.querySelector('a.skip')); return [s.color, s.backgroundColor]; })()"
    )
    page.keyboard.press("Enter")
    check(
        "arms: the skip link is the first stop, keeps its ink when hovered, and focuses the page without leaving it",
        fg != bg
        and page.evaluate("document.activeElement.id") == "main"
        and page.url.split("#")[0].endswith("arms.html"),
        f"{fg} on {bg}, focus {page.evaluate('document.activeElement.id')}, url {page.url}",
    )
    page.locator('.facet-chips button[data-value="local"]').click()
    page.locator("button[data-group-by=system]").first.click()
    page.goto(page.url)
    # a system group with no local arm keeps its heading hidden, and it can be the first row
    page.wait_for_selector("#arms tbody tr:not([hidden])", timeout=30000)
    pressed = page.evaluate(
        "[...document.querySelectorAll('[aria-pressed=true]')].map(b => b.textContent.trim())"
    )
    check(
        "arms: a grouping and a facet picked are kept in the address and come back on reload",
        "system" in pressed and "local" in pressed and page.locator("#arms tr.grouphead").count() > 1,
        pressed,
    )
    page.close()


def check_arms_default_view(browser, base: str) -> None:
    """The arms page's third critique (owner, 2026-11-12): it opened on every arm alphabetically, no leader in sight,
    and a filter that matched nothing left bare column heads. It opens grouped by dataset, the arms a goal decided on
    first, three a group; nothing left says so, with a way back."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "arms.html")
    page.wait_for_selector("#arms tbody tr", timeout=30000)
    page.wait_for_timeout(300)
    # Each visible row: a group's heading, an arm a goal decided on (leader, recommended, baseline), or another arm.
    rows = page.evaluate(
        "[...document.querySelectorAll('#arms tbody tr')].filter(r => r.offsetParent !== null).map(r =>"
        " r.classList.contains('grouphead') ? 'head' : [...r.querySelectorAll('.role')].some(b =>"
        " b.classList.contains('role-result') || b.textContent.trim() === 'baseline') ? 'decided' : 'arm')"
    )
    groups: list = []
    for x in rows:
        if x == "head":
            groups.append([])
        elif groups:
            groups[-1].append(x)
    check(
        "arms: opens grouped by dataset, each group at most three rows, a decided arm never after an undecided one",
        rows[:1] == ["head"]
        and all(len(g) <= 3 for g in groups)
        and not any(a == "arm" and b == "decided" for g in groups for a, b in zip(g, g[1:]))
        and any("decided" in g for g in groups),
        groups[:6],
    )
    page.fill("input[data-filter=arms]", "zzzz-no-arm")
    page.wait_for_timeout(200)
    empty = page.locator("#arms tr.emptyrow")
    check(
        "arms: a filter that matches nothing says so, and its button clears it",
        empty.count() == 1 and "No arm matches" in empty.inner_text(),
        empty.inner_text() if empty.count() else "no empty row",
    )
    page.locator("#arms [data-clearall]").click()
    page.wait_for_timeout(200)
    check(
        "arms: ... and after clearing, the rows are back",
        page.locator("#arms tr.emptyrow").count() == 0
        and page.input_value("input[data-filter=arms]") == ""
        and not errors,
        errors[:2],
    )
    page.close()


def check_arms_sort_and_kinds(browser, base: str) -> None:
    """The arms page's critique (2026-11-12): sorting a grouped table threw on a group's heading row; a cost sorted as
    text, blanks first; no row said what it was scored against."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "arms.html")
    page.wait_for_selector("#arms tbody tr", timeout=30000)
    page.locator("button[data-group-by=set]").first.click()
    page.locator("#arms th .sortbtn", has_text="cost").click()
    page.wait_for_timeout(300)
    check(
        "arms: a grouped table sorts by a column without an error, its groups kept",
        not errors and page.locator("#arms tr.grouphead").count() > 1,
        errors[:2],
    )
    page.goto(base + "arms.html?group=none")  # the page opens grouped by dataset; this is the ungrouped sort
    page.wait_for_selector("#arms tbody tr", timeout=30000)
    head = page.locator("#arms th .sortbtn", has_text="cost")
    head.click()
    head.click()  # descending: a blank must still come last
    page.wait_for_timeout(300)
    vals = page.evaluate(
        "[...document.querySelectorAll('#arms tbody tr')].filter(r => !r.hidden).map(r => (r.cells[7].querySelector('[data-v]') || {dataset: {v: ''}}).dataset.v)"
    )
    shown = [v for v in vals if v != ""]
    check(
        "arms: cost sorts by its value, descending, every blank after every number",
        bool(shown)
        and all(float(a) >= float(b) for a, b in zip(shown, shown[1:]))
        and "" not in vals[: len(shown)],
        vals[:12],
    )
    kinds = page.evaluate(
        "['t-judged','t-silver'].map(k => document.querySelectorAll('#arms tbody tr.' + k).length)"
    )
    check(
        "arms: every row says what it is measured against (the row key, judged and silver rows tinted, the reference named)",
        page.locator(".rowkey").count() == 1
        and all(n > 0 for n in kinds)
        and page.locator("#arms tbody td", has_text="measured · against").count() > 0,
        kinds,
    )
    page.close()


def check_home_tiles(browser, base: str) -> None:
    """At 1400 px the ten period tiles share one row, each about 104 px wide: a number must stay on one line there,
    the ones the catalog shows and the widest a small project has (a bill of $0.1992, 190,334 tokens)."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(base + "index.html")
    page.wait_for_selector("#period .tile b", timeout=30000)
    page.wait_for_timeout(500)
    lines = """() => [...document.querySelectorAll('#period .tile b')].map(b => {
      const r = document.createRange(); r.selectNodeContents(b);
      const visible = [...r.getClientRects()].filter(x => x.width > 0);
      return {text: b.innerText, lines: new Set(visible.map(x => Math.round(x.top))).size,
              over: b.scrollWidth > b.parentElement.clientWidth}; })"""
    built = page.evaluate(lines)
    check(
        "1400 px: every period tile's number is on one line",
        bool(built) and all(t["lines"] <= 1 for t in built),
        str([t for t in built if t["lines"] > 1]),
    )
    page.evaluate(
        """() => { const w = ['$0.1992', '190,334', '$1.2345', '999,999'];
          [...document.querySelectorAll('#period .tile b')].forEach((b, i) => { b.textContent = w[i % w.length]; }); }"""
    )
    wide = page.evaluate(lines)
    check(
        "1400 px: and so are the widest numbers a small project has ($0.1992, 190,334, $1.2345, 999,999)",
        all(t["lines"] <= 1 for t in wide),
        str([t for t in wide if t["lines"] > 1]),
    )
    page.close()


def check_gutters(browser, base: str, sub: list) -> None:
    """At 1400 px the goal, dataset, arm and metric pages start their content at the same left edge (scenario 080c U6:
    the dataset pages ran edge to edge, 24 px, the others sat in a 134 px gutter); the arms index too (scenario 080d: it ran 24 px from the edges while every other page sat in 134 px; one rule now: the
    content column is the page's .wrap, a table wider than it scrolls inside its own box)."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    lefts = {}
    for path in ("arms.html", *sub):
        page.goto(base + path)
        page.wait_for_selector("h1", timeout=30000)
        lefts[path.split("/")[0].split(".")[0]] = page.evaluate(
            "() => Math.round(document.querySelector('main h1, h1').getBoundingClientRect().left)"
        )
    check(
        "1400 px: the arms index, goal, dataset, arm and metric pages share one left gutter",
        len(set(lefts.values())) == 1,
        str(lefts),
    )
    page.goto(base + "d/cnn_dailymail_200.html")
    page.wait_for_selector("table#arms tbody tr", timeout=30000)
    wrapped = page.evaluate(
        """() => [...document.querySelectorAll('table#arms td')].filter(td => /^(\\$|p50)/.test(td.innerText.trim()))
          .map(td => { const r = document.createRange(); r.selectNodeContents(td);
            return {text: td.innerText.trim(), lines: new Set([...r.getClientRects()].filter(x => x.width > 0).map(x => Math.round(x.top))).size}; })
          .filter(x => x.lines > 1)"""
    )
    check(
        "1400 px: a dataset page's cost and speed cells each sit on one line (the narrower gutter must not wrap them)",
        not wrapped,
        str(wrapped[:3]),
    )
    page.close()


#: Every unrotated text of every chart of a page, as the browser drew it: [svg index, text, left, top, right, bottom].
CHART_TEXTS = """() => [...document.querySelectorAll('figure.chart svg')].flatMap((svg, k) => {
  const box = svg.getBoundingClientRect();
  return [...svg.querySelectorAll('text')].filter(t => !t.getAttribute('transform')
      && getComputedStyle(t).display !== 'none' && (t.textContent || '').trim())
    .map(t => { const r = t.getBoundingClientRect();
      return [k, t.textContent.trim().slice(0, 40), r.left, r.top, r.right, r.bottom, box.left, box.top, box.right, box.bottom]; }); })"""

#: Each id link and code in a table, with the places its lines break: a break not after _ / - . is mid-word.
ID_BREAKS = """() => [...document.querySelectorAll('main table a.cell-link, main table td code')].flatMap(a => {
  const lines = []; let top = null, cur = '';
  const w = document.createTreeWalker(a, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) { const n = w.currentNode;
    for (let i = 0; i < n.length; i++) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 1);
      const q = r.getClientRects()[0]; if (!q) continue;
      if (top !== null && q.top > top + 2) { lines.push(cur); cur = ''; }
      top = q.top; cur += n.data[i]; } }
  lines.push(cur);
  return lines.slice(0, -1).some(l => !/[_\\/.\\-]$/.test(l.trimEnd()) && !/\\s$/.test(l)) ? [lines.join(' | ')] : []; })"""


def check_display(browser, base: str, cat: Path) -> None:
    """How the catalog reads (scenario 080d review): no chart text over another or cut at any width, an id breaks at a
    separator and never inside a word, a section's heading has room above what it heads, the code font is the page's own,
    a row linked by its address is marked, and the jump links of the arms page land below the bar."""
    pages = [
        p.relative_to(cat).as_posix() for sub in ("g", "d", "m") for p in sorted((cat / sub).glob("*.html"))
    ][:40]
    for width in (1400, 390):
        page = browser.new_page(viewport={"width": width, "height": 900})
        bad_over, bad_cut, charts, bad_ids = [], [], 0, []
        for path in pages:
            page.goto(base + path)
            page.wait_for_selector("main", timeout=30000)
            page.wait_for_timeout(150)
            texts = page.evaluate(CHART_TEXTS)
            charts += len({t[0] for t in texts})
            for i, a in enumerate(texts):
                if a[2] < a[6] - 1 or a[4] > a[8] + 1 or a[3] < a[7] - 1 or a[5] > a[9] + 1:
                    bad_cut.append((path, a[1]))
                for b in texts[i + 1 :]:
                    if (
                        a[0] == b[0]
                        and a[2] < b[4] + 1
                        and b[2] < a[4] + 1
                        and a[3] < b[5] - 2
                        and b[3] < a[5] - 2
                    ):
                        bad_over.append((path, a[1], b[1]))
            bad_ids += [(path, x) for x in page.evaluate(ID_BREAKS)]
        check(
            f"{width} px: no chart text drawn over another, on {len(pages)} pages ({charts} charts)",
            charts > 0 and not bad_over,
            str(bad_over[:4]),
        )
        check(f"{width} px: no chart text cut off by its drawing's edge", not bad_cut, str(bad_cut[:4]))
        for path in ("goals.html", "datasets.html", "labels.html", "metrics.html", "arms.html"):
            page.goto(base + path)
            page.wait_for_selector("main", timeout=30000)
            bad_ids += [(path, x) for x in page.evaluate(ID_BREAKS)]
        check(
            f"{width} px: an id in a table breaks after _ / - . and never inside a word",
            not bad_ids,
            str(bad_ids[:4]),
        )
        page.close()
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    broken = []
    for path in ("arms.html", *pages):
        page.goto(base + path)
        page.wait_for_selector("main", timeout=30000)
        broken += [
            (path, x)
            for x in page.evaluate(
                """() => [...document.querySelectorAll('main table td')].filter(e => e.offsetParent
                    && /^(\\$[0-9.]+( · [0-9,]+ tok)?|p50 [0-9.,]+ · p95 [0-9.,]+ ms|[0-9.,]+ ms)$/.test(e.innerText.trim().split('\\n')[0])).map(e => {
                  const r = document.createRange(); r.selectNodeContents(e);
                  return [e.innerText.trim(), new Set([...r.getClientRects()].filter(x => x.width > 0).map(x => Math.round(x.top))).size]; })
                  .filter(x => x[1] > 1)"""
            )
        ]
    check(
        "1400 px: a cost, speed or axis cell on the arms, goal, dataset and metric pages sits on one line",
        not broken,
        str(broken[:4]),
    )
    page.goto(base + "captures.html")
    page.wait_for_selector("main", timeout=30000)
    fonts = page.evaluate(
        """() => { const f = s => { const e = document.querySelector(s); return e ? getComputedStyle(e).fontFamily : null; };
        return [f('main code'), f('h2.eyebrow')]; }"""
    )
    check(
        "code is set in the catalog's mono, the heading's, not the browser's generic monospace",
        fonts[0] is not None and fonts[0] == fonts[1],
        str(fonts),
    )
    gaps = []
    for path in ("goals.html", "activity.html", *pages[:2]):
        page.goto(base + path)
        page.wait_for_selector("main", timeout=30000)
        gaps += [
            (path, g)
            for g in page.evaluate(
                """() => [...document.querySelectorAll('section.block h2.eyebrow')].map(h => {
                  let n = h.nextElementSibling; while (n && n.offsetHeight === 0) n = n.nextElementSibling;
                  return n ? Math.round(n.getBoundingClientRect().top - h.getBoundingClientRect().bottom) : 99; })"""
            )
            if g < 12
        ]
    check(
        "a section's eyebrow has at least 12 px above what it heads (goals, activity, a goal, a dataset)",
        not gaps,
        str(gaps[:4]),
    )
    anchors = re.findall(
        r'href="(labels\.html#set-[^"]+)"',
        "".join(p.read_text(encoding="utf-8") for p in cat.rglob("*.html")),
    )
    if anchors:
        page.goto(base + anchors[0])
        page.wait_for_selector("tr:has(:target)", timeout=30000)
        marked = page.evaluate(
            """() => { const r = document.querySelector('tr:has(:target)'); const c = getComputedStyle(r.cells[0]).backgroundColor;
            return [c, r.getBoundingClientRect().top]; }"""
        )
        check(
            "a label set's address (labels.html#set-...) marks its row and scrolls it into view",
            marked[0] not in ("rgba(0, 0, 0, 0)", "transparent") and 0 <= marked[1] < 900,
            str(marked),
        )
    page.goto(base + "arms.html#bygoal")
    page.wait_for_selector("table#arms tbody tr", timeout=30000)
    page.wait_for_timeout(300)
    landed = page.evaluate(
        """() => { const h = document.getElementById('bygoal'); const bar = document.querySelector('.bar').getBoundingClientRect();
        return [h ? h.getBoundingClientRect().top : null, bar.bottom,
          [...document.querySelectorAll('#arms tr.grouphead')].filter(r => !r.hidden && !r.textContent.trim()).length]; }"""
    )
    check(
        "arms page: a jump link (#bygoal) lands below the bar, and no group heading is empty (a full-page screenshot "
        "taken after the jump shows the sticky head and headings where they stuck, not where the page has them)",
        landed[0] is not None and landed[0] >= landed[1] - 1 and landed[2] == 0,
        str(landed),
    )
    page.close()


def drive(cat: Path, base: str) -> None:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    sub = [
        next(iter(sorted((cat / "g").glob("*.html")))).relative_to(cat).as_posix(),
        next(iter(sorted((cat / "d").glob("*.html")))).relative_to(cat).as_posix(),
        next(iter(sorted((cat / "a").glob("*.html")))).relative_to(cat).as_posix(),
        next(iter(sorted((cat / "m").glob("*.html")))).relative_to(cat).as_posix(),
    ]
    with sync_playwright() as pw:
        browser = _slow.launch(pw)
        errors: list = []
        phone = browser.new_page(viewport={"width": 390, "height": 844})
        phone.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        phone.on("pageerror", lambda e: errors.append(str(e)))
        for path in (*PAGES, *sub):
            phone.goto(base + path)
            phone.wait_for_selector("main", timeout=30000)
            wide = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(f"phone width: no sideways scroll on {path}", wide <= 1, f"{wide}px too wide")

        # At phone width a dataset id breaks after an underscore, never inside a word ("orrery_tr / iage_v1").
        phone.goto(base + "datasets.html")
        phone.wait_for_selector("table#datasets tbody tr", timeout=30000)
        broken = phone.evaluate(
            """() => [...document.querySelectorAll('table#datasets tbody tr td:first-child > a.cell-link')].flatMap(a => {
              const lines = []; let top = null, cur = '';
              const w = document.createTreeWalker(a, NodeFilter.SHOW_TEXT);
              while (w.nextNode()) { const n = w.currentNode;
                for (let i = 0; i < n.length; i++) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 1);
                  const t = r.getBoundingClientRect().top; if (top !== null && t > top + 2) { lines.push(cur); cur = ''; }
                  top = t; cur += n.data[i]; } }
              lines.push(cur);
              return lines.slice(0, -1).some(l => !l.endsWith('_')) ? [lines.join(' | ')] : []; })"""
        )
        check(
            "phone width: dataset ids break after an underscore, never inside a word",
            not broken,
            str(broken[:3]),
        )

        check_display(browser, base, cat)
        check_home_tiles(browser, base)
        check_gutters(browser, base, sub)
        check_arms_sort_and_kinds(browser, base)
        check_arms_default_view(browser, base)
        check_arms_skip_and_address(browser, base)

        page = browser.new_page(viewport={"width": 1280, "height": 900})
        # The pages count their default period (the last 14 days) from the viewer's date, so the data's own dates age
        # out of it: pinned to a day the committed runs were inside it, or the figures below move with the calendar.
        page.clock.set_fixed_time("2026-11-15T12:00:00Z")
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # The label tables at desktop width: long set ids wrap, so the columns that say something (promoted, the
        # agreement counts) are on screen, not behind a sideways scroll.
        labelled = [p.relative_to(cat).as_posix() for p in sorted((cat / "d").glob("*.html"))]
        labelled = [p for p in labelled if 'id="agree-' in (cat / p).read_text(encoding="utf-8")][:3]
        for path in ("labels.html", *labelled):
            page.goto(base + path)
            page.wait_for_selector("main", timeout=30000)
            over = page.evaluate(
                """[...document.querySelectorAll('table#labelsets, table[id^="agree-"], table[id^="labels-"]')]
                .map(t => [t.id, t.scrollWidth - t.closest('.scroll-x').clientWidth]).filter(x => x[1] > 1)"""
            )
            check(
                f"desktop width: the label tables on {path} fit, nothing behind a sideways scroll",
                not over,
                str(over),
            )

        # The answer is never the column that scrolls off: goals at a glance, the goals page, and the triage goal's
        # arms (its 45-character ids and its limit's head) fit at desktop width.
        for path, sel in (
            ("index.html", "table#glance"),
            ("goals.html", "table#goals"),
            ("g/triage_orrery.html", "table[id^='ans']"),
        ):
            page.goto(base + path)
            page.wait_for_selector("main", timeout=30000)
            over = page.evaluate(
                f"""[...document.querySelectorAll("{sel}")]
                .map(t => [t.id, t.scrollWidth - t.closest('.scroll-x').clientWidth]).filter(x => x[1] > 1)"""
            )
            check(
                f"desktop width: {sel} on {path} fits, nothing behind a sideways scroll", not over, str(over)
            )
            # Fitting is not enough: another machine's fonts widen the text (CI's goals table was 26 px over where
            # this one had none to spare). At its narrowest, every cell wrapped as far as it goes, the table must
            # leave 8% of its box free.
            tight = page.evaluate(
                f"""[...document.querySelectorAll("{sel}")].map(t => {{
                  const box = t.closest('.scroll-x').clientWidth; t.style.width = 'min-content';
                  const least = t.getBoundingClientRect().width; t.style.width = '';
                  return [t.id, Math.round(least), box]; }}).filter(x => x[1] > x[2] * 0.92)"""
            )
            check(
                f"desktop width: {sel} on {path} keeps 8% slack at its narrowest (fonts differ between machines)",
                not tight,
                f"[id, narrowest, box]: {tight}",
            )
            narrow = browser.new_page(viewport={"width": 1100, "height": 900})
            narrow.goto(base + path)
            narrow.wait_for_selector("main", timeout=30000)
            over = narrow.evaluate(
                f"""[...document.querySelectorAll("{sel}")]
                .map(t => [t.id, t.scrollWidth - t.closest('.scroll-x').clientWidth]).filter(x => x[1] > 1)"""
            )
            narrow.close()
            check(f"1100 px width: {sel} on {path} fits", not over, str(over))

        # The arms page at full size: all time, every row shown.
        page.goto(base + "arms.html#pall")
        page.wait_for_selector("table#arms")
        hero = page.locator(".hero").first.inner_text()
        m = re.search(r"(\d+) arms from (\d+) systems", hero)
        n_arms, n_cfg = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        check(
            f"arms page: the table lists the {n_arms} arms it says",
            # the page opens grouped by dataset: a group's heading is a row of the table, not an arm
            n_arms > 100 and page.locator("table#arms tbody tr:not(.grouphead)").count() == n_arms,
            f"hero {hero[:80]!r}, rows {page.locator('table#arms tbody tr:not(.grouphead)').count()}",
        )
        page.click('.group-chips[data-for="arms"] [data-group-by="system"]')
        heads = page.locator("table#arms tr.grouphead").count()
        check(
            f"arms page: grouped by system, one heading per system ({n_cfg})",
            heads == n_cfg,
            f"{heads} headings",
        )
        page.click('.group-chips[data-for="arms"] [data-group-by=""]')
        for facet, value, attr in (
            ("weights", "open", "weights"),
            ("weights", "proprietary", "weights"),
            ("quality", "a contender", "quality"),
        ):
            chip = page.locator(f'.facet-chips[data-for="arms"] [data-facet="{facet}"][data-value="{value}"]')
            chip.click()
            kept = page.evaluate(
                """([a])=>[...document.querySelectorAll('table#arms tbody tr')].filter(r=>!r.classList.contains('grouphead')
                &&!r.classList.contains('fout')).map(r=>r.dataset[a])""",
                [attr],
            )
            check(
                f"arms page: the {value} filter keeps some arms, all of them {value}",
                bool(kept) and len(kept) < n_arms and all(k == value for k in kept),
                f"{len(kept)} kept, {sorted(set(kept))}",
            )
            chip.click()
        feed = page.locator("table#armfeed tbody tr").count()
        check(
            f"arms page: what changed is shorter than one line per arm ({feed} lines, {n_arms} arms)",
            0 < feed < n_arms,
        )

        page.goto(base + "datasets.html#pall")
        page.click('.group-chips[data-for="datasets"] [data-group-by="goal"]')
        n_goals = len(list((cat / "g").glob("*.html")))
        goal_heads = page.locator("table#datasets tr.grouphead").all_inner_texts()
        check(
            f"datasets page: grouped by goal, a heading for each of the {n_goals} goals",
            len(goal_heads) >= n_goals,
            " | ".join(goal_heads),
        )
        page.goto(base + "metrics.html#pall")
        page.click('.group-chips[data-for="metrics"] [data-group-by="role"]')
        roles = {t.split()[1] for t in page.locator("table#metrics tr.grouphead").all_inner_texts()}
        check(
            "metrics page: grouped by role, decides and describes among them",
            {"decides", "describes"} <= roles <= {"decides", "weighs", "describes"},
            str(roles),
        )

        page.goto(base + "activity.html#p90d")
        page.wait_for_selector("table#actarms")
        moved = page.evaluate(
            """[...document.querySelectorAll('table#actarms tbody tr [data-flow="runs"]')].slice(0,10)
            .map(c=>c.dataset.prev===undefined?null:Math.abs(+c.dataset.v-(+c.dataset.prev)))"""
        )
        nums = [x for x in moved if x is not None]
        check(
            "activity page: what moved most against the period before comes first",
            len(nums) >= 2 and nums == sorted(nums, reverse=True),
            str(moved),
        )

        links = set()
        for f in cat.rglob("*.html"):
            for href in re.findall(r'href="(?:\.\./)*inspect\.html\?([^"]+)"', f.read_text(encoding="utf-8")):
                links.add(href.replace("&amp;", "&"))
        # The largest comparison, the same one every run (several tie on size).
        largest = max(sorted(links), key=lambda q: q.count(","), default="")
        page.goto(base + "inspect.html?" + largest)
        page.wait_for_selector("span.chip.v-better, span.chip.v-worse, span.chip.v-none", timeout=120000)
        page.wait_for_load_state("networkidle")
        ids = [r.rsplit("/", 1)[-1] for r in largest.split("runs=", 1)[-1].split("&", 1)[0].split(",")]
        # A verdict row shows an arm by what it does not share with the others; its full name is the
        # row's tooltip. The picker above, folded, names none of them.
        text = page.locator("#app").inner_text() + " ".join(
            page.eval_on_selector_all("#app [title]", "els => els.map(e => e.title)")
        )
        unnamed = [i for i in ids if i not in text]
        rows = page.locator("table.data").first.locator("tbody tr").count()
        check(
            f"inspector: the largest comparison the catalog links to ({len(ids)} arms) answers; every arm is "
            f"compared ({rows} verdict rows) or named in a note saying why not",
            rows > 0 and not unnamed,
            f"not named: {unnamed[:5]}",
        )
        # The inspector's charts: no name cut with an ellipsis or at the drawing's edge, none over another or over a cross
        # (scenario 080d inspector review: "intents_llama_scout_v1 ×" lost its 3, labels covered another arm's cross).
        page.wait_for_selector("#scatterbox svg, figure.chart svg", timeout=60000)
        names = page.evaluate(
            """() => [...document.querySelectorAll('#app figure.chart svg')].flatMap((svg, k) => {
              const b = svg.getBoundingClientRect();
              return [...svg.querySelectorAll('text.cl, text.rl')].map(t => { const r = t.getBoundingClientRect();
                return [k, t.textContent.trim(), r.left, r.top, r.right, r.bottom, b.left, b.top, b.right, b.bottom]; }); })"""
        )
        crosses = page.evaluate(
            """() => [...document.querySelectorAll('#app figure.chart svg')].flatMap((svg, k) =>
              [...svg.querySelectorAll('.centroid path')].map(p => { const r = p.getBoundingClientRect(); return [k, r.left, r.top, r.right, r.bottom]; }))"""
        )
        bad = [n[1] for n in names if "…" in n[1] or n[2] < n[6] - 1 or n[4] > n[8] + 1]
        bad += [
            f"{a[1]} over {b[1]} {[round(v) for v in a[2:6] + b[2:6]]}"
            for i, a in enumerate(names)
            for b in names[i + 1 :]
            if a[0] == b[0] and a[2] < b[4] and b[2] < a[4] and a[3] < b[5] - 1 and b[3] < a[5] - 1
        ]
        bad += [
            f"{n[1]} over a cross"
            for n in names
            if n[1]
            and any(
                c[0] == n[0] and n[2] < c[3] - 1 and c[1] + 1 < n[4] and n[3] < c[4] - 1 and c[2] + 1 < n[5]
                for c in crosses
                if not (abs((c[1] + c[3]) / 2 - n[2]) < 14)  # its own cross sits at its label's start
            )
        ]
        check(
            "inspector: chart names are whole, none over another name or another arm's cross",
            not bad,
            str(bad[:4]),
        )
        # Every system on the arms page has the day it was first run, as the home page's systems tile counts them:
        # an undated row (a system whose runs were all re-parsed) never counts as new there.
        ct = (cat / "arms.html").read_text(encoding="utf-8")
        ct = ct[ct.index('<table id="systems"') :]
        ct = ct[: ct.index("</table>")]
        undated = re.findall(r'<tr data-key="(c:[^"]+)"(?![^>]*data-made)', ct)
        check(
            "arms page: every system row is dated (its first run, any kind)",
            not undated,
            ", ".join(undated[:5]),
        )

        # Runs re-scored or re-parsed in place (Few-NERD's, SciFact's) are the runs that were measured: their runs and
        # spend count in every period figure, dated when they were measured, once each. A copy (judged, re-scored,
        # silver, adjudicated) keeps the run's id too and is never counted: counting them tripled the spend.
        rows_js = (cat / "datasets-rows.js").read_text(encoding="utf-8")
        per = json.loads(rows_js[rows_js.index("{") : rows_js.rindex("}") + 1])
        counted = {
            d: (
                len(per.get(d, {}).get("runs") or []),
                round(sum(x[1] for x in per.get(d, {}).get("usd") or []), 2),
            )
            for d in ("few_nerd_280", "scifact_200", "ag_news_200")
        }
        check(
            "datasets: runs re-scored in place count once in the period figures, copies never (the run records' "
            "28 runs $2.61, 26 runs $2.97, 33 runs $0.58)",
            counted == {"few_nerd_280": (28, 2.61), "scifact_200": (26, 2.97), "ag_news_200": (33, 0.58)},
            str(counted),
        )

        # One recommendation per goal and dataset, from the goal's own measure (judged groups are shown, never
        # recommend), and a round's best read as the goal decides: on gold, never the arm that wrote silver.
        cnn = (cat / "g" / "news_summary_cnn.html").read_text(encoding="utf-8").replace("<wbr>", "")
        recs = sorted(set(re.findall(r"Recommended: <b><a [^>]*>([^<]+)</a>", cnn)))
        best = re.findall(r"best</small> <a class=\"cell-link\"[^>]*>([a-z0-9_]+)</a>", cnn)
        check(
            "CNN goal page: one recommendation (gold's), and round r1's best is gold's leader, not silver's author",
            recs == ["cnn_bart_l_v1"] and best[:1] == ["cnn_bart_l_v1"],
            f"recommended {recs}; best {best[:3]}",
        )

        # The triage goal page names its scorer once, not after each of 80 arms (the baseline's gap sentence too), and
        # prints the r3 conclusion once. It once listed 51 contenders twice; at 65 items the non-inferiority test now
        # admits none ("too few ... needs 100"), so the page says none, and the folding of a long list is checked on a
        # decision made for it (test_why_lines.py).
        page.goto(base + "g/triage_orrery.html")
        seen = page.locator("main").inner_text()
        concl = "Onboarding was the fix round 1 needed"
        check(
            "triage goal page: the scorer named once, no contenders said as none, round r3's conclusion shown once",
            "rescored 5f2c057c" not in seen
            and "re-score by scorer 5f2c057c" in seen
            and "Contenders beside it" in seen
            and "): none." in seen
            and seen.count(concl) == 1,
            f"per-arm hashes {seen.count('rescored 5f2c057c')}, conclusion shown {seen.count(concl)}×",
        )

        # Small things read as words: an arm's rounds as sentences, a probe's yes or no (never "reasons False"),
        # what α and MASI mean beside them, and the showcase dataset's "what's inside" filled.
        arm_p = (cat / "a" / "runs-cnn_dailymail_200-cnn_bart_l_v1.html").read_text(encoding="utf-8")
        raw = sorted(
            f.name
            for f in (cat / "models").glob("*.html")
            if re.search(r"<code>[^<]*\b(True|False)\b", f.read_text(encoding="utf-8"))
        )
        tri = (cat / "d" / "orrery_triage_v1_labelled.html").read_text(encoding="utf-8")
        check(
            "words: rounds as sentences, no raw booleans on model pages, α and MASI explained, triage profiled",
            "Round <b>r1</b> of" in arm_p
            and "in play" not in arm_p
            and not raw
            and "MASI distance" in tri
            and "A profile is optional" not in tri,
            f"raw booleans on {raw[:3]}",
        )

        # The datasets table says what a period's spend was when no run was (CNN: "0 runs" beside "$13.09", the
        # judges' calls), a rise past doubling as a multiple ("▲ 3089%"), and "—" where a row had no runs to draw.
        page.goto(base + "datasets.html")
        page.wait_for_selector("table#datasets tbody tr", timeout=30000)
        seen = page.evaluate(
            """() => { const rows = [...document.querySelectorAll('table#datasets tbody tr')];
              const cell = (r, f) => (r.querySelector(`[data-flow=${f}]`) || {}).innerText || '';
              const cnn = rows.find(r => r.dataset.key === 'cnn_dailymail_200');
              return {cnn: cell(cnn, 'usd'), pct: rows.map(r => cell(r, 'usd') + ' ' + cell(r, 'runs')).join(' '),
                      blank: rows.filter(r => { const c = r.querySelector('[data-flow=line]');
                        return c && !c.querySelector('svg') && !c.innerText.trim(); }).length}; }"""
        )
        caps = (cat / "captures.html").read_text(encoding="utf-8")
        check(
            "datasets: judging spend said, no ▲ past 100%, no blank runs-per-day cell; captures without an empty column",
            "judging" in seen["cnn"]
            and not re.search(r"▲ \d{3,}%", seen["pct"])
            and seen["blank"] == 0
            and captures_table_has_no_empty_columns(caps),
            str(seen)[:300],
        )

        # The goal pages' charts: no name drawn over another (33 pairs, the names spaced 12 units on 14-unit boxes),
        # no "$-1" axis for a cost every arm shares, and a strip without the arm scored against what it wrote.
        crossed, minus = {}, []
        for gp in sorted((cat / "g").glob("*.html")):
            page.goto(base + "g/" + gp.name)
            page.wait_for_selector("main", timeout=30000)
            n = page.evaluate(
                """() => [...document.querySelectorAll('figure.chart svg')].reduce((s, svg) => {
                  const b = [...svg.querySelectorAll('text.name')].map(t => t.getBBox());
                  for (let i = 0; i < b.length; i++) for (let j = i + 1; j < b.length; j++)
                    if (b[i].x + 1 < b[j].x + b[j].width && b[j].x + 1 < b[i].x + b[i].width
                        && b[i].y + 1 < b[j].y + b[j].height && b[j].y + 1 < b[i].y + b[i].height) s++;
                  return s; }, 0)"""
            )
            if n:
                crossed[gp.stem] = n
            if "$-1" in gp.read_text(encoding="utf-8"):
                minus.append(gp.stem)
        cov = (cat / "m" / "coverage.html").read_text(encoding="utf-8")
        check(
            "goal pages' charts: no name over another, no $-1 axis; the coverage strip leaves out silver's author",
            not crossed and not minus and "Not drawn: cnn_anthropic_l_v2" in cov,
            f"overlapping names {crossed}; $-1 on {minus}",
        )

        # How to read a goal's groups and its strategy are said once a page (CNN printed them 3 and 6 times).
        twice = {
            gp.stem: (n1, n2)
            for gp in sorted((cat / "g").glob("*.html"))
            for t in [gp.read_text(encoding="utf-8")]
            for n1, n2 in [
                (
                    t.count("over each arm&#x27;s") + t.count("over each arm's"),
                    t.count("The rule recommends;"),
                )
            ]
            if n1 > 1 or n2 > 1
        }
        check("goal pages: the groups' explanation and the strategy said once each", not twice, str(twice))

        # "Test every arm in this group against its leader" leaves out the arms a round retired, and says how many; a
        # group whose arms all have too few items says so on its heading (it stays listed, never recommended).
        from evaluation_harness.catalog_build import slug  # noqa: PLC0415

        retired_in_link, unmarked, author_tested = [], [], []
        for gp in sorted((cat / "g").glob("*.html")):
            for grp in gp.read_text(encoding="utf-8").split('<h3 class="sub">')[1:]:
                head, _, rest = grp.partition("</h3>")
                grp_html = rest.split('<h3 class="sub">')[0]
                gone = {
                    m
                    for row in re.findall(r'<tr class="[^"]*t-retired[^"]*".*?</tr>', grp_html, re.S)
                    for m in re.findall(r'href="\.\./a/([^"]+)\.html"', row)
                }
                # The arm that wrote the reference is scored against its own outputs: never tested against the
                # leader, neither in the group's link nor from its own row (the 0.8.0 newcomer run).
                author_rows = re.findall(r'<tr class="[^"]*t-author[^"]*".*?</tr>', grp_html, re.S)
                authors = {m for row in author_rows for m in re.findall(r'href="\.\./a/([^"]+)\.html"', row)}
                author_tested += [f"{gp.stem}: its row" for row in author_rows if "test vs leader" in row]
                btn = re.search(
                    r'<a class="btn" href="\.\./inspect\.html\?runs=([^&"]+)[^"]*">Test every arm', grp_html
                )
                if btn:
                    ids = [slug(x) for x in btn.group(1).split(",")]
                    retired_in_link += [f"{gp.stem}: {x}" for x in ids if x in gone]
                    author_tested += [f"{gp.stem}: {x}" for x in ids if x in authors]
                    if gone and " left out)" not in grp_html.split("</p>")[0]:
                        unmarked.append(f"{gp.stem}: link does not say retired arms are left out")
                if "No arm is eligible: n " in grp_html and "below the goal" not in head:
                    unmarked.append(f"{gp.stem}: {re.sub('<[^>]+>', '', head)[:60]}")
        check(
            "goal pages: the leader link leaves out retired arms (and says so); a group below min_items says so",
            not retired_in_link and not unmarked,
            f"retired arms in a link {retired_in_link[:4]}; unmarked short groups {unmarked[:4]}",
        )
        check(
            "goal pages: the arm that wrote the reference is never tested against the leader (link or row)",
            not author_tested,
            author_tested[:6],
        )

        # A dataset page opens on the measure its goal decides on, and never inspects two judges' scores as one.
        firsts = {}
        for d in ("orrery_triage_v1_labelled", "summeval_100"):
            dp = (cat / "d" / f"{d}.html").read_text(encoding="utf-8")
            firsts[d] = (
                re.search(r'href="\.\./m/([a-z_0-9]+)\.html"', dp[dp.index("<tbody") :]) or [None, ""]
            )[1]
        cnn_d = (cat / "d" / "cnn_dailymail_200.html").read_text(encoding="utf-8")
        check(
            "dataset pages: the deciding measure's arms first; one inspect button per judging pass",
            firsts == {"orrery_triage_v1_labelled": "triage_cost", "summeval_100": "tau"}
            and "Inspect the 58 arms" not in cnn_d
            and "judged by judge-summ-v1" in cnn_d
            and "judged by judge-summ-v2" in cnn_d,
            f"first rows {firsts}",
        )

        # Where an arm's time went, in one form on every dataset page: "served on <machine>" or "run on ...".
        odd = sorted(
            {
                m
                for f in (cat / "d").glob("*.html")
                for m in re.findall(
                    r"<br><small>((?:on|run on|served on) [^<]+)</small>", f.read_text(encoding="utf-8")
                )
                if m.startswith("on ")
            }
        )
        check("dataset pages: the machine in one form (served on / run on)", not odd, ", ".join(odd[:5]))

        # A config's place in a goal's field is counted as the site counts it: one place per config, no arm a round
        # retired (a re-timing on Linux, a paired side run).
        def place(cfg: str) -> str:
            row = ct[ct.index(f'data-key="c:{cfg}"') :]
            return ",".join(re.findall(r"#(\d+ of \d+)", row[: row.index("</tr>")])) or "none"

        places = {
            c: place(c) for c in ("ag_anthropic_l_v1", "se_openai_l_n100_v1", "se_gemma_l_pubtext_n100_v1")
        }
        check(
            "arms page: AG News anthropic_l is 5th of 30 and SummEval openai_l 1st of 33, as on the site; a paired "
            "side run has no place",
            places
            == {
                "ag_anthropic_l_v1": "5 of 30",
                "se_openai_l_n100_v1": "1 of 33",
                "se_gemma_l_pubtext_n100_v1": "none",
            },
            str(places),
        )

        # A reference set is never younger than the first run scored against its bytes: the 0.4.0 migration dated
        # every gold set by the migration, so the references page listed sets a month old as new. A run that recorded
        # other bytes of a set whose texts are committed was scored against an earlier version of it (a set promoted
        # again under its id), which dates that version, not this one.
        from evaluation_harness._fingerprint import references_digest  # noqa: PLC0415
        from evaluation_harness.catalog_adapter import HarnessAdapter  # noqa: PLC0415

        A = HarnessAdapter()
        A.arms()
        now_sha: dict = {}
        first: dict = {}
        for _ds, _d, rec, _arm in A._every:
            data = (rec.get("fingerprint") or {}).get("data") or {}
            ref, made = data.get("reference_id"), rec.get("created_at")
            if not ref or not made:
                continue
            if ref not in now_sha:
                committed = any((HARNESS / "data" / "references" / ref).glob("*.txt"))
                now_sha[ref] = references_digest(HARNESS, ref, HARNESS / "data") if committed else None
            if now_sha[ref] and data.get("references_sha256") not in (None, now_sha[ref]):
                continue
            first[ref] = min(first.get(ref, "~"), made)
        young = [
            f"{r['id']} {r['created_at'][:10]} > {first[r['id']][:10]}"
            for r in A.references()
            if r["id"] in first and (r.get("created_at") or "") > first[r["id"]]
        ]
        check(
            "references: each dated no later than the first run scored against it",
            not young,
            "; ".join(young[:4]),
        )

        # A goal page's rounds count their arms as `evh round-list` does: a re-scored run is the same arm.
        differ = []
        for gp in sorted((cat / "g").glob("*.html")):
            shown = dict(
                re.findall(r"<b>(r\d+)</b>.*?<span data-v=\"(\d+)\">\d+ arms</span>", gp.read_text(), re.S)
            )
            if not shown:
                continue
            cli = subprocess.run(
                [sys.executable, str(HARNESS / "scripts" / "cli.py"), "round-list", gp.stem],
                cwd=HARNESS,
                capture_output=True,
                text=True,
            ).stdout
            said = dict(re.findall(r"^\s*(r\d+)\s+\S+\s+\S+\s+(\d+) arm\(s\)", cli, re.M))
            differ += [
                f"{gp.stem} {rid}: page {n}, evh round-list {said.get(rid)}"
                for rid, n in shown.items()
                if said.get(rid) != n
            ]
        check(
            "goal pages: each round's arms counted as evh round-list counts them",
            not differ,
            "; ".join(differ[:4]),
        )

        # The triage sheet's rows stay short: an item's fields in two lines, winners and arms named by what sets them
        # apart (listed whole, a row was 187 px tall).
        pair = ",".join(
            f"rescored-5f2c057c/orrery_triage_v1_labelled/{c}"
            for c in ("triage_baseline_pro_v1", "triage_local_dgx_gpt_oss_120b_v2")
        )
        page.goto(f"{base}inspect.html?dataset=orrery_triage_v1_labelled&sheet=1&runs={pair}")
        page.wait_for_selector("#sheettable tbody tr", timeout=60000)
        tallest = page.evaluate(
            "Math.max(...[...document.querySelectorAll('#sheettable tbody tr')].map(r => r.getBoundingClientRect().height))"
        )
        check(
            "sheet: the triage sheet's rows stay under 100 px", tallest < 100, f"tallest row {tallest:.0f} px"
        )

        # The sheet of a judging pass's arms, as a dataset page names them (judged-<scorer>/<dataset>/<system>).
        judged = sorted(q for q in links if "runs=judged-" in q)
        if judged:
            q = max(judged, key=lambda x: x.count(","))
            ds = q.split("runs=judged-", 1)[1].split("/")[1]
            arms = q.split("runs=", 1)[1].split("&", 1)[0].split(",")[:3]
            page.goto(f"{base}inspect.html?dataset={ds}&sheet=1&runs={','.join(arms)}")
            page.wait_for_selector("#sheettable, .callout, p.err", timeout=60000)
            over = page.evaluate(
                """[...document.querySelectorAll('#sheettable thead th')]
                .filter(h => h.scrollWidth > h.clientWidth + 1).map(h => h.innerText.slice(0, 60))"""
            )
            check(
                f"sheet: a judging pass's arms as the dataset page names them ({len(arms)} on {ds}) open, and no "
                "column header runs over the next",
                page.locator("#sheettable").count() == 1 and not over,
                f"headers over their cells: {over[:3]}" if over else page.locator("main").inner_text()[-300:],
            )

        # Against a silver reference the inspector names its author and marks that arm's row, so a "better 1.000" is
        # read as the author scored against its own output; an item's cards lead with the item's score.
        # The catalog's own links leave the author out (it is never tested against a leader), so the comparison
        # adds it, as a person comparing it by hand would: the reference's manifest names it. Four arms besides it
        # are enough to see its row marked.
        def with_author(q: str) -> str:
            from urllib.parse import unquote  # noqa: PLC0415

            whole = q.split("runs=", 1)[1].split("&", 1)[0]
            found = re.search(r"baseline=([^&]+)", q)
            base_arm = unquote(found.group(1)) if found else ""
            kept = (
                [base_arm, *[a for a in whole.split(",") if a != base_arm][:3]]
                if base_arm
                else whole.split(",")[:4]
            )
            q = q.replace("runs=" + whole, "runs=" + ",".join(kept), 1)
            runs = q.split("runs=", 1)[1].split("&", 1)[0].split(",")
            ds = runs[0].split("/")[1]
            m = HARNESS / "data" / "references" / "silver" / ds / "manifest.json"
            from evaluation_harness._common import system_now  # noqa: PLC0415

            # the author by the id its system has now (a migration renamed systems; the manifest keeps the old one)
            who = system_now(json.loads(m.read_text()).get("authored_by")) if m.is_file() else None
            arm = f"silver/{ds}/{who}"
            return (
                q.replace("runs=" + ",".join(runs), "runs=" + ",".join([*runs, arm]), 1)
                if who and arm not in runs
                else q
            )

        silver = sorted(
            (with_author(q) for q in links if "runs=silver/" in q and "baseline=" in q),
            key=lambda x: -x.count(","),
        )
        for q in silver:
            page.goto(base + "inspect.html?" + q)
            page.wait_for_selector(
                "span.chip.v-better, span.chip.v-worse, span.chip.v-none, .callout", timeout=120000
            )
            if page.locator("tr.t-author").count():
                break
        if silver and page.locator("tr.t-author").count():
            app_text = page.locator("#app").inner_text()
            page.locator("tr.eprow").first.click()
            page.wait_for_selector(".outgrid", timeout=60000)
            cards = page.locator(".outcol .itemscore").all_inner_texts()
            check(
                "inspector: against silver it names the arm that wrote it, marks its row, and the cards show scores",
                "written by" in app_text
                and "wrote the reference" in page.locator("tr.t-author").first.inner_text()
                and cards
                and all(c.strip()[:1].isdigit() for c in cards),
                f"{app_text[:200]!r} {cards[:2]}",
            )
        else:
            check(
                "inspector: a silver-scored comparison with its author in it exists in the catalog",
                False,
                str(silver[:1]),
            )
        check("no console errors", not errors, " | ".join(errors[:5]))
        browser.close()


def sqlite_copy(cat: Path) -> Path:
    """This repository's data as a SQLite store (a copy: the tracked files stay as they are), and the catalog built over
    it, in .build/real-sqlite/. The process then reads it: a SQLite store is not the repository's files, so serving
    the files' catalog on it left every comparison with no runs to answer from."""
    root = HARNESS / ".build" / "real-sqlite"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    shutil.copytree(HARNESS / "data", root / "data")
    os.environ.update(EVAL_DATA_DIR=str(root / "data"), EVAL_STORE="sqlite")
    cli = [sys.executable, str(HARNESS / "scripts" / "cli.py")]
    for args in (["data-migrate", "--to", "sqlite"], ["catalog", "--out", str(root / "catalog")]):
        r = subprocess.run(cli + args, cwd=HARNESS, capture_output=True, text=True, check=False)  # nosec B603
        if r.returncode:
            raise SystemExit(f"setup: evh {' '.join(args)} failed:\n{r.stdout}{r.stderr}")
    return root / "catalog"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--catalog", type=Path, default=HARNESS / ".build" / "budget-catalog")
    ap.add_argument(
        "--display-only", action="store_true", help="only how the pages read (any catalog, a small one too)"
    )
    args = ap.parse_args()
    try:
        import playwright  # noqa: F401, PLC0415
    except ImportError:
        print("  FAIL Playwright is not installed: `make browser-install` (requirements-browser.txt)")
        return 1
    cat = args.catalog.resolve()
    if os.environ.get("EVAL_STORE", "").strip() == "sqlite":
        cat = sqlite_copy(cat)
    if not (cat / "index.html").is_file():
        print(f"  FAIL no catalog at {cat}: `make browser-real-check` builds one")
        return 1
    log = HARNESS / ".build" / "real-browser-serve.log"
    server, base = serve(cat, log)
    try:
        if args.display_only:
            from playwright.sync_api import sync_playwright  # noqa: PLC0415

            with sync_playwright() as pw:
                browser = _slow.launch(pw)
                check_display(browser, base, cat)
                browser.close()
        else:
            drive(cat, base)
    finally:
        os.killpg(server.pid, signal.SIGTERM)
        server.wait(timeout=10)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
