#!/usr/bin/env python3
"""The catalog and the inspector in a real browser (headless Chromium, through Playwright).

    make browser-install     # once: requirements-browser.txt and Chromium
    make browser-check

test_catalog.py checks what the server answers; this checks what a reader sees. In a fresh
tutorial project with item fields and three arms, with the inspector on a free port:

  - the catalog home and goals pages load; the inspector opens on the primary metric with a
    verdict per arm and its charts, switches baseline, and shows an item beside its reference;
  - the dataset page lists the fields, their coverage, a public field's summary, "not public"
    for the hidden one, and no element id twice;
  - the inspector offers a filter on every field and a breakdown on the choice and yes/no ones;
  - a filter narrows the comparison and says so, and comes off again;
  - a breakdown draws its table, names the groups, and flags groups too small to separate;
  - opening an item shows its fields;
  - at phone width no page scrolls sideways;
  - no page logs a console error.

Missing Playwright is a failure that says how to install it, not a skip.
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
HARNESS = HERE.parent
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))  # _wheel, shared with the deploy
import _wheel  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402


def project(tmp: Path) -> tuple:
    """The package installed from its wheel, a tutorial project with fields and three arms, built."""
    site = _wheel.install(tmp / "site-packages")
    proj = tmp / "proj"
    proj.mkdir()
    env = {
        **os.environ,
        "PYTHONPATH": str(site),
        "PYTHONDONTWRITEBYTECODE": "1",
        "EVAL_BUILD_REF": "browser-check",
    }
    for k in ("EVAL_HOME", "EVAL_DATA_DIR", "EVAL_RUNS_DIR"):
        env.pop(k, None)

    def evh(*args: str) -> None:
        r = subprocess.run(
            [sys.executable, "-m", "evaluation_harness", *args],
            cwd=proj,
            env=env,
            capture_output=True,
            text=True,
        )
        if r.returncode:
            raise SystemExit(f"setup: evh {' '.join(args)} failed:\n{r.stdout}{r.stderr}")

    evh("init", "--tutorial")
    shutil.copy(proj / "tutorial/fields/tickets.yaml", proj / "data/fields/")
    evh(
        "dataset-create",
        "--dataset-id",
        "tickets_v1",
        "--source-dir",
        "tutorial/tickets",
        "--fieldset",
        "tickets",
        "--fields",
        "tutorial/ticket_fields.csv",
    )
    evh("dataset-materialize", "--dataset-id", "tickets_v1")
    for f in (proj / "tutorial/systems").glob("tickets_*.yaml"):
        shutil.copy(f, proj / "data/systems/")
    evh("label-import", "tutorial/gold", "--dataset-id", "tickets_v1", "--set", "owner_gold", "--by", "owner")
    evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "owner_gold",
        "--tier",
        "gold",
        "--reason",
        "The kit's hand-written summaries decide.",
        "--by",
        "owner",
    )
    for arm in ("lead1", "lead2", "author"):
        evh("run", "--system", f"tickets_{arm}_v1", "--dataset", "tickets_v1")
    # A goal with an open round: the goal page then carries its suggestions, each with a copy button.
    shutil.copy(proj / "tutorial/goals/tickets_summary.yaml", proj / "data/goals/")
    evh(
        "round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1",
        "--hypothesis", "how many leading sentences summarise a ticket best",
        "--keep", "tickets_lead1_v1,tickets_lead2_v1,tickets_author_v1",
    )  # fmt: skip
    # Production tickets and a pick waiting for tickets_v1 (RFC-023): the dataset page's selection gives a command.
    (proj / "prod.jsonl").write_text(
        "".join(
            json.dumps({"id": f"p{n}", "body": f"A new ticket {n}.", "created_at": f"2026-11-0{n}T09:00:00Z"})
            + "\n"
            for n in (1, 2)
        )
    )
    evh(
        "capture",
        "--importer",
        "jsonl",
        "--query",
        json.dumps({"path": "prod.jsonl"}),
        "--capture",
        "prod_c1",
    )
    evh("dataset-from-capture", "prod_c1", "--dataset-id", "prod_v1")
    evh("pick", "--dataset-id", "prod_v1", "--item", "p1", "--item", "p2", "--for", "tickets_v1")
    # A person's labels on two tickets: the sheet's wrong signal against them marks those two.
    (proj / "sheet.csv").write_text("item_id,label\nt01_login,Login fails.\nt02_invoice,Invoice wrong.\n")
    evh("label-import", "sheet.csv", "--dataset-id", "tickets_v1", "--set", "owner_v1", "--by", "owner")
    evh("catalog")
    return proj, env


def serve(proj: Path, env: dict, log: Path) -> tuple:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with open(log, "w", encoding="utf-8") as fh:  # the child keeps its own copy of the fd
        p = subprocess.Popen(
            [sys.executable, "-m", "evaluation_harness", "catalog-serve", "--port", str(port)],
            cwd=proj,
            env=env,
            stdout=fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    for _ in range(100):
        if "catalog:" in log.read_text():
            break
        if p.poll() is not None:
            raise SystemExit(f"catalog-serve exited:\n{log.read_text()}")
        time.sleep(0.1)
    return p, f"http://127.0.0.1:{port}/.build/catalog/"


def drive(base: str, overview: str = "") -> None:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        errors: list = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(base + "index.html")
        check(
            "home: the dataset is in the coverage table",
            "tickets_v1" in page.locator("table#coverage").inner_text(),
        )
        check(
            "home: activity and spend side by side, the last 14 days first",
            page.locator(".duo #activity figure.chart").first.is_visible()
            and page.locator("#spend [data-unit='usd']").is_visible()
            and page.get_attribute('#period .chip[data-period="14d"]', "aria-pressed") == "true",
        )
        shown = {
            t.locator("span").first.inner_text().lower(): (t.get_attribute("title") or "").split(" ")[0]
            for t in page.locator(".tile[data-tile]").all()
        }
        cli = {
            ln[:17].strip(): ln[17:35].strip()
            for ln in (overview or "").splitlines()[1:11]
            if ln.startswith("  ")
        }
        check(
            "home: every tile is what `evh overview` prints for the same period, from today",
            bool(cli) and all(shown.get(k) == v for k, v in cli.items()),
            f"page {shown} cli {cli}",
        )
        from datetime import date, timedelta  # noqa: PLC0415

        from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

        days = [date(2026, 1, 1) + timedelta(days=i) for i in range(0, 800, 7)] + [
            date(2028, 2, 29),
            date(2026, 3, 31),
            date(2026, 12, 31),
        ]
        bad = []
        for d in days:
            ms = int((d - date(1970, 1, 1)).total_seconds() * 1000)
            for k, *_ in cp.PERIODS:
                js = page.evaluate("([k,t])=>window.Period.bounds(k,t,'2025-06-01')", [k, ms])
                py = cp.bounds(k, d, "2025-06-01")
                if (js["since"], js["until"], js["prev"]) != (
                    py["since"],
                    py["until"],
                    list(py["prev"] or []) or None,
                ):
                    bad.append((d.isoformat(), k, js, py))
        check(
            f"home: the browser's periods are evh overview's, on {len(days)} days and every period",
            not bad,
            str(bad[:3]),
        )
        page.click('#period .chip[data-period="all"]')
        check(
            "home: 'all time' has no trend; the note says since when, its title the dates to today",
            page.locator("#period-span").inner_text().startswith("since ")
            and (page.get_attribute("#period-span", "title") or "").endswith(date.today().isoformat())
            and "compared" not in (page.get_attribute("#period-span", "title") or "")
            and page.locator(".tile[data-tile='7'] .trend").inner_text() == "",
        )
        check(
            "home: the feed lists what the tutorial recorded today, and its 'nothing recorded' note stays hidden",
            page.locator("#feeda tbody tr:not([hidden])").count() > 0
            and not page.locator("[data-feed-empty]").is_visible(),
        )
        page.locator('#spend button[data-unit-show="tokens"]').click()
        check(
            "home: spend in tokens (what a free local model still uses)",
            page.locator('#spend [data-unit="tokens"]').is_visible()
            and not page.locator('#spend [data-unit="usd"]').is_visible(),
        )
        page.select_option("#period select.more", "lastmonth")
        check(
            "home: last month (the tutorial ran today) is empty, and the feed and activity say so",
            page.locator("[data-feed-empty]").is_visible()
            and not page.locator("#feeda").is_visible()
            and "No measured run in this period" in page.locator("#activity").inner_text(),
        )
        page.goto(base + "datasets.html#p30d")
        check(
            "datasets page: the dataset is listed",
            "tickets_v1" in page.locator("table#datasets").inner_text(),
        )
        check(
            "datasets page: opens at the period its link names; the tutorial's dataset is new and active in it",
            page.get_attribute('#period button.chip[data-period="30d"]', "aria-pressed") == "true"
            and page.locator("table#datasets span.new").count() == 1
            and page.locator('.row-chips [data-rows="active"] b').inner_text() == "1",
        )
        page.click('#period button.chip[data-period="all"]')
        page.goto(base + "datasets.html#plastmonth")
        # new and active both 0: one chip says both (a new row has run in the period, so equal counts are one set)
        merged = page.locator('.row-chips [data-rows="new"]')
        check(
            "datasets page: when new and active count the same, one chip says both",
            "new and active" in merged.inner_text()
            and not page.locator('.row-chips [data-rows="active"]').is_visible(),
        )
        merged.click()
        check(
            "datasets page: last month (the tutorial ran today) has no active dataset, and says so",
            page.locator("p.pempty").first.is_visible() and not page.locator("table#datasets").is_visible(),
        )
        page.goto(base + "index.html")
        page.click('.nav details.navgroup[data-group="arms"] > summary')
        check(
            "menu: Arms opens Arms, Configs, Models, Prompts and Metrics",
            page.locator('.nav details.navgroup[data-group="arms"] .navlist a').all_inner_texts()
            == ["Arms", "Configs", "Models", "Prompts", "Metrics"],
        )
        page.goto(base + "arms.html#p30d")
        rows = page.locator("table#arms tbody tr:not(.grouphead)")
        check(
            "arms page: every arm a row, each saying how it was measured",
            rows.count() >= 3 and "measured" in page.locator("table#arms").inner_text(),
        )
        page.click('.group-chips [data-group-by="set"]')
        heads = page.locator("table#arms tr.grouphead:not(.emptyrow)").all_inner_texts()
        check(
            "arms page: grouped by dataset, each heading naming it, how its arms are scored and the measure",
            bool(heads) and all("tickets_v1" in h and ("against" in h or "judged" in h) for h in heads),
            heads,
        )
        page.locator("table#arms input.pick").nth(0).check()
        page.locator("table#arms input.pick").nth(1).check()
        link = page.locator(".compare-bar [data-compare]")
        check(
            "arms page: two arms on one dataset picked open in the inspector",
            page.locator(".compare-bar").is_visible()
            and link.get_attribute("aria-disabled") == "false"
            and "inspect.html?runs=" in (link.get_attribute("href") or ""),
        )
        page.goto(base + "activity.html#pall")
        check(
            "activity page: the charts and the period's tables",
            page.locator("#activity figure.chart").first.is_visible()
            and "tickets_v1" in page.locator("table#actds").inner_text(),
        )
        page.goto(base + "a/runs-tickets_v1-tickets_lead2_v1.html")
        check(
            "arm page: its metrics link to their pages",
            page.locator('a[href="../m/overlap_f1.html"]').count() >= 1,
        )
        page.goto(base + "goals.html")
        check("goals page: loads", page.locator("main").count() == 1)
        page.goto(base + "g/tickets_summary.html")
        check(
            "goal page: the open round opens in the inspector (evh inspect --round)",
            page.locator('a[title^="evh inspect --round r1"]').count() == 1,
        )
        # Each round is a folded section: open the open one, as a reader does, to reach its suggestions.
        page.click("details.roundcard.t-open > summary")
        btn = page.locator("button.copy").first
        cmd = btn.get_attribute("data-copy") if btn.count() else None
        if cmd:
            btn.click()
            page.wait_for_function(
                "document.querySelector('button.copy').textContent !== 'copy'", timeout=5000
            )
        got = page.evaluate("navigator.clipboard.readText()") if cmd else None
        check(
            "goal page: a suggested command's copy button puts the command on the clipboard",
            bool(cmd) and got == cmd,
            f"{cmd!r} -> {got!r}",
        )

        # The picker: a goal with one dataset picks it; its arms are listed, filtered and ticked together.
        page.goto(base + "inspect.html")
        page.wait_for_selector("details.pk[open] #pk-goal", timeout=15000)
        page.select_option("#pk-goal", "tickets_summary")
        listed = page.locator(".pk-arm").count()
        check(
            "inspector picker: a goal with one dataset picks it and lists its arms",
            page.locator('.pk-dsb[aria-pressed="true"]').get_attribute("data-ds") == "tickets_v1"
            and listed == 3,
            listed,
        )
        page.fill("#pk-q", "lead")
        check("inspector picker: the filter narrows the arms", page.locator(".pk-arm").count() == 2)
        page.fill("#pk-q", "")
        page.click("#pk-all")
        check(
            "inspector picker: every arm shown is ticked, and named while ticked",
            page.locator(".pk-arm input:checked").count() == 3
            and page.locator("#pk-count [data-untick]").count() == 3,
        )
        with page.expect_navigation():
            page.click("#pk-open")
        got = sorted(parse_qs(urlparse(page.url).query).get("runs", [""])[0].split(","))
        check(
            "inspector picker: Inspect opens the ticked arms, the picker folded",
            got == sorted(f"runs/tickets_v1/tickets_{a}_v1" for a in ("lead1", "lead2", "author"))
            and page.locator("details.pk:not([open])").count() == 1,
            got,
        )

        arms = ",".join(f"runs/tickets_v1/tickets_{a}_v1" for a in ("lead1", "lead2", "author"))
        page.goto(f"{base}inspect.html?runs={arms}&baseline=runs/tickets_v1/tickets_lead1_v1")
        page.wait_for_selector("#metric", timeout=15000)
        check(
            "inspector: opens on the primary metric",
            page.locator("#metric").input_value() == "overlap_f1",
            page.locator("#metric").input_value(),
        )
        verdicts = page.locator("table.data").first.locator("tbody tr").count()
        check("inspector: a verdict row per arm against the baseline", verdicts == 2, verdicts)
        check(
            "inspector: an arm's name opens its page, the metric its page",
            page.locator('table.data a[href="a/runs-tickets_v1-tickets_lead2_v1.html"]').count() == 1
            and page.locator('p.eyebrow a[href="m/overlap_f1.html"]').count() == 1,
        )
        check("inspector: the charts are drawn", page.locator("figure.chart svg").count() >= 2)
        foot = page.locator("[data-elsewhere=term]").inner_text()
        check(
            "inspector: the footer names the comparison picked as its command",
            foot == f"evh inspect --runs {arms} --baseline runs/tickets_v1/tickets_lead1_v1",
            foot,
        )
        with page.expect_navigation():
            page.select_option("#baseline", "runs/tickets_v1/tickets_lead2_v1")
        page.wait_for_selector("#baseline")
        check(
            "inspector: the baseline can be switched",
            page.locator("#baseline").input_value() == "runs/tickets_v1/tickets_lead2_v1",
        )
        page.locator("tr.eprow").first.click()
        page.wait_for_selector(".outgrid", timeout=15000)
        check(
            "inspector: an item shows each arm's output beside the gold reference",
            page.locator(".refcol").count() == 1 and page.locator(".outcol").count() == 4,
            page.locator(".outcol").count(),
        )
        metric = page.locator("#metric").input_value()
        cards = page.locator(".outcol .itemscore").all_inner_texts()
        check(
            "inspector: each arm's card on an item leads with the item's score for the metric in view",
            len(cards) >= 3 and all(metric in c and c.strip()[:1].isdigit() for c in cards),
            str(cards),
        )
        check(
            "inspector: an item shows the item itself, what every arm read",
            page.locator("details.srcbox").count() == 1
            and "item itself" in page.locator("details.srcbox summary").inner_text(),
        )
        ep = page.locator("tr.eprow").nth(2).get_attribute("data-ep")
        page.goto(f"{base}inspect.html?runs={arms}&item={ep}")
        page.wait_for_selector(".outgrid", timeout=15000)
        check(
            "inspector: ?item= (a dataset page's inspect link) opens that item",
            page.locator("tr.eprow.on").get_attribute("data-ep") == ep,
        )

        page.goto(base + "d/tickets_v1.html")
        ftable = page.locator("table#fields").inner_text()
        check("dataset page: element ids are unique", page.locator('[id="fields"]').count() == 1)
        check(
            "dataset page: the fields, with their labels",
            all(x in ftable for x in ("Area", "Plan", "Names a deadline")),
            ftable[:200],
        )
        check("dataset page: coverage, 6 of 6 and 2 of 6", "6 of 6" in ftable and "2 of 6" in ftable)
        check("dataset page: a public field summarised (account 2)", "account 2" in " ".join(ftable.split()))
        check("dataset page: the hidden field shows 'not public'", "not public" in ftable)
        pickcmd = page.locator("#picks .cmdpick code.cmd")
        check(
            "picks waiting: nothing ticked, no command to copy",
            "tick the picks" in pickcmd.inner_text() and page.locator("#picks button.copy").is_hidden(),
            pickcmd.inner_text(),
        )
        page.locator('#picks input.cmdsel[value="prod_v1:p2"]').check()
        check(
            "picks waiting: a ticked row gives the dataset-extend command, to copy",
            pickcmd.inner_text() == "evh dataset-extend tickets_v1 --dataset-id <next> --pick prod_v1:p2"
            and page.locator("#picks button.copy").is_visible(),
            pickcmd.inner_text(),
        )
        before = len(errors)
        page.locator("#picks th", has_text="item").click()
        page.locator("#picks th", has_text="item").click()
        order = page.locator("#picks tbody tr td:nth-child(2)").all_inner_texts()
        check(
            "sort: a later table on a page sorts by the clicked column (desc: p2 first), no error",
            order == ["p2", "p1"] and len(errors) == before,
            f"{order} {errors[before:]}",
        )
        page.locator("#picks input.cmdall").check()
        check(
            "picks waiting: select all shown takes every row",
            "--pick prod_v1:p1" in pickcmd.inner_text() and "--pick prod_v1:p2" in pickcmd.inner_text(),
            pickcmd.inner_text(),
        )

        # Paging (catalog.js): a 23-row table shows 10, then 20, then all 23; a filter pages its matches.
        paged = page.evaluate(
            """() => {
              const wrap = document.createElement('div'); wrap.className = 'scroll-x';
              const t = document.createElement('table'); t.className = 'data'; t.id = 'pagetest';
              t.innerHTML = '<thead><tr><th>n</th></tr></thead><tbody>'
                + Array.from({length: 23}, (_, i) => `<tr><td>row ${i} ${i % 2 ? 'odd' : 'even'}</td></tr>`).join('')
                + '</tbody>';
              wrap.appendChild(t); document.querySelector('main').appendChild(wrap);
              window.paginate(t);
              const vis = () => [...t.tBodies[0].rows].filter(r => r.offsetParent !== null).length;
              const out = [vis()];
              wrap.nextElementSibling.querySelector('[data-more]').click(); out.push(vis());
              wrap.nextElementSibling.querySelector('[data-all]').click(); out.push(vis());
              [...t.tBodies[0].rows].forEach(r => { r.hidden = !r.textContent.includes('odd'); }); t._repage();
              wrap.nextElementSibling.querySelector('[data-less]')?.click(); out.push(vis());
              return out;
            }"""
        )
        check(
            "paging: 10, then 20, then all 23; 11 filtered matches page to 10",
            paged == [10, 20, 23, 10],
            paged,
        )

        page.goto(f"{base}inspect.html?runs={arms}&baseline=runs/tickets_v1/tickets_lead1_v1")
        page.wait_for_selector("#wfield", timeout=15000)
        opts = page.locator("#wfield option").all_inner_texts()
        check("inspector: a filter on every field", opts == ["Area", "Plan", "Names a deadline"], opts)
        by = page.locator("#by option").all_inner_texts()
        check(
            "inspector: a breakdown on the choice and yes/no fields",
            by == ["none", "Area", "Plan", "Names a deadline"],
            by,
        )

        page.select_option("#wfield", "area")
        page.wait_for_selector("#wv")
        page.select_option("#wv", "account")
        with page.expect_navigation():
            page.click("#addwhere button")
        page.wait_for_selector(".note")
        notes = " ".join(page.locator(".note").all_inner_texts())
        check(
            "inspector: a filter narrows to 2 tickets and says so",
            "Filtered to the 2 item(s) where area = account" in notes,
            notes[:300],
        )
        chip = page.locator('[data-unwhere="area:account"]')
        check("inspector: the filter is a removable chip", chip.count() == 1)
        with page.expect_navigation():
            chip.click()
        page.wait_for_selector("#by")
        check(
            "inspector: removing it brings every ticket back",
            "Filtered to" not in " ".join(page.locator(".note").all_inner_texts()),
        )

        with page.expect_navigation():
            page.select_option("#by", "deadline")
        page.wait_for_selector("h3.sub")
        check(
            "inspector: a breakdown table by Names a deadline",
            page.locator("h3.sub", has_text="By Names a deadline").count() == 1,
        )
        table = page.locator("h3.sub + div table").inner_text()
        check(
            "inspector: groups named yes and no, too-small groups flagged",
            "yes" in table and "no" in table and "cannot reach 0.05" in table,
            table[:300],
        )

        page.locator("tr.eprow").first.click()
        page.wait_for_selector("table.fields", timeout=15000)
        it = page.locator("table.fields").inner_text().lower()
        check("inspector: an item shows its fields", "area" in it and "names a deadline" in it, it)

        # The comparison's "only where they disagree" box (RFC-023): ticking it asks for disagree=1.
        page.locator("#disagree").check()
        page.wait_for_url("**disagree=1**", timeout=15000)
        check(
            "inspector: the disagree box narrows the comparison (disagree=1)",
            "disagree=1" in page.url,
            page.url,
        )

        # The sheet (RFC-023, UXS-002 05): one dataset's tickets down, a column per arm, a box per row giving the commands.
        two = "runs/tickets_v1/tickets_lead1_v1,runs/tickets_v1/tickets_author_v1"
        page.goto(f"{base}inspect.html?dataset=tickets_v1&sheet=1&runs={two}")
        page.wait_for_selector("#sheettable", timeout=15000)
        n_rows = page.locator("#sheettable tbody tr").count()
        check(
            "sheet: one row per ticket, the counts above it",
            n_rows == 6 and page.locator("#scounts").inner_text().startswith("6 "),
            f"{n_rows} {page.locator('#scounts').inner_text()}",
        )
        heads = [h.strip().lower() for h in page.locator("#sheettable thead th").all_inner_texts()]
        check(
            "sheet: the item, its start, the signals, then a column of output and of scores per arm; the fields last",
            heads[2:4] == ["the start", "signals"]
            and heads[-1] == "fields"
            and sum("overlap_f1" in h and not h.startswith("winner") for h in heads) == 2
            and sum("output" in h or "first: production" in h for h in heads) == 2
            and any(h.startswith("winner:") for h in heads)
            and any("label" in h and "owner_v1" in h for h in heads),
            str(heads),
        )
        foot_rows = page.locator("#sheettable tfoot tr")
        foot_text = [t.inner_text() for t in foot_rows.all()]
        check(
            "sheet: the footer, per arm: its mean, its win rate, its verdict (a leader among them)",
            len(foot_text) >= 3
            and foot_text[0].lower().startswith("mean overlap_f1")
            and any(t.lower().startswith("win rate") and "%" in t for t in foot_text)
            and foot_text[-1].lower().startswith("verdict")
            and "leader" in foot_text[-1],
            str(foot_text),
        )
        sel_cell = page.locator("#sheettable tbody tr").first.locator("td.item")
        check(
            "sheet: the item column is sticky",
            sel_cell.evaluate("e => getComputedStyle(e).position") == "sticky",
            sel_cell.evaluate("e => getComputedStyle(e).position"),
        )
        narrow = browser.new_page(viewport={"width": 640, "height": 800})
        narrow.on("pageerror", lambda e: errors.append(str(e)))
        narrow.goto(f"{base}inspect.html?dataset=tickets_v1&sheet=1&runs={two}")
        narrow.wait_for_selector("#sheettable", timeout=15000)
        box = narrow.locator("#sheettable").locator("xpath=ancestor::div[contains(@class,'scroll-x')][1]")
        overflow = box.evaluate("e => e.scrollWidth - e.clientWidth")
        item_cell = narrow.locator("#sheettable tbody tr").first.locator("td.item")
        left0 = item_cell.evaluate("e => e.getBoundingClientRect().left")
        box.evaluate("e => { e.scrollLeft = e.scrollWidth; }")
        left1 = item_cell.evaluate("e => e.getBoundingClientRect().left")
        far = (
            narrow.locator("#sheettable tbody tr")
            .first.locator("td")
            .nth(-1)
            .evaluate("e => e.getBoundingClientRect().left")
        )
        check(
            "sheet: scrolled across the arms, the item stays in place",
            overflow > 100 and abs(left1 - left0) < 2 and far < 640,
            f"overflow {overflow}, item at {left0} then {left1}, the last column at {far}",
        )
        narrow.close()
        check("sheet: nothing ticked, no commands", page.locator("#spanel").is_hidden())
        first = page.locator("#sheettable tbody input.ssel").first
        it_id = first.get_attribute("value") or ""
        first.check()
        page.locator("#sfor").fill("tickets_v2")
        page.locator("#snote").fill("worth keeping")
        pk, sh = page.locator("#spick").inner_text(), page.locator("#ssheet").inner_text()
        check(
            "sheet: a ticked row gives evh pick (with the target and note typed) and evh label-sheet",
            pk == f'evh pick --dataset-id tickets_v1 --item {it_id} --for tickets_v2 --note "worth keeping"'
            and sh == f"evh label-sheet --dataset-id tickets_v1 --item {it_id} --out sheet.csv --runs {two}",
            f"{pk} | {sh}",
        )
        origin = base.rstrip("/").rsplit("/.build", 1)[0]

        def download(selector):
            href = page.locator(selector).get_attribute("href") or ""
            got = page.request.get(origin + href) if href.startswith("/api/sheet?") else None
            body = got.body() if got is not None else b""
            rows_ = list(csv.reader(io.StringIO(body.decode("utf-8-sig", "replace"), newline="")))
            return href, got, body, [",".join(x) for x in rows_], rows_

        href, got, body, lines, cells = download("#ssheetdl")
        check(
            "sheet: 'download these rows (CSV)' gives the sheet for the ticked rows, as Excel reads it: the mark, the row, the footer",
            got is not None
            and got.status == 200
            and "attachment" in (got.headers.get("content-disposition") or "")
            and body.startswith(b"\xef\xbb\xbf")
            and cells[0][:3] == ["item_id", "item", "signals"]
            and cells[1][0] == it_id
            and cells[2][0].startswith("#mean overlap_f1")
            and any(x[0] == "#verdict" for x in cells)
            and not any(x[0].startswith("t0") for x in cells[2:]),
            f"{href} {got.status if got else None} {lines[:3]}",
        )
        href, got, body, lines, cells = download("#sheetdl")
        rows_in = [x for x in lines[1:] if not x.startswith("#")]
        check(
            "sheet: 'download (CSV)' gives every row shown",
            got is not None and got.status == 200 and len(rows_in) == 6 and "format=csv" in href,
            f"{href} {len(rows_in)} rows",
        )
        page.locator("#sfill").check()
        href, got, body, lines, cells = download("#sheetdl")
        check(
            "sheet: with the empty label columns to fill: label, also right, note, and no footer",
            got is not None
            and got.status == 200
            and cells[0][-3:] == ["label", "also right", "note"]
            and not any(x.startswith("#") for x in lines),
            f"{href} {lines[:1]}",
        )
        page.locator("#sfill").uncheck()
        page.locator("#sscores").check()
        shown_out = page.locator("#sheettable thead th.outc").first.is_visible()
        spans = page.locator("#sheettable tfoot td.foot").evaluate_all(
            "es => es.every(e => e.colSpan === Math.max(1, +e.dataset.n))"
        )
        href, got, body, lines, cells = download("#sheetdl")
        arm1 = two.split(",")[0]
        check(
            "sheet: 'scores only' hides the outputs (the footer follows) and the download leaves them out",
            not shown_out
            and spans
            and "scores=only" in page.url
            and got is not None
            and arm1 not in cells[0]
            and f"{arm1}: overlap_f1" in cells[0],
            f"{shown_out} {spans} {page.url} {lines[:1]}",
        )
        page.locator("#sscores").uncheck()
        page.locator("#sheettable tbody tr td:nth-child(2)").first.click()
        page.wait_for_selector("#drill .eyebrow", timeout=15000)
        drill_text = page.locator("#drill").inner_text()
        check("sheet: a row opens the ticket", it_id.lower() in drill_text.lower(), drill_text[:300])
        # wrong against the person's two labels: the first arm's one sentence is neither, so exactly those two rows
        page.goto(f"{base}inspect.html?dataset=tickets_v1&sheet=1&runs={two}&wrong=tickets_v1/owner_v1")
        page.wait_for_selector("#sheettable", timeout=15000)
        carry = page.locator("#sheettable tbody tr .sig-wrong").count()
        page.locator('input.sonly[value="wrong"]').check()
        page.wait_for_url("**only=wrong**", timeout=15000)
        page.wait_for_selector("#sheettable", timeout=15000)
        kept = page.locator("#sheettable tbody tr").count()
        marked = page.locator("#sheettable tbody tr .sig-wrong").count()
        check(
            "sheet: only a signal keeps the rows that carry it (wrong against the person's two labels)",
            carry == 2 and kept == marked == carry,
            f"{carry} carry it, {kept} rows kept, {marked} marked",
        )
        page.goto(f"{base}inspect.html?dataset=tickets_v1&sheet=1&runs={two}&metric=latency_ms")
        page.wait_for_selector("#sheettable", timeout=15000)
        check(
            "sheet: the metric is chosen on the page (latency_ms: lower is better, said above the table)",
            "lower is better" in page.locator("#scounts").inner_text()
            and page.locator("#smetric").input_value() == "latency_ms",
            page.locator("#scounts").inner_text(),
        )
        page.goto(f"{base}inspect.html?dataset=prod_v1&sheet=1&item=p1")
        page.wait_for_selector("#drill .eyebrow", timeout=15000)
        check(
            "sheet with no arm (a pick's link): the item opens, its labels said",
            "No label for this" in page.locator("#drill").inner_text(),
            page.locator("#drill").inner_text()[:300],
        )

        # A phone: the pages must not scroll sideways (tables scroll inside their own box).
        phone = browser.new_page(viewport={"width": 390, "height": 844})
        phone.on("pageerror", lambda e: errors.append(str(e)))
        for path, ready in (
            *(
                (p, "main")
                for p in (
                    "index.html",
                    "goals.html",
                    "datasets.html",
                    "captures.html",
                    "labels.html",
                    "references.html",
                )
            ),
            *((p, "main") for p in ("metrics.html", "arms.html", "activity.html", "g/tickets_summary.html")),
            ("d/tickets_v1.html", "table#fields"),
            (f"inspect.html?runs={arms}&by=deadline", "h3.sub"),
            (f"inspect.html?dataset=tickets_v1&sheet=1&runs={arms}", "#sheettable"),
        ):
            phone.goto(base + path)
            phone.wait_for_selector(ready, timeout=15000)
            wide = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(f"phone width: no sideways scroll on {path.split('?')[0]}", wide <= 1, f"{wide}px too wide")

        # At scale (PLAN_0.8.0 S3): this comparison as the server answers it, stretched to 10,000 items and 40 arms.
        # The page overflowed the call stack there (Math.min over 400,000 values: no verdicts, ever) and drew all
        # 10,000 rows, 3.2 million elements; now it shows its verdicts and draws only the rows it shows.
        def stretch(route) -> None:
            got = route.fetch()
            d = got.json()
            base_arm = d["baseline"]
            other = next(a for a in d["series"] if a != base_arm)
            items = [f"x{k:05d}" for k in range(10000)]
            row = next(r for r in d["rows"] if r["arm"] == other)
            arm = next(x for x in d.get("arms") or [] if x.get("id") == other)
            copies = [f"{other}~{j}" for j in range(39)]
            d["items"] = items
            d["series"] = {base_arm: {i: (k % 7) / 7 for k, i in enumerate(items)}}
            for j, c in enumerate(copies):
                d["series"][c] = {i: ((k + j) % 9) / 9 for k, i in enumerate(items)}
            d["rows"] = [{**row, "arm": c, "n": len(items)} for c in copies]
            d["arms"] = [x for x in d.get("arms") or [] if x.get("id") == base_arm] + [
                {**arm, "id": c} for c in copies
            ]
            d["shape"] = {
                "latency_ms": {a: {i: 100.0 + (k % 50) for k, i in enumerate(items)} for a in d["series"]}
            }
            route.fulfill(response=got, body=json.dumps(d))

        big = browser.new_page()
        big_errors: list = []
        big.on("pageerror", lambda e: big_errors.append(str(e)))
        big.route("**/api/compare**", stretch)
        big.goto(base + f"inspect.html?runs={arms}")
        big.wait_for_function(
            "document.querySelectorAll('table.data')[0]?.querySelectorAll('tbody tr').length >= 39",
            timeout=60000,
        )
        drawn = big.locator("table.eps tbody tr").count()
        elements = big.evaluate("document.getElementsByTagName('*').length")
        pager = big.locator("#eps-pager").inner_text()
        check(
            "inspector at 10,000 items and 40 arms: 39 verdicts, no page error, 10 rows of the per-item table drawn",
            not big_errors and drawn == 10 and elements < 20000 and "Showing 10 of 10000" in pager,
            (big_errors[:1], drawn, elements, pager),
        )
        bins, dots = big.locator("svg rect.bin").count(), big.locator("svg circle.dot").count()
        check(
            "... its charts drawn from bins (the spread, the differences, the scatter's grid), not 1.2 million dots",
            bins > 100 and dots == 0 and big.locator("#scatterbox rect.bin").count() > 0,
            (bins, dots),
        )
        big.locator("#eps-pager [data-more]").click()
        check("... show 10 more draws ten more", big.locator("table.eps tbody tr").count() == 20)
        bulk = big.locator("#eps-pager [data-bulk]").inner_text()
        big.locator("#eps-pager [data-bulk]").click()
        check(
            "... past 1,000 items there is no show all, a thousand more instead",
            bulk == "show 1000 more" and big.locator("table.eps tbody tr").count() == 1020,
            (bulk, big.locator("table.eps tbody tr").count()),
        )
        big.goto(base + f"inspect.html?runs={arms}&item=x04321")
        big.wait_for_selector("tr.eprow.on", timeout=60000)
        check(
            "... ?item= far down the list: the table is drawn down to it and it opens",
            big.locator("tr.eprow.on").get_attribute("data-ep") == "x04321"
            and big.locator("table.eps tbody tr").count() == 4322,
            big.locator("table.eps tbody tr").count(),
        )
        big.close()

        # The sheet at 10,000 rows: drawn on demand too (it was 940,000 elements at 40 arms); select all still takes
        # every row of the sheet, and a sort orders all of them, not only the rows drawn.
        def stretch_sheet(route) -> None:
            got = route.fetch()
            d = got.json()
            row = d["rows"][0]
            d["rows"] = [{**row, "item": f"x{k:05d}"} for k in range(10000)]
            d["total"] = len(d["rows"])
            route.fulfill(response=got, body=json.dumps(d))

        sheet = browser.new_page()
        sheet_errors: list = []
        sheet.on("pageerror", lambda e: sheet_errors.append(str(e)))
        sheet.route("**/api/sheet**", stretch_sheet)
        sheet.goto(base + f"inspect.html?dataset=tickets_v1&sheet=1&runs={arms}")
        sheet.wait_for_selector("#sheettable tbody tr", timeout=60000)
        sheet_rows = sheet.locator("#sheettable tbody tr").count()
        check(
            "sheet at 10,000 rows: 10 drawn, the pager says how many, no page error",
            sheet_rows == 10
            and "Showing 10 of 10000" in sheet.locator("#sheet-pager").inner_text()
            and not sheet_errors,
            (sheet_rows, sheet_errors[:1]),
        )
        sheet.locator("#sall").check()
        check(
            "... select all takes every row of the sheet, drawn or not",
            sheet.locator("#sn").inner_text() == "10000"
            and "--item x09999" in sheet.locator("#spick").inner_text(),
            sheet.locator("#sn").inner_text(),
        )
        sheet.locator("#sheettable thead th.item").click()
        sheet.locator("#sheettable thead th.item").click()
        top = sheet.locator("#sheettable tbody tr").first.get_attribute("data-ep")
        check(
            "... a sort orders all 10,000 rows, not the 10 drawn (descending: x09999 first)",
            top == "x09999",
            top,
        )
        sheet.close()
        check("no console errors", not errors, " | ".join(errors))
        browser.close()


def main() -> int:
    try:
        import playwright  # noqa: F401, PLC0415
    except ImportError:
        print("  FAIL Playwright is not installed: `make browser-install` (requirements-browser.txt)")
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="evh-browser-"))
    server = None
    try:
        proj, env = project(tmp)
        server, base = serve(proj, env, tmp / "serve.log")
        ov = subprocess.run(
            [sys.executable, "-m", "evaluation_harness", "overview", "--period", "14d"],
            cwd=proj, env=env, capture_output=True, text=True,
        )  # fmt: skip
        drive(base, ov.stdout)
    finally:
        if server is not None:
            os.killpg(server.pid, signal.SIGTERM)
            server.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
