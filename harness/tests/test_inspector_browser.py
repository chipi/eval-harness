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

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

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
    for f in (proj / "tutorial/configs").glob("tickets_*.yaml"):
        shutil.copy(f, proj / "data/configs/")
    shutil.copytree(proj / "tutorial/gold", proj / "data/references/gold/tickets_v1")
    for arm in ("lead1", "lead2", "author"):
        evh("experiment-run", "--config", f"data/configs/tickets_{arm}.yaml")
    # A goal with an open round: the goal page then carries its suggestions, each with a copy button.
    shutil.copy(proj / "tutorial/goals/tickets_summary.yaml", proj / "data/goals/")
    evh(
        "round-open", "--goal", "tickets_summary", "--dataset", "tickets_v1",
        "--hypothesis", "how many leading sentences summarise a ticket best",
        "--keep", "tickets_lead1_v1,tickets_lead2_v1,tickets_author_v1",
    )  # fmt: skip
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


def drive(base: str) -> None:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        errors: list = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(base + "index.html")
        check("home: the dataset is listed", "tickets_v1" in page.locator("table#datasets").inner_text())
        page.goto(base + "goals.html")
        check("goals page: loads", page.locator("main").count() == 1)
        page.goto(base + "g/tickets_summary.html")
        check(
            "goal page: the open round opens in the inspector (evh inspect --round)",
            page.locator('a[title^="evh inspect --round r1"]').count() == 1,
        )
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
        check("inspector: the charts are drawn", page.locator("figure.chart svg").count() >= 2)
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
        check(
            "inspector: an item shows the item itself, what every arm read",
            page.locator("details.srcbox").count() == 1
            and "item itself" in page.locator("details.srcbox summary").inner_text(),
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

        # A phone: the pages must not scroll sideways (tables scroll inside their own box).
        phone = browser.new_page(viewport={"width": 390, "height": 844})
        phone.on("pageerror", lambda e: errors.append(str(e)))
        for path, ready in (
            ("d/tickets_v1.html", "table#fields"),
            (f"inspect.html?runs={arms}&by=deadline", "h3.sub"),
        ):
            phone.goto(base + path)
            phone.wait_for_selector(ready, timeout=15000)
            wide = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(f"phone width: no sideways scroll on {path.split('?')[0]}", wide <= 1, f"{wide}px too wide")
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
        drive(base)
    finally:
        if server is not None:
            os.killpg(server.pid, signal.SIGTERM)
            server.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
