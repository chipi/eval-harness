#!/usr/bin/env python3
"""The Workbench on its server (RFC-032 step 1): catalog-serve serves it under /workbench/, and it reads the project
through the model's API.

    python tests/test_workbench_live.py

In a project with a goal, a dataset, its reference and a run: the startup prints the link that signs in; through it the
home lists the project's goal with the next step its status names; the goal's screen shows its dataset as the API
says; a screen not wired yet says so instead of showing the mockup's data; a browser with no cookie is asked to sign
in; at a phone's width nothing scrolls sideways; and a public server has no /workbench/.
"""

from __future__ import annotations

import os
import re
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
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-wblive-"))
env = dict(
    os.environ,
    EVH_ACTOR="person:tester",
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-wb-live",
    EVAL_STORE="files",
)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project."""
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def serve(*extra: str) -> tuple[subprocess.Popen, int, list[str]]:
    """catalog-serve on a free port; its startup lines once it answers."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port), *extra], cwd=proj, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    lines: list[str] = []
    assert p.stdout is not None
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    if "--public" in extra:
        return p, port, lines
    while line := p.stdout.readline():  # the startup's lines, up to its last
        lines.append(line.rstrip())
        if "reads the runs once" in line:
            break
    return p, port, lines


try:
    r = evh("init", "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    (proj / "data" / "configs" / "one_v1.yaml").write_text(
        "config_id: one_v1\ndataset_id: tk_v1\nparams:\n  provider: echo\n  sentences: 1\n"
    )
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        ("label-import", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t"),
        ("reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold", "--reason", "the kit's summaries, for the test", "--by", "t"),
        ("run", "--config", "data/configs/one_v1.yaml"),
        ("goal-new", "tickets_summary", "--set", "title=Ticket summaries", "--set", "statement=A one-line summary of a ticket.",
         "--set", "decision=Which system writes it.", "--set", "success_criteria.primary.measure=overlap_f1",
         "--set", "success_criteria.primary.direction=higher", "--set", "datasets.0.dataset_id=tk_v1", "--set", "datasets.0.role=test"),
        ("catalog",),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    check(
        "setup: a goal, its dataset, reference and run, and the catalog",
        r.returncode == 0,
        (r.stdout + r.stderr)[-300:],
    )

    from playwright.sync_api import sync_playwright

    srv, port, lines = serve()
    try:
        link = next(
            (
                m.group(0)
                for ln in lines
                if (m := re.search(r"http://\S+/api/v1/session\?token=\S+&next=/workbench/", ln))
            ),
            None,
        )
        check("the startup prints the Workbench's sign-in link", link is not None, lines)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(str(link))
            page.wait_for_selector("table >> text=Ticket summaries", timeout=20000)
            page.wait_for_function(
                "() => !document.querySelector('main').textContent.includes('…')", timeout=20000
            )
            home = page.locator("main").inner_text()
            check(
                "the home lists the project's goal and the next step its status names, read through the API",
                "Ticket summaries" in home
                and "promote a baseline on tk_v1" in home
                and "Nothing is running." in home
                and not errors,
                (home[:400], errors[:2]),
            )
            page.click("text=Ticket summaries")
            page.wait_for_selector("h1:has-text('Ticket summaries')", timeout=20000)
            goal = page.locator("main").inner_text()
            check(
                "the goal's screen shows its dataset, reference and run as the API says",
                "tk_v1" in goal
                and "gold/tk_v1" in goal
                and "1 run(s)" in goal
                and "promote a baseline on tk_v1" in goal,
                goal[:500],
            )
            page.goto(f"http://127.0.0.1:{port}/workbench/#dataset")
            page.wait_for_selector("h1", timeout=20000)
            check(
                "a screen not wired yet says so, and shows none of the mockup's data",
                "This screen comes later" in page.locator("main").inner_text()
                and "cnn_dailymail" not in page.content(),
                page.locator("main").inner_text()[:200],
            )
            phone = browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                storage_state=page.context.storage_state(),
            ).new_page()
            phone.goto(f"http://127.0.0.1:{port}/workbench/#home")
            phone.wait_for_selector("table >> text=Ticket summaries", timeout=20000)
            over = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check("at a phone's width the home does not scroll sideways", over <= 0, over)
            stranger = browser.new_context().new_page()
            stranger.goto(f"http://127.0.0.1:{port}/workbench/")
            stranger.wait_for_selector("h1:has-text('Sign in')", timeout=20000)
            check(
                "a browser with no cookie is asked to sign in, and reads nothing",
                "Ticket summaries" not in stranger.content(),
            )
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=20)

    pub, pport, _ = serve("--public", "evals.example")
    try:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            f"http://127.0.0.1:{pport}/workbench/", headers={"Host": "evals.example"}
        )
        try:
            code = urllib.request.urlopen(req, timeout=30).status  # noqa: S310 - the test's own server  # nosec B310
        except urllib.error.HTTPError as exc:
            code = exc.code
        check("a public server has no /workbench/", code == 404, code)
    finally:
        pub.terminate()
        pub.wait(timeout=20)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
