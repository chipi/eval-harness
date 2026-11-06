#!/usr/bin/env python3
"""The data page in a real browser (headless Chromium, through Playwright), on both stores (UXS-004).

    python tests/test_data_page_browser.py                 the checks
    python tests/test_data_page_browser.py --shots DIR     the checks, and a screenshot of every step in DIR

In a tutorial project served by a local catalog-serve, kept as files and then moved into its database:

  - the header's Data menu has Manage on the local server; a page opened from disk does not show it;
  - the overview: the store badge, the settings tiles, the data folders; finding a file by name;
  - a folder of settings, and its "+ New";
  - a setting: its fields (not its YAML), the runs made with it, its sha256, Edit and Delete; the file as stored
    behind a disclosure; a run's file read-only, with what writes it;
  - the form: a field per key, required ones marked, the project's datasets suggested; an emptied required field is
    refused at its field and in the list, nothing saved; a number changed, an optional field set from "more fields",
    a parameter added (its key, its type, its value), saved: the file keeps its comments;
  - a new goal in its form: fields filled, a dataset card added and removed, Create, then Delete through the page's
    own confirmation;
  - deleting a run, after the panel says what goes;
  - at phone width no page scrolls sideways; no page logs a console error.

Missing Playwright is a failure that says how to install it, not a skip.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HARNESS / "tests"))
from evaluation_harness._check import check, summary  # noqa: E402
from test_data_page import serve, setup  # noqa: E402


def drive(store: str, base: str, proj: Path, shots: Path | None) -> None:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    n = [0]

    def shot(page, name: str) -> None:
        if shots is not None:
            n[0] += 1
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(shots / f"{store}-{n[0]:02d}-{name}.png"), full_page=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 860})
        errors: list = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        failed: list = []
        page.on("response", lambda r: failed.append(f"{r.status} {r.url}") if r.status >= 400 else None)

        try:
            page.goto(base + "index.html")
            page.wait_for_function("document.body.classList.contains('local-data')", timeout=10000)
            page.locator("details.navgroup[data-group=data] summary").click()
            link = page.locator("details.navgroup[data-group=data] a[href$='data.html']")
            check(f"{store}: the Data menu has Manage on a local server", link.is_visible())
            shot(page, "menu")

            page.goto(base + "data.html")
            page.wait_for_selector(".dm-tile")
            badge = page.locator("#store").inner_text()
            check(f"{store}: the overview's store badge", (store == "files" and badge == "store: files")
                  or (store == "sqlite" and badge.startswith("store: SQLite") and "project.sqlite" in badge), badge)  # fmt: skip
            tiles = page.locator(".dm-tile strong").all_inner_texts()
            check(
                f"{store}: the settings tiles",
                tiles[:3] == ["configs", "goals", "fields"] and "validate.json" in tiles,
                tiles,
            )
            check(f"{store}: the data folders", "runs" in page.locator(".dm-data").inner_text())
            shot(page, "overview")
            page.fill("#dm-q", "lead1")
            page.wait_for_selector(".dm-hits li")
            check(
                f"{store}: find lists the files a name matches",
                "configs/tickets_lead1.yaml" in page.locator(".dm-hits").inner_text(),
            )
            shot(page, "find")

            page.goto(base + "data.html?path=configs")
            page.wait_for_selector(".dm-table")
            check(f"{store}: a settings folder lists its files and offers + New",
                  "tickets_lead1.yaml" in page.locator(".dm-table").inner_text() and page.locator(".dm-new").is_visible())  # fmt: skip
            shot(page, "folder")

            page.goto(base + "data.html?path=configs/tickets_lead1.yaml")
            page.wait_for_selector(".df-show dl.df-view")
            shown = page.locator(".df-show").inner_text()
            check(f"{store}: a setting shows its fields, not its YAML, and the runs made with it",
                  "config id" in shown and "tickets_lead1_v1" in shown and "sentences" in shown
                  and not page.locator(".dm-stored").evaluate("d => d.open")
                  and "1 run was made with this config" in page.locator(".dm-warn").inner_text()
                  and "sha256" in page.locator(".dm-meta").inner_text()
                  and page.get_by_role("link", name="Edit").is_visible() and page.get_by_role("button", name="Delete").is_visible(),
                  shown[:300])  # fmt: skip
            shot(page, "setting")

            # The form: a refused save, then a save of three changes.
            page.get_by_role("link", name="Edit").click()
            page.wait_for_selector(".df-row[data-at='config_id']")
            req = page.locator(".df-row[data-at='config_id'] .df-label").inner_text()
            dl = page.locator("#dl-datasets option").evaluate_all("os => os.map(o => o.value)")
            check(f"{store}: the form has a field per key, required ones marked, the project's datasets suggested",
                  req.endswith("*") and page.locator("[data-p='dataset_id']").get_attribute("list") == "dl-datasets"
                  and "tickets_v1" in dl and page.locator("[data-p='params.sentences']").input_value() == "1"
                  and page.locator("details.df-more").count() == 1 and page.locator("textarea, .dm-edit").count() == 0,
                  (req, dl))  # fmt: skip
            shot(page, "form")
            page.fill("[data-p='dataset_id']", "")
            page.click("#dm-save")
            page.wait_for_selector("#dm-result .dm-bad")
            err = page.locator(".df-row[data-at='dataset_id'] .df-err")
            check(f"{store}: an emptied required field is refused at its field and in the list; nothing saved",
                  err.is_visible() and "dataset id" in page.locator("#dm-result").inner_text()
                  and "edit=1" in page.url, (err.inner_text() if err.count() else "", page.locator("#dm-result").inner_text()))  # fmt: skip
            shot(page, "form-refused")
            page.fill("[data-p='dataset_id']", "tickets_v1")
            page.fill("[data-p='params.sentences']", "2")
            page.locator("details.df-more summary").click()
            page.fill("[data-p='goal']", "tickets_summary")
            page.locator(".df-row[data-at='params'] .df-addkey").click()
            page.fill("[data-rename='params.key1']", "temperature")
            page.locator("[data-rename='params.key1']").press("Tab")
            page.select_option("[data-retype='params.temperature']", "number")
            page.fill("[data-p='params.temperature']", "0.2")
            shot(page, "form-filled")
            page.click("#dm-save")
            page.wait_for_function(
                "(document.querySelector('.dm-note') || {}).textContent?.includes('Saved.')"
            )
            stored = page.locator(".dm-stored pre").text_content() or ""
            check(f"{store}: Save writes the three changes and keeps the file's comments",
                  stored.startswith('# Arm "lead1"') and "  sentences: 2" in stored and "goal: tickets_summary" in stored
                  and "  temperature: 0.2" in stored and "tickets_summary" in page.locator(".df-show").inner_text(), stored)  # fmt: skip
            shot(page, "saved")

            # A new goal in its form, created, then deleted.
            page.goto(base + "data.html?path=goals")
            page.wait_for_selector(".dm-new")
            page.click(".dm-new")
            page.wait_for_selector(".df-row[data-at='goal_id']")
            page.fill("[data-p='goal_id']", "draft_goal")
            page.fill("[data-p='title']", "A draft goal")
            page.fill("[data-p='statement']", "Drafts for people so that they decide.")
            page.fill("[data-p='decision']", "Which draft to keep.")
            page.fill("[data-p='success_criteria.primary.measure']", "overlap_f1")
            page.fill("[data-p='datasets.0.dataset_id']", "tickets_v1")
            page.locator(".df-row[data-at='datasets'] .df-add").click()
            two = page.locator(".df-card").count()
            page.locator(".df-card[data-at='datasets.1'] .df-del").click()
            check(
                f"{store}: a dataset card is added, then removed",
                two == 2 and page.locator(".df-card").count() == 1,
                two,
            )
            shot(page, "new-goal")
            page.click("#dm-save")
            page.wait_for_function(
                "(document.querySelector('.dm-note') || {}).textContent?.includes('Created.')"
            )
            check(f"{store}: Create creates it, its fields shown",
                  "Created." in page.locator(".dm-note").inner_text() and "A draft goal" in page.locator(".df-show").inner_text())  # fmt: skip
            page.get_by_role("button", name="Delete").click()
            page.wait_for_selector(".dm-confirm")
            check(
                f"{store}: Delete asks on the page, not in a browser dialog",
                "cannot be undone" in page.locator(".dm-confirm").inner_text(),
            )
            shot(page, "delete-confirm")
            page.click("#dm-yes")
            page.wait_for_function(
                "(document.querySelector('.dm-note') || {}).textContent?.includes('Deleted goals/draft_goal.yaml.')"
            )
            check(
                f"{store}: the goal is deleted and the folder says so",
                "Deleted goals/draft_goal.yaml." in page.locator(".dm-note").inner_text(),
            )

            # A run: its file read-only, then the run deleted.
            page.goto(base + "data.html?path=runs")
            page.wait_for_selector(".dm-table")
            run = page.locator(".dm-del").first.get_attribute("data-run") or ""
            shot(page, "runs")
            page.goto(base + f"data.html?path={run}/metrics.json")
            page.wait_for_selector(".dm-ro")
            check(f"{store}: a run's file is read-only and says what writes it",
                  "Written by" in page.locator(".dm-ro").inner_text() and page.get_by_role("link", name="Edit").count() == 0)  # fmt: skip
            shot(page, "run-file")
            page.goto(base + "data.html?path=runs")
            page.wait_for_selector(".dm-del")
            page.locator(f".dm-del[data-run='{run}']").click()
            page.wait_for_selector(".dm-confirm")
            check(
                f"{store}: deleting a run says what goes",
                "6 outputs and 6 rows go" in page.locator(".dm-confirm").inner_text(),
            )
            shot(page, "run-delete-confirm")
            page.click("#dm-yes")
            page.wait_for_function(
                "(document.querySelector('.dm-note') || {}).textContent?.includes('Deleted the run')"
            )
            check(
                f"{store}: the run is deleted",
                run not in page.locator(".dm-table").inner_text()
                if page.locator(".dm-table").count()
                else True,
            )

            # Phone width: nothing scrolls sideways.
            page.set_viewport_size({"width": 390, "height": 800})
            wide = []
            for url in ("data.html", "data.html?path=configs", "data.html?path=configs/tickets_lead1.yaml",
                        "data.html?path=configs/tickets_lead1.yaml&edit=1", "data.html?path=goals&new=1"):  # fmt: skip
                page.goto(base + url)
                page.wait_for_timeout(400)
                if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                    wide.append(url)
            check(f"{store}: at phone width no page scrolls sideways", not wide, wide)
            page.goto(base + "data.html?path=configs/tickets_lead1.yaml&edit=1")
            page.wait_for_selector(".df-row")
            shot(page, "phone-form")
            check(
                f"{store}: no console errors",
                not errors,
                " | ".join(errors[:5]) + " | " + " | ".join(failed[:5]),
            )

            # Opened from disk: the menu has no Manage.
            disk = browser.new_page()
            disk.goto((proj / ".build" / "catalog" / "index.html").as_uri())
            disk.wait_for_timeout(500)
            check(f"{store}: a page opened from disk does not show Manage",
                  not disk.locator("a[href$='data.html']").first.is_visible())  # fmt: skip
        except Exception:
            # what the page showed when a step failed: its text, the errors it logged, the requests that failed
            print(f"  page at {page.url}:\n" + page.locator("body").inner_text()[:1500])
            print("  console:", errors[:5], "failed requests:", failed[:5])
            raise
        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shots", type=Path, help="save a screenshot of every step here")
    args = ap.parse_args()
    try:
        import playwright  # noqa: F401, PLC0415
    except ImportError:
        print("  FAIL Playwright is not installed: `make browser-install` (requirements-browser.txt)")
        return 1
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    for store in ("files", "sqlite"):
        proj, env = setup(store)
        p, port = serve(proj, env)
        try:
            drive(store, f"http://127.0.0.1:{port}/.build/catalog/", proj, args.shots)
        finally:
            os.killpg(p.pid, 15)
            p.wait(timeout=30)
            shutil.rmtree(proj, ignore_errors=True)
    return summary()


if __name__ == "__main__":
    raise SystemExit(main())
