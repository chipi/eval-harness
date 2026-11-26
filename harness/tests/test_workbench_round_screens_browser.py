#!/usr/bin/env python3
"""The Workbench's round and system screens, as the 0.8.1 newcomer scenario (step 14) found them wanting.

    python tests/test_workbench_round_screens_browser.py

A goal whose only round (r1) ran on the validation side of its dataset (a study's rounds do), carried one system, and is
closed. Behind a real catalog-serve:

  - Open the next round "On" the dataset itself: the arm is not offered (a run on another dataset is never carried in:
    `round-open --keep` refuses it), and the screen says where it did run and what to do; On that validation side it is
    offered;
  - Close a round: dismissing the browser's confirm says on the page that the round was not closed, and changes nothing;
  - Make a system from a model: a project with no model record says why no model is listed and how to get one (a record,
    or a clone of a system);
  - The eval screen's chart reads start as soon as the round is known, not after every other read of the screen has
    landed (the scenario: "Reading the chart…" 2.5 s after load).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _signin
import _cli  # noqa: E402
import _serve  # noqa: E402
import _signin  # noqa: E402
import _slow  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-wbrounds-"))
env = dict(
    os.environ,
    EVH_ACTOR="person:tester",
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-wb-rounds",
    EVAL_STORE="files",
)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args: str) -> subprocess.CompletedProcess:
    return _cli.run(proj, env, *args, timeout=600)


def serve() -> tuple[subprocess.Popen, int, list[str]]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL, encoding="utf-8",
    )  # fmt: skip
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    return p, port, _serve.startup(p, [])


try:
    r = evh("init", "--store", "files", "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    (proj / "data" / "systems" / "one_v1.yaml").write_text(
        "system_id: one_v1\nparams:\n  provider: echo\n  sentences: 1\n", encoding="utf-8"
    )
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        ("dataset-split", "--dataset-id", "tk_v1", "--test", "0.4", "--seed", "3"),
        ("dataset-materialize", "--dataset-id", "tk_v1_validation"),
        ("run", "--system", "one_v1", "--dataset", "tk_v1_validation"),
        ("goal-new", "tickets_summary", "--set", "title=Ticket summaries", "--set", "statement=A one-line summary of a ticket.",
         "--set", "decision=Which system writes it.", "--set", "success_criteria.primary.measure=overlap_f1",
         "--set", "success_criteria.primary.direction=higher", "--set", "datasets.0.dataset_id=tk_v1",
         "--set", "datasets.0.role=pilot", "--set", "datasets.1.dataset_id=tk_v1_validation", "--set", "datasets.1.role=validation"),
        ("round-open", "--goal", "tickets_summary", "--dataset", "tk_v1_validation", "--hypothesis",
         "Does one sentence hold up on the validation side?", "--keep", "one_v1"),
        ("round-close", "--goal", "tickets_summary", "--round", "r1", "--conclusion", "one sentence is enough for now",
         "--by", "person:tester"),
        ("catalog",),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    check(
        "setup: a goal whose r1 ran on its validation side, closed",
        r.returncode == 0,
        (r.stdout + r.stderr)[-300:],
    )

    from playwright.sync_api import sync_playwright

    srv, port, lines = serve()
    try:
        link = _signin.link(lines)
        with sync_playwright() as pw:
            browser = _slow.launch(pw)
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            errors: list = []

            def fresh():
                """A new page of the signed-in context: the open form holds an unsent choice, and leaving asks first."""
                pg = ctx.new_page()
                pg.on("pageerror", lambda e: errors.append(str(e)))
                return pg

            page = fresh()
            page.goto(str(link))
            page.wait_for_selector("h1:has-text('Your goals')", timeout=20000)
            base = f"http://127.0.0.1:{port}/workbench/"

            # 1. the next round's offer, On the dataset itself and On the side r1 ran on
            page.goto(f"{base}#eval/tickets_summary")
            page.wait_for_selector("#ro-carry", timeout=20000)
            page.wait_for_function(
                "() => !document.querySelector('#ro-carry').textContent.includes('Reading')", timeout=20000
            )
            carry = page.locator("#ro-carry").inner_text()
            check(
                "Open the next round On tk_v1: the arm of r1 is not offered, and the screen says where r1 ran it and that a "
                "run is not carried to another dataset",
                page.locator("#ro-carry input[name=ro-keep]").count() == 0
                and "one_v1" in carry
                and "not offered: no run on tk_v1" in carry
                and "tk_v1_validation" in carry
                and "another dataset" in carry,
                carry,
            )
            page.select_option("#ro-ds", "tk_v1_validation")
            page.wait_for_selector("#ro-carry input[name=ro-keep][value=one_v1]", timeout=20000)
            check(
                "On the side r1 ran on, the arm is offered and ticked",
                page.locator("#ro-carry input[name=ro-keep][value=one_v1]").is_checked()
                and "not offered" not in page.locator("#ro-carry").inner_text(),
            )

            # 3. a project with no model record
            page = fresh()
            page.goto(f"{base}#systems/tickets_summary")
            try:
                page.wait_for_selector("#sn-model", timeout=8000)
            except Exception:
                print("MAIN", page.locator("main").inner_text()[:500], page.url)
                raise
            why = page.locator("[data-form=system-new]").inner_text()
            check(
                "Make a system from a model, with no model record in the project: the screen says why no model is listed "
                "(a model is listed when it has a record that says where it runs) and the two ways on (bring in a model, "
                "or clone a system)",
                "model record" in why and "Clone it, change one thing" in why and "Bring in a model" in why,
                why,
            )

            # 2. Close the round: the confirm dismissed says so on the page; nothing else changes
            r = evh(
                "round-open", "--goal", "tickets_summary", "--dataset", "tk_v1_validation", "--from", "r1",
                "--hypothesis", "Does a second sentence help?", "--keep", "one_v1",
            )  # fmt: skip
            check("the second round is open", r.returncode == 0, (r.stdout + r.stderr)[-300:])
            page = fresh()
            asked: list = []
            page.on("dialog", lambda d: (asked.append(d.message), d.dismiss()))
            page.goto(f"{base}#eval/tickets_summary/r2")
            page.wait_for_selector("#rc-close", timeout=20000)
            page.fill("#rc-text", "The second sentence adds nothing here.")
            page.fill("#ev-by", "tester")
            page.click("#rc-close")
            page.wait_for_timeout(500)
            out = page.locator("#rc-out").inner_text()
            r2 = yaml.safe_load(
                (proj / "data" / "rounds" / "tickets_summary" / "r2.yaml").read_text(encoding="utf-8")
            )
            check(
                "Close the round, the confirm dismissed: the page says the round was not closed, beside the button; the "
                "round stays open and the conclusion typed stays",
                asked
                and "not closed" in out.lower()
                and r2.get("status") == "open"
                and page.locator("#rc-text").input_value() == "The second sentence adds nothing here.",
                (asked, out, r2.get("status")),
            )

            # 4. the charts' reads start once the round is known, while the evidence read is still on its way
            page = fresh()
            held: list = []
            chart_asked: list = []

            def hold_evidence(route) -> None:
                held.append(route)

            page.route("**/api/v1/goals/tickets_summary/rounds/r2/evidence", hold_evidence)
            page.on("request", lambda q: chart_asked.append(q.url) if "/api/v1/charts/" in q.url else None)
            t0 = time.time()
            page.goto(f"{base}#eval/tickets_summary/r2")
            page.wait_for_function(
                "() => !document.querySelector('main')?.textContent.includes('Opening')", timeout=20000
            )
            for _ in range(40):
                if chart_asked:
                    break
                page.wait_for_timeout(100)
            check(
                "the eval screen asks for its charts while the round's evidence read is still held: no chart waits for the "
                "screen's other reads",
                len(held) >= 1 and len(chart_asked) >= 1,
                (len(held), chart_asked),
            )
            for route in held:
                route.continue_()
            page.unroute("**/api/v1/goals/tickets_summary/rounds/r2/evidence")
            page.wait_for_function(
                "() => !document.querySelector('[data-lands]') && !/Reading|Opening/.test(document.querySelector('main').textContent)",
                timeout=30000,
            )
            print(f"INFO  load to every chart drawn, a tiny project, evidence held: {time.time() - t0:.2f}s")
            check("no page error", not errors, errors[:2])
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=20)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
