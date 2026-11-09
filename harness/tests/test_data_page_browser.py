#!/usr/bin/env python3
"""The data page in a real browser (headless Chromium, through Playwright), on both stores (UXS-004).

    python tests/test_data_page_browser.py                 the checks
    python tests/test_data_page_browser.py --shots DIR     the checks, and a screenshot of every step in DIR

In a tutorial project served by a local catalog-serve, kept as files and then moved into its database:

  - a SQLite project that deploys Configure (`configure: true`): the header has Configure, a menu of its own beside
    the catalog's (its Data menu as it was); a page opened from disk does not show it. A files project: no Configure
    in its menus, no data.html, nothing served at /api/data;
  - the overview: the store badge, the settings tiles, the data folders; finding a file by name;
  - a folder of settings, and its "+ New";
  - a setting: its fields (not its YAML), the runs made with it, its sha256, Edit and Delete; the file as stored
    behind a disclosure; a run's file read-only, with what writes it;
  - the form: a field per key, required ones marked, the project's datasets suggested; an emptied required field is
    refused at its field and in the list, nothing saved; a number changed, an optional field set from "more fields",
    a parameter added (its key, its type, its value), saved: the file keeps its comments;
  - a new goal in its form: fields filled, a dataset card added and removed, Create, then Delete through the page's
    own confirmation;
  - every kind of setting through the page alone (an arm config, a fieldset, a judge scorer, a model record, a
    failure-mode list, the validate policy; the goal above): created in its form, a value changed, deleted; the
    harness's own check (evh validate) reads what the page created; in SQLite everything stays in the database;
  - deleting a run, after the panel says what goes;
  - the catalog's rebuild from the page: the line says when it was built, Rebuild runs it, and the Goals page shows
    a goal's title changed in the form; the catalog is served throughout;
  - in the dark theme (the catalog's default) every page and the form paint dark: no field, card or panel on a
    light ground, every label, help line, error and control's text at a contrast of at least 3.5 against its ground;
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

#: Each store's environment, for the commands the walk runs to check what the page wrote (set by main).
ENV: dict[str, dict] = {}


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
            # Without the server's token (RFC-026) the page says how to get in; the printed Configure link sets it.
            anon = browser.new_page()
            anon.goto(base + "data.html")
            anon.wait_for_selector(".dm-notice")
            check(f"{store}: without the token, the page names the Configure link catalog-serve prints",
                  "Configure link" in anon.locator(".dm-notice").inner_text())  # fmt: skip
            anon.close()
            token = (proj / ".build" / "api-token").read_text().strip()
            root = base.split("/.build/")[0]
            page.goto(f"{root}/api/v1/session?token={token}&next=/.build/catalog/data.html")
            page.wait_for_selector(".dm-tile")
            check(
                f"{store}: the Configure link sets the token's cookie and opens the page",
                page.url == base + "data.html",
                page.url,
            )
            page.goto(base + "index.html")
            page.wait_for_function("document.body.classList.contains('local-data')", timeout=10000)
            link = page.locator("nav.nav > a[href$='data.html']")
            page.locator("details.navgroup[data-group=data] summary").click()
            data_menu = page.locator("details.navgroup[data-group=data] .navlist").inner_text()
            check(f"{store}: Configure is a menu of its own on a local server; the Data menu is the catalog's",
                  link.is_visible() and link.inner_text() == "Configure" and "Manage" not in data_menu
                  and "Configure" not in data_menu, data_menu)  # fmt: skip
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
                  and page.locator(".df-form > .df-group > details.df-more").count() == 1 and page.locator("textarea, .dm-edit").count() == 0,
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
            page.locator(".df-form > .df-group > details.df-more > summary").click()
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

            # Every kind of setting through the page alone: created in its form, a value changed, deleted.
            def save_and_wait(word: str) -> str:
                page.click("#dm-save")
                page.wait_for_function(
                    f"(document.querySelector('.dm-note') || {{}}).textContent?.includes({word!r})"
                    " || !!document.querySelector('#dm-result .dm-bad')"
                )
                bad = page.locator("#dm-result .dm-bad")
                return bad.inner_text() if bad.count() else ""

            def unfold() -> None:
                # "more fields" opened, as a person would click it: the form folds what a setting does not set
                page.evaluate(
                    "document.querySelectorAll('#dm-form details.df-more').forEach(d => d.open = true)"
                )

            def add(at: str) -> None:
                unfold()
                page.locator(f".df-row[data-at='{at}'] .df-add").first.click()

            def fill(sel: str, value: str) -> None:
                unfold()
                page.fill(sel, value)

            def fill_config() -> None:
                fill("#dm-name", "ui_arm")
                fill("[data-p='config_id']", "ui_arm_v1")
                fill("[data-p='dataset_id']", "tickets_v1")
                fill("[data-p='params.provider']", "echo")

            def fill_fieldset() -> None:
                fill("[data-p='fieldset_id']", "ui_fields")
                add("fields")
                fill("[data-p='fields.0.name']", "channel")
                page.select_option("[data-p='fields.0.type']", label="choice")
                add("fields.0.values")
                fill("[data-p='fields.0.values.0']", "email")
                unfold()
                page.locator(".df-row[data-at='fields.0.values'] .df-add").click()
                fill("[data-p='fields.0.values.1']", "chat")

            def fill_scorer() -> None:
                fill("[data-p='scorer_id']", "ui_scorer")
                fill("[data-p='dataset_id']", "tickets_v1")
                for i, family in (
                    (0, "vendor_a"),
                    (1, "vendor_b"),
                ):  # two judges of two families (ADR-0001 §4)
                    page.locator(".df-row[data-at='judges'] .df-add").last.click()
                    fill(f"[data-p='judges.{i}.id']", f"j{i}")
                    unfold()
                    page.select_option(f"[data-p='judges.{i}.params.provider']", label="fake")
                    fill(f"[data-p='judges.{i}.params.model']", f"fake-{i}")
                    fill(f"[data-p='judges.{i}.params.usd_per_mtok_in']", "0")
                    fill(f"[data-p='judges.{i}.params.usd_per_mtok_out']", "0")
                    fill(f"[data-p='judges.{i}.params.family']", family)
                fill("[data-p='prompt.file']", "tutorial/judge_prompt.txt")

            def fill_model() -> None:
                fill("[data-p='model_id']", "ui_model")
                add("aliases")
                fill("[data-p='aliases.0']", "echo")

            def fill_modes() -> None:
                fill("[data-p='failure_modes_id']", "ui_modes")
                add("modes")
                fill("[data-p='modes.0.id']", "invented-fact")

            kinds = {
                "configs/ui_arm.yaml": fill_config,
                "fields/ui_fields.yaml": fill_fieldset,
                "scorers/ui_scorer.yaml": fill_scorer,
                "models/ui_model.yaml": fill_model,
                "failure-modes/ui_modes.yaml": fill_modes,
            }
            made, edited, gone = [], [], []
            for target, fill_kind in kinds.items():
                folder = target.split("/")[0]
                page.goto(base + f"data.html?path={folder}&new=1")
                page.wait_for_selector(".df-row")
                fill_kind()
                said = save_and_wait("Created.")
                if said or "Created." not in page.locator(".dm-note").inner_text():
                    made.append((target, said[:300]))
                    continue
                if target == "configs/ui_arm.yaml":
                    shot(page, "created-arm")
            check(
                f"{store}: every kind of setting is created in its form, through the page alone",
                not made,
                made,
            )
            change = {"configs/ui_arm.yaml": ("config_id", "ui_arm_v2"), "fields/ui_fields.yaml": ("fields.0.label", "Channel"),
                      "scorers/ui_scorer.yaml": ("judges.0.params.model", "fake-b"), "models/ui_model.yaml": ("aliases.0", "echo-2"),
                      "failure-modes/ui_modes.yaml": ("modes.0.label", "Invented fact")}  # fmt: skip
            for target, (field, value) in change.items():
                page.goto(base + f"data.html?path={target}&edit=1")
                page.wait_for_selector(".df-row")
                fill(f"[data-p='{field}']", value)
                said = save_and_wait("Saved.")
                if said or value not in page.locator(".df-show").inner_text():
                    edited.append((target, said[:200]))
            # the validate policy: its tile opens it, or a new one when the project has none
            page.goto(base + "data.html")
            page.wait_for_selector(".dm-tile")
            page.locator(".dm-tile", has_text="validate.json").click()
            page.wait_for_selector(".df-row, .df-show")
            if page.locator(".df-show").count():
                page.get_by_role("link", name="Edit").click()
                page.wait_for_selector(".df-row")
            add("committed")
            page.locator("[data-p^='committed.']").last.fill("runs")
            said = save_and_wait("aved.") if "new=1" not in page.url else save_and_wait("Created.")
            policy = page.locator(".df-show").inner_text() if page.locator(".df-show").count() else ""
            if said or "runs" not in policy:
                edited.append(("validate.json", said[:200] or policy[:200]))
            check(
                f"{store}: every kind's setting takes a change through its form (the validate policy too)",
                not edited,
                edited,
            )
            import subprocess as _sp  # noqa: PLC0415

            v = _sp.run([sys.executable, "-m", "evaluation_harness", "validate"], cwd=proj, env=os.environ | ENV[store],
                        capture_output=True, text=True, check=False)  # fmt: skip
            check(f"{store}: evh validate reads what the page created and passes", v.returncode == 0,
                  (v.stdout + v.stderr)[-600:])  # fmt: skip
            for target in kinds:
                page.goto(base + f"data.html?path={target}")
                page.wait_for_selector(".dm-del-file")
                page.click(".dm-del-file")
                page.wait_for_selector(".dm-confirm")
                page.click("#dm-yes")
                page.wait_for_function(
                    "(document.querySelector('.dm-note') || {}).textContent?.includes('Deleted')"
                )
                if (
                    page.request.get(
                        base.replace(".build/catalog/", "") + f"api/data/file?path={target}"
                    ).status
                    != 404
                ):
                    gone.append(target)
            check(f"{store}: each one is deleted through the page", not gone, gone)
            if store == "sqlite":
                on_disk = sorted(x.name for x in (proj / "data").iterdir())
                check(f"{store}: everything the page wrote is in the database (data/ on disk holds only it)",
                      all(n.startswith("project.sqlite") for n in on_disk), on_disk)  # fmt: skip

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

            # The catalog's rebuild: a goal's title changed in the form, then shown on the Goals page once rebuilt.
            page.goto(base + "data.html?path=goals/tickets_summary.yaml&edit=1")
            page.wait_for_selector("[data-p='title']")
            page.fill("[data-p='title']", "Ticket summaries, renamed on the data page")
            page.click("#dm-save")
            page.wait_for_function(
                "(document.querySelector('.dm-note') || {}).textContent?.includes('Saved.')"
            )
            page.wait_for_selector("#dm-rebuild-go")
            before = page.locator("#dm-rebuild").inner_text()
            page.click("#dm-rebuild-go")
            page.wait_for_function(
                "(document.getElementById('dm-rebuild') || {}).textContent?.includes('Rebuilding')",
                timeout=10000,
            )
            shot(page, "rebuilding")
            served = page.request.get(base + "index.html").status
            page.wait_for_function(
                "(document.getElementById('dm-rebuild') || {}).textContent?.includes('Rebuilt in')",
                timeout=300000,
            )
            shot(page, "rebuilt")
            goals = page.request.get(base + "goals.html").text()
            check(f"{store}: the page rebuilds the catalog: the Goals page shows the new title, the catalog served throughout",
                  "were built" in before and served == 200 and "Ticket summaries, renamed on the data page" in goals,
                  (before, served))  # fmt: skip

            # The dark theme, the catalog's default: every page and the form paint dark.
            page.emulate_media(color_scheme="dark")
            light: list = []
            for url, name in (("data.html", "dark-overview"), ("data.html?path=configs/tickets_lead1.yaml", "dark-setting"),
                              ("data.html?path=configs/tickets_lead1.yaml&edit=1", "dark-form"),
                              ("data.html?path=goals&new=1", "dark-new-goal"), ("data.html?path=runs", "dark-runs")):  # fmt: skip
                page.goto(base + url)
                page.wait_for_selector(".dm-tile, .df-row, .df-show, .dm-table")
                if "edit=1" in url:
                    page.fill("[data-p='dataset_id']", "")
                    page.click("#dm-save")
                    page.wait_for_selector("#dm-result .dm-bad")
                page.wait_for_timeout(400)  # past the buttons' colour transition
                bright = page.evaluate("""() => {
                  const rgba = c => { const m = c.match(/[\\d.]+/g) || [0, 0, 0, 0]; const [r, g, b, a = 1] = m.map(Number); return {r, g, b, a}; };
                  const L = ({r, g, b}) => [r, g, b].map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; })
                    .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
                  const page = rgba(getComputedStyle(document.body).backgroundColor);
                  const out = [];
                  if (L(page) > 0.2) out.push('body on a light ground');
                  document.querySelectorAll('input, select, textarea, .df-card, .dm-confirm, .dm-text, button, .tile, label, .df-help, .df-err, .dm-bad').forEach(el => {
                    const cs = getComputedStyle(el);
                    const own = rgba(cs.backgroundColor), ground = own.a >= 0.5 ? own : page;
                    const fg = L(rgba(cs.color)), bg = L(ground);
                    const ratio = (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
                    const field = /^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName) || el.matches('.df-card, .dm-confirm, .dm-text, .tile');
                    if ((field && bg > 0.2) || ratio < 3.5) out.push(`${el.tagName}.${el.className} contrast ${ratio.toFixed(1)}`);
                  });
                  return out.slice(0, 5);
                }""")
                if bright:
                    light.append((url, bright))
                shot(page, name)
            check(
                f"{store}: in the dark theme every page and the form paint dark, every text readable (contrast >= 3.5)",
                not light,
                light,
            )
            page.emulate_media(color_scheme="light")

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

            # Opened from disk: the menu has no Configure.
            disk = browser.new_page()
            disk.goto((proj / ".build" / "catalog" / "index.html").as_uri())
            disk.wait_for_timeout(500)
            check(f"{store}: a page opened from disk does not show Configure",
                  not disk.locator("a[href$='data.html']").first.is_visible())  # fmt: skip
        except Exception:
            # what the page showed when a step failed: its text, the errors it logged, the requests that failed
            print(f"  page at {page.url}:\n" + page.locator("body").inner_text()[:1500])
            print("  console:", errors[:5], "failed requests:", failed[:5])
            raise
        browser.close()


def files_case(base: str) -> None:
    """A files project deploys no Configure: not in its menus, no page, nothing served."""
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(base + "index.html")
        page.wait_for_timeout(800)
        nav = page.locator("nav.nav").inner_html()
        status = page.request.get(base + "data.html").status
        api = page.request.get(base.replace(".build/catalog/", "") + "api/data/store").status
        browser.close()
    check(
        "files: no Configure in the menus, no data.html, nothing at /api/data",
        "data.html" not in nav and "Configure" not in nav and status == 404 and api == 404,
        (status, api),
    )


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
        ENV[store] = env
        p, port = serve(proj, env)
        try:
            base = f"http://127.0.0.1:{port}/.build/catalog/"
            if store == "files":
                files_case(base)
            else:
                drive(store, base, proj, args.shots)
        finally:
            os.killpg(p.pid, 15)
            p.wait(timeout=30)
            shutil.rmtree(proj, ignore_errors=True)
    return summary()


if __name__ == "__main__":
    raise SystemExit(main())
