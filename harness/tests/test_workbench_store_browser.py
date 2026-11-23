#!/usr/bin/env python3
"""The Workbench's settings move a project's data into the store config.yaml names (W8; RFC-025): $0 and offline.

    python tests/test_workbench_store_browser.py

A project `evh init --store files --tutorial` makes, whose config.yaml a person then switches to `store: sqlite`. Behind
a real catalog-serve, on the settings screen: the store config.yaml names is said with its database not made yet; the
move's dry run (a data-migrate job) counts what would move, as `evh data-migrate --dry-run --json` does, and only then is
Move it offered; the move runs as a job while the server answers every other call with 503, which the page waits out
(a move this small ends before the page asks again, so the page's first two reads of the job are answered 503 here, as
the server answers them during a longer move); read again, the data is in the database and none of it is left under data/.
"""

from __future__ import annotations

import json
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
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _signin
import _serve  # noqa: E402
import _signin  # noqa: E402
import _slow  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-wbstore-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-wb-store")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_STORE", "EVAL_MAX_COST_USD", "EVH_FOR", "EVH_PUBLIC"):
    env.pop(k, None)


import _cli  # noqa: E402


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project."""
    return _cli.run(proj, env, *args, timeout=600)


def serve() -> tuple[subprocess.Popen, int, list[str]]:
    """catalog-serve on a free port; its startup lines once it answers."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL, encoding="utf-8",
    )  # fmt: skip
    lines: list[str] = []
    assert p.stdout is not None
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    return p, port, _serve.startup(p, lines)  # its start-up lines, the rest read as it comes


try:
    r = evh("init", "--store", "files", "--tutorial")
    r = r if r.returncode else evh("catalog")
    cfg = proj / "config.yaml"
    text = cfg.read_text(encoding="utf-8")
    check(
        "setup: a project in the files store, with the tutorial's settings, and its catalog",
        r.returncode == 0 and "store: files" in text,
        r.stderr[-300:],
    )
    cfg.write_text(
        re.sub(r"^store: files\b", "store: sqlite", text, count=1, flags=re.M), encoding="utf-8"
    )  # the person's edit
    before = sorted(str(x.relative_to(proj / "data")) for x in (proj / "data").rglob("*") if x.is_file())
    cli = evh("data-migrate", "--to", "sqlite", "--dry-run", "--json")
    counted = (
        (json.loads(cli.stdout.splitlines()[-1]).get("result") or {}).get("values") or {}
        if cli.returncode == 0
        else {}
    )

    from playwright.sync_api import sync_playwright

    srv, port, lines = serve()
    try:
        link = _signin.link(lines)
        with sync_playwright() as pw:
            browser = _slow.launch(pw)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list = []
            waited: list = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("response", lambda resp: waited.append(resp.url) if resp.status == 503 else None)
            page.goto(str(link))
            page.wait_for_selector("h1", timeout=20000)
            page.goto(f"http://127.0.0.1:{port}/workbench/#settings")
            page.wait_for_selector("#mv-dry", timeout=20000)
            check(
                "the settings say the store config.yaml names, its database not made yet; Move it is off before a dry run",
                "config.yaml names sqlite" in page.locator("main").inner_text()
                and "not made yet" in page.locator("main").inner_text()
                and page.locator("#mv-run").is_disabled(),
                page.locator("main").inner_text()[:500],
            )
            page.fill("#st-by", "tester")
            page.click("#mv-dry")
            page.wait_for_selector("#mv-st-out pre, #mv-st-out [role=alert]", timeout=60000)
            dry = page.locator("#mv-st-out").inner_text()
            check(
                "Count what would move: data-migrate's dry run as a job, the counts evh data-migrate --dry-run --json gives "
                "as values; then Move it is offered; nothing moved",
                counted.get("files", 0) > 0
                and f"{counted['files']} file(s)" in dry
                and page.locator("#mv-run").is_enabled()
                and not (proj / "data" / "project.sqlite").exists(),
                (dry[:300], counted, cli.stderr[-300:]),
            )
            served: list = []

            def busy(route) -> None:
                """The job's first two reads during the move, answered as a migrating server answers them."""
                if route.request.method == "GET" and len(served) < 2:
                    served.append(route.request.url)
                    route.fulfill(
                        status=503,
                        headers={"Retry-After": "1", "Content-Type": "application/json"},
                        body='{"error": "a migration holds the project; try again when it ends"}',
                    )
                else:
                    route.continue_()

            page.route(re.compile(r".*/api/v1/jobs/[^/]+$"), busy)
            page.click("#mv-run")
            page.wait_for_selector("#mv-st-out:has-text('Moved.'), #mv-st-out [role=alert]", timeout=300000)
            left = sorted(
                str(x.relative_to(proj / "data")) for x in (proj / "data").rglob("*") if x.is_file()
            )
            check(
                "Move it: the move runs as a job (the page waits out the server's 503s), the data is in the database and "
                "none of it is left under data/",
                len(served) == 2
                and "Moved." in page.locator("#mv-st-out").inner_text()
                and (proj / "data" / "project.sqlite").is_file()
                and not [x for x in left if not x.startswith("project.sqlite")],
                (page.locator("#mv-st-out").inner_text()[:400], left[:10], len(before), len(waited)),
            )
            page.click("#mv-st-out [data-again]")
            page.wait_for_function(
                "() => /config.yaml names sqlite: one database/.test(document.querySelector('main').textContent)"
                " && /bytes/.test(document.querySelector('main').textContent)",
                timeout=20000,
            )
            check(
                "read again: the database and its size; no page error",
                "data/project.sqlite" in page.locator("main").inner_text() and not errors,
                (page.locator("main").inner_text()[:400], errors[:2]),
            )
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=20)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
