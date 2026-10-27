#!/usr/bin/env python3
"""The catalog of this repository's own runs in a real browser: hundreds of arms, not a tutorial's
three. test_inspector_browser.py proves each control on a small project; this proves the pages hold
at the size the deployment serves.

    python tests/test_catalog_real_browser.py --catalog .build/budget-catalog
    make browser-real-check            (builds the catalog first when it is missing)

With the inspector on a free port, over a built catalog:

  - every page a reader reaches from the menu, and a goal, a dataset, an arm and a metric page,
    loads with no console error and no sideways scroll at phone width;
  - the arms page lists as many arms as it says, groups them into as many configs as it says,
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
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
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


def drive(cat: Path, base: str) -> None:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    sub = [
        next(iter(sorted((cat / "g").glob("*.html")))).relative_to(cat).as_posix(),
        next(iter(sorted((cat / "d").glob("*.html")))).relative_to(cat).as_posix(),
        next(iter(sorted((cat / "a").glob("*.html")))).relative_to(cat).as_posix(),
        next(iter(sorted((cat / "m").glob("*.html")))).relative_to(cat).as_posix(),
    ]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        errors: list = []
        phone = browser.new_page(viewport={"width": 390, "height": 844})
        phone.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        phone.on("pageerror", lambda e: errors.append(str(e)))
        for path in (*PAGES, *sub):
            phone.goto(base + path)
            phone.wait_for_selector("main", timeout=30000)
            wide = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(f"phone width: no sideways scroll on {path}", wide <= 1, f"{wide}px too wide")

        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # The arms page at full size: all time, every row shown.
        page.goto(base + "arms.html#pall")
        page.wait_for_selector("table#arms")
        hero = page.locator(".hero").first.inner_text()
        m = re.search(r"(\d+) arms from (\d+) configs", hero)
        n_arms, n_cfg = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        check(
            f"arms page: the table lists the {n_arms} arms it says",
            n_arms > 100 and page.locator("table#arms tbody tr").count() == n_arms,
            f"hero {hero[:80]!r}, rows {page.locator('table#arms tbody tr').count()}",
        )
        page.click('.group-chips[data-for="arms"] [data-group-by="config"]')
        heads = page.locator("table#arms tr.grouphead").count()
        check(
            f"arms page: grouped by config, one heading per config ({n_cfg})",
            heads == n_cfg,
            f"{heads} headings",
        )
        page.click('.group-chips[data-for="arms"] [data-group-by=""]')
        for facet, value, attr in (
            ("weights", "open", "weights"),
            ("weights", "proprietary", "weights"),
            ("quality", "ties the leader", "quality"),
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
        text = page.locator("main").inner_text()
        unnamed = [i for i in ids if i not in text]
        rows = page.locator("table.data").first.locator("tbody tr").count()
        check(
            f"inspector: the largest comparison the catalog links to ({len(ids)} arms) answers; every arm is "
            f"compared ({rows} verdict rows) or named in a note saying why not",
            rows > 0 and not unnamed,
            f"not named: {unnamed[:5]}",
        )
        check("no console errors", not errors, " | ".join(errors[:5]))
        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--catalog", type=Path, default=HARNESS / ".build" / "budget-catalog")
    args = ap.parse_args()
    try:
        import playwright  # noqa: F401, PLC0415
    except ImportError:
        print("  FAIL Playwright is not installed: `make browser-install` (requirements-browser.txt)")
        return 1
    cat = args.catalog.resolve()
    if not (cat / "index.html").is_file():
        print(f"  FAIL no catalog at {cat}: `make browser-real-check` builds one")
        return 1
    log = HARNESS / ".build" / "real-browser-serve.log"
    server, base = serve(cat, log)
    try:
        drive(cat, base)
    finally:
        os.killpg(server.pid, signal.SIGTERM)
        server.wait(timeout=10)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
